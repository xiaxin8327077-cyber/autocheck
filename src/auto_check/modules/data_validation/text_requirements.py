"""Bind directly named dictionary predicates to their documented physical values."""

from collections import defaultdict
from dataclasses import dataclass
import re

from .document_evidence import _business_aliases, _label_forms
from .semantic_grounding import _Unbound, _document_codes


_RELATION = re.compile(
    r"\s*(?P<modal>不应当?|不得|不能|不可|禁止|应当?|必须|须)?\s*"
    r"(?:已)?(?P<negative>并不|未|不)?\s*(?P<verb>并非|归类为|归[为入]|分类为|分为|等于|属于|标为|是|为|!=|<>|≠|=)"
    r"\s*['\"‘“「]?"
)
_END = re.compile(r"['\"’”」]?\s*(?:$|[，,。；;！？!?]|的|时|则|且|并且)")


@dataclass(frozen=True)
class _Predicate:
    label: str
    value: object
    negative: bool
    violation_op: str | None


def _named_predicates(request, roles):
    lowered = request.lower()
    names = defaultdict(set)
    for role, fields in roles.items():
        for field in fields:
            key = (role, field["field_name"])
            for term in (field["field_name"], *_label_forms(field), *_business_aliases(field)):
                if term and term.lower() in lowered:
                    names[term.lower()].add(key)
    if not names:
        return {}
    mentions = re.compile("|".join(re.escape(term) for term in sorted(names, key=len, reverse=True)), re.IGNORECASE)
    facts = defaultdict(set)
    field_map = {(role, field["field_name"]): field for role, fields in roles.items() for field in fields}
    for mention in mentions.finditer(request):
        keys = names[mention[0].lower()]
        relation = _RELATION.match(request, mention.end())
        if not relation or len(keys) != 1:
            continue
        key, = keys
        if not field_map[key].get("dictionary"):
            continue
        try:
            codes = _document_codes(field_map[key])
        except _Unbound:
            continue
        following = request[relation.end():]
        matches = [(code, label) for code, label in codes.items() if following.startswith(label)
                   and _END.match(following, len(label))]
        if not matches or len({label for _, label in matches}) != 1:
            facts[key].add(None)
            continue
        value, label = matches[0]
        if len(matches) > 1:
            value = None
        negative = bool(relation["negative"]) or relation["verb"] in {"并非", "!=", "<>", "≠"}
        violation_op = None
        if relation["modal"]:
            prohibition = relation["modal"] in {"不应", "不应当", "不得", "不能", "不可", "禁止"}
            violation_op = "eq" if prohibition != negative else "neq"
        facts[key].add(_Predicate(label, value, negative, violation_op))
    return {key: (next(iter(values)), _document_codes(field_map[key])) for key, values in facts.items()
            if len(values) == 1 and None not in values}


def bind_named_dictionary_requirements(draft, base_fields, related_fields, request):
    """Only replace a predicate when the request identifies one field and one dictionary entry."""
    facts = _named_predicates(request, {"base": base_fields, "related": related_fields}) if request else {}
    if not facts:
        return
    expression = draft.get("expression")
    conditions = expression.get("conditions", [expression]) if isinstance(expression, dict) else []
    for item in conditions if isinstance(conditions, list) else ():
        if (not isinstance(item, dict) or not isinstance(item.get("left"), str) or item.get("right_type") != "value"
                or item.get("op") not in ("eq", "neq")):
            continue
        binding = facts.get(("base", item["left"]))
        if binding and binding[0].value is not None:
            fact, _ = binding
            item["right"] = fact.value
            if fact.violation_op:
                item["op"] = fact.violation_op

    intent = draft.get("semantic_intent")
    scopes = intent.get("scopes") if isinstance(intent, dict) else None
    for scope in scopes if isinstance(scopes, list) else ():
        if not isinstance(scope, dict) or not isinstance(scope.get("fields"), list) or len(scope["fields"]) != 1:
            continue
        name, = scope["fields"]
        role = scope.get("table", "base")
        binding = facts.get((role, name)) if isinstance(name, str) and isinstance(role, str) else None
        if not binding:
            continue
        fact, codes = binding
        if fact.violation_op:
            continue
        if fact.value is None:
            scope["ambiguous_document_label"] = fact.label
            continue
        others = [code for code in codes if code != fact.value]
        included, excluded = (others, [fact.value]) if fact.negative else ([fact.value], others)
        if included:
            scope["category"] = "、".join(codes[code] for code in included)
            scope["memberships"] = {name: {"include": included, "exclude": excluded}}
    filters = draft.get("filters")
    for raw in filters if isinstance(filters, list) else ():
        if not isinstance(raw, dict) or raw.get("op") not in ("eq", "neq", "in", "not_in"):
            continue
        role, name = raw.get("table", "base"), raw.get("field")
        binding = facts.get((role, name)) if isinstance(role, str) and isinstance(name, str) else None
        if binding:
            fact, codes = binding
            if not fact.violation_op and fact.value is not None:
                values = [code for code in codes if (code == fact.value) != fact.negative]
                if values:
                    raw.update(op="eq" if len(values) == 1 else "in", value=values[0] if len(values) == 1 else values)
