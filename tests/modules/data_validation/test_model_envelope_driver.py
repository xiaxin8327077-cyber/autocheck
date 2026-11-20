"""A selected single rule must retain an unambiguous driver declaration."""
from copy import deepcopy

import pytest

from auto_check.modules.data_validation.project_driver import normalize_project_driver
from auto_check.modules.data_validation.semantic_generation import _flatten_plan_envelopes, _IncompleteDraft


@pytest.mark.parametrize('inner', [None, {'version': 1, 'table_role': 'related'}])
def test_single_rule_uses_its_outer_driver_without_changing_the_comparison(inner):
    reply = {
        'target': {'table': 'detail'}, 'related_target': {'table': 'projects'},
        'project_driver': {'version': 1, 'table_role': 'related'},
        'draft': {'rule_type': 'field_compare',
                  'expression': {'left': 'amount', 'op': 'lte', 'right_type': 'value', 'right': 0}},
    }
    if inner is not None:
        reply['draft']['project_driver'] = inner
    original = deepcopy(reply)

    normalized = _flatten_plan_envelopes(deepcopy(reply))

    assert normalize_project_driver(normalized['draft']['project_driver']) == {'version': 1, 'table_role': 'related'}
    assert normalized['draft']['expression'] == {'left': 'amount', 'op': 'lte', 'right_type': 'value', 'right': 0}
    assert reply == original


@pytest.mark.parametrize('conflicting', [{'version': 1, 'table_role': 'base'},
                                       {'version': True, 'table_role': 'related'}])
def test_outer_driver_must_not_replace_a_different_inner_declaration(conflicting):
    reply = {'project_driver': conflicting,
             'draft': {'project_driver': {'version': 1, 'table_role': 'related'}, 'rule_type': 'field_compare'}}
    with pytest.raises(_IncompleteDraft):
        _flatten_plan_envelopes(reply)


def test_group_driver_is_not_guessed_for_independent_plans():
    reply = {'project_driver': {'version': 1, 'table_role': 'related'},
             'draft': {'plan_mode': 'alternatives', 'plans': [
                 {'rule_type': 'field_compare', 'project_driver': {'version': 1, 'table_role': 'base'}},
                 {'rule_type': 'field_compare', 'project_driver': {'version': 1, 'table_role': 'related'}},
             ]}}
    with pytest.raises(_IncompleteDraft):
        _flatten_plan_envelopes(reply)
