"""Separate named text prerequisites from the condition that reports a violation."""
from collections import defaultdict
import re

from .document_evidence import _business_aliases, _label_forms
from .query_spec import TEXT_FILTER_OPS
from .request_text_predicates import _QUOTED, _TRAILER, _literal_words
from .text_requirements import _RELATION, _named_predicates


_SCOPE_ERROR = "请将“时”之前各项文字前提分别列为筛选条件，并只将其后的异常判定用于比较。"
_AND = re.compile(r"\s*(?:[，,]\s*)?(?:并且|而且|同时|且)\s*")


def _field_names(fields):
    names = defaultdict(set)
    for field in fields:
        for label in (field["field_name"], *_label_forms(field), *_business_aliases(field)):
            if label:
                names[label.lower()].add(field["field_name"])
    return names


def _filters(prefix, names, subject):
    # Offsets from the masked copy refer to the original text, including quoted pipes and conjunctions.
    masked = _QUOTED.sub(lambda m: "\0" * len(m[0]), prefix)
    if re.search(r"(?:或者|或)\s*(?:(?:" + subject + r")\s*)?不?(?:包含|含有|含)", masked, re.I):
        return None
    prefix_rule = re.compile(r"\s*(?P<subject>" + subject + r")?\s*(?P<neg>不)?(?:包含|含有|含)\s*", re.I)
    start = 0
    name = None
    filters = []
    for separator in [*_AND.finditer(masked), None]:
        end = separator.start() if separator else len(prefix)
        match = prefix_rule.match(masked, start, end)
        if not match:
            return None
        if match["subject"]:
            fields = names[match["subject"].lower()]
            if len(fields) != 1:
                return None
            name, = fields
        terms = _literal_words(prefix[match.end():end].strip())
        if not name or not terms:
            return None
        words = list(dict.fromkeys(word for term in terms for word in term.split("|")))
        if not all(words) or len(words) > 50:
            return None
        filters.append({"table": "base", "field": name, "op": "not_contains_any" if match["neg"] else "contains_any",
                        "value": words})
        if separator:
            start = separator.end()
    return filters


def _predicate_key(field, op, words):
    if (isinstance(field, str) and isinstance(op, str) and op in TEXT_FILTER_OPS and isinstance(words, list)
            and all(isinstance(w, str) for w in words)):
        return field, op, frozenset(words)
    return None


def bind_conditional_text_scopes(draft, fields, request):
    """Normalize a flat model group only when its text predicates match the stated prerequisites."""
    expr = draft.get("expression")
    if not isinstance(expr, dict) or "时" not in request:
        return
    rows = expr.get("conditions", [expr])
    if not isinstance(rows, list):
        return
    text_keys = {_predicate_key(row.get("left"), row.get("op"), row.get("right"))
                 for row in rows if isinstance(row, dict)}
    text_keys.discard(None)
    masked = _QUOTED.sub(lambda m: "\0" * len(m[0]), request)
    if "含" not in masked:
        return
    names = _field_names(fields)
    subject = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    if not subject:
        return
    unresolved = False
    for separator in re.finditer(r"时\s*[，,]?\s*", masked):
        suffix = request[separator.end():]
        target = re.match(subject, suffix, re.I)
        if "含" not in masked[:separator.start()]:
            continue
        prefix = re.sub(r"^\s*(?:如果|当|若)\s*", "", request[:separator.start()]).strip()
        written = _filters(prefix, names, subject)
        if written is None:
            # A more complex prerequisite must not be flattened into an OR with the outcome.
            if target and text_keys and expr.get("logic") == "any" and not draft.get("filters"):
                return _SCOPE_ERROR
            continue
        required = {_predicate_key(f["field"], f["op"], f["value"]) for f in written}
        if not target:
            unresolved |= bool(required & text_keys)
            continue
        scopes = {f["field"] for f in written}
        target_names = names[target[0].lower()]
        facts = _named_predicates(suffix, {"base": fields})
        fact = facts.get(("base", next(iter(target_names)))) if len(target_names) == 1 else None
        relation = _RELATION.match(suffix, target.end())
        sole_outcome = False
        if fact and relation and fact[0].value is not None:
            tail = suffix[relation.end():]
            sole_outcome = (tail.startswith(fact[0].label)
                            and _TRAILER.fullmatch(tail[len(fact[0].label):].lstrip("'’”」\"")) is not None)
        remaining = []
        for part in rows:
            if not isinstance(part, dict):
                return _SCOPE_ERROR
            key = _predicate_key(part.get("left"), part.get("op"), part.get("right"))
            if key not in required:
                remaining.append(part)
        filters = draft.get("filters", [])
        if not isinstance(filters, list):
            return _SCOPE_ERROR
        existing = set()
        for raw in filters:
            if not isinstance(raw, dict):
                return _SCOPE_ERROR
            if raw.get("table", "base") == "base" and isinstance(raw.get("field"), str) and raw["field"] in scopes:
                key = _predicate_key(raw["field"], raw.get("op"), raw.get("value"))
                if key not in required:
                    return _SCOPE_ERROR
                existing.add(key)
            elif sole_outcome:
                return "请仅保留原文中“时”之前明确的文字筛选，不要用异常结果字段缩小检查范围。"
        intent = draft.get("semantic_intent")
        if sole_outcome and isinstance(intent, dict) and intent.get("scopes"):
            return "请核实附加的分类筛选范围，原文仅以“时”之前的文字条件限定记录。"
        if not sole_outcome and len(remaining) == len(rows) and required <= existing:
            return
        if len(remaining) != 1:
            return _SCOPE_ERROR
        outcome, = remaining
        if not isinstance(outcome.get("left"), str) or target_names != {outcome["left"]}:
            return _SCOPE_ERROR
        if outcome.get("left") in scopes:
            return _SCOPE_ERROR
        if fact and fact[0].value is not None and (fact[0].negative or fact[0].violation_op):
            violation = fact[0].violation_op or "neq"
            if outcome.get("op") != violation or outcome.get("right_type") != "value" or outcome.get("right") != fact[0].value:
                return "请保留“时”之后所指文档字段、取值及对应的异常方向。"
        metrics = intent.get("metrics") if isinstance(intent, dict) else None
        if not isinstance(metrics, list):
            return _SCOPE_ERROR
        retained = []
        for metric in metrics:
            if (not isinstance(metric, dict) or not isinstance(metric.get("fields"), list)
                    or not all(isinstance(n, str) for n in metric["fields"])):
                return _SCOPE_ERROR
            choices = set(metric["fields"])
            if choices and choices <= scopes:
                continue
            if choices & scopes:
                return _SCOPE_ERROR
            retained.append({k: v for k, v in metric.items() if k != "condition_index"})
        draft["expression"] = outcome
        draft["filters"] = filters + [f for f in written if _predicate_key(f["field"], f["op"], f["value"]) not in existing]
        intent["metrics"] = retained
        return
    return _SCOPE_ERROR if unresolved else None
