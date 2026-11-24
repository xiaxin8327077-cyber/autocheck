"""Check literal-text requirements against named document fields and model predicates."""
from __future__ import annotations

from collections import defaultdict
import re

from .document_evidence import _business_aliases, _label_forms
from .query_spec import TEXT_FILTER_OPS, type_family


_POLICY = re.compile(r"(不得|不能|不应|不可|禁止|必须|应当|应该|应|须)\s*(?:包含|含有|含)\s*")
_QUOTES = {'"': '"', "'": "'", '“': '”', '‘': '’', '「': '」'}
_QUOTED = re.compile("|".join(re.escape(a) + "[^" + re.escape(b) + "]*" + re.escape(b) for a, b in _QUOTES.items()))
_SEPARATOR = re.compile(r"\s*(?:(?:[，,]\s*)?(?:或者|或)|、|\|)\s*")
_CONNECTOR = re.compile(r"[\s，,；;]*(?:并且|而且|同时|并|且)?\s*$")
_TRAILER = re.compile(r"[\s。；;！!]*(?:[，,]\s*(?:请)?(?:核实|核查|复核|确认))?[\s。；;！!]*$")


def _literal_words(text):
    words = []
    pos = 0
    while pos < len(text):
        quoted = _QUOTED.match(text, pos)
        if quoted:
            word = quoted[0][1:-1]
            pos = quoted.end()
        else:
            token = re.match(r"(?:(?!或者|或|并且|而且|且|[、|，,。；;！!]).)+", text[pos:])
            if not token or any(c in token[0] for c in _QUOTES):
                return None
            word = token[0].strip()
            pos += token.end()
        if not word or len(word) > 200:
            return None
        words.append(word)
        if _TRAILER.fullmatch(text[pos:]):
            return list(dict.fromkeys(words)) if len(words) <= 50 else None
        separator = _SEPARATOR.match(text, pos)
        if not separator:
            return None
        pos = separator.end()
    return None


def _requirements(request, fields):
    # Mask quoted text at its original offsets; a phrase inside a quoted keyword is data.
    masked = _QUOTED.sub(lambda m: "\0" * len(m[0]), request)
    names = defaultdict(set)
    for f in fields:
        if type_family(f.get("data_type")) in ("string", "number"):
            for name in (f["field_name"], *_label_forms(f), *_business_aliases(f)):
                if name:
                    names[name.casefold()].add(f["field_name"])
    clauses = []
    for match in _POLICY.finditer(masked):
        prefix = masked[:match.start()].rstrip()
        subject = max((n for n in names if prefix.casefold().endswith(n)), key=len, default="")
        start = len(prefix) - len(subject)
        if subject:
            targets = names[subject]
        elif clauses and re.search(r"(?:[，,；;]|并且|而且|同时|并|且)$", prefix):
            targets = clauses[-1][2]
        else:
            targets = set()
        clauses.append((start, match, targets))
    for index, (start, match, targets) in enumerate(clauses):
        end = clauses[index + 1][0] if index + 1 < len(clauses) else len(request)
        if index + 1 < len(clauses):
            end = match.end() + _CONNECTOR.search(masked[match.end():end]).start()
        clause = masked[match.end():end]
        scope_end = re.search(r"(?:的(?:记录|数据|项目|行|对象)|时)\s*(?:[，,]|(?=" +
                              "|".join(re.escape(n) for n in names) + "))", clause, re.I) if names else None
        if scope_end and re.search("[，,。；;]", clause[:scope_end.start()]):
            scope_end = None
        words_end = match.end() + scope_end.start() if scope_end else end
        words = _literal_words(request[match.end():words_end])
        op = "not_contains_any" if match[1] in {"必须", "应当", "应该", "应", "须"} else "contains_any"
        yield targets, op, words, bool(scope_end)


def bind_text_predicates(draft, fields, request):
    """Return a repair reason when a named requirement is definitely missing or contradicted."""
    expression = draft.get("expression")
    if not isinstance(expression, dict):
        return None
    parts = expression.get("conditions", [expression])
    if not isinstance(parts, list):
        return None
    requirements = defaultdict(list)
    filters = draft.get("filters")
    filters = filters if isinstance(filters, list) else []
    predicates = [*parts, *filters]
    for targets, op, words, is_scope in _requirements(request, fields):
        if len(targets) == 1:
            field, = targets
            if is_scope:
                scope_op = "contains_any" if op == "not_contains_any" else "not_contains_any"
                if not any(isinstance(f, dict) and f.get("field") == field and f.get("table", "base") == "base"
                           and f.get("op") == scope_op and (words is None or isinstance(f.get("value"), list)
                           and set(map(str, f["value"])) == set(words)) for f in filters):
                    return f"请将字段 {field} 的文字前提按原文关键词和方向作为筛选条件。"
            else:
                requirements[field].append((op, words))
        elif not any(isinstance(p, dict) and p.get("op") in TEXT_FILTER_OPS for p in predicates):
            return "请核实原文所指的真实字段，并在规则中保留文字包含要求及关键词。"
    for field, checks in requirements.items():
        slots = [p for p in parts if isinstance(p, dict) and p.get("left") == field]
        if not slots:
            return f"请保留文档字段 {field} 的文字要求作为异常检查，筛选条件不能代替该项检查。"
        if len(checks) == len(slots) == 1 and len(parts) == 1 and checks[0][1]:
            op, words = checks[0]
            slots[0].clear()
            slots[0].update(left=field, op=op, right_type="value", right=words)
            draft["null_policy"] = "skip"
            continue
        available = list(slots)
        for op, words in checks:
            compatible = next((p for p in available if p.get("op") == op and isinstance(p.get("right"), list)
                               and (words is None or set(map(str, p["right"])) == set(words))), None)
            if compatible is None:
                return f"请保留字段 {field} 的各项文字包含要求、关键词和对应关系，分别生成完整条件。"
            available.remove(compatible)
    return None
