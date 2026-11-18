import pytest

from auto_check.modules.data_validation.candidate_preview import preview_definition, run_preview_cases
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_spec import query_ready


BASE_COLUMNS = [
    {"column_name": "row_id", "comment": "编号", "data_type": "varchar"},
    {"column_name": "project_code", "comment": "项目号", "data_type": "varchar"},
    {"column_name": "amount", "comment": "金额", "data_type": "decimal"},
    {"column_name": "status", "comment": "状态", "data_type": "varchar"},
    {"column_name": "start_date", "comment": "开始日", "data_type": "date"},
    {"column_name": "report_date", "comment": "报送日期", "data_type": "date"},
]
RELATED_COLUMNS = [
    {"column_name": "id", "comment": "明细编号", "data_type": "varchar"},
    {"column_name": "project_code", "comment": "项目号", "data_type": "varchar"},
    {"column_name": "limit_amount", "comment": "额度", "data_type": "decimal"},
    {"column_name": "is_valid", "comment": "有效标志", "data_type": "varchar"},
    {"column_name": "report_date", "comment": "报送日期", "data_type": "date"},
]


def _relational(**overrides):
    definition = {
        "name": "两表额度校验",
        "source_id": "src",
        "dialect": "mysql",
        "table_name": "loan",
        "business_key": "row_id",
        "report_date_field": "report_date",
        "rule_type": "field_compare",
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
    definition.update(overrides)
    return definition


def test_preview_returns_nested_relational_cases_and_all_pass():
    preview = preview_definition(_relational(), BASE_COLUMNS, RELATED_COLUMNS)
    assert preview["persisted"] is False
    assert preview["related_columns"][0]["column_name"] == "id"
    assert "EXISTS (SELECT 1 FROM `loan_detail` AS o" in preview["sql_preview"]
    result = run_preview_cases(preview)
    assert result["failed_count"] == 0 and result["not_run_count"] == 0
    assert result["passed_count"] == len(result["cases"])
    assert all(set(case["row"]) == {"base", "related", "report_date"} for case in result["cases"])
    names = {case["name"] for case in result["cases"]}
    assert {"正常", "明显异常", "边界", "空值", "关联多行", "日期不一致", "筛选不命中", "无关联记录", "关联键为空"} <= names


def test_unconfirmed_spec_compiles_but_all_cases_not_run():
    definition = _relational()
    definition["filters"][0]["confirmed"] = False
    definition["join"]["relationship_confirmed"] = False
    definition["join"]["unmatched_policy"] = "unresolved"
    assert query_ready(definition) is False
    preview = preview_definition(definition, BASE_COLUMNS, RELATED_COLUMNS)
    assert "EXISTS" in preview["sql_preview"]
    result = run_preview_cases(preview)
    assert result["passed_count"] == 0 and result["failed_count"] == 0
    assert result["not_run_count"] == len(result["cases"])


def test_unary_defaults_and_null_target_is_evaluated_not_skipped():
    definition = {
        "name": "开始日不能为空",
        "source_id": "src",
        "dialect": "mysql",
        "table_name": "loan",
        "business_key": "row_id",
        "report_date_field": "report_date",
        "rule_type": "field_compare",
        "violation_message": "开始日不能为空",
        "expression": {"left": "start_date", "op": "is_null", "right_type": "field", "right": ""},
    }
    preview = preview_definition(definition, BASE_COLUMNS)
    normalized = preview["definition"]["expression"]
    assert normalized == {"left": "start_date", "op": "is_null"}
    assert preview["definition"]["null_policy"] == "violate"
    assert preview["definition"]["equality_policy"] == "allow_equal"
    assert query_ready(preview["definition"]) is True
    result = run_preview_cases(preview)
    by_name = {case["name"]: case for case in result["cases"]}
    assert by_name["空值"]["expected_count"] == 1
    assert by_name["空值"]["actual_count"] == 1
    assert by_name["正常"]["actual_count"] == 0
    assert result["failed_count"] == 0


def test_nested_case_shape_is_validated_and_client_status_ignored():
    preview = preview_definition(_relational(), BASE_COLUMNS, RELATED_COLUMNS)
    good = preview["cases"][0]
    forged = [{**good, "status": "passed", "actual_count": 99, "expected_count": 1 - good["expected_count"]}]
    result = run_preview_cases(preview, forged)
    assert result["failed_count"] == 1 and result["passed_count"] == 0
    with pytest.raises(AppError):
        run_preview_cases(preview, [{**good, "row": {"base": {}, "related": [], "report_date": "2026-01-01"}}])
    with pytest.raises(AppError):
        run_preview_cases(preview, [{**good, "row": {"base": good["row"]["base"], "related": [], "report_date": "2026-01-01", "extra": 1}}])


def test_filters_only_new_spec_uses_nested_scope_samples():
    definition = {
        "name": "状态金额校验",
        "source_id": "src",
        "dialect": "mysql",
        "table_name": "loan",
        "business_key": "row_id",
        "report_date_field": "report_date",
        "rule_type": "field_compare",
        "violation_message": "金额异常",
        "null_policy": "skip",
        "equality_policy": "allow_equal",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
        "filters": [
            {"table": "base", "field": "status", "op": "eq", "value": "1", "confirmed": True},
        ],
    }
    preview = preview_definition(definition, BASE_COLUMNS)
    result = run_preview_cases(preview)
    assert result["failed_count"] == 0 and result["not_run_count"] == 0
    assert all(case["row"]["related"] == [] for case in result["cases"])
    assert {case["name"] for case in result["cases"]} >= {"正常", "明显异常", "筛选不命中"}


def test_join_date_must_be_strict_date_and_same_source_fields_exist():
    definition = _relational()
    related = [dict(column) for column in RELATED_COLUMNS]
    next(column for column in related if column["column_name"] == "report_date")["data_type"] = "datetime"
    with pytest.raises(AppError):
        preview_definition(definition, BASE_COLUMNS, related)

    missing = [column for column in RELATED_COLUMNS if column["column_name"] != "limit_amount"]
    with pytest.raises(AppError):
        preview_definition(definition, BASE_COLUMNS, missing)

    with pytest.raises(AppError):
        preview_definition(definition, BASE_COLUMNS, None)


def test_filter_value_type_must_match_column_type():
    definition = _relational()
    definition["filters"][0]["value"] = [1, 2]
    with pytest.raises(AppError):
        preview_definition(definition, BASE_COLUMNS, RELATED_COLUMNS)


def test_hash_changes_with_confirmation_and_filters():
    first = preview_definition(_relational(), BASE_COLUMNS, RELATED_COLUMNS)
    changed = _relational()
    changed["filters"][0]["confirmed"] = False
    second = preview_definition(changed, BASE_COLUMNS, RELATED_COLUMNS)
    assert first["content_sha256"] != second["content_sha256"]
