from __future__ import annotations

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
    ) -> None:
        self.storage = storage
        self._datasource_loader = datasource_loader
        self._sql_executor = sql_executor or SqlPreviewExecutor()
        self._system_executor = system_executor or SystemDataPreviewExecutor()

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
        for region in self.storage.list_regions(selected, include_disabled=False):
            fields = self.storage.list_fields(region["id"], include_disabled=False)
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
            try:
                preview = self._execute_saved_region(region, fields)
                item.update({
                    "status": "success",
                    "columns": preview.columns,
                    "rows": preview.rows,
                    "has_more": preview.has_more,
                    "returned_count": preview.returned_count,
                })
            except DomainError as error:
                item.update({
                    "status": "error",
                    "error": {"code": error.code, "message": error.message},
                })
            except Exception:
                item.update({
                    "status": "error",
                    "error": {"code": "internal_error", "message": "数据读取失败"},
                })
            regions.append(item)
        return {
            "board": {"code": board.code, "name": board.name},
            "regions": regions,
        }

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
        self, region: Mapping[str, Any], fields: list[Mapping[str, Any]]
    ) -> QueryPreview:
        source_config = self.storage.get_source_config(int(region["id"]))
        if source_config is None:
            raise ValidationError("数据来源尚未配置")
        source_mode = source_config.get("source_mode")
        if source_mode == "system":
            if not region["system_supported"]:
                raise ValidationError("该数据区域暂不支持系统数据")
            return self._system_executor.execute(
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
        return self._sql_executor.execute(source, sql_text, fields, str(region["shape"]))


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
