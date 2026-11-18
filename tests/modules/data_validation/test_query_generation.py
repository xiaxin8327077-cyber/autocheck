from copy import deepcopy

import pytest
from sqlalchemy import insert, update

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.generation_policy import review_ready
from auto_check.modules.data_validation.project_context import infer_project_context
from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_followup_service_bridge import _rules


FIELDS = [("row_id", "项目编号", "varchar", "Y"), ("c_projname", "项目名称", "varchar", ""),
          ("amount", "实收信托", "numeric", ""),
          ("start_date", "项目开始日", "date", ""), ("status", "项目状态", "varchar", ""),
          ("report_status", "项目状态", "varchar", ""), ("business_day", "数据日期", "date", "")]


def make_rules(*, unary=False, related=False):
    selection = _select_payload()
    if related:
        selection["related_target"] = {"table": "state_table"}
    expression = {"left": "项目开始日", "op": "is_null"} if unary else {
        "left": "amount", "op": "eq", "right_type": "value", "right": 0}
    draft = _generate_payload(expression=expression)
    draft["filters"] = [{"table": "related" if related else "base", "field": "status", "op": "eq", "value": "1", "confirmed": True}]
    if related:
        draft["join"] = {"table_name": "state_table", "on": [{"left": "row_id", "right": "row_id"}],
                         "report_date_field": "business_day", "relationship_confirmed": True, "unmatched_policy": "exclude"}
    rules, model = _rules_with_doc([selection, draft], fields=FIELDS)
    table = rules.storage.doc_tables(rules.storage.active_document()["id"])[0]
    with rules.storage.database.begin() as connection:
        for name, dictionary in [("status", "【D1】\n0-已完结\n1-存续"), ("report_status", "【D2】\n0-本月销户\n1-已完结未销户\n2-存续")]:
            connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == table["id"], DOC_FIELDS.c.field_name == name).values(dictionary=dictionary))
        if related:
            second = {key: value for key, value in table.items() if key != "id"}
            second.update(table_name="state_table", table_name_cn="项目状态表")
            related_id = connection.execute(insert(DOC_TABLES).values(**second)).inserted_primary_key[0]
            for field in rules.storage.doc_fields(table["id"]):
                copied = {key: value for key, value in field.items() if key != "id"}
                copied["table_id"] = related_id
                connection.execute(insert(DOC_FIELDS).values(**copied))
    return rules, model


def resolved_definition(candidate):
    definition = {**candidate, "name": candidate["rule_name"], "description": "存续项目校验", "report_date_field": "business_day"}
    choice = next(item for item in candidate["questions"] if item["id"] == "filters.0")["options"][1]
    definition["filters"] = [deepcopy(choice["selection"])]
    definition["uncertainty_resolutions"] = [choice["label"] for _ in definition["uncertainties"]]
    if definition.get("join"):
        definition["join"] = {**definition["join"], "relationship_confirmed": True, "unmatched_policy": "exclude", "report_date_field": "business_day"}
    return definition


def test_begin_date_required_with_documented_scope_is_not_rejected_as_unsupported():
    rules, model = make_rules(unary=True)
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目项目开始日不能为空"))
    assert candidate["unsupported_requirements"] == []
    assert candidate["expression"] == {"left": "start_date", "op": "is_null"}
    assert candidate["null_policy"] == "violate"
    assert candidate["equality_policy"] == "allow_equal"
    assert candidate["preview"] is None
    definition = resolved_definition(candidate)
    preview = rules.preview_candidate(user(), definition)
    assert '"start_date" IS NULL' in preview["sql_preview"]
    assert '"start_date" IS NOT NULL' not in preview["sql_preview"]
    assert preview["sql_params"]["filter_1"] == "2"
    result = rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"]})
    assert result["failed_count"] == result["not_run_count"] == 0
    assert result["passed_count"] >= 4
    assert len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []


def test_two_table_choices_compile_exists_and_never_accept_model_confirmation():
    rules, model = make_rules(related=True)
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目实收信托一般不为0"))
    assert candidate["join"]["relationship_confirmed"] is False
    assert candidate["join"]["unmatched_policy"] == "unresolved"
    assert candidate["filters"][0]["confirmed"] is False
    assert candidate["join"]["report_date_field"] == "business_day"
    assert {item["id"] for item in candidate["questions"]} >= {"filters.0", "join.relationship_confirmed", "join.unmatched_policy"}
    definition = resolved_definition(candidate)
    definition["null_policy"] = "skip"
    preview = rules.preview_candidate(user(), definition)
    assert "EXISTS" in preview["sql_preview"] and '"state_table"' in preview["sql_preview"]
    assert preview["related_columns"]
    result = rules.test_candidate(user(), {"definition": definition})
    assert result["failed_count"] == result["not_run_count"] == 0
    assert result["passed_count"] > 4
    assert len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []


PROJECT_TABLE = "reg_pub_project_info"
PROJECT_FIELDS = [
    ("c_projcode", "项目编号", "varchar", "Y"), ("c_proj_name", "项目名称", "varchar", ""),
    ("c_projname", "项目名全称", "varchar", ""), ("start_date", "项目开始日期", "date", ""),
    ("c_projstatus", "项目状态", "varchar", ""), ("pro_status", "项目状态", "varchar", ""),
    ("pro_isclose", "信托产品存续标识", "varchar", ""), ("business_day", "数据日期", "date", ""),
]


@pytest.mark.parametrize("scope_note", ["存续范围对应的状态字段和状态码尚未确认",
                                        "需确认哪个用于筛选存续项目", "存续项目用哪一列过滤？"])
@pytest.mark.parametrize(("separator", "independent"), [("", ""), ("，", "关联键无法确认"),
                                                        ("以及", "截止日期尚未确认")])
def test_first_active_scope_choice_reaches_backend_sql_without_repeat_prompt(scope_note, separator, independent):
    # 实际截图措辞和模型两轮变体，并核对独立问题不被一并放行。
    mixed = scope_note.rstrip("？")
    if independent:
        mixed += separator + independent
    rules, model = _rules([
        _select_payload(target={"table": "reg_pub_project_account_info"}, uncertainties=["需确认存续范围使用哪个状态字段。"]),
        _generate_payload(expression={"left": "start_date", "op": "is_null"}, uncertainties=[mixed],
                          filters=[{"table": "base", "field": "pro_status", "op": "eq", "value": "2"}]),
    ], table=PROJECT_TABLE, table_cn="项目基本信息", fields=PROJECT_FIELDS, extra_tables=[{
        "name": "reg_pub_project_account_info", "cn": "项目账户表", "dimension": "账户", "fields": PROJECT_FIELDS[:3],
    }])
    with rules.storage.database.begin() as connection:
        for name, entry in [("c_projstatus", "1-存续"), ("pro_status", "2-存续"), ("pro_isclose", "1-存续（未完结）")]:
            connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == name).values(dictionary=entry))

    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目开始日期不能为空"))
    question = next(item for item in candidate["questions"] if item["id"] == "filters.0")
    assert candidate["table_name"] == PROJECT_TABLE and "candidate_options" not in candidate
    assert [item["selection"]["field"] for item in question["options"]] == ["c_projstatus", "pro_status", "pro_isclose"]
    assert question["remember_scope"] == "active_status"
    choice = question["options"][0]
    assert choice["selection"] == {"table": "base", "field": "c_projstatus", "op": "eq", "value": "1", "confirmed": True}
    assert candidate["filters"][0]["confirmed"] is False
    assert candidate["uncertainties"] == [question["uncertainty"]] + ([independent] if independent else [])
    # 同表单逻辑：只对关联到该选项的事项记录处理结果，不给其余问题批量写已确认。
    definition = {**candidate, "name": candidate["rule_name"], "filters": [choice["selection"]],
                  "uncertainty_resolutions": [choice["label"] if issue == question["uncertainty"] else ""
                                              for issue in candidate["uncertainties"]]}
    preview = rules.preview_candidate(user(), {"definition": definition})
    sql = preview["sql_preview"]
    assert '"c_projstatus" = :filter_1' in sql
    assert preview["sql_params"]["filter_1"] == "1"
    assert 't."c_projname" AS project_name' in sql
    assert not any(f'"{field}"' in sql for field in ("pro_status", "pro_isclose", "c_acstate_origin", "c_proj_name"))
    normalized = preview["definition"]
    assert [issue for issue, resolved in zip(normalized["uncertainties"], normalized["uncertainty_resolutions"])
            if not resolved] == ([independent] if independent else [])
    assert review_ready(normalized) is (not independent)
    result = rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"]})
    assert result["passed_count"] >= 4 and result["failed_count"] == result["not_run_count"] == 0
    assert {case["row"]["base"]["c_projstatus"]: case["actual_count"] for case in result["cases"]
            if case["row"]["base"]["start_date"] is None}["1"] == 1
    outside = next(case for case in result["cases"] if case["name"] == "筛选不命中")
    assert outside["row"]["base"]["start_date"] is None and outside["actual_count"] == 0
    assert preview["persisted"] is result["persisted"] is False
    assert len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []


@pytest.mark.parametrize("table_name", [PROJECT_TABLE, "another_project_table"])
def test_preferred_project_name_is_scoped_to_exact_physical_table(table_name):
    table = {"id": 1, "table_name": table_name, "dimension": "项目"}
    fields = [{"field_name": name, "field_cn": cn, "data_type": kind, "is_pk": key}
              for name, cn, kind, key in PROJECT_FIELDS]
    result = infer_project_context({}, table, fields, [table], {1: fields})
    if table_name == PROJECT_TABLE:
        assert result["context"]["name_field"] == "c_projname"
        assert not result["questions"]
        supplied = {"project_context": {"mode": "base", "name_field": "c_proj_name"}}
        assert infer_project_context(supplied, table, fields, [table], {1: fields})["context"]["name_field"] == "c_projname"
        missing = [field for field in fields if field["field_name"] != "c_projname"]
        result = infer_project_context({}, table, missing, [table], {1: missing})
        assert result["context"] is None and not result["questions"]
        assert "c_projname" in result["uncertainties"][0]
    else:
        assert result["context"] is None
        assert result["questions"][0]["id"] == "project_context.name_field"
        assert {option["value"] for option in result["questions"][0]["options"]} == {"c_projname", "c_proj_name"}


def test_second_table_must_belong_to_the_same_document_source():
    rules, model = make_rules(related=True)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "state_table").values(data_source_name="监管报表"))
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text="存续项目实收不为0"))
    assert error.value.code == "MODEL_RESPONSE_INVALID"
    assert len(model.calls) == 1


def test_saved_scope_retests_current_version_and_document_change_blocks_confirmation():
    from tests.modules.data_validation.support import doc_xlsx_bytes
    rules, _model = make_rules()
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目实收信托不为0"))
    definition = resolved_definition(candidate)
    definition["null_policy"] = "skip"
    preview = rules.preview_candidate(user(), definition)
    rule = rules.save_draft(user(), definition)
    version = rules.storage.latest_version(rule["id"])
    assert version["content_sha256"] == preview["content_sha256"]
    assert version["definition"]["mapping_version"].startswith("doc-v1-")
    columns = [{"column_name": name, "comment": label, "data_type": kind} for name, label, kind, _pk in FIELDS]
    rules.metadata.describe_table = lambda _source, _table: {"columns": columns}
    result = rules.run_tests(user(), rule["id"], 1)
    assert result["persisted"] is True
    assert result["content_sha256"] == version["content_sha256"]
    assert result["failed_count"] == result["not_run_count"] == 0
    assert rules.storage.list_cases(rule["id"], 1)
    rules.metadata.describe_table = lambda _source, _table: {"columns": [item for item in columns if item["column_name"] != "business_day"]}
    with pytest.raises(AppError) as drift:
        rules.run_tests(user(), rule["id"], 1)
    assert drift.value.code == "MAPPING_DRIFT"
    assert all(item["status"] == "not_run" for item in rules.storage.list_cases(rule["id"], 1))
    with pytest.raises(AppError):
        rules.confirm_rule(user(), rule["id"], 1, version["content_sha256"])
    rules.metadata.describe_table = lambda _source, _table: {"columns": columns}
    rules.run_tests(user(), rule["id"], 1)
    rules.import_document(user(), "new-doc.xlsx", doc_xlsx_bytes(fields=FIELDS))
    with pytest.raises(AppError) as error:
        rules.confirm_rule(user(), rule["id"], 1, version["content_sha256"])
    assert error.value.code == "CONFLICT_VERSION"


def test_saved_unconfirmed_scope_is_persisted_as_not_run_never_as_failed_or_passed():
    rules, _model = make_rules(unary=True)
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目项目开始日不能为空"))
    definition = resolved_definition(candidate)
    definition["filters"][0]["confirmed"] = False
    rule = rules.save_draft(user(), definition)
    columns = [{"column_name": name, "comment": label, "data_type": kind} for name, label, kind, _pk in FIELDS]
    rules.metadata.describe_table = lambda _source, _table: {"columns": columns}
    result = rules.run_tests(user(), rule["id"], 1)
    assert result["not_run_count"] == len(result["cases"]) > 0
    assert result["passed_count"] == result["failed_count"] == 0
    assert all(item["status"] == "not_run" and item["actual_count"] == -1 for item in rules.storage.list_cases(rule["id"], 1))
    with pytest.raises(AppError):
        rules.confirm_rule(user(), rule["id"], 1, result["content_sha256"])
