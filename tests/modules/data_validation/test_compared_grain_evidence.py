from copy import deepcopy
import time

import pytest

from auto_check.modules.data_validation.candidate_preview import run_preview_cases
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_project_driver_binding import document_tables, make_rules


KEY = {"left": "project_key", "right": "funding_owner"}
DATE = {"left": "day", "right": "day"}


def compared_sources(*, shared_alias, join_keys, another_metric=False):
    project, _, funding, _ = document_tables()
    fields = {f["field_name"]: f for f in funding["fields"]}
    fields["day"].update(source_table="mart.project_snapshot", source_field="day")
    fields["funding_owner"]["is_pk"] = "Y"
    project_measure = next(f for f in project["fields"] if f["field_name"] == "project_received")
    project_measure["logic"] = "业务别名：项目实收。"
    fields["funding_received"].update(field_cn="募集实收" if shared_alias else "募集份额",
                                      logic="业务别名：募集实收。" if shared_alias else "")
    if another_metric:
        funding["fields"].append({**fields["funding_received"], "field_name": "other_received", "field_cn": "其他实收"})
    proposal = {
        "business_key": "project_key", "project_driver": {"version": 1, "table_role": "base"},
        "rule_name": "实收与募集份额合计一致", "rule_type": "field_compare", "null_policy": "zero",
        "violation_message": "项目实收与同日募集份额合计不一致",
        "expression": {"left": "project_received", "op": "neq", "right_type": "field",
                       "right_table": "related", "right": "funding_received"},
        "join": {"table_name": "funding_rows", "on": deepcopy(join_keys), "report_date_field": "day",
                 "relationship_confirmed": True, "unmatched_policy": "review", "right_aggregate": "sum"},
        "semantic_intent": {"metrics": [
            {"side": "left", "term": "项目实收", "fields": ["project_received"]},
            {"side": "right", "term": "募集份额", "fields": ["funding_received"]},
        ], "scopes": [], "open_questions": []},
    }
    selection = {"target": {"table": "project_snapshot"}, "related_target": {"table": "funding_rows"}}
    rules, model = make_rules([{**selection, "draft": proposal}], tables=[project, funding])
    request = _request(request_text="对比项目和募集表中的实收是否一致", analysis_protocol=2)
    return rules, model, request


@pytest.mark.parametrize(("shared_alias", "join_keys"), [(True, [KEY]), (False, [DATE, KEY]), (True, [KEY, DATE])])
def test_bound_right_operand_and_proven_period_compile_the_first_aggregate(shared_alias, join_keys):
    rules, model, request = compared_sources(shared_alias=shared_alias, join_keys=join_keys)
    result = rules.parse_rule_request(user(), request)
    assert len(model.calls) == 1
    assert result["preview"] and not result["questions"] and not result.get("candidate_options")
    definition = result["preview"]["definition"]
    assert definition["expression"] == {"left": "project_received", "op": "neq", "right_type": "field",
                                         "right_table": "related", "right": "funding_received"}
    assert definition["join"]["right_aggregate"] == "sum"
    verified = run_preview_cases(result["preview"])
    assert verified["passed_count"] and not verified["failed_count"] and not verified["not_run_count"]


@pytest.mark.parametrize("bad_keys", [
    [KEY, DATE, DATE], [DATE], [KEY, {"left": "project_key", "right": "funding_id"}],
    [KEY, {"left": "project_key", "right": "day"}],
])
def test_aggregate_preview_rejects_unproven_or_duplicate_keys(bad_keys):
    rules, _, request = compared_sources(shared_alias=False, join_keys=[KEY])
    version = rules.parse_rule_request(user(), request)["preview"]["definition"]
    bad = deepcopy(version)
    bad["join"]["on"] = deepcopy(bad_keys)
    bad["semantic_intent"]["expected_join"]["on"] = deepcopy(bad_keys)
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.preview_candidate(user(), {"definition": bad})


@pytest.mark.parametrize("right_owner", ["related", "base"])
def test_opposite_operand_covers_only_its_exact_field_and_owner(right_owner):
    rules, model, request = compared_sources(shared_alias=True, join_keys=[KEY], another_metric=True)
    proposal = deepcopy(model.payloads[0])
    proposal["draft"]["expression"]["right_table"] = right_owner
    analysis = SemanticAnalysis(rules, user(), rules._analysis_inputs(user(), request), request["request_text"], None, None)
    analysis.index = DocumentEvidence(analysis.tables, analysis.fields, analysis.request)
    _, pending = analysis.expand_interpretation_evidence(proposal)
    assert pending
    missing_left = {item["field"] for item in analysis.interpretation_checks
                    if item["side"] == "left" and item["table"] == "funding_rows"}
    assert "other_received" in missing_left
    assert ("funding_received" in missing_left) == (right_owner == "base")


def captured_ended_sum():
    from tests.modules.data_validation.test_project_driver_binding import field, table

    project, funding, account = "proj_info_dtl_pboc", "raise_info_dtl_pboc", "account_info_dtl_pboc"
    left, right = "f_equity_total_4001_bal", "f_end_share"
    title = "项目4001实收余额与募集期末实收份额汇总差异核对"
    reason = "已确认业务知识明确项目端4001科目余额与募集端f_end_share为独立维度，且按同一c_projinnercode、d_cldate对应，应核对跨维度差异。差额不等于0即异常，容差0。"
    response = {"target": {"table": project}, "related_target": {"table": funding}, "draft": {
        "business_key": "c_projinnercode", "project_driver": {"version": 1, "table_role": "base"},
        "rule_name": title, "rule_type": "field_compare", "expression": {"left": left, "op": "neq", "right_type": "field",
            "right_table": "related", "right": right}, "violation_message": "项目4001实收余额与募集期末实收份额汇总差异不为0",
        "null_policy": "zero", "semantic_intent": {"metrics": [
            {"side": "left", "term": "权益合计（4001科目余额）", "fields": [left]},
            {"side": "right", "term": "募集期末实收份额", "fields": [right]}],
            "scopes": [{"category": "项目存续状态", "fields": ["c_projstatus"],
                        "memberships": {"c_projstatus": {"include": ["2"], "exclude": []}}}], "open_questions": []},
        "join": {"table_name": funding, "on": [{"left": "c_projinnercode", "right": "c_projinnercode"}],
                 "report_date_field": "d_cldate", "right_aggregate": "sum", "relationship_confirmed": True,
                 "unmatched_policy": "exclude"},
    }}
    docs = [table(1, project, "项目信息", "项目", [
        field("c_projinnercode", "TCMP编号", pk="Y", source=("upstream.entity", "entity_id"),
              logic="直接取项目主数据的项目编号[entity_id]。"), field("d_cldate", "数据日期", "date"),
        field("project_name", "项目名全称"),
        field("c_projstatus", "产品存续状态", dictionary="1-存续\n2-终止"),
        field("branch_code", "项目分组", dictionary="A-甲\nB-乙"),
        field(left, "权益合计（4001科目余额）", "numeric", logic="业务别名：项目实收信托、项目4001实收信托余额。定义：同一报送日期项目4001科目的实收信托余额。")]),
        table(2, funding, "募集合同明细", "募集", [
            field("c_projinnercode", "项目编号", pk="Y", source=(f"mart.{project}", "c_projinnercode")),
            field("d_cldate", "数据日期", "date", source=(f"mart.{project}", "d_cldate")), field("contract_id", "合同编号", pk="Y"),
            field(right, "期末产品份额（实收本金）", "numeric", logic="业务别名：募集期末实收份额。")]),
        table(3, account, "科目余额", "科目", [field("f_balance", "科目余额", "numeric")])]
    return response, docs, title, reason


@pytest.mark.parametrize("request_mode", ["ordinary", "adopted", "edited"])
def test_captured_sum_draft_does_not_expand_verified_adopted_operands_across_tables(request_mode):
    response, docs, title, reason = captured_ended_sum()
    project, funding, account = (row["table_name"] for row in docs)
    left, right = (response["draft"]["expression"][name] for name in ("left", "right"))
    rules, _ = make_rules([], tables=docs)
    text = title + "\n" + reason + ("。另按单独的科目余额判断。" if request_mode == "edited" else "")
    request = _request(request_text=text, analysis_protocol=2, include_suggestions=False)
    scope = {"variants": [{"filters": []}], "suggestion": {"category": "consistency", "kind": "aggregate_consistency",
            "title": title, "reason": reason, "references": [{"table_name": project, "field_name": left}, {"table_name": funding, "field_name": right}]}}
    inputs = rules._analysis_inputs(user(), request, period_scope=None if request_mode == "ordinary" else scope)
    analysis = SemanticAnalysis(rules, user(), inputs, text, None, None)
    analysis.index = DocumentEvidence(analysis.tables, analysis.fields, text)
    analysis.expand_interpretation_evidence(response)
    competing = {(check["table"], check["field"]) for check in analysis.interpretation_checks}
    assert ((account, "f_balance") in competing) == (request_mode != "adopted")


@pytest.mark.parametrize("row", ["first", "second", "new_filter"])
def test_captured_sum_draft_does_not_reopen_scopes_already_selected_on_the_parent(row):
    captured, docs, title, reason = captured_ended_sum()
    project, funding = (doc["table_name"] for doc in docs[:2])
    left, right = (captured["draft"]["expression"][side] for side in ("left", "right"))
    known_scope = {"category": "终止", "fields": ["c_projstatus"],
                   "memberships": {"c_projstatus": {"include": ["2"], "exclude": ["1"]}}}
    main = deepcopy(captured)
    main.pop("related_target")
    main["draft"].pop("join")
    main["draft"]["expression"] = {"left": left, "op": "neq", "right_type": "value", "right": 0}
    main["draft"]["semantic_intent"].update(metrics=[{"side": "left", "term": left, "fields": [left]}], scopes=[known_scope])
    rules, model = make_rules([main], tables=docs)
    parent_request = _request(request_text=f"终止项目的{left}不为0时异常", analysis_protocol=2, include_suggestions=False)
    parent = rules.parse_rule_request(user(), parent_request)
    assert parent.get("preview"), parent.get("uncertainties")
    parent["ai_suggestions"] = [{"id": "ended-sum", "category": "consistency", "kind": "aggregate_consistency",
        "title": title, "reason": reason, "adoption": {"operations": ["sum"], "preconditions": []},
        "references": [{"table_name": project, "field_name": left}, {"table_name": funding, "field_name": right}]}]
    job = rules.analyses.start(user(), parent_request, worker=lambda *_: parent)
    for _ in range(100):
        if rules.analyses.completed_result(user(), job["analysis_id"]):
            break
        time.sleep(.01)

    first, second = deepcopy(captured), deepcopy(captured)
    for reply, included, excluded in ((first, ["2"], []), (second, ["1"], ["2"])):
        intent = reply["draft"]["semantic_intent"]
        intent["metrics"][0]["term"] = "项目4001实收余额"
        intent["scopes"][0].update(category="存续项目", memberships={"c_projstatus": {"include": included, "exclude": excluded}})
        if row == "new_filter":
            reply["draft"]["filters"] = [{"field": "branch_code", "op": "eq", "value": "A"}]
    model.payloads.extend([first, second] if row == "first" else [second])
    receipt = parent["preview"]
    request = _request(request_text=title + "\n" + reason, analysis_protocol=2, include_suggestions=False, adoption_context={
        "mode": "inherit_selected", "parent_analysis_id": job["analysis_id"], "parent_context": parent["analysis_context"],
        "suggestion_id": "ended-sum", "parents": [{"definition": receipt["definition"], "hash": receipt["content_sha256"]}],
    })

    before = len(model.calls)
    result = rules.parse_rule_request(user(), request)
    assert result.get("preview"), result.get("uncertainties")
    child_calls = model.calls[before:]
    assert not any("待修复草稿数据" in call["messages"][0]["content"] or "只补全草稿指定位置" in call["messages"][0]["content"]
                   for call in child_calls)
    assert 1 <= len(child_calls) <= 2
    definition = result["preview"]["definition"]
    assert {f["field"]: f["value"] for f in definition["filters"]} == {
        "c_projstatus": "2", **({"branch_code": "A"} if row == "new_filter" else {})}
    assert definition["join"]["right_aggregate"] == "sum"
    assert definition["expression"] == captured["draft"]["expression"]
