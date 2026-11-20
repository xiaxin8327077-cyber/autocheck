"""Prepare shared, document-scoped model analysis examples for retrieval."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from .query_spec import COMPARISON_OPS, FILTER_OPS, MAX_CONDITIONS, MAX_FILTERS, UNARY_OPS, is_finite_number


_CONTEXT_FIELDS = ("source_id", "source_name", "dialect", "doc_sha256", "doc_version", "model_id", "prompt_fingerprint", "knowledge_fingerprint")
_FLAGS = ("has_join", "has_alternatives", "unsupported", "unstructured_review", "requires_selection")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_EMBEDDED_DATA = re.compile(r"(?<![A-Za-z0-9_])(?:select\s|insert\s+into\s|update\s+\S+\s+set\s|delete\s+from\s|"
                            r"(?:create|drop|alter)\s+table\s)|```|\{\s*[\"'][^\"']+[\"']\s*:|[^\n\t]+\t[^\n\t]+\n", re.I)


def digest(value) -> str:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def context_key(context: dict) -> str:
    if not all(context.get(key) for key in ("source_id", "dialect", "doc_sha256", "doc_version")):
        return ""
    return digest({key: context.get(key) for key in _CONTEXT_FIELDS})


def request_keys(request: str) -> tuple[str, str]:
    # Threshold-insensitive lookup recalls examples only; it does not assign meaning to the new request.
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", request)).strip("。.!！?？")
    pattern = re.sub(r"(?<![a-zA-Z_0-9])-?\d+(?:\.\d+)?(?![a-zA-Z_0-9])", "#", normalized)
    return digest(normalized), digest(pattern)


def _identifier(value) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER.fullmatch(value))


def _comparison(raw, request: str) -> dict | None:
    if (not isinstance(raw, dict) or not _identifier(raw.get("left")) or not isinstance(raw.get("op"), str)
            or raw["op"] not in COMPARISON_OPS | UNARY_OPS):
        return None
    comparison = {"left": raw["left"], "op": raw["op"]}
    if raw["op"] in UNARY_OPS:
        return comparison
    right = raw.get("right")
    if raw.get("right_type", "field") == "field" and _identifier(right) and raw.get("right_table", "base") in ("base", "related"):
        return {**comparison, "right_type": "field", "right": right, "right_table": raw.get("right_table", "base")}
    if raw.get("right_type") != "value":
        return None
    comparison["right_type"] = "value"
    if is_finite_number(right) and re.search(r"(?<![\d.])" + re.escape(str(right)) + r"(?![\d.])", request):
        comparison["right"] = right
    return comparison


def safe_example(request: str, baseline: dict) -> dict | None:
    if (not isinstance(request, str) or not request.strip() or len(request) > 4000 or _EMBEDDED_DATA.search(request)
            or not isinstance(baseline, dict)):
        return None
    result = {}
    for key in ("table_name", "report_category", "rule_type"):
        value = baseline.get(key)
        if not isinstance(value, str) or len(value) > 128:
            return None
        if key != "report_category" and not _IDENTIFIER.fullmatch(value):
            return None
        if key == "report_category" and not re.fullmatch(r"[\w :-]*", value):
            return None
        result[key] = value
    for key in _FLAGS:
        if not isinstance(baseline.get(key), bool):
            return None
        result[key] = baseline[key]
    if "field_bindings" in baseline:
        bindings = baseline["field_bindings"]
        if not isinstance(bindings, list) or len(bindings) > 32:
            return None
        fields = set()
        for row in bindings:
            if not isinstance(row, dict) or row.get("role") not in ("metric", "scope", "join", "key", "date"):
                return None
            name, table = row.get("field"), row.get("table", "")
            if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name) or not isinstance(table, str) or (table and not _IDENTIFIER.fullmatch(table)):
                return None
            fields.add((row["role"], table, name))
        if fields:
            result["field_bindings"] = [{"role": role, "field": name, **({"table": table} if table else {})}
                                        for role, table, name in sorted(fields)]
    expression = baseline.get("expression")
    if isinstance(expression, dict) and expression:
        if "conditions" in expression:
            conditions = expression["conditions"]
            if expression.get("logic") not in ("any", "all") or not isinstance(conditions, list) or not 2 <= len(conditions) <= MAX_CONDITIONS:
                return None
            comparisons = [_comparison(item, request) for item in conditions]
            if not all(comparisons):
                return None
            result["expression"] = {"logic": expression["logic"], "conditions": comparisons}
        else:
            comparison = _comparison(expression, request)
            if not comparison:
                return None
            result["expression"] = comparison
    filters = baseline.get("filters")
    if filters:
        if not isinstance(filters, list) or len(filters) > MAX_FILTERS:
            return None
        bounded = []
        for item in filters:
            if (not isinstance(item, dict) or not _identifier(item.get("field")) or not isinstance(item.get("op"), str) or item["op"] not in FILTER_OPS
                    or item.get("table", "base") not in ("base", "related")):
                return None
            bounded.append({"table": item.get("table", "base"), "field": item["field"], "op": item["op"]})
        result["filters"] = bounded
    return result


def text_fragments(request: str) -> set[str]:
    text = re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", request).casefold())
    return {text[i:i + 2] for i in range(max(1, len(text) - 1))}


def example_signature(example: dict) -> dict:
    # Operand order in AND/OR groups and filter order do not create a distinct analysis.
    signature = dict(example)
    expression = example.get("expression", {})
    if "conditions" in expression:
        signature["expression"] = {**expression, "conditions": sorted(expression["conditions"], key=digest)}
    if "filters" in example:
        signature["filters"] = sorted(example["filters"], key=digest)
    return signature
