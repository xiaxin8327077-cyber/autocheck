from __future__ import annotations

import shutil
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path


CURRENT_SCHEMA_VERSION = 2
MIGRATION_STATUSES = {"completed", "skipped", "failed"}
REQUIRED_SCHEMA_TABLES = {
    "app_kv",
    "history_runs",
    "schema_migrations",
    "storage_migration_runs",
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
}


def ensure_storage_schema(connection: sqlite3.Connection) -> None:
    if storage_schema_is_current(connection):
        return
    _backup_before_schema_migration(connection)
    _ensure_legacy_tables(connection)
    _ensure_migration_tables(connection)
    _migrate_v2(connection)


def storage_schema_is_current(connection: sqlite3.Connection) -> bool:
    if _schema_version_for_connection(connection) < CURRENT_SCHEMA_VERSION:
        return False
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    except sqlite3.DatabaseError:
        return False
    table_names = {
        str(row["name"] if hasattr(row, "keys") else row[0])
        for row in rows
    }
    return REQUIRED_SCHEMA_TABLES <= table_names


def get_schema_version(db_path: str | Path) -> int:
    path = Path(db_path)
    if not path.exists():
        return 0
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def backup_database_if_exists(db_path: str | Path) -> Path | None:
    path = Path(db_path)
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = path.parent / f"backup-before-storage-v2-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / path.name
    shutil.copy2(path, backup_path)
    return backup_path


def _backup_before_schema_migration(connection: sqlite3.Connection) -> Path | None:
    db_path = _main_database_path(connection)
    if db_path is None:
        return None
    if not _has_existing_database_content(connection):
        return None
    if _schema_version_for_connection(connection) >= CURRENT_SCHEMA_VERSION:
        return None
    try:
        connection.execute("PRAGMA wal_checkpoint(FULL)")
    except sqlite3.DatabaseError:
        pass
    return backup_database_if_exists(db_path)


def _main_database_path(connection: sqlite3.Connection) -> Path | None:
    for row in connection.execute("PRAGMA database_list").fetchall():
        name = row["name"] if hasattr(row, "keys") else row[1]
        filename = row["file"] if hasattr(row, "keys") else row[2]
        if str(name) == "main" and str(filename or "").strip():
            return Path(str(filename))
    return None


def _has_existing_database_content(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchone()
    return int(row[0] if row is not None else 0) > 0


def _schema_version_for_connection(connection: sqlite3.Connection) -> int:
    try:
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    except sqlite3.OperationalError:
        return 0
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def fingerprint_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def migration_completed(
    connection: sqlite3.Connection,
    source_type: str,
    source_path: str = "",
    source_key: str = "",
    source_fingerprint: str = "",
) -> bool:
    row = connection.execute(
        """
        SELECT status
        FROM storage_migration_runs
        WHERE source_type = ?
          AND source_path = ?
          AND source_key = ?
          AND source_fingerprint = ?
        """,
        (str(source_type), str(source_path), str(source_key), str(source_fingerprint)),
    ).fetchone()
    if row is None:
        return False
    status = row["status"] if hasattr(row, "keys") else row[0]
    return str(status) == "completed"


def record_migration(
    connection: sqlite3.Connection,
    source_type: str,
    source_path: str = "",
    source_key: str = "",
    source_fingerprint: str = "",
    migrated_count: int = 0,
    skipped_count: int = 0,
    status: str = "completed",
    message: str = "",
) -> None:
    if status not in MIGRATION_STATUSES:
        raise ValueError("invalid migration status")
    message_lines = str(message or "").splitlines()
    safe_message = (message_lines[0] if message_lines else "")[:500]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection.execute(
        """
        INSERT INTO storage_migration_runs(
            source_type, source_path, source_key, source_fingerprint,
            migrated_count, skipped_count, status, message,
            started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_type, source_path, source_key, source_fingerprint)
        DO UPDATE SET
            migrated_count = excluded.migrated_count,
            skipped_count = excluded.skipped_count,
            status = excluded.status,
            message = excluded.message,
            finished_at = excluded.finished_at
        """,
        (
            str(source_type),
            str(source_path),
            str(source_key),
            str(source_fingerprint),
            int(migrated_count),
            int(skipped_count),
            status,
            safe_message,
            now,
            now,
        ),
    )


def _ensure_legacy_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS history_runs (
            kind TEXT NOT NULL,
            id TEXT NOT NULL,
            payload TEXT NOT NULL,
            run_date TEXT NOT NULL DEFAULT '',
            run_at TEXT NOT NULL DEFAULT '',
            config_fingerprint TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (kind, id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_runs_sort ON history_runs(kind, run_date DESC, run_at DESC)"
    )


def _ensure_migration_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_migration_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            source_key TEXT NOT NULL DEFAULT '',
            source_fingerprint TEXT NOT NULL DEFAULT '',
            migrated_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT '',
            UNIQUE(source_type, source_path, source_key, source_fingerprint)
        )
        """
    )


def _migrate_v2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS data_sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            db_type TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            database_name TEXT NOT NULL,
            schema_name TEXT NOT NULL,
            username TEXT NOT NULL,
            password_encrypted TEXT NOT NULL DEFAULT '',
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            last_login_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS config_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_headers (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            run_date TEXT NOT NULL DEFAULT '',
            run_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            executor_id TEXT NOT NULL DEFAULT '',
            executor_username TEXT NOT NULL DEFAULT '',
            executor_name TEXT NOT NULL DEFAULT '',
            config_fingerprint TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_run_headers_sort
            ON run_headers(kind, run_date DESC, run_at DESC);

        CREATE TABLE IF NOT EXISTS reconcile_runs (
            id TEXT PRIMARY KEY,
            config_name TEXT NOT NULL DEFAULT '',
            dws_source_name TEXT NOT NULL DEFAULT '',
            rule_version TEXT NOT NULL DEFAULT '',
            baseline_id TEXT NOT NULL DEFAULT '',
            baseline_run_at TEXT NOT NULL DEFAULT '',
            baseline_count INTEGER,
            total_count INTEGER NOT NULL DEFAULT 0,
            added_count INTEGER,
            removed_count INTEGER,
            FOREIGN KEY (id) REFERENCES run_headers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reconcile_run_counts (
            run_id TEXT NOT NULL,
            count_type TEXT NOT NULL,
            label TEXT NOT NULL,
            count_value INTEGER NOT NULL,
            PRIMARY KEY (run_id, count_type, label),
            FOREIGN KEY (run_id) REFERENCES reconcile_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reconcile_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            result_order INTEGER NOT NULL,
            project_code TEXT NOT NULL DEFAULT '',
            project_name TEXT NOT NULL DEFAULT '',
            asset_total TEXT NOT NULL DEFAULT '',
            liability_equity_total TEXT NOT NULL DEFAULT '',
            received_trust_balance TEXT NOT NULL DEFAULT '',
            difference TEXT NOT NULL DEFAULT '',
            direction TEXT NOT NULL DEFAULT '',
            difference_reason TEXT NOT NULL DEFAULT '',
            match_status TEXT NOT NULL DEFAULT '',
            valuation_asset_total TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES reconcile_runs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_reconcile_results_run
            ON reconcile_results(run_id, result_order);

        CREATE INDEX IF NOT EXISTS idx_reconcile_results_project
            ON reconcile_results(project_code);

        CREATE INDEX IF NOT EXISTS idx_reconcile_results_reason
            ON reconcile_results(difference_reason, match_status);

        CREATE TABLE IF NOT EXISTS reconcile_result_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER NOT NULL,
            detail_order INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT '',
            specific_reason TEXT NOT NULL DEFAULT '',
            data_json TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (result_id) REFERENCES reconcile_results(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reconcile_delta_results (
            run_id TEXT NOT NULL,
            delta_type TEXT NOT NULL,
            result_order INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id, delta_type, result_order),
            FOREIGN KEY (run_id) REFERENCES reconcile_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS db_validation_runs (
            id TEXT PRIMARY KEY,
            report_date TEXT NOT NULL DEFAULT '',
            result_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            table_count INTEGER NOT NULL DEFAULT 0,
            enable_public_info_check INTEGER NOT NULL DEFAULT 0,
            enable_template_check INTEGER NOT NULL DEFAULT 0,
            excel_filename TEXT NOT NULL DEFAULT '',
            excel_path TEXT NOT NULL DEFAULT '',
            download_url TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (id) REFERENCES run_headers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS db_validation_selected_tables (
            run_id TEXT NOT NULL,
            table_order INTEGER NOT NULL,
            table_code TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (run_id, table_order),
            FOREIGN KEY (run_id) REFERENCES db_validation_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS db_validation_warnings (
            run_id TEXT NOT NULL,
            warning_order INTEGER NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (run_id, warning_order),
            FOREIGN KEY (run_id) REFERENCES db_validation_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS db_validation_result_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            row_order INTEGER NOT NULL,
            table_code TEXT NOT NULL DEFAULT '',
            rule_id TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES db_validation_runs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_db_validation_runs_sort
            ON db_validation_runs(report_date DESC);

        CREATE INDEX IF NOT EXISTS idx_db_validation_result_rows_run
            ON db_validation_result_rows(run_id, row_order);

        CREATE TABLE IF NOT EXISTS flow_chain_runs (
            id TEXT PRIMARY KEY,
            chain_id TEXT NOT NULL DEFAULT '',
            chain_name TEXT NOT NULL DEFAULT '',
            is_multi_chain INTEGER NOT NULL DEFAULT 0,
            trigger_type TEXT NOT NULL DEFAULT '',
            executor_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            step_count INTEGER NOT NULL DEFAULT 0,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (id) REFERENCES run_headers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS flow_chain_run_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            step_order INTEGER NOT NULL,
            flow_id TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            sp_task_id TEXT NOT NULL DEFAULT '',
            start_time TEXT NOT NULL DEFAULT '',
            end_time TEXT NOT NULL DEFAULT '',
            duration_seconds INTEGER,
            payload_json TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES flow_chain_runs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_flow_chain_run_steps_run
            ON flow_chain_run_steps(run_id, step_order);

        CREATE TABLE IF NOT EXISTS flow_chain_run_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            log_order INTEGER NOT NULL,
            log_time TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            progress INTEGER,
            step TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES flow_chain_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS flow_chain_run_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            chain_order INTEGER NOT NULL,
            chain_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            step_count INTEGER NOT NULL DEFAULT 0,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES flow_chain_runs(id) ON DELETE CASCADE
        );
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, applied_at)
        VALUES (?, datetime('now'))
        """,
        (CURRENT_SCHEMA_VERSION,),
    )
