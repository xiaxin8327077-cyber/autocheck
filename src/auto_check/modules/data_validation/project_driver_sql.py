"""Fixed project-first SELECT templates for new, versioned rules."""

from .compiler import _comparison_predicate, _filter_predicate, _keyword_predicate, _summed_details
from .contracts import AppError
from .formula import CALCULATION_MESSAGE, compile_formula, group_formula_parts, group_formula_projection, is_arithmetic
from .issue_query_results import compiled_projection
from .query_spec import comparison_conditions, excludes_unmatched_sum, is_condition_group, TEXT_FILTER_OPS, UNARY_OPS
from .sql_guard import quote_identifier


def _comparisons(definition, dialect, column, params, parts):
    policy = definition["null_policy"]
    handling = definition.get("null_handling") or {}
    predicates = []
    grouped = is_condition_group(definition)
    for index, item in enumerate(comparison_conditions(definition)):
        if index + 1 in parts:
            predicates.append(parts[index + 1].comparison)
            continue
        left = column("base", item["left"])
        if item["op"] in TEXT_FILTER_OPS:
            predicates.append(_keyword_predicate(dialect, left, item["op"], item["right"], params, f"keyword_{index}", skip_empty=True))
            continue
        if item["op"] in UNARY_OPS:
            predicates.append(f"{left} IS {'NOT ' if item['op'] == 'is_not_null' else ''}NULL")
            continue
        if handling.get("left", policy) == "zero":
            left = f"COALESCE({left}, 0)"
        if item.get("right_type") == "value":
            name = f"right_value_{index}" if grouped else "right_value"
            params[name] = item["right"]
            right = ":" + name
        else:
            right = column(item.get("right_table", "base"), item["right"])
            if handling.get("right", policy) == "zero":
                right = f"COALESCE({right}, 0)"
        predicates.append(_comparison_predicate(dialect, left, item, right, policy))
    logic = " OR " if definition["expression"].get("logic") == "any" else " AND "
    return "(" + logic.join(predicates) + ")"


def _sum_evidence(definition, detail_date, detail_scope, amount):
    # The outer join introduces a NULL row for an absent detail. Count only actual matches;
    # the second count distinguishes an excluded detail from a project with no detail at all.
    raw_count = f"COUNT({detail_date})"
    eligible = f"{detail_date} IS NOT NULL AND ({detail_scope})"
    count = f"COUNT(CASE WHEN {eligible} THEN 1 END)"
    if definition["null_policy"] == "zero":
        total = f"SUM(CASE WHEN {eligible} THEN COALESCE({amount}, 0) END)"
    else:
        value = f"CASE WHEN {eligible} THEN {amount} END"
        total = f"CASE WHEN {count} = COUNT({value}) THEN SUM({value}) END"
    return raw_count, count, total


def compile_project_driver(definition, dialect, spec, aliases):
    driver = definition["project_driver"]
    context = spec["project_context"]
    join = spec["join"]
    if (not isinstance(driver, dict) or set(driver) != {"version", "table_role"}
            or type(driver["version"]) is not int or driver["version"] not in (1, 2, 3)
            or driver["table_role"] not in ("base", "related") or not context
            or definition.get("rule_type") != "field_compare"):
        raise AppError("VALIDATION_ERROR")
    project_role = driver["table_role"]
    legacy = driver["version"] == 1
    matched_only = driver["version"] >= 3 or excludes_unmatched_sum(join)
    related_project = project_role == "related"
    if (related_project and (not join or context["mode"] != "lookup" or context["table_name"] != join["table_name"]
                             or context["key"] not in join["on"] or context.get("date_field") != join["report_date_field"])
            or not related_project and context["mode"] != "base"):
        raise AppError("VALIDATION_ERROR")

    def quote(name):
        return quote_identifier(dialect, name)

    def column(role, name):
        return ("p." if role == project_role else "d.") + quote(name)

    base_day = definition.get("report_date_field") or "report_date"
    day_name = join["report_date_field"] if related_project else base_day
    code_name = context["key"]["right"] if related_project else context["code_field"]
    project_table = quote(join["table_name"] if related_project else definition["table_name"])
    project_code, project_day = column(project_role, code_name), column(project_role, day_name)
    project_name = column(project_role, context["name_field"])
    params = {"report_date": definition.get("report_date"), "violation_message": definition.get("violation_message") or "校验异常"}
    filters = {"p": [], "d": []}
    for index, item in enumerate(spec["filters"], 1):
        alias = "p" if item["table"] == project_role else "d"
        filters[alias].append(_filter_predicate(dialect, alias, item, params, index))
    project_scope = " AND ".join(filters["p"]) or "1 = 1"
    detail_scope = " AND ".join(filters["d"]) or "1 = 1"
    source = f" FROM {project_table} AS p"
    period = f"{project_day} = :report_date"
    where = [period, *filters["p"]]
    if legacy:
        params.update(dv_missing_project_code="项目源数据缺少项目编号，请核实", dv_duplicate_project="同日报送项目编号重复，请核实项目源数据")
        text_type = "CHAR" if dialect == "mysql" else "TEXT"
        missing_code = f"({project_code} IS NULL OR TRIM(CAST({project_code} AS {text_type})) = '')"
        unique = (f"(SELECT COUNT(*) FROM {project_table} AS q WHERE q.{quote(day_name)} = {project_day} "
                  f"AND q.{quote(code_name)} = {project_code}) = 1")
        where = [period, f"({project_scope})", f"NOT {missing_code}", unique]
    aggregate = bool(join and join.get("right_aggregate") == "sum")
    missing_record = None
    group_clause = ""
    columns = compiled_projection(definition)
    values = {role: column("related" if other else "base", field) for role, field, other in columns if field}
    values.update(project_match_count="1")
    formula = (compile_formula(definition, lambda name: column("base", name), params, ":violation_message")
               if is_arithmetic(definition["expression"]) else None)
    if formula:
        values.update(checked_value=formula.checked, comparison_value=formula.value)
    parts = group_formula_parts(definition, lambda name: column("base", name), params, ":violation_message")
    if parts:
        for role, field, computed in group_formula_projection(parts, definition["expression"]["conditions"]):
            values[role] = computed or column("base", field)
    if join:
        detail_table = quote(definition["table_name"] if related_project else join["table_name"])
        detail_day = column("base", base_day) if related_project else column("related", join["report_date_field"])
        date_pair = {"left": base_day, "right": join["report_date_field"]}
        match = [f"{column('base', pair['left'])} = {column('related', pair['right'])}" for pair in join["on"]
                 if not matched_only or pair != date_pair]
        match.append(f"{detail_day} = {project_day}")
        if aggregate and not legacy:
            source += _summed_details(definition, join, detail_table, detail_day, filters["d"], column,
                                      matched_only=matched_only)
        else:
            join_type = "INNER JOIN" if matched_only else "LEFT JOIN"
            source += f" {join_type} {detail_table} AS d ON " + " AND ".join(match)
        if not matched_only:
            params["dv_missing_record"] = "没有对应明细记录，请核查"
        if aggregate:
            if related_project:
                raise AppError("VALIDATION_ERROR")
            right = column("related", definition["expression"]["right"])
            if legacy:
                raw_count, eligible_count, total = _sum_evidence(definition, detail_day, detail_scope, right)
                missing_record = f"{raw_count} = 0"
            else:
                eligible_count, total = "s.dv_count", "s.dv_sum"
                missing_record = "s.dv_count IS NULL"
            values.update(related_count=eligible_count if legacy or matched_only else "COALESCE(s.dv_count, 0)", comparison_value=total)
            checked = column("base", definition["expression"]["left"])
            left = f"COALESCE({checked}, 0)" if definition["null_policy"] == "zero" else checked
            predicate = f"({left} <> ({total}))"
            if legacy:
                grouping = [val for val in values.values() if val.startswith("p.")]
                group_clause = " GROUP BY " + ", ".join(dict.fromkeys([project_code, project_name, project_day, *grouping]))
        else:
            missing_record = f"{detail_day} IS NULL"
            predicate = formula.hit if formula else _comparisons(definition, dialect, column, params, parts)
    else:
        predicate = formula.hit if formula else _comparisons(definition, dialect, column, params, parts)

    kind = "'numeric'" if definition["null_policy"] in ("zero", "review") else "'comparison'"
    message = ":violation_message"
    hit = predicate
    if formula:
        kind, message = formula.kind, formula.message
    elif definition["null_policy"] == "review":
        unknown = f"({predicate}) IS NULL"
        hit = f"({predicate} OR {unknown})"
        params["dv_missing_value"] = "缺值待核实：比较字段为 NULL"
        kind = f"CASE WHEN {unknown} THEN 'missing_value' ELSE {kind} END"
        message = f"CASE WHEN {unknown} THEN :dv_missing_value ELSE {message} END"
    if parts:
        if definition["null_policy"] == "skip":
            kind = "'numeric'"
        errors = [part.zero_denominator for part in parts.values() if part.zero_denominator]
        if errors:
            error = "(" + " OR ".join(errors) + ")"
            hit = f"({hit} OR {error})"
            kind = f"CASE WHEN {error} THEN 'calculation_error' ELSE {kind} END"
            message = f"CASE WHEN {error} THEN '{CALCULATION_MESSAGE}' ELSE {message} END"
    if missing_record:
        eligible = f"{eligible_count} > 0" if aggregate else detail_scope
        if matched_only:
            if aggregate or filters["d"]:
                hit = f"(({eligible}) AND {hit})"
        else:
            hit = (f"({missing_record} OR (({eligible}) AND {hit}))" if legacy or aggregate or filters["d"]
                   else f"({missing_record} OR {hit})")
            kind = f"CASE WHEN {missing_record} THEN 'missing_record' ELSE {kind} END"
            message = f"CASE WHEN {missing_record} THEN :dv_missing_record ELSE {message} END"
    values.update(issue_kind=kind, violation_message=message)

    def projection(items):
        return ", ".join(f"{items.get(role, 'NULL')} AS {aliases.get(role, role)}" for role, _, _ in columns)

    normal = "SELECT " + projection(values) + source + " WHERE " + " AND ".join(where)
    normal += group_clause + " HAVING " + hit if group_clause else " AND " + hit
    if not legacy:
        return normal, params

    # Return one identifiable source issue per unusable project key, irrespective of detail count.
    source_issues = {"project_code": project_code, "data_date": project_day, "project_match_count": "COUNT(*)",
                     "issue_kind": "'comparison'", "violation_message": f"CASE WHEN {missing_code} "
                     "THEN :dv_missing_project_code ELSE :dv_duplicate_project END"}
    if not related_project and definition["business_key"] == code_name:
        source_issues["business_key"] = project_code
    invalid = (f"SELECT {projection(source_issues)} FROM {project_table} AS p WHERE {period} "
               f"GROUP BY {project_day}, {project_code} HAVING ({missing_code} OR COUNT(*) > 1) "
               f"AND MAX(CASE WHEN {project_scope} THEN 1 ELSE 0 END) = 1")
    return normal + " UNION ALL " + invalid, params
