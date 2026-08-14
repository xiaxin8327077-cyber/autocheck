from __future__ import annotations

from contextlib import contextmanager
import re
from typing import Any, Callable, Iterable, Iterator

from auto_check.app.config import DataSourceConfig
from auto_check.app.pbc_import import TableColumn, TableRef


def ensure_select_only(sql: str) -> None:
    normalized = sql.lstrip().lower()
    if not (normalized.startswith("select") or normalized.startswith("with")):
        raise ValueError("Only SELECT queries are allowed")
    if ";" in normalized.rstrip(";") or _WRITE_KEYWORD_RE.search(_strip_string_literals(normalized)):
        raise ValueError("Only SELECT queries are allowed")


_WRITE_KEYWORD_RE = re.compile(r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|merge|call|copy)\b")


def _strip_string_literals(sql: str) -> str:
    return re.sub(r"('([^']|'')*'|\"([^\"]|\"\")*\")", "''", sql)


def qualified_name(config: DataSourceConfig, table_name: str) -> str:
    if config.db_type == "postgresql":
        schema = config.schema or "public"
        return f"{_quote_pg(schema)}.{_quote_pg(table_name)}"
    if config.db_type == "mysql":
        database = config.schema or config.database
        return f"{_quote_mysql(database)}.{_quote_mysql(table_name)}" if database else _quote_mysql(table_name)
    raise ValueError(f"Unsupported database type: {config.db_type}")


def quote_identifier(db_type: str, identifier: str) -> str:
    value = str(identifier or "")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", value):
        raise ValueError(f"非法标识符：{value}")
    return _quote_identifier(db_type, value)


def build_insert_sql(db_type: str, table: TableRef, columns: list[str]) -> str:
    if not columns:
        raise ValueError("at least one column is required")
    quoted_columns = ", ".join(_quote_identifier(db_type, column) for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {table.quoted(db_type)} ({quoted_columns}) VALUES ({placeholders})"


def build_clear_table_sql(db_type: str, table: TableRef) -> str:
    return f"TRUNCATE TABLE {table.quoted(db_type)}"


class DatabaseClient:
    def __init__(
        self,
        config: DataSourceConfig,
        *,
        query_logger: Callable[[str], None] | None = None,
        connect_timeout_seconds: int | None = None,
    ):
        self.config = config
        self.query_logger = query_logger
        self.connect_timeout_seconds = connect_timeout_seconds

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        ensure_select_only(sql)
        bound_params = tuple(params)
        if self.query_logger is not None:
            schema_text = f"，schema={self.config.schema}" if self.config.schema else ""
            self.query_logger(
                f"数据库={self.config.db_type}://{self.config.host}:{self.config.port}/{self.config.database}"
                f"{schema_text}\nSQL:\n{sql.strip()}\n参数={bound_params!r}"
            )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(self._sql_for_driver(sql), bound_params)
                columns = [column[0].lower() for column in cursor.description or []]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def test_connection(self) -> None:
        self.fetch_one("SELECT 1 AS ok")

    def clear_table(self, table: TableRef) -> None:
        table = _table_ref_for_write(self.config, table)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(build_clear_table_sql(self.config.db_type, table))
            connection.commit()

    def insert_rows(self, table: TableRef, columns: list[str], rows: list[tuple[Any, ...]]) -> int:
        if not rows:
            return 0
        return self.insert_row_batches(table, columns, rows)

    def insert_row_batches(
        self,
        table: TableRef,
        columns: list[str],
        rows: Iterable[tuple[Any, ...]],
        *,
        batch_size: int = 10000,
        on_batch: Callable[[int], None] | None = None,
    ) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        table = _table_ref_for_write(self.config, table)
        sql = build_insert_sql(self.config.db_type, table, columns)
        inserted = 0
        batch: list[tuple[Any, ...]] = []
        with self._connect() as connection:
            try:
                with connection.cursor() as cursor:
                    for row in rows:
                        batch.append(row)
                        if len(batch) >= batch_size:
                            cursor.executemany(sql, batch)
                            inserted += len(batch)
                            batch = []
                            if on_batch:
                                on_batch(inserted)
                    if batch:
                        cursor.executemany(sql, batch)
                        inserted += len(batch)
                        if on_batch:
                            on_batch(inserted)
                connection.commit()
            except Exception:
                rollback = getattr(connection, "rollback", None)
                if callable(rollback):
                    rollback()
                raise
        return inserted

    def table_columns(self, table: TableRef) -> list[TableColumn]:
        schema, table_name = _table_schema_and_name(self.config, table)
        if self.config.db_type == "postgresql":
            rows = self.fetch_all(
                """
                SELECT c.column_name,
                       COALESCE(col_description((quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass::oid, c.ordinal_position), '') AS column_comment
                FROM information_schema.columns c
                WHERE c.table_schema = %s AND c.table_name = %s
                ORDER BY c.ordinal_position
                """,
                (schema, table_name),
            )
        elif self.config.db_type == "mysql":
            rows = self.fetch_all(
                """
                SELECT column_name, COALESCE(column_comment, '') AS column_comment
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema, table_name),
            )
        else:
            raise ValueError(f"Unsupported database type: {self.config.db_type}")
        if not rows:
            raise ValueError(f"target table {table.quoted(self.config.db_type)} has no readable columns")
        return [TableColumn(str(row.get("column_name", "")), str(row.get("column_comment", "") or "")) for row in rows]

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self.config.db_type == "postgresql":
            import psycopg

            connect_kwargs: dict[str, Any] = {
                "host": self.config.host,
                "port": self.config.port,
                "dbname": self.config.database,
                "user": self.config.username,
                "password": self.config.password,
            }
            if self.connect_timeout_seconds is not None:
                connect_kwargs["connect_timeout"] = self.connect_timeout_seconds
            connection = psycopg.connect(**connect_kwargs)
        elif self.config.db_type == "mysql":
            import pymysql

            connect_kwargs = {
                "host": self.config.host,
                "port": self.config.port,
                "database": self.config.database,
                "user": self.config.username,
                "password": self.config.password,
                "charset": "utf8mb4",
            }
            if self.connect_timeout_seconds is not None:
                connect_kwargs.update(
                    connect_timeout=self.connect_timeout_seconds,
                    read_timeout=self.connect_timeout_seconds,
                    write_timeout=self.connect_timeout_seconds,
                )
            connection = pymysql.connect(**connect_kwargs)
        else:
            raise ValueError(f"Unsupported database type: {self.config.db_type}")

        try:
            yield connection
        finally:
            connection.close()

    def _sql_for_driver(self, sql: str) -> str:
        if self.config.db_type == "mysql":
            return sql.replace("%s", "%s")
        return sql


def _quote_pg(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_mysql(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


def _quote_identifier(db_type: str, identifier: str) -> str:
    if db_type == "postgresql":
        return _quote_pg(identifier)
    if db_type == "mysql":
        return _quote_mysql(identifier)
    raise ValueError(f"Unsupported database type: {db_type}")


def _table_schema_and_name(config: DataSourceConfig, table: TableRef) -> tuple[str, str]:
    if len(table.parts) == 1:
        if config.db_type == "postgresql":
            return config.schema or "public", table.parts[0]
        return config.schema or config.database, table.parts[0]
    if len(table.parts) == 2:
        return table.parts[0], table.parts[1]
    return table.parts[-2], table.parts[-1]


def _table_ref_for_write(config: DataSourceConfig, table: TableRef) -> TableRef:
    if len(table.parts) != 1:
        return table
    table_name = table.parts[0]
    if config.db_type == "postgresql" and config.schema:
        return TableRef((config.schema, table_name))
    if config.db_type == "mysql":
        schema = config.schema or config.database
        if schema:
            return TableRef((schema, table_name))
    return table
