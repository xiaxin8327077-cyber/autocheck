from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, MetaData, String, Table, Text, delete, insert, select
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.engine import Connection


_METADATA = MetaData()

USERS = Table(
    "users",
    _METADATA,
    Column("id", String(64), primary_key=True),
    Column("username", String(191), nullable=False),
    Column("display_name", String(191), nullable=False),
    Column("role", String(32), nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("created_at", DATETIME(fsp=6), nullable=False),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
    Column("last_login_at", DATETIME(fsp=6), nullable=True),
)


def load_users(connection: Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        select(USERS).order_by(USERS.c.created_at, USERS.c.id)
    ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "username": str(row["username"]),
            "display_name": str(row["display_name"]),
            "role": str(row["role"]),
            "password_hash": str(row["password_hash"]),
            "enabled": bool(row["enabled"]),
            "created_at": _datetime_text(row["created_at"]),
            "updated_at": _datetime_text(row["updated_at"]),
            "last_login_at": _datetime_text(row["last_login_at"]),
        }
        for row in rows
    ]


def replace_users(connection: Connection, users: list[dict[str, Any]]) -> None:
    connection.execute(delete(USERS))
    if not users:
        return
    connection.execute(
        insert(USERS),
        [
            {
                "id": str(user.get("id", "")),
                "username": str(user.get("username", "")),
                "display_name": str(user.get("display_name", "")),
                "role": str(user.get("role", "user")),
                "password_hash": str(user.get("password_hash", "")),
                "enabled": bool(user.get("enabled", True)),
                "created_at": _parse_required_datetime(user.get("created_at")),
                "updated_at": _parse_required_datetime(user.get("updated_at")),
                "last_login_at": _parse_optional_datetime(user.get("last_login_at")),
            }
            for user in users
        ],
    )


def _parse_required_datetime(value: Any) -> datetime:
    parsed = _parse_optional_datetime(value)
    if parsed is None:
        raise ValueError("required user datetime is empty")
    return parsed


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).strip().replace("T", " ")).replace(tzinfo=None)


def _datetime_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="microseconds")
    return str(value)
