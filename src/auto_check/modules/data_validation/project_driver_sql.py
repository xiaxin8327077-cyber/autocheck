"""Fixed project-first SELECT templates for new, versioned rules."""

from .compiler import _filter_predicate, _OPS
from .contracts import AppError
from .issue_query_results import compiled_projection
from .query_spec import comparison_conditions, is_condition_group, UNARY_OPS
from .sql_guard import quote_identifier


def _comparisons(definition, column, params):
    policy = definition["null_policy"]
    handling = definition.get("null_handling") or {}
    predicates = []
    grouped = is_condition_group(definition)
    for index, item in enumerate(comparison_conditions(definition)):
        left = column("base", item["left"])
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
        predicates.append(f"{left} {_OPS[item['op']]} {right}")
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


def _summed_details(definition, join, detail_table, detail_day, filters, column):
    # Aggregate actual details before matching projects, so repeated project rows
    # cannot multiply an otherwise identical detail sum.
    keys = [column("related", pair["right"]) for pair in join["on"]]
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
    match = [f"{column('base', pair['left'])} = s.dv_key_{i}" for i, pair in enumerate(join["on"])]
    return (" LEFT JOIN (SELECT " + ", ".join(selected) + f" FROM {detail_table} AS d WHERE {detail_day} = :report_date"
            + " GROUP BY " + ", ".join(dict.fromkeys(keys)) + ") AS s ON " + " AND ".join(match))


def compile_project_driver(definition, dialect, spec, aliases):
    driver = definition["project_driver"]
    context = spec["project_context"]
    join = spec["join"]
    if (not isinstance(driver, dict) or set(driver) != {"version", "table_role"}
            or type(driver["version"]) is not int or driver["version"] not in (1, 2)
            or driver["table_role"] not in ("base", "related") or not context
            or definition.get("rule_type") != "field_compare"):
        raise AppError("VALIDATION_ERROR")
    project_role = driver["table_role"]
    legacy = driver["version"] == 1
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
    if join:
        detail_table = quote(definition["table_name"] if related_project else join["table_name"])
        detail_day = column("base", base_day) if related_project else column("related", join["report_date_field"])
        match = [f"{column('base', pair['left'])} = {column('related', pair['right'])}" for pair in join["on"]]
        match.append(f"{detail_day} = {project_day}")
        if aggregate and not legacy:
            source += _summed_details(definition, join, detail_table, detail_day, filters["d"], column)
        else:
            source += f" LEFT JOIN {detail_table} AS d ON " + " AND ".join(match)
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
            values.update(related_count=eligible_count if legacy else "COALESCE(s.dv_count, 0)", comparison_value=total)
            checked = column("base", definition["expression"]["left"])
            left = f"COALESCE({checked}, 0)" if definition["null_policy"] == "zero" else checked
            predicate = f"({left} <> ({total}))"
            if legacy:
                grouping = [val for val in values.values() if val.startswith("p.")]
                group_clause = " GROUP BY " + ", ".join(dict.fromkeys([project_code, project_name, project_day, *grouping]))
        else:
            missing_record = f"{detail_day} IS NULL"
            predicate = _comparisons(definition, column, params)
    else:
        predicate = _comparisons(definition, column, params)

    kind = "'numeric'" if definition["null_policy"] in ("zero", "review") else "'comparison'"
    message = ":violation_message"
    hit = predicate
    if definition["null_policy"] == "review":
        unknown = f"({predicate}) IS NULL"
        hit = f"({predicate} OR {unknown})"
        params["dv_missing_value"] = "缺值待核实：比较字段为 NULL"
        kind = f"CASE WHEN {unknown} THEN 'missing_value' ELSE {kind} END"
        message = f"CASE WHEN {unknown} THEN :dv_missing_value ELSE {message} END"
    if missing_record:
        eligible = f"{eligible_count} > 0" if aggregate else detail_scope
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
