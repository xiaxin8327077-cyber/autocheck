from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.test_runner import default_field_compare_cases, evaluate_case

_OPERATORS = [("eq", "="), ("neq", "<>"), ("lt", "<"), ("lte", "<="), ("gt", ">"), ("gte", ">=")]


def _definition(**overrides):
    definition = {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "table_name": "loan",
        "business_key": "project_code",
        "violation_message": "贷款期限异常",
        "null_policy": "skip",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
    }
    definition.update(overrides)
    return definition


def test_loan_term_compiles_for_both_dialects() -> None:
    definition = {
        "rule_type": "field_compare",
        "table_name": "loan",
        "business_key": "project_code",
        "violation_message": "贷款期限异常",
        "null_policy": "skip",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
    }
    for dialect in ("mysql", "postgresql"):
        sql, params = compile_rule({"definition": {**definition, "dialect": dialect}})
        assert "maturity_date" in sql and "<" in sql and "issue_date" in sql
        assert ":report_date" in sql
        assert "business_key" in sql and "violation_message" in sql
        assert "IS NOT NULL" in sql
        assert "report_date" in params


def test_amount_equation_uses_tolerance() -> None:
    sql, params = compile_rule({"definition": {
        "rule_type": "amount_equation",
        "dialect": "mysql",
        "table_name": "balance",
        "business_key": "id",
        "assets": "assets",
        "liabilities": "liabilities",
        "equity": "equity",
        "tolerance": 0.01,
        "violation_message": "不平",
    }})
    assert ":tolerance" in sql
    assert params["tolerance"] == 0.01
    assert "0.01" not in sql


def test_field_compare_defaults_to_field_right_type() -> None:
    """旧版表达式没有 right_type，仍按字段比较编译，不产生绑定常量。"""
    sql, params = compile_rule({"definition": _definition()})
    assert "maturity_date" in sql and "issue_date" in sql and "<" in sql
    assert "right_value" not in params
    explicit_sql, explicit_params = compile_rule({"definition": _definition(
        expression={"left": "maturity_date", "op": "lt", "right": "issue_date", "right_type": "field"},
    )})
    assert explicit_sql == sql
    assert explicit_params == params


@pytest.mark.parametrize("op, symbol", _OPERATORS)
@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_field_compare_supports_full_operator_matrix(dialect: str, op: str, symbol: str) -> None:
    sql, _params = compile_rule({"definition": _definition(
        dialect=dialect,
        expression={"left": "maturity_date", "op": op, "right": "issue_date"},
    )})
    quoted = "`" if dialect == "mysql" else '"'
    assert f"t.{quoted}maturity_date{quoted} {symbol} t.{quoted}issue_date{quoted}" in sql


@pytest.mark.parametrize("op, symbol", _OPERATORS)
@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_numeric_constant_matrix_uses_bound_parameter(dialect: str, op: str, symbol: str) -> None:
    sql, params = compile_rule({"definition": _definition(
        dialect=dialect,
        expression={"left": "amount", "op": op, "right_type": "value", "right": 100},
    )})
    assert ":right_value" in sql
    assert params["right_value"] == 100
    assert "100" not in sql
    assert symbol in sql
    # 常量不是字段，skip 只对左字段判空。
    assert sql.count("IS NOT NULL") == 1


def test_numeric_zero_constant_is_valid_and_not_concatenated() -> None:
    sql, params = compile_rule({"definition": _definition(
        expression={"left": "amount", "op": "eq", "right_type": "value", "right": 0},
    )})
    assert params["right_value"] == 0
    assert ":right_value" in sql
    assert "= :right_value" in sql


def test_numeric_constant_does_not_treat_constant_as_quoted_column() -> None:
    sql, _params = compile_rule({"definition": _definition(
        dialect="mysql",
        expression={"left": "amount", "op": "gt", "right_type": "value", "right": 12345.5},
    )})
    assert "`12345.5`" not in sql
    assert "t.`amount` > :right_value" in sql


@pytest.mark.parametrize("value", [
    True, False, None, "0", "1.5", float("nan"), float("inf"), float("-inf"), [0], {"value": 0},
])
def test_invalid_numeric_constant_raises(value) -> None:
    with pytest.raises(AppError) as caught:
        compile_rule({"definition": _definition(
            expression={"left": "amount", "op": "eq", "right_type": "value", "right": value},
        )})
    assert caught.value.code == "VALIDATION_ERROR"


@pytest.mark.parametrize("right_type", ["column", "VALUE", "constant", 1, ["value"]])
def test_invalid_right_type_raises(right_type) -> None:
    with pytest.raises(AppError) as caught:
        compile_rule({"definition": _definition(
            expression={"left": "amount", "op": "eq", "right_type": right_type, "right": 0},
        )})
    assert caught.value.code == "VALIDATION_ERROR"


def test_value_mode_requires_right_constant() -> None:
    with pytest.raises(AppError) as caught:
        compile_rule({"definition": _definition(
            expression={"left": "amount", "op": "eq", "right_type": "value"},
        )})
    assert caught.value.code == "VALIDATION_ERROR"


def test_huge_int_constant_does_not_overflow() -> None:
    huge = 10 ** 400
    sql, params = compile_rule({"definition": _definition(
        expression={"left": "amount", "op": "lt", "right_type": "value", "right": huge},
    )})
    assert params["right_value"] == huge
    assert ":right_value" in sql


class _Metadata:
    def __init__(self, columns) -> None:
        self.columns = columns
        self.calls: list[tuple[str, dict]] = []

    def describe_table(self, _source_id, _table_name):
        return {"columns": self.columns, "mapping_version": "map"}

    def execute_select(self, _source_id, sql, params, timeout_seconds, max_rows):
        self.calls.append((sql, dict(params)))
        return SimpleNamespace(columns=("business_key",), rows=(), truncated=False)


def test_constant_right_is_not_checked_as_column_for_drift() -> None:
    metadata = _Metadata([
        {"column_name": "project_code", "data_type": "varchar"},
        {"column_name": "amount", "data_type": "decimal"},
        {"column_name": "report_date", "data_type": "date"},
    ])
    version = {"definition": _definition(
        expression={"left": "amount", "op": "gt", "right_type": "value", "right": 0},
    )}
    run = execute_version(version, {"report_date": "2026-09-30"}, metadata)
    assert run.status == "PASS" and run.error_code == ""
    sql, params = metadata.calls[0]
    assert ":right_value" in sql and params["right_value"] == 0


def test_missing_field_right_still_reports_mapping_drift() -> None:
    metadata = _Metadata([
        {"column_name": "project_code", "data_type": "varchar"},
        {"column_name": "amount", "data_type": "decimal"},
    ])
    version = {"definition": _definition(
        expression={"left": "amount", "op": "gt", "right": "missing_amount"},
    )}
    run = execute_version(version, {}, metadata)
    assert run.status == "ERROR" and run.error_code == "MAPPING_DRIFT"
    assert metadata.calls == []


@pytest.mark.parametrize("op", ["eq", "neq", "lt", "lte", "gt", "gte"])
def test_numeric_constant_case_matrix_is_self_consistent(op: str) -> None:
    definition = _definition(
        equality_policy="reject_equal",
        expression={"left": "amount", "op": op, "right_type": "value", "right": 100},
    )
    cases = default_field_compare_cases(definition, [{"column_name": "amount", "data_type": "decimal"}])
    assert [case["name"] for case in cases] == ["正常", "明显异常", "边界", "空值"]
    for case in cases:
        assert set(case["row"]) == {"amount"}
        assert evaluate_case(definition, case["row"]) == case["expected_count"]


def test_numeric_zero_case_matrix_is_self_consistent() -> None:
    definition = _definition(
        equality_policy="reject_equal",
        expression={"left": "amount", "op": "eq", "right_type": "value", "right": 0},
    )
    cases = default_field_compare_cases(definition, [{"column_name": "amount", "data_type": "numeric"}])
    assert [case["expected_count"] for case in cases] == [0, 1, 1, 0]
    for case in cases:
        assert evaluate_case(definition, case["row"]) == case["expected_count"]


def test_field_compare_case_generator_keeps_both_columns() -> None:
    definition = _definition()
    cases = default_field_compare_cases(definition, [
        {"column_name": "maturity_date", "data_type": "date"},
        {"column_name": "issue_date", "data_type": "date"},
    ])
    assert all(set(case["row"]) == {"maturity_date", "issue_date"} for case in cases)
    for case in cases:
        assert evaluate_case(definition, case["row"]) == case["expected_count"]


def test_default_cases_reject_invalid_constant() -> None:
    definition = _definition(expression={"left": "amount", "op": "eq", "right_type": "value", "right": True})
    with pytest.raises(AppError) as caught:
        default_field_compare_cases(definition, [])
    assert caught.value.code == "VALIDATION_ERROR"


def test_execute_version_rebuilds_bound_params_from_stored_sql_text() -> None:
    definition = _definition(
        expression={"left": "amount", "op": "gt", "right_type": "value", "right": 100},
    )
    sql, _compiled = compile_rule({"definition": definition})
    metadata = _Metadata([
        {"column_name": "project_code", "data_type": "varchar"},
        {"column_name": "amount", "data_type": "decimal"},
        {"column_name": "report_date", "data_type": "date"},
    ])
    version = {"definition": definition, "sql_text": sql}
    run = execute_version(version, {"report_date": "2026-09-30", "right_value": 999}, metadata)
    assert run.status == "PASS" and run.error_code == ""
    executed_sql, bound = metadata.calls[0]
    assert executed_sql == sql
    assert bound["right_value"] == 100
    assert bound["report_date"] == "2026-09-30"


@pytest.mark.parametrize("equality_policy", ["allow_equal", "reject_equal"])
@pytest.mark.parametrize("op, symbol", _OPERATORS)
def test_numeric_constant_semantics_follow_sql_operator(
    op: str, symbol: str, equality_policy: str,
) -> None:
    definition = _definition(
        equality_policy=equality_policy,
        expression={"left": "amount", "op": op, "right_type": "value", "right": 0},
    )
    sql, params = compile_rule({"definition": definition})
    assert symbol in sql and params["right_value"] == 0
    cases = default_field_compare_cases(definition, [{"column_name": "amount", "data_type": "decimal"}])
    assert [case["name"] for case in cases] == ["正常", "明显异常", "边界", "空值"]
    by_name = {case["name"]: case for case in cases}
    for case in cases:
        assert evaluate_case(definition, case["row"]) == case["expected_count"]
    # 常量模式忽略 equality_policy：违规样本必须命中，边界严格按 op 判定。
    assert evaluate_case(definition, by_name["明显异常"]["row"]) == 1
    assert evaluate_case(definition, by_name["边界"]["row"]) == (0 if op in ("lt", "gt", "neq") else 1)


def test_numeric_constant_eq_zero_hits_even_when_equality_allowed() -> None:
    definition = _definition(
        equality_policy="allow_equal",
        expression={"left": "amount", "op": "eq", "right_type": "value", "right": 0},
    )
    assert evaluate_case(definition, {"amount": 0}) == 1
    cases = default_field_compare_cases(definition, [{"column_name": "amount", "data_type": "decimal"}])
    boundary = [case for case in cases if case["name"] == "边界"][0]
    assert boundary["expected_count"] == 1


def test_field_compare_keeps_legacy_allow_equal_override() -> None:
    definition = _definition(
        equality_policy="allow_equal",
        expression={"left": "maturity_date", "op": "lt", "right": "issue_date"},
    )
    assert evaluate_case(definition, {"maturity_date": "2026-01-01", "issue_date": "2026-01-01"}) == 0
    assert evaluate_case(definition, {"maturity_date": "2026-01-01", "issue_date": "2026-01-02"}) == 1
