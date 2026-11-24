"""Use the documented original of a directly copied metric when the request is independent of detail rows."""
from copy import deepcopy
from decimal import Decimal
import re

from .document_evidence import _business_aliases, referenced_fields
from .documented_choices import _scope_join
from .parallel_checks import parse_number_comparison
from .project_driver import _find_entity
from .query_grounding import _FILTER_OPERATORS, resolve_report_date
from .query_spec import COMPARISON_OPS, UNARY_OPS, valid_comparison_literal
from .semantic_grounding import without_period_join_key


def _only_origin_lookup(join, source, source_fields, detail, detail_fields):
    if (not isinstance(join, dict) or join.get("table_name") != source["table_name"] or
            join.keys() - {"table_name", "on", "report_date_field", "relationship_confirmed", "unmatched_policy", "right_aggregate"} or
            join.get("right_aggregate") or join.get("unmatched_policy") not in (None, "", "exclude", "unresolved")):
        return False
    expected = _scope_join(source, source_fields, detail, detail_fields)
    if not expected or join.get("report_date_field", expected["report_date_field"]) != expected["report_date_field"]:
        return False
    keyed = without_period_join_key({**join, "report_date_field": expected["report_date_field"]}, detail_fields, source_fields)
    keys = keyed.get("on")
    return (isinstance(keys, list) and len(keys) == len(expected["on"]) and
            all(pair in keys for pair in expected["on"]))


def prefer_document_origin(analysis, selection, plan):
    """Return a new draft only when its complete check belongs to the original metric's table."""
    if not isinstance(plan, dict) or plan.get("rule_type") != "field_compare" or analysis.index is None:
        return plan
    expr, intent = plan.get("expression"), plan.get("semantic_intent")
    if not isinstance(expr, dict) or not isinstance(intent, dict) or not isinstance(expr.get("left"), str):
        return plan
    name, op = expr["left"], expr.get("op")
    if not isinstance(op, str) or expr.get("left_type", "field") != "field" or expr.get("right_table", "base") != "base":
        return plan
    if op in UNARY_OPS:
        if expr.keys() - {"left", "left_type", "op"}:
            return plan
    elif (op not in COMPARISON_OPS or expr.get("right_type") != "value"
          or not valid_comparison_literal(op, expr.get("right"))
          or expr.keys() - {"left", "left_type", "op", "right", "right_type", "right_table"}):
        return plan
    metrics = intent.get("metrics")
    if (not isinstance(metrics, list) or len(metrics) != 1 or not isinstance(metrics[0], dict)
            or metrics[0].get("side") != "left" or metrics[0].get("fields") != [name]):
        return plan
    category = plan.get("report_category", selection.get("report_category"))
    try:
        detail = analysis.resolve(plan.get("target", selection.get("target")), category)
        origin = analysis.index.authoritative_metric_origin(detail, name)
        if not origin:
            return plan
        table, column = origin
        source = analysis.resolve({"table": table}, category)
    except ValueError:
        return plan
    source_fields, detail_fields = analysis.fields[source["id"]], analysis.fields[detail["id"]]
    related = plan.get("related_target", selection.get("related_target"))
    join = plan.get("join")
    if related is not None and (not isinstance(related, dict) or related.get("table") != table or not join):
        return plan
    if join is not None and not _only_origin_lookup(join, source, source_fields, detail, detail_fields):
        return plan
    scopes, filters = intent.get("scopes"), plan.get("filters", [])
    if not isinstance(scopes, list) or not isinstance(filters, list):
        return plan
    names = {field["field_name"] for field in source_fields}
    if any(not join or not isinstance(row, dict) or row.get("table") != "related"
           for row in [*scopes, *filters]):
        return plan
    if (any(not isinstance(row.get("field"), str) or row["field"] not in names for row in filters) or
            any(not isinstance(row.get("fields"), list) or not row["fields"]
                or not all(isinstance(n, str) and n in names for n in row["fields"]) for row in scopes)):
        return plan
    if plan.get("report_date_field") and plan["report_date_field"] != resolve_report_date(detail_fields)[0]:
        return plan
    result = deepcopy(plan)
    result.update(target={"table": table}, related_target=None)
    result["expression"]["left"] = column
    metric = result["semantic_intent"]["metrics"][0]
    metric["fields"] = [column]
    if metric.get("recommended") == name:
        metric["recommended"] = column
    if isinstance(metric.get("rule_names"), dict) and name in metric["rule_names"]:
        metric["rule_names"] = {column: metric["rule_names"][name]}
    for row in [*result.get("filters", []), *result["semantic_intent"]["scopes"]]:
        row["table"] = "base"
    for key in ("join", "business_key", "project_driver", "report_date_field"):
        result.pop(key, None)
    return result


def _fully_named_project_check(request, plan, fields):
    """Prove that the entire request only names its project scope, metric and numeric comparison."""
    expr = plan.get("expression")
    intent = plan.get("semantic_intent")
    if (not isinstance(expr, dict) or not isinstance(intent, dict) or expr.get("right_type") != "value"
            or type(expr.get("right")) not in (int, float) or not isinstance(expr.get("op"), str) or expr["op"] not in _FILTER_OPERATORS):
        return False
    text = re.sub(r"\s+", "", request).rstrip("。！？.!?")
    scopes = intent.get("scopes")
    if not isinstance(scopes, list):
        return False
    if scopes:
        if len(scopes) != 1 or not isinstance(scopes[0], dict):
            return False
        scope = scopes[0].get("category")
        if (not isinstance(scope, str) or not scope or not text.startswith(scope)
                or re.search(r"有|无|存在|发生|缺|关联|匹配|对应|至少|仅|且|并|包含|相关|带有|[，,；;]", scope)):
            return False
        text = re.sub(r"^[，,：:]?(?:但是|但|且|的)?", "", text[len(scope):])
    parsed = parse_number_comparison(text)
    if parsed and len(parsed[0]) == 1 and parsed[1:] == (expr["op"], expr["right"]):
        term = parsed[0][0]
    else:
        op = _FILTER_OPERATORS[expr["op"]][1]
        match = re.fullmatch(r"(.+?)(?:" + op + r")(-?\d+(?:\.\d+)?)", text)
        if not match or Decimal(match[2]) != Decimal(str(expr["right"])):
            return False
        term = match[1]
    field = next((f for f in fields if f["field_name"] == expr.get("left")), {})
    return len(term) >= 2 and any(term.lower() in label for label in (
        str(field.get("field_cn") or "").lower(), str(field.get("field_name") or "").lower(), *_business_aliases(field)))


def drop_unused_project_lookup(analysis, selection, plan):
    """Discard a detail join introduced only after the model inspected another metric's grain."""
    first = getattr(analysis, "initial_proposal", None)
    if not isinstance(first, dict) or not isinstance(plan, dict):
        return plan
    join = plan.get("join")
    if (not isinstance(join, dict) or first.get("plans") or first.get("join") or first.get("related_target")
            or first.get("rule_type") != "field_compare" or plan.get("rule_type") != "field_compare"
            or not isinstance(first.get("project_driver"), dict) or first["project_driver"].get("table_role") != "base"
            or first.get("expression") != plan.get("expression") or first.get("filters", []) != plan.get("filters", [])
            or join.get("unmatched_policy") not in (None, "exclude", "unresolved") or join.get("right_aggregate")):
        return plan
    if referenced_fields({**plan, "join": None})["related"]:
        return plan
    # The review can correct dictionary values, but a new scope is not an unused lookup.
    def scope_owners(draft):
        intent = draft.get("semantic_intent")
        rows = intent.get("scopes") if isinstance(intent, dict) else None
        if not isinstance(rows, list) or any(not isinstance(s, dict) for s in rows):
            return None
        return [(s.get("table", "base"), s.get("category"), s.get("fields")) for s in rows]
    if scope_owners(first) != scope_owners(plan):
        return plan
    target = first.get("target", selection.get("target"))
    related = plan.get("related_target", selection.get("related_target")) or {"table": join.get("table_name")}
    if (plan.get("target", selection.get("target")) != target or not isinstance(related, dict)
            or related.get("table") != join.get("table_name")):
        return plan
    category = plan.get("report_category", selection.get("report_category"))
    try:
        project, detail = analysis.resolve(target, category), analysis.resolve(related, category)
    except ValueError:
        return plan
    if not any(c.get("table_id") == detail["id"] for g in analysis.competing_evidence
               if g.get("kind") == "metrics" for c in g["candidates"]):
        return plan
    project_fields, detail_fields = analysis.fields[project["id"]], analysis.fields[detail["id"]]
    names = [detail["table_name"], str(detail.get("table_name_cn") or "").removesuffix("表")]
    if any(name and name.lower() in analysis.request.lower() for name in names):
        return plan
    tables = [t for t in analysis.tables if t.get("data_source_name") == project.get("data_source_name")]
    entity, is_project, issues = _find_entity(project, tables, analysis.fields, plan)
    if not entity or not is_project or issues or not _fully_named_project_check(analysis.request, plan, project_fields):
        return plan
    pairs = join.get("on")
    if not isinstance(pairs, list) or not all(isinstance(p, dict) and p.keys() == {"left", "right"} for p in pairs):
        return plan
    detail_date, _ = resolve_report_date(detail_fields)
    project_date, _ = resolve_report_date(project_fields)
    if not detail_date or not project_date or join.get("report_date_field", detail_date) != detail_date:
        return plan
    reverse = {**join, "table_name": project["table_name"], "report_date_field": project_date,
               "on": [{"left": p["right"], "right": p["left"]} for p in pairs]}
    if not _only_origin_lookup(reverse, project, project_fields, detail, detail_fields):
        return plan
    result = {**plan, "related_target": None}
    result.pop("join")
    return result
