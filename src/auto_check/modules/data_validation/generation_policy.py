"""Document ranking and durable review requirements for AI rule candidates."""
from __future__ import annotations

import re
from typing import Any

from .contracts import AppError
from .model_calls import failure

REVIEW_FIELDS = ("uncertainties", "uncertainty_resolutions", "unsupported_requirements")


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
    if re.search(r"一般|通常|原则上|例外|除外|除.+外", text):
        result.append("需求包含一般、通常或例外表述，请明确适用范围、允许的例外及其处理方式。")
    if "存续" in text:
        result.append("请依据文档确认存续范围的状态字段与对应状态码。")
    return result
