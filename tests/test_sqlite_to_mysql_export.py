from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sqlite3
from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "001_init_schema.sql"
EXPORT_SCRIPT = ROOT / "scripts" / "export_sqlite_to_mysql.py"


def _load_exporter():
    assert EXPORT_SCRIPT.exists(), "scripts/export_sqlite_to_mysql.py is required"
    spec = importlib.util.spec_from_file_location("export_sqlite_to_mysql", EXPORT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mysql_schema_asset_is_generic_safe_and_complete_for_legacy_migration_boundary():
    assert SCHEMA_SQL.exists(), "MySQL application schema SQL is required"
    exporter = _load_exporter()
    migration_schema = {
        table_name: EXPECTED_APP_SCHEMA[table_name]
        for table_name in exporter.MIGRATION_TARGET_TABLE_ORDER
    }

    text = SCHEMA_SQL.read_text(encoding="utf-8")
    upper = text.upper()

    assert "USE `auto_check`;" in text
    assert "CREATE DATABASE" not in upper
    assert re.search(r"\bDROP\b", upper) is None
    assert re.search(r"\bTRUNCATE\b", upper) is None
    assert len(exporter.MIGRATION_TARGET_TABLE_ORDER) == 20
    assert set(exporter.MIGRATION_TARGET_TABLE_ORDER) < set(EXPECTED_APP_SCHEMA)
    assert len(re.findall(r"(?im)^CREATE TABLE `", text)) == len(migration_schema)
    assert len(re.findall(r"\) ENGINE=.* COMMENT='", text)) == len(migration_schema)
    assert len(re.findall(r" COMMENT '", text)) >= 155
    assert "DATE" in text
    assert "DATETIME(6)" in text
    assert "TIME(6)" in text
    assert "DECIMAL(38,12)" in text

    for table_name in migration_schema:
        assert f"CREATE TABLE `{table_name}`" in text
        for column_name in migration_schema[table_name]:
            assert f"`{column_name}`" in text


def test_exporter_generates_mysql_sql_report_and_keeps_console_sanitized(tmp_path, capsys):
    source = tmp_path / "auto-check.db"
    _create_sqlite_fixture(source)
    before_hash = _sha256(source)
    schema_output = tmp_path / "schema.sql"
    data_output = tmp_path / "data.sql"
    report_output = tmp_path / "report.json"
    exporter = _load_exporter()

    result = exporter.export_sqlite_to_mysql(
        source,
        database="auto_check",
        schema_output=schema_output,
        data_output=data_output,
        report_output=report_output,
    )

    captured = capsys.readouterr()
    assert "encrypted-secret-not-stdout" not in captured.out
    assert "encrypted-secret-not-stdout" not in captured.err
    assert "hash-secret-not-stdout" not in captured.out
    assert "hash-secret-not-stdout" not in captured.err
    assert before_hash == _sha256(source)

    assert result["target_tables"] == len(exporter.MIGRATION_TARGET_TABLE_ORDER)
    assert result["target_schema_version"] == CURRENT_APP_SCHEMA_VERSION
    assert result["total_exported_rows"] >= 20
    assert schema_output.read_text(encoding="utf-8") == SCHEMA_SQL.read_text(encoding="utf-8")

    data_text = data_output.read_text(encoding="utf-8")
    assert "USE `auto_check`;" in data_text
    assert "START TRANSACTION;" in data_text
    assert data_text.rstrip().endswith("COMMIT;")
    assert "CREATE DATABASE" not in data_text.upper()
    assert re.search(r"\bDROP\b", data_text.upper()) is None
    assert re.search(r"\bTRUNCATE\b", data_text.upper()) is None
    assert "CREATE TABLE" not in data_text.upper()
    assert "INSERT INTO `data_sources`" in data_text
    assert "INSERT INTO `run_headers`" in data_text
    assert "INSERT INTO `app_schema_version`" in data_text
    assert data_text.rfind("INSERT INTO `app_schema_version`") > data_text.rfind("INSERT INTO `storage_migration_runs`")
    assert "'2026-07-14'" in data_text
    assert "'2026-07-14 10:11:12.123456'" in data_text
    assert "'12:34:56.987654'" in data_text
    assert "123.450000000000" in data_text

    report = json.loads(report_output.read_text(encoding="utf-8"))
    assert report == result
    assert report["source_integrity_check"] == ["ok"]
    assert report["source_foreign_key_issue_count"] == 0
    assert report["excluded_tables"]["app_kv"]
    assert report["excluded_tables"]["history_runs"]
    assert report["excluded_tables"]["schema_migrations"]
    assert report["excluded_tables"]["sqlite_sequence"]
    assert report["tables"]["data_sources"]["exported_rows"] == 1
    assert report["tables"]["run_headers"]["exported_rows"] == 3
    assert report["tables"]["flow_chain_run_logs"]["exported_rows"] == 1
    assert report["post_migration_schema_scripts"] == [
        "sql/app_storage/mysql/002_report_navigation.sql",
        "sql/app_storage/mysql/003_report_navigation_seed.sql",
    ]


def test_exporter_opens_sqlite_source_read_only(tmp_path, monkeypatch):
    source = tmp_path / "auto-check.db"
    _create_sqlite_fixture(source)
    exporter = _load_exporter()
    calls = []
    real_connect = exporter.sqlite3.connect

    def spy_connect(database, *args, **kwargs):
        calls.append((database, kwargs))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(exporter.sqlite3, "connect", spy_connect)

    exporter.export_sqlite_to_mysql(
        source,
        database="auto_check",
        schema_output=tmp_path / "schema.sql",
        data_output=tmp_path / "data.sql",
        report_output=tmp_path / "report.json",
    )

    assert any(str(database).startswith("file:") and "mode=ro" in str(database) for database, _ in calls)
    assert any(kwargs.get("uri") is True for _, kwargs in calls)


def _create_sqlite_fixture(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        _ensure_sqlite_fixture_schema(connection)
        connection.execute(
            """
            INSERT INTO data_sources(
                id, name, db_type, host, port, database_name, schema_name,
                username, password_encrypted, is_default, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ds-main",
                "DWS 生产只读",
                "mysql",
                "10.20.18.9",
                3306,
                "risk_dw",
                "",
                "risk_reader",
                "encrypted-secret-not-stdout",
                1,
                "2026-07-14 09:00:00.000001",
                "2026-07-14 09:05:00.000002",
            ),
        )
        connection.execute(
            "INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)",
            ("flow_tool", '{"service_url":"https://internal.example","token":"secret-token"}', "2026-07-14 09:06:00"),
        )
        connection.execute(
            """
            INSERT INTO users(
                id, username, display_name, role, password_hash, enabled,
                created_at, updated_at, last_login_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "u-admin",
                "admin",
                "管理员",
                "admin",
                "hash-secret-not-stdout",
                1,
                "2026-07-14 09:10:00",
                "2026-07-14 09:11:00",
                "2026-07-14 09:12:00",
            ),
        )
        connection.execute(
            "INSERT INTO config_snapshots(fingerprint, payload_json, created_at) VALUES (?, ?, ?)",
            ("f" * 64, '{"data_sources":[]}', "2026-07-14 09:13:00"),
        )
        _insert_run_header(connection, "reconcile-1", "reconcile")
        connection.execute(
            """
            INSERT INTO reconcile_runs(
                id, config_name, dws_source_name, rule_version, baseline_id,
                baseline_run_at, baseline_count, total_count, added_count, removed_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("reconcile-1", "默认配置", "DWS", "v1", "baseline-1", "2026-07-14 08:00:00", 2, 1, 1, 0),
        )
        connection.execute(
            "INSERT INTO reconcile_run_counts(run_id, count_type, label, count_value) VALUES (?, ?, ?, ?)",
            ("reconcile-1", "status", "存在差异", 1),
        )
        cursor = connection.execute(
            """
            INSERT INTO reconcile_results(
                run_id, result_order, project_code, project_name, asset_total,
                liability_equity_total, received_trust_balance, difference,
                direction, difference_reason, match_status, valuation_asset_total, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "reconcile-1",
                1,
                "P001",
                "测试项目",
                "123.450000000000",
                "120.000000000000",
                "3.450000000000",
                "3.450000000000",
                "借方",
                "金额不一致",
                "diff",
                "123.450000000000",
                '{"project_code":"P001"}',
            ),
        )
        result_id = cursor.lastrowid
        connection.execute(
            "INSERT INTO reconcile_result_details(result_id, detail_order, kind, specific_reason, data_json) VALUES (?, ?, ?, ?, ?)",
            (result_id, 1, "reason", "金额差异", '{"amount":"123.45"}'),
        )
        connection.execute(
            "INSERT INTO reconcile_delta_results(run_id, delta_type, result_order, payload_json) VALUES (?, ?, ?, ?)",
            ("reconcile-1", "added", 1, '{"project_code":"P001"}'),
        )
        _insert_run_header(connection, "dbv-1", "db_validation")
        connection.execute(
            """
            INSERT INTO db_validation_runs(
                id, report_date, result_count, warning_count, table_count,
                enable_public_info_check, enable_template_check, excel_filename, excel_path, download_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("dbv-1", "2026-07-14", 1, 1, 1, 1, 0, "result.xlsx", "D:/out/result.xlsx", "/download/result.xlsx"),
        )
        connection.execute(
            "INSERT INTO db_validation_selected_tables(run_id, table_order, table_code) VALUES (?, ?, ?)",
            ("dbv-1", 1, "ZG01"),
        )
        connection.execute(
            "INSERT INTO db_validation_warnings(run_id, warning_order, message) VALUES (?, ?, ?)",
            ("dbv-1", 1, "warning"),
        )
        connection.execute(
            """
            INSERT INTO db_validation_result_rows(
                run_id, row_order, table_code, rule_id, severity, message, detail, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("dbv-1", 1, "ZG01", "R001", "error", "message", "detail", '{"row":1}'),
        )
        _insert_run_header(connection, "flow-1", "flow_chain")
        connection.execute(
            """
            INSERT INTO flow_chain_runs(
                id, chain_id, chain_name, is_multi_chain, trigger_type,
                executor_name, status, error, step_count, duration_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("flow-1", "chain-1", "链路一", 0, "manual", "管理员", "success", "", 1, 5),
        )
        connection.execute(
            """
            INSERT INTO flow_chain_run_steps(
                run_id, step_order, flow_id, name, status, sp_task_id,
                start_time, end_time, duration_seconds, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "flow-1",
                1,
                "flow-a",
                "步骤一",
                "success",
                "sp-1",
                "2026-07-14 10:11:12.123456",
                "2026-07-14 10:11:17.123456",
                5,
                '{"step":1}',
            ),
        )
        connection.execute(
            "INSERT INTO flow_chain_run_logs(run_id, log_order, log_time, message, progress, step, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("flow-1", 1, "12:34:56.987654", "日志", 100, "步骤一", '{"log":1}'),
        )
        connection.execute(
            """
            INSERT INTO flow_chain_run_details(
                run_id, chain_order, chain_name, status, step_count, duration_seconds, error, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("flow-1", 1, "链路一", "success", 1, 5, "", '{"detail":1}'),
        )
        connection.execute(
            """
            INSERT INTO storage_migration_runs(
                source_type, source_path, source_key, source_fingerprint,
                migrated_count, skipped_count, status, message, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("sqlite", "auto-check.db", "", "a" * 64, 1, 0, "completed", "ok", "2026-07-14 10:00:00", "2026-07-14 10:00:01"),
        )


def _insert_run_header(connection: sqlite3.Connection, run_id: str, kind: str) -> None:
    connection.execute(
        """
        INSERT INTO run_headers(
            id, kind, run_date, run_at, finished_at, status,
            executor_id, executor_username, executor_name, config_fingerprint, payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            kind,
            "2026-07-14",
            "2026-07-14 10:11:12.123456",
            "2026-07-14 10:12:12.123456",
            "success",
            "u-admin",
            "admin",
            "管理员",
            "f" * 64,
            json.dumps({"id": run_id, "kind": kind}, ensure_ascii=False),
        ),
    )


def _ensure_sqlite_fixture_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE app_kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE history_runs (
            kind TEXT NOT NULL,
            id TEXT NOT NULL,
            payload TEXT NOT NULL,
            run_date TEXT NOT NULL DEFAULT '',
            run_at TEXT NOT NULL DEFAULT '',
            config_fingerprint TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (kind, id)
        );

        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE data_sources (
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

        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE users (
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

        CREATE TABLE config_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE run_headers (
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

        CREATE TABLE reconcile_runs (
            id TEXT PRIMARY KEY,
            config_name TEXT NOT NULL DEFAULT '',
            dws_source_name TEXT NOT NULL DEFAULT '',
            rule_version TEXT NOT NULL DEFAULT '',
            baseline_id TEXT NOT NULL DEFAULT '',
            baseline_run_at TEXT NOT NULL DEFAULT '',
            baseline_count INTEGER,
            total_count INTEGER NOT NULL DEFAULT 0,
            added_count INTEGER,
            removed_count INTEGER
        );

        CREATE TABLE reconcile_run_counts (
            run_id TEXT NOT NULL,
            count_type TEXT NOT NULL,
            label TEXT NOT NULL,
            count_value INTEGER NOT NULL,
            PRIMARY KEY (run_id, count_type, label)
        );

        CREATE TABLE reconcile_results (
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
            payload_json TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE reconcile_result_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER NOT NULL,
            detail_order INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT '',
            specific_reason TEXT NOT NULL DEFAULT '',
            data_json TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE reconcile_delta_results (
            run_id TEXT NOT NULL,
            delta_type TEXT NOT NULL,
            result_order INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id, delta_type, result_order)
        );

        CREATE TABLE db_validation_runs (
            id TEXT PRIMARY KEY,
            report_date TEXT NOT NULL DEFAULT '',
            result_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            table_count INTEGER NOT NULL DEFAULT 0,
            enable_public_info_check INTEGER NOT NULL DEFAULT 0,
            enable_template_check INTEGER NOT NULL DEFAULT 0,
            excel_filename TEXT NOT NULL DEFAULT '',
            excel_path TEXT NOT NULL DEFAULT '',
            download_url TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE db_validation_selected_tables (
            run_id TEXT NOT NULL,
            table_order INTEGER NOT NULL,
            table_code TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (run_id, table_order)
        );

        CREATE TABLE db_validation_warnings (
            run_id TEXT NOT NULL,
            warning_order INTEGER NOT NULL,
            message TEXT NOT NULL,
            PRIMARY KEY (run_id, warning_order)
        );

        CREATE TABLE db_validation_result_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            row_order INTEGER NOT NULL,
            table_code TEXT NOT NULL DEFAULT '',
            rule_id TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE flow_chain_runs (
            id TEXT PRIMARY KEY,
            chain_id TEXT NOT NULL DEFAULT '',
            chain_name TEXT NOT NULL DEFAULT '',
            is_multi_chain INTEGER NOT NULL DEFAULT 0,
            trigger_type TEXT NOT NULL DEFAULT '',
            executor_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            step_count INTEGER NOT NULL DEFAULT 0,
            duration_seconds INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE flow_chain_run_steps (
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
            payload_json TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE flow_chain_run_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            log_order INTEGER NOT NULL,
            log_time TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            progress INTEGER,
            step TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE flow_chain_run_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            chain_order INTEGER NOT NULL,
            chain_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            step_count INTEGER NOT NULL DEFAULT 0,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE storage_migration_runs (
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
            finished_at TEXT NOT NULL DEFAULT ''
        );

        INSERT INTO schema_migrations(version, applied_at) VALUES (2, '2026-07-14 00:00:00');
        """
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
