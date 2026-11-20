"""执行版本、查询输出及同范围导出的端到端回归（合成数据）。"""

import csv
import io
import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.storage import RULES, TASKS
from tests.modules.data_validation.support import Metadata, loan_definition, service, user


class ResultMetadata(Metadata):
    def __init__(self, names, values):
        super().__init__()
        self.names, self.values = names, values

    def execute_select(self, *_args, **_kwargs):
        return SimpleNamespace(columns=self.names, rows=self.values, truncated=False)


def registered(store, definition, sql):
    rule = store.create_rule(creator_user_id="1", name=definition["name"], description="",
                             definition=definition, sql_text=sql, mapping_version="v1",
                             content_sha256="hash", generation_mode="manual")
    store.set_status(rule["id"], "enabled", rule["version_id"])
    return rule["id"]


def test_selected_fields_survive_storage_paging_and_export_without_driver_extras():
    metadata = ResultMetadata(
        ["business_key", "checked_value", "data_date", "empty_field", "null_field", "zero_field", "unexpected"],
        [("00001", Decimal("1.2300000000000000000007"), date(2026, 9, 30), "", None, 0, "private")],
    )
    _, svc = service(metadata=metadata)
    sql = ("SELECT t.project_code AS business_key, t.maturity_date AS checked_value, "
           "t.report_date AS data_date, '' AS empty_field, NULL AS null_field, 0 AS zero_field FROM loan t")
    rule_id = registered(svc.storage, loan_definition(rule_type="custom_sql", sql=sql, report_category="pbc_template"), sql)
    task = svc.start_task(user(), {"rule_ids": [rule_id], "report_period": "2026-09-30"})
    issue = svc.list_task_issues(user(), task["id"])["items"][0]
    details = issue["query_result"]
    assert details["values"] == {
        "business_key": "00001", "checked_value": "1.2300000000000000000007", "data_date": "2026-09-30",
        "empty_field": "", "null_field": None, "zero_field": 0,
    }
    columns = {c["name"]: c for c in details["columns"]}
    assert columns["checked_value"] == {"name": "checked_value", "label": "checked_value", "source_field": "maturity_date"}
    assert columns["business_key"]["label"] == "business_key"
    assert issue["report_category"] == "group:pbc"
    rows = list(csv.DictReader(io.StringIO(svc.export_issues(user(), task["id"], "csv")["content"].decode())))
    assert rows[0]["checked_value"] == details["values"]["checked_value"]
    assert rows[0]["校验字段"] == "checked_value（maturity_date）"
    assert "unexpected" not in rows[0]


def test_selected_oversized_and_unknown_types_are_explicit_without_object_stringification():
    class Private:
        def __str__(self):
            raise AssertionError("private objects must not be rendered")

    sql = ("SELECT t.maturity_date AS checked_value, t.issue_date AS large, t.report_date AS private_value, "
           "'问题' AS violation_message FROM loan AS t")
    definition = loan_definition(rule_type="custom_sql", sql=sql)
    meta = ResultMetadata(["unexpected", "checked_value", "large", "private_value", "violation_message"],
                          [("driver-only", 0, "界" * 100000, Private(), "问题")])
    run = execute_version({"definition": definition, "sql_text": sql}, {"report_date": "2026-09-30"}, meta)
    result = run.query_results[0]
    assert result["values"] == {"checked_value": 0, "violation_message": "问题"}
    assert result["unavailable"] == {"large": "oversized", "private_value": "unsupported"}
    assert len(json.dumps(result).encode()) < 65535


@pytest.mark.parametrize("sql", [
    "SELECT * FROM loan", "SELECT t.* FROM loan AS t",
    "SELECT v.* FROM (SELECT t.* FROM loan AS t) AS v",
])
def test_custom_wildcards_do_not_collect_driver_fields(sql):
    meta = ResultMetadata(["business_key", "checked_value", "secret"], [("private", 4, "private")])
    run = execute_version({"definition": loan_definition(rule_type="custom_sql", sql=sql), "sql_text": sql}, {}, meta)
    assert run.query_results == ({"columns": [], "values": {}, "status": "unsupported_projection"},)
    assert run.rows[0]["business_key"] is None


def test_compiler_wrapper_keeps_its_explicit_aggregate_evidence():
    from tests.modules.data_validation.test_related_sum import BASE, RELATED, definition
    from auto_check.modules.data_validation.compiler import compile_rule

    spec = definition("mysql")
    sql, _ = compile_rule({"definition": spec})
    meta = ResultMetadata(["business_key", "checked_value", "data_date", "comparison_value", "related_count",
                           "violation_message", "issue_kind", "unexpected"],
                          [("00003", 0, date(2026, 9, 30), None, 0, "无明细", "missing_value", "private")])
    meta.describe_table = lambda source, table: {"columns": BASE if table == "owners" else RELATED}
    run = execute_version({"definition": spec, "sql_text": sql}, {}, meta)
    assert run.query_results[0]["values"] == {
        "business_key": "00003", "checked_value": 0, "data_date": "2026-09-30", "comparison_value": None,
        "related_count": 0, "violation_message": "无明细", "issue_kind": "missing_value",
    }
    assert {c["name"]: c.get("source_field") for c in run.query_results[0]["columns"]}["comparison_value"] == "part"


def test_scope_uses_execution_versions_even_after_rule_changes_and_owner_checks():
    db, svc = service(metadata=Metadata(rows=[("KEY",)]))
    owner = user()
    ids = []
    for old_name, code in [("人行历史", "pbc_central"), ("另一类", "old-category"), ("无分类", "")]:
        original = loan_definition(name=old_name, report_category=code)
        ids.append(registered(svc.storage, original, "SELECT project_code AS business_key FROM loan"))
    task = svc.start_task(owner, {"rule_ids": ids, "report_period": "2026-09-30"})
    with db.begin() as conn:
        conn.execute(RULES.update().values(name="已经删除", status="deleted", report_category="current"))
    rows = svc.list_recent_tasks(owner, {"report_category": "pbc_template"})
    assert rows[0]["categories"] == [
        {"code": "group:pbc", "name": "人行报送", "rule_count": 1},
        {"code": "old-category", "name": "old-category", "rule_count": 1},
        {"code": "__uncategorized__", "name": "未分类", "rule_count": 1},
    ]
    assert rows[0]["summary"] == dict(rule_count=1, completed_count=1, failed_count=0,
                                      pending_count=0, issue_count=1, truncated=False)
    assert svc.list_recent_tasks(owner, {"report_category": "current"}) == []
    assert svc.list_recent_tasks(user("2"), {}) == []
    admin = user("2", "admin")
    assert svc.list_recent_tasks(admin, {})[0]["id"] == task["id"]
    with pytest.raises(AppError, match="FORBIDDEN"):
        svc.task_detail(admin, task["id"], {})
    with pytest.raises(AppError, match="FORBIDDEN"):
        svc.export_issues(admin, task["id"], "csv", {"rule_id": ids[1]})
    detail = svc.task_detail(owner, task["id"], {"report_category": "__uncategorized__"})
    assert detail["total_rule_count"] == 3
    assert [(r["name"], r["source_name"], r["report_category_name"]) for r in detail["rules"]] == [
        ("无分类", "监管报表", "未分类")]
    for i in range(103):
        svc.storage.add_issue(task_id=task["id"], rule_id=ids[1], version_no=1, business_key=str(i), message="历史")
    scope = {"report_category": "old-category", "rule_id": str(ids[1])}
    page = svc.list_task_issues(owner, task["id"], {**scope, "page_size": 100, "page": 2})
    assert (page["total"], len(page["items"])) == (104, 4)
    assert all(i["query_result"] is None and i["rule_name"] == "另一类" for i in page["items"])
    result = svc.export_issues(owner, task["id"], "csv", scope)
    assert len(result["issues"]) == 104 and not result["truncated"]
    assert svc.list_task_issues(owner, task["id"], {**scope, "rule_id": ids[0]})["total"] == 0


def test_filter_precedes_recent_batch_limit():
    db, svc = service(metadata=Metadata())
    rule_id = registered(svc.storage, loan_definition(report_category="rare"), "SELECT project_code AS business_key FROM loan")
    task = svc.start_task(user(), {"rule_ids": [rule_id], "report_period": "2026-09-30"})
    with db.begin() as conn:
        conn.execute(TASKS.insert(), [dict(creator_user_id="1", source_id="src", report_period="2026-09-30",
                                          status="completed", params_json="{}", truncated=0, created_at="d")] * 101)
    rows = svc.list_recent_tasks(user(), {"report_category": "rare"})
    assert [r["id"] for r in rows] == [task["id"]]

def test_cancelled_batch_keeps_published_results_and_stays_cancelled_when_worker_finishes():
    _, svc = service()
    records = []
    for name in ("已发布", "执行中"):
        rid = registered(svc.storage, loan_definition(name=name), "SELECT project_code AS business_key FROM loan")
        version = svc.storage.latest_version(rid)
        records.append(dict(rule_id=rid, version_id=version["id"], version_no=1,
                            content_sha256=version["content_sha256"], sql_summary=""))
    task_id = svc.storage.create_task(creator_user_id="1", source_id="src", report_period="2026-09-30",
                                      params={}, rules=records)["id"]
    first, pending = svc.storage.task_rules(task_id)
    # A completed item in the cancelled batch remains inspectable after a late publication.
    snapshot = {"columns": [{"name": "x", "label": "x"}], "values": {"x": "0001"}}
    kwargs = dict(status="VIOLATION", error_code="", violation_count=1, truncated=True,
                  issues=[{"business_key": "0001", "query_result": snapshot}])
    assert svc.storage.record_rule_result(first["id"], **kwargs)
    svc.cancel_task(user(), task_id)
    assert not svc.storage.record_rule_result(first["id"], **kwargs)
    assert not svc.storage.record_rule_result(pending["id"], **kwargs)
    svc._refresh_task_status(task_id)
    detail = svc.task_detail(user(), task_id, {})
    assert detail["status"] == "cancelled" and detail["rules"][0]["status"] == "VIOLATION"
    assert svc.list_task_issues(user(), task_id)["items"][0]["query_result"] == snapshot


def test_projection_schema_upgrade_only_adds_nullable_result_and_preserves_history():
    from pathlib import Path
    from auto_check.modules.data_validation.module import DataValidationModule
    from auto_check.modules.data_validation.storage import ISSUES

    module_path = Path(__file__).resolve().parents[3] / "src/auto_check/modules/data_validation"
    manifest = json.loads((module_path / "manifest.json").read_text("utf-8"))
    assert manifest["schema_version"] >= 14
    registry = {}
    DataValidationModule().register_schema(SimpleNamespace(add=registry.__setitem__))
    assert "query_result_json" in registry[ISSUES.name]
    assert ISSUES.c.query_result_json.nullable
    migration = (module_path / "migrations/014_issue_query_results.sql").read_text("utf-8")
    assert "ALTER TABLE data_validation_issues ADD COLUMN query_result_json TEXT NULL" in migration


def test_rule_drilldown_counts_and_truncation_follow_only_matching_versions():
    from auto_check.modules.data_validation.storage import TASK_RULES

    db, svc = service(metadata=Metadata())
    ids = [registered(svc.storage, loan_definition(name=str(i), report_category="a" if i < 3 else "b"),
                      "SELECT project_code AS business_key FROM loan") for i in range(4)]
    task = svc.start_task(user(), {"rule_ids": ids, "report_period": "2026-09-30"})
    with db.begin() as conn:
        for rule_id, state, clipped in zip(ids, ["VIOLATION", "TIMEOUT", "queued", "CANCELLED"], [1, 0, 0, 0]):
            conn.execute(TASK_RULES.update().where(TASK_RULES.c.rule_id == rule_id).values(status=state, truncated=clipped))
    summary = svc.task_detail(user(), task["id"], {"report_category": "a"})["summary"]
    assert (summary["rule_count"], summary["completed_count"], summary["failed_count"], summary["pending_count"],
            summary["truncated"]) == (3, 1, 1, 1, True)
    assert svc.list_task_issues(user(), task["id"], {"report_category": "a", "rule_id": ids[1]})["truncated"] is False
    assert svc.export_issues(user(), task["id"], "csv", {"report_category": "b"})["truncated"] is False


def test_result_storage_rejects_unbounded_payload_in_same_transaction():
    from tests.modules.data_validation.test_project_results_persistence import _queued_task_rule

    _, svc = service()
    item = _queued_task_rule(svc.storage)
    with pytest.raises(ValueError):
        svc.storage.record_rule_result(item["id"], status="VIOLATION", error_code="", violation_count=2,
                                       truncated=False, issues=[
                                           {"business_key": "first"},
                                           {"business_key": "second", "query_result": {"values": {"x": "x" * 65536}}},
                                       ])
    assert svc.storage.task_rules(item["task_id"])[0]["status"] == "queued"
    assert svc.storage.list_issues(item["task_id"])["items"] == []


def test_compiled_sqlite_query_publishes_only_the_matching_project_and_contract():
    import sqlite3
    from auto_check.modules.data_validation.compiler import compile_rule
    from tests.modules.data_validation.test_project_context_executor import BASE_COLUMNS, _definition

    spec = _definition(name="合同金额校验", include_result_fields=True, report_category="pbc_template")
    sql, _params = compile_rule({"definition": spec})
    labels = {"amount": "合同金额", "contract_no": "合同编号", "project_code": "项目编号", "project_name": "项目名称"}
    columns = [dict(item, comment=labels.get(item["column_name"], "")) for item in BASE_COLUMNS]
    with sqlite3.connect(":memory:") as business:
        business.execute("CREATE TABLE contract(contract_no text, project_code text, project_name text, amount numeric, report_date date)")
        business.executemany("INSERT INTO contract VALUES(?,?,?,?,?)", [
            ("000017", "0098", "合成项目甲", 1.25, "2026-09-30"),
            ("000018", "0099", "其他期", 50, "2026-08-31"),
            ("000019", "0100", "未命中", 0, "2026-09-30"),
        ])

        def execute(_source_id, sql_text, bound, **_limits):
            cursor = business.execute(sql_text, bound)
            return SimpleNamespace(columns=[col[0] for col in cursor.description], rows=cursor.fetchall(), truncated=False)

        _, svc = service(metadata=SimpleNamespace(describe_table=lambda *_: {"columns": columns}, execute_select=execute))
        rule_id = registered(svc.storage, spec, sql)
        task = svc.start_task(user(), {"rule_ids": [rule_id], "report_period": "2026-09-30"})

    page = svc.list_task_issues(user(), task["id"])
    assert page["total"] == 1
    payload = page["items"][0]["query_result"]
    assert payload["values"] == {
        "business_key": "000017", "project_code": "0098", "project_name": "合成项目甲", "data_date": "2026-09-30",
        "checked_value": 1.25, "violation_message": "金额异常", "issue_kind": "comparison",
    }
    assert {"name": "checked_value", "source_field": "amount", "label": "checked_value"} in payload["columns"]
    assert {"name": "business_key", "source_field": "contract_no", "label": "business_key"} in payload["columns"]


def test_task_detail_route_enforces_owner_and_view_results_and_handles_missing_batch():
    from auto_check.app.module_system.contracts import ModuleRequest
    from auto_check.app.module_system.permissions import default_permission_evaluator
    from auto_check.app.module_system.routing import ModuleRouter
    from auto_check.modules.data_validation.api import register_routes
    from auto_check.modules.data_validation.module import MANIFEST

    _, svc = service(metadata=Metadata())
    rule_id = registered(svc.storage, loan_definition(report_category="rare"), "SELECT project_code AS business_key FROM loan")
    task = svc.start_task(user(), {"rule_ids": [rule_id], "report_period": "2026-09-30"})
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: svc)

    def request(task_id, caller, permission):
        return router.dispatch(ModuleRequest(method="GET", path=f"{MANIFEST.api_prefix}/tasks/{task_id}",
                                             path_params={}, query={"report_category": "rare"}, body=None,
                                             current_user={**caller, "capabilities": [permission]}))

    success = request(task["id"], user(), "dv.view_results")
    assert success.status == 200 and success.body["data"]["rules"][0]["rule_id"] == rule_id
    assert request(task["id"], user(), "dv.view").status == 403
    assert request(task["id"], user("2", "admin"), "dv.view_results").status == 403
    assert request(10084, user(), "dv.view_results").status == 404


def test_snapshot_labels_ignore_new_source_catalog_and_doc_revisions():
    from auto_check.modules.data_validation.storage import TASK_RULES

    meta = Metadata()
    navigation = SimpleNamespace(list_report_processes=lambda: [SimpleNamespace(code="a", name="甲报送")])
    db, svc = service(metadata=meta, report_navigation=navigation)

    def publish(label):
        svc.storage.create_document(name="规则表", file_name="test", content_sha256=label, table_count=1,
                                    field_count=0, warnings=[], imported_by="1", tables=[dict(
                                        data_source_name="监管报表", table_name="loan", table_name_cn=label,
                                        sheet_name="甲报送_贷款")])

    publish("甲贷款旧表")
    rid = registered(svc.storage, loan_definition(report_category="a"), "SELECT project_code AS business_key FROM loan")
    task = svc.start_task(user(), {"rule_ids": [rid], "report_period": "2026-09-30"})
    publish("甲贷款新表")
    meta.sources = [SimpleNamespace(id="src", name="新数据源", dialect="mysql")]
    navigation.list_report_processes = lambda: [SimpleNamespace(code="a", name="新分类名称")]
    detail = svc.task_detail(user(), task["id"], {})["rules"][0]
    assert [detail[k] for k in ("source_name", "table_name_cn", "report_category_name")] == ["监管报表", "甲贷款旧表", "甲报送"]
    with db.begin() as conn:
        conn.execute(TASK_RULES.update().values(source_name=None, table_name_cn=None, report_category_name=None))
    old = svc.task_detail(user(), task["id"], {})["rules"][0]
    assert [old[k] for k in ("source_name", "table_name_cn", "report_category_name")] == ["", "", "a"]


def test_cancelled_slow_worker_cannot_publish_into_retried_generation():
    import threading
    from concurrent.futures import ThreadPoolExecutor
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]
    meta = Metadata()
    calls = []

    def controlled(*args, **kwargs):
        i = len(calls)
        calls.append(i)
        entered[i].set()
        assert release[i].wait(10)
        return SimpleNamespace(columns=["business_key"], rows=[("first" if i == 0 else "retry",)], truncated=False)

    meta.execute_select = controlled
    _, svc = service(metadata=meta)
    rid = registered(svc.storage, loan_definition(), "SELECT project_code AS business_key FROM loan")
    v = svc.storage.latest_version(rid)
    task = svc.storage.create_task(creator_user_id="1", source_id="src", report_period="2026-09-30", params={}, rules=[
        dict(rule_id=rid, version_id=v["id"], version_no=1, content_sha256=v["content_sha256"], sql_summary="")])
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(svc._run_task, task["id"])
        try:
            assert entered[0].wait(3)
            svc.cancel_task(user(), task["id"])
            second = pool.submit(svc.retry_failed, user(), task["id"])
            assert entered[1].wait(3)
            release[0].set()
            first.result(timeout=3)
            assert svc.list_task_issues(user(), task["id"])["total"] == 0
            release[1].set()
            second.result(timeout=3)
        finally:
            for latch in release:
                latch.set()
    page = svc.list_task_issues(user(), task["id"])
    assert [row["query_result"]["values"]["business_key"] for row in page["items"]] == ["retry"]


def test_late_cancel_after_completion_preserves_final_task_state():
    _, svc = service(metadata=Metadata())
    rid = registered(svc.storage, loan_definition(), "SELECT project_code AS business_key FROM loan")
    task = svc.start_task(user(), {"rule_ids": [rid], "report_period": "2026-09-30"})
    assert svc.cancel_task(user(), task["id"])["status"] == "completed"


@pytest.mark.parametrize("selection", [[], [1, 1], list(range(1, 100002)), [0], [-1], [1.5], [True], ["1x"], "12", [1, "01"]])
def test_task_rejects_invalid_selection_before_any_admission(selection):
    _, svc = service(metadata=Metadata())
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        svc.start_task(user(), {"rule_ids": selection, "report_period": "2026-09-30"})
    assert svc.storage.list_tasks("1") == []


@pytest.mark.parametrize("budget", ["bytes", "cells"])
def test_wide_exports_stop_before_global_budget_and_report_truncation(monkeypatch, budget):
    from auto_check.modules.data_validation import exports

    _, svc = service(metadata=Metadata())
    rid = registered(svc.storage, loan_definition(), "SELECT project_code AS business_key FROM loan")
    task = svc.start_task(user(), {"rule_ids": [rid], "report_period": "2026-09-30"})
    for n in range(20):
        key = f"column_{n}"
        result = {"columns": [{"name": key, "label": key}], "values": {key: "测试" * 60}}
        svc.storage.add_issue(task_id=task["id"], rule_id=rid, version_no=1, business_key=str(n),
                              message="", query_result_json=json.dumps(result))
    if budget == "bytes":
        monkeypatch.setattr(exports, "MAX_EXPORT_BYTES", 2000, raising=False)
    else:
        monkeypatch.setattr(exports, "MAX_EXPORT_CELLS", 80, raising=False)
    product = svc.export_issues(user(), task["id"], "csv")
    rows = list(csv.DictReader(io.StringIO(product["content"].decode())))
    assert product["truncated"] and 0 < len(rows) < 20
    assert rows[0]["truncated"] == "true" and len(rows) == len(product["issues"])
    if budget == "bytes":
        assert len(product["content"]) <= 2000
    else:
        assert (1 + len(rows)) * len(rows[0]) <= 80
