"""Carry verified choices from the selected plans into a supplement."""
from copy import deepcopy
import json

from .analysis_memory import digest
from .business_display import field_label, table_label
from .contracts import AppError
from .document_evidence import referenced_fields
from .documented_choices import ScopeEvidenceRequired
from .query_grounding import dictionary_options
from .semantic_grounding import _code_key, _document_codes, _explicit_filter, _Unbound
from .query_spec import is_finite_number, type_family


def attach_period_applicability(items, business_scope, source_id, tables, fields_by_table):
    """Publish only configured, documented period filters with an actionable suggestion."""
    prefix = "PERIOD_APPLICABILITY "
    entries = [line.strip()[len(prefix):] for line in business_scope.splitlines() if line.strip().startswith(prefix)]
    if not entries:
        return items
    for item in items:
        refs = item.get("references") or []
        if item.get("category") != "period" or not item.get("adoption") or not refs:
            continue
        referenced = {(ref["table_name"], ref["field_name"]) for ref in refs}
        try:
            matched = {}
            for entry in entries:
                fact = json.loads(entry)
                if not isinstance(fact, dict) or not all(isinstance(fact.get(k), str) and fact[k]
                                                        for k in ("source_id", "table", "field")):
                    raise ValueError
                table, field = fact["table"], fact["field"]
                if fact["source_id"] != source_id or (table, field) not in referenced:
                    continue
                rows = [row for row in tables if row["table_name"] == table]
                if len(rows) != 1 or not isinstance(fact.get("filters"), list) or not fact["filters"]:
                    raise ValueError
                documented = {f["field_name"]: f for f in fields_by_table[rows[0]["id"]]}
                if field not in documented:
                    raise ValueError
                applicable, dictionaries = matched.setdefault((table, field), ([], {}))
                for raw in fact["filters"]:
                    if not isinstance(raw, dict) or set(raw) - {"field", "op", "value"}:
                        raise ValueError
                    bound = {**_explicit_filter(raw, {"base": documented}), "table": table}
                    options = dictionary_options(documented[bound["field"]])
                    if options:
                        dictionaries[bound["field"]] = options
                    if bound not in applicable:
                        applicable.append(bound)
            if matched and len(referenced) == 1:
                applicable, dictionaries = next(iter(matched.values()))
                item["applicability_filters"] = applicable
                if dictionaries:
                    item["applicability_dictionary"] = dictionaries
            elif matched:
                item["applicability_by_metric"] = [
                    {"table": table, "field": field, "filters": matched[table, field][0]}
                    for table, field in sorted(matched)]
        except (ValueError, TypeError, _Unbound):
            item.pop("adoption", None)
            item["support_level"] = "needs_confirmation"
            item.setdefault("limitations", []).append("请核实业务口径设置中期间适用范围的 JSON、文档字段和字典取值。")
    return items


def period_check(definition, columns, target_field):
    """Rebind a scalar unary or numeric-constant check to one documented period measure."""
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
        result["null_evidence"] = [{"side": "left", "field": terms[0]["left"], "source": "沿用已确认主方案的空值处理。"}]
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
    selected = mode == "inherit_selected"
    if (mode not in (None, "suggestion_only", "inherit_selected")
            or mode == "suggestion_only" and (receipts is not None or inherit_check)
            or selected and "inherit_check" in reference):
        raise AppError("VALIDATION_ERROR")
    if (not suggestion.get("adoption") or not tables
            or not selected and (suggestion.get("category") != "period" or len(tables) != 1)
            or (mode != "suggestion_only" and (not isinstance(receipts, list) or not receipts))):
        raise AppError("ANALYSIS_CONTEXT_CHANGED")
    table = refs[0]["table_name"]
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
    groups, checks, variants = {}, {}, {}
    for receipt in receipts:
        definition = receipt.get("definition") if isinstance(receipt, dict) else None
        if (not isinstance(definition, dict) or not selected and definition.get("table_name") != table
                or definition.get("source_id") != previous["source_id"] or not definition.get("semantic_intent")
                or not any(c.get("table_name") == definition.get("table_name") and c.get("report_category") == definition.get("report_category")
                           and c.get("semantic_intent") == definition["semantic_intent"] for c in options)):
            raise AppError("ANALYSIS_CONTEXT_CHANGED")
        preview = service.preview_candidate(user, {"definition": definition}, return_questions=True)
        if not preview.get("sql_preview") or preview.get("questions") or preview["content_sha256"] != receipt.get("hash"):
            raise AppError("ANALYSIS_CONTEXT_CHANGED")
        validated = preview["definition"]
        join = validated.get("join") or {}
        parent_table = validated["table_name"]
        if selected and not tables.intersection((parent_table, join.get("table_name"))):
            raise AppError("ANALYSIS_CONTEXT_CHANGED")
        if join and not selected:
            raise AppError("VALIDATION_ERROR")
        filters = []
        for f in validated.get("filters") or []:
            if f.get("confirmed") is not True:
                raise AppError("ANALYSIS_CONTEXT_CHANGED")
            owner = join["table_name"] if f.get("table") == "related" else parent_table
            filters.append({**f, "table": owner})
        filters.sort(key=digest)
        filter_signature = sorted(_filter_identity(f) for f in filters) if selected else filters
        groups[digest(filter_signature)] = filters
        if inherit_check:
            check = period_check(validated, preview["columns"], refs[0]["field_name"])
            if check is None:
                raise AppError("VALIDATION_ERROR")
            pair = {"filters": filters, "check": check}
            checks[digest(pair)] = pair
        if selected:
            variant = {"table": parent_table, "report_category": validated.get("report_category"),
                       "report_date_field": validated.get("report_date_field"), "filters": filters}
            if join:
                variant["join"] = deepcopy(join)
            if suggestion.get("category") == "period":
                period_checks = {}
                for ref in refs:
                    if ref["table_name"] == parent_table:
                        field = ref["field_name"]
                        check = period_check(validated, preview["columns"], field)
                        if check:
                            period_checks[field] = check
                if len(refs) == 1 and period_checks:
                    variant["check"] = period_checks[refs[0]["field_name"]]
                elif period_checks:
                    variant["period_checks"] = period_checks
                variant["business_key"] = validated.get("business_key")
            variants[digest({**variant, "filters": filter_signature})] = variant
    return {"table": table, "fields": sorted({r["field_name"] for r in refs}), "groups": [groups[k] for k in sorted(groups)],
            **({"applicability_filters": deepcopy(suggestion["applicability_filters"])} if suggestion.get("applicability_filters") else {}),
            **({"checks": [checks[k] for k in sorted(checks)]} if checks else {}),
            **({"suggestion": {key: deepcopy(suggestion[key]) for key in (
                    "category", "kind", "references", "reason", "adoption", "limitations", "applicability_by_metric") if key in suggestion},
                "variants": [variants[k] for k in sorted(variants)]} if selected else {})}


def _join_keys(join, left_day, *, reversed_roles=False):
    right_day = join.get("report_date_field")
    on = join.get("on") or []
    if not isinstance(on, list) or not all(isinstance(pair, dict) for pair in on):
        return None
    keys = [(pair.get("left"), pair.get("right")) for pair in on]
    if keys.count((left_day, right_day)) == 1:
        keys.remove((left_day, right_day))
    return sorted(digest((right, left) if reversed_roles else (left, right)) for left, right in keys)


def bind_adopted_join(draft, table, related_target, scope, variant):
    """Use the verified relationship when it can express the same parent population."""
    parent = variant.get("join")
    parent_table = variant["table"]
    child = draft.get("join")
    related_name = related_target.get("table") if isinstance(related_target, dict) else None
    if parent is None:
        if table != parent_table:
            parent_day = variant["report_date_field"]
            if (related_name != parent_table or not isinstance(child, dict)
                    or child.get("report_date_field") not in (None, "", parent_day)):
                raise ScopeEvidenceRequired("补充建议需要保留已选数据对象的业务日期，请核实两者适用范围。")
            draft["join"] = {**child, "report_date_field": parent_day}
        return related_target
    if scope["suggestion"].get("kind") == "aggregate_consistency":
        reversed_roles = parent_table != table
        expected = (parent["table_name"], parent_table) if reversed_roles else (parent_table, parent["table_name"])
        if (not isinstance(child, dict) or (table, related_name) != expected
                or child.get("report_date_field") != (variant["report_date_field"] if reversed_roles else parent["report_date_field"])
                or _join_keys(child, parent["report_date_field"] if reversed_roles else variant["report_date_field"])
                != _join_keys(parent, variant["report_date_field"], reversed_roles=reversed_roles)):
            raise ScopeEvidenceRequired("补充汇总需要保留已选关联的对象、匹配键与日期，请核实同口径的关联。")
        draft["join"] = {**child, "relationship_confirmed": True, "unmatched_policy": parent["unmatched_policy"]}
        return related_target
    if (table != parent_table or related_name not in (None, parent["table_name"])
            or child is not None and (not isinstance(child, dict)
                or child.get("table_name") != parent["table_name"]
                or child.get("report_date_field") not in (None, "", parent["report_date_field"])
                or child.get("right_aggregate") != parent.get("right_aggregate")
                or child.get("unmatched_policy") not in (None, "unresolved", parent.get("unmatched_policy"))
                or child.get("on") and _join_keys(child, variant["report_date_field"]) != _join_keys(parent, variant["report_date_field"]))):
        raise ScopeEvidenceRequired("补充建议与已选方案的关联范围不同，请核实两者适用的业务对象。")
    draft["join"] = deepcopy(parent)
    return related_target or {"table": parent["table_name"]}


def adopted_join_matches(current, expected, left_day):
    return (isinstance(current, dict) and all(current.get(key) == expected.get(key) for key in (
        "table_name", "report_date_field", "relationship_confirmed", "unmatched_policy", "right_aggregate"))
        and _join_keys(current, left_day) == _join_keys(expected, left_day))


def verify_adopted_goal(definition, table, related, scope):
    suggestion = scope["suggestion"]
    aggregate = suggestion.get("kind") == "aggregate_consistency"
    period = suggestion.get("category") == "period"
    if not (aggregate or period):
        return
    def qualified(fields):
        return {(owner, name) for role, owner in (("base", table), ("related", related))
                for name in fields[role] if owner}
    operands = referenced_fields({"expression": definition.get("expression")})
    evidence = referenced_fields({key: definition.get(key) for key in ("join", "filters", "business_key")})
    if definition.get("report_date_field"):
        evidence["base"].add(definition["report_date_field"])
    references = {(ref["table_name"], ref["field_name"]) for ref in suggestion["references"]}
    actual = qualified(operands)
    if (not actual or not actual <= references or not references <= (actual | qualified(evidence))
            or aggregate and ((definition.get("join") or {}).get("right_aggregate") != "sum"
                              or not operands["base"] or not operands["related"])):
        message = "请核实补充建议指定的两侧指标、关联和按明细求和的范围。" if aggregate else "请核实期间建议指定的指标及适用范围。"
        raise ScopeEvidenceRequired(message)


def adopted_scope_label(group, groups, table, related, fields, other):
    """Distinguish inherited filters using active document field and dictionary labels."""
    if len(groups) < 2:
        return ""
    columns = {table: {f["field_name"]: f for f in fields}, related: {f["field_name"]: f for f in other}}
    captions = []
    for item in group:
        same_field = [f for g in groups for f in g if (f["table"], f["field"]) == (item["table"], item["field"])]
        if all(any(_filter_identity(item) == _filter_identity(f) for f in g) for g in groups):
            continue
        field = columns.get(item["table"], {}).get(item["field"])
        label = field_label(field) or item["field"]
        if len({_filter_identity(f) for f in same_field}) > 1:
            value = item.get("value")
            labels = {option["value"]: option["label"] for option in dictionary_options(field or {})}
            values = value if isinstance(value, list) else [value]
            if item["op"] in ("eq", "in"):
                condition = "、".join(labels.get(v, str(v)) for v in values)
            else:
                operators = {"is_null": "为空", "is_not_null": "非空", "neq": "不等于", "not_in": "排除",
                             "gt": "大于", "gte": "大于等于", "lt": "小于", "lte": "小于等于",
                             "contains": "包含", "not_contains": "不包含"}
                condition = operators.get(item["op"], "") + "、".join(labels.get(v, str(v)) for v in values if v is not None)
            label += "：" + condition
        captions.append(label)
    return "、".join(dict.fromkeys(captions))


def name_adopted_scope(candidate, suffix):
    name = candidate.get("rule_name")
    if suffix and name and suffix not in name:
        suffix = f"（{suffix[:80]}）"
        candidate["rule_name"] = name[:200 - len(suffix)] + suffix


def distinguish_adopted_scopes(options):
    groups = {}
    for option in options:
        if option["candidate"].get("rule_name"):
            groups.setdefault(option["label"], []).append(option)

    def column(candidate, role, name):
        return next((field_label(c) for c in candidate.get(role, []) if c["column_name"] == name), name or "")

    for siblings in groups.values():
        if len(siblings) < 2:
            continue
        candidates = [option["candidate"] for option in siblings]
        joins = [c.get("join") or {} for c in candidates]
        dates = {c.get("report_date_field") for c in candidates}
        related_dates = {j.get("report_date_field") for j in joins}
        relationships = {(j.get("table_name"), tuple(_join_keys(j, c.get("report_date_field")) or ()))
                         for c, j in zip(candidates, joins)}
        policies = {j.get("unmatched_policy") for j in joins}
        null_policies = {c.get("null_policy") for c in candidates}
        for option, candidate, join in zip(siblings, candidates, joins):
            labels = []
            if len(dates) > 1:
                labels.append("业务日期：" + column(candidate, "columns", candidate.get("report_date_field")))
            if len(relationships) > 1:
                if not join:
                    labels.append("仅主表")
                else:
                    other = table_label(candidate.get("related_table_name_cn"), join["table_name"])
                    keys = [column(candidate, "columns", p["left"]) + "＝" + column(candidate, "related_columns", p["right"])
                            for p in join.get("on", [])]
                    labels.append(f"关联{other}" + ("：" + "、".join(keys) if keys else ""))
            if len(related_dates) > 1 and join.get("report_date_field"):
                labels.append("关联日期：" + column(candidate, "related_columns", join["report_date_field"]))
            if len(policies) > 1 and join:
                labels.extend({"exclude": ["仅核查有同日关联的记录"], "review": ["缺同日关联记录待核查"]}.get(join.get("unmatched_policy"), []))
            if len(null_policies) > 1:
                labels.extend({"zero": ["空值按0"], "review": ["空值待核查"], "skip": ["跳过空值"],
                               "violate": ["空值视为异常"], "empty_string_as_null": ["空字符串视为空值"]}.get(candidate.get("null_policy"), []))
            name_adopted_scope(candidate, "，".join(labels))
            option["label"] = candidate["rule_name"]


def _period_applicability(draft, table, related, scope):
    facts = (scope.get("suggestion") or {}).get("applicability_by_metric")
    if not facts:
        return scope.get("applicability_filters", [])
    used = referenced_fields({"expression": draft.get("expression")})
    checked = {table: used["base"], related: used["related"]}
    matched = [fact["filters"] for fact in facts if fact["field"] in checked.get(fact["table"], ())]
    if not matched:
        return []
    signatures = {tuple(sorted(_filter_identity(item) for item in filters)) for filters in matched}
    if len(signatures) > 1:
        raise ScopeEvidenceRequired("期间建议中的检查指标适用范围不同，请明确本次检查的指标和范围。")
    return matched[0]


def reconcile_confirmed_scope_partitions(draft, table, related, scope, group, base_fields, related_fields):
    """Take the excluded codes from the document when the included set is already confirmed."""
    intent = draft.get("semantic_intent")
    declared = intent.get("scopes") if isinstance(intent, dict) else None
    if not isinstance(declared, list):
        return
    facts = [*group, *_period_applicability(draft, table, related, scope)]
    owners = {"base": (table, base_fields), "related": (related, related_fields)}
    for row in declared:
        if not isinstance(row, dict) or not isinstance(row.get("fields"), list) or len(row["fields"]) != 1:
            continue
        name = row["fields"][0]
        role = row.get("table", "base")
        if not isinstance(name, str) or not isinstance(role, str) or role not in owners:
            continue
        members = row.get("memberships")
        partition = members.get(name) if isinstance(members, dict) and set(members) == {name} else None
        included = partition.get("include") if isinstance(partition, dict) else None
        if not isinstance(included, list) or not included:
            continue
        owner, fields = owners[role]
        required = [fact for fact in facts if (fact["table"], fact["field"]) == (owner, name) and fact["op"] in ("eq", "in")]
        field = next((f for f in fields if f["field_name"] == name), None) if required else None
        if not field:
            continue
        numeric = type_family(field.get("data_type")) == "number"
        positive = {_code_key(value, numeric) for value in included}
        if None in positive or not any(positive == {_code_key(value, numeric) for value in (
                fact["value"] if fact["op"] == "in" else [fact["value"]])} for fact in required):
            continue
        try:
            codes = _document_codes(field)
        except _Unbound:
            continue
        canonical = [value for value in codes if _code_key(value, numeric) in positive]
        if len(canonical) != len(positive):
            continue
        members[name] = {"include": canonical, "exclude": [value for value in codes if value not in canonical]}
        row.pop("ambiguous_document_label", None)


def bind_period_filters(draft, table, related, scope, group):
    if not scope.get("suggestion"):
        used = referenced_fields({"expression": draft.get("expression")})
        if table != scope["table"] or not used["base"].intersection(scope["fields"]):
            raise ScopeEvidenceRequired("期间建议的检查指标与已采纳的文档字段不一致，请核实适用范围。")
    filters = draft.setdefault("filters", [])
    if not isinstance(filters, list):
        raise ScopeEvidenceRequired("期间建议的筛选条件格式需要核实。")
    declared = {(s.get("table", "base"), field) for s in draft.get("semantic_intent", {}).get("scopes", [])
                for field in s.get("fields", [])}
    group = list(group)
    for required in _period_applicability(draft, table, related, scope):
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


def _filter_value(item):
    op, value = item.get("op"), item.get("value")
    if op == "eq":
        return "in", [digest(value)]
    if op in ("in", "not_in") and isinstance(value, list):
        return op, sorted(digest(v) for v in value)
    return op, value


def _filter_identity(item):
    return digest([item["table"], item["field"], *_filter_value(item)])


def _same_filter(left, right):
    return _filter_value(left) == _filter_value(right)
