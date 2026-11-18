from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.query_spec import (
    apply_numeric_null_policy,
    infer_numeric_null_handling,
    is_new_spec,
    query_ready,
)


def _field(name, data_type="decimal", **extra):
    return {"column_name": name, "data_type": data_type, **extra}


def _definition(**overrides):
    definition = {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "table_name": "loan",
        "business_key": "row_id",
        "report_date_field": "report_date",
        "violation_message": "金额异常",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
    }
    definition.update(overrides)
    return definition


def test_infer_defaults_to_review_and_reads_explicit_doc_evidence_only():
    plain = [_field("amount")]
    inferred = infer_numeric_null_handling(_definition(), plain)
    assert inferred["applicable"] is True
    assert inferred["null_policy"] == "review"
    assert inferred["null_handling"] == {"left": "review", "right": "review"}
    assert is_new_spec({**_definition(), "null_policy": "review"}) is True

    evidenced = [_field("amount", comment="空值视为0")]
    inferred = infer_numeric_null_handling(_definition(), evidenced)
    assert inferred["null_policy"] == "zero"
    assert inferred["null_handling"]["left"] == "zero"

    # 字段名/default/nullable/类型都不能作为零化证据。
    for name in ("amount_zero", "amount"):
        trap = _field(name, default_value="0", nullable="YES", comment="上报金额", logic="直取")
        result = infer_numeric_null_handling(
            _definition(expression={"left": name, "op": "gt", "right_type": "value", "right": 0}),
            [trap],
        )
        assert result["null_policy"] == "review"

    # 日期比较不绑定数值策略，保留原口径。
    date_def = _definition(
        expression={"left": "start_date", "op": "lt", "right_type": "value", "right": 0},
    )
    assert infer_numeric_null_handling(date_def, [_field("start_date", "date")])["applicable"] is False


def test_zero_evidence_rejects_empty_string_upstream_negation_condition_and_mixed_text():
    definition = lambda left: _definition(expression={"left": left, "op": "gt", "right_type": "value", "right": 0})
    cases = [
        (_field("a", comment="空串视为0"), "empty-string"),
        (_field("b", comment="空白按0处理"), "whitespace"),
        (_field("c", field_cn="金额", logic="直取", source_field_cn="上游字段，NULL视为0"), "upstream-source"),
        (_field("d", comment="不得将NULL视为0"), "negation"),
        (_field("e", comment="尚未确定空值是否按0处理"), "unconfirmed-question"),
        (_field("f", comment="若结算状态为空，则NULL视为0"), "conditional"),
        (_field("g", field_cn="金额", logic="本列不允许为空；空值视为0", comment="另一句"), "mixed-negate-positive"),
        (_field("h", dictionary="NULL=0", field_cn="金额", logic="直取"), "dictionary-only"),
        (_field("null_zero_value", field_cn="金额", logic="直取"), "physical-name-only"),
    ]
    for field, label in cases:
        result = infer_numeric_null_handling(definition(field["column_name"]), [field])
        assert result["null_policy"] == "review", f"{label} 不得推断为零化"

    positive = [
        _field("p1", field_cn="金额", comment="本列空值视为0"),
        _field("p2", field_cn="金额", logic="文档明确：NULL=0"),
    ]
    for field in positive:
        result = infer_numeric_null_handling(definition(field["column_name"]), [field])
        assert result["null_policy"] == "zero", f"{field['column_name']} 应有明确无条件零化事实"


def test_zero_policy_only_binds_real_numeric_column_types():
    numeric = infer_numeric_null_handling(
        _definition(),
        [_field("amount", "decimal", comment="NULL视为0")],
    )
    assert numeric["null_policy"] == "zero"
    text_def = _definition(expression={"left": "remark", "op": "eq", "right_type": "value", "right": 0})
    assert infer_numeric_null_handling(text_def, [_field("remark", "varchar", comment="NULL视为0")])["applicable"] is False


def test_apply_binds_review_or_documented_zero_without_mutating_input():
    definition = _definition()
    bound = apply_numeric_null_policy(definition, [_field("amount")])
    assert bound["null_policy"] == "review"
    assert bound["null_handling"] == {"left": "review", "right": "review"}
    assert definition.get("null_policy") is None
    assert "null_evidence" in bound

    zero = apply_numeric_null_policy(
        _definition(), [_field("amount", logic="文档明确：NULL按0处理")],
    )
    assert zero["null_policy"] == "zero"
    assert zero["null_evidence"]


def test_query_ready_accepts_review_for_numeric_and_rejects_non_numeric_review():
    from auto_check.modules.data_validation.candidate_preview import preview_definition
    columns = [
        _field("row_id", "varchar"), _field("amount", "decimal"),
        _field("report_date", "date"),
    ]
    definition = _definition(null_policy="review", equality_policy="allow_equal")
    preview = preview_definition(definition, columns)
    assert preview["definition"]["null_policy"] == "review"
    date_columns = [
        _field("row_id", "varchar"), _field("start_date", "date"),
        _field("report_date", "date"),
    ]
    try:
        preview_definition(
            _definition(null_policy="review", equality_policy="allow_equal",
                         expression={"left": "start_date", "op": "lt", "right_type": "value", "right": 0}),
            date_columns,
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "VALIDATION_ERROR"
    else:
        raise AssertionError("日期比较不得绑定 review")


def test_base_review_sql_uses_fixed_missing_or_comparison_template():
    definition = _definition(null_policy="review", equality_policy="allow_equal")
    sql, params = compile_rule({"definition": definition})
    assert "COALESCE" not in sql
    assert "(t.`amount` > :right_value OR t.`amount` IS NULL)" in sql
    assert "AS violation_message, CASE WHEN t.`amount` IS NULL THEN 'missing_value' ELSE 'numeric' END AS issue_kind" in sql
    assert params["dv_missing_left"] == "缺值待核实：amount 为 NULL"
    assert "IS NOT NULL" not in sql


def test_two_field_review_reports_both_missing_fields():
    definition = _definition(
        null_policy="review", equality_policy="allow_equal",
        expression={"left": "amount_a", "op": "gt", "right": "amount_b"},
    )
    sql, params = compile_rule({"definition": definition})
    assert "(t.`amount_a` > t.`amount_b` OR t.`amount_a` IS NULL OR t.`amount_b` IS NULL)" in sql
    assert "dv_missing_both" in params and "amount_a" in params["dv_missing_both"] and "amount_b" in params["dv_missing_both"]


def test_documented_zero_still_coalesces_and_skips_missing_candidate():
    definition = _definition(
        null_policy="zero", equality_policy="allow_equal",
        null_handling={"left": "zero", "right": "zero"},
        null_evidence=[{"side": "left", "field": "amount", "source": "NULL视为0"}],
    )
    sql, _params = compile_rule({"definition": definition})
    assert "COALESCE(t.`amount`, 0) > :right_value" in sql
    assert "IS NULL" not in sql


def _sqlite_run(sql, params, script):
    import sqlite3
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(script)
        cursor = connection.execute(sql, params)
        columns = tuple(item[0] for item in cursor.description or ())
        return columns, cursor.fetchall()
    finally:
        connection.close()


def test_sqlite_base_review_keeps_missing_and_true_violations_without_zeroing():
    definition = _definition(null_policy="review", equality_policy="allow_equal")
    sql, params = compile_rule({"definition": definition})
    script = """
        CREATE TABLE loan (row_id TEXT, amount REAL, report_date TEXT);
        INSERT INTO loan VALUES ('A', NULL, '2026-09-30');
        INSERT INTO loan VALUES ('B', 0, '2026-09-30');
        INSERT INTO loan VALUES ('C', 10, '2026-09-30');
        INSERT INTO loan VALUES ('D', -5, '2026-09-30');
        INSERT INTO loan VALUES ('E', NULL, '2026-09-30');
    """
    columns, rows = _sqlite_run(sql, {**params, "report_date": "2026-09-30"}, script)
    result = [dict(zip(columns, row)) for row in rows]
    assert {item["business_key"] for item in result} == {"A", "C", "E"}
    kinds = {item["business_key"]: item["issue_kind"] for item in result}
    assert kinds == {"A": "missing_value", "C": "numeric", "E": "missing_value"}
    assert all("缺值待核实：amount" in item["violation_message"] for item in result if item["issue_kind"] == "missing_value")


def test_sqlite_related_review_prioritizes_real_violation_and_does_not_amplify_or_fake_missing_row():
    definition = _definition(
        null_policy="review", equality_policy="allow_equal",
        expression={"left": "amount", "op": "gt", "right_type": "field", "right": "limit_amount",
                    "right_table": "related"},
        join={"table_name": "contract_limit", "on": [{"left": "contract_no", "right": "contract_no"}],
              "report_date_field": "report_date", "unmatched_policy": "exclude",
              "relationship_confirmed": True},
    )
    sql, params = compile_rule({"definition": definition})
    script = """
        CREATE TABLE loan (row_id TEXT, contract_no TEXT, amount REAL, report_date TEXT);
        CREATE TABLE contract_limit (contract_no TEXT, limit_amount REAL, report_date TEXT);
        INSERT INTO loan VALUES ('C1','K1',10,'2026-09-30');
        INSERT INTO loan VALUES ('C2','K2',10,'2026-09-30');
        INSERT INTO loan VALUES ('C3','K3',10,'2026-09-30');
        INSERT INTO loan VALUES ('C4','K4',NULL,'2026-09-30');
        INSERT INTO loan VALUES ('C5','K5',10,'2026-09-30');
        INSERT INTO loan VALUES ('C6','K6',10,'2026-09-30');
        INSERT INTO contract_limit VALUES ('K1',NULL,'2026-09-30');
        INSERT INTO contract_limit VALUES ('K1',5,'2026-09-30');
        INSERT INTO contract_limit VALUES ('K2',NULL,'2026-09-30');
        INSERT INTO contract_limit VALUES ('K4',5,'2026-09-30');
        INSERT INTO contract_limit VALUES ('K5',NULL,'2026-09-30');
        INSERT INTO contract_limit VALUES ('K5',20,'2026-09-30');
        INSERT INTO contract_limit VALUES ('K6',5,'2026-09-30');
        INSERT INTO contract_limit VALUES ('K6',1,'2026-09-30');
    """
    columns, rows = _sqlite_run(sql, {**params, "report_date": "2026-09-30"}, script)
    result = [dict(zip(columns, row)) for row in rows]
    # C3 无关联记录仍按 unmatched 排除；其余每基表行最多一条，不放大。
    assert {item["business_key"] for item in result} == {"C1", "C2", "C4", "C5", "C6"}
    kinds = {item["business_key"]: item["issue_kind"] for item in result}
    assert kinds == {
        "C1": "numeric",      # 同时存在真违规与 NULL：数字违规优先
        "C2": "missing_value",
        "C4": "missing_value",  # 左值为 NULL
        "C5": "missing_value",  # 有真值但无违规，另有 NULL
        "C6": "numeric",      # 多条相关记录只出一行
    }
    assert len([item for item in result if item["business_key"] == "C1"]) == 1


def test_rule_run_rows_keep_issue_kind_for_persistence():
    from types import SimpleNamespace
    from auto_check.modules.data_validation.executor import execute_version

    class Metadata:
        def describe_table(self, _source, table):
            return {"columns": [
                {"column_name": "row_id", "data_type": "varchar"},
                {"column_name": "amount", "data_type": "decimal"},
                {"column_name": "report_date", "data_type": "date"},
            ], "mapping_version": "map"}

        def execute_select(self, _source, sql, params, timeout_seconds, max_rows):
            return SimpleNamespace(
                columns=("business_key", "violation_message", "issue_kind"),
                rows=(("A", "缺值待核实：amount 为 NULL", "missing_value"),),
                truncated=False,
            )

    run = execute_version(
        {"definition": _definition(null_policy="review", equality_policy="allow_equal")},
        {"report_date": "2026-09-30"}, Metadata(),
    )
    assert run.status == "VIOLATION" and run.violation_count == 1
    assert run.columns == ("business_key", "violation_message", "issue_kind")
    assert run.rows[0]["issue_kind"] == "missing_value"
    assert "amount" in run.rows[0]["violation_message"]
