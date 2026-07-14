from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.mysql import DATETIME, insert as mysql_insert
from sqlalchemy.engine import Connection

from auto_check.app.security import decrypt_secret, encrypt_secret

if TYPE_CHECKING:
    from auto_check.app.config import DataSourceEntry


_METADATA = MetaData()

_DATA_SOURCES = Table(
    "data_sources",
    _METADATA,
    Column("id", String(255), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("db_type", String(32), nullable=False),
    Column("host", String(255), nullable=False),
    Column("port", Integer, nullable=False),
    Column("database_name", String(255), nullable=False),
    Column("schema_name", String(255), nullable=False),
    Column("username", String(255), nullable=False),
    Column("password_encrypted", Text, nullable=False),
    Column("is_default", Boolean, nullable=False),
    Column("created_at", DATETIME(fsp=6), nullable=False),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)

_APP_SETTINGS = Table(
    "app_settings",
    _METADATA,
    Column("key", String(255), primary_key=True),
    Column("value_json", Text, nullable=False),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)

_CONFIG_SNAPSHOTS = Table(
    "config_snapshots",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("fingerprint", String(64), nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("created_at", DATETIME(fsp=6), nullable=False),
)


def has_normalized_config(connection: Connection) -> bool:
    data_source_count = connection.execute(
        select(func.count()).select_from(_DATA_SOURCES)
    ).scalar_one()
    setting_count = connection.execute(
        select(func.count()).select_from(_APP_SETTINGS)
    ).scalar_one()
    return int(data_source_count) > 0 or int(setting_count) > 0


def save_data_sources(connection: Connection, entries: list[DataSourceEntry]) -> None:
    entry_ids = [str(entry.id) for entry in entries]
    delete_statement = delete(_DATA_SOURCES)
    if entry_ids:
        delete_statement = delete_statement.where(_DATA_SOURCES.c.id.not_in(entry_ids))
    connection.execute(delete_statement)

    now = _utc_now()
    for entry in entries:
        source = entry.config
        password_encrypted = encrypt_secret(source.password) if source.password else ""
        statement = mysql_insert(_DATA_SOURCES).values(
            id=str(entry.id),
            name=str(entry.name),
            db_type=str(source.db_type),
            host=str(source.host),
            port=int(source.port),
            database_name=str(source.database),
            schema_name=str(source.schema),
            username=str(source.username),
            password_encrypted=password_encrypted,
            is_default=bool(entry.is_default),
            created_at=now,
            updated_at=now,
        )
        connection.execute(
            statement.on_duplicate_key_update(
                name=statement.inserted.name,
                db_type=statement.inserted.db_type,
                host=statement.inserted.host,
                port=statement.inserted.port,
                database_name=statement.inserted.database_name,
                schema_name=statement.inserted.schema_name,
                username=statement.inserted.username,
                password_encrypted=statement.inserted.password_encrypted,
                is_default=statement.inserted.is_default,
                updated_at=statement.inserted.updated_at,
            )
        )


def load_data_sources(connection: Connection) -> list[DataSourceEntry]:
    from auto_check.app.config import DataSourceConfig, DataSourceEntry

    rows = connection.execute(
        select(
            _DATA_SOURCES.c.id,
            _DATA_SOURCES.c.name,
            _DATA_SOURCES.c.db_type,
            _DATA_SOURCES.c.host,
            _DATA_SOURCES.c.port,
            _DATA_SOURCES.c.database_name,
            _DATA_SOURCES.c.schema_name,
            _DATA_SOURCES.c.username,
            _DATA_SOURCES.c.password_encrypted,
            _DATA_SOURCES.c.is_default,
        ).order_by(_DATA_SOURCES.c.name, _DATA_SOURCES.c.id)
    ).mappings().all()
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


def save_setting(connection: Connection, key: str, value: Any) -> None:
    statement = mysql_insert(_APP_SETTINGS).values(
        key=str(key),
        value_json=_stable_json(value),
        updated_at=_utc_now(),
    )
    connection.execute(
        statement.on_duplicate_key_update(
            value_json=statement.inserted.value_json,
            updated_at=statement.inserted.updated_at,
        )
    )


def load_setting(connection: Connection, key: str, default: Any) -> Any:
    row = connection.execute(
        select(_APP_SETTINGS.c.value_json).where(_APP_SETTINGS.c.key == str(key))
    ).mappings().first()
    if row is None:
        return default
    return _decode_json(row["value_json"], default)


def save_config_snapshot(connection: Connection, payload: Any) -> str:
    payload_json = _stable_json(payload)
    fingerprint = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    connection.execute(
        mysql_insert(_CONFIG_SNAPSHOTS).values(
            fingerprint=fingerprint,
            payload_json=payload_json,
            created_at=_utc_now(),
        )
    )
    return fingerprint


def load_config_snapshot(connection: Connection) -> dict[str, Any] | None:
    row = connection.execute(
        select(
            _CONFIG_SNAPSHOTS.c.id,
            _CONFIG_SNAPSHOTS.c.fingerprint,
            _CONFIG_SNAPSHOTS.c.payload_json,
            _CONFIG_SNAPSHOTS.c.created_at,
        ).order_by(
            _CONFIG_SNAPSHOTS.c.created_at.desc(),
            _CONFIG_SNAPSHOTS.c.id.desc(),
        ).limit(1)
    ).mappings().first()
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "fingerprint": str(row["fingerprint"]),
        "payload": _decode_json(row["payload_json"], {}),
        "created_at": row["created_at"],
    }


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list, int, float, bool)) or value is None:
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return default


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
