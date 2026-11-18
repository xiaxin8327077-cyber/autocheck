from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError


def _definition(**overrides):
    definition = {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "table_name": "contract",
        "business_key": "contract_no",
        "report_date_field": "report_date",
        "violation_message": "金额异常",
        "null_policy": "skip",
        "equality_policy": "allow_equal",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
    }
    definition.update(overrides)
    return definition


def test_legacy_sql_without_context_is_byte_identical():
    legacy = _definition()
    sql, params = compile_rule({"definition": legacy})
    assert sql == (
        "SELECT t.`contract_no` AS business_key, '金额异常' AS violation_message "
        "FROM `contract` AS t WHERE t.`report_date` = :report_date "
        "AND t.`amount` IS NOT NULL AND t.`amount` > :right_value"
    )
    assert params == {"report_date": None, "right_value": 0}


def test_base_context_adds_only_output_columns_in_both_dialects():
    context = {"mode": "base", "code_field": "project_code", "name_field": "project_name", "confirmed": True}
    for dialect, quoted in (("mysql", "`"), ("postgresql", '"')):
        sql, _params = compile_rule({"definition": _definition(dialect=dialect, project_context=context)})
        assert f"AS violation_message, 'comparison' AS issue_kind, t.{quoted}project_code{quoted} AS project_code" in sql
        assert f"t.{quoted}project_name{quoted} AS project_name FROM" in sql
        assert "JOIN" not in sql.upper()


def test_lookup_context_uses_correlated_count_and_max_without_join_or_where_change():
    context = {
        "mode": "lookup", "code_field": "project_code", "name_field": "project_name",
        "table_name": "dim_project", "key": {"left": "project_code", "right": "project_code"},
        "date_field": "report_date",
        "unique_evidence": {"kind": "pk", "fields": ["project_code", "report_date"], "confirmed": True},
        "confirmed": True,
    }
    sql, params = compile_rule({"definition": _definition(project_context=context)})
    assert "EXISTS" not in sql.upper()
    assert " JOIN " not in sql.upper()
    assert "(SELECT CASE WHEN COUNT(*) = 1 THEN MAX(p.`project_name`) END FROM `dim_project` AS p WHERE p.`project_code` = t.`project_code` AND p.`report_date` = :report_date) AS project_name" in sql
    assert "(SELECT COUNT(*) FROM `dim_project` AS p WHERE p.`project_code` = t.`project_code` AND p.`report_date` = :report_date) AS project_match_count" in sql
    # 输出维度不得改变业务 WHERE：外层仍只有日期与金额谓词。
    outer_where = sql.split(" FROM `contract` AS t WHERE ", 1)[1].split(" AND (SELECT", 1)[0]
    assert outer_where.count(" AND ") == 2
    assert "right_value" in params and params["right_value"] == 0


def test_lookup_without_date_requires_key_only_unique_evidence():
    context = {
        "mode": "lookup", "code_field": "project_code", "name_field": "project_name",
        "table_name": "dim_project", "key": {"left": "project_code", "right": "project_code"},
        "date_field": None,
        "unique_evidence": {"kind": "pk", "fields": ["project_code"], "confirmed": True},
        "confirmed": True,
    }
    sql, _params = compile_rule({"definition": _definition(project_context=context)})
    assert "p.`report_date`" not in sql
    assert "COUNT(*) = 1" in sql


def test_context_rejected_for_unsupported_rule_types():
    context = {"mode": "base", "code_field": "project_code", "name_field": "project_name", "confirmed": True}
    for definition in (
        _definition(rule_type="unique", keys=["contract_no"]),
        _definition(rule_type="custom_sql", sql="SELECT 1"),
        _definition(rule_type="enum", field="status", allowed=["1"]),
    ):
        try:
            compile_rule({"definition": {**definition, "project_context": context}})
        except AppError as exc:
            assert exc.code == "VALIDATION_ERROR"
        else:
            raise AssertionError(f"{definition['rule_type']} 不得静默支持 project_context")
