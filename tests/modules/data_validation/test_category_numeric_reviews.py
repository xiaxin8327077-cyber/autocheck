from copy import deepcopy
from unittest.mock import patch

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_grounding import check_request_coverage
from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_followup_service_bridge import _rules


REQUEST = "非净值型项目的净值不得大于1或小于0"
MODEL_ISSUES = [
    "需确认使用 project_report.mode 或其他字段识别非净值型项目。",
    "净值字段需确认是否为 project_report.performance（非净值型产品本期业绩表现），且需确认取值口径是否代表净值。",
]
DICTIONARY = "【字典】\nA-开放式非净值型\nB-净值型\nD-封闭式非净值型\nE-其他"
FIELDS = [
    ("row_code", "项目编号", "varchar", "Y"), ("row_name", "项目名称", "varchar", ""),
    ("report_day", "报送日期", "date", ""), ("mode", "运行方式", "varchar", ""),
    ("orig", "运行方式_原始", "varchar", ""), ("nav", "单位净值", "numeric", ""),
    ("total", "累计净值", "numeric", ""), ("opening", "期初累计净值", "numeric", ""),
    ("performance", "非净值型产品本期业绩表现", "numeric", ""), ("day", "累计净值日期", "date", ""),
]


def setup_rules(*, notes=(), dictionary=DICTIONARY, fields=FIELDS, draft=None):
    select = {"result_type": "clarification", "uncertainties": [*MODEL_ISSUES, *notes]}
    rules, model = _rules([select, draft or {"rule_type": None, "uncertainties": MODEL_ISSUES}],
                          table="project_report", fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(["mode", "orig"])).values(dictionary=dictionary))
    return rules, model


def test_clarified_target_produces_real_questions_and_both_boundaries_before_sql():
    rules, model = setup_rules()
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule", side_effect=AssertionError("pending")):
        result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert len(model.calls) == 2 and result["table_name"] == "project_report"
    assert result["model_judgments"]["select_table"]["uncertainties"] == MODEL_ISSUES
    assert result["preview"] is None and not result["can_enable"]
    metric, scope = [q for q in result["questions"] if q["id"] != "null_policy"]
    assert metric["targets"] == ["expression.conditions.0.left", "expression.conditions.1.left"]
    assert {o["value"] for o in metric["options"]} == {"nav", "total", "opening"}
    assert scope["id"] == "filters.0"
    assert {option["selection"]["field"] for option in scope["options"]} == {"mode", "orig"}
    assert all(o["selection"]["value"] == ["A", "D"] for o in scope["options"])
    assert set(result["uncertainties"]) == {q["uncertainty"] for q in (metric, scope)}
    chosen = deepcopy(result)
    for condition in chosen["expression"]["conditions"]:
        condition["left"] = "total"
    chosen.update(questions=[], filters=[scope["options"][1]["selection"]],
                  uncertainty_resolutions=["累计净值", "原始运行方式"], null_policy="skip")
    ready = rules.preview_candidate(user(), chosen, return_questions=True)
    assert "sql_preview" in ready and ready["definition"]["expression"]["logic"] == "any"
    assert [part["right"] for part in ready["definition"]["expression"]["conditions"]] == [1, 0]
    reordered = deepcopy(chosen)
    reordered["expression"]["conditions"].reverse()
    assert rules.preview_candidate(user(), reordered)["sql_preview"]
    for mutation in ("use_performance", "half_range", "wrong_categories"):
        wrong = deepcopy(chosen)
        if mutation == "use_performance":
            for condition in wrong["expression"]["conditions"]:
                condition["left"] = "performance"
        elif mutation == "half_range":
            wrong["expression"] = wrong["expression"]["conditions"][0]
        else:
            wrong["filters"][0]["value"] = ["B", "E"]
        with pytest.raises(AppError):
            rules.preview_candidate(user(), wrong)


def test_independent_review_in_the_same_sentence_remains_after_document_fields_are_bound():
    issue = "还需确认是否按月末截止"
    rules, _ = setup_rules(notes=["净值字段需确认是否为 project_report.performance；" + issue])
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert issue in result["uncertainties"] and result["preview"] is None


@pytest.mark.parametrize("dictionary", ["1-净值型\n9-其他", "1-开放式非净值型\n1-净值型", "【RHZD0008】"])
def test_missing_or_conflicting_codes_cannot_use_complement(dictionary):
    rules, _ = setup_rules(dictionary=dictionary)
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert result.get("filters", []) == [] and result["preview"] is None
    assert result["questions"][0]["id"] == "expression.conditions.0.left"
    assert any("筛选" in text for text in result["uncertainties"])


def test_no_metric_with_matching_meaning_leaves_the_request_unbound():
    fields = [f for f in FIELDS if f[0] not in {"nav", "total", "opening"}]
    rules, model = setup_rules(fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert len(model.calls) == 1 and result["rule_type"] is None and not result.get("preview")
    assert result["uncertainties"] == MODEL_ISSUES


def test_unique_documented_metric_and_scope_are_bound_without_an_unnecessary_question():
    fields = [f for f in FIELDS if f[0] not in {"total", "opening", "orig"}]
    rules, _ = setup_rules(fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert not result["questions"] and not result["uncertainties"]
    definition = result["preview"]["definition"]
    assert [c["left"] for c in definition["expression"]["conditions"]] == ["nav", "nav"]
    assert definition["filters"] == [{"table": "base", "field": "mode", "op": "in", "value": ["A", "D"], "confirmed": True}]


def test_an_independent_proposed_filter_is_preserved_and_keeps_sql_pending():
    extra = {"table": "base", "field": "row_code", "op": "eq", "value": "example"}
    rules, _ = setup_rules(draft={"rule_type": None, "filters": [extra]})
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert result["filters"][-1] == {**extra, "confirmed": False}
    assert result.get("preview_error") and not result["preview"]


def test_different_categories_metrics_thresholds_and_operators_use_the_same_document_rules():
    fields = [{"field_name": "kind", "field_cn": "账户类型", "dictionary": "1-普通类\n3-特殊类", "data_type": "int"},
              {"field_name": "bal", "field_cn": "账户余额", "data_type": "decimal"}]
    definition = {"description": "普通类账户的余额不得小于-3或大于12.5", "expression": {"logic": "any", "conditions": [
        {"left": "bal", "op": "lt", "right_type": "value", "right": -3},
        {"left": "bal", "op": "gt", "right_type": "value", "right": 12.5}]},
        "filters": [{"table": "base", "field": "kind", "op": "eq", "value": 1, "confirmed": True}]}
    assert not check_request_coverage(definition, fields, [], dimension="账户")
    definition["expression"]["conditions"][1]["right"] = 12
    assert check_request_coverage(definition, fields, [], dimension="账户")


@pytest.mark.parametrize("typed", [True, False])
def test_selected_table_with_date_references_continues_to_documented_comparison(typed):
    fields = [("loan_code", "贷款编号", "varchar", "Y"), ("on_day", "数据日期", "date", ""),
              ("funding_day", "贷款开始日", "date", ""), ("agreement_day", "合同开始日", "date", ""),
              ("end_day", "合同到期日", "date", ""), ("performance", "收益率", "numeric", "")]
    note = "需确认开始日字段使用 loan.funding_day 或 loan.agreement_day"
    selection = {"status": "needs_clarification", "target": {"table": "loan"}, "uncertainties": [note]}
    if typed:
        selection["field_choices"] = [{"side": "left", "term": "开始日",
            "fields": ["funding_day", "agreement_day", "absent", "performance"]}]
    draft = {"rule_type": "field_compare", "expression": {"left": "funding_day", "op": "gt", "right": "end_day"},
             "null_policy": "skip", "equality_policy": "allow_equal", "uncertainties": []}
    rules, model = _rules([selection, draft], table="loan", table_cn="贷款", dimension="贷款", fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text="开始日不得晚于合同到期日"))
    assert result["preview"] is None and len(model.calls) == 2
    question, = result["questions"]
    assert question["id"] == "expression.left"
    assert {item["value"] for item in question["options"]} == {"agreement_day", "funding_day"}
    assert all(note not in text for text in result["uncertainties"])
    chosen = {**result, "questions": [], "expression": {**result["expression"], "left": "agreement_day"},
              "uncertainty_resolutions": ["采用合同开始日"] * len(result["uncertainties"])}
    assert "agreement_day" in rules.preview_candidate(user(), chosen)["sql_preview"]


SCREEN_REVIEWS = [
    "proj_info_dtl_pboc中f_curr_performance为'非净值型产品本期业绩表现'，是否即为净值需确认；"
    "非净值型判定字段c_oper_mode取值为2或4，但需确认是否需排除其他运行方式",
    "需求中的'净值'字段未明确指定，本规则采用'单位净值'f_netvalue；"
    "但'非净值型产品本期业绩表现'f_curr_performance也可能被理解为净值，请确认",
    "非净值型筛选依据c_oper_mode取值为2或4，已按此范围执行，但需确认是否还需排除其他特殊状态",
]


def _screen_replay(*, extra="", document_scope=""):
    names = {"mode": "c_oper_mode", "orig": "c_oper_mode_orig", "nav": "f_netvalue", "performance": "f_curr_performance"}
    fields = [(names.get(name, name), label, kind, key) for name, label, kind, key in FIELDS]
    notes = [*SCREEN_REVIEWS, *([extra] if extra else [])]
    rules, _ = _rules([{"status": "needs_clarification", "target": {"table": "proj_info_dtl_pboc"},
                        "uncertainties": notes[:1]}, {"rule_type": None, "uncertainties": notes[1:]}],
                      table="proj_info_dtl_pboc", fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(["c_oper_mode", "c_oper_mode_orig"]))
                     .values(dictionary="2-开放式非净值型\n3-封闭式净值型\n4-封闭式非净值型"))
        conn.execute(update(DOC_TABLES).values(scope=document_scope))
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule", side_effect=AssertionError("未作答")):
        result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    metric, scope = result["questions"]
    chosen = deepcopy(result)
    for condition in chosen["expression"]["conditions"]:
        condition["left"] = "f_netvalue"
    chosen.update(questions=[], filters=[scope["options"][0]["selection"]],
                  uncertainties=[*notes, metric["text"], scope["text"]],
                  uncertainty_resolutions=[""] * len(notes) + ["明确选择 f_netvalue",
                                                               f"明确选择 {scope['options'][0]['label']}"])
    return rules, result, chosen


@pytest.mark.parametrize("metric_receipt", ["明确选择 f_netvalue", "已选择单位净值"])
def test_exact_reported_model_text_is_reconciled_at_generation_and_on_retry(metric_receipt):
    rules, result, chosen = _screen_replay(document_scope="取数范围按项目编号排除所列项目。")
    assert result["uncertainties"] == [q["text"] for q in result["questions"]]
    assert result["model_judgments"]["generate_rule"]["uncertainties"] == SCREEN_REVIEWS[1:]
    chosen["uncertainty_resolutions"][-2] = metric_receipt
    preview = rules.preview_candidate(user(), chosen, return_questions=True)
    assert preview["sql_params"]["filter_1_0"] == "2" and preview["sql_params"]["filter_1_1"] == "4"
    assert [preview["sql_params"][f"right_value_{i}"] for i in [1, 2]] == [1, 0]
    assert preview["definition"]["uncertainties"] == [q["text"] for q in result["questions"]]
    assert preview["definition"]["uncertainty_resolutions"] == chosen["uncertainty_resolutions"][-2:]


@pytest.mark.parametrize("extra,document_scope,needle", [
    ("是否还需排除已冻结状态？", "", "冻结"), ("请核对币种折算和月末截止。", "", "币种"),
    ("", "本项校验应排除冻结状态。", "其他特殊状态"),
    ("非净值型判定字段c_oper_mode取值为2或8", "", "2或8"),
    ("proj_info_dtl_pboc中missing_metric为单位净值，是否即为净值需确认", "", "missing_metric"),
])
def test_specific_scope_and_document_restrictions_remain_at_both_gates(extra, document_scope, needle):
    rules, result, chosen = _screen_replay(extra=extra, document_scope=document_scope)
    assert any(needle in text for text in result["uncertainties"])
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule", side_effect=AssertionError("独立口径未决")):
        reply = rules.preview_candidate(user(), chosen, return_questions=True)
    assert any(needle in text for text in reply["uncertainties"])


def test_old_candidate_cannot_substitute_a_different_field_or_an_unconfirmed_answer():
    rules, _, chosen = _screen_replay()
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule", side_effect=AssertionError("未核实")):
        for answer in ("", "已选择单位", "明确选择 total"):
            chosen["uncertainty_resolutions"][-2] = answer
            assert rules.preview_candidate(user(), chosen, return_questions=True)["status"] == "needs_confirmation"
        chosen["uncertainty_resolutions"][-2] = "明确选择 f_netvalue"
        chosen["filters"][0]["value"] = ["2", "3"]
        assert rules.preview_candidate(user(), chosen, return_questions=True)["status"] == "needs_confirmation"


def test_old_caption_receipt_needs_a_unique_documented_column_and_an_unchanged_request():
    rules, _, chosen = _screen_replay()
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule", side_effect=AssertionError("附加范围未决")):
        changed = {**chosen, "description": REQUEST + "，还需排除其他特殊状态"}
        assert rules.preview_candidate(user(), changed, return_questions=True)["status"] == "needs_confirmation"
        with rules.storage.database.begin() as conn:
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "total").values(field_cn="单位净值"))
        chosen["uncertainty_resolutions"][-2] = "已选择单位净值"
        assert rules.preview_candidate(user(), chosen, return_questions=True)["status"] == "needs_confirmation"


def test_account_balance_dictionary_and_metric_decisions_cover_a_different_table():
    note = ("ledger中interest为本期利息，是否即为余额需确认；"
            "普通类筛选依据account_kind取值为8，已按此范围执行，但需确认是否还需排除其他特殊状态")
    fields = [("row_id", "账户编号", "varchar", "Y"), ("run_day", "业务日期", "date", ""),
              ("account_kind", "账户类型", "int", ""), ("interest", "本期利息", "decimal", ""),
              ("available", "可用余额", "numeric", ""), ("book", "账面余额", "numeric", "")]
    rules, _ = _rules([{"target": {"table": "ledger"}, "uncertainties": [note]}, {"rule_type": None}],
                      table="ledger", table_cn="账户台账", dimension="账户", fields=fields)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "account_kind")
                           .values(dictionary="8-普通类\n2-专用类"))
    result = rules.parse_rule_request(user(), _request(request_text="普通类账户的余额不得小于-5"))
    question, = result["questions"]
    assert result["uncertainties"] == [question["text"]]
    assert {opt["value"] for opt in question["options"]} == {"available", "book"}
    confirmed = {**result, "questions": [], "expression": {**result["expression"], "left": "book"},
                 "uncertainties": [note, question["text"]], "uncertainty_resolutions": ["", "明确选择 book"]}
    preview = rules.preview_candidate(user(), confirmed, return_questions=True)
    assert "book" in preview["sql_preview"] and preview["definition"]["filters"][0]["value"] == 8
