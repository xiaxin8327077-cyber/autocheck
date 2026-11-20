"""Record only field choices offered by the originating analysis and verified by preview."""
from copy import deepcopy
import re

from .analysis_reuse import analysis_baseline


def _operand(expression, target):
    match = re.fullmatch(r"expression\.(?:conditions\.(\d+)\.)?(left|right)", target)
    if not match:
        return None
    condition = expression
    if match[1] is not None:
        index = int(match[1])
        conditions = expression.get("conditions") or []
        if index >= len(conditions):
            return None
        condition = conditions[index]
    return (condition, match[2]) if isinstance(condition.get(match[2]), str) else None


def selected_baseline(previous, verified, fields):
    alternatives = [entry["candidate"] for entry in previous.get("candidate_options") or []]
    candidates = alternatives or [previous]
    for candidate in candidates:
        questions = candidate.get("questions") or []
        description = candidate.get("description") or ""
        descriptions = {description}
        if (verified["expression"].get("op") == "is_null"
                and any(q["id"] == "check_requirement" and any(o.get("value") == "not_empty" for o in q["options"])
                        for q in questions)):
            descriptions.add(description.strip() + "不得为空")
        if (candidate.get("table_name") != verified.get("table_name")
                or candidate.get("source_id") != verified.get("source_id")
                or (candidate.get("report_category") and candidate["report_category"] != verified.get("report_category"))
                or verified.get("description") not in descriptions
                or candidate.get("rule_type") != verified.get("rule_type")):
            continue
        expression = deepcopy(candidate.get("expression") or {})
        filters = list(candidate.get("filters") or [])
        category = candidate.get("report_category") or ""
        selected = False
        for question in questions:
            key = question["id"]
            options = question.get("options") or []
            if key.startswith("expression."):
                targets = question.get("targets") or [key]
                proposed = [_operand(verified["expression"], path) for path in targets]
                original = [_operand(expression, path) for path in targets]
                if not all(proposed) or not all(original):
                    continue
                values = {row[side] for row, side in proposed}
                if len(values) == 1 and any(option.get("value") in values for option in options):
                    value = values.pop()
                    for row, side in original:
                        row[side] = value
                    selected = True
            elif key == "report_category" and any(o.get("value") == verified.get("report_category") for o in options):
                category = verified["report_category"]
                selected = True
            elif match := re.fullmatch(r"filters\.(\d+)", key):
                index = int(match[1])
                actual = verified.get("filters") or []
                if (index < min(len(actual), len(filters)) and actual[index].get("confirmed") is True
                        and any(option.get("selection") == actual[index] for option in options)):
                    filters[index] = actual[index]
                    selected = True
        # Only use a matching original shape with approved substitutions; unrelated edits cannot enter memory.
        if ((selected or alternatives) and expression == verified["expression"]
                and filters == (verified.get("filters") or [])):
            baseline = analysis_baseline({**candidate, "expression": expression, "filters": filters, "report_category": category}, fields)
            baseline["requires_selection"] = True
            baseline["has_alternatives"] = bool(alternatives)
            return baseline
    return None
