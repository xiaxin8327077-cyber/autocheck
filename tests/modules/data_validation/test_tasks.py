import json

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.exports import rule_pack
from tests.modules.data_validation.support import Metadata, loan_definition, service, user


def _enable(rules, owner, definition=None):
    saved = rules.save_draft(owner, definition or loan_definition())
    version = rules.storage.latest_version(saved["id"])
    rules.run_tests(owner, saved["id"], 1)
    rules.confirm_rule(owner, saved["id"], 1, version["content_sha256"])
    return rules.storage.get_rule(saved["id"]), rules.storage.get_version(saved["id"], 1)


def test_task_snapshots_rule_hash() -> None:
    metadata = Metadata()
    _database, rules = service(metadata=metadata)
    owner = user()
    rule, version = _enable(rules, owner)
    response = rules.start_task(owner, {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-09-30"})
    assert response["status"] in {"queued", "running"}
    stored = rules.storage.task_rules(response["id"])[0]
    assert stored["content_sha256"] == version["content_sha256"]
    rules.save_draft(owner, loan_definition(violation_message="变更"), rule["id"])
    latest = rules.storage.latest_version(rule["id"])
    rules.run_tests(owner, rule["id"], int(latest["version_no"]))
    rules.confirm_rule(owner, rule["id"], int(latest["version_no"]), latest["content_sha256"])
    assert rules.storage.task_rules(response["id"])[0]["content_sha256"] == version["content_sha256"]
    with pytest.raises(AppError):
        rules.start_task(owner, {"rule_ids": [rules.disable_rule(owner, rule["id"])["id"]]})


def test_source_failure_is_not_pass() -> None:
    _database, rules = service(metadata=Metadata(error=ConnectionError("down")))
    owner = user()
    rule, _version = _enable(rules, owner)
    response = rules.start_task(owner, {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-09-30"})
    stored = rules.storage.task_rules(response["id"])[0]
    task = rules.storage.get_task(response["id"])
    assert stored["status"] == "ERROR"
    assert stored["error_code"] == "SOURCE_UNAVAILABLE"
    assert stored["status"] != "PASS"
    assert task["status"] in {"failed", "partial_failed"}

    _database, rules = service(metadata=Metadata(error=TimeoutError("slow")))
    rule, _version = _enable(rules, owner)
    response = rules.start_task(owner, {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-09-30"})
    stored = rules.storage.task_rules(response["id"])[0]
    assert stored["status"] == "TIMEOUT"
    assert stored["status"] != "PASS"


def test_retry_runs_only_failed_rules() -> None:
    metadata = Metadata()
    _database, rules = service(metadata=metadata)
    owner = user()
    first, _version = _enable(rules, owner, loan_definition(name="一"))
    second, _version = _enable(rules, owner, loan_definition(name="二"))
    third, _version = _enable(rules, owner, loan_definition(name="三"))
    response = rules.start_task(owner, {"rule_ids": [first["id"], second["id"], third["id"]], "source_id": "src", "report_period": "2026-09-30"})
    rows = rules.storage.task_rules(response["id"])
    rules.storage.update_task_rule(int(rows[2]["id"]), status="ERROR", error_code="SOURCE_UNAVAILABLE")
    before = len(metadata.calls)
    rules.retry_failed(owner, response["id"])
    assert len(metadata.calls) == before + 1


def test_truncated_issues_stay_marked() -> None:
    metadata = Metadata(rows=(("a",),), truncated=True)
    _database, rules = service(metadata=metadata)
    owner = user()
    rule, _version = _enable(rules, owner)
    response = rules.start_task(owner, {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-09-30"})
    exported = rules.export_issues(owner, response["id"], "csv")
    assert rules.storage.get_task(response["id"])["truncated"] == 1
    assert exported["truncated"] is True


def test_other_user_export_is_denied() -> None:
    _database, rules = service(metadata=Metadata())
    owner = user("1")
    rule, _version = _enable(rules, owner)
    response = rules.start_task(owner, {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-09-30"})
    with pytest.raises(AppError) as error:
        rules.export_issues(user("2"), response["id"], "csv")
    assert error.value.code == "FORBIDDEN"
    assert "business_key" not in json.dumps({"code": error.value.code})
    assert rules.storage.latest_audit(0)["action_code"] == "access_denied"


def test_cancel_running_task() -> None:
    _database, rules = service(metadata=Metadata())
    owner = user()
    first, _version = _enable(rules, owner, loan_definition(name="先"))
    second, _version = _enable(rules, owner, loan_definition(name="后"))
    rules.inline = False
    rules.gate = __import__("threading").Event()
    response = rules.start_task(owner, {"rule_ids": [first["id"], second["id"]], "source_id": "src", "report_period": "2026-09-30"})
    assert response["status"] in {"queued", "running"}
    rows = rules.storage.task_rules(response["id"])
    rules.storage.update_task_rule(int(rows[0]["id"]), status="PASS")
    rules.cancel_task(owner, response["id"])
    rows = rules.storage.task_rules(response["id"])
    assert rows[0]["status"] == "PASS"
    assert rows[1]["status"] == "CANCELLED"
    rules.gate.set()
    rules.join()


def test_rule_pack_round_trip_imports_as_draft() -> None:
    _database, rules = service(metadata=Metadata())
    owner = user()
    rule, version = _enable(rules, owner)
    packed = rules.export_rule_pack(owner, [rule["id"]])
    imported = rules.import_rule_pack(owner, packed)
    assert imported[0]["status"] == "draft"
    assert imported[0]["current_version_id"] is None
    assert imported[0]["id"] != rule["id"]
    bad = rule_pack([{"name": "坏", "definition": loan_definition(rule_type="custom_sql", dialect="mysql"), "sql_text": "DELETE FROM loan"}])
    with pytest.raises(AppError) as error:
        rules.import_rule_pack(owner, bad)
    assert error.value.code == "SQL_POLICY_DENIED"


def test_batch_run_previews_count_and_reports_conflicts() -> None:
    _database, rules = service(metadata=Metadata())
    owner = user()
    created = [_enable(rules, owner, loan_definition(name=str(index)))[0] for index in range(3)]
    ids = [rule["id"] for rule in created]
    assert rules.preview_batch(owner, ids)["count"] == 3
    rules.disable_rule(owner, ids[0])
    response = rules.start_task(owner, {"rule_ids": ids, "source_id": "src", "report_period": "2026-09-30"})
    assert len(rules.storage.task_rules(response["id"])) == 2
    assert response["skipped"][0]["rule_id"] == ids[0]
    assert response["skipped"][0]["reason"]


def test_same_period_keeps_each_execution() -> None:
    from tests.modules.data_validation.test_execution_result_details import ResultMetadata

    metadata = ResultMetadata(["贷款业务编号"], [("first",)])
    _database, rules = service(metadata=metadata)
    owner = user()
    rule, _version = _enable(rules, owner)
    payload = {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-09-30"}
    first = rules.start_task(owner, payload)
    metadata.values = [("second",)]
    second = rules.start_task(owner, payload)
    listed = rules.list_recent_tasks(owner, {"report_period": "2026-09-30"})
    other = rules.list_recent_tasks(owner, {"report_period": "2026-10-31"})
    assert [item["id"] for item in listed] == [second["id"], first["id"]]
    assert [item["run_no"] for item in listed] == [2, 1]
    assert other == []
    assert rules.storage.list_issues(first["id"])["items"][0]["business_key"] == "first"
    assert rules.storage.get_task(first["id"])["report_period"] == "2026-09-30"
    assert rules.storage.get_task(second["id"])["report_period"] == "2026-09-30"


def test_issue_page_does_not_read_the_whole_task() -> None:
    database, rules = service(metadata=Metadata())
    owner = user()
    rule, _version = _enable(rules, owner)
    response = rules.start_task(owner, {"rule_ids": [rule["id"]], "source_id": "src", "report_period": "2026-09-30"})
    for index in range(60):
        rules.storage.add_issue(task_id=response["id"], rule_id=rule["id"], version_no=1, business_key=f"K{index}", message="异常")
    database.sql.clear()
    page = rules.list_task_issues(owner, response["id"], {"page": 2, "page_size": 20})
    assert page["total"] == 60
    assert len(page["items"]) == 20
    assert page["page"] == 2
    listed = [sql for sql in database.sql if "data_validation_issues" in sql and "ORDER BY" in sql.upper()]
    assert listed and "LIMIT" in listed[-1].upper()
