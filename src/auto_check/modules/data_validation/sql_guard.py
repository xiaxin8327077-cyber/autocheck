"""模块侧只读 SQL 守卫。"""

from __future__ import annotations

import re

from auto_check.app.data_source_platform import ensure_readonly_sql

from .contracts import AppError

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_JOIN = re.compile(r"\bjoin\b", re.IGNORECASE)
_QUOTED = re.compile(r"`[^`]*`|\"([^\"]|\"\")*\"|'([^']|'')*'")


def guard_sql(dialect: str, sql: str, identifiers: set[str], *, allow_join: bool = True) -> None:
    if dialect not in {"mysql", "postgresql"}:
        raise AppError("SQL_POLICY_DENIED")
    for name in identifiers:
        if not isinstance(name, str) or _IDENTIFIER.fullmatch(name) is None:
            raise AppError("SQL_POLICY_DENIED")
    try:
        ensure_readonly_sql(sql)
    except ValueError as exc:
        raise AppError("SQL_POLICY_DENIED") from exc
    if not allow_join and _contains_join(sql):
        # 编译产物只用相关 EXISTS 半连接；显式 JOIN 会引入行放大与 NULL 口径风险。
        raise AppError("SQL_POLICY_DENIED")


def guard_generated_sql(
    dialect: str, sql: str, identifiers: set[str], tables: set[str] | None = None,
) -> None:
    """编译产物专用守卫：表名一并白名单，且禁止显式 JOIN。"""
    names = set(identifiers)
    for table in tables or ():
        if not isinstance(table, str):
            raise AppError("SQL_POLICY_DENIED")
        names.add(table)
    guard_sql(dialect, sql, names, allow_join=False)


def _contains_join(sql: str) -> bool:
    return _JOIN.search(_QUOTED.sub(" ", str(sql or ""))) is not None


def quote_identifier(dialect: str, name: str) -> str:
    if _IDENTIFIER.fullmatch(name) is None:
        raise AppError("SQL_POLICY_DENIED")
    if dialect == "mysql":
        return f"`{name}`"
    return f'"{name}"'
