"""Cross-cutting safeguards for fact delivery and immutable saved-version evidence."""
from copy import deepcopy
import json

import pytest

from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError, content_hash
from tests.modules.data_validation.support import Metadata, user
from tests.modules.data_validation.test_followup_service_bridge import (
    _rules, _select_payload, _generate_payload, _request,
)

FIELDS = [("row_id", "明细编号", "varchar", "Y"), ("c_projcode", "项目编号", "varchar", ""),
          ("c_projname", "项目名称", "varchar", ""), ("amount", "金额", "decimal", ""),
          ("report_date", "报送日期", "date", "")]


def prepared():
    rules, model = _rules([
        _select_payload(),
        _generate_payload(expression={"left": "金额", "op": "eq", "right_type": "value", "right": 0}),
    ], fields=FIELDS)
    rules.metadata = Metadata(sources=rules.metadata.list_sources(), columns=[
        {"column_name": name, "comment": cn, "data_type": kind} for name, cn, kind, _pk in FIELDS
    ])
    return rules, model


def test_two_call_generation_receives_bounded_actual_facts_and_safe_existing_rule_summary():
    rules, model = prepared()
    # A real existing user-visible rule; its SQL/literal must not be uploaded.
    definition = {
        "name": "已有条件", "source_id": "src", "table_name": "test_table",
        "rule_type": "field_compare", "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 987654321},
        "filters": [{"table": "base", "field": "c_projcode", "op": "eq", "value": "PRIVATE_FILTER_LITERAL"}],
    }
    rules.storage.create_rule(
        creator_user_id="1", name="已有条件", description="", definition=definition,
        sql_text="SELECT PRIVATE_SQL_LITERAL", mapping_version="old", content_sha256="old", generation_mode="manual",
    )
    candidate = rules.parse_rule_request(user(), _request(request_text="金额不得为0"))
    assert candidate["preview"] is not None
    assert len(model.calls) == 2
    generation_text = " ".join(str(message["content"]) for message in model.calls[1]["messages"])
    assert "suggestion_document_facts" in generation_text
    assert "existing_rule_summaries" in generation_text
    assert "c_projcode" in generation_text and "项目编号" in generation_text
    assert "PRIVATE_FILTER_LITERAL" not in generation_text
    assert "PRIVATE_SQL_LITERAL" not in generation_text
    assert "987654321" not in generation_text
    assert rules.metadata.calls == []


def save_prior_numeric_policy(rules):
    preview = rules.preview_candidate(user(), {
        "name": "历史已测数值口径", "rule_type": "field_compare", "source_id": "src", "table_name": "test_table",
        "business_key": "row_id", "report_date_field": "report_date", "violation_message": "数值条件",
        "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": {"left": "amount", "op": "eq", "right_type": "value", "right": 0},
    })
    old_definition = deepcopy(preview["definition"])
    old_definition["null_policy"] = "skip"
    old_definition.pop("null_handling", None)
    old_definition.pop("null_evidence", None)
    sql, _params = compile_rule({"definition": old_definition})
    digest = content_hash(old_definition, old_definition["dialect"], old_definition["mapping_version"], sql)
    saved = rules.storage.create_rule(
        creator_user_id="1", name=old_definition["name"], description="", definition=old_definition,
        sql_text=sql, mapping_version=old_definition["mapping_version"], content_sha256=digest, generation_mode="ai",
    )
    version = rules.storage.latest_version(int(saved["id"]))
    # Simulate genuine earlier receipts, not a client-provided passing flag.
    rules.storage.replace_cases(int(saved["id"]), 1, [{
        "name": "旧版本正常样本", "row": {"amount": 1}, "expected_count": 0,
        "actual_count": 0, "status": "passed",
    }])
    return saved, version


@pytest.mark.parametrize("action", ["retest", "confirm"])
def test_rebinding_numeric_policy_cannot_test_or_enable_new_sql_under_old_saved_hash(action):
    rules, _model = prepared()
    saved, version = save_prior_numeric_policy(rules)
    before = deepcopy(version)
    with pytest.raises(AppError) as error:
        if action == "retest":
            rules.run_tests(user(), int(saved["id"]), 1)
        else:
            rules.confirm_rule(user(), int(saved["id"]), 1, version["content_sha256"])
    assert error.value.code == "CONFLICT_VERSION"
    after = rules.storage.latest_version(int(saved["id"]))
    assert after["definition"] == before["definition"]
    assert after["sql_text"] == before["sql_text"]
    assert after["content_sha256"] == before["content_sha256"]
    assert rules.storage.get_rule(int(saved["id"]))["status"] == "draft"
    if action == "retest":
        assert all(case["status"] != "passed" for case in rules.storage.list_cases(int(saved["id"]), 1))
    assert rules.metadata.calls == []


def test_alternative_does_not_inherit_another_tables_project_questions_or_null_evidence():
    from sqlalchemy import update
    from auto_check.modules.data_validation.storage import DOC_FIELDS
    fields = [(name, "实收信托余额" if name == "amount" else cn, kind, pk)
              for name, cn, kind, pk in FIELDS] + [("another_name", "项目名称", "varchar", "")]
    other_fields = [("contract_id", "合同编号", "varchar", "Y"),
                    ("project_id", "项目编号", "varchar", ""),
                    ("project_name", "项目名称", "varchar", ""),
                    ("other_amount", "实收信托余额", "decimal", ""),
                    ("report_date", "报送日期", "date", "")]
    rules, _model = _rules([
        _select_payload(),
        _generate_payload(expression={"left": "实收信托余额", "op": "eq", "right_type": "value", "right": 0}),
    ], fields=fields, extra_tables=[{
        "name": "contract_table", "cn": "合同表", "dimension": "合同", "fields": other_fields,
    }])
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "amount").values(logic="文档明确：NULL按0处理"))
    candidate = rules.parse_rule_request(user(), _request(request_text="项目的实收信托一般不为0"))
    assert any(question["id"] == "project_context.name_field" for question in candidate["questions"])
    assert candidate["null_policy"] == "zero"
    other = next(option["candidate"] for option in candidate["candidate_options"]
                 if option["candidate"]["table_name"] == "contract_table")
    assert not any(question["id"].startswith("project_context.") for question in other["questions"])
    assert other["project_context"]["code_field"] == "project_id"
    assert other["project_context"]["name_field"] == "project_name"
    assert other["null_policy"] == "skip"
    assert not other["null_evidence"]
    assert other["preview"]["definition"]["null_policy"] == "skip"
    assert 't."project_name" AS "项目名称"' in other["preview"]["sql_preview"]
