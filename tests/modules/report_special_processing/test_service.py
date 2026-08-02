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
    def list_report_processes(self):
        from auto_check.app.report_navigation_platform import ReportProcess
        return (ReportProcess("pbc", "人行报送", 10, True),)


class MemoryStorage:
    def __init__(self): self.records = {}; self.audits = []; self.calls = []
    def create(self, record, reports, audit):
        self.calls.append("create"); value = {**record, "id": 1, "record_no": "RSP-20260802-token", "row_version": 1, "reports": list(reports)}; self.records[1] = value; self.audits.append(audit); return deepcopy(value)
    def get(self, record_id): return deepcopy(self.records.get(record_id))
    def update(self, record_id, row_version, changes, reports, audit):
        current = self.records.get(record_id)
        if current is None: return None
        from auto_check.modules.report_special_processing.contracts import VersionConflictError
        if current["row_version"] != row_version: raise VersionConflictError()
        current.update(changes); current["reports"] = list(reports); current["row_version"] += 1; self.audits.append(audit); return deepcopy(current)
    def update_status(self, record_id, row_version, changes, audit):
        current = self.records[record_id]
        from auto_check.modules.report_special_processing.contracts import VersionConflictError
        if current["row_version"] != row_version: raise VersionConflictError()
        current.update(changes); current["row_version"] += 1; self.audits.append(audit); return deepcopy(current)


def _service():
    from auto_check.modules.report_special_processing.service import SpecialProcessingService
    return SpecialProcessingService(MemoryStorage(), Directory(), Reports(), now=lambda: NOW)


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
