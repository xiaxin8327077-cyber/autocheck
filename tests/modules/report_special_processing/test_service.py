from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import json
import pytest


NOW = datetime(2026, 8, 2, 10, 20, tzinfo=ZoneInfo("Asia/Shanghai"))


class User:
    def __init__(self, user_id, username, display_name, role="user"):
        self.id = user_id
        self.username = username
        self.display_name = display_name
        self.active = True
        self.role = role


class Directory:
    def __init__(self):
        self.users = {
            "1": User("1", "creator", "创建人"),
            "2": User("2", "handler", "处理人"),
            "9": User("9", "admin", "管理员", role="admin"),
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
    def __init__(self):
        self.records = {}
        self.audits = []
        self.attachments = []
        self.calls = []
        self.create_reports_args = []
        self._next_id = 1
        self._next_audit_id = 1
        self._next_attachment_id = 1

    def create(self, record, reports, processes, audit):
        self.calls.append("create")
        self.create_reports_args.append(list(reports))
        record_id = self._next_id
        self._next_id += 1
        value = {
            **record,
            "id": record_id,
            "record_no": "RSP-20260802-token",
            "row_version": 1,
            "reports": list(reports),
            "report_processes": [dict(item) for item in processes],
            "report_process_codes": [item["code"] for item in processes],
        }
        self.records[record_id] = value
        stored_audit = dict(audit)
        stored_audit["id"] = self._next_audit_id
        stored_audit["record_id"] = record_id
        self._next_audit_id += 1
        self.audits.append(stored_audit)
        return deepcopy(value)
    def get(self, record_id): return deepcopy(self.records.get(record_id))
    def list(self, query):
        items = [deepcopy(item) for item in self.records.values()]
        return {"items": items, "total": len(items), "page": 1, "page_size": 10}
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
        stored_audit = dict(audit)
        stored_audit["id"] = self._next_audit_id
        stored_audit["record_id"] = record_id
        self._next_audit_id += 1
        self.audits.append(stored_audit)
        return deepcopy(current)
    def update_status(self, record_id, row_version, changes, audit, attachments=()):
        current = self.records[record_id]
        from auto_check.modules.report_special_processing.contracts import VersionConflictError
        if current["row_version"] != row_version: raise VersionConflictError()
        current.update(changes)
        current["row_version"] += 1
        stored_audit = dict(audit)
        stored_audit["id"] = self._next_audit_id
        stored_audit["record_id"] = record_id
        self._next_audit_id += 1
        ids = []
        for sequence_no, item in enumerate(attachments, 1):
            attachment_id = self._next_attachment_id
            self._next_attachment_id += 1
            ids.append(attachment_id)
            content = bytes(item["content"])
            self.attachments.append({
                "id": attachment_id,
                "record_id": record_id,
                "audit_id": stored_audit["id"],
                "sequence_no": sequence_no,
                "content_type": item["content_type"],
                "content": content,
            })
        if ids:
            fields = json.loads(stored_audit["changed_fields_json"])
            fields["confirm_attachments"] = {"count": len(ids), "ids": ids}
            stored_audit["changed_fields_json"] = json.dumps(
                fields, ensure_ascii=False, separators=(",", ":")
            )
        self.audits.append(stored_audit)
        return deepcopy(current)

    def get_confirm_attachment(self, record_id, attachment_id):
        for item in self.attachments:
            if item["id"] == attachment_id and item["record_id"] == record_id:
                return dict(item)
        return None

    def delete_record(self, record_id, row_version):
        current = self.records.get(record_id)
        from auto_check.modules.report_special_processing.contracts import RecordNotFoundError, VersionConflictError
        if current is None:
            raise RecordNotFoundError()
        if current["row_version"] != row_version:
            raise VersionConflictError()
        del self.records[record_id]
        self.audits = [item for item in self.audits if item.get("record_id") != record_id]
        self.attachments = [item for item in self.attachments if item.get("record_id") != record_id]
        self.calls.append("delete")


def _service(reports=None, directory=None, role_label_resolver=None):
    from auto_check.modules.report_special_processing.service import SpecialProcessingService
    return SpecialProcessingService(
        MemoryStorage(),
        directory or Directory(),
        reports or Reports(),
        now=lambda: NOW,
        role_label_resolver=role_label_resolver,
    )


def _payload(save_mode="record", **updates):
    value = {
        "save_mode": save_mode,
        "report_process_code": "pbc",
        "reports": ["表一"],
        "summary": "摘要",
        "processing_content": "内容",
        "processing_script": "DROP TABLE x;",
        "report_period": "2026-07-31",
        "special_handling_at": "2026-08-01T15:32:18+08:00",
        "handler_user_id": "2",
        "dimension": "project",
        "governance_owner_user_id": "1",
        "table_name": "t_demo",
        "field_name": "amt",
        "value_before": "1",
        "value_after": "2",
    }
    value.update(updates)
    return value


def test_create_formal_record_snapshots_users_process_and_audits_without_script_text():
    service = _service()
    record = service.create(_payload(), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req")
    assert record["status"] == "pending"
    assert record["report_process_name_snapshot"] == "人行报送"
    assert record["handler_display_name_snapshot"] == "处理人"
    audit = service.storage.audits[0]
    assert "DROP TABLE" not in audit["changed_fields_json"]
    assert record["processing_script"] == "DROP TABLE x;"


def test_create_formal_record_persists_dimension_governance_fields_and_skips_reports():
    directory = Directory()
    directory.users["owner"] = User("owner", "gov_owner", "治理负责人甲", role="custom_pa")
    service = _service(directory=directory)
    record = service.create(
        _payload(governance_owner_user_id="owner"),
        {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"},
        request_id="req-dim",
    )
    assert record["status"] == "pending"
    assert record["dimension"] == "project"
    assert record["governance_owner_user_id"] == "owner"
    assert record["governance_owner_username_snapshot"] == "gov_owner"
    assert record["governance_owner_display_name_snapshot"] == "治理负责人甲"
    assert record["table_name"] == "t_demo"
    assert record["field_name"] == "amt"
    assert record["value_before"] == "1"
    assert record["value_after"] == "2"
    assert record["processing_content"] in {"", None}
    assert record["reports"] == []
    assert service.storage.create_reports_args == [[]]

    listed = service.list_records({}, {"id": "1", "role": "user", "capabilities": ["rsp.view"]})
    item = listed["items"][0]
    assert item["dimension"] == "project"
    assert item["governance_owner_display_name_snapshot"] == "治理负责人甲"
    assert item["table_name"] == "t_demo"
    assert item["field_name"] == "amt"


def test_confirm_denied_for_non_governance_owner_even_with_capability():
    from auto_check.modules.report_special_processing.contracts import PermissionDeniedError

    directory = Directory()
    directory.users["owner"] = User("owner", "gov_owner", "治理负责人甲", role="custom_pa")
    service = _service(directory=directory)
    record = service.create(
        _payload(governance_owner_user_id="owner"),
        {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"},
        request_id="req-create",
    )
    stranger = {
        "id": "1",
        "username": "creator",
        "role": "user",
        "capabilities": ["rsp.view", "rsp.edit", "rsp.confirm"],
    }
    with pytest.raises(PermissionDeniedError):
        service.change_status(
            record["id"],
            {"target_status": "completed", "row_version": record["row_version"]},
            stranger,
            request_id="req-deny",
        )
    completed = service.change_status(
        record["id"],
        {"target_status": "completed", "row_version": record["row_version"]},
        {"id": "owner", "role": "custom_pa", "capabilities": ["rsp.confirm"]},
        request_id="req-ok",
    )
    assert completed["status"] == "completed"


def test_draft_can_be_partial_but_completion_requires_complete_data():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    service = _service()
    draft = service.create(
        {
            "save_mode": "draft",
            "report_process_code": "pbc",
            "table_name": "t_draft",
            "field_name": "col_a",
        },
        {"id": "1", "username": "creator", "role": "user"},
        request_id="req",
    )
    with pytest.raises(ValidationError):
        service.change_status(draft["id"], {"target_status": "pending", "row_version": 1}, {"id": "1", "role": "user"}, request_id="req")


def test_resource_permission_status_machine_admin_void_reopen_and_optimistic_lock():
    from auto_check.modules.report_special_processing.contracts import PermissionDeniedError, VersionConflictError
    service = _service(); record = service.create(_payload(), {"id": "1", "username": "creator", "role": "user"}, request_id="req")
    with pytest.raises(PermissionDeniedError):
        service.update(record["id"], {**_payload(), "row_version": 1}, {"id": "9", "role": "user"}, request_id="req")
    # 谁创建谁处理：处理人无权改状态；创建人可推进，确认需 rsp.confirm（管理员）
    with pytest.raises(PermissionDeniedError):
        service.change_status(record["id"], {"target_status": "processing", "row_version": 1}, {"id": "2", "role": "user"}, request_id="req")
    processing = service.change_status(record["id"], {"target_status": "processing", "row_version": 1}, {"id": "1", "role": "user"}, request_id="req")
    with pytest.raises(VersionConflictError):
        service.change_status(record["id"], {"target_status": "completed", "row_version": 1}, {"id": "9", "role": "admin"}, request_id="req")
    completed = service.change_status(record["id"], {"target_status": "completed", "row_version": processing["row_version"]}, {"id": "9", "role": "admin"}, request_id="req")
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
        admin,
        request_id="req-complete",
    )
    assert service.storage.audits[-1]["action_summary"].splitlines() == [
        "完成记录：",
        "1.状态由待确认改为已完成",
    ]
    reopened = service.reopen(
        completed["id"],
        {"row_version": completed["row_version"], "reason": "补充"},
        admin,
        request_id="req-reopen",
    )
    assert service.storage.audits[-1]["action_summary"].splitlines() == [
        "重开记录：",
        "1.状态由已完成改为待确认",
        "2.重开原因：补充",
    ]
    service.void(
        reopened["id"],
        {"row_version": reopened["row_version"], "reason": "口径失效"},
        admin,
        request_id="req-void",
    )
    assert service.storage.audits[-1]["action_summary"].splitlines() == [
        "作废记录：",
        "1.状态由待确认改为已作废",
        "2.作废理由：口径失效",
    ]


def test_draft_create_and_update_audit_summary():
    service = _service()
    actor = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}
    draft = service.create(
        {
            "save_mode": "draft",
            "report_process_code": "pbc",
            "summary": "草稿摘要",
            "table_name": "t_draft",
            "field_name": "col_a",
        },
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
            "table_name": "t_draft",
            "field_name": "col_a",
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
        {
            "save_mode": "draft",
            "report_process_code": "pbc",
            "summary": "草稿",
            "table_name": "t_draft",
            "field_name": "col_a",
        },
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
    ]


def test_script_audit_preview_truncates_to_eight_lines_and_400_chars():
    from auto_check.modules.report_special_processing.service import (
        SCRIPT_AUDIT_PREVIEW_CHARS,
        SCRIPT_AUDIT_PREVIEW_LINES,
        SpecialProcessingService,
    )

    preview, truncated = SpecialProcessingService._script_audit_preview("select 1;")
    assert truncated is False
    assert preview == "select 1;"

    long_chars = "a" * (SCRIPT_AUDIT_PREVIEW_CHARS + 20)
    preview, truncated = SpecialProcessingService._script_audit_preview(long_chars)
    assert truncated is True
    assert preview == "a" * SCRIPT_AUDIT_PREVIEW_CHARS

    lines = [f"L{index}" for index in range(SCRIPT_AUDIT_PREVIEW_LINES + 1)]
    preview, truncated = SpecialProcessingService._script_audit_preview("\n".join(lines))
    assert truncated is True
    assert preview == "\n".join(lines[:SCRIPT_AUDIT_PREVIEW_LINES])
    assert f"L{SCRIPT_AUDIT_PREVIEW_LINES}" not in preview


def test_update_audit_stores_full_script_and_display_preview():
    import json
    from auto_check.modules.report_special_processing.service import SCRIPT_AUDIT_PREVIEW_CHARS

    service = _service()
    actor = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}
    created = service.create(_payload(processing_script="select 1;"), actor, request_id="req-create")
    marker = "UNIQUE_SCRIPT_TAIL"
    long_script = ("select col\n" * 20) + marker + ("x" * 80)
    service.update(
        created["id"],
        {**_payload(processing_script=long_script), "row_version": created["row_version"]},
        actor,
        request_id="req-script",
    )
    payload = json.loads(service.storage.audits[-1]["changed_fields_json"])
    script_meta = payload["processing_script"]
    assert script_meta["old"] == "select 1;"
    assert script_meta["new"] == long_script
    assert script_meta["old_preview"] == "select 1;"
    assert script_meta["old_truncated"] is False
    assert script_meta["new_truncated"] is True
    assert len(script_meta["new_preview"]) <= SCRIPT_AUDIT_PREVIEW_CHARS
    assert marker not in script_meta["new_preview"]
    assert marker in script_meta["new"]
    assert marker in long_script
    assert "处理脚本由" in service.storage.audits[-1]["action_summary"]


def test_detail_capabilities_match_frontend_resource_actions():
    service = _service()
    record = service.create(
        _payload(),
        {"id": "1", "username": "creator", "role": "user"},
        request_id="req",
    )

    assert service.get(record["id"], {"id": "1", "role": "user"})["can_edit"] is True
    assert service.get(record["id"], {"id": "2", "role": "user"})["can_edit"] is False  # 处理人不可单独编辑
    assert service.get(record["id"], {"id": "3", "role": "user"})["can_edit"] is False
    admin = service.get(record["id"], {"id": "9", "role": "admin"})
    assert admin["can_edit"] is True
    assert admin["can_confirm"] is True
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
        actor,
        request_id="req-status",
    )
    completed = service.change_status(
        processing["id"],
        {"target_status": "completed", "row_version": processing["row_version"]},
        admin,
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


def test_summary_exposes_distinct_record_total_for_all_tab():
    import inspect
    from auto_check.modules.report_special_processing.service import SpecialProcessingService

    source = inspect.getsource(SpecialProcessingService.summary)
    assert "record_total" in source
    assert "summary_for_report_period" in source


def test_admin_can_hard_delete_any_status_record():
    from auto_check.modules.report_special_processing.contracts import PermissionDeniedError

    service = _service()
    admin = {"id": "9", "username": "admin", "display_name": "管理员", "role": "admin"}
    user = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}
    created = service.create(_payload(), user, request_id="req-create")

    with pytest.raises(PermissionDeniedError):
        service.delete(created["id"], {"row_version": created["row_version"]}, user, request_id="req-deny")

    deleted = service.delete(
        created["id"],
        {"row_version": created["row_version"]},
        admin,
        request_id="req-delete",
    )
    assert deleted["deleted"] is True
    assert service.storage.get(created["id"]) is None
    assert "delete" in service.storage.calls


def test_catalog_governance_candidates_by_dimension_role_display_name():
    directory = Directory()
    directory.users = {
        "pa1": User("pa1", "gov_pa", "治理项目资产甲", role="custom_pa"),
        "pa2": User("pa2", "gov_pa2", "治理项目资产乙", role="custom_pa"),
        "ff1": User("ff1", "gov_ff", "治理资金财务甲", role="custom_ff"),
        "other": User("other", "plain", "普通用户", role="user"),
        "9": User("9", "admin", "管理员", role="admin"),
    }

    def role_label_resolver():
        return {
            "数据治理_项目资产": "custom_pa",
            "数据治理_资金财务": "custom_ff",
            "管理员": "admin",
            "普通用户": "user",
        }

    service = _service(directory=directory, role_label_resolver=role_label_resolver)
    catalog = service.catalog({"id": "9", "role": "admin", "capabilities": ["rsp.view", "rsp.confirm"]})

    assert catalog["dimensions"] == [
        {"code": "project", "label": "项目端"},
        {"code": "fund", "label": "资金端"},
        {"code": "asset", "label": "资产端"},
        {"code": "finance", "label": "财务端"},
    ]
    candidates = catalog["governance_owner_candidates_by_dimension"]
    project_ids = [item["id"] for item in candidates["project"]]
    asset_ids = [item["id"] for item in candidates["asset"]]
    fund_ids = [item["id"] for item in candidates["fund"]]
    finance_ids = [item["id"] for item in candidates["finance"]]
    assert project_ids == asset_ids == ["pa1", "pa2"]
    assert fund_ids == finance_ids == ["ff1"]
    assert catalog["capabilities"]["can_confirm"] is True

    empty_service = _service(
        directory=directory,
        role_label_resolver=lambda: {"管理员": "admin"},
    )
    empty_catalog = empty_service.catalog({"id": "1", "role": "user", "capabilities": ["rsp.view"]})
    empty_candidates = empty_catalog["governance_owner_candidates_by_dimension"]
    assert empty_candidates["project"] == []
    assert empty_candidates["asset"] == []
    assert empty_candidates["fund"] == []
    assert empty_candidates["finance"] == []
    assert empty_catalog["capabilities"]["can_confirm"] is False


class FakeNotificationPublisher:
    def __init__(self):
        self.requests = []

    def publish(self, request):
        self.requests.append(request)


def _requests_for(publisher, event_type):
    return [
        request
        for request in publisher.requests
        if request.event_type == event_type
    ]


@pytest.fixture
def service_with_publisher():
    from auto_check.modules.report_special_processing.service import SpecialProcessingService
    publisher = FakeNotificationPublisher()
    directory = Directory()
    directory.users["owner"] = User("owner", "gov_owner", "治理负责人甲", role="custom_pa")
    service = SpecialProcessingService(
        MemoryStorage(),
        directory,
        Reports(),
        now=lambda: NOW,
        notification_publisher=publisher,
    )
    return service, publisher


class TestNotificationTriggerMatrix:
    @pytest.mark.parametrize("operation", [
        "create_formal",
        "submit_draft",
        "reopen_completed",
    ])
    def test_new_pending_relationship_publishes_one_notification(self, operation, service_with_publisher):
        service, publisher = service_with_publisher
        if operation == "create_formal":
            record = service.create(_payload(governance_owner_user_id="owner"), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req-1")
        elif operation == "submit_draft":
            record = service.create(_payload(save_mode="draft", governance_owner_user_id="owner"), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req-1")
            assert len(publisher.requests) == 0  # draft save should not publish
            record = service.update(record["id"], _payload(save_mode="record", governance_owner_user_id="owner", row_version=1), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req-2")
        elif operation == "reopen_completed":
            record = service.create(_payload(governance_owner_user_id="owner"), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req-1")
            owner_actor = {"id": "owner", "username": "gov_owner", "display_name": "治理负责人甲", "role": "custom_pa", "capabilities": ["rsp.confirm"]}
            record = service.change_status(record["id"], {"target_status": "completed", "row_version": record["row_version"]}, owner_actor, request_id="req-2")
            record = service.reopen(record["id"], {"row_version": record["row_version"], "reason": "重开原因"}, {"id": "1", "username": "creator", "display_name": "创建人", "role": "user", "capabilities": ["rsp.reopen"]}, request_id="req-3")
        pending_requests = _requests_for(
            publisher,
            "pending_confirmation_created",
        )
        expected_pending_count = 2 if operation == "reopen_completed" else 1
        assert len(pending_requests) == expected_pending_count
        request = pending_requests[0]
        assert request.recipient_user_ids == ("owner",)
        assert request.category == "todo"
        assert request.level == "info"
        assert request.title == "有报表特殊处理请您确认"
        assert "治理负责人甲" in request.content or "项目端" in request.content

    def test_reassignment_publishes_notification(self, service_with_publisher):
        service, publisher = service_with_publisher
        directory = service._users
        directory.users["owner2"] = User("owner2", "gov_owner2", "治理负责人乙", role="custom_pa")
        record = service.create(_payload(governance_owner_user_id="owner"), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req-1")
        assert len(publisher.requests) == 1
        # Reassign to owner2
        updated = service.update(record["id"], _payload(governance_owner_user_id="owner2", row_version=1), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req-2")
        assert len(publisher.requests) == 2
        assert publisher.requests[1].recipient_user_ids == ("owner2",)

    @pytest.mark.parametrize("operation", [
        "save_draft",
        "void",
        "delete",
    ])
    def test_operations_without_notification_semantics_do_not_publish(self, operation, service_with_publisher):
        service, publisher = service_with_publisher
        actor = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user", "capabilities": ["rsp.create", "rsp.edit", "rsp.confirm", "rsp.void", "rsp.delete"]}
        record = service.create(_payload(governance_owner_user_id="owner"), actor, request_id="req-1")
        publisher.requests.clear()
        if operation == "save_draft":
            draft_record = service.create(_payload(save_mode="draft", governance_owner_user_id="owner"), actor, request_id="req-2")
            publisher.requests.clear()
            service.update(draft_record["id"], _payload(save_mode="draft", governance_owner_user_id="owner", row_version=1), actor, request_id="req-3")
        elif operation == "void":
            service.void(record["id"], {"reason": "测试作废", "row_version": record["row_version"]}, actor, request_id="req-2")
        elif operation == "delete":
            service.delete(record["id"], {"row_version": record["row_version"]}, actor, request_id="req-2")
        assert publisher.requests == []

    def test_publish_failure_does_not_break_business(self, service_with_publisher):
        service, publisher = service_with_publisher
        # Make the publisher raise an exception
        def failing_publish(request):
            raise RuntimeError("notification service unavailable")
        service._notifications = failing_publish
        # Business operation should still succeed
        record = service.create(_payload(governance_owner_user_id="owner"), {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}, request_id="req-1")
        assert record["status"] == "pending"

    def test_completion_notifies_creator_instead_of_selected_handler(
        self,
        service_with_publisher,
    ):
        service, publisher = service_with_publisher
        record = service.create(
            _payload(
                handler_user_id="2",
                governance_owner_user_id="owner",
            ),
            {
                "id": "1",
                "username": "creator",
                "display_name": "创建人",
                "role": "user",
            },
            request_id="req-create",
        )
        assert record["creator_user_id"] == "1"
        assert record["handler_user_id"] == "2"

        completed = service.change_status(
            record["id"],
            {
                "target_status": "completed",
                "row_version": record["row_version"],
            },
            {
                "id": "owner",
                "username": "gov_owner",
                "display_name": "治理负责人甲",
                "role": "custom_pa",
                "capabilities": ["rsp.confirm"],
            },
            request_id="req-complete",
        )

        requests = _requests_for(publisher, "confirmation_completed")
        assert len(requests) == 1
        request = requests[0]
        assert request.recipient_user_ids == ("1",)
        assert request.category == "task"
        assert request.level == "success"
        assert request.title == "您提交的报表特殊处理已完成确认"
        assert request.content == "项目端 · amt"
        assert request.dedupe_key == (
            f"rsp-completed:{completed['id']}:"
            f"{completed['row_version']}:1"
        )
        assert request.action.type == "navigate"
        assert request.action.route == "report-special-processing"
        assert request.action.query == {
            "record_id": str(completed["id"]),
            "highlight": "1",
            "period": "07-31",
        }
        assert "open" not in request.action.query

    def test_denied_or_conflicting_completion_does_not_publish(
        self,
        service_with_publisher,
    ):
        from auto_check.modules.report_special_processing.contracts import (
            PermissionDeniedError,
            VersionConflictError,
        )

        service, publisher = service_with_publisher
        record = service.create(
            _payload(governance_owner_user_id="owner"),
            {
                "id": "1",
                "username": "creator",
                "display_name": "创建人",
                "role": "user",
            },
            request_id="req-create",
        )
        publisher.requests.clear()

        with pytest.raises(PermissionDeniedError):
            service.change_status(
                record["id"],
                {
                    "target_status": "completed",
                    "row_version": record["row_version"],
                },
                {
                    "id": "2",
                    "role": "user",
                    "capabilities": ["rsp.confirm"],
                },
                request_id="req-denied",
            )
        assert _requests_for(publisher, "confirmation_completed") == []

        with pytest.raises(VersionConflictError):
            service.change_status(
                record["id"],
                {"target_status": "completed", "row_version": 999},
                {
                    "id": "owner",
                    "role": "custom_pa",
                    "capabilities": ["rsp.confirm"],
                },
                request_id="req-conflict",
            )
        assert _requests_for(publisher, "confirmation_completed") == []

    def test_completion_publish_failure_preserves_completed_business_result(
        self,
        service_with_publisher,
    ):
        class FailingPublisher:
            def publish(self, request):
                raise RuntimeError("notification service unavailable")

        service, publisher = service_with_publisher
        record = service.create(
            _payload(governance_owner_user_id="owner"),
            {
                "id": "1",
                "username": "creator",
                "display_name": "创建人",
                "role": "user",
            },
            request_id="req-create",
        )
        publisher.requests.clear()
        service._notifications = FailingPublisher()

        completed = service.change_status(
            record["id"],
            {
                "target_status": "completed",
                "row_version": record["row_version"],
            },
            {
                "id": "owner",
                "role": "custom_pa",
                "capabilities": ["rsp.confirm"],
            },
            request_id="req-complete",
        )

        assert completed["status"] == "completed"
        assert service.storage.get(record["id"])["status"] == "completed"

    def test_reopen_then_reconfirm_uses_new_completion_dedupe_key(
        self,
        service_with_publisher,
    ):
        service, publisher = service_with_publisher
        creator = {
            "id": "1",
            "username": "creator",
            "display_name": "创建人",
            "role": "user",
            "capabilities": ["rsp.create", "rsp.reopen"],
        }
        owner = {
            "id": "owner",
            "username": "gov_owner",
            "display_name": "治理负责人甲",
            "role": "custom_pa",
            "capabilities": ["rsp.confirm"],
        }
        record = service.create(
            _payload(governance_owner_user_id="owner"),
            creator,
            request_id="req-create",
        )
        first = service.change_status(
            record["id"],
            {
                "target_status": "completed",
                "row_version": record["row_version"],
            },
            owner,
            request_id="req-complete-1",
        )
        reopened = service.reopen(
            record["id"],
            {"row_version": first["row_version"], "reason": "补充口径"},
            creator,
            request_id="req-reopen",
        )
        second = service.change_status(
            record["id"],
            {
                "target_status": "completed",
                "row_version": reopened["row_version"],
            },
            owner,
            request_id="req-complete-2",
        )

        requests = _requests_for(publisher, "confirmation_completed")
        assert [request.dedupe_key for request in requests] == [
            f"rsp-completed:{first['id']}:{first['row_version']}:1",
            f"rsp-completed:{second['id']}:{second['row_version']}:1",
        ]
        assert requests[0].dedupe_key != requests[1].dedupe_key


PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPEG_TINY = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP_TINY = b"RIFF" + (12).to_bytes(4, "little") + b"WEBP" + b"VP8L" + b"\x00" * 4


def _b64_image(content, content_type="image/png"):
    import base64
    return {
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode("ascii"),
    }


def _complete_actor():
    return {"id": "9", "username": "admin", "display_name": "管理员", "role": "admin"}


def test_complete_without_note_or_images_omits_reason_and_attachments():
    service = _service()
    created = service.create(_payload(), {"id": "1", "username": "creator", "role": "user"}, request_id="req-create")
    completed = service.change_status(
        created["id"],
        {"target_status": "completed", "row_version": created["row_version"]},
        _complete_actor(),
        request_id="req-complete",
    )
    assert completed["status"] == "completed"
    fields = json.loads(service.storage.audits[-1]["changed_fields_json"])
    assert "reason" not in fields
    assert "confirm_attachments" not in fields
    assert service.storage.attachments == []
    assert service.storage.audits[-1]["action_summary"].splitlines() == [
        "完成记录：",
        "1.状态由待确认改为已完成",
    ]


def test_complete_with_note_stores_user_text_not_button_label():
    service = _service()
    created = service.create(_payload(), {"id": "1", "username": "creator", "role": "user"}, request_id="req-create")
    service.change_status(
        created["id"],
        {
            "target_status": "completed",
            "row_version": created["row_version"],
            "reason": "  源系统核对无误  ",
        },
        _complete_actor(),
        request_id="req-complete",
    )
    fields = json.loads(service.storage.audits[-1]["changed_fields_json"])
    assert fields["reason"]["new"] == "源系统核对无误"
    assert fields["reason"]["new"] != "源系统已确认"
    assert "确认说明" not in service.storage.audits[-1]["action_summary"]
    assert service.storage.attachments == []


def test_complete_with_one_to_three_images_persists_bytes_and_audit_ids():
    from auto_check.modules.report_special_processing.contracts import RecordNotFoundError

    service = _service()
    created = service.create(_payload(), {"id": "1", "username": "creator", "role": "user"}, request_id="req-create")
    images = [
        _b64_image(PNG_1x1, "image/png"),
        _b64_image(JPEG_TINY, "image/jpeg"),
        _b64_image(WEBP_TINY, "image/webp"),
    ]
    service.change_status(
        created["id"],
        {
            "target_status": "completed",
            "row_version": created["row_version"],
            "reason": "已贴图",
            "confirm_images": images,
        },
        _complete_actor(),
        request_id="req-complete",
    )
    fields = json.loads(service.storage.audits[-1]["changed_fields_json"])
    ids = fields["confirm_attachments"]["ids"]
    assert fields["confirm_attachments"]["count"] == 3
    assert ids == [item["id"] for item in service.storage.attachments]
    payloads = [PNG_1x1, JPEG_TINY, WEBP_TINY]
    types = ["image/png", "image/jpeg", "image/webp"]
    for attachment_id, expected, content_type in zip(ids, payloads, types):
        loaded = service.get_confirm_attachment(created["id"], attachment_id, _complete_actor())
        assert loaded["content"] == expected
        assert loaded["content_type"] == content_type
        assert expected not in service.storage.audits[-1]["changed_fields_json"].encode("utf-8")
    with pytest.raises(RecordNotFoundError):
        service.get_confirm_attachment(created["id"] + 99, ids[0], _complete_actor())


def test_complete_rejects_fourth_image_oversize_and_bad_magic():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service()
    actor = {"id": "1", "username": "creator", "role": "user"}
    admin = _complete_actor()

    created = service.create(_payload(), actor, request_id="req-1")
    with pytest.raises(ValidationError) as too_many:
        service.change_status(
            created["id"],
            {
                "target_status": "completed",
                "row_version": created["row_version"],
                "confirm_images": [_b64_image(PNG_1x1)] * 4,
            },
            admin,
            request_id="req-4",
        )
    assert "最多粘贴 3 张图片" in too_many.value.fields["confirm_images"]
    assert service.storage.get(created["id"])["status"] == "pending"
    assert service.storage.attachments == []

    created2 = service.create(_payload(), actor, request_id="req-2")
    oversize = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024 + 1)
    with pytest.raises(ValidationError) as large:
        service.change_status(
            created2["id"],
            {
                "target_status": "completed",
                "row_version": created2["row_version"],
                "confirm_images": [_b64_image(oversize)],
            },
            admin,
            request_id="req-big",
        )
    assert "2 MiB" in large.value.fields["confirm_images"]

    created3 = service.create(_payload(), actor, request_id="req-3")
    with pytest.raises(ValidationError) as magic:
        service.change_status(
            created3["id"],
            {
                "target_status": "completed",
                "row_version": created3["row_version"],
                "confirm_images": [_b64_image(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/svg+xml")],
            },
            admin,
            request_id="req-svg",
        )
    assert "PNG" in magic.value.fields["confirm_images"]
    assert service.storage.attachments == []


def test_delete_record_removes_confirm_attachments():
    service = _service()
    created = service.create(_payload(), {"id": "1", "username": "creator", "role": "user"}, request_id="req-create")
    completed = service.change_status(
        created["id"],
        {
            "target_status": "completed",
            "row_version": created["row_version"],
            "confirm_images": [_b64_image(PNG_1x1)],
        },
        _complete_actor(),
        request_id="req-complete",
    )
    assert service.storage.attachments
    service.delete(
        completed["id"],
        {"row_version": completed["row_version"]},
        _complete_actor(),
        request_id="req-delete",
    )
    assert service.storage.records == {}
    assert service.storage.audits == []
    assert service.storage.attachments == []


def test_reopen_then_reconfirm_keeps_old_and_new_attachment_sets():
    service = _service()
    admin = _complete_actor()
    created = service.create(_payload(), {"id": "1", "username": "creator", "role": "user"}, request_id="req-create")
    first = service.change_status(
        created["id"],
        {
            "target_status": "completed",
            "row_version": created["row_version"],
            "reason": "第一次确认",
            "confirm_images": [_b64_image(PNG_1x1)],
        },
        admin,
        request_id="req-1",
    )
    reopened = service.reopen(
        first["id"],
        {"row_version": first["row_version"], "reason": "补充口径"},
        admin,
        request_id="req-reopen",
    )
    service.change_status(
        reopened["id"],
        {
            "target_status": "completed",
            "row_version": reopened["row_version"],
            "reason": "第二次确认",
            "confirm_images": [_b64_image(JPEG_TINY, "image/jpeg"), _b64_image(PNG_1x1)],
        },
        admin,
        request_id="req-2",
    )
    complete_audits = [
        json.loads(item["changed_fields_json"])
        for item in service.storage.audits
        if item.get("to_status") == "completed"
    ]
    assert len(complete_audits) == 2
    assert complete_audits[0]["reason"]["new"] == "第一次确认"
    assert complete_audits[1]["reason"]["new"] == "第二次确认"
    assert complete_audits[0]["confirm_attachments"]["count"] == 1
    assert complete_audits[1]["confirm_attachments"]["count"] == 2
    assert complete_audits[0]["confirm_attachments"]["ids"] != complete_audits[1]["confirm_attachments"]["ids"]
    assert len(service.storage.attachments) == 3
