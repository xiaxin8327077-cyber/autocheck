"""Versioned read-only access to configured business data sources."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from threading import RLock
from typing import Any, Callable, Iterator, Mapping

from auto_check.app.config import DataSourceConfig, DataSourceEntry
from auto_check.app.module_system.services import BoundService, PlatformServiceSpec
from auto_check.app.storage_config import load_data_sources

DATA_SOURCE_SERVICE = "platform.data_sources"
DATA_SOURCE_VERSION = 1
_CLOSED_FACADE_ERROR = "platform service facade is closed"
_POLICY_DENIED = "SQL_POLICY_DENIED"
_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"

_ALLOWED_DIALECTS = frozenset({"mysql", "postgresql"})
_WRITE_WORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "truncate",
    "alter",
    "create",
    "grant",
    "revoke",
    "merge",
    "call",
    "copy",
    "replace",
    "into",
    "outfile",
    "dumpfile",
)
_DANGEROUS_FUNCTIONS = (
    "pg_read_file",
    "pg_sleep",
    "sleep",
    "benchmark",
    "load_file",
    "lo_import",
    "dblink",
)
_LOCK_PHRASES = ("for update", "for share", "lock in share mode")

SourceQuery = Callable[
    [DataSourceConfig, str, Mapping[str, Any], float, int],
    tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]],
]


@dataclass(frozen=True)
class PublicDataSource:
    id: str
    name: str
    dialect: str
    database_name: str
    schema_name: str


@dataclass(frozen=True)
class SelectResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool


class _DataSourceFacade:
    def __init__(self, application_database: Any, connector: SourceQuery) -> None:
        self._database = application_database
        self._connector = connector
        self._closed = False
        self._lock = RLock()

    def __repr__(self) -> str:
        return f"DataSourceFacade(closed={self._closed})"

    def list_sources(self) -> tuple[PublicDataSource, ...]:
        with self._lock:
            self._require_open()
            return tuple(self._public_source(entry) for entry in self._load_sources())

    def list_tables(
        self,
        source_id: str,
        *,
        keyword: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        with self._lock:
            self._require_open()
            source = self._require_source(source_id)
            safe_page = max(int(page), 1)
            safe_page_size = min(max(int(page_size), 1), 100)
            schema_name = _schema_name(source.config)
            count_sql, count_params = _table_count_sql(source.config, schema_name, keyword)
            _columns, count_rows = self._connector(
                source.config, count_sql, count_params, 10, 1
            )
            total = int(count_rows[0][0]) if count_rows else 0
            list_sql, list_params = _table_page_sql(
                source.config,
                schema_name,
                keyword,
                limit=safe_page_size,
                offset=(safe_page - 1) * safe_page_size,
            )
            columns, rows = self._connector(
                source.config, list_sql, list_params, 10, safe_page_size
            )
            items = []
            for row in rows:
                record = dict(zip(columns, row))
                items.append(
                    {
                        "schema_name": schema_name,
                        "table_name": str(record["table_name"]),
                        "comment": str(record.get("comment") or ""),
                    }
                )
            return {
                "items": items,
                "total": total,
                "page": safe_page,
                "page_size": safe_page_size,
            }

    def describe_table(self, source_id: str, table_name: str) -> dict[str, Any]:
        with self._lock:
            self._require_open()
            source = self._require_source(source_id)
            physical_name = str(table_name or "").strip()
            if not physical_name:
                raise ValueError(_SOURCE_UNAVAILABLE)
            sql, params = _column_sql(source.config, physical_name)
            columns, rows = self._connector(source.config, sql, params, 10, 10000)
            described = [_column_record(dict(zip(columns, row))) for row in rows]
            return {
                "mapping_version": _mapping_version(described),
                "columns": described,
            }

    def execute_select(
        self,
        source_id: str,
        sql: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float,
        max_rows: int,
    ) -> SelectResult:
        with self._lock:
            self._require_open()
            ensure_readonly_sql(sql)
            if int(max_rows) < 1:
                raise ValueError("VALIDATION_ERROR")
            source = self._require_source(source_id)
            fetch_limit = int(max_rows) + 1
            columns, rows = self._connector(
                source.config,
                sql,
                dict(params),
                float(timeout_seconds),
                fetch_limit,
            )
            truncated = len(rows) > int(max_rows)
            return SelectResult(
                columns=tuple(columns),
                rows=tuple(rows[: int(max_rows)]),
                truncated=truncated,
            )

    def _load_sources(self) -> list[DataSourceEntry]:
        with self._database.connect() as connection:
            entries = load_data_sources(connection)
        return [
            entry
            for entry in entries
            if str(entry.config.db_type) in _ALLOWED_DIALECTS
        ]

    def _require_source(self, source_id: str) -> DataSourceEntry:
        wanted = str(source_id or "")
        for entry in self._load_sources():
            if entry.id == wanted:
                return entry
        raise ValueError(_SOURCE_UNAVAILABLE)

    def _public_source(self, entry: DataSourceEntry) -> PublicDataSource:
        return PublicDataSource(
            id=entry.id,
            name=entry.name,
            dialect=str(entry.config.db_type),
            database_name=entry.config.database,
            schema_name=entry.config.schema,
        )

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError(_CLOSED_FACADE_ERROR)

    def _close(self) -> None:
        with self._lock:
            self._closed = True


def create_data_source_service(
    application_database: Any,
    *,
    connector: SourceQuery | None = None,
) -> PlatformServiceSpec:
    """Create the v1 read-only data-source platform service."""

    query = connector or query_business_source

    def bind(_owner: str) -> BoundService:
        facade = _DataSourceFacade(application_database, query)
        return BoundService(value=facade, close=facade._close)

    return PlatformServiceSpec(
        name=DATA_SOURCE_SERVICE,
        version=DATA_SOURCE_VERSION,
        binder=bind,
    )


def ensure_readonly_sql(sql: str) -> None:
    """Reject anything other than one read-only SELECT or WITH query."""

    stripped = _strip_comments_and_strings(str(sql or "")).strip()
    if not stripped:
        raise ValueError(_POLICY_DENIED)
    if stripped.endswith(";"):
        stripped = stripped[:-1].strip()
    if ";" in stripped:
        raise ValueError(_POLICY_DENIED)
    first = stripped.split(None, 1)[0].lower()
    if first not in {"select", "with"}:
        raise ValueError(_POLICY_DENIED)
    lowered = stripped.lower()
    if any(phrase in lowered for phrase in _LOCK_PHRASES):
        raise ValueError(_POLICY_DENIED)
    for word in (*_WRITE_WORDS, *_DANGEROUS_FUNCTIONS):
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            raise ValueError(_POLICY_DENIED)


def query_business_source(
    config: DataSourceConfig,
    sql: str,
    params: Mapping[str, Any],
    timeout_seconds: float,
    max_rows: int,
) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    bound_sql, bound_params = _bind_named_params(sql, params)
    with _connect(config, timeout_seconds) as connection:
        cursor = connection.cursor()
        try:
            _apply_timeout(cursor, config, timeout_seconds)
            cursor.execute(bound_sql, bound_params)
            description = cursor.description or []
            columns = tuple(str(column[0]) for column in description)
            fetched = tuple(cursor.fetchmany(max_rows))
            return columns, fetched
        finally:
            cursor.close()


def _bind_named_params(sql: str, params: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
    values: list[Any] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            raise ValueError("VALIDATION_ERROR")
        values.append(params[name])
        return "\x00"

    tokenized = re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", replace, sql)
    escaped = tokenized.replace("%", "%%").replace("\x00", "%s")
    return escaped, tuple(values)


def _strip_comments_and_strings(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", " ", without_block)
    return re.sub(r"('([^']|'')*'|\"([^\"]|\"\")*\")", "''", without_line)


def _schema_name(config: DataSourceConfig) -> str:
    if config.db_type == "postgresql":
        return config.schema or "public"
    return config.schema or config.database


def _keyword_params(keyword: str) -> tuple[str, str]:
    text = str(keyword or "").strip()
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return text, f"%{escaped}%"


def _table_count_sql(
    config: DataSourceConfig, schema_name: str, keyword: str
) -> tuple[str, dict[str, Any]]:
    raw, pattern = _keyword_params(keyword)
    if config.db_type == "mysql":
        sql = (
            "SELECT COUNT(*) AS total FROM information_schema.TABLES t "
            "WHERE t.TABLE_SCHEMA = :schema_name AND t.TABLE_TYPE = 'BASE TABLE' "
            "AND (:keyword = '' OR t.TABLE_NAME LIKE :pattern OR t.TABLE_COMMENT LIKE :pattern)"
        )
    else:
        sql = (
            "SELECT COUNT(*) AS total FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0 "
            "WHERE n.nspname = :schema_name AND c.relkind IN ('r', 'p') "
            "AND (:keyword = '' OR c.relname ILIKE :pattern OR COALESCE(d.description, '') ILIKE :pattern)"
        )
    return sql, {"schema_name": schema_name, "keyword": raw, "pattern": pattern}


def _table_page_sql(
    config: DataSourceConfig,
    schema_name: str,
    keyword: str,
    *,
    limit: int,
    offset: int,
) -> tuple[str, dict[str, Any]]:
    raw, pattern = _keyword_params(keyword)
    params = {
        "schema_name": schema_name,
        "keyword": raw,
        "pattern": pattern,
        "limit": limit,
        "offset": offset,
    }
    if config.db_type == "mysql":
        sql = (
            "SELECT t.TABLE_NAME AS table_name, COALESCE(t.TABLE_COMMENT, '') AS comment "
            "FROM information_schema.TABLES t "
            "WHERE t.TABLE_SCHEMA = :schema_name AND t.TABLE_TYPE = 'BASE TABLE' "
            "AND (:keyword = '' OR t.TABLE_NAME LIKE :pattern OR t.TABLE_COMMENT LIKE :pattern) "
            "ORDER BY t.TABLE_NAME LIMIT :limit OFFSET :offset"
        )
    else:
        sql = (
            "SELECT c.relname AS table_name, COALESCE(d.description, '') AS comment "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0 "
            "WHERE n.nspname = :schema_name AND c.relkind IN ('r', 'p') "
            "AND (:keyword = '' OR c.relname ILIKE :pattern "
            "OR COALESCE(d.description, '') ILIKE :pattern) "
            "ORDER BY c.relname LIMIT :limit OFFSET :offset"
        )
    return sql, params


def _column_sql(config: DataSourceConfig, table_name: str) -> tuple[str, dict[str, Any]]:
    params = {"schema_name": _schema_name(config), "table_name": table_name}
    if config.db_type == "mysql":
        sql = (
            "SELECT c.COLUMN_NAME AS column_name, c.DATA_TYPE AS data_type, "
            "COALESCE(c.COLUMN_COMMENT, '') AS comment, c.IS_NULLABLE AS nullable "
            "FROM information_schema.COLUMNS c "
            "WHERE c.TABLE_SCHEMA = :schema_name AND c.TABLE_NAME = :table_name "
            "ORDER BY c.ORDINAL_POSITION"
        )
    else:
        sql = (
            "SELECT a.attname AS column_name, "
            "pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type, "
            "COALESCE(d.description, '') AS comment, "
            "CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS nullable "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_description d ON d.objoid = a.attrelid AND d.objsubid = a.attnum "
            "WHERE n.nspname = :schema_name AND c.relname = :table_name "
            "AND a.attnum > 0 AND NOT a.attisdropped "
            "ORDER BY a.attnum"
        )
    return sql, params


def _column_record(record: Mapping[str, Any]) -> dict[str, Any]:
    nullable = record.get("nullable")
    return {
        "column_name": str(record.get("column_name") or ""),
        "data_type": str(record.get("data_type") or ""),
        "comment": str(record.get("comment") or ""),
        "nullable": nullable is True or str(nullable).upper() == "YES",
    }


def _mapping_version(columns: list[dict[str, Any]]) -> str:
    payload = json.dumps(columns, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


@contextmanager
def _connect(config: DataSourceConfig, timeout_seconds: float) -> Iterator[Any]:
    timeout = max(int(timeout_seconds), 1)
    if config.db_type == "postgresql":
        import psycopg

        connection = psycopg.connect(
            host=config.host,
            port=config.port,
            dbname=config.database,
            user=config.username,
            password=config.password,
            connect_timeout=timeout,
        )
    elif config.db_type == "mysql":
        import pymysql

        connection = pymysql.connect(
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.username,
            password=config.password,
            charset="utf8mb4",
            connect_timeout=timeout,
            read_timeout=timeout,
            write_timeout=timeout,
        )
    else:
        raise ValueError(_SOURCE_UNAVAILABLE)
    try:
        yield connection
    finally:
        connection.close()


def _apply_timeout(cursor: Any, config: DataSourceConfig, timeout_seconds: float) -> None:
    milliseconds = max(int(float(timeout_seconds) * 1000), 1)
    if config.db_type == "postgresql":
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", (str(milliseconds),))
        cursor.execute("SELECT set_config('search_path', %s, true)", (_schema_name(config),))
        return
    cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={milliseconds}")
