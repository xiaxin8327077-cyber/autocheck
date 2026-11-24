"""Document-field arithmetic for a single row. Trees contain no executable text."""

import math
import operator
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from .contracts import AppError


_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BINARY = {"+": operator.add, "-": operator.sub, "*": operator.mul, "/": operator.truediv}
_COMPARISONS = {"eq": ("=", operator.eq), "neq": ("<>", operator.ne), "lt": ("<", operator.lt),
                "lte": ("<=", operator.le), "gt": (">", operator.gt), "gte": (">=", operator.ge)}
CALCULATION_MESSAGE = "公式无法计算：除数为 0"


def _tree_fields(tree):
    fields = []
    count = 0

    def visit(node, depth):
        nonlocal count
        count += 1
        if type(node) is not dict or depth > 96 or count > 1023:
            raise AppError("VALIDATION_ERROR")
        if node.keys() == {"field"}:
            name = node["field"]
            if not isinstance(name, str) or not _FIELD.fullmatch(name):
                raise AppError("VALIDATION_ERROR")
            if name not in fields:
                fields.append(name)
        elif node.keys() == {"value"}:
            value = node["value"]
            if not (type(value) is int
                    or type(value) is float and math.isfinite(value)):
                raise AppError("VALIDATION_ERROR")
        elif node.keys() == {"op", "left", "right"} and isinstance(node["op"], str) and node["op"] in _BINARY:
            visit(node["left"], depth + 1)
            visit(node["right"], depth + 1)
        else:
            raise AppError("VALIDATION_ERROR")

    visit(tree, 0)
    return fields


def formula_fields(tree):
    """Validate an arithmetic operation and return its distinct input fields in order."""
    fields = _tree_fields(tree)
    if "op" not in tree:
        raise AppError("VALIDATION_ERROR")
    return fields


def is_arithmetic(expr):
    return isinstance(expr, dict) and (expr.get("left_type") == "formula" or expr.get("right_type") == "formula")


def has_arithmetic(expr):
    return is_arithmetic(expr) or (isinstance(expr, dict) and isinstance(expr.get("conditions"), list)
                                   and any(is_arithmetic(item) for item in expr["conditions"]))


def _operand_tree(expr, side):
    kind = expr.get(side + "_type", "field")
    if kind == "formula":
        formula_fields(expr.get(side))
        return expr[side]
    if kind == "field" or (kind == "value" and side == "right"):
        node = {kind: expr.get(side)}
        _tree_fields(node)
        return node
    raise AppError("VALIDATION_ERROR")


def arithmetic_fields(expr):
    if (expr.keys() - {"left_type", "left", "op", "right_type", "right", "right_table"}
            or expr.get("right_table", "base") != "base"
            or not isinstance(expr.get("op"), str) or expr["op"] not in _COMPARISONS):
        raise AppError("VALIDATION_ERROR")
    names = list(dict.fromkeys(name for side in ("left", "right") for name in _tree_fields(_operand_tree(expr, side))))
    return names


def arithmetic_projection(expr):
    """Return the compared values and each input field from either arithmetic tree."""
    fields = arithmetic_fields(expr)
    left = expr["left"] if expr.get("left_type", "field") == "field" else ""
    right = expr["right"] if expr.get("right_type", "field") == "field" else ""
    inputs = [name for name in fields if name not in (left, right)]
    return [("checked_value", left, False), ("comparison_value", right, False),
            *((f"formula_field_{index}", name, False) for index, name in enumerate(inputs, 1))]


def _number(value):
    if value is None:
        return None
    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        raise AppError("VALIDATION_ERROR")
    try:
        number = Decimal(str(value))
        if number.is_finite():
            return number
    except InvalidOperation:
        pass
    raise AppError("VALIDATION_ERROR")


def formula_value(tree, row, zero_fields):
    """Return the decimal result and whether a zero denominator occurred at any depth."""
    _tree_fields(tree)
    zero_denominator = False

    def visit(node):
        nonlocal zero_denominator
        if "field" in node:
            field = node["field"]
            value = row.get(field)
            return Decimal(0) if value is None and field in zero_fields else _number(value)
        if "value" in node:
            return _number(node["value"])
        left, right = visit(node["left"]), visit(node["right"])
        if node["op"] == "/" and right == 0:
            zero_denominator = True
            return None
        if left is None or right is None:
            return None
        return _BINARY[node["op"]](left, right)

    with localcontext() as context:
        context.prec = 100
        value = visit(tree)
    return value, zero_denominator


def _zero_fields(definition, names):
    if definition["null_policy"] == "zero":
        return set(names)
    if definition["null_policy"] != "review":
        return set()
    return {item["field"] for item in definition.get("null_evidence") or []
            if item["field"] in names and item.get("side") in ("left", "right")}


def evaluate_formula(definition, row):
    expr = definition["expression"]
    names = arithmetic_fields(expr)
    zero = _zero_fields(definition, names)
    missing = any(row.get(name) is None for name in names if name not in zero)
    left, left_error = formula_value(_operand_tree(expr, "left"), row, zero)
    right, right_error = formula_value(_operand_tree(expr, "right"), row, zero)
    if left_error or right_error:
        return 1, "calculation_error"
    if missing:
        return (0, None) if definition["null_policy"] == "skip" else (1, "missing_value")
    return (1, "numeric") if _COMPARISONS[expr["op"]][1](left, right) else (0, None)


def formula_sample_rows(definition, seed):
    """Build JSON-serializable synthetic operands, including equality, differences and missing inputs."""
    expr = definition["expression"]
    fields = arithmetic_fields(expr)
    filtered = {item["field"] for item in definition.get("filters", []) if item.get("table", "base") == "base"}
    base = dict(seed)
    for index, name in enumerate(fields, 1):
        if name not in filtered:
            base[name] = index + 1
    yield "公式操作数", base
    left, right = _operand_tree(expr, "left"), _operand_tree(expr, "right")
    adjustable = None
    target = None
    if "field" in left and left["field"] not in _tree_fields(right):
        adjustable, target = left["field"], right
    elif "field" in right and right["field"] not in _tree_fields(left):
        adjustable, target = right["field"], left
    if adjustable:
        result, _ = formula_value(target, base, set())
        boundary = base
        if result is None or not _json_exact(result):
            # Try a second witness with simple factors. A rounded recurring decimal
            # cannot serve as an equality boundary in a JSON number sample.
            boundary = {**base, **{name: 1 for name in fields if name not in filtered}}
            result, _ = formula_value(target, boundary, set())
    if adjustable and result is not None:
        for label, delta in [("等于计算值", 0), ("低于计算值", -1), ("高于计算值", 1)]:
            value = result + delta
            if not _json_exact(value):
                continue
            yield label, {**boundary, adjustable: int(value) if value == value.to_integral_value() else float(value)}
    for name in fields:
        yield f"{name} 缺值", {**base, name: None}
        yield f"{name} 取负值", {**base, name: -1}
    yield "操作数均为零", {**base, **dict.fromkeys(fields, 0)}


def _json_exact(number):
    if number == number.to_integral_value():
        return True
    value = float(number)
    return math.isfinite(value) and Decimal(str(value)) == number


@dataclass(frozen=True)
class FormulaSql:
    checked: str
    value: str
    comparison: str
    zero_denominator: str
    hit: str
    kind: str
    message: str


def compile_formula(definition, column, params, message, *, prefix="formula"):
    """Compile validated arithmetic using the caller's quoted column references and bind map."""
    expr = definition["expression"]
    names = arithmetic_fields(expr)
    zero = _zero_fields(definition, names)
    denominators = []
    constant_count = 0

    def operand(name):
        raw = column(name)
        return f"COALESCE({raw}, 0)" if name in zero else raw

    def visit(node):
        nonlocal constant_count
        if "field" in node:
            return operand(node["field"])
        if "value" in node:
            constant_count += 1
            key = f"{prefix}_value_{constant_count}"
            params[key] = node["value"]
            return ":" + key
        left, right = visit(node["left"]), visit(node["right"])
        if node["op"] == "/":
            denominators.append(f"{right} = 0")
            # A decimal literal promotes integer operands in PostgreSQL, preserves decimal
            # arithmetic in MySQL, and gives fractional results in SQLite verification.
            return f"(1.000000000000000000 * {left} / NULLIF({right}, 0))"
        if "op" not in node["left"] and "op" not in node["right"]:
            # PostgreSQL and MySQL can overflow within an integer subtree before a
            # decimal parent operation sees its result. Promote the first operation
            # in each branch; the native decimal type then propagates to its parent.
            if definition.get("dialect") == "postgresql":
                left = f"CAST({left} AS NUMERIC)"
            else:
                left = f"(CAST(1 AS DECIMAL(1,0)) * {left})"
        return f"({left} {node['op']} {right})"

    checked = visit(_operand_tree(expr, "left"))
    value = visit(_operand_tree(expr, "right"))
    check = f"{checked} {_COMPARISONS[expr['op']][0]} {value}"
    if expr.get("left_type", "field") == "field":
        checked = column(expr["left"])
    if expr.get("right_type", "field") == "field":
        value = column(expr["right"])
    cases = []
    error = ""
    if denominators:
        error = "(" + " OR ".join(denominators) + ")"
        cases.append((error, "calculation_error", CALCULATION_MESSAGE))
    if definition["null_policy"] == "review":
        missing = [column(name) + " IS NULL" for name in names if name not in zero]
        if missing:
            cases.append(("(" + " OR ".join(missing) + ")", "missing_value", "缺值待核实：公式字段为 NULL"))
    hit = "(" + " OR ".join([*(condition for condition, _, _ in cases), check]) + ")"
    if not cases:
        return FormulaSql(checked, value, check, error, hit, "'numeric'", message)
    kinds = " ".join(f"WHEN {condition} THEN '{kind}'" for condition, kind, _ in cases)
    messages = " ".join(f"WHEN {condition} THEN '{label}'" for condition, _, label in cases)
    return FormulaSql(checked, value, check, error, hit, f"CASE {kinds} ELSE 'numeric' END", f"CASE {messages} ELSE {message} END")


def group_formula_parts(definition, column, params, message):
    return {index: compile_formula({**definition, "expression": item}, column, params, message, prefix=f"formula_{index}")
            for index, item in enumerate(definition["expression"].get("conditions", []), 1) if is_arithmetic(item)}


def group_formula_projection(parts, conditions):
    for index, formula in parts.items():
        suffix = f"_{index}" if index > 1 else ""
        for role, field, other in arithmetic_projection(conditions[index - 1]):
            value = formula.checked if role == "checked_value" else formula.value if role == "comparison_value" else None
            yield role + suffix, field, value
