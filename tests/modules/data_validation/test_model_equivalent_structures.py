from copy import deepcopy

import pytest

from auto_check.modules.data_validation.semantic_generation import _normalize_documented_operands
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


FIELDS = [('id', '记录编号', 'varchar', 'Y'), ('day', '数据日期', 'date', ''),
          ('amount', '读数', 'numeric', ''), ('balance', '余额', 'numeric', '')]
CANONICAL = {'left': 'amount', 'op': 'gt', 'right_type': 'value', 'right': 0}


@pytest.mark.parametrize('expression', [
    {'op': 'and', 'conditions': [CANONICAL]},
    {'op': 'or', 'conditions': [CANONICAL]},
    {'logic': 'AND', 'conditions': [CANONICAL]},
    {'left': 'amount', 'op': 'gt', 'right': 0},
    {'left': 'amount', 'op': 'gt', 'right': 0.5},
    {'left': {'table': 'base', 'field': 'amount'}, 'op': 'eq', 'right_type': 'field',
     'right': {'table': 'base', 'field': 'balance'}},
])
def test_equivalent_model_shapes_are_bound_before_intent_validation(expression):
    expression = deepcopy(expression)
    right_field = isinstance(expression.get('right'), dict)
    metrics = [{'side': 'left', 'term': '读数', 'fields': ['amount']}]
    if right_field:
        metrics.append({'side': 'right', 'term': '余额', 'fields': ['balance']})
    draft = {'business_key': 'id', 'rule_name': '读数核查', 'rule_type': 'field_compare',
             'expression': expression, 'null_policy': 'zero', 'violation_message': '读数异常',
             'semantic_intent': {'metrics': metrics, 'scopes': [], 'open_questions': []}}
    rules, model = _rules_with_doc([{'target': {'table': 'test_table'}, 'draft': draft}, draft], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text='核查读数', analysis_protocol=2))
    assert result['preview'] and not result['questions']
    expected = {'left': 'amount', 'op': 'eq', 'right_type': 'field', 'right': 'balance'} if right_field else {
        **CANONICAL, 'right': expression.get('right', 0)}
    assert result['expression'] == expected
    assert len(model.calls) == 1


@pytest.mark.parametrize('explicit_role', [None, 'related', 'base'])
def test_object_operand_preserves_explicit_role_and_only_uses_documented_fields(explicit_role):
    fields = [{'field_name': name, 'data_type': 'numeric'} for name in ['amount', 'balance']]
    part = {'left': 'amount', 'op': 'eq', 'right_type': 'field', 'right': {'table': 'related', 'field': 'balance'}}
    if explicit_role:
        part['right_table'] = explicit_role
    draft = {'expression': part}
    _normalize_documented_operands(draft, fields, fields)
    if explicit_role == 'base':
        assert isinstance(part['right'], dict)  # Conflicting declarations are not silently resolved.
    else:
        assert part['right'] == 'balance' and part['right_table'] == 'related'


@pytest.mark.parametrize('value', ['balance', '0', False])
def test_implicit_constant_type_is_only_inferred_for_finite_json_numbers(value):
    draft = {'expression': {'left': 'amount', 'op': 'eq', 'right': value}}
    _normalize_documented_operands(draft, [], [])
    assert 'right_type' not in draft['expression']
