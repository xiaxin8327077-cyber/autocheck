from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from typing import Any, Mapping

from .contracts import (
    InvalidTransitionError,
    PermissionDeniedError,
    PlatformUnavailableError,
    RecordNotFoundError,
    RecordStatus,
    STATUS_LABELS,
    ValidationError,
)
from .permissions import can_edit, can_reopen, can_transition, can_void
from .statistics import status_metrics
from .validator import (
    MAX_REPORTS,
    MAX_SCRIPT_BYTES,
    validate_action,
    validate_page_query,
    validate_record_input,
)


class SpecialProcessingService:
    def __init__(self, storage: Any, user_directory: Any, report_navigation: Any, *, now: Any) -> None:
        self.storage = storage
        self._users = user_directory
        self._reports = report_navigation
        self._now = now

    def catalog(self) -> dict[str, Any]:
        try:
            processes = tuple(self._reports.list_report_processes())
            users = tuple(self._users.list_active_users())
        except Exception:
            raise PlatformUnavailableError() from None
        return {
            "report_processes": [
                {"code": item.code, "name": item.name, "order": item.order, "active": item.active}
                for item in processes
                if item.active
            ],
            "users": [
                {"id": item.id, "username": item.username, "display_name": item.display_name}
                for item in users
                if item.active
            ],
            "statuses": [
                {"code": status.value, "label": label}
                for status, label in STATUS_LABELS.items()
            ],
            "limits": {"max_reports": MAX_REPORTS, "max_script_bytes": MAX_SCRIPT_BYTES},
            "workflow": {"enabled": False, "status": "not_enabled"},
        }

    def list_records(self, query: Mapping[str, str]) -> dict[str, Any]:
        return self.storage.list(validate_page_query(query))

    def get(self, record_id: int) -> dict[str, Any]:
        return self._record(record_id)

    def audit(self, record_id: int, query: Mapping[str, str]) -> dict[str, Any]:
        self._record(record_id)
        return self.storage.audit(record_id, validate_page_query(query))

    def create(
        self,
        payload: Mapping[str, Any],
        current_user: Mapping[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        value = validate_record_input(payload)
        process = self._process(value.report_process_code)
        actor = self._user(current_user.get("id"))
        handler = self._user(value.handler_user_id) if value.handler_user_id else None
        now = self._now()
        status = RecordStatus.DRAFT if value.save_mode == "draft" else RecordStatus.PENDING
        record = self._record_values(value, process, handler)
        record.update(
            status=status.value,
            creator_user_id=actor.id,
            creator_username_snapshot=actor.username,
            created_at=now,
            updated_by_user_id=actor.id,
            updated_by_username_snapshot=actor.username,
            updated_at=now,
            completed_at=None,
            voided_at=None,
            voided_by_user_id=None,
            void_reason=None,
            workflow_status="not_enabled",
            workflow_instance_id=None,
            workflow_version=0,
            row_version=1,
        )
        audit = self._audit(
            "create", actor, now, None, status.value, {"created": True}, "创建特殊处理记录", request_id
        )
        return self.storage.create(record, value.reports, audit)

    def update(
        self,
        record_id: int,
        payload: Mapping[str, Any],
        current_user: Mapping[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        current = self._record(record_id)
        if not can_edit(current_user, current):
            raise PermissionDeniedError()
        value = validate_record_input(payload)
        if value.row_version is None:
            raise ValidationError(fields={"row_version": "不能为空"})
        if current["status"] != "draft" and value.save_mode != "record":
            raise InvalidTransitionError()
        process = self._process(value.report_process_code)
        handler = self._user(value.handler_user_id) if value.handler_user_id else None
        actor = self._user(current_user.get("id"))
        now = self._now()
        next_status = "pending" if current["status"] == "draft" and value.save_mode == "record" else current["status"]
        changes = self._record_values(value, process, handler)
        changes.update(
            status=next_status,
            updated_by_user_id=actor.id,
            updated_by_username_snapshot=actor.username,
            updated_at=now,
        )
        changed = self._changed_fields(current, changes, value.processing_script)
        audit = self._audit(
            "update" if next_status == current["status"] else "status_change",
            actor,
            now,
            current["status"],
            next_status,
            changed,
            "更新特殊处理记录",
            request_id,
        )
        return self.storage.update(record_id, value.row_version, changes, value.reports, audit)

    def change_status(
        self,
        record_id: int,
        payload: Mapping[str, Any],
        current_user: Mapping[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        current = self._record(record_id)
        if not can_edit(current_user, current):
            raise PermissionDeniedError()
        version, reason = validate_action(payload)
        target = payload.get("target_status")
        if not isinstance(target, str) or not can_transition(str(current["status"]), target):
            raise InvalidTransitionError()
        if target in {"pending", "completed"}:
            self._require_complete(current)
        actor = self._user(current_user.get("id"))
        now = self._now()
        changes: dict[str, Any] = {
            "status": target,
            "updated_by_user_id": actor.id,
            "updated_by_username_snapshot": actor.username,
            "updated_at": now,
        }
        if target == "completed":
            changes["completed_at"] = now
        audit = self._audit(
            "status_change", actor, now, current["status"], target,
            {"status": {"changed": True}, **({"reason": {"present": True}} if reason else {})},
            "变更处理状态", request_id,
        )
        return self.storage.update_status(record_id, version, changes, audit)

    def void(
        self, record_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        if not can_void(current_user):
            raise PermissionDeniedError()
        current = self._record(record_id)
        if current["status"] not in {"pending", "processing"}:
            raise InvalidTransitionError()
        version, reason = validate_action(payload, require_reason=True)
        actor = self._user(current_user.get("id")); now = self._now()
        changes = {
            "status": "voided", "voided_at": now, "voided_by_user_id": actor.id,
            "void_reason": reason, "updated_by_user_id": actor.id,
            "updated_by_username_snapshot": actor.username, "updated_at": now,
        }
        audit = self._audit("void", actor, now, current["status"], "voided", {"reason": {"present": True}}, "作废特殊处理记录", request_id)
        return self.storage.update_status(record_id, version, changes, audit)

    def reopen(
        self, record_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        if not can_reopen(current_user):
            raise PermissionDeniedError()
        current = self._record(record_id)
        if current["status"] not in {"completed", "voided"}:
            raise InvalidTransitionError()
        version, reason = validate_action(payload, require_reason=True)
        actor = self._user(current_user.get("id")); now = self._now()
        changes = {
            "status": "pending", "completed_at": None, "voided_at": None,
            "voided_by_user_id": None, "void_reason": None,
            "updated_by_user_id": actor.id, "updated_by_username_snapshot": actor.username,
            "updated_at": now,
        }
        audit = self._audit("reopen", actor, now, current["status"], "pending", {"reason": {"present": True}}, "重开特殊处理记录", request_id)
        return self.storage.update_status(record_id, version, changes, audit)

    def summary(self, query: Mapping[str, str]) -> dict[str, Any]:
        raw_period = query.get("report_period")
        try:
            period = date.fromisoformat(raw_period) if raw_period else self._now().date()
        except ValueError:
            raise ValidationError(fields={"report_period": "日期格式无效"}) from None
        counts, by_process = self.storage.summary_for_report_period(period)
        metrics = status_metrics(counts)
        return {
            "period": period.isoformat(),
            **metrics,
            "draft": int(counts.get("draft", 0)),
            "pending": int(counts.get("pending", 0)),
            "processing": int(counts.get("processing", 0)),
            "voided": int(counts.get("voided", 0)),
            "by_report_process": by_process,
            "generated_at": self._now(),
        }

    def _record(self, record_id: int) -> dict[str, Any]:
        value = self.storage.get(record_id)
        if value is None:
            raise RecordNotFoundError()
        return value

    def _user(self, user_id: Any) -> Any:
        if user_id in {None, ""}:
            raise ValidationError(fields={"handler_user_id": "用户不存在或已停用"})
        try:
            user = self._users.get_user(str(user_id))
        except Exception:
            raise PlatformUnavailableError() from None
        if user is None or not user.active:
            raise ValidationError(fields={"handler_user_id": "用户不存在或已停用"})
        return user

    def _process(self, code: str) -> Any:
        try:
            process = next(
                (item for item in self._reports.list_report_processes() if item.code == code and item.active),
                None,
            )
        except Exception:
            raise PlatformUnavailableError() from None
        if process is None:
            raise ValidationError(fields={"report_process_code": "关联报送无效"})
        return process

    @staticmethod
    def _record_values(value: Any, process: Any, handler: Any) -> dict[str, Any]:
        script = value.processing_script
        return {
            "report_process_code": process.code,
            "report_process_name_snapshot": process.name,
            "report_period": value.report_period,
            "summary": value.summary or None,
            "processing_content": value.processing_content or None,
            "processing_script": script,
            "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest() if script else None,
            "special_handling_at": value.special_handling_at,
            "handler_user_id": handler.id if handler else None,
            "handler_username_snapshot": handler.username if handler else None,
            "handler_display_name_snapshot": handler.display_name if handler else None,
        }

    @staticmethod
    def _require_complete(record: Mapping[str, Any]) -> None:
        required = (
            record.get("reports"), record.get("summary"), record.get("processing_content"),
            record.get("report_period"), record.get("special_handling_at"), record.get("handler_user_id"),
        )
        if any(value is None or value == "" or value == () or value == [] for value in required):
            raise ValidationError(message="完成或正式保存前必须补全必填字段")

    @staticmethod
    def _changed_fields(current: Mapping[str, Any], changes: Mapping[str, Any], script: str | None) -> dict[str, Any]:
        result = {
            key: {"changed": True}
            for key, value in changes.items()
            if key not in {"processing_script", "script_sha256"} and current.get(key) != value
        }
        if current.get("processing_script") != script:
            old_script = current.get("processing_script") or ""
            result["processing_script"] = {
                "changed": True,
                "old_sha256": current.get("script_sha256"),
                "new_sha256": changes.get("script_sha256"),
                "old_chars": len(old_script),
                "new_chars": len(script or ""),
            }
        return result

    @staticmethod
    def _audit(
        action: str, actor: Any, now: datetime, from_status: str | None, to_status: str | None,
        changed: Mapping[str, Any], summary: str, request_id: str,
    ) -> dict[str, Any]:
        return {
            "action_code": action,
            "operator_user_id": actor.id,
            "operator_username_snapshot": actor.username,
            "operator_display_name_snapshot": actor.display_name,
            "occurred_at": now,
            "from_status": from_status,
            "to_status": to_status,
            "changed_fields_json": json.dumps(changed, ensure_ascii=False, separators=(",", ":")),
            "action_summary": summary,
            "request_id": request_id,
        }
