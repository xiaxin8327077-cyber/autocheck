from auto_check.modules.data_validation.query_spec import (
    apply_numeric_null_policy,
    infer_numeric_null_handling,
    is_numeric_comparison,
    needs_issue_kind,
)


def _definition(**overrides):
    definition = {
        "rule_type": "field_compare",
        "table_name": "t",
        "business_key": "id",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
    }
    definition.update(overrides)
    return definition


def test_helpers_are_type_safe_on_untrusted_model_shapes():
    malformed = [
        _definition(expression={"left": "amount", "op": [], "right_type": "value", "right": 0}),
        _definition(expression={"left": "amount", "op": {}, "right_type": "value", "right": 0}),
        _definition(expression={"left": [], "op": "gt", "right_type": "value", "right": 0}),
        _definition(expression={"left": "amount", "op": "gt", "right_type": [], "right": []}),
        _definition(expression={"left": "amount", "op": "gt", "right": [], "right_type": "field"}),
        _definition(expression=[]),
        _definition(expression="bad"),
        _definition(rule_type=[]),
    ]
    fields = [{"column_name": "amount", "data_type": "decimal"}]
    for definition in malformed:
        assert is_numeric_comparison(definition, {}) is False
        assert needs_issue_kind(definition) in (True, False)
        inferred = infer_numeric_null_handling(definition, fields)
        assert inferred["applicable"] is False and inferred["null_policy"] is None
        bound = apply_numeric_null_policy(definition, fields)
        assert bound is not definition
    assert infer_numeric_null_handling(_definition(), "not-a-list")["applicable"] is False
