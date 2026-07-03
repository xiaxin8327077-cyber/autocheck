from __future__ import annotations

import json
import sqlite3
from typing import Any, TYPE_CHECKING

from auto_check.app.security import decrypt_secret, encrypt_secret

if TYPE_CHECKING:
    from auto_check.app.config import DataSourceEntry


def has_normalized_config(connection: sqlite3.Connection) -> bool:
    data_source_count = connection.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]
    setting_count = connection.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0]
    return int(data_source_count) > 0 or int(setting_count) > 0


def save_data_sources(connection: sqlite3.Connection, entries: list[DataSourceEntry]) -> None:
    connection.execute("DELETE FROM data_sources")
    for entry in entries:
        source = entry.config
        password_encrypted = encrypt_secret(source.password) if source.password else ""
        connection.execute(
            """
            INSERT INTO data_sources(
                id, name, db_type, host, port, database_name, schema_name,
                username, password_encrypted, is_default, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                str(entry.id),
                str(entry.name),
                str(source.db_type),
                str(source.host),
                int(source.port),
                str(source.database),
                str(source.schema),
                str(source.username),
                password_encrypted,
                1 if entry.is_default else 0,
            ),
        )


def load_data_sources(connection: sqlite3.Connection) -> list[DataSourceEntry]:
    from auto_check.app.config import DataSourceConfig, DataSourceEntry

    rows = connection.execute(
        """
        SELECT id, name, db_type, host, port, database_name, schema_name,
               username, password_encrypted, is_default
        FROM data_sources
        ORDER BY rowid
        """
    ).fetchall()
    entries: list[DataSourceEntry] = []
    for row in rows:
        encrypted_password = str(row["password_encrypted"] or "")
        password = decrypt_secret(encrypted_password) if encrypted_password else ""
        entries.append(
            DataSourceEntry(
                id=str(row["id"]),
                name=str(row["name"]),
                config=DataSourceConfig(
                    db_type=str(row["db_type"]),
                    host=str(row["host"]),
                    port=int(row["port"]),
                    database=str(row["database_name"]),
                    schema=str(row["schema_name"]),
                    username=str(row["username"]),
                    password=password,
                ),
                is_default=bool(row["is_default"]),
            )
        )
    return entries


def save_setting(connection: sqlite3.Connection, key: str, value: Any) -> None:
    connection.execute(
        """
        INSERT INTO app_settings(key, value_json, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at
        """,
        (str(key), json.dumps(value, ensure_ascii=False, sort_keys=True)),
    )


def load_setting(connection: sqlite3.Connection, key: str, default: Any) -> Any:
    row = connection.execute(
        "SELECT value_json FROM app_settings WHERE key = ?",
        (str(key),),
    ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(str(row["value_json"]))
    except json.JSONDecodeError:
        return default


def save_users(connection: sqlite3.Connection, users: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM users")
    for user in users:
        connection.execute(
            """
            INSERT INTO users(
                id, username, display_name, role, password_hash, enabled,
                created_at, updated_at, last_login_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(user.get("id", "")),
                str(user.get("username", "")),
                str(user.get("display_name", "")),
                str(user.get("role", "user")),
                str(user.get("password_hash", "")),
                1 if bool(user.get("enabled", True)) else 0,
                str(user.get("created_at", "")),
                str(user.get("updated_at", "")),
                str(user.get("last_login_at", "")),
            ),
        )


def load_users(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, username, display_name, role, password_hash, enabled,
               created_at, updated_at, last_login_at
        FROM users
        ORDER BY rowid
        """
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "username": str(row["username"]),
            "display_name": str(row["display_name"]),
            "role": str(row["role"]),
            "password_hash": str(row["password_hash"]),
            "enabled": bool(row["enabled"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "last_login_at": str(row["last_login_at"]),
        }
        for row in rows
    ]
