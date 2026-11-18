from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_spec import query_ready


def _legacy(**overrides):
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
    return {"definition": definition}


def _relational():
    return {
        "rule_type": "field_compare",
        "dialect": "mysql",
        "table_name": "loan",
        "business_key": "row_id",
        "report_date_field": "report_date",
        "violation_message": "额度异常",
        "null_policy": "skip",
        "equality_policy": "allow_equal",
        "expression": {
            "left": "amount", "op": "gt", "right_type": "field",
            "right": "limit_amount", "right_table": "related",
        },
        "filters": [
            {"table": "base", "field": "status", "op": "in", "value": ["1", "2"], "confirmed": True},
            {"table": "related", "field": "is_valid", "op": "eq", "value": "Y", "confirmed": True},
        ],
        "join": {
            "table_name": "loan_detail",
            "on": [{"left": "project_code", "right": "project_code"}],
            "report_date_field": "report_date",
            "unmatched_policy": "exclude",
            "relationship_confirmed": True,
        },
    }


def test_legacy_sql_is_unchanged():
    sql, params = compile_rule(_legacy())
    assert sql == (
        "SELECT t.`project_code` AS business_key, '贷款期限异常' AS violation_message "
        "FROM `loan` AS t WHERE t.`report_date` = :report_date "
        "AND t.`maturity_date` IS NOT NULL AND t.`issue_date` IS NOT NULL "
        "AND t.`maturity_date` < t.`issue_date`"
    )
    assert params == {"report_date": None}
    assert query_ready(_legacy()["definition"]) is True


def test_filters_are_and_bound_and_join_uses_exists_semijoin():
    sql, params = compile_rule({"definition": _relational()})
    assert sql.count(" AND ") >= 4
    assert "(t.`status` IS NOT NULL AND t.`status` IN (:filter_1_0, :filter_1_1))" in sql
    assert "'1'" not in sql and "'2'" not in sql
    assert "filter_1_0" in params and params["filter_1_0"] == "1"
    assert "EXISTS (SELECT 1 FROM `loan_detail` AS o WHERE" in sql
    assert "o.`project_code` = t.`project_code`" in sql
    assert "o.`report_date` = :report_date" in sql
    assert "o.`is_valid` = :filter_2" in sql
    assert "t.`amount` > o.`limit_amount`" in sql
    assert "JOIN" not in sql.upper()


def test_right_table_related_comparison_stays_inside_exists():
    sql, params = compile_rule({"definition": _relational()})
    exists = sql.split("EXISTS (", 1)[1]
    assert "t.`amount` > o.`limit_amount`" in exists
    assert params["filter_2"] == "Y"


def test_value_constant_with_filters_is_bound():
    definition = _relational()
    definition["expression"] = {"left": "amount", "op": "gt", "right_type": "value", "right": 0}
    definition["join"] = None
    definition["filters"] = [
        {"table": "base", "field": "status", "op": "eq", "value": "1", "confirmed": True},
    ]
    sql, params = compile_rule({"definition": definition})
    assert "t.`amount` > :right_value" in sql
    assert "t.`status` = :filter_1" in sql
    assert params["right_value"] == 0 and params["filter_1"] == "1"


def test_unary_null_compiles_without_skip_predicate():
    for op, keyword in (("is_null", "IS NULL"), ("is_not_null", "IS NOT NULL")):
        definition = {
            "rule_type": "field_compare", "dialect": "mysql", "table_name": "loan",
            "business_key": "row_id", "report_date_field": "report_date",
            "violation_message": "开始日不能为空", "null_policy": "violate",
            "equality_policy": "allow_equal",
            "expression": {"left": "start_date", "op": op, "right_type": "field", "right": ""},
        }
        sql, params = compile_rule({"definition": definition})
        assert f"t.`start_date` {keyword}" in sql
        assert "start_date` IS NOT NULL" not in sql or keyword == "IS NOT NULL"
        assert params == {"report_date": None}
        assert query_ready(definition) is True


def test_negative_filter_binds_with_explicit_null_guard():
    definition = {
        "rule_type": "field_compare", "dialect": "postgresql", "table_name": "loan",
        "business_key": "row_id", "report_date_field": "report_date",
        "violation_message": "状态异常", "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
        "filters": [
            {"table": "base", "field": "status", "op": "not_in", "value": ["9"], "confirmed": True},
        ],
    }
    sql, params = compile_rule({"definition": definition})
    assert '(t."status" IS NOT NULL AND t."status" NOT IN (:filter_1_0))' in sql
    assert params["filter_1_0"] == "9"


def test_invalid_filter_and_join_structures_raise():
    bad_filters = _relational()
    bad_filters["filters"] = [{"table": "base", "field": "status", "op": "like", "value": "1"}]
    try:
        compile_rule({"definition": bad_filters})
    except AppError as exc:
        assert exc.code == "VALIDATION_ERROR"
    else:
        raise AssertionError("invalid filter op must be rejected")

    bad_join = _relational()
    bad_join["join"]["unmatched_policy"] = "violation"
    try:
        compile_rule({"definition": bad_join})
    except AppError as exc:
        assert exc.code == "VALIDATION_ERROR"
    else:
        raise AssertionError("unsupported unmatched_policy must be rejected")
