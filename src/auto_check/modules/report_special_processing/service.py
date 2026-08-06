from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from typing import Any, Mapping, Sequence

from .contracts import (
    InvalidTransitionError,
    PermissionDeniedError,
    PlatformUnavailableError,
    RecordNotFoundError,
    RecordStatus,
    STATUS_LABELS,
    ValidationError,
)
from .permissions import can_delete, can_edit, can_reopen, can_transition, can_void
from .statistics import status_metrics
from .export_workbook import MAX_EXPORT_ROWS, build_export_xlsx
from .validator import (
    MAX_REPORTS,
    MAX_SCRIPT_BYTES,
    validate_action,
    validate_page_query,
    validate_record_input,
)


_AUDIT_FIELD_LABELS = {
    "report_process_name_snapshot": "关联报送",
    "report_period": "所处报送期",
    "reports": "涉及报表",
    "summary": "处理摘要",
    "processing_content": "处理说明",
    "processing_script": "处理脚本",
    "special_handling_at": "特殊处理时间",
    "handler_display_name_snapshot": "处理人",
    "status": "状态",
    "void_reason": "作废理由",
}
_AUDIT_SKIP_KEYS = frozenset(
    {
        "updated_by_user_id",
        "updated_by_username_snapshot",
        "updated_at",
        "handler_user_id",
        "handler_username_snapshot",
        "report_process_code",
        "script_sha256",
        "completed_at",
        "voided_at",
        "voided_by_user_id",
        "void_reason",
        "creator_user_id",
        "creator_username_snapshot",
        "created_at",
        "workflow_status",
        "workflow_instance_id",
        "workflow_version",
        "row_version",
    }
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

    def list_records(
        self,
        query: Mapping[str, str],
        current_user: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.storage.list(validate_page_query(query))
        return {
            **result,
            "items": [
                self._with_capabilities(item, current_user)
                for item in result.get("items", [])
            ],
        }

    def export_records(self, query: Mapping[str, str]) -> tuple[str, bytes]:
        page_query = validate_page_query(
            {
                **dict(query),
                "page": "1",
                "page_size": "100",
                "sort": str(query.get("sort") or "special_handling_at_desc"),
            }
        )
        items = self.storage.list_for_export(page_query, limit=MAX_EXPORT_ROWS)
        if not items:
            raise ValidationError(message="无数据可导出")
        period = str(query.get("report_period") or "").strip() or "all"
        stamp = self._now().astimezone().strftime("%Y%m%d_%H%M%S")
        filename = f"报表特殊处理_{period}_{stamp}.xlsx"
        return filename, build_export_xlsx(items)

    def get(
        self,
        record_id: int,
        current_user: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._with_capabilities(self._record(record_id), current_user)

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
        processes = self._processes(value.report_process_codes)
        actor = self._user(current_user.get("id"))
        handler = self._user(value.handler_user_id) if value.handler_user_id else None
        now = self._now()
        status = RecordStatus.DRAFT if value.save_mode == "draft" else RecordStatus.PENDING
        record = self._record_values(value, processes, handler)
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
            "create",
            actor,
            now,
            None,
            status.value,
            {"created": True, "save_mode": value.save_mode},
            "保存草稿" if value.save_mode == "draft" else "创建特殊处理记录",
            request_id,
        )
        created = self.storage.create(record, value.reports, processes, audit)
        self._refresh_special_governance_stats()
        return created

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
        processes = self._processes(value.report_process_codes)
        handler = self._user(value.handler_user_id) if value.handler_user_id else None
        actor = self._user(current_user.get("id"))
        now = self._now()
        next_status = "pending" if current["status"] == "draft" and value.save_mode == "record" else current["status"]
        changes = self._record_values(value, processes, handler)
        changes.update(
            status=next_status,
            updated_by_user_id=actor.id,
            updated_by_username_snapshot=actor.username,
            updated_at=now,
        )
        changed = self._changed_fields(current, changes, value.processing_script, value.reports)
        draft_save = value.save_mode == "draft" or next_status == "draft"
        audit = self._audit(
            "update" if next_status == current["status"] else "status_change",
            actor,
            now,
            current["status"],
            next_status,
            changed,
            self._build_action_summary(
                "update" if next_status == current["status"] else "status_change",
                current["status"],
                next_status,
                changed,
                draft_save=draft_save,
            ),
            request_id,
        )
        updated = self.storage.update(
            record_id, value.row_version, changes, value.reports, processes, audit
        )
        self._refresh_special_governance_stats()
        return updated

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
            {"status": {"changed": True, "old": current["status"], "new": target}, **({"reason": {"present": True}} if reason else {})},
            self._build_action_summary(
                "status_change",
                current["status"],
                target,
                {"status": {"changed": True, "old": current["status"], "new": target}},
            ),
            request_id,
        )
        changed = self.storage.update_status(record_id, version, changes, audit)
        self._refresh_special_governance_stats()
        return changed

    def void(
        self, record_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        if not can_void(current_user):
            raise PermissionDeniedError()
        current = self._record(record_id)
        if current["status"] not in {"draft", "pending", "processing"}:
            raise InvalidTransitionError()
        version, reason = validate_action(payload, require_reason=True, reason_max_length=20)
        actor = self._user(current_user.get("id")); now = self._now()
        changes = {
            "status": "voided", "voided_at": now, "voided_by_user_id": actor.id,
            "void_reason": reason, "updated_by_user_id": actor.id,
            "updated_by_username_snapshot": actor.username, "updated_at": now,
        }
        changed = {
            "status": {"changed": True, "old": current["status"], "new": "voided"},
            "reason": {"present": True, "new": reason},
        }
        audit = self._audit(
            "void",
            actor,
            now,
            current["status"],
            "voided",
            changed,
            self._build_action_summary("void", current["status"], "voided", {
                "status": changed["status"],
                "void_reason": {"changed": True, "new": reason},
            }),
            request_id,
        )
        voided = self.storage.update_status(record_id, version, changes, audit)
        self._refresh_special_governance_stats()
        return voided

    def delete(
        self, record_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        if not can_delete(current_user):
            raise PermissionDeniedError()
        current = self._record(record_id)
        version, _reason = validate_action(payload, require_reason=False)
        self.storage.delete_record(record_id, version)
        self._refresh_special_governance_stats()
        return {"id": record_id, "deleted": True, "record_no": current.get("record_no")}

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
        audit = self._audit(
            "reopen",
            actor,
            now,
            current["status"],
            "pending",
            {
                "status": {"changed": True, "old": current["status"], "new": "pending"},
                "reason": {"present": True, "new": reason},
            },
            self._build_action_summary(
                "reopen",
                current["status"],
                "pending",
                {"status": {"changed": True, "old": current["status"], "new": "pending"}},
            ),
            request_id,
        )
        reopened = self.storage.update_status(record_id, version, changes, audit)
        self._refresh_special_governance_stats()
        return reopened

    def summary(self, query: Mapping[str, str]) -> dict[str, Any]:
        raw_period = query.get("report_period")
        try:
            period = date.fromisoformat(raw_period) if raw_period else self._now().date()
        except ValueError:
            raise ValidationError(fields={"report_period": "日期格式无效"}) from None
        counts, by_process, record_total = self.storage.summary_for_report_period(period)
        metrics = status_metrics(counts)
        return {
            "period": period.isoformat(),
            **metrics,
            "draft": int(counts.get("draft", 0)),
            "pending": int(counts.get("pending", 0)),
            "processing": int(counts.get("processing", 0)),
            "voided": int(counts.get("voided", 0)),
            "record_total": int(record_total),
            "by_report_process": by_process,
            "generated_at": self._now(),
        }

    def _record(self, record_id: int) -> dict[str, Any]:
        value = self.storage.get(record_id)
        if value is None:
            raise RecordNotFoundError()
        return value

    @staticmethod
    def _with_capabilities(
        record: Mapping[str, Any],
        current_user: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            **record,
            "can_edit": can_edit(current_user, record),
            "can_admin": str((current_user or {}).get("role") or "") == "admin",
        }

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
            raise ValidationError(fields={"report_process_codes": "关联报送无效"})
        return process

    def _processes(self, codes: tuple[str, ...]) -> tuple[dict[str, str], ...]:
        resolved = []
        for code in codes:
            process = self._process(code)
            resolved.append({"code": process.code, "name": process.name})
        return tuple(resolved)

    def _refresh_special_governance_stats(self) -> None:
        """Best-effort single-card refresh; never fail the business write."""
        refresh = getattr(self._reports, "refresh_card_provider", None)
        if not callable(refresh):
            return
        try:
            refresh(card_code="special_governance")
        except Exception:
            return

    @staticmethod
    def _record_values(value: Any, processes: Sequence[Mapping[str, str]] | tuple[dict[str, str], ...], handler: Any) -> dict[str, Any]:
        script = value.processing_script
        primary = processes[0]
        names = "；".join(item["name"] for item in processes)
        return {
            "report_process_code": primary["code"],
            "report_process_name_snapshot": names[:500],
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
    def _format_audit_value(value: Any, *, field: str | None = None) -> str:
        if value is None or value == "" or value == [] or value == ():
            return "（空）"
        if field == "status":
            return STATUS_LABELS.get(str(value), str(value))
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, datetime):
            text = value.isoformat()
            return text.replace("T", " ").replace("+08:00", "").strip()
        if isinstance(value, (list, tuple)):
            names = [str(item).strip() for item in value if str(item).strip()]
            separator = "；" if field == "report_process_name_snapshot" else "、"
            text = separator.join(names) if names else "（空）"
        else:
            text = str(value).strip() or "（空）"
        if len(text) > 40:
            return f"{text[:40]}…"
        return text

    @classmethod
    def _build_action_summary(
        cls,
        action: str,
        from_status: str | None,
        to_status: str | None,
        changed: Mapping[str, Any],
        *,
        draft_save: bool = False,
    ) -> str:
        parts: list[str] = []
        for key, meta in changed.items():
            label = _AUDIT_FIELD_LABELS.get(key)
            if not label or not isinstance(meta, Mapping):
                continue
            if key == "processing_script":
                old_chars = int(meta.get("old_chars") or 0)
                new_chars = int(meta.get("new_chars") or 0)
                parts.append(f"处理脚本由{old_chars}字改为{new_chars}字")
                continue
            if key == "void_reason":
                reason_text = cls._format_audit_value(meta.get("new"))
                if reason_text != "（空）":
                    parts.append(f"作废理由：{reason_text}")
                continue
            old_text = cls._format_audit_value(meta.get("old"), field=key)
            new_text = cls._format_audit_value(meta.get("new"), field=key)
            parts.append(f"{label}由{old_text}改为{new_text}")
        if (
            from_status
            and to_status
            and from_status != to_status
            and "status" not in changed
        ):
            parts.append(
                f"状态由{cls._format_audit_value(from_status, field='status')}"
                f"改为{cls._format_audit_value(to_status, field='status')}"
            )
        if parts:
            numbered = [f"{index}.{text}" for index, text in enumerate(parts, 1)]
            if action == "void" or to_status == "voided":
                header = "作废记录："
            elif action == "reopen":
                header = "重开记录："
            elif action == "status_change" and to_status == "completed":
                header = "完成记录："
            elif action == "status_change":
                header = "状态变更："
            elif action == "create":
                header = "创建记录："
            elif draft_save or to_status == "draft":
                header = "保存草稿："
            else:
                header = "更新记录："
            summary = header + "\n" + "\n".join(numbered)
            return summary[:1000]
        defaults = {
            "create": "创建特殊处理记录",
            "update": "更新特殊处理记录",
            "status_change": "变更处理状态",
            "void": "作废特殊处理记录",
            "reopen": "重开特殊处理记录",
        }
        if action == "create" and to_status == "draft":
            return "保存草稿"
        if draft_save or (action == "update" and to_status == "draft"):
            return "保存草稿"
        if action == "status_change" and to_status == "completed":
            return "完成特殊处理记录"
        if action == "status_change" and from_status and to_status:
            return (
                f"状态由{cls._format_audit_value(from_status, field='status')}"
                f"改为{cls._format_audit_value(to_status, field='status')}"
            )
        return defaults.get(action, "更新特殊处理记录")

    @staticmethod
    def _changed_fields(
        current: Mapping[str, Any],
        changes: Mapping[str, Any],
        script: str | None,
        reports: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in changes.items():
            if key in _AUDIT_SKIP_KEYS or key in {"processing_script", "script_sha256"}:
                continue
            if current.get(key) == value:
                continue
            if key not in _AUDIT_FIELD_LABELS:
                result[key] = {"changed": True}
                continue
            result[key] = {"changed": True, "old": current.get(key), "new": value}
        if reports is not None:
            old_reports = [str(item).strip() for item in (current.get("reports") or []) if str(item).strip()]
            new_reports = [str(item).strip() for item in reports if str(item).strip()]
            if old_reports != new_reports:
                result["reports"] = {"changed": True, "old": old_reports, "new": new_reports}
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
