"""Exact-request keys and replayable model structures, before user confirmation."""
from copy import deepcopy

from .analysis_memory import context_key, digest


# Increment when the local interpretation of stored model structures becomes incompatible.
CACHE_FORMAT_VERSION = 3
_SELECTION_FIELDS = (
    "target", "table", "related_target", "report_category", "candidate_targets",
    "result_type", "uncertainties", "unsupported_requirements", "dictionary_questions", "ai_suggestions", "project_driver",
)
_DRAFT_FIELDS = (
    "rule_name", "rule_type", "expression", "violation_message", "null_policy", "equality_policy",
    "semantic_intent", "filters", "join", "target", "related_target", "report_category", "recommended",
    "match_reason", "ai_suggestions", "uncertainties", "unsupported_requirements", "dictionary_questions", "plan_mode",
    "interpretation_exclusions", "business_key", "project_driver",
)


def result_key(context, request):
    namespace = context_key(context)
    if not namespace or not isinstance(request, str) or not request.strip():
        return ""
    # Preserve internal whitespace, punctuation and literal values exactly.
    return digest([CACHE_FORMAT_VERSION, namespace, request.strip()])


def _draft_snapshot(draft):
    result = _pick(draft, _DRAFT_FIELDS)
    for key in ("target", "related_target"):
        if key in result:
            result[key] = _pick(result[key], ("table", "report_category"))
    if isinstance(result.get("ai_suggestions"), list):
        result["ai_suggestions"] = [_suggestion_snapshot(item) for item in result["ai_suggestions"] if isinstance(item, dict)]
    elif "ai_suggestions" in result:
        result["ai_suggestions"] = []
    intent = result.get("semantic_intent")
    if isinstance(intent, dict):
        result["semantic_intent"] = semantic_intent_snapshot(intent)
    return result


def semantic_intent_snapshot(intent):
    result = _pick(intent, ("metrics", "scopes", "open_questions"))
    result["metrics"] = [_pick(item, ("term", "side", "fields", "recommended", "condition_index", "formula_path", "rule_names"))
                         for item in intent.get("metrics", [])]
    result["scopes"] = [_pick(item, ("category", "table", "fields", "recommended", "memberships", "excluded_fields"))
                        for item in intent.get("scopes", [])]
    return result


def _pick(value, fields):
    return {key: deepcopy(value[key]) for key in fields if key in value} if isinstance(value, dict) else deepcopy(value)


def _suggestion_snapshot(item):
    result = _pick(item, ("category", "title", "reason", "references", "preconditions", "limitations", "kind",
                          "requires_aggregation", "operations", "ops", "requires", "scope_replacements", "check_target"))
    if isinstance(result.get("references"), list):
        result["references"] = [_pick(ref, ("table_name", "field_name")) for ref in result["references"]]
    if isinstance(result.get("scope_replacements"), list):
        result["scope_replacements"] = [_pick(change, ("table_name", "field_name", "op", "value"))
                                         for change in result["scope_replacements"]]
    if isinstance(result.get("check_target"), dict):
        result["check_target"] = _pick(result["check_target"], ("table_name", "related_table_name", "expression"))
    if isinstance(item.get("expression"), dict):
        result["expression"] = deepcopy(item["expression"])
    if item.get("sql") not in (None, ""):
        # Preserve the existing rejected-SQL notice without storing its contents.
        result["sql"] = True
    return result


def model_snapshot(selection, draft=None):
    result = {"selection": {key: deepcopy(selection[key]) for key in _SELECTION_FIELDS if key in selection}}
    if isinstance(result["selection"].get("ai_suggestions"), list):
        result["selection"]["ai_suggestions"] = [_suggestion_snapshot(item) for item in selection["ai_suggestions"]
                                                if isinstance(item, dict)]
    for key in ("target", "related_target"):
        if key in result["selection"]:
            result["selection"][key] = _pick(result["selection"][key], ("table", "report_category"))
    if "candidate_targets" in result["selection"]:
        targets = []
        for item in result["selection"]["candidate_targets"]:
            target = _pick(item, ("table", "target", "related_target", "report_category"))
            for key in ("target", "related_target"):
                if key in target:
                    target[key] = _pick(target[key], ("table", "report_category"))
            targets.append(target)
        result["selection"]["candidate_targets"] = targets
    if draft is not None:
        if "plans" in draft:
            result["draft"] = _draft_snapshot(_pick(draft, ("plan_mode", "ai_suggestions", "interpretation_exclusions")))
            result["draft"]["plans"] = [_draft_snapshot(plan) for plan in draft["plans"]]
        else:
            result["draft"] = _draft_snapshot(draft)
    return result
