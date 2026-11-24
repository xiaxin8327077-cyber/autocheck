from copy import deepcopy

import pytest

from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


FIELDS = [('row_id', '记录编号', 'varchar', 'Y'), ('day', '数据日期', 'date', ''),
          ('caption', '标题', 'varchar', ''), ('score', '评分', 'numeric', '')]


def reply(field='caption', term='标题', expression=None):
    return {'target': {'table': 'test_table'}, 'draft': {
        'business_key': 'row_id', 'rule_name': '文字检查', 'rule_type': 'field_compare',
        'expression': expression or {'left': field, 'op': 'is_not_null'},
        'violation_message': '文字内容需核查', 'null_policy': 'skip',
        'semantic_intent': {'metrics': [{'side': 'left', 'term': term, 'fields': [field]}],
                            'scopes': [], 'open_questions': []}}}


@pytest.mark.parametrize('request_text,op,words', [
    ('标题不能包含%或‰', 'contains_any', ['%', '‰']),
    ('标题必须包含“center”或“X_Y”', 'not_contains_any', ['center', 'X_Y']),
    ('标题不得含有“A或B”、"100%"', 'contains_any', ['A或B', '100%']),
    ('标题不应包含"O\'Brien"或“路径\\a”', 'contains_any', ["O'Brien", '路径\\a']),
])
def test_explicit_text_requirement_cannot_be_replaced_by_nonempty(request_text, op, words):
    initial = reply()
    rules, model = _rules_with_doc([initial, deepcopy(initial)], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text=request_text, analysis_protocol=2))
    assert result.get('preview'), result.get('uncertainties')
    assert result['expression'] == {'left': 'caption', 'op': op, 'right_type': 'value', 'right': words}
    assert not result.get('questions')
    assert len(model.calls) == 1


def test_text_match_does_not_steal_a_different_fields_condition():
    initial = reply(field='score', term='评分', expression={
        'left': 'score', 'op': 'lt', 'right_type': 'value', 'right': 0})
    initial['draft']['null_policy'] = 'zero'
    initial['draft']['filters'] = [{'field': 'caption', 'op': 'contains_any', 'value': ['中心']}]
    rules, _ = _rules_with_doc([initial], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text='标题包含中心的记录，评分不得小于0', analysis_protocol=2))
    assert result['expression'] == initial['draft']['expression']
    assert result['preview']


def test_ambiguous_text_polarity_is_not_rewritten_from_a_substring():
    from auto_check.modules.data_validation.request_text_predicates import bind_text_predicates

    draft = reply()['draft']
    original = deepcopy(draft)
    bind_text_predicates(draft, [{'field_name': n, 'field_cn': c, 'data_type': t} for n,c,t,_ in FIELDS],
                         '标题不能不包含“center”')
    assert draft == original


def test_multiple_requirements_on_one_field_preserve_separate_slots():
    a = {'left': 'caption', 'op': 'contains_any', 'right_type': 'value', 'right': ['甲']}
    b = {**a, 'op': 'not_contains_any', 'right': ['乙']}
    for request in ['标题不得包含“甲”，标题必须包含“乙”。', '标题不得包含甲且必须包含乙。']:
        raw = reply(expression={'logic':'any', 'conditions':[a,b]})
        raw['draft']['semantic_intent']['metrics'] = [
            {'side':'left','fields':['caption'],'term':'标题','condition_index':i} for i in range(2)]
        rules, _ = _rules_with_doc([deepcopy(raw) for _ in range(3)], fields=FIELDS)
        result = rules.parse_rule_request(user(), _request(request_text=request, analysis_protocol=2))
        assert result['preview'] and result['expression'] == raw['draft']['expression']


def test_model_metric_caption_cannot_assign_named_field_to_another_source():
    from auto_check.modules.data_validation.request_text_predicates import bind_text_predicates
    d = reply('score','标题')['draft']
    source = [{'field_name': n, 'field_cn': c, 'data_type': t} for n,c,t,_ in FIELDS]
    assert bind_text_predicates(d, source, '标题不得包含“甲”。')
    assert d['expression'] == {'left':'score', 'op':'is_not_null'}


def test_missing_second_clause_cannot_be_treated_as_one_unquoted_word():
    from auto_check.modules.data_validation.request_text_predicates import bind_text_predicates
    d = reply()['draft']
    source = [{'field_name': n, 'field_cn': c, 'data_type': t} for n,c,t,_ in FIELDS]
    assert bind_text_predicates(d, source, '标题不能包含甲且必须包含乙。')
    assert d['expression'] == {'left':'caption','op':'is_not_null'}


def test_literal_list_keeps_quoted_commas_and_comma_or_continuation():
    raw = reply()
    rules, _ = _rules_with_doc([deepcopy(raw) for _ in range(3)], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text='标题不能包含“甲，乙”，或“丙”。', analysis_protocol=2))
    assert result['expression']['right'] == ['甲，乙','丙']


def test_unknown_subject_cannot_turn_a_text_check_into_nonempty():
    from auto_check.modules.data_validation.request_text_predicates import bind_text_predicates
    d = reply('score','报价摘要')['draft']
    source = [{'field_name': n, 'field_cn': c, 'data_type': t} for n,c,t,_ in FIELDS]
    assert bind_text_predicates(d, source, '报价摘要不能包含“甲”。')
    assert d['expression'] == {'left':'score', 'op':'is_not_null'}
    d['expression'] = {'left':'caption','op':'contains_any','right_type':'value','right':['甲']}
    assert not bind_text_predicates(d, source, '报价摘要不能包含“甲”。')


def test_quoted_data_is_not_a_field_requirement():
    from auto_check.modules.data_validation.request_text_predicates import bind_text_predicates
    d = reply('score','评分')['draft']
    source = [{'field_name': n, 'field_cn': c, 'data_type': t} for n,c,t,_ in FIELDS]
    assert not bind_text_predicates(d, source, '备注为“报价摘要不能包含甲”的记录，要核对评分。')

@pytest.mark.parametrize('operator,values', [('contains_any',['错误词']), ('not_contains_any',['甲']), ('contains_any',['甲'])])
def test_a_required_violation_check_is_not_satisfied_by_a_population_filter(operator, values):
    from auto_check.modules.data_validation.request_text_predicates import bind_text_predicates
    fields = [{'field_name': n, 'field_cn': c, 'data_type': t} for n,c,t,_ in FIELDS]
    draft = reply('score','评分',expression={'left':'score','op':'gt','right_type':'value','right':1})['draft']
    draft['filters'] = [{'field':'caption','op':operator,'value':values}]
    original = deepcopy(draft)
    assert bind_text_predicates(draft, fields, '标题不得包含“甲”，且评分不得超过1。')
    assert draft == original

@pytest.mark.parametrize('request_text', ['标题必须包含“甲”的记录，评分不得超过1。', '标题必须包含“甲”时评分不得超过1。'])
def test_a_named_text_prerequisite_remains_a_filter(request_text):
    from auto_check.modules.data_validation.request_text_predicates import bind_text_predicates
    fields = [{'field_name': n, 'field_cn': c, 'data_type': t} for n,c,t,_ in FIELDS]
    draft = reply('score','评分',expression={'left':'score','op':'gt','right_type':'value','right':1})['draft']
    draft['filters'] = [{'field':'caption','op':'contains_any','value':['甲']}]
    original = deepcopy(draft)
    assert not bind_text_predicates(draft, fields, request_text)
    assert draft == original
    draft['filters'][0]['value'] = ['乙']
    assert bind_text_predicates(draft, fields, request_text)
