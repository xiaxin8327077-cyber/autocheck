from unittest.mock import patch

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.conditional_reviews import BoundReviewEvidence, category_numeric_check
from auto_check.modules.data_validation.query_grounding import dictionary_options
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_explicit_scope_compound_preview import REQUEST, VALUE, MISSING
from tests.modules.data_validation.test_followup_service_bridge import _rules


TABLE = "proj_info_dtl_pboc"
HEAD = "需要确认proj_info_dtl_pboc.c_oper_mode_orig中哪些码值属于“净值型”"
BODY = "字典线索为1开放式净值型、3封闭式净值型，是否1和3均视为净值型"
SCREEN = HEAD + "（" + BODY + "）"
DICTIONARY = "【RHZD0008】\n1-开放式净值型\n2-开放式非净值型\n3-封闭式净值型\n4-封闭式非净值型"


def _rules_and_document():
    selection = {"target": {"table": TABLE}, "uncertainties": [SCREEN]}
    draft = {"rule_type": "field_compare", "expression": {"logic": "any", "conditions": [MISSING, VALUE]},
             "null_policy": "review", "uncertainties": [SCREEN]}
    fields = [("row_id", "项目编号", "varchar", "Y"), ("on_day", "数据日期", "date", ""),
              ("name", "项目名称", "varchar", ""), ("f_netvalue", "单位净值", "numeric", ""),
              ("c_oper_mode", "运行方式", "varchar", ""), ("c_oper_mode_orig", "运行方式_原始", "varchar", "")]
    rules, _ = _rules([selection, draft], table=TABLE, fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(["c_oper_mode", "c_oper_mode_orig"]))
                     .values(dictionary=DICTIONARY))
    return rules


def test_screenshot_membership_question_is_answered_for_new_analysis_and_preexisting_candidate():
    rules = _rules_and_document()
    candidate = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert candidate["model_judgments"]["select_table"]["uncertainties"] == [SCREEN]
    assert not candidate["questions"] and not candidate["uncertainties"]
    definition = candidate["preview"]["definition"]
    assert definition["filters"][0]["field"] == "c_oper_mode_orig"
    assert definition["filters"][0]["value"] == ["1", "3"]
    old = {**definition, "uncertainties": [SCREEN], "uncertainty_resolutions": [""]}
    assert rules.preview_candidate(user(), old, return_questions=True)["sql_preview"] == candidate["preview"]["sql_preview"]
    independent = "另需核实币种折算。"
    for note in [SCREEN + "；" + independent, HEAD + "（" + BODY + "，" + independent + "）"]:
        with patch("auto_check.modules.data_validation.candidate_preview.compile_rule", side_effect=AssertionError("币种未确认")):
            result = rules.preview_candidate(user(), {**old, "uncertainties": [note]}, return_questions=True)
        assert result["status"] == "needs_confirmation"
        assert any("币种折算" in item for item in result["uncertainties"])


def _evidence(dictionary, *, kind="varchar"):
    fields = [{"field_name": "original", "field_cn": "评级_原始", "dictionary": dictionary, "data_type": kind},
              {"field_name": "book", "field_cn": "账面余额", "data_type": "numeric"}]
    check = category_numeric_check("原始评级为特别的账户的账面余额不得大于10", fields, dictionary_options, dimension="账户")
    return check, BoundReviewEvidence(check, fields, "ledger", "")


@pytest.mark.parametrize("note", [
    "请确认ledger.original中哪些代码属于特别（字典线索为AB:乙类特别,A:甲类特别，是否AB,A均视为特别）",
    "需核对original中哪些取值表示特别，字典为A（甲类特别）、AB（乙类特别），是否A和AB都属于特别",
    "需要明确original中哪些编码归入特别；字典条目为AB乙类特别、A甲类特别；是否AB以及A均归入特别",
])
def test_letter_codes_in_any_order_with_all_labels_verified(note):
    # The two matching codes are beyond dictionary_options' ordinary display cap.
    dictionary = "\n".join(f"{i}-普通" for i in range(105)) + "\nA-甲类特别\nAB-乙类特别\nZ-非特别"
    check, evidence = _evidence(dictionary)
    assert check.scope.dictionary_entries == {"original": [
        {"value": "A", "label": "甲类特别"}, {"value": "AB", "label": "乙类特别"}]}
    assert evidence.remaining_dictionary_review(note) == ""


@pytest.mark.parametrize("change", [
    lambda s: s.replace("AB乙类特别", "AB甲类特别"), lambda s: s.replace("、AB乙类特别", ""),
    lambda s: s.replace("、AB乙类特别", "、Z非特别"), lambda s: s.replace("A和AB", "A"),
    lambda s: s.replace("A和AB", "A和A"), lambda s: s.replace("A和AB", "A和Z"),
    lambda s: s.replace("A甲类特别", "A甲类特别或部分豁免"), lambda s: s.replace("ledger.", "different."),
    lambda s: s.replace("original中", "unknown中"),
])
def test_incomplete_or_incorrect_assertions_and_foreign_fields_stay_open(change):
    _, evidence = _evidence("A-甲类特别\nAB-乙类特别\nZ-非特别")
    question = change("请确认ledger.original中哪些代码属于特别（字典线索为A甲类特别、AB乙类特别，是否A和AB均视为特别）")
    assert evidence.remaining_dictionary_review(question) == question
    assert evidence.remaining(question)


def test_conflicting_dictionary_never_proves_a_membership_question():
    check, evidence = _evidence("1-甲类特别\n2-乙类特别\n2-普通", kind="int")
    assert not check.scope.selections and not check.scope.dictionary_entries
    note = "请确认original中哪些编码属于特别（字典线索为1甲类特别、2乙类特别，是否1和2均视为特别）"
    assert evidence.remaining_dictionary_review(note) == note
