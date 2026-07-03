from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from auto_check.app.pbc_import import TableRef, parse_table_ref


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ReconcileSourceRef:
    id: str = ""
    name: str = ""
    match_by: str = "id_then_name"


@dataclass(frozen=True)
class ReconcileTableSchema:
    source_ref: ReconcileSourceRef = field(default_factory=ReconcileSourceRef)
    table: str = ""
    display_name: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    optional_fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReconcileSchemaSettings:
    version: int = 1
    tables: dict[str, ReconcileTableSchema] = field(default_factory=dict)
    strict: bool = False


def reconcile_schema_settings_from_dict(payload: dict[str, Any] | None) -> ReconcileSchemaSettings:
    payload = payload or {}
    raw_tables = payload.get("tables", {})
    tables: dict[str, ReconcileTableSchema] = {}
    if isinstance(raw_tables, dict):
        for key, value in raw_tables.items():
            if isinstance(value, dict):
                logical_key = str(key or "").strip()
                if logical_key:
                    tables[logical_key] = reconcile_table_schema_from_dict(value)
    return ReconcileSchemaSettings(
        version=_coerce_version(payload.get("version")),
        tables=tables,
        strict=_coerce_bool(payload.get("strict"), default=False),
    )


def reconcile_schema_settings_to_dict(settings: ReconcileSchemaSettings) -> dict[str, Any]:
    return {
        "version": int(settings.version or 1),
        "strict": bool(settings.strict),
        "tables": {
            key: reconcile_table_schema_to_dict(table)
            for key, table in settings.tables.items()
        },
    }


def load_reconcile_schema_settings_from_yaml(path: str | Path) -> ReconcileSchemaSettings:
    payload = _parse_simple_yaml(Path(path).read_text(encoding="utf-8"))
    root = payload.get("reconcile_schema", payload)
    if not isinstance(root, dict):
        return ReconcileSchemaSettings(strict=True)
    settings = reconcile_schema_settings_from_dict(root)
    return ReconcileSchemaSettings(version=settings.version, tables=settings.tables, strict=True)


def reconcile_table_schema_from_dict(payload: dict[str, Any]) -> ReconcileTableSchema:
    source_payload = payload.get("source_ref") if isinstance(payload.get("source_ref"), dict) else {}
    fields = _string_map(payload.get("fields"))
    optional_fields = _string_map(payload.get("optional_fields"))
    return ReconcileTableSchema(
        source_ref=ReconcileSourceRef(
            id=str(source_payload.get("id", payload.get("source_id", "")) or ""),
            name=str(source_payload.get("name", payload.get("source_name", "")) or ""),
            match_by=str(source_payload.get("match_by", "id_then_name") or "id_then_name"),
        ),
        table=str(payload.get("table", "") or ""),
        display_name=str(payload.get("display_name", "") or ""),
        fields=fields,
        optional_fields=optional_fields,
    )


def reconcile_table_schema_to_dict(table: ReconcileTableSchema) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_ref": {
            "id": table.source_ref.id,
            "name": table.source_ref.name,
            "match_by": table.source_ref.match_by or "id_then_name",
        },
        "table": table.table,
        "display_name": table.display_name,
        "fields": dict(table.fields),
    }
    if table.optional_fields:
        payload["optional_fields"] = dict(table.optional_fields)
    return payload


def safe_table_ref(value: str) -> TableRef:
    return parse_table_ref(str(value or "").strip())


def safe_column_name(value: str) -> str:
    column = str(value or "").strip()
    if not _IDENTIFIER_RE.match(column):
        raise ValueError(f"unsafe column identifier: {column}")
    return column


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        logical = str(key or "").strip()
        physical = str(item or "").strip()
        if logical and physical:
            result[logical] = physical
    return result


def _coerce_version(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return max(parsed, 1)


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = _strip_yaml_comment(raw_line.rstrip())
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        if ":" not in content:
            raise ValueError(f"unsupported yaml line: {raw_line}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"unsupported yaml line: {raw_line}")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value_text = raw_value.strip()
        if value_text == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_yaml_scalar(value_text)
    return root


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    previous = ""
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single and previous != "\\":
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
        previous = char
    return line.rstrip()


def _parse_yaml_scalar(value: str) -> Any:
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        return value
