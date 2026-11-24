"""Keep a grounded, adoptable period check separate from the main request's metric choices."""
from copy import deepcopy
import re

from .ai_suggestions import MAX_SUGGESTIONS, build_ai_suggestions
from .document_evidence import _business_aliases, referenced_fields


def _owners(analysis, selection, plan):
    category = plan.get("report_category", selection.get("report_category"))
    target = plan.get("target", selection.get("target"))
    related = plan.get("related_target", selection.get("related_target") if target == selection.get("target") else None)
    return {"base": analysis.resolve(target, category), "related": analysis.resolve(related, category) if related else None}


def _named_by_request(analysis, owner, field):
    name = field["field_name"]
    if re.search(r"(?<![a-z0-9_])" + re.escape(name.lower()) + r"(?![a-z0-9_])", analysis.request.lower()):
        return True
    if analysis.index and (owner["id"], name) in analysis.index.named_metric_choices():
        return True
    # A shortened but distinctive ending of a documented label also names a specific metric.
    def labels(row):
        return [str(row.get("field_cn") or "").lower(), *_business_aliases(row)]
    other = [label for row in analysis.fields[owner["id"]] if row["field_name"] != name for label in labels(row)]
    request = analysis.request.lower()
    return any(label[i:] in request and not any(label[i:] in peer for peer in other)
               for label in labels(field) for i in range(len(label) - 1))


def deferred_period_fields(analysis, selection, raw, owner_choices=()):
    if not isinstance(raw, dict):
        return set()
    plans = raw.get("plans", [raw])
    if not isinstance(plans, list) or not plans or any(not isinstance(p, dict) for p in plans):
        return set()
    suggestions = list(analysis.model_suggestions)
    for block in ([raw, *plans] if "plans" in raw else [raw]):
        if isinstance(block.get("ai_suggestions"), list):
            suggestions.extend(block["ai_suggestions"])
    if not any(isinstance(s, dict) and s.get("category") == "period" for s in suggestions):
        return set()
    candidates = [{"report_category": p.get("report_category", selection.get("report_category", ""))} for p in plans]
    validated = build_ai_suggestions(
        suggestions, tables=analysis.tables, fields_by_table=analysis.fields, candidates=candidates,
        model_only=True, limit=MAX_SUGGESTIONS,
        select_category_tables=lambda tables, codes: analysis.service._category_tables(tables, codes, analysis.categories),
    )
    single = {(s["references"][0]["table_name"], s["references"][0]["field_name"]) for s in validated
              if s["category"] == "period" and s.get("adoption") and len(s["references"]) == 1}
    if not single:
        return set()
    protected = {(c.get("table_id"), c.get("field")) for c in analysis.confirmed_checks}
    owners = {}
    for plan in plans:
        try:
            roles = _owners(analysis, selection, plan)
        except ValueError:
            return set()
        intent = plan.get("semantic_intent")
        if not isinstance(intent, dict) or not isinstance(intent.get("metrics"), list):
            return set()
        # Option lists are not actual uses. Everything else, including formula leaves, keeps its role.
        used = referenced_fields({**plan, "semantic_intent": {**intent, "metrics": []}})
        for role, table in roles.items():
            if table:
                owners[table["id"]] = table
                protected.update((table["id"], name) for name in used[role])
    for choice in owner_choices:
        if not isinstance(choice, dict):
            continue
        binding = choice.get("binding") or {}
        if not isinstance(binding, dict):
            continue
        selected = choice.get("selection")
        name = selected.get("field") if isinstance(selected, dict) else selected
        if isinstance(name, str):
            protected.update((i, name) for i, t in owners.items() if not binding.get("owner") or binding["owner"] == t["table_name"])
    return {(i, f["field_name"]) for i, table in owners.items() for f in analysis.fields[i]
            if (table["table_name"], f["field_name"]) in single and (i, f["field_name"]) not in protected
            and not _named_by_request(analysis, table, f)}


def defer_period_metric_choices(analysis, selection, raw, owner_choices=()):
    deferred = deferred_period_fields(analysis, selection, raw, owner_choices)
    if not deferred:
        return raw
    result = deepcopy(raw)
    changed = False
    for plan in result.get("plans", [result]):
        roles = _owners(analysis, selection, plan)
        expr = plan.get("expression") or {}
        rows = expr.get("conditions", [expr]) if isinstance(expr, dict) else []
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            continue
        for metric in plan["semantic_intent"].get("metrics", []):
            fields = metric.get("fields") if isinstance(metric, dict) else None
            if not isinstance(fields, list) or len(fields) < 2 or any(not isinstance(n, str) for n in fields):
                continue
            indices = [metric["condition_index"]] if "condition_index" in metric else range(len(rows))
            if any(type(i) is not int or not 0 <= i < len(rows) for i in indices):
                continue
            if metric.get("side") not in ("left", "right"):
                continue
            names = [rows[i].get("right_table", "base") if metric["side"] == "right" else "base" for i in indices]
            if not names or any(n not in ("base", "related") or n != names[0] for n in names):
                continue
            owner = roles[names[0]]
            if not owner:
                continue
            kept = [n for n in fields if (owner["id"], n) not in deferred]
            if not kept or kept == fields:
                continue
            metric["fields"] = kept
            if metric.get("recommended") not in kept:
                metric.pop("recommended", None)
            if isinstance(metric.get("rule_names"), dict):
                metric["rule_names"] = {n: v for n, v in metric["rule_names"].items() if n in kept}
            changed = True
    return result if changed else raw
