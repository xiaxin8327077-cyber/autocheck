from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

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
    def __init__(self): self.records = {}; self.audits = []; self.calls = []; self.create_reports_args = []
    def create(self, record, reports, processes, audit):
        self.calls.append("create")
        self.create_reports_args.append(list(reports))
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
        self.audits.append(audit)
        return deepcopy(current)
    def update_status(self, record_id, row_version, changes, audit):
        current = self.records[record_id]
        from auto_check.modules.report_special_processing.contracts import VersionConflictError
        if current["row_version"] != row_version: raise VersionConflictError()
        current.update(changes); current["row_version"] += 1; self.audits.append(audit); return deepcopy(current)

    def delete_record(self, record_id, row_version):
        current = self.records.get(record_id)
        from auto_check.modules.report_special_processing.contracts import RecordNotFoundError, VersionConflictError
        if current is None:
            raise RecordNotFoundError()
        if current["row_version"] != row_version:
            raise VersionConflictError()
        del self.records[record_id]
        self.audits = [item for item in self.audits if item.get("record_id") != record_id]
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
