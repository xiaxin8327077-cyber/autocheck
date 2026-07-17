from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import Column, MetaData, SmallInteger, String, Table, delete, select
from sqlalchemy.dialects.mysql import DATETIME, insert as mysql_insert
from sqlalchemy.engine import Connection


DEFAULT_INTERFACE_RADIUS_PX = 4
MIN_INTERFACE_RADIUS_PX = 1
MAX_INTERFACE_RADIUS_PX = 15

_METADATA = MetaData()

USER_INTERFACE_PREFERENCES = Table(
    "user_interface_preferences",
    _METADATA,
    Column("user_id", String(64), primary_key=True),
    Column("radius_px", SmallInteger, nullable=False),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)


def load_user_interface_preferences(connection: Connection, user_id: str) -> int:
    row = connection.execute(
        select(USER_INTERFACE_PREFERENCES.c.radius_px).where(
            USER_INTERFACE_PREFERENCES.c.user_id == str(user_id)
        )
    ).mappings().first()
    value = row["radius_px"] if row is not None else None
    if type(value) is not int or not MIN_INTERFACE_RADIUS_PX <= value <= MAX_INTERFACE_RADIUS_PX:
        return DEFAULT_INTERFACE_RADIUS_PX
    return value


def save_user_interface_preferences(connection: Connection, user_id: str, radius_px: int) -> int:
    radius_px = _validate_radius(radius_px)
    statement = mysql_insert(USER_INTERFACE_PREFERENCES).values(
        user_id=str(user_id),
        radius_px=radius_px,
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    connection.execute(
        statement.on_duplicate_key_update(
            radius_px=statement.inserted.radius_px,
            updated_at=statement.inserted.updated_at,
        )
    )
    return radius_px


def prune_user_interface_preferences(
    connection: Connection,
    active_user_ids: Iterable[str],
) -> None:
    active_ids = sorted({str(user_id) for user_id in active_user_ids if str(user_id)})
    statement = delete(USER_INTERFACE_PREFERENCES)
    if active_ids:
        statement = statement.where(USER_INTERFACE_PREFERENCES.c.user_id.not_in(active_ids))
    connection.execute(statement)


def _validate_radius(value: int) -> int:
    if type(value) is not int or not MIN_INTERFACE_RADIUS_PX <= value <= MAX_INTERFACE_RADIUS_PX:
        raise ValueError("radius_px must be an integer between 1 and 15")
    return value
