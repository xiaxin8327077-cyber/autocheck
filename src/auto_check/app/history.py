from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from auto_check.app.app_database import ApplicationDatabase
from auto_check.app.config import AppConfig, default_config_path
from auto_check.app.storage_history import (
    count_kind_runs,
    delete_db_validation_run,
    delete_flow_chain_run,
    delete_reconcile_run,
    get_db_validation_download_metadata,
    get_db_validation_run,
    get_flow_chain_run,
    get_reconcile_run,
    list_db_validation_runs,
    list_db_validation_run_summaries,
    list_flow_chain_runs,
    list_reconcile_runs,
    save_db_validation_run,
    save_flow_chain_run,
    save_reconcile_run,
)
from auto_check.app.time_utils import beijing_now


RULE_VERSION = "logic-2026-06-12-v1"


class HistoryStore(Protocol):
    """Storage boundary for check history."""

    def list_runs(self) -> list[dict[str, Any]]: ...

    def count_runs(self) -> int: ...

    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    def save_run(self, run: dict[str, Any]) -> None: ...

    def delete_run(self, run_id: str) -> bool: ...


class JsonHistoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def list_runs(self) -> list[dict[str, Any]]:
        return sorted(_load_runs(self.path), key=_history_sort_key, reverse=True)

    def count_runs(self) -> int:
        return len(_load_runs(self.path))

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        for run in self.list_runs():
            if run.get("id") == run_id:
                return run
        return None

    def save_run(self, run: dict[str, Any]) -> None:
        runs = [item for item in _load_runs(self.path) if item.get("id") != run.get("id")]
        runs.append(run)
        _save_runs(self.path, sorted(runs, key=_history_sort_key, reverse=True))

    def delete_run(self, run_id: str) -> bool:
        runs = _load_runs(self.path)
        kept = [run for run in runs if run.get("id") != run_id]
        if len(kept) == len(runs):
            return False
        _save_runs(self.path, kept)
        return True


class DatabaseHistoryStore:
    def __init__(self, database: ApplicationDatabase, *, kind: str = "reconcile"):
        self.database = database
        self.kind = str(kind or "reconcile")

    def list_runs(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            if self.kind == "reconcile":
                return list_reconcile_runs(connection)
            if self.kind == "db_validation":
                return list_db_validation_runs(connection)
            if self.kind == "flow_chain":
                return list_flow_chain_runs(connection)
        return []

    def count_runs(self) -> int:
        if self.kind in {"reconcile", "db_validation", "flow_chain"}:
            with self.database.connect() as connection:
                return count_kind_runs(connection, self.kind)
        return 0

    def list_summaries(self) -> list[dict[str, Any]]:
        if self.kind == "db_validation":
            with self.database.connect() as connection:
                return list_db_validation_run_summaries(connection)
        return [summarize_run(run) for run in self.list_runs()]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            if self.kind == "reconcile":
                run = get_reconcile_run(connection, run_id)
                return run
            if self.kind == "db_validation":
                run = get_db_validation_run(connection, run_id)
                return run
            if self.kind == "flow_chain":
                run = get_flow_chain_run(connection, run_id)
                return run
        return None

    def get_download_metadata(self, run_id: str) -> dict[str, str] | None:
        if self.kind != "db_validation":
            return None
        with self.database.connect() as connection:
            return get_db_validation_download_metadata(connection, run_id)

    def save_run(self, run: dict[str, Any]) -> None:
        with self.database.transaction() as connection:
            if self.kind == "reconcile":
                save_reconcile_run(connection, run)
            elif self.kind == "db_validation":
                save_db_validation_run(connection, run)
            elif self.kind == "flow_chain":
                save_flow_chain_run(connection, run)

    def delete_run(self, run_id: str) -> bool:
        with self.database.transaction() as connection:
            if self.kind == "reconcile":
                return delete_reconcile_run(connection, run_id)
            if self.kind == "db_validation":
                return delete_db_validation_run(connection, run_id)
            if self.kind == "flow_chain":
                return delete_flow_chain_run(connection, run_id)
        return False


def default_history_path(config_path: str | Path | None = None) -> Path:
    base_path = Path(config_path) if config_path is not None else default_config_path()
    return base_path.with_name("history.json")


def default_db_validation_history_path(config_path: str | Path | None = None) -> Path:
    base_path = Path(config_path) if config_path is not None else default_config_path()
    return base_path.with_name("db-validation-history.json")


def build_history_entry(
    *,
    previous_runs: list[dict[str, Any]],
    run_date: str,
    config_name: str,
    dws_source_name: str = "",
    config: AppConfig,
    results: list[dict[str, Any]],
    executor_id: str = "",
    executor_username: str = "",
    executor_name: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or beijing_now()
    fingerprint = config_fingerprint(config)
    baseline = _latest_baseline(previous_runs, run_date)
    has_baseline = baseline is not None
    baseline_results = baseline.get("results", []) if baseline else []
    added_results, removed_results = _diff_results(baseline_results, results) if has_baseline else ([], [])

    return {
        "id": uuid4().hex,
        "run_at": current_time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_date": run_date,
        "config_name": config_name,
        "dws_source_name": str(dws_source_name or ""),
        "executor_id": str(executor_id or ""),
        "executor_username": str(executor_username or ""),
        "executor_name": str(executor_name or executor_username or ""),
        "config_fingerprint": fingerprint,
        "rule_version": RULE_VERSION,
        "baseline_id": str(baseline.get("id", "")) if baseline else "",
        "baseline_run_at": str(baseline.get("run_at", "")) if baseline else "",
        "baseline_count": len(baseline_results),
        "total_count": len(results),
        "status_counts": dict(Counter(str(item.get("match_status", "")) for item in results)),
        "reason_counts": dict(Counter(str(item.get("difference_reason", "")) for item in results)),
        "added_count": len(added_results) if has_baseline else None,
        "removed_count": len(removed_results) if has_baseline else None,
        "results": results,
        "added_results": added_results,
        "removed_results": removed_results,
    }


def config_fingerprint(config: AppConfig) -> str:
    payload = asdict(config)
    for source in ("dws", "business"):
        payload[source].pop("password", None)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def summarize_run(run: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in run.items() if key not in {"results", "added_results", "removed_results"}}


def _load_runs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, list):
        return payload
    return list(payload.get("runs", []))


def _save_runs(path: Path, runs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump({"runs": runs}, file, ensure_ascii=False, indent=2)


def _latest_baseline(
    previous_runs: list[dict[str, Any]],
    run_date: str,
) -> dict[str, Any] | None:
    candidates = [
        run
        for run in previous_runs
        if run.get("run_date") == run_date
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda run: str(run.get("run_at", "")), reverse=True)[0]


def _history_sort_key(run: dict[str, Any]) -> tuple[str, str]:
    return (str(run.get("run_date", "")), str(run.get("run_at", "")))


def _diff_results(
    old_results: list[dict[str, Any]],
    new_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    old_by_key = {_result_key(item): item for item in old_results}
    new_by_key = {_result_key(item): item for item in new_results}
    added = [item for key, item in new_by_key.items() if key not in old_by_key]
    removed = [item for key, item in old_by_key.items() if key not in new_by_key]
    return added, removed


def _result_key(result: dict[str, Any]) -> tuple[str, str]:
    return (
        str(result.get("project_code", "")),
        str(result.get("difference", "")),
    )
