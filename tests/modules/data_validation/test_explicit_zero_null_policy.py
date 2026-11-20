import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_spec import (
    apply_numeric_null_policy, infer_numeric_null_handling, validate_query_spec, validate_spec_against_columns,
)
from tests.modules.data_validation.test_related_sum import BASE, RELATED, definition


LIMIT = {"left": "amount", "op": "lte", "right_type": "value", "right": 0}
FIELDS = {"left": "amount", "op": "neq", "right_type": "field", "right": "active"}


def plain(expression, **overrides):
    rule = definition("postgresql")
    rule.pop("join")
    return {**rule, "expression": expression, "filters": [], "null_policy": "zero", **overrides}


@pytest.mark.parametrize("expression", [
    LIMIT, FIELDS, {"logic": "any", "conditions": [LIMIT, FIELDS]},
    {"logic": "any", "conditions": [LIMIT, {"left": "owner_id", "op": "is_null"}]},
])
def test_explicit_zero_survives_rebinding_without_claiming_document_evidence(expression):
    rule = plain(expression, null_evidence=[{"side": "left", "field": "amount", "source": "unverified"}])
    inferred = infer_numeric_null_handling(rule, BASE)
    assert (inferred["null_policy"], inferred["null_handling"], inferred["evidence"]) == ("zero", None, [])
    bound = apply_numeric_null_policy(rule, BASE, request_text="检查本期数值")
    assert bound["null_policy"] == "zero" and "null_handling" not in bound and bound["null_evidence"] == []
    assert apply_numeric_null_policy(bound, BASE) == bound
    validate_spec_against_columns(bound, BASE)


@pytest.mark.parametrize("expression", [
    {"left": "asof", "op": "eq", "right": "asof"},
    {"left": "owner_id", "op": "eq", "right": "owner_id"},
    {"left": "amount", "op": "is_null"},
    {"logic": "all", "conditions": [LIMIT, {"left": "asof", "op": "eq", "right": "asof"}]},
])
def test_explicit_zero_cannot_turn_unary_or_nonnumeric_checks_into_numeric_comparisons(expression):
    rule = plain(expression)
    assert infer_numeric_null_handling(rule, BASE)["null_policy"] != "zero"
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        validate_spec_against_columns(rule, BASE)


def test_implicit_default_and_legacy_zero_receipts_keep_their_original_definitions():
    rule = plain(LIMIT)
    rule.pop("null_policy")
    rule["null_evidence"] = [{"side": "left", "field": "amount", "source": "unverified"}]
    default = apply_numeric_null_policy(rule, BASE)
    assert default["null_policy"] == "review" and not default["null_evidence"]
    for op, columns, source in [
        ("gt", BASE, "空值按 0 参与本次数值比较，0 不会命中校验条件。"),
        ("lte", [{**col, "comment": "空值视为0"} for col in BASE], " 空值视为0 "),
    ]:
        old = plain({**LIMIT, "op": op}, null_handling={"left": "zero", "right": "zero"},
                    null_evidence=[{"side": "left", "field": "amount", "source": source}])
        assert apply_numeric_null_policy(old, columns) == old


def test_sum_accepts_explicit_zero_for_values_and_keeps_missing_rows_under_review():
    rule = {**definition("postgresql"), "null_policy": "zero"}
    bound = apply_numeric_null_policy(rule, BASE, RELATED)
    assert bound["null_policy"] == "zero" and bound.get("null_handling") is None and bound["null_evidence"] == []
    assert apply_numeric_null_policy(bound, BASE, RELATED) == bound
    assert validate_spec_against_columns(bound, BASE, RELATED)["join"]["unmatched_policy"] == "review"
    for policy in ("review", "zero"):
        matching = {**rule, "null_policy": policy, "null_handling": {"left": policy, "right": policy}}
        validate_query_spec(matching)
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        validate_query_spec({**bound, "join": {**bound["join"], "unmatched_policy": "zero"}})


@pytest.mark.parametrize("policy,handling", [
    ("skip", None), ("unknown", None), ("zero", {"left": "review", "right": "zero"}),
    ("review", {"left": "zero", "right": "zero"}),
])
def test_sum_rejects_unsupported_value_policies_and_conflicting_side_modes(policy, handling):
    rule = {**definition("postgresql"), "null_policy": policy, "null_handling": handling}
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        validate_query_spec(rule)


@pytest.mark.parametrize("native_type", ["money", "bit"])
def test_zero_policy_rejects_native_types_that_cannot_coalesce_with_numeric_zero(native_type):
    columns = [{**column, "data_type": native_type} if column["column_name"] == "amount" else column for column in BASE]
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        validate_spec_against_columns(plain(LIMIT), columns)
