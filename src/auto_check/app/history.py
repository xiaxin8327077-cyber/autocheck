from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from auto_check.app.config import AppConfig, default_config_path
from auto_check.app.local_store import delete_history_run, get_history_run, list_history_runs, save_history_run
from auto_check.app.time_utils import beijing_now


RULE_VERSION = "logic-2026-06-12-v1"


class HistoryStore(Protocol):
    """Storage boundary for check history."""

    def list_runs(self) -> list[dict[str, Any]]: ...

    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    def save_run(self, run: dict[str, Any]) -> None: ...

    def delete_run(self, run_id: str) -> bool: ...


class JsonHistoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def list_runs(self) -> list[dict[str, Any]]:
        return sorted(_load_runs(self.path), key=_history_sort_key, reverse=True)

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


class SqliteHistoryStore:
    def __init__(self, config_path: str | Path, *, kind: str = "reconcile"):
        self.config_path = Path(config_path)
        self.kind = str(kind or "reconcile")

    def list_runs(self) -> list[dict[str, Any]]:
        return list_history_runs(self.config_path, self.kind)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return get_history_run(self.config_path, self.kind, run_id)

    def save_run(self, run: dict[str, Any]) -> None:
        save_history_run(self.config_path, self.kind, run)

    def delete_run(self, run_id: str) -> bool:
        return delete_history_run(self.config_path, self.kind, run_id)


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
