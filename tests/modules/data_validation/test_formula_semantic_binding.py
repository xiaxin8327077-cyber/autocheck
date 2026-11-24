from copy import deepcopy

import pytest

from auto_check.modules.data_validation.analysis_result_cache import model_snapshot
from auto_check.modules.data_validation.document_evidence import documented_equation
from auto_check.modules.data_validation.semantic_generation import _IncompleteDraft, _validate_intent, reviewed_semantic_choices
from auto_check.modules.data_validation.semantic_grounding import semantic_coverage_issue
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc
from tests.modules.data_validation.test_ai_latency_pipeline import combined
from tests.modules.data_validation.test_semantic_generation import draft
from tests.modules.data_validation.test_project_driver_binding import make_rules, semantic_draft


FIELDS = [('serial', '记录号', 'varchar', 'Y'), ('day', '数据日期', 'date', ''),
          ('remaining', '结余量', 'numeric', ''), ('previous', '上期结余量', 'numeric', ''),
          ('arrivals', '入库量', 'numeric', ''), ('sent', '出库量', 'numeric', ''),
          ('audited', '复核出库量', 'numeric', '')]
DOCUMENT = [dict(field_name=n, field_cn=l, data_type=t) for n, l, t, _ in FIELDS]
TREE = {'op': '-', 'left': {'op': '+', 'left': {'field': 'previous'}, 'right': {'field': 'arrivals'}},
        'right': {'field': 'sent'}}


def proposal(*, alternatives=False):
    rule = draft('remaining')
    rule['expression'] = {'left': 'remaining', 'op': 'neq', 'right_type': 'formula', 'right': deepcopy(TREE)}
    rule['business_key'] = 'serial'
    metrics = [{'side': 'left', 'term': '结余量', 'fields': ['remaining']}]
    for path, name, label in [(['left', 'left'], 'previous', '上期结余量'), (['left', 'right'], 'arrivals', '入库量'),
                              (['right'], 'sent', '出库计量')]:
        metrics.append({'side': 'right', 'term': label, 'fields': [name], 'formula_path': path})
    if alternatives:
        metrics[-1]['fields'].append('audited')
    rule['semantic_intent']['metrics'] = metrics
    return rule


@pytest.mark.parametrize('grouped', [False, True])
def test_documented_formula_keeps_every_leaf_at_its_own_position(grouped):
    rule = proposal()
    if grouped:
        rule['expression'] = {'logic': 'any', 'conditions': [rule['expression'],
            {'left_type': 'formula', 'left': {'op': '/', 'left': {'field': 'arrivals'}, 'right': {'value': 2}},
             'op': 'lt', 'right_type': 'formula', 'right': {'op': '*', 'left': {'field': 'previous'}, 'right': {'value': 3}}}]}
        for m in rule['semantic_intent']['metrics']:
            m['condition_index'] = 0
        for side, name in [('left', 'arrivals'), ('right', 'previous')]:
            rule['semantic_intent']['metrics'].append({'condition_index': 1, 'side': side, 'fields': [name], 'term': name,
                                                      'formula_path': ['left']})
    rules, model = _rules_with_doc([combined(rule)], fields=FIELDS)
    res = rules.parse_rule_request(user(), _request(request_text='检查出入库数量公式', analysis_protocol=2))
    assert res['preview'] and res['expression'] == rule['expression'] and not res['questions']
    assert len(model.calls) == 1


def test_formula_choice_only_changes_selected_document_leaf():
    rule = proposal(alternatives=True)
    rules, _ = _rules_with_doc([combined(rule)], fields=FIELDS)
    res = rules.parse_rule_request(user(), _request(request_text='检查各项出入库数量关系', analysis_protocol=2))
    question, = res['questions']
    assert question['id'] == 'expression.right.right.field'
    assert {o['value'] for o in question['options']} == {'sent','audited'}
    edited = deepcopy(res)
    edited['expression']['right']['right']['field'] = 'audited'
    chosen, = reviewed_semantic_choices(res, edited)
    assert chosen['binding']['formula_path'] == ['right'] and chosen['binding']['side'] == 'right'
    snapshot = model_snapshot(combined(rule), rule)
    assert snapshot['draft']['semantic_intent']['metrics'][-1]['formula_path'] == ['right']
    assert not semantic_coverage_issue(edited, res['semantic_intent'], DOCUMENT, [])
    edited['expression']['right']['left']['op'] = '-'
    assert semantic_coverage_issue(edited, res['semantic_intent'], DOCUMENT, [])


def test_formula_rejects_non_numeric_document_leaf():
    rule = proposal()
    rule['expression']['right']['right']['field'] = 'serial'
    rule['semantic_intent']['metrics'][-1]['fields'] = ['serial']
    with pytest.raises(_IncompleteDraft):
        _validate_intent(rule, DOCUMENT, [])


@pytest.mark.parametrize("paths", [[], [["left"], ["right", "left"], ["right"]]])
def test_unique_formula_fields_bind_even_when_model_omits_or_misplaces_paths(paths):
    rule = proposal()
    for i, metric in enumerate(rule["semantic_intent"]["metrics"][1:]):
        metric.pop("formula_path")
        if paths:
            metric["formula_path"] = paths[i]
    rules, model = _rules_with_doc([combined(rule)], fields=FIELDS)
    res = rules.parse_rule_request(user(), _request(request_text="结余量应满足公式：结余量=上期结余量+入库量-出库量。", analysis_protocol=2))
    assert res["preview"] and not res["questions"] and res["expression"] == rule["expression"]
    assert len(model.calls) == 1


@pytest.mark.parametrize('defect', ['sign', 'missing', 'direction'])
def test_explicit_document_equation_corrects_wrong_sign_term_or_direction_in_first_draft(defect):
    good = proposal()
    bad = deepcopy(good)
    if defect == 'sign':
        bad['expression']['right']['op'] = '+'
    elif defect == 'missing':
        bad['expression'].update(right_type='field', right='previous')
        bad['semantic_intent']['metrics'] = bad['semantic_intent']['metrics'][:2]
        bad['semantic_intent']['metrics'][1].pop('formula_path')
    else:
        bad['expression']['op'] = 'eq'
    rules, model = _rules_with_doc([combined(bad)], fields=FIELDS)
    res = rules.parse_rule_request(user(), _request(request_text='应满足公式：结余量=上期结余量+入库量-出库量。', analysis_protocol=2))
    assert res.get('preview') and res['expression'] == good['expression']
    assert len(model.calls) == 1


def test_literal_equation_binds_registered_alias_and_respects_parentheses():
    fields = [dict(f, logic="业务别名：进货数量。" if f["field_name"] == "arrivals" else "") for f in DOCUMENT]
    equation = documented_equation("应满足公式：结余量＝（上期结余量＋进货数量）÷2。", fields)
    assert equation['right'] == {'op': '/', 'left': TREE['left'], 'right': {'value': 2}}
    for term in ['缺少文档的别名', '进货数量']:
        ambiguous = [*fields, dict(field_name="other", field_cn="进货数量", data_type="decimal")]
        assert documented_equation(f"应满足公式：结余量=上期结余量+{term}。", ambiguous) is None
    assert documented_equation("若结余量等于上期结余量和到货量之和则标记异常", fields) is None


def test_documented_detail_formula_gets_actual_project_role_despite_wrong_model_marker():
    plan = semantic_draft()
    plan['project_driver'] = {'version': 1, 'table_role': 'base'}
    plan['expression'] = {'left': 'amount', 'op': 'neq', 'right_type': 'formula',
                          'right': {'op': '+', 'left': {'field': 'other_amount'}, 'right': {'value': 2}}}
    plan['semantic_intent']['scopes'] = []
    plan['filters'] = []
    rules, model = make_rules([{'target': {'table': 'asset_rows'}, 'report_category': 'pbc_central', 'draft': plan}])
    result = rules.parse_rule_request(user(), _request(request_text='资产明细应满足公式：资产收益权余额=其他余额+2。', analysis_protocol=2))
    assert result['preview'] and result['expression'] == plan['expression']
    assert result['table_name'] == 'asset_rows' and result['project_driver']['table_role'] == 'related'
    assert len(model.calls) == 1
