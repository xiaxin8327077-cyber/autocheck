"""Conservative project-main-table parsing for independent numeric checks."""
from __future__ import annotations

from decimal import Decimal
import re
from typing import Any

from .query_spec import is_finite_number, type_family

_PREFIX = re.compile(r"(?:(?P<active>存续的?|仍存续的?)?(?:信托)?(?:项目维度|项目级|项目)(?:的|[：:，,])?)")
_VIOLATION_OP = {
    "小于等于": "lte", "大于等于": "gte", "小于": "lt", "低于": "lt",
    "大于": "gt", "高于": "gt", "超过": "gt", "超出": "gt", "等于": "eq", "为": "eq",
}
_NUMBER = r"-?\d{1,12}(?:\.\d{1,6})?"
_EMPHASIS = r"(?:(?:一定|务必|必须|应当|应该|需要|须|需)(?:要)?)?"
NONEMPTY_REQUIREMENT = rf"{_EMPHASIS}(?:(?:不得为|不能为?|不可为|不应为|不为|非)空(?:值)?|必填)"
_CONNECTOR = r"而且|并且|同时|且|并|或者|或"
_MIXED_SEPARATOR = rf"(?:[，,；;、]?(?P<link>{_CONNECTOR})[，,]?|[，,；;、])"
_NONEMPTY_CLAUSE = re.compile(rf"{NONEMPTY_REQUIREMENT}(?=[，,；;、]|{_CONNECTOR})")
_NONEMPTY_FIRST = re.compile(
    rf"(?P<term>\w{{1,80}}?){NONEMPTY_REQUIREMENT}{_MIXED_SEPARATOR}(?P<other>.+)"
)
_EMPTY_TAIL = re.compile(
    rf"{_MIXED_SEPARATOR}(?P<term>\w{{0,80}}?)"
    rf"(?:(?P<required>{NONEMPTY_REQUIREMENT})|(?:为|是)空(?:值)?)"
)
_ENDPOINTS = r"不?(?:包)?含(?:(?:两个)?(?:端点|边界)|两端)"
_RANGE = re.compile(
    rf"(?P<term>[\w]{{1,80}}?)(?:(?:必须|应当|应该|应|须|需)(?:处于|位于|介于|落在|在)|介于)"
    rf"(?P<low>{_NUMBER})(?:到|至|和|与|~|～|-)(?P<high>{_NUMBER})(?:之间|范围内|以内)?"
    rf"(?:[（(](?P<endpoints>{_ENDPOINTS})[）)]|[，,](?P<trailing_endpoints>{_ENDPOINTS}))?"
)
_REQUIRED_OP = {
    "大于等于": "lt", "小于等于": "gt", "不低于": "lt", "不少于": "lt", "不小于": "lt",
    "不高于": "gt", "不超过": "gt", "不大于": "gt", "大于": "lte", "高于": "lte",
    "小于": "gte", "低于": "gte", "等于": "neq",
}
_REQUIRED_OPERATOR = "|".join(_REQUIRED_OP)
_REQUIRED_COMPARISON = re.compile(rf"(?P<op>{_REQUIRED_OPERATOR})(?P<value>{_NUMBER})")
_REQUIRED_PAIR = re.compile(
    rf"(?P<term>\w{{1,80}}?)(?:必须|应当|应该|应|须|需)(?P<first>(?:{_REQUIRED_OPERATOR}){_NUMBER})"
    rf"(?P<link>并且|或者|且|或)(?:必须|应当|应该|应|须|需)?(?P<second>.+)"
)
_NUMERIC_PREDICATE = re.compile(
    rf"(?:一般|通常|原则上)?{_EMPHASIS}"
    r"(?:不得|不能|不应该|不应|不(?=小于|大于|超过|低于|高于))"
    rf"(?P<op>{'|'.join(_VIOLATION_OP)})(?P<value>{_NUMBER})"
)
_COMPARE = re.compile(r"(?P<terms>[\u4e00-\u9fffA-Za-z_0-9、，,和与及]{2,100}?)" + _NUMERIC_PREDICATE.pattern)
_COMPARISON_IN_TERM = re.compile(r"[<>≤≥≠=]|(?:大于|小于|低于|高于|超过|超出|等于|不少于|不多于|早于|晚于)")
# Short business terms are resolved only against documented labels on the project table.
# An unqualified asset is intentionally a clarification even with one known proposal.
_ALIASES = {"实收": ("实收信托",), "资产": ("资产大类科目余额", "总资产", "资产总额")}


def contains_check_predicate(term: str) -> bool:
    """Recognize an embedded predicate in text being considered as a field name."""
    if _NONEMPTY_CLAUSE.search(term) or re.search(r"(?:且|同时|或者|或|(?<!合)并)$", term):
        return True
    comparison = _COMPARISON_IN_TERM.search(term)
    # A documented name may itself specify an interval, e.g. 小于90天的贷款余额.
    return bool(comparison and re.search(r"且|同时|或|(?<!合)并|\d$", term[comparison.end():]))


def parse_number_comparison(text: str) -> tuple[list[str], str, int | float] | None:
    """返回明确写出的指标、违规比较符与常量，不接收附加范围或运算。"""
    compact = re.sub(r"\s+", "", text).rstrip("。！？.!?")
    comparison = _COMPARE.fullmatch(compact)
    if not comparison or _NUMERIC_PREDICATE.fullmatch(compact) or contains_check_predicate(comparison["terms"]):
        return None
    terms = re.split(r"[、，,和与及]", comparison["terms"])
    if not 1 <= len(terms) <= 3 or any(not term for term in terms) or len(set(terms)) != len(terms):
        return None
    value = Decimal(comparison["value"])
    constant = int(value) if value == value.to_integral_value() else float(value)
    if not is_finite_number(constant):
        return None
    return terms, _VIOLATION_OP[comparison["op"]], constant


def number_comparison_prefix(text: str) -> tuple[list[str], str, int | float, str] | None:
    """Locate a numeric comparison and retain any units or further conditions."""
    compact = re.sub(r"\s+", "", text).rstrip("。！？.!?")
    match = _COMPARE.match(compact)
    if match:
        comparison = parse_number_comparison(match[0])
        if comparison:
            return (*comparison, compact[match.end():])
    return None


def parse_mixed_group(text: str) -> tuple[str, list[tuple[str, str, int | float | None]]] | None:
    """Parse a null check combined with a numeric threshold, retaining their logical relationship."""
    compact = re.sub(r"\s+", "", text).rstrip("。！？.!?")
    first = _NONEMPTY_FIRST.fullmatch(compact)
    if first:
        term = first["term"]
        if contains_check_predicate(term):
            return None
        clause = first["other"]
        numeric = parse_number_comparison(term + clause if _NUMERIC_PREDICATE.fullmatch(clause) else clause)
        if numeric and len(numeric[0]) == 1:
            logic = "all" if (first["link"] or "").startswith("或") else "any"
            return logic, [(term, "is_null", None), (numeric[0][0], numeric[1], numeric[2])]
        return None
    numeric = number_comparison_prefix(compact)
    if numeric and len(numeric[0]) == 1:
        last = _EMPTY_TAIL.fullmatch(numeric[3])
        if last and (last["link"] or last["required"]) and not contains_check_predicate(last["term"]):
            term = numeric[0][0]
            either = (last["link"] or "").startswith("或")
            # Two independent requirements joined by 且 are violated by either failure.
            logic = "any" if either != bool(last["required"]) else "all"
            return logic, [(term, numeric[1], numeric[2]), (last["term"] or term, "is_null", None)]
    return None


def parse_numeric_group(text: str) -> tuple[str, list[tuple[str, str, int | float]]] | None:
    """Recognize a complete set of explicitly prohibited numeric comparisons."""
    compact = re.sub(r"\s+", "", text).rstrip("。！？.!?")
    interval = _RANGE.fullmatch(compact)
    if interval:
        term = interval["term"]
        exclusive = (interval["endpoints"] or interval["trailing_endpoints"] or "").startswith("不")
        return "any", [(term, "lte" if exclusive else "lt", float(interval["low"])),
                       (term, "gte" if exclusive else "gt", float(interval["high"]))]
    required = _REQUIRED_PAIR.fullmatch(compact)
    if required:
        parts = [_REQUIRED_COMPARISON.fullmatch(required[key]) for key in ("first", "second")]
        if all(parts):
            return ("all" if required["link"].startswith("或") else "any",
                    [(required["term"], _REQUIRED_OP[part["op"]], float(part["value"])) for part in parts])
    compact = re.sub(r"[，,；;](?=不)", "也", compact)
    compact = re.sub(r"[，,；;](?=也|并且|且|同时|或)", "", compact)
    clauses = re.split(r"(或者|或|并且|同时|且|也(?=不))", compact)
    if len(clauses) < 3:
        return None
    first = parse_number_comparison(clauses[0])
    if not first or len(first[0]) != 1:
        return None
    term = first[0][0]
    comparisons = [(term, first[1], first[2])]
    connectors = set()
    for connector, clause in zip(clauses[1::2], clauses[2::2]):
        repeated_prohibition = parse_number_comparison(clause) or parse_number_comparison(term + clause)
        parsed = repeated_prohibition or parse_number_comparison(f"{term}不得{clause}")
        if not parsed or len(parsed[0]) != 1:
            return None
        term = parsed[0][0]
        comparisons.append((term, parsed[1], parsed[2]))
        # 两项分别用“不得”限定时，各自违反其中任一要求就需核查。
        connectors.add("any" if connector.startswith("或") or repeated_prohibition else "all")
    if len(connectors) != 1:
        return None
    return connectors.pop(), comparisons


def project_parallel_checks(request: str, fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = re.sub(r"\s+", "", request)
    prefix = _PREFIX.match(text)
    if not prefix:
        return None
    comparison = parse_number_comparison(text[prefix.end():])
    if not comparison:
        return None
    terms, op, constant = comparison
    if len(terms) < 2:
        return None
    numbers = [field for field in fields if type_family(field.get("data_type")) == "number"]
    checks = []
    for term in terms:
        accepted = _ALIASES.get(term, ())
        exact = [field for field in numbers if term in (field.get("field_cn"), field.get("field_name"))]
        matches = exact or [field for field in numbers if field.get("field_cn") in accepted]
        # Unknown text must not conceal an additional condition or a different rule shape.
        if not matches and term not in _ALIASES:
            return None
        chosen = matches[0] if len(matches) == 1 and (term != "资产" or bool(exact)) else None
        checks.append({"term": term, "field": chosen, "options": matches})
    bound = [check["field"]["field_name"] for check in checks if check["field"]]
    if not bound or len(bound) != len(set(bound)):
        return None
    return {"checks": checks, "op": op, "constant": constant,
            "active": bool(prefix["active"])}
