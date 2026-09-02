from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from auto_check.app.db import qualified_name
from auto_check.app.pbc_import import parse_table_ref
from auto_check.db_validation.mapping_models import CrossTableMapping, FieldMapping, TableMapping
from auto_check.db_validation.mapping_storage import DbValidationMappingStorage
from auto_check.db_validation.metadata import FieldMetadataLoader, TableFieldCatalog, match_chinese_field_name
from auto_check.db_validation.tables import detail_table_codes_with_dependencies


TECHNICAL_FIELDS = frozenset({
    "id",
    "created_at",
    "updated_at",
    "create_time",
    "update_time",
    "created_by",
    "updated_by",
    "deleted",
    "delete_flag",
    "is_deleted",
})
_ZG_PATTERN = re.compile(r"(?<![a-z0-9])zg(0[1-9]|1[0-3])(?![a-z0-9])", re.I)


class DbValidationMappingService:
    def __init__(self, database: Any) -> None:
        self.storage = DbValidationMappingStorage(database)

    def status_payload(self) -> dict[str, Any]:
        try:
            return self.storage.status_payload()
        except Exception:
            return {
                "initialized": False,
                "refreshed_at": "",
                "refresh_source": "",
                "table_count": 0,
                "field_count": 0,
                "mapped_field_count": 0,
                "unmapped_field_count": 0,
                "required_missing_count": 0,
                "missing_physical_count": 0,
                "last_error": "映射表尚未初始化",
                "last_failed_at": "",
            }

    def tables_payload(self) -> list[dict[str, Any]]:
        try:
            return [item.to_payload() for item in self.storage.load_tables()]
        except Exception:
            return []

    def current_catalog(self) -> TableFieldCatalog | None:
        try:
            return self.storage.latest_catalog()
        except Exception:
            return None

    def detail_payload(self) -> dict[str, Any]:
        payload = self.storage.detail_payload()
        payload["field_mapping"] = self.status_payload()
        return payload

    def save_override(self, **values: str) -> dict[str, Any]:
        self.storage.save_override(**values)
        return self.detail_payload()

    def restore_override(self, **values: str) -> dict[str, Any]:
        self.storage.restore_override(**values)
        return self.detail_payload()

    def required_missing_for_run(
        self,
        *,
        selected_tables: list[str] | tuple[str, ...] | None = None,
        include_template: bool = False,
        include_public_info: bool = False,
    ) -> list[dict[str, Any]]:
        tables_for_run = (
            detail_table_codes_with_dependencies(selected_tables)
            if selected_tables is not None
            else None
        )
        return self.storage.required_missing_for_tables(
            tables_for_run,
            include_template=include_template,
            include_public_info=include_public_info,
        )

    def record_failed_refresh(
        self,
        *,
        signature: tuple[Any, ...],
        source: str,
        error_message: str,
    ) -> dict[str, Any]:
        try:
            self.storage.record_failed_snapshot(
                signature=signature,
                refresh_source=source,
                error_message=error_message,
            )
        except Exception:
            pass
        return self.status_payload()

    def missing_required_fields(
        self,
        selected_tables: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return self.storage.required_missing_for_tables(selected_tables)
        except Exception:
            return []

    def refresh(
        self,
        *,
        metadata_client: Any,
        data_clients: dict[str, Any],
        baseinfo_table: str,
        field_info_table: str,
        sys_manage_id: str,
        classification_id: str,
        signature: tuple[Any, ...],
        source: str,
        public_info_sys_manage_id: str = "",
        public_info_classification_id: str = "",
        required_chinese_fields_by_scope: dict[str, frozenset[str]] | None = None,
        optional_chinese_fields_by_scope: dict[str, frozenset[str]] | None = None,
    ) -> TableFieldCatalog:
        scope_map = dict(required_chinese_fields_by_scope or {})
        optional_scope_map = dict(optional_chinese_fields_by_scope or {})
        configured_detail_tables = self._configured_detail_tables(
            metadata_client,
            baseinfo_table=baseinfo_table,
            sys_manage_id=sys_manage_id,
            classification_id=classification_id,
        )
        existing = self.storage.load_tables()
        overrides = self._override_index(self.storage.load_active_overrides())
        tables = self._build_tables(existing, configured_detail_tables, overrides)

        detail_catalog = FieldMetadataLoader(
            metadata_client,
            baseinfo_table=baseinfo_table,
            field_info_table=field_info_table,
            sys_manage_id=sys_manage_id,
            classification_id=classification_id,
        ).load()
        if public_info_sys_manage_id or public_info_classification_id:
            public_info_catalog = FieldMetadataLoader(
                metadata_client,
                baseinfo_table=baseinfo_table,
                field_info_table=field_info_table,
                sys_manage_id=public_info_sys_manage_id,
                classification_id=public_info_classification_id,
            ).load()
        else:
            public_info_catalog = detail_catalog

        fields: list[FieldMapping] = []
        for table in tables:
            required = self._resolve_required_for_table(table, scope_map)
            optional = self._resolve_required_for_table(table, optional_scope_map) - required
            fields.extend(
                self._build_fields_for_table(
                    table=table,
                    client=data_clients.get(table.relation_type),
                    metadata_catalog=(public_info_catalog if table.relation_type == "public_info" else detail_catalog),
                    overrides=overrides,
                    required=required,
                    optional=optional,
                )
            )
        cross_table_fields = self._cross_table_detail_fields(tables, data_clients.get("detail"))
        self.storage.refresh_cross_table_mappings(self._build_cross_table_mappings(tables, cross_table_fields))
        return self.storage.save_snapshot(
            signature=signature,
            refresh_source=source,
            tables=tables,
            fields=fields,
        )

    @staticmethod
    def _build_cross_table_mappings(
        tables: list[TableMapping],
        detail_fields: dict[str, set[str]],
    ) -> list[CrossTableMapping]:
        template_tables = {
            (item.logical_code, item.scope_code): item.effective_table_name
            for item in tables
            if item.relation_type == "template" and item.logical_code in {"ZG09", "ZG10"}
        }
        mappings: list[CrossTableMapping] = []
        for (logical_code, scope_code), template_table in sorted(template_tables.items()):
            for detail_field in sorted(detail_fields.get(logical_code, ())):
                template_field = _automatic_template_field(logical_code, detail_field)
                if not template_field:
                    continue
                mappings.append(CrossTableMapping(
                    mapping_code=f"{logical_code}:{scope_code}:{detail_field.lower()}",
                    logical_code=logical_code,
                    scope_code=scope_code,
                    automatic_detail_field_name=detail_field,
                    automatic_template_table_name=template_table,
                    automatic_template_field_name=template_field,
                ))
        return mappings

    @staticmethod
    def _cross_table_detail_fields(
        tables: list[TableMapping],
        client: Any | None,
    ) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {"ZG09": set(), "ZG10": set()}
        if client is None:
            return result
        for table in tables:
            if table.relation_type != "detail" or table.logical_code not in result:
                continue
            try:
                result[table.logical_code].update(
                    str(column.name)
                    for column in client.table_columns(parse_table_ref(table.effective_table_name))
                    if str(column.name).lower() not in TECHNICAL_FIELDS
                )
            except Exception:
                continue
        return result

    def _build_tables(
        self,
        existing: tuple[TableMapping, ...] | list[TableMapping],
        configured_detail_tables: dict[str, str],
        overrides: dict[tuple[str, str, str, str, str], str],
    ) -> list[TableMapping]:
        tables: list[TableMapping] = []
        for item in existing:
            automatic = item.automatic_table_name
            if item.relation_type == "detail":
                automatic = configured_detail_tables.get(item.logical_code, item.automatic_table_name)
            override = overrides.get(("table", item.relation_type, item.logical_code, item.scope_code, ""))
            if override is None:
                override = item.override_table_name
            tables.append(
                TableMapping(
                    relation_type=item.relation_type,
                    logical_code=item.logical_code,
                    scope_code=item.scope_code,
                    automatic_table_name=automatic,
                    override_table_name=override,
                    mapping_status=item.mapping_status,
                    status_message=item.status_message,
                )
            )
        return tables

    def _build_fields_for_table(
        self,
        *,
        table: TableMapping,
        client: Any | None,
        metadata_catalog: TableFieldCatalog,
        overrides: dict[tuple[str, str, str, str, str], str],
        required: frozenset[str],
        optional: frozenset[str],
    ) -> list[FieldMapping]:
        if client is None:
            return []
        # 模板采用纵表结构：列仅用于承载“指标码—指标值”，真正的
        # 逐笔字段与模板指标关系由跨表映射维护，不参与中文字段映射。
        if table.relation_type == "template":
            return []
        try:
            physical_columns = [
                str(column.name)
                for column in client.table_columns(parse_table_ref(table.effective_table_name))
                if str(column.name).lower() not in TECHNICAL_FIELDS
            ]
        except Exception as exc:
            return [
                FieldMapping(
                    relation_type=table.relation_type,
                    logical_code=table.logical_code,
                    scope_code=table.scope_code,
                    chinese_name=chinese_name,
                    automatic_field_name=None,
                    mapping_status=("required_missing" if is_required else "unmapped"),
                    is_required=is_required,
                    status_message=f"物理表不可读：{table.effective_table_name}（{exc}）",
                )
                for chinese_name, is_required in (
                    [(name, True) for name in sorted(required)]
                    + [(name, False) for name in sorted(optional)]
                )
            ]

        configured_fields = dict(metadata_catalog.by_table.get(table.effective_table_name, {}))
        if not configured_fields and table.automatic_table_name != table.effective_table_name:
            configured_fields = dict(metadata_catalog.by_table.get(table.automatic_table_name, {}))
        fields: list[FieldMapping] = []
        # 字段映射只纳入规则明确声明的必需字段和可选字段；元数据和
        # 物理表中的其他字段不进入弹窗，也不参与映射统计。
        field_matches = [
            (chinese_name, is_required, match_chinese_field_name(chinese_name, configured_fields))
            for chinese_name, is_required in (
                [(name, True) for name in required]
                + [(name, False) for name in optional]
            )
        ]
        field_matches.sort(key=lambda item: (not item[1], item[2] != item[0], item[0]))
        claimed_fields: dict[str, int] = {}
        for chinese_name, is_required, metadata_chinese_name in field_matches:
            automatic = configured_fields.get(metadata_chinese_name) if metadata_chinese_name else None
            override = overrides.get(
                ("field", table.relation_type, table.logical_code, table.scope_code, chinese_name)
            )
            if override is None and metadata_chinese_name and metadata_chinese_name != chinese_name:
                # 兼容旧版本以元数据中文名保存的人工修改。
                override = overrides.get(
                    ("field", table.relation_type, table.logical_code, table.scope_code, metadata_chinese_name)
                )
            effective = override or automatic
            if effective and effective in claimed_fields:
                previous_index = claimed_fields[effective]
                previous = fields[previous_index]
                metadata_label = metadata_chinese_name or previous.chinese_name
                fields[previous_index] = replace(
                    previous,
                    status_message=(
                        f"语义匹配：校验字段“{chinese_name}”共用元数据“{metadata_label}”"
                    ),
                )
                continue
            if effective and effective in physical_columns:
                message = (
                    f"语义匹配：元数据“{metadata_chinese_name}”"
                    if metadata_chinese_name and metadata_chinese_name != chinese_name
                    else ""
                )
                fields.append(FieldMapping(
                    relation_type=table.relation_type,
                    logical_code=table.logical_code,
                    scope_code=table.scope_code,
                    chinese_name=chinese_name,
                    automatic_field_name=automatic,
                    override_field_name=override,
                    mapping_status="mapped",
                    is_required=is_required,
                    status_message=message,
                ))
                claimed_fields[effective] = len(fields) - 1
                continue
            if automatic or override:
                fields.append(FieldMapping(
                    relation_type=table.relation_type,
                    logical_code=table.logical_code,
                    scope_code=table.scope_code,
                    chinese_name=chinese_name,
                    automatic_field_name=automatic,
                    override_field_name=override,
                    mapping_status="missing_physical",
                    is_required=is_required,
                    status_message=f"映射的英文字段 {effective} 在实际表中不存在",
                ))
                if effective:
                    claimed_fields[effective] = len(fields) - 1
                continue
            fields.append(FieldMapping(
                relation_type=table.relation_type,
                logical_code=table.logical_code,
                scope_code=table.scope_code,
                chinese_name=chinese_name,
                automatic_field_name=None,
                override_field_name=None,
                mapping_status=("required_missing" if is_required else "unmapped"),
                is_required=is_required,
                status_message=(
                    f"规则必需字段缺失：{chinese_name}"
                    if is_required
                    else f"未找到字段映射：{chinese_name}"
                ),
            ))
        return fields

    @staticmethod
    def _override_index(overrides: list[dict[str, Any]]) -> dict[tuple[str, str, str, str, str], str]:
        result: dict[tuple[str, str, str, str, str], str] = {}
        for item in overrides:
            key = (
                str(item.get("mapping_kind") or ""),
                str(item.get("relation_type") or ""),
                str(item.get("logical_code") or ""),
                str(item.get("scope_code") or ""),
                str(item.get("chinese_name") or ""),
            )
            value = str(item.get("override_value") or "").strip()
            if value:
                result[key] = value
        return result

    @staticmethod
    def _resolve_required_for_table(
        table: TableMapping,
        scope_map: dict[str, frozenset[str]],
    ) -> frozenset[str]:
        """按表解析必需中文字段集合：detail 按 logical_code，
        template/public_info 按 TEMPLATE/PUBLIC_INFO 固定键。"""
        if not scope_map:
            return frozenset()
        if table.relation_type == "detail":
            return scope_map.get(table.logical_code, frozenset())
        if table.relation_type == "template":
            return scope_map.get("TEMPLATE", frozenset())
        if table.relation_type == "public_info":
            return scope_map.get("PUBLIC_INFO", frozenset())
        return frozenset()

    @staticmethod
    def _configured_detail_tables(
        metadata_client: Any,
        *,
        baseinfo_table: str,
        sys_manage_id: str,
        classification_id: str,
    ) -> dict[str, str]:
        loader = FieldMetadataLoader(
            metadata_client,
            baseinfo_table=baseinfo_table,
            sys_manage_id=sys_manage_id,
            classification_id=classification_id,
        )
        where = ["COALESCE(table_name_en, '') <> ''"]
        params: list[str] = []
        if loader.sys_manage_ids:
            where.append(f"sys_manage_id IN ({', '.join(['%s'] * len(loader.sys_manage_ids))})")
            params.extend(loader.sys_manage_ids)
        if loader.classification_ids:
            where.append(f"classification_id IN ({', '.join(['%s'] * len(loader.classification_ids))})")
            params.extend(loader.classification_ids)
        rows = metadata_client.fetch_all(
            f"SELECT table_name_en FROM {qualified_name(metadata_client.config, baseinfo_table)} "
            f"WHERE {' AND '.join(where)}",
            tuple(params),
        )
        candidates: dict[str, list[str]] = {}
        for row in rows:
            table_name = str(row.get("table_name_en", "")).strip()
            match = _ZG_PATTERN.search(table_name)
            if match:
                candidates.setdefault(f"ZG{match.group(1)}", []).append(table_name)
        return {
            logical_code: min(
                names,
                key=lambda name: (
                    "change" in name.lower(),
                    "bulu" in name.lower(),
                    len(name),
                    name.lower(),
                ),
            )
            for logical_code, names in candidates.items()
        }


def _automatic_template_field(logical_code: str, detail_field: str) -> str:
    field = str(detail_field or "").strip().lower()
    if logical_code == "ZG09":
        if field == "fb00001":
            return "f1"
        if field == "fb00002":
            return "f2"
        if len(field) == 5 and field.startswith("g") and field[1:4].isdigit():
            column = {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"}.get(field[-1], "")
            if column:
                return f"{column}_g{field[1:4]}00"
    if logical_code == "ZG10" and field.startswith("h") and field[1:].isdigit():
        return f"A_{field}"
    return ""
