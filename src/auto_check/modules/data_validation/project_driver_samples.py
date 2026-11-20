"""项目为范围、明细按实际行数计数的合成样本。"""

from __future__ import annotations

import datetime
import math

from .contracts import AppError
from .query_samples import (
    _column_types, _fail_value, _nested_cases, case_fields, evaluate_matched_rows,
    filter_matches, ordered_values, sql_equal,
)
from .query_spec import BASE, RELATED, base_type, comparison_conditions, is_finite_number, type_family, validate_query_spec


MAX_DETAILS = 20
ISSUE_KINDS = {"missing_record", "missing_value", "comparison", "numeric"}
_INTEGER_TYPES = {
    "int", "integer", "bigint", "smallint", "tinyint", "mediumint", "bit",
    "int2", "int4", "int8", "serial", "bigserial",
}


def evaluate_project_case(definition: dict, row: dict) -> tuple[int, str | None]:
    spec = validate_query_spec(definition)
    join = spec["join"]
    context = spec["project_context"]
    role = definition["project_driver"]["table_role"]
    project = row["project"]
    period = row["report_date"]
    base_date = definition.get("report_date_field") or "report_date"
    project_date = base_date if role == BASE else join["report_date_field"]

    def in_scope(record, side):
        return all(filter_matches(item["op"], record.get(item["field"]), item["value"])
                   for item in spec["filters"] if item["table"] == side)

    if not sql_equal(project.get(project_date), period) or not in_scope(project, role):
        return 0, None
    code = context["code_field"] if role == BASE else context["key"]["right"]
    if definition["project_driver"]["version"] == 1 and (project.get(code) is None or not str(project[code]).strip(" ")):
        return 1, "comparison"
    if not join:
        count, kind = evaluate_matched_rows(definition, spec, project, [])
        return count, (kind or "comparison") if count else None

    project_key, detail_key = ("left", "right") if role == BASE else ("right", "left")
    detail_role = RELATED if role == BASE else BASE
    detail_date = join["report_date_field"] if role == BASE else base_date
    matches = [
        entry for entry in row["details"]
        if sql_equal(entry.get(detail_date), period)
        and all(sql_equal(project.get(pair[project_key]), entry.get(pair[detail_key])) for pair in join["on"])
    ]
    if not matches:
        return 1, "missing_record"
    scoped = [entry for entry in matches if in_scope(entry, detail_role)]
    if not scoped:
        return 0, None
    if join.get("right_aggregate") == "sum":
        return evaluate_matched_rows(definition, spec, project, scoped)

    hits = []
    for entry in scoped:
        base, related = (project, entry) if role == BASE else (entry, project)
        count, kind = evaluate_matched_rows(definition, spec, base, [related])
        if count:
            hits.append(kind or "comparison")
    return len(hits), hits[0] if hits and len(set(hits)) == 1 else None


def project_sample_schema(definition, columns, related_columns):
    """返回真实项目/明细样本列的类型，包括业务定位列和已记录的同名项目属性副本。"""
    base_fields, related_fields = case_fields(definition)
    base_fields.append(definition["business_key"])
    role = definition["project_driver"]["table_role"]
    base_types, related_types = _column_types(columns), _column_types(related_columns)
    if role == BASE:
        project, details = base_fields, related_fields
        project_types, detail_types = base_types, related_types
    else:
        project, details = related_fields, base_fields
        project_types, detail_types = related_types, base_types
    context = definition["project_context"]
    project.append(context["code_field"] if role == BASE else context["key"]["right"])
    if context.get("name_field"):
        project.append(context["name_field"])
    if definition.get("join"):
        details.extend(item["field"] for item in definition.get("filters") or []
                       if item.get("table", BASE) == role and item["field"] in detail_types)
        if context.get("name_field") in detail_types:
            details.append(context["name_field"])
    if set(project) - project_types.keys() or set(details) - detail_types.keys():
        raise AppError("VALIDATION_ERROR")
    return {key: project_types[key] for key in project}, {key: detail_types[key] for key in details}


def _valid_date(value):
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_value(value, dtype):
    if value is None:
        return True
    base = base_type(dtype)
    if base in _INTEGER_TYPES:
        return type(value) is int
    family = type_family(dtype)
    if family == "number":
        return is_finite_number(value)
    if base == "date":
        return _valid_date(value)
    if base in {"boolean", "bool"}:
        return type(value) is bool
    if not isinstance(value, str) or len(value) > 2000:
        return False
    if base in {"datetime", "timestamp"}:
        try:
            datetime.datetime.fromisoformat(value)
        except ValueError:
            return False
    return True


def validate_project_sample(row, project_types, detail_types):
    if (set(row) != {"report_date", "project", "details"} or not _valid_date(row["report_date"])
            or not isinstance(row["details"], list) or len(row["details"]) > MAX_DETAILS
            or (row["details"] and not detail_types)):
        raise AppError("VALIDATION_ERROR")

    def validate_record(record, types):
        if (not isinstance(record, dict) or set(record) != set(types)
                or any(not _valid_value(record[key], dtype) for key, dtype in types.items())):
            raise AppError("VALIDATION_ERROR")

    validate_record(row["project"], project_types)
    for record in row["details"]:
        validate_record(record, detail_types)


def default_project_cases(definition, columns, related_columns):
    role = definition["project_driver"]["table_role"]
    join = definition.get("join")
    project_types, detail_types = project_sample_schema(definition, columns, related_columns)
    # 复用既有表达式在边界、空值、条件组合上的取值。仅取输入，不沿用旧半连接的命中数量。
    legacy_definition = {key: value for key, value in definition.items() if key != "project_driver"}
    seeds = _nested_cases(legacy_definition, columns, related_columns)
    cases = []

    def sample_value(value, dtype):
        if value is not None and base_type(dtype) in {"boolean", "bool"}:
            return bool(value)
        if type(value) is float and base_type(dtype) in _INTEGER_TYPES:
            # 小数阈值仍原样比较，行值取实际整数列可存储的邻近值。
            return math.floor(value)
        return value

    def complete(source, types):
        return {key: sample_value(source[key] if key in source else ordered_values(dtype)[0], dtype)
                for key, dtype in types.items()}

    def add(name, row):
        if any(case["row"] == row for case in cases):
            return
        count, kind = evaluate_project_case(definition, row)
        case = {"name": name, "row": row, "expected_count": count}
        if kind:
            case["expected_issue_kind"] = kind
        cases.append(case)

    for seed in seeds:
        original = seed["row"]
        if role == RELATED:
            if len(original["related"]) != 1:
                continue
            main, items = original["related"][0], [original["base"]]
            if main.get(join["report_date_field"]) != original["report_date"]:
                continue
            if any(not sql_equal(main.get(pair["right"]), items[0].get(pair["left"])) for pair in join["on"]):
                continue
        else:
            main, items = original["base"], original["related"]
        add(seed["name"], {"report_date": original["report_date"], "project": complete(main, project_types),
                           "details": [complete(item, detail_types) for item in items]})

    witness = next((case for case in cases if case["expected_count"] and (not join or case["row"]["details"])
                    and case.get("expected_issue_kind") != "missing_record"), cases[0])
    row = witness["row"]
    project, period = row["project"], row["report_date"]
    details = row["details"]
    for condition in comparison_conditions(definition):
        operands = [(BASE, condition["left"])]
        if condition.get("right_type", "field") == "field" and "right" in condition:
            operands.append((condition.get("right_table", BASE), condition["right"]))
        for side, field in operands:
            dtype = (project_types if side == role else detail_types)[field]
            if type_family(dtype) != "number" or base_type(dtype) == "bit":
                continue
            for label, value in [("负数", -1), ("零", 0)]:
                if side == role:
                    add(f"{field} 取{label}", {**row, "project": {**project, field: value}})
                elif details:
                    add(f"{field} 取{label}", {**row, "details": [{**details[0], field: value}]})
    if not join:
        return cases
    add("本期无明细", {**row, "details": []})
    if not details:
        return cases
    detail = details[0]
    date_field = join["report_date_field"] if role == BASE else definition.get("report_date_field") or "report_date"
    previous = (datetime.date.fromisoformat(period) - datetime.timedelta(days=1)).isoformat()
    add("仅有上期明细", {**row, "details": [{**detail, date_field: previous}]})
    add("两条相同明细逐条核查", {**row, "details": [dict(detail), dict(detail)]})
    if role == RELATED:
        add("明细定位编号为空", {**row, "details": [{**detail, definition["business_key"]: None}]})
    for item in definition.get("filters") or []:
        field = item["field"]
        if item.get("table", BASE) == role:
            outside = sample_value(_fail_value(item, project_types[field]), project_types[field])
            add("范围外项目无明细", {**row, "project": {**project, field: outside}, "details": []})
            if field in detail_types and _valid_value(outside, detail_types[field]):
                add("明细副本与项目范围值不同", {**row, "details": [{**detail, field: outside}]})
        else:
            excluded = {**detail, field: sample_value(_fail_value(item, detail_types[field]), detail_types[field])}
            add("明细全部不在检查范围", {**row, "details": [excluded, dict(excluded)]})
    return cases
