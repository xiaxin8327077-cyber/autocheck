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
    # Most SQL can be validated before connecting. Only backslash-bearing queries
    # need the active session's rules for the ends of quoted strings.
    bound = None if "\\" in sql else _bind_named_params(sql, params, config.db_type)
    with _connect(config, timeout_seconds) as connection:
        cursor = connection.cursor()
        try:
            _apply_timeout(cursor, config, timeout_seconds)
            if bound is None:
                if config.db_type == "mysql":
                    cursor.execute("SELECT @@SESSION.sql_mode")
                    modes = set(cursor.fetchone()[0].split(","))
                    bound = _bind_named_params(sql, params, config.db_type,
                        backslash_strings="NO_BACKSLASH_ESCAPES" not in modes, ansi_quotes="ANSI_QUOTES" in modes)
                else:
                    standard = connection.info.parameter_status("standard_conforming_strings")
                    bound = _bind_named_params(sql, params, config.db_type, backslash_strings=standard == "off")
            cursor.execute(*bound)
            description = cursor.description or []
            columns = tuple(str(column[0]) for column in description)
            fetched = tuple(cursor.fetchmany(max_rows))
            return columns, fetched
        finally:
            cursor.close()


def _quoted_end(sql: str, start: int, *, backslash: bool) -> int:
    quote = sql[start]
    i = start + 1
    while i < len(sql):
        if backslash and sql[i] == "\\":
            i += 2
        elif sql[i] != quote:
            i += 1
        elif sql.startswith(quote * 2, i):
            i += 2
        else:
            return i + 1
    raise ValueError("VALIDATION_ERROR")


_BIND_NAME = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")
# PostgreSQL dollar tags follow identifier rules and may contain non-ASCII characters.
_DOLLAR_TAG = r"(?<![\w$\x80-\U0010ffff])\$(?:[A-Za-z_\x80-\U0010ffff][A-Za-z0-9_\x80-\U0010ffff]*)?\$"
_BIND_TOKEN = re.compile(_BIND_NAME.pattern + r"""|['"\x60#]|--|/\*|""" + _DOLLAR_TAG)
_COMMENT_TOKEN = re.compile(r"/\*|\*/")
_PG_LINE_END = re.compile(r"[\r\n]")
_PG_ESCAPE_STRING = re.compile(r"(?<![\w$\x80-\U0010ffff])[Ee]'")
_PG_QUOTE_CONTINUATION = re.compile(r"(?:[ \t\f\v]|--[^\r\n]*)*[\r\n](?:[ \t\f\v\r\n]|--[^\r\n]*)*'")


def _block_comment_end(sql: str, start: int, postgres: bool) -> int:
    if postgres:
        depth = 1
        for mark in _COMMENT_TOKEN.finditer(sql, start + 2):
            depth += 1 if mark[0] == "/*" else -1
            if not depth:
                return mark.end()
    else:
        end = sql.find("*/", start + 2)
        if end >= 0:
            if sql.startswith("/*!", start) and _BIND_NAME.search(sql, start + 3, end):
                # MySQL may execute versioned comments. Never silently drop a parameter.
                raise ValueError("VALIDATION_ERROR")
            return end + 2
    raise ValueError("VALIDATION_ERROR")


def _bind_named_params(
    sql: str, params: Mapping[str, Any], dialect: str = "mysql", *,
    backslash_strings: bool | None = None, ansi_quotes: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    postgres = dialect == "postgresql"
    if backslash_strings is None:
        backslash_strings = not postgres
    chunks: list[str] = []
    values: list[Any] = []
    start = i = 0
    while match := _BIND_TOKEN.search(sql, i):
        at = match.start()
        token = match[0]
        i = match.end()
        if name := match[1]:
            if name not in params:
                raise ValueError("VALIDATION_ERROR")
            chunks.extend((sql[start:at].replace("%", "%%"), "%s"))
            values.append(params[name])
            start = i
        elif token in ("'", '"') or (not postgres and token == "`"):
            escape_prefix = postgres and at > 0 and bool(_PG_ESCAPE_STRING.match(sql, at - 1))
            string_quote = token == "'" or (token == '"' and not postgres and not ansi_quotes)
            i = _quoted_end(sql, at, backslash=string_quote and (backslash_strings or escape_prefix))
            if escape_prefix:
                # Newline-separated continuations inherit E-string backslash rules.
                while continuation := _PG_QUOTE_CONTINUATION.match(sql, i):
                    i = _quoted_end(sql, continuation.end() - 1, backslash=True)
        elif token == "/*":
            i = _block_comment_end(sql, at, postgres)
        elif token == "--" or (token == "#" and not postgres):
            if not postgres and token == "--" and i < len(sql) and ord(sql[i]) > 32 and sql[i] != "\x7f":
                i = at + 1  # A second minus can start the next operator or a comment.
                continue
            if postgres:
                newline = _PG_LINE_END.search(sql, i)
                i = newline.end() if newline else len(sql)
            else:
                newline_at = sql.find("\n", i)
                i = len(sql) if newline_at < 0 else newline_at + 1
        elif postgres and token.startswith("$"):
            end = sql.find(token, i)
            if end < 0:
                raise ValueError("VALIDATION_ERROR")
            i = end + len(token)
    chunks.append(sql[start:].replace("%", "%%"))
    return "".join(chunks), tuple(values)


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
