from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_check.app.local_store import _connect, db_path_for_config
from auto_check.app.storage_history import (
    migrate_db_validation_history_json_to_legacy_runs,
    migrate_legacy_db_validation_runs,
    migrate_legacy_flow_chain_runs,
    migrate_legacy_reconcile_runs,
    migrate_reconcile_history_json,
)
from auto_check.app.storage_schema import fingerprint_text


def migrate_legacy_histories(config_path: str | Path) -> dict[str, int]:
    """Manually migrate legacy history sources into normalized history tables."""

    config_path = Path(config_path)
    with _connect(db_path_for_config(config_path)) as connection:
        return {
            "reconcile_history_runs": migrate_legacy_reconcile_runs(connection, config_path),
            "reconcile_history_json": migrate_reconcile_history_json(connection, config_path),
            "db_validation_history_runs": migrate_legacy_db_validation_runs(connection, config_path),
            "db_validation_history_json": migrate_db_validation_history_json_to_legacy_runs(connection, config_path),
            "flow_chain_history_runs": migrate_legacy_flow_chain_runs(connection, config_path),
        }


def build_legacy_history_migration_status(config_path: str | Path) -> dict[str, Any]:
    config_path = Path(config_path)
    db_path = db_path_for_config(config_path)
    with _connect(db_path) as connection:
        sources = [
            _history_runs_source_status(connection, config_path, "reconcile", "自动对数旧历史表"),
            _history_json_source_status(connection, config_path.with_name("history.json"), "history_json", "自动对数旧 history.json"),
            _history_runs_source_status(connection, config_path, "db_validation", "人行逐笔旧历史表"),
            _history_json_source_status(
                connection,
                config_path.with_name("db-validation-history.json"),
                "db_validation_history_json",
                "人行逐笔旧 db-validation-history.json",
            ),
            _history_runs_source_status(connection, config_path, "flow_chain", "流程链旧历史表"),
        ]
    pending_count = sum(1 for source in sources if source["state"] == "pending")
    failed_count = sum(1 for source in sources if source["state"] == "failed")
    completed_count = sum(1 for source in sources if source["state"] == "completed")
    existing_count = sum(1 for source in sources if source["exists"])
    can_migrate = any(source["can_migrate"] for source in sources)
    if can_migrate:
        status_text = f"发现 {pending_count + failed_count} 个旧历史来源待迁移"
    elif existing_count:
        status_text = "旧历史迁移已全部完成"
    else:
        status_text = "未发现旧历史数据"
    return {
        "can_migrate": can_migrate,
        "completed": not can_migrate,
        "has_legacy_sources": existing_count > 0,
        "source_count": len(sources),
        "existing_count": existing_count,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "completed_count": completed_count,
        "status_text": status_text,
        "sources": sources,
    }


def _history_runs_source_status(connection, config_path: Path, kind: str, label: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT payload
        FROM history_runs
        WHERE kind = ?
        ORDER BY run_date DESC, run_at DESC
        """,
        (kind,),
    ).fetchall()
    payloads = [str(row["payload"] or "") for row in rows]
    source_path = str(config_path.with_name("auto-check.db"))
    source_fingerprint = fingerprint_text("\n".join(payloads)) if payloads else ""
    return _source_status(
        connection,
        label=label,
        source_type="history_runs",
        source_path=source_path,
        source_key=kind,
        source_fingerprint=source_fingerprint,
        record_count=len(payloads),
        exists=bool(payloads),
    )


def _history_json_source_status(connection, path: Path, source_type: str, label: str) -> dict[str, Any]:
    try:
        source_text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        source_text = ""
        return _source_status(
            connection,
            label=label,
            source_type=source_type,
            source_path=str(path),
            source_key="",
            source_fingerprint="",
            record_count=0,
            exists=True,
            error=str(exc),
        )
    record_count, error = _json_history_record_count(source_text) if source_text else (0, "")
    return _source_status(
        connection,
        label=label,
        source_type=source_type,
        source_path=str(path),
        source_key="",
        source_fingerprint=fingerprint_text(source_text) if source_text else "",
        record_count=record_count,
        exists=path.exists() and bool(source_text),
        error=error,
    )


def _source_status(
    connection,
    *,
    label: str,
    source_type: str,
    source_path: str,
    source_key: str,
    source_fingerprint: str,
    record_count: int,
    exists: bool,
    error: str = "",
) -> dict[str, Any]:
    migration = _migration_row(connection, source_type, source_path, source_key, source_fingerprint) if exists else None
    migration_status = str(migration["status"]) if migration is not None else ""
    if not exists:
        state = "not_found"
        can_migrate = False
    elif migration_status == "completed":
        state = "completed"
        can_migrate = False
    elif migration_status == "failed":
        state = "failed"
        can_migrate = True
    else:
        state = "pending"
        can_migrate = True
    return {
        "label": label,
        "source_type": source_type,
        "source_path": source_path,
        "source_key": source_key,
        "source_fingerprint": source_fingerprint,
        "record_count": record_count,
        "exists": exists,
        "state": state,
        "can_migrate": can_migrate,
        "migration_status": migration_status,
        "migrated_count": int(migration["migrated_count"]) if migration is not None else 0,
        "skipped_count": int(migration["skipped_count"]) if migration is not None else 0,
        "message": error or (str(migration["message"]) if migration is not None else ""),
        "finished_at": str(migration["finished_at"]) if migration is not None else "",
    }


def _migration_row(connection, source_type: str, source_path: str, source_key: str, source_fingerprint: str):
    return connection.execute(
        """
        SELECT status, migrated_count, skipped_count, message, finished_at
        FROM storage_migration_runs
        WHERE source_type = ?
          AND source_path = ?
          AND source_key = ?
          AND source_fingerprint = ?
        """,
        (source_type, source_path, source_key, source_fingerprint),
    ).fetchone()


def _json_history_record_count(source_text: str) -> tuple[int, str]:
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        return 0, f"JSON 解析失败：{exc.msg}"
    if isinstance(payload, list):
        return len(payload), ""
    if isinstance(payload, dict):
        runs = payload.get("runs", [])
        return len(runs) if isinstance(runs, list) else 0, ""
    return 0, "JSON 顶层结构不是对象或数组"
