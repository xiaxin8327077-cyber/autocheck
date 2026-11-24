"""执行一条已编译规则，并把运行失败与业务命中分开。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .compiler import compile_rule
from .contracts import AppError
from .formula import is_arithmetic
from .generation_policy import review_ready
from .issue_query_results import collect_row, output_projection
from .project_context import (
    STATUS_MISSING_NULL, STATUS_OK,
    normalize_project_context,
    project_code_fields,
    project_name_fields,
    project_output_columns,
    project_row_status,
    project_semantics_required,
)
from .query_spec import base_type, is_condition_group, is_new_spec, needs_issue_kind, query_ready, referenced_columns, validate_spec_against_columns
from .sql_guard import guard_generated_sql, guard_sql


@dataclass(frozen=True)
class RuleRun:
    status: str
    violation_count: int
    truncated: bool
    error_code: str
    columns: tuple[str, ...] = ()
    rows: tuple[dict[str, Any], ...] = ()
    query_results: tuple[dict[str, Any], ...] = ()


def _columns_by_name(described: dict[str, Any]) -> dict[str, str]:
    return {
        str(column.get("column_name")): column.get("data_type")
        for column in described.get("columns") or [] if column.get("column_name")
    }


def execute_version(
    version: dict[str, Any],
    params: dict[str, Any],
    metadata: Any,
    *,
    require_project_context: bool = False,
) -> RuleRun:
    definition = version["definition"]
    try:
        if not query_ready(definition):
            return RuleRun("ERROR", 0, False, "VALIDATION_ERROR")
    except AppError:
        return RuleRun("ERROR", 0, False, "VALIDATION_ERROR")
    context = normalize_project_context(definition["project_context"]) if definition.get("project_context") is not None else None
    try:
        if not review_ready(definition):
            return RuleRun("ERROR", 0, False, "VALIDATION_ERROR")
    except AppError:
        return RuleRun("ERROR", 0, False, "VALIDATION_ERROR")

    source_id = str(definition.get("source_id") or "")
    list_sources = getattr(metadata, "list_sources", None)
    if callable(list_sources):
        source = next((item for item in list_sources() if str(item.id) == source_id), None)
        if source and str(source.dialect) != str(definition.get("dialect") or "mysql"):
            return RuleRun("ERROR", 0, False, "MAPPING_DRIFT")
    table_name = str(definition.get("table_name") or "")
    described = metadata.describe_table(source_id, table_name)
    base_types = _columns_by_name(described)
    base_columns = [
        column for column in described.get("columns") or [] if isinstance(column, dict)
    ]
    # 真实表结构自身中文角色/需求文本要求项目上下文；显式标志为 OR，缺 ctx 禁止执行旧 hash。
    requires_project_context = (
        require_project_context
        or bool(project_code_fields(base_columns) or project_name_fields(base_columns))
        or project_semantics_required(definition)
    )
    if context is None and requires_project_context:
        return RuleRun("ERROR", 0, False, "PROJECT_CONTEXT_REQUIRED")
    references = referenced_columns(definition)
    missing_base = [name for name in references["base"] if name not in base_types]
    main_date = str(definition.get("report_date_field") or "report_date")
    if definition.get("rule_type") == "field_compare" and is_new_spec(definition):
        # 新规格的主表日期映射同样严格限定真实 DATE，防止用采集时间对齐。
        if base_type(base_types.get(main_date)) != "date":
            return RuleRun("ERROR", 0, False, "MAPPING_DRIFT")

    known_related: set[str] = set()
    other_table = ""
    other_types: dict[str, str] = {}
    related_columns = []
    if references["related"]:
        join = definition.get("join") or {}
        if join:
            other_table = str(join.get("table_name") or "")
        elif context is not None and context["mode"] == "lookup":
            other_table = str(context["table_name"])
        try:
            described_other = metadata.describe_table(source_id, other_table)
        except AppError:
            raise
        except Exception:
            return RuleRun("ERROR", 0, False, "SOURCE_UNAVAILABLE")
        other_types = _columns_by_name(described_other)
        related_columns = described_other.get("columns") or []
        known_related = set(other_types)
        missing_related = [name for name in references["related"] if name not in known_related]
        # 执行期日期对齐漂移：关联/维度日期字段必须仍存在且严格为 DATE。
        if join:
            if base_type(other_types.get(str(join.get("report_date_field") or ""))) != "date":
                return RuleRun("ERROR", 0, False, "MAPPING_DRIFT")
        if context is not None and context["mode"] == "lookup" and context.get("date_field"):
            if base_type(other_types.get(str(context["date_field"]))) != "date":
                return RuleRun("ERROR", 0, False, "MAPPING_DRIFT")
        main_date = str(definition.get("report_date_field") or "report_date")
        if base_type(base_types.get(main_date)) != "date":
            return RuleRun("ERROR", 0, False, "MAPPING_DRIFT")
    else:
        missing_related: list[str] = []

    if missing_base or missing_related:
        return RuleRun("ERROR", 0, False, "MAPPING_DRIFT")
    if definition.get("rule_type") == "field_compare" and is_new_spec(definition):
        try:
            validate_spec_against_columns(definition, described.get("columns") or [],
                [{"column_name": name, "data_type": kind} for name, kind in other_types.items()] if other_table else None)
        except AppError:
            return RuleRun("ERROR", 0, False, "MAPPING_DRIFT")

    compiled_projection = definition.get("rule_type") != "custom_sql"
    if version.get("sql_text"):
        # 执行仍用已持久化的 SQL，但绑定参数必须按当前定义重建，避免缺参。
        sql = str(version["sql_text"])
        if definition.get("rule_type") == "custom_sql":
            compiled_params = dict(definition.get("params") or {})
        else:
            compiled_sql, compiled_params = compile_rule(version)
            compiled_projection = sql == compiled_sql
            if (definition.get("result_aliases") or context is not None or is_condition_group(definition)
                    or is_arithmetic(definition.get("expression"))
                    or definition.get("null_policy") in ("review", "zero")) and sql != compiled_sql:
                # 新增/修改 project_context 或数值空值策略后，旧持久化 SQL 必须拒绝执行。
                return RuleRun("ERROR", 0, False, "MAPPING_DRIFT")
            if "\\" in str(definition.get("violation_message") or "") and sql != compiled_sql:
                # Older literal SQL can interpret a backslash as quote escaping on MySQL.
                return RuleRun("ERROR", 0, False, "SQL_POLICY_DENIED")
    else:
        sql, compiled_params = compile_rule(version)

    bound = dict(compiled_params)
    bound.update(params)
    if definition.get("rule_type") != "custom_sql":
        # 值只来自定义：外部参数不得覆盖 right_value/tolerance/filter_* 等编译常量。
        for name, value in compiled_params.items():
            if name != "report_date":
                bound[name] = value

    if definition.get("rule_type") == "custom_sql":
        guard_sql(str(definition.get("dialect") or "mysql"), sql, set(base_types))
    else:
        tables = {table_name}
        if other_table:
            tables.add(other_table)
        guard_generated_sql(
            str(definition.get("dialect") or "mysql"), sql, set(base_types) | known_related, tables,
            definition=definition,
        )
    try:
        result = metadata.execute_select(
            source_id,
            sql,
            bound,
            timeout_seconds=float(params.get("timeout_seconds") or 60),
            max_rows=int(params.get("max_rows") or 200),
        )
    except TimeoutError:
        return RuleRun("TIMEOUT", 0, False, "TIMEOUT")
    except AppError:
        raise
    except Exception:
        return RuleRun("ERROR", 0, False, "SOURCE_UNAVAILABLE")
    count = len(result.rows)
    status = "PASS" if count == 0 else "VIOLATION"
    public_columns = ("business_key", "violation_message")
    if definition.get("project_driver") or needs_issue_kind(definition):
        public_columns += ("issue_kind",)
    if context is not None:
        public_columns += tuple(project_output_columns(context))
    raw_columns = tuple(column if isinstance(column, str) else None for column in (getattr(result, "columns", None) or ()))
    public_rows: list[dict[str, Any]] = []
    query_results: list[dict[str, Any]] = []
    columns, collection_status = output_projection(definition, sql, compiled_projection, raw_columns, base_columns, related_columns)
    result_aliases = definition.get("result_aliases") if compiled_projection else None
    row_template = (definition.get("project_driver") or {}).get("version") in (2, 3)
    for values in result.rows:
        raw = dict(zip(raw_columns, values)) if raw_columns else {}
        query_result = collect_row(columns, collection_status, raw)
        query_results.append(query_result)
        raw = query_result["values"]
        if result_aliases:
            raw = {role: raw.get(name) for role, name in result_aliases.items()}
        item = {
            "business_key": raw.get("business_key"),
            "violation_message": raw.get("violation_message"),
        }
        if "issue_kind" in public_columns:
            fallback = ("numeric" if definition.get("null_policy") == "zero" else "comparison") if row_template else "legacy"
            item["issue_kind"] = raw.get("issue_kind") or fallback
        if context is not None:
            if row_template and context["mode"] == "base":
                for role, field in (("project_code", context["code_field"]), ("project_name", context["name_field"])):
                    if field == definition["business_key"]:
                        raw[role] = raw.get("business_key")
            name = raw.get("project_name")
            item["project_code"] = raw.get("project_code")
            item["project_name"] = name
            if row_template:
                item["project_name_status"] = STATUS_OK if name is not None and str(name).strip() else STATUS_MISSING_NULL
            else:
                item["project_name_status"] = project_row_status(
                    mode="lookup" if definition.get("project_driver") else context["mode"],
                    code=raw.get("project_code"), name=name, match_count=raw.get("project_match_count"),
                )
        public_rows.append(item)
    return RuleRun(status, count, bool(result.truncated), "",
                   tuple(public_columns), tuple(public_rows), tuple(query_results))
