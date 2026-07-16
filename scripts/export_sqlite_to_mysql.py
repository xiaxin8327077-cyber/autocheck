from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote


CURRENT_APP_SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "001_init_schema.sql"

# The SQLite exporter deliberately covers only the original normalized storage
# boundary. Report-navigation tables have no SQLite source equivalent and are
# created and seeded by the follow-up MySQL scripts listed below.
MIGRATION_TARGET_TABLE_ORDER = [
    "app_schema_version",
    "data_sources",
    "app_settings",
    "users",
    "config_snapshots",
    "run_headers",
    "reconcile_runs",
    "reconcile_run_counts",
    "reconcile_results",
    "reconcile_result_details",
    "reconcile_delta_results",
    "db_validation_runs",
    "db_validation_selected_tables",
    "db_validation_warnings",
    "db_validation_result_rows",
    "flow_chain_runs",
    "flow_chain_run_steps",
    "flow_chain_run_logs",
    "flow_chain_run_details",
    "storage_migration_runs",
]
EXPORT_TABLE_ORDER = [
    table for table in MIGRATION_TARGET_TABLE_ORDER if table != "app_schema_version"
]
POST_MIGRATION_SCHEMA_SCRIPTS = [
    "sql/app_storage/mysql/002_report_navigation.sql",
    "sql/app_storage/mysql/003_report_navigation_seed.sql",
]
EXCLUDED_TABLES = {
    "app_kv": "legacy configuration/auth snapshot; normalized rows are exported from data_sources, app_settings, and users",
    "history_runs": "legacy history snapshot; normalized history rows are exported from run tables",
    "schema_migrations": "SQLite schema history; replaced by app_schema_version",
    "sqlite_sequence": "SQLite internal auto-increment state",
}
DATE_COLUMNS = {"run_headers.run_date", "db_validation_runs.report_date"}
DATETIME_COLUMNS = {
    "data_sources.created_at",
    "data_sources.updated_at",
    "app_settings.updated_at",
    "users.created_at",
    "users.updated_at",
    "users.last_login_at",
    "config_snapshots.created_at",
    "run_headers.run_at",
    "run_headers.finished_at",
    "reconcile_runs.baseline_run_at",
    "flow_chain_run_steps.start_time",
    "flow_chain_run_steps.end_time",
    "storage_migration_runs.started_at",
    "storage_migration_runs.finished_at",
}
TIME_COLUMNS = {"flow_chain_run_logs.log_time"}
DECIMAL_COLUMNS = {
    "reconcile_results.asset_total",
    "reconcile_results.liability_equity_total",
    "reconcile_results.received_trust_balance",
    "reconcile_results.difference",
    "reconcile_results.valuation_asset_total",
}
JSON_COLUMNS = {
    "app_settings.value_json",
    "config_snapshots.payload_json",
    "run_headers.payload_json",
    "reconcile_results.payload_json",
    "reconcile_result_details.data_json",
    "reconcile_delta_results.payload_json",
    "db_validation_result_rows.payload_json",
    "flow_chain_run_steps.payload_json",
    "flow_chain_run_logs.payload_json",
    "flow_chain_run_details.payload_json",
}
INTEGER_COLUMNS = {
    "data_sources.port",
    "data_sources.is_default",
    "users.enabled",
    "reconcile_runs.baseline_count",
    "reconcile_runs.total_count",
    "reconcile_runs.added_count",
    "reconcile_runs.removed_count",
    "reconcile_run_counts.count_value",
    "reconcile_results.id",
    "reconcile_results.result_order",
    "reconcile_result_details.id",
    "reconcile_result_details.result_id",
    "reconcile_result_details.detail_order",
    "reconcile_delta_results.result_order",
    "db_validation_runs.result_count",
    "db_validation_runs.warning_count",
    "db_validation_runs.table_count",
    "db_validation_runs.enable_public_info_check",
    "db_validation_runs.enable_template_check",
    "db_validation_selected_tables.table_order",
    "db_validation_warnings.warning_order",
    "db_validation_result_rows.id",
    "db_validation_result_rows.row_order",
    "flow_chain_runs.is_multi_chain",
    "flow_chain_runs.step_count",
    "flow_chain_runs.duration_seconds",
    "flow_chain_run_steps.id",
    "flow_chain_run_steps.step_order",
    "flow_chain_run_steps.duration_seconds",
    "flow_chain_run_logs.id",
    "flow_chain_run_logs.log_order",
    "flow_chain_run_logs.progress",
    "flow_chain_run_details.id",
    "flow_chain_run_details.chain_order",
    "flow_chain_run_details.step_count",
    "flow_chain_run_details.duration_seconds",
    "storage_migration_runs.id",
    "storage_migration_runs.migrated_count",
    "storage_migration_runs.skipped_count",
}


def export_sqlite_to_mysql(
    source: str | Path,
    *,
    database: str,
    schema_output: str | Path,
    data_output: str | Path,
    report_output: str | Path,
) -> dict[str, Any]:
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite source not found: {source_path}")
    database_name = _validate_database_name(database)
    schema_path = Path(schema_output)
    data_path = Path(data_output)
    report_path = Path(report_output)
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_SCHEMA_SQL.exists():
        raise FileNotFoundError(f"MySQL schema SQL not found: {DEFAULT_SCHEMA_SQL}")

    shutil.copyfile(DEFAULT_SCHEMA_SQL, schema_path)
    source_sha256 = _file_sha256(source_path)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    with _connect_read_only(source_path) as connection:
        connection.row_factory = sqlite3.Row
        integrity_rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
        if integrity_rows != ["ok"]:
            raise RuntimeError(f"SQLite integrity_check failed: {integrity_rows}")
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        table_names = _table_names(connection)
        missing_tables = [table for table in EXPORT_TABLE_ORDER if table not in table_names]
        if missing_tables:
            raise RuntimeError(f"SQLite source is missing normalized tables: {', '.join(missing_tables)}")

        table_reports: dict[str, Any] = {}
        data_lines = [
            "-- Auto Check SQLite to MySQL data export",
            "-- Generated by scripts/export_sqlite_to_mysql.py",
            f"-- Source SHA-256: {source_sha256}",
            f"SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;",
            f"USE `{database_name}`;",
            "SET FOREIGN_KEY_CHECKS=0;",
            "START TRANSACTION;",
            "",
        ]
        total_exported_rows = 0
        for table_name in EXPORT_TABLE_ORDER:
            columns = _table_columns(connection, table_name)
            rows = _table_rows(connection, table_name, columns)
            source_checksum = _checksum_rows([{column: row[column] for column in columns} for row in rows])
            converted_rows = [_convert_row(table_name, columns, row) for row in rows]
            converted_checksum = _checksum_rows(converted_rows)
            if converted_rows:
                data_lines.extend(_insert_lines(table_name, columns, converted_rows))
                data_lines.append("")
            table_reports[table_name] = {
                "source_rows": len(rows),
                "exported_rows": len(converted_rows),
                "primary_key": _primary_key_columns(connection, table_name),
                "source_row_checksum_sha256": source_checksum,
                "converted_row_checksum_sha256": converted_checksum,
            }
            total_exported_rows += len(converted_rows)

    data_lines.extend(
        [
            "SET FOREIGN_KEY_CHECKS=1;",
            (
                "INSERT INTO `app_schema_version` "
                "(`version`, `applied_at`, `source_sha256`, `description`) VALUES "
                f"({CURRENT_APP_SCHEMA_VERSION}, {_sql_quote(generated_at.replace('T', ' ').removesuffix('Z'))}, "
                f"{_sql_quote(source_sha256)}, {_sql_quote('manual SQLite export')});"
            ),
            "COMMIT;",
            "",
        ]
    )
    data_path.write_text("\n".join(data_lines), encoding="utf-8", newline="\n")

    report = {
        "generated_at_utc": generated_at,
        "source_file": str(source_path),
        "source_size_bytes": source_path.stat().st_size,
        "source_sha256": source_sha256,
        "source_integrity_check": integrity_rows,
        "source_foreign_key_issue_count": len(foreign_key_rows),
        "target_database": database_name,
        "target_schema_version": CURRENT_APP_SCHEMA_VERSION,
        "target_tables": len(MIGRATION_TARGET_TABLE_ORDER),
        "exported_source_tables": len(EXPORT_TABLE_ORDER),
        "post_migration_schema_scripts": POST_MIGRATION_SCHEMA_SCRIPTS,
        "total_exported_rows": total_exported_rows,
        "excluded_tables": EXCLUDED_TABLES,
        "tables": table_reports,
        "typed_conversions": {
            "date_columns": sorted(DATE_COLUMNS),
            "datetime_columns": sorted(DATETIME_COLUMNS),
            "time_columns": sorted(TIME_COLUMNS),
            "decimal_columns": sorted(DECIMAL_COLUMNS),
        },
        "notes": [
            "The schema script never creates, drops, or truncates the auto_check database.",
            "The data script records app_schema_version only at the end of the transaction.",
            "Date, datetime, time, and monetary values are written for native MySQL column types.",
            "Generated SQL may contain encrypted credentials and password hashes; handle it as sensitive data.",
            "Apply the listed post-migration schema scripts after importing this legacy migration export.",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(
        "Exported Auto Check SQLite data: "
        f"{total_exported_rows} rows, {len(EXPORT_TABLE_ORDER)} source tables, report={report_path}"
    )
    return report


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path.resolve()).replace(chr(92), '/'), safe=':/')}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in rows}


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    if not rows:
        raise RuntimeError(f"SQLite source table has no columns: {table_name}")
    return [str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows]


def _primary_key_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    pk_rows = sorted(
        [
            (
                int(row["pk"] if isinstance(row, sqlite3.Row) else row[5]),
                str(row["name"] if isinstance(row, sqlite3.Row) else row[1]),
            )
            for row in rows
            if int(row["pk"] if isinstance(row, sqlite3.Row) else row[5])
        ]
    )
    return [name for _, name in pk_rows]


def _table_rows(connection: sqlite3.Connection, table_name: str, columns: list[str]) -> list[sqlite3.Row]:
    order_columns = _primary_key_columns(connection, table_name) or columns[:1]
    order_by = ", ".join(_quote_identifier(column) for column in order_columns)
    return connection.execute(f"SELECT * FROM {_quote_identifier(table_name)} ORDER BY {order_by}").fetchall()


def _convert_row(table_name: str, columns: list[str], row: sqlite3.Row) -> dict[str, Any]:
    return {column: _convert_value(table_name, column, row[column]) for column in columns}


def _convert_value(table_name: str, column: str, value: Any) -> Any:
    key = f"{table_name}.{column}"
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        if key in DATE_COLUMNS or key in DATETIME_COLUMNS or key in TIME_COLUMNS or key in DECIMAL_COLUMNS:
            return None
    if key in DATE_COLUMNS:
        return _normalize_date(value)
    if key in DATETIME_COLUMNS:
        return _normalize_datetime(value)
    if key in TIME_COLUMNS:
        return _normalize_time(value)
    if key in DECIMAL_COLUMNS:
        return _normalize_decimal(value)
    if key in JSON_COLUMNS:
        return _normalize_json(value)
    if key in INTEGER_COLUMNS:
        return None if value == "" else int(value)
    return value


def _insert_lines(table_name: str, columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    lines = [f"-- {table_name}: {len(rows)} rows"]
    for row in rows:
        value_sql = ", ".join(_literal(row[column]) for column in columns)
        lines.append(f"INSERT INTO {_quote_identifier(table_name)} ({column_sql}) VALUES ({value_sql});")
    return lines


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    return _sql_quote(str(value))


def _sql_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("\0", "\\0")
        .replace("'", "''")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\x1a", "\\Z")
    )
    return f"'{escaped}'"


def _quote_identifier(value: str) -> str:
    return f"`{str(value).replace('`', '``')}`"


def _normalize_date(value: Any) -> str:
    text = str(value).strip().replace("/", "-")
    if " " in text:
        text = text.split(" ", 1)[0]
    if "T" in text:
        text = text.split("T", 1)[0]
    return datetime.fromisoformat(text).date().isoformat()


def _normalize_datetime(value: Any) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("T", " "))
    return parsed.replace(tzinfo=None).isoformat(sep=" ", timespec="microseconds")


def _normalize_time(value: Any) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.rsplit("T", 1)[-1]
    if " " in text:
        text = text.rsplit(" ", 1)[-1]
    parsed = datetime.fromisoformat(f"2000-01-01 {text}").time()
    return parsed.isoformat(timespec="microseconds")


def _normalize_decimal(value: Any) -> Decimal | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.000000000001"))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc


def _normalize_json(value: Any) -> str:
    if isinstance(value, (dict, list)):
        parsed = value
    else:
        text = str(value or "").strip()
        parsed = json.loads(text) if text else {}
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum_rows(rows: list[dict[str, Any]]) -> str:
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _validate_database_name(value: str) -> str:
    database = str(value or "").strip()
    if not database:
        raise ValueError("database name is required")
    if not all(character.isalnum() or character == "_" for character in database):
        raise ValueError("database name may only contain letters, digits, and underscore")
    return database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Auto Check SQLite application storage to MySQL SQL files.")
    parser.add_argument("--source", required=True, help="Path to the source auto-check.db SQLite file")
    parser.add_argument("--database", default="auto_check", help="Existing MySQL database name")
    parser.add_argument("--schema-output", required=True, help="Output path for generic MySQL schema SQL")
    parser.add_argument("--data-output", required=True, help="Output path for converted data SQL")
    parser.add_argument("--report-output", required=True, help="Output path for JSON migration report")
    args = parser.parse_args(argv)
    export_sqlite_to_mysql(
        args.source,
        database=args.database,
        schema_output=args.schema_output,
        data_output=args.data_output,
        report_output=args.report_output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
