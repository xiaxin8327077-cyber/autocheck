"""The model resolves ordinary execution choices; real business alternatives stay visible."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.prompt_defaults import COMMON_MODEL_CHOICES_GUIDANCE
from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc
from tests.modules.data_validation.test_followup_service_bridge import _add_table
from tests.modules.data_validation.test_semantic_generation import draft


FIELDS = [
    ("project_id", "项目编号", "varchar", "Y"),
    ("contract_id", "合同代码", "varchar", "Y"),
    ("split_id", "拆分序号", "int", "Y"),
    ("project_name", "项目名称", "varchar", ""),
    ("amount", "金额", "numeric", ""),
    ("business_day", "数据日期", "date", ""),
]
RELATED = [
    ("project_id", "项目编号", "varchar", "Y"),
    ("project_name", "项目名称", "varchar", ""),
    ("flag", "转让标识", "varchar", ""),
    ("business_day", "数据日期", "date", ""),
]


def rules_with_choices(*, locator="project_id", relationship=True, unmatched="exclude", questions=(), metrics=None,
                       expand=False, chosen_date="business_day", extra_related=()):
    proposal = draft(business_key=locator)
    proposal["join"] = {"table_name": "projects", "on": [{"left": "project_id", "right": "project_id"}],
                        "report_date_field": chosen_date, "relationship_confirmed": relationship,
                        "unmatched_policy": unmatched}
    proposal["semantic_intent"]["scopes"] = [{"category": "转让", "table": "related", "fields": ["flag"],
        "memberships": {"flag": {"include": ["1"], "exclude": ["2"]}}}]
    proposal["semantic_intent"]["open_questions"] = list(questions)
    fields = deepcopy(FIELDS)
    if metrics:
        fields.append(("other_amount", "另一口径金额", "numeric", ""))
        proposal["semantic_intent"]["metrics"][0]["fields"] = metrics
    reply = {"target": {"table": "test_table"}, "related_target": {"table": "projects"}, "draft": proposal}
    replies = [reply]
    if expand:
        first = deepcopy(reply)
        first["expand_evidence"] = True
        first["draft"]["join"].update(relationship_confirmed=False, unmatched_policy="unresolved")
        replies = [first, proposal]
    rules, model = _rules_with_doc(replies, fields=fields)
    _add_table(rules, name="projects", cn="项目信息", dimension="项目", fields=[*RELATED, *extra_related])
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "flag").values(dictionary="1-是\n2-否"))
        base = rules.storage.doc_tables(rules.storage.active_document()["id"])[0]
        connection.execute(update(DOC_FIELDS).where(
            DOC_FIELDS.c.table_id == base["id"], DOC_FIELDS.c.field_name == "project_id",
        ).values(source_table="projects", source_field="project_id"))
    return rules, model


@pytest.mark.parametrize("locator", ["project_id", "contract_id", "split_id"])
def test_model_resolved_common_choices_do_not_become_three_user_questions_or_return_on_replay(locator):
    rules, model = rules_with_choices(locator=locator)
    request = _request(request_text="转让项目的金额不能低于19", analysis_protocol=2)
    first = rules.parse_rule_request(user(), request)
    assert not {q["id"] for q in first["questions"]} & {"business_key", "join.relationship_confirmed", "join.unmatched_policy"}
    assert first["business_key"] == locator and first["preview"]
    assert first["join"]["relationship_confirmed"] is True
    assert first["join"]["unmatched_policy"] == "exclude"
    assert any("另行核查" in text for text in first["notices"])
    assert first["filters"] == [{"table": "related", "field": "flag", "op": "eq", "value": "1", "confirmed": True}]
    repeated = rules.parse_rule_request(user(), request)
    assert repeated["business_key"] == locator and repeated["preview"]["content_sha256"] == first["preview"]["content_sha256"]
    assert len(model.calls) == 1 and rules.storage.visible_rules("1") == []


@pytest.mark.parametrize("relationship,unmatched", [
    (False, "exclude"),
    (True, "unresolved"),
])
def test_proven_project_driver_resolves_ordinary_execution_choices(relationship, unmatched):
    rules, _ = rules_with_choices(relationship=relationship, unmatched=unmatched)
    result = rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert result["questions"] == []
    assert result["preview"] is not None
    assert result["project_driver"]["table_role"] == "related"


def test_model_resolved_execution_does_not_remove_a_real_metric_choice():
    rules, _ = rules_with_choices(metrics=["amount", "other_amount"])
    result = rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert {q["id"] for q in result["questions"]} == {"expression.left"}
    assert {o["value"] for o in result["questions"][0]["options"]} == {"amount", "other_amount"}
    assert result["preview"] is None


def test_model_resolved_execution_does_not_answer_an_independent_business_question():
    question = "该金额是否包含已结算收益？"
    rules, _ = rules_with_choices(questions=[question])
    result = rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert question in result["uncertainties"] and not result["preview"]
    assert not result["questions"]


def test_model_can_resolve_the_same_join_after_reading_more_evidence():
    rules, model = rules_with_choices(expand=True)
    result = rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert result.get("preview") and result["business_key"] == "project_id"
    assert result["join"]["relationship_confirmed"] is True and result["join"]["unmatched_policy"] == "exclude"
    assert len(model.calls) == 2


def test_model_can_choose_a_real_business_date_when_two_are_documented():
    rules, _ = rules_with_choices(chosen_date="report_day", extra_related=[("report_day", "报送日期", "date", "")])
    result = rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert result["preview"] and result["join"]["report_date_field"] == "report_day"


def test_model_locator_on_a_single_combined_envelope_is_not_lost():
    rules, model = rules_with_choices(locator="contract_id")
    reply = model.payloads[0]
    reply["business_key"] = reply["draft"].pop("business_key")
    result = rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert result.get("preview") and result["business_key"] == "contract_id"


@pytest.mark.parametrize("locator", ["missing", 1, True, ["project_id"]])
def test_model_cannot_introduce_an_unknown_or_malformed_locator(locator):
    rules, model = rules_with_choices(locator=locator)
    model.payloads.extend(deepcopy(model.payloads[0]["draft"]) for _ in range(5))
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert error.value.code == "MODEL_RESPONSE_INVALID"


@pytest.mark.parametrize("date,extra", [
    ("project_id", []),
    ("missing", []),
])
def test_bad_model_date_is_not_silently_replaced_with_another_date(date, extra):
    rules, model = rules_with_choices(chosen_date=date, extra_related=extra)
    model.payloads.extend(deepcopy(model.payloads[0]["draft"]) for _ in range(5))
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert error.value.code == "MODEL_RESPONSE_INVALID"


def test_common_choices_guidance_and_the_new_fields_are_sent_to_the_model():
    rules, model = rules_with_choices()
    rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    prompt = model.calls[0]["messages"][0]["content"]
    assert COMMON_MODEL_CHOICES_GUIDANCE in prompt
    assert "business_key" in prompt and "relationship_confirmed表示" in prompt


def test_editable_business_scope_controls_guidance_instead_of_a_hidden_fixed_default():
    rules, model = rules_with_choices()
    custom = "本次由业务人员选择缺关联处理，其他要求保持原样。"
    rules.storage.save_prompt("business_scope", custom, "1")
    rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    prompt = model.calls[0]["messages"][0]["content"]
    assert custom in prompt and COMMON_MODEL_CHOICES_GUIDANCE not in prompt


def test_model_date_choice_does_not_depend_on_a_fixed_chinese_column_label():
    rules, model = rules_with_choices(chosen_date="as_of", extra_related=[("as_of", "报表所属日", "date", "")])
    model.payloads.append(deepcopy(model.payloads[0]["draft"]))
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "as_of")
                           .values(logic="本期报送所对应的数据日期。"))
    result = rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能低于19", analysis_protocol=2))
    assert result["preview"] and result["join"]["report_date_field"] == "as_of"
    assert len(model.calls) == 2


@pytest.mark.parametrize("before_date,after_date,join_changes,accepted", [
    pytest.param(None, "business_day", {}, True, id="add-same-period"),
    pytest.param("business_day", None, {}, True, id="remove-same-period"),
    pytest.param(None, "other_date", {}, False, id="other-date"),
    pytest.param(None, "project_id", {}, False, id="varchar-date-key"),
    pytest.param(None, "business_day", {"unmatched_policy": "unresolved"}, False, id="undo-exclude"),
    pytest.param(None, "business_day", {"table_name": "another_table"}, False, id="change-table"),
    pytest.param(None, "business_day", {"relationship_confirmed": 1}, False, id="integer-confirmation"),
])
def test_full_draft_repair_preserves_join_except_for_redundant_period(
    before_date, after_date, join_changes, accepted,
):
    rules, model = rules_with_choices(extra_related=[("other_date", "采集日期", "date", "")])
    selection = deepcopy(model.payloads[0])
    original = selection.pop("draft")
    original["business_key"] = "unknown_locator"  # Trigger a full repair on an unrelated field.
    repaired = deepcopy(original)
    repaired["business_key"] = "contract_id"
    for proposal, right_date in ((original, before_date), (repaired, after_date)):
        if right_date:
            proposal["join"]["on"].append({"left": "business_day", "right": right_date})
    repaired["join"].update(join_changes)
    model.payloads = [selection, original, repaired]
    request = _request(request_text="转让项目的金额不能低于19", analysis_protocol=2)

    with patch.object(SemanticAnalysis, "check_repair_targets", autospec=True,
                      side_effect=SemanticAnalysis.check_repair_targets) as check_repair:
        if accepted:
            result = rules.parse_rule_request(user(), request)
            assert not result["questions"]
            definition = result["preview"]["definition"]
            assert definition["business_key"] == "contract_id"
            expected_join = deepcopy(repaired["join"])
            expected_join["on"] = [pair for pair in expected_join["on"]
                                   if pair != {"left": "business_day", "right": "business_day"}]
            assert definition["join"] == expected_join
        else:
            with pytest.raises(AppError) as error:
                rules.parse_rule_request(user(), request)
            assert error.value.code == "MODEL_RESPONSE_INVALID"
        check_repair.assert_called_once()
    assert len(model.calls) == 3


@pytest.mark.parametrize("operator,null_hit", [("lte", 1), ("gt", 0)])
def test_model_zero_amount_policy_survives_analysis_preview_testing_and_save(operator, null_hit):
    from auto_check.modules.data_validation.query_samples import evaluate_case_with_kind
    from auto_check.modules.data_validation.candidate_preview import run_preview_cases

    rules, model = rules_with_choices()
    guidance = '金额字段NULL统一按0比较，数值比较选择null_policy="zero"。'
    rules.storage.save_prompt("business_scope", guidance, "1")
    draft = model.payloads[0]["draft"]
    draft.update(null_policy="zero", expression={"left": "amount", "op": operator, "right_type": "value", "right": 0})
    text = "转让项目的金额应大于0" if operator == "lte" else "转让项目的金额不应大于0"
    result = rules.parse_rule_request(user(), _request(request_text=text, analysis_protocol=2))
    assert guidance in model.calls[0]["messages"][0]["content"]
    assert result["null_policy"] == "zero" and result["preview"] and not result["questions"]
    preview = result["preview"]
    assert "COALESCE(" in preview["sql_preview"]
    tested = run_preview_cases(preview)
    assert tested["failed_count"] == tested["not_run_count"] == 0
    rule = preview["definition"]
    row = {"report_date": "2026-11-01", "details": [{
        "project_id": "p", "business_day": "2026-11-01", "amount": None}], "project": {
        "project_id": "p", "business_day": "2026-11-01", "flag": "1"}}
    assert evaluate_case_with_kind(rule, row)[0] == null_hit
    saved = rules.save_draft(user(), rule)
    stored = rules.storage.latest_version(saved["id"])
    assert stored["definition"]["null_policy"] == "zero"
    assert stored["content_sha256"] == preview["content_sha256"]
    assert "COALESCE(" in stored["sql_text"]
