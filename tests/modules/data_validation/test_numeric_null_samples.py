"""显式数值 NULL->0 口径的样本求值：仅按规则配置生效，不改默认口径。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from auto_check.modules.data_validation.ai_service import refine_candidate
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_samples import (
    default_field_compare_cases, evaluate_case, evaluate_expression, evaluate_relational,
)
from auto_check.modules.data_validation.query_spec import is_new_spec
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload


def _legacy(**overrides):
    definition = {
        "rule_type": "field_compare",
        "expression": {"left": "rate", "op": "lt", "right_type": "value", "right": 0},
        "null_policy": "zero",
        "equality_policy": "reject_equal",
    }
    definition.update(overrides)
    return definition


def _relational(**overrides):
    definition = {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "table_name": "metric_base",
        "business_key": "metric_id",
        "report_date_field": "report_date",
        "violation_message": "额度异常",
        "null_policy": "zero",
        "equality_policy": "reject_equal",
        "expression": {"left": "quota", "op": "lte", "right_type": "field", "right": "limit_quota"},
        "filters": [{"table": "base", "field": "status", "op": "eq", "value": "A", "confirmed": True}],
        "join": {
            "table_name": "metric_limit", "on": [{"left": "metric_id", "right": "metric_id"}],
            "report_date_field": "report_date", "unmatched_policy": "exclude",
            "relationship_confirmed": True,
        },
    }
    definition.update(overrides)
    return definition


def _related_row(**values):
    row = {"metric_id": "M1", "report_date": "2026-09-30", "limit_quota": 5}
    row.update(values)
    return row


def _nested_row(base=None, related=None):
    return {
        "base": {"metric_id": "M1", "report_date": "2026-09-30", "quota": None, "status": "A",
                 **(base or {})},
        "related": related if related is not None else [_related_row()],
        "report_date": "2026-09-30",
    }


def test_explicit_zero_turns_only_none_into_zero_for_binary_numeric_compare():
    definition = _legacy(expression={"left": "rate", "op": "eq", "right_type": "value", "right": 0})
    assert evaluate_expression(definition, {"rate": None}) == 1
    assert evaluate_expression(definition, {"rate": 0}) == 1
    assert evaluate_expression(definition, {"rate": -1}) == 0
    assert evaluate_expression(definition, {"rate": 1}) == 0

    fields = _legacy(
        expression={"left": "left_value", "op": "gte", "right_type": "field", "right": "right_value"},
    )
    assert evaluate_expression(fields, {"left_value": None, "right_value": None}) == 1  # 0 >= 0
    assert evaluate_expression(fields, {"left_value": None, "right_value": -1}) == 1   # 0 >= -1
    assert evaluate_expression(fields, {"left_value": -1, "right_value": None}) == 0
    # 两 0 在 eq 下是违规；不能沿用 legacy allow_equal 覆盖。
    equal_zero = _legacy(
        expression={"left": "left_value", "op": "eq", "right_type": "field", "right": "right_value"},
        equality_policy="allow_equal",
    )
    assert evaluate_expression(equal_zero, {"left_value": None, "right_value": None}) == 1


def test_zero_policy_rejects_empty_string_bool_nan_and_keeps_decimal_precision():
    for bad in ("", True, float("nan"), float("inf")):
        with pytest.raises(AppError):
            evaluate_expression(_legacy(), {"rate": bad})

    precise = _legacy(expression={
        "left": "left_value", "op": "eq", "right_type": "field", "right": "right_value",
    })
    assert evaluate_expression(precise, {
        "left_value": Decimal("1.250"), "right_value": Decimal("1.25"),
    }) == 1
    assert evaluate_expression(precise, {
        "left_value": Decimal("1.25"), "right_value": Decimal("1.3"),
    }) == 0
    assert evaluate_expression(_legacy(
        expression={"left": "rate", "op": "eq", "right_type": "value", "right": Decimal("2.50")},
    ), {"rate": Decimal("2.5")}) == 1


def test_review_null_is_missing_value_issue_not_skip_and_not_zero():
    definition = _legacy(null_policy="review")
    assert evaluate_expression(definition, {"rate": None}) == 1
    fields = _legacy(
        expression={"left": "left_value", "op": "gte", "right_type": "field", "right": "right_value"},
        null_policy="review",
    )
    assert evaluate_expression(fields, {"left_value": None, "right_value": None}) == 1
    assert evaluate_expression(fields, {"left_value": None, "right_value": -1}) == 1
    assert evaluate_expression(fields, {"left_value": -1, "right_value": None}) == 1
    # review 下 eq 两 0（真实 0，非 NULL）的数值语义仍按 op 计算。
    equal = _legacy(
        expression={"left": "left_value", "op": "eq", "right_type": "field", "right": "right_value"},
        null_policy="review", equality_policy="allow_equal",
    )
    assert evaluate_expression(equal, {"left_value": 0, "right_value": 0}) == 1


def test_split_null_handling_applies_per_side_mode():
    split = _legacy(
        expression={"left": "left_value", "op": "gte", "right_type": "field", "right": "right_value"},
        null_policy="review", null_handling={"left": "zero", "right": "review"},
    )
    # 左侧 NULL->0，右侧真实值 -1：0 >= -1 数值违规。
    assert evaluate_expression(split, {"left_value": None, "right_value": -1}) == 1
    # 右侧 NULL 属 review：缺失候选，不按 0 参与比较。
    assert evaluate_expression(split, {"left_value": 5, "right_value": None}) == 1


def test_relational_review_flags_matched_null_but_unmatched_stays_excluded():
    definition = _relational(null_policy="review")
    assert evaluate_case(definition, _nested_row(base={"quota": None}, related=[_related_row(limit_quota=5)])) == 1
    assert evaluate_case(definition, _nested_row(
        base={"quota": 1}, related=[_related_row(limit_quota=None)],
    )) == 1
    assert evaluate_case(definition, _nested_row(related=[_related_row(metric_id="OTHER")])) == 0
    assert evaluate_case(definition, _nested_row(base={"status": "B"})) == 0


def test_skip_date_text_and_unary_semantics_are_unchanged():
    date_skip = _legacy(
        expression={"left": "start_date", "op": "lt", "right_type": "field", "right": "end_date"},
        null_policy="skip",
    )
    assert evaluate_expression(date_skip, {"start_date": None, "end_date": "2026-01-01"}) == 0
    text_skip = _legacy(
        expression={"left": "label", "op": "neq", "right_type": "field", "right": "other_label"},
        null_policy="skip",
    )
    assert evaluate_expression(text_skip, {"label": "", "other_label": "X"}) == 0
    assert evaluate_expression(text_skip, {"label": None, "other_label": "X"}) == 0

    unary = _legacy(
        expression={"left": "quota", "op": "is_null"},
        null_policy="violate", equality_policy="allow_equal",
    )
    assert evaluate_relational(unary, _nested_row(base={"quota": None})) == 1
    assert evaluate_relational(unary, _nested_row(base={"quota": 0})) == 0


def test_relational_zero_uses_matched_rows_only_and_keeps_filters_join_keys():
    definition = _relational()
    # 关联行 limit_quota 为 None -> 0；基表 quota None -> 0；0 <= 0 违规。
    assert evaluate_case(definition, _nested_row(related=[_related_row(limit_quota=None)])) == 1
    # 只有 unmatched 关联行：仍按 unmatched exclusion，不参与比较。
    assert evaluate_case(definition, _nested_row(related=[_related_row(metric_id="OTHER")])) == 0
    # 筛选/关联键语义不变。
    assert evaluate_case(definition, _nested_row(base={"status": "B"})) == 0
    assert evaluate_case(definition, _nested_row(
        base={"metric_id": "BASE"}, related=[_related_row(metric_id="OTHER")],
    )) == 0
    # 单边 NULL：右侧 NULL->0，左侧 5 -> 5<=0 不违规；左侧 NULL->0，右侧 5 -> 0<=5 违规。
    assert evaluate_case(definition, _nested_row(base={"quota": 5}, related=[_related_row(limit_quota=None)])) == 0
    assert evaluate_case(definition, _nested_row(base={"quota": None}, related=[_related_row(limit_quota=5)])) == 1


def test_default_cases_for_review_flag_missing_value_and_zero_computes_against_zero():
    columns = [
        {"column_name": "metric_id", "data_type": "varchar"},
        {"column_name": "rate", "data_type": "decimal"},
        {"column_name": "status", "data_type": "varchar"},
        {"column_name": "report_date", "data_type": "date"},
    ]
    filters = [{"table": "base", "field": "status", "op": "eq", "value": "A", "confirmed": True}]
    review_definition = _legacy(null_policy="review", filters=filters)
    review_cases = default_field_compare_cases(review_definition, columns)
    null_case = next(case for case in review_cases if case["name"] == "空值")
    assert null_case["expected_count"] == 1
    assert null_case["expected_issue_kind"] == "missing_value"

    zero_definition = _legacy(filters=filters)
    zero_cases = default_field_compare_cases(zero_definition, columns)
    zero_null = next(case for case in zero_cases if case["name"] == "空值")
    # op lt 常量 0：NULL->0 后 0 < 0 不违规，无 issue kind。
    assert zero_null["expected_count"] == 0
    assert zero_null.get("expected_issue_kind") in (None, "numeric")
    zero_hit_definition = _legacy(
        expression={"left": "rate", "op": "gte", "right_type": "value", "right": 0}, filters=filters,
    )
    zero_hit_null = next(
        case for case in default_field_compare_cases(zero_hit_definition, columns)
        if case["name"] == "空值"
    )
    assert zero_hit_null["expected_count"] == 1
    assert zero_hit_null["expected_issue_kind"] == "numeric"
    for case in review_cases:
        assert evaluate_case(review_definition, case["row"]) == case["expected_count"]
    for case in zero_cases:
        assert evaluate_case(zero_definition, case["row"]) == case["expected_count"]

    legacy_skip = default_field_compare_cases(_legacy(null_policy="skip"), columns)
    assert [case["name"] for case in legacy_skip] == ["正常", "明显异常", "边界", "空值"]
    assert next(case for case in legacy_skip if case["name"] == "空值")["expected_count"] == 0


def test_refine_consumes_backend_policy_default_review_and_evidence_based_zero():
    base = {
        "rule_type": "field_compare",
        "expression": {"left": "quota", "op": "eq", "right_type": "value", "right": 0},
        "uncertainties": [], "unsupported_requirements": [],
        "equality_policy": "unresolved",
    }
    plain = refine_candidate({**base, "null_policy": "skip"},
                            columns=[{"column_name": "quota", "data_type": "decimal"}],
                            dialect="mysql", existing=[])
    assert plain["null_policy"] == "review"
    assert plain["null_handling"] == {"left": "review", "right": "review"}
    assert plain["null_evidence"] == []

    documented = refine_candidate(
        {**base, "null_policy": "skip"},
        columns=[{"column_name": "quota", "data_type": "decimal", "comment": "额度（空值视为0）"}],
        dialect="mysql", existing=[],
    )
    assert documented["null_policy"] == "zero"
    assert documented["null_handling"] == {"left": "zero", "right": "zero"}
    assert documented["null_evidence"]

    date = refine_candidate(
        {**base, "null_policy": "skip", "expression": {"left": "start_date", "op": "lt", "right_type": "value", "right": 0}},
        columns=[{"column_name": "start_date", "data_type": "date"}],
        dialect="mysql", existing=[],
    )
    assert date["null_policy"] == "skip"
    assert date["null_handling"] is None

    split = refine_candidate(
        {
            **base, "null_policy": "skip",
            "expression": {"left": "quota", "op": "eq", "right_type": "field", "right": "limit_quota"},
        },
        columns=[
            {"column_name": "quota", "data_type": "decimal", "comment": "额度（空值视为0）"},
            {"column_name": "limit_quota", "data_type": "decimal", "comment": "上限"},
        ],
        dialect="mysql", existing=[],
    )
    assert split["null_policy"] == "review"
    assert split["null_handling"] == {"left": "zero", "right": "review"}
    assert any(item["side"] == "left" for item in split["null_evidence"])


def test_core_is_new_spec_treats_explicit_zero_as_new_semantics():
    definition = _legacy(
        expression={"left": "rate", "op": "eq", "right_type": "value", "right": 0},
        filters=[{"table": "base", "field": "status", "op": "eq", "value": "A", "confirmed": True}],
    )
    assert is_new_spec(definition) is True


@pytest.mark.parametrize(("request_text", "op", "policy", "null_count"), [
    ("应收金额不得大于0", "gt", "zero", 0),
    ("应收金额不得小于0", "lt", "zero", 0),
    ("应收金额不得为0", "eq", "skip", 0),
    ("应收金额不得大于0，同时核查缺值", "gt", "review", 1),
])
def test_ai_numeric_constant_sql_respects_the_requested_checks(request_text, op, policy, null_count):
    rules, _model = _rules_with_doc([
        _select_payload(),
        _generate_payload(
            expression={"left": "amount", "op": op, "right_type": "value", "right": 0},
            null_policy="review",
        ),
    ], fields=[
        ("entry_id", "业务编号", "varchar", "Y"), ("amount", "应收金额", "decimal", ""),
        ("business_day", "数据日期", "date", ""),
    ])

    candidate = rules.parse_rule_request(user(), _request(request_text=request_text))
    preview = candidate["preview"]
    definition = preview["definition"]
    assert candidate["null_policy"] == definition["null_policy"] == policy
    sql = preview["sql_preview"]
    assert ("COALESCE(" in sql) == (policy == "zero")
    assert (" OR " in sql and "IS NULL" in sql) == (policy == "review")
    assert preview["sql_params"]["right_value"] == 0
    empty_case = next(case for case in preview["cases"] if case["name"] == "空值")
    assert empty_case["expected_count"] == null_count
    tests = rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"]})
    assert tests["failed_count"] == tests["not_run_count"] == 0
    saved = rules.save_draft(user(), definition)
    stored = rules.storage.latest_version(saved["id"])
    assert stored["sql_text"] == sql
    assert stored["content_sha256"] == preview["content_sha256"]
