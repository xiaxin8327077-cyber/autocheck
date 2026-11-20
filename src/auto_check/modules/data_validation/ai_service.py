"""把自然语言要求变成结构化候选。模型不可用时不写规则。

规则名称、目标表与监管报送分类由模型自动生成：模型从数据源真实表清单与
报送导航分类中选定目标，服务层校验真实存在后才产出候选。
"""

from __future__ import annotations

from collections.abc import Collection
import json
from typing import Any

from .model_calls import failure
from .generation_policy import issues, merge, string_list
from .dictionary_reviews import dictionary_question_text

from .contracts import AppError
from .query_spec import COMPARISON_OPS, MAX_CONDITIONS, UNARY_OPS, apply_numeric_null_policy, is_condition_group, is_finite_number
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


def model_expression(raw: Any) -> Any:
    """Normalize equivalent boolean names without dropping part of an expression."""
    if not isinstance(raw, dict) or "conditions" not in raw:
        return raw
    key = "logic" if "logic" in raw else "op"
    logic = str(raw.get(key) or "").lower()
    if set(raw) == {key, "conditions"} and logic in {"or", "and", "any", "all"}:
        return {"logic": {"or": "any", "and": "all"}.get(logic, logic), "conditions": raw["conditions"]}
    return raw


def _dictionary_questions(payload: dict[str, Any], stage: str) -> tuple[list[dict[str, str]], list[str]]:
    rows = payload.get("dictionary_questions")
    if rows is None or rows == {} or (isinstance(rows, str) and not rows.strip()):
        return [], []
    if not isinstance(rows, list):
        rows = [rows]
    if len(rows) > 100:
        raise failure("MODEL_RESPONSE_INVALID", stage)
    labels = {"table": "表名", "field": "字段名", "category": "分类名称"}
    references, unbound = [], []
    for row in rows:
        if isinstance(row, str) and row.strip():
            string_list([row], stage=stage)
            unbound.append(f"字典取值需要核实：{row.strip()}")
            continue
        item = row if isinstance(row, dict) else {}
        if len(item) > 100:
            raise failure("MODEL_RESPONSE_INVALID", stage)
        string_list([v for v in item.values() if isinstance(v, str)], stage=stage)
        reference = {k: item[k].strip() for k in labels if isinstance(item.get(k), str) and item[k].strip()}
        if reference.keys() == item.keys() == labels.keys():
            if reference not in references:
                references.append(reference)
            continue
        known = "，".join(f"{labels[k]}“{v}”" for k, v in reference.items())
        missing = "、".join(label for k, label in labels.items() if k not in reference)
        reason = f"未提供{missing}" if missing else "附加说明尚未核实"
        context = f"（{known}）" if known else ""
        unbound.append(f"字典取值需要核实{context}，{reason}。")
        for k, value in item.items():
            if k not in labels and isinstance(value, str) and value.strip():
                unbound.append(value.strip())
    return references, unbound


def pending_judgment_reviews(judgment: dict[str, Any], *, table: str = "", fields: Collection[str] = (),
                             category: str = "") -> list[str]:
    """Return free text and dictionary questions outside the independently verified bindings."""
    text = judgment.get("text_uncertainties", judgment["uncertainties"])
    if isinstance(fields, str):
        fields = (fields,)
    pending = [
        dictionary_question_text(q)
        for q in judgment.get("dictionary_questions", [])
        if not (q["table"] == table and q["field"] in fields and q["category"] == category)
    ]
    return merge(text, pending)


def model_judgment(payload: dict[str, Any], *, stage: str) -> dict[str, Any]:
    """保留模型各阶段返回的业务判断，供分析结果查看。"""
    judgment = {key: issues(payload, key, stage=stage) for key in ("uncertainties", "unsupported_requirements")}
    questions, unbound = _dictionary_questions(payload, stage)
    judgment["uncertainties"] = merge(judgment["uncertainties"], unbound)
    if questions:
        judgment["dictionary_questions"] = questions
        judgment["text_uncertainties"] = judgment["uncertainties"]
        judgment["uncertainties"] = pending_judgment_reviews(judgment)
    if questions or unbound:
        string_list(judgment["uncertainties"], stage=stage)
    if stage == "select_table":
        target = payload.get("target")
        related = payload.get("related_target")
        fields = {
            "table": (target.get("table") if isinstance(target, dict) else None) or payload.get("table"),
            "related_table": related.get("table") if isinstance(related, dict) else None,
            "report_category": payload.get("report_category"),
        }
        judgment.update({key: value for key, value in fields.items() if isinstance(value, str) and value})
        return judgment

    def scalar(value: Any) -> bool:
        return (isinstance(value, str) and len(value) <= 2000) or is_finite_number(value)

    def safe_condition(condition):
        return {key: condition[key] for key in ("left", "op", "right_type", "right", "right_table")
                if key in condition and scalar(condition[key])}

    expression = model_expression(payload.get("expression"))
    if isinstance(expression, dict):
        if expression.get("logic") in ("any", "all") and isinstance(expression.get("conditions"), list):
            judgment["expression"] = {"logic": expression["logic"], "conditions": [
                safe_condition(item) for item in expression["conditions"][:MAX_CONDITIONS] if isinstance(item, dict)
            ]}
        else:
            judgment["expression"] = safe_condition(expression)
    filters = payload.get("filters")
    if isinstance(filters, list):
        safe_filters = []
        for condition in filters[:8]:
            if not isinstance(condition, dict):
                continue
            item = {key: condition[key] for key in ("table", "field", "op") if isinstance(condition.get(key), str)}
            value = condition.get("value")
            if value is None or scalar(value) or isinstance(value, list) and len(value) <= 50 and all(map(scalar, value)):
                item["value"] = value
            safe_filters.append(item)
        judgment["filters"] = safe_filters
    for key in ("rule_type", "null_policy"):
        if isinstance(payload.get(key), str):
            judgment[key] = payload[key]
    return judgment


def refine_candidate(
    candidate: dict[str, Any], *, columns: list[dict[str, Any]], dialect: str, existing: list[dict[str, Any]],
    related_columns: list[dict[str, Any]] | None = None,
    source_id: str = "", table_name: str = "", request_text: str = "",
) -> dict[str, Any]:
    """用真实列结构精炼模型候选：字段别名匹配、SQL 守卫、重复检测。"""
    uncertainties = issues(candidate, "uncertainties", stage="generate_rule")
    unsupported = issues(candidate, "unsupported_requirements", stage="generate_rule")
    raw = model_expression(candidate.get("expression"))
    if candidate.get("rule_type") != "field_compare" or not isinstance(raw, dict):
        raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    grouped = is_condition_group({"expression": raw})
    if grouped and (set(raw) != {"logic", "conditions"} or raw["logic"] not in ("any", "all")
                    or not isinstance(raw["conditions"], list) or not 2 <= len(raw["conditions"]) <= MAX_CONDITIONS):
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
    conditions = raw["conditions"] if grouped else [raw]
    bound = []
    questions = []
    answers = {}
    operands_bound = True
    model_choices = candidate.get("field_choices")
    choices_limit = 2 * MAX_CONDITIONS if grouped else 4
    choices_for_rule = model_choices[:choices_limit] if isinstance(model_choices, list) else []
    for index, condition in enumerate(conditions):
        choices = choices_for_rule
        if grouped:
            choices = [item for item in choices if isinstance(item, dict) and (
                item.get("condition_index") == index or
                ("condition_index" not in item and isinstance(condition, dict) and item.get("term")
                 and item["term"] == condition.get(str(item.get("side"))))
            )]
        result, pending, resolved = _bind_condition(condition, columns, related_columns, choices, uncertainties, grouped)
        operands_bound = operands_bound and resolved
        bound.append(result)
        for question in pending:
            if grouped:
                side = question["id"].split(".")[-1]
                target = f"expression.conditions.{index}.{side}"
                operand = (side, condition[side], condition.get("right_table", "base") if side == "right" else "base")
                shared = answers.get(operand)
                if shared and shared["options"] == question["options"]:
                    shared["targets"].append(target)
                    continue
                question.update(id=target, targets=[target])
                answers[operand] = question
            questions.append(question)
    expression = {"logic": raw["logic"], "conditions": bound} if grouped else bound[0]
    unary = not grouped and expression["op"] in UNARY_OPS
    uncertainties = list(dict.fromkeys(uncertainties))
    # 数值策略按需求、经绑定的比较条件与文档确定；日期和文本保留各自的策略。
    inferred = {} if unary or not operands_bound else apply_numeric_null_policy(
        {
            "rule_type": candidate.get("rule_type"),
            "expression": expression,
            "null_policy": candidate.get("null_policy") or "unresolved",
        },
        columns=columns, related_columns=related_columns, request_text=request_text,
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


def _bind_condition(expression, columns, related_columns, choices, uncertainties, grouped):
    resolved = True
    if not isinstance(expression, dict) or not isinstance(expression.get("op"), str):
        raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    op = expression["op"]
    unary = op in UNARY_OPS
    allowed = {"left", "op"} if unary else {"left", "op", "right", "right_type", "right_table"}
    if (op not in COMPARISON_OPS | UNARY_OPS or (grouped and set(expression) - allowed)
            or (not unary and expression.get("right_type", "field") not in ("field", "value"))):
        raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    expression = {"left": expression.get("left"), "op": expression["op"]} if unary else dict(expression)
    is_value = expression.get("right_type") == "value"
    if is_value and not is_finite_number(expression.get("right")):
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
        question = _field_choice_question(choices, side, side_columns)
        if len(matches) == 1:
            expression[side] = matches[0]
        elif len(matches) > 1:
            uncertainties.append(f"{label} 对应多个字段，需要人工确认")
        else:
            uncertainties.append(f"{label} 不在文档字段中，需要人工确认")
        if question is not None:
            if len(matches) != 1:
                question["uncertainty"] = uncertainties[-1]
                expression[side] = question["options"][0]["value"]
            questions.append(question)
        elif len(matches) != 1:
            options = [column for column in side_columns if column["column_name"] in matches
                       or (not matches and label in str(column.get("comment") or ""))]
            if options:
                questions.append({"id": f"expression.{side}", "text": f"这里的“{label}”，你指哪个指标？",
                    "uncertainty": uncertainties[-1], "options": [{"value": column["column_name"],
                    "label": f"{column.get('comment') or column['column_name']}（{column['column_name']}）"} for column in options[:20]]})
                if grouped:
                    expression[side] = options[0]["column_name"]
            else:
                resolved = False
    return expression, questions, resolved


def _field_choice_question(choices: list[Any], side: str, columns: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_name = {column["column_name"]: column for column in columns}
    for choice in choices:
        if not isinstance(choice, dict) or choice.get("side") != side or not isinstance(choice.get("fields"), list):
            continue
        names = list(dict.fromkeys(name for name in choice["fields"][:20] if isinstance(name, str) and name in by_name))
        if len(names) < 2:
            continue
        recommended = choice.get("recommended")
        term = str(choice.get("term") or "指标").strip()[:60]
        return {"id": f"expression.{side}", "text": f"这里的「{term}」指哪个字段？", "options": [
            {"value": name, "label": f"{by_name[name].get('comment') or name}（{name}）",
             **({"tag": "模型建议"} if name == recommended else {})} for name in names
        ]}
    return None


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
