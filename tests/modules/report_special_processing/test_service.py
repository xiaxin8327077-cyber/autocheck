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
        self.record_attachments = []
        self.calls = []
        self.create_reports_args = []
        self.field_mappings = {}
        self._next_id = 1
        self._next_audit_id = 1
        self._next_attachment_id = 1
        self._next_record_attachment_id = 1

    def _new_record_attachment(self, record_id, item):
        att_id = self._next_record_attachment_id
        self._next_record_attachment_id += 1
        meta = {
            "id": att_id,
            "record_id": record_id,
            "file_name": item.file_name,
            "file_extension": item.file_extension,
            "content_type": item.content_type,
            "byte_size": item.byte_size,
            "content_sha256": item.content_sha256,
            "content": item.content,
            "created_by": {"user_id": "1", "username": "creator"},
            "created_at": NOW,
            "removed": False,
            "removed_at": None,
        }
        self.record_attachments.append(meta)
        return att_id

    @staticmethod
    def _public_attachment(meta):
        return {
            "id": meta["id"],
            "file_name": meta["file_name"],
            "file_extension": meta["file_extension"],
            "content_type": meta["content_type"],
            "byte_size": meta["byte_size"],
            "content_sha256": meta["content_sha256"],
            "created_by": meta["created_by"],
            "created_at": meta["created_at"],
            "removed": meta["removed_at"] is not None,
        }

    def list_field_mappings(self, datasource_id):
        wanted = str(datasource_id or "").strip()
        return [
            dict(value)
            for (ds, _schema, _table), value in self.field_mappings.items()
            if ds == wanted
        ]

    def get_field_mapping(self, datasource_id, schema_name, table_name):
        row = self.field_mappings.get((str(datasource_id or "").strip(), str(schema_name or "").strip(), str(table_name or "").strip()))
        return dict(row) if row is not None else None

    def upsert_field_mapping(self, datasource_id, schema_name, table_name, project_field, contract_field, *, user_id, username):
        key = (str(datasource_id or "").strip(), str(schema_name or "").strip(), str(table_name or "").strip())
        row = {
            "datasource_id": key[0],
            "schema": key[1],
            "table_name": key[2],
            "project_field": str(project_field or ""),
            "contract_field": str(contract_field or ""),
            "updated_by_username_snapshot": str(username or ""),
            "updated_at": NOW,
        }
        self.field_mappings[key] = row
        return dict(row)

    def create(self, record, reports, processes, audit, *, record_attachment_change=None, attachment_actor=None):
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
        attachment_ids = []
        if record_attachment_change is not None:
            for item in record_attachment_change.new_files:
                attachment_ids.append(self._new_record_attachment(record_id, item))
            fields = json.loads(audit["changed_fields_json"])
            fields["record_attachments"] = {"count": len(attachment_ids), "ids": attachment_ids}
            audit = dict(audit)
            audit["changed_fields_json"] = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
        value["record_attachments"] = [
            self._public_attachment(meta)
            for meta in self.record_attachments
            if meta["record_id"] == record_id and meta["removed_at"] is None
        ]
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
    def list_record_attachments(self, record_id, *, include_removed=False, attachment_ids=None):
        result = []
        wanted = set(attachment_ids) if attachment_ids is not None else None
        for meta in self.record_attachments:
            if meta["record_id"] != record_id:
                continue
            if wanted is not None:
                if meta["id"] not in wanted:
                    continue
            elif not include_removed and meta["removed_at"] is not None:
                continue
            result.append(self._public_attachment(meta))
        return result
    def get_record_attachment(self, record_id, attachment_id):
        for meta in self.record_attachments:
            if meta["record_id"] == record_id and meta["id"] == attachment_id:
                public = self._public_attachment(meta)
                public["content"] = meta["content"]
                return public
        return None
    def update(self, record_id, row_version, changes, reports, processes, audit, *, record_attachment_change=None, attachment_actor=None):
        current = self.records.get(record_id)
        if current is None: return None
        from auto_check.modules.report_special_processing.contracts import VersionConflictError
        if current["row_version"] != row_version: raise VersionConflictError()
        current.update(changes)
        current["reports"] = list(reports)
        current["report_processes"] = [dict(item) for item in processes]
        current["report_process_codes"] = [item["code"] for item in processes]
        current["row_version"] += 1
        if record_attachment_change is not None:
            current_atts = [
                meta for meta in self.record_attachments
                if meta["record_id"] == record_id and meta["removed_at"] is None
            ]
            current_ids = [meta["id"] for meta in current_atts]
            retained = set(record_attachment_change.retained_ids)
            removed_ids = [cid for cid in current_ids if cid not in retained]
            for meta in self.record_attachments:
                if meta["record_id"] == record_id and meta["id"] in removed_ids:
                    meta["removed_at"] = NOW
            added_ids = [
                self._new_record_attachment(record_id, item)
                for item in record_attachment_change.new_files
            ]
            if removed_ids or added_ids:
                new_ids = [cid for cid in current_ids if cid in retained] + added_ids
                fields = json.loads(audit["changed_fields_json"])
                fields["record_attachments"] = {
                    "changed": True,
                    "old_ids": current_ids,
                    "new_ids": new_ids,
                    "added_ids": added_ids,
                    "removed_ids": removed_ids,
                }
                audit = dict(audit)
                audit["changed_fields_json"] = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
        current["record_attachments"] = [
            self._public_attachment(meta)
            for meta in self.record_attachments
            if meta["record_id"] == record_id and meta["removed_at"] is None
        ]
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


class Dictionary:
    """platform.dictionary v1 测试替身：仅含一个启用业务系统。"""

    def __init__(self, items=None, disabled=()):
        from auto_check.app.platform_services import PublicDictionaryItem

        defaults = [PublicDictionaryItem(code="valuation", label="估值系统", sort_order=10)]
        self.items = list(items) if items is not None else defaults
        self.disabled = set(disabled)

    def list_active_items(self, dictionary_code):
        if dictionary_code != "business_system":
            return ()
        return tuple(item for item in self.items if item.code not in self.disabled)

    def get_active_item(self, dictionary_code, item_code):
        return next(
            (item for item in self.list_active_items(dictionary_code) if item.code == str(item_code)),
            None,
        )


def _service(reports=None, directory=None, role_label_resolver=None, dictionary=None, metadata=None):
    from auto_check.modules.report_special_processing.service import SpecialProcessingService
    return SpecialProcessingService(
        MemoryStorage(),
        directory or Directory(),
        reports or Reports(),
        now=lambda: NOW,
        role_label_resolver=role_label_resolver,
        dictionary_service=dictionary if dictionary is not None else Dictionary(),
        metadata_service=metadata,
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
        "business_system_code": "valuation",
        "governance_owner_user_id": "1",
        "table_name": "演示表｜t_demo",
        "field_name": "金额｜amt",
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
    assert record["table_name"] == "演示表｜t_demo"
    assert record["field_name"] == "金额｜amt"
    assert record["value_before"] == "1"
    assert record["value_after"] == "2"
    assert record["processing_content"] in {"", None}
    assert record["reports"] == []
    assert service.storage.create_reports_args == [[]]

    listed = service.list_records({}, {"id": "1", "role": "user", "capabilities": ["rsp.view"]})
    item = listed["items"][0]
    assert item["dimension"] == "project"
    assert item["governance_owner_display_name_snapshot"] == "治理负责人甲"
    assert item["table_name"] == "演示表｜t_demo"
    assert item["field_name"] == "金额｜amt"


def test_create_accepts_governance_owner_outside_dimension_candidates():
    directory = Directory()
    directory.users["outsider"] = User("outsider", "other", "其他用户", role="user")
    service = _service(directory=directory)
    record = service.create(
        _payload(governance_owner_user_id="outsider"),
        {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"},
        request_id="req-any-owner",
    )
    assert record["governance_owner_user_id"] == "outsider"
    assert record["governance_owner_display_name_snapshot"] == "其他用户"


def _png_bytes(marker: bytes = b"") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + marker


def _attachment_file(client_id: str, file_name: str, content: bytes) -> dict:
    return {
        "client_id": client_id,
        "file_name": file_name,
        "content_type": "image/png",
        "data_base64": _b64encode(content),
    }


def _b64encode(content: bytes) -> str:
    import base64

    return base64.b64encode(content).decode("ascii")


def _attachment_change(retained=None, files=None) -> dict:
    return {"record_attachments": {"retained_ids": retained or [], "new_files": files or []}}


def _create_user() -> dict:
    return {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}


def test_create_record_with_attachments_stores_metadata_and_audit_count():
    service = _service()
    payload = _payload(
        record_attachments={
            "retained_ids": [],
            "new_files": [
                _attachment_file("c1", "a.png", _png_bytes(b"one")),
                _attachment_file("c2", "b.png", _png_bytes(b"two")),
            ],
        }
    )
    record = service.create(payload, _create_user(), request_id="req-att")
    names = [item["file_name"] for item in record["record_attachments"]]
    assert names == ["a.png", "b.png"]
    assert all("content" not in item for item in record["record_attachments"])
    audit_fields = json.loads(service.storage.audits[0]["changed_fields_json"])
    assert audit_fields["record_attachments"]["count"] == 2


def test_create_omitting_attachments_has_none():
    service = _service()
    record = service.create(_payload(), _create_user(), request_id="req-noatt")
    assert record["record_attachments"] == []


def test_update_attachment_only_increments_version_and_writes_summary():
    service = _service()
    record = service.create(
        _payload(record_attachments={"retained_ids": [], "new_files": [_attachment_file("c1", "a.png", _png_bytes(b"one"))]}),
        _create_user(),
        request_id="req-1",
    )
    record_id = record["id"]
    existing_id = record["record_attachments"][0]["id"]
    updated = service.update(
        record_id,
        _payload(
            save_mode="record",
            row_version=record["row_version"],
            record_attachments={
                "retained_ids": [existing_id],
                "new_files": [_attachment_file("c2", "b.png", _png_bytes(b"two"))],
            },
        ),
        _create_user(),
        request_id="req-2",
    )
    assert updated["row_version"] == record["row_version"] + 1
    audit_fields = json.loads(service.storage.audits[-1]["changed_fields_json"])
    field = audit_fields["record_attachments"]
    assert field["old_ids"] == [existing_id]
    assert field["removed_ids"] == []
    assert len(field["added_ids"]) == 1
    assert service.storage.audits[-1]["action_summary"] == "修改附件（新增 1 个，移除 0 个）"


def test_update_rejects_retained_id_from_other_record_or_removed():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service()
    record = service.create(
        _payload(record_attachments={"retained_ids": [], "new_files": [_attachment_file("c1", "a.png", _png_bytes(b"one"))]}),
        _create_user(),
        request_id="req-1",
    )
    with pytest.raises(ValidationError):
        service.update(
            record["id"],
            _payload(row_version=record["row_version"], record_attachments={"retained_ids": [99999], "new_files": []}),
            _create_user(),
            request_id="req-2",
        )


def test_update_explicit_empty_set_clears_attachments():
    service = _service()
    record = service.create(
        _payload(record_attachments={"retained_ids": [], "new_files": [_attachment_file("c1", "a.png", _png_bytes(b"one"))]}),
        _create_user(),
        request_id="req-1",
    )
    updated = service.update(
        record["id"],
        _payload(row_version=record["row_version"], record_attachments={"retained_ids": [], "new_files": []}),
        _create_user(),
        request_id="req-2",
    )
    assert updated["record_attachments"] == []
    audit_fields = json.loads(service.storage.audits[-1]["changed_fields_json"])
    assert audit_fields["record_attachments"]["removed_ids"]


def test_update_rejects_duplicate_content_against_current_retained():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service()
    content = _png_bytes(b"same")
    record = service.create(
        _payload(record_attachments={"retained_ids": [], "new_files": [_attachment_file("c1", "a.png", content)]}),
        _create_user(),
        request_id="req-1",
    )
    existing_id = record["record_attachments"][0]["id"]
    with pytest.raises(ValidationError):
        service.update(
            record["id"],
            _payload(
                row_version=record["row_version"],
                record_attachments={
                    "retained_ids": [existing_id],
                    "new_files": [_attachment_file("c2", "dup.png", content)],
                },
            ),
            _create_user(),
            request_id="req-2",
        )


def test_get_record_attachment_reads_current_and_removed_but_not_cross_record():
    from auto_check.modules.report_special_processing.contracts import RecordNotFoundError

    service = _service()
    record = service.create(
        _payload(record_attachments={"retained_ids": [], "new_files": [_attachment_file("c1", "a.png", _png_bytes(b"one"))]}),
        _create_user(),
        request_id="req-1",
    )
    record_id = record["id"]
    attachment_id = record["record_attachments"][0]["id"]
    detail_user = {"id": "1", "role": "user", "capabilities": ["rsp.detail"]}
    item = service.get_record_attachment(record_id, attachment_id, detail_user)
    assert item["file_name"] == "a.png"
    assert item["content"] == _png_bytes(b"one")
    # 移除后仍可按历史 ID 读取。
    service.update(
        record_id,
        _payload(row_version=record["row_version"], record_attachments={"retained_ids": [], "new_files": []}),
        _create_user(),
        request_id="req-2",
    )
    removed_item = service.get_record_attachment(record_id, attachment_id, detail_user)
    assert removed_item["removed"] is True
    # 跨记录统一 not found。
    with pytest.raises(RecordNotFoundError):
        service.get_record_attachment(record_id, 99999, detail_user)


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
            "table_name": "草稿表｜t_draft",
            "field_name": "列A｜col_a",
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
            "table_name": "草稿表｜t_draft",
            "field_name": "列A｜col_a",
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
            "table_name": "草稿表｜t_draft",
            "field_name": "列A｜col_a",
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
            "table_name": "草稿表｜t_draft",
            "field_name": "列A｜col_a",
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
        dictionary_service=Dictionary(),
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
        assert request.content == "项目端 · 金额"
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


# ================= 业务系统字典与双语表字段（v1.2.14） =================

ACTOR = {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"}


class MultiDictionary(Dictionary):
    def __init__(self):
        from auto_check.app.platform_services import PublicDictionaryItem

        super().__init__(items=[
            PublicDictionaryItem(code="valuation", label="估值系统", sort_order=10),
            PublicDictionaryItem(code="ta", label="TA估值", sort_order=20),
        ], disabled={"off"})


def test_catalog_exposes_active_business_systems():
    service = _service(dictionary=MultiDictionary())
    catalog = service.catalog(ACTOR)
    assert catalog["business_systems"] == [
        {"code": "valuation", "name": "估值系统"},
        {"code": "ta", "name": "TA估值"},
    ]


def test_catalog_exposes_report_period_field_matchers_from_dictionary():
    from auto_check.app.platform_services import PublicDictionaryItem

    class ReportPeriodDictionary(MultiDictionary):
        def list_active_items(self, dictionary_code):
            if dictionary_code == "report_period_field":
                return (
                    PublicDictionaryItem(code="cldate", label="cldate", sort_order=10),
                    PublicDictionaryItem(code="caldate", label="caldate", sort_order=20),
                )
            return super().list_active_items(dictionary_code)

    catalog = _service(dictionary=ReportPeriodDictionary()).catalog(ACTOR)
    assert catalog["report_period_fields"] == [
        {"code": "cldate", "name": "cldate"},
        {"code": "caldate", "name": "caldate"},
    ]


def test_create_formal_requires_known_business_system():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary())
    with pytest.raises(ValidationError) as exc:
        service.create(_payload(business_system_code="ghost"), ACTOR, request_id="r1")
    assert "business_system_code" in exc.value.fields
    with pytest.raises(ValidationError):
        service.create(_payload(business_system_code="off"), ACTOR, request_id="r2")
    with pytest.raises(ValidationError):
        service.create(_payload(business_system_code=None), ACTOR, request_id="r3")


def test_create_draft_allows_empty_business_system_but_known_code_still_validated():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary())
    record = service.create(_payload(save_mode="draft", business_system_code=None), ACTOR, request_id="d1")
    assert record["business_system_code"] is None
    with pytest.raises(ValidationError):
        service.create(_payload(save_mode="draft", business_system_code="ghost"), ACTOR, request_id="d2")


def test_create_snapshots_business_system_name():
    service = _service(dictionary=MultiDictionary())
    record = service.create(_payload(business_system_code="ta"), ACTOR, request_id="s1")
    assert record["business_system_code"] == "ta"
    assert record["business_system_name_snapshot"] == "TA估值"
    listed = service.storage.records[record["id"]]
    assert listed["business_system_name_snapshot"] == "TA估值"


def test_create_enforces_bilingual_table_and_field():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary())
    with pytest.raises(ValidationError) as exc:
        service.create(_payload(table_name="legacy_table"), ACTOR, request_id="b1")
    assert "table_name" in exc.value.fields
    with pytest.raises(ValidationError) as exc:
        service.create(_payload(field_name="只有中文"), ACTOR, request_id="b2")
    assert "field_name" in exc.value.fields
    ok = service.create(
        _payload(table_name="资产表｜fa_balance；估值表｜valuation"),
        ACTOR,
        request_id="b3",
    )
    assert ok["table_name"] == "资产表｜fa_balance；估值表｜valuation"


def test_update_legacy_values_unchanged_allowed_but_modified_must_upgrade():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary())
    # 直接种入历史遗留记录（旧 create 不受双语约束），再验证编辑兼容规则
    legacy = service.create(_payload(save_mode="draft", table_name="资产表｜fa", field_name="金额｜amt"), ACTOR, request_id="l0")
    record_id = legacy["id"]
    service.storage.records[record_id]["table_name"] = "legacy_t"
    service.storage.records[record_id]["field_name"] = "legacy_f"
    row_version = legacy["row_version"]
    updated = service.update(
        record_id,
        {**_payload(save_mode="draft", table_name="legacy_t", field_name="legacy_f", summary="新摘要"), "row_version": row_version},
        ACTOR,
        request_id="l1",
    )
    assert updated["table_name"] == "legacy_t"
    with pytest.raises(ValidationError):
        service.update(
            record_id,
            {**_payload(save_mode="draft", table_name="changed_t", field_name="legacy_f"), "row_version": updated["row_version"]},
            ACTOR,
            request_id="l2",
        )


def test_update_keeps_disabled_business_system_when_unchanged():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary())
    created = service.create(_payload(business_system_code="ta"), ACTOR, request_id="o1")
    stored = service.storage.records[created["id"]]
    stored["business_system_code"] = "off"
    stored["business_system_name_snapshot"] = "历史停用项"
    updated = service.update(
        created["id"],
        {**_payload(business_system_code="off", summary="编辑其他"), "row_version": created["row_version"]},
        ACTOR,
        request_id="o2",
    )
    assert updated["business_system_code"] == "off"
    assert updated["business_system_name_snapshot"] == "历史停用项"
    with pytest.raises(ValidationError):
        service.update(
            created["id"],
            {**_payload(business_system_code="ghost"), "row_version": updated["row_version"]},
            ACTOR,
            request_id="o3",
        )


def test_create_field_group_alignment_with_tables():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary())
    # 分组字段串：第 N 组对应第 N 张表，允许空组
    ok = service.create(
        _payload(table_name="资产表｜fa；估值表｜va", field_name="金额｜amt；；汇率｜rate；利率｜ir"),
        ACTOR,
        request_id="g1",
    )
    assert ok["field_name"] == "金额｜amt；；汇率｜rate；利率｜ir"
    # 组数与表数不一致 → 拒绝
    with pytest.raises(ValidationError) as exc:
        service.create(
            _payload(table_name="资产表｜fa", field_name="金额｜amt；；汇率｜rate"),
            ACTOR,
            request_id="g2",
        )
    assert "field_name" in exc.value.fields
    # 表名非规范但字段用分组格式 → 要求先升级表名
    with pytest.raises(ValidationError) as exc:
        service.create(
            _payload(table_name="legacy_table", field_name="金额｜amt；；汇率｜rate"),
            ACTOR,
            request_id="g3",
        )
    assert "table_name" in exc.value.fields
    # 表名不允许使用分组分隔符
    with pytest.raises(ValidationError) as exc:
        service.create(
            _payload(table_name="资产表｜fa；；估值表｜va"),
            ACTOR,
            request_id="g4",
        )
    assert "table_name" in exc.value.fields
    # 所有分组均为空 → 字段名视为未填写
    with pytest.raises(ValidationError) as exc:
        service.create(
            _payload(table_name="资产表｜fa；估值表｜va", field_name="；；"),
            ACTOR,
            request_id="g5",
        )
    assert "field_name" in exc.value.fields


def test_update_table_count_change_realigns_grouped_fields():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary())
    created = service.create(
        _payload(table_name="资产表｜fa；估值表｜va", field_name="金额｜amt；；汇率｜rate"),
        ACTOR,
        request_id="g6",
    )
    # 仅修改表名导致分组数不一致 → 拒绝（字段名仍为分组格式）
    with pytest.raises(ValidationError) as exc:
        service.update(
            created["id"],
            {
                **_payload(table_name="资产表｜fa", field_name="金额｜amt；；汇率｜rate"),
                "row_version": created["row_version"],
            },
            ACTOR,
            request_id="g7",
        )
    assert "field_name" in exc.value.fields
    # 同步调整分组后可保存
    updated = service.update(
        created["id"],
        {
            **_payload(table_name="合并表｜fa_all", field_name="金额｜amt；汇率｜rate"),
            "row_version": created["row_version"],
        },
        ACTOR,
        request_id="g8",
    )
    assert updated["table_name"] == "合并表｜fa_all"
    assert updated["field_name"] == "金额｜amt；汇率｜rate"


# ===== 数据源 → 表 → 字段 → 修改前/后 结构化内容 =====

from types import SimpleNamespace


def _structured_payload(**updates):
    value = {
        "datasource_id": "ds1",
        "datasource_type": "postgresql",
        "tables": [{
            "schema": "public",
            "table_name": "t_customer",
            "chinese_table_name": "客户信息表",
            "table_name_source": "DATABASE",
            "projects": ["金牛1号", "金牛2号"],
            "contracts": ["HT001"],
            "fields": [
                {"column_name": "customer_status", "chinese_column_name": "客户状态",
                 "column_name_source": "DATABASE", "value_before": "正常", "value_after": "冻结"},
                {"column_name": "customer_type", "chinese_column_name": "客户类型",
                 "column_name_source": "MANUAL", "value_before": "A", "value_after": "B"},
            ],
        }],
    }
    value.update(updates)
    return value


def test_field_mapping_upsert_list_and_get():
    service = _service(metadata=FakeMetadata())
    # 显式空 capabilities 的用户应被拒绝（绕过角色矩阵）
    from auto_check.modules.report_special_processing.contracts import PermissionDeniedError
    from auto_check.modules.report_special_processing.contracts import ValidationError
    with pytest.raises(PermissionDeniedError):
        service.list_field_mappings("ds1", {"id": "9", "role": "admin", "capabilities": []})
    result = service.upsert_field_mapping("ds1", {"schema": "public", "table_name": "t_customer", "project_field": "project_code", "contract_field": "contract_no"}, ACTOR)
    assert result["project_field"] == "project_code"
    assert result["contract_field"] == "contract_no"
    listed = service.list_field_mappings("ds1", ACTOR)["items"]
    assert any(item["table_name"] == "t_customer" for item in listed)
    # 覆盖更新
    service.upsert_field_mapping("ds1", {"schema": "public", "table_name": "t_customer", "project_field": "p_code"}, ACTOR)
    listed = service.list_field_mappings("ds1", ACTOR)["items"]
    item = next(item for item in listed if item["table_name"] == "t_customer")
    assert item["project_field"] == "p_code"
    assert item["contract_field"] == "", "覆盖更新为整体替换，未传字段清空"
    # 两个定位字段都为空不允许保存
    with pytest.raises(ValidationError):
        service.upsert_field_mapping("ds1", {"schema": "public", "table_name": "t_other"}, ACTOR)


def test_generate_script_success_with_mappings():
    service = _service(metadata=FakeMetadata())
    service.upsert_field_mapping("ds1", {"schema": "public", "table_name": "t_customer", "project_field": "project_code", "contract_field": "contract_no"}, ACTOR)
    result = service.generate_script({"structured_content": _structured_payload()}, ACTOR)
    script = result["script"]
    assert "UPDATE t_customer" in script
    assert "WHERE project_code IN ('金牛1号', '金牛2号')" in script
    assert "AND contract_no IN ('HT001')" in script
    assert "SET customer_status = '冻结'" in script
    assert "AND customer_status = '正常'" in script


def test_generate_script_rejects_missing_mapping():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    service = _service(metadata=FakeMetadata())
    with pytest.raises(ValidationError) as exc:
        service.generate_script({"structured_content": _structured_payload()}, ACTOR)
    message = exc.value.fields.get("processing_script", "")
    assert "未配置项目定位字段" in message
    # 只配置项目字段、未配置合同字段时，合同侧单独报错
    service.upsert_field_mapping(
        "ds1", {"schema": "public", "table_name": "t_customer", "project_field": "project_code"}, ACTOR,
    )
    with pytest.raises(ValidationError) as exc2:
        service.generate_script({"structured_content": _structured_payload()}, ACTOR)
    assert "未配置合同定位字段" in exc2.value.fields.get("processing_script", "")


def test_generate_script_rejects_missing_scope():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    service = _service(metadata=FakeMetadata())
    payload = _structured_payload(tables=[{
        "schema": "public",
        "table_name": "t_customer",
        "chinese_table_name": "客户信息表",
        "table_name_source": "MANUAL",
        "projects": [],
        "contracts": [],
        "fields": [{"column_name": "customer_status", "chinese_column_name": "客户状态",
                     "column_name_source": "MANUAL", "value_before": "正常", "value_after": "冻结"}],
    }])
    with pytest.raises(ValidationError) as exc:
        service.generate_script({"structured_content": payload}, ACTOR)
    assert "请填写项目或合同处理范围" in exc.value.fields.get("processing_script", "")


def test_generate_script_requires_structured_content():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    service = _service(metadata=FakeMetadata())
    with pytest.raises(ValidationError) as exc:
        service.generate_script({}, ACTOR)
    assert "structured_content" in exc.value.fields


class FakeMetadata:
    def __init__(self, entries=None):
        self.entries = entries if entries is not None else {
            "ds1": SimpleNamespace(name="TCMP生产库", config=SimpleNamespace(db_type="postgresql")),
        }
        self.table_calls = []
        self.column_calls = []

    def resolve(self, datasource_id):
        return self.entries.get(str(datasource_id))

    def list_datasources(self):
        return [{"id": key, "name": entry.name, "db_type": entry.config.db_type} for key, entry in self.entries.items()]

    def list_tables(self, datasource_id, *, keyword="", page=1, page_size=20):
        self.table_calls.append((datasource_id, keyword, page, page_size))
        return {"items": [{"table_name": "t_customer", "table_comment": "客户信息表", "schema": "public"}],
                "total": 1, "page": page, "page_size": page_size, "total_pages": 1, "schema": "public"}

    def list_columns(self, datasource_id, table_name, *, keyword="", page=1, page_size=50):
        self.column_calls.append((datasource_id, table_name, keyword, page, page_size))
        return {"items": [{"column_name": "customer_status", "column_comment": "客户状态", "data_type": "varchar"}],
                "total": 1, "page": page, "page_size": page_size, "total_pages": 1}


def test_create_structured_persists_content_and_derives_strings():
    metadata = FakeMetadata()
    service = _service(dictionary=MultiDictionary(), metadata=metadata)
    record = service.create(_payload(structured_content=_structured_payload()), ACTOR, request_id="s1")
    assert record["datasource_id"] == "ds1"
    assert record["datasource_name_snapshot"] == "TCMP生产库"
    assert record["datasource_type"] == "postgresql"
    assert record["table_name"] == "客户信息表｜t_customer"
    assert record["field_name"] == "客户状态｜customer_status；客户类型｜customer_type"
    assert record["value_before"] == "正常\nA"
    assert record["value_after"] == "冻结\nB"
    stored = service.storage.records[record["id"]]
    assert "customer_status" in stored["structured_content_json"]


def test_create_structured_pins_backend_datasource_type_over_client():
    metadata = FakeMetadata({
        "ds1": SimpleNamespace(name="核算库", config=SimpleNamespace(db_type="mysql")),
    })
    service = _service(dictionary=MultiDictionary(), metadata=metadata)
    record = service.create(
        _payload(structured_content=_structured_payload(datasource_type="postgresql")),
        ACTOR, request_id="s2",
    )
    assert record["datasource_type"] == "mysql"
    assert record["datasource_name_snapshot"] == "核算库"


def test_create_structured_rejects_unknown_datasource():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary(), metadata=FakeMetadata(entries={}))
    with pytest.raises(ValidationError) as exc:
        service.create(_payload(structured_content=_structured_payload()), ACTOR, request_id="s3")
    assert "datasource_id" in exc.value.fields


def test_create_structured_formal_requires_field_values():
    from auto_check.modules.report_special_processing.contracts import ValidationError

    service = _service(dictionary=MultiDictionary(), metadata=FakeMetadata())
    payload = _structured_payload()
    payload["tables"][0]["fields"][0]["value_before"] = ""
    with pytest.raises(ValidationError) as exc:
        service.create(_payload(structured_content=payload), ACTOR, request_id="s4")
    assert exc.value.fields["value_before"] == "客户状态：请输入修改前内容"
    # 草稿允许字段级修改前/后为空
    draft = service.create(
        _payload(save_mode="draft", structured_content=payload), ACTOR, request_id="s5",
    )
    assert draft["status"] == "draft"


def test_legacy_payload_still_uses_bilingual_strings():
    service = _service(dictionary=MultiDictionary(), metadata=FakeMetadata())
    record = service.create(
        _payload(table_name="资产表｜fa_balance", field_name="金额｜amt", value_before="1", value_after="2"),
        ACTOR, request_id="s6",
    )
    assert record.get("structured_content_json") is None
    assert record["datasource_id"] is None
    assert record["table_name"] == "资产表｜fa_balance"


def test_structured_update_roundtrip_echoes_content():
    service = _service(dictionary=MultiDictionary(), metadata=FakeMetadata())
    created = service.create(_payload(structured_content=_structured_payload()), ACTOR, request_id="s7")
    updated = service.update(
        created["id"],
        {
            **_payload(structured_content=_structured_payload(tables=[{
                "schema": "public",
                "table_name": "t_customer",
                "chinese_table_name": "客户主表",
                "table_name_source": "MANUAL",
                "projects": ["P1"],
                "fields": [{
                    "column_name": "customer_id", "chinese_column_name": "客户编号",
                    "column_name_source": "DATABASE", "value_before": "x", "value_after": "y",
                }],
            }])), "row_version": created["row_version"],
        },
        ACTOR, request_id="s8",
    )
    assert json.loads(updated["structured_content_json"])["tables"][0]["chinese_table_name"] == "客户主表"
    assert updated["table_name"] == "客户主表｜t_customer"
    audit = service.storage.audits[-1]
    changed = json.loads(audit["changed_fields_json"])
    assert "structured_content_json" not in changed
    assert changed["table_name"]["new"] == "客户主表｜t_customer"


def test_metadata_passthrough_and_query_limits():
    from auto_check.modules.report_special_processing.contracts import (
        PlatformUnavailableError,
        ValidationError,
    )

    service = _service(dictionary=MultiDictionary())
    with pytest.raises(PlatformUnavailableError):
        service.list_datasources()

    metadata = FakeMetadata()
    service = _service(dictionary=MultiDictionary(), metadata=metadata)
    assert service.list_datasources()["items"][0]["id"] == "ds1"
    result = service.list_datasource_tables("ds1", {"keyword": "客户", "page": "2", "page_size": "999"})
    assert metadata.table_calls == [("ds1", "客户", 2, 100)]
    assert result["items"][0]["table_name"] == "t_customer"
    columns = service.list_datasource_columns("ds1", "t_customer", {})
    assert metadata.column_calls == [("ds1", "t_customer", "", 1, 50)]
    assert columns["items"][0]["column_name"] == "customer_status"
    with pytest.raises(ValidationError):
        service.list_datasource_tables("ds1", {"page": "abc"})
