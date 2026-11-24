"""Bind the model's structured interpretation to the active document, without reading the request."""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

from .contracts import AppError
from .formula import has_arithmetic
from .project_context import base_type
from .query_grounding import bind_model_join, dictionary_options, resolve_report_date
from .query_spec import (
    MAX_CONDITIONS, MAX_FILTERS, MAX_IN_VALUES, MAX_JOIN_KEYS, TEXT_FILTER_OPS, UNARY_OPS, _validate_filter_value, type_family,
    validate_query_spec,
)


class _Unbound(ValueError):
    pass


def _items(value, limit):
    if not isinstance(value, list) or limit is not None and len(value) > limit:
        raise _Unbound("模型给出的结构化口径格式或数量不符合要求，请重新分析。")
    return value


def _choice(item, label_key):
    if not isinstance(item, dict) or not isinstance(item.get(label_key), str) or not item[label_key].strip():
        raise _Unbound("模型未提供明确的业务口径名称，请重新分析。")
    names = _items(item.get("fields"), 20)
    if not names or not all(isinstance(name, str) and name for name in names):
        raise _Unbound(f"请明确「{item[label_key]}」对应的文档字段。")
    return list(dict.fromkeys(names))


def _document_codes(field):
    name = field["field_name"]
    codes = {}
    for line in re.split(r"[\r\n；;]+", str(field.get("dictionary") or "")):
        line = line.strip()
        if not line or re.fullmatch(r"【[^】]+】|\[[^\]]+\]", line):
            continue
        entries = dictionary_options({**field, "dictionary": line})
        if len(entries) != 1:
            raise _Unbound(f"请补全 {name} 的字段字典。")
        code, label = entries[0]["value"], entries[0]["label"]
        if codes.setdefault(code, label) != label:
            raise _Unbound(f"请核实 {name} 的重复字典取值。")
    if not codes:
        raise _Unbound(f"请补全 {name} 的字段字典。")
    return codes


def dictionary_partition_question(scope, base_fields, related_fields):
    """Offer documented values after a model fails to partition a real classification field."""
    if not isinstance(scope, dict) or not isinstance(scope.get("category"), str):
        return None
    role = scope.get("table", "base")
    names = scope.get("fields")
    if role not in ("base", "related") or not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        return None
    fields = {f["field_name"]: f for f in (base_fields if role == "base" else related_fields)}
    if any(n not in fields for n in names):
        return None
    options = []
    try:
        for name in dict.fromkeys(names):
            field = fields[name]
            codes = _document_codes(field)
            counts = Counter(codes.values())
            for code, label in codes.items():
                caption = label if counts[label] == 1 else f"{label}（{code}）"
                if len(names) != 1:
                    caption = f"{field.get('field_cn') or name}·{caption}"
                options.append({"label": caption, "value": f"{name}={code}"})
    except _Unbound:
        return None
    table_id = fields[names[0]].get("table_id")
    if table_id is None:
        return None
    category = scope["category"]
    signature = sha256(category.encode()).hexdigest()[:12]
    field_ids = ",".join(sorted(str(fields[name].get("id", name)) for name in set(names)))
    return {"id": f"dictionary/{table_id}/{role}/{field_ids}/{signature}", "evidence_term": category, "requires_analysis": True,
            "text": f"「{category}」应纳入哪一项文档分类取值？", "options": options}


def apply_dictionary_answers(draft, base_fields, related_fields, answers):
    """Rebind a selected document code even if the next model reply repeats the invalid range."""
    intent = draft.get("semantic_intent")
    if not isinstance(intent, dict) or not isinstance(intent.get("scopes"), list):
        return
    for answer in answers:
        parts = answer.get("question_id", "").split("/")
        if len(parts) != 5 or parts[0] != "dictionary" or parts[2] not in ("base", "related"):
            continue
        _, table_id, role, raw_fields, signature = parts
        if sha256(answer.get("context", "").encode()).hexdigest()[:12] != signature:
            continue
        offered_fields = raw_fields.split(",")
        for field in base_fields if role == "base" else related_fields:
            name = field["field_name"]
            if (str(field.get("table_id")) != table_id or str(field.get("id", name)) not in offered_fields
                    or f"（{name}=" not in answer.get("answer", "")):
                continue
            try:
                codes = _document_codes(field)
            except _Unbound:
                continue
            for code, label in codes.items():
                caption = label if list(codes.values()).count(label) == 1 else f"{label}（{code}）"
                receipt = f"{caption}（{name}={code}）"
                if answer["answer"] not in (receipt, f"{field.get('field_cn') or name}·{receipt}"):
                    continue
                candidates = [scope for scope in intent["scopes"] if isinstance(scope, dict) and scope.get("table", "base") == role
                              and isinstance(scope.get("fields"), list) and name in scope["fields"]]
                if len(candidates) > 1:
                    candidates = [scope for scope in candidates if scope.get("category") == answer.get("context")]
                    if len(candidates) != 1:
                        continue
                scope = candidates[0] if candidates else {}
                if not candidates:
                    intent["scopes"].append(scope)
                scope.update(table=role, fields=[name], category=caption,
                             memberships={name: {"include": [code], "exclude": [v for v in codes if v != code]}})
                scope.pop("recommended", None)
                scope.pop("ambiguous_document_label", None)
                filters = draft.get("filters")
                for item in filters if isinstance(filters, list) else ():
                    if (isinstance(item, dict) and item.get("table", "base") == role and item.get("field") == name
                            and item.get("op") in ("eq", "in", "neq", "not_in")):
                        item.update(op="eq", value=code)
                break


def _code_key(value, numeric):
    if type(value) not in (int, float, str):
        return None
    if numeric:
        try:
            number = Decimal(str(value))
            return number if number.is_finite() else None
        except InvalidOperation:
            return None
    return str(value)


def _scope_options(scope, roles, snapshots):
    options = []
    names = _choice(scope, "category")
    role = scope.get("table", "base")
    if role not in ("base", "related"):
        raise _Unbound("分类字段的所属表无效。")
    fields = roles[role]
    memberships = scope.get("memberships")
    if not isinstance(memberships, dict) or set(memberships) != set(names):
        raise _Unbound(f"请补全「{scope['category']}」各候选字段包含和排除的字典码。")
    for name in names:
        field = fields.get(name)
        if not field:
            raise _Unbound(f"当前文档缺少分类字段 {name}，请核对字段归属。")
        codes = _document_codes(field)
        ambiguous = scope.get("ambiguous_document_label")
        if ambiguous and list(codes.values()).count(ambiguous) > 1:
            raise _Unbound(f"「{ambiguous}」对应多个字典取值，请选择适用的文档分类。")
        partition = memberships[name]
        if not isinstance(partition, dict) or set(partition) != {"include", "exclude"}:
            raise _Unbound(f"请补全 {name} 的字典码分组。")
        numeric = type_family(field.get("data_type")) == "number"
        by_spelling = {_code_key(code, numeric): code for code in codes}
        groups = {}
        for key in ("include", "exclude"):
            group = _items(partition[key], MAX_IN_VALUES if key == "include" else len(codes))
            selected = set()
            for value in group:
                code = by_spelling.get(_code_key(value, numeric))
                if code is None or code in selected:
                    raise _Unbound(f"请核实 {name} 的未知或重复分类码。")
                selected.add(code)
            groups[key] = selected
        included, excluded = groups["include"], groups["exclude"]
        if not included or included & excluded or included | excluded != set(codes):
            raise _Unbound(f"请将 {name} 的所有字典码完整分为属于和不属于「{scope['category']}」的两组。")
        category = scope["category"].strip()
        if any(code not in included for code, label in codes.items() if label == category):
            raise _Unbound(f"请核实 {name} 的分类分组，必须包含与「{category}」完全相符的字典取值。")
        for negative_code, label in codes.items():
            # Only compare a documented opposite with its actual positive peer.
            # Terms inside either label by themselves do not establish a partition.
            for match in re.finditer(r"非|未|不", label):
                prefix, term = label[:match.start()], label[match.end():]
                if len(term) < 2 or term not in category:
                    continue
                positive = {code for code, text in codes.items() if text == prefix + term}
                if not positive:
                    continue
                opposite = match.group() + term
                negative_wanted = opposite in category
                positive_wanted = term in category.replace(opposite, "")
                if ((negative_wanted and not positive_wanted and positive & included)
                        or (positive_wanted and not negative_wanted and negative_code in included)):
                    raise _Unbound(f"请核实 {name} 的分类分组，所选字典码与「{scope['category']}」的正反含义相反。")
        snapshots.setdefault(role, {})[name] = [{"value": code, "label": codes[code]}
                                                for code in sorted(codes, key=str)]
        values = [code for code in codes if code in included]
        selection = {"table": role, "field": name, "op": "in" if len(values) > 1 else "eq",
                     "value": values if len(values) > 1 else values[0], "confirmed": True}
        options.append({"value": str(len(options)), "label": f"{field.get('field_cn') or name}（{name}），"
                        + "、".join(f"{value}={codes[value]}" for value in values),
                        "selection": selection, **({"tag": "模型建议"} if scope.get("recommended") == name else {})})
    return options


def _explicit_filter(raw, roles):
    if not isinstance(raw, dict):
        raise _Unbound("模型给出的筛选条件格式不完整，请重新分析。")
    role, name = raw.get("table", "base"), raw.get("field")
    field = roles.get(role, {}).get(name) if isinstance(role, str) and isinstance(name, str) else None
    if not field:
        raise _Unbound(f"请核实模型筛选字段 {name} 在所选表中的归属。")
    # Reuse the SQL contract's shape and type validation, with the table already resolved.
    try:
        item, = validate_query_spec({"filters": [{**raw, "table": "base", "confirmed": True}]})["filters"]
        _validate_filter_value(item, field.get("data_type"))
    except (AppError, TypeError):
        raise _Unbound(f"请核实 {name} 的筛选操作及取值类型。") from None
    item["table"] = role
    dictionary = str(field.get("dictionary") or "").strip()
    if dictionary and item["op"] not in UNARY_OPS | TEXT_FILTER_OPS:
        codes = _document_codes(field)
        values = item["value"] if isinstance(item["value"], list) else [item["value"]]
        if any(value not in codes for value in values):
            raise _Unbound(f"请核实 {name} 的筛选取值是否属于当前字典。")
    return item


def _conditions(expression):
    if not isinstance(expression, dict):
        raise _Unbound("请明确要检查的字段和异常条件。")
    rows = expression.get("conditions", [expression])
    if not _items(rows, MAX_CONDITIONS) or not all(isinstance(row, dict) for row in rows):
        raise _Unbound("请核实模型给出的比较条件。")
    return rows


def _metric_slot(row, item):
    """Locate an operand field or a field leaf inside its arithmetic tree."""
    side = item["side"]
    path = item.get("formula_path")
    if row.get(side + "_type") != "formula":
        if path is not None:
            raise _Unbound("公式指标位置与比较操作数不一致。")
        return row, side
    if not isinstance(path, list) or not path:
        raise _Unbound("请明确该指标对应的公式字段位置。")
    node = row.get(side)
    for step in path:
        if step not in ("left", "right") or not isinstance(node, dict):
            raise _Unbound("公式指标位置无效。")
        node = node.get(step)
    if not isinstance(node, dict) or set(node) != {"field"}:
        raise _Unbound("该位置不是公式的字段操作数。")
    return node, "field"


def _metric_bindings(metrics, expression, roles):
    rows = _conditions(expression)
    claimed = set()
    for item in metrics:
        names = _choice(item, "term")
        side = item.get("side")
        if side not in ("left", "right"):
            raise _Unbound("指标口径缺少表达式位置。")
        index = item.get("condition_index")
        if index is not None and (type(index) is not int or not 0 <= index < len(rows)):
            raise _Unbound("指标口径指向的比较条件不存在。")
        targets = []
        for i, row in enumerate(rows):
            if index is not None and i != index:
                continue
            if side == "right" and (row.get("op") in UNARY_OPS or row.get("right_type") == "value"):
                continue
            try:
                slot, key = _metric_slot(row, item)
            except _Unbound:
                if index is None and len(rows) > 1:
                    continue
                raise
            if index is None and len(rows) > 1 and slot.get(key) not in [*names, item["term"]]:
                continue
            role = row.get("right_table", "base") if side == "right" else "base"
            location = (i, side, tuple(item.get("formula_path", ())))
            if location in claimed or (targets and role != targets[0][1]):
                raise _Unbound("模型给出的指标口径重叠或跨越了不同的表，请核实。")
            claimed.add(location)
            targets.append((i, role))
        if not targets:
            raise _Unbound(f"请明确「{item['term']}」用于哪个比较条件。")
        fields = roles.get(targets[0][1], {})
        available = [name for name in names if name in fields]
        if not available:
            raise _Unbound(f"请核实「{item['term']}」对应的活动文档字段。")
        yield item, available, fields, [i for i, _ in targets]


def _bind_metrics(candidate, metrics, roles):
    expression = candidate["expression"]
    rows = _conditions(expression)
    bindings = list(_metric_bindings(metrics, expression, roles))
    ambiguous_count = sum(len(names) > 1 for _, names, _, _ in bindings)
    for metric, names, fields, indices in bindings:
        side = metric["side"]
        suffix = "." + ".".join([*metric["formula_path"], "field"]) if "formula_path" in metric else ""
        paths = [(f"expression.conditions.{i}.{side}" if "conditions" in expression else f"expression.{side}") + suffix
                 for i in indices]
        recommended = metric.get("recommended")
        slot, key = _metric_slot(rows[indices[0]], metric)
        current = slot.get(key)
        chosen = recommended if recommended in names else current if current in names else names[0]
        rule_names = metric.get("rule_names", {}) if ambiguous_count == 1 and len(names) > 1 else {}
        if rule_names.get(chosen):
            candidate["rule_name"] = rule_names[chosen].strip()
        for i in indices:
            slot, key = _metric_slot(rows[i], metric)
            slot[key] = chosen
        questions = candidate["questions"]
        questions[:] = [q for q in questions if q["id"] not in paths]
        if len(names) > 1:
            text = f"「{metric['term']}」采用哪个指标字段？"
            options = [{"value": name, "label": f"{fields[name].get('field_cn') or name}（{name}）",
                        **({"rule_name": rule_names[name].strip()} if rule_names.get(name) else {}),
                        **({"tag": "模型建议"} if name == recommended else {})} for name in names]
            questions.append({"id": paths[0], "text": text, "uncertainty": text, "options": options,
                              **({"targets": paths} if len(paths) > 1 else {})})
            candidate["uncertainties"].append(text)


def _roles(base, related):
    return {role: {field["field_name"]: field for field in fields}
            for role, fields in (("base", base), ("related", related))}


def without_period_join_key(join, base_fields, related_fields):
    """Compare join facts without an equality already imposed by both reporting dates."""
    if not isinstance(join, dict) or not isinstance(join.get("on"), list) or join.get("right_aggregate"):
        return join
    left, _ = resolve_report_date(base_fields)
    right, _ = resolve_report_date(related_fields, join.get("report_date_field"))
    if not left or not right or right != join.get("report_date_field"):
        return join
    pair = {"left": left, "right": right}
    return {**join, "on": [item for item in join["on"] if item != pair]}


def join_decisions_refine(previous, current, *, base_fields=(), related_fields=()):
    """Complete undecided execution choices without changing the join's established meaning."""
    previous = without_period_join_key(previous, base_fields, related_fields)
    current = without_period_join_key(current, base_fields, related_fields)
    def same(left, right):
        return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return same(previous, current)
    decisions = {"relationship_confirmed", "unmatched_policy"}
    if not same({k: v for k, v in previous.items() if k not in decisions},
                {k: v for k, v in current.items() if k not in decisions}):
        return False
    before, after = previous.get("relationship_confirmed", False), current.get("relationship_confirmed", False)
    if type(before) is not bool or type(after) is not bool or before and not after:
        return False
    old_policy = previous.get("unmatched_policy") or "unresolved"
    new_policy = current.get("unmatched_policy") or "unresolved"
    resolved = ("review", "exclude") if current.get("right_aggregate") == "sum" else ("exclude",)
    return (old_policy in ("unresolved", *resolved) and new_policy in ("unresolved", *resolved)
            and (old_policy == "unresolved" or old_policy == new_policy))


def _verify_join(join, roles):
    allowed = {"table_name", "on", "report_date_field", "unmatched_policy", "relationship_confirmed", "right_aggregate"}
    if (not isinstance(join, dict) or join.keys() - allowed or not isinstance(join.get("table_name"), str)
            or join.get("right_aggregate") not in (None, "sum") or not roles["related"]):
        raise _Unbound("请核实关联表、汇总方式和关联条件结构。")
    pairs = _items(join.get("on"), MAX_JOIN_KEYS)
    if not pairs:
        raise _Unbound("请提供主表与关联表的对应字段。")
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != {"left", "right"}:
            raise _Unbound("请提供完整的一对关联字段。")
        if not all(isinstance(name, str) for name in pair.values()):
            raise _Unbound("请提供关联字段的真实物理名称。")
        left = type_family(roles["base"].get(pair["left"], {}).get("data_type"))
        right = type_family(roles["related"].get(pair["right"], {}).get("data_type"))
        if not left or left != right:
            raise _Unbound("关联字段需存在于各自的表，且类型一致。")
    if "relationship_confirmed" in join and type(join["relationship_confirmed"]) is not bool:
        raise _Unbound("关联关系的分析结论必须是明确的布尔值。")
    policy = join.get("unmatched_policy")
    allowed_policies = (None, "unresolved", "review", "exclude") if join.get("right_aggregate") else (None, "unresolved", "exclude")
    if policy not in allowed_policies:
        raise _Unbound("所选缺关联记录的处理方式不适用于当前关联，请核实。")
    period = join.get("report_date_field")
    if period not in (None, "") and (not isinstance(period, str)
            or base_type(roles["related"].get(period, {}).get("data_type")) != "date"):
        raise _Unbound("模型选择的关联日期必须来自关联表中真实的 DATE 字段。")


def ground_semantic_candidate(candidate, draft, base_fields, related_fields):
    """Bind choices and filters in place. Preserve a structural baseline for preview and save."""
    candidate.setdefault("questions", [])
    notes = candidate.setdefault("uncertainties", [])
    intent = draft.get("semantic_intent", {})
    try:
        if not isinstance(intent, dict) or intent.keys() - {"metrics", "scopes", "open_questions"}:
            raise _Unbound("模型给出的结构化语义格式不完整，请重新分析。")
        intent = deepcopy(intent)
        metrics = _items(intent.get("metrics", []), None if has_arithmetic(candidate.get("expression")) else 2 * MAX_CONDITIONS)
        scopes = _items(intent.get("scopes", []), MAX_FILTERS)
        open_questions = _items(intent.get("open_questions", []), 100)
        if not all(isinstance(q, str) and q.strip() for q in open_questions):
            raise _Unbound("模型给出的待确认事项格式不完整。")
        notes.extend(open_questions)
        roles = _roles(base_fields, related_fields if draft.get("join") else [])
        _bind_metrics(candidate, metrics, roles)
        raw_filters = list(_items(draft.get("filters", []), MAX_FILTERS))
        filters = []
        snapshots = {}
        candidate["filters"] = filters
        for scope in scopes:
            options = _scope_options(scope, roles, snapshots)
            role = scope.get("table", "base")
            names = {o["selection"]["field"] for o in options}
            suggestions = [raw for raw in raw_filters if isinstance(raw, dict) and raw.get("table", "base") == role
                           and isinstance(raw.get("field"), str) and raw["field"] in names]
            if len(suggestions) > 1 or any(item.get("op") not in ("eq", "in") for item in suggestions):
                raise _Unbound(f"请核对「{scope['category']}」的分类范围与同一字段上的额外筛选。")
            for suggestion in suggestions:
                selection = next(o["selection"] for o in options if o["selection"]["field"] == suggestion["field"])
                values = selection["value"] if selection["op"] == "in" else [selection["value"]]
                numeric = type_family(roles[role][selection["field"]].get("data_type")) == "number"
                included = {_code_key(code, numeric) for code in values}
                proposed = suggestion.get("value") if suggestion["op"] == "in" else [suggestion.get("value")]
                if (not isinstance(proposed, list) or not proposed or
                        any(_code_key(value, numeric) not in included for value in proposed)):
                    raise _Unbound(f"请核对「{scope['category']}」的分类分组与模型提出的筛选码值。")
                raw_filters.remove(suggestion)
            selected = next((o for o in options if o.get("tag")), options[0])
            if len(options) > 1:
                text = f"「{scope['category']}」采用哪个筛选字段？"
                candidate["questions"].append({"id": f"filters.{len(filters)}", "text": text, "uncertainty": text,
                                               "options": options})
                notes.append(text)
            filters.append({**selected["selection"], "confirmed": len(options) == 1})
        explicit = [_explicit_filter(raw, roles) for raw in raw_filters]
        filters.extend(explicit)
        if len(filters) > MAX_FILTERS:
            raise _Unbound("筛选条件超过支持的数量，请拆分规则。")
        if draft.get("join") is not None:
            _verify_join(draft["join"], roles)
            bind_model_join(candidate, draft["join"], base_fields, related_fields, accept_model_decisions=True)
        intent.update(expected_expression=deepcopy(candidate["expression"]), explicit_filters=deepcopy(explicit),
                      dictionary_snapshots=snapshots)
        if candidate.get("join"):
            intent["expected_join"] = deepcopy(candidate["join"])
        candidate["semantic_intent"] = intent
    except _Unbound as exc:
        candidate.update(status="needs_clarification", preview_error=str(exc), can_enable=False)
        notes.append(str(exc))
    notes[:] = list(dict.fromkeys(notes))
    if candidate["questions"] or notes:
        candidate["can_enable"] = False


def align_project_driver_semantics(candidate, field_mapping):
    """Keep semantic obligations, choices and dictionary receipts on their final roles."""
    intent = candidate.get("semantic_intent")
    driver = candidate.get("project_driver")
    if not isinstance(intent, dict) or not isinstance(driver, dict):
        return
    intent = deepcopy(intent)
    for scope in intent.get("scopes", []):
        if scope.get("table", "base") != "base":
            continue
        names = scope.get("fields") or []
        if not names or not all(name in field_mapping for name in names):
            continue
        scope["table"] = "related"
        scope["fields"] = [field_mapping[name] for name in names]
        memberships = scope.get("memberships") or {}
        scope["memberships"] = {field_mapping[name]: deepcopy(memberships[name]) for name in names}
        if scope.get("recommended") in field_mapping:
            scope["recommended"] = field_mapping[scope["recommended"]]
        excluded = scope.get("excluded_fields") or {}
        scope["excluded_fields"] = {field_mapping.get(name, name): deepcopy(reason)
                                    for name, reason in excluded.items()}
    for item in intent.get("explicit_filters", []):
        if item.get("table", "base") == "base" and item.get("field") in field_mapping:
            item["table"] = "related"
            item["field"] = field_mapping[item["field"]]
    snapshots = deepcopy(intent.get("dictionary_snapshots") or {})
    base_snapshots = snapshots.get("base") or {}
    for name in list(base_snapshots):
        if name in field_mapping:
            snapshots.setdefault("related", {})[field_mapping[name]] = base_snapshots.pop(name)
    if not base_snapshots:
        snapshots.pop("base", None)
    intent["dictionary_snapshots"] = snapshots
    if candidate.get("join"):
        intent["expected_join"] = deepcopy(candidate["join"])
    intent["expected_project_driver"] = deepcopy(driver)
    candidate["semantic_intent"] = intent
    for question in candidate.get("questions") or []:
        for option in question.get("options") or []:
            selection = option.get("selection")
            if (isinstance(selection, dict) and selection.get("table", "base") == "base"
                    and selection.get("field") in field_mapping):
                selection["table"] = "related"
                selection["field"] = field_mapping[selection["field"]]


def _same_filter(current, expected):
    if current == expected:
        return True
    if not isinstance(current, dict) or expected.get("op") not in ("in", "not_in"):
        return False
    values = current.get("value")
    return (isinstance(values, list) and len(values) == len(expected["value"])
            and all(value in values for value in expected["value"])
            and {**current, "value": expected["value"]} == expected)


def semantic_coverage_issue(definition, intent, base_fields, related_fields):
    """Recheck each model obligation and document dictionary against the user's edited definition."""
    try:
        if not isinstance(intent, dict) or "expected_expression" not in intent or "explicit_filters" not in intent:
            return "缺少已核实的结构化口径，请重新分析。"
        notes = definition.get("uncertainties", [])
        answers = definition.get("uncertainty_resolutions", [])
        if not isinstance(notes, list) or not isinstance(answers, list):
            return "请核实各项业务问题的答复。"
        answered = {q for q, answer in zip(notes, answers)
                    if isinstance(q, str) and isinstance(answer, str) and answer.strip()}
        if any(question not in answered for question in _items(intent.get("open_questions", []), 100)
               if isinstance(question, str)):
            return "请保留并答复模型提出的待确认业务问题。"
        roles = _roles(base_fields, related_fields if definition.get("join") else [])
        expected = deepcopy(intent["expected_expression"])
        rows = _conditions(expected)
        actual_expression = definition.get("expression")
        actual = _conditions(actual_expression)
        if len(rows) != len(actual):
            return "请完整保留模型给出的各项检查条件。"
        for metric, names, _, indices in _metric_bindings(_items(intent.get("metrics", []), None if has_arithmetic(expected) else 2 * MAX_CONDITIONS),
                                                         expected, roles):
            side = metric["side"]
            selections = [_metric_slot(actual[i], metric) for i in indices]
            chosen = selections[0][0].get(selections[0][1])
            if chosen not in names or any(slot.get(key) != chosen for slot, key in selections):
                return f"请确认「{metric['term']}」对应的文档字段。"
            for i in indices:
                slot, key = _metric_slot(rows[i], metric)
                slot[key] = chosen
        if actual_expression != expected:
            return "比较条件与模型给出的结构化口径不一致。"
        expected_driver = intent.get("expected_project_driver")
        if ((expected_driver is None) != ("project_driver" not in definition)
                or expected_driver is not None and expected_driver != definition.get("project_driver")):
            return "项目驱动侧与已核实的文档口径不一致，请重新分析。"
        baseline_join = intent.get("expected_join") or {}
        actual_join = definition.get("join") or {}
        if (baseline_join.get("table_name") != actual_join.get("table_name")
                or any(baseline_join.get(key) and baseline_join[key] != actual_join.get(key)
                       for key in ("on", "report_date_field", "right_aggregate"))):
            return "关联表或关联条件与已核实的文档口径不一致。"
        remaining = list(_items(definition.get("filters", []), MAX_FILTERS))
        snapshots = {}
        expected_filters = [[o["selection"] for o in _scope_options(scope, roles, snapshots)]
                            for scope in _items(intent.get("scopes", []), MAX_FILTERS)]
        if intent.get("dictionary_snapshots", {}) != snapshots:
            return "活动文档中的字典码或含义已有变化，请重新分析分类口径。"
        expected_filters.extend([_explicit_filter(item, roles)] for item in _items(intent["explicit_filters"], MAX_FILTERS))
        for options in expected_filters:
            for i, current in enumerate(remaining):
                if any(_same_filter(current, option) for option in options):
                    remaining.pop(i)
                    break
            else:
                return "请完整保留并确认模型口径对应的筛选字段和文档取值。"
        return "存在结构化口径未包含的额外筛选条件。" if remaining else ""
    except _Unbound as exc:
        return str(exc)
