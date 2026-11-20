"""字段比较规则的 filters/join 结构校验与就绪门禁。

本模块只校验结构与取值边界，不访问业务库。字段是否存在、类型是否匹配由
``validate_spec_against_columns`` 按活动文档列或执行期实际表结构复核。
"""

from __future__ import annotations

import datetime as _datetime
import math
import re
from typing import Any

from .contracts import AppError
from .project_context import normalize_project_context
from .project_driver import validate_project_driver, validate_project_driver_columns

BASE = "base"
RELATED = "related"

FILTER_OPS = frozenset({
    "eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in", "is_null", "is_not_null",
})
COMPARISON_OPS = frozenset({"eq", "neq", "lt", "lte", "gt", "gte"})
UNARY_OPS = frozenset({"is_null", "is_not_null"})
MAX_FILTERS = 8
MAX_CONDITIONS = 8
MAX_IN_VALUES = 50
MAX_JOIN_KEYS = 4
MAX_VALUE_LENGTH = 200

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_DATE_TYPES = {"date", "datetime", "timestamp", "time", "year"}
_NUMBER_TYPES = {
    "int", "integer", "bigint", "smallint", "tinyint", "mediumint", "bit",
    "decimal", "numeric", "float", "double", "double precision", "real", "money",
    "int2", "int4", "int8", "float4", "float8", "serial", "bigserial",
}
_STRING_TYPES = {
    "char", "varchar", "text", "tinytext", "mediumtext", "longtext",
    "enum", "set", "uuid", "character varying", "character", "bpchar",
}


def base_type(data_type: Any) -> str:
    return str(data_type or "").strip().lower().split("(", 1)[0].strip()


def type_family(data_type: Any) -> str:
    base = base_type(data_type)
    if base in _DATE_TYPES:
        return "date"
    if base in _NUMBER_TYPES:
        return "number"
    if base in _STRING_TYPES:
        return "string"
    return ""


def is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _fail() -> None:
    raise AppError("VALIDATION_ERROR")


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def is_condition_group(definition: dict[str, Any]) -> bool:
    expression = definition.get("expression")
    return isinstance(expression, dict) and ("conditions" in expression or "logic" in expression)


def comparison_conditions(definition: dict[str, Any]) -> list[dict[str, Any]]:
    """保留旧单项表达式；组内严格校验每一项，不接受部分有效的组。"""
    expression = definition.get("expression") or {}
    if not isinstance(expression, dict):
        _fail()
    if not is_condition_group(definition):
        return [expression]
    if set(expression) != {"logic", "conditions"} or expression["logic"] not in ("any", "all"):
        _fail()
    conditions = expression["conditions"]
    if not isinstance(conditions, list) or not 2 <= len(conditions) <= MAX_CONDITIONS:
        _fail()
    for condition in conditions:
        if not isinstance(condition, dict) or not _identifier(condition.get("left")):
            _fail()
        op = condition.get("op")
        if not isinstance(op, str):
            _fail()
        if op in UNARY_OPS:
            if set(condition) != {"left", "op"}:
                _fail()
            continue
        if op not in COMPARISON_OPS or set(condition) - {"left", "op", "right", "right_type", "right_table"}:
            _fail()
        side = condition.get("right_table", BASE)
        kind = condition.get("right_type", "field")
        if side not in (BASE, RELATED) or kind not in ("field", "value"):
            _fail()
        right = condition.get("right")
        if kind == "value":
            if side != BASE or not is_finite_number(right):
                _fail()
        elif not _identifier(right):
            _fail()
    return list(conditions)


def _valid_date_text(value: Any) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?", value) is None:
        return False
    try:
        if len(value) == 10:
            _datetime.date.fromisoformat(value)
        else:
            _datetime.datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


_ZERO_POSITIVE = re.compile(
    r"(?:NULL|空值)\s*(?:视为|视同|按|当作|转换为|转为|等于)\s*0"
    r"|(?:NULL|空值)\s*=\s*0",
    re.IGNORECASE,
)
# 只要出现否定/疑问/未确认/条件限定，整列不得零化；宁可 review，不挑单句正面证据。
_ZERO_UNSAFE = re.compile(
    r"不能|不允许|不得|不可|禁止|勿|不应|并非|不等于|不视为|不当作|不按|不转|不要"
    r"|尚未|未确定|未明确|待确认|需确认|需要确认|不确定|存疑|暂定|待定|视情况|可能"
    r"|原则上|一般|若|如果|假如|当|遇到|发生|情形|情况|条件下|例外|特殊|特定|仅|只有|部分|某种"
    r"|是否|\?|？",
)
_MISSING_VALUE_REQUIREMENT = re.compile(r"空值|缺值|缺失|为\s*空|未填写|\bNULL\b", re.IGNORECASE)


def _field_entries(columns: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(columns, list):
        return result
    for column in columns or []:
        if not isinstance(column, dict):
            continue
        name = str(column.get("column_name") or column.get("field_name") or "")
        if name:
            result[name] = column
    return result


def _column_text(field: dict[str, Any]) -> str:
    """本列自身文档语义；不含物理名、上游源字段或字典，避免另字段语义误判。"""
    return " ".join(
        str(field.get(key) or "") for key in ("field_cn", "comment", "logic")
    )


def _has_explicit_zero_semantics(field: dict[str, Any]) -> bool:
    text = _column_text(field)
    if not text.strip() or _ZERO_UNSAFE.search(text):
        return False
    return _ZERO_POSITIVE.search(text) is not None


def infer_numeric_null_handling(
    definition: dict[str, Any],
    rawfields: list[dict[str, Any]],
    relatedFields: list[dict[str, Any]] | None = None,
    *,
    request_text: str = "",
) -> dict[str, Any]:
    """保留已有文档推断及版本证据，另支持对真实数值操作数明确选择规则级零化。"""
    inferred = _infer_document_numeric_null_handling(definition, rawfields, relatedFields, request_text=request_text)
    if definition.get("null_policy") != "zero" or not inferred["applicable"] or inferred["null_policy"] == "zero":
        return inferred
    if is_condition_group(definition):
        base_types = {name: field.get("data_type") for name, field in _field_entries(rawfields).items()}
        related_types = {name: field.get("data_type") for name, field in _field_entries(relatedFields).items()}
        if not is_numeric_comparison(definition, base_types, related_types):
            return inferred
    return {"applicable": True, "null_policy": "zero", "null_handling": None, "evidence": [],
            "reason": "本规则明确约定数值比较中的 NULL 按 0 处理。"}


def _infer_document_numeric_null_handling(
    definition: dict[str, Any],
    rawfields: list[dict[str, Any]],
    relatedFields: list[dict[str, Any]] | None = None,
    *,
    request_text: str = "",
) -> dict[str, Any]:
    """按真实文档证据绑定数值比较空值处理。

    返回 {"applicable": bool, "null_policy": "review"|"zero"|"skip"|None,
           "null_handling": {"left","right"}|None, "evidence": [...], "reason": str}。
    原值缺失采用 review，文档明确零化时尊重文档。新 AI 常量检查按需求命中数值，
    只有以 0 代入不改变命中时才使用等效 COALESCE，否则跳过空值。
    """
    empty = {
        "applicable": False, "null_policy": None, "null_handling": None,
        "evidence": [], "reason": "非数值二元比较，不绑定空值策略",
    }
    if definition.get("rule_type") != "field_compare" or is_unary(definition):
        return empty
    if is_condition_group(definition):
        bindings = [
            _infer_document_numeric_null_handling({**definition, "expression": item}, rawfields, relatedFields,
                                                  request_text=request_text)
            for item in comparison_conditions(definition) if item["op"] not in UNARY_OPS
        ]
        if not any(item["applicable"] for item in bindings):
            return empty
        first = bindings[0]
        if all((item["null_policy"], item["null_handling"]) == (first["null_policy"], first["null_handling"])
               for item in bindings):
            return {**first, "evidence": [proof for item in bindings for proof in item["evidence"]]}
        # 纯数值命中时，若零化仅为等效跳过（没有字段文档指定零化），可统一跳过。
        if all(item["null_policy"] == "skip" or (item["null_policy"] == "zero"
                   and item["reason"].startswith("空值按 0 参与本次数值比较")) for item in bindings):
            return {**empty, "applicable": True, "null_policy": "skip", "reason": "组合条件只检查实际数值。"}
        return {**empty, "applicable": True, "null_policy": "unresolved",
                "reason": "各比较条件的缺值口径不同，需确认整组缺值处理。"}
    expression = definition.get("expression") or {}
    if (not isinstance(expression, dict) or not isinstance(expression.get("op"), str)
            or expression["op"] not in COMPARISON_OPS):
        return empty
    base_fields = _field_entries(rawfields)
    related_fields = _field_entries(relatedFields)
    left_name = expression.get("left")
    if not isinstance(left_name, str):
        return {**empty, "reason": "左操作数不是文档字段名"}
    left_field = base_fields.get(left_name)
    if left_field is None or type_family(left_field.get("data_type")) != "number":
        return {**empty, "reason": "左操作数不是文档中的数值字段"}
    right_type = expression.get("right_type") or "field"
    if not isinstance(right_type, str):
        return {**empty, "reason": "右操作数类型非法"}
    if right_type == "value":
        if not is_finite_number(expression.get("right")):
            return {**empty, "reason": "右侧不是有限数值常量"}
        right_field = None
    else:
        right_name = expression.get("right")
        if not isinstance(right_name, str):
            return {**empty, "reason": "右操作数不是文档字段名"}
        right_field = (
            related_fields.get(right_name) if expression.get("right_table") == RELATED
            else base_fields.get(right_name)
        )
        if right_field is None or type_family(right_field.get("data_type")) != "number":
            return {**empty, "reason": "右操作数不是文档中的数值字段"}

    join = definition.get("join")
    if isinstance(join, dict) and join.get("right_aggregate") == "sum":
        return {
            "applicable": True, "null_policy": "review", "null_handling": {"left": "review", "right": "review"},
            "evidence": [], "reason": "比较实际存储的数值与同日明细合计，缺行或实际字段缺值均须核实。",
        }
    left_zero = _has_explicit_zero_semantics(left_field)
    right_zero = False
    evidence: list[dict[str, str]] = []
    if left_zero:
        evidence.append({"side": "left", "field": str(left_name), "source": _column_text(left_field)})
    elif right_field is None:
        values_only = bool(request_text.strip()) and not _MISSING_VALUE_REQUIREMENT.search(request_text)
        if values_only or definition.get("null_policy") == "zero":
            from .query_samples import sql_compare

            if not sql_compare(expression["op"], 0, expression["right"]):
                reason = "空值按 0 参与本次数值比较，0 不会命中校验条件。"
                return {
                    "applicable": True, "null_policy": "zero",
                    "null_handling": {"left": "zero", "right": "zero"},
                    "evidence": [{"side": "left", "field": left_name, "source": reason}],
                    "reason": reason,
                }
        if values_only or (definition.get("generation_mode") == "ai" and definition.get("null_policy") == "skip"):
            return {**empty, "applicable": True, "null_policy": "skip", "reason": "需求只检查数值比较命中。"}
    if right_field is not None:
        right_zero = _has_explicit_zero_semantics(right_field)
        if right_zero:
            evidence.append({"side": "right", "field": str(expression.get("right")),
                             "source": _column_text(right_field)})

    if left_zero and (right_field is None or right_zero):
        return {
            "applicable": True, "null_policy": "zero",
            "null_handling": {"left": "zero", "right": "zero"},
            "evidence": evidence, "reason": "文档明确 NULL/空值视为 0",
        }
    handling = {
        "left": "zero" if left_zero else "review",
        "right": ("zero" if right_zero else "review") if right_field is not None else "review",
    }
    return {
        "applicable": True, "null_policy": "review",
        "null_handling": handling,
        "evidence": evidence,
        "reason": "缺省 review：原值 NULL 单列缺值待核实，不跳过当通过、不转 0",
    }


def apply_numeric_null_policy(
    definition: dict[str, Any],
    columns: list[dict[str, Any]],
    related_columns: list[dict[str, Any]] | None = None,
    *,
    request_text: str = "",
) -> dict[str, Any]:
    """按真实列类型绑定规则声明或文档推断的空值策略，返回新字典。"""
    result = dict(definition)
    inferred = infer_numeric_null_handling(result, columns, related_columns, request_text=request_text)
    if not inferred["applicable"]:
        return result
    result["null_policy"] = inferred["null_policy"]
    if inferred.get("null_handling"):
        result["null_handling"] = dict(inferred["null_handling"])
    else:
        result.pop("null_handling", None)
    result["null_evidence"] = list(inferred.get("evidence") or [])
    return result


def is_numeric_comparison(
    definition: dict[str, Any],
    base_types: dict[str, Any],
    related_types: dict[str, Any] | None = None,
) -> bool:
    """主表达式是否为二元数值比较；filters/一元/其他规则类型不算。"""
    if definition.get("rule_type") != "field_compare" or is_unary(definition):
        return False
    if is_condition_group(definition):
        binary = [item for item in comparison_conditions(definition) if item["op"] not in UNARY_OPS]
        return bool(binary) and all(is_numeric_comparison({**definition, "expression": item}, base_types, related_types)
                                    for item in binary)
    expression = definition.get("expression") or {}
    if (not isinstance(expression, dict) or not isinstance(expression.get("op"), str)
            or expression["op"] not in COMPARISON_OPS):
        return False
    left = expression.get("left")
    if not isinstance(left, str) or type_family(base_types.get(left)) != "number":
        return False
    if str(expression.get("right_type") or "field") == "value":
        return is_finite_number(expression.get("right"))
    right = expression.get("right")
    if not isinstance(right, str):
        return False
    source = (related_types or {}) if expression.get("right_table") == RELATED else base_types
    return type_family(source.get(right)) == "number"


def needs_issue_kind(definition: dict[str, Any]) -> bool:
    """是否需要在 SELECT 投影 issue_kind。

    review/zero 数值、非数值新规格比较输出类型；旧 shape 为保持 SQL 字节不变不输出，
    由存储/UI 按 legacy 处理。
    """
    if "project_driver" in definition:
        return True
    if definition.get("rule_type") != "field_compare":
        return False
    policy = definition.get("null_policy")
    if policy in ("review", "zero"):
        return True
    return is_new_spec(definition)


def validate_query_spec(definition: dict[str, Any]) -> dict[str, Any]:
    """校验 filters/join/right_table 的结构与取值边界，返回规范化副本。

    返回：{"filters": [...], "join": {...}|None, "right_table": "base"|"related"}。
    不校验字段是否真实存在，也不校验字段类型归属。
    """

    raw_filters = definition.get("filters", [])
    if raw_filters is None:
        raw_filters = []
    if not isinstance(raw_filters, list) or len(raw_filters) > MAX_FILTERS:
        _fail()

    raw_join = definition.get("join")
    join: dict[str, Any] | None = None
    if raw_join is not None:
        if not isinstance(raw_join, dict) or set(raw_join) - {"table_name", "on", "report_date_field", "unmatched_policy", "relationship_confirmed", "right_aggregate"}:
            _fail()
        table_name = raw_join.get("table_name")
        if not _identifier(table_name):
            _fail()
        raw_on = raw_join.get("on")
        if not isinstance(raw_on, list) or not 1 <= len(raw_on) <= MAX_JOIN_KEYS:
            _fail()
        on: list[dict[str, str]] = []
        for item in raw_on:
            if not isinstance(item, dict) or set(item) - {"left", "right"}:
                _fail()
            left = item.get("left")
            right = item.get("right")
            if not _identifier(left) or not _identifier(right):
                _fail()
            on.append({"left": left, "right": right})
        date_field = raw_join.get("report_date_field")
        if not _identifier(date_field):
            _fail()
        unmatched = raw_join.get("unmatched_policy") or "unresolved"
        aggregate = raw_join.get("right_aggregate")
        if "right_aggregate" in raw_join and aggregate != "sum":
            _fail()
        if unmatched not in (("review",) if aggregate else ("unresolved", "exclude")):
            _fail()
        confirmed = raw_join.get("relationship_confirmed", False)
        if not isinstance(confirmed, bool):
            _fail()
        join = {
            "table_name": table_name,
            "on": on,
            "report_date_field": date_field,
            "unmatched_policy": unmatched,
            "relationship_confirmed": confirmed,
        }
        if aggregate:
            join["right_aggregate"] = aggregate

    filters: list[dict[str, Any]] = []
    for item in raw_filters:
        if not isinstance(item, dict) or set(item) - {"table", "field", "op", "value", "confirmed"}:
            _fail()
        table = item.get("table", BASE)
        if table not in (BASE, RELATED):
            _fail()
        field = item.get("field")
        if not _identifier(field):
            _fail()
        op = item.get("op")
        if not isinstance(op, str) or op not in FILTER_OPS:
            _fail()
        confirmed = item.get("confirmed", False)
        if not isinstance(confirmed, bool):
            _fail()
        value = item.get("value")
        if op in ("is_null", "is_not_null"):
            if value is not None:
                _fail()
        elif op in ("in", "not_in"):
            if not isinstance(value, list) or not 1 <= len(value) <= MAX_IN_VALUES:
                _fail()
            for entry in value:
                if isinstance(entry, bool) or not isinstance(entry, (str, int, float)):
                    _fail()
                if isinstance(entry, str) and (not entry or len(entry) > MAX_VALUE_LENGTH):
                    _fail()
                if isinstance(entry, float) and not math.isfinite(entry):
                    _fail()
        else:
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                _fail()
            if isinstance(value, str) and (not value or len(value) > MAX_VALUE_LENGTH):
                _fail()
            if isinstance(value, float) and not math.isfinite(value):
                _fail()
        filters.append({
            "table": table, "field": field, "op": op, "value": value, "confirmed": confirmed,
        })

    if any(item["table"] == RELATED for item in filters) and join is None:
        _fail()

    expression = definition.get("expression") or {}
    if not isinstance(expression, dict):
        _fail()
    conditions = comparison_conditions(definition)
    if is_condition_group(definition):
        if definition.get("rule_type") != "field_compare" or (join and join.get("right_aggregate")):
            _fail()
        if join is None and any(item.get("right_table") == RELATED for item in conditions):
            _fail()
        if definition.get("null_policy") not in (None, "unresolved") and not _valid_null_policy(definition):
            _fail()
        if definition.get("equality_policy") not in (None, "unresolved", "allow_equal", "reject_equal"):
            _fail()
    right_table = expression.get("right_table") or BASE
    if right_table not in (BASE, RELATED):
        _fail()
    right_type = expression.get("right_type") or "field"
    if right_type not in ("field", "value"):
        _fail()
    if right_table == RELATED:
        if join is None or right_type != "field" or not _identifier(expression.get("right")):
            _fail()
    policy = definition.get("null_policy")
    if join and join.get("right_aggregate") and (
        definition.get("rule_type") != "field_compare" or right_table != RELATED or expression.get("op") != "neq"
        or policy not in ("review", "zero")
        or definition.get("null_handling") not in (None, {"left": policy, "right": policy})
    ):
        _fail()

    raw_handling = definition.get("null_handling")
    if raw_handling is not None:
        if not isinstance(raw_handling, dict) or set(raw_handling) - {"left", "right"}:
            _fail()
        if any(item not in ("zero", "review") for item in raw_handling.values()):
            _fail()
        if is_condition_group(definition) and (
            definition.get("null_policy") not in ("zero", "review")
            or (definition["null_policy"] == "zero" and "review" in raw_handling.values())
        ):
            _fail()
    raw_evidence = definition.get("null_evidence")
    if raw_evidence is not None:
        if (not isinstance(raw_evidence, list) or len(raw_evidence) > 20
                or any(not isinstance(item, dict) or set(item) - {"side", "field", "source"}
                       or item.get("side") not in ("left", "right")
                       or not isinstance(item.get("field"), str) or not isinstance(item.get("source"), str)
                       for item in raw_evidence)):
            _fail()

    raw_context = definition.get("project_context")
    context = None
    if raw_context is not None:
        context = normalize_project_context(raw_context)
        if context["mode"] == "lookup":
            if context["table_name"] == str(definition.get("table_name") or ""):
                _fail()
            if join is not None and join["table_name"] != context["table_name"]:
                # 主表 + join + 项目维度 = 第三张不同表，突破两表上限。
                _fail()
            if join is not None:
                pair = {"left": context["key"]["left"], "right": context["key"]["right"]}
                if pair not in join["on"]:
                    _fail()
                if context["date_field"] != join["report_date_field"]:
                    _fail()

    driver = validate_project_driver(definition, context=context, join=join)
    return {"filters": filters, "join": join, "right_table": right_table,
            "project_context": context, "project_driver": driver}


def validate_spec_against_columns(
    definition: dict[str, Any],
    base_columns: list[dict[str, Any]],
    related_columns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """在真实/文档列结构上复核规格；返回 normalized spec。

    ``base_columns`` 与 ``related_columns`` 使用 ``column_name`` / ``data_type``。
    join 存在时 ``related_columns`` 必须提供，否则抛 VALIDATION_ERROR。
    """

    spec = validate_query_spec(definition)
    base_types = {
        str(column.get("column_name")): column.get("data_type")
        for column in base_columns or [] if column.get("column_name")
    }
    related_types = {
        str(column.get("column_name")): column.get("data_type")
        for column in related_columns or [] if column.get("column_name")
    }
    if is_new_spec(definition):
        if any(name not in base_types for name in referenced_columns(definition)["base"]):
            _fail()
        if base_type(base_types.get(definition.get("report_date_field") or "report_date")) != "date":
            _fail()

    for condition in comparison_conditions(definition):
        left = condition.get("left")
        if not _identifier(left) or left not in base_types:
            _fail()
        if isinstance(condition.get("op"), str) and condition["op"] in UNARY_OPS:
            continue
        right_type = condition.get("right_type") or "field"
        right = condition.get("right")
        if right_type == "value":
            if not is_finite_number(right) or (is_new_spec(definition) and type_family(base_types.get(left)) != "number"):
                _fail()
        else:
            right_types = related_types if condition.get("right_table") == RELATED else base_types
            if not _identifier(right) or right not in right_types:
                _fail()
            if (is_new_spec(definition) and not type_family(base_types.get(left))) or type_family(base_types.get(left)) != type_family(
                right_types.get(right)
            ):
                _fail()

    if definition.get("null_policy") in ("zero", "review"):
        # 只允许二元数值主表达式；日期/文本/状态/filters/关联键不转 0 或报缺值。
        if is_unary(definition) or not is_numeric_comparison(definition, base_types, related_types):
            _fail()
        handling = definition.get("null_handling") or {}
        if any(item == "zero" and not definition.get("null_evidence") for item in handling.values()):
            # 逐侧指定的零化须保留证据，规则统一 zero 可由 null_policy 单独表达。
            _fail()
        for condition in comparison_conditions(definition):
            if condition.get("op") in UNARY_OPS:
                continue
            operands = [("left", base_types.get(condition.get("left")))]
            if condition.get("right_type", "field") == "field":
                types = related_types if condition.get("right_table") == RELATED else base_types
                operands.append(("right", types.get(condition.get("right"))))
            if any(handling.get(side, definition["null_policy"]) == "zero" and base_type(kind) in {"money", "bit"}
                   for side, kind in operands):
                # These native types do not support the compiler's numeric-zero COALESCE.
                _fail()

    for item in spec["filters"]:
        types = related_types if item["table"] == RELATED else base_types
        data_type = types.get(item["field"])
        if data_type is None:
            _fail()
        _validate_filter_value(item, data_type)

    join = spec["join"]
    if join is not None:
        if not related_columns:
            _fail()
        if join["table_name"] == str(definition.get("table_name") or ""):
            _fail()
        for pair in join["on"]:
            if pair["left"] not in base_types or pair["right"] not in related_types:
                _fail()
            if not type_family(base_types.get(pair["left"])) or type_family(base_types.get(pair["left"])) != type_family(related_types.get(pair["right"])):
                _fail()
        date_type = related_types.get(join["report_date_field"])
        if date_type is None or base_type(date_type) != "date":
            _fail()

    context = spec["project_context"]
    if context is not None:
        from .project_context import validate_project_context_against_columns
        validate_project_context_against_columns(context, base_types, related_types or None)
    validate_project_driver_columns(
        definition, base_columns, related_columns, context=context, join=join,
    )

    return spec


def _validate_filter_value(item: dict[str, Any], data_type: Any) -> None:
    if item["op"] in ("is_null", "is_not_null"):
        return  # Presence checks have no literal to cast and work for every SQL column type.
    family = type_family(data_type)
    if not family:
        _fail()
    values = item["value"] if item["op"] in ("in", "not_in") else [item["value"]]
    for value in values:
        if family == "number":
            if not is_finite_number(value):
                _fail()
        elif family == "date":
            if not _valid_date_text(value):
                _fail()
        elif family == "string":
            if not isinstance(value, str):
                _fail()


def is_unary(definition: dict[str, Any]) -> bool:
    expression = definition.get("expression") or {}
    return (not is_condition_group(definition) and isinstance(expression, dict)
            and isinstance(expression.get("op"), str) and expression["op"] in UNARY_OPS)


def canonicalize_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """返回规范化副本：一元表达式只保留 left/op，并补齐一元默认口径。

    保存/确认哈希必须与预览使用同一规范，避免模型多带 right/right_type 造成
    未保存预览哈希与已保存版本不一致。
    """
    result = dict(definition)
    if result.get("expression") is not None and not isinstance(result["expression"], dict):
        _fail()
    expression = dict(result.get("expression") or {})
    if is_condition_group(result):
        comparison_conditions(result)
    elif is_unary(result):
        if "null_policy" not in result:
            result["null_policy"] = "violate"
        if "equality_policy" not in result:
            result["equality_policy"] = "allow_equal"
        result["expression"] = {"left": expression.get("left"), "op": expression.get("op")}
    if result.get("project_context") is not None:
        result["project_context"] = normalize_project_context(result["project_context"])
    driver = validate_project_driver(result)
    if driver is not None:
        result["project_driver"] = driver
    return result


def is_new_spec(definition: dict[str, Any]) -> bool:
    expression = definition.get("expression") or {}
    if not isinstance(expression, dict):
        return True
    return is_condition_group(definition) or (definition.get("filters") is not None and definition.get("filters") != []) or definition.get("join") is not None \
        or expression.get("right_table") == RELATED or is_unary(definition) \
        or definition.get("project_context") is not None \
        or definition.get("project_driver") is not None \
        or definition.get("null_policy") in ("zero", "review")


def _valid_null_policy(definition: dict[str, Any]) -> bool:
    policy = definition.get("null_policy")
    if is_unary(definition):
        return policy == "violate"
    if is_condition_group(definition) and all(item["op"] in UNARY_OPS for item in comparison_conditions(definition)):
        return policy in ("skip", "violate")
    return policy in ("skip", "zero", "review")


def query_ready(definition: dict[str, Any]) -> bool:
    """确认/执行门禁。旧 shape 恒为 True，历史规则行为不变。"""

    if definition.get("rule_type") != "field_compare":
        return not is_condition_group(definition)
    if not is_new_spec(definition):
        return True
    if definition.get("equality_policy") not in ("allow_equal", "reject_equal"):
        return False
    if definition.get("unsupported_requirements"):
        return False
    try:
        spec = validate_query_spec(definition)
        if not _valid_null_policy(definition):
            return False
    except AppError:
        return False
    if any(not item["confirmed"] for item in spec["filters"]):
        return False
    join = spec["join"]
    if join is not None:
        if not join["relationship_confirmed"] or join["unmatched_policy"] == "unresolved":
            return False
    context = spec["project_context"]
    if context is not None:
        if not context["confirmed"]:
            return False
        if context["mode"] == "lookup" and not context["unique_evidence"].get("confirmed"):
            return False
    return True


def query_unresolved_reasons(definition: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if definition.get("rule_type") != "field_compare" or not is_new_spec(definition):
        return reasons
    try:
        spec = validate_query_spec(definition)
        if not _valid_null_policy(definition):
            reasons.append("空值口径尚未确认为计为违规" if is_unary(definition) else
                           "空值口径尚未确认（数值比较应绑定 review/有据 zero，日期/文本应为 skip）")
    except AppError:
        return ["查询结构或字段不符合契约"]
    if definition.get("equality_policy") not in ("allow_equal", "reject_equal"):
        reasons.append("相等口径尚未确认")
    if definition.get("unsupported_requirements"):
        reasons.append("存在未解决的不支持要求")
    if any(not item["confirmed"] for item in spec["filters"]):
        reasons.append("存在未确认的筛选条件")
    join = spec["join"]
    if join is not None:
        if not join["relationship_confirmed"]:
            reasons.append("关联关系尚未确认")
        if join["unmatched_policy"] == "unresolved":
            reasons.append("未匹配记录处理尚未确认")
    context = spec["project_context"]
    if context is not None:
        if not context["confirmed"]:
            reasons.append("项目上下文映射尚未确认")
        if context["mode"] == "lookup" and not context["unique_evidence"].get("confirmed"):
            reasons.append("项目维度唯一性证据尚未确认")
    return reasons


def referenced_columns(definition: dict[str, Any]) -> dict[str, list[str]]:
    """执行期字段漂移检查清单（含日期字段）。"""

    base: list[str] = []
    related: list[str] = []

    def add(bucket: list[str], value: Any) -> None:
        text = str(value or "")
        if text and text not in bucket:
            bucket.append(text)

    add(base, definition.get("business_key") or "id")
    if definition.get("rule_type") == "field_compare" and is_new_spec(definition):
        add(base, definition.get("report_date_field") or "report_date")
    for expression in comparison_conditions(definition):
        add(base, expression.get("left"))
        if (expression.get("right_type") or "field") == "field":
            add(related if expression.get("right_table") == RELATED else base, expression.get("right"))

    spec: dict[str, Any] = {"filters": [], "join": None, "right_table": "base"}
    try:
        spec = validate_query_spec(definition)
    except AppError:
        pass
    for item in spec["filters"]:
        add(related if item["table"] == RELATED else base, item["field"])
    join = spec["join"]
    if join is not None:
        for pair in join["on"]:
            add(base, pair["left"])
            add(related, pair["right"])
        add(related, join["report_date_field"])

    context = spec.get("project_context")
    if context is not None:
        add(base, context["code_field"])
        if context["mode"] == "base":
            add(base, context["name_field"])
        else:
            add(base, context["key"]["left"])
            add(related, context["key"]["right"])
            add(related, context["name_field"])
            if context.get("date_field"):
                add(related, context["date_field"])

    # 其余历史规则类型沿用既有字段键。
    for key in ("field", "assets", "liabilities", "equity", "key", "other_key"):
        add(base, definition.get(key))
    for item in definition.get("keys") or []:
        add(base, item)
    return {"base": base, "related": related}
