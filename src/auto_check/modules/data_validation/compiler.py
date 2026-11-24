"""把配置型规则编译成方言 SQL。值只走绑定参数。

历史规则按版本保留原投影。关联使用相关 EXISTS 半连接，右表重复不会放大基表行。
"""

from __future__ import annotations

import math
from typing import Any

from .contracts import AppError
from .formula import (CALCULATION_MESSAGE, arithmetic_projection, compile_formula, group_formula_parts,
                      group_formula_projection, has_arithmetic, is_arithmetic)
from .project_context import normalize_project_context
from .query_spec import BASE, RELATED, TEXT_FILTER_OPS, UNARY_OPS, comparison_conditions, is_condition_group, needs_issue_kind, valid_comparison_literal, validate_query_spec
from .sql_guard import quote_identifier
from .result_aliases import quoted_output_aliases

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


def _text_column(dialect, column):
    return f"CAST({column} AS {'CHAR' if dialect == 'mysql' else 'TEXT'})"


def _keyword_predicate(dialect, raw_column, op, words, params, prefix, *, skip_empty=False):
    column = _text_column(dialect, raw_column)
    positive = op == "contains_any"
    # MySQL connections use utf8mb4. PostgreSQL's C collation and utf8mb4_bin
    # preserve case and literal punctuation irrespective of the source column collation.
    function, collation = ("INSTR", "utf8mb4_bin") if dialect == "mysql" else ("STRPOS", '"C"')
    predicates = []
    for offset, word in enumerate(words):
        name = f"{prefix}_{offset}"
        params[name] = word
        predicates.append(f"{function}({column} COLLATE {collation}, :{name}) {'>' if positive else '='} 0")
    match = "(" + (" OR " if positive else " AND ").join(predicates) + ")"
    return f"(LENGTH({column}) > 0 AND {match})" if skip_empty else match


def _comparison_predicate(dialect, left, item, right, policy):
    if item.get("right_type") == "value" and isinstance(item["right"], str):
        column = _text_column(dialect, left)
        predicate = f"{column} {_OPS[item['op']]} {right}"
        return f"(LENGTH({column}) > 0 AND {predicate})" if policy == "skip" else predicate
    return f"{left} {_OPS[item['op']]} {right}"


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
    if op in TEXT_FILTER_OPS:
        return _keyword_predicate(dialect, column, op, item["value"], params, f"filter_{index}")
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


def _related_predicates(dialect: str, spec: dict[str, Any], params: dict[str, Any]) -> list[str]:
    join = spec["join"]
    clauses = [
        f"o.{quote_identifier(dialect, pair['right'])} = t.{quote_identifier(dialect, pair['left'])}"
        for pair in join["on"]
    ]
    clauses.append(f"o.{quote_identifier(dialect, join['report_date_field'])} = :report_date")
    for index, item in enumerate(spec["filters"], start=1):
        if item["table"] == RELATED:
            clauses.append(_filter_predicate(dialect, "o", item, params, index))
    return clauses


def _exists_clause(
    dialect: str, spec: dict[str, Any], params: dict[str, Any], comparison: str | None,
) -> str:
    clauses = _related_predicates(dialect, spec, params)
    if comparison is not None:
        clauses.append(comparison)
    other = quote_identifier(dialect, spec["join"]["table_name"])
    return f"EXISTS (SELECT 1 FROM {other} AS o WHERE {' AND '.join(clauses)})"


def _project_select_suffix(dialect: str, definition: dict[str, Any], aliases: dict[str, str]) -> str:
    """项目上下文只增加输出投影，不增加 WHERE/聚合，保持业务行与计数不变。"""
    raw = definition.get("project_context")
    if raw is None:
        return ""
    context = normalize_project_context(raw)
    code = quote_identifier(dialect, context["code_field"])
    name = quote_identifier(dialect, context["name_field"])
    if context["mode"] == "base":
        return f", t.{code} AS {aliases['project_code']}, t.{name} AS {aliases['project_name']}"
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
        f", t.{code} AS {aliases['project_code']}, {name_expression} AS {aliases['project_name']}, "
        f"{count_expression} AS {aliases['project_match_count']}"
    )


def _inject_review_projection(
    select: str, message_sql: str, message_expr: str, issue_expr: str, aliases: dict[str, str],
) -> str:
    marker = f"{message_sql} AS {aliases['violation_message']}"
    if marker not in select:
        raise AppError("VALIDATION_ERROR")
    return select.replace(
        marker, f"{message_expr} AS {aliases['violation_message']}, {issue_expr} AS {aliases['issue_kind']}", 1,
    )


def _summed_details(definition, join, detail_table, detail_day, filters, column, *, matched_only=False):
    # Aggregate actual details before matching projects, so repeated project rows
    # cannot multiply an otherwise identical detail sum.
    date_pair = {"left": definition.get("report_date_field") or "report_date", "right": join["report_date_field"]}
    pairs = [pair for pair in join["on"] if not matched_only or pair != date_pair]
    pairs = pairs or join["on"]
    keys = [column("related", pair["right"]) for pair in pairs]
    selected = [f"{key} AS dv_key_{i}" for i, key in enumerate(keys)]
    amount = column("related", definition["expression"]["right"])
    eligible = " AND ".join(filters)
    count = f"COUNT(CASE WHEN {eligible} THEN 1 END)" if filters else "COUNT(*)"
    value = f"COALESCE({amount}, 0)" if definition["null_policy"] == "zero" else amount
    if filters:
        value = f"CASE WHEN {eligible} THEN {value} END"
    total = f"SUM({value})"
    if definition["null_policy"] != "zero":
        total = f"CASE WHEN {count} = COUNT({value}) THEN {total} END"
    selected.extend([count + " AS dv_count", total + " AS dv_sum"])
    match = [f"{column('base', pair['left'])} = s.dv_key_{i}" for i, pair in enumerate(pairs)]
    join_type = " INNER JOIN" if matched_only else " LEFT JOIN"
    return (join_type + " (SELECT " + ", ".join(selected) + f" FROM {detail_table} AS d WHERE {detail_day} = :report_date"
            + " GROUP BY " + ", ".join(dict.fromkeys(keys)) + ") AS s ON " + " AND ".join(match))


def _related_sum_query(dialect: str, definition: dict[str, Any], spec: dict[str, Any],
                       params: dict[str, Any], message_sql: str, aliases: dict[str, str]) -> str:
    expression = definition["expression"]
    left = quote_identifier(dialect, expression["left"])
    right = quote_identifier(dialect, expression["right"])
    base = quote_identifier(dialect, definition["table_name"])
    related = quote_identifier(dialect, spec["join"]["table_name"])
    key = quote_identifier(dialect, definition["business_key"])
    date = quote_identifier(dialect, definition["report_date_field"])
    zero = definition.get("null_policy") == "zero"
    matched_only = spec["join"]["unmatched_policy"] == "exclude"
    source = f"FROM {base} AS t"
    if matched_only:
        def column(side, name):
            return ("t." if side == BASE else "d.") + quote_identifier(dialect, name)
        filters = [_filter_predicate(dialect, "d", item, params, index)
                   for index, item in enumerate(spec["filters"], 1) if item["table"] == RELATED]
        source += _summed_details(definition, spec["join"], related, column(RELATED, spec["join"]["report_date_field"]),
                                  filters, column, matched_only=True)
        count, total = "s.dv_count", "s.dv_sum"
    else:
        detail_scope = " AND ".join(_related_predicates(dialect, spec, params))
        detail_from = f" FROM {related} AS o WHERE {detail_scope}"
        total = (f"(SELECT SUM(COALESCE(o.{right}, 0)){detail_from})" if zero else
                 f"(SELECT CASE WHEN COUNT(*) = COUNT(o.{right}) THEN SUM(o.{right}) END{detail_from})")
        count = f"(SELECT COUNT(*){detail_from})"
    base_scope = [f"t.{date} = :report_date"]
    for index, item in enumerate(spec["filters"], 1):
        if item["table"] == BASE:
            base_scope.append(_filter_predicate(dialect, "t", item, params, index))
    if matched_only:
        base_scope.append("s.dv_count > 0")
    evidence = (f"SELECT t.{key} AS {aliases['business_key']}{_project_select_suffix(dialect, definition, aliases)}, "
                f"t.{date} AS {aliases['data_date']}, t.{left} AS {aliases['checked_value']}, "
                f"{count} AS {aliases['related_count']}, {total} AS {aliases['comparison_value']} "
                f"{source} WHERE {' AND '.join(base_scope)}")
    checked, compared = f"v.{aliases['checked_value']}", f"v.{aliases['comparison_value']}"
    if matched_only and zero:
        return (f"SELECT v.*, {message_sql} AS {aliases['violation_message']}, 'numeric' AS {aliases['issue_kind']} "
                f"FROM ({evidence}) AS v WHERE COALESCE({checked}, 0) <> {compared}")
    if not matched_only:
        params["dv_missing_rows"] = "缺值待核实：无匹配的同日明细"
    params.update(dv_missing_left=f"缺值待核实：{expression['left']} 为 NULL",
                  dv_missing_right=f"缺值待核实：同日明细的 {expression['right']} 含 NULL")
    if zero:
        missing = f"v.{aliases['related_count']} = 0"
        return (f"SELECT v.*, CASE WHEN {missing} THEN :dv_missing_rows ELSE {message_sql} END AS {aliases['violation_message']}, "
                f"CASE WHEN {missing} THEN 'missing_value' ELSE 'numeric' END AS {aliases['issue_kind']} "
                f"FROM ({evidence}) AS v WHERE {missing} OR COALESCE({checked}, 0) <> COALESCE({compared}, 0)")
    missing = f"{checked} IS NULL OR {compared} IS NULL"
    missing_rows = "" if matched_only else f"WHEN v.{aliases['related_count']} = 0 THEN :dv_missing_rows "
    return (f"SELECT v.*, CASE {missing_rows}"
            f"WHEN {checked} IS NULL THEN :dv_missing_left "
            f"WHEN {compared} IS NULL THEN :dv_missing_right ELSE {message_sql} END AS {aliases['violation_message']}, "
            f"CASE WHEN {missing} THEN 'missing_value' ELSE 'numeric' END AS {aliases['issue_kind']} "
            f"FROM ({evidence}) AS v WHERE {missing} OR {checked} <> {compared}")


def _condition_group_query(
    dialect: str, definition: dict[str, Any], spec: dict[str, Any], params: dict[str, Any],
    select: str, message_sql: str, aliases: dict[str, str],
) -> str:
    policy = definition.get("null_policy")
    handling = definition.get("null_handling") or {}
    left_mode = handling.get("left", policy)
    right_mode = handling.get("right", policy)
    predicates = []
    parts = group_formula_parts(definition, lambda name: "t." + quote_identifier(dialect, name), params, message_sql)
    for index, item in enumerate(comparison_conditions(definition), 1):
        if index in parts:
            predicates.append(parts[index].comparison)
            continue
        left = f"t.{quote_identifier(dialect, item['left'])}"
        if item["op"] in TEXT_FILTER_OPS:
            predicates.append(_keyword_predicate(dialect, left, item["op"], item["right"], params, f"keyword_{index}", skip_empty=True))
            continue
        if item["op"] in UNARY_OPS:
            keyword = "IS NULL" if item["op"] == "is_null" else "IS NOT NULL"
            predicates.append(f"{left} {keyword}")
            continue
        if left_mode == "zero":
            left = f"COALESCE({left}, 0)"
        if item.get("right_type") == "value":
            name = f"right_value_{index}"
            params[name] = item["right"]
            right = f":{name}"
        else:
            alias = "o" if item.get("right_table") == RELATED else "t"
            right = f"{alias}.{quote_identifier(dialect, item['right'])}"
            if right_mode == "zero":
                right = f"COALESCE({right}, 0)"
        predicates.append(_comparison_predicate(dialect, left, item, right, policy))
    operator = " OR " if definition["expression"]["logic"] == "any" else " AND "
    predicate = f"({operator.join(predicates)})"
    for index, item in enumerate(spec["filters"], 1):
        if item["table"] == BASE:
            select += f" AND {_filter_predicate(dialect, 't', item, params, index)}"

    def in_scope(clause: str) -> str:
        return _exists_clause(dialect, spec, params, clause) if spec["join"] else clause

    hit = in_scope(predicate)
    if parts:
        labels = []
        if definition.get("include_result_fields") is True:
            for role, field, computed in group_formula_projection(parts, definition["expression"]["conditions"]):
                value = computed or "t." + quote_identifier(dialect, field)
                labels.append(f"{value} AS {aliases.get(role, role)}")
        if labels:
            marker = f"{message_sql} AS {aliases['violation_message']}"
            select = select.replace(marker, marker + ", " + ", ".join(labels), 1)
        failures = [part.zero_denominator for part in parts.values() if part.zero_denominator]
        error = in_scope("(" + " OR ".join(failures) + ")") if failures else ""
        unknown = in_scope(f"{predicate} IS NULL") if policy == "review" else ""
        decisions = []
        if error:
            decisions.append((error, "calculation_error", CALCULATION_MESSAGE))
        if unknown:
            decisions.append((unknown if not spec["join"] else f"{unknown} AND NOT ({hit})",
                              "missing_value", "缺值待核实：比较字段为 NULL"))
        kind_sql = "'numeric'"
        msg_sql = message_sql
        if decisions:
            kind_sql = "CASE " + " ".join(f"WHEN {clause} THEN '{kind}'" for clause, kind, _ in decisions) + " ELSE 'numeric' END"
            msg_sql = "CASE " + " ".join(f"WHEN {clause} THEN '{label}'" for clause, _, label in decisions) + f" ELSE {message_sql} END"
        select = _inject_review_projection(select, message_sql, msg_sql, kind_sql, aliases)
        return select + " AND (" + " OR ".join(filter(None, [error, hit, unknown])) + ")"
    if policy == "review":
        # 只有在完整布尔组的结果尚不确定时才报缺值。多条关联记录有确定命中时优先显示违规。
        missing = in_scope(f"{predicate} IS NULL")
        params["dv_missing_group"] = "缺值待核实：比较字段为 NULL，无法确定整组是否命中"
        select = _inject_review_projection(
            select, message_sql, f"CASE WHEN {hit} THEN {message_sql} ELSE :dv_missing_group END",
            f"CASE WHEN {hit} THEN 'numeric' ELSE 'missing_value' END", aliases,
        )
        return f"{select} AND ({hit} OR {missing})"
    kind = "'numeric'" if policy == "zero" else "'comparison'"
    return f"{_inject_review_projection(select, message_sql, message_sql, kind, aliases)} AND {hit}"


def compile_rule(version: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    definition = version["definition"]
    dialect = str(definition.get("dialect") or version.get("dialect") or "mysql")
    rule_type = str(definition.get("rule_type") or "")
    table = str(definition.get("table_name") or "")
    key = str(definition.get("business_key") or "id")
    message = str(definition.get("violation_message") or "校验异常")
    # Backslashes can escape quote-doubling on MySQL. Bind such text, never embed it in SQL.
    bind_message = "\\" in message or is_condition_group(definition)
    message_sql = ":violation_message" if bind_message else "'" + message.replace("'", "''") + "'"
    if (definition.get("project_context") is not None or is_condition_group(definition)) and rule_type != "field_compare":
        # 其余类型的安全投影语义尚未核验；明确拒绝，禁止默默只出合同键。
        raise AppError("VALIDATION_ERROR")
    aliases = quoted_output_aliases(definition, dialect)
    if "project_driver" in definition:
        from .project_driver_sql import compile_project_driver
        return compile_project_driver(definition, dialect, validate_query_spec(definition), aliases)
    context_suffix = _project_select_suffix(dialect, definition, aliases) if rule_type == "field_compare" else ""
    quoted_table = quote_identifier(dialect, table)
    quoted_key = quote_identifier(dialect, key)
    date_field = quote_identifier(dialect, str(definition.get("report_date_field") or "report_date"))
    expr = definition.get("expression") or {}
    if rule_type == "field_compare" and is_arithmetic(expr):
        spec = validate_query_spec(definition)
        params = {"report_date": definition.get("report_date")}
        if bind_message:
            params["violation_message"] = message
        def column(name):
            return "t." + quote_identifier(dialect, name)
        formula = compile_formula(definition, column, params, message_sql)
        if definition.get("include_result_fields") is True:
            context_suffix += f", t.{date_field} AS {aliases['data_date']}"
            for role, field, _ in arithmetic_projection(expr):
                operand = (formula.checked if role == "checked_value" else formula.value
                           if role == "comparison_value" else column(field))
                context_suffix += f", {operand} AS {aliases.get(role, role)}"
        predicates = [f"t.{date_field} = :report_date"]
        predicates.extend(_filter_predicate(dialect, "t", item, params, index)
                          for index, item in enumerate(spec["filters"], 1) if item["table"] == BASE)
        if spec["join"]:
            predicates.append(_exists_clause(dialect, spec, params, None))
        predicates.append(formula.hit)
        return (f"SELECT t.{quoted_key} AS {aliases['business_key']}, {formula.message} AS {aliases['violation_message']}, "
                f"{formula.kind} AS {aliases['issue_kind']}{context_suffix} FROM {quoted_table} AS t WHERE "
                + " AND ".join(predicates)), params
    if rule_type == "field_compare" and definition.get("include_result_fields") is True:
        conditions = comparison_conditions(definition)
        expression = conditions[0]
        context_suffix += f", t.{date_field} AS {aliases['data_date']}"
        if not has_arithmetic(expr) and all(item.get("left") == expression.get("left") for item in conditions):
            checked_field = quote_identifier(dialect, str(expression.get("left") or ""))
            context_suffix += f", t.{checked_field} AS {aliases['checked_value']}"
        if (not is_condition_group(definition) and expression.get("op") not in UNARY_OPS and (expression.get("right_type") or "field") == "field"
                and expression.get("right_table") != RELATED):
            comparison_field = quote_identifier(dialect, str(expression.get("right") or ""))
            context_suffix += f", t.{comparison_field} AS {aliases['comparison_value']}"
    select = (
        f"SELECT t.{quoted_key} AS {aliases['business_key']}, {message_sql} AS {aliases['violation_message']}{context_suffix} "
        f"FROM {quoted_table} AS t WHERE t.{date_field} = :report_date"
    )
    params: dict[str, Any] = {"report_date": definition.get("report_date")}
    if bind_message:
        params["violation_message"] = message
    if rule_type == "field_compare":
        spec = validate_query_spec(definition)
        if is_condition_group(definition):
            return _condition_group_query(dialect, definition, spec, params, select, message_sql, aliases), params
        if (spec["join"] or {}).get("right_aggregate") == "sum":
            return _related_sum_query(dialect, definition, spec, params, message_sql, aliases), params
        expression = definition.get("expression") or {}
        left = str(expression.get("left") or "")
        op_name = str(expression.get("op") or "")
        if op_name not in _OPS and op_name not in UNARY_OPS and op_name not in TEXT_FILTER_OPS:
            raise AppError("VALIDATION_ERROR")
        # 旧版表达式只有 left/op/right，未声明 right_type 时仍按字段比较处理。
        right_type = str(expression.get("right_type") or "field")
        if right_type not in _RIGHT_TYPES:
            raise AppError("VALIDATION_ERROR")

        # 新规格：主表筛选条件（AND，字符串/数值常量全部绑定）。
        for index, item in enumerate(spec["filters"], start=1):
            if item["table"] == BASE:
                select += f" AND {_filter_predicate(dialect, 't', item, params, index)}"

        if op_name in UNARY_OPS or op_name in TEXT_FILTER_OPS:
            # 一元判空：目标为 NULL 的行必须进入违规判断，不能按 skip 提前排除。
            raw = f"t.{quote_identifier(dialect, left)}"
            if op_name in TEXT_FILTER_OPS:
                select += " AND " + _keyword_predicate(dialect, raw, op_name, expression["right"], params, "keyword", skip_empty=True)
            else:
                keyword = "IS NULL" if op_name == "is_null" else "IS NOT NULL"
                select += f" AND {raw} {keyword}"
            join = spec["join"]
            if join is not None:
                select += f" AND {_exists_clause(dialect, spec, params, None)}"
            if needs_issue_kind(definition):
                select = _inject_review_projection(select, message_sql, message_sql, "'comparison'", aliases)
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
            if not valid_comparison_literal(op_name, right_value):
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
                select += " AND " + _comparison_predicate(dialect, left_sql, expression, right_sql, policy)
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
                kind = "'numeric'" if policy == "zero" else "'comparison'"
                select = _inject_review_projection(select, message_sql, message_sql, kind, aliases)
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
            select = _inject_review_projection(select, message_sql, message_case, issue_expr, aliases)
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
        select = _inject_review_projection(select, message_sql, message_case, issue_expr, aliases)
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
        fields = [f"t.{quote_identifier(dialect, str(item))}" for item in definition["keys"]]
        keys = ", ".join(fields)
        projected = [f"{field} AS {aliases[f'unique_key_{i}']}" if definition.get("result_aliases") else field
                     for i, field in enumerate(fields[:-1])]
        projected.append(f"{fields[-1]} AS {aliases['business_key']}")
        select = (
            f"SELECT {', '.join(projected)}, {message_sql} AS {aliases['violation_message']} "
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
