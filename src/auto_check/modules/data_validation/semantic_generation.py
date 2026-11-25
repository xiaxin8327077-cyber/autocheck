"""Model-led analysis of requests against an authorized, versioned document."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
import re
from threading import current_thread
import unicodedata
from uuid import uuid4

from .adoption_scope import (adopted_join_matches, adopted_scope_label, apply_period_check, attach_period_applicability,
                             bind_adopted_join, bind_period_filters, distinguish_adopted_scopes, name_adopted_scope,
                             reconcile_confirmed_scope_partitions, verify_adopted_goal, verify_bound_period_filters)
from .ai_service import model_expression, model_judgment, refine_candidate
from .ai_suggestions import CATEGORIES, KINDS, MAX_REFERENCES, MAX_SUGGESTIONS, build_ai_suggestions
from .analysis_reuse import memory_choice
from .analysis_memory import digest
from .analysis_jobs import AnalysisControl, MAX_MODEL_ROUNDS
from .analysis_result_cache import model_snapshot, semantic_intent_snapshot
from .candidate_choices import check_without_category_prefix, difference_lines, document_category, document_display, option_id
from .candidate_preview import candidate_definition, compile_prepared_preview
from .conditional_reviews import category_scope_only
from .document_evidence import DocumentEvidence, _business_aliases, compact_directory, documented_equation, referenced_fields
from .documented_origins import drop_unused_project_lookup, prefer_document_origin
from .documented_choices import (
    ScopeEvidenceRequired, bind_shared_measure, choice_identity, document_choices, exclusion_supported, missing_registered_grain,
    plan_facts, qualified_peer_choice, verified_null_policy, verify_grain_facts,
)
from .contracts import AppError, PBC_REPORT_CATEGORIES, PBC_SHARED_CATEGORY, PBC_SHARED_CATEGORY_NAME
from .generation_policy import clarification_candidate, merge
from .interpretation_roles import defer_period_metric_choices, deferred_period_fields
from .formula import arithmetic_fields, formula_fields, has_arithmetic, is_arithmetic
from .model_calls import LOGGER, failure, semantic_completion
from .parallel_checks import parse_mixed_group, parse_numeric_group
from .prompt_defaults import (
    DEFAULT_PROMPTS, SEMANTIC_CALL_OPTIONS, SEMANTIC_COMBINED_EXAMPLE, SEMANTIC_MAX_BUDGET_UNITS, SEMANTIC_MAX_PLANS,
    SEMANTIC_OUTPUT_CONTRACT, SEMANTIC_SELECTION_CONTRACT, SEMANTIC_TOTAL_OUTPUT_TOKENS,
    semantic_budget_instruction,
)
from .project_driver import normalize_project_driver
from .query_grounding import _check_numeric_requirement, dictionary_options
from .query_spec import MAX_CONDITIONS, apply_numeric_null_policy, is_condition_group, is_finite_number, is_numeric_comparison, is_unary, type_family, valid_comparison_literal
from .request_text_predicates import bind_text_predicates
from .request_scopes import bind_conditional_text_scopes
from .text_requirements import bind_named_dictionary_requirements
from .semantic_grounding import _document_codes, _metric_slot, _roles, _scope_options, _Unbound, apply_dictionary_answers, dictionary_partition_question, ground_semantic_candidate, join_decisions_refine


SEMANTIC_MEMORY_CONTRACT = (
    "\n历史请求和结构仅作参考数据，请按当前需求和活动文档独立核实对象、指标、范围、阈值及待确认项。"
    "当新请求修改明确数值时，重新核实表达式常量。相同表名也要核对报送分类。"
    "不把他人选择或以前的推荐当作本次确认；仅对 current_owner_choices 中仍适用的本人选择予以保留。"
    "最外层另给 reuse_decision。采用或调整某项记忆时填 reuse 或 adapt，并给从 0 起的 memory_index；"
    "其余填 fresh 并按当前需求独立生成。无论是否采用记忆，证据充分就在本轮给出 target 和完整 draft，"
    "证据不足按上方协议请求展开或澄清。不要在回复中转述历史请求或旧 SQL。参考数据："
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def suggestion_backed_interpretations(missing, draft, table_name, suggestions):
    """Review a document candidate which the model itself identifies as a corresponding metric."""
    expression = draft.get("expression") or {}
    parts = expression.get("conditions", [expression]) if isinstance(expression, dict) else []
    if not isinstance(parts, list):
        return []
    primary = {index: (table_name, part["left"]) for index, part in enumerate(parts)
               if isinstance(part, dict) and isinstance(part.get("left"), str)}
    references = []
    for item in suggestions:
        if not isinstance(item, dict) or item.get("category") != "consistency" or item.get("kind") != "aggregate_consistency":
            continue
        refs = item.get("references") or []
        if not isinstance(refs, list):
            continue
        pairs = {(ref.get("table_name"), ref.get("field_name")) for ref in refs
                 if isinstance(ref, dict) and isinstance(ref.get("table_name"), str) and isinstance(ref.get("field_name"), str)}
        references.append(pairs)
    return [check for check in missing if check.get("kind") == "metrics" and check.get("side") == "left"
            and check.get("table") != table_name
            and any(primary.get(check.get("condition_index", 0)) in pairs
                    and (check.get("table"), check.get("field")) in pairs for pairs in references)]


def _execution_signature(definition):
    """Compare verified execution definitions without altering stored values or their order."""
    def freeze(value, path=(), *, unordered=False):
        if isinstance(value, dict):
            items = []
            for key, child in sorted(value.items()):
                child_path = (*path, key)
                commutative = (
                    child_path in (("filters",), ("null_evidence",))
                    or (child_path == ("expression", "conditions") and value.get("logic") in ("all", "any"))
                    or (child_path == ("filters", "value") and value.get("op") in ("in", "not_in"))
                )
                items.append((key, freeze(child, child_path, unordered=commutative)))
            return ("object", tuple(items))
        if isinstance(value, list):
            elements = (freeze(item, path) for item in value)
            return ("list", tuple(sorted(elements) if unordered else elements))
        if type(value) in (int, float):
            return ("number", Decimal(str(value)))
        return (type(value).__name__, value)

    # Result captions are generated from the verified fields in projection order.
    prose = {"name", "description", "violation_message", "semantic_intent", "result_aliases"}
    return freeze({key: value for key, value in definition.items() if key not in prose})


def _literal_parts(text):
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).strip("。.!！?？")
    return re.split(r"(?<![\w.])(-?\d+(?:\.\d+)?)(?![\w.])", text, flags=re.ASCII)


_LITERAL_OPERATOR = re.compile(r"(?:应当|应该|必须|应|须)?(?P<negative>不得|不能|不可|不应|不)?"
                               r"(?P<op>大于等于|小于等于|大于|高于|超过|超出|小于|低于|少于|多于|等于|为|"
                               r"!=|<>|==|[<>]=?|[=≤≥≠])$")
_COMPARISON_KIND = {
    "低于": "<", "小于": "<", "少于": "<", "高于": ">", "大于": ">", "多于": ">", "超过": ">", "超出": ">",
    "小于等于": "<=", "≤": "<=", "大于等于": ">=", "≥": ">=", "等于": "=", "为": "=", "==": "=",
    "!=": "≠", "<>": "≠",
}
_THRESHOLD_UNIT = re.compile(r"(?:亿|万|千|百)?(?:人民币元|美元|港元|欧元|日元|元|份|笔|个基点|基点|个百分点|%)")
_IDENTIFIER_OR_DATE = re.compile(r"(?:日期|年月|年份|年度|编号|代码|编码)(?:为|是|等于|=|:)?$")
_FILTER_OPERATORS = {"<": "lt", ">": "gt", "<=": "lte", ">=": "gte", "=": "eq", "≠": "neq"}
_OPPOSITE_FILTER = {"lt": "gte", "gt": "lte", "lte": "gt", "gte": "lt", "eq": "neq", "neq": "eq"}


def _metric_threshold(parts, labels):
    """Find a single literal directly compared with this documented metric in the request."""
    values = []
    for index in range(1, len(parts), 2):
        before, after = parts[index - 1], parts[index + 1]
        match = _LITERAL_OPERATOR.search(before)
        if not match or not before[:match.start()].endswith(labels):
            continue
        if re.match(r"[年月日:/.-]", after):
            continue
        unit_match = _THRESHOLD_UNIT.match(after)
        if not unit_match and re.match(r"[万亿千百美分角]", after):
            continue
        operator = _COMPARISON_KIND.get(match["op"], match["op"])
        values.append((Decimal(parts[index]), (bool(match["negative"]), operator),
                       unit_match[0] if unit_match else ""))
    return values[0] if len(values) == 1 else None


def _changed_thresholds(analysis, examples):
    """Recognize literal-only edits and rephrased comparisons on the same documented metric."""
    current = _literal_parts(analysis.request)
    changes = set()
    for example in examples:
        previous = _literal_parts(example.get("previous_request", ""))
        edits = []
        if current[::2] == previous[::2]:
            for index in range(1, len(current), 2):
                old, new = Decimal(previous[index]), Decimal(current[index])
                if old != new:
                    edits.append((old, new, index))
        expression = example.get("expression") or {}
        for part in expression.get("conditions", [expression]):
            if part.get("right_type") != "value" or not is_finite_number(part.get("right")):
                continue
            field, old = part["left"], Decimal(str(part["right"]))
            table = analysis.service._memory_table(example, analysis.tables, analysis.categories)
            fields = analysis.fields.get(table["id"], []) if table else []
            labels = tuple(row.get("field_cn") or field for row in fields if row["field_name"] == field)
            if not labels or any(_IDENTIFIER_OR_DATE.search(label) for label in labels):
                continue
            if len(edits) == 1 and edits[0][0] == old and sum(Decimal(v) == old for v in previous[1::2]) == 1:
                _, new, index = edits[0]
                if not (_IDENTIFIER_OR_DATE.search(current[index - 1]) or re.match(r"[年月日:/-]", current[index + 1])):
                    changes.add((field, old, new, ""))
                continue
            labels += (field,)
            new_term = _metric_threshold(current, labels)
            old_term = _metric_threshold(previous, labels)
            if not new_term or not old_term or old_term[0] != old or new_term[1] != old_term[1]:
                continue
            new, _, unit = new_term
            if unit != old_term[2]:
                question = f"请明确当前阈值 {new}{unit} 与指标存储单位之间的换算口径。"
                changes.add((field, old, new, question))
            elif new != old:
                changes.add((field, old, new, ""))
    return changes


def _threshold_question(draft, changes):
    if not changes or not isinstance(draft, dict):
        return ""
    plans = draft.get("plans", [draft])
    if not isinstance(plans, list):
        return ""
    comparisons = []
    for plan in plans:
        expression = plan.get("expression") if isinstance(plan, dict) else None
        if not isinstance(expression, dict):
            continue
        conditions = expression.get("conditions", [expression])
        if isinstance(conditions, list):
            comparisons.extend(part for part in conditions if isinstance(part, dict))
    if not comparisons:
        return ""
    for field, old, new, unit_question in sorted(changes):
        if unit_question:
            return unit_question
        values = [(part.get("left"), Decimal(str(part["right"]))) for part in comparisons
                  if part.get("right_type") == "value" and is_finite_number(part.get("right"))]
        bound = [value for left, value in values if left == field]
        if (old in bound or new not in (bound or [value for _, value in values])):
            return f"请核实当前需求中阈值 {new} 对应的指标及异常条件。"
    return ""


def _model_json_object(raw):
    """Protocol 2 consumes one complete object; cropping can discard a later rule or plan."""
    text = str(raw or '').strip()
    fenced = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    def unique_members(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON member')
            result[key] = value
        return result
    def invalid_number(_value):
        raise ValueError('Non-finite JSON number')
    try:
        value = json.loads(text, object_pairs_hook=unique_members, parse_constant=invalid_number)
    except (TypeError, ValueError) as exc:
        raise AppError('VALIDATION_ERROR') from exc
    if not isinstance(value, dict):
        raise AppError('VALIDATION_ERROR')
    return value


def reviewed_semantic_choices(previous, edited):
    """Only send submitted selections which were actual options on the owner's last result."""
    if not isinstance(edited, dict) or previous.get("table_name") != edited.get("table_name"):
        return []
    choices = []
    for question in previous.get("questions") or []:
        targets = question.get("targets") or [question["id"]]
        for option in question.get("options") or []:
            expected = option.get("selection", option.get("value"))
            if expected is None:
                continue
            for target in targets:
                value = edited
                for part in target.split("."):
                    if isinstance(value, list) and part.isdigit() and int(part) < len(value):
                        value = value[int(part)]
                    else:
                        value = value.get(part) if isinstance(value, dict) else None
                if value != expected:
                    break
            else:
                choices.append({"targets": targets, "selection": expected,
                                "binding": choice_identity(previous, targets, expected)})
    return choices


class _IncompleteDraft(ValueError):
    """A recoverable structural omission which the model can correct once."""

    def __init__(self, message, path=(), category="structure"):
        super().__init__(message)
        self.path = path
        self.category = category


def _same_declaration(left, right):
    # Python's equality treats True as 1, including inside nested expressions.
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _asks_for_condition(draft):
    if (not isinstance(draft, dict) or "rule_type" not in draft or draft["rule_type"] not in (None, "null")
            or draft.get("expression") != {} or "plans" in draft):
        return False
    intent = draft.get("semantic_intent")
    questions = intent.get("open_questions") if isinstance(intent, dict) else None
    return isinstance(questions, list) and bool(questions) and all(isinstance(q, str) and q.strip() for q in questions)


def _flatten_plan_envelopes(reply):
    """Canonicalize each selected draft before memory, field coverage and model proposal checks."""
    rule_fields = ("rule_type", "expression", "filters", "join", "project_driver", "semantic_intent", "null_policy", "equality_policy", "business_key",
                   "rule_name", "violation_message")
    proposal = reply.get("draft", reply)
    if isinstance(proposal, dict) and isinstance(proposal.get("plans"), list):
        # Older replies may attach an empty semantic summary to a group of independent drafts.
        summary = proposal.get("semantic_intent")
        if (isinstance(summary, dict) and summary.keys() <= {"metrics", "scopes", "open_questions"}
                and all(value in (None, []) for value in summary.values())):
            proposal.pop("semantic_intent")
    if isinstance(proposal, dict) and proposal is not reply:
        if reply.get("plans") not in (None, []):
            raise _IncompleteDraft("合并回复不可同时给出单独草稿和另一组方案")
        reply.pop("plans", None)
        if "plans" not in proposal:
            for key in ("business_key", "project_driver"):
                if key in reply and key not in proposal:
                    proposal[key] = deepcopy(reply[key])
        for key in ("target", "related_target", "report_category", "plan_mode"):
            if key in reply and key in proposal and not _same_declaration(reply[key], proposal[key]):
                raise _IncompleteDraft("选表封装与规则草稿的声明不一致")
        for key in rule_fields:
            if key in reply and (key not in proposal or not _same_declaration(reply[key], proposal[key])):
                raise _IncompleteDraft("合并回复只能给出一份一致的规则声明")
        if "plan_mode" in reply:
            proposal["plan_mode"] = reply["plan_mode"]
    plans = proposal.get("plans") if isinstance(proposal, dict) else None
    if not isinstance(plans, list):
        return reply
    if (any(key in proposal for key in rule_fields)
            or any(proposal.get(key) for key in ("uncertainties", "unsupported_requirements", "dictionary_questions"))):
        raise _IncompleteDraft("规则对象与多方案不可并列")
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict) or "draft" not in plan:
            continue
        inner = plan["draft"]
        if not isinstance(inner, dict) or "draft" in inner or "plans" in inner:
            raise _IncompleteDraft("每个 plans 项须对应一份独立规则草稿")
        merged = dict(inner)
        for key, value in plan.items():
            if key == "draft":
                continue
            if key == "ai_suggestions" and isinstance(value, list) and isinstance(merged.get(key), list):
                merged[key] = [*value, *merged[key]]
            elif key in merged and not _same_declaration(merged[key], value):
                raise _IncompleteDraft("同一方案内外层的声明必须一致")
            else:
                merged[key] = value
        plans[index] = merged
    return reply


def _required_list(value, key, *, limit=100):
    items = value.get(key)
    if not isinstance(items, list) or limit is not None and len(items) > limit:
        path = ("semantic_intent", key) if key in {"metrics", "scopes", "open_questions"} else ()
        raise _IncompleteDraft(f"{key} 必须是数组" if limit is None else f"{key} 必须是最多 {limit} 项的数组", path)
    return items


def _discard_cached_plan_suggestion_copies(proposal):
    # cache snapshots store the complete accepted list at the top of the draft.
    # Older snapshots can retain suggestions on individual plans from an earlier round.
    if isinstance(proposal.get("ai_suggestions"), list) and isinstance(proposal.get("plans"), list):
        for plan in proposal["plans"]:
            if isinstance(plan, dict):
                plan.pop("ai_suggestions", None)


def _validate_intent(draft, base_fields, related_fields):
    locator = draft.get("business_key")
    if locator not in (None, "") and (not isinstance(locator, str)
            or locator not in {field["field_name"] for field in base_fields}):
        raise _IncompleteDraft("结果定位字段必须来自当前主表的真实字段", category="unknown_field")
    for key in ("rule_name", "violation_message"):
        if draft.get(key) is not None and not isinstance(draft[key], str):
            raise _IncompleteDraft(f"{key} 必须是文本", (key,))
    intent = draft.get("semantic_intent")
    if not isinstance(intent, dict):
        raise _IncompleteDraft("缺少 semantic_intent 对象", ("semantic_intent",))
    questions = _required_list(intent, "open_questions")
    if any(not isinstance(q, str) or not q.strip() or len(q) > 2000 for q in questions):
        raise _IncompleteDraft("open_questions 只能包含独立的非空问题文本")
    metrics = _required_list(intent, "metrics", limit=None if has_arithmetic(draft.get("expression")) else 16)
    scopes = _required_list(intent, "scopes", limit=8)
    for row in [*metrics, *scopes]:
        if not isinstance(row, dict):
            raise _IncompleteDraft("每个指标或分类需提供对象")
        fields = _required_list(row, "fields", limit=20)
        if not fields or any(not isinstance(name, str) or not name for name in fields):
            raise _IncompleteDraft("fields 需列出有文档依据的物理列名")
    for row in metrics:
        if row.get("side") not in ("left", "right") or not isinstance(row.get("term"), str) or not row["term"].strip():
            raise _IncompleteDraft("每个指标需注明 side 和 term")
        names = row.get("rule_names", {})
        if (not isinstance(names, dict) or names.keys() - set(row["fields"])
                or any(not isinstance(name, str) or not name.strip() or len(name) > 200 for name in names.values())):
            raise _IncompleteDraft("rule_names 只能按候选字段给出不超过200字的完整规则名称")
    roles = _roles(base_fields, related_fields)
    for index, row in enumerate(scopes):
        scope_path = ("semantic_intent", "scopes", index, "memberships")
        members = row.get("memberships")
        if not isinstance(row.get("category"), str) or not row["category"].strip():
            raise _IncompleteDraft("每项范围需注明 category 与完整字典分组 memberships")
        if not isinstance(members, dict) or set(row["fields"]) != set(members):
            raise _IncompleteDraft("每个候选范围字段均需给出自己的完整字典分组", scope_path)
        for partition in members.values():
            if not isinstance(partition, dict) or not all(isinstance(partition.get(k), list) for k in ("include", "exclude")):
                raise _IncompleteDraft("每个候选字段的 memberships 必须同时给出 include 和 exclude", scope_path)
        # Physical field membership is a separate fact. Only patch partitions for documented fields.
        role = row.get("table", "base")
        if not isinstance(role, str) or role not in roles or not roles[role]:
            raise _IncompleteDraft("分类范围必须对应已选文档对象", category="unknown_field")
        missing = set(row["fields"]) - roles[role].keys()
        if missing:
            path = ("semantic_intent", "scopes", index, "field") if len(missing) == 1 else ()
            raise _IncompleteDraft("分类字段须更正为文档中真实的物理列，并保留原业务范围及字典分组",
                                   path, category="unknown_field")
        if draft.get("rule_type") is None:
            try:
                _scope_options(row, roles, {})
            except _Unbound as exc:
                raise _IncompleteDraft(str(exc), scope_path, category="dictionary_partition") from exc
        chosen = set(row["fields"])
        excluded = row.get("excluded_fields", {})
        if not isinstance(excluded, dict) or any(not isinstance(reason, str) or not reason.strip() for reason in excluded.values()):
            raise _IncompleteDraft("excluded_fields 的每项须说明据用户要求或文档排除此字段的理由")
        if chosen.intersection(excluded):
            raise _IncompleteDraft("同一字段不可同时作为候选和被排除的字段")
    if draft.get("rule_type") is None and (questions or draft.get("unsupported_requirements")):
        for row in metrics:
            known = roles["base"] if row["side"] == "left" else {**roles["base"], **roles["related"]}
            if not set(row["fields"]) <= known.keys():
                raise _IncompleteDraft("待确认的指标也必须是已选表中的真实列名", category="unknown_field")
        return
    if draft.get("rule_type") != "field_compare" or not isinstance(draft.get("expression"), dict):
        raise _IncompleteDraft("请给出完整的 field_compare 表达式，或说明具体缺少哪项条件")
    expression = draft["expression"]
    parts = expression.get("conditions", [expression])
    if not isinstance(parts, list) or not parts or any(not isinstance(part, dict) for part in parts):
        raise _IncompleteDraft("expression 的条件结构无效")
    known = {role: {f["field_name"] for f in fields}
             for role, fields in (("base", base_fields), ("related", related_fields))}
    for index, part in enumerate(parts):
        if is_arithmetic(part):
            try:
                used = arithmetic_fields(part)
            except AppError as exc:
                raise _IncompleteDraft("公式必须按括号和运算顺序提供完整的四则运算树。", category="field_binding") from exc
            numeric = {f["field_name"] for f in base_fields if type_family(f.get("data_type")) == "number"}
            if not set(used) <= numeric:
                raise _IncompleteDraft("公式各项必须来自同一行的真实数值列。", category="field_binding")
            for row in metrics:
                if row.get("condition_index", 0) != index:
                    continue
                try:
                    slot, key = _metric_slot(part, row)
                except _Unbound as exc:
                    raise _IncompleteDraft(str(exc), category="field_binding") from exc
                if slot.get(key) not in row["fields"] or not set(row["fields"]) <= numeric:
                    raise _IncompleteDraft("公式指标候选须对应同一个字段位置，且全部为主表数值列。", category="field_binding")
            continue
        sides = ["left"]
        if part.get("op") not in ("is_null", "is_not_null") and part.get("right_type", "field") == "field":
            sides.append("right")
        for side in sides:
            role = part.get("right_table", "base") if side == "right" else "base"
            if not isinstance(role, str) or role not in known or not any(row["side"] == side and row.get("condition_index", index) == index
                    and part.get(side) in row["fields"] and set(row["fields"]) <= known[role] for row in metrics):
                raise _IncompleteDraft(f"第 {index + 1} 项比较的 {side} 指标需要一致的真实表达式字段与 metrics 候选字段",
                                       category="field_binding")


def _fold_documented_scope(draft, base_fields, related_fields):
    """A single, fully verified scope may be repeated as one conjunct of the violation."""
    expr = draft.get("expression")
    intent = draft.get("semantic_intent")
    if (not isinstance(expr, dict) or set(expr) != {"logic", "conditions"} or expr["logic"] != "all"
            or draft.get("filters") or not isinstance(intent, dict)):
        return draft
    conditions, scopes, metrics = expr["conditions"], intent.get("scopes"), intent.get("metrics")
    if (not isinstance(conditions, list) or not 2 <= len(conditions) <= MAX_CONDITIONS
            or not all(isinstance(c, dict) for c in conditions) or not isinstance(metrics, list)
            or not isinstance(scopes, list) or len(scopes) != 1):
        return draft
    scope = scopes[0]
    if (not isinstance(scope, dict) or scope.keys() - {"fields", "category", "memberships", "table", "recommended"}
            or scope.get("table", "base") != "base" or not isinstance(scope.get("fields"), list)
            or len(scope["fields"]) != 1 or not isinstance(scope["fields"][0], str)):
        return draft
    name, = scope["fields"]
    positions = [i for i, c in enumerate(conditions) if c.get("left") == name]
    if len(positions) != 1:
        return draft
    pos, = positions
    cond = conditions[pos]
    if (set(cond) != {"left", "op", "right_type", "right"} or cond["right_type"] != "value"
            or cond["op"] not in ("eq", "in")):
        return draft
    try:
        selection = _scope_options(scope, _roles(base_fields, related_fields), {})[0]["selection"]
    except _Unbound:
        return draft
    values = cond["right"] if cond["op"] == "in" else [cond["right"]]
    included = selection["value"] if selection["op"] == "in" else [selection["value"]]
    if (not isinstance(values, list) or len(values) != len(included) or not all(isinstance(v, str) for v in values)
            or set(values) != set(included)):
        return draft
    remaining = [c for i, c in enumerate(conditions) if i != pos]
    rebound = []
    removed = 0
    for m in metrics:
        index = m.get("condition_index") if isinstance(m, dict) else None
        if type(index) is not int or not 0 <= index < len(conditions):
            return draft
        if index == pos:
            if (set(m) != {"condition_index", "side", "fields", "term"} or m["side"] != "left"
                    or m["fields"] != [name] or not isinstance(m["term"], str) or not m["term"].strip()):
                return draft
            removed += 1
        else:
            metric = dict(m)
            if len(remaining) == 1:
                del metric["condition_index"]
            else:
                metric["condition_index"] = index if index < pos else index - 1
            rebound.append(metric)
    if removed != 1:
        return draft
    normalized = {**draft, "expression": remaining[0] if len(remaining) == 1 else {"logic": "all", "conditions": remaining},
                  "semantic_intent": {**intent, "metrics": rebound}}
    try:
        _validate_intent(normalized, base_fields, related_fields)
    except _IncompleteDraft:
        return draft
    return normalized


def _formula_leaf_slots(tree, path=()):
    if "field" in tree:
        yield path, tree["field"]
    elif "op" in tree:
        for side in ("left", "right"):
            yield from _formula_leaf_slots(tree[side], (*path, side))


def _normalize_formula_metrics(draft, fields):
    """A formula leaf already names its field. Only genuine alternatives need a declaration."""
    expression = draft.get("expression")
    intent = draft.get("semantic_intent")
    if not isinstance(expression, dict) or not isinstance(intent, dict) or not isinstance(intent.get("metrics"), list):
        return
    parts = expression.get("conditions", [expression])
    if not isinstance(parts, list):
        return
    labels = {f["field_name"]: f.get("field_cn") or f["field_name"] for f in fields}
    metrics = intent["metrics"]
    for index, part in enumerate(parts):
        if not is_arithmetic(part):
            continue
        try:
            arithmetic_fields(part)
        except AppError:
            continue  # Full draft validation requests a corrected expression.
        for side in ("left", "right"):
            if part.get(side + "_type", "field") == "value":
                continue
            slots = (list(_formula_leaf_slots(part[side])) if part.get(side + "_type") == "formula"
                     else [((), part[side])])
            declarations = [m for m in metrics if isinstance(m, dict) and m.get("side") == side
                            and m.get("condition_index", 0) == index]
            covered = set()
            for item in declarations:
                names = item.get("fields")
                if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                    continue
                matches = [path for path, name in slots if name in names]
                declared = item.get("formula_path")
                if len(matches) == 1:
                    if matches[0]:
                        item["formula_path"] = list(matches[0])
                    else:
                        item.pop("formula_path", None)
                    covered.add(matches[0])
                elif isinstance(declared, list) and tuple(declared) in matches:
                    covered.add(tuple(declared))
                elif matches and all(name in [n for path, n in slots if path in matches] for name in names):
                    # Contributors at different positions are separate inputs, including repeated references.
                    metrics.remove(item)
            for path, name in slots:
                if path not in covered and name in labels:
                    metrics.append({"side": side, "term": labels[name], "fields": [name],
                                    **({"condition_index": index} if "conditions" in expression else {}),
                                    **({"formula_path": list(path)} if path else {})})


def _normalize_documented_operands(draft, base_fields, related_fields, request="", answers=()):
    """Normalize explicit operands and excluded blank placeholders on a private draft."""
    if isinstance(draft.get("expression"), dict):
        draft["expression"] = model_expression(draft["expression"])
    filters = draft.get("filters")
    for item in filters if isinstance(filters, list) else ():
        if not isinstance(item, dict) or item.get("op") not in ("regexp", "not_regexp"):
            continue
        pattern = item.get("value")
        if isinstance(pattern, str) and not re.search(r"[.\\^$*+?{}\[\]()]", pattern):
            words = pattern.split("|")
            if all(words):
                item.update(op="contains_any" if item["op"] == "regexp" else "not_contains_any", value=words)
    try:
        normalize_project_driver(draft.get("project_driver"))
    except AppError:
        pass
    else:
        join = draft.get("join")
        if isinstance(join, dict) and join.get("right_aggregate") is None and join.get("unmatched_policy") == "review":
            # Marked queries already report projects lacking details. The legacy
            # join policy describes the opposite, detail-to-project lookup.
            join["unmatched_policy"] = "exclude"
    known = {field["field_name"] for field in base_fields}
    related = {field["field_name"] for field in related_fields}
    expression = draft.get("expression")
    parts = expression.get("conditions", [expression]) if isinstance(expression, dict) else []
    if (isinstance(expression, dict) and set(expression) == {"logic", "conditions"}
            and expression["logic"] in ("any", "all") and isinstance(parts, list) and len(parts) == 1
            and isinstance(parts[0], dict)):
        part = parts[0]
        keys = {"left", "op"} if part.get("op") in ("is_null", "is_not_null") else {"left", "op", "right_type", "right", "right_table"}
        if set(part) <= keys:
            draft["expression"] = part
    for part in parts if isinstance(parts, list) else []:
        if not isinstance(part, dict):
            continue
        operand = part.get("left")
        if (isinstance(operand, dict) and set(operand) == {"table", "field"} and operand["table"] == "base"
                and isinstance(operand["field"], str) and operand["field"] in known):
            part["left"] = operand["field"]
        right = part.get("right")
        if (part.get("right_type", "field") == "field" and isinstance(right, dict) and set(right) == {"table", "field"}
                and right.get("table") in ("base", "related")
                and part.get("right_table", right["table"]) == right["table"]
                and isinstance(right.get("field"), str) and right["field"] in (known if right["table"] == "base" else related)):
            part["right"] = right["field"]
            if right["table"] == "related":
                part["right_table"] = "related"
            right = part["right"]
        if part.get("op") not in ("is_null", "is_not_null") and "right_type" not in part and is_finite_number(right):
            part["right_type"] = "value"
        if (part.get("right_type", "field") == "field" and "right_table" not in part
                and isinstance(right, str) and right not in known and right in related):
            part["right_table"] = "related"
    bind_named_dictionary_requirements(draft, base_fields, related_fields, request)
    apply_dictionary_answers(draft, base_fields, related_fields, answers)
    scope_issue = bind_conditional_text_scopes(draft, base_fields, request)
    if scope_issue:
        raise _IncompleteDraft(scope_issue, category="request_condition")
    text_issue = bind_text_predicates(draft, base_fields, request)
    if text_issue:
        raise _IncompleteDraft(text_issue, category="request_condition")
    intent = draft.get("semantic_intent")
    scopes = intent.get("scopes") if isinstance(intent, dict) else None
    if isinstance(scopes, list):
        _normalize_excluded_blanks(scopes, _roles(base_fields, related_fields))
        draft.update(_fold_documented_scope(draft, base_fields, related_fields))
    _normalize_formula_metrics(draft, base_fields)
    return draft


def _normalize_excluded_blanks(scopes, roles):
    for scope in scopes:
        if not isinstance(scope, dict) or not isinstance(scope.get("memberships"), dict):
            continue
        role = scope.get("table", "base")
        fields = roles.get(role, {}) if isinstance(role, str) else {}
        for name, partition in scope["memberships"].items():
            if name not in fields or not isinstance(partition, dict):
                continue
            included, excluded = partition.get("include"), partition.get("exclude")
            if (not isinstance(included, list) or not included or "" in included
                    or not isinstance(excluded, list) or excluded.count("") != 1):
                continue
            try:
                codes = _document_codes(fields[name])
            except _Unbound:
                continue
            # The predicate uses only positive memberships. An unregistered blank explicitly
            # excluded by the model has no effect. The full remaining partition is still validated.
            if "" not in codes:
                partition["exclude"] = [value for value in excluded if value != ""]


class SemanticAnalysis:
    def __init__(self, service, user, inputs, request_text, progress, cancel_event):
        self.service = service
        self.user = user
        self.inputs = inputs
        adoption_scope = inputs.get("period_scope") or {}
        variants = adoption_scope.get("variants") or []
        self.inherited_checks = adoption_scope.get("checks") or (
            variants if variants and all(v.get("check") for v in variants) else [])
        self.request = request_text
        self.progress = progress
        self.cancel = cancel_event
        self.reusable_response = None
        self.tables = inputs["tables"]
        self.fields = inputs["fields_by_table"]
        self.index = None
        self.competing_evidence = []
        self.interpretation_checks = []
        self.confirmed_checks = self.confirmed_evidence(inputs.get("clarification_answers") or [])
        self.interpretation_overflow = []
        self.request_conditions = []
        self.document_review = None
        self.round_number = getattr(cancel_event, 'model_round', 0)
        self.output_tokens_used = getattr(cancel_event, "output_tokens_used", 0)
        self.budget_units = 1
        self.syntax_retries = 0
        self.model_suggestions = []
        self.initial_proposal = None
        self.coverage_reviewed = False
        self.owner_choices = []
        thread_name = current_thread().name
        self.analysis_id = (getattr(cancel_event, 'analysis_id', None)
                            or (thread_name[12:] if thread_name.startswith("dv-analysis-") else uuid4().hex[:12]))
        self.categories = inputs["categories"]
        self.prompts = inputs["prompts"]
        self.prefix = inputs["knowledge_prefix"] + "通用校验口径：\n" + self.prompts["business_scope"] + "\n"
        if variants:
            verified = {key: adoption_scope[key] for key in ("suggestion", "variants", "applicability_filters") if key in adoption_scope}
            self.prefix += ("\n本次采纳建议与用户已选方案的已核实口径：" + _json(verified)
                            + "。保留各已选范围、关联与日期，采用建议声明的指标及检查目标。"
                            "已选范围和已登记适用范围由系统应用；filters和scopes只声明上述已核实范围之外的新增限制。"
                            "已核实的条件无需重复询问。期间方案提供check时沿用该条件；汇总比较按建议自身的运算和容差。\n")
        if inputs.get("clarification_answers"):
            self.prefix += ("\n当前用户对上一轮业务问题的回答（独立上下文数据，原始需求保持不变）："
                            + _json(inputs["clarification_answers"])
                            + "。问题用于说明回答指向，不能把问题中举出的备选事项自动当成新需求；"
                            "结合回答保留已选择口径，不重复询问同一事项。\n")
        self.context = {"analysis_protocol": 2, **{k: inputs["context"][k] for k in ("source_id", "dialect", "doc_version", "doc_sha256")}}
        if inputs["knowledge_context"]:
            self.context["knowledge_context"] = inputs["knowledge_context"]

    def call(self, prompt, stage, *, public_stage_override=None):
        public_stage = public_stage_override or (stage if stage == "select_table" else "generate_rule")
        remaining = max(0, SEMANTIC_TOTAL_OUTPUT_TOKENS - self.output_tokens_used)
        if not remaining:
            raise failure("ANALYSIS_OUTPUT_LIMIT", public_stage, analysis_id=self.analysis_id, round_number=self.round_number)
        supplement = stage == "supplement_suggestions"
        allocated = min(SEMANTIC_CALL_OPTIONS["max_tokens"] * (1 if supplement else self.budget_units), remaining)
        options = {**SEMANTIC_CALL_OPTIONS, "max_tokens": allocated,
                   "reasoning_effort": "low" if self.inputs.get("reasoning_enabled") else "none"}
        bounded_prompt = prompt
        if self.model_suggestions:
            previous = model_snapshot({"ai_suggestions": self.model_suggestions})["selection"]["ai_suggestions"]
            bounded_prompt += ("\n上一轮补充建议：" + _json(previous)
                               + "\n本轮若给 ai_suggestions，请返回按当前文档和已确认业务口径核实后的完整建议清单。"
                               "同一建议改写只留一项，不同范围、公式或容差的独立建议都保留。"
                               "preconditions 只列仍待确认的事项，已确认的单位、计算方式、容差等可写在 reason。"
                               "不再有建议时给 []；省略 ai_suggestions 则沿用上一轮。")
        bounded_prompt += semantic_budget_instruction(allocated, remaining, stage)
        if not supplement:
            bounded_prompt += ("\n本次需求原文（只生成本句委托的主校验，不照搬示例）：" + _json(self.request)
                               + "。只有对象、分类或指标名、未说明检查要求时只问检查什么，不自行添加NULL或阈值检查；"
                               "文档可以列出的字段、分类或口径应给结构化选项，不先默认一个再让用户手写是否还要另一个；"
                               "独立建议放ai_suggestions，不充当用户尚未提出的主校验。")
        self.round_number += 1
        model_id = self.inputs["context"]["model_id"]
        def record_usage(tokens):
            # Missing/failed replies may still consume their entire upstream allocation.
            self.output_tokens_used += tokens if type(tokens) is int and tokens >= 0 else allocated
            if isinstance(self.cancel, AnalysisControl):
                self.cancel.output_tokens_used = self.output_tokens_used
        raw = semantic_completion(self.service.model, model_id, bounded_prompt, stage=stage, public_stage=public_stage,
                                  round_number=self.round_number, analysis_id=self.analysis_id,
                                  options=options, cancel_event=self.cancel, usage_observer=record_usage)
        if self.output_tokens_used > SEMANTIC_TOTAL_OUTPUT_TOKENS:
            raise failure("ANALYSIS_OUTPUT_LIMIT", public_stage, analysis_id=self.analysis_id, round_number=self.round_number)
        try:
            parsed = _model_json_object(raw)
            if supplement:
                if not isinstance(parsed.get("ai_suggestions"), list):
                    raise _IncompleteDraft("补充建议必须是 ai_suggestions 数组")
                for item in parsed["ai_suggestions"]:
                    if (not isinstance(item, dict) or item.get("category") not in CATEGORIES
                            or item.get("kind") not in KINDS):
                        raise _IncompleteDraft("补充建议类型与输出协议不一致")
                    for key in ("operations", "preconditions", "limitations"):
                        if key in item and (not isinstance(item[key], list)
                                or any(not isinstance(value, str) for value in item[key])):
                            raise _IncompleteDraft("补充建议的操作、前提及限制必须使用字符串数组")
                return {"ai_suggestions": parsed["ai_suggestions"][:MAX_SUGGESTIONS],
                        "no_suggestion_reason": parsed.get("no_suggestion_reason")}
            parsed = _flatten_plan_envelopes(parsed)
            if stage in ("generate_rule", "repair_rule", "review_interpretations") and isinstance(parsed.get("draft"), dict):
                canonical = deepcopy(parsed["draft"])
                for key, value in parsed.items():
                    if key == "draft":
                        continue
                    if key == "ai_suggestions" and isinstance(value, list) and isinstance(canonical.get(key), list):
                        canonical[key] = [*value, *canonical[key]]
                    elif key in canonical and not _same_declaration(canonical[key], value):
                        raise _IncompleteDraft("选表封装与规则草稿的声明不一致")
                    else:
                        canonical[key] = deepcopy(value)
                parsed = canonical
            blocks = [parsed]
            if isinstance(parsed.get("draft"), dict):
                blocks.append(parsed["draft"])
            for block in list(blocks):
                plans = block.get("plans")
                if isinstance(plans, list):
                    blocks.extend(item for item in plans if isinstance(item, dict))
            period = self.inputs.get("period_scope") or {}
            for block in blocks:
                if self.inputs.get("include_suggestions") is False:
                    block.pop("ai_suggestions", None)
                intent = block.get("semantic_intent")
                if self.inherited_checks and block.get("rule_type") == "field_compare" and isinstance(intent, dict):
                    # Review the user's chosen predicate from the first draft. Materialization
                    # below expands every distinct selected predicate and scope.
                    target_field = period["fields"][0]
                    apply_period_check(block, self.inherited_checks[0]["check"], target_field, target_field)
                if isinstance(intent, dict) and isinstance(intent.get("filters"), list):
                    if "filters" in block and not _same_declaration(block["filters"], intent["filters"]):
                        raise _IncompleteDraft("规则与语义说明中的筛选条件不一致")
                    block["filters"] = intent.pop("filters")
                if _asks_for_condition(block):
                    block["rule_type"] = None
            declared = [block["ai_suggestions"] for block in blocks if isinstance(block.get("ai_suggestions"), list)]
            if declared:
                self.model_suggestions = [deepcopy(item) for items in declared for item in items]
            return parsed
        except _IncompleteDraft as exc:
            raise failure("MODEL_RESPONSE_INVALID", public_stage, category="plan_envelope",
                          analysis_id=self.analysis_id, round_number=self.round_number) from exc
        except AppError as exc:
            error = failure("MODEL_RESPONSE_INVALID", public_stage, category="invalid_json_object",
                            analysis_id=self.analysis_id, round_number=self.round_number)
            cause = exc.__cause__
            syntax = isinstance(cause, json.JSONDecodeError)
            LOGGER.warning('Semantic JSON invalid reference=%s analysis=%s round=%d stage=%s chars=%d reason=%s line=%d column=%d',
                           error.reference, self.analysis_id, self.round_number, stage, len(raw),
                           'syntax' if syntax else 'object_required', cause.lineno if syntax else 0, cause.colno if syntax else 0)
            if self.syntax_retries == 0 and stage in ('select_table', 'select_and_generate'):
                self.syntax_retries += 1
                self.service._emit_progress(self.progress, 'generation', 'running', '模型回复格式不完整，正在重新请求（最多一次）')
                # Re-ask from the same authorized snapshot. Never guess missing JSON or forward broken output as instructions.
                return self.call(prompt + '\n请只返回一个完整、可解析的 JSON 对象，不要输出未闭合的片段。', 'repair_json',
                                 public_stage_override=public_stage)
            raise error from exc

    def resolve(self, target, category):
        name = target.get("table") if isinstance(target, dict) else None
        declared = target.get("report_category") if isinstance(target, dict) else None
        if declared not in (None, ""):
            if category not in (None, "", declared):
                raise _IncompleteDraft("目标表的报送分类声明不一致")
            category = declared
        if category is not None and not isinstance(category, str):
            raise _IncompleteDraft("report_category 必须为文档分类编码")
        matches = [t for t in self.tables if t["table_name"] == name]
        if len(matches) > 1:
            matches = self.service._category_tables(matches, {category} if isinstance(category, str) else set(), self.categories)
        if (len(matches) != 1 or not self.fields.get(int(matches[0]["id"]))
                or category and self.service._doc_category_scope(matches[0], self.categories)
                and not self.service._category_tables(matches, {category}, self.categories)):
            raise _IncompleteDraft("目标表需唯一对应所选来源与报送分类的活动文档，且具有字段说明")
        return matches[0]

    def evidence(self, table, *, full=True, names=None):
        item = self.index.describe(table, full=full, names=names)
        category = document_category(self.service._doc_category_scope(table, self.categories), self.categories)
        if category:
            item["report_category"] = category["code"]
        return item

    def selection_prompt(self, *, views=None, expanded_ids=()):
        if views is None:
            views = [self.evidence(t, full=t["id"] in expanded_ids) for t in self.tables]
        docs = _json(compact_directory(views))
        source = self.inputs["source"]["name"]
        if self.prompts["select_table"] == DEFAULT_PROMPTS["select_table"]:
            template = "来源：{source_name}。分类：{categories}。需求：{request_text}。文档：{tables}"
        else:
            template = self.prompts["select_table"]
        return self.prefix + self.service._render(template, {
            "request_text": self.request, "source_name": source, "categories": _json(self.categories), "tables": docs,
        }) + SEMANTIC_SELECTION_CONTRACT

    def bind_missing_target(self, selection):
        """Only infer a missing table when *all* cited columns jointly identify one authorized document."""
        proposal = selection.get("draft", selection)
        if (not isinstance(proposal, dict) or proposal.get("rule_type") != "field_compare"
                or not isinstance(proposal.get("expression"), dict) or not isinstance(proposal.get("semantic_intent"), dict)
                or any(selection.get(k) or proposal.get(k) for k in ("related_target", "candidate_targets", "plans", "join"))):
            return selection
        referenced = referenced_fields(proposal)
        names = referenced["base"]
        if not names or referenced["related"]:
            return selection
        matches = [t for t in self.tables
                   if names <= {f["field_name"] for f in self.fields.get(t["id"], [])}]
        if len(matches) == 1:
            t = matches[0]
            category = document_category(self.service._doc_category_scope(t, self.categories), self.categories)
            bound = {**selection, "target": {"table": t["table_name"]}, "draft": proposal}
            category_code = (category or {}).get("code", "")
            if not bound.get("report_category"):
                bound["report_category"] = category_code
            elif category_code and bound["report_category"] != category_code:
                bound["expand_evidence"] = True
            return bound
        if not matches:
            return selection
        views = [self.evidence(t, full=False, names=names) for t in matches]
        prompt = (self.selection_prompt(views=views) + "\n上一轮已给规则，物理列可来自多表。仅核实以下草稿归属，"
                  "在所列文档中选择 target。业务依据支持同一草稿时给 draft_matches:true；"
                  "仍有多种合理归属请列 candidate_targets，禁止因同名任意推荐。草稿数据：" + _json(proposal))
        checked = self.call(prompt, "select_table")
        additional = checked.get("candidate_targets", [])
        if not isinstance(additional, list) or len(additional) > 2:
            raise failure("MODEL_RESPONSE_INVALID", "select_table")
        objects = ([checked] if checked.get("target") else []) + additional
        if checked.get("related_target") and not checked.get("target"):
            raise failure("MODEL_RESPONSE_INVALID", "select_table")
        if objects:
            try:
                chosen = self.documents(objects)
            except (_IncompleteDraft, TypeError) as exc:
                raise failure("MODEL_RESPONSE_INVALID", "select_table") from exc
            verified_ids = {t["id"] for t in matches}
            if any(t["id"] not in verified_ids for t in chosen):
                raise failure("MODEL_RESPONSE_INVALID", "select_table")
            if checked.get("draft_matches") is True and checked.get("target") and not additional and len(chosen) == 1:
                checked = {**checked, "draft": proposal}
                self.index.details[chosen[0]["id"]].update(names)
        return checked

    def bind_missing_related_target(self, selection):
        """Complete a single draft's explicit join declaration, never infer a relationship."""
        proposal = selection.get("draft", selection)
        if (not isinstance(proposal, dict) or proposal.get("rule_type") != "field_compare"
                or not selection.get("target") or selection.get("related_target") not in (None, {})
                or selection.get("candidate_targets") or proposal.get("candidate_targets")
                or "plans" in selection or "plans" in proposal):
            return selection
        if proposal.get("target", selection["target"]) != selection["target"]:
            return selection
        join = proposal.get("join")
        if not isinstance(join, dict) or not isinstance(join.get("table_name"), str):
            return selection
        related = {"table": join["table_name"]}
        if proposal.get("related_target") not in (None, {}, related):
            return selection
        declarations = [selection.get("report_category"), proposal.get("report_category")]
        for item in (selection.get("target"), proposal.get("target"), proposal.get("related_target")):
            if isinstance(item, dict):
                declarations.append(item.get("report_category"))
        declarations = [value for value in declarations if value not in (None, "")]
        if any(not isinstance(value, str) for value in declarations) or len(set(declarations)) > 1:
            return selection
        category = declarations[0] if declarations else None
        try:
            base = self.resolve(selection["target"], category)
            other = self.resolve(related, category)
        except _IncompleteDraft:
            return selection
        if base["id"] == other["id"]:
            return selection
        if category and any(self.service._doc_category_scope(t, self.categories) is not None
                            and not self.service._category_tables([t], {category}, self.categories) for t in (base, other)):
            return selection
        bound = {**selection, "related_target": related}
        if category:
            bound["report_category"] = category
        return bound

    def ready_for_combined(self, selection, proposal, docs):
        if selection.get("expand_evidence") or not isinstance(proposal, dict):
            return False
        if proposal is self.document_review:
            return True
        default = selection.get("target")
        if not isinstance(default, dict) or not docs:
            return False
        plans = proposal.get("plans", [proposal])
        if not isinstance(plans, list) or not plans:
            return False
        covered = set()
        for plan in plans:
            if not isinstance(plan, dict):
                return False
            target = plan.get("target", default)
            related = plan.get("related_target", selection.get("related_target") if target == default else None)
            try:
                category = plan.get("report_category", selection.get("report_category"))
                base = self.resolve(target, category)
                other = self.resolve(related, category) if related else None
            except _IncompleteDraft:
                return False
            if base not in docs or other and other not in docs:
                return False
            covered.add(base["id"])
            if other:
                covered.add(other["id"])
            plan = _normalize_documented_operands(deepcopy(plan), self.fields[base["id"]],
                                                 self.fields[other["id"]] if other else [], self.request,
                                                 self.inputs.get("clarification_answers") or [])
            names = referenced_fields(plan)
            if not names["base"] or not names["base"] <= self.index.details[base["id"]]:
                return False
            if names["related"] and not related:
                return False
            if other and (not names["related"] or not names["related"] <= self.index.details[other["id"]]):
                return False
            if plan.get("unsupported_requirements") and any(not self.index.fully_expanded(t) for t in docs):
                return False
        return covered == {table["id"] for table in docs}

    def bind_planned_targets(self, selection):
        proposal = selection.get("draft", selection)
        plans = proposal.get("plans") if isinstance(proposal, dict) else None
        if not isinstance(plans, list) or not 1 <= len(plans) <= SEMANTIC_MAX_PLANS:
            return selection
        bound = deepcopy(selection)
        extra = bound.get("candidate_targets", [])
        if not isinstance(extra, list) or len(extra) > 2:
            return selection
        promote = not bound.get("target")
        try:
            if promote:
                if not all(isinstance(p, dict) and isinstance(p.get("target"), dict) for p in plans):
                    return selection
                # Each plan must bind independently before the first becomes the display default.
                for plan in plans:
                    category = plan.get("report_category", bound.get("report_category"))
                    self.resolve(plan["target"], category)
                    if plan.get("related_target"):
                        self.resolve(plan["related_target"], category)
                first = plans[0]
                bound["target"] = dict(first["target"])
                if first.get("report_category"):
                    bound["target"]["report_category"] = first["report_category"]
                if first.get("related_target"):
                    if bound.get("related_target") not in (None, first["related_target"]):
                        raise _IncompleteDraft("多方案的首项与外层关联表声明不一致")
                    bound["related_target"] = dict(first["related_target"])
                    if first.get("report_category"):
                        bound["related_target"]["report_category"] = first["report_category"]
                    for plan in bound.get("draft", bound)["plans"]:
                        plan.setdefault("related_target", None)
            known = {table["id"] for table in self.documents([bound, *extra])}
            for plan in plans:
                if not isinstance(plan, dict) or not plan.get("target"):
                    continue
                category = plan.get("report_category", bound.get("report_category"))
                item = {"target": plan["target"], **({"report_category": category} if category else {})}
                if plan.get("related_target"):
                    item["related_target"] = plan["related_target"]
                ids = {table["id"] for table in self.documents([item])}
                if ids <= known:
                    continue
                if len(extra) >= 2:
                    return selection
                extra.append(item)
                known.update(ids)
        except _IncompleteDraft as exc:
            if promote:
                raise failure("MODEL_RESPONSE_INVALID", "select_table", category="target_document_binding",
                              analysis_id=self.analysis_id, round_number=self.round_number) from exc
            return selection
        if extra:
            bound["candidate_targets"] = extra
        return bound

    def documented_peer_choice(self, selection, proposal, owner_choices=()):
        """Use the same condition indices during discovery, review and final grounding."""
        plans = proposal.get("plans", [proposal])
        if not isinstance(plans, list):
            return proposal
        normalized = []
        changed = False
        for plan in plans:
            item = drop_unused_project_lookup(self, selection, plan)
            item = prefer_document_origin(self, selection, item)
            changed |= item is not plan
            plan = item
            expr = plan.get("expression") if isinstance(plan, dict) else None
            if (len(plans) == 1 and isinstance(expr, dict) and "conditions" not in expr
                    and plan.get("rule_type") == "field_compare" and "公式" in self.request and isinstance(plan.get("semantic_intent"), dict)):
                base = self.resolve(plan.get("target", selection.get("target")), plan.get("report_category", selection.get("report_category")))
                literal = documented_equation(self.request, self.fields[base["id"]])
                if literal and literal != expr:
                    expr = literal
                    item = {**plan, "expression": expr, "semantic_intent": {**plan["semantic_intent"], "metrics": []}}
            if isinstance(expr, dict) and expr.get("logic") == "all" and "conditions" in expr:
                category = plan.get("report_category", selection.get("report_category"))
                base = self.resolve(plan.get("target", selection.get("target")), category)
                target = plan.get("related_target", selection.get("related_target"))
                related = self.resolve(target, category) if target else None
                item = _fold_documented_scope(plan, self.fields[base["id"]], self.fields[related["id"]] if related else [])
            if has_arithmetic(expr):
                base = self.resolve(plan.get("target", selection.get("target")), plan.get("report_category", selection.get("report_category")))
                item = deepcopy(item)
                _normalize_formula_metrics(item, self.fields[base["id"]])
                # The document can name multiple numeric fields for one literal operand.
                intent = item.get("semantic_intent")
                metrics = intent.get("metrics") if isinstance(intent, dict) else None
                parts = expr.get("conditions", [expr])
                for metric in metrics if isinstance(metrics, list) else []:
                    if not isinstance(metric, dict) or "formula_path" not in metric:
                        continue
                    term = metric.get("term")
                    names = metric.get("fields")
                    if not isinstance(term, str) or not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                        continue
                    chosen = next((c["selection"] for c in owner_choices if isinstance(c, dict)
                                   and c.get("selection") in names and self.matches_owner_choice(c, "metrics",
                                   {**metric, "fields": [c["selection"]]}, base, "base", base, 0)), None)
                    if chosen:
                        index = metric.get("condition_index", 0)
                        if type(index) is int and isinstance(parts, list) and 0 <= index < len(parts):
                            try:
                                current, key = _metric_slot(item["expression"].get("conditions", [item["expression"]])[index], metric)
                            except _Unbound:
                                continue
                            current[key] = chosen
                            metric["fields"] = [chosen]
                            metric.pop("recommended", None)
                        continue
                    if term not in self.request:
                        continue
                    peers = [f["field_name"] for f in self.fields[base["id"]] if type_family(f.get("data_type")) == "number"
                             and term.lower() in (str(f.get("field_cn") or "").lower(), *_business_aliases(f))]
                    if any(n in peers for n in names):
                        metric["fields"] = list(dict.fromkeys([*names, *peers]))
            normalized.append(item)
            changed |= item is not plan
        if changed:
            proposal = {**proposal, "plans": normalized} if "plans" in proposal else normalized[0]
        proposal = qualified_peer_choice(self, selection, proposal, owner_choices=owner_choices)
        return defer_period_metric_choices(self, selection, proposal, owner_choices)

    def expand_interpretation_evidence(self, selection, owner_choices=()):
        """A plausible first answer cannot hide equally specific, unreviewed document evidence."""
        if self.inherited_checks:
            # The owner has already selected the document measure and the exact condition.
            return selection, False
        proposal = selection.get("draft", selection if "rule_type" in selection or "plans" in selection else {})
        if _asks_for_condition(proposal):
            return selection, False
        if isinstance(proposal, dict):
            try:
                normalized = self.documented_peer_choice(selection, proposal, owner_choices)
            except _IncompleteDraft:
                normalized = proposal
            if normalized is not proposal:
                proposal = normalized
                selection = {**selection, "draft": proposal}
                if "plans" not in proposal and proposal.get("target") and proposal["target"] != selection.get("target"):
                    selection = {**selection, "target": proposal["target"],
                                 "related_target": proposal.get("related_target")}
        plans = proposal.get("plans", [proposal]) if isinstance(proposal, dict) else []
        if not isinstance(plans, list):
            return selection, False
        deferred = deferred_period_fields(self, selection, proposal, owner_choices)
        declarations, entries = set(), []
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            try:
                category = plan.get("report_category", selection.get("report_category"))
                base = self.resolve(plan.get("target", selection.get("target")), category)
                target = plan.get("related_target", selection.get("related_target"))
                related = self.resolve(target, category) if target else None
            except _IncompleteDraft:
                continue
            roles = {"base": base, "related": related}
            intent = plan.get("semantic_intent") or {}
            if not isinstance(intent, dict):
                continue
            expression = plan.get("expression") or {}
            conditions = expression.get("conditions", [expression]) if isinstance(expression, dict) else []
            for key in ("metrics", "scopes"):
                rows = intent.get(key) or []
                if not isinstance(rows, list):
                    continue
                for row_index, item in enumerate(rows):
                    if not isinstance(item, dict) or not isinstance(item.get("fields"), list):
                        continue
                    role = item.get("table", "base") if key == "scopes" else "base"
                    if key == "metrics" and item.get("side") == "right":
                        index = item.get("condition_index", 0)
                        if type(index) is not int or not isinstance(conditions, list) or not 0 <= index < len(conditions):
                            continue
                        condition = conditions[index]
                        if (not isinstance(condition, dict) or condition.get('right_type') == 'value'
                                or condition.get('op') in ('is_null', 'is_not_null')):
                            continue
                        role = conditions[index].get("right_table", "base") if isinstance(conditions[index], dict) else "base"
                    owner = roles.get(role) if isinstance(role, str) else None
                    if owner:
                        declarations.update((key, owner["id"], role, item.get("side", ""), item.get("condition_index", 0), name)
                                            for name in item["fields"] if isinstance(name, str))
                        index = item.get("condition_index", 0)
                        formula_metric = (key == "metrics" and isinstance(conditions, list) and type(index) is int
                                          and 0 <= index < len(conditions) and is_arithmetic(conditions[index]))
                        entries.append((key, item, owner, role, base, row_index, formula_metric))
            join = plan.get("join")
            if (len(plans) == 1 and related and related["id"] != base["id"] and isinstance(join, dict)
                    and join.get("table_name") == related["table_name"] and isinstance(conditions, list)):
                # The opposite operand of this very comparison already accounts for that document field.
                # Other fields in its table, and choices in other checks, still require review.
                for index, condition in enumerate(conditions):
                    if (not isinstance(condition, dict) or condition.get("right_type") != "field"
                            or condition.get("right_table") != "related"
                            or not isinstance(condition.get("left"), str) or not isinstance(condition.get("right"), str)):
                        continue
                    left, right = condition["left"], condition["right"]
                    if (("metrics", base["id"], "base", "left", index, left) in declarations
                            and ("metrics", related["id"], "related", "right", index, right) in declarations
                            and any(f["field_name"] == left for f in self.fields[base["id"]])
                            and any(f["field_name"] == right for f in self.fields[related["id"]])):
                        declarations.add(("metrics", related["id"], "base", "left", index, right))
        pending = []
        for key, item, owner, role, base, row_index, formula_metric in entries:
            if formula_metric:  # Each leaf already has its own document options.
                continue
            reviewed = any(self.matches_owner_choice(choice, key, item, owner, role, base, row_index)
                           for choice in owner_choices if isinstance(choice, dict))
            if reviewed:
                continue
            primary_metric = key == "metrics" and item.get("side") == "left" and role == "base"
            if len(plans) > 1 and primary_metric:
                missing_grain = missing_registered_grain(self, owner, item, declarations, role)
                if missing_grain:
                    raise ScopeEvidenceRequired(f"多个检查项中仍有独立指标口径 {missing_grain}，请明确各维度和检查项的组合。")
            candidates = self.index.competing_fields(owner, item["fields"], item.get("term" if key == "metrics" else "category", ""),
                self.tables, category=key == "scopes",
                across_tables=primary_metric and len(item["fields"]) == 1 and len(plans) == 1)
            if key == "metrics" and deferred:
                candidates = [{**candidate, "fields": [name for name in candidate["fields"]
                               if (candidate["table_id"], name) not in deferred]} for candidate in candidates]
                candidates = [candidate for candidate in candidates if candidate["fields"]]
            missing = [candidate for candidate in candidates
                       if any((key, candidate["table_id"], role, item.get("side", ""), item.get("condition_index", 0), name)
                              not in declarations for name in candidate["fields"])]
            if missing:
                pending.append({"kind": key, "term": candidates[0]["request_term"],
                                "first_interpretation": item.get("term" if key == "metrics" else "category"),
                                "role": role, "side": item.get("side", ""), "condition_index": item.get("condition_index", 0),
                                "candidates": candidates})
        if not pending:
            self.remember_declared_interpretations(entries)
            return selection, False
        if not owner_choices:
            try:
                reviewed = document_choices(self, selection, pending, _validate_intent)
            except (_Unbound, _IncompleteDraft):
                reviewed = None
            if reviewed is not None:
                self.remember_declared_interpretations(entries)
                bound = self.bind_planned_targets({**selection, "draft": reviewed})
                self.document_review = bound["draft"]
                return bound, False
        bound = deepcopy(selection)
        extra = list(bound.get("candidate_targets") or [])
        known = {table["id"] for table in self.documents(([bound] if bound.get("target") else []) + extra)}
        for group in pending:
            for candidate in group["candidates"]:
                if candidate["table_id"] in known or len(extra) >= 2:
                    continue
                table = next(table for table in self.tables if table["id"] == candidate["table_id"])
                category = document_category(self.service._doc_category_scope(table, self.categories), self.categories)
                extra.append({"target": {"table": table["table_name"]},
                              **({"report_category": category["code"]} if category else {})})
                known.add(table["id"])
        if extra:
            bound["candidate_targets"] = extra
        bound["expand_evidence"] = True
        self.competing_evidence = []
        self.interpretation_checks = []
        for group in pending:
            self.interpretation_overflow.extend(candidate for candidate in group['candidates'] if candidate['table_id'] not in known)
            actual = [{**candidate, "fields": [name for name in candidate["fields"]
                       if (group["kind"], candidate["table_id"], group["role"], group["side"], group["condition_index"], name)
                       not in declarations]} for candidate in group["candidates"] if candidate["table_id"] in known]
            actual = [candidate for candidate in actual if candidate["fields"]]
            if actual:
                self.competing_evidence.append({**group, "candidates": actual})
                for candidate in actual:
                    for name in candidate["fields"]:
                        check = {**{key: group[key] for key in ("kind", "term", "role", "side", "condition_index")},
                                 "id": f"I{len(self.interpretation_checks) + 1}", "table": candidate["table"],
                                 "table_id": candidate["table_id"], "field": name,
                                 "label": next(field.get("field_cn") or name for field in self.fields[candidate["table_id"]]
                                               if field["field_name"] == name), "dimension": candidate["dimension"]}
                        if not any(all(old[key] == check[key] for key in ("kind", "role", "side", "condition_index", "table_id", "field"))
                                   for old in self.interpretation_checks):
                            self.interpretation_checks.append(check)
        self.remember_declared_interpretations(entries)
        return bound, True

    def matches_owner_choice(self, choice, key, item, owner, role, base, row_index):
        binding = choice.get("binding") or {}
        if (binding.get("kind") != key or binding.get("role") != role or binding.get("base") != base["table_name"]
                or binding.get("owner") != owner["table_name"]
                or any(binding.get(k) != self.context.get(k) for k in ("source_id", "doc_version", "doc_sha256"))
                or binding.get("term") != item.get("category" if key == "scopes" else "term")):
            return False
        try:
            if self.resolve({"table": base["table_name"]}, binding.get("report_category"))["id"] != base["id"]:
                return False
        except _IncompleteDraft:
            return False
        value = choice.get("selection")
        if key == "metrics":
            return (item["fields"] == [value] and binding.get("side") == item.get("side")
                    and binding.get("formula_path") == item.get("formula_path")
                    and item.get("condition_index", 0) in binding.get("indices", []))
        if (not isinstance(value, dict) or item["fields"] != [value.get("field")] or binding.get("index") != row_index):
            return False
        try:
            options = _scope_options(item, {role: {f["field_name"]: f for f in self.fields[owner["id"]]}}, {})
        except _Unbound:
            return False
        return any(option["selection"] == value for option in options)

    def remember_declared_interpretations(self, entries):
        # Expansion must not let the next reply replace an already discovered interpretation.
        # Preserve other original metric/scope groups as well, even if only one group needed expansion.
        for key, item, owner, role, _base, _index, _formula_metric in entries:
            for name in item["fields"]:
                field = next((field for field in self.fields[owner["id"]] if field["field_name"] == name), None)
                if field is None:
                    continue
                check = {"kind": key, "term": item.get("term" if key == "metrics" else "category", ""),
                         "role": role, "side": item.get("side", ""), "condition_index": item.get("condition_index", 0),
                         "id": f"I{len(self.interpretation_checks) + 1}", "table": owner["table_name"],
                         "table_id": owner["id"], "field": name, "label": field.get("field_cn") or name,
                         "dimension": owner.get("dimension") or "", "first_seen": True}
                old = next((old for old in self.interpretation_checks
                            if old.get("formula_path") == item.get("formula_path") and
                            all(old[k] == check[k] for k in ("kind", "role", "side", "condition_index", "table_id", "field"))), None)
                if old is None:
                    if "formula_path" in item:
                        check["formula_path"] = item["formula_path"]
                    self.interpretation_checks.append(check)
                else:
                    old['first_seen'] = True
                if key == "scopes":
                    members = item.get("memberships")
                    partition = members.get(name) if isinstance(members, dict) else None
                    if isinstance(partition, dict) and isinstance(partition.get("include"), list):
                        (old if old is not None else check).update(term=item["category"], partition=partition)

    def missing_interpretations(self, raw, targets, *, apply_choices=False):
        covered = set()
        deferred = deferred_period_fields(self, targets[0], raw, self.owner_choices)
        plans = raw.get("plans", [raw]) if isinstance(raw, dict) else []
        for plan in plans if isinstance(plans, list) else []:
            if not isinstance(plan, dict):
                continue
            default = targets[0]
            category = plan.get("report_category", default.get("report_category"))
            try:
                base = self.resolve(plan.get("target", default.get("target", default)), category)
                target = plan.get("related_target", default.get("related_target"))
                related = self.resolve(target, category) if target else None
            except _IncompleteDraft:
                continue
            intent = plan.get("semantic_intent")
            if not isinstance(intent, dict):
                continue
            expression = plan.get("expression") or {}
            conditions = expression.get("conditions", [expression]) if isinstance(expression, dict) else []
            for check in self.interpretation_checks:
                rows = intent.get(check["kind"])
                for item in rows if isinstance(rows, list) else []:
                    if not isinstance(item, dict) or not isinstance(item.get("fields"), list):
                        continue
                    role = item.get("table", "base") if check["kind"] == "scopes" else "base"
                    if check["kind"] == "metrics":
                        if (item.get("side") != check["side"] or item.get("formula_path") != check.get("formula_path")
                                or item.get("condition_index", 0) != check["condition_index"]):
                            continue
                        if item.get("side") == "right":
                            index = item.get("condition_index", 0)
                            if type(index) is not int or not isinstance(conditions, list) or not 0 <= index < len(conditions):
                                continue
                            role = conditions[index].get("right_table", "base") if isinstance(conditions[index], dict) else "base"
                    owner = {"base": base, "related": related}.get(role) if isinstance(role, str) else None
                    field = check["field"]
                    if not owner or owner["id"] != check["table_id"] or role != check["role"] or field not in item["fields"]:
                        continue
                    if check["kind"] == "scopes":
                        members = item.get("memberships")
                        partition = members.get(field) if isinstance(members, dict) else None
                        prev = check.get("partition")
                        receipt = check.get("receipt") or (self.scope_receipt(prev) if prev else "")
                        if receipt and receipt != self.scope_receipt(partition):
                            if not (apply_choices and prev and item["fields"] == [field]
                                    and self.index.unique_requested_category(owner["id"], field, check["term"])
                                    and not plan.get("filters")):
                                continue
                            # The original partition must be exactly the explicitly named dictionary value.
                            names = {str(o["value"]) for f in self.fields[owner["id"]] if f["field_name"] == field
                                     for o in dictionary_options(f) if o["label"] == check["term"]}
                            if names != set(map(str, prev["include"])):
                                continue
                            item.update(category=check["term"], memberships={field: deepcopy(prev)})
                        elif check.get("confirmed") and not receipt and item.get("category") != check["term"]:
                            continue
                    if apply_choices and check.get("confirmed") and len(item["fields"]) > 1:
                        if check["kind"] == "scopes":
                            if any(f.get("field") in item["fields"] and f.get("field") != field
                                   for f in plan.get("filters") or [] if isinstance(f, dict)):
                                continue
                            if not isinstance(partition, dict):
                                continue
                            item["memberships"] = {field: partition}
                        else:
                            index, side = check["condition_index"], check["side"]
                            if not isinstance(conditions, list) or not 0 <= index < len(conditions) or not isinstance(conditions[index], dict):
                                continue
                            try:
                                slot, key = _metric_slot(conditions[index], item)
                            except _Unbound:
                                continue
                            slot[key] = field
                            item.pop("rule_names", None)
                        item["fields"] = [field]
                        item.pop("recommended", None)
                    covered.add(check["id"])
        exclusions = raw.get("interpretation_exclusions") if isinstance(raw, dict) else None
        for exclusion in exclusions if isinstance(exclusions, list) and len(exclusions) <= 64 else []:
            if (not isinstance(exclusion, dict) or not isinstance(exclusion.get("reason"), str)
                    or not 1 <= len(exclusion["reason"].strip()) <= 300):
                continue
            evidence = exclusion.get("evidence")
            ids = exclusion.get("ids", [exclusion.get("id")])
            if not isinstance(evidence, dict) or not isinstance(evidence.get("quote"), str) or not evidence["quote"].strip() or not isinstance(ids, list):
                continue
            quote = evidence["quote"].strip()
            if len(quote) > 500 or len(ids) > 64:
                continue
            for check in self.interpretation_checks:
                if check["id"] not in ids:
                    continue
                if check.get('first_seen') or check.get("confirmed"):
                    # A model-written reason is not a user's choice. Keep the original field/scope as an option.
                    continue
                table = next(table for table in self.tables if table["id"] == check["table_id"])
                field = next(field for field in self.fields[table["id"]] if field["field_name"] == check["field"])
                if exclusion_supported(check, field, evidence.get("source"), quote, self.request):
                    covered.add(check["id"])
        return [check for check in self.interpretation_checks if check["id"] not in covered
                and not (check["kind"] == "metrics" and (check["table_id"], check["field"]) in deferred)]

    def complete_interpretation_review(self, raw, selection, targets, docs, owner_choices, *, evidence_reviewed=False):
        coverage_pending = []
        self.check_draft_envelope(raw)
        if self.inherited_checks:
            return raw, selection, targets, docs, []
        self.preserve_plan_group(raw, targets[0])
        raw = self.documented_peer_choice(selection, raw, owner_choices)
        if not self.interpretation_checks:
            updated, pending = self.expand_interpretation_evidence({**selection, "draft": raw}, owner_choices)
            if self.document_review is not None:
                raw = self.document_review
            if pending or self.document_review is not None:
                selection = updated
                targets = ([selection] if selection.get("target") else []) + selection.get("candidate_targets", [])
                docs = self.documents(targets)
                evidence_reviewed = not pending
        if self.document_review is not None:
            plans = self.document_review.get("plans", [])
            owners = {(p.get("target") or selection["target"])["table"] for p in plans}
            if len(owners) > 1:
                raw = self.document_review
                evidence_reviewed = True
        missing = self.missing_interpretations(raw, targets)
        if missing and not evidence_reviewed:
            prompt = self.expanded_prompt(selection, docs, owner_choices)
            prompt += ("\n补充文档已展开，请按原需求核实这些检索线索是否适用；有真实歧义时给结构化选择，"
                       "不要求为每个词语命中单独生成方案或排除报告。检索线索：" + _json(missing)
                       + "\n上一轮待复核回复数据：" + _json(raw))
            raw = self.call(prompt, "review_interpretations")
            if isinstance(raw, dict):
                self.preserve_plan_group(raw, targets[0])
                raw = self.documented_peer_choice(selection, raw, owner_choices)
        if (not owner_choices and not self.coverage_reviewed and isinstance(raw, dict)
                and self.round_number < MAX_MODEL_ROUNDS):
            prior_plans = raw.get("plans", [raw])
            if not isinstance(prior_plans, list) or not prior_plans or any(not isinstance(plan, dict) for plan in prior_plans):
                raise _IncompleteDraft("规则方案必须为非空对象数组。")
            missing = self.missing_interpretations(raw, targets)
            backed = []
            for plan in prior_plans:
                owner = self.resolve(plan.get("target", targets[0].get("target", targets[0])),
                                     plan.get("report_category", targets[0].get("report_category")))
                backed.extend(suggestion_backed_interpretations(missing, plan, owner["table_name"], self.model_suggestions))
            backed = list({check["id"]:check for check in backed}.values())
            if backed:
                self.coverage_reviewed = True
                prompt = self.expanded_prompt(selection, docs, owner_choices)
                prompt += ("\n以下文档指标口径仍未被覆盖：其中有些属于你已列出的同表候选族，有些也被补充建议引用为对应指标。"
                           "请再次核实：原需求未限定维度时，确属原指标的独立可选方案要完整放入plans，"
                           "不能用一条无实际比较字段的join替代独立方案；补充差异核对仍独立保留。"
                           "不同期间的指标分别注明文档规定的适用范围，不将仅适用当期新发的指标强加到存量记录。"
                           "不适用时给有文档依据的interpretation_exclusions，不强制把所有检索词当成新规则。"
                           "保留当前已核实主案的字段、阈值、异常方向及范围。遗漏候选：" + _json(backed)
                           + "\n当前草稿：" + _json(raw))
                prior_suggestions = deepcopy(self.model_suggestions)
                try:
                    revised = self.call(prompt, "repair_rule")
                    self.check_draft_envelope(revised)
                    revised = self.documented_peer_choice(selection, revised, owner_choices)
                    plans = revised.get("plans", [revised])
                    if not isinstance(plans, list):
                        raise _IncompleteDraft("其他维度须给出独立方案。")
                    available = [plan for plan in plans if isinstance(plan, dict)]
                    for previous in prior_plans:
                        for index, proposed in enumerate(available):
                            try:
                                self.check_repair_targets(previous, proposed, targets[0])
                            except (_IncompleteDraft, AppError):
                                continue
                            available.pop(index)
                            break
                        else:
                            raise _IncompleteDraft("补全其他维度时仍须保留已经核实的全部原方案。")
                except (_IncompleteDraft, AppError) as coverage_error:
                    if isinstance(coverage_error, AppError) and coverage_error.code not in ("MODEL_RESPONSE_INVALID", "VALIDATION_ERROR"):
                        raise
                    self.model_suggestions = prior_suggestions
                    # A failed optional coverage answer cannot authorize a fourth rewrite of the original rule.
                    return raw, selection, targets, docs, backed
                raw = revised
                backed_ids = {check["id"] for check in backed}
                coverage_pending = [check for check in self.missing_interpretations(raw, targets)
                                    if check["id"] in backed_ids]
        # Once the model has the actual evidence, retrieval hits are not extra business requirements.
        # The returned rule still undergoes field, role, dictionary and SQL validation below.
        # Preserve actual declared choices; an incidental search hit has not been presented as a choice.
        self.interpretation_checks.extend(self.confirmed_checks)
        declared_missing = [check for check in self.missing_interpretations(raw, targets, apply_choices=True)
                            if self.required_interpretation(check, owner_choices)]
        declared_missing.extend(check for check in coverage_pending if check not in declared_missing)
        return raw, selection, targets, docs, declared_missing

    def required_interpretation(self, check, owner_choices=()):
        if check.get("confirmed"):
            return True
        field = check.get("field") or ""
        if field and re.search(r"(?<![A-Za-z0-9_])" + re.escape(field) + r"(?![A-Za-z0-9_])", self.request, re.I):
            return True
        owner = check["table_id"]
        for choice in owner_choices:
            binding = choice.get("binding") or {}
            if (binding.get("owner") != check["table"] or binding.get("kind") != check["kind"]
                    or binding.get("role") != check["role"] or binding.get("term") != check["term"]
                    or any(binding.get(k) != self.context.get(k) for k in ("source_id", "doc_version", "doc_sha256"))):
                continue
            try:
                if self.resolve({"table": check["table"]}, binding.get("report_category"))["id"] != owner:
                    continue
            except _IncompleteDraft:
                continue
            selected = choice.get("selection")
            if (check["kind"] == "metrics" and selected == field and binding.get("side") == check["side"]
                    and binding.get("formula_path") == check.get("formula_path")
                    and check["condition_index"] in binding.get("indices", [])):
                return True
            if (check["kind"] == "scopes" and isinstance(selected, dict) and selected.get("field") == field
                    and selected.get("table", "base") == check["role"]):
                return True
        if check["kind"] == "scopes":
            selected = [f for f in self.fields[owner] if f["field_name"] == field]
            return (field in self.index.explicitly_named_scopes(owner, selected) or
                    (check.get("first_seen", False) and self.index.unique_requested_category(owner, field, check.get("term"))))
        return any(self.index.exact_metric_field({"id": owner}, field, label)
                   for label in (check.get("label"), check.get("term")))

    @staticmethod
    def scope_receipt(partition):
        if not isinstance(partition, dict) or not isinstance(partition.get("include"), list):
            return ""
        return digest(sorted(map(str, partition["include"])))[:16]

    def confirmed_evidence(self, answers):
        """Resolve a previous field selection against this request's active document."""
        result = []
        for answer in answers:
            parts = answer.get("question_id", "").split("/", 7)
            if len(parts) != 8 or parts[0] != "evidence":
                continue
            _, table_id, kind, role, side, index, name, receipt = parts
            side, *path = side.split(".")
            if path and (kind != "metrics" or any(step not in ("left", "right") for step in path)):
                continue
            term = answer.get("context", "")
            table = next((t for t in self.tables if str(t["id"]) == table_id), None)
            if not table or kind not in ("metrics", "scopes") or role not in ("base", "related") or not index.isdecimal():
                continue
            field = next((f for f in self.fields[table["id"]] if f["field_name"] == name), None)
            if field and answer["answer"].endswith(f"（{table['table_name']}.{name}）"):
                result.append({"id": answer["question_id"], "kind": kind, "term": term, "role": role,
                               "side": side, "condition_index": int(index), "field": name, "table_id": table["id"],
                               "table": table["table_name"], "label": field.get("field_cn") or name, "confirmed": True,
                               "receipt": receipt, **({"formula_path": path} if path else {})})
        return result

    def evidence_questions(self, missing):
        questions = []
        for c in missing:
            purpose = "筛选范围" if c["kind"] == "scopes" else "检查指标"
            source = next(t for t in self.tables if t["id"] == c["table_id"])
            label = source.get("table_name_cn") or c["table"]
            text = f"是否采用「{label}」的「{c['label']}」作为「{c['term']}」的{purpose}？"
            receipt = self.scope_receipt(c.get("partition"))
            side = ".".join([c["side"], *c.get("formula_path", [])])
            key = f"evidence/{c['table_id']}/{c['kind']}/{c['role']}/{side}/{c['condition_index']}/{c['field']}/{receipt}"
            option = {"value": f"{c['table']}.{c['field']}", "label": f"采用{c['label']}"}
            if receipt:
                field = next(f for f in self.fields[c["table_id"]] if f["field_name"] == c["field"])
                included = set(map(str, c["partition"]["include"]))
                labels = [f"{o['value']}＝{o['label']}" for o in dictionary_options(field) if str(o["value"]) in included]
                if labels:
                    option["description"] = "纳入范围：" + "、".join(labels)
            questions.append({"id": key, "text": text, "requires_analysis": True, "evidence_term": c["term"],
                              "options": [option]})
        return {**self.clarify([q["text"] for q in questions]), "questions": questions}

    def restore_metric_choices(self, original, reviewed, default, missing):
        """Reconcile two model bindings of the same comparison against its document."""
        if not original or not all(c["kind"] == "metrics" and c.get("first_seen") for c in missing):
            return None
        before = self.verified_facts([original], default)
        after = self.verified_facts([reviewed], default)
        if not before or not after:
            return None
        first, last = before[0], after[0]
        if any(first[k] != last[k] for k in ("table", "related", "join", "logic", "null", "category")):
            return None
        if not set(first["scopes"]) <= set(last["scopes"]) or not first["filters"] <= last["filters"]:
            return None
        slots = {(c["condition_index"], c["side"], tuple(c.get("formula_path", ()))) for c in missing}
        if len(slots) != 1 or not isinstance(original.get("expression"), dict) or not isinstance(reviewed.get("expression"), dict):
            return None
        index, side, path = slots.pop()
        source = deepcopy(original["expression"].get("conditions", [original["expression"]]))
        result = deepcopy(reviewed)
        rows = result["expression"].get("conditions", [result["expression"]])
        if (not isinstance(rows, list) or not isinstance(source, list) or len(source) != len(rows)
                or type(index) is not int or not 0 <= index < len(rows)
                or not isinstance(source[index], dict) or not isinstance(rows[index], dict)
                or source[:index] != rows[:index] or source[index + 1:] != rows[index + 1:]
                or {k: v for k, v in source[index].items() if k != side} != {k: v for k, v in rows[index].items() if k != side}):
            return None
        role = "related" if side == "right" and rows[index].get("right_table") == "related" else "base"
        owner = last["related"] if role == "related" else last["table"]
        if not owner or any(c["role"] != role or c["table_id"] != owner["id"] for c in missing):
            return None
        reviewed_metrics = (result.get("semantic_intent") or {}).get("metrics")
        if not isinstance(reviewed_metrics, list):
            return None
        metrics = [m for m in reviewed_metrics if isinstance(m, dict) and m.get("side") == side and m.get("condition_index", 0) == index]
        metrics = [m for m in metrics if tuple(m.get("formula_path", ())) == path]
        if len(metrics) != 1:
            return None
        metric, = metrics
        try:
            old_slot, old_key = _metric_slot(source[index], metric)
            new_slot, new_key = _metric_slot(rows[index], metric)
        except _Unbound:
            return None
        old_field, reviewed_field = old_slot.get(old_key), new_slot.get(new_key)
        old_slot[old_key] = reviewed_field
        if source[index] != rows[index]:
            return None
        fields = {f["field_name"]: f for f in self.fields[owner["id"]]}
        current = metric.get("fields")
        if not isinstance(current, list) or not all(isinstance(n, str) and n in fields for n in current):
            return None
        names = list(dict.fromkeys([*(c["field"] for c in missing), *current]))
        if len({type_family(fields[n].get("data_type")) for n in names}) != 1:
            return None
        # An explicit document label wins over a later, unrelated substitution.
        # Two named fields, or multiple originally proposed fields, remain selectable.
        declared = {n for m in first["metrics"] if isinstance(m, dict) and m.get("side") == side and m.get("condition_index", 0) == index
                    and tuple(m.get("formula_path", ())) == path
                    for n in m.get("fields", []) if isinstance(n, str)}
        named = self.index.named_metric_choices()
        names = [n for n in names if n in declared or n.lower() in self.index.wanted or (owner["id"], n) in named]
        if not names or len(names) > 20:
            return None
        metric.update(fields=names, term=missing[0]["term"])
        metric.pop("recommended", None)
        new_slot[new_key] = names[0]
        if len(names) == 1 and names[0] == old_field:
            for key in ("rule_name", "violation_message"):
                if key in original:
                    result[key] = original[key]
        else:
            metric["rule_names"] = {n: p["rule_name"] for n, p in ((old_field, original), (reviewed_field, reviewed))
                                    if n in names and p.get("rule_name")}
            result["violation_message"] = "所选指标命中校验条件，请核实。"
        return result

    @staticmethod
    def check_draft_envelope(raw):
        if not isinstance(raw, dict) or not any(key in raw for key in ('rule_type', 'plans')):
            raise _IncompleteDraft('规则回复必须包含规则对象或 plans，不能重复选表封装')

    def preserve_plan_group(self, proposal, default):
        """Allocate for the current documented group without freezing unconfirmed model drafts."""
        plans = proposal.get("plans") if isinstance(proposal, dict) else None
        current = []
        mode = proposal.get("plan_mode", "alternatives") if isinstance(proposal, dict) else None
        if isinstance(plans, list) and 2 <= len(plans) <= SEMANTIC_MAX_PLANS and mode in ("alternatives", "parallel"):
            for plan in plans:
                if not isinstance(plan, dict):
                    break
                category = plan.get("report_category", default.get("report_category"))
                target = plan.get("target", default.get("target", default))
                related = plan.get("related_target", default.get("related_target") if target == default.get("target") else None)
                try:
                    base = self.resolve(target, category)
                    other = self.resolve(related, category) if related else None
                except _IncompleteDraft:
                    break
                intent = plan.get("semantic_intent")
                questions = intent.get("open_questions") if isinstance(intent, dict) else None
                pending = {q for q in questions if isinstance(q, str) and q} if isinstance(questions, list) else set()
                judgment = model_judgment(plan, stage="generate_rule")
                pending.update(judgment["unsupported_requirements"])
                if plan.get("rule_type") is None:
                    pending.update(judgment["uncertainties"])
                facts = self.bound_plan_facts(plan, base, other, category)
                current.append((base["id"], other["id"] if other else None, facts, pending))
        if not isinstance(plans, list) or len(current) != len(plans):
            current = []
        if current:
            checks = []
            for base, other, facts, _ in current:
                if not facts or not facts["parts"] or not all(
                    "left" in part and "op" in part and (part["op"] in ("is_null", "is_not_null") or "right" in part)
                    for part in facts["parts"]
                ):
                    continue
                predicates = frozenset(frozenset(part.items()) for part in facts["parts"])
                check = (base, other, facts["logic"], predicates, set(facts["scopes"]), facts["filters"], facts["null"])
                if check not in checks:
                    checks.append(check)
            self.budget_units = max(self.budget_units, min(SEMANTIC_MAX_BUDGET_UNITS, len(checks)))

    def documents(self, targets):
        result = []
        for target in targets:
            if not isinstance(target, dict):
                raise _IncompleteDraft("候选对象必须给出真实表名")
            main = target.get("target", target)
            for item in (main, target.get("related_target") or {}):
                if item:
                    table = self.resolve(item, target.get("report_category"))
                    if table not in result:
                        result.append(table)
        if not result:
            raise _IncompleteDraft("请给出当前活动文档中的真实主表")
        return result

    def clarify(self, why, unsupported=(), *, model_suggestions=None, **extra):
        self.service._emit_progress(self.progress, "generation", "needs_confirmation", "需要补充规则口径或文档依据")
        result = clarification_candidate(why, list(unsupported), **{**self.context, **extra})
        if self.inputs.get("include_suggestions") is False:
            return {**result, "ai_suggestions": []}
        result["ai_suggestions"] = build_ai_suggestions(
            self.model_suggestions if model_suggestions is None else model_suggestions,
            tables=self.tables, fields_by_table=self.fields, candidates=[result],
            model_only=True, limit=MAX_SUGGESTIONS,
            select_category_tables=lambda tables, codes: self.service._category_tables(tables, codes, self.categories),
        )
        return result

    def run(self, examples, owner_choices, existing, *, reuse_result=True):
        self.owner_choices = owner_choices
        if not self.inputs.get("clarification_answers") and not owner_choices:
            scope = category_scope_only(check_without_category_prefix(self.request, self.categories))
            if scope and any(scope["label"] in option["label"] for fields in self.fields.values() for field in fields
                             if scope["label"] in str(field.get("dictionary") or "") for option in dictionary_options(field)):
                return self.clarify([f"已指定「{scope['label']}{scope['entity']}」的范围，请补充要检查的字段和异常条件。"])
        cache_allowed = reuse_result and not owner_choices
        threshold_changes = _changed_thresholds(self, examples)
        self.index = DocumentEvidence(self.tables, self.fields, self.request)
        if cache_allowed:
            response = self.service.storage.cached_analysis_result(self.inputs["context"], self.request)
            if response and not _threshold_question(response.get("draft"), threshold_changes):
                try:
                    selection = deepcopy(response["selection"])
                    targets, docs, judgment = self.prepare_selection(selection)
                    if targets:
                        if not isinstance(response.get("draft"), dict):
                            raise _IncompleteDraft("缓存中的规则草稿结构无效")
                        proposal = deepcopy(response["draft"])
                        _discard_cached_plan_suggestion_copies(proposal)
                        cached_suggestions = proposal.get("ai_suggestions", selection.get("ai_suggestions"))
                        if isinstance(cached_suggestions, list):
                            self.model_suggestions = deepcopy(cached_suggestions)
                        self.initial_proposal = deepcopy(proposal)
                        reviewed, pending = self.expand_interpretation_evidence({**selection, "draft": proposal})
                        if pending:
                            raise _IncompleteDraft("缓存尚未核实当前文档中的独立候选口径")
                        refreshed = reviewed.get("draft", proposal)
                        targets, docs, judgment = self.prepare_selection(reviewed)
                        result = self.materialize(refreshed, targets, {t["id"] for t in docs}, existing,
                                                  allow_supplement=refreshed != proposal)
                    else:
                        result = self.clarify(judgment["uncertainties"], judgment["unsupported_requirements"],
                                              model_suggestions=response["selection"].get("ai_suggestions", []))
                except ScopeEvidenceRequired as exc:
                    return self.clarify([str(exc)])
                except AppError as exc:
                    if exc.code not in ("MODEL_RESPONSE_INVALID", "VALIDATION_ERROR"):
                        raise
                except (_IncompleteDraft, KeyError, TypeError, ValueError):
                    pass
                else:
                    result.update(memory_decision="exact", analysis_reused=True)
                    return result
                # A rejected cached selection cannot authorize the next model request.
                self.budget_units = 1
                self.competing_evidence = []
                self.interpretation_checks = []
                self.interpretation_overflow = []
                self.document_review = None
                self.model_suggestions = []
                self.initial_proposal = None
        self.index = DocumentEvidence(self.tables, self.fields, self.request)
        select_prompt = self.selection_prompt()
        prompt = select_prompt + self.rule_prompt("使用上方 fields 及完整字典", "从上方真实文档选择", continuation=True)
        prompt += ('\n本次合并回复：单方案格式为 {"target":{"table":"真实主表名"},'
                   '"related_target":{"table":"真实关联表名"},"draft":{上述规则}}；'
                   '多方案在最外层给 plan_mode 和 plans，每项按单方案格式声明自己的表和规则。'
                   '单表省略 related_target；有 join 必须声明其 related_target。需扩展时只返回目标。')
        prompt += SEMANTIC_COMBINED_EXAMPLE
        if examples or owner_choices:
            history = {"memories": examples, "current_owner_choices": owner_choices, "current_request": self.request}
            prompt += SEMANTIC_MEMORY_CONTRACT + _json(history)
        selection = self.call(prompt, "select_and_generate")
        decision, remembered = memory_choice(selection, examples) if examples else ("", None)
        memory_table = None
        if remembered is not None:
            baseline = examples[selection["memory_index"]]
            memory_table = self.service._memory_table(baseline, self.tables, self.categories)
            try:
                selected_docs = self.documents([selection, {**selection, **remembered}])
            except _IncompleteDraft:
                selected_docs = []
            if selected_docs != [memory_table]:
                decision, remembered = "fresh", None
        independent_draft = (selection.get("reuse_decision") in (None, "fresh") and selection.get("memory_index") is None)
        correction = _threshold_question(selection.get("draft", selection), threshold_changes)
        if correction or (examples and not independent_draft and remembered is None):
            # An unverified memory must not supply the comparison or constrain its fresh replacement.
            selection = {key: value for key, value in selection.items() if key not in ("draft", "rule_type", "plans")}
            decision, remembered = "fresh", None
        if not selection.get("target") and not selection.get("candidate_targets"):
            selection = self.bind_missing_target(selection)
        selection = self.bind_planned_targets(selection)
        incomplete = [t["id"] for t in self.tables if not self.index.fully_expanded(t)]
        only_memory_decision = examples and selection.get("reuse_decision") and not (
            selection.get("result_type") or selection.get("uncertainties") or selection.get("unsupported_requirements"))
        if not selection.get("target") and not selection.get("candidate_targets") and (incomplete or only_memory_decision):
            # No document can be ruled out by absent retrieval hits. Expand before asking the user.
            relevant = [i for i in self.index.expansion_order if i in incomplete][:2]
            selection = self.call(self.selection_prompt(expanded_ids=relevant) +
                                  "\n本轮只选表，需要更多文档请给出有依据的候选表，不因目录没有详情断言字段不存在。", "select_table")
            stale = _threshold_question(selection.get("draft", selection), threshold_changes)
            if stale:
                correction = stale
                selection = {key: value for key, value in selection.items() if key not in ("draft", "rule_type", "plans")}
            if decision:
                decision, remembered = "fresh", None
            selection = self.bind_planned_targets(selection)
        selection = self.bind_missing_related_target(selection)
        self.initial_proposal = deepcopy(selection.get("draft", selection if "rule_type" in selection else None))
        try:
            self.preserve_plan_group(selection.get("draft", selection), selection)
            selection, review_interpretations = self.expand_interpretation_evidence(selection, owner_choices)
        except ScopeEvidenceRequired as exc:
            return self.clarify([str(exc)])
        targets, docs, select_judgment = self.prepare_selection(selection)
        if not targets:
            if cache_allowed:
                self.reusable_response = model_snapshot({**selection, "ai_suggestions": self.model_suggestions})
            return self.clarify(select_judgment["uncertainties"], select_judgment["unsupported_requirements"])
        proposal = selection.get("draft", selection if "rule_type" in selection or "plans" in selection else None)
        can_use_memory = remembered is not None and docs == [memory_table]
        cached = None
        if (self.inherited_checks and isinstance(proposal, dict) and proposal.get("rule_type") == "field_compare"
                and (selection.get("target") or {}).get("table") == self.inputs["period_scope"]["table"]):
            # Scope, types, joins and dictionary codes still pass through materialize against full metadata.
            cached = proposal
        elif not review_interpretations and (not examples or independent_draft or can_use_memory):
            if self.ready_for_combined(selection, proposal, docs):
                cached = proposal
        if decision and cached is None:
            decision = "fresh"
        if self.document_review is not None:
            cached = self.document_review
            if decision:
                decision = "fresh"
        if not isinstance(cached, dict):
            cached = None
        if cached is None and isinstance(proposal, dict):
            self.request_conditions = self.explicit_review_conditions(proposal, targets[0], docs)
        allowed = {t["id"] for t in docs}
        raw = None
        prompt = ""
        try:
            if cached is None:
                prompt = self.expanded_prompt(selection, docs, owner_choices)
                if correction:
                    prompt += "\n" + correction
                raw = self.call(prompt, "generate_rule")
            else:
                raw = cached
            question = _threshold_question(raw, threshold_changes)
            if question:
                return self.clarify([question])
            raw, selection, targets, docs, missing = self.complete_interpretation_review(
                raw, selection, targets, docs, owner_choices, evidence_reviewed=cached is None)
            allowed = {table["id"] for table in docs}
            question = _threshold_question(raw, threshold_changes)
            if question:
                return self.clarify([question])
            if missing:
                if any(c.get("confirmed") for c in missing):
                    raise _IncompleteDraft("规则遗漏了用户已确认的字段口径，请在相应指标或范围中落实：" +
                                           _json([c for c in missing if c.get("confirmed")]), category="confirmed_field")
                restored = self.restore_metric_choices(proposal, raw, targets[0], missing)
                if restored is None:
                    return self.evidence_questions(missing)
                raw = restored
            result = self.materialize(deepcopy(raw), targets, allowed, existing)
        except ScopeEvidenceRequired as exc:
            return self.clarify([str(exc)])
        except (_IncompleteDraft, AppError) as exc:
            if isinstance(exc, AppError) and exc.code not in ("MODEL_RESPONSE_INVALID", "VALIDATION_ERROR"):
                raise
            if self.document_review is not None and not (isinstance(exc, _IncompleteDraft) and exc.category == "confirmed_field"):
                return self.clarify(["文档候选的条件、范围或字段归属仍需核实，请补充要检查的口径。"])
            repair_source = deepcopy(raw)
            path = exc.path if isinstance(exc, _IncompleteDraft) and isinstance(raw, dict) else ()
            if path and "plans" in raw and path[0] != "plans":
                path = ()
            LOGGER.info("Semantic review analysis=%s round=%d stage=generate_rule category=%s path=%s",
                        self.analysis_id, self.round_number, exc.category if isinstance(exc, _IncompleteDraft) else exc.code,
                        ".".join(map(str, path)) if path else "draft")
            self.service._emit_progress(self.progress, "generation", "running", "正在补全并重新核实规则草稿")
            try:
                if path:
                    raw = self.patch(raw, path, str(exc), docs, owner_choices)
                else:
                    prompt = prompt or self.expanded_prompt(selection, docs, owner_choices)
                    problem = (str(exc) if isinstance(exc, _IncompleteDraft)
                               else getattr(exc, "repair_hint", "") or "请核对 JSON 对象、表达式、类型和文档字段")
                    prompt += "\n只修正以下错误，保留已核实的对象、范围、阈值、异常条件与各方案：" + problem
                    if raw is not None:
                        prompt += "\n待修复草稿数据：" + _json(raw)
                    repaired = self.call(prompt, "repair_rule")
                    if not isinstance(exc, _IncompleteDraft) or exc.category != "request_condition":
                        self.check_repair_targets(raw, repaired, targets[0],
                                                  confirmed=self.confirmed_checks if isinstance(exc, _IncompleteDraft)
                                                  and exc.category == "confirmed_field" else ())
                    raw = repaired
                self.check_draft_envelope(raw)
                question = _threshold_question(raw, threshold_changes)
                if question:
                    return self.clarify([question])
                raw = self.documented_peer_choice(selection, raw, owner_choices)
                missing = [c for c in self.missing_interpretations(raw, targets, apply_choices=True) if self.required_interpretation(c, owner_choices)]
                if any(c.get("confirmed") for c in missing):
                    raise _IncompleteDraft("修复后的规则仍遗漏用户已确认的字段", category="confirmed_field")
                if missing:
                    return self.evidence_questions(missing)
                result = self.materialize(deepcopy(raw), targets, allowed, existing)
            except ScopeEvidenceRequired as exc:
                return self.clarify([str(exc)])
            except (_IncompleteDraft, AppError) as repair_error:
                if isinstance(repair_error, AppError) and repair_error.code not in ("MODEL_RESPONSE_INVALID", "VALIDATION_ERROR"):
                    raise
                category = getattr(repair_error, "category", "") or "rule_validation"
                if category == "request_condition":
                    return self.clarify([str(repair_error)])
                clarified = (None if category == "repair_condition_changed"
                             else self.dictionary_clarification(exc, repair_source, targets))
                if clarified is not None:
                    return clarified
                raise failure("MODEL_RESPONSE_INVALID", "generate_rule", category=category,
                              analysis_id=self.analysis_id, round_number=self.round_number) from repair_error
            cached = None
            if decision:
                decision = "fresh"
        cache_selection = {key: value for key, value in selection.items() if key != "ai_suggestions"}
        response = model_snapshot(cache_selection, {**raw, "ai_suggestions": self.model_suggestions})
        _discard_cached_plan_suggestion_copies(response["draft"])
        if decision:
            result.update(memory_decision=decision, analysis_reused=decision in ("adapt", "reuse") and cached is not None)
        if cache_allowed and result.get("ai_suggestions_status") != "incomplete":
            self.reusable_response = response
        return result

    def dictionary_clarification(self, error, raw, targets):
        if not isinstance(error, _IncompleteDraft) or error.category != "dictionary_partition" or not isinstance(raw, dict):
            return None
        path = error.path
        plan = raw
        if path[:1] == ("plans",) and len(path) > 2:
            plan = raw["plans"][path[1]]
            path = path[2:]
        if len(path) != 4 or path[:2] != ("semantic_intent", "scopes"):
            return None
        scope = plan.get("semantic_intent", {}).get("scopes", [])[path[2]]
        default = targets[0]
        category = plan.get("report_category", default.get("report_category"))
        try:
            base = self.resolve(plan.get("target", default.get("target", default)), category)
            related_target = plan.get("related_target", default.get("related_target"))
            related = self.resolve(related_target, category) if related_target else None
        except _IncompleteDraft:
            return None
        question = dictionary_partition_question(scope, self.fields[base["id"]], self.fields[related["id"]] if related else [])
        if question is None:
            return None
        result = self.clarify([question["text"]])
        result["questions"] = [question]
        return result

    def prepare_selection(self, selection):
        if not isinstance(selection, dict):
            raise _IncompleteDraft("选表结果结构无效")
        try:
            judgment = model_judgment(selection, stage="select_table")
        except AppError as exc:
            raise failure("MODEL_RESPONSE_INVALID", "select_table", category="selection_structure",
                          analysis_id=self.analysis_id, round_number=self.round_number) from exc
        self.context["model_judgments"] = {"select_table": judgment}
        additional = selection.get("candidate_targets", [])
        if not isinstance(additional, list) or len(additional) > 2:
            raise failure("MODEL_RESPONSE_INVALID", "select_table", category="candidate_targets_structure",
                          analysis_id=self.analysis_id, round_number=self.round_number)
        targets = ([selection] if selection.get("target") else []) + additional
        if not targets:
            if not (judgment["uncertainties"] or judgment["unsupported_requirements"]):
                raise failure("MODEL_RESPONSE_INVALID", "select_table", category="missing_target_and_explanation",
                              analysis_id=self.analysis_id, round_number=self.round_number)
            return targets, [], judgment
        try:
            docs = self.documents(targets)
            main_ids = {self.resolve(target.get("target", target), target.get("report_category"))["id"] for target in targets}
        except _IncompleteDraft as exc:
            raise failure("MODEL_RESPONSE_INVALID", "select_table", category="target_document_binding",
                          analysis_id=self.analysis_id, round_number=self.round_number) from exc
        self.budget_units = max(self.budget_units, min(SEMANTIC_MAX_BUDGET_UNITS, len(main_ids)))
        self.service._emit_progress(self.progress, "semantics", "completed", "已核实需求所用的分析对象")
        self.service._emit_progress(self.progress, "metadata", "completed", "已读取所选对象的完整字段和字典",
                                    table_name=docs[0]["table_name"], field_count=sum(len(self.fields[t["id"]]) for t in docs))
        self.service._emit_progress(self.progress, "generation", "running", "正在核实规则草稿")
        return targets, docs, judgment

    def expanded_prompt(self, selection, docs, owner_choices):
        # Selection stays compact. Once an object is chosen, expose its actual full document:
        # a weak first draft must not hide the field needed to correct that draft.
        views = [self.evidence(table) for table in docs]
        evidence = _json(views)
        prompt = self.rule_prompt(evidence, "、".join(t["table_name"] for t in docs))
        hints = {k: selection[k] for k in ("target", "related_target", "report_category", "semantic_hints",
                                           "field_choices", "candidate_targets") if k in selection}
        prompt += "\n已展开选定表的完整文档，独立核实原需求与所有可行口径。选表结果：" + _json(hints)
        if self.competing_evidence:
            prompt += ("\n以下是按需求原词发现、尚待业务判断的竞争证据，不预先认定同义或适用。"
                       "term是本次需求的原词，first_interpretation只是首轮暂选解释，并非用户指定。"
                       "禁止把该暂选解释作为更窄的需求，再据它排除其他合理定义。"
                       "逐一核实各表粒度、指标和分类定义。用户未限定且确有不同可行粒度时保留独立plans；"
                       "同表指标或范围的原始/当前等口径未被需求裁决时保留metrics.fields或scopes.fields选项。"
                       "推荐不等于用户确认。仅共用码值或无关派生字段不构成候选，不要求逐列写排除说明："
                       + _json(self.competing_evidence))
            prompt += ("\n下列编号只是文档检索线索，不是必须逐项采用的业务要求，也不需要逐编号排除报告。"
                       "由你结合原需求与完整字段定义判断适用性；明确限定、不同业务指标/期间、重复存储或缺少必要范围依据时不强行纳入；"
                       "原始/当前、单位/累计等口径若用户未裁决，应保留选择，不能因为另一个更常用就排除。"
                       "独立维度方案无需互相比较，不能仅因量纲或粒度不同排除其独立校验。待核实编号："
                       + _json(self.interpretation_checks))
        if self.interpretation_overflow:
            prompt += ("\n其他目录检索命中（不预先认定存在独立校验）：" + _json(self.interpretation_overflow)
                       + "。只有文档确实支持多个独立维度且需求未限定时才提出具体业务选择，不能仅按命中表数量追问。")
        proposal = selection.get("draft")
        plans = proposal.get("plans", [proposal]) if isinstance(proposal, dict) else []
        multiple = isinstance(plans, list) and len(plans) > 1
        for plan in plans if isinstance(plans, list) else []:
            intent = plan.get("semantic_intent") if isinstance(plan, dict) else None
            if isinstance(intent, dict):
                for key in ("metrics", "scopes"):
                    items = intent.get(key)
                    if isinstance(items, list):
                        multiple |= any(isinstance(item, dict) and isinstance(item.get("fields"), list)
                                        and len(item["fields"]) > 1 for item in items)
        if multiple:
            prompt += "\n上一轮已发现的多口径草稿数据（结合完整证据复核，不能默默收成唯一口径）：" + _json(proposal)
        if owner_choices:
            prompt += "\n当前用户在上一版对实际选项的选择（重新核实）：" + _json(owner_choices)
        prompt += SEMANTIC_COMBINED_EXAMPLE
        prompt += ("\n上述只是虚构格式示例。本轮可返回带target/draft的一致封装或直接规则对象；"
                   "candidate_targets表示可能独立的被检查对象，不能直接当成related_target。"
                   "启用知识明确列出的多个适用维度，应分别生成plans，不用一个额外join代替另一项独立校验。"
                   "已确认业务知识适用于语义相同的改述，不按历史例句是否逐字相同判断适用性。")
        return prompt

    def rule_prompt(self, evidence, table, *, continuation=False):
        if self.prompts["generate_rule"] == DEFAULT_PROMPTS["generate_rule"]:
            template = "需求：{request_text}。已选对象：{table}。文档：{fields}。"
            if continuation:
                template = "所用证据：{fields}。"
        else:
            template = self.prompts["generate_rule"]
        return ("" if continuation else self.prefix) + self.service._render(template, {
            "request_text": self.request, "table": table, "fields": evidence,
        }) + SEMANTIC_OUTPUT_CONTRACT

    def patch(self, raw, path, problem, docs, owner_choices):
        if path[0] == "plans":
            result = deepcopy(raw)
            index = path[1]
            result["plans"][index] = self.patch(raw["plans"][index], path[2:], problem, docs, owner_choices)
            return result
        field = path[-1]
        if field in ("memberships", "field"):
            scope = raw["semantic_intent"]["scopes"][path[2]]
            role = scope.get("table", "base")
            if role not in ("base", "related") or role == "related" and len(docs) < 2:
                raise _IncompleteDraft("修复分类字段必须属于已选文档对象")
            table = docs[1] if role == "related" else docs[0]
            target = raw.get("related_target" if role == "related" else "target")
            if target:
                table = self.resolve(target, raw.get("report_category"))
                if table not in docs:
                    raise _IncompleteDraft("修复分类字段必须属于已选文档对象")
            if field == "field":
                return self.patch_scope_field(raw, scope, path[2], table, problem, owner_choices)
            evidence = [self.evidence(table, full=False, names=set(scope["fields"]))]
        elif field in ("rule_name", "violation_message"):
            evidence = []
        else:
            evidence = [self.evidence(t) for t in docs]
        prompt = (self.prefix + "只补全草稿指定位置，单独返回 {\"patch\":{\"" + field + "\":对应结构}}。"
                  + "位置：" + ".".join(map(str, path)) + "。错误：" + problem + "。原始需求：" + self.request
                  + "。metrics=[{side,term,fields}]；scopes=[{category,fields,memberships:{列:{include,exclude}}}]；"
                  + "open_questions=[独立未决问题]。保留确有依据的所有字段口径和完整字典分组。"
                  + "草稿数据：" + _json(raw) + "。本轮授权对象及字段：" + _json(evidence))
        if owner_choices:
            prompt += "。当前用户选择：" + _json(owner_choices)
        reply = self.call(prompt, "repair_rule")
        if set(reply) == {"patch"} and isinstance(reply["patch"], dict) and set(reply["patch"]) == {field}:
            value = reply["patch"][field]
        else:
            # A model using the previous complete-draft format can only fill the same hole.
            check = deepcopy(reply)
            # An equivalent selection wrapper is context, not a change to the rule hole.
            for key, owner in (("target", docs[0]), ("related_target", docs[1] if len(docs) > 1 else None)):
                if key not in raw and owner is not None and check.get(key) == {"table": owner["table_name"]}:
                    check.pop(key)
            if "report_category" not in raw and check.get("report_category"):
                try:
                    if self.resolve({"table": docs[0]["table_name"]}, check["report_category"]) == docs[0]:
                        check.pop("report_category")
                except _IncompleteDraft:
                    pass
            current = check
            for part in path[:-1]:
                try:
                    current = current[part]
                except (TypeError, IndexError, KeyError):
                    raise _IncompleteDraft("修复未补齐指定结构") from None
            if not isinstance(current, dict) or field not in current:
                raise _IncompleteDraft("修复未补齐指定结构")
            value = current.pop(field)
            original = deepcopy(raw)
            previous = original
            for part in path[:-1]:
                previous = previous[part]
            previous.pop(field, None)
            if check != original:
                raise _IncompleteDraft("修复改变了指定位置以外的草稿内容", category="repair_condition_changed")
        result = deepcopy(raw)
        current = result
        for part in path[:-1]:
            current = current[part]
        current[field] = value
        return result

    def patch_scope_field(self, raw, scope, index, table, problem, owner_choices):
        fields = self.fields[table["id"]]
        known = {f["field_name"] for f in fields}
        missing, = set(scope["fields"]) - known
        choices = {f["field_name"] for f in fields if f.get("dictionary") and f["field_name"] not in scope["fields"]}
        prompt = (self.prefix + problem + "。只修复错误列 " + missing
                  + '，返回 {"patch":{"field":"正确物理名"}}。保留其余字段、分类及全部码值。原需求：'
                  + self.request + "。草稿：" + _json(raw) + "。候选字典证据："
                  + _json(self.evidence(table, full=False, names=choices)))
        if owner_choices:
            prompt += "。当前用户选择：" + _json(owner_choices)
        reply = self.call(prompt, "repair_rule")
        is_patch = set(reply) == {"patch"} and isinstance(reply["patch"], dict) and set(reply["patch"]) == {"field"}
        if is_patch:
            name = reply["patch"]["field"]
        else:
            try:
                name = reply["semantic_intent"]["scopes"][index]["fields"][scope["fields"].index(missing)]
            except (KeyError, IndexError, TypeError):
                raise _IncompleteDraft("修复未补齐分类字段") from None
        if not isinstance(name, str) or name not in choices:
            raise _IncompleteDraft("分类字段修复必须采用所选对象中独立的真实字典列")
        result = deepcopy(raw)
        fixed = result["semantic_intent"]["scopes"][index]
        fixed["fields"] = [name if field == missing else field for field in scope["fields"]]
        fixed["memberships"][name] = fixed["memberships"].pop(missing)
        if fixed.get("recommended") == missing:
            fixed["recommended"] = name
        if not is_patch and reply != result:
            raise _IncompleteDraft("分类字段修复不得改变其他字段或码值")
        return result

    def check_repair_targets(self, raw, repaired, default, *, confirmed=()):
        if not raw:
            return
        mode = raw.get("plan_mode", "alternatives")
        if mode in ("parallel", "alternatives") and repaired.get("plan_mode", "alternatives") != mode:
            raise _IncompleteDraft("修复不可改变原有方案之间的关系")
        old_plans = raw.get("plans", [raw])
        new_plans = repaired.get("plans", [repaired])
        if isinstance(old_plans, list) and all(isinstance(p, dict) for p in old_plans):
            if not isinstance(new_plans, list) or len(old_plans) != len(new_plans):
                raise _IncompleteDraft("修复不可增删原有方案")
            for before, after in zip(old_plans, new_plans):
                if not isinstance(after, dict):
                    raise _IncompleteDraft("修复草稿格式无效")
                category = before.get("report_category", default.get("report_category"))
                table = self.resolve(before.get("target", default.get("target", default)), category)
                related = before.get("related_target", default.get("related_target"))
                owners = {"base": table["id"], "related": self.resolve(related, category)["id"] if related else None}
                selected = [(c["kind"], c["role"], c["side"], c["condition_index"], c["field"])
                            for c in confirmed if c["table_id"] == owners[c["role"]]]
                base_fields = self.fields[table["id"]]
                related_fields = self.fields[self.resolve(related, category)["id"]] if related else []
                roles = _roles(base_fields, related_fields)
                old_bound = _normalize_documented_operands(deepcopy(before), base_fields, related_fields, self.request, self.inputs.get("clarification_answers") or [])
                new_bound = _normalize_documented_operands(deepcopy(after), base_fields, related_fields, self.request, self.inputs.get("clarification_answers") or [])
                policy = verified_null_policy(old_bound, roles)
                if policy is not None and policy != new_bound.get("null_policy"):
                    raise _IncompleteDraft("修复不可改变已核实的空值处理口径")
                old_expr, new_expr = old_bound.get("expression"), new_bound.get("expression")
                if isinstance(old_expr, dict):
                    if not isinstance(new_expr, dict):
                        raise _IncompleteDraft("修复不可移除已有异常条件")
                    old_rows = old_expr.get("conditions", [old_expr])
                    new_rows = new_expr.get("conditions", [new_expr])
                    if isinstance(old_rows, list) and old_rows and all(isinstance(r, dict) for r in old_rows):
                        if (not isinstance(new_rows, list) or len(new_rows) != len(old_rows)
                                or old_expr.get("logic") != new_expr.get("logic")):
                            raise _IncompleteDraft("修复不可改变原有条件的数量和组合关系")
                        for index, (left, right) in enumerate(zip(old_rows, new_rows)):
                            if not isinstance(right, dict):
                                raise _IncompleteDraft("修复草稿比较条件无效")
                            for side in ("left", "right"):
                                if left.get(side + "_type") != "formula":
                                    continue
                                try:
                                    names = formula_fields(left.get(side))
                                except AppError:
                                    continue
                                if any(type_family(roles["base"].get(n, {}).get("data_type")) != "number" for n in names):
                                    continue
                                expected = deepcopy(left)
                                for check in confirmed:
                                    if (check["kind"] == "metrics" and check["side"] == side and check["condition_index"] == index
                                            and check["role"] == "base" and check["table_id"] == table["id"] and check.get("formula_path")):
                                        try:
                                            slot, key = _metric_slot(expected, check)
                                        except _Unbound:
                                            continue
                                        slot[key] = check["field"]
                                if right.get(side + "_type") != "formula" or not _same_declaration(expected[side], right.get(side)):
                                    raise _IncompleteDraft("修复不可改变已经核实的公式字段、常量及运算顺序")
                            name = left.get("left")
                            if (isinstance(name, str) and name in roles["base"] and name != right.get("left")
                                    and ("metrics", "base", "left", index, right.get("left")) not in selected):
                                raise _IncompleteDraft("修复不可改变已核实的左侧字段")
                            implicit_constant = (left.get("op") not in ("is_null", "is_not_null")
                                                 and "right_type" not in left and is_finite_number(left.get("right")))
                            kind = left.get("right_type", "value" if implicit_constant else "field")
                            if left.get("op") not in ("is_null", "is_not_null") and kind in ("value", "field"):
                                if right.get("right_type", "field") != kind:
                                    raise _IncompleteDraft("修复不可改变右侧操作数类型")
                                if kind == "field":
                                    role = left.get("right_table", "base")
                                    if isinstance(role, str) and role in roles and roles[role]:
                                        name = left.get("right")
                                        if right.get("right_table", "base") != role or (
                                                isinstance(name, str) and name in roles[role] and right.get("right") != name
                                                and ("metrics", role, "right", index, right.get("right")) not in selected):
                                            raise _IncompleteDraft("修复不可改变已核实的右侧字段及其归属")
                            if left.get("op") in ("lt", "lte", "gt", "gte", "eq", "neq", "is_null", "is_not_null"):
                                if left["op"] != right.get("op"):
                                    raise _IncompleteDraft("修复不可改变已有异常方向")
                            if kind == "value" and (right.get("right_type") != "value"
                                    or not valid_comparison_literal(left.get("op"), right.get("right")) or left.get("right") != right.get("right")):
                                raise _IncompleteDraft("修复不可改变原有常量阈值")
                for key in ("filters", "join"):
                    preserved = (join_decisions_refine(before.get(key), after.get(key),
                                                      base_fields=base_fields, related_fields=related_fields) if key == "join"
                                 else _same_declaration(before.get(key), after.get(key)))
                    if not preserved:
                        raise _IncompleteDraft("修复不可改变已有筛选或关联范围")
                locator = before.get("business_key")
                if isinstance(locator, str) and locator in roles["base"] and locator != after.get("business_key"):
                    raise _IncompleteDraft("修复不可改变已核实的结果定位字段")
                old_intent, new_intent = before.get("semantic_intent"), after.get("semantic_intent")
                old_scopes = old_intent.get("scopes") if isinstance(old_intent, dict) else None
                new_scopes = new_intent.get("scopes") if isinstance(new_intent, dict) else None
                if confirmed and isinstance(new_scopes, list) and isinstance(old_scopes, list):
                    old_scopes, new_scopes = list(old_scopes), list(new_scopes)
                    for scope in old_scopes[:]:
                        if scope in new_scopes:
                            old_scopes.remove(scope)
                            new_scopes.remove(scope)
                    for c in confirmed:
                        if c["kind"] != "scopes" or c["table_id"] != owners[c["role"]]:
                            continue
                        def same_field(scope):
                            return isinstance(scope, dict) and scope.get("table", "base") == c["role"] and scope.get("fields") == [c["field"]]
                        old = [s for s in old_scopes if same_field(s)]
                        new = [s for s in new_scopes if same_field(s)]
                        if len(old) <= 1 and len(new) == 1:
                            new_scopes.remove(new[0])
                            if old:
                                old_scopes.remove(old[0])
                if isinstance(old_intent, dict) and old_scopes != new_scopes:
                    raise _IncompleteDraft("修复不可改变已有分类范围")
                try:
                    old_driver = normalize_project_driver(before.get("project_driver"))
                except AppError:
                    old_driver = None
                if old_driver is not None and old_driver != after.get("project_driver"):
                    raise _IncompleteDraft("修复不可改变或移除已声明的项目驱动侧")
                for key in ("target", "related_target", "report_category"):
                    if not isinstance(after, dict) or before.get(key, default.get(key)) != after.get(key, default.get(key)):
                        raise _IncompleteDraft("修复不可更换所选文档对象")

    def verified_facts(self, plans, default):
        facts = []
        for plan in plans:
            if not isinstance(plan, dict) or plan.get("rule_type") != "field_compare":
                continue
            target = plan.get("target", default.get("target", default))
            category = plan.get("report_category", default.get("report_category"))
            related = plan.get("related_target", default.get("related_target") if target == default.get("target") else None)
            try:
                table = self.resolve(target, category)
                other = self.resolve(related, category) if related else None
            except _IncompleteDraft:
                continue
            facts.append(self.bound_plan_facts(plan, table, other, category))
        return facts

    def bound_plan_facts(self, plan, table, other, category):
        if plan.get("rule_type") != "field_compare":
            return None
        bound = _normalize_documented_operands(deepcopy(plan), self.fields[table["id"]], self.fields[other["id"]] if other else [], self.request, self.inputs.get("clarification_answers") or [])
        return plan_facts(bound, table, other, self.fields, category)

    def explicit_review_conditions(self, proposal, default, docs):
        """Retain only comparisons whose field and unitless literal the user actually named."""
        parts = _literal_parts(self.request.lower())
        if len(parts) < 3:
            return []
        labels = {(table["id"], f["field_name"]): tuple(filter(None, (
            f.get("field_cn"), f["field_name"].lower(), *_business_aliases(f))))
            for table in docs for f in self.fields[table["id"]]}
        checks = []
        for fact in self.verified_facts(proposal.get("plans", [proposal]), default):
            rows = [(fact["table"]["id"], p["left"], "", p["right"]) for p in fact["parts"]
                    if p.get("right_type") == "value" and "left" in p]
            rows.extend(fact["filters"])
            for owner, field, op, value in rows:
                names = labels.get((owner, field))
                match = _metric_threshold(parts, names) if names and is_finite_number(value) else None
                if not match or match[2] or match[0] != Decimal(str(value)):
                    continue
                negative, symbol = match[1]
                expected = _FILTER_OPERATORS[symbol]
                if op and op != (_OPPOSITE_FILTER[expected] if negative else expected):
                    continue
                label = next((n for n in names if n.lower() in self.request.lower()), names[0])
                checks.append((owner, field, op, value, label))
        # Only complete lists with an explicit distributive marker assert separate operands.
        # A lone mention, alternative, or a fragment of a longer field name does not.
        for before in parts[:-1:2]:
            comparison = _LITERAL_OPERATOR.search(before)
            if comparison and (group := re.search(r"([^，,。；;：:]+?)(?:分别|各自)$", before[:comparison.start()])):
                names = re.split(r"[、与和及]", group[1])
                owners = [[key for key, aliases in labels.items() if name in aliases] for name in names]
                if len(names) >= 2 and all(len(keys) == 1 for keys in owners):
                    checks.extend((*keys[0], "", None, name) for keys, name in zip(owners, names))
        return checks

    def check_request_conditions(self, facts):
        for owner, field, op, value, label in self.request_conditions:
            if op:
                relevant = [f for f in facts if owner in (f["table"]["id"], (f["related"] or {}).get("id"))]
                if relevant and any((owner, field, op, value) not in f["filters"] or
                                    (owner, field, _OPPOSITE_FILTER[op], value) in f["filters"] for f in relevant):
                    raise _IncompleteDraft(f"请核实{label}的筛选范围，保留需求中的数值 {value} 及其边界。", category="request_condition")
            else:
                operands = [part for f in facts if f["table"]["id"] == owner for part in f["parts"]
                            if part.get("left") == field]
                if not operands or (value is not None and not any(p.get("right") == value for p in operands)):
                    detail = f"与阈值 {value} 的比较" if value is not None else "的独立检查"
                    raise _IncompleteDraft(f"请核实需求中{label}{detail}。", category="request_condition")

    def materialize(self, raw, targets, allowed, existing, *, allow_supplement=True):
        raw = defer_period_metric_choices(self, targets[0], raw, self.owner_choices)
        raw = deepcopy(raw)
        self.preserve_plan_group(raw, targets[0])
        plans = raw.get("plans", [raw])
        if not isinstance(plans, list) or not 1 <= len(plans) <= SEMANTIC_MAX_PLANS or any(not isinstance(p, dict) for p in plans):
            raise _IncompleteDraft(f"plans 需要 1 至 {SEMANTIC_MAX_PLANS} 份独立的规则草稿")
        facts = self.verified_facts(plans, targets[0])
        mode = raw.get("plan_mode", "alternatives")
        if mode not in ("parallel", "alternatives"):
            raise _IncompleteDraft("plan_mode 应为 parallel 或 alternatives")
        group = parse_mixed_group(self.request) or parse_numeric_group(self.request)
        terms = {term for term, _, _ in group[1]} if group else set()
        options = []
        suggestions = [*self.model_suggestions,
                       *(raw["ai_suggestions"] if isinstance(raw.get("ai_suggestions"), list) else [])]
        period_scope = self.inputs.get("period_scope")
        selected_adoption = bool((period_scope or {}).get("variants"))
        materialized_plans = [(i, draft, None) for i, draft in enumerate(plans)]
        if period_scope:
            variants = (period_scope.get("variants") or period_scope.get("checks")
                        or [{"filters": filters} for filters in period_scope["groups"]])
            materialized_plans = [(i, deepcopy(draft), variant) for i, draft in enumerate(plans)
                                  for variant in variants]
        for plan_index, draft, variant in materialized_plans:
            inherited_group = variant["filters"] if variant else None
            check = (variant or {}).get("check")
            selected_scope = variant if selected_adoption else None
            default = targets[0]
            target = draft.get("target", default.get("target", default))
            category_code = draft.get("report_category", default.get("report_category"))
            if selected_scope and isinstance(target, dict) and target.get("table") == selected_scope["table"]:
                category_code = selected_scope.get("report_category") or category_code
            table = self.resolve(target, category_code)
            related_target = draft.get("related_target", default.get("related_target") if target == default.get("target") else None)
            inherited_date = None
            if selected_scope and draft.get("rule_type"):
                related_target = bind_adopted_join(draft, table["table_name"], related_target, period_scope, selected_scope)
                if table["table_name"] == selected_scope["table"]:
                    inherited_date = selected_scope.get("report_date_field")
                    if selected_scope.get("business_key"):
                        draft["business_key"] = selected_scope["business_key"]
                elif selected_scope.get("join"):
                    inherited_date = selected_scope["join"]["report_date_field"]
            related = self.resolve(related_target, category_code) if related_target else None
            adopted_tables = ((selected_scope or {}).get("table"), (selected_scope or {}).get("join", {}).get("table_name"))
            if table["id"] not in allowed or related and (related["id"] == table["id"] or
                    related["id"] not in allowed and related["table_name"] not in adopted_tables):
                raise _IncompleteDraft("方案只能采用本轮已提供完整字段的独立主表及关联表")
            fields = self.fields[table["id"]]
            other = self.fields[related["id"]] if related else []
            _normalize_documented_operands(draft, fields, other, self.request, self.inputs.get("clarification_answers") or [])
            if draft.get("rule_type") == "field_compare" and isinstance(draft.get("semantic_intent"), dict):
                check_field = period_scope["fields"][0] if check else None
                if selected_scope and selected_scope.get("period_checks"):
                    used = referenced_fields({"expression": draft.get("expression")})["base"]
                    if len(used) == 1:
                        check_field = next(iter(used))
                        check = selected_scope["period_checks"].get(check_field)
                if check:
                    label = next((f["field_cn"] for f in fields if f["field_name"] == check_field and f.get("field_cn")), check_field)
                    apply_period_check(draft, check, check_field, label)
            bind_shared_measure(draft, fields, self.request)
            if selected_scope:
                reconcile_confirmed_scope_partitions(draft, table["table_name"], (related or {}).get("table_name"),
                                                     period_scope, inherited_group, fields, other)
            try:
                _validate_intent(draft, fields, other)
            except _IncompleteDraft as exc:
                if exc.path and "plans" in raw:
                    exc.path = ("plans", plan_index, *exc.path)
                raise
            judgment = model_judgment(draft, stage="generate_rule")
            if draft.get("rule_type") is None:
                issues = list(draft["semantic_intent"]["open_questions"])
                judgments = {**self.context["model_judgments"], "generate_rule": judgment}
                if len(plans) == 1:
                    return self.clarify(issues, judgment["unsupported_requirements"], table_name=table["table_name"],
                                        report_category=category_code, model_suggestions=suggestions,
                                        semantic_intent=semantic_intent_snapshot(draft["semantic_intent"]), model_judgments=judgments)
                candidate = clarification_candidate(issues, judgment["unsupported_requirements"], **self.context,
                                                     table_name=table["table_name"], semantic_intent=semantic_intent_snapshot(draft["semantic_intent"]))
                candidate["model_judgments"] = judgments
                candidate["parallel_blocked"] = "该项仍需补充校验条件"
            else:
                join = draft.get("join")
                if (related is None) != (join is None) or related and (
                        not isinstance(join, dict) or join.get("table_name") != related["table_name"]):
                    raise _IncompleteDraft("关联表、join.table_name 与文档对象必须一致")
                if inherited_group is not None:
                    inherited = bind_period_filters(draft, table["table_name"], (related or {}).get("table_name"),
                                                    period_scope, inherited_group)
                candidate = self.candidate(draft, table, category_code, fields, other, existing, judgment,
                                           inherited_date=inherited_date)
                if check:
                    candidate.pop("null_handling", None)
                    candidate.update(deepcopy(check))
                    candidate["semantic_intent"]["expected_null_policy"] = check["null_policy"]
                    candidate["semantic_intent"]["inherited_period_check"] = deepcopy(check)
                if inherited_group is not None:
                    verify_bound_period_filters(candidate, inherited, period_scope["groups"])
                if selected_scope:
                    verify_adopted_goal(candidate, table["table_name"], (related or {}).get("table_name"), period_scope)
                    adopted_join = draft.get("join") if selected_scope.get("join") else None
                    if (inherited_date and candidate.get("report_date_field") != inherited_date
                            or adopted_join and not adopted_join_matches(candidate.get("join"), adopted_join, inherited_date)):
                        raise ScopeEvidenceRequired("补充建议需要保留已选方案的日期及缺少关联记录时的处理口径。")
                    candidate["semantic_intent"]["inherited_adoption_scope"] = {
                        **({"report_date_field": inherited_date} if inherited_date else {}),
                        **({"unmatched_policy": adopted_join["unmatched_policy"]} if adopted_join else {}),
                    }
                    suffix = adopted_scope_label(inherited_group, period_scope["groups"], table["table_name"],
                                                 (related or {}).get("table_name"), fields, other)
                    name_adopted_scope(candidate, suffix)
                # Independent parallel rules may cover different named metrics. A range
                # on a single metric still needs both ends in every interpretation.
                if (terms and (len(terms) == 1 or mode != "parallel" or len(plans) == 1)
                        and not candidate.get("questions") and not candidate.get("uncertainties")):
                    labels = {name for field in fields for name in (field["field_name"], field.get("field_cn"))}
                    if terms <= labels:
                        issue = _check_numeric_requirement(candidate, {"base": fields, "related": other},
                                                           self.request, None, candidate.get("filters") or [])
                        if issue:
                            raise _IncompleteDraft(issue, category="request_condition")
            if mode == "parallel":
                candidate["parallel_check"] = True
            if draft is not raw and isinstance(draft.get("ai_suggestions"), list):
                suggestions.extend(draft["ai_suggestions"])
            label = str(table.get("table_name_cn") or table["table_name"])
            metrics = draft["semantic_intent"]["metrics"]
            field = "、".join(dict.fromkeys(item["term"] for item in metrics))
            candidate.update(document_display(table, related))
            grain = candidate["grain"]
            if selected_adoption:
                signature = json.dumps([candidate_definition(candidate), candidate.get("questions") or []],
                                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            else:
                signature = _json([candidate.get("report_category"), candidate.get("expression"), candidate.get("filters"),
                                   candidate.get("join"), candidate.get("project_driver"), candidate["semantic_intent"]])
            options.append({"id": option_id(self.context["source_id"], table["table_name"], field, self.request,
                                            self.context["doc_sha256"], signature),
                            "label": candidate.get("rule_name") or label, "table_label": label, "field_label": field,
                            "grain": grain, "recommended": draft.get("recommended") is True,
                            "differences": difference_lines(label, grain, field),
                            "match_reason": str(draft.get("match_reason") or "")[:240], "candidate": candidate})
        if selected_adoption:
            distinguish_adopted_scopes(options)
        elif len({o["id"] for o in options}) != len(options):
            raise _IncompleteDraft("请合并完全相同的方案，仅保留具有独立业务含义的方案")
        candidates = [o["candidate"] for o in options]
        if self.request_conditions and all(c.get("rule_type") and not c.get("uncertainties") and
                                           not c.get("questions") for c in candidates):
            self.check_request_conditions(facts)
        verify_grain_facts(self, facts)
        self.preview_after_all_reviews(candidates)
        ready_definitions, pending_ids, retained_options = set(), set(), []
        for option in options:
            candidate = option["candidate"]
            preview = candidate.get("preview")
            if preview and not any(candidate.get(key) for key in ("questions", "uncertainties", "unsupported_requirements")):
                signature = _execution_signature(preview["definition"])
                if signature in ready_definitions:
                    if not selected_adoption:
                        raise _IncompleteDraft("请合并执行条件和业务范围完全相同的方案，仅保留独立校验")
                    continue
                ready_definitions.add(signature)
            elif selected_adoption:
                if option["id"] in pending_ids:
                    continue
                pending_ids.add(option["id"])
            retained_options.append(option)
        options = retained_options
        candidates = [o["candidate"] for o in options]
        primary = dict(next((c for c in candidates if c.get("rule_type")), candidates[0]))
        if len(options) > 1:
            primary["candidate_options"] = options
            primary["comparison_suggestions"] = []
        def validate_suggestions(items):
            verified = build_ai_suggestions(
                items, tables=self.inputs["tables"], fields_by_table=self.fields, candidates=candidates,
                request_text=self.request,
                existing_rules=existing, actionable_only=True, model_only=True, limit=MAX_SUGGESTIONS,
                select_category_tables=lambda tables, codes: self.service._category_tables(tables, codes, self.categories),
                default_business_scope=self.prompts["business_scope"] == DEFAULT_PROMPTS["business_scope"],
            )

            return attach_period_applicability(verified, self.prompts["business_scope"], self.inputs["context"]["source_id"],
                                               self.inputs["tables"], self.fields)

        include_suggestions = self.inputs.get("include_suggestions", True)
        primary["ai_suggestions"] = validate_suggestions(suggestions) if include_suggestions else []
        suggestion_candidates = [c for c in candidates if c.get("rule_type") and c.get("columns")]
        if include_suggestions and allow_supplement and suggestion_candidates:
            supplemental = self.supplement_suggestions(suggestion_candidates, primary["ai_suggestions"])
            self.model_suggestions = deepcopy(supplemental or [])
            primary["ai_suggestions"] = validate_suggestions(self.model_suggestions)
            raw["ai_suggestions"] = self.model_suggestions
            _discard_cached_plan_suggestion_copies(raw)
            if supplemental:
                refreshed = defer_period_metric_choices(self, targets[0], raw, self.owner_choices)
                if refreshed is not raw:
                    return self.materialize(refreshed, targets, allowed, existing, allow_supplement=False)
            if supplemental is None or (supplemental and not primary["ai_suggestions"]):
                primary["ai_suggestions_status"] = "incomplete"
                for card in [primary, *candidates]:
                    card["notices"] = merge(card.get("notices") or [], ["本次补充建议未完成，可重新分析以获取建议。"])
        for suggestion in primary["ai_suggestions"]:
            definition = suggestion.get("definition")
            if definition:
                # A supplemental check has its own expression, independent of the primary request.
                definition.update(analysis_protocol=2, semantic_intent={
                    "metrics": [], "scopes": [], "open_questions": [],
                    "expected_expression": definition["expression"], "explicit_filters": definition.get("filters", []),
                    "expected_join": definition.get("join") or {},
                })
                category = definition.get("report_category") or primary.get("report_category")
                try:
                    owner = self.resolve({"table": definition.get("table_name")}, category)
                except _IncompleteDraft:
                    definition.setdefault("uncertainties", []).append("补充规则的文档表尚未唯一确定，请重新分析该建议。")
                else:
                    resolution = self.service._bind_new_project_driver(
                        definition, owner, self.fields[owner["id"]], self.tables, self.fields,
                    )
                    if resolution:
                        definition["uncertainties"] = merge(definition.get("uncertainties") or [], resolution[1])
        pending = any(not c.get("preview") for c in candidates)
        self.service._emit_progress(self.progress, "generation", "needs_confirmation" if pending else "completed",
                                    "规则草稿仍需确认" if pending else "已完成规则草稿核实")
        return primary

    def supplement_suggestions(self, candidates, previous=()):
        scope = self.prompts["business_scope"]
        defaults = set(DEFAULT_PROMPTS["business_scope"].splitlines())
        paragraphs = [(p, p.split("。", 1)[0]) for p in scope.splitlines() if p.strip() and p not in defaults]
        supplemental_policy = re.compile(r"补充|建议|另(?:需|可|应|行|提|核|查)|独立(?:核对|检查|比较|核查)")
        for line in self.inputs.get("knowledge_prefix", "").splitlines():
            if line.startswith("{"):
                document = json.loads(line)
                for entry in document.get("条目", []):
                    summary = entry["summary"]
                    pieces = ([summary] if supplemental_policy.search(summary)
                              else [s for s in re.split(r"(?<=[。！？])", summary) if s.strip()])
                    paragraphs.extend((entry["topic"] + "：" + s, s.split("。", 1)[0]) for s in pieces)
        policy = [(p, anchor, set(re.findall(r"[a-z_][a-z0-9_]*", p.lower()))) for p, anchor in paragraphs]

        def mentions(column, line, identifiers):
            label = (column.get("field_cn") or column.get("comment") or "").lower()
            return (column["column_name"].lower() in identifiers
                    or any(len(name) >= 2 and name in line.lower() for name in (label, *_business_aliases(column))))

        summaries = []
        seen_evidence = set()
        relevant = {}
        previous_refs = {(ref["table_name"], ref["field_name"]) for item in previous for ref in item["references"]}
        for candidate in candidates:
            summary = {key: candidate[key] for key in ("rule_name", "table_name", "table_name_cn", "report_category",
                       "report_category_name", "grain", "expression",
                       "filters", "business_key", "report_date_field", "join", "project_driver",
                       "null_policy", "null_handling", "equality_policy") if candidate.get(key)}
            summary["covered_behaviors"] = {
                "missing_detail_records": bool(candidate.get("join")
                                               and (candidate.get("project_driver") or {}).get("version") in (1, 2)),
            }
            metrics = (candidate.get("semantic_intent") or {}).get("metrics") or []
            summary["main_metric_bindings"] = [{k: m[k] for k in ("condition_index", "side", "formula_path", "term", "fields")
                                                if k in m} for m in metrics if isinstance(m, dict)]
            scopes = (candidate.get("semantic_intent") or {}).get("scopes") or []
            summary["main_scope_bindings"] = scopes
            refs = referenced_fields(candidate)
            refs["base"].add(candidate.get("report_date_field"))
            main = referenced_fields({"expression": candidate.get("expression"), "semantic_intent": {"metrics": metrics}})
            summary["references"] = []
            for role, table, columns in (("base", candidate["table_name"], candidate["columns"]),
                    ("related", (candidate.get("join") or {}).get("table_name"), candidate.get("related_columns") or [])):
                if not table:
                    continue
                measured = [c for c in columns if c["column_name"] in main[role]]
                policies = [(p, ids) for p, anchor, ids in policy if any(mentions(c, anchor, ids) for c in measured)]
                relevant.update(dict.fromkeys(p[0] for p in policies))
                evidence_clauses = [(sentence, set(re.findall(r"[a-z_][a-z0-9_]*", sentence.lower())))
                                    for p, _ in policies for sentence in p.split("。") if supplemental_policy.search(sentence)]
                for col in columns:
                    name = col["column_name"]
                    ref = {"table_name": table, "field_name": name, "label": col.get("field_cn") or col.get("comment", "")}
                    key = (candidate.get("report_category"), table, name)
                    if name in refs[role]:
                        if key not in seen_evidence and name in main[role]:
                            ref.update({k: col[k] for k in ("data_type", "source_field", "source_field_cn") if col.get(k)})
                            if col.get("logic"):
                                ref["logic"] = col["logic"].split("\n\n", 1)[0]
                            seen_evidence.add(key)
                        if col.get("dictionary") and any(s.get("table", "base") == role and name in s.get("fields", [])
                                                         for s in scopes):
                            ref["dictionary"] = col["dictionary"]
                        summary["references"].append(ref)
                    elif key not in seen_evidence and ((table, name) in previous_refs
                                                       or any(mentions(col, *clause) for clause in evidence_clauses)):
                        fact = {k: col[k] for k in ("data_type", "logic", "source_field_cn") if col.get(k)}
                        summary.setdefault("policy_field_evidence", []).append({**ref, **fact})
                        seen_evidence.add(key)
            summaries.append(summary)
        # Matching a document name retrieves evidence. Only an explicit supplemental policy,
        # an actual prior suggestion or distinct main target tables requests another model turn.
        declared = any(supplemental_policy.search(p) for p in relevant)
        comparison_complete = all((c.get("join") or {}).get("right_aggregate") for c in candidates)
        if not previous and (comparison_complete or not declared and len({c["table_name"] for c in candidates}) < 2):
            return []
        if self.round_number >= MAX_MODEL_ROUNDS or self.output_tokens_used >= SEMANTIC_TOTAL_OUTPUT_TOKENS:
            return None
        prior = [{k: s[k] for k in ("category", "kind", "title", "reason", "operations", "references", "preconditions",
                                     "limitations") if k in s} for s in previous]
        prompt = ("当前数据来源：" + _json(self.inputs["source"]["name"]) +
                  "。\n本轮只提出独立补充校验建议。按当前来源、报送分类及原文，逐项核对适用的已确认业务口径与启用知识，"
                  "并用活动文档实际字段核实。输出最终完整清单；初步建议可能有错误，逐项纠正比较方向、类型和前提，"
                  "删除与已确认口径矛盾的项，补齐本次适用且主案未覆盖的已确认独立建议，不可返回空清单。"
                  "main_metric_bindings.fields 中每个备选都已属于主方案，expression仅展示该方案当前绑定；"
                  "只把实际列入主案的口径计作已覆盖。主案漏列的可选指标不取代已确认的独立建议。"
                  "已覆盖的选项或covered_behaviors不重复建议。policy_field_evidence是相关口径引用的其他文档字段，"
                  "若当前主规则本身就是某段知识要求的补充项，该项已被主规则覆盖，不得再次建议；"
                  "先核对该段要求的主规则触发范围与当前实际范围，不能只看到‘应提出建议’便照抄。"
                  "仅当口径和本次业务范围确实适用时采用，字段存在本身不能推出校验。"
                  "明确要求在另一适用期间独立检查单一指标时，给可采纳的category=period建议，kind按原检查选择；"
                  "references只填该项被检查的字段，期间依据和适用范围写reason，继承原谓词、阈值、异常方向与空值口径。"
                  "反向分类只能依已确认口径确定异常方向，不把状态取反机械地换成另一比较符。"
                  "某状态下字段与常量比较采用field_compare_binary；只有实际跨粒度汇总才用aggregate_consistency。"
                  "field_compare_unary仅用于IS NULL或IS NOT NULL；上下限、区间等数值比较即使只涉及一个字段也用field_compare_binary。"
                  "口径明确要求跨粒度核对时保留比较双方、汇总方法、范围与容差，主方案分别与常量比较未覆盖双方一致性。"
                  "不从多个同表备选推导求和，普通数值缺失不构成缺明细；仅在有应有明细的业务范围依据时才建议缺记录检查。"
                  "不自行提出项目编号为空或重复项目检查。"
                  '只输出 {"ai_suggestions":[...]}；只有与本次无关、主案已完整覆盖或依据不足时可为空，'
                  '此时用no_suggestion_reason说明具体业务对象、条件和原因。每项须满足以下JSON结构：'
                  "\ncategory为以下枚举之一：" + _json(CATEGORIES) + "；kind为以下枚举之一：" + _json(KINDS) +
                  '。title与reason是简短中文字符串。跨粒度汇总一致性采用category="consistency"、kind="aggregate_consistency"。'
                  'operations是实际运算的字符串数组，求和为"operations":["sum"]，不涉及汇总可省略。'
                  f'references为1至{MAX_REFERENCES}个真实字段对象（至多{MAX_REFERENCES}个），每个只有table_name、field_name两个字符串。'
                  "优先引用直接比较的两侧指标；日期、关联键与范围在reason说明。preconditions和limitations必须是字符串数组，"
                  "没有用[]；只有尚未确定的业务前提写preconditions，不填写结构化筛选对象或已确认事实。"
                  "已在下方口径明确的阈值、容差、单位、范围或字段均不得重问。无需输出主规则、方案或SQL。"
                  "\n用户原文：" + _json(self.request)
                  + "\n匹配本次指标的业务口径与启用知识（参考数据）： " + _json(list(relevant))
                  + "\n主规则阶段的待审建议：" + _json(prior)
                  + "\n主规则及文档依据：" + _json(summaries))
        try:
            reply = self.call(prompt, "supplement_suggestions")
            if not reply["ai_suggestions"] and (previous or declared):
                reason = reply.get("no_suggestion_reason")
                if not isinstance(reason, str) or not reason.strip():
                    return None
            return reply["ai_suggestions"]
        except AppError as exc:
            if exc.code in {"ANALYSIS_TIMEOUT", "ANALYSIS_OUTPUT_LIMIT"}:
                raise
            LOGGER.info("Optional suggestions unavailable analysis=%s code=%s", self.analysis_id, exc.code)
            return None

    def preview_after_all_reviews(self, candidates):
        """Finish every candidate's document review before compiling SQL for any of them."""
        prepared = []
        for candidate in candidates:
            candidate.update(preview=None, can_enable=False)
            if candidate.get("rule_type") is None or candidate.get("preview_error"):
                continue
            payload = {**candidate, "name": candidate.get("rule_name") or candidate["table_name"]}
            review = self.service.preview_candidate(self.user, payload, return_questions=True, validate_only=True)
            if review.get("status") == "needs_confirmation":
                candidate["questions"] = review["questions"]
                candidate["uncertainties"] = review["uncertainties"]
                candidate["uncertainty_resolutions"] = [""] * len(review["uncertainties"])
            else:
                prepared.append(review)
        if len(prepared) == len(candidates):
            for candidate, review in zip(candidates, prepared):
                self.service._apply_candidate_preview(candidate, compile_prepared_preview(review))

    def candidate(self, draft, table, category_code, fields, other, existing, judgment, *, inherited_date=None):
        filters = draft.get("filters")
        if isinstance(filters, list) and any(isinstance(item, dict) and item.get("op") in ("regexp", "not_regexp") for item in filters):
            raise ScopeEvidenceRequired("当前支持按文字关键词包含或排除记录；该条件包含正则表达式，请明确需要匹配的文字。")
        columns = self.service._doc_columns(fields)
        related_columns = self.service._doc_columns(other)
        # SQL and legacy field guesses are never accepted; execution choices are bound to real fields below.
        model_fields = {k: draft[k] for k in ("rule_name", "rule_type", "expression", "violation_message", "null_policy",
                                               "equality_policy", "unsupported_requirements", "project_driver") if k in draft}
        model_fields["expression"] = model_expression(model_fields["expression"])
        candidate = refine_candidate(model_fields, columns=columns, related_columns=related_columns,
                                     dialect=self.context["dialect"], existing=existing,
                                     source_id=self.context["source_id"], table_name=table["table_name"])
        if "project_driver" in model_fields:
            candidate["project_driver"] = deepcopy(model_fields["project_driver"])
        scope = self.service._doc_category_scope(table, self.categories)
        category = document_category(scope, self.categories)
        if scope and scope <= (PBC_REPORT_CATEGORIES | {PBC_SHARED_CATEGORY}):
            category = {"code": PBC_SHARED_CATEGORY, "name": PBC_SHARED_CATEGORY_NAME}
        if not category and category_code:
            if category_code in PBC_REPORT_CATEGORIES:
                category_code = PBC_SHARED_CATEGORY
            category = self.service._doc_category(self.categories, category_code)
            if not category or scope and category["code"] not in scope:
                raise _IncompleteDraft("报送分类需对应目标表的文档归属")
        category = category or {"code": "", "name": "未分类"}
        candidate.update(self.context, description=self.request, table_name=table["table_name"],
                         report_category=category["code"], report_category_name=category["name"],
                         columns=columns, related_columns=related_columns, generation_mode="ai",
                         scope_description=str(table.get("table_name_cn") or table["table_name"]),
                         mapping_version=f"doc-v{self.context['doc_version']}-{self.context['doc_sha256'][:12]}",
                         model_judgments={**self.context["model_judgments"], "generate_rule": judgment}, notices=[])
        if inherited_date:
            candidate["report_date_field"] = inherited_date
        related_table = next((t for t in self.tables if t["table_name"] == (draft.get("join") or {}).get("table_name")
                              and self.fields.get(t["id"]) == other), None) if other else None
        candidate.update(document_display(table, related_table))
        ground_semantic_candidate(candidate, draft, fields, other)
        if "semantic_intent" not in candidate:
            # Locate a bad partition only after grounding failed, without re-parsing valid dictionaries on success.
            roles = _roles(fields, other)
            for index, scope in enumerate(draft["semantic_intent"]["scopes"]):
                try:
                    _scope_options(scope, roles, {})
                except _Unbound as exc:
                    raise _IncompleteDraft(str(exc), ("semantic_intent", "scopes", index, "memberships"),
                                           category="dictionary_partition") from exc
            raise _IncompleteDraft(candidate.get("preview_error") or "无法核实所声明的字段或完整字典分组")
        candidate["semantic_intent"].update(semantic_intent_snapshot(draft["semantic_intent"]))
        policy = draft.get("null_policy") or "unresolved"
        if not is_unary(candidate):
            numeric = is_numeric_comparison(candidate, {f["field_name"]: f.get("data_type") for f in fields},
                                            {f["field_name"]: f.get("data_type") for f in other})
            if numeric and any(q["id"].startswith("expression.") for q in candidate["questions"]):
                # A document-derived zero for the suggested field must not become the model's choice for its peers.
                candidate["semantic_intent"]["expected_null_policy"] = policy
            if policy == "empty_string_as_null" or (policy == "violate" and not numeric and not is_condition_group(candidate)):
                candidate["unsupported_requirements"] = merge(candidate["unsupported_requirements"],
                                                             ["所声明的空值策略不适用于当前比较条件。"])
            candidate = apply_numeric_null_policy({**candidate, "null_policy": policy}, columns, related_columns)
        expression = candidate["expression"]
        numeric_fields = {f["field_name"] for f in fields if type_family(f.get("data_type")) == "number"}
        if any(part.get("op") in ("contains_any", "not_contains_any") and part.get("left") in numeric_fields
               for part in expression.get("conditions", [expression])):
            candidate["notices"] = merge(candidate.get("notices") or [], [
                "检查字段文档为数值型，字符条件按数据库转换后的文本执行；数值类型本身限制可入库内容，如需核查原始文本请使用对应文本字段。"])
        implied = ("reject_equal" if expression.get("op") in ("eq", "lte", "gte")
                   and expression.get("right_type") != "value" else "allow_equal")
        # Equality is already determined by the executable operator. A redundant
        # model metadata mismatch is not a new business question for the user.
        candidate["equality_policy"] = implied
        if candidate.get("null_policy") == "unresolved":
            candidate["questions"].append(self.service._null_policy_question())
        if has_arithmetic(expression) and "project_driver" in candidate:
            # For a new formula the document establishes whether its base holds the project or its detail.
            # Keep the marked path strict if the unmarked document binding cannot prove a role.
            probe = deepcopy(candidate)
            probe.pop("project_driver")
            resolution = self.service._bind_new_project_driver(probe, table, fields, self.tables, self.fields)
            if resolution and not resolution[1] and not probe.get("unsupported_requirements") and probe.get("project_driver"):
                candidate["project_driver"] = probe["project_driver"]
        notes = self.service._document_candidate_details(candidate, table, fields, self.inputs["tables"], self.fields,
                                                         model_business_key=draft.get("business_key"))
        candidate["uncertainties"] = merge(candidate["uncertainties"], notes)
        candidate["uncertainty_resolutions"] = [""] * len(candidate["uncertainties"])
        return candidate
