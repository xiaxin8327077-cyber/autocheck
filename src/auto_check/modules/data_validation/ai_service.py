"""把自然语言要求变成结构化候选。模型不可用时不写规则。

规则名称、目标表与监管报送分类由模型自动生成：模型从数据源真实表清单与
报送导航分类中选定目标，服务层校验真实存在后才产出候选。
"""

from __future__ import annotations

import json
import math
from typing import Any

from .model_calls import failure
from .generation_policy import issues

from .contracts import AppError
from .query_spec import apply_numeric_null_policy
from .sql_guard import guard_sql

_PROMPT_VERSION = "data-validation-ai-v5"
_TABLE_LIST_LIMIT = 100


def parse_rule(
    user_text: str, *, tables: list[dict[str, Any]], categories: list[dict[str, Any]],
    model: Any, model_id: str = "",
) -> dict[str, Any]:
    """调用模型，从用户要求、数据源表清单与监管报送分类中生成候选。

    规则名称、目标表与监管报送分类均由模型自动选定。
    """
    prompt = (
        f"{user_text}\n数据源表清单：{json.dumps(tables, ensure_ascii=False)}"
        f"\n监管报送分类：{json.dumps(categories, ensure_ascii=False)}"
    )
    try:
        raw = model.complete(
            model_id,
            [{"role": "user", "content": prompt}],
            timeout_seconds=20,
        )
    except Exception as exc:
        raise AppError("MODEL_UNAVAILABLE") from exc
    try:
        candidate = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError("VALIDATION_ERROR") from exc
    if not isinstance(candidate, dict):
        raise AppError("VALIDATION_ERROR")
    target = candidate.get("target") or {}
    if not isinstance(target, dict):
        target = {}
    candidate["target"] = target
    return candidate


def refine_candidate(
    candidate: dict[str, Any], *, columns: list[dict[str, Any]], dialect: str, existing: list[dict[str, Any]],
    related_columns: list[dict[str, Any]] | None = None,
    source_id: str = "", table_name: str = "",
) -> dict[str, Any]:
    """用真实列结构精炼模型候选：字段别名匹配、SQL 守卫、重复检测。"""
    uncertainties = issues(candidate, "uncertainties", stage="generate_rule")
    unsupported = issues(candidate, "unsupported_requirements", stage="generate_rule")
    expression = candidate.get("expression")
    unary = isinstance(expression, dict) and expression.get("op") in ("is_null", "is_not_null")
    if (candidate.get("rule_type") != "field_compare" or not isinstance(expression, dict)
            or not isinstance(uncertainties, list) or not all(isinstance(item, str) for item in uncertainties)
            or not isinstance(expression.get("op"), str)
            or expression.get("op") not in {"lt", "lte", "gt", "gte", "eq", "neq", "is_null", "is_not_null"}
            or (not unary and (not isinstance(expression.get("right_type", "field"), str)
                               or expression.get("right_type", "field") not in {"field", "value"}))):
        raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    for key, allowed in (
        ("null_policy", {"unresolved", "skip", "violate", "empty_string_as_null", "zero", "review"}),
        ("equality_policy", {"unresolved", "allow_equal", "reject_equal"}),
    ):
        value = candidate.get(key) or "unresolved"
        if not isinstance(value, str) or value not in allowed:
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    for key in ("rule_name", "violation_message", "sql"):
        if candidate.get(key) is not None and not isinstance(candidate[key], str):
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    uncertainties = list(uncertainties)
    expression = {"left": expression.get("left"), "op": expression["op"]} if unary else dict(expression)
    is_value = expression.get("right_type") == "value"
    if is_value:
        value = expression.get("right")
        if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    questions = []
    for side in (("left",) if is_value or unary else ("left", "right")):
        label = expression.get(side)
        if not isinstance(label, str) or not label.strip():
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        right_table = expression.get("right_table", "base")
        if not isinstance(right_table, str) or right_table not in {"base", "related"} or (right_table == "related" and (is_value or not related_columns)):
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        side_columns = related_columns if side == "right" and right_table == "related" else columns
        matches = _match_columns(side_columns, label)
        if len(matches) == 1:
            expression[side] = matches[0]
        elif len(matches) > 1:
            uncertainties.append(f"{label} 对应多个字段，需要人工确认")
        else:
            uncertainties.append(f"{label} 不在文档字段中，需要人工确认")
        if len(matches) != 1:
            options = [column for column in side_columns if column["column_name"] in matches
                       or (not matches and label in str(column.get("comment") or ""))]
            if options:
                questions.append({"id": f"expression.{side}", "text": f"这里的“{label}”，你指哪个指标？",
                    "uncertainty": uncertainties[-1], "options": [{"value": column["column_name"],
                    "label": f"{column.get('comment') or column['column_name']}（{column['column_name']}）"} for column in options[:20]]})
    # 空值口径由服务端按真实文档证据推断，不依赖模型选择：数值缺省 review；
    # 仅字段文档明确 NULL=0 才 zero；日期/文本保持模型原 skip/unresolved。
    inferred = {} if unary else apply_numeric_null_policy(
        {
            "rule_type": candidate.get("rule_type"),
            "expression": expression,
            "null_policy": candidate.get("null_policy") or "unresolved",
        },
        columns=columns, related_columns=related_columns,
    )
    null_handling = inferred.get("null_handling")
    null_evidence = list(inferred.get("null_evidence") or [])
    sql_status = "candidate"
    error_code = ""
    sql_text = str(candidate.get("sql") or "")
    if sql_text:
        try:
            guard_sql(dialect, sql_text, {item["column_name"] for item in columns})
        except AppError as exc:
            sql_status = "rejected"
            error_code = exc.code
    # 相同比较关系不一定是同一条规则：必须同时核对来源与目标对象。
    duplicate = _duplicate(expression, existing, source_id=source_id, table_name=table_name)
    return {
        "rule_name": candidate.get("rule_name") or "未命名规则",
        "rule_type": candidate.get("rule_type"),
        "expression": expression,
        "violation_message": candidate.get("violation_message") or "",
        "null_policy": "violate" if unary else inferred.get("null_policy") or candidate.get("null_policy") or "unresolved",
        "null_handling": null_handling,
        "null_evidence": null_evidence,
        "equality_policy": "allow_equal" if unary else candidate.get("equality_policy") or "unresolved",
        "uncertainties": uncertainties,
        "unsupported_requirements": unsupported,
        "uncertainty_resolutions": [],
        "questions": questions,
        "duplicate": duplicate,
        "sql_status": sql_status,
        "verification_status": "not_run",
        "error_code": error_code,
        "can_enable": not uncertainties and not unsupported and sql_status != "rejected",
        "prompt_version": _PROMPT_VERSION,
    }


def table_list_limit() -> int:
    return _TABLE_LIST_LIMIT


def _match_columns(columns: list[dict[str, Any]], label: str) -> list[str]:
    found = []
    for column in columns:
        names = {str(column.get("column_name") or ""), str(column.get("comment") or "")}
        aliases = column.get("aliases") or []
        names.update(str(item) for item in aliases)
        if label in names:
            found.append(str(column["column_name"]))
    return found


def _duplicate(expression: dict[str, Any], existing: list[dict[str, Any]], *, source_id: str = "",
               table_name: str = "") -> dict[str, str]:
    def normalized(value: dict[str, Any]) -> dict[str, Any]:
        result = dict(value)
        if result.get("right_type") == "field":
            result.pop("right_type")
        return result

    partial: dict[str, str] | None = None
    for rule in existing:
        definition = rule.get("definition") or {}
        current = definition.get("expression") or {}
        not_current = not current or normalized(current) != normalized(expression)
        if not_current:
            continue
        same_target = (
            str(definition.get("source_id") or "") == str(source_id)
            and str(definition.get("table_name") or "") == str(table_name)
        )
        if same_target:
            return {"kind": "exact", "rule_code": str(rule.get("rule_code") or ""),
                    "evidence": "相同来源、对象、字段和比较关系"}
        if partial is None:
            partial = {
                "kind": "partial_overlap",
                "rule_code": str(rule.get("rule_code") or ""),
                "evidence": f"相同比较关系但对象不同：{definition.get('table_name') or '未知'} vs {table_name or '未知'}，粒度/口径可能不一致",
            }
    return partial or {"kind": "none", "rule_code": "", "evidence": ""}