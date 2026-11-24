"""从已验证的编译投影采集真实 SQL 输出，驱动返回的其他列不进入结果。"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from .formula import arithmetic_projection, has_arithmetic, is_arithmetic

from .query_spec import RELATED, UNARY_OPS, comparison_conditions, is_condition_group, needs_issue_kind


# TEXT 的容量按字节计；列名、说明、JSON 转义均计入单行预算。
_MAX_BYTES = 48 * 1024
_MAX_COLUMNS = 48
_MAX_VALUE = 8192

_IDENT = r"[A-Za-z_][A-Za-z_0-9]{0,127}"
_PHYSICAL = rf"(?:{_IDENT}|\x60{_IDENT}\x60|\"{_IDENT}\")"
_ALIAS_NAME = r"[^\W\d]\w{0,127}"
_ALIAS = rf"(?:{_ALIAS_NAME}|\x60(?:[^\x60]|\x60\x60){{1,128}}\x60|\"(?:[^\"]|\"\"){{1,128}}\")"
_PROJECTION_DELIMITERS = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`|,")
_FROM = re.compile(
    rf"\s*SELECT\s+(?P<projection>.+?)\s+FROM\s+(?P<table>{_PHYSICAL})"
    rf"(?:\s+(?:AS\s+)?(?P<alias>{_PHYSICAL}))?(?:\s+WHERE\s+.+)?\s*;?\s*",
    re.IGNORECASE | re.DOTALL,
)
# 自定义 SQL 仅识别可证明的简单列、字面常量与显式别名。CTE、函数、星号不猜测。
_SIMPLE = re.compile(
    rf"(?:(?:(?P<qual>{_PHYSICAL})\.)?(?P<field>{_PHYSICAL})|(?:'[\w\s]*'|[0-9.]+))"
    rf"(?:\s+AS\s+(?P<alias>{_ALIAS}))?", re.IGNORECASE,
)


def _identifier(value):
    value = value or ""
    if len(value) >= 2 and value[0] in '`"' and value[-1] == value[0]:
        return value[1:-1].replace(value[0] * 2, value[0])
    return value


def _simple_projection(sql, base_table):
    if len(sql) > 32768:
        return None
    statement = _FROM.fullmatch(sql)
    if not statement or _identifier(statement["table"]) != base_table:
        return None
    columns = []
    projection = statement["projection"]
    chunks, start = [], 0
    for token in _PROJECTION_DELIMITERS.finditer(projection):
        if token.group() == ",":
            chunks.append(projection[start:token.start()])
            start = token.end()
    chunks.append(projection[start:])
    for item in chunks:
        matched = _SIMPLE.fullmatch(item.strip())
        if not matched:
            return None
        qualifier = _identifier(matched["qual"])
        if qualifier and qualifier not in {base_table, _identifier(statement["alias"])}:
            return None
        field = _identifier(matched["field"])
        if field.upper() in {"NULL", "TRUE", "FALSE"}:
            field = ""
        name = _identifier(matched["alias"]) or field
        if not name:
            return None
        columns.append((name, field, False))
    return columns


def _project_rule_projection(definition):
    context = definition["project_context"]
    related = definition["project_driver"]["table_role"] == RELATED
    join = definition.get("join") or {}
    columns = [
        ("business_key", definition["business_key"], False),
        ("project_code", context["key"]["right"] if related else context["code_field"], related),
        ("project_name", context["name_field"], related),
        ("data_date", join["report_date_field"] if related else definition.get("report_date_field") or "report_date", related),
    ]
    for index, part in enumerate(comparison_conditions(definition)):
        if is_arithmetic(part):
            suffix = f"_{index + 1}" if index else ""
            columns.extend((role + suffix, field, other) for role, field, other in arithmetic_projection(part))
            continue
        suffix = f"_{index + 1}" if index else ""
        columns.append(("checked_value" + suffix, part["left"], False))
        if part["op"] not in UNARY_OPS and part.get("right_type", "field") == "field":
            columns.append(("comparison_value" + suffix, part["right"], part.get("right_table") == RELATED))
    projection, seen = [], set()
    for role, field, other in columns:
        if not field or (field, other) not in seen:
            seen.add((field, other))
            projection.append((role, field, other))
    if join.get("right_aggregate") == "sum":
        projection.append(("related_count", "", True))
    if join or definition["null_policy"] == "review" or has_arithmetic(definition["expression"]):
        projection.append(("issue_kind", "", False))
    projection.append(("violation_message", "", False))
    return projection


def compiled_projection(definition, *, named_unique_keys=False):
    key = definition.get("business_key") or "id"
    if definition["rule_type"] == "unique":
        keys = definition["keys"]
        return [(f"unique_key_{index}" if named_unique_keys else k, k, False) for index, k in enumerate(keys[:-1])] + [
            ("business_key", keys[-1], False), ("violation_message", "", False)]
    columns = [("business_key", key, False), ("violation_message", "", False)]
    if definition["rule_type"] != "field_compare":
        return columns
    context = definition.get("project_context") or {}
    driver = definition.get("project_driver") or {}
    if driver.get("version") in (2, 3):
        return _project_rule_projection(definition)
    project_related = driver.get("table_role") == RELATED
    if context:
        lookup = context["mode"] == "lookup"
        code = context["key"]["right"] if project_related else context["code_field"]
        columns.extend([("project_code", code, project_related), ("project_name", context["name_field"], lookup)])
        if lookup or driver:
            columns.append(("project_match_count", "", True))
    aggregate = (definition.get("join") or {}).get("right_aggregate") == "sum"
    if definition.get("include_result_fields") is True or aggregate or driver:
        conditions = comparison_conditions(definition)
        expr = conditions[0]
        date = definition["join"]["report_date_field"] if project_related else definition.get("report_date_field") or "report_date"
        columns.append(("data_date", date, project_related))
        if has_arithmetic(definition["expression"]):
            for index, part in enumerate(conditions, 1):
                if is_arithmetic(part):
                    suffix = f"_{index}" if index > 1 else ""
                    columns.extend((role + suffix, field, other) for role, field, other in arithmetic_projection(part))
        elif all(c["left"] == expr["left"] for c in conditions):
            columns.append(("checked_value", expr["left"], False))
        if aggregate:
            columns.extend([("related_count", "", True), ("comparison_value", expr["right"], True)])
        elif (not is_arithmetic(expr) and not is_condition_group(definition) and expr["op"] not in UNARY_OPS
              and (expr.get("right_type") or "field") == "field" and (driver or expr.get("right_table") != RELATED)):
            columns.append(("comparison_value", expr["right"], expr.get("right_table") == RELATED))
    if driver or needs_issue_kind(definition):
        columns.append(("issue_kind", "", False))
    return columns


def output_projection(definition, sql, compiled, raw_names, base, related):
    source_roles = {}
    if compiled:
        aliases = definition.get("result_aliases", {})
        source_roles = {aliases[role]: role for role in ("checked_value", "comparison_value") if role in aliases}
        selections = [(aliases.get(role, role), field, other) for role, field, other in
                      compiled_projection(definition, named_unique_keys=bool(aliases))]
    else:
        selections = _simple_projection(sql, definition.get("table_name"))
    if selections is None:
        return [], "unsupported_projection"
    selected_counts = Counter(name for name, _, _ in selections)
    received_counts = Counter(raw_names)
    columns = []
    partial = False
    description_bytes = 0
    for name, field, other in selections:
        if (selected_counts[name] != 1 or received_counts[name] != 1 or len(columns) >= _MAX_COLUMNS
                or len(name) > 128 or len(field) > 128):
            partial = True
            continue
        # 表头严格采用实际 SQL 输出别名；不再从文档或字段备注推导中文名。
        descriptor = {"name": name, "label": name.encode("utf-8", "replace").decode("utf-8")}
        if field:
            descriptor["source_field"] = field
            if name in source_roles:
                descriptor["role"] = source_roles[name]
        length = _encoded_size(descriptor) + 1
        if description_bytes + length > _MAX_BYTES // 2:
            partial = True
            continue
        description_bytes += length
        columns.append(descriptor)
    positions = {name: index for index, name in enumerate(raw_names)}
    columns.sort(key=lambda c: positions[c["name"]])
    return columns, "partial_projection" if partial else ""


def _value(value):
    kind = type(value)
    if value is None or kind is bool:
        return value, ""
    if kind is int:
        if value.bit_length() > 4096:
            return None, "oversized"
        return (str(value) if abs(value) > 2**53 - 1 else value), ""
    if kind is float and math.isfinite(value):
        return value, ""
    if kind is Decimal:
        if not value.is_finite():
            return None, "unsupported"
        value = str(value)
    elif kind in (date, datetime, time):
        value = value.isoformat()
    elif kind is not str:
        return None, "unsupported"
    if len(value) > _MAX_VALUE:
        return None, "oversized"
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None, "unsupported"
    return value, ""


def _encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def encode_result(result: dict | None) -> str | None:
    if result is None:
        return None
    payload = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("Query result exceeds its storage limit")
    return payload


def collect_row(columns, status, raw):
    result = {"columns": columns, "values": {}}
    if status:
        result["status"] = status
    # 为每个列的不可用原因预留空间，即使后续多个值超限也能说明原因。
    size = _encoded_size(result) + sum(_encoded_size(c["name"]) + 32 for c in columns) + 32
    for column in columns:
        name = column["name"]
        if name not in raw:
            result["status"] = "partial_projection"
            continue
        value, reason = _value(raw[name])
        if not reason:
            increment = _encoded_size(value) + _encoded_size(name) + 2
            if size + increment > _MAX_BYTES:
                reason = "oversized"
            else:
                size += increment
        if reason:
            result.setdefault("unavailable", {})[name] = reason
        else:
            result["values"][name] = value
    return result
