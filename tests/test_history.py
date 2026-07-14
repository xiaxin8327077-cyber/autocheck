from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest

from auto_check.app import storage_history
from auto_check.app.config import AppConfig, DataSourceConfig
from auto_check.app.history import DatabaseHistoryStore, JsonHistoryStore, build_history_entry
from mysql_config_test_support import MemoryApplicationDatabase


@pytest.fixture
def app_database() -> MemoryApplicationDatabase:
    return MemoryApplicationDatabase()


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


def _reconcile_run(run_id: str = "reconcile-1") -> dict:
    return {
        "id": run_id,
        "run_date": date(2026, 6, 30),
        "run_at": datetime(2026, 7, 1, 10, 0, 0),
        "finished_at": datetime(2026, 7, 1, 10, 1, 0),
        "status": "completed",
        "executor_id": "u1",
        "executor_username": "operator",
        "executor_name": "张三",
        "config_name": "local",
        "dws_source_name": "dws",
        "config_fingerprint": "abc",
        "rule_version": "logic-test",
        "baseline_id": "baseline-1",
        "baseline_run_at": datetime(2026, 6, 30, 9, 0, 0),
        "baseline_count": 1,
        "total_count": 1,
        "added_count": 0,
        "removed_count": 0,
        "status_counts": {"explained": 1},
        "reason_counts": {"asset missing": 1},
        "results": [
            {
                "project_code": "P001",
                "project_name": "Project One",
                "asset_total": Decimal("100.10"),
                "liability_equity_total": Decimal("80.00"),
                "received_trust_balance": Decimal("0"),
                "difference": Decimal("20.10"),
                "direction": "asset greater than liability and equity",
                "difference_reason": "asset missing",
                "match_status": "explained",
                "valuation_asset_total": Decimal("80.00"),
                "details": [
                    {
                        "kind": "asset_gap",
                        "data": {"specific_reason": "specific asset gap", "asset_gap": "20.10"},
                    }
                ],
            }
        ],
        "added_results": [],
        "removed_results": [],
    }


def _db_validation_run(run_id: str = "dbv-1") -> dict:
    return {
        "id": run_id,
        "run_at": datetime(2026, 7, 3, 10, 0, 0),
        "finished_at": datetime(2026, 7, 3, 10, 1, 0),
        "run_date": date(2026, 6, 30),
        "report_date": date(2026, 6, 30),
        "status": "completed",
        "result_count": 2,
        "warning_count": 1,
        "table_count": 2,
        "selected_tables": ["ZG01", "ZG02"],
        "warnings": ["ZG02 当期表无数据"],
        "enable_public_info_check": True,
        "enable_template_check": False,
        "excel_filename": "result.xlsx",
        "excel_path": "C:/tmp/result.xlsx",
        "download_url": "/api/tools/db-validation/history/download/dbv-1",
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


def _flow_chain_run(run_id: str = "flow-1") -> dict:
    return {
        "id": run_id,
        "run_at": datetime(2026, 7, 3, 12, 0, 0),
        "finished_at": datetime(2026, 7, 3, 12, 1, 5),
        "run_date": date(2026, 7, 3),
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
                "begin_time": datetime(2026, 7, 3, 12, 0, 1),
                "end_time": datetime(2026, 7, 3, 12, 0, 30),
                "message": "完成",
            },
            {
                "flow_id": "flow-b",
                "flow_name": "流程B",
                "status": "failed",
                "sp_task_id": 658150,
                "begin_time": datetime(2026, 7, 3, 12, 0, 31),
                "end_time": datetime(2026, 7, 3, 12, 1, 5),
                "message": "超时",
            },
        ],
        "logs": [
            {
                "time": datetime(2026, 7, 3, 12, 1, 5),
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


def test_history_entry_ignores_other_dates_but_compares_same_date_across_sources():
    other_date = build_history_entry(
        previous_runs=[],
        run_date="2026-04-29",
        config_name="本地测试",
        config=_config(),
        results=[_result("P1", "资产缺失", "-100")],
        now=datetime(2026, 5, 28, 9, 0, 0),
    )
    other_source = build_history_entry(
        previous_runs=[],
        run_date="2026-04-30",
        config_name="其他环境",
        config=_config(),
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
    assert entry["added_count"] == 1
    assert entry["removed_count"] == 1


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


def test_database_history_store_writes_reconcile_results_to_mysql_tables(app_database):
    store = DatabaseHistoryStore(app_database)
    run = _reconcile_run()

    store.save_run(run)

    tables = app_database.connection.tables
    assert len(tables["run_headers"]) == 1
    assert tables["run_headers"][0]["run_date"] == date(2026, 6, 30)
    assert tables["run_headers"][0]["run_at"] == datetime(2026, 7, 1, 10, 0, 0)
    assert tables["reconcile_runs"][0]["baseline_run_at"] == datetime(2026, 6, 30, 9, 0, 0)
    assert tables["reconcile_results"][0]["asset_total"] == Decimal("100.10")
    assert tables["reconcile_results"][0]["difference_reason"] == "asset missing"
    assert tables["reconcile_result_details"][0]["specific_reason"] == "specific asset gap"
    assert store.get_run(run["id"])["results"][0]["asset_total"] == "100.10"
    assert store.count_runs() == 1


def test_database_history_store_persists_lists_gets_and_deletes_runs(app_database):
    store = DatabaseHistoryStore(app_database)
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

    assert [entry["id"] for entry in store.list_runs()] == [second["id"], first["id"]]
    assert store.get_run(first["id"])["results"][0]["project_code"] == "P1"
    assert store.delete_run(first["id"]) is True
    assert store.get_run(first["id"]) is None
    assert [entry["id"] for entry in store.list_runs()] == [second["id"]]
    assert store.delete_run("missing") is False
    assert all(row["run_id"] == second["id"] for row in app_database.connection.tables["reconcile_results"])


def test_database_history_store_sorts_reconcile_by_run_date_then_run_time_desc(app_database):
    store = DatabaseHistoryStore(app_database)
    runs = [
        _reconcile_run("older-date-later-run"),
        _reconcile_run("newer-date-earlier-run"),
        _reconcile_run("same-date-later-run"),
    ]
    runs[0]["run_date"] = "2026-04-30"
    runs[0]["run_at"] = "2026-06-01 12:00:00"
    runs[1]["run_date"] = "2026-05-31"
    runs[1]["run_at"] = "2026-05-31 09:00:00"
    runs[2]["run_date"] = "2026-05-31"
    runs[2]["run_at"] = "2026-05-31 10:00:00"

    for run in runs:
        store.save_run(run)

    assert [entry["id"] for entry in store.list_runs()] == [
        "same-date-later-run",
        "newer-date-earlier-run",
        "older-date-later-run",
    ]


def test_database_history_store_replaces_owned_children_in_one_save(app_database):
    store = DatabaseHistoryStore(app_database)
    run = _reconcile_run()
    store.save_run(run)

    updated = _reconcile_run()
    updated["results"] = [
        {
            "project_code": "P002",
            "project_name": "Project Two",
            "difference": "0",
            "difference_reason": "balanced",
            "match_status": "explained",
            "details": [],
        }
    ]
    updated["status_counts"] = {"explained": 1}
    updated["reason_counts"] = {"balanced": 1}
    store.save_run(updated)

    tables = app_database.connection.tables
    assert [row["project_code"] for row in tables["reconcile_results"]] == ["P002"]
    assert [row["label"] for row in tables["reconcile_run_counts"] if row["count_type"] == "reason"] == ["balanced"]
    assert tables["reconcile_result_details"] == []


def test_database_history_store_rolls_back_failed_reconcile_save(app_database, monkeypatch):
    store = DatabaseHistoryStore(app_database)
    run = _reconcile_run()
    run["added_results"] = [{"project_code": "P999"}]

    def fail_delta_insert(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(storage_history, "_insert_delta_result", fail_delta_insert)

    with pytest.raises(RuntimeError, match="boom"):
        store.save_run(run)

    assert app_database.connection.tables["run_headers"] == []
    assert app_database.connection.tables["reconcile_runs"] == []
    assert app_database.connection.tables["reconcile_results"] == []


def test_database_history_store_writes_db_validation_history_to_mysql_tables(app_database):
    store = DatabaseHistoryStore(app_database, kind="db_validation")
    run = _db_validation_run()

    store.save_run(run)

    tables = app_database.connection.tables
    assert tables["db_validation_runs"][0]["report_date"] == date(2026, 6, 30)
    assert tables["db_validation_runs"][0]["result_count"] == 2
    assert [row["table_code"] for row in tables["db_validation_selected_tables"]] == ["ZG01", "ZG02"]
    assert [row["message"] for row in tables["db_validation_warnings"]] == ["ZG02 当期表无数据"]
    assert [(row["table_code"], row["rule_id"], row["severity"]) for row in tables["db_validation_result_rows"]] == [
        ("ZG01", "R001", "error"),
        ("ZG02", "R002", "warning"),
    ]
    assert store.get_run(run["id"])["rows"][0]["rule_id"] == "R001"
    assert store.list_runs()[0]["id"] == "dbv-1"


def test_database_history_store_lists_db_validation_summaries_without_payload_json(app_database):
    store = DatabaseHistoryStore(app_database, kind="db_validation")
    run = _db_validation_run()
    store.save_run(run)
    app_database.connection.executed_sql.clear()

    summaries = store.list_summaries()

    assert summaries == [
        {
            "id": "dbv-1",
            "run_at": "2026-07-03 10:00:00",
            "finished_at": "2026-07-03 10:01:00",
            "run_date": "2026-06-30",
            "report_date": "2026-06-30",
            "status": "completed",
            "executor_id": "",
            "executor_username": "",
            "executor_name": "",
            "result_count": 2,
            "warning_count": 1,
            "table_count": 2,
            "enable_public_info_check": True,
            "enable_template_check": False,
            "download_url": "/api/tools/db-validation/history/download/dbv-1",
        }
    ]
    assert "excel_path" not in summaries[0]
    assert all("payload_json" not in sql for sql in app_database.connection.executed_sql)


def test_database_history_store_reads_db_validation_download_metadata_without_payload_json(app_database):
    store = DatabaseHistoryStore(app_database, kind="db_validation")
    store.save_run(_db_validation_run())
    app_database.connection.executed_sql.clear()

    metadata = store.get_download_metadata("dbv-1")

    assert metadata == {"excel_path": "C:/tmp/result.xlsx", "excel_filename": "result.xlsx"}
    assert all("payload_json" not in sql for sql in app_database.connection.executed_sql)


def test_database_history_store_writes_flow_chain_history_to_mysql_tables(app_database):
    store = DatabaseHistoryStore(app_database, kind="flow_chain")
    run = _flow_chain_run()

    store.save_run(run)

    tables = app_database.connection.tables
    assert tables["flow_chain_runs"][0]["chain_name"] == "资管新规1"
    assert tables["flow_chain_runs"][0]["is_multi_chain"] is False
    assert [(row["flow_id"], row["name"], row["sp_task_id"]) for row in tables["flow_chain_run_steps"]] == [
        ("flow-a", "流程A", "658149"),
        ("flow-b", "流程B", "658150"),
    ]
    assert tables["flow_chain_run_logs"][0]["log_time"] == time(12, 1, 5)
    assert tables["flow_chain_run_details"][0]["error"] == "流程B超时"
    assert store.get_run(run["id"])["steps"][1]["message"] == "超时"
    assert store.list_runs()[0]["id"] == "flow-1"
