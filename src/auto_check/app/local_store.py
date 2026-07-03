from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from auto_check.app.storage_schema import ensure_storage_schema


CONFIG_STORE_KEY = "config_store"
AUTH_KEY = "auth"


def db_path_for_config(config_path: str | Path) -> Path:
    return Path(config_path).with_name("auto-check.db")


def read_app_value(config_path: str | Path, key: str) -> Any | None:
    db_path = db_path_for_config(config_path)
    with _connect(db_path) as connection:
        row = connection.execute("SELECT value FROM app_kv WHERE key = ?", (str(key),)).fetchone()
    if row is None:
        return None
    return json.loads(str(row["value"]))


def write_app_value(config_path: str | Path, key: str, value: Any) -> None:
    with _connect(db_path_for_config(config_path)) as connection:
        connection.execute(
            """
            INSERT INTO app_kv(key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (str(key), json.dumps(value, ensure_ascii=False, sort_keys=True)),
        )


def load_json_file_payload(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_json_file_payload(config_path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def load_combined_payload(config_path: str | Path) -> dict[str, Any]:
    config_payload = read_app_value(config_path, CONFIG_STORE_KEY)
    auth_payload = read_app_value(config_path, AUTH_KEY)
    if isinstance(config_payload, dict) or isinstance(auth_payload, dict):
        payload = dict(config_payload) if isinstance(config_payload, dict) else {}
        if isinstance(auth_payload, dict):
            payload[AUTH_KEY] = auth_payload
        return payload

    payload = load_json_file_payload(config_path)
    auth = payload.get(AUTH_KEY)
    if isinstance(auth, dict):
        write_app_value(config_path, AUTH_KEY, auth)
    return payload


def save_combined_payload(config_path: str | Path, payload: dict[str, Any]) -> None:
    auth = payload.get(AUTH_KEY)
    config_payload = {key: value for key, value in payload.items() if key != AUTH_KEY}
    if config_payload:
        write_app_value(config_path, CONFIG_STORE_KEY, config_payload)
    if isinstance(auth, dict):
        write_app_value(config_path, AUTH_KEY, auth)

    snapshot = dict(config_payload)
    if isinstance(auth, dict):
        snapshot[AUTH_KEY] = auth
    save_json_file_payload(config_path, snapshot)


def list_history_runs(config_path: str | Path, kind: str) -> list[dict[str, Any]]:
    db_path = db_path_for_config(config_path)
    if not db_path.exists():
        return []
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT payload
            FROM history_runs
            WHERE kind = ?
            ORDER BY run_date DESC, run_at DESC
            """,
            (str(kind),),
        ).fetchall()
    return [json.loads(str(row["payload"])) for row in rows]


def get_history_run(config_path: str | Path, kind: str, run_id: str) -> dict[str, Any] | None:
    db_path = db_path_for_config(config_path)
    if not db_path.exists():
        return None
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT payload FROM history_runs WHERE kind = ? AND id = ?",
            (str(kind), str(run_id)),
        ).fetchone()
    if row is None:
        return None
    return json.loads(str(row["payload"]))


def save_history_run(config_path: str | Path, kind: str, run: dict[str, Any]) -> None:
    run_id = str(run.get("id", "") or "")
    if not run_id:
        raise ValueError("history run id is required")
    with _connect(db_path_for_config(config_path)) as connection:
        connection.execute(
            """
            INSERT INTO history_runs(kind, id, payload, run_date, run_at, config_fingerprint)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, id) DO UPDATE SET
                payload = excluded.payload,
                run_date = excluded.run_date,
                run_at = excluded.run_at,
                config_fingerprint = excluded.config_fingerprint
            """,
            (
                str(kind),
                run_id,
                json.dumps(run, ensure_ascii=False, sort_keys=True),
                str(run.get("run_date", "") or ""),
                str(run.get("run_at", "") or ""),
                str(run.get("config_fingerprint", "") or ""),
            ),
        )


def delete_history_run(config_path: str | Path, kind: str, run_id: str) -> bool:
    db_path = db_path_for_config(config_path)
    if not db_path.exists():
        return False
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM history_runs WHERE kind = ? AND id = ?",
            (str(kind), str(run_id)),
        )
        return cursor.rowcount > 0


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    _ensure_schema(connection)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _ensure_schema(connection: sqlite3.Connection) -> None:
    ensure_storage_schema(connection)
