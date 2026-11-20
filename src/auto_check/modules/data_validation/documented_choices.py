"""Turn sufficiently documented interpretations into explicit choices on a private model draft."""
from copy import deepcopy
from itertools import combinations
import re

from .ai_service import model_expression
from .contracts import AppError
from .document_evidence import _GENERIC_METRICS, _business_aliases, referenced_fields
from .generation_policy import text_tokens
from .parallel_checks import NONEMPTY_REQUIREMENT
from .prompt_defaults import SEMANTIC_MAX_PLANS
from .query_grounding import resolve_report_date
from .query_spec import is_finite_number, is_numeric_comparison, type_family
from .semantic_grounding import (
    _document_codes, _explicit_filter, _roles, _scope_options, _Unbound,
    join_decisions_refine, without_period_join_key,
)


class ScopeEvidenceRequired(ValueError):
    """A known alternate grain cannot carry the request's original scope without more evidence."""


_PERIOD = re.compile(r"初始|期初|年初|月初|上期|上年|上月|历史")
_VARIANT = re.compile(r"原始|当前|现行|[\s_（）()\-]")


def _simple_metric(plan, by_name):
    expr = plan.get("expression")
    intent = plan.get("semantic_intent")
    if not isinstance(expr, dict) or not isinstance(intent, dict) or plan.get("rule_type") != "field_compare":
        return None
    if (plan.get("join") or plan.get("related_target") or plan.get("unsupported_requirements")
            or not isinstance(intent.get("scopes"), list) or not isinstance(intent.get("open_questions"), list)):
        return None
    if expr.get("op") in ("is_null", "is_not_null"):
        if expr.keys() != {"left", "op"}:
            return None
    elif (expr.keys() != {"left", "op", "right_type", "right"} or expr.get("right_type") != "value"
          or expr.get("op") not in {"eq", "neq", "lt", "lte", "gt", "gte"} or not is_finite_number(expr["right"])):
        return None
    metrics = intent.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != 1 or not isinstance(metrics[0], dict):
        return None
    m = metrics[0]
    name = expr.get("left")
    choices = m.get("fields")
    if (not isinstance(name, str) or not isinstance(choices, list) or name not in choices
            or not all(isinstance(f, str) and f in by_name for f in choices)
            or m.get("side") != "left" or m.get("condition_index", 0) != 0 or not isinstance(m.get("term"), str)):
        return None
    return m


def _offer_scope(scope, group, roles):
    names = scope["fields"]
    if len(names) != 1 or names[0] in (scope.get("excluded_fields") or {}):
        return False
    fields = roles[scope.get("table", "base")]
    field = fields[names[0]]
    codes = _document_codes(field)
    lines = {line.strip() for line in field["dictionary"].splitlines() if line.strip()}
    original = _scope_options(scope, roles, {})[0]["selection"]
    included = original["value"] if original["op"] == "in" else [original["value"]]
    if not any(group["term"] in str(codes[code]).lower() for code in included):
        return False
    family = _VARIANT.sub("", str(field.get("field_cn") or ""))
    if not family:
        return False
    for peer in group["candidates"][0]["fields"]:
        if peer in names:
            continue
        other = fields[peer]
        if (peer in (scope.get("excluded_fields") or {}) or _document_codes(other) != codes
                or {line.strip() for line in other["dictionary"].splitlines() if line.strip()} != lines
                or type_family(other.get("data_type")) != type_family(field.get("data_type"))
                or _VARIANT.sub("", str(other.get("field_cn") or "")) != family):
            return False
        names.append(peer)
        scope["memberships"][peer] = deepcopy(scope["memberships"][field["field_name"]])
    _scope_options(scope, roles, {})
    return len(names) > 1


def _direct_sources(field, owner, column):
    """Paired source lines may reference the active table and its monthly snapshots."""
    if not re.fullmatch(r"直取[。.]?|直接取(?:值|数)?[。.]?", str(field.get("logic") or "").strip()):
        return ()
    tables = str(field.get("source_table") or "").strip().splitlines()
    columns = str(field.get("source_field") or "").strip().splitlines()
    if any(not re.fullmatch(r"(?:[A-Za-z_][\w]*\.){0,2}[A-Za-z_][\w]*", table.strip()) for table in tables):
        return ()
    sources = [name.strip().split(".")[-1] for name in tables]
    if (len(sources) != len(columns) or owner not in sources
            or not all(source in {owner, owner + "_YYYY_MM"} and name.strip() == column
                       for source, name in zip(sources, columns))):
        return ()
    return tuple(sorted(table.strip() for table in tables))


def _scope_join(base, base_fields, alternate, fields):
    date, _ = resolve_report_date(base_fields)
    from_date, _ = resolve_report_date(fields)
    by_name = {f["field_name"]: f for f in fields}
    owner = base["table_name"]
    sources = _direct_sources(by_name[from_date], owner, date) if date and from_date else ()
    if not sources:
        return None
    keys = [f for f in base_fields if f.get("is_pk") == "Y" and f["field_name"] != date]
    if not 1 <= len(keys) <= 4 or not alternate.get("dimension") or alternate["dimension"] == base.get("dimension"):
        return None
    pairs = []
    for key in keys:
        family = type_family(key.get("data_type"))
        candidates = [f for f in fields if family and type_family(f.get("data_type")) == family
                      and _direct_sources(f, owner, key["field_name"]) == sources]
        if len(candidates) != 1:
            return None
        pairs.append({"left": candidates[0]["field_name"], "right": key["field_name"]})
    linked = {pair["left"] for pair in pairs} | {from_date}
    if not any(f.get("is_pk") == "Y" and f["field_name"] not in linked for f in fields):
        return None
    return {"table_name": owner, "on": pairs, "report_date_field": date, "unmatched_policy": "unresolved"}


def _summary_of(field, tablename, column):
    logic = str(field.get("logic") or "")
    return (str(field.get("source_table") or "").split(".")[-1] == tablename
            and field.get("source_field") == column and "分组" in logic
            and any(word in logic for word in ("相加", "求和", "汇总"))
            and not _business_aliases(field))


def _check_grain_documents(analysis, base, other, declared):
    service = analysis.service
    owner_categories = service._doc_category_scope(base, analysis.categories)
    other_categories = service._doc_category_scope(other, analysis.categories)
    if (not owner_categories or owner_categories != other_categories
            or base.get("data_source_name") != other.get("data_source_name")
            or any(sum(t["table_name"] == item["table_name"] for t in analysis.tables) != 1 for item in (base, other))
            or (declared and not service._category_tables([other], {declared}, analysis.categories))):
        raise ScopeEvidenceRequired("需核实两个指标所在文档的数据源和报送分类，才能提供跨维度方案。")


def _other_grain(analysis, selection, base, plan, group):
    term = group["term"]
    left = plan["expression"]["left"]
    base_fields = analysis.fields[base["id"]]
    by_name = {f["field_name"]: f for f in base_fields}
    if (term in _GENERIC_METRICS or len(term) < 2 or not any(term in a for a in _business_aliases(by_name[left]))
            or not (plan["semantic_intent"]["scopes"] or plan.get("filters"))):
        return None
    by_id = {t["id"]: t for t in analysis.tables}
    peers = []
    for hit in group["candidates"]:
        if hit["table_id"] == base["id"]:
            if hit["fields"] != [left]:
                return None
            continue
        table = by_id[hit["table_id"]]
        peers.extend((table, f) for f in analysis.fields[table["id"]] if f["field_name"] in hit["fields"])
    registered = [(t, f) for t, f in peers if any(term in a for a in _business_aliases(f))]
    if len(registered) != 1:
        return None
    other, field = registered[0]
    if plan["expression"].get("right_type") == "value" and plan["expression"]["right"] != 0:
        raise ScopeEvidenceRequired("不同维度的指标采用非零阈值前，需核实计量单位和相应阈值。")
    if any(not _summary_of(f, other["table_name"], field["field_name"]) for t, f in peers if (t, f) != registered[0]):
        return None
    # A user who explicitly asks about a summary must still get model review of that grain.
    if len(peers) > len(registered):
        if re.search(r"汇总|分组|合计", analysis.request):
            return None
        grains = text_tokens(base.get("dimension", "")) | text_tokens(other.get("dimension", ""))
        for t, _ in peers:
            if t != other and (text_tokens(t.get("dimension", "")) - grains) & analysis.index.wanted:
                return None
    declared = plan.get("report_category") or selection.get("report_category")
    target = {"table": other["table_name"]}
    _check_grain_documents(analysis, base, other, declared)
    join = _scope_join(base, base_fields, other, analysis.fields[other["id"]])
    if not join:
        raise ScopeEvidenceRequired("需补充" + other["table_name"] + "关联原范围所用的业务编号、同日报送日期及对应列来源。")
    alt = deepcopy(plan)
    alt.update(target=target, related_target={"table": base["table_name"]}, join=join, recommended=False)
    # The alternate has a different base. Its project role must be proven for that table.
    alt.pop("project_driver", None)
    if "business_key" in alt and not any(f["field_name"] == alt["business_key"] for f in analysis.fields[other["id"]]):
        del alt["business_key"]
    name = field["field_name"]
    alt["expression"]["left"] = name
    metric = alt["semantic_intent"]["metrics"][0]
    metric.update(term=field["field_cn"] or name, fields=[name])
    metric.pop("recommended", None)
    metric.pop("rule_names", None)
    # Keep the requested condition visible without copying the first grain's business description.
    alt["rule_name"] = (analysis.request + "（" + (field["field_cn"] or name) + "）")[:200]
    alt["violation_message"] = alt["rule_name"]
    alt.pop("ai_suggestions", None)
    alt["match_reason"] = "字段文档登记了相关业务别名，请确认采用此检查维度及对应范围。"
    for row in [*alt["semantic_intent"]["scopes"], *alt.get("filters", [])]:
        row["table"] = "related"
    return alt


def document_choices(analysis, selection, pending, validate_intent):
    """Return only completely evidenced pending choices. Other candidates retain model review."""
    first = selection.get("draft", selection)
    if (selection.get("related_target") or selection.get("candidate_targets") or selection.get("expand_evidence")
            or not selection.get("target") or not isinstance(first, dict) or first.get("interpretation_exclusions")):
        return None
    proposal = deepcopy(first)
    plans = proposal.get("plans", [proposal])
    base = analysis.resolve(selection["target"], selection.get("report_category"))
    if selection["target"].get("report_category") not in (None, "", selection.get("report_category")):
        return None
    roles = _roles(analysis.fields[base["id"]], [])
    fields = roles["base"]
    metrics = []
    for plan in plans:
        if (not isinstance(plan, dict) or plan.get("target", selection["target"]) != selection["target"]
                or plan.get("report_category", selection.get("report_category")) != selection.get("report_category")):
            return None
        metric = _simple_metric(plan, fields)
        if not metric:
            return None
        validate_intent(plan, analysis.fields[base["id"]], [])
        metrics.append(metric)
        for row in plan["semantic_intent"]["scopes"]:
            if not isinstance(row, dict) or row.get("table", "base") != "base":
                return None
            _scope_options(row, roles, {})
        if not isinstance(plan.get("filters", []), list):
            return None
        for row in plan.get("filters", []):
            _explicit_filter(row, roles)
        # Previously unseen paraphrases still need a document turn. A model's exact label on a
        # parallel field choice can instead be checked directly against its full authorized entry.
        unseen = referenced_fields(plan)["base"] - analysis.index.details[base["id"]]
        if unseen:
            declared_peer = (len(metric["fields"]) > 1 and unseen <= set(metric["fields"])
                             and all(metric["term"] in str(fields[name].get("field_cn") or "") for name in unseen))
            exact_labels = (len(plans) > 1 and unseen == set(metric["fields"])
                            and fields[plan["expression"]["left"]].get("field_cn") == metric["term"])
            if not (declared_peer or exact_labels):
                return None
    named = {name for m in metrics for name in m["fields"]}
    same_condition = all(
        {k: v for k, v in p["expression"].items() if k != "left"} ==
        {k: v for k, v in plans[0]["expression"].items() if k != "left"}
        and p.get("null_policy") == plans[0].get("null_policy")
        and p["semantic_intent"]["scopes"] == plans[0]["semantic_intent"]["scopes"]
        and p.get("filters") == plans[0].get("filters") for p in plans)
    alternate_group = None
    offered_scope = any(len(scope["fields"]) > 1 for p in plans for scope in p["semantic_intent"]["scopes"])
    for group in pending:
        hits = group["candidates"]
        if any(hit.get("requires_model_review") for hit in hits):
            return None
        if group["kind"] == "scopes":
            if len(hits) != 1 or hits[0]["table_id"] != base["id"]:
                return None
            covered = False
            for plan in plans:
                for scope in plan["semantic_intent"]["scopes"]:
                    if scope["category"] != group["first_interpretation"]:
                        continue
                    if set(scope["fields"]) < set(hits[0]["fields"]):
                        if not _offer_scope(scope, group, roles):
                            return None
                        offered_scope = True
                    covered |= set(hits[0]["fields"]) <= set(scope["fields"])
            if not covered:
                return None
        elif len(plans) == 1 and len(hits) > 1:
            alternate_group = group
        elif (same_condition and len(hits) == 1 and hits[0]["table_id"] == base["id"]
              and len(named.intersection(hits[0]["fields"])) > 1):
            for name in set(hits[0]["fields"]) - named:
                periods = _PERIOD.findall(str(fields[name].get("field_cn") or ""))
                if not periods or any(period in analysis.request for period in periods):
                    return None
        else:
            return None
    if alternate_group:
        alt = _other_grain(analysis, selection, base, plans[0], alternate_group)
        if alt:
            return {"plan_mode": "alternatives", "plans": [plans[0], alt]}
        return None
    return proposal if offered_scope or any(len(m["fields"]) > 1 for m in metrics) else None


def _predicate(selection, owners):
    value = selection.get("value")
    if isinstance(value, list):
        value = frozenset(value)
    return (owners[selection["table"]], selection["field"], selection["op"], value)


def verified_null_policy(plan, roles):
    """A model's numeric NULL decision is binding once its binary operands are verified."""
    policy = plan.get("null_policy")
    if policy not in ("zero", "review"):
        return policy if policy in ("skip", "violate", "empty_string_as_null") else None
    base_types = {name: field.get("data_type") for name, field in roles["base"].items()}
    related_types = {name: field.get("data_type") for name, field in roles["related"].items()}
    try:
        return policy if is_numeric_comparison(plan, base_types, related_types) else None
    except AppError:
        # A malformed condition group still needs a repair before its types can be confirmed.
        return None


def plan_facts(plan, base, related, all_fields, category):
    """Record independently verified facts, including intact parts of an incomplete model reply."""
    if plan.get("rule_type") != "field_compare":
        return None
    roles = _roles(all_fields[base["id"]], all_fields[related["id"]] if related else [])
    owners = {"base": base["id"], "related": related["id"] if related else None}
    scopes, filters = [], set()
    intent = plan.get("semantic_intent")
    intent = intent if isinstance(intent, dict) else {}
    for scope in intent.get("scopes", []) if isinstance(intent.get("scopes"), list) else []:
        if not isinstance(scope, dict) or scope.get("table", "base") not in ("base", "related"):
            continue
        try:
            choices = _scope_options(scope, roles, {})
        except _Unbound:
            continue
        scopes.append(frozenset(_predicate(opt["selection"], owners) for opt in choices))
    for row in plan.get("filters", []) if isinstance(plan.get("filters"), list) else []:
        try:
            filters.add(_predicate(_explicit_filter(row, roles), owners))
        except _Unbound:
            continue
    expression = model_expression(plan.get("expression"))
    expression = expression if isinstance(expression, dict) else {}
    conditions = expression.get("conditions", [expression])
    parts = []
    for part in conditions if isinstance(conditions, list) else []:
        facts = {}
        if isinstance(part, dict):
            left = part.get("left")
            if isinstance(left, str) and left in roles["base"]:
                facts["left"] = left
            if part.get("op") in ("lt", "lte", "eq", "neq", "gt", "gte", "is_null", "is_not_null"):
                facts["op"] = part["op"]
            if part.get("op") not in ("is_null", "is_not_null"):
                right = part.get("right")
                if is_finite_number(right) and part.get("right_type", "value") == "value":
                    facts.update(right_type="value", right=right)
                role = part.get("right_table", "base")
                if (isinstance(right, str) and role in ("base", "related") and right in roles[role]
                        and part.get("right_type", "field") == "field"):
                    facts.update(right_type="field", right_table=role, right=right)
        parts.append(facts)
    join = without_period_join_key(plan.get("join"), all_fields[base["id"]],
                                   all_fields[related["id"]] if related else [])
    return {"table": base, "category": category, "related": related, "join": join,
            "scopes": scopes, "filters": filters, "parts": parts if any(parts) else [],
            # An empty first draft provides no range facts to freeze before document review.
            "scopes_complete": bool(scopes) and len(scopes) == len(intent["scopes"]),
            "filters_complete": bool(filters) and len(filters) == len(plan["filters"]),
            "logic": expression.get("logic"), "null": verified_null_policy(plan, roles),
            "metrics": intent.get("metrics", [])}


def _covers(current, previous):
    if (current["table"]["id"] != previous["table"]["id"]
            or previous["related"] and previous["related"] != current["related"]
            or previous["null"] and previous["null"] != current["null"]
            or not previous["filters"] <= current["filters"]
            or previous["filters_complete"] and previous["filters"] != current["filters"]):
        return False
    if previous["join"] and not join_decisions_refine(previous["join"], current["join"]):
        return False
    if (previous["scopes_complete"] and len(current["scopes"]) != len(previous["scopes"]) or
            not all(any(old <= new for new in current["scopes"]) for old in previous["scopes"])):
        return False
    parts = previous["parts"]
    return (not parts or (previous["logic"] == current["logic"] and len(parts) == len(current["parts"])
            and _same_predicate_facts(parts, current["parts"])))


def _same_predicate_facts(previous, current):
    """AND/OR branches commute, but each verified occurrence needs its own match."""
    candidates = [[i for i, now in enumerate(current) if all(now.get(k) == v for k, v in old.items())]
                  for old in previous]
    owners = [None] * len(current)

    def match(index, visited):
        for target in candidates[index]:
            if target in visited:
                continue
            visited.add(target)
            if owners[target] is None or match(owners[target], visited):
                owners[target] = index
                return True
        return False

    return all(match(index, set()) for index in range(len(previous)))


def _metric_terms(facts, fields, request_tokens):
    """Model labels alone cannot unbind two indicators sharing registered request terminology."""
    names = {part["left"] for part in facts["parts"] if "left" in part}
    aliases = {word for f in fields if f["field_name"] in names for a in _business_aliases(f) for word in text_tokens(a)}
    declared = {m["term"] for m in facts["metrics"] if isinstance(m, dict) and m.get("side") == "left"
                and isinstance(m.get("term"), str) and isinstance(m.get("fields"), list)
                and any(isinstance(name, str) and name in names for name in m["fields"])}
    return (aliases & request_tokens) - _GENERIC_METRICS, declared & request_tokens


def _check_same_grain_measure(analysis, a, b):
    _check_grain_documents(analysis, a["table"], b["table"], a["category"])
    _check_grain_documents(analysis, b["table"], a["table"], b["category"])
    parts = [side["parts"] for side in (a, b)]
    if (any(len(row) != 1 for row in parts) or a["null"] != b["null"]
            or any(part.get("right_type") == "field" or part.get("right", 0) != 0 for row in parts for part in row)
            or {k: v for k, v in parts[0][0].items() if k != "left"} !=
               {k: v for k, v in parts[1][0].items() if k != "left"}):
        raise ScopeEvidenceRequired("请核实各维度的异常条件、空值要求、计量单位和阈值。")
    if a["filters"] != b["filters"] or set(a["scopes"]) != set(b["scopes"]):
        raise ScopeEvidenceRequired("不同维度的同一指标必须保留完整的原始范围和筛选条件，请核实各方案的字段归属。")
    if not (a["filters"] or a["scopes"]):
        return
    for side, owner in ((a, b), (b, a)):
        if side["related"] != owner["table"]:
            continue
        join = side["join"] or {}
        expected = _scope_join(owner["table"], analysis.fields[owner["table"]["id"]],
                               side["table"], analysis.fields[side["table"]["id"]])
        if (expected and join.get("on") == expected["on"] and join.get("report_date_field") == expected["report_date_field"]
                and not join.get("right_aggregate")):
            return
    raise ScopeEvidenceRequired("需核实跨维度范围对应的业务键、同日报送日期及文档记载的关联来源。")


def verify_prior_facts(current, earlier):
    if any(not any(_covers(now, old) for now in current) for old in earlier):
        raise ScopeEvidenceRequired("重新分析改变了已经核实的异常条件、阈值、空值处理或适用范围，请核实后继续。")


def verify_grain_facts(analysis, current):
    tokens = text_tokens(analysis.request)
    terms = [_metric_terms(row, analysis.fields[row["table"]["id"]], tokens) for row in current]
    for (a, (alias_a, terms_a)), (b, (alias_b, terms_b)) in combinations(zip(current, terms), 2):
        if a["table"]["id"] == b["table"]["id"]:
            continue
        scoped = a["filters"] or a["scopes"] or b["filters"] or b["scopes"]
        if alias_a & alias_b or (scoped and terms_a & terms_b):
            _check_same_grain_measure(analysis, a, b)


def exclusion_supported(check, field, source, quote, request):
    """Accept an explicit exclusion of this field/metric, backed by its own text."""
    if source == "request" and quote in request:
        labels = [v for v in (check["field"], check["label"]) if v and v != check["term"]]
        return any(re.search(r"(?:排除|不含|不包括|不使用|不采用|不校验|不检查)\s*" + re.escape(label), quote)
                   for label in labels)
    if source != "document" or quote not in str(field.get("logic") or ""):
        return False
    sentences = [part.strip() for part in re.split(r"[。；;\r\n]+", str(field.get("logic") or "")) if part.strip()]
    quoted = quote.strip().rstrip("。；;")
    if quoted not in sentences:
        return False
    # A preference, generic field metadata or a piece of a longer negated sentence
    # cannot establish that the field is inapplicable to the requested metric.
    return bool(re.search(r"(?:不能替代|不适用于|不得用于|不能用于|不属于|不代表|不表示|不等同于)"
                          r"[^，,。；;]{0,60}" + re.escape(check["term"]), quoted))


def choice_identity(previous, targets, selected):
    """Bind a genuine previous question to its precise document and semantic operand."""
    expression = previous.get("expression") or {}
    intent = previous.get("semantic_intent") or {}
    base = previous.get("table_name")
    role = "base"
    prefix = {k: previous.get(k) for k in ("source_id", "doc_version", "doc_sha256", "report_category")}
    if isinstance(selected, dict):
        if len(targets) != 1 or not (path := re.fullmatch(r"filters\.(\d+)", targets[0])):
            return {}
        i = int(path[1])
        scopes = intent.get("scopes", [])
        if i >= len(scopes):
            return {}
        scope = scopes[i]
        role = scope.get("table", "base")
        if selected.get("table", "base") != role or selected.get("field") not in scope.get("fields", []):
            return {}
        binding = {"kind": "scopes", "term": scope.get("category"), "index": i}
    elif isinstance(selected, str):
        rows = expression.get("conditions", [expression])
        indices = []
        terms = set()
        sides = set()
        roles = set()
        for target in targets:
            match = re.fullmatch(r"expression(?:\.conditions\.(\d+))?\.(left|right)", target)
            if not match:
                return {}
            index, side = int(match[1] or 0), match[2]
            if index >= len(rows):
                return {}
            indices.append(index)
            sides.add(side)
            roles.add(rows[index].get("right_table", "base") if side == "right" else "base")
            metrics = [m for m in intent.get("metrics", []) if m.get("side") == side
                       and m.get("condition_index", index) == index and selected in m.get("fields", [])]
            if len(metrics) != 1:
                return {}
            terms.add(metrics[0].get("term"))
        if len(terms) != 1 or len(sides) != 1 or len(roles) != 1:
            return {}
        role = roles.pop()
        binding = {"kind": "metrics", "term": terms.pop(), "indices": indices, "side": sides.pop()}
    else:
        return {}
    owner = base if role == "base" else (previous.get("join") or {}).get("table_name")
    return {**prefix, **binding, "base": base, "owner": owner, "role": role}


def _exact_metric_choices(analysis, selection, draft, expression):
    """Discard incidental choices only for an operand already bound to its unique explicit name."""
    intent = draft.get("semantic_intent")
    metrics = intent.get("metrics") if isinstance(intent, dict) else None
    if not isinstance(metrics, list) or not isinstance(expression, dict):
        return draft
    conditions = expression.get("conditions", [expression])
    if not isinstance(conditions, list):
        return draft
    result = draft
    for pos, item in enumerate(metrics):
        names = item.get("fields") if isinstance(item, dict) else None
        if not isinstance(names, list) or len(names) < 2:
            continue
        i, side = item.get("condition_index", 0), item.get("side")
        if type(i) is not int or not 0 <= i < len(conditions) or not isinstance(conditions[i], dict):
            continue
        condition = conditions[i]
        if side not in ("left", "right") or (side == "right" and condition.get("right_type") == "value"):
            continue
        name = condition.get(side)
        role = "related_target" if side == "right" and condition.get("right_table") == "related" else "target"
        target = draft.get(role, selection.get(role))
        if not target or not isinstance(name, str) or name not in names:
            continue
        owner = analysis.resolve(target, draft.get("report_category", selection.get("report_category")))
        if not analysis.index.exact_metric_field(owner, name, item.get("term")):
            continue
        fields = {f["field_name"]: f for f in analysis.fields[owner["id"]]}
        if any(not isinstance(n, str) or n not in fields for n in names):
            continue  # Unknown columns still require the normal document/role validation.
        if any(n != name and (n.lower() in analysis.index.wanted or any(
                (owner["id"], n) in pairs for pairs in analysis.index.document_names.values())) for n in names):
            continue
        if result is draft:
            result = deepcopy(draft)
        metric = result["semantic_intent"]["metrics"][pos]
        metric["fields"] = [name]
        metric.pop("recommended", None)
        if isinstance(metric.get("rule_names"), dict):
            metric["rule_names"] = {k: v for k, v in metric["rule_names"].items() if k == name}
    return result


def _reviewed_scope_choices(analysis, selection, draft):
    groups = [g for g in analysis.competing_evidence if g["kind"] == "scopes"]
    intent = draft.get("semantic_intent")
    scopes = intent.get("scopes") if isinstance(intent, dict) else None
    if not groups or not isinstance(scopes, list):
        return draft
    result = draft
    for i, scope in enumerate(scopes):
        names = scope.get("fields") if isinstance(scope, dict) else None
        if not isinstance(names, list) or len(names) != 1 or not isinstance(scope.get("category"), str):
            continue
        role = scope.get("table", "base")
        key = "related_target" if role == "related" else "target"
        target = draft.get(key, selection.get(key))
        if role not in ("base", "related") or not target:
            continue
        table = analysis.resolve(target, draft.get("report_category", selection.get("report_category")))
        for group in groups:
            if (group["role"] != role or group["term"] not in scope["category"] or
                    not any(c["table_id"] == table["id"] for c in group["candidates"])):
                continue
            peers = analysis.index.competing_fields(table, names, group["term"], [table], category=True)
            if not peers or len(peers[0]["fields"]) < 2:
                continue
            fields = {f["field_name"]: f for f in analysis.fields[table["id"]]}
            offered = deepcopy(scope)
            try:
                if not _offer_scope(offered, {**group, "candidates": peers}, {role: fields}):
                    continue
            except _Unbound:
                continue
            if result is draft:
                result = deepcopy(draft)
            result["semantic_intent"]["scopes"][i] = offered
            break
    return result


def qualified_peer_choice(analysis, selection, draft, *, owner_choices=(), single=True):
    """A generic unary check cannot silently require every qualified variant at once."""
    if "plans" in draft:
        plans = draft["plans"]
        if (not isinstance(plans, list) or not 1 <= len(plans) <= SEMANTIC_MAX_PLANS
                or not all(isinstance(p, dict) and "plans" not in p for p in plans)):
            return draft
        reviewed = [qualified_peer_choice(analysis, selection, p, owner_choices=owner_choices, single=len(plans) == 1)
                    for p in plans]
        return {**draft, "plans": reviewed} if any(a is not b for a, b in zip(plans, reviewed)) else draft
    expr = model_expression(draft.get("expression"))
    if not owner_choices and not analysis.inputs.get("clarification_answers"):
        draft = _exact_metric_choices(analysis, selection, draft, expr)
        draft = _reviewed_scope_choices(analysis, selection, draft)
    target = draft.get("target", selection.get("target"))
    if (single and target and not draft.get("join") and isinstance(expr, dict)
            and set(expr) == {"left", "op"} and expr["op"] == "is_null"
            and not analysis.inputs.get("clarification_answers")):
        request = re.sub(r"\s+", "", analysis.request).rstrip("。！.!")
        match = re.fullmatch(r"(.+?)" + NONEMPTY_REQUIREMENT, request)
        intent = draft.get("semantic_intent")
        metrics = intent.get("metrics") if isinstance(intent, dict) else None
        if (match and isinstance(metrics, list) and len(metrics) == 1 and isinstance(metrics[0], dict)
                and metrics[0].get("side") == "left" and metrics[0].get("fields") == [expr["left"]]):
            term = match[1]
            base = analysis.resolve(target, draft.get("report_category", selection.get("report_category")))
            fields = analysis.fields[base["id"]]
            source = next((f for f in fields if f["field_name"] == expr["left"]), {})
            peers = [f["field_name"] for f in fields if type_family(f.get("data_type")) == type_family(source.get("data_type"))
                     and re.fullmatch(r"(?:期初|期末|当期|累计|原始|当前|现行)" + re.escape(term), f.get("field_cn") or "")]
            if (expr["left"] in peers and 2 <= len(peers) <= 20
                    and not any(analysis.matches_owner_choice(c, "metrics", metrics[0], base, "base", base, 0)
                                for c in owner_choices if isinstance(c, dict))):
                result = deepcopy(draft)
                result["semantic_intent"]["metrics"][0].update(term=term, fields=peers)
                result["violation_message"] = "所选" + term + "字段为空"
                return result
    if (not isinstance(expr, dict) or expr.get("logic") not in ("any", "all")
            or set(expr) != {"logic", "conditions"} or draft.get("join") or not target):
        return draft
    rows = expr["conditions"]
    if not isinstance(rows, list) or not 2 <= len(rows) <= 3 or not all(isinstance(row, dict) for row in rows):
        return draft
    if any(set(row) != {"left", "op"} or row.get("op") != "is_null" for row in rows):
        return draft
    names = [row["left"] for row in rows]
    if not all(isinstance(n, str) for n in names) or len(set(names)) != len(names):
        return draft
    intent = draft.get("semantic_intent")
    metrics = intent.get("metrics") if isinstance(intent, dict) else None
    if not isinstance(metrics, list) or len(metrics) != len(rows):
        return draft
    base = analysis.resolve(target, draft.get("report_category", selection.get("report_category")))
    fields = {f["field_name"]: f for f in analysis.fields[base["id"]]}
    anchors, named = [], []
    for i, name in enumerate(names):
        field = fields.get(name, {})
        label = field.get("field_cn")
        bindings = [m for m in metrics if isinstance(m, dict) and m.get("side") == "left" and m.get("fields") == [name]
                    and m.get("term") == label and m.get("condition_index", i) == i]
        if len(bindings) != 1 or not label:
            return draft
        named.append(label in analysis.request or name in analysis.request)
        hits = analysis.index.competing_fields(base, [name], label, [base])
        if not hits or not set(names) <= set(hits[0]["fields"]):
            return draft
        anchors.append(hits[0]["request_term"])
    if len(set(anchors)) != 1 or all(named):
        return draft
    term = anchors[0]
    if not all(term in fields[name]["field_cn"] for name in names):
        return draft
    if any(named):
        raise ScopeEvidenceRequired("需求中只明确了部分字段，请确认要检查的指标：" + "、".join(fields[n]["field_cn"] for n in names))
    if re.search(r"(?:任一|任意|任何|全部|所有|各项)(?:项|个|种)?(?:的)?" + re.escape(term)
                 + "|" + re.escape(term) + r"(?:指标|字段)?(?:均|都|全部|任一)", analysis.request):
        return draft
    result = deepcopy(draft)
    result["expression"] = deepcopy(rows[0])
    result["semantic_intent"]["metrics"] = [{"side": "left", "term": term, "fields": names}]
    result["violation_message"] = "所选" + term + "字段为空"
    return result


def missing_registered_grain(analysis, owner, item, declarations, role):
    names = item["fields"]
    if len(names) != 1 or not isinstance(names[0], str):
        return None
    own = next((f for f in analysis.fields[owner["id"]] if f["field_name"] == names[0]), {})
    if not _business_aliases(own):
        return None
    groups = analysis.index.competing_fields(owner, names, item.get("term", ""), analysis.tables, across_tables=True)
    for group in groups:
        term = group["request_term"]
        if (group.get("requires_model_review") or group["table_id"] == owner["id"] or term in _GENERIC_METRICS
                or not any(term in a for a in _business_aliases(own))):
            continue
        for f in analysis.fields[group["table_id"]]:
            name = f["field_name"]
            if (name in group["fields"] and any(term in a for a in _business_aliases(f)) and
                    ("metrics", group["table_id"], role, item.get("side", ""), item.get("condition_index", 0), name)
                    not in declarations):
                return group["table"] + "." + name
    return None
