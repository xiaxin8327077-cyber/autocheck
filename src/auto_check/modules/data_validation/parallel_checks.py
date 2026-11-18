"""Conservative project-main-table parsing for independent numeric checks."""
from __future__ import annotations

from decimal import Decimal
import re
from typing import Any

from .query_spec import is_finite_number, type_family

_PREFIX = re.compile(r"(?:(?P<active>存续的?|仍存续的?)?(?:信托)?(?:项目维度|项目级|项目)(?:的|[：:，,])?)")
_COMPARE = re.compile(r"(?P<terms>[\u4e00-\u9fffA-Za-z_0-9、，,和与及]{2,100}?)(?P<op>不得小于|不能小于|不小于|不得低于|不得大于|不能大于|不大于|不得高于|不得等于|不能等于|不得为|不能为)(?P<value>-?\d{1,12}(?:\.\d{1,6})?)")
_VIOLATION_OP = {
    "不得小于": "lt", "不能小于": "lt", "不小于": "lt", "不得低于": "lt",
    "不得大于": "gt", "不能大于": "gt", "不大于": "gt", "不得高于": "gt",
    "不得等于": "eq", "不能等于": "eq", "不得为": "eq", "不能为": "eq",
}
# Short business terms are resolved only against documented labels on the project table.
# An unqualified asset is intentionally a clarification even with one known proposal.
_ALIASES = {"实收": ("实收信托",), "资产": ("资产大类科目余额", "总资产", "资产总额")}


def project_parallel_checks(request: str, fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = re.sub(r"\s+", "", request).rstrip("。！？.!?")
    prefix = _PREFIX.match(text)
    if not prefix:
        return None
    comparison = _COMPARE.fullmatch(text[prefix.end():])
    if not comparison:
        return None
    terms = re.split(r"[、，,和与及]", comparison["terms"])
    if not 2 <= len(terms) <= 3 or any(not term for term in terms) or len(set(terms)) != len(terms):
        return None
    value = Decimal(comparison["value"])
    constant = int(value) if value == value.to_integral_value() else float(value)
    if not is_finite_number(constant):
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
    return {"checks": checks, "op": _VIOLATION_OP[comparison["op"]], "constant": constant,
            "active": bool(prefix["active"])}
