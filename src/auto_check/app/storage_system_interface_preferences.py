from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.dialects.mysql import CHAR, DATETIME, TINYINT, insert as mysql_insert
from sqlalchemy.engine import Connection

if TYPE_CHECKING:
    from .storage_user_interface_preferences import UserInterfacePreferences


DEFAULT_VITALITY_THEME_COLOR = "#3466D9"
DEFAULT_CALM_THEME_COLOR = "#355F63"
THEME_COLOR_PATTERN = re.compile(r"^#[0-9A-F]{6}$")


@dataclass(frozen=True, slots=True)
class SystemInterfacePreferences:
    vitality_theme_color: str = DEFAULT_VITALITY_THEME_COLOR
    calm_theme_color: str = DEFAULT_CALM_THEME_COLOR
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class EffectiveThemeColors:
    vitality_theme_color: str = DEFAULT_VITALITY_THEME_COLOR
    calm_theme_color: str = DEFAULT_CALM_THEME_COLOR


_METADATA = MetaData()

SYSTEM_INTERFACE_PREFERENCES = Table(
    "system_interface_preferences",
    _METADATA,
    Column("id", TINYINT(unsigned=True), primary_key=True),
    Column("vitality_theme_color", CHAR(7), nullable=False),
    Column("calm_theme_color", CHAR(7), nullable=False),
    Column("updated_by", String(64), nullable=True),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)


def normalize_theme_color(value: object, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if type(value) is not str:
        raise ValueError("theme color must be a #RRGGBB string")
    normalized = value.upper()
    if not THEME_COLOR_PATTERN.fullmatch(normalized):
        raise ValueError("theme color must be a #RRGGBB string")
    return normalized


def load_system_interface_preferences(
    connection: Connection,
) -> SystemInterfacePreferences:
    row = connection.execute(
        select(
            SYSTEM_INTERFACE_PREFERENCES.c.vitality_theme_color,
            SYSTEM_INTERFACE_PREFERENCES.c.calm_theme_color,
            SYSTEM_INTERFACE_PREFERENCES.c.updated_by,
        ).where(SYSTEM_INTERFACE_PREFERENCES.c.id == 1)
    ).mappings().first()
    if row is None:
        return SystemInterfacePreferences()
    return SystemInterfacePreferences(
        vitality_theme_color=_load_system_theme_color(
            row.get("vitality_theme_color"), DEFAULT_VITALITY_THEME_COLOR
        ),
        calm_theme_color=_load_system_theme_color(
            row.get("calm_theme_color"), DEFAULT_CALM_THEME_COLOR
        ),
        updated_by=row.get("updated_by") if type(row.get("updated_by")) is str else None,
    )


def save_system_interface_preferences(
    connection: Connection,
    *,
    vitality_theme_color: str,
    calm_theme_color: str,
    updated_by: str | None = None,
) -> SystemInterfacePreferences:
    vitality_theme_color = normalize_theme_color(vitality_theme_color)
    calm_theme_color = normalize_theme_color(calm_theme_color)
    normalized_updated_by = None if updated_by is None else str(updated_by)
    statement = mysql_insert(SYSTEM_INTERFACE_PREFERENCES).values(
        id=1,
        vitality_theme_color=vitality_theme_color,
        calm_theme_color=calm_theme_color,
        updated_by=normalized_updated_by,
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    connection.execute(
        statement.on_duplicate_key_update(
            vitality_theme_color=statement.inserted.vitality_theme_color,
            calm_theme_color=statement.inserted.calm_theme_color,
            updated_by=statement.inserted.updated_by,
            updated_at=statement.inserted.updated_at,
        )
    )
    return SystemInterfacePreferences(
        vitality_theme_color=vitality_theme_color,
        calm_theme_color=calm_theme_color,
        updated_by=normalized_updated_by,
    )


def resolve_effective_theme_colors(
    user: UserInterfacePreferences,
    system: SystemInterfacePreferences,
) -> EffectiveThemeColors:
    return EffectiveThemeColors(
        vitality_theme_color=user.vitality_theme_color or system.vitality_theme_color,
        calm_theme_color=user.calm_theme_color or system.calm_theme_color,
    )


def _load_system_theme_color(value: object, default: str) -> str:
    try:
        normalized = normalize_theme_color(value)
    except ValueError:
        return default
    assert normalized is not None
    return normalized
