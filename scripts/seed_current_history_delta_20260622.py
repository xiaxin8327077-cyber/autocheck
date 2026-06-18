from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from auto_check.app.config import AppConfig, default_config_path, load_store, normalize_store, resolve_data_source
from auto_check.app.history import SqliteHistoryStore, build_history_entry
from auto_check.app.local_store import db_path_for_config, list_history_runs


REPORT_DATE = "2026-06-22"
PROJECT_PREFIX = "DELTA20260622"
HISTORY_EXECUTOR_ID = "seed-history-delta-20260622"


def main() -> None:
    config_path = default_config_path()
    store = normalize_store(load_store(config_path))
    dws_config = resolve_data_source(store, store.reconcile_data_sources.dws_source_id)
    business_config = resolve_data_source(store, store.reconcile_data_sources.business_source_id)
    config = AppConfig(dws=dws_config, business=business_config)

    _delete_previous_generated_history(config_path)

    history_store = SqliteHistoryStore(config_path, kind="reconcile")
    baseline = build_history_entry(
        previous_runs=[],
        run_date=REPORT_DATE,
        config_name="6.22新增减少测试数据",
        dws_source_name="6.22新增减少测试数据",
        config=config,
        results=[*_stable_results(), *_removed_results()],
        executor_id=HISTORY_EXECUTOR_ID,
        executor_username="admin",
        executor_name="管理员",
        now=datetime(2026, 6, 22, 9, 0, 0),
    )
    current = build_history_entry(
        previous_runs=[baseline],
        run_date=REPORT_DATE,
        config_name="6.22新增减少测试数据",
        dws_source_name="6.22新增减少测试数据",
        config=config,
        results=[*_stable_results(), *_added_results()],
        executor_id=HISTORY_EXECUTOR_ID,
        executor_username="admin",
        executor_name="管理员",
        now=datetime(2026, 6, 22, 10, 0, 0),
    )

    history_store.save_run(baseline)
    history_store.save_run(current)
    _print_verification(config_path)


def _stable_results() -> list[dict]:
    return [
        _result(f"{PROJECT_PREFIX}ST{i:02d}", f"江苏信托-6.22稳定项目{i:02d}", "资产差异", i, "已解释")
        for i in range(1, 11)
    ]


def _added_results() -> list[dict]:
    return [
        _result(f"{PROJECT_PREFIX}AD{i:02d}", f"江苏信托-6.22本次新增项目{i:02d}", "资产缺失", i + 10, "未解释")
        for i in range(1, 11)
    ]


def _removed_results() -> list[dict]:
    return [
        _result(f"{PROJECT_PREFIX}RM{i:02d}", f"江苏信托-6.22本次减少项目{i:02d}", "负债及权益科目缺失", i + 20, "已解释")
        for i in range(1, 11)
    ]


def _result(project_code: str, project_name: str, reason: str, index: int, status: str) -> dict:
    difference = 100000 + index * 1000
    return {
        "project_code": project_code,
        "project_name": project_name,
        "asset_total": str(50000000 + difference),
        "valuation_asset_total": str(50000000),
        "liability_equity_total": str(50000000),
        "difference": str(difference),
        "difference_reason": reason,
        "specific_reason": f"{reason}，用于验证历史详情新增/减少/全部列表展示。",
        "match_status": status,
    }


def _delete_previous_generated_history(config_path: Path) -> None:
    db_path = db_path_for_config(config_path)
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            DELETE FROM history_runs
            WHERE kind = 'reconcile'
              AND (
                payload LIKE ?
                OR payload LIKE ?
              )
            """,
            (f'%"executor_id": "{HISTORY_EXECUTOR_ID}"%', f"%{PROJECT_PREFIX}%"),
        )


def _print_verification(config_path: Path) -> None:
    runs = [
        run
        for run in list_history_runs(config_path, "reconcile")
        if str(run.get("executor_id") or "") == HISTORY_EXECUTOR_ID
    ]
    runs.sort(key=lambda item: str(item.get("run_at") or ""), reverse=True)
    if not runs:
        print("No generated history found")
        return
    latest = runs[0]
    print(
        "Seeded 2026-06-22 history delta scenario: "
        f"total={latest.get('total_count')}, "
        f"added={latest.get('added_count')}, "
        f"removed={latest.get('removed_count')}"
    )


if __name__ == "__main__":
    main()
