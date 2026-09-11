from __future__ import annotations

from dataclasses import replace as _dataclass_replace
from datetime import date, datetime
import hashlib
import json
import re
from typing import Any, Callable, Mapping, Sequence

from .contracts import (
    DIMENSION_LABELS,
    InvalidTransitionError,
    PermissionDeniedError,
    PlatformUnavailableError,
    RecordNotFoundError,
    RecordStatus,
    STATUS_LABELS,
    ValidationError,
)
from .permissions import (
    can_confirm,
    can_create,
    can_delete,
    can_edit,
    can_reopen,
    can_transition,
    can_void,
    can_view,
    user_has_capability,
    with_resolved_capabilities,
)
from .statistics import status_metrics
from .export_workbook import MAX_EXPORT_ROWS, build_export_xlsx
from .bilingual_names import (
    MAX_BILINGUAL_ITEMS,
    MAX_BILINGUAL_PART_LEN,
    MAX_BILINGUAL_TOTAL_LEN,
    BilingualNameError,
    BILINGUAL_GROUP_SEPARATOR,
    BILINGUAL_ITEM_SEPARATOR,
    BILINGUAL_PART_SEPARATOR,
    parse_bilingual_groups,
    parse_bilingual_items,
    serialize_bilingual_items,
)
from .display_summary import ownership_system_field_summary
from .structured_content import (
    StructuredContentError,
    SUPPORTED_DATASOURCE_TYPES,
    parse_structured_content,
)
from .audit_diff import build_structured_audit_diff
from .sql_builder import ScriptGenerationError, generate_script

_RE_PHYSICAL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]{0,127}$")
from .validator import (
    ALLOWED_ATTACHMENT_EXTENSIONS,
    MAX_RECORD_ATTACHMENTS,
    MAX_RECORD_ATTACHMENTS_TOTAL_BYTES,
    MAX_RECORD_ATTACHMENT_BYTES,
    MAX_REPORTS,
    MAX_SCRIPT_BYTES,
    validate_action,
    validate_confirm_images,
    validate_page_query,
    validate_record_attachment_change,
    validate_record_input,
)


_AUDIT_FIELD_LABELS = {
    "report_process_name_snapshot": "关联报送",
    "report_period": "所处报送期",
    "dimension": "所属维度",
    "business_system_name_snapshot": "所属业务系统",
    "datasource_name_snapshot": "数据源",
    "summary": "处理摘要",
    "table_name": "处理表名",
    "field_name": "处理字段名",
    "value_before": "修改前",
    "value_after": "修改后",
    "processing_script": "处理脚本",
    "special_handling_at": "特殊处理时间",
    "handler_display_name_snapshot": "处理人",
    "governance_owner_display_name_snapshot": "数据治理负责人",
    "status": "状态",
    "void_reason": "作废理由",
    "reopen_reason": "重开原因",
}
SCRIPT_AUDIT_PREVIEW_LINES = 8
SCRIPT_AUDIT_PREVIEW_CHARS = 400
_AUDIT_SKIP_KEYS = frozenset(
    {
        "updated_by_user_id",
        "updated_by_username_snapshot",
        "updated_at",
        "handler_user_id",
        "handler_username_snapshot",
        "report_process_code",
        "business_system_code",
        "datasource_id",
        "datasource_type",
        "structured_content_json",
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
_STRUCTURED_DERIVED_AUDIT_KEYS = frozenset({
    "datasource_name_snapshot", "table_name", "field_name", "value_before", "value_after",
})

_GOVERNANCE_ROLE_DISPLAY_PROJECT_ASSET = "数据治理_项目资产"
_GOVERNANCE_ROLE_DISPLAY_FUND_FINANCE = "数据治理_资金财务"
_DIMENSION_ORDER = ("project", "fund", "asset", "finance")


class SpecialProcessingService:
    def __init__(
        self,
        storage: Any,
        user_directory: Any,
        report_navigation: Any,
        *,
        now: Any,
        role_label_resolver: Callable[[], Mapping[str, str]] | None = None,
        notification_publisher: Any = None,
        dictionary_service: Any = None,
        metadata_service: Any = None,
    ) -> None:
        self.storage = storage
        self._users = user_directory
        self._reports = report_navigation
        self._now = now
        self._role_label_resolver = role_label_resolver
        self._notifications = notification_publisher
        self._dictionary = dictionary_service
        self._metadata = metadata_service

    def _actor(self, current_user: Mapping[str, Any] | None) -> dict[str, Any]:
        """模块内解析能力矩阵并补齐用户 capabilities，不改平台派发协议。"""
        matrix = None
        try:
            from auto_check.app.storage_role_capabilities import load_role_capability_matrix
            from auto_check.app.storage_role_definitions import load_custom_role_codes

            with self.storage.database.connect() as connection:
                custom_roles = load_custom_role_codes(connection)
                matrix = load_role_capability_matrix(connection, custom_roles=custom_roles)
        except Exception:
            matrix = None
        return with_resolved_capabilities(current_user, matrix)

    def catalog(self, current_user: Mapping[str, Any] | None = None) -> dict[str, Any]:
        actor = self._actor(current_user)
        try:
            processes = tuple(self._reports.list_report_processes())
            users = tuple(self._users.list_active_users())
        except Exception:
            raise PlatformUnavailableError() from None
        candidates_by_dimension = self._governance_owner_candidates_by_dimension(users)
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
            "dimensions": [
                {"code": code, "label": DIMENSION_LABELS[code]}
                for code in _DIMENSION_ORDER
            ],
            "business_systems": [
                {"code": item.code, "name": item.label}
                for item in self._active_business_system_items()
            ],
            "report_period_fields": [
                {"code": item.code, "name": item.label}
                for item in self._active_report_period_field_items()
            ],
            "governance_owner_candidates_by_dimension": candidates_by_dimension,
            "statuses": [
                {"code": status.value, "label": label}
                for status, label in STATUS_LABELS.items()
            ],
            "limits": {
                "max_reports": MAX_REPORTS,
                "max_script_bytes": MAX_SCRIPT_BYTES,
                "record_attachments": {
                    "max_count": MAX_RECORD_ATTACHMENTS,
                    "max_file_bytes": MAX_RECORD_ATTACHMENT_BYTES,
                    "max_total_bytes": MAX_RECORD_ATTACHMENTS_TOTAL_BYTES,
                    "allowed_extensions": list(ALLOWED_ATTACHMENT_EXTENSIONS),
                },
            },
            "workflow": {"enabled": False, "status": "not_enabled"},
            "capabilities": {
                "can_view": can_view(actor),
                "can_create": can_create(actor),
                "can_confirm": user_has_capability(actor, "rsp.confirm"),
                "can_delete": can_delete(actor),
            },
        }

    def _active_business_system_items(self) -> tuple[Any, ...]:
        return self._active_dictionary_items("business_system")

    def _active_report_period_field_items(self) -> tuple[Any, ...]:
        return self._active_dictionary_items("report_period_field")

    def _active_dictionary_items(self, dictionary_code: str) -> tuple[Any, ...]:
        if self._dictionary is None:
            return ()
        try:
            return tuple(self._dictionary.list_active_items(dictionary_code))
        except Exception:
            return ()

    def _resolve_business_system(
        self, code: Any, current: Mapping[str, Any] | None
    ) -> tuple[str | None, str | None]:
        """解析所属业务系统代码并返回 (代码, 名称快照)。

        创建新选必须是当前启用项；编辑时保持原代码不变则沿用当前名称快照（
        已停用项仍可读）；改选或新建必须命中启用项。
        """
        clean = str(code or "").strip()
        if not clean:
            return (None, None)
        current_code = str((current or {}).get("business_system_code") or "").strip()
        if current is not None and clean == current_code:
            return (clean, (current or {}).get("business_system_name_snapshot"))
        if self._dictionary is None:
            raise ValidationError(fields={"business_system_code": "业务系统字典服务暂不可用"})
        try:
            item = self._dictionary.get_active_item("business_system", clean)
        except Exception:
            raise PlatformUnavailableError() from None
        if item is None:
            raise ValidationError(fields={"business_system_code": "所属业务系统无效或已停用，请重新选择"})
        return (item.code, item.label)

    @staticmethod
    def _require_canonical_bilingual(field: str, label: str, value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        try:
            if field == "field_name":
                # 字段名支持分组格式（；；分隔，组对应处理表）；无分隔符时即旧版单组规范串。
                parse_bilingual_groups(text)
            else:
                if BILINGUAL_GROUP_SEPARATOR in text:
                    raise BilingualNameError("处理表名不支持分组分隔符“；；”")
                parse_bilingual_items(text)
        except ValueError as exc:
            raise ValidationError(fields={field: f"{label}：{exc}"}) from None

    @staticmethod
    def _enforce_field_group_alignment(value: Any) -> None:
        """分组字段串必须与处理表数量一一对应。"""
        field_value = str(getattr(value, "field_name") or "").strip()
        if BILINGUAL_GROUP_SEPARATOR not in field_value:
            return
        table_value = str(getattr(value, "table_name") or "").strip()
        try:
            tables = parse_bilingual_items(table_value)
        except ValueError as exc:
            raise ValidationError(fields={
                "table_name": f"处理表名：保存关联字段前需先按“中文｜英文”规范格式补全（{exc}）",
            }) from None
        groups = parse_bilingual_groups(field_value)
        if len(groups) != len(tables):
            raise ValidationError(fields={
                "field_name": f"处理字段名：字段分组数（{len(groups)}）必须与处理表数（{len(tables)}）一致",
            })

    def _enforce_bilingual_fields(
        self, value: Any, current: Mapping[str, Any] | None
    ) -> None:
        """新建记录强制双语规范串；编辑时未改动的旧值可保留，一旦修改必须升级格式。"""
        for field, label in (("table_name", "处理表名"), ("field_name", "处理字段名")):
            submitted = str(getattr(value, field) or "").strip()
            if current is not None:
                previous = str(current.get(field) or "").strip()
                if submitted == previous:
                    continue
            self._require_canonical_bilingual(field, label, submitted)
        # 分组一致性：只要字段名为分组格式就校验（含表名被单独修改的情况）。
        if BILINGUAL_GROUP_SEPARATOR in str(getattr(value, "field_name") or ""):
            self._enforce_field_group_alignment(value)

    def _role_display_name_to_code(self) -> dict[str, str]:
        resolver = self._role_label_resolver
        if resolver is None:
            return {}
        try:
            raw = resolver()
        except Exception:
            return {}
        mapping: dict[str, str] = {}
        for display_name, role_code in dict(raw or {}).items():
            label = str(display_name or "").strip()
            code = str(role_code or "").strip()
            if label and code:
                mapping[label] = code
        return mapping

    def _governance_owner_candidates_by_dimension(
        self,
        users: Sequence[Any],
    ) -> dict[str, list[dict[str, str]]]:
        label_to_code = self._role_display_name_to_code()
        project_asset_code = label_to_code.get(_GOVERNANCE_ROLE_DISPLAY_PROJECT_ASSET)
        fund_finance_code = label_to_code.get(_GOVERNANCE_ROLE_DISPLAY_FUND_FINANCE)

        def _users_for_role(role_code: str | None) -> list[dict[str, str]]:
            if not role_code:
                return []
            return [
                {
                    "id": str(item.id),
                    "username": str(item.username),
                    "display_name": str(item.display_name),
                }
                for item in users
                if bool(getattr(item, "active", False))
                and str(getattr(item, "role", "") or "") == role_code
            ]

        project_asset_users = _users_for_role(project_asset_code)
        fund_finance_users = _users_for_role(fund_finance_code)
        return {
            "project": list(project_asset_users),
            "asset": list(project_asset_users),
            "fund": list(fund_finance_users),
            "finance": list(fund_finance_users),
        }

    def list_records(
        self,
        query: Mapping[str, str],
        current_user: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        actor = self._actor(current_user)
        if not can_view(actor):
            raise PermissionDeniedError()
        result = self.storage.list(validate_page_query(query))
        return {
            **result,
            "items": [
                self._with_capabilities(item, actor)
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
        return self._with_capabilities(self._record(record_id), self._actor(current_user))

    def get_confirm_attachment(
        self,
        record_id: int,
        attachment_id: int,
        current_user: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.get(record_id, current_user)
        item = self.storage.get_confirm_attachment(record_id, attachment_id)
        if item is None:
            raise RecordNotFoundError()
        content = item.get("content")
        content_type = str(item.get("content_type") or "")
        if not isinstance(content, (bytes, bytearray)) or not content_type:
            raise RecordNotFoundError()
        return {"content": bytes(content), "content_type": content_type}

    def get_record_attachment(
        self,
        record_id: int,
        attachment_id: int,
        current_user: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 先校验记录详情权限；跨记录或历史附件统一 not found，不泄露存在性。
        self.get(record_id, current_user)
        item = self.storage.get_record_attachment(record_id, attachment_id)
        if item is None:
            raise RecordNotFoundError()
        return item

    def _validated_record_attachment_change(
        self,
        payload: Mapping[str, Any],
        *,
        creating: bool,
        current: Sequence[Mapping[str, Any]] = (),
    ) -> Any:
        change = validate_record_attachment_change(payload, creating=creating)
        if change is None:
            return None
        current_ids = {int(item["id"]) for item in current}
        if not creating:
            for retained_id in change.retained_ids:
                if retained_id not in current_ids:
                    raise ValidationError(fields={"record_attachments": "附件引用无效"})
        current_by_id = {int(item["id"]): item for item in current}
        retained_bytes = sum(
            int(current_by_id[retained_id].get("byte_size") or 0)
            for retained_id in change.retained_ids

        )
        new_bytes = sum(item.byte_size for item in change.new_files)
        if retained_bytes + new_bytes > MAX_RECORD_ATTACHMENTS_TOTAL_BYTES:
            raise ValidationError(fields={"record_attachments": "附件总大小超过 30 MiB"})
        seen_hashes = {
            str(item.get("content_sha256"))
            for item in current
            if int(item["id"]) in {int(retained_id) for retained_id in change.retained_ids}
        }
        for item in change.new_files:
            if item.content_sha256 in seen_hashes:
                raise ValidationError(
                    fields={f"record_attachments.{item.client_id}": "该附件已添加"}
                )
            seen_hashes.add(item.content_sha256)
        return change

    @staticmethod
    def _attachment_actor(current_user: Mapping[str, Any]) -> dict[str, str]:
        return {
            "user_id": str(current_user.get("id") or ""),
            "username": str(current_user.get("username") or ""),
        }

    def _pin_datasource(self, value: Any) -> Any:
        """结构化内容的数据源类型/名称以系统已配置数据源为准，防前端伪造。

        每个表都可能使用不同数据源：记录级标识取第一条表的（顶层），
        其余表的数据源逐个校验存在性与类型，并把类型与名称修正为配置实际值。
        """
        content = value.structured_content
        if content is None or self._metadata is None:
            return value
        resolved: dict[str, tuple[str, str]] = {}
        for wanted in [content.datasource_id, *(table.datasource_id for table in content.tables)]:
            key = str(wanted or "").strip()
            if not key or key in resolved:
                continue
            entry = self._metadata.resolve(key)
            if entry is None:
                raise ValidationError(fields={
                    "datasource_id": "数据源不存在或已被删除，请在系统配置中确认",
                })
            db_type = str(getattr(entry.config, "db_type", "") or "").strip().lower()
            if db_type not in SUPPORTED_DATASOURCE_TYPES:
                raise ValidationError(fields={
                    "datasource_id": "该数据源类型暂不支持处理表字段自动读取（仅支持 PostgreSQL / MySQL）",
                })
            resolved[key] = (db_type, str(getattr(entry, "name", "") or "")[:200])
        pinned_type = resolved.get(content.datasource_id, (content.datasource_type, ""))[0]
        pinned_name = resolved.get(
            content.datasource_id, ("", value.datasource_name_snapshot or ""),
        )[1]
        pinned_tables = tuple(
            _dataclass_replace(
                table,
                datasource_type=resolved.get(table.datasource_id, (table.datasource_type, ""))[0],
                datasource_name=resolved.get(table.datasource_id, ("", table.datasource_name))[1],
            )
            for table in content.tables
        )
        return _dataclass_replace(
            value,
            structured_content=_dataclass_replace(
                content,
                datasource_type=pinned_type,
                tables=pinned_tables,
            ),
            datasource_name_snapshot=pinned_name or None,
        )

    # ===== 数据源元数据透传（表/字段选择器） =====

    def _require_metadata(self) -> Any:
        if self._metadata is None:
            raise PlatformUnavailableError(message="数据源元数据服务暂时不可用，请稍后重试")
        return self._metadata

    @staticmethod
    def _metadata_query(query: Mapping[str, str], *, default_page_size: int) -> tuple[str, int, int]:
        keyword = str(query.get("keyword") or "").strip()[:100]
        try:
            page = int(query.get("page") or 1)
            page_size = int(query.get("page_size") or default_page_size)
        except (TypeError, ValueError):
            raise ValidationError(fields={"page": "分页参数无效"}) from None
        if page < 1 or page > 10000:
            raise ValidationError(fields={"page": "分页参数无效"})
        page_size = min(100, max(1, page_size))
        return keyword, page, page_size

    def list_datasources(self) -> dict[str, Any]:
        return {"items": self._require_metadata().list_datasources()}

    def list_datasource_tables(self, datasource_id: str, query: Mapping[str, str]) -> dict[str, Any]:
        keyword, page, page_size = self._metadata_query(query, default_page_size=20)
        return self._require_metadata().list_tables(
            str(datasource_id or "").strip(), keyword=keyword, page=page, page_size=page_size,
        )

    def list_datasource_columns(self, datasource_id: str, table_name: str, query: Mapping[str, str]) -> dict[str, Any]:
        keyword, page, page_size = self._metadata_query(query, default_page_size=50)
        return self._require_metadata().list_columns(
            str(datasource_id or "").strip(), str(table_name or "").strip(),
            keyword=keyword, page=page, page_size=page_size,
        )

    # ===== 处理范围 字段定位映射（项目/合同） =====

    def list_field_mappings(self, datasource_id: str, current_user: Mapping[str, Any]) -> dict[str, Any]:
        if not can_view(self._actor(current_user)):
            raise PermissionDeniedError()
        wanted = str(datasource_id or "").strip()
        if not wanted:
            return {"items": []}
        return {"items": self.storage.list_field_mappings(wanted)}

    def upsert_field_mapping(
        self,
        datasource_id: str,
        payload: Mapping[str, Any],
        current_user: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not user_has_capability(self._actor(current_user), "rsp.edit"):
            raise PermissionDeniedError()
        wanted = str(datasource_id or "").strip()
        if not wanted:
            raise ValidationError(fields={"datasource_id": "数据源无效"})
        schema_name = str((payload or {}).get("schema") or "").strip()[:128]
        table_name = str((payload or {}).get("table_name") or "").strip()
        if not table_name or len(table_name) > 128:
            raise ValidationError(fields={"table_name": "处理表名无效"})
        project_field = str((payload or {}).get("project_field") or "").strip()
        contract_field = str((payload or {}).get("contract_field") or "").strip()
        if not project_field and not contract_field:
            raise ValidationError(fields={"project_field": "项目字段与合同字段至少填写一个"})
        for column, label in ((project_field, "project_field"), (contract_field, "contract_field")):
            if column and not _RE_PHYSICAL_NAME.match(column):
                raise ValidationError(fields={label: "字段名必须是数据库真实列名"})
        actor = self._user(current_user.get("id"))
        return self.storage.upsert_field_mapping(
            wanted, schema_name, table_name, project_field, contract_field,
            user_id=actor.id, username=actor.username,
        )

    def generate_script(self, payload: Mapping[str, Any], current_user: Mapping[str, Any]) -> dict[str, Any]:
        """根据表单生成处理脚本文本（仅生成，绝不执行）。

        payload: {structured_content, report_period, field_types}
        - report_period: 基本信息“所属报送期”（YYYY-MM-DD），参与报送期 WHERE 条件；
        - field_types: {datasource_id: {table_name: {column: data_type}}}，来源为前端已缓存
          的表字段元数据，仅用于条件值字面量格式判断（不影响生成权限与内容安全）。
        """
        if not user_has_capability(self._actor(current_user), "rsp.edit"):
            raise PermissionDeniedError()
        structured_raw = (payload or {}).get("structured_content")
        if structured_raw is None:
            raise ValidationError(fields={"structured_content": "请先完善特殊处理内容"})
        try:
            content = parse_structured_content(structured_raw)
        except StructuredContentError as exc:
            raise ValidationError(fields=exc.fields) from None
        report_period = str((payload or {}).get("report_period") or "").strip()[:16]
        field_types = (payload or {}).get("field_types") or {}
        if not isinstance(field_types, Mapping):
            raise ValidationError(fields={"structured_content": "字段类型信息无效"})
        try:
            script = generate_script(
                content,
                report_period=report_period,
                field_types=field_types,
            )
        except ScriptGenerationError as exc:
            raise ValidationError(fields={"processing_script": str(exc)}) from None
        return {"script": script}

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
        if not can_create(self._actor(current_user)):
            raise PermissionDeniedError()
        value = validate_record_input(payload)
        value = self._pin_datasource(value)
        processes = self._processes(value.report_process_codes)
        actor = self._user(current_user.get("id"))
        handler = self._user(value.handler_user_id) if value.handler_user_id else None
        governance_owner = (
            self._user(value.governance_owner_user_id, field="governance_owner_user_id")
            if value.governance_owner_user_id
            else None
        )
        now = self._now()
        status = RecordStatus.DRAFT if value.save_mode == "draft" else RecordStatus.PENDING
        self._enforce_bilingual_fields(value, None)
        business_system_code, business_system_name = self._resolve_business_system(
            value.business_system_code, None
        )
        record = self._record_values(value, processes, handler, governance_owner)
        record.update(
            business_system_code=business_system_code,
            business_system_name_snapshot=business_system_name,
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
        attachment_change = self._validated_record_attachment_change(payload, creating=True)
        attachment_actor = (
            self._attachment_actor(current_user) if attachment_change is not None else None
        )
        created = self.storage.create(
            record,
            (),
            processes,
            audit,
            record_attachment_change=attachment_change,
            attachment_actor=attachment_actor,
        )
        if status == RecordStatus.PENDING:
            self._publish_pending_notification(created)
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
        actor_user = self._actor(current_user)
        if not can_edit(actor_user, current):
            raise PermissionDeniedError()
        value = validate_record_input(payload)
        value = self._pin_datasource(value)
        if value.row_version is None:
            raise ValidationError(fields={"row_version": "不能为空"})
        if current["status"] != "draft" and value.save_mode != "record":
            raise InvalidTransitionError()
        processes = self._processes(value.report_process_codes)
        handler = self._user(value.handler_user_id) if value.handler_user_id else None
        governance_owner = (
            self._user(value.governance_owner_user_id, field="governance_owner_user_id")
            if value.governance_owner_user_id
            else None
        )
        actor = self._user(current_user.get("id"))
        now = self._now()
        next_status = "pending" if current["status"] == "draft" and value.save_mode == "record" else current["status"]
        self._enforce_bilingual_fields(value, current)
        business_system_code, business_system_name = self._resolve_business_system(
            value.business_system_code, current
        )
        changes = self._record_values(value, processes, handler, governance_owner)
        changes.update(
            business_system_code=business_system_code,
            business_system_name_snapshot=business_system_name,
            status=next_status,
            updated_by_user_id=actor.id,
            updated_by_username_snapshot=actor.username,
            updated_at=now,
        )
        changed = self._changed_fields(
            current,
            changes,
            value.processing_script,
            value.processing_script_mode,
        )
        attachment_change = None
        attachment_actor = None
        attachment_added = 0
        attachment_removed = 0
        if "record_attachments" in payload:
            current_attachments = self.storage.list_record_attachments(record_id)
            attachment_change = self._validated_record_attachment_change(
                payload, creating=False, current=current_attachments
            )
            if attachment_change is not None:
                attachment_actor = self._attachment_actor(current_user)
                current_ids = {int(item["id"]) for item in current_attachments}
                attachment_removed = len(current_ids - set(attachment_change.retained_ids))
                attachment_added = len(attachment_change.new_files)
        attachments_changed = attachment_added > 0 or attachment_removed > 0
        draft_save = value.save_mode == "draft" or next_status == "draft"
        action_code = "update" if next_status == current["status"] else "status_change"
        summary = self._build_action_summary(
            action_code,
            current["status"],
            next_status,
            changed,
            draft_save=draft_save,
        )
        if attachments_changed:
            if changed:
                summary = f"{summary}；附件新增 {attachment_added} 个、移除 {attachment_removed} 个"
            else:
                summary = f"修改附件（新增 {attachment_added} 个，移除 {attachment_removed} 个）"
        audit = self._audit(
            action_code,
            actor,
            now,
            current["status"],
            next_status,
            changed,
            summary,
            request_id,
        )
        updated = self.storage.update(
            record_id,
            value.row_version,
            changes,
            (),
            processes,
            audit,
            record_attachment_change=attachment_change,
            attachment_actor=attachment_actor,
        )
        if updated.get("status") == "pending":
            if current["status"] == "pending":
                old_owner = str(current.get("governance_owner_user_id") or "")
                new_owner = str(updated.get("governance_owner_user_id") or "")
                if old_owner != new_owner:
                    self._publish_pending_notification(updated)
            else:
                self._publish_pending_notification(updated)
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
        actor_user = self._actor(current_user)
        target = payload.get("target_status")
        if isinstance(target, str) and target in {"completed"}:
            if not can_confirm(actor_user, current):
                raise PermissionDeniedError()
        elif not can_edit(actor_user, current):
            raise PermissionDeniedError()
        version, reason = validate_action(payload)
        if not isinstance(target, str) or not can_transition(str(current["status"]), target):
            raise InvalidTransitionError()
        confirm_images: tuple[dict[str, Any], ...] = ()
        if target == "completed":
            confirm_images = validate_confirm_images(payload.get("confirm_images"))
        elif payload.get("confirm_images") not in (None, [], ()):
            raise ValidationError(fields={"confirm_images": "仅确认完成时可提交图片"})
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
        changed_fields: dict[str, Any] = {
            "status": {"changed": True, "old": current["status"], "new": target},
        }
        if target == "completed" and reason:
            changed_fields["reason"] = {"present": True, "new": reason}
        elif reason:
            changed_fields["reason"] = {"present": True}
        audit = self._audit(
            "status_change", actor, now, current["status"], target,
            changed_fields,
            self._build_action_summary(
                "status_change",
                current["status"],
                target,
                {"status": {"changed": True, "old": current["status"], "new": target}},
            ),
            request_id,
        )
        changed = self.storage.update_status(
            record_id,
            version,
            changes,
            audit,
            attachments=confirm_images,
        )
        if target == "completed":
            self._publish_completion_notification(changed, request_id=request_id)
        self._refresh_special_governance_stats()
        return changed

    def void(
        self, record_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        current = self._record(record_id)
        if not can_void(self._actor(current_user), current):
            raise PermissionDeniedError()
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
        if not can_delete(self._actor(current_user)):
            raise PermissionDeniedError()
        current = self._record(record_id)
        version, _reason = validate_action(payload, require_reason=False)
        self.storage.delete_record(record_id, version)
        self._refresh_special_governance_stats()
        return {"id": record_id, "deleted": True, "record_no": current.get("record_no")}

    def reopen(
        self, record_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        current = self._record(record_id)
        if not can_reopen(self._actor(current_user), current):
            raise PermissionDeniedError()
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
                {
                    "status": {"changed": True, "old": current["status"], "new": "pending"},
                    "reopen_reason": {"changed": True, "new": reason},
                },
            ),
            request_id,
        )
        reopened = self.storage.update_status(record_id, version, changes, audit)
        if reopened.get("status") == "pending":
            self._publish_pending_notification(reopened)
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
            "can_confirm": can_confirm(current_user, record),
            "can_void": can_void(current_user, record),
            "can_reopen": can_reopen(current_user, record),
            "can_delete": can_delete(current_user),
            "can_create": can_create(current_user),
            "can_view": can_view(current_user),
            "can_admin": can_delete(current_user),
        }

    def _user(self, user_id: Any, *, field: str = "handler_user_id") -> Any:
        if user_id in {None, ""}:
            raise ValidationError(fields={field: "用户不存在或已停用"})
        try:
            user = self._users.get_user(str(user_id))
        except Exception:
            raise PlatformUnavailableError() from None
        if user is None or not user.active:
            raise ValidationError(fields={field: "用户不存在或已停用"})
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

    def _publish_pending_notification(self, record: Mapping[str, Any]) -> None:
        if self._notifications is None:
            return
        owner_id = str(record.get("governance_owner_user_id") or "").strip()
        if not owner_id:
            return
        record_id = int(record["id"])
        row_version = int(record["row_version"])
        from auto_check.app.notifications.contracts import (
            NotificationAction,
            NotificationPublishRequest,
        )
        request = NotificationPublishRequest(
            event_type="pending_confirmation_created",
            dedupe_key=f"rsp-pending:{record_id}:{row_version}:{owner_id}",
            recipient_user_ids=(owner_id,),
            category="todo",
            level="info",
            title="有报表特殊处理请您确认",
            content=ownership_system_field_summary(record),
            action=NotificationAction(
                type="navigate",
                route="report-special-processing",
                query={"record_id": str(record_id), "highlight": "1", "open": "confirm", "period": str(record.get("report_period") or "").strip()[5:]},
            ),
        )
        try:
            self._notifications.publish(request)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "notification publish failed for record %s:%s recipient=%s",
                record_id, row_version, owner_id,
                exc_info=True,
            )

    def _publish_completion_notification(
        self,
        record: Mapping[str, Any],
        *,
        request_id: str,
    ) -> None:
        if self._notifications is None:
            return
        creator_id = str(record.get("creator_user_id") or "").strip()
        if not creator_id:
            return

        record_id = int(record["id"])
        row_version = int(record["row_version"])
        report_period = str(record.get("report_period") or "").strip()
        query = {
            "record_id": str(record_id),
            "highlight": "1",
        }
        if len(report_period) >= 10:
            query["period"] = report_period[5:10]

        from auto_check.app.notifications.contracts import (
            NotificationAction,
            NotificationPublishRequest,
        )

        request = NotificationPublishRequest(
            event_type="confirmation_completed",
            dedupe_key=(
                f"rsp-completed:{record_id}:{row_version}:{creator_id}"
            ),
            recipient_user_ids=(creator_id,),
            category="task",
            level="success",
            title="您提交的报表特殊处理已完成确认",
            content=ownership_system_field_summary(record),
            action=NotificationAction(
                type="navigate",
                route="report-special-processing",
                query=query,
            ),
        )
        try:
            self._notifications.publish(request)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "completion notification publish failed for record "
                "%s:%s recipient=%s request=%s",
                record_id,
                row_version,
                creator_id,
                request_id,
                exc_info=True,
            )

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
    def _record_values(
        value: Any,
        processes: Sequence[Mapping[str, str]] | tuple[dict[str, str], ...],
        handler: Any,
        governance_owner: Any = None,
    ) -> dict[str, Any]:
        script = value.processing_script
        primary = processes[0]
        names = "；".join(item["name"] for item in processes)
        structured = value.structured_content
        datasource_name = None
        if structured is not None:
            datasource_name = (value.datasource_name_snapshot or "").strip() or structured.datasource_id
        return {
            "report_process_code": primary["code"],
            "report_process_name_snapshot": names[:500],
            "report_period": value.report_period,
            "dimension": value.dimension,
            "business_system_code": None,
            "business_system_name_snapshot": None,
            "datasource_id": structured.datasource_id if structured else None,
            "datasource_name_snapshot": datasource_name,
            "datasource_type": structured.datasource_type if structured else None,
            "structured_content_json": structured.to_json() if structured else None,
            "summary": value.summary or None,
            "table_name": value.table_name,
            "field_name": value.field_name,
            "value_before": value.value_before,
            "value_after": value.value_after,
            "processing_content": "",
            "processing_script": script,
            "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest() if script else None,
            "special_handling_at": value.special_handling_at,
            "handler_user_id": handler.id if handler else None,
            "handler_username_snapshot": handler.username if handler else None,
            "handler_display_name_snapshot": handler.display_name if handler else None,
            "governance_owner_user_id": governance_owner.id if governance_owner else None,
            "governance_owner_username_snapshot": (
                governance_owner.username if governance_owner else None
            ),
            "governance_owner_display_name_snapshot": (
                governance_owner.display_name if governance_owner else None
            ),
        }

    @staticmethod
    def _require_complete(record: Mapping[str, Any]) -> None:
        required = (
            record.get("summary"),
            record.get("report_period"),
            record.get("special_handling_at"),
            record.get("handler_user_id"),
            record.get("dimension"),
            record.get("governance_owner_user_id"),
            record.get("table_name"),
            record.get("field_name"),
            record.get("value_before"),
            record.get("value_after"),
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

    @staticmethod
    def _script_audit_preview(script: str | None) -> tuple[str, bool]:
        text = str(script or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = text.splitlines()
        preview = "\n".join(lines[:SCRIPT_AUDIT_PREVIEW_LINES])
        truncated = len(lines) > SCRIPT_AUDIT_PREVIEW_LINES
        if len(preview) > SCRIPT_AUDIT_PREVIEW_CHARS:
            preview = preview[:SCRIPT_AUDIT_PREVIEW_CHARS]
            truncated = True
        if preview != text:
            truncated = True
        return preview, truncated

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
        structured_change = changed.get("structured_content")
        if isinstance(structured_change, Mapping):
            basic_count = sum(
                1 for key in changed
                if key not in {"structured_content", "processing_script", "status"}
                and key in _AUDIT_FIELD_LABELS
            )
            parts: list[str] = []
            if basic_count:
                parts.append(f"基本信息{basic_count}项")
            special_count = int(structured_change.get("change_count") or 0)
            affected_tables = int(structured_change.get("affected_tables") or 0)
            parts.append(f"特殊处理内容{special_count}项（涉及{affected_tables}张处理表）")
            if "processing_script" in changed:
                parts.append("脚本同步更新")
            if "status" in changed or (from_status and to_status and from_status != to_status):
                parts.append(
                    f"状态由{cls._format_audit_value(from_status, field='status')}"
                    f"改为{cls._format_audit_value(to_status, field='status')}"
                )
            if action == "void" or to_status == "voided":
                header = "作废记录："
            elif action == "reopen":
                header = "重开记录："
            elif action == "status_change" and to_status == "completed":
                header = "完成记录："
            elif draft_save or to_status == "draft":
                header = "保存草稿："
            else:
                header = "更新记录："
            return (header + "\n" + "\n".join(
                f"{index}.{text}" for index, text in enumerate(parts, 1)
            ))[:1000]
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
            if key == "reopen_reason":
                reason_text = cls._format_audit_value(meta.get("new"))
                if reason_text != "（空）":
                    parts.append(f"重开原因：{reason_text}")
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
        script_mode: str = "AUTO",
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        old_structured = current.get("structured_content")
        if not isinstance(old_structured, Mapping):
            try:
                old_structured = json.loads(str(current.get("structured_content_json") or ""))
            except (TypeError, ValueError):
                old_structured = None
        try:
            new_structured = json.loads(str(changes.get("structured_content_json") or ""))
        except (TypeError, ValueError):
            new_structured = None
        structured_change = build_structured_audit_diff(
            old_structured if isinstance(old_structured, Mapping) else None,
            new_structured if isinstance(new_structured, Mapping) else None,
        )
        structured_mode = isinstance(old_structured, Mapping) and isinstance(new_structured, Mapping)
        for key, value in changes.items():
            if key in _AUDIT_SKIP_KEYS or key in {
                "processing_script",
                "script_sha256",
                "processing_content",
                "governance_owner_user_id",
                "governance_owner_username_snapshot",
            }:
                continue
            if structured_mode and key in _STRUCTURED_DERIVED_AUDIT_KEYS:
                continue
            if current.get(key) == value:
                continue
            if key == "dimension":
                old_code = current.get(key)
                new_code = value
                result[key] = {
                    "changed": True,
                    "old": DIMENSION_LABELS.get(str(old_code or ""), old_code),
                    "new": DIMENSION_LABELS.get(str(new_code or ""), new_code),
                }
                continue
            if key not in _AUDIT_FIELD_LABELS:
                result[key] = {"changed": True}
                continue
            result[key] = {"changed": True, "old": current.get(key), "new": value}
        if structured_change is not None:
            result["structured_content"] = structured_change
        if current.get("processing_script") != script:
            old_script = current.get("processing_script") or ""
            new_script = script or ""
            old_preview, old_truncated = SpecialProcessingService._script_audit_preview(old_script)
            new_preview, new_truncated = SpecialProcessingService._script_audit_preview(new_script)
            result["processing_script"] = {
                "changed": True,
                "mode": script_mode,
                "old_sha256": current.get("script_sha256"),
                "new_sha256": changes.get("script_sha256"),
                "old_chars": len(old_script),
                "new_chars": len(new_script),
                "old": old_script,
                "new": new_script,
                "old_preview": old_preview,
                "new_preview": new_preview,
                "old_truncated": old_truncated,
                "new_truncated": new_truncated,
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
