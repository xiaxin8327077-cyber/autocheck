from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


NOW = datetime(2026, 8, 2, 10, 20, tzinfo=ZoneInfo("Asia/Shanghai"))


class User:
    def __init__(self, user_id, username, display_name):
        self.id, self.username, self.display_name, self.active = user_id, username, display_name, True


class Directory:
    def __init__(self):
        self.users = {
            "1": User("1", "creator", "创建人"),
            "2": User("2", "handler", "处理人"),
            "9": User("9", "admin", "管理员"),
        }
    def list_active_users(self): return tuple(self.users.values())
    def get_user(self, user_id): return self.users.get(str(user_id))


class Reports:
    def __init__(self):
        self.refresh_calls = []
        self.refresh_error = None

    def list_report_processes(self):
        from auto_check.app.report_navigation_platform import ReportProcess
        return (ReportProcess("pbc", "人行报送", 10, True),)

    def refresh_card_provider(self, *, card_code):
        self.refresh_calls.append(card_code)
        if self.refresh_error is not None:
            raise self.refresh_error
        return {"ok": True, "refreshed": True}


class MemoryStorage:
    def __init__(self): self.records = {}; self.audits = []; self.calls = []
    def create(self, record, reports, processes, audit):
        self.calls.append("create")
        value = {
            **record,
            "id": 1,
            "record_no": "RSP-20260802-token",
            "row_version": 1,
            "reports": list(reports),
            "report_processes": [dict(item) for item in processes],
            "report_process_codes": [item["code"] for item in processes],
        }
        self.records[1] = value
        self.audits.append(audit)
        return deepcopy(value)
    def get(self, record_id): return deepcopy(self.records.get(record_id))
    def update(self, record_id, row_version, changes, reports, processes, audit):
        current = self.records.get(record_id)
        if current is None: return None
        from auto_check.modules.report_special_processing.contracts import VersionConflictError
        if current["row_version"] != row_version: raise VersionConflictError()
        current.update(changes)
        current["reports"] = list(reports)
        current["report_processes"] = [dict(item) for item in processes]
        current["report_process_codes"] = [item["code"] for item in processes]
        current["row_version"] += 1
        self.audits.append(audit)
        return deepcopy(current)
    def update_status(self, record_id, row_version, changes, audit):
        current = self.records[record_id]
        from auto_check.modules.report_special_processing.contracts import VersionConflictError
        if current["row_version"] != row_version: raise VersionConflictError()
        current.update(changes); current["row_version"] += 1; self.audits.append(audit); return deepcopy(current)


def _service(reports=None):
    from auto_check.modules.report_special_processing.service import SpecialProcessingService
    return SpecialProcessingService(
        MemoryStorage(), Directory(), reports or Reports(), now=lambda: NOW
    )


def _payload(save_mode="record", **updates):
    value = {"save_mode": save_mode, "report_process_code": "pbc", "reports": ["表一"], "summary": "摘要", "processing_content": "内容", "processing_script": "DROP TABLE x;", "report_period": "2026-07-31", "special_handling_at": "2026-08-01T15:32:18+08:00", "handler_user_id": "2"}
    value.update(updates); return value


def test_create_formal_record_snapshots_users_process_and_audits_without_script_text():
    service = _service()
    record = service.create(_payload(), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req")
    assert record["status"] == "pending"
    assert record["report_process_name_snapshot"] == "人行报送"
    assert record["handler_display_name_snapshot"] == "处理人"
    audit = service.storage.audits[0]
    assert "DROP TABLE" not in audit["changed_fields_json"]
    assert record["processing_script"] == "DROP TABLE x;"


def test_draft_can_be_partial_but_completion_requires_complete_data():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    service = _service()
    draft = service.create({"save_mode": "draft", "report_process_code": "pbc"}, {"id": "1", "username": "creator", "role": "user"}, request_id="req")
    with pytest.raises(ValidationError):
        service.change_status(draft["id"], {"target_status": "pending", "row_version": 1}, {"id": "1", "role": "user"}, request_id="req")


def test_resource_permission_status_machine_admin_void_reopen_and_optimistic_lock():
    from auto_check.modules.report_special_processing.contracts import PermissionDeniedError, VersionConflictError
    service = _service(); record = service.create(_payload(), {"id": "1", "username": "creator", "role": "user"}, request_id="req")
    with pytest.raises(PermissionDeniedError):
        service.update(record["id"], {**_payload(), "row_version": 1}, {"id": "9", "role": "user"}, request_id="req")
    processing = service.change_status(record["id"], {"target_status": "processing", "row_version": 1}, {"id": "2", "role": "user"}, request_id="req")
    with pytest.raises(VersionConflictError):
        service.change_status(record["id"], {"target_status": "completed", "row_version": 1}, {"id": "1", "role": "user"}, request_id="req")
    completed = service.change_status(record["id"], {"target_status": "completed", "row_version": processing["row_version"]}, {"id": "1", "role": "user"}, request_id="req")
    reopened = service.reopen(record["id"], {"row_version": completed["row_version"], "reason": "补充口径"}, {"id": "9", "role": "admin"}, request_id="req")
    voided = service.void(record["id"], {"row_version": reopened["row_version"], "reason": "口径失效"}, {"id": "9", "role": "admin"}, request_id="req")
    assert (completed["status"], reopened["status"], voided["status"]) == ("completed", "pending", "voided")


def test_complete_and_void_write_explicit_audit_summaries():
    service = _service()
    actor = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}
    admin = {"id": "9", "username": "admin", "display_name": "管理员", "role": "admin"}
    created = service.create(_payload(), actor, request_id="req-create")
    completed = service.change_status(
        created["id"],
        {"target_status": "completed", "row_version": created["row_version"], "reason": "处理完成"},
        actor,
        request_id="req-complete",
    )
    assert service.storage.audits[-1]["action_summary"].splitlines() == [
        "完成记录：",
        "1.状态由待处理改为已完成",
    ]
    reopened = service.reopen(
        completed["id"],
        {"row_version": completed["row_version"], "reason": "补充"},
        admin,
        request_id="req-reopen",
    )
    service.void(
        reopened["id"],
        {"row_version": reopened["row_version"], "reason": "口径失效"},
        admin,
        request_id="req-void",
    )
    assert service.storage.audits[-1]["action_summary"].splitlines() == [
        "作废记录：",
        "1.状态由待处理改为已作废",
        "2.作废理由：口径失效",
    ]


def test_draft_create_and_update_audit_summary():
    service = _service()
    actor = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}
    draft = service.create(
        {"save_mode": "draft", "report_process_code": "pbc", "summary": "草稿摘要"},
        actor,
        request_id="req-draft",
    )
    assert service.storage.audits[-1]["action_summary"] == "保存草稿"
    service.update(
        draft["id"],
        {
            "save_mode": "draft",
            "report_process_code": "pbc",
            "row_version": draft["row_version"],
            "summary": "新草稿摘要",
        },
        actor,
        request_id="req-draft-update",
    )
    assert service.storage.audits[-1]["action_summary"].splitlines()[0] == "保存草稿："
    assert "处理摘要由草稿摘要改为新草稿摘要" in service.storage.audits[-1]["action_summary"]


def test_draft_can_be_voided_by_admin():
    service = _service()
    admin = {"id": "9", "username": "admin", "display_name": "管理员", "role": "admin"}
    draft = service.create(
        {"save_mode": "draft", "report_process_code": "pbc", "summary": "草稿"},
        {"id": "1", "username": "creator", "role": "user"},
        request_id="req-draft",
    )
    voided = service.void(
        draft["id"],
        {"row_version": draft["row_version"], "reason": "不再需要"},
        admin,
        request_id="req-void-draft",
    )
    assert voided["status"] == "voided"
    assert service.storage.audits[-1]["action_summary"].splitlines() == [
        "作废记录：",
        "1.状态由草稿改为已作废",
        "2.作废理由：不再需要",
    ]


def test_update_audit_summary_describes_field_changes():
    service = _service()
    actor = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}
    created = service.create(_payload(), actor, request_id="req-create")
    service.update(
        created["id"],
        {
            **_payload(),
            "row_version": created["row_version"],
            "summary": "新摘要",
            "processing_content": "新说明",
            "reports": ["表二", "表三"],
        },
        actor,
        request_id="req-update",
    )
    summary = service.storage.audits[-1]["action_summary"]
    assert summary.splitlines() == [
        "更新记录：",
        "1.处理摘要由摘要改为新摘要",
        "2.处理说明由内容改为新说明",
        "3.涉及报表由表一改为表二、表三",
    ]


def test_detail_capabilities_match_frontend_resource_actions():
    service = _service()
    record = service.create(
        _payload(),
        {"id": "1", "username": "creator", "role": "user"},
        request_id="req",
    )

    assert service.get(record["id"], {"id": "1", "role": "user"})["can_edit"] is True
    assert service.get(record["id"], {"id": "3", "role": "user"})["can_edit"] is False
    admin = service.get(record["id"], {"id": "9", "role": "admin"})
    assert admin["can_edit"] is True
    assert admin["can_admin"] is True


def test_writes_best_effort_refresh_owned_special_governance_card_only():
    reports = Reports()
    service = _service(reports)
    actor = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}
    admin = {"id": "9", "username": "admin", "display_name": "管理员", "role": "admin"}

    created = service.create(_payload(), actor, request_id="req-create")
    updated = service.update(
        created["id"], {**_payload(), "row_version": created["row_version"]}, actor, request_id="req-update"
    )
    processing = service.change_status(
        updated["id"],
        {"target_status": "processing", "row_version": updated["row_version"]},
        {"id": "2", "role": "user"},
        request_id="req-status",
    )
    completed = service.change_status(
        processing["id"],
        {"target_status": "completed", "row_version": processing["row_version"]},
        actor,
        request_id="req-complete",
    )
    reopened = service.reopen(
        completed["id"],
        {"row_version": completed["row_version"], "reason": "补充口径"},
        admin,
        request_id="req-reopen",
    )
    voided = service.void(
        reopened["id"],
        {"row_version": reopened["row_version"], "reason": "口径失效"},
        admin,
        request_id="req-void",
    )

    assert voided["status"] == "voided"
    assert reports.refresh_calls == ["special_governance"] * 6


def test_refresh_failure_does_not_roll_back_successful_write():
    reports = Reports()
    reports.refresh_error = RuntimeError("refresh unavailable")
    service = _service(reports)

    record = service.create(
        _payload(),
        {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"},
        request_id="req",
    )

    assert record["id"] == 1
    assert record["status"] == "pending"
    assert service.storage.get(1)["status"] == "pending"
    assert reports.refresh_calls == ["special_governance"]
