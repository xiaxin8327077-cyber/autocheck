from __future__ import annotations

from datetime import datetime, timezone
import secrets
from typing import Any, Callable, Mapping, Sequence

from .catalog import BOARD_CATALOG, BUILTIN_FIELD_SEEDS, BUILTIN_REGION_SEEDS
from .contracts import VersionConflictError
from .storage import DashboardManagementStorage, SchemaVersionConflictError
from .sql_executor import (
    QueryPreview,
    SqlPreviewExecutor,
    validate_readonly_query,
    validate_storable_query,
)
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
    BUSINESS_TIMEZONE,
    QUARTERLY_SPECIAL_PROCESSING,
    REPORT_RECONCILIATION_COMPLETION_TIME,
    SNAPSHOT_REGION_CODES,
    SnapshotValidationError,
    normalize_reconciliation_completion_row,
    normalize_snapshot_rows,
)


class SqlRetestRequiredError(DomainError):
    status = 409
    code = "sql_retest_required"
    message = "SQL、数据源或字段已变化，请重新测试后保存"


class TruncatedResultError(ValueError):
    """完整看板读取到被截断的来源结果时抛出。"""


class SnapshotDataNotReadyError(ValueError):
    """当前年度没有可用的年度快照数据时抛出。"""


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
        self._sql_executor = sql_executor or SqlPreviewExecutor()
        self._board_sql_executor = sql_executor or SqlPreviewExecutor(preview_limit=None)
        self._system_executor = system_executor or SystemDataPreviewExecutor()
        self._board_system_executor = system_executor or SystemDataPreviewExecutor(preview_limit=None)
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
        return self._preview_fixed_board_data(validate_board_code(board_code))

    def preview_external_board_data(self, board_code: str) -> dict[str, Any]:
        try:
            selected = validate_board_code(board_code)
        except ValidationError as error:
            raise NotFoundError("外部看板接口不存在") from error
        return self._preview_fixed_board_data(selected)

    def _preview_fixed_board_data(self, board_code: str) -> dict[str, Any]:
        selected = validate_board_code(board_code)
        board = next(board for board in BOARD_CATALOG if board.code == selected)
        regions = []
        request_now = self._now()
        business_now = _business_datetime(request_now)
        region_seeds = tuple(
            seed for seed in BUILTIN_REGION_SEEDS if seed.board_code == selected
        )
        stored_regions = self.storage.list_regions(selected, include_disabled=False)
        stored_regions_by_code = {
            str(region["region_code"]): region
            for region in stored_regions
            if bool(region.get("built_in"))
        }

        for region_seed in region_seeds:
            region = stored_regions_by_code.get(region_seed.code)
            field_seeds = tuple(
                seed for seed in BUILTIN_FIELD_SEEDS if seed.region_code == region_seed.code
            )
            item = {
                "code": region_seed.code,
                "name": region_seed.name,
                "shape": region_seed.shape,
                "fields": [
                    {
                        "alias": field.alias,
                        "name": field.name,
                        "value_type": field.value_type,
                    }
                    for field in field_seeds
                ],
            }
            if region is None:
                item.update(_preview_error(NotFoundError(
                    "固定数据区域尚未初始化"
                )))
                regions.append(item)
                continue
            stored_fields = self.storage.list_fields(
                region["id"], include_disabled=False
            )
            stored_fields_by_alias = {
                str(field["field_alias"]): field
                for field in stored_fields
                if bool(field.get("built_in"))
            }
            fields = [
                stored_fields_by_alias[field.alias]
                for field in field_seeds
                if field.alias in stored_fields_by_alias
            ]
            if len(fields) != len(field_seeds):
                item.update(_preview_error(ValidationError(
                    "外部接口固定字段配置不完整"
                )))
                regions.append(item)
                continue
            snapshot_enabled = str(region["region_code"]) in SNAPSHOT_REGION_CODES
            period_alias = _snapshot_period_alias(str(region["region_code"]))
            if snapshot_enabled and period_alias not in {
                str(field["field_alias"])
                for field in _source_fields(str(region["region_code"]), fields)
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
                if preview.has_more:
                    raise TruncatedResultError("数据来源未返回完整结果")
                if snapshot_enabled:
                    refreshed_at = request_now
                    normalized = normalize_snapshot_rows(
                        str(region["region_code"]), preview.rows, business_now
                    )
                    if str(region["region_code"]) == QUARTERLY_SPECIAL_PROCESSING:
                        normalized = _with_current_reporting_month_zero(
                            normalized, business_now
                        )
                    snapshots = self.storage.refresh_year_snapshots(
                        int(region["id"]),
                        normalized,
                        period_year=business_now.year,
                        refreshed_at=refreshed_at,
                    )
                    snapshots = _presentation_snapshots(
                        snapshots, str(region["region_code"])
                    )
                    if not snapshots:
                        raise SnapshotDataNotReadyError()
                    preview = _snapshot_preview(
                        fields,
                        snapshots,
                        region_code=str(region["region_code"]),
                        request_now=business_now,
                    )
                    item.update(_preview_item(preview))
                    item.update({
                        "snapshot_status": "fresh",
                        "snapshot_refreshed_at": _latest_snapshot_refresh(snapshots),
                    })
                else:
                    item.update(_preview_item(preview))
            except TruncatedResultError as error:
                item.update(_preview_error(error))
            except (SnapshotValidationError, SnapshotDataNotReadyError) as error:
                item.update(_preview_error(error))
            except Exception as error:
                if (
                    not snapshot_enabled
                    or isinstance(error, ValidationError) and error.fields
                ):
                    item.update(_preview_error(error))
                else:
                    try:
                        fallback = self._snapshot_fallback(
                            region,
                            fields,
                            period_year=business_now.year,
                            request_now=business_now,
                        )
                    except Exception as fallback_error:
                        item.update(_preview_error(fallback_error))
                        regions.append(item)
                        continue
                    if fallback is None:
                        item.update(_preview_error(SnapshotDataNotReadyError()))
                    else:
                        preview, refreshed_at = fallback
                        item.update(_preview_item(preview))
                        item.update({
                            "snapshot_status": "stale",
                            "snapshot_refreshed_at": refreshed_at,
                        })
            regions.append(item)
        return {
            "status": (
                "partial"
                if any(region.get("status") == "error" for region in regions)
                else "success"
            ),
            "generated_at": _datetime_text(request_now),
            "data_year": business_now.year,
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
        snapshots = _presentation_snapshots(
            snapshots, str(region["region_code"])
        )
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
        region_code = str(region.get("region_code") or "")
        preview = self._sql_executor.execute(
            source,
            sql_text,
            _source_fields(region_code, fields),
            region["shape"],
        )
        preview = _project_derived_preview(region_code, preview, fields)
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
        region_code = str(region.get("region_code") or "")
        fields = self.storage.list_fields(region_id, include_disabled=False)
        result = self._system_executor.execute(
            self.storage.database,
            region_code,
            _source_fields(region_code, fields),
            str(region["shape"]),
        )
        preview = _project_derived_preview(region_code, result.preview, fields)
        return {
            "columns": preview.columns,
            "rows": preview.rows,
            "has_more": preview.has_more,
            "returned_count": preview.returned_count,
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
            validate_storable_query(source, values["sql_text"])
            sql_warning = None
            try:
                validate_readonly_query(source, values["sql_text"])
            except ValidationError as error:
                sql_warning = error.message
                expected_signature = None
            else:
                expected_signature = self._sql_executor.signature_for(
                    source,
                    values["sql_text"],
                    _source_fields(str(region.get("region_code") or ""), fields),
                    region["shape"],
                )
            current = self.storage.get_source_config(region_id)
            test_is_current = (
                expected_signature is not None
                and current is not None
                and current.get("tested_signature") == expected_signature
            )
            values.update({
                "tested_signature": expected_signature if test_is_current else None,
                "tested_at": current.get("tested_at") if test_is_current else None,
                "tested_by": current.get("tested_by") if test_is_current else None,
            })
        try:
            saved = self.storage.save_source_config(
                region_id,
                values,
                row_version,
                expected_region_version=region["row_version"],
            )
        except SchemaVersionConflictError as error:
            raise ConflictError() from error
        except VersionConflictError as error:
            raise ConflictError() from error
        if values["source_mode"] == "sql" and sql_warning:
            return {**saved, "sql_warning": sql_warning}
        return saved

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
        region_code = str(region.get("region_code") or "")
        source_fields = _source_fields(region_code, fields)
        if source_mode == "system":
            if not region["system_supported"]:
                raise ValidationError("该数据区域暂不支持系统数据")
            preview = self._board_system_executor.execute(
                self.storage.database,
                region_code,
                source_fields,
                str(region["shape"]),
            ).preview
            return _project_derived_preview(region_code, preview, fields)
        if source_mode != "sql":
            raise ValidationError("数据来源尚未配置")
        datasource_id = str(source_config.get("datasource_id") or "")
        sql_text = str(source_config.get("sql_text") or "")
        if not datasource_id or not sql_text:
            raise ValidationError("自定义 SQL 尚未完成配置")
        source = self._data_source(datasource_id)
        preview = self._board_sql_executor.execute(
            source, sql_text, source_fields, str(region["shape"])
        )
        return _project_derived_preview(region_code, preview, fields)


def _source_fields(
    region_code: str, fields: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    if region_code == QUARTERLY_SPECIAL_PROCESSING:
        return [
            {
                **field,
                "field_alias": "month",
                "name": "报送期月份",
                "description": "内部统计字段。格式：YYYY-MM。",
            }
            if str(field.get("field_alias")) == "quarter" else dict(field)
            for field in fields
        ]
    if region_code != REPORT_RECONCILIATION_COMPLETION_TIME:
        return list(fields)
    return [
        field
        for field in fields
        if str(field.get("field_alias")) != "reconciliation_completed_time"
    ]


def _project_derived_preview(
    region_code: str,
    preview: QueryPreview,
    output_fields: Sequence[Mapping[str, Any]],
) -> QueryPreview:
    if region_code != REPORT_RECONCILIATION_COMPLETION_TIME:
        return preview
    columns = tuple(str(field["field_alias"]) for field in output_fields)
    try:
        rows = tuple(
            {
                alias: normalized.get(alias)
                for alias in columns
            }
            for raw_row in preview.rows
            for normalized in (
                normalize_reconciliation_completion_row(
                    raw_row, allow_legacy_time=False
                ),
            )
        )
    except (TypeError, ValueError) as error:
        raise ValidationError(
            str(error),
            fields={"reconciliation_completed_at": str(error)},
        ) from error
    return QueryPreview(
        columns=columns,
        rows=rows,
        has_more=preview.has_more,
        returned_count=len(rows),
        tested_signature=preview.tested_signature,
    )


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
    if isinstance(error, TruncatedResultError):
        return {
            "status": "error",
            "error": {"code": "truncated_result", "message": "数据来源未返回完整结果"},
        }
    if isinstance(error, SnapshotDataNotReadyError):
        return {
            "status": "error",
            "error": {"code": "data_not_ready", "message": "当前年度数据尚未准备完成"},
        }
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
    if region_code == QUARTERLY_SPECIAL_PROCESSING:
        monthly_snapshots = [
            snapshot for snapshot in snapshots
            if snapshot.get("period_type") == "month"
        ]
        quarter_counts: dict[int, int] = {}
        for snapshot in monthly_snapshots:
            month = int(snapshot["period_value"])
            quarter = (month - 1) // 3 + 1
            count = snapshot["row"].get("special_processing_count")
            quarter_counts[quarter] = quarter_counts.get(quarter, 0) + int(count or 0)
        current_quarter = (request_now.month - 1) // 3 + 1
        projected_snapshots = [
            {
                "period_value": quarter,
                "row": {
                    "quarter": f"第{quarter}季度",
                    "special_processing_count": quarter_counts[quarter],
                },
            }
            for quarter in sorted(quarter_counts)
        ]
        projected_snapshots.extend(
            {
                "period_value": quarter,
                "row": {"quarter": f"第{quarter}季度", "special_processing_count": 0},
            }
            for quarter in range(current_quarter + 1, 5)
            if quarter not in quarter_counts
        )
        projected_snapshots.sort(key=lambda snapshot: int(snapshot["period_value"]))
    else:
        projected_snapshots = list(snapshots)
    rows = tuple(
        {
            alias: normalized.get(alias)
            for alias in columns
        }
        for snapshot in projected_snapshots
        for normalized in (
            normalize_reconciliation_completion_row(
                snapshot["row"], allow_legacy_time=True
            )
            if region_code == REPORT_RECONCILIATION_COMPLETION_TIME
            else dict(snapshot["row"])
        ,)
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
    return "month"


def _with_current_reporting_month_zero(
    rows: tuple[Any, ...], business_now: datetime
) -> tuple[Any, ...]:
    """Mark the current reporting month as zero when its successful query is empty.

    The current reporting period is the preceding calendar month.  This is the
    only automatic zero, so a successful empty query cannot erase historical
    monthly baselines or values outside the active reporting period.
    """
    if business_now.month == 1:
        # The current year's system query intentionally does not include the
        # prior December.  Never infer a zero that could overwrite its stored
        # actual result.
        return rows
    year = business_now.year
    month = business_now.month - 1
    if year == 2026 and month <= 7:
        return rows
    if any(row.period_year == year and row.period_value == month for row in rows):
        return rows
    from .year_snapshots import SnapshotRow
    return (*rows, SnapshotRow(year, "month", month, {
        "month": f"{year:04d}-{month:02d}",
        "special_processing_count": 0,
    }))


def _presentation_snapshots(
    snapshots: list[Mapping[str, Any]], region_code: str
) -> list[Mapping[str, Any]]:
    if region_code != QUARTERLY_SPECIAL_PROCESSING:
        return snapshots
    return [
        snapshot for snapshot in snapshots
        if snapshot.get("period_type") == "month"
    ]


def _datetime_text(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    return str(value)


def _business_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(BUSINESS_TIMEZONE).replace(tzinfo=None)
