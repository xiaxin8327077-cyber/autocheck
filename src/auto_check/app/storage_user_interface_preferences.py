from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import Column, MetaData, SmallInteger, String, Table, delete, select
from sqlalchemy.dialects.mysql import DATETIME, insert as mysql_insert
from sqlalchemy.engine import Connection


DEFAULT_INTERFACE_RADIUS_PX = 4
MIN_INTERFACE_RADIUS_PX = 1
MAX_INTERFACE_RADIUS_PX = 15
DEFAULT_THEME_GRADIENT_ENABLED = False
DEFAULT_LINE_CHART_STYLE = "straight"
LINE_CHART_STYLES = frozenset({"straight", "smooth"})


@dataclass(frozen=True, slots=True)
class UserInterfacePreferences:
    radius_px: int = DEFAULT_INTERFACE_RADIUS_PX
    theme_gradient_enabled: bool = DEFAULT_THEME_GRADIENT_ENABLED
    line_chart_style: str = DEFAULT_LINE_CHART_STYLE

_METADATA = MetaData()

USER_INTERFACE_PREFERENCES = Table(
    "user_interface_preferences",
    _METADATA,
    Column("user_id", String(64), primary_key=True),
    Column("radius_px", SmallInteger, nullable=False),
    Column("theme_gradient_enabled", SmallInteger, nullable=False),
    Column("line_chart_style", String(16), nullable=False),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)


def load_user_interface_preferences(
    connection: Connection,
    user_id: str,
) -> UserInterfacePreferences:
    row = connection.execute(
        select(
            USER_INTERFACE_PREFERENCES.c.radius_px,
            USER_INTERFACE_PREFERENCES.c.theme_gradient_enabled,
            USER_INTERFACE_PREFERENCES.c.line_chart_style,
        ).where(
            USER_INTERFACE_PREFERENCES.c.user_id == str(user_id)
        )
    ).mappings().first()
    radius_px = row.get("radius_px") if row is not None else None
    theme_gradient_enabled = row.get("theme_gradient_enabled") if row is not None else None
    line_chart_style = row.get("line_chart_style") if row is not None else None
    return UserInterfacePreferences(
        radius_px=(
            radius_px
            if type(radius_px) is int
            and MIN_INTERFACE_RADIUS_PX <= radius_px <= MAX_INTERFACE_RADIUS_PX
            else DEFAULT_INTERFACE_RADIUS_PX
        ),
        theme_gradient_enabled=(
            bool(theme_gradient_enabled)
            if type(theme_gradient_enabled) is int and theme_gradient_enabled in {0, 1}
            else DEFAULT_THEME_GRADIENT_ENABLED
        ),
        line_chart_style=(
            line_chart_style
            if type(line_chart_style) is str and line_chart_style in LINE_CHART_STYLES
            else DEFAULT_LINE_CHART_STYLE
        ),
    )


def save_user_interface_preferences(
    connection: Connection,
    user_id: str,
    *,
    radius_px: int,
    theme_gradient_enabled: bool,
    line_chart_style: str,
) -> UserInterfacePreferences:
    radius_px = _validate_radius(radius_px)
    theme_gradient_enabled = _validate_theme_gradient_enabled(theme_gradient_enabled)
    line_chart_style = _validate_line_chart_style(line_chart_style)
    statement = mysql_insert(USER_INTERFACE_PREFERENCES).values(
        user_id=str(user_id),
        radius_px=radius_px,
        theme_gradient_enabled=int(theme_gradient_enabled),
        line_chart_style=line_chart_style,
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    connection.execute(
        statement.on_duplicate_key_update(
            radius_px=statement.inserted.radius_px,
            theme_gradient_enabled=statement.inserted.theme_gradient_enabled,
            line_chart_style=statement.inserted.line_chart_style,
            updated_at=statement.inserted.updated_at,
        )
    )
    return UserInterfacePreferences(radius_px, theme_gradient_enabled, line_chart_style)


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


def _validate_theme_gradient_enabled(value: bool) -> bool:
    if type(value) is not bool:
        raise ValueError("theme_gradient_enabled must be a boolean")
    return value


def _validate_line_chart_style(value: str) -> str:
    if type(value) is not str or value not in LINE_CHART_STYLES:
        raise ValueError("line_chart_style must be one of: smooth, straight")
    return value
