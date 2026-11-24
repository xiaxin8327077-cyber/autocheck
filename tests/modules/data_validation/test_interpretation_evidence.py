from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
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
    assert not result.get('preview')
    question, = result['questions']
    assert question['id'] == 'expression.left'
    assert {o['value'] for o in question['options']} == {'balance', 'original'}


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


@pytest.mark.parametrize('registered_alias', [False, True])
def test_review_cannot_replace_an_explicit_metric_with_the_other_named_field(registered_alias):
    first = draft('balance')
    first['semantic_intent']['metrics'][0]['term'] = '可用余额'
    fields = [(name, '可用余额' if name == 'balance' else label, kind, pk) for name, label, kind, pk in FIELDS]
    fields.append(('original', '历史账户数值' if registered_alias else '原始余额', 'numeric', ''))
    replaced = deepcopy(first)
    replaced['expression']['left'] = 'original'
    replaced['semantic_intent']['metrics'][0]['fields'] = ['original']
    rules, model = _rules_with_doc([{**combined(first), 'expand_evidence': True}, replaced], fields=fields)
    if registered_alias:
        with rules.storage.database.begin() as conn:
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'original').values(logic='业务别名：原始余额。'))

    result = run(rules, '可用余额与原始余额低于19都要核实')

    assert not result.get('preview')
    question, = result['questions']
    assert {o['value'] for o in question['options']} == {'balance', 'original'}


def test_reference_to_scope_in_other_fields_dictionary_notes_is_not_a_filter_option():
    fields = [*FIELDS, ('flag', '包装类型', 'varchar', ''), ('carrier', '运输包装类型', 'varchar', '')]
    first = draft('flag')
    first['expression'] = {'left': 'flag', 'op': 'is_not_null'}
    first['semantic_intent'].update(metrics=[{'term': '包装类型', 'side': 'left', 'fields': ['flag']}],
        scopes=[{'category': '运输包装类型', 'fields': ['carrier'],
                 'memberships': {'carrier': {'include': ['N'], 'exclude': ['C']}}}])
    rules, _ = _rules_with_doc([combined(first), first], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'carrier')
                     .values(dictionary='C-冷链运输\nN-常温运输'))
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'flag')
                     .values(dictionary='1-散装\n2-箱装\n按运输包装类型选择，条件不符时留空。'))
    result = run(rules, '非冷链运输记录的包装类型不得有值')
    assert result['preview'] and not result['questions']
    assert result['expression'] == {'left': 'flag', 'op': 'is_not_null'}
    assert [(f['field'], f['value']) for f in result['filters']] == [('carrier', 'N')]


def test_named_scope_reordered_dictionary_or_new_caption_cannot_reverse_its_codes():
    first = draft('balance')
    first['semantic_intent']['scopes'] = [{'category': '预付', 'fields': ['mode'],
        'memberships': {'mode': {'include': ['1'], 'exclude': ['2']}}}]
    wrong = deepcopy(first)
    wrong['semantic_intent']['scopes'] = [{'category': '后付', 'fields': ['mode'],
        'memberships': {'mode': {'include': ['2'], 'exclude': ['1']}}}]
    rules, _ = _rules_with_doc([{**combined(first), 'expand_evidence': True}, wrong],
        fields=[*FIELDS, ('mode', '结算方式', 'varchar', '')])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'mode').values(dictionary='1-预付\n2-后付'))
    result = run(rules, '预付的余额低于19要核实')
    assert result['preview'] and not result['questions']
    assert [(f['field'], f['value']) for f in result['filters']] == [('mode', '1')]


def test_documented_alternatives_in_one_comparison_preserve_the_remaining_condition():
    first = draft('balance')
    first['expression'] = {'logic': 'all', 'conditions': [first['expression'], draft('amount')['expression']]}
    first['semantic_intent']['metrics'] = [
        {'side': 'left', 'condition_index': 0, 'term': '余额', 'fields': ['balance', 'original']},
        {'side': 'left', 'condition_index': 1, 'term': '份额', 'fields': ['amount']}]
    later = deepcopy(first)
    later['expression']['conditions'][0]['left'] = 'temp'
    later['semantic_intent']['metrics'][0]['fields'] = ['temp']
    fields = [(n, '可用余额' if n == 'balance' else label, t, pk) for n, label, t, pk in FIELDS]
    rules, _ = _rules_with_doc([{**combined(first), 'expand_evidence': True}, later], fields=[
        *fields, ('original', '原始余额', 'numeric', ''), ('temp', '暂估值', 'numeric', '')])
    result = run(rules, '可用余额或原始余额低于19，且份额低于19时要核实')
    question, = result['questions']
    assert question['id'] == 'expression.conditions.0.left'
    assert {o['value'] for o in question['options']} == {'balance', 'original'}
    assert result['expression']['conditions'][1] == draft('amount')['expression']


def test_scoped_nonempty_review_keeps_the_exact_metric_and_the_verified_category():
    fields = [*FIELDS, ('kind', '项目类型', 'varchar', ''), ('subtype', '类型', 'varchar', ''),
              ('sector', '运输类别', 'varchar', '')]
    first = draft('kind')
    first.update(rule_name='项目类型非空检查', violation_message='项目类型为空')
    first['expression'] = {'left': 'kind', 'op': 'is_null'}
    first['semantic_intent'].update(metrics=[{'term': '项目类型', 'side': 'left', 'fields': ['kind']}],
        scopes=[{'category': '冷链运输', 'fields': ['sector'],
                 'memberships': {'sector': {'include': ['C'], 'exclude': ['N']}}}])
    revised = deepcopy(first)
    revised.update(rule_name='细分类型非空检查', violation_message='细分类型为空')
    revised['expression']['left'] = 'subtype'
    revised['semantic_intent']['metrics'] = [{'term': '细分类型', 'side': 'left', 'fields': ['subtype']}]
    rules, _ = _rules_with_doc([{**combined(first), 'expand_evidence': True}, revised], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'sector')
                     .values(dictionary='C-冷链运输\nN-常温运输'))
    result = run(rules, '冷链运输项目类型不得为空')
    assert result['preview'] and not result['questions']
    assert result['filters'][0]['field'] == 'sector' and result['filters'][0]['value'] == 'C'
    assert result['expression'] == {'left': 'kind', 'op': 'is_null'}
    assert result['preview']['definition']['name'] == '项目类型非空检查'
    assert result['preview']['definition']['violation_message'] == '项目类型为空'


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


@pytest.mark.parametrize('second', ['omitted', 'multiple', 'reversed'])
def test_selected_document_scope_survives_a_fresh_model_reply_and_repairs_without_reasking(second):
    first = draft('balance')
    first['semantic_intent']['scopes'] = [{'category': '预付', 'fields': ['settlement'],
        'memberships': {'settlement': {'include': ['1'], 'exclude': ['2']}}}]
    lost = draft('balance')
    repeated = deepcopy(first)
    repeated_scope = repeated['semantic_intent']['scopes'][0]
    repeated_scope['fields'].append('prior')
    repeated_scope['memberships']['prior'] = deepcopy(repeated_scope['memberships']['settlement'])
    replies = [{**combined(first), 'expand_evidence': True}, lost]
    reversed_scope = deepcopy(first)
    reversed_scope['semantic_intent']['scopes'] = [{'category': '后付', 'fields': ['settlement'],
        'memberships': {'settlement': {'include': ['2'], 'exclude': ['1']}}}]
    replies += [combined(repeated)] if second == 'multiple' else [combined(reversed_scope if second == 'reversed' else lost), first]
    rules, model = _rules_with_doc(replies,
        fields=[*FIELDS, ('settlement', '结算方式', 'varchar', ''), ('prior', '其他口径分类', 'varchar', '')])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'settlement').values(dictionary='1-预付\n2-后付'))
    request = _request(request_text='预付的余额低于19要核实', analysis_protocol=2, reasoning_enabled=False)
    result = rules.parse_rule_request(user(), request)
    q, = result['questions']
    assert q['requires_analysis'] and '预付' in q['text'] and '结算方式' in q['text']
    option, = q['options']
    assert option['value'] == 'test_table.settlement'
    if second == 'multiple':
        with rules.storage.database.begin() as conn:
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == 'prior').values(dictionary='1-预付\n2-后付'))
    answer = {'question_id': q['id'], 'context': q['evidence_term'], 'question': q['text'],
              'answer': f"{option['label']}（{option['value']}）"}
    confirmed = rules.parse_rule_request(user(), {**request, 'clarification_answers': [answer]})
    assert confirmed['preview'] and confirmed['filters'][0]['field'] == 'settlement'
    assert confirmed['filters'][0]['value'] == '1' and not confirmed['questions']
    assert len(model.calls) == (3 if second == 'multiple' else 4) and q['text'] in model.calls[2]['messages'][0]['content']


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
