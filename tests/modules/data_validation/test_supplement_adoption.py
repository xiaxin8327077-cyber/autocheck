from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

import pytest

from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.module import MANIFEST
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_project_driver_binding import document_tables, make_rules
from tests.modules.data_validation.test_frontend_multi_behavior import copy_web_modules
from tests.modules.data_validation.test_full_flow import call
from tests.modules.data_validation.test_compared_grain_evidence import compared_sources, KEY


def analyze_suggestion(*, operation="SUM", documented=True, captured=None):
    project, _, detail, _ = document_tables()
    fields = {f["field_name"]: f for f in project["fields"] + detail["fields"]}
    fields["transfer_flag"].update(field_cn="项目状态", dictionary="1-存续\n2-终止")
    fields["project_received"]["logic"] = "业务别名：项目实收。"
    fields["funding_received"]["logic"] = "业务别名：募集实收。"
    fields["day"].update(source_table="mart.project_snapshot", source_field="day")
    if documented:
        fields["funding_owner"]["is_pk"] = "Y"
    refs = [{"table_name": "funding_rows", "field_name": "funding_received"},
            {"table_name": "project_snapshot", "field_name": "project_received"}]
    suggestion = {"title": "项目实收与募集份额合计一致", "kind": "aggregate_consistency",
                  "operations": [operation], "references": refs, "preconditions": ["各明细都已入账"]}
    if captured:
        suggestion = captured
        owner_ref, funding_ref = captured["references"]
        project["table_name"], detail["table_name"] = owner_ref["table_name"], funding_ref["table_name"]
        fields["project_received"]["field_name"] = owner_ref["field_name"]
        fields["funding_received"]["field_name"] = funding_ref["field_name"]
        for name in ("day", "funding_owner"):
            fields[name]["source_table"] = "mart." + project["table_name"]
        detail["fields"].append({**fields["funding_received"], "field_name": "f_end_amt",
                                 "field_cn": "期末产品金额", "logic": "期末份额乘以单位净值"})
    left = fields["project_received"]["field_name"]
    draft = {"rule_name": "存续项目实收非负", "rule_type": "field_compare", "business_key": "project_key",
             "project_driver": {"version": 1, "table_role": "base"}, "violation_message": "实收小于零",
             "expression": {"left": left, "op": "lt", "right_type": "value", "right": 0},
             "null_policy": "zero", "semantic_intent": {
                 "metrics": [{"side": "left", "term": "项目实收", "fields": [left]}],
                 "scopes": [{"table": "base", "category": "存续", "fields": ["transfer_flag"],
                             "memberships": {"transfer_flag": {"include": ["1"], "exclude": ["2"]}}}],
                 "open_questions": []}, "ai_suggestions": [suggestion]}
    other = deepcopy(draft)
    other.pop("ai_suggestions")
    other["rule_name"] = "存续项目募集实收非负"
    other["business_key"] = "funding_id"
    other["project_driver"]["table_role"] = "related"
    right = fields["funding_received"]["field_name"]
    other["expression"]["left"] = right
    other["semantic_intent"]["metrics"] = [{"side": "left", "term": "募集实收", "fields": [right]}]
    other["semantic_intent"]["scopes"][0]["table"] = "related"
    other["join"] = {"table_name": project["table_name"], "on": [{"left": "funding_owner", "right": "project_key"}],
                     "report_date_field": "day", "relationship_confirmed": True, "unmatched_policy": "exclude"}
    reply = {"plan_mode": "parallel", "plans": [{"target": {"table": project["table_name"]}, "draft": draft},
             {"target": {"table": detail["table_name"]}, "related_target": {"table": project["table_name"]}, "draft": other}],
             "ai_suggestions": [suggestion]}
    rules, model = make_rules([reply], [project, detail])
    result = rules.parse_rule_request(user(), _request(request_text="存续项目的实收不得小于0", analysis_protocol=2))
    assert len(model.calls) == 1
    assert len(result.get("candidate_options", [])) == 2, result.get("uncertainties")
    return rules, result


def test_independent_adoption_uses_only_grounded_model_proposal():
    rules, result = analyze_suggestion()
    [suggestion] = result["ai_suggestions"]
    assert suggestion["adoption"] == {"operations": ["sum"], "preconditions": ["各明细都已入账"]}
    assert not suggestion.get("definition")
    assert len(result["candidate_options"]) == 2
    assert rules.list_rules(user(), {})["items"] == []


# Public structured advice from the November 20 review response, before the owner
# confirmed the comparison basis. The model supplied no SQL or draft definition.
CAPTURED_PAID_ADVICE = {
    "category": "consistency", "kind": "aggregate_consistency",
    "title": "项目4001实收余额与募集合同期末实收份额汇总核对",
    "reason": "业务知识明确实收核对按项目、数据日期汇总募集合同明细f_end_share，应与项目4001实收余额对应；两者均为同一项目实收口径，建议核查一致性与允许差额。",
    "references": [
        {"table_name": "proj_info_dtl_pboc", "field_name": "f_equity_total_4001_bal"},
        {"table_name": "raise_info_dtl_pboc", "field_name": "f_end_share"},
    ],
    "preconditions": ["需确认单位（元/万元）及是否包含待结转收益", "需确认允许差额范围"],
    "limitations": ["合同份额含待结转收益，项目余额为科目余额，两者统计口径可能不同，差异不代表错误"],
}


@pytest.mark.skipif(not shutil.which("node"), reason="需要 Node.js 验证工作台按钮")
def test_captured_paid_advice_uses_confirmed_knowledge_without_reasking(tmp_path):
    rules, result = analyze_suggestion(captured=CAPTURED_PAID_ADVICE)
    [offered] = result["ai_suggestions"]
    assert offered["adoption"]["preconditions"] == CAPTURED_PAID_ADVICE["preconditions"]
    assert offered["references"] == CAPTURED_PAID_ADVICE["references"]
    confirmed = "项目4001余额与同项目同日募集期末实收份额合计比较，包含待结转收益，差额非0即异常，容差为0。"
    knowledge = rules.knowledge
    entry = {**knowledge.settings()["draft"][0], "kind": "local", "topic": "项目实收与募集份额对照",
             "keywords": ["项目4001实收余额"], "summary": confirmed, "source_name": "监管报送集市",
             "reference": "内存验收中的用户确认", "valid_from": "", "valid_to": ""}
    knowledge.save(user(), {"expected_revision": 0, "entries": [entry]})
    knowledge.save(user(), {"expected_revision": 1, "enabled": True}, activation=True)
    _, generated, _ = compared_sources(shared_alias=True, join_keys=[KEY])
    proposal = deepcopy(generated.payloads[0])
    project, funding = CAPTURED_PAID_ADVICE["references"]
    proposal["target"]["table"] = project["table_name"]
    proposal["related_target"]["table"] = funding["table_name"]
    draft = proposal["draft"]
    draft["join"]["table_name"] = funding["table_name"]
    draft["expression"].update(left=project["field_name"], right=funding["field_name"])
    for metric, ref in zip(draft["semantic_intent"]["metrics"], (project, funding)):
        metric["fields"] = [ref["field_name"]]
    draft["semantic_intent"]["scopes"] = deepcopy(rules.model.payloads[0]["plans"][0]["draft"]["semantic_intent"]["scopes"])
    rules.model.payloads.append(proposal)
    visit, analyze, router, owner = browser_and_routes(tmp_path, rules, result)
    ready = analyze(visit()["request"])
    assert len(rules.model.calls) == 2 and confirmed in str(rules.model.calls[-1]["messages"])
    assert ready["preview"] and not ready["questions"] and not ready["uncertainties"]
    for terminal in ({"status": "completed", "result": ready},
                     {"status": "failed", "error": {"code": "MODEL_UNAVAILABLE"}}):
        visit(end_session=True, cancel_snapshot=terminal)
    merged = visit(child=ready)
    sample = merged["sample"]
    assert sample["definition"]["expression"] == {
        "left": "f_equity_total_4001_bal", "op": "neq", "right_type": "field",
        "right": "f_end_share", "right_table": "related"}
    assert sample["definition"]["project_driver"]["table_role"] == "base"
    preview = ready["preview"]
    assert "f_end_amt" not in preview["sql_preview"]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE proj_info_dtl_pboc (day, project_key, project_name, transfer_flag, f_equity_total_4001_bal)")
        db.execute("CREATE TABLE raise_info_dtl_pboc (day, funding_owner, f_end_share, f_end_amt)")
        day = "2026-11-20"
        db.executemany("INSERT INTO proj_info_dtl_pboc VALUES (?, ?, ?, ?, ?)",
                       [(day, "A", "甲", "1", 10), (day, "B", "乙", "1", 8.001)])
        db.executemany("INSERT INTO raise_info_dtl_pboc VALUES (?, ?, ?, ?)",
                       [(day, "A", 3, 100), (day, "A", 7, 100), (day, "B", 8, 8.001),
                        ("2026-11-19", "A", 30, 0)])
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": day}).fetchall()
        assert [(row["TCMP编号"], row["异常类型"]) for row in rows] == [("B", "numeric")]
    tested = call(router, "POST", "/ai/tests", owner, sample)["data"]
    assert tested["passed_count"] and not tested["failed_count"] and not tested["not_run_count"]
    assert [o["candidate"]["expression"]["op"] for o in result["candidate_options"]] == ["lt", "lt"]
    assert rules.list_rules(user(), {})["items"] == []
    for check in merged["samples"]:
        assert call(router, "POST", "/ai/tests", owner, check)["data"]["failed_count"] == 0
    saved = call(router, "POST", "/ai/candidates/batch-save", {**owner, "capabilities": [*owner["capabilities"], "dv.manage"]},
                 merged["batch"])["data"]
    assert saved["count"] == 3
    definitions = [rules.storage.latest_version(row["id"]) for row in saved["rules"]]
    assert [entry["definition"]["expression"]["op"] for entry in definitions] == ["lt", "lt", "neq"]
    expected_hashes = {check["expected_hash"] for check in merged["samples"]}
    assert {entry["content_sha256"] for entry in definitions} == expected_hashes


def test_average_stays_informational():
    _, result = analyze_suggestion(operation="AVG")
    [suggestion] = result["ai_suggestions"]
    assert suggestion["support_level"] == "unsupported" and "adoption" not in suggestion


def browser_and_routes(tmp_path, rules, result):
    owner = {**user(), "capabilities": ["dv.ai_use", "dv.test", "dv.view"]}
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    # Both input and output of the browser analysis call cross the Python route boundary.
    # First collect its proposed request. Then replay its response through the same UI.
    fixture, requests = tmp_path / "fixture.json", tmp_path / "requests.json"
    copy_web_modules(tmp_path)
    scenario = shutil.copy(Path(__file__).with_name("frontend_supplement_adoption.mjs"), tmp_path)
    shutil.copy(Path(__file__).with_name("frontend_workbench_dom.mjs"), tmp_path)
    def visit(pending=None, child=None, reasoning=False, scope_review=None, end_session=False, failure=False,
              cancel_snapshot=None):
        fixture.write_text(json.dumps({"result": result, "pending": pending, "child": child, "reasoning": reasoning,
                                       "scopeReview": scope_review, "endSession": end_session, "failure": failure,
                                       "cancelSnapshot": cancel_snapshot}),
                           encoding="utf-8")
        run = subprocess.run(["node", scenario, fixture, requests], cwd=tmp_path, encoding="utf-8",
                             capture_output=True, timeout=60)
        assert run.returncode == 0, run.stderr
        return json.loads(requests.read_text(encoding="utf-8"))
    def analyze(payload):
        job = call(router, "POST", "/ai/analyses", owner, payload)["data"]
        path = "/ai/analyses/" + job["analysis_id"]
        for _ in range(100):
            snapshot = call(router, "GET", path, owner)["data"]
            if snapshot["status"] != "running":
                assert snapshot["status"] == "completed", snapshot.get("error")
                return snapshot["result"]
            time.sleep(0.05)
        pytest.fail("模拟分析会话未在期限内完成")
    return visit, analyze, router, owner


@pytest.mark.skipif(not shutil.which("node"), reason="需要 Node.js 验证工作台按钮")
def test_button_starts_independent_analysis_and_transports_real_sample(tmp_path):
    rules, result = analyze_suggestion()
    _, compare_model, _ = compared_sources(shared_alias=True, join_keys=[KEY])
    proposal = deepcopy(compare_model.payloads[0])
    proposal["draft"]["semantic_intent"]["scopes"] = deepcopy(rules.model.payloads[0]["plans"][0]["draft"]["semantic_intent"]["scopes"])
    rules.model.payloads.append(proposal)
    visit, analyze, router, owner = browser_and_routes(tmp_path, rules, result)
    payload = visit()["request"]
    assert visit(reasoning=True, scope_review="unselected")["request"]["reasoning_enabled"] is True
    visit(scope_review="separate", end_session=True)
    visit(failure=True)
    assert payload["reasoning_enabled"] is False and payload["model_id"] == "model-1" and payload["source_id"] == "src"
    assert all(value in payload["request_text"] for value in ("project_received", "funding_received", "各明细都已入账", "transfer_flag", "sum"))
    assert "revision_of" not in payload and "revised_definition" not in payload
    pending_proposal = deepcopy(proposal)
    pending_proposal["draft"]["semantic_intent"]["open_questions"] = ["募集份额与项目实收采用什么计量口径比较？"]
    rules.model.payloads[1] = pending_proposal
    pending = analyze(payload)
    assert not pending.get("preview") and "计量口径" in str(pending.get("uncertainties"))
    rules.model.payloads.append(proposal)
    accepted = visit(pending)["clarification"]
    assert accepted["request_text"] == payload["request_text"] and accepted["reasoning_enabled"] is False
    ready = analyze(accepted)
    assert ready["preview"], ready.get("uncertainties")
    sample_payload = visit(pending, ready)["sample"]
    definition = sample_payload["definition"]
    assert definition["expression"]["op"] == "neq" and definition["expression"]["right_table"] == "related"
    assert definition["project_driver"]["table_role"] == "base" and definition["filters"][0]["field"] == "transfer_flag"
    assert definition["join"]["on"] == [KEY] and definition["join"]["right_aggregate"] == "sum"
    preview = ready["preview"]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE project_snapshot (day, project_key, project_name, transfer_flag, project_received)")
        db.execute("CREATE TABLE funding_rows (day, funding_owner, funding_received)")
        day = "2026-11-20"
        db.executemany("INSERT INTO project_snapshot VALUES (?, ?, ?, ?, ?)",
                       [(day, key, key, scope, total) for key, scope, total in
                        [("A", "1", 10), ("B", "1", 11), ("C", "1", 0), ("D", "2", 20)]])
        db.executemany("INSERT INTO funding_rows VALUES (?, ?, ?)",
                       [(day, "A", 4), (day, "A", 6), (day, "B", 10), ("2026-11-19", "C", 0)])
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": day}).fetchall()
        assert {(row["TCMP编号"], row["异常类型"], row["关联记录数"]) for row in rows} == {
            ("B", "numeric", 1), ("C", "missing_record", 0)}
    tested = call(router, "POST", "/ai/tests", owner, sample_payload)["data"]
    assert tested["passed_count"] and not tested["failed_count"] and not tested["not_run_count"]
    assert rules.list_rules(user(), {})["items"] == []
