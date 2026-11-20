from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_followup_service_bridge import _add_table
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


def test_combined_single_metric_does_not_silence_same_term_documented_variants():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '余额'
    reviewed = deepcopy(first)
    reviewed['semantic_intent']['metrics'][0]['fields'] = ['balance', 'prior_balance']
    fields = [*FIELDS, ('prior_balance', '原始余额', 'numeric', '')]
    rules, model = _rules_with_doc([combined(first), reviewed], fields=fields)

    result = run(rules, '余额低于19要核实')

    assert len(model.calls) == 2
    question, = result['questions']
    assert {o['value'] for o in question['options']} == {'balance', 'prior_balance'}
    assert not result['preview']


def test_other_grain_metric_evidence_is_authorized_before_generating_alternatives():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '余额'
    other = draft('line_balance')
    other.update(target={'table': 'detail_lines'})
    other['semantic_intent']['metrics'][0]['term'] = '余额'
    rules, model = _rules_with_doc([combined(first), {'plans': [first, other]}, {'ai_suggestions': []}], fields=FIELDS)
    _add_table(rules, name='detail_lines', cn='明细余额表', dimension='业务编号＋明细编号',
               fields=[('line_id', '明细编号', 'varchar', 'Y'), ('line_balance', '明细余额', 'numeric', ''),
                       ('business_day', '数据日期', 'date', '')])

    result = run(rules, '余额低于19要核实')

    assert len(model.calls) == 3 and '本轮只提出独立补充校验建议' in model.calls[2]['messages'][0]['content']
    assert {o['candidate']['table_name'] for o in result['candidate_options']} == {'test_table', 'detail_lines'}
    assert 'detail_lines' in model.calls[1]['messages'][0]['content']


def test_matching_category_definition_is_reviewed_without_auditing_unrelated_shared_codes():
    fields = [*FIELDS, ('current', '当前结算方式', 'varchar', ''), ('original', '原始结算方式', 'varchar', ''),
              ('other', '归档标识', 'varchar', '')]
    first = draft('balance')
    partition = {'include': ['1'], 'exclude': ['2']}
    first['semantic_intent']['scopes'] = [{'category': '预付', 'fields': ['current'],
                                         'memberships': {'current': partition}}]
    reviewed = deepcopy(first)
    reviewed['semantic_intent']['scopes'][0].update(fields=['current', 'original'],
        memberships={'current': partition, 'original': partition})
    rules, model = _rules_with_doc([combined(first), reviewed], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(('current', 'original')))
                     .values(dictionary='1-预付\n2-后付'))
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'other').values(dictionary='1-是\n2-否'))

    result = run(rules, '预付的余额低于19要核实')

    assert len(model.calls) == 1
    question, = result['questions']
    assert {o['selection']['field'] for o in question['options']} == {'current', 'original'}
    assert 'other' not in {o['selection']['field'] for o in question['options']}


def test_explicit_metric_qualifier_retains_the_single_call_path():
    first = draft('original')
    first['semantic_intent']['metrics'][0]['term'] = '原始余额'
    fields = [*FIELDS, ('original', '原始余额', 'numeric', '')]
    rules, model = _rules_with_doc([combined(first)], fields=fields)

    result = run(rules, '原始余额低于19要核实')

    assert len(model.calls) == 1 and result['preview'] and not result['questions']


def test_shared_adaptation_does_not_bypass_competing_metric_evidence():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '当前余额'
    revised = deepcopy(first)
    revised['expression']['right'] = 29
    revised['semantic_intent']['metrics'][0]['term'] = '余额'
    checked = deepcopy(revised)
    checked['semantic_intent']['metrics'][0]['fields'] = ['balance', 'original']
    fields = [(name, '当前余额' if name == 'balance' else cn, kind, pk) for name, cn, kind, pk in FIELDS]
    fields.append(('original', '原始余额', 'numeric', ''))
    memory = {**_select_payload(), 'reuse_decision': 'adapt', 'memory_index': 0, 'draft': revised}
    rules, model = _rules_with_doc([combined(first), memory, checked], fields=fields)
    assert run(rules, '当前余额低于19要核实')['preview']

    result = run(rules, '余额低于29要核实')

    assert len(model.calls) == 3 and not result['preview']
    question, = result['questions']
    assert {o['value'] for o in question['options']} == {'balance', 'original'}


def test_review_omitting_a_user_named_metric_choice_cannot_publish_or_cache_a_unique_rule():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '余额'
    first['semantic_intent']['metrics'][0]['fields'] = ['balance', 'original']
    reviewed = deepcopy(first)
    reviewed['semantic_intent']['metrics'][0]['fields'] = ['balance']
    fields = [*FIELDS, ('original', '原始余额', 'numeric', '')]
    rules, model = _rules_with_doc([{**combined(first), 'expand_evidence': True}, reviewed], fields=fields)

    request_text = '余额与原始余额两种口径低于19都要核实'
    result = run(rules, request_text)

    assert len(model.calls) == 2
    assert result['rule_type'] is None and not result.get('preview')
    assert 'original' in ''.join(result['uncertainties'])
    context = rules._analysis_inputs({'id': '1'}, _request(request_text=request_text, analysis_protocol=2))['context']
    assert rules.storage.cached_analysis_result(context, request_text) is None


@pytest.mark.parametrize('attach_legacy_exclusion', [True, False])
def test_reviewed_distinct_measure_needs_no_per_field_exclusion_report(attach_legacy_exclusion):
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '余额'
    reviewed = deepcopy(first)
    quote = '该列仅为模拟余额，使用测试场景估算，不能替代实际业务余额。'
    if attach_legacy_exclusion:
        reviewed['interpretation_exclusions'] = [{'id': 'I1', 'reason': '模拟场景值不属于实际业务余额。',
            'evidence': {'source': 'document', 'quote': quote}}]
    fields = [*FIELDS, ('change', '模拟余额', 'numeric', '')]
    rules, model = _rules_with_doc([combined(first), reviewed], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'change').values(logic=quote))

    result = run(rules, '余额低于19要核实')

    assert len(model.calls) == 2 and quote in model.calls[1]['messages'][0]['content']
    assert result['preview'] and not result['questions'] and not result.get('candidate_options')
    assert result['expression'] == first['expression']


def test_selection_only_response_cannot_bypass_interpretation_coverage():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '余额'
    reviewed = deepcopy(first)
    reviewed['semantic_intent']['metrics'][0]['fields'] = ['balance', 'original']
    fields = [*FIELDS, ('original', '原始余额', 'numeric', '')]
    rules, model = _rules_with_doc([_select_payload(), first, reviewed], fields=fields)

    result = run(rules, '余额低于19要核实')

    assert len(model.calls) == 3 and not result['preview']
    assert {o['value'] for o in result['questions'][0]['options']} == {'balance', 'original'}


def test_direct_copied_metric_does_not_invent_an_independent_interpretation():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '余额'
    rules, model = _rules_with_doc([combined(first)], fields=FIELDS)
    _add_table(rules, name='copies', cn='明细附带值', dimension='明细',
               fields=[('id', '明细编号', 'varchar', 'Y'), ('copied', '余额', 'numeric', ''),
                       ('business_day', '数据日期', 'date', '')])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'copied').values(
            source_table='example.test_table', source_field='balance', logic='直取'))

    result = run(rules, '余额低于19要核实')

    assert len(model.calls) == 1 and result['preview'] and not result['questions']


def test_explicit_documented_alias_does_not_expand_unrelated_shorter_metric_names():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '专项权益余额'
    fields = [(name, '基础期末余额' if name == 'balance' else cn, kind, pk)
              for name, cn, kind, pk in FIELDS]
    rules, model = _rules_with_doc([combined(first)], fields=fields)
    _add_table(rules, name='accounts', cn='账户余额', dimension='账户',
               fields=[('id', '编号', 'varchar', 'Y'), ('amount', '余额', 'numeric', ''),
                       ('business_day', '数据日期', 'date', '')])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'balance').values(
            logic='业务别名：专项权益余额。表示本期基础期末余额。'))

    result = run(rules, '专项权益余额低于19要核实')

    assert len(model.calls) == 1 and result['preview'] and not result['questions']


def test_review_cannot_replace_an_explicit_metric_with_the_other_named_field():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '可用余额'
    fields = [(name, '可用余额' if name == 'balance' else label, kind, pk) for name, label, kind, pk in FIELDS]
    fields.append(('original', '原始余额', 'numeric', ''))
    replaced = deepcopy(first)
    replaced['expression']['left'] = 'original'
    replaced['semantic_intent']['metrics'][0]['fields'] = ['original']
    rules, model = _rules_with_doc([{**combined(first), 'expand_evidence': True}, replaced], fields=fields)

    result = run(rules, '可用余额与原始余额低于19都要核实')

    assert result['rule_type'] is None and not result.get('preview')
    assert 'balance' in ''.join(result['uncertainties'])


def test_generic_request_quote_cannot_discard_the_original_interpretation():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '余额'
    replacement = deepcopy(first)
    replacement['expression']['left'] = 'original'
    replacement['semantic_intent']['metrics'][0]['fields'] = ['original']
    replacement['interpretation_exclusions'] = [{'id': 'I2', 'reason': '用户只确认原始余额',
        'evidence': {'source': 'request', 'quote': '余额'}}]
    rules, _ = _rules_with_doc([combined(first), replacement, replacement],
        fields=[*FIELDS, ('original', '原始余额', 'numeric', '')])

    result = run(rules, '余额低于19要核实')

    assert result['rule_type'] is None and not result.get('preview')


def test_evidence_expansion_cannot_drop_the_first_scope_without_competing_fields():
    fields = [*FIELDS, ('settlement', '结算方式', 'varchar', '')]
    first = draft('balance')
    first['semantic_intent']['scopes'] = [{'category': '预付', 'fields': ['settlement'],
        'memberships': {'settlement': {'include': ['1'], 'exclude': ['2']}}}]
    lost = draft('balance')
    rules, _ = _rules_with_doc([{**combined(first), 'expand_evidence': True}, lost, lost], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'settlement').values(dictionary='1-预付\n2-后付'))

    result = run(rules, '预付的余额低于19要核实')

    assert result['rule_type'] is None and not result.get('preview')


def test_more_documented_grains_than_supported_cannot_be_silently_omitted():
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '余额'
    question = '应按业务编号、合同、账户还是分户核对余额？'
    reviewed = deepcopy(first)
    reviewed['semantic_intent']['open_questions'] = [question]
    rules, model = _rules_with_doc([combined(first), reviewed], fields=FIELDS)
    for i, grain in enumerate(('合同', '账户', '分户')):
        _add_table(rules, name=f'detail_{i}', cn=f'{grain}余额表', dimension=grain,
                   fields=[('id', '编号', 'varchar', 'Y'), (f'amount_{i}', '余额', 'numeric', ''),
                           ('business_day', '数据日期', 'date', '')])

    result = run(rules, '余额低于19要核实')

    assert len(model.calls) == 2
    assert all(grain in model.calls[1]['messages'][0]['content'] for grain in ('合同', '账户', '分户'))
    assert question in result['uncertainties']
    assert not result.get('preview') and not result.get('can_enable')


def test_complete_combined_plans_declare_their_own_targets_without_a_second_selection():
    first = draft('balance')
    other = draft('line_balance')
    other['target'] = {'table': 'detail_lines'}
    fields = [(name, '汇总读数' if name == 'balance' else cn, kind, pk) for name, cn, kind, pk in FIELDS]
    rules, model = _rules_with_doc([combined({'plans': [first, other]}), {'ai_suggestions': []}], fields=fields)
    _add_table(rules, name='detail_lines', cn='明细余额表', dimension='明细',
               fields=[('line_id', '明细编号', 'varchar', 'Y'), ('line_balance', '逐笔测量', 'numeric', ''),
                       ('business_day', '数据日期', 'date', '')])

    result = run(rules, '汇总读数与逐笔测量都低于19要核实')

    assert len(model.calls) == 2 and '本轮只提出独立补充校验建议' in model.calls[1]['messages'][0]['content']
    assert {o['candidate']['table_name'] for o in result['candidate_options']} == {'test_table', 'detail_lines'}
