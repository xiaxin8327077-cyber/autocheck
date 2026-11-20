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
        # 未标记项目驱动的生成规则只允许已有的相关子查询。
        raise AppError("SQL_POLICY_DENIED")


def guard_generated_sql(
    dialect: str, sql: str, identifiers: set[str], tables: set[str] | None = None,
    *, definition: dict | None = None,
) -> None:
    """Only the project's own compiled, versioned template may introduce an explicit JOIN."""
    names = set(identifiers)
    for table in tables or ():
        if not isinstance(table, str):
            raise AppError("SQL_POLICY_DENIED")
        names.add(table)
    project_template = definition is not None and "project_driver" in definition
    if project_template:
        from .compiler import compile_rule
        from .query_spec import referenced_columns
        if (definition.get("dialect") != dialect or definition.get("rule_type") != "field_compare"
                or compile_rule({"definition": definition})[0] != sql):
            raise AppError("SQL_POLICY_DENIED")
        required_tables = {definition["table_name"]}
        if definition.get("join"):
            required_tables.add(definition["join"]["table_name"])
        fields = referenced_columns(definition)
        allowed_tables = names if tables is None else tables
        required_fields = set(fields["base"] + fields["related"])
        if not required_tables <= allowed_tables or not required_fields <= identifiers:
            raise AppError("SQL_POLICY_DENIED")
    guard_sql(dialect, sql, names, allow_join=project_template)


def _contains_join(sql: str) -> bool:
    return _JOIN.search(_QUOTED.sub(" ", str(sql or ""))) is not None


def quote_identifier(dialect: str, name: str) -> str:
    if _IDENTIFIER.fullmatch(name) is None:
        raise AppError("SQL_POLICY_DENIED")
    if dialect == "mysql":
        return f"`{name}`"
    return f'"{name}"'
