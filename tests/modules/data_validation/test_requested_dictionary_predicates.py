from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.storage import DOC_FIELDS
from auto_check.modules.data_validation.semantic_grounding import apply_dictionary_answers, dictionary_partition_question
from auto_check.modules.data_validation.text_requirements import bind_named_dictionary_requirements
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_latency_pipeline import combined
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


FIELDS = [('row_id', '记录编号', 'varchar', 'Y'), ('day', '数据日期', 'date', ''),
          ('channel', '流转渠道', 'varchar', ''), ('mode', '分拣方式', 'varchar', '')]


def proposal(scope_code='01', op='eq', value='07'):
    return {'business_key': 'row_id', 'rule_name': '分拣复核', 'rule_type': 'field_compare',
            'expression': {'left': 'mode', 'op': op, 'right_type': 'value', 'right': value},
            'violation_message': '分拣方式待复核', 'null_policy': 'skip',
            'semantic_intent': {'metrics': [{'side': 'left', 'term': '分拣方式', 'fields': ['mode']}],
                                'scopes': [{'category': '流转渠道', 'fields': ['channel'], 'memberships': {
                                    'channel': {'include': [scope_code], 'exclude': ['02' if scope_code == '01' else '01']}}}],
                                'open_questions': []}}


def service_with_replies(draft, count):
    rules, model = _rules_with_doc([combined(deepcopy(draft)) for _ in range(count)], fields=FIELDS)
    with rules.storage.database.begin() as conn:
        for name, dictionary in [('channel', '01-零售\n02-批发'), ('mode', '07-人工\n08-自动')]:
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == name).values(dictionary=dictionary))
    return rules, model


def parse(draft, request):
    rules, model = service_with_replies(draft, 3)
    return rules.parse_rule_request(user(), _request(request_text=request, analysis_protocol=2)), model


@pytest.mark.parametrize('scope_code,op,value', [('02', 'eq', '07'), ('01', 'neq', '07'), ('01', 'eq', '08')])
def test_request_names_dictionary_scope_and_forbidden_code(scope_code, op, value):
    result, model = parse(proposal(scope_code, op, value), '流转渠道为零售的记录，分拣方式不应为人工。')
    assert len(model.calls) == 1 and result['preview'] and not result['questions']
    definition = result['preview']['definition']
    assert definition['filters'] == [{'table': 'base', 'field': 'channel', 'op': 'eq', 'value': '01', 'confirmed': True}]
    assert definition['expression'] == {'left': 'mode', 'right_type': 'value', 'op': 'eq', 'right': '07'}


def test_request_names_required_code_and_negated_scope():
    result, _ = parse(proposal(), '流转渠道不是零售的记录，分拣方式应为自动。')
    assert result['preview']['definition']['filters'][0]['value'] == '02'
    assert result['expression'] == {'left': 'mode', 'op': 'neq', 'right_type': 'value', 'right': '08'}


@pytest.mark.parametrize('text,labels', [
    ('零售的记录请复核。', '01-零售\n02-批发'),
    ('流转渠道为“零售”或“批发”的记录请复核。', '01-零售\n02-批发'),
    ('流转渠道为零售或流转渠道为批发的记录请复核。', '01-零售\n02-批发'),
])
def test_ambiguous_or_unnamed_scope_is_not_rebound(text, labels):
    draft = proposal(scope_code='02')
    original = deepcopy(draft)
    bind_named_dictionary_requirements(draft, [{'field_name': 'channel', 'field_cn': '流转渠道',
                                              'data_type': 'varchar', 'dictionary': labels}], [], text)
    assert draft == original


@pytest.mark.parametrize('dtype,zero', [('int', 0), ('text', '00')])
def test_document_code_zero_preserves_its_type_and_explicit_filter(dtype, zero):
    draft = proposal('02', 'neq', '07')
    draft['filters'] = [{'field': 'channel', 'op': 'eq', 'value': '02'}]
    fields = [{'field_name': name, 'field_cn': label, 'data_type': dtype, 'dictionary': '00-默认\n02-变更'}
              for name, label in [('channel','流转渠道'), ('mode','分拣方式')]]
    bind_named_dictionary_requirements(draft, fields, [], '流转渠道为默认的记录，分拣方式不得为默认。')
    assert draft['filters'][0]['value'] == zero
    assert draft['expression']['right'] == zero and draft['expression']['op'] == 'eq'


def test_repeated_invalid_partition_offers_document_codes_and_applies_actual_choice():
    draft = proposal()
    scope = draft['semantic_intent']['scopes'][0]
    scope.update(category='门店渠道', memberships={'channel': {'include': ['到店'], 'exclude': ['未设置']}})
    rules, _ = service_with_replies(draft, 8)
    request = _request(request_text='到门店的记录，分拣方式不得为人工。', analysis_protocol=2)
    initial = rules.parse_rule_request(user(), request)
    assert not initial.get('preview')
    question, = initial['questions']
    assert question['requires_analysis'] and {opt['label'] for opt in question['options']} == {'零售', '批发'}
    chosen = next(opt for opt in question['options'] if opt['label'] == '零售')
    answers = [{'question_id': question['id'], 'context': question['evidence_term'], 'question': question['text'],
                'answer': f"{chosen['label']}（{chosen['value']}）"}]
    final = rules.parse_rule_request(user(), {**request, 'clarification_answers': answers})
    assert final['preview'] and not final['questions']
    assert final['preview']['definition']['filters'] == [
        {'field': 'channel', 'op': 'eq', 'value': '01', 'table': 'base', 'confirmed': True}]


def test_confirmed_classification_must_be_from_original_offered_field_and_document():
    fields = [dict(field_name=n, field_cn=n, table_id=8, id=i, dictionary='01-零售\n02-批发', data_type='varchar')
              for i,n in enumerate(['channel', 'mode'], 1)]
    d = proposal()
    q = dictionary_partition_question(d['semantic_intent']['scopes'][0], fields, [])
    for field, table, context in [('mode', 8, q['evidence_term']), ('channel', 9, q['evidence_term']), ('channel', 8, '新分类')]:
        changed = deepcopy(d)
        apply_dictionary_answers(changed, [{**f, 'table_id': table} for f in fields], [], [
            {'question_id': q['id'], 'context': context, 'answer': f'批发（{field}=02）'}])
        assert changed == d


def test_one_name_for_two_physical_codes_requires_an_identifiable_choice():
    draft = proposal('02')
    rules, _ = service_with_replies(draft, 8)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'channel').values(dictionary='01-零售\n02-零售'))
    request = _request(request_text='流转渠道为零售的记录，分拣方式不得为人工。', analysis_protocol=2)
    result = rules.parse_rule_request(user(), request)
    assert not result.get('preview')
    q, = result['questions']
    assert {o['label'] for o in q['options']} == {'零售（01）','零售（02）'}
    selected = q['options'][0]
    final = rules.parse_rule_request(user(), {**request, 'clarification_answers': [{'question_id': q['id'],
        'context': q['evidence_term'], 'question': q['text'], 'answer': f"{selected['label']}（{selected['value']}）"}]})
    assert final['preview']['definition']['filters'][0]['value'] == '01'
