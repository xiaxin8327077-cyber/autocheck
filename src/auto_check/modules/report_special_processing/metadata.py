"""数据源元数据适配层：读取系统已配置数据源的真实表/字段与中文注释。

- 数据源只允许来自系统已配置列表（app.storage_config.load_data_sources），
  本模块绝不接受用户提交的 IP/端口/账号/密码/连接串。
- PostgreSQL / MySQL 的元数据 SQL 差异只在本文件内适配，前端只消费统一结构：
  表 {schema, table_name, table_comment}；字段 {column_name, column_comment, data_type}。
- 表与字段查询一律后端搜索 + 后端分页，不整库返回。
- 连接与读取异常统一脱敏为固定文案，不泄露驱动信息。
"""

from __future__ import annotations

import logging
from typing import Any

from auto_check.app.db import DatabaseClient

from .contracts import DataSourceConnectionError, DataSourceMetadataError, ValidationError

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
DEFAULT_TABLE_PAGE_SIZE = 20
DEFAULT_COLUMN_PAGE_SIZE = 50

_TABLES_MYSQL = (
    "SELECT t.TABLE_NAME AS table_name, COALESCE(t.TABLE_COMMENT, '') AS table_comment "
    "FROM information_schema.TABLES t "
    "WHERE t.TABLE_SCHEMA = %s AND t.TABLE_TYPE = 'BASE TABLE' "
    "AND (%s = '' OR t.TABLE_NAME LIKE %s OR t.TABLE_COMMENT LIKE %s) "
    "ORDER BY t.TABLE_NAME LIMIT %s OFFSET %s"
)
_TABLES_COUNT_MYSQL = (
    "SELECT COUNT(*) AS total FROM information_schema.TABLES t "
    "WHERE t.TABLE_SCHEMA = %s AND t.TABLE_TYPE = 'BASE TABLE' "
    "AND (%s = '' OR t.TABLE_NAME LIKE %s OR t.TABLE_COMMENT LIKE %s)"
)
_COLUMNS_MYSQL = (
    "SELECT c.COLUMN_NAME AS column_name, COALESCE(c.COLUMN_COMMENT, '') AS column_comment, "
    "c.DATA_TYPE AS data_type "
    "FROM information_schema.COLUMNS c "
    "WHERE c.TABLE_SCHEMA = %s AND c.TABLE_NAME = %s "
    "AND (%s = '' OR c.COLUMN_NAME LIKE %s OR c.COLUMN_COMMENT LIKE %s) "
    "ORDER BY c.ORDINAL_POSITION LIMIT %s OFFSET %s"
)
_COLUMNS_COUNT_MYSQL = (
    "SELECT COUNT(*) AS total FROM information_schema.COLUMNS c "
    "WHERE c.TABLE_SCHEMA = %s AND c.TABLE_NAME = %s "
    "AND (%s = '' OR c.COLUMN_NAME LIKE %s OR c.COLUMN_COMMENT LIKE %s)"
)
_TABLES_PG = (
    "SELECT c.relname AS table_name, COALESCE(d.description, '') AS table_comment "
    "FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0 "
    "WHERE n.nspname = %s AND c.relkind IN ('r', 'p') "
    "AND (%s = '' OR c.relname ILIKE %s OR COALESCE(d.description, '') ILIKE %s) "
    "ORDER BY c.relname LIMIT %s OFFSET %s"
)
_TABLES_COUNT_PG = (
    "SELECT COUNT(*) AS total FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0 "
    "WHERE n.nspname = %s AND c.relkind IN ('r', 'p') "
    "AND (%s = '' OR c.relname ILIKE %s OR COALESCE(d.description, '') ILIKE %s)"
)
_COLUMNS_PG = (
    "SELECT a.attname AS column_name, COALESCE(d.description, '') AS column_comment, "
    "pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type "
    "FROM pg_attribute a "
    "JOIN pg_class c ON c.oid = a.attrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "LEFT JOIN pg_description d ON d.objoid = a.attrelid AND d.objsubid = a.attnum "
    "WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped "
    "AND (%s = '' OR a.attname ILIKE %s OR COALESCE(d.description, '') ILIKE %s) "
    "ORDER BY a.attnum LIMIT %s OFFSET %s"
)
_COLUMNS_COUNT_PG = (
    "SELECT COUNT(*) AS total FROM pg_attribute a "
    "JOIN pg_class c ON c.oid = a.attrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "LEFT JOIN pg_description d ON d.objoid = a.attrelid AND d.objsubid = a.attnum "
    "WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped "
    "AND (%s = '' OR a.attname ILIKE %s OR COALESCE(d.description, '') ILIKE %s)"
)


class DatasourceMetadataService:
    """基于应用库中已配置的数据源提供表/字段元数据查询。"""

    def __init__(self, application_database: Any) -> None:
        self.database = application_database

    def list_datasources(self) -> list[dict[str, str]]:
        from auto_check.app.storage_config import load_data_sources

        with self.database.connect() as connection:
            entries = load_data_sources(connection)
        return [
            {
                "id": entry.id,
                "name": entry.name,
                "db_type": str(entry.config.db_type),
                "database": str(entry.config.database or ""),
                "schema": str(entry.config.schema or ""),
            }
            for entry in entries
        ]

    def resolve(self, datasource_id: str):
        from auto_check.app.storage_config import load_data_sources

        wanted = str(datasource_id or "").strip()
        if not wanted:
            return None
        with self.database.connect() as connection:
            for entry in load_data_sources(connection):
                if entry.id == wanted:
                    return entry
        return None

    def list_tables(self, datasource_id: str, *, keyword: str = "", page: int = 1, page_size: int = DEFAULT_TABLE_PAGE_SIZE) -> dict[str, Any]:
        return self._query(
            datasource_id,
            keyword=keyword, page=page, page_size=page_size,
            sql_by_dialect=("TABLES", "table", ("table_name", "table_comment", "schema")),
            column_error="表信息获取失败，请稍后重试",
        )

    def list_columns(self, datasource_id: str, table_name: str, *, keyword: str = "", page: int = 1, page_size: int = DEFAULT_COLUMN_PAGE_SIZE) -> dict[str, Any]:
        table = str(table_name or "").strip()
        if not table or len(table) > 128:
            raise ValidationError(fields={"table_name": "处理表名无效"})
        return self._query(
            datasource_id,
            keyword=keyword, page=page, page_size=page_size,
            sql_by_dialect=("COLUMNS", table, ("column_name", "column_comment", "data_type")),
            column_error="字段信息获取失败，请稍后重试",
        )

    # ===== 内部实现 =====

    def _query(self, datasource_id: str, *, keyword: str, page: int, page_size: int,
               sql_by_dialect, column_error: str) -> dict[str, Any]:
        entry = self.resolve(datasource_id)
        if entry is None:
            raise ValidationError(fields={"datasource_id": "数据源不存在或已被删除，请在系统配置中维护后重试"})
        dialect = self._dialect(entry.config.db_type)
        scope = self._scope(entry.config, dialect)
        keyword = str(keyword or "").strip()[:100]
        page = max(1, int(page or 1))
        page_size = min(MAX_PAGE_SIZE, max(1, int(page_size or 20)))
        offset = (page - 1) * page_size
        like = f"%{keyword}%"
        kind, bound_target, fields = sql_by_dialect

        client = DatabaseClient(entry.config, connect_timeout_seconds=8)
        try:
            client.test_connection()
        except Exception as exc:  # noqa: BLE001 - 统一脱敏
            logger.warning("datasource %s connection failed: %s", datasource_id, type(exc).__name__)
            raise DataSourceConnectionError() from None

        sql, count_sql, params = self._build(dialect, kind, scope, bound_target, keyword, like, page_size, offset)
        try:
            total_row = client.fetch_one(count_sql, params["count"])
            rows = client.fetch_all(sql, params["page"])
        except Exception as exc:  # noqa: BLE001 - 统一脱敏
            logger.warning("datasource %s metadata read failed: %s", datasource_id, type(exc).__name__)
            raise DataSourceMetadataError(message=column_error) from None
        total = int((total_row or {}).get("total") or 0)
        items = [{field: str(row.get(field) if row.get(field) is not None else "") for field in fields} for row in rows]
        if kind == "TABLES":
            # 每行附带 schema，供前端保存到结构化内容（数据库/架构定位）。
            for item in items:
                item["schema"] = scope
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "schema": scope,
        }

    @staticmethod
    def _dialect(db_type: Any) -> str:
        value = str(db_type or "").strip().lower()
        if value == "postgresql":
            return "pg"
        if value == "mysql":
            return "mysql"
        raise ValidationError(fields={"datasource_id": "该数据源类型暂不支持表/字段元数据读取（当前支持 PostgreSQL / MySQL）"})

    @staticmethod
    def _scope(config: Any, dialect: str) -> str:
        return str(config.schema or (config.database if dialect == "mysql" else "public") or "").strip()

    @staticmethod
    def _build(dialect: str, kind: str, scope: str, target: str, keyword: str, like: str,
               page_size: int, offset: int):
        if kind == "TABLES":
            if dialect == "pg":
                sql, count_sql = _TABLES_PG, _TABLES_COUNT_PG
            else:
                sql, count_sql = _TABLES_MYSQL, _TABLES_COUNT_MYSQL
            page_params = (scope, keyword, like, like, page_size, offset)
            count_params = (scope, keyword, like, like)
        else:
            if dialect == "pg":
                sql, count_sql = _COLUMNS_PG, _COLUMNS_COUNT_PG
            else:
                sql, count_sql = _COLUMNS_MYSQL, _COLUMNS_COUNT_MYSQL
            page_params = (scope, target, keyword, like, like, page_size, offset)
            count_params = (scope, target, keyword, like, like)
        return sql, count_sql, {"page": page_params, "count": count_params}
