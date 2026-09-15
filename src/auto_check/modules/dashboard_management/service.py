from __future__ import annotations

from datetime import datetime, timezone
import secrets
from typing import Any, Callable, Mapping

from .catalog import BOARD_CATALOG
from .contracts import VersionConflictError
from .storage import DashboardManagementStorage, SchemaVersionConflictError
from .sql_executor import QueryPreview, SqlPreviewExecutor
from .system_data import SystemDataPreviewExecutor
from .validator import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
    validate_board_code,
    validate_create_field,
    validate_create_region,
    validate_update_field,
    validate_update_region,
)
from .year_snapshots import (
    QUARTERLY_SPECIAL_PROCESSING,
    SNAPSHOT_REGION_CODES,
    SnapshotValidationError,
    normalize_snapshot_rows,
)


class SqlRetestRequiredError(DomainError):
    status = 409
    code = "sql_retest_required"
    message = "SQL、数据源或字段已变化，请重新测试后保存"


class DashboardManagementService:
    def __init__(
        self,
        storage: DashboardManagementStorage,
        *,
        datasource_loader: Callable[[], list[Any]] | None = None,
        sql_executor: SqlPreviewExecutor | None = None,
        system_executor: SystemDataPreviewExecutor | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.storage = storage
        self._datasource_loader = datasource_loader
        if sql_executor is None:
            self._sql_executor = SqlPreviewExecutor()
            self._snapshot_sql_executor = SqlPreviewExecutor(preview_limit=12)
        else:
            self._sql_executor = sql_executor
            self._snapshot_sql_executor = sql_executor
        if system_executor is None:
            self._system_executor = SystemDataPreviewExecutor()
            self._snapshot_system_executor = SystemDataPreviewExecutor(preview_limit=12)
        else:
            self._system_executor = system_executor
            self._snapshot_system_executor = system_executor
        self._now = now or (lambda: datetime.now(timezone.utc))

    def catalog(self, board_code: str, current_user: Mapping[str, Any]) -> dict[str, Any]:
        del current_user
        selected = validate_board_code(board_code)
        regions = []
        for region in self.storage.list_regions(selected):
            item = dict(region)
            item["fields"] = self.storage.list_fields(region["id"])
            item["source_config"] = self.storage.get_source_config(region["id"])
            item["system_source"] = self._system_executor.source_for(
                self.storage.database, str(region["region_code"])
            )
            regions.append(item)
        return {
            "boards": [
                {"code": board.code, "name": board.name, "display_order": board.display_order}
                for board in BOARD_CATALOG
            ],
            "board": next(
                {"code": board.code, "name": board.name, "display_order": board.display_order}
                for board in BOARD_CATALOG if board.code == selected
            ),
            "regions": regions,
        }

    def preview_board_data(
        self, board_code: str, current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        del current_user
        selected = validate_board_code(board_code)
        board = next(board for board in BOARD_CATALOG if board.code == selected)
        regions = []
        request_now = self._now()
        for region in self.storage.list_regions(selected, include_disabled=False):
            fields = self.storage.list_fields(region["id"], include_disabled=False)
            snapshot_enabled = (
                bool(region.get("built_in"))
                and str(region["region_code"]) in SNAPSHOT_REGION_CODES
            )
            item = {
                "code": region["region_code"],
                "name": region["name"],
                "shape": region["shape"],
                "fields": [
                    {
                        "alias": field["field_alias"],
                        "name": field["name"],
                        "value_type": field["value_type"],
                    }
                    for field in fields
                ],
            }
            period_alias = _snapshot_period_alias(str(region["region_code"]))
            if snapshot_enabled and period_alias not in {
                str(field["field_alias"]) for field in fields
            }:
                item.update(_preview_error(SnapshotValidationError(
                    f"快照区域必须启用周期字段：{period_alias}"
                )))
                regions.append(item)
                continue
            try:
                preview = self._execute_saved_region(
                    region, fields, snapshot_enabled=snapshot_enabled
                )
                if snapshot_enabled:
                    if preview.has_more:
                        raise SnapshotValidationError(
                            "快照区域查询结果最多支持 12 个周期"
                        )
                    refreshed_at = request_now
                    normalized = normalize_snapshot_rows(
                        str(region["region_code"]), preview.rows, refreshed_at
                    )
                    snapshots = self.storage.refresh_year_snapshots(
                        int(region["id"]),
                        normalized,
                        period_year=refreshed_at.year,
                        refreshed_at=refreshed_at,
                    )
                    preview = _snapshot_preview(
                        fields,
                        snapshots,
                        region_code=str(region["region_code"]),
                        request_now=request_now,
                    )
                    item.update(_preview_item(preview))
                    item.update({
                        "snapshot_status": "fresh",
                        "snapshot_refreshed_at": _latest_snapshot_refresh(snapshots),
                    })
                else:
                    item.update(_preview_item(preview))
            except Exception as error:
                fallback = None
                if snapshot_enabled:
                    fallback = self._snapshot_fallback(
                        region,
                        fields,
                        period_year=request_now.year,
                        request_now=request_now,
                    )
                if fallback is not None:
                    preview, refreshed_at = fallback
                    item.update(_preview_item(preview))
                    item.update({
                        "snapshot_status": "stale",
                        "snapshot_refreshed_at": refreshed_at,
                    })
                else:
                    item.update(_preview_error(error))
            regions.append(item)
        return {
            "board": {"code": board.code, "name": board.name},
            "regions": regions,
        }

    def _snapshot_fallback(
        self,
        region: Mapping[str, Any],
        fields: list[Mapping[str, Any]],
        *,
        period_year: int,
        request_now: datetime,
    ) -> tuple[QueryPreview, str | None] | None:
        try:
            snapshots = self.storage.list_year_snapshots(
                int(region["id"]), period_year
            )
        except Exception:
            return None
        if not snapshots:
            return None
        return (
            _snapshot_preview(
                fields,
                snapshots,
                region_code=str(region["region_code"]),
                request_now=request_now,
            ),
            _latest_snapshot_refresh(snapshots),
        )

    def create_region(
        self, board_code: str, payload: Mapping[str, Any], current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        del current_user
        values = validate_create_region(payload)
        fields = values.pop("fields")
        values.update({
            "board_code": validate_board_code(board_code),
            "region_code": f"custom_region_{secrets.token_hex(6)}",
            "built_in": False,
            "system_supported": False,
            "default_mode": "sql",
        })
        return self.storage.create_region_with_fields_and_default_sql(values, fields)

    def update_region(
        self, region_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        del current_user
        existing = self.storage.get_region(region_id)
        if existing is None:
            raise NotFoundError("数据区域不存在")
        values, version = validate_update_region(payload, existing)
        try:
            return self.storage.update_region(region_id, values, version)
        except VersionConflictError as error:
            raise ConflictError() from error

    def delete_region(
        self, region_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        del current_user
        existing = self.storage.get_region(region_id)
        if existing is None:
            raise NotFoundError("数据区域不存在")
        if existing["built_in"]:
            raise ValidationError("内置数据区域不能删除")
        row_version = _delete_region_payload(payload)
        try:
            self.storage.delete_custom_region(region_id, row_version)
        except VersionConflictError as error:
            raise ConflictError() from error
        return {"id": region_id, "deleted": True}

    def create_field(
        self, region_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        del current_user
        region = self.storage.get_region(region_id)
        if region is None:
            raise NotFoundError("数据区域不存在")
        return self.storage.create_field_and_invalidate_source(
            region_id, validate_create_field(payload)
        )

    def update_field(
        self, field_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        del current_user
        existing = self.storage.get_field(field_id)
        if existing is None:
            raise NotFoundError("字段不存在")
        values, version = validate_update_field(payload, existing)
        try:
            return self.storage.update_field_and_invalidate_source(
                field_id, values, version
            )
        except VersionConflictError as error:
            raise ConflictError() from error
        except ValueError as error:
            message = str(error) or "字段更新失败"
            raise ValidationError(message, fields={"enabled": message}) from error

    def list_datasources(self) -> list[dict[str, str]]:
        entries = self._data_sources()
        summaries = []
        for entry in entries:
            if isinstance(entry, Mapping):
                summaries.append({
                    "id": str(entry.get("id") or ""),
                    "name": str(entry.get("name") or ""),
                    "db_type": str(entry.get("db_type") or ""),
                })
            else:
                summaries.append({
                    "id": str(entry.id),
                    "name": str(entry.name),
                    "db_type": str(entry.config.db_type),
                })
        return summaries

    def test_sql(
        self, region_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        region = self._region(region_id)
        datasource_id, sql_text = _test_sql_payload(payload)
        source = self._data_source(datasource_id)
        fields = self.storage.list_fields(region_id, include_disabled=False)
        preview = self._sql_executor.execute(source, sql_text, fields, region["shape"])
        username = str(current_user.get("username") or current_user.get("id") or "")
        try:
            source_config = self.storage.record_successful_sql_test(
                region_id, preview.tested_signature, username, region["row_version"],
            )
        except SchemaVersionConflictError as error:
            raise SqlRetestRequiredError() from error
        except VersionConflictError as error:
            raise ConflictError() from error
        return _preview_response(preview, source_config)

    def preview_system_data(
        self, region_id: int, current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        del current_user
        region = self._region(region_id)
        if not region["system_supported"]:
            raise ValidationError("该数据区域暂不支持系统数据")
        result = self._system_executor.execute(
            self.storage.database,
            str(region["region_code"]),
            self.storage.list_fields(region_id, include_disabled=False),
            str(region["shape"]),
        )
        return {
            "columns": result.preview.columns,
            "rows": result.preview.rows,
            "has_more": result.preview.has_more,
            "returned_count": result.preview.returned_count,
            "source": result.source,
        }

    def save_source_config(
        self, region_id: int, payload: Mapping[str, Any], current_user: Mapping[str, Any]
    ) -> dict[str, Any]:
        del current_user
        region = self._region(region_id)
        values, row_version = _source_save_payload(payload)
        if values["source_mode"] == "system":
            if not region["system_supported"]:
                raise ValidationError("该数据区域暂不支持系统数据", fields={"source_mode": "不支持系统数据"})
            values.update({"datasource_id": None, "sql_text": None, "tested_signature": None,
                           "tested_at": None, "tested_by": None})
        else:
            source = self._data_source(values["datasource_id"])
            fields = self.storage.list_fields(region_id, include_disabled=False)
            expected_signature = self._sql_executor.signature_for(
                source, values["sql_text"], fields, region["shape"],
            )
            current = self.storage.get_source_config(region_id)
            if current is None or current.get("tested_signature") != expected_signature:
                raise SqlRetestRequiredError()
            values.update({
                "tested_signature": expected_signature,
                "tested_at": current.get("tested_at"),
                "tested_by": current.get("tested_by"),
            })
        try:
            return self.storage.save_source_config(
                region_id,
                values,
                row_version,
                expected_region_version=region["row_version"],
            )
        except SchemaVersionConflictError as error:
            raise SqlRetestRequiredError() from error
        except VersionConflictError as error:
            raise ConflictError() from error

    def _region(self, region_id: int) -> Mapping[str, Any]:
        region = self.storage.get_region(region_id)
        if region is None:
            raise NotFoundError("数据区域不存在")
        return region

    def _data_sources(self) -> list[Any]:
        if self._datasource_loader is not None:
            return list(self._datasource_loader())
        from auto_check.app.storage_config import load_data_sources

        with self.storage.database.connect() as connection:
            return load_data_sources(connection)

    def _data_source(self, datasource_id: str) -> Any:
        for entry in self._data_sources():
            entry_id = entry.get("id") if isinstance(entry, Mapping) else entry.id
            if str(entry_id) == datasource_id:
                if isinstance(entry, Mapping) and "config" not in entry:
                    break
                return entry
        raise ValidationError("数据源不存在或已删除", fields={"datasource_id": "数据源不存在或已删除"})

    def _execute_saved_region(
        self,
        region: Mapping[str, Any],
        fields: list[Mapping[str, Any]],
        *,
        snapshot_enabled: bool = False,
    ) -> QueryPreview:
        source_config = self.storage.get_source_config(int(region["id"]))
        if source_config is None:
            raise ValidationError("数据来源尚未配置")
        source_mode = source_config.get("source_mode")
        if source_mode == "system":
            if not region["system_supported"]:
                raise ValidationError("该数据区域暂不支持系统数据")
            executor = (
                self._snapshot_system_executor
                if snapshot_enabled
                else self._system_executor
            )
            return executor.execute(
                self.storage.database,
                str(region["region_code"]),
                fields,
                str(region["shape"]),
            ).preview
        if source_mode != "sql":
            raise ValidationError("数据来源尚未配置")
        datasource_id = str(source_config.get("datasource_id") or "")
        sql_text = str(source_config.get("sql_text") or "")
        if not datasource_id or not sql_text:
            raise ValidationError("自定义 SQL 尚未完成配置")
        source = self._data_source(datasource_id)
        expected_signature = self._sql_executor.signature_for(
            source, sql_text, fields, str(region["shape"])
        )
        if source_config.get("tested_signature") != expected_signature:
            raise SqlRetestRequiredError()
        executor = self._snapshot_sql_executor if snapshot_enabled else self._sql_executor
        return executor.execute(source, sql_text, fields, str(region["shape"]))


def _test_sql_payload(payload: Mapping[str, Any]) -> tuple[str, str]:
    if not isinstance(payload, Mapping) or set(payload) - {"datasource_id", "sql_text"}:
        raise ValidationError()
    datasource_id = payload.get("datasource_id")
    sql_text = payload.get("sql_text")
    if not isinstance(datasource_id, str) or not datasource_id.strip():
        raise ValidationError("请选择数据源", fields={"datasource_id": "请选择数据源"})
    if not isinstance(sql_text, str) or not sql_text.strip():
        raise ValidationError("请输入 SQL", fields={"sql_text": "请输入 SQL"})
    return datasource_id.strip(), sql_text


def _delete_region_payload(payload: Mapping[str, Any]) -> int:
    if not isinstance(payload, Mapping) or set(payload) != {"row_version"}:
        raise ValidationError()
    row_version = payload.get("row_version")
    if type(row_version) is not int or row_version < 1:
        raise ValidationError("版本号无效", fields={"row_version": "版本号无效"})
    return row_version


def _source_save_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, Mapping):
        raise ValidationError()
    allowed = {"source_mode", "datasource_id", "sql_text", "row_version"}
    if set(payload) - allowed:
        raise ValidationError()
    row_version = payload.get("row_version")
    if type(row_version) is not int or row_version < 1:
        raise ValidationError("版本号无效", fields={"row_version": "版本号无效"})
    source_mode = payload.get("source_mode")
    if source_mode not in {"sql", "system"}:
        raise ValidationError("来源模式无效", fields={"source_mode": "来源模式无效"})
    if source_mode == "system":
        return {"source_mode": "system"}, row_version
    datasource_id, sql_text = _test_sql_payload({
        "datasource_id": payload.get("datasource_id"), "sql_text": payload.get("sql_text"),
    })
    return {"source_mode": "sql", "datasource_id": datasource_id, "sql_text": sql_text}, row_version


def _preview_response(preview: QueryPreview, source_config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "columns": preview.columns,
        "rows": preview.rows,
        "has_more": preview.has_more,
        "returned_count": preview.returned_count,
        "tested_signature": preview.tested_signature,
        "row_version": source_config["row_version"],
    }


def _preview_item(preview: QueryPreview) -> dict[str, Any]:
    return {
        "status": "success",
        "columns": preview.columns,
        "rows": preview.rows,
        "has_more": preview.has_more,
        "returned_count": preview.returned_count,
    }


def _preview_error(error: Exception) -> dict[str, Any]:
    if isinstance(error, DomainError):
        return {
            "status": "error",
            "error": {"code": error.code, "message": error.message},
        }
    if isinstance(error, SnapshotValidationError):
        return {
            "status": "error",
            "error": {"code": "invalid_request", "message": str(error)},
        }
    return {
        "status": "error",
        "error": {"code": "internal_error", "message": "数据读取失败"},
    }


def _snapshot_preview(
    fields: list[Mapping[str, Any]],
    snapshots: list[Mapping[str, Any]],
    *,
    region_code: str,
    request_now: datetime,
) -> QueryPreview:
    columns = tuple(str(field["field_alias"]) for field in fields)
    projected_snapshots = list(snapshots)
    if region_code == QUARTERLY_SPECIAL_PROCESSING:
        current_quarter = (request_now.month - 1) // 3 + 1
        existing_quarters = {
            int(snapshot["period_value"]) for snapshot in projected_snapshots
        }
        projected_snapshots.extend(
            {
                "period_value": quarter,
                "row": {
                    "quarter": f"第{quarter}季度",
                    "special_processing_count": 0,
                },
            }
            for quarter in range(current_quarter + 1, 5)
            if quarter not in existing_quarters
        )
        projected_snapshots.sort(key=lambda snapshot: int(snapshot["period_value"]))
    rows = tuple(
        {alias: snapshot["row"].get(alias) for alias in columns}
        for snapshot in projected_snapshots
    )
    return QueryPreview(
        columns=columns,
        rows=rows,
        has_more=False,
        returned_count=len(rows),
        tested_signature="",
    )


def _latest_snapshot_refresh(snapshots: list[Mapping[str, Any]]) -> str | None:
    refreshed = [
        value
        for snapshot in snapshots
        if (value := snapshot.get("source_refreshed_at")) is not None
    ]
    if not refreshed:
        return None
    return _datetime_text(max(refreshed))


def _snapshot_period_alias(region_code: str) -> str:
    return "quarter" if region_code == "quarterly_special_processing" else "month"


def _datetime_text(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    return str(value)
