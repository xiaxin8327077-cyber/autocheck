"""Document ranking and durable review requirements for AI rule candidates."""
from __future__ import annotations

import re
from typing import Any

from .conditional_reviews import metric_choices
from .contracts import AppError
from .model_calls import failure
from .parallel_checks import number_comparison_prefix, parse_mixed_group, parse_number_comparison

REVIEW_FIELDS = ("uncertainties", "uncertainty_resolutions", "unsupported_requirements")
GENERAL_QUALIFIER = re.compile(r"一般|通常|原则上")
EXPLICIT_EXCLUSION = re.compile(r"例外|除外|除.+外|排除|剔除|不含|不包括")


def string_list(value: Any, *, stage: str = "") -> list[str]:
    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(item, str) or len(item) > 2000 for item in value):
        if stage:
            raise failure("MODEL_RESPONSE_INVALID", stage)
        raise AppError("VALIDATION_ERROR")
    return [item.strip() for item in value]


def issues(payload: dict[str, Any], key: str, *, stage: str) -> list[str]:
    values = string_list(payload.get(key, []), stage=stage)
    # Old templates used the singular key, sometimes returning a string.
    if key == "uncertainties" and "uncertainty" in payload:
        legacy = payload["uncertainty"]
        values += string_list([legacy] if isinstance(legacy, str) else legacy, stage=stage)
    return list(dict.fromkeys(item for item in values if item))


def merge(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for group in groups for item in group if item.strip()))


def validate_review(definition: dict[str, Any]) -> None:
    for key in REVIEW_FIELDS:
        if key in definition:
            definition[key] = string_list(definition[key])
    questions = definition.get("uncertainties", [])
    resolutions = definition.get("uncertainty_resolutions", [])
    if len(resolutions) > len(questions) or any(not item for item in questions):
        raise AppError("VALIDATION_ERROR")


def review_ready(definition: dict[str, Any]) -> bool:
    validate_review(definition)
    questions = definition.get("uncertainties", [])
    resolutions = definition.get("uncertainty_resolutions", [])
    from .query_spec import query_ready
    return (not definition.get("unsupported_requirements") and query_ready(definition)
            and len(resolutions) == len(questions) and all(resolutions))


def ai_review_pending(definition: dict[str, Any]) -> bool:
    """Business decisions needed before an AI candidate can be compiled."""
    return (bool(definition.get("questions"))
            or definition.get("null_policy", "unresolved") == "unresolved"
            or definition.get("equality_policy", "unresolved") == "unresolved"
            or not review_ready(definition))


def text_tokens(value: str) -> set[str]:
    text = str(value).lower()
    result = set(re.findall(r"[a-z_][a-z0-9_]*", text))
    for chunk in re.findall(r"[一-鿿]{2,}", text):
        for size in range(2, min(8, len(chunk)) + 1):
            result.update(chunk[offset:offset + size] for offset in range(len(chunk) - size + 1))
    return result


def shortlist_tables(tables: list[dict[str, Any]], request_text: str, limit: int) -> list[dict[str, Any]]:
    if len(tables) <= limit:
        return tables[:limit]
    wanted = text_tokens(request_text[:4000])
    def score(table: dict[str, Any]) -> int:
        name = f"{table.get('table_name') or ''} {table.get('table_name_cn') or ''}".lower()
        detail = f"{table.get('source_desc') or ''} {table.get('scope') or ''}".lower()[:2000]
        return sum(len(token) * (4 if token in name else 1) for token in wanted if token in name or token in detail)
    ranked = sorted(enumerate(tables), key=lambda item: (-score(item[1]), item[0]))
    return [table for _, table in ranked[:limit]]


def clarification_candidate(questions: list[str], unsupported: list[str], **context: Any) -> dict[str, Any]:
    return {
        **context, "rule_type": None, "expression": {}, "uncertainties": questions,
        "unsupported_requirements": unsupported, "uncertainty_resolutions": [],
        "verification_status": "not_run", "can_enable": False, "status": "needs_clarification",
    }


def request_reviews(text: str) -> list[str]:
    result = []
    if GENERAL_QUALIFIER.search(text) or re.search(r"例外|除外|除.+外", text):
        result.append("需求包含一般、通常或例外表述，请明确适用范围、允许的例外及其处理方式。")
    if "存续" in text:
        result.append("请依据文档确认存续范围的状态字段与对应状态码。")
    return result


def _known_limit_question(clause: str, names: list[str], op: str, value: int | float) -> bool:
    question = re.match(r"(?:需要?|请|待)?(?:确认|明确)?是否", clause)
    if not question:
        return False
    directions = set()
    for alternative in re.split(r"还是|或者|或", clause[question.end():]):
        term = re.sub(r"^(?:仅|只|还)?(?:需要?|应)?(?:检查|校验|核查)", "", alternative)
        for name in names:
            if term.startswith(name):
                term = term[len(name):]
                break
        term = term.removeprefix("是否")
        if term == "非空":
            continue
        predicate = parse_number_comparison("指标不得" + term)
        if not predicate or predicate[0] != ["指标"] or predicate[2] != value:
            return False
        directions.add(predicate[1])
    # Asking which side of the bound is the exception is answered by the violation predicate.
    complement = {"lt": "gte", "gte": "lt", "gt": "lte", "lte": "gt", "eq": "neq", "neq": "eq"}
    return op in directions and directions <= {op, complement[op]}


def remaining_qualifier_reviews(request: str, expression: dict, notes: list[str], *,
                                fields: list[dict] | None = None, subject: str = "") -> list[str]:
    """Remove only restatements of the manual exception policy for a grounded, explicit limit."""
    compact = re.sub(r"\s+", "", request).rstrip("。！？.!?")
    qualifier = GENERAL_QUALIFIER.search(compact)
    if not notes or not qualifier or EXPLICIT_EXCLUSION.search(compact):
        return notes
    tail = compact[qualifier.end():]
    parsed = number_comparison_prefix("指标" + tail)
    if not parsed or parsed[0] != ["指标"]:
        return notes
    _, op, value, remainder = parsed
    limit = tail.removesuffix(remainder)
    conditions = expression.get("conditions", [expression])
    numeric = [row for row in conditions if row.get("right_type") == "value"]
    if len(numeric) != 1 or (numeric[0].get("op"), numeric[0].get("right")) != (op, value):
        return notes
    mixed = parse_mixed_group(subject or compact)
    if remainder and not mixed:
        return notes
    names = []
    if mixed:
        field = numeric[0].get("left")
        if (mixed[0] != "any" or expression.get("logic") != "any" or len(conditions) != 2
                or len({term for term, _, _ in mixed[1]}) != 1
                or not any(row == {"left": field, "op": "is_null"} for row in conditions)):
            return notes
        term = mixed[1][0][0]
        documented = next((f for f in metric_choices(term, fields or []) if f["field_name"] == field), None)
        if fields and documented is None:
            return notes
        if documented:
            names = sorted({term, field, documented.get("field_cn") or field}, key=len, reverse=True)

    word = re.escape(qualifier[0])
    policy = re.compile(
        rf"(?:需求(?:中|中的)?)?(?:{word}{re.escape(limit)}(?:的|中)?(?:{word})?|{word})"
        r"(?:尚未|未|没有)(?:明确定义|明确|定义|说明)(?:(?:具体|合理)的?)?(?:例外|排除)(?:规则|条件|情形|情况)?"
    )
    decision = re.compile(r"(?:需(?:要)?|待|请)?(?:确认|明确)?是否(?:应|需要)?(?:将|把)(.+?)"
                          r"(?:作为|视为|列为)(?:异常|疑点)候选(?:记录)?(?:处理)?")
    threshold = re.compile(rf"(?:需求(?:中的?)?)?{word}{re.escape(limit)}的(?:校验|比较)?阈值(?:尚未|未)(?:明确|指定)")
    remaining = []
    for note in notes:
        parts = []
        changed = False
        reviewing_limit = False
        for part in re.finditer(r"([^，,；;。\n]+)([，,；;。\n]*)", note):
            clause = re.sub(r"""[\s“”‘’「」"'？?]""", "", part[1])
            match = decision.fullmatch(clause)
            stale = reviewing_limit and re.fullmatch(r"(?:当前|目前)(?:仅|只)实现了?非空(?:检查|校验)", clause)
            reviewing_limit = bool(names and (threshold.fullmatch(clause) or _known_limit_question(clause, names, op, value)))
            if (policy.fullmatch(clause) or (match and parse_number_comparison("指标不得" + match[1]) == parsed[:3])
                    or reviewing_limit or stale):
                changed = True
                continue
            parts.append(part[0])
        if not changed:
            remaining.append(note)
        elif parts:
            remaining.append("".join(parts).strip().rstrip("，,；;"))
    return list(dict.fromkeys(remaining))
