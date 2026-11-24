"""Carry documented filters from confirmed selections into a period supplement."""
from copy import deepcopy
import json

from .analysis_memory import digest
from .contracts import AppError
from .document_evidence import referenced_fields
from .documented_choices import ScopeEvidenceRequired
from .query_grounding import dictionary_options
from .semantic_grounding import _explicit_filter, _Unbound
from .query_spec import is_finite_number, type_family


def attach_period_applicability(items, business_scope, source_id, tables, fields_by_table):
    """Publish only configured, documented period filters with an actionable suggestion."""
    prefix = "PERIOD_APPLICABILITY "
    entries = [line.strip()[len(prefix):] for line in business_scope.splitlines() if line.strip().startswith(prefix)]
    if not entries:
        return items
    for item in items:
        refs = item.get("references") or []
        if item.get("category") != "period" or not item.get("adoption") or len(refs) != 1:
            continue
        table, field = refs[0]["table_name"], refs[0]["field_name"]
        try:
            applicable, dictionaries = [], {}
            for entry in entries:
                fact = json.loads(entry)
                if not isinstance(fact, dict) or not all(isinstance(fact.get(k), str) and fact[k]
                                                        for k in ("source_id", "table", "field")):
                    raise ValueError
                if (fact["source_id"], fact["table"], fact["field"]) != (source_id, table, field):
                    continue
                rows = [row for row in tables if row["table_name"] == table]
                if len(rows) != 1 or not isinstance(fact.get("filters"), list) or not fact["filters"]:
                    raise ValueError
                documented = {f["field_name"]: f for f in fields_by_table[rows[0]["id"]]}
                if field not in documented:
                    raise ValueError
                for raw in fact["filters"]:
                    if not isinstance(raw, dict) or set(raw) - {"field", "op", "value"}:
                        raise ValueError
                    bound = {**_explicit_filter(raw, {"base": documented}), "table": table}
                    options = dictionary_options(documented[bound["field"]])
                    if options:
                        dictionaries[bound["field"]] = options
                    if bound not in applicable:
                        applicable.append(bound)
            if applicable:
                item["applicability_filters"] = applicable
                if dictionaries:
                    item["applicability_dictionary"] = dictionaries
        except (ValueError, TypeError, _Unbound):
            item.pop("adoption", None)
            item["support_level"] = "needs_confirmation"
            item.setdefault("limitations", []).append("请核实业务口径设置中期间适用范围的 JSON、文档字段和字典取值。")
    return items


def period_check(definition, columns, target_field):
    """Rebind a scalar unary or numeric-constant check to one documented period measure."""
    if definition.get("join"):
        return None
    expression = deepcopy(definition.get("expression") or {})
    terms = expression.get("conditions", [expression])
    types = {c.get("column_name"): type_family(c.get("data_type")) for c in columns}
    if not terms or not target_field or not types.get(target_field):
        return None
    source = terms[0].get("left")
    if not isinstance(source, str) or types.get(source) != types[target_field]:
        return None
    for term in terms:
        if term.get("left") != source or term.get("left_type", "field") != "field":
            return None
        if term.get("op") not in ("is_null", "is_not_null") and not (
                term.get("op") in ("gt", "gte", "lt", "lte", "eq", "neq") and types[target_field] == "number"
                and term.get("right_type") == "value" and is_finite_number(term.get("right"))):
            return None
        term["left"] = target_field
    return {"expression": expression, **{key: deepcopy(definition[key]) for key in ("null_policy", "null_handling", "equality_policy")
                                        if key in definition}}


def apply_period_check(draft, check, field, label):
    draft.pop("null_handling", None)
    draft.update(deepcopy(check))
    terms = draft["expression"].get("conditions", [draft["expression"]])
    grouped = "conditions" in draft["expression"]
    draft["semantic_intent"]["metrics"] = [
        {"side": "left", "term": label, "fields": [field], **({"condition_index": i} if grouped else {})}
        for i in range(len(terms))]
    operators = {"is_null": "为空", "is_not_null": "非空", "gt": "大于", "lt": "小于", "gte": "大于等于",
                 "lte": "小于等于", "eq": "等于", "neq": "不等于"}
    joiner = "或" if draft["expression"].get("logic") == "any" else "且"
    summary = label + joiner.join(operators[t["op"]] + str(t.get("right", "")) for t in terms)
    draft.update(rule_name=summary, violation_message=summary)


def preserve_period_policy(definition, columns):
    """Apply the selected parent policy after document defaults have been inferred."""
    intent = definition.get("semantic_intent") or {}
    check = intent.get("inherited_period_check")
    if check is None:
        return definition
    expression = definition["expression"]
    terms = expression.get("conditions", [expression])
    if (not isinstance(check, dict) or not terms or check.get("expression") != expression
            or intent.get("expected_expression") != expression or check.get("null_policy") != intent.get("expected_null_policy")
            or period_check(check, columns, terms[0].get("left")) != check):
        raise AppError("VALIDATION_ERROR")
    result = {**definition, **deepcopy(check)}
    if "null_handling" not in check:
        result.pop("null_handling", None)
    if definition.get("null_evidence"):
        result["null_evidence"] = [{"side": "left", "field": terms[0]["left"], "source": "按原条件采纳，沿用已确认主方案的空值处理。"}]
    return result


def verified_period_scope(service, user, payload):
    reference = payload.get("adoption_context")
    if reference is None:
        return None
    if not isinstance(reference, dict) or payload.get("analysis_protocol") != 2:
        raise AppError("VALIDATION_ERROR")
    parent_id = reference.get("parent_analysis_id")
    if not isinstance(parent_id, str):
        raise AppError("ANALYSIS_CONTEXT_CHANGED")
    previous = service.analyses.completed_result(user, parent_id)
    if (not previous or previous.get("source_id") != payload.get("source_id")
            or previous.get("analysis_context") != reference.get("parent_context")):
        raise AppError("ANALYSIS_CONTEXT_CHANGED")
    suggestion = next((s for s in previous.get("ai_suggestions") or [] if s.get("id") == reference.get("suggestion_id")), {})
    refs = suggestion.get("references") or []
    inherit_check = reference.get("inherit_check", False)
    if type(inherit_check) is not bool or (inherit_check and len(refs) != 1):
        raise AppError("VALIDATION_ERROR")
    tables = {r["table_name"] for r in refs}
    mode = reference.get("mode")
    receipts = reference.get("parents")
    if mode not in (None, "suggestion_only") or mode == "suggestion_only" and (receipts is not None or inherit_check):
        raise AppError("VALIDATION_ERROR")
    if (suggestion.get("category") != "period" or not suggestion.get("adoption") or len(tables) != 1
            or (mode != "suggestion_only" and (not isinstance(receipts, list) or not receipts))):
        raise AppError("ANALYSIS_CONTEXT_CHANGED")
    table = tables.pop()
    options = [o["candidate"] for o in previous.get("candidate_options") or []] or [previous]
    parent_input = {"source_id": previous["source_id"], "model_id": payload.get("model_id"),
                    "request_text": previous["analysis_request_text"], "analysis_protocol": 2,
                    "reasoning_enabled": previous["reasoning_enabled"], "clarification_answers": previous["clarification_answers"]}
    if previous.get("include_suggestions") is False:
        parent_input["include_suggestions"] = False
    service._check_preview_context(user, parent_input, previous["analysis_context"], period_scope=previous.get("period_scope"))
    if mode == "suggestion_only":
        facts = suggestion.get("applicability_filters")
        if not facts:
            raise AppError("ANALYSIS_CONTEXT_CHANGED")
        return {"table": table, "fields": sorted({r["field_name"] for r in refs}), "groups": [[]],
                "applicability_filters": deepcopy(facts)}
    groups, checks = {}, {}
    for receipt in receipts:
        definition = receipt.get("definition") if isinstance(receipt, dict) else None
        if (not isinstance(definition, dict) or definition.get("table_name") != table
                or definition.get("source_id") != previous["source_id"] or not definition.get("semantic_intent")
                or not any(c.get("table_name") == table and c.get("report_category") == definition.get("report_category")
                           and c.get("semantic_intent") == definition["semantic_intent"] for c in options)):
            raise AppError("ANALYSIS_CONTEXT_CHANGED")
        preview = service.preview_candidate(user, {"definition": definition}, return_questions=True)
        if not preview.get("sql_preview") or preview.get("questions") or preview["content_sha256"] != receipt.get("hash"):
            raise AppError("ANALYSIS_CONTEXT_CHANGED")
        validated = preview["definition"]
        if validated.get("join"):
            raise AppError("VALIDATION_ERROR")
        filters = []
        for f in validated.get("filters") or []:
            if f.get("confirmed") is not True:
                raise AppError("ANALYSIS_CONTEXT_CHANGED")
            owner = validated["join"]["table_name"] if f.get("table") == "related" else table
            filters.append({**f, "table": owner})
        filters.sort(key=digest)
        groups[digest(filters)] = filters
        if inherit_check:
            check = period_check(validated, preview["columns"], refs[0]["field_name"])
            if check is None:
                raise AppError("VALIDATION_ERROR")
            pair = {"filters": filters, "check": check}
            checks[digest(pair)] = pair
    return {"table": table, "fields": sorted({r["field_name"] for r in refs}), "groups": [groups[k] for k in sorted(groups)],
            **({"applicability_filters": deepcopy(suggestion["applicability_filters"])} if suggestion.get("applicability_filters") else {}),
            **({"checks": [checks[k] for k in sorted(checks)]} if checks else {})}


def bind_period_filters(draft, table, related, scope, group):
    used = referenced_fields({"expression": draft.get("expression")})
    if table != scope["table"] or not used["base"].intersection(scope["fields"]):
        raise ScopeEvidenceRequired("期间建议的检查指标与已采纳的文档字段不一致，请核实适用范围。")
    filters = draft.setdefault("filters", [])
    if not isinstance(filters, list):
        raise ScopeEvidenceRequired("期间建议的筛选条件格式需要核实。")
    declared = {(s.get("table", "base"), field) for s in draft.get("semantic_intent", {}).get("scopes", [])
                for field in s.get("fields", [])}
    group = list(group)
    for required in scope.get("applicability_filters", []):
        same_field = [f for f in group if (f["table"], f["field"]) == (required["table"], required["field"])]
        if same_field and not any(_same_filter(f, required) for f in same_field):
            raise ScopeEvidenceRequired(f"期间指标与已选方案对字段 {required['field']} 的范围不同，请明确适用范围。")
        if required not in group:
            group.append(required)
    applied = []
    for item in group:
        if item["table"] not in (table, related):
            raise ScopeEvidenceRequired("期间建议缺少原适用范围引用的关联表，请核实关联范围。")
        target = {**deepcopy(item), "table": "base" if item["table"] == table else "related"}
        applied.append(target)
        present = [f for f in filters if isinstance(f, dict) and f.get("table", "base") == target["table"]
                   and f.get("field") == target["field"]]
        if (target["table"], target["field"]) in declared:
            # Ground the model's dictionary scope first, then compare the exact bound values.
            continue
        selected_field = [f for f in group if f["field"] == item["field"] and f["table"] == item["table"]]
        if any(not any(_same_filter(f, existing) for f in selected_field) for existing in present):
            raise ScopeEvidenceRequired(f"期间建议与已选方案对字段 {target['field']} 的范围不同，请明确采用哪个范围。")
        if not any(_same_filter(target, f) for f in present):
            filters.append(target)
    return applied


def verify_bound_period_filters(candidate, applied, groups):
    for expected in applied:
        if not any(f.get("table", "base") == expected["table"] and f.get("field") == expected["field"]
                   and _same_filter(expected, f) for f in candidate.get("filters") or []):
            raise ScopeEvidenceRequired(f"期间建议与已选方案对字段 {expected['field']} 的范围不同，请核实。")
    selected = {(f["table"], f["field"]) for f in applied}
    for other_group in groups:
        for other in other_group:
            if other["table"] not in (candidate["table_name"], (candidate.get("join") or {}).get("table_name")):
                continue
            role = "base" if other["table"] == candidate["table_name"] else "related"
            if (role, other["field"]) in selected:
                continue
            if any(f.get("table", "base") == role and f["field"] == other["field"] and _same_filter(other, f)
                   for f in candidate.get("filters") or []):
                raise ScopeEvidenceRequired(f"期间建议同时使用了另一个已选范围的字段 {other['field']}，请分别确认各方案的适用范围。")


def _same_filter(left, right):
    if left["op"] in ("eq", "in") and right.get("op") in ("eq", "in"):
        def members(f):
            values = f["value"] if f["op"] == "in" else [f["value"]]
            return sorted(digest(v) for v in values) if isinstance(values, list) else None
        return members(left) == members(right)
    return left["op"] == right.get("op") and left.get("value") == right.get("value")
