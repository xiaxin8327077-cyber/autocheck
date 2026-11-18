"""把配置型规则编译成方言 SQL。值只走绑定参数。

旧 field_compare 表达式的 SQL 文本保持不变；新 filters/join 规格在其后追加，
join 使用相关 EXISTS 半连接，右表重复不会放大基表行。
"""

from __future__ import annotations

import math
from typing import Any

from .contracts import AppError
from .project_context import normalize_project_context
from .query_spec import BASE, RELATED, UNARY_OPS, needs_issue_kind, validate_query_spec
from .sql_guard import quote_identifier

_OPS = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">=", "eq": "=", "neq": "<>"}
_RIGHT_TYPES = {"field", "value"}
_FILTER_OPS = {
    "eq": "=", "neq": "<>", "lt": "<", "lte": "<=",
    "gt": ">", "gte": ">=", "in": "IN", "not_in": "NOT IN",
}


def is_finite_number(value: Any) -> bool:
    """仅接受有限 int/float。bool 是 int 子类必须排除；int 无上界，不能转 float 判有限。"""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _filter_predicate(
    dialect: str,
    alias: str,
    item: dict[str, Any],
    params: dict[str, Any],
    index: int,
) -> str:
    column = f"{alias}.{quote_identifier(dialect, item['field'])}"
    op = item["op"]
    if op == "is_null":
        return f"{column} IS NULL"
    if op == "is_not_null":
        return f"{column} IS NOT NULL"
    if op in ("in", "not_in"):
        names = []
        for offset, value in enumerate(item["value"]):
            name = f"filter_{index}_{offset}"
            params[name] = value
            names.append(f":{name}")
        keyword = _FILTER_OPS[op]
        return f"({column} IS NOT NULL AND {column} {keyword} ({', '.join(names)}))"
    name = f"filter_{index}"
    params[name] = item["value"]
    if op == "neq":
        return f"({column} IS NOT NULL AND {column} <> :{name})"
    return f"{column} {_FILTER_OPS[op]} :{name}"


def _exists_clause(
    dialect: str,
    spec: dict[str, Any],
    params: dict[str, Any],
    comparison: str | None,
) -> str:
    join = spec["join"]
    clauses = [
        f"o.{quote_identifier(dialect, pair['right'])} = t.{quote_identifier(dialect, pair['left'])}"
        for pair in join["on"]
    ]
    clauses.append(f"o.{quote_identifier(dialect, join['report_date_field'])} = :report_date")
    for index, item in enumerate(spec["filters"], start=1):
        if item["table"] == RELATED:
            clauses.append(_filter_predicate(dialect, "o", item, params, index))
    if comparison is not None:
        clauses.append(comparison)
    other = quote_identifier(dialect, join["table_name"])
    return f"EXISTS (SELECT 1 FROM {other} AS o WHERE {' AND '.join(clauses)})"


def _project_select_suffix(dialect: str, definition: dict[str, Any]) -> str:
    """项目上下文只增加输出投影，不增加 WHERE/聚合，保持业务行与计数不变。"""
    raw = definition.get("project_context")
    if raw is None:
        return ""
    context = normalize_project_context(raw)
    code = quote_identifier(dialect, context["code_field"])
    name = quote_identifier(dialect, context["name_field"])
    if context["mode"] == "base":
        return f", t.{code} AS project_code, t.{name} AS project_name"
    table = quote_identifier(dialect, context["table_name"])
    key_left = quote_identifier(dialect, context["key"]["left"])
    key_right = quote_identifier(dialect, context["key"]["right"])
    predicate = f"p.{key_right} = t.{key_left}"
    if context.get("date_field"):
        date_column = quote_identifier(dialect, context["date_field"])
        predicate += f" AND p.{date_column} = :report_date"
    name_expression = (
        f"(SELECT CASE WHEN COUNT(*) = 1 THEN MAX(p.{name}) END "
        f"FROM {table} AS p WHERE {predicate})"
    )
    count_expression = f"(SELECT COUNT(*) FROM {table} AS p WHERE {predicate})"
    return (
        f", t.{code} AS project_code, {name_expression} AS project_name, "
        f"{count_expression} AS project_match_count"
    )


def _inject_review_projection(
    select: str, message_sql: str, message_expr: str, issue_expr: str,
) -> str:
    marker = f"{message_sql} AS violation_message"
    if marker not in select:
        raise AppError("VALIDATION_ERROR")
    return select.replace(
        marker, f"{message_expr} AS violation_message, {issue_expr} AS issue_kind", 1,
    )


def _inject_issue_column(select: str, issue_expr: str) -> str:
    marker = " AS violation_message"
    index = select.find(marker)
    if index < 0:
        raise AppError("VALIDATION_ERROR")
    end = index + len(marker)
    return select[:end] + f", {issue_expr} AS issue_kind" + select[end:]


def compile_rule(version: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    definition = version["definition"]
    dialect = str(definition.get("dialect") or version.get("dialect") or "mysql")
    rule_type = str(definition.get("rule_type") or "")
    table = str(definition.get("table_name") or "")
    key = str(definition.get("business_key") or "id")
    message = str(definition.get("violation_message") or "校验异常")
    # Backslashes can escape quote-doubling on MySQL. Bind such text, never embed it in SQL.
    bind_message = "\\" in message
    message_sql = ":violation_message" if bind_message else "'" + message.replace("'", "''") + "'"
    if definition.get("project_context") is not None and rule_type != "field_compare":
        # 其余类型的安全投影语义尚未核验；明确拒绝，禁止默默只出合同键。
        raise AppError("VALIDATION_ERROR")
    context_suffix = _project_select_suffix(dialect, definition) if rule_type == "field_compare" else ""
    quoted_table = quote_identifier(dialect, table)
    quoted_key = quote_identifier(dialect, key)
    select = (
        f"SELECT t.{quoted_key} AS business_key, {message_sql} AS violation_message{context_suffix} "
        f"FROM {quoted_table} AS t WHERE t.{quote_identifier(dialect, str(definition.get('report_date_field') or 'report_date'))} = :report_date"
    )
    params: dict[str, Any] = {"report_date": definition.get("report_date")}
    if bind_message:
        params["violation_message"] = message
    if rule_type == "field_compare":
        spec = validate_query_spec(definition)
        expression = definition.get("expression") or {}
        left = str(expression.get("left") or "")
        op_name = str(expression.get("op") or "")
        if op_name not in _OPS and op_name not in UNARY_OPS:
            raise AppError("VALIDATION_ERROR")
        # 旧版表达式只有 left/op/right，未声明 right_type 时仍按字段比较处理。
        right_type = str(expression.get("right_type") or "field")
        if right_type not in _RIGHT_TYPES:
            raise AppError("VALIDATION_ERROR")

        # 新规格：主表筛选条件（AND，字符串/数值常量全部绑定）。
        for index, item in enumerate(spec["filters"], start=1):
            if item["table"] == BASE:
                select += f" AND {_filter_predicate(dialect, 't', item, params, index)}"

        if op_name in UNARY_OPS:
            # 一元判空：目标为 NULL 的行必须进入违规判断，不能按 skip 提前排除。
            keyword = "IS NULL" if op_name == "is_null" else "IS NOT NULL"
            select += f" AND t.{quote_identifier(dialect, left)} {keyword}"
            join = spec["join"]
            if join is not None:
                select += f" AND {_exists_clause(dialect, spec, params, None)}"
            if needs_issue_kind(definition):
                select = _inject_issue_column(select, "'comparison'")
            return select, params

        right_table = spec["right_table"]
        policy = definition.get("null_policy")
        handling = definition.get("null_handling") or {}
        default_mode = policy if policy in ("zero", "review") else None
        left_mode = handling.get("left", default_mode)
        right_mode = handling.get("right", default_mode)
        review_mode = left_mode == "review" or right_mode == "review"
        left_field = quote_identifier(dialect, left)
        raw_left_ref = f"t.{left_field}"
        raw_right_ref = None
        if right_type == "value":
            right_value = expression.get("right")
            if not is_finite_number(right_value):
                raise AppError("VALIDATION_ERROR")
            params["right_value"] = right_value
            right_sql = ":right_value"
        else:
            right_column = quote_identifier(dialect, str(expression.get('right') or ''))
            raw_right_ref = f"o.{right_column}" if right_table == RELATED else f"t.{right_column}"
            right_sql = f"COALESCE({raw_right_ref}, 0)" if right_mode == "zero" else raw_right_ref
        left_sql = f"COALESCE({raw_left_ref}, 0)" if left_mode == "zero" else raw_left_ref

        if policy == "skip":
            select += f" AND {raw_left_ref} IS NOT NULL"
            # 常量不是字段，skip 只跳过左字段为空的行。
            if right_type == "field" and right_table == BASE:
                select += f" AND {right_sql} IS NOT NULL"

        join = spec["join"]
        if not review_mode:
            if right_table != RELATED:
                select += f" AND {left_sql} {_OPS[op_name]} {right_sql}"
            if join is not None:
                comparison = None
                if right_table == RELATED:
                    if policy == "skip":
                        comparison = f"{raw_right_ref} IS NOT NULL"
                    comparison = (
                        f"{comparison + ' AND ' if comparison else ''}"
                        f"{left_sql} {_OPS[op_name]} {right_sql}"
                    )
                select += f" AND {_exists_clause(dialect, spec, params, comparison)}"
            if needs_issue_kind(definition):
                select = _inject_issue_column(select, "'numeric'" if policy == "zero" else "'comparison'")
            return select, params

        # review：固定安全模板，缺值与真正数值违规都进入核查候选；不改 filters/join keys。
        left_label = str(left)
        right_label = str(expression.get("right") or "")
        params["dv_missing_left"] = f"缺值待核实：{left_label} 为 NULL"
        if right_type == "field":
            params["dv_missing_right"] = f"缺值待核实：{right_label} 为 NULL"
        if right_table == RELATED:
            matched = _exists_clause(dialect, spec, params, None)
            violation = _exists_clause(dialect, spec, params, f"{left_sql} {_OPS[op_name]} {right_sql}")
            missing_predicates = []
            if left_mode == "review":
                missing_predicates.append(f"{raw_left_ref} IS NULL")
            if right_mode == "review":
                right_missing = _exists_clause(
                    dialect, spec, params, f"{raw_right_ref} IS NULL",
                )
                missing_predicates.append(right_missing)
            candidate_parts = [violation]
            if missing_predicates:
                candidate_parts.append(f"{matched} AND ({' OR '.join(missing_predicates)})")
            select += f" AND ({' OR '.join(candidate_parts)})"
            issue_expr = (
                f"CASE WHEN {violation} THEN 'numeric' "
                f"WHEN {matched} AND ({' OR '.join(missing_predicates) or 'FALSE'}) "
                f"THEN 'missing_value' ELSE 'numeric' END"
            )
            message_case = f"CASE WHEN {violation} THEN {message_sql}"
            if len(missing_predicates) == 2:
                params["dv_missing_both"] = f"缺值待核实：{left_label}、{right_label} 为 NULL"
                message_case += f" WHEN {' AND '.join(missing_predicates)} THEN :dv_missing_both"
            if left_mode == "review":
                message_case += f" WHEN {raw_left_ref} IS NULL THEN :dv_missing_left"
            if right_mode == "review":
                message_case += f" WHEN {right_missing} THEN :dv_missing_right"
            message_case += f" ELSE {message_sql} END"
            select = _inject_review_projection(select, message_sql, message_case, issue_expr)
            return select, params

        missing_checks = []
        if left_mode == "review":
            missing_checks.append(f"{raw_left_ref} IS NULL")
        if right_mode == "review" and raw_right_ref is not None:
            missing_checks.append(f"{raw_right_ref} IS NULL")
        predicate = "(" + " OR ".join([f"{left_sql} {_OPS[op_name]} {right_sql}", *missing_checks]) + ")"
        select += f" AND {predicate}"
        issue_expr = (
            f"CASE WHEN {' OR '.join(missing_checks)} THEN 'missing_value' ELSE 'numeric' END"
        )
        message_case = "CASE"
        if len(missing_checks) == 2:
            params["dv_missing_both"] = f"缺值待核实：{left_label}、{right_label} 为 NULL"
            message_case += f" WHEN {' AND '.join(missing_checks)} THEN :dv_missing_both"
        if left_mode == "review":
            message_case += f" WHEN {raw_left_ref} IS NULL THEN :dv_missing_left"
        if right_mode == "review" and raw_right_ref is not None:
            message_case += f" WHEN {raw_right_ref} IS NULL THEN :dv_missing_right"
        message_case += f" ELSE {message_sql} END"
        select = _inject_review_projection(select, message_sql, message_case, issue_expr)
        if join is not None:
            select += f" AND {_exists_clause(dialect, spec, params, None)}"
        return select, params
    if rule_type == "amount_equation":
        assets = quote_identifier(dialect, str(definition["assets"]))
        liabilities = quote_identifier(dialect, str(definition["liabilities"]))
        equity = quote_identifier(dialect, str(definition["equity"]))
        params["tolerance"] = definition.get("tolerance", 0.01)
        select += f" AND ABS(t.{assets} - (t.{liabilities} + t.{equity})) > :tolerance"
        return select, params
    if rule_type == "not_null":
        field = quote_identifier(dialect, str(definition["field"]))
        select += f" AND t.{field} IS NULL"
        return select, params
    if rule_type == "enum":
        field = quote_identifier(dialect, str(definition["field"]))
        params["allowed"] = list(definition.get("allowed") or [])
        select += f" AND t.{field} NOT IN :allowed"
        return select, params
    if rule_type == "unique":
        keys = ", ".join(f"t.{quote_identifier(dialect, str(item))}" for item in definition["keys"])
        select = (
            f"SELECT {keys} AS business_key, {message_sql} AS violation_message "
            f"FROM {quoted_table} AS t GROUP BY {keys} HAVING COUNT(*) > 1"
        )
        return select, {"violation_message": message} if bind_message else {}
    if rule_type == "cross_table_exists":
        other = quote_identifier(dialect, str(definition["other_table"]))
        left = quote_identifier(dialect, str(definition["key"]))
        right = quote_identifier(dialect, str(definition.get("other_key") or definition["key"]))
        select += (
            f" AND NOT EXISTS (SELECT 1 FROM {other} AS o WHERE o.{right} = t.{left})"
        )
        return select, params
    if rule_type == "custom_sql":
        sql = str(definition.get("sql") or version.get("sql_text") or "")
        return sql, dict(definition.get("params") or {})
    raise AppError("VALIDATION_ERROR")
