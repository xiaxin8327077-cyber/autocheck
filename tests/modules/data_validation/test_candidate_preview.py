import sqlite3

import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import user, service, loan_definition
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload


def generated(null_policy="skip"):
    rules, _ = _rules_with_doc([_select_payload(), _generate_payload(null_policy=null_policy)], fields=[
        ("row_id", "编号", "varchar", "Y"), ("c_projcode", "项目编号", "varchar", ""),
        ("c_projname", "项目名称", "varchar", ""),
        ("maturity_date", "到期日期", "date", ""),
        ("issue_date", "发放日期", "date", ""), ("report_date", "报送日期", "date", ""),
    ])
    candidate = rules.parse_rule_request(user(), _request())
    return rules, candidate


def test_analysis_returns_compiled_sql_and_cases_without_saving_or_business_queries():
    rules, candidate = generated()
    preview = candidate["preview"]
    assert preview and preview["persisted"] is False
    assert preview["sql_preview"].startswith("SELECT")
    assert preview["definition"]["business_key"] == "row_id"
    assert len(preview["cases"]) == 4
    assert rules.storage.visible_rules("1") == []
    # 日期比较按文档策略绑定 skip 后重预览，空值用例才计入通过/不通过。
    definition = {**preview["definition"], "null_policy": "skip"}
    resolved = rules.preview_candidate(user(), definition)
    evidence = rules.test_candidate(user(), {"definition": definition, "expected_hash": resolved["content_sha256"]})
    assert evidence["passed_count"] == 4
    assert evidence["not_run_count"] == 0
    assert evidence["persisted"] is False
    assert rules.storage.visible_rules("1") == []


def test_preview_formats_select_and_returns_checked_values_and_data_date():
    rules, candidate = generated()
    definition = {**candidate["preview"]["definition"], "null_policy": "skip",
                  "violation_message": "WHERE, AND ('核实')"}
    preview = rules.preview_candidate(user(), definition)
    formatted = preview["sql_display"]
    assert formatted.startswith("SELECT\n    ")
    assert '\nFROM "test_table" AS t\nWHERE ' in formatted
    assert "\n  AND " in formatted
    assert "WHERE, AND (''核实'')" in formatted
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE test_table (row_id, c_projcode, c_projname, maturity_date, issue_date, report_date)")
        conn.execute("INSERT INTO test_table VALUES (?, ?, ?, ?, ?, ?)",
                     ("1", "P1", "项目甲", "2026-10-01", "2026-10-02", "2026-10-31"))
        params = {**preview["sql_params"], "report_date": "2026-10-31"}
        displayed = dict(conn.execute(formatted, params).fetchone())
        assert displayed == dict(conn.execute(preview["sql_preview"], params).fetchone())
    assert displayed["到期日期"] == "2026-10-01"
    assert displayed["发放日期"] == "2026-10-02"
    assert displayed["报送日期"] == "2026-10-31"
    saved = rules.save_draft(user(), preview["definition"])
    version = rules.storage.latest_version(saved["id"])
    assert version["sql_text"] == preview["sql_preview"]
    assert version["content_sha256"] == preview["content_sha256"]


def test_explicit_empty_value_decision_precedes_first_hash_and_all_sample_cases():
    rules, candidate = generated("unresolved")
    assert candidate["preview"] is None and [q["id"] for q in candidate["questions"]] == ["null_policy"]
    definition = {**candidate, "questions": [], "name": candidate["rule_name"], "null_policy": "skip"}
    current = rules.preview_candidate(user(), definition)
    result = rules.test_candidate(user(), {"definition": definition, "expected_hash": current["content_sha256"]})
    assert result["passed_count"] == 4 and result["not_run_count"] == result["failed_count"] == 0
    with pytest.raises(AppError) as exc:
        rules.test_candidate(user(), {"definition": definition, "expected_hash": "stale-hash"})
    assert exc.value.code == "CONFLICT_VERSION"


def test_preview_ignores_client_sql_columns_and_returns_real_constant_binding():
    rules, _ = _rules_with_doc([_select_payload(), _generate_payload()], fields=[
        ("row_id", "项目编号", "varchar", "Y"), ("c_projname", "项目名称", "varchar", ""),
        ("amount", "实收信托", "decimal", ""),
        ("report_date", "报送日期", "date", ""),
    ])
    definition = {"name": "常量", "source_id": "src", "table_name": "test_table", "rule_type": "field_compare",
                  "business_key": "row_id", "expression": {"left": "amount", "op": "eq", "right_type": "value", "right": 0},
                  "violation_message": "请核实", "null_policy": "skip", "equality_policy": "allow_equal",
                  "sql": "DELETE FROM test_table", "columns": [{"column_name": "invented"}],
                  "result_aliases": {"checked_value": "客户端伪造"}}
    preview = rules.preview_candidate(user(), definition)
    assert "DELETE" not in preview["sql_preview"]
    assert "客户端伪造" not in preview["sql_preview"]
    assert preview["definition"]["result_aliases"]["checked_value"] == "实收信托"
    assert preview["sql_params"]["right_value"] == 0
    assert "sql" not in preview["definition"]
    definition["expression"]["left"] = "invented"
    with pytest.raises(AppError):
        rules.preview_candidate(user(), definition)


def test_case_payload_cannot_forge_passed_status_and_old_doc_mapping_is_rejected():
    rules, candidate = generated()
    definition = {**candidate["preview"]["definition"], "null_policy": "skip"}
    preview = rules.preview_candidate(user(), definition)
    cases = [{**case, "expected_count": 1 - case["expected_count"], "status": "passed", "actual_count": 99} for case in preview["cases"]]
    result = rules.test_candidate(user(), {"definition": definition, "cases": cases})
    assert result["failed_count"] == 4 and result["passed_count"] == 0
    with pytest.raises(AppError) as exc:
        rules.preview_candidate(user(), {**definition, "mapping_version": "doc-v-old"})
    assert exc.value.code == "CONFLICT_VERSION"


def test_ambiguous_fields_produce_real_choices_and_compile_without_another_model_call():
    rules, model = _rules_with_doc([_select_payload(), _generate_payload(expression={
        "left": "金额", "op": "eq", "right_type": "value", "right": 0,
    })], fields=[("row_id", "编号", "varchar", "Y"), ("c_projcode", "项目编号", "varchar", ""),
                ("c_projname", "项目名称", "varchar", ""),
                ("amount_a", "金额", "decimal", ""),
                ("amount_b", "金额", "decimal", ""), ("report_date", "报送日期", "date", "")])
    candidate = rules.parse_rule_request(user(), _request())
    question = candidate["questions"][0]
    assert question["id"] == "expression.left"
    assert {option["value"] for option in question["options"]} == {"amount_a", "amount_b"}
    assert candidate["preview"] is None
    definition = {**candidate, "questions": [], "name": candidate["rule_name"], "description": "金额零值提醒",
                  "expression": {**candidate["expression"], "left": "amount_b"},
                  "uncertainty_resolutions": ["明确选择 amount_b"]}
    preview = rules.preview_candidate(user(), definition)
    assert "amount_b" in preview["sql_preview"] and len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []


def test_real_date_choice_compiles_after_amount_choice_without_more_ai_calls():
    rules, model = _rules_with_doc([_select_payload(), _generate_payload(expression={
        "left": "实收金额", "op": "eq", "right_type": "value", "right": 0,
    })], fields=[("row_id", "编号", "varchar", "Y"), ("c_projcode", "项目编号", "varchar", ""),
                ("c_projname", "项目名称", "varchar", ""),
                ("amount_a", "实收金额", "decimal", ""),
                ("amount_b", "实收金额", "decimal", ""), ("balance_day", "余额日期", "date", ""),
                ("event_day", "成立日期", "date", ""), ("etl_time", "采集时间", "timestamp", "")])
    candidate = rules.parse_rule_request(user(), _request())
    assert candidate["preview"] is None
    # 唯一明确的期间列（余额日期）自动采用；事件日期与采集时间不得入选。
    assert candidate["report_date_field"] == "balance_day"
    assert [item["id"] for item in candidate["questions"]] == ["expression.left"]
    assert "report_date_field" not in {item["id"] for item in candidate["questions"]}
    definition = {**candidate, "questions": [], "name": candidate["rule_name"], "report_date_field": "balance_day",
                  "expression": {**candidate["expression"], "left": "amount_b"},
                  "uncertainty_resolutions": ["明确选择 amount_b"]}
    preview = rules.preview_candidate(user(), definition)
    assert '"balance_day" = :report_date' in preview["sql_preview"]
    assert 't."report_date"' not in preview["sql_preview"]
    assert preview["sql_params"]["right_value"] == 0
    other = rules.preview_candidate(user(), {**definition, "report_date_field": "event_day"})
    assert other["content_sha256"] != preview["content_sha256"]
    for field, code in (("", "PREVIEW_DATE_FIELD_REQUIRED"), ("invented", "PREVIEW_DATE_FIELD_INVALID"), ("etl_time", "PREVIEW_DATE_FIELD_INVALID")):
        with pytest.raises(AppError) as error:
            rules.preview_candidate(user(), {**definition, "report_date_field": field})
        assert error.value.code == code
    assert len(model.calls) == 2 and rules.storage.visible_rules("1") == []


@pytest.mark.parametrize("statuses", [[], ["not_run"], ["unknown"], ["passed", "not_run"], ["passed", "failed"]])
def test_confirmation_rejects_empty_or_not_all_passed_service_cases(monkeypatch, statuses):
    _database, rules = service()
    rule = rules.save_draft(user(), loan_definition())
    version = rules.storage.latest_version(rule["id"])
    monkeypatch.setattr(rules.storage, "list_cases", lambda *_args: [{"status": status} for status in statuses])
    with pytest.raises(AppError) as exc:
        rules.confirm_rule(user(), rule["id"], version["version_no"], version["content_sha256"])
    assert exc.value.code == "VALIDATION_ERROR"
    assert rules.storage.get_rule(rule["id"])["status"] == "draft"


def test_confirmation_rejects_an_older_version_even_with_a_matching_old_hash():
    _database, rules = service()
    rule = rules.save_draft(user(), loan_definition())
    previous = rules.storage.latest_version(rule["id"])
    rules.save_draft(user(), loan_definition(description="新版要求"), rule["id"])
    with pytest.raises(AppError) as exc:
        rules.confirm_rule(user(), rule["id"], previous["version_no"], previous["content_sha256"])
    assert exc.value.code == "CONFLICT_VERSION"


@pytest.mark.parametrize("cases", [[], [{}], "bad", [{"name": "x", "row": {}, "expected_count": True}], [{}] * 101])
def test_preview_cases_are_bounded_and_typed(cases):
    rules, candidate = generated()
    with pytest.raises(AppError):
        rules.test_candidate(user(), {"definition": candidate["preview"]["definition"], "cases": cases})
