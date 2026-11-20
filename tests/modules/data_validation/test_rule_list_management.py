from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, update

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import MANIFEST
from auto_check.modules.data_validation.service import DataValidationService
from auto_check.modules.data_validation.storage import METADATA, RULES, RuleStorage
from tests.modules.data_validation.support import Metadata, loan_definition, service, user


def test_delete_route_requires_manage_and_creator_and_records_one_history_event():
    _, rules = service()
    rule_id = rules.save_draft(user(), loan_definition())["id"]
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    path = f"{MANIFEST.api_prefix}/rules/{rule_id}"
    assert router.preflight("DELETE", path).max_body_bytes >= len(b"{}")

    def dispatch(method, actor, capabilities):
        return router.dispatch(ModuleRequest(
            method=method, path=path, path_params={},
            query={}, body=None, current_user={**actor, "capabilities": capabilities},
        ))

    assert dispatch("DELETE", user(), ["dv.view"]).status == 403
    missing = router.dispatch(ModuleRequest(method="DELETE", path=path + "000", path_params={},
                              query={}, body={}, current_user={**user(), "capabilities": ["dv.manage"]}))
    assert missing.status == 404
    assert dispatch("DELETE", user("2", "admin"), ["dv.manage"]).status == 403
    for _ in range(2):
        assert dispatch("DELETE", user(), ["dv.manage"]).body["data"]["status"] == "deleted"
    detail = dispatch("GET", user(), ["dv.view"])
    assert (detail.status, detail.body["error"]["code"]) == (409, "RULE_DELETED")
    events = rules.list_rule_history(user("2", "admin"), rule_id)["items"]
    assert [event["action_code"] for event in events] == ["delete", "create"]
    assert (events[0]["before_status"], events[0]["after_status"]) == ("draft", "deleted")
    with pytest.raises(AppError, match="FORBIDDEN"):
        rules.list_rule_history(user("2"), rule_id)


def test_deleted_rule_keeps_accepted_task_version_and_evidence_but_cannot_be_reused(monkeypatch):
    from tests.modules.data_validation.test_execution_result_details import ResultMetadata

    _, rules = service(metadata=ResultMetadata(["贷款业务编号", "异常说明"], [("loan-001", "贷款期限异常")]))
    owner = user()
    rule_id = rules.save_draft(owner, loan_definition())["id"]
    version = rules.storage.latest_version(rule_id)
    assert "AS `贷款业务编号`" in version["sql_text"] and "AS `异常说明`" in version["sql_text"]
    digest = version["content_sha256"]
    rules.run_tests(owner, rule_id, 1)
    rules.confirm_rule(owner, rule_id, 1, digest)
    cases = rules.storage.list_cases(rule_id, 1)
    payload = {"rule_ids": [rule_id], "source_id": "src", "report_period": "2026-11-01"}
    with monkeypatch.context() as patch:
        patch.setattr(rules, "_dispatch_execution", lambda task_id: None)
        task = rules.start_task(owner, payload)
    rules.delete_rule(owner, rule_id)
    for query in ({}, {"status": "deleted"}):
        assert rules.list_rules(owner, query)["total"] == 0
    stats = rules.rule_stats(owner)
    assert stats["total"] == stats["unclassified"]["total"] == 0
    for action in (
        lambda: rules.save_draft(owner, loan_definition(), rule_id),
        lambda: rules.disable_rule(owner, rule_id),
        lambda: rules.copy_rule(owner, rule_id),
        lambda: rules.run_tests(owner, rule_id, 1),
        lambda: rules.confirm_rule(owner, rule_id, 1, digest),
        lambda: rules.export_rule_pack(owner, [rule_id]),
        lambda: rules.start_task(owner, payload),
    ):
        with pytest.raises(AppError, match="RULE_DELETED"):
            action()
    assert rules.storage.list_cases(rule_id, 1) == cases
    rules._run_task(task["id"])
    snapshot = rules.storage.task_rules(task["id"])[0]
    assert (snapshot["content_sha256"], snapshot["status"]) == (digest, "VIOLATION")
    assert b"loan-001" in rules.export_issues(owner, task["id"], "csv")["content"]
    assert [e["action_code"] for e in rules.list_rule_history(owner, rule_id)["items"]] == ["delete", "confirm", "create"]


def test_write_transactions_reject_rule_deleted_after_service_precheck():
    database, rules = service()
    rule = rules.save_draft(user(), loan_definition())
    rid = rule["id"]
    with database.begin() as connection:
        connection.execute(update(RULES).where(RULES.c.id == rid).values(status="deleted"))
    for write in (
        lambda: rules.storage.set_status(rid, "enabled", rule["version_id"]),
        lambda: rules.storage.add_version(rid, loan_definition(), "", "", "hash"),
        lambda: rules.storage.replace_cases(rid, 1, []),
        lambda: rules.storage.invalidate_cases(rid, 1),
    ):
        with pytest.raises(AppError, match="RULE_DELETED"):
            write()
    assert rules.storage.latest_version(rid)["version_no"] == 1


def test_explicit_retry_rejects_deleted_failed_rule_before_retrying_any_snapshot():
    metadata = Metadata(error=ConnectionError("test"))
    _, rules = service(metadata=metadata)
    owner = user()
    ids = []
    for name in ("甲", "乙"):
        rule = rules.save_draft(owner, loan_definition(name=name))
        rules.storage.set_status(rule["id"], "enabled", rule["version_id"])
        ids.append(rule["id"])
    payload = {"rule_ids": ids, "source_id": "src", "report_period": "2026-11-01"}
    task_id = rules.start_task(owner, payload)["id"]
    failed = rules.storage.task_rules(task_id)
    assert [row["status"] for row in failed] == ["ERROR", "ERROR"]
    rules.delete_rule(owner, ids[-1])
    metadata.error = None
    metadata.calls.clear()
    with pytest.raises(AppError, match="RULE_DELETED"):
        rules.retry_failed(owner, task_id)
    assert not metadata.calls
    assert rules.storage.task_rules(task_id) == failed
    assert rules.storage.get_task(task_id)["status"] == "failed"


def test_retry_accepted_before_rule_deletion_can_publish_its_result(monkeypatch):
    metadata = Metadata(error=ConnectionError("test"))
    _, rules = service(metadata=metadata)
    owner = user()
    rule = rules.save_draft(owner, loan_definition())
    rules.storage.set_status(rule["id"], "enabled", rule["version_id"])
    task = rules.start_task(owner, {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-11-01"})
    execute = rules._execute_task_rule

    def after_admission(item):
        rules.delete_rule(owner, rule["id"])
        execute(item)

    monkeypatch.setattr(rules, "_execute_task_rule", after_admission)
    metadata.error = None
    assert rules.retry_failed(owner, task["id"])["status"] == "completed"
    assert rules.storage.task_rules(task["id"])[0]["status"] == "PASS"


def test_retry_without_claimed_snapshots_does_not_write_another_workers_task_status():
    metadata = Metadata(error=ConnectionError("test"))
    database, rules = service(metadata=metadata)
    owner = user()
    rule = rules.save_draft(owner, loan_definition())
    rules.storage.set_status(rule["id"], "enabled", rule["version_id"])
    task = rules.start_task(owner, {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-11-01"})
    claimed = rules.storage.claim_failed_task_rules(task["id"])
    rules.delete_rule(owner, rule["id"])
    metadata.error = None
    metadata.calls.clear()
    database.sql.clear()
    assert rules.retry_failed(owner, task["id"])["status"] == "running"
    assert not metadata.calls
    assert not any(sql.startswith("UPDATE data_validation_tasks") for sql in database.sql), "未领取快照的重试不能覆盖正在执行的任务状态"
    rules._execute_task_rule(claimed[0])
    assert rules._refresh_task_status(task["id"])["status"] == "completed"


def test_delete_and_audit_roll_back_together(monkeypatch):
    _, rules = service()
    rid = rules.save_draft(user(), loan_definition())["id"]

    def failed_audit(*args):
        raise RuntimeError("simulated audit failure")

    with monkeypatch.context() as patch:
        patch.setattr(rules.storage, "_write_history", failed_audit)
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            rules.delete_rule(user(), rid)
    assert rules.get_rule(user(), rid)["status"] == "draft"
    assert rules.list_rule_history(user(), rid)["total"] == 1


def test_task_waiting_for_deletion_sees_committed_status(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}")
    METADATA.create_all(engine)
    storage = RuleStorage(engine)
    rules = DataValidationService(storage)
    rid = rules.save_draft(user(), loan_definition())["id"]
    version = storage.latest_version(rid)
    storage.set_status(rid, "enabled", version["id"])
    selected = dict(rule_id=rid, version_id=version["id"], version_no=1,
                    content_sha256=version["content_sha256"], sql_summary="test")
    deleting, admitting, release = Event(), Event(), Event()

    @event.listens_for(engine, "before_cursor_execute")
    def hold_delete(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("INSERT INTO data_validation_audit_logs"):
            deleting.set()
            assert release.wait(5)
        elif statement == "BEGIN IMMEDIATE" and deleting.is_set():
            admitting.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            deletion = pool.submit(rules.delete_rule, user(), rid)
            try:
                assert deleting.wait(5)
                task = pool.submit(storage.create_task, creator_user_id="1", source_id="src",
                                   report_period="2026-11-01", params={}, rules=[selected])
                assert admitting.wait(5)
            finally:
                release.set()
            assert deletion.result()["status"] == "deleted"
            with pytest.raises(AppError, match="RULE_DELETED"):
                task.result()
        assert storage.list_tasks("1") == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("new_status", ["deleted", "disabled", "enabled"])
def test_task_admission_rechecks_status_and_current_version_before_writing(new_status):
    database, rules = service(metadata=Metadata())
    rid = rules.save_draft(user(), loan_definition())["id"]
    version = rules.storage.latest_version(rid)
    selected = dict(rule_id=rid, version_id=version["id"], version_no=1,
                    content_sha256=version["content_sha256"], sql_summary="test")
    with database.begin() as connection:
        connection.execute(update(RULES).where(RULES.c.id == rid).values(
            status=new_status, current_version_id=version["id"] + int(new_status == "enabled"),
        ))
    with pytest.raises(AppError, match="RULE_DELETED|CONFLICT_VERSION"):
        rules.storage.create_task(creator_user_id="1", source_id="src", report_period="2026-11-01",
                                  params={}, rules=[selected])
    assert rules.storage.list_tasks("1") == []


def test_list_uses_active_document_source_and_category_for_table_label_in_one_query():
    class Navigation:
        def list_report_processes(self):
            return [SimpleNamespace(code="a", name="甲报送"), SimpleNamespace(code="b", name="乙报送")]

    metadata = Metadata()
    database, rules = service(metadata=metadata, report_navigation=Navigation())
    for category in ("a", "b", ""):
        rules.save_draft(user(), loan_definition(report_category=category))
    rules.save_draft(user(), loan_definition(table_name="unknown"))

    def document(names):
        tables = [dict(data_source_name=source, table_name="loan", table_name_cn=label, sheet_name=sheet)
                  for source, sheet, label in names]
        return rules.storage.create_document(name="规则表", file_name="test", content_sha256="test",
                                             table_count=len(tables), field_count=0, warnings=[],
                                             imported_by="1", tables=tables)

    document([("监管报表", "甲报送_旧表", "旧表")])
    document([("监管报表", "甲报送_明细", "甲贷款明细"), ("监管报表", "乙报送_明细", "乙贷款明细"),
              ("监管报送集市", "甲报送_其他", "其他来源贷款")])
    database.sql.clear()
    items = rules.list_rules(user(), {})["items"]
    labels = {(item["table_name"], item["report_category"]): item["table_name_cn"] for item in items}
    assert labels == {("loan", "a"): "甲贷款明细", ("loan", "b"): "乙贷款明细", ("loan", ""): "",
                      ("unknown", ""): ""}
    assert sum("FROM data_validation_doc_tables" in sql for sql in database.sql) == 1
    assert not metadata.calls


def test_list_keeps_rules_visible_when_source_catalog_is_unavailable():
    class OfflineCatalog:
        def list_sources(self):
            raise RuntimeError("source registry unavailable")

    _, rules = service()
    rules.save_draft(user(), loan_definition())
    rules.storage.create_document(name="规则表", file_name="test", content_sha256="test", table_count=1,
                                  field_count=0, warnings=[], imported_by="1", tables=[{
                                      "data_source_name": "监管报表", "table_name": "loan", "table_name_cn": "贷款表",
                                  }])
    rules.metadata = OfflineCatalog()
    [item] = rules.list_rules(user(), {})["items"]
    assert (item["table_name"], item["table_name_cn"]) == ("loan", "")
