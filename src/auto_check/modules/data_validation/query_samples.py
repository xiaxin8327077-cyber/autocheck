"""配置型规则的合成样本与进程内求值。

旧规则继续生成扁平 row；包含 filters/join/right_table=related 的新规格统一使用
嵌套 row：{"base": {...}, "related": [{...}], "report_date": "YYYY-MM-DD"}。
求值严格模拟 SQL 三值逻辑与 EXISTS 半连接，不做业务库查询。
"""

from __future__ import annotations

import datetime as _datetime
import math
from decimal import Decimal, localcontext
from typing import Any

from .contracts import AppError
from .query_spec import (
    BASE,
    MAX_IN_VALUES,
    RELATED,
    UNARY_OPS,
    base_type,
    comparison_conditions,
    is_condition_group,
    is_finite_number,
    is_new_spec,
    is_unary,
    type_family,
    validate_query_spec,
)

_DATE_TYPES = {"date", "datetime", "timestamp", "time", "year"}
_NUMBER_TYPES = {
    "int", "integer", "bigint", "smallint", "tinyint", "mediumint",
    "decimal", "numeric", "float", "double", "real", "money",
}


def _base_type(data_type: Any) -> str:
    return base_type(data_type)


def ordered_values(data_type: Any) -> tuple[Any, Any]:
    """按字段类型合成一对可比较的样本值 a < b；日期值随当前日期漂移。"""
    base = _base_type(data_type)
    if base in _DATE_TYPES:
        anchor = _datetime.date.today() + _datetime.timedelta(days=1)
        return anchor.isoformat(), (anchor + _datetime.timedelta(days=1)).isoformat()
    if type_family(data_type) == "number":
        return 1, 2
    return "样本A", "样本B"


def sample_pairs(op: str, low: Any, high: Any) -> tuple[tuple[Any, Any], tuple[Any, Any]]:
    if op in ("gt", "gte"):
        return (low, high), (high, low)
    if op == "eq":
        return (low, high), (low, low)
    if op == "neq":
        return (low, low), (low, high)
    return (high, low), (low, high)


def value_sample_pair(op: str, constant: Any) -> tuple[Any, Any]:
    below = math.floor(constant) - 1
    above = math.ceil(constant) + 1
    if op == "eq":
        return above, constant
    if op == "neq":
        return constant, below
    if op == "lt":
        return above, below
    if op == "lte":
        return above, constant
    if op == "gt":
        return below, above
    if op == "gte":
        return below, constant
    return above, below


def sql_equal(left: Any, right: Any) -> bool:
    """SQL 等值：任一侧 NULL 结果为 UNKNOWN，不按真处理。"""
    if left is None or right is None:
        return False
    return left == right


def sql_compare(op: str, left: Any, right: Any) -> bool:
    """SQL 比较：任一侧 NULL 结果为 UNKNOWN，调用方按不触发违规处理。"""
    if left is None or right is None:
        return False
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    raise AppError("VALIDATION_ERROR")


def filter_matches(op: str, value: Any, predicate: Any) -> bool:
    if op == "is_null":
        return value is None
    if op == "is_not_null":
        return value is not None
    if value is None:
        return False
    if op == "eq":
        return value == predicate
    if op == "neq":
        return value != predicate
    if op == "lt":
        return value < predicate
    if op == "lte":
        return value <= predicate
    if op == "gt":
        return value > predicate
    if op == "gte":
        return value >= predicate
    if op == "in":
        return any(value == item for item in predicate)
    if op == "not_in":
        return all(value != item for item in predicate)
    raise AppError("VALIDATION_ERROR")


def _is_numeric_sample(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    return False


def _coalesce_zero(value: Any) -> Any:
    """显式 zero 口径：仅 NULL 转 0；空串/非法数值不是 NULL，不能冒充 0。"""
    if value is None:
        return 0
    if not _is_numeric_sample(value):
        raise AppError("VALIDATION_ERROR")
    return value


def _null_modes(definition: dict[str, Any]) -> tuple[str | None, str | None]:
    """按 core null_handling 返回左右侧 zero/review；未绑定数值策略时为 None。"""
    handling = definition.get("null_handling") or {}
    if definition.get("null_policy") == "zero":
        return "zero", "zero"
    if definition.get("null_policy") == "review":
        return (
            str(handling.get("left") or "review"),
            str(handling.get("right") or "review"),
        )
    return None, None


def _prepare_numeric_operand(value: Any, mode: str | None) -> tuple[Any, bool]:
    """zero->0；review->缺失标志；未绑定保持原值（None 不参与比较）。"""
    if mode == "zero":
        return _coalesce_zero(value), False
    if mode == "review":
        if value is None:
            return 0, True
        if not _is_numeric_sample(value):
            raise AppError("VALIDATION_ERROR")
        return value, False
    return value, False


def _flat_evaluation(definition: dict[str, Any], row: dict[str, Any]) -> tuple[int, str | None]:
    """返回 (是否违规, issue_kind)；issue_kind 仅数值策略产生。"""
    if definition.get("rule_type") != "field_compare":
        return 0, None
    expression = definition.get("expression") or {}
    left_name = expression["left"]
    right_type = str(expression.get("right_type") or "field")
    left = row.get(left_name)
    if right_type == "value":
        right = expression.get("right")
        if not _is_numeric_sample(right):
            raise AppError("VALIDATION_ERROR")
    elif right_type == "field":
        right = row.get(expression["right"])
    else:
        raise AppError("VALIDATION_ERROR")
    if definition.get("null_policy") == "skip":
        if left is None or left == "":
            return 0, None
        if right_type == "field" and (right is None or right == ""):
            return 0, None

    left_mode, right_mode = _null_modes(definition)
    numeric_policy = bool(left_mode or right_mode)
    missing = False
    if numeric_policy:
        left, missing_left = _prepare_numeric_operand(left, left_mode)
        right, missing_right = _prepare_numeric_operand(right, right_mode)
        missing = missing_left or missing_right
        if missing:
            return 1, "missing_value"
    elif left is None or right is None:
        return 0, None
    if (
        right_type == "field" and left == right
        and definition.get("equality_policy") == "allow_equal"
        and not numeric_policy
    ):
        return 0, None
    op = expression["op"]
    violated = {
        "lt": left < right,
        "lte": left <= right,
        "gt": left > right,
        "gte": left >= right,
        "eq": left == right,
        "neq": left != right,
    }[op]
    if not violated:
        return 0, None
    return 1, ("numeric" if numeric_policy else None)


def evaluate_expression(definition: dict[str, Any], row: dict[str, Any]) -> int:
    """旧版字段比较语义，保持历史行为（含空串按空值跳过的旧口径）。"""
    return _flat_evaluation(definition, row)[0]


def _group_evaluation(
    definition: dict[str, Any], base: dict[str, Any], matches: list[dict[str, Any]],
) -> tuple[int, str | None]:
    conditions = comparison_conditions(definition)
    left_mode, right_mode = _null_modes(definition)
    any_condition = definition["expression"]["logic"] == "any"
    hit_kind = "numeric" if left_mode or right_mode else "comparison"
    needs_review = False
    for related in matches:
        states: list[bool | None] = []
        for item in conditions:
            left = base.get(item["left"])
            op = item["op"]
            if op in UNARY_OPS:
                states.append(left is None if op == "is_null" else left is not None)
                continue
            if item.get("right_type") == "value":
                right = item["right"]
            else:
                right = (related if item.get("right_table") == RELATED else base).get(item["right"])
            left, missing_left = _prepare_numeric_operand(left, left_mode)
            right, missing_right = _prepare_numeric_operand(right, right_mode)
            if missing_left or missing_right:
                states.append(None)
            else:
                states.append(sql_compare(op, left, right))
        if (any_condition and True in states) or (not any_condition and all(states)):
            return 1, hit_kind
        if None in states and (any_condition or False not in states):
            needs_review = True
    return (1, "missing_value") if needs_review else (0, None)


def _relational_evaluation(definition: dict[str, Any], row: dict[str, Any]) -> tuple[int, str | None]:
    """新规格求值：先过滤，再按 EXISTS 半连接判断，每基表行最多计 1。"""
    spec = validate_query_spec(definition)
    base = row.get("base") or {}
    related = row.get("related") or []
    period = row.get("report_date")
    base_date_field = str(definition.get("report_date_field") or "report_date")

    if not isinstance(period, str) or not sql_equal(base.get(base_date_field), period):
        return 0, None
    for item in spec["filters"]:
        if item["table"] == BASE and not filter_matches(
            item["op"], base.get(item["field"]), item["value"],
        ):
            return 0, None

    join = spec["join"]
    matched: list[dict[str, Any]] = []
    if join is not None:
        related_date = join["report_date_field"]
        for entry in related:
            if not isinstance(entry, dict):
                continue
            if not sql_equal(entry.get(related_date), period):
                continue
            if not all(
                sql_equal(entry.get(pair["right"]), base.get(pair["left"]))
                for pair in join["on"]
            ):
                continue
            if any(
                item["table"] == RELATED
                and not filter_matches(item["op"], entry.get(item["field"]), item["value"])
                for item in spec["filters"]
            ):
                continue
            matched.append(entry)

    return evaluate_matched_rows(definition, spec, base, matched)


def evaluate_matched_rows(
    definition: dict[str, Any], spec: dict[str, Any], base: dict[str, Any], matched: list[dict[str, Any]],
) -> tuple[int, str | None]:
    """在已满足期间、关联和范围条件的记录上执行原表达式。"""
    expression = definition["expression"]
    join = spec["join"]
    if is_condition_group(definition):
        return _group_evaluation(definition, base, matched if join is not None else [{}])
    right_type = str(expression.get("right_type") or "field")
    left_value = base.get(expression["left"])
    if join and join.get("right_aggregate") == "sum":
        parts = [entry.get(expression["right"]) for entry in matched]
        if not parts:
            return 1, "missing_value"
        if definition.get("null_policy") == "zero":
            left_value = 0 if left_value is None else left_value
            parts = [0 if value is None else value for value in parts]
        elif left_value is None or any(value is None for value in parts):
            return 1, "missing_value"
        if not all(_is_numeric_sample(value) for value in [left_value, *parts]):
            raise AppError("VALIDATION_ERROR")
        numbers = [Decimal(str(value)) for value in parts]
        # 金额用十进制按明细逐项相加，保留大额与小数同组时的有效位数。
        with localcontext() as context:
            places = max(number.adjusted() for number in numbers) - min(number.as_tuple().exponent for number in numbers)
            context.prec = max(context.prec, places + len(str(len(numbers))) + 2)
            total = sum(numbers, Decimal(0))
        return (1, "numeric") if Decimal(str(left_value)) != total else (0, None)
    left_mode, right_mode = _null_modes(definition)
    numeric_policy = bool(left_mode or right_mode)
    if is_unary(definition):
        # 空值口径由 op 本身表达，不能提前按 null_policy 跳过目标为 NULL 的行。
        if join is not None and not matched:
            return 0, None
        if expression["op"] == "is_null":
            return (1, None) if left_value is None else (0, None)
        return (1, None) if left_value is not None else (0, None)
    if spec["right_table"] == RELATED:
        right_field = expression["right"]
        if numeric_policy:
            left_compare, missing_left = _prepare_numeric_operand(left_value, left_mode)
            if missing_left:
                return 1, "missing_value"
            hit = False
            for entry in matched:
                right_compare, missing_right = _prepare_numeric_operand(entry.get(right_field), right_mode)
                if missing_right:
                    return 1, "missing_value"
                if sql_compare(expression["op"], left_compare, right_compare):
                    hit = True
                    break
            return (1, "numeric") if hit else (0, None)
        return (
            (1, None) if any(
                sql_compare(expression["op"], left_value, entry.get(right_field)) for entry in matched
            ) else (0, None)
        )
    if right_type == "value":
        right_value = expression.get("right")
        if not _is_numeric_sample(right_value):
            raise AppError("VALIDATION_ERROR")
    else:
        right_value = base.get(expression["right"])
    if join is not None and not matched:
        return 0, None
    if numeric_policy:
        left_compare, missing_left = _prepare_numeric_operand(left_value, left_mode)
        right_compare, missing_right = _prepare_numeric_operand(right_value, right_mode)
        if missing_left or missing_right:
            return 1, "missing_value"
        return (1, "numeric") if sql_compare(expression["op"], left_compare, right_compare) else (0, None)
    return (1, None) if sql_compare(expression["op"], left_value, right_value) else (0, None)


def evaluate_case_with_kind(definition: dict[str, Any], row: dict[str, Any]) -> tuple[int, str | None]:
    if "project_driver" in definition:
        from .project_driver_samples import evaluate_project_case
        return evaluate_project_case(definition, row)
    if is_new_spec(definition):
        return _relational_evaluation(definition, row)
    return _flat_evaluation(definition, row)


def evaluate_relational(definition: dict[str, Any], row: dict[str, Any]) -> int:
    return _relational_evaluation(definition, row)[0]


def evaluate_case(definition: dict[str, Any], row: dict[str, Any]) -> int:
    return evaluate_case_with_kind(definition, row)[0]


# ---------------------------------------------------------------------------
# 样本构造


_SKIP = object()


def _column_types(columns: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {
        str(column.get("column_name")): column.get("data_type")
        for column in columns or [] if column.get("column_name")
    }


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def case_fields(definition: dict[str, Any]) -> tuple[list[str], list[str]]:
    """返回嵌套样本 base/related 的精确字段集合。"""
    spec = validate_query_spec(definition)
    base: list[str] = []
    related: list[str] = []
    for item in comparison_conditions(definition):
        base.append(str(item["left"]))
        if item.get("op") not in UNARY_OPS and item.get("right_type", "field") == "field":
            (related if item.get("right_table") == RELATED else base).append(str(item["right"]))
    base.append(str(definition.get("report_date_field") or "report_date"))
    join = spec["join"]
    if join is not None:
        for pair in join["on"]:
            base.append(pair["left"])
            related.append(pair["right"])
        related.append(join["report_date_field"])
    for item in spec["filters"]:
        (related if item["table"] == RELATED else base).append(item["field"])
    return _unique(base), _unique(related)


def _alternate(value: Any, data_type: Any) -> Any:
    base = _base_type(data_type)
    if base in _NUMBER_TYPES and isinstance(value, (int, float)) and not isinstance(value, bool):
        return value + 1
    if base in _DATE_TYPES:
        try:
            day = _datetime.date.fromisoformat(str(value)[:10])
            return (day + _datetime.timedelta(days=1)).isoformat()
        except ValueError:
            return "2099-12-31"
    if isinstance(value, str):
        return "样本Z" if value != "样本Z" else "样本Y"
    return "样本Z"


def _above(value: Any, data_type: Any) -> Any:
    base = _base_type(data_type)
    if base in _NUMBER_TYPES and isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.ceil(value) + 1
    if base in _DATE_TYPES:
        return "9999-12-31"
    return "~~~"


def _below(value: Any, data_type: Any) -> Any:
    base = _base_type(data_type)
    if base in _NUMBER_TYPES and isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.floor(value) - 1
    if base in _DATE_TYPES:
        return "0001-01-01"
    return "0"


def _not_in(values: list[Any], data_type: Any) -> Any:
    candidate = _alternate(values[0], data_type)
    offset = 0
    while candidate in values and offset < 1000:
        offset += 1
        candidate = _alternate((values[0] + offset) if isinstance(values[0], (int, float)) else f"{values[0]}{offset}", data_type)
    return candidate


def _pass_value(item: dict[str, Any], data_type: Any) -> Any:
    op = item["op"]
    value = item["value"]
    if op == "is_null":
        return None
    if op == "is_not_null":
        return ordered_values(data_type)[0]
    if op == "in":
        return value[0]
    if op == "not_in":
        return _not_in(list(value), data_type)
    if op == "eq":
        return value
    if op == "neq":
        return _alternate(value, data_type)
    if op == "lt":
        return _below(value, data_type)
    if op == "lte":
        return value
    if op == "gt":
        return _above(value, data_type)
    if op == "gte":
        return value
    raise AppError("VALIDATION_ERROR")


def _fail_value(item: dict[str, Any], data_type: Any) -> Any:
    op = item["op"]
    value = item["value"]
    if op == "is_null":
        return ordered_values(data_type)[0]
    if op == "is_not_null":
        return None
    if op == "in":
        return _not_in(list(value), data_type)
    if op == "not_in":
        return value[0]
    if op == "eq":
        return _alternate(value, data_type)
    if op == "neq":
        return value
    if op == "lt":
        return value
    if op == "lte":
        return _above(value, data_type)
    if op == "gt":
        return value
    if op == "gte":
        return _below(value, data_type)
    return _SKIP


def _expected_count(kind: str, op: str, equality_policy: str, right_type: str = "field") -> int:
    if kind == "violation":
        return 1
    if kind == "boundary":
        if right_type == "field" and equality_policy == "allow_equal":
            return 0
        return 0 if op in ("lt", "gt", "neq") else 1
    return 0


def _row_has_none(row: Any) -> bool:
    if isinstance(row, dict):
        return any(_row_has_none(value) for value in row.values())
    if isinstance(row, list):
        return any(_row_has_none(value) for value in row)
    return row is None


def _apply_numeric_null_case_expectations(
    definition: dict[str, Any], cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """显式 zero/review 口径下按 evaluator 计算 NULL 样本预期，并标注 issue 类型。"""
    policy = str(definition.get("null_policy") or "")
    if policy not in {"zero", "review"}:
        return cases
    for case in cases:
        row = case.get("row") or {}
        if not _row_has_none(row):
            continue
        expected, kind = evaluate_case_with_kind(definition, row)
        case["expected_count"] = expected
        if kind:
            case["expected_issue_kind"] = kind
    return cases


def _legacy_flat_cases(
    definition: dict[str, Any], columns: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """旧规则样本，逐字保留历史行为。"""
    expression = definition.get("expression") or {}
    left_name = expression["left"]
    op = str(expression.get("op") or "lt")
    right_type = str(expression.get("right_type") or "field")
    equality_policy = str(definition.get("equality_policy") or "")
    column_types = _column_types(columns)
    if right_type == "value":
        constant = expression.get("right")
        if not is_finite_number(constant):
            raise AppError("VALIDATION_ERROR")
        normal_value, violation_value = value_sample_pair(op, constant)
        samples = [
            ("正常", normal_value, "normal"),
            ("明显异常", violation_value, "violation"),
            ("边界", constant, "boundary"),
            ("空值", None, "null"),
        ]
        return _apply_numeric_null_case_expectations(definition, [
            {
                "name": name,
                "row": {left_name: value},
                "expected_count": _expected_count(kind, op, equality_policy, "value"),
            }
            for name, value, kind in samples
        ])
    if right_type != "field":
        raise AppError("VALIDATION_ERROR")
    right_name = expression["right"]
    data_type = column_types.get(left_name) or column_types.get(right_name)
    low, high = ordered_values(data_type)
    normal_pair, violation_pair = sample_pairs(op, low, high)
    samples = [
        ("正常", normal_pair[0], normal_pair[1], "normal"),
        ("明显异常", violation_pair[0], violation_pair[1], "violation"),
        ("边界", low, low, "boundary"),
        ("空值", None, high, "null"),
    ]
    return _apply_numeric_null_case_expectations(definition, [
        {
            "name": name,
            "row": {left_name: left_value, right_name: right_value},
            "expected_count": _expected_count(kind, op, equality_policy, "field"),
        }
        for name, left_value, right_value, kind in samples
    ])


def _comparison_assignment(
    definition: dict[str, Any],
    spec: dict[str, Any],
    base_types: dict[str, Any],
    related_types: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    expression = definition.get("expression") or {}
    op = str(expression.get("op") or "lt")
    right_type = str(expression.get("right_type") or "field")
    if right_type == "value":
        normal, violation = value_sample_pair(op, expression.get("right"))
        return {
            "normal": {expression["left"]: normal},
            "violation": {expression["left"]: violation},
            "boundary": {expression["left"]: expression.get("right")},
        }
    left_type = base_types.get(expression["left"]) or related_types.get(expression["right"])
    low, high = ordered_values(left_type)
    normal_pair, violation_pair = sample_pairs(op, low, high)
    right_field = expression["right"]
    return {
        "normal": {expression["left"]: normal_pair[0], right_field: normal_pair[1]},
        "violation": {expression["left"]: violation_pair[0], right_field: violation_pair[1]},
        "boundary": {expression["left"]: low, right_field: low},
    }


def _group_cases(
    definition: dict[str, Any], spec: dict[str, Any], base: dict[str, Any], related: dict[str, Any],
    period: str, base_types: dict[str, Any], related_types: dict[str, Any],
) -> list[dict[str, Any]]:
    """逐项改变操作数、合成组合与范围样本；用单项比较的已知语义设置预期。"""
    conditions = comparison_conditions(definition)
    cases = []
    join = spec["join"]

    def add(name, base_values, related_values, *, matched=True):
        row = {"base": dict(base_values), "related": [dict(related_values)] if join and matched else [],
               "report_date": period}
        if any(case["row"] == row for case in cases):
            return
        # 默认样本至多有一条关联行。以已有单条件实现独立建立预期，重测才执行组求值器。
        scope = {**definition, "expression": {"left": definition.get("report_date_field") or "report_date",
                                              "op": "is_not_null"}, "null_policy": "skip"}
        count, kind = 0, None
        if _relational_evaluation(scope, row)[0]:
            results = [_relational_evaluation({**definition, "expression": item}, row) for item in conditions]
            combine = any if definition["expression"]["logic"] == "any" else all
            if combine(hit and issue != "missing_value" for hit, issue in results):
                count = 1
                kind = "numeric" if definition.get("null_policy") in ("zero", "review") else "comparison"
            elif combine(hit for hit, _ in results):
                count, kind = 1, "missing_value"
        case = {"name": name, "row": row, "expected_count": count}
        if kind:
            case["expected_issue_kind"] = kind
        cases.append(case)

    # 模板数据先使用列类型，再由筛选、日期、关联键确定测试范围。未传列类型时数值常量仍为数值。
    for item in conditions:
        if item.get("right_type") == "value" and not base_types.get(item["left"]):
            base[item["left"]] = item["right"]
    add("范围内基准值", base, related)
    combined = {state: (dict(base), dict(related)) for state in ("命中", "未命中")}
    bounds: dict[str, list[Any]] = {}
    for index, item in enumerate(conditions, 1):
        left, op = item["left"], item["op"]
        data_type = base_types.get(left)
        low, high = (1, 2) if type_family(data_type) == "number" else ordered_values(data_type)
        right_name = None
        if op in UNARY_OPS:
            non_null = base[left] if base[left] is not None else low
            values = [("命中", None if op == "is_null" else non_null, None),
                      ("未命中", non_null if op == "is_null" else None, None)]
        elif item.get("right_type") == "value":
            bound = item["right"]
            normal, hit = value_sample_pair(op, bound)
            bounds.setdefault(left, []).append(bound)
            values = [("命中", hit, None), ("未命中", normal, None), ("边界", bound, None), ("空值", None, None)]
        else:
            right_name = item["right"]
            normal, hit = sample_pairs(op, low, high)
            values = [("命中", *hit), ("未命中", *normal), ("边界", low, low),
                      ("左侧空值", None, high), ("右侧空值", low, None)]
        for label, left_value, right_value in values:
            main, other = dict(base), dict(related)
            main[left] = left_value
            if right_name is not None:
                (other if item.get("right_table") == RELATED else main)[right_name] = right_value
            add(f"条件 {index} · {label}取值", main, other)
            if label in combined:
                both_base, both_other = combined[label]
                both_base[left] = left_value
                if right_name is not None:
                    (both_other if item.get("right_table") == RELATED else both_base)[right_name] = right_value
    for label, (main, other) in combined.items():
        add(f"组合{label}取值", main, other)
    for field, thresholds in bounds.items():
        ordered = sorted(set(thresholds))
        for lo, hi in zip(ordered, ordered[1:]):
            # 先分别取半，避免两端求和溢出；超大整数用整数中点。
            middle = (lo + hi) // 2 if isinstance(lo, int) and isinstance(hi, int) and hi - lo > 1 else None
            if middle is None:
                try:
                    middle = lo / 2 + hi / 2
                except OverflowError:
                    continue
            if lo < middle < hi:
                add(f"{field} 区间内", {**base, field: middle}, related)
    witness = next((case["row"] for case in cases if case["expected_count"] == 1), cases[0]["row"])
    main = witness["base"]
    other = (witness["related"] or [{}])[0]
    for index, item in enumerate(spec["filters"], 1):
        filtered_base, filtered_other = dict(main), dict(other)
        side, types = (filtered_other, related_types) if item["table"] == RELATED else (filtered_base, base_types)
        side[item["field"]] = _fail_value(item, types.get(item["field"]))
        add(f"筛选 {index} 不命中", filtered_base, filtered_other)
    if join:
        add("无关联记录", main, other, matched=False)
        add("跨期关联记录", main, {**other, join["report_date_field"]: "2000-01-01"})
    return cases


def _nested_cases(
    definition: dict[str, Any],
    base_columns: list[dict[str, Any]] | None,
    related_columns: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    spec = validate_query_spec(definition)
    join = spec["join"]
    expression = definition.get("expression") or {}
    base_types = _column_types(base_columns)
    related_types = _column_types(related_columns)
    if join is not None and related_columns is None:
        raise AppError("VALIDATION_ERROR")
    base_fields, related_fields = case_fields(definition)
    anchor = (_datetime.date.today() + _datetime.timedelta(days=1)).isoformat()

    base_filters = {item["field"]: item for item in spec["filters"] if item["table"] == BASE}
    related_filters = {item["field"]: item for item in spec["filters"] if item["table"] == RELATED}
    left_keys = {pair["left"]: pair["right"] for pair in join["on"]} if join else {}
    right_keys = {pair["right"]: pair["left"] for pair in join["on"]} if join else {}

    def base_row() -> dict[str, Any]:
        row: dict[str, Any] = {}
        for field in base_fields:
            if field == str(definition.get("report_date_field") or "report_date"):
                row[field] = anchor
            elif field == expression.get("left"):
                row[field] = ordered_values(base_types.get(field))[0]
            elif (
                str(expression.get("right_type") or "field") == "field"
                and spec["right_table"] != RELATED
                and field == expression.get("right")
            ):
                row[field] = ordered_values(base_types.get(field))[1]
            elif field in base_filters:
                row[field] = _pass_value(base_filters[field], base_types.get(field))
            elif field in left_keys:
                row[field] = ordered_values(base_types.get(field))[0]
            else:
                row[field] = ordered_values(base_types.get(field))[0]
        return row

    def related_row(
        *,
        matched: bool = True,
        date: str | None = None,
        key_value: Any = _SKIP,
        comparison_values: dict[str, Any] | None = None,
        filter_overrides: dict[str, Any] | None = None,
        null_key: bool = False,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for field in related_fields:
            if join is None:
                continue
            if field == join["report_date_field"]:
                row[field] = date or anchor
            elif field in right_keys:
                base_value = base_row().get(right_keys[field])
                if null_key:
                    row[field] = None
                elif not matched:
                    row[field] = key_value if key_value is not _SKIP else _alternate(base_value, related_types.get(field))
                else:
                    row[field] = base_value
            elif comparison_values is not None and field in comparison_values:
                row[field] = comparison_values[field]
            elif field in related_filters:
                row[field] = (filter_overrides or {}).get(
                    field, _pass_value(related_filters[field], related_types.get(field)),
                )
            else:
                row[field] = ordered_values(related_types.get(field))[0]
        return row

    if is_condition_group(definition):
        return _group_cases(definition, spec, base_row(), related_row(), anchor, base_types, related_types)
    assignment = {} if is_unary(definition) else _comparison_assignment(
        definition, spec, base_types, related_types,
    )

    def build(kind: str, related_rows: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        base = base_row()
        values = assignment.get(kind) or {}
        for field, value in values.items():
            if field in base_fields:
                base[field] = value
        rows = related_rows if related_rows is not None else (
            [related_row(comparison_values=values)] if join is not None else []
        )
        return base, rows

    cases: list[dict[str, Any]] = []

    def add(name: str, expected: int, base: dict[str, Any], related: list[dict[str, Any]]) -> None:
        cases.append({
            "name": name,
            "row": {"base": base, "related": related, "report_date": anchor},
            "expected_count": expected,
        })

    if join and join.get("right_aggregate") == "sum":
        left, right = expression["left"], expression["right"]
        def sum_case(name, amount, parts, expected, issue_kind=None):
            base = {**base_row(), left: amount}
            rows = [related_row(comparison_values={right: value}) for value in parts]
            add(name, expected, base, rows)
            if issue_kind:
                cases[-1]["expected_issue_kind"] = issue_kind
        sum_case("两笔相同明细合计一致", 8, [4, 4], 0)
        sum_case("明细合计有差额", 8, [3, 4], 1, "numeric")
        sum_case("正负明细合计为零", 0, [2, -2], 0)
        sum_case("同日无关联明细", 0, [], 1, "missing_value")
        zero = definition.get("null_policy") == "zero"
        sum_case("明细中一项缺值", 4, [4, None], 0 if zero else 1, None if zero else "missing_value")
        sum_case("主表原值缺失", None, [0], 0 if zero else 1, None if zero else "missing_value")
        base = {**base_row(), left: 2}
        other_day = (_datetime.date.fromisoformat(anchor) - _datetime.timedelta(days=1)).isoformat()
        add("跨期明细不计入", 0, base, [related_row(comparison_values={right: 2}),
                                      related_row(date=other_day, comparison_values={right: 10})])
        return cases

    if is_unary(definition):
        left_field = expression["left"]
        sample = ordered_values(base_types.get(left_field))[0]
        normal_value = sample if expression["op"] == "is_null" else None
        violating_value = None if expression["op"] == "is_null" else sample

        def unary_build(value: Any, related_rows: list[dict[str, Any]] | None = None):
            base = base_row()
            base[left_field] = value
            rows = related_rows if related_rows is not None else (
                [related_row()] if join is not None else []
            )
            return base, rows

        add("正常", 0, *unary_build(normal_value))
        add("明显异常", 1, *unary_build(violating_value))
        add("空值", 1 if expression["op"] == "is_null" else 0, *unary_build(None))
        # 空串边界只对文本型生成；DATE/NUMBER 列不应出现空串样本。
        if _base_type(base_types.get(left_field)) not in _DATE_TYPES | _NUMBER_TYPES:
            add("边界", 0 if expression["op"] == "is_null" else 1, *unary_build(""))

        if base_filters:
            fail_base, fail_rows = unary_build(violating_value)
            field = next(iter(base_filters))
            fail_base[field] = _fail_value(base_filters[field], base_types.get(field))
            add("筛选不命中", 0, fail_base, fail_rows)

        if join is not None:
            add("关联多行", 1, *unary_build(
                violating_value, [related_row(), related_row()],
            ))
            date_base, date_rows = unary_build(violating_value, [related_row()])
            if date_rows:
                date_rows[0][join["report_date_field"]] = (
                    _datetime.date.today() + _datetime.timedelta(days=2)
                ).isoformat()
            add("日期不一致", 0, date_base, date_rows)
            add("无关联记录", 0, *unary_build(violating_value, []))
            empty_key_base, empty_key_rows = unary_build(violating_value, [related_row(null_key=True)])
            add("关联键为空", 0, empty_key_base, empty_key_rows)
            if related_filters:
                filter_base, filter_rows = unary_build(violating_value, [related_row()])
                if filter_rows:
                    field = next(iter(related_filters))
                    filter_rows[0][field] = _fail_value(related_filters[field], related_types.get(field))
                add("关联筛选不命中", 0, filter_base, filter_rows)
        return cases

    normal_base, normal_rows = build("normal")
    add("正常", 0, normal_base, normal_rows)

    violation_base, violation_rows = build("violation")
    add("明显异常", 1, violation_base, violation_rows)

    boundary_base, boundary_rows = build("boundary")
    add("边界", _expected_count("boundary", str(expression.get("op") or "lt"), str(definition.get("equality_policy") or ""), "value" if expression.get("right_type") == "value" else "field"), boundary_base, boundary_rows)

    null_base, null_rows = build("normal")
    if spec["right_table"] == RELATED and null_rows:
        null_rows[0][expression["right"]] = None
    else:
        null_base[expression["left"]] = None
    add("空值", 0, null_base, null_rows)

    if join is not None:
        multi_base, multi_rows = build("normal")
        if spec["right_table"] == RELATED:
            multi_base[expression["left"]] = assignment["violation"][expression["left"]]
            extra = related_row(comparison_values=assignment["violation"])
            multi_rows = list(multi_rows) + [extra]
        else:
            multi_base[expression["left"]] = assignment["violation"][expression["left"]]
            multi_rows = list(multi_rows) + [related_row()]
        add("关联多行", 1, multi_base, multi_rows)

        date_base, date_rows = build("violation")
        if date_rows:
            date_rows[0][join["report_date_field"]] = (
                _datetime.date.today() + _datetime.timedelta(days=2)
            ).isoformat()
        add("日期不一致", 0, date_base, date_rows)

    if base_filters:
        fail_base, fail_rows = build("violation")
        field = next(iter(base_filters))
        fail_base[field] = _fail_value(base_filters[field], base_types.get(field))
        add("筛选不命中", 0, fail_base, fail_rows)

    if join is not None:
        add("无关联记录", 0, *build("violation", related_rows=[]))

        empty_key_base, empty_key_rows = build("violation")
        if empty_key_rows:
            empty_key_rows[0][join["on"][0]["right"]] = None
        add("关联键为空", 0, empty_key_base, empty_key_rows)

        if related_filters:
            filter_base, filter_rows = build("violation")
            if filter_rows:
                field = next(iter(related_filters))
                filter_rows[0][field] = _fail_value(related_filters[field], related_types.get(field))
            add("关联筛选不命中", 0, filter_base, filter_rows)

    return _apply_numeric_null_case_expectations(definition, cases)


def default_cases(
    definition: dict[str, Any],
    columns: list[dict[str, Any]] | None = None,
    related_columns: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if "project_driver" in definition:
        from .project_driver_samples import default_project_cases
        return default_project_cases(definition, columns, related_columns)
    if is_new_spec(definition):
        return _nested_cases(definition, columns, related_columns)
    return _legacy_flat_cases(definition, columns)


def default_field_compare_cases(
    definition: dict[str, Any],
    columns: list[dict[str, Any]] | None = None,
    related_columns: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return default_cases(definition, columns, related_columns)
