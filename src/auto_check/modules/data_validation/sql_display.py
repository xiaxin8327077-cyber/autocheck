"""Render bound values in a SQL copy intended only for display and copying."""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

from .contracts import AppError

__all__ = ["inline_sql_parameters", "saved_sql_display"]

_DIALECTS = frozenset({"mysql", "postgresql"})
_PARAMETER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DOLLAR_QUOTE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def inline_sql_parameters(sql: str, params: dict, dialect: str, *, preserve_report_date: bool = True, require_all_parameters: bool = False) -> str:
    """Return a display-only SQL string without mutating the SQL or parameters.

    By default ``report_date`` is kept for previews; execution review can provide
    its batch value and set preserve_report_date=False. Unknown bindings are kept.
    Quoted regions, comments, PostgreSQL dollar strings and casts are
    copied without looking for bindings inside them.
    """
    if dialect not in _DIALECTS or not isinstance(sql, str) or not isinstance(params, dict):
        raise AppError("VALIDATION_ERROR")

    parts: list[str] = []
    index = 0
    while index < len(sql):
        char = sql[index]

        if char in {"'", '"', "`"}:
            end = _quoted_region_end(sql, index, char)
            parts.append(sql[index:end])
            index = end
            continue

        if sql.startswith("--", index) or (dialect == "mysql" and char == "#"):
            end = sql.find("\n", index)
            end = len(sql) if end < 0 else end
            parts.append(sql[index:end])
            index = end
            continue

        if sql.startswith("/*", index):
            closing = sql.find("*/", index + 2)
            end = len(sql) if closing < 0 else closing + 2
            parts.append(sql[index:end])
            index = end
            continue

        if dialect == "postgresql" and char == "$":
            delimiter = _DOLLAR_QUOTE.match(sql, index)
            if delimiter is not None:
                closing = sql.find(delimiter.group(), delimiter.end())
                end = len(sql) if closing < 0 else closing + len(delimiter.group())
                parts.append(sql[index:end])
                index = end
                continue

        if char == ":":
            if index + 1 < len(sql) and sql[index + 1] == ":":
                parts.append("::")
                index += 2
                continue
            name_match = _PARAMETER_NAME.match(sql, index + 1)
            if name_match is not None:
                name = name_match.group()
                if require_all_parameters and name not in params:
                    raise AppError("VALIDATION_ERROR")
                if (name == "report_date" and preserve_report_date) or name not in params:
                    parts.append(sql[index:name_match.end()])
                else:
                    parts.append(_sql_literal(params[name], dialect))
                index = name_match.end()
                continue

        parts.append(char)
        index += 1

    return "".join(parts)


def saved_sql_display(version: dict) -> dict:
    from .compiler import compile_rule

    sql = version.get("sql_text") or ""
    if not sql:
        return {"sql_display": ""}
    try:
        definition = version["definition"]
        if definition.get("rule_type") == "custom_sql":
            params = definition.get("params") or {}
        else:
            _, params = compile_rule(version)
        return {"sql_display": inline_sql_parameters(sql, {"report_date": None, **params}, definition["dialect"],
                                                    require_all_parameters=True)}
    except (AppError, KeyError, ValueError, TypeError):
        return {"sql_display_error": "RULE_SQL_DISPLAY_UNAVAILABLE"}


def _quoted_region_end(sql: str, start: int, quote: str) -> int:
    """Find a quote's end, honoring doubled quotes and backslash escapes."""
    index = start + 1
    while index < len(sql):
        if sql[index] == "\\":
            index += 2
        elif sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
            else:
                return index + 1
        else:
            index += 1
    return len(sql)


def _sql_literal(value: Any, dialect: str) -> str:
    if value is None:
        return "NULL"
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if type(value) is int:
        return str(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise AppError("VALIDATION_ERROR")
        return repr(value)
    if type(value) is Decimal:
        if not value.is_finite():
            raise AppError("VALIDATION_ERROR")
        return str(value)
    if type(value) is str:
        return _string_literal(value, dialect)
    raise AppError("VALIDATION_ERROR")


def _string_literal(value: str, dialect: str) -> str:
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise AppError("VALIDATION_ERROR") from None

    has_control = any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)
    if dialect == "mysql" and ("\\" in value or has_control):
        # Hex avoids every NO_BACKSLASH_ESCAPES and control-character ambiguity.
        return f"CONVERT(0x{encoded.hex().upper()} USING utf8mb4)"

    if dialect == "postgresql" and "\\" in value:
        escaped = value.replace("\\", "\\\\").replace("'", "''")
        return f"E'{escaped}'"
    return "'" + value.replace("'", "''") + "'"
