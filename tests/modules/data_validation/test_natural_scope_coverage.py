import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload


def _parse(text, *, filters=(), dictionary="1-个人\n2-机构", state_dictionary="A-存续\nT-已终止", name="客户名称",
           second_type=""):
    fields = [
        ("row_id", "编号", "varchar", "Y"), ("checked_name", name, "varchar", ""),
        ("customer_type", "客户类型", "int", ""), ("account_state", "账户状态", "varchar", ""),
        ("business_day", "业务日期", "date", ""),
    ]
    if second_type:
        fields.append(("report_type", "客户报告类型", "int", ""))
    rules, _ = _rules_with_doc([
        _select_payload(), _generate_payload(expression={"left": "checked_name", "op": "is_null"}, filters=list(filters)),
    ], fields=fields)
    with rules.storage.database.begin() as conn:
        for field, options in (("customer_type", dictionary), ("account_state", state_dictionary), ("report_type", second_type)):
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == field).values(dictionary=options))
    return rules, rules.parse_rule_request(user(), _request(request_text=text))


CUSTOMER = {"table": "base", "field": "customer_type", "op": "eq", "value": 2, "confirmed": True}
ACTIVE = {"table": "base", "field": "account_state", "op": "eq", "value": "A", "confirmed": True}


def _reject_edit(rules, definition, filters):
    edited = {**definition, "filters": filters}
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.preview_candidate(user(), edited)
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.save_draft(user(), edited)


@pytest.mark.parametrize(("text", "filters"), [
    ("客户名称不能为空，只检查机构客户", [CUSTOMER, ACTIVE]),
    ("客户名称必填，仅限机构客户", []),
    ("客户名称必填，仅核查机构客户", [{**CUSTOMER, "value": 1}]),
    ("仅限机构客户，客户名称必填", []),
])
def test_trailing_restriction_uses_documented_code_in_generated_and_saved_sql(text, filters):
    rules, result = _parse(text, filters=filters)
    assert result["filters"] == [CUSTOMER]
    preview = result["preview"]
    assert preview["sql_params"]["filter_1"] == 2 and '"customer_type" = :filter_1' in preview["sql_preview"]
    assert '"account_state"' not in preview["sql_preview"]
    _reject_edit(rules, preview["definition"], [])
    _reject_edit(rules, preview["definition"], [{**CUSTOMER, "value": 1}])
    _reject_edit(rules, preview["definition"], [CUSTOMER, ACTIVE])
    assert rules.save_draft(user(), preview["definition"])["id"]


@pytest.mark.parametrize(("text", "filters"), [
    ("户名不能为空，所有状态均纳入，包括存续和已终止", []),
    ("户名必填，不限状态，包括存续和已终止", [ACTIVE]),
    ("户名必填，全部状态都检查，不仅限于存续", []),
])
def test_all_states_never_becomes_a_single_status(text, filters):
    rules, result = _parse(text, filters=filters, name="户名")
    assert result["filters"] == []
    preview = result["preview"]
    assert '"checked_name" IS NULL' in preview["sql_preview"] and "filter_1" not in preview["sql_params"]
    _reject_edit(rules, preview["definition"], [ACTIVE])


@pytest.mark.parametrize("dictionary", ["", "2-机构\n2-个人"])
def test_missing_or_contradictory_dictionary_cannot_widen_a_trailing_restriction(dictionary):
    _, result = _parse("客户名称必填，只检查机构客户", filters=[CUSTOMER], dictionary=dictionary)
    assert result["preview"] is None and "机构" in result["preview_error"]


def test_all_states_keeps_independent_customer_scope():
    _, result = _parse("客户名称必填，只检查机构客户，所有状态均纳入，包括存续和已终止",
                       filters=[ACTIVE, CUSTOMER])
    assert result["filters"] == [CUSTOMER]
    assert result["preview"]["sql_params"]["filter_1"] == 2


def test_negative_subset_with_no_dictionary_evidence_requires_confirmation():
    _, result = _parse("客户名称必填，只检查非机构客户", filters=[CUSTOMER])
    assert result["preview"] is None and "非机构" in result["preview_error"]


def test_all_states_needs_no_status_dictionary():
    _, result = _parse("户名不能为空，所有状态均纳入，包括存续和已终止", state_dictionary="", name="户名")
    assert result["preview"] and "filter_1" not in result["preview"]["sql_params"]


@pytest.mark.parametrize("filters", [[], [ACTIVE]])
def test_explicit_additional_condition_is_covered_or_a_concrete_problem(filters):
    text = "客户名称不能为空，只检查机构客户，且账户状态为存续"
    rules, result = _parse(text, filters=filters)
    if filters:
        assert result["filters"] == [CUSTOMER, ACTIVE]
        definition = result["preview"]["definition"]
        _reject_edit(rules, definition, [CUSTOMER])
        _reject_edit(rules, {**definition, "expression": {"left": "row_id", "op": "is_null"}}, filters=[CUSTOMER, ACTIVE])
        assert rules.save_draft(user(), definition)["id"]
    else:
        assert result["preview"] is None and "账户状态" in result["preview_error"]


@pytest.mark.parametrize("extra", ["换算币种后账户状态为存续", "账户状态为存续的记录还需复核额度"])
def test_partial_match_of_a_documented_filter_cannot_discard_an_independent_requirement(extra):
    _, result = _parse(f"客户名称不能为空，只检查机构客户，且{extra}", filters=[ACTIVE])
    assert result["preview"] is None and extra in result["preview_error"]


def test_all_states_and_a_conflicting_restriction_require_clarification():
    _, result = _parse("户名必填，所有状态都检查，仅限存续账户", name="户名")
    assert result["preview"] is None and "所有状态" in result["preview_error"]


def test_explicit_trailing_active_status_is_never_sent_to_sql_as_all_states():
    _, result = _parse("户名必填，仅检查存续状态", name="户名")
    assert result["filters"] == [ACTIVE] or (result["preview"] is None and "存续" in result["preview_error"])


@pytest.mark.parametrize("clause", ["不检查存续账户", "只检查已终止", "只检查尚待后台复核的对象"])
def test_unmapped_explicit_restriction_is_preserved_as_a_question(clause):
    _, result = _parse("户名必填，" + clause, name="户名")
    assert result["preview"] is None and clause in result["preview_error"]


def test_universal_status_request_does_not_swallow_a_restriction_in_an_example():
    _, result = _parse("户名必填，所有状态均纳入，包括存续和已终止但排除特殊账户", name="户名")
    assert result["preview"] is None and "排除特殊账户" in result["preview_error"]


def test_two_documented_definitions_require_a_choice_and_accept_either_on_retry():
    rules, result = _parse("客户名称必填，仅限机构客户", second_type="6-机构\n9-个人")
    question = next(q for q in result["questions"] if q["id"] == "filters.0")
    options = [o["selection"] for o in question["options"]]
    assert [(item["field"], item["value"]) for item in options] == [("customer_type", 2), ("report_type", 6)]
    assert result["filters"][0]["confirmed"] is False and result["preview"] is None
    for item in options:
        preview = rules.preview_candidate(user(), {**result, "name": result["rule_name"], "questions": [], "filters": [item]})
        assert preview["sql_params"]["filter_1"] == item["value"]


def test_ambiguous_code_cannot_be_offered_as_one_of_two_valid_interpretations():
    _, result = _parse("客户名称必填，仅限机构客户", dictionary="2-个人\n2-机构", second_type="6-机构")
    assert result["preview"] is None and "机构" in result.get("preview_error", "")
    assert not any(q["id"].startswith("filters.") for q in result["questions"])


def test_same_status_label_on_a_different_entity_is_not_the_requested_scope():
    _, result = _parse("客户名称必填，仅限存续客户", filters=[ACTIVE])
    assert result["preview"] is None and "存续客户" in result["preview_error"]
