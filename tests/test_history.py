from datetime import datetime

from auto_check.app.history import JsonHistoryStore, SqliteHistoryStore, build_history_entry
from auto_check.app.config import AppConfig, DataSourceConfig
from auto_check.app.local_store import db_path_for_config


def _result(project_code, reason, difference, status="已解释"):
    return {
        "project_code": project_code,
        "project_name": f"项目{project_code}",
        "difference_reason": reason,
        "difference": str(difference),
        "match_status": status,
    }


def _config() -> AppConfig:
    return AppConfig(
        dws=DataSourceConfig(
            db_type="postgresql",
            host="127.0.0.1",
            port=5432,
            database="auto_check_test",
            schema="dws",
            username="postgres",
            password="secret",
        ),
        business=DataSourceConfig(
            db_type="mysql",
            host="127.0.0.1",
            port=3306,
            database="business",
            schema="",
            username="root",
            password="secret",
        ),
    )


def test_first_history_entry_has_no_added_removed_without_baseline():
    entry = build_history_entry(
        previous_runs=[],
        run_date="2026-04-30",
        config_name="本地测试",
        dws_source_name="本地 DWS",
        config=_config(),
        results=[
            _result("P1", "资产缺失", "-100"),
            _result("P2", "暂无法确定", "20", status="未解释"),
        ],
        now=datetime(2026, 5, 28, 10, 30, 0),
    )

    assert entry["run_at"] == "2026-05-28 10:30:00"
    assert entry["rule_version"]
    assert entry["config_fingerprint"]
    assert entry["config_name"] == "本地测试"
    assert entry["dws_source_name"] == "本地 DWS"
    assert entry["total_count"] == 2
    assert entry["baseline_run_at"] == ""
    assert entry["baseline_count"] == 0
    assert entry["added_count"] is None
    assert entry["removed_count"] is None
    assert entry["status_counts"] == {"已解释": 1, "未解释": 1}
    assert entry["reason_counts"] == {"资产缺失": 1, "暂无法确定": 1}
    assert entry["added_results"] == []
    assert entry["removed_results"] == []


def test_history_entry_compares_against_previous_same_date_without_data_source_limit():
    first = build_history_entry(
        previous_runs=[],
        run_date="2026-04-30",
        config_name="旧名称",
        config=_config(),
        results=[
            _result("P1", "资产缺失", "-100"),
            _result("P2", "实收信托有误", "50"),
        ],
        now=datetime(2026, 5, 28, 10, 0, 0),
    )

    entry = build_history_entry(
        previous_runs=[first],
        run_date="2026-04-30",
        config_name="新名称",
        config=_config(),
        results=[
            _result("P1", "资产缺失", "-100"),
            _result("P3", "资产重复", "80"),
        ],
        now=datetime(2026, 5, 28, 11, 0, 0),
    )

    assert entry["baseline_id"] == first["id"]
    assert entry["baseline_run_at"] == first["run_at"]
    assert entry["baseline_count"] == 2
    assert entry["added_count"] == 1
    assert entry["removed_count"] == 1
    assert entry["added_results"][0]["project_code"] == "P3"
    assert entry["removed_results"][0]["project_code"] == "P2"


def test_history_entry_treats_changed_difference_as_added_and_removed_for_same_project():
    first = build_history_entry(
        previous_runs=[],
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "资产缺失", "-100")],
        now=datetime(2026, 5, 28, 10, 0, 0),
    )

    entry = build_history_entry(
        previous_runs=[first],
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "资产缺失", "-120")],
        now=datetime(2026, 5, 28, 11, 0, 0),
    )

    assert entry["added_count"] == 1
    assert entry["removed_count"] == 1
    assert entry["added_results"][0]["difference"] == "-120"
    assert entry["removed_results"][0]["difference"] == "-100"


def test_history_entry_ignores_reason_change_when_project_and_difference_are_same():
    first = build_history_entry(
        previous_runs=[],
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "资产缺失", "-100")],
        now=datetime(2026, 5, 28, 10, 0, 0),
    )

    entry = build_history_entry(
        previous_runs=[first],
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "暂无法确定", "-100")],
        now=datetime(2026, 5, 28, 11, 0, 0),
    )

    assert entry["added_count"] == 0
    assert entry["removed_count"] == 0


def test_first_run_for_report_period_does_not_compare_previous_report_period():
    previous_period = build_history_entry(
        previous_runs=[],
        run_date="2026-04-29",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "资产缺失", "-100")],
        now=datetime(2026, 5, 28, 9, 0, 0),
    )

    entry = build_history_entry(
        previous_runs=[previous_period],
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P2", "资产重复", "80")],
        now=datetime(2026, 5, 28, 10, 0, 0),
    )

    assert entry["baseline_id"] == ""
    assert entry["baseline_run_at"] == ""
    assert entry["baseline_count"] == 0
    assert entry["added_count"] is None
    assert entry["removed_count"] is None
    assert entry["added_results"] == []
    assert entry["removed_results"] == []


def test_history_entry_ignores_other_dates_but_compares_same_date_across_sources():
    other_date = build_history_entry(
        previous_runs=[],
        run_date="2026-04-29",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "资产缺失", "-100")],
        now=datetime(2026, 5, 28, 9, 0, 0),
    )
    other_config = AppConfig(
        dws=_config().dws,
        business=DataSourceConfig(
            db_type="mysql",
            host="127.0.0.1",
            port=3306,
            database="other_business",
            schema="",
            username="root",
            password="secret",
        ),
    )
    other_source = build_history_entry(
        previous_runs=[],
        run_date="2026-04-30",
        config_name="其他环境",
        config=other_config,
        results=[_result("P2", "资产重复", "80")],
        now=datetime(2026, 5, 28, 9, 30, 0),
    )

    entry = build_history_entry(
        previous_runs=[other_date, other_source],
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P3", "实收信托有误", "50")],
        now=datetime(2026, 5, 28, 10, 0, 0),
    )

    assert entry["baseline_id"] == other_source["id"]
    assert entry["baseline_run_at"] == other_source["run_at"]
    assert entry["baseline_count"] == 1
    assert entry["added_count"] == 1
    assert entry["removed_count"] == 1
    assert entry["added_results"][0]["project_code"] == "P3"
    assert entry["removed_results"][0]["project_code"] == "P2"


def test_json_history_store_persists_lists_gets_and_deletes_runs(tmp_path):
    store = JsonHistoryStore(tmp_path / "history.json")
    first = build_history_entry(
        previous_runs=store.list_runs(),
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "资产缺失", "-100")],
        now=datetime(2026, 5, 28, 10, 0, 0),
    )
    second = build_history_entry(
        previous_runs=[first],
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P2", "资产重复", "80")],
        now=datetime(2026, 5, 28, 11, 0, 0),
    )

    store.save_run(first)
    store.save_run(second)

    assert [entry["id"] for entry in store.list_runs()] == [second["id"], first["id"]]
    assert store.get_run(first["id"])["results"][0]["project_code"] == "P1"
    assert store.delete_run(first["id"]) is True
    assert [entry["id"] for entry in store.list_runs()] == [second["id"]]
    assert store.delete_run("missing") is False


def test_sqlite_history_store_writes_reconcile_results_to_normalized_tables(tmp_path):
    import sqlite3

    config_path = tmp_path / "config.json"
    store = SqliteHistoryStore(config_path)
    run = build_history_entry(
        previous_runs=[],
        run_date="2026-06-30",
        config_name="local",
        dws_source_name="dws",
        config=_config(),
        results=[
            {
                "project_code": "P001",
                "project_name": "Project One",
                "asset_total": "100",
                "liability_equity_total": "80",
                "received_trust_balance": "0",
                "difference": "20",
                "direction": "asset greater than liability and equity",
                "difference_reason": "asset missing",
                "match_status": "explained",
                "valuation_asset_total": "80",
                "details": [
                    {
                        "kind": "asset_gap",
                        "data": {"specific_reason": "specific asset gap", "asset_gap": "20"},
                    }
                ],
            }
        ],
    )

    store.save_run(run)

    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        header_count = connection.execute("SELECT COUNT(*) FROM run_headers").fetchone()[0]
        result_row = connection.execute(
            "SELECT project_code, difference_reason, match_status FROM reconcile_results"
        ).fetchone()
        detail_row = connection.execute(
            "SELECT kind, specific_reason FROM reconcile_result_details"
        ).fetchone()

    assert header_count == 1
    assert result_row == ("P001", "asset missing", "explained")
    assert detail_row == ("asset_gap", "specific asset gap")
    assert store.get_run(run["id"])["results"][0]["project_code"] == "P001"
    assert store.list_runs()[0]["total_count"] == 1


def test_reconcile_history_migrates_from_legacy_history_runs(tmp_path):
    import json
    import sqlite3

    config_path = tmp_path / "config.json"
    legacy_run = build_history_entry(
        previous_runs=[],
        run_date="2026-06-30",
        config_name="legacy",
        config=_config(),
        results=[
            {
                "project_code": "P900",
                "project_name": "Legacy Project",
                "asset_total": "10",
                "liability_equity_total": "8",
                "received_trust_balance": "0",
                "difference": "2",
                "direction": "asset greater than liability and equity",
                "difference_reason": "asset missing",
                "match_status": "explained",
                "details": [],
            }
        ],
    )
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS history_runs (kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, run_date TEXT NOT NULL DEFAULT '', run_at TEXT NOT NULL DEFAULT '', config_fingerprint TEXT NOT NULL DEFAULT '', PRIMARY KEY (kind, id))"
        )
        connection.execute(
            "INSERT INTO history_runs(kind, id, payload, run_date, run_at, config_fingerprint) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "reconcile",
                legacy_run["id"],
                json.dumps(legacy_run, ensure_ascii=False),
                legacy_run["run_date"],
                legacy_run["run_at"],
                legacy_run["config_fingerprint"],
            ),
        )

    store = SqliteHistoryStore(config_path)
    assert store.get_run(legacy_run["id"])["results"][0]["project_code"] == "P900"

    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM reconcile_results").fetchone()[0]
        migration = connection.execute(
            "SELECT status, migrated_count FROM storage_migration_runs WHERE source_type = 'history_runs'"
        ).fetchone()
    assert count == 1
    assert migration == ("completed", 1)


def test_reconcile_history_migrates_from_legacy_history_json_file(tmp_path):
    import json
    import sqlite3

    config_path = tmp_path / "config.json"
    legacy_run = build_history_entry(
        previous_runs=[],
        run_date="2026-06-30",
        config_name="legacy-file",
        config=_config(),
        results=[
            {
                "project_code": "P901",
                "project_name": "Legacy File Project",
                "asset_total": "10",
                "liability_equity_total": "8",
                "received_trust_balance": "0",
                "difference": "2",
                "direction": "asset greater than liability and equity",
                "difference_reason": "asset missing",
                "match_status": "explained",
                "details": [],
            }
        ],
    )
    config_path.with_name("history.json").write_text(
        json.dumps({"runs": [legacy_run]}, ensure_ascii=False),
        encoding="utf-8",
    )

    store = SqliteHistoryStore(config_path)

    assert store.get_run(legacy_run["id"])["results"][0]["project_code"] == "P901"
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        result_count = connection.execute("SELECT COUNT(*) FROM reconcile_results").fetchone()[0]
        migration = connection.execute(
            "SELECT status, migrated_count FROM storage_migration_runs WHERE source_type = 'history_json'"
        ).fetchone()

    assert result_count == 1
    assert migration == ("completed", 1)


def test_db_validation_history_json_imports_to_legacy_history_runs(tmp_path):
    import json
    import sqlite3

    config_path = tmp_path / "config.json"
    config_path.with_name("db-validation-history.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "id": "dbv-1",
                        "run_at": "2026-07-01 10:00:00",
                        "run_date": "2026-06-30",
                        "report_date": "2026-06-30",
                        "status": "completed",
                        "result_count": 2,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = SqliteHistoryStore(config_path, kind="db_validation")

    assert store.get_run("dbv-1")["result_count"] == 2
    assert store.list_runs()[0]["id"] == "dbv-1"
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        row = connection.execute(
            "SELECT report_date, result_count FROM db_validation_runs WHERE id = 'dbv-1'"
        ).fetchone()
    assert row == ("2026-06-30", 2)


def test_sqlite_history_store_writes_db_validation_history_to_normalized_tables(tmp_path):
    import sqlite3

    config_path = tmp_path / "config.json"
    store = SqliteHistoryStore(config_path, kind="db_validation")
    run = {
        "id": "dbv-normalized-1",
        "run_at": "2026-07-03 10:00:00",
        "finished_at": "2026-07-03 10:01:00",
        "run_date": "2026-06-30",
        "report_date": "2026-06-30",
        "status": "completed",
        "result_count": 2,
        "warning_count": 1,
        "table_count": 2,
        "selected_tables": ["ZG01", "ZG02"],
        "warnings": ["ZG02 当期表无数据"],
        "enable_public_info_check": True,
        "enable_template_check": False,
        "excel_filename": "result.xlsx",
        "excel_path": str(tmp_path / "result.xlsx"),
        "download_url": "/api/tools/db-validation/history/download/dbv-normalized-1",
        "rows": [
            {
                "table_code": "ZG01",
                "rule_id": "R001",
                "severity": "error",
                "message": "字段缺失",
                "detail": "第 1 行字段缺失",
            },
            {
                "table_code": "ZG02",
                "rule_id": "R002",
                "severity": "warning",
                "message": "金额不一致",
                "detail": "第 2 行金额不一致",
            },
        ],
    }

    store.save_run(run)

    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        run_row = connection.execute(
            "SELECT report_date, result_count, warning_count, table_count FROM db_validation_runs"
        ).fetchone()
        selected_tables = connection.execute(
            "SELECT table_code FROM db_validation_selected_tables ORDER BY table_order"
        ).fetchall()
        warnings = connection.execute(
            "SELECT message FROM db_validation_warnings ORDER BY warning_order"
        ).fetchall()
        result_rows = connection.execute(
            "SELECT table_code, rule_id, severity FROM db_validation_result_rows ORDER BY row_order"
        ).fetchall()

    assert run_row == ("2026-06-30", 2, 1, 2)
    assert [row[0] for row in selected_tables] == ["ZG01", "ZG02"]
    assert [row[0] for row in warnings] == ["ZG02 当期表无数据"]
    assert result_rows == [("ZG01", "R001", "error"), ("ZG02", "R002", "warning")]
    assert store.get_run(run["id"])["rows"][0]["rule_id"] == "R001"
    assert store.list_runs()[0]["id"] == "dbv-normalized-1"


def test_db_validation_history_migrates_from_legacy_history_runs(tmp_path):
    import json
    import sqlite3

    config_path = tmp_path / "config.json"
    legacy_run = {
        "id": "dbv-legacy-sqlite",
        "run_at": "2026-07-03 11:00:00",
        "run_date": "2026-06-30",
        "report_date": "2026-06-30",
        "status": "completed",
        "result_count": 3,
        "selected_tables": ["ZG01"],
    }
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS history_runs (kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, run_date TEXT NOT NULL DEFAULT '', run_at TEXT NOT NULL DEFAULT '', config_fingerprint TEXT NOT NULL DEFAULT '', PRIMARY KEY (kind, id))"
        )
        connection.execute(
            "INSERT INTO history_runs(kind, id, payload, run_date, run_at, config_fingerprint) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "db_validation",
                legacy_run["id"],
                json.dumps(legacy_run, ensure_ascii=False),
                legacy_run["run_date"],
                legacy_run["run_at"],
                "",
            ),
        )

    store = SqliteHistoryStore(config_path, kind="db_validation")

    assert store.get_run(legacy_run["id"])["result_count"] == 3
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        row = connection.execute(
            "SELECT report_date, result_count FROM db_validation_runs WHERE id = ?",
            (legacy_run["id"],),
        ).fetchone()
    assert row == ("2026-06-30", 3)


def test_sqlite_history_store_writes_flow_chain_history_to_normalized_tables(tmp_path):
    import sqlite3

    config_path = tmp_path / "config.json"
    store = SqliteHistoryStore(config_path, kind="flow_chain")
    run = {
        "id": "flow-normalized-1",
        "run_at": "2026-07-03 12:00:00",
        "finished_at": "2026-07-03 12:01:05",
        "run_date": "2026-07-03",
        "chain_id": "chain-zgxg-1",
        "chain_name": "资管新规1",
        "chain_names": ["资管新规1"],
        "is_multi_chain": False,
        "trigger_type": "manual",
        "executor_name": "管理员",
        "status": "failed",
        "error": "流程B超时",
        "step_count": 2,
        "duration_seconds": 65,
        "steps": [
            {
                "flow_id": "flow-a",
                "flow_name": "流程A",
                "status": "completed",
                "sp_task_id": 658149,
                "begin_time": "2026-07-03 12:00:01",
                "end_time": "2026-07-03 12:00:30",
                "message": "完成",
            },
            {
                "flow_id": "flow-b",
                "flow_name": "流程B",
                "status": "failed",
                "sp_task_id": 658150,
                "begin_time": "2026-07-03 12:00:31",
                "end_time": "2026-07-03 12:01:05",
                "message": "超时",
            },
        ],
        "logs": [
            {
                "time": "2026-07-03 12:01:05",
                "message": "流程B执行失败",
                "progress": 80,
                "step": "流程B",
            }
        ],
        "chain_details": [
            {
                "chain_name": "资管新规1",
                "status": "failed",
                "step_count": 2,
                "duration_seconds": 65,
                "error": "流程B超时",
            }
        ],
    }

    store.save_run(run)

    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        run_row = connection.execute(
            """
            SELECT chain_id, chain_name, is_multi_chain, trigger_type, executor_name,
                   status, error, step_count, duration_seconds
            FROM flow_chain_runs
            """
        ).fetchone()
        step_rows = connection.execute(
            """
            SELECT flow_id, name, status, sp_task_id, start_time, end_time
            FROM flow_chain_run_steps
            ORDER BY step_order
            """
        ).fetchall()
        log_rows = connection.execute(
            """
            SELECT log_time, message, progress, step
            FROM flow_chain_run_logs
            ORDER BY log_order
            """
        ).fetchall()
        detail_rows = connection.execute(
            """
            SELECT chain_name, status, step_count, duration_seconds, error
            FROM flow_chain_run_details
            ORDER BY chain_order
            """
        ).fetchall()

    assert run_row == ("chain-zgxg-1", "资管新规1", 0, "manual", "管理员", "failed", "流程B超时", 2, 65)
    assert step_rows == [
        ("flow-a", "流程A", "completed", "658149", "2026-07-03 12:00:01", "2026-07-03 12:00:30"),
        ("flow-b", "流程B", "failed", "658150", "2026-07-03 12:00:31", "2026-07-03 12:01:05"),
    ]
    assert log_rows == [("2026-07-03 12:01:05", "流程B执行失败", 80, "流程B")]
    assert detail_rows == [("资管新规1", "failed", 2, 65, "流程B超时")]
    assert store.get_run(run["id"])["steps"][1]["message"] == "超时"
    assert store.list_runs()[0]["id"] == "flow-normalized-1"


def test_flow_chain_history_migrates_from_legacy_history_runs(tmp_path):
    import json
    import sqlite3

    config_path = tmp_path / "config.json"
    legacy_run = {
        "id": "flow-legacy-sqlite",
        "run_at": "2026-07-03 13:00:00",
        "finished_at": "2026-07-03 13:01:00",
        "run_date": "2026-07-03",
        "chain_id": "chain-legacy",
        "chain_name": "历史链路",
        "trigger_type": "manual",
        "executor_name": "管理员",
        "status": "completed",
        "step_count": 1,
        "duration_seconds": 60,
        "steps": [
            {
                "flow_id": "flow-legacy",
                "flow_name": "历史流程",
                "status": "completed",
                "sp_task_id": 658200,
            }
        ],
        "chain_details": [
            {
                "chain_name": "历史链路",
                "status": "completed",
                "step_count": 1,
                "duration_seconds": 60,
            }
        ],
    }
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS history_runs (kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, run_date TEXT NOT NULL DEFAULT '', run_at TEXT NOT NULL DEFAULT '', config_fingerprint TEXT NOT NULL DEFAULT '', PRIMARY KEY (kind, id))"
        )
        connection.execute(
            "INSERT INTO history_runs(kind, id, payload, run_date, run_at, config_fingerprint) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "flow_chain",
                legacy_run["id"],
                json.dumps(legacy_run, ensure_ascii=False),
                legacy_run["run_date"],
                legacy_run["run_at"],
                "",
            ),
        )

    store = SqliteHistoryStore(config_path, kind="flow_chain")

    assert store.get_run(legacy_run["id"])["chain_name"] == "历史链路"
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        run_row = connection.execute(
            "SELECT chain_id, chain_name, status, step_count FROM flow_chain_runs WHERE id = ?",
            (legacy_run["id"],),
        ).fetchone()
        step_row = connection.execute(
            "SELECT flow_id, name, sp_task_id FROM flow_chain_run_steps WHERE run_id = ?",
            (legacy_run["id"],),
        ).fetchone()
    assert run_row == ("chain-legacy", "历史链路", "completed", 1)
    assert step_row == ("flow-legacy", "历史流程", "658200")


def test_history_store_sorts_by_run_date_then_run_time_desc(tmp_path):
    store = JsonHistoryStore(tmp_path / "history.json")
    older_check_date_later_run = build_history_entry(
        previous_runs=[],
        run_date="2026-04-30",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "资产缺失", "-100")],
        now=datetime(2026, 6, 1, 12, 0, 0),
    )
    newer_check_date_earlier_run = build_history_entry(
        previous_runs=[],
        run_date="2026-05-31",
        config_name="本地测试",
        config=_config(),
        results=[_result("P2", "资产重复", "80")],
        now=datetime(2026, 5, 31, 9, 0, 0),
    )
    same_check_date_later_run = build_history_entry(
        previous_runs=[],
        run_date="2026-05-31",
        config_name="本地测试",
        config=_config(),
        results=[_result("P3", "实收信托有误", "50")],
        now=datetime(2026, 5, 31, 10, 0, 0),
    )

    store.save_run(older_check_date_later_run)
    store.save_run(newer_check_date_earlier_run)
    store.save_run(same_check_date_later_run)

    assert [entry["id"] for entry in store.list_runs()] == [
        same_check_date_later_run["id"],
        newer_check_date_earlier_run["id"],
        older_check_date_later_run["id"],
    ]


def test_sqlite_history_store_persists_lists_gets_and_deletes_runs(tmp_path):
    config_path = tmp_path / "config.json"
    store = SqliteHistoryStore(config_path)
    first = build_history_entry(
        previous_runs=store.list_runs(),
        run_date="2026-04-30",
        config_name="local",
        config=_config(),
        results=[_result("P1", "asset missing", "-100")],
        now=datetime(2026, 5, 28, 10, 0, 0),
    )
    second = build_history_entry(
        previous_runs=[first],
        run_date="2026-04-30",
        config_name="local",
        config=_config(),
        results=[_result("P2", "asset duplicate", "80")],
        now=datetime(2026, 5, 28, 11, 0, 0),
    )

    store.save_run(first)
    store.save_run(second)

    assert db_path_for_config(config_path).exists()
    assert not config_path.with_name("history.json").exists()
    assert [entry["id"] for entry in store.list_runs()] == [second["id"], first["id"]]
    assert store.get_run(first["id"])["results"][0]["project_code"] == "P1"
    assert store.delete_run(first["id"]) is True
    assert [entry["id"] for entry in store.list_runs()] == [second["id"]]
    assert store.delete_run("missing") is False
