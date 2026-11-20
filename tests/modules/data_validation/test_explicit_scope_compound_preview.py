"""Exercise the complete AI flow when the request already supplies all business decisions."""
import json

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_followup_service_bridge import _rules


REQUEST = "原始运行方式为净值型的项目的单位净值不得为空且一般不大于10"
SCOPE_REVIEW = "原始运行方式字段c_oper_mode_orig中'净值型'对应的具体码值未在文档中明确，需进一步确认"
LIMIT_REVIEW = "需求中'一般不大于10'的'一般'未定义排除规则，需确认是否将大于10作为异常候选处理"
ENUMERATED_REVIEW = ("需要确认proj_info_dtl_pboc.c_oper_mode_orig中哪些码值属于“净值型”"
                     "（字典线索为1开放式净值型、3封闭式净值型，是否1和3均视为净值型）")
VALUE = {"left": "f_netvalue", "op": "gt", "right_type": "value", "right": 10}
MISSING = {"left": "f_netvalue", "op": "is_null"}


def _project_rules(selection, proposal):
    fields = [("project_id", "项目编号", "varchar", "Y"), ("project_name", "项目名称", "varchar", ""),
              ("d_cdate", "数据日期", "date", ""), ("f_netvalue", "单位净值", "numeric", ""),
              ("f_totalnetvalue", "累计净值", "numeric", ""), ("c_oper_mode", "运行方式", "varchar", ""),
              ("c_oper_mode_orig", "运行方式_原始", "varchar", "")]
    fields += [(f"spare_{i}", f"备用字段{i}", "varchar", "") for i in range(63)]
    rules, model = _rules([selection, proposal], table="proj_info_dtl_pboc", table_cn="项目信息", fields=fields)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(["c_oper_mode_orig", "c_oper_mode"]))
                           .values(dictionary="1-开放式净值型\n2-开放式非净值型\n3-封闭式净值型\n4-封闭式非净值型"))
    return rules, model


@pytest.mark.parametrize("complete_proposal", [True, False])
def test_explicit_scope_nonempty_and_soft_bound_generate_a_preview_without_reasking(complete_proposal):
    selection = {"target": {"table": "proj_info_dtl_pboc"}, "uncertainties": [SCOPE_REVIEW]}
    proposal = {"rule_type": "field_compare", "expression": {"logic": "any", "conditions": [VALUE, MISSING]},
                "null_policy": "review", "uncertainties": [LIMIT_REVIEW]}
    if not complete_proposal:
        proposal.update(rule_type=None, expression=None)
    rules, model = _project_rules(selection, proposal)
    candidate = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert len(model.calls) == 2
    assert not candidate.get("preview_error") and not candidate["uncertainties"] and not candidate["questions"], candidate
    preview = candidate["preview"]
    definition = preview["definition"]
    assert definition["expression"]["logic"] == "any"
    conditions = definition["expression"]["conditions"]
    assert all(item["left"] == "f_netvalue" for item in conditions)
    assert {(item["op"], item.get("right")) for item in conditions} == {("gt", 10), ("is_null", None)}
    if complete_proposal:
        assert conditions[0]["op"] == "gt", "保留已经过核对的模型方案"
    assert definition["filters"] == [{"table": "base", "field": "c_oper_mode_orig", "op": "in",
                                     "value": ["1", "3"], "confirmed": True}]
    assert "IS NULL" in preview["sql_preview"] and " OR " in preview["sql_preview"]
    assert any("人工核实" in text for text in candidate["notices"])


@pytest.mark.parametrize("stage", ["select_table", "generate_rule"])
def test_enumerated_scope_question_is_answered_by_the_document_at_generation_and_retry(stage):
    selection = {"target": {"table": "proj_info_dtl_pboc"}}
    proposal = {"rule_type": "field_compare", "expression": {"logic": "any", "conditions": [VALUE, MISSING]}}
    (selection if stage == "select_table" else proposal)["uncertainties"] = [ENUMERATED_REVIEW]
    rules, model = _project_rules(selection, proposal)
    candidate = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert candidate["model_judgments"][stage]["uncertainties"] == [ENUMERATED_REVIEW]
    assert not candidate["uncertainties"] and not candidate["questions"]
    assert candidate["preview"]["definition"]["filters"][0]["value"] == ["1", "3"]
    prompt = model.calls[1]["messages"][0]["content"].split("选表阶段上下文（核实仍有效的事项）：", 1)[1]
    first_prompt = model.calls[0]["messages"][0]["content"]
    assert "完整字典映射：proj_info_dtl_pboc.c_oper_mode_orig" in first_prompt
    assert "全部码值为 1=开放式净值型、3=封闭式净值型" in first_prompt
    assert "仍需核对口径，不是已确认事实" not in first_prompt
    context, _ = json.JSONDecoder().raw_decode(prompt)
    assert context["verified_category_filter"] == {
        "category": "净值型", "field": "c_oper_mode_orig",
        "entries": [{"value": "1", "label": "开放式净值型"}, {"value": "3", "label": "封闭式净值型"}],
    }
    assert ENUMERATED_REVIEW not in context["uncertainties"]
    old = {**candidate["preview"]["definition"], "uncertainties": [ENUMERATED_REVIEW], "uncertainty_resolutions": []}
    rechecked = rules.preview_candidate(user(), old, return_questions=True)
    assert rechecked["sql_preview"] == candidate["preview"]["sql_preview"]
    assert not rechecked["definition"]["uncertainties"]
    assert len(model.calls) == 2, "重新核对已选口径应只读当前文档，不再调用模型"


def test_structured_lookup_preserves_only_unanswered_references_across_stages():
    original = {"table": "proj_info_dtl_pboc", "field": "c_oper_mode_orig", "category": "净值型"}
    unknown = {**original, "category": "未说明的类别"}
    select = {"target": {"table": original["table"]}, "dictionary_questions": [original]}
    draft = {"rule_type": "field_compare", "expression": {"logic": "any", "conditions": [VALUE, MISSING]},
             "dictionary_questions": [unknown, original], "uncertainties": ["需核实月末截止日期"]}
    rules, model = _project_rules(select, draft)
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    assert result["pending_dictionary_questions"] == [unknown]
    assert not result["preview"] and "需核实月末截止日期" in result["uncertainties"]
    assert any("未说明的类别" in note for note in result["uncertainties"])
    assert not any("“净值型”" in note for note in result["uncertainties"])
    assert result["model_judgments"]["generate_rule"]["dictionary_questions"] == [unknown, original]
    assert len(model.calls) == 2


def test_preview_rechecks_a_structured_question_without_matching_a_request_template():
    ref = {"table": "proj_info_dtl_pboc", "field": "c_oper_mode_orig", "category": "净值型"}
    select = {"target": {"table": ref["table"]}}
    draft = {"rule_type": "field_compare", "expression": {"logic": "any", "conditions": [MISSING, VALUE]}}
    rules, model = _project_rules(select, draft)
    candidate = rules.parse_rule_request(user(), _request(request_text=REQUEST))
    definition = {**candidate["preview"]["definition"], "description": "按审核人已选的范围检查单位净值",
                  "uncertainties": ['proj_info_dtl_pboc.c_oper_mode_orig 字段“净值型”的字典取值需要核实。', "需核实月末截止日期"],
                  "uncertainty_resolutions": ["", ""]}
    result = rules.preview_candidate(user(), {"definition": definition, "pending_dictionary_questions": [ref]}, return_questions=True)
    assert result["status"] == "needs_confirmation" and not result.get("sql_preview")
    assert result["definition"]["uncertainties"] == ["需核实月末截止日期"]
    assert result["definition"]["uncertainty_resolutions"] == [""]
    assert len(model.calls) == 2


@pytest.mark.parametrize("model_draft", [
    {"rule_type": None},
    {"rule_type": "field_compare", "expression": MISSING},
    {"rule_type": "field_compare", "expression": {"logic": "any", "conditions": [{**VALUE, "right": 0}, MISSING]}},
])
def test_zero_limit_and_emphasized_nonempty_are_both_grounded_even_if_model_questions_them(model_draft):
    request = "原始运行方式为净值型的项目的单位净值一般不大于0且一定不能为空"
    notes = ["需求中'一般不大于0'的校验阈值未明确，需确认是否仅检查非空还是需检查单位净值是否大于0",
             "需求中'一般不大于0'的阈值未明确，需确认是否还需检查单位净值小于等于0或大于0；当前仅实现非空检查"]
    select = {"target": {"table": "proj_info_dtl_pboc"}, "uncertainties": notes[:1]}
    rules, model = _project_rules(select, {**model_draft, "uncertainties": notes[1:]})
    candidate = rules.parse_rule_request(user(), _request(request_text=request))
    assert not candidate.get("preview_error"), candidate.get("preview_error")
    assert not candidate["questions"] and not candidate["uncertainties"], candidate["uncertainties"]
    expression = candidate["preview"]["definition"]["expression"]
    assert expression["logic"] == "any"
    assert {(item["left"], item["op"], item.get("right")) for item in expression["conditions"]} == {
        ("f_netvalue", "gt", 0), ("f_netvalue", "is_null", None),
    }
    assert candidate["preview"]["definition"]["filters"][0]["value"] == ["1", "3"]
    assert candidate["model_judgments"]["select_table"]["uncertainties"] == notes[:1]
    assert candidate["model_judgments"]["generate_rule"]["uncertainties"] == notes[1:]
    assert len(model.calls) == 2
