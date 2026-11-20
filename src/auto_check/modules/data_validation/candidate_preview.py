"""Compile unsaved candidates and run bounded synthetic cases, without storage or business queries."""

from __future__ import annotations

import re
from typing import Any

from .compiler import compile_rule, is_finite_number
from .contracts import AppError, content_hash
from .generation_policy import ai_review_pending, validate_review
from .project_driver_samples import ISSUE_KINDS, MAX_DETAILS, project_sample_schema, validate_project_sample
from .query_spec import (
    BASE,
    RELATED,
    canonicalize_definition,
    comparison_conditions,
    is_condition_group,
    is_new_spec,
    is_unary,
    query_ready,
    validate_spec_against_columns,
)
from .query_samples import case_fields, evaluate_case_with_kind
from .result_aliases import build_result_aliases
from .sql_display import inline_sql_parameters
from .sql_guard import guard_generated_sql
from .test_runner import default_field_compare_cases, evaluate_case

_DEFINITION_KEYS = (
    "name", "description", "rule_type", "source_id", "dialect", "report_category", "table_name",
    "business_key", "report_date_field", "expression", "violation_message", "null_policy", "equality_policy",
    "generation_mode", "mapping_version", "uncertainties", "uncertainty_resolutions", "unsupported_requirements",
    "filters", "join", "project_context", "null_handling", "null_evidence", "include_result_fields",
    "analysis_protocol", "semantic_intent", "project_driver",
)
_SQL_LAYOUT_TOKENS = re.compile(r"'([^']|'')*'|\"[^\"]*\"|`[^`]*`|[(),]|\b(?:SELECT|FROM|WHERE|AND)\b")


def _format_preview_sql(sql: str) -> str:
    """Lay out the outer SELECT without modifying quoted values or nested expressions."""
    parts: list[str] = []
    depth = 0
    in_select = True
    start = 0
    for token in _SQL_LAYOUT_TOKENS.finditer(sql):
        value = token.group()
        if value == "(":
            depth += 1
        elif value == ")":
            depth -= 1
        elif depth == 0:
            if value == "SELECT":
                parts.append(sql[start:token.start()])
                parts.append("SELECT\n    ")
                in_select = True
                start = token.end() + 1
            elif value == "," and in_select:
                parts.append(sql[start:token.end()] + "\n    ")
                start = token.end() + 1
            elif value in {"FROM", "WHERE", "AND"}:
                in_select = False
                parts.append(sql[start:token.start()].rstrip() + ("\n  " if value == "AND" else "\n"))
                start = token.start()
    return "".join(parts) + sql[start:]


def candidate_definition(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy only rule inputs, excluding any client preview, test results or SQL."""
    return {key: payload[key] for key in _DEFINITION_KEYS if key in payload}


def compile_checked_definition(definition: dict[str, Any], documented_identifiers: list[str]) -> tuple[str, dict[str, Any]]:
    sql, params = compile_rule({"definition": definition})
    if "project_driver" in definition:
        guard_generated_sql(str(definition.get("dialect") or ""), sql, set(documented_identifiers), definition=definition)
    else:
        guard_generated_sql(str(definition.get("dialect") or ""), sql, set(documented_identifiers))
    return sql, params


def preview_definition(
    payload: dict[str, Any],
    columns: list[dict[str, Any]],
    related_columns: list[dict[str, Any]] | None = None,
    project_columns: list[dict[str, Any]] | None = None,
    *,
    preserve_result_fields: bool = False,
    validate_only: bool = False,
    require_ai_review: bool = False,
) -> dict[str, Any]:
    definition = candidate_definition(payload)
    if not preserve_result_fields:
        definition["include_result_fields"] = True
    # 一元表达式规范化并补默认口径；非一元保持 unresolved 缺省。
    definition = canonicalize_definition(definition)
    definition.setdefault("null_policy", "unresolved")
    definition.setdefault("equality_policy", "unresolved")
    if definition.get("rule_type") != "field_compare":
        raise AppError("VALIDATION_ERROR")
    names = {str(column["column_name"]): column for column in columns}
    related = {str(column["column_name"]): column for column in related_columns or []}
    conditions = comparison_conditions(definition)
    for expression in conditions:
        if not isinstance(expression, dict) or expression.get("op") not in (
            "lt", "lte", "gt", "gte", "eq", "neq", "is_null", "is_not_null",
        ):
            raise AppError("VALIDATION_ERROR")
        if not isinstance(expression.get("left"), str) or expression.get("left") not in names:
            raise AppError("VALIDATION_ERROR")
        unary = expression.get("op") in ("is_null", "is_not_null")
        right_table = expression.get("right_table") or BASE
        if not unary:
            if right_table not in (BASE, RELATED):
                raise AppError("VALIDATION_ERROR")
            right_type = expression.get("right_type", "field")
            if right_type == "value":
                if right_table == RELATED or not is_finite_number(expression.get("right")):
                    raise AppError("VALIDATION_ERROR")
            elif right_type != "field" or not isinstance(expression.get("right"), str):
                raise AppError("VALIDATION_ERROR")
            else:
                target = related if right_table == RELATED else names
                if expression.get("right") not in target:
                    raise AppError("VALIDATION_ERROR")
    if not isinstance(definition.get("business_key"), str) or definition.get("business_key") not in names:
        raise AppError("VALIDATION_ERROR")
    only_unary = all(item.get("op") in ("is_null", "is_not_null") for item in conditions)
    allowed_null = ("unresolved", "skip", "violate") if only_unary else ("unresolved", "skip", "zero", "review")
    if definition.get("null_policy", "unresolved") not in allowed_null:
        raise AppError("VALIDATION_ERROR")
    if definition.get("equality_policy", "unresolved") not in ("unresolved", "allow_equal", "reject_equal"):
        raise AppError("VALIDATION_ERROR")
    if (not is_condition_group(definition) and not only_unary and expression.get("right_type", "field") == "field"
            and definition.get("equality_policy") != "unresolved"):
        implied = "reject_equal" if expression["op"] in ("eq", "lte", "gte") else "allow_equal"
        if definition.get("equality_policy") not in (None, implied):
            raise AppError("VALIDATION_ERROR")
    date_field = definition.get("report_date_field", "report_date")
    if not date_field:
        raise AppError("PREVIEW_DATE_FIELD_REQUIRED")
    if not isinstance(date_field, str) or date_field not in names:
        raise AppError("PREVIEW_DATE_FIELD_REQUIRED" if date_field == "report_date" else "PREVIEW_DATE_FIELD_INVALID")
    date_column = next(column for column in columns if column["column_name"] == date_field)
    if date_field != "report_date" and str(date_column.get("data_type") or "").strip().lower() != "date":
        raise AppError("PREVIEW_DATE_FIELD_INVALID")

    # filters/join/project_context 结构、字段存在性、取值类型与关联日期对齐复核。
    second_columns = related_columns if related_columns is not None else project_columns
    validate_spec_against_columns(definition, columns, second_columns)
    validate_review(definition)
    if (require_ai_review or definition.get("generation_mode") == "ai") and (
            payload.get("questions") or ai_review_pending(definition)):
        raise AppError("VALIDATION_ERROR")
    identifiers = set(names) | {str(column["column_name"]) for column in (second_columns or [])} \
        | {str(definition.get("table_name") or "")}
    join = (definition.get("join") or {}) if isinstance(definition.get("join"), dict) else {}
    if join:
        identifiers.add(str(join.get("table_name") or ""))
    context = definition.get("project_context")
    if isinstance(context, dict) and context.get("mode") == "lookup":
        identifiers.add(str(context.get("table_name") or ""))
    if not preserve_result_fields or "result_aliases" in payload:
        definition["result_aliases"] = build_result_aliases(definition, columns, second_columns, project_columns)
    prepared = {"definition": definition, "documented_identifiers": sorted(identifiers),
                "columns": columns, "related_columns": second_columns, "project_columns": project_columns}
    if validate_only:
        return prepared
    return compile_prepared_preview(prepared)


def compile_prepared_preview(prepared: dict[str, Any]) -> dict[str, Any]:
    """Compile only a server-validated definition and its matching document evidence."""
    definition = prepared["definition"]
    columns = prepared["columns"]
    second_columns = prepared["related_columns"]
    project_columns = prepared["project_columns"]
    context = definition.get("project_context")
    documented_identifiers = prepared["documented_identifiers"]
    sql, params = compile_checked_definition(definition, documented_identifiers)
    digest = content_hash(definition, str(definition.get("dialect") or ""), str(definition.get("mapping_version") or ""), sql)
    cases = default_field_compare_cases(definition, columns, second_columns)
    return {
        "definition": definition,
        "sql_preview": sql,
        "sql_display": _format_preview_sql(inline_sql_parameters(sql, params, str(definition.get("dialect") or ""))),
        "sql_display_params": {key: value for key, value in params.items() if key == "report_date"},
        "sql_params": params,
        "content_sha256": digest,
        "cases": [{**case, "status": "not_run", "actual_count": None} for case in cases],
        "sample_source": "document_synthetic",
        "persisted": False,
        **({"columns": [{"column_name": col["column_name"], "comment": col.get("comment") or "",
                         "data_type": col["data_type"]} for col in columns]} if "project_driver" in definition else {}),
        "related_columns": [
            {"column_name": column.get("column_name"), "comment": column.get("comment") or "",
             "data_type": column.get("data_type") or ""}
            for column in (second_columns or [])
        ],
        "project_columns": [
            {"column_name": column.get("column_name"), "comment": column.get("comment") or "",
             "data_type": column.get("data_type") or ""}
            for column in (project_columns or [])
        ],
        "project_table": (context.get("table_name") if isinstance(context, dict) and context.get("mode") == "lookup" else None),
    }


def _valid_case_value(value: Any) -> bool:
    if value is None:
        return True
    if type(value) not in (str, int, float):
        return False
    if isinstance(value, str) and len(value) > 2000:
        return False
    if type(value) in (int, float) and not is_finite_number(value):
        return False
    return True


def _collect_values(row: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for value in row.values():
        if isinstance(value, dict):
            values.extend(_collect_values(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    values.extend(_collect_values(item))
                else:
                    values.append(item)
        else:
            values.append(value)
    return values


def run_preview_cases(preview: dict[str, Any], supplied: Any = None) -> dict[str, Any]:
    definition = preview["definition"]
    selected = preview["cases"] if supplied is None else supplied
    if not isinstance(selected, list) or not 1 <= len(selected) <= 100:
        raise AppError("VALIDATION_ERROR")
    expression = definition["expression"]
    nested = is_new_spec(definition)
    project_driven = "project_driver" in definition
    if project_driven:
        project_types, detail_types = project_sample_schema(definition, preview["columns"], preview["related_columns"])
    elif nested:
        base_fields, related_fields = case_fields(definition)
        fields = set(base_fields)
    else:
        fields = {expression["left"]}
        if not is_unary(definition) and expression.get("right_type", "field") == "field":
            fields.add(expression["right"])
    ready = query_ready(definition)

    results = []
    for case in selected:
        if not isinstance(case, dict) or not isinstance(case.get("row"), dict):
            raise AppError("VALIDATION_ERROR")
        row = case["row"]
        expected = case.get("expected_count")
        if type(expected) is not int or not 0 <= expected <= (MAX_DETAILS if project_driven else 1):
            raise AppError("VALIDATION_ERROR")
        name = case.get("name", "样本测试")
        if not isinstance(name, str) or len(name) > 100:
            raise AppError("VALIDATION_ERROR")

        expected_kind = case.get("expected_issue_kind")
        if project_driven:
            validate_project_sample(row, project_types, detail_types)
            if expected_kind is not None and (not isinstance(expected_kind, str) or expected_kind not in ISSUE_KINDS):
                raise AppError("VALIDATION_ERROR")
        elif nested:
            if set(row) != {"base", "related", "report_date"}:
                raise AppError("VALIDATION_ERROR")
            base = row["base"]
            related_rows = row["related"]
            period = row["report_date"]
            if not isinstance(base, dict) or set(base) != set(base_fields):
                raise AppError("VALIDATION_ERROR")
            if not isinstance(related_rows, list) or len(related_rows) > 20:
                raise AppError("VALIDATION_ERROR")
            if not isinstance(period, str) or not period:
                raise AppError("VALIDATION_ERROR")
            for value in base.values():
                if not _valid_case_value(value):
                    raise AppError("VALIDATION_ERROR")
            for item in related_rows:
                if not isinstance(item, dict) or set(item) != set(related_fields):
                    raise AppError("VALIDATION_ERROR")
                for value in item.values():
                    if not _valid_case_value(value):
                        raise AppError("VALIDATION_ERROR")
        else:
            if set(row) != fields:
                raise AppError("VALIDATION_ERROR")
            for value in row.values():
                if not _valid_case_value(value):
                    raise AppError("VALIDATION_ERROR")

        unresolved = not ready
        if not unresolved and definition.get("null_policy", "unresolved") == "unresolved":
            unresolved = any(value is None for value in _collect_values(row))
        try:
            actual_kind = None
            if project_driven and not unresolved:
                actual, actual_kind = evaluate_case_with_kind(definition, row)
            else:
                actual = None if unresolved else evaluate_case(definition, row)
        except (TypeError, ValueError, OverflowError):
            raise AppError("VALIDATION_ERROR") from None
        matches = actual == expected and (not project_driven or expected_kind is None or actual_kind == expected_kind)
        status = "not_run" if actual is None else "passed" if matches else "failed"
        result = {"name": name, "row": row, "expected_count": expected, "actual_count": actual, "status": status}
        if project_driven:
            result["actual_issue_kind"] = actual_kind
            if expected_kind is not None:
                result["expected_issue_kind"] = expected_kind
        results.append(result)
    return {
        "cases": results,
        "content_sha256": preview["content_sha256"],
        "persisted": False,
        "passed_count": sum(case["status"] == "passed" for case in results),
        "failed_count": sum(case["status"] == "failed" for case in results),
        "not_run_count": sum(case["status"] == "not_run" for case in results),
        "sample_source": "document_synthetic",
    }
