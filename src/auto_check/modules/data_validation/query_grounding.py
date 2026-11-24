"""Document-backed choices for bounded query scopes. Never infer a status code from convention."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .business_display import (
    join_relationship_description, join_relationship_label, join_unmatched_option, join_unmatched_question, table_label,
)
from .conditional_reviews import (
    bind_document_metric_questions, bind_verified_null_fields, category_numeric_check, conditional_null_check,
    metric_choices, plain_null_check, reconcile_field_choices,
)
from .model_calls import failure
from .parallel_checks import (
    NONEMPTY_REQUIREMENT, number_comparison_prefix, parse_mixed_group, parse_number_comparison, parse_numeric_group,
)
from .project_context import project_code_fields
from .query_spec import base_type, type_family

# 期间口径的明确语义；事件/发生/采集时间不得当作可按期校验的业务日期。
PERIOD_DATE_COMMENTS = re.compile(
    r"(?:数据|业务|报送|报告|统计|余额|会计|核算|账务|帐务)日期"
    r"|(?:期末|期初|日终|月结)日期?",
)
EVENT_DATE_COMMENTS = re.compile(
    r"开始|生效|成立|签发|签订|发生|到期|结束|截止|创建|更新|录入|采集|同步|提交"
    r"|起息|结息|放款|还款|销户|开业|注销|计划|预计|审批|复核|记账|入账",
)


def _field_name(field: dict[str, Any]) -> str:
    return str(field.get("field_name") or field.get("column_name") or "")


def _field_comment(field: dict[str, Any]) -> str:
    return str(field.get("field_cn") or field.get("comment") or "")


def is_period_date_field(field: dict[str, Any]) -> bool:
    """严格 DATE 且注释明确为期间口径，并排除事件/处理时间语义。"""
    if base_type(field.get("data_type")) != "date":
        return False
    comment = _field_comment(field).strip()
    return bool(comment) and bool(PERIOD_DATE_COMMENTS.search(comment)) and not EVENT_DATE_COMMENTS.search(comment)


def resolve_report_date(fields: list[dict[str, Any]], explicit: Any = "") -> tuple[str, list[dict[str, Any]]]:
    """按真实文档列确定校验日期字段。

    显式合法值（调用方已确认且仍是 DATE）保持不变；否则仅当恰好一个高可信
    期间列时自动采用。多个合理候选、仅有事件日期或没有证据时返回空值，由
    调用方保留人工问题。不依赖字段/表名硬编码，也不信任模型或客户端元数据。
    """
    wanted = str(explicit or "")
    date_fields = [field for field in fields if base_type(field.get("data_type")) == "date"]
    preferred = [field for field in date_fields if PERIOD_DATE_COMMENTS.search(_field_comment(field))]
    ordered = preferred + [field for field in date_fields if field not in preferred]
    if wanted and any(_field_name(field) == wanted for field in date_fields):
        return wanted, ordered
    confident = [field for field in date_fields if is_period_date_field(field)]
    if len(confident) == 1:
        return _field_name(confident[0]), ordered
    return "", ordered


def dictionary_options(field: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse explicit code-label lines; dictionary ids/headings are not values."""
    result: list[dict[str, Any]] = []
    kind = str(field.get("data_type") or "").lower().split("(", 1)[0].strip()
    integer = kind in {"int", "integer", "smallint", "bigint", "tinyint", "mediumint"}
    numeric = integer or kind in {"numeric", "decimal", "float", "double", "real"}
    for line in re.split(r"[\r\n;；]+", str(field.get("dictionary") or "")):
        match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?|[^\s:：=—\-]{1,80})\s*[-—:：=]\s*(.{1,200})\s*", line)
        if not match or match[1] in {"原编号", "字典", "备注", "说明"}:
            continue
        value: Any = match[1]
        if numeric:
            try:
                value = int(value) if integer else float(value)
            except ValueError:
                continue
            if isinstance(value, float) and not math.isfinite(value):
                continue
        option = {"value": value, "label": match[2].strip()}
        if option not in result:
            result.append(option)
    return result[:100]


def date_options(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _, ordered = resolve_report_date(fields)
    return [{"value": _field_name(field), "label": f"{_field_comment(field) or '日期字段'}（{_field_name(field)}）",
             "description": "用于按同一业务日期校验，不是项目发生日期或采集时间。"} for field in ordered]


def project_mart_target(source_name: str, tables: list[dict[str, Any]], request: str) -> dict[str, Any] | None:
    """The user-defined base table for project-grain requests in the reporting mart."""
    if source_name != "监管报送集市":
        return None
    explicit_project = re.search(r"项目维度|项目级|按项目|项目信息表|\breg_pub_project_info\b", request, re.I)
    project_subject = re.search(r"(?:存续|未完结)(?:的)?(?:信托)?项目|项目(?:的|状态|是否|编号|名称|开始日|结束日|实收)|项目[，,：:]", request)
    other_grain = re.search(r"合同|协议|账户|交易|资产明细|产品维度|产品级|按产品", request)
    if not explicit_project and (not project_subject or other_grain):
        return None
    return next((table for table in tables if table.get("table_name") == "reg_pub_project_info"), None)


def field_profiles(tables: list[dict[str, Any]], fields_by_table: dict[int, list[dict[str, Any]]], request: str) -> str:
    """Small selector hints permit single-table planning without sending whole documents."""
    from .generation_policy import text_tokens
    wanted = text_tokens(request[:4000])
    project_state = bool(_PROJECT_STATE_TERMS.search(request))
    lines = []
    verified_lines = []
    remaining_budget = 16000
    for table in tables:
        ranked = []
        fields = fields_by_table.get(int(table["id"]), [])
        check = conditional_null_check(request, fields, dictionary_options, dimension=str(table.get("dimension") or ""))
        numeric = category_numeric_check(request, fields, dictionary_options, dimension=str(table.get("dimension") or ""))
        if numeric:
            check = numeric.scope
        if check:
            for field_name, entries in check.dictionary_entries.items():
                mapping = "、".join(f"{item['value']}={item['label']}" for item in entries)
                fact = f"完整字典映射：{table['table_name']}.{field_name} 中“{check.label}”的全部码值为 {mapping}。"
                if len(fact) + 1 <= remaining_budget:
                    verified_lines.append(fact)
                    remaining_budget -= len(fact) + 1
        scoped_values = {item["field"]: item["value"] if item["op"] == "in" else [item["value"]]
                         for item in check.selections} if check else {}
        for position, field in enumerate(fields):
            label = f"{field.get('field_name') or ''} {field.get('field_cn') or ''}"
            dictionary = str(field.get("dictionary") or "")
            score = sum(len(token) for token in wanted if token in label)
            score += sum(2 * len(token) for token in wanted if token in dictionary)
            entries = dictionary_options(field) if project_state else []
            status_evidence = any(_ACTIVE_STATUS_LABEL.fullmatch(item["label"]) for item in entries)
            scoped = field.get("field_name") in scoped_values
            if score or status_evidence or scoped:
                ranked.append((not (scoped or status_evidence), -score, position, field))
        hints = []
        for _status_rank, _score, _position, field in sorted(ranked, key=lambda item: item[:3])[:4]:
            entries = dictionary_options(field)
            selected_values = scoped_values.get(field["field_name"], [])
            labels = [f"{item['value']}={item['label']}" for item in entries
                      if item["value"] in selected_values or item["label"] in request
                      or (project_state and _ACTIVE_STATUS_LABEL.fullmatch(item["label"]))][:3]
            hints.append(f"{field['field_name']}:{str(field.get('field_cn') or '')[:40]}" + ("[" + ",".join(labels) + "]" if labels else ""))
        if hints:
            lines.append(f"{table['table_name']}|" + " / ".join(hints))
    return "\n".join([*verified_lines, *lines])[:16000]


_ACTIVE_SCOPE_REVIEW = "请确认存续范围的状态字段与状态码"
_SCOPE_REVIEW_PART = re.compile(r"状态|字典|代码|取值|存续(?:范围|口径)|筛选口径|如何判定|如何界定|定义")
_FILTER_WORD = re.compile(r"筛选|过滤|判定|识别")
_CHOICE_WORD = re.compile(r"哪(?:一)?(?:个|列|项|种|套|字段)|用哪|按哪|如何|怎么|(?:尚?未|无法|需要?|待|请)确认")
_INDEPENDENT_REVIEW_PART = re.compile(
    r"关联|联接|匹配|日期|期间|时点|截止|跨期|币种|单位|汇总|聚合|例外|除外|排除|粒度|另[一有]|其他|额外"
)
_REVIEW_SPLIT = re.compile(
    r"[；;。\n，,]|(?:以及|并且|同时|另需|与|和)\s*(?=(?:还|需|待|请|未|无法|确认|核对|确定)*"
    r"(?:关联|日期|业务日期|截止日期))",
)


def _bind_active_scope_review(uncertainties: list[str], *, requires_choice: bool) -> None:
    # 合并选表、生成和系统对存续口径的重复提问，保留独立事项。
    remaining = []
    for issue in uncertainties:
        parts = [part.strip() for part in _REVIEW_SPLIT.split(issue) if part.strip()]
        kept = [part for part in parts if not (
            "存续" in part and not _INDEPENDENT_REVIEW_PART.search(part)
            and (_SCOPE_REVIEW_PART.search(part) or (_FILTER_WORD.search(part) and _CHOICE_WORD.search(part)))
        )]
        if len(kept) == len(parts):
            remaining.append(issue)
        elif kept:
            remaining.append("；".join(kept))
    if requires_choice:
        remaining.insert(0, _ACTIVE_SCOPE_REVIEW)
    uncertainties[:] = list(dict.fromkeys(remaining))


_ACTIVE_STATUS_LABEL = re.compile(r"存续(?:\s*[（(]\s*未完结\s*[）)])?|未完结")
_ACTIVE_SCOPE_LABEL = re.compile(r"(?:仍)?(?:存续|未完结)")
_PROJECT_STATE_TERMS = re.compile(r"项目状态|是否(?:仍|已|尚)?(?:存续|未完结|完结)|未完结|存续")
_SCOPE_LABEL = r"(?P<label>[\u4e00-\u9fff]{2,30}?)(?:的)?"
_ENTITIES = "项目|产品|合同|客户|记录|账户|资产"
_LEADING_SCOPE = re.compile(
    r"^请?(?:仅|只)?(?:检查|校验|核查|对)?(?:全部|所有)?"
    + _SCOPE_LABEL + rf"(?P<entity>{_ENTITIES})"
)
_CLAUSE_BREAK = re.compile(r"[，,；;。]|而且|并且|且|同时")
_ONLY_PREFIX = r"(?:但)?(?:仅限于?|限于|(?:仅|只)(?:检查|核查|校验|纳入|包括|针对))"
_ONLY_SCOPE = re.compile(_ONLY_PREFIX + _SCOPE_LABEL + rf"(?P<entity>{_ENTITIES}|状态)")
_RESTRICTED = re.compile(_ONLY_PREFIX + r"|(?:但)?不(?:检查|核查|校验|纳入)")
_ALL_STATES = re.compile(
    r"(?:(?:所有|全部|各种|各类)状态(?:均|都|全部)?(?:纳入|检查|核查|校验|覆盖|包括)?"
    r"|不限状态|不限制状态|状态不限|不区分状态)"
)
_LIMITING_QUALIFIER = re.compile(r"当期|本期|上期|上一期|期初|期末|当月|本月|上月|截至|存续|终止|结束|清算|完结|复核")
_FILTER_OPERATORS = {
    "eq": ("等于", r"等于|为|[=:：]"), "neq": ("不等于", r"不等于|不为|!=|<>|≠"),
    "lt": ("小于", r"小于|<(?![>=])"), "lte": ("小于或等于", r"小于或等于|不大于|<=|≤"),
    "gt": ("大于", r"大于|>(?!=)"), "gte": ("大于或等于", r"大于或等于|不小于|>=|≥"),
    "in": ("属于", r"属于|(?i:IN)"), "not_in": ("不属于", r"不属于|(?i:NOT\s+IN)"),
    "is_null": ("为空", r"为空|(?i:IS\s+NULL)"),
    "is_not_null": ("不为空", r"不为空|(?i:IS\s+NOT\s+NULL)"),
}
_VALUE_END = r"\s*(?=$|[，,；;。！？!?）)]|且|并|的(?:记录|项目|产品|合同|客户|账户|资产))"
_EXCLUSION_PREFIX = r"(?:^|[，,；;。]|并且|且|并)\s*(?:请|需要)?\s*"
_EXCLUSION_WORD = r"(?:排除|剔除|不含|不包括)"


def _active_scope_requested(request: str) -> bool:
    # 单独提到字典标签（包括示例、否定和待检查字段名）不能推导筛选。
    return bool(re.search(r"(?:^|[，,；;。])(?:范围|状态)(?:限于|仅限于?|为|等于)(?:仍)?(?:存续|未完结)(?:$|[，,；;。])", request))


def _scope_label(label: str) -> str:
    return "当期终止" if re.fullmatch(r"(?:当期|本期)(?:已)?(?:结束|终止)", label) else label


def _scope_options(role: str, fields: list[dict[str, Any]], qualifier: str, entity: str,
                   *, active_scope: bool) -> list[dict[str, Any]]:
    """Match a requested scope against document values before using model filter proposals."""
    if not (qualifier or active_scope):
        return []
    qualifier = _scope_label(qualifier)
    options = []
    seen = set()
    for field in fields:
        name = _field_name(field)
        caption = _field_comment(field)
        for entry in dictionary_options(field):
            value, label = entry["value"], entry["label"]
            matches = (_ACTIVE_STATUS_LABEL.fullmatch(label) if active_scope else
                       (_scope_label(label) == qualifier and (caption.startswith(entity) or caption.endswith(entity)))
                       or (label == "是" and caption.startswith("是否") and _scope_label(caption[2:]) == qualifier))
            if not name or (name, value) in seen or not matches:
                continue
            seen.add((name, value))
            options.append({
                "value": str(len(options)),
                "label": f"{_field_comment(field) or name}（{name}）等于 {value}—{label}",
                "description": str(field.get("logic") or "依据文档字典，请确认采用此业务口径。")[:2000],
                "selection": {"table": role, "field": name, "op": "eq", "value": value, "confirmed": True},
            })
    return options


def _named_filter_pattern(field: dict[str, Any], op: str) -> str:
    aliases = [re.escape(name) for name in (_field_name(field), _field_comment(field)) if name]
    return rf"(?<![A-Za-z0-9_])(?:{'|'.join(aliases)})[\s`）)]*(?:{_FILTER_OPERATORS[op][1]})\s*"


def _filter_value_pattern(value: Any) -> str:
    def literal(item: Any) -> str:
        return rf"['\"“‘]?{re.escape(str(item))}['\"”’]?"

    if isinstance(value, list):
        joined = r"\s*[,，、]\s*".join(literal(item) for item in value)
        return rf"[（(\[]?\s*{joined}\s*[）)\]]?"
    return literal(value)


def _requested_filter_choices(role: str, fields: list[dict[str, Any]], raw: dict[str, Any], request: str,
                              *, whole_clause: bool = False) -> list[dict[str, Any]]:
    """Only reference predicates stated by the user. A model-proposed value cannot prove its own meaning."""
    choices = []
    match = re.fullmatch if whole_clause else re.search
    for field in fields:
        field_name = _field_name(field)
        caption = _field_comment(field) or field_name
        entries = dictionary_options(field)
        if entries and raw["op"] in {"eq", "neq"}:
            candidates = [(op, entry["value"], entry["label"]) for op in ("eq", "neq") for entry in entries]
        else:
            candidates = [(raw["op"], raw.get("value"), "")]
        for op, value, label in candidates:
            if op in {"is_null", "is_not_null"}:
                value = None
                value_pattern = ""
            else:
                literals = [_filter_value_pattern(value)]
                if label:
                    literals.append(_filter_value_pattern(label))
                value_pattern = rf"(?:{'|'.join(literals)})"
            explicit_condition = match(_named_filter_pattern(field, op) + value_pattern + _VALUE_END, request)
            explicit_exclusion = label and op == "neq" and match(
                _EXCLUSION_PREFIX + rf"(?:{_EXCLUSION_WORD}\s*{re.escape(label)}|除\s*{re.escape(label)}\s*外)" + _VALUE_END,
                request,
            )
            if not explicit_condition and not explicit_exclusion:
                continue
            comparison = f"{caption}（{field_name}）{_FILTER_OPERATORS[op][0]}"
            if op not in {"is_null", "is_not_null"}:
                comparison += f" {value}" + (f"—{label}" if label else "")
            choices.append({"value": str(len(choices)), "label": comparison,
                            "description": str(field.get("logic") or "依据需求中的筛选条件和文档字段。")[:240],
                            "selection": {"table": role, "field": field_name, "op": op, "value": value, "confirmed": True}})
    return choices


_FIELD_REF = re.compile(
    r"(?:(?P<table>[A-Za-z_][\w]*)\.)?(?P<field>[A-Za-z_][\w]*)"
    r"(?:[（(](?P<label>[^()（）]+)[）)])?",
)


def documented_number_field(fields: list[dict[str, Any]], term: str) -> str:
    """仅返回全量文档中唯一有该指标名称或取数逻辑证据的数值列。"""
    numbers = [field for field in fields if type_family(field.get("data_type")) == "number"]
    # 上期等派生列会在取数说明中引用本期指标；字段本身的名称、括注先于其它列的引用。
    matches = [field for field in numbers if term == _field_name(field) or term in _field_comment(field)]
    if not matches:
        matches = [field for field in numbers if term in str(field.get("logic") or "")]
    if not term or len(matches) != 1:
        return ""
    field = matches[0]
    name, caption = _field_name(field), _field_comment(field)
    if name == term or (term in caption and not re.search(r"(?:不含|不包括|不包含|扣除|剔除|非)" + re.escape(term), caption)):
        return name
    # 逻辑里的条件、公式也会提到其它指标。只认直接取值，或明确的分类码、标签及取值字段。
    logic = str(field.get("logic") or "").strip()
    label = re.escape(term)
    if re.fullmatch(r"(?:直接)?取(?:字段)?[「“]?" + label + r"[」”]?(?:\[[\w.]+\])?[。；;]?", logic):
        return name
    coded_source = re.search(
        r"(?:(?<!不)为|(?<![!<>])=)\s*['\"]?[\w.]+[-—:：]" + label
        + r"[\u4e00-\u9fff]{0,20}['\"]?\s*[,，]\s*(?:直接)?取(?P<source>[\u4e00-\u9fff]{2,40})"
          r"(?:\[[\w.]+\])?\s*(?:[；;。\n]|$)", logic,
    )
    return name if coded_source and coded_source["source"] in caption else ""


def _documented_comparison(request: str, fields: list[dict[str, Any]], scope: re.Match | None) -> dict[str, Any] | None:
    subject = request[scope.end():].lstrip("的，,：:") if scope else request
    comparison = parse_number_comparison(subject)
    if not comparison or len(comparison[0]) != 1:
        return None
    terms, op, value = comparison
    term = terms[0]
    field = documented_number_field(fields, term)
    if not field:
        return None
    return {"term": term, "expression": {"left": field, "op": op, "right_type": "value", "right": value}}


def _unique_scope_binding(scope: re.Match | None, options: list[dict[str, Any]],
                          fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not scope or len(options) != 1:
        return None
    selection = options[0]["selection"]
    field = next(item for item in fields if _field_name(item) == selection["field"])
    qualifier, caption = _scope_label(scope["label"]), _field_comment(field)
    labels = [entry["label"] for entry in dictionary_options(field) if entry["value"] == selection["value"]]
    if len(labels) != 1:
        return None
    label = labels[0]
    active = _ACTIVE_SCOPE_LABEL.fullmatch(qualifier)
    if not (qualifier == _scope_label(label)
            or (caption.startswith("是否") and _scope_label(caption[2:]) == qualifier and label == "是")
            or (active and _ACTIVE_STATUS_LABEL.fullmatch(label))):
        return None
    if any(_field_comment(other) == caption
           or (_field_comment(other).startswith("是否") and _scope_label(_field_comment(other)[2:]) == qualifier)
           or any(_scope_label(entry["label"]) == qualifier for entry in dictionary_options(other))
           for other in fields if _field_name(other) != selection["field"]):
        return None
    return selection


@dataclass
class _ScopeClauses:
    remaining: str
    groups: list[tuple[str, list[dict[str, Any]]]]
    all_states: bool
    issue: str
    additional: list[str]

    @property
    def expression_request(self) -> str:
        # The additional filter clauses must pass _scope_clause_issue before checking this expression.
        return self.remaining.split("，", 1)[0] if self.additional else self.remaining


def _scope_clauses(request: str, roles: dict[str, list[dict[str, Any]]], scope_confirmed: bool) -> _ScopeClauses:
    """Separate explicit population clauses before grounding the comparison and any other conditions."""
    clauses = _CLAUSE_BREAK.split(request)
    all_states = any(_ALL_STATES.fullmatch(clause) for clause in clauses)
    groups = []
    remaining = []
    issue = ""
    restricted = False
    for index, clause in enumerate(clauses):
        if not clause or _ALL_STATES.fullmatch(clause):
            continue
        if all_states and re.fullmatch(r"(?:包括|包含|例如|比如|不仅限于)[\u4e00-\u9fff、]{1,60}", clause):
            if not re.search(r"但|除|剔|只|(?:且|仍|仅)(?!限于)|不含|不包括|不纳入|必须|不得|为空", clause):
                continue
        scope = _ONLY_SCOPE.fullmatch(clause) if len(clauses) > 1 else None
        if not scope:
            remaining.append(clause)
            if index and _RESTRICTED.match(clause):
                restricted = True
            continue
        restricted = True
        qualifier, entity = scope["label"], scope["entity"]
        active = bool(_ACTIVE_SCOPE_LABEL.fullmatch(qualifier))
        if active and scope_confirmed and entity in {"项目", "记录"}:
            continue
        options = []
        for role, fields in roles.items():
            if active and entity not in {"状态", "记录"}:
                fields = [field for field in fields if entity in _field_comment(field)]
            found = _scope_options(role, fields, qualifier, entity, active_scope=active)
            by_name = {_field_name(field): field for field in fields}
            conflicting_codes = any(
                sum(entry["value"] == item["selection"]["value"]
                    for entry in dictionary_options(by_name[item["selection"]["field"]])) > 1
                for item in found
            )
            if conflicting_codes or (len(found) == 1 and _unique_scope_binding(scope, found, fields) is None):
                issue = f"「{qualifier}{entity}」的文档字段或字典值有歧义，请核对后再生成预览。"
                options = []
                break
            options.extend(found)
        if not options and not issue:
            issue = f"当前文档缺少可核对的「{qualifier}{entity}」筛选字段和取值，请补充后再生成预览。"
        groups.append((qualifier + entity, options))
    if all_states and scope_confirmed:
        issue = "需求包含所有状态，但当前表仅覆盖存续范围，请核对选表。"
    cleaned = "，".join(remaining) if restricted or all_states else request
    return _ScopeClauses(cleaned, groups, all_states, issue, remaining[1:] if restricted or all_states else [])


def _scope_clause_issue(parts: _ScopeClauses, roles: dict[str, list[dict[str, Any]]],
                        filters: list[dict[str, Any]]) -> str:
    if parts.issue:
        return parts.issue
    if not (parts.groups or parts.all_states or parts.additional):
        return ""
    for label, options in parts.groups:
        if sum(option["selection"] in filters for option in options) != 1:
            return f"需求中的「{label}」范围还未落实到筛选条件。"
    if parts.all_states and any(
        item["field"] == _field_name(field) and ("状态" in _field_comment(field)
            or any(_ACTIVE_STATUS_LABEL.fullmatch(entry["label"]) for entry in dictionary_options(field)))
        for item in filters for field in roles[item["table"]]
    ):
        return "需求包含所有状态，不能同时限定某个状态值，请核对范围。"
    equalities = {}
    grouped = [option for _, options in parts.groups for option in options]
    leading = _LEADING_SCOPE.match(parts.remaining)
    for condition in filters:
        role = condition["table"]
        if condition["op"] == "eq":
            field = role, condition["field"]
            if field in equalities and equalities[field] != condition["value"]:
                return f"「{condition['field']}」有互相冲突的筛选取值，请核对范围。"
            equalities[field] = condition["value"]
        allowed = list(grouped)
        if leading:
            allowed.extend(_scope_options(role, roles[role], leading["label"], leading["entity"],
                                          active_scope=bool(_ACTIVE_SCOPE_LABEL.fullmatch(leading["label"]))))
        column = [field for field in roles[role] if _field_name(field) == condition["field"]]
        allowed.extend(_requested_filter_choices(role, column, condition, parts.remaining))
        if not any(option["selection"] == condition for option in allowed):
            return f"需求中缺少「{condition['field']}」这项额外筛选的依据，请核对范围。"
    # No trailing AND clause may disappear just because the model omitted its filter.
    for clause in parts.additional:
        if not any(
            choice["selection"] == condition
            for condition in filters
            for choice in _requested_filter_choices(condition["table"], roles[condition["table"]], condition, clause,
                                                     whole_clause=True)
        ):
            return f"请确认「{clause}」对应的筛选字段和取值后再生成预览。"
    return ""


def documented_scope_comparison(request: str, fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    """同一张表上，由需求和全量文档唯一确定的范围字典与单指标常量条件。"""
    compact = re.sub(r"\s+", "", request)
    scope = _LEADING_SCOPE.match(compact)
    if not scope:
        return None
    options = _scope_options("base", fields, scope["label"], scope["entity"],
                             active_scope=bool(_ACTIVE_SCOPE_LABEL.fullmatch(scope["label"])))
    selection = _unique_scope_binding(scope, options, fields)
    comparison = _documented_comparison(compact, fields, scope)
    if not selection or not comparison:
        return None
    return {**comparison, "entity": scope["entity"], "filter": selection}


def _direct_sources(field: dict[str, Any]) -> set[tuple[str, str]]:
    """只把明确直取的对应列作为关联证据，计算、拼接、同名列均不证明键相等。"""
    logic = str(field.get("logic") or "").strip().rstrip("。.")
    if logic not in ("直取", "直接取") and not re.fullmatch(r"直接取[^，。；;+]+\[\w+\]", logic):
        return set()
    tables = str(field.get("source_table") or "").splitlines()
    names = str(field.get("source_field") or "").splitlines()
    if len(tables) != len(names):
        return set()
    result = set()
    for table, name in zip(tables, names):
        table, name = table.strip(), name.strip()
        if not re.fullmatch(r"\w+(?:\.\w+)*", table) or not re.fullmatch(r"\w+", name):
            return set()
        if "[" in logic and not logic.endswith(f"[{name}]"):
            return set()
        result.add((table, name))
    return result


def _same_documented_value(field: dict[str, Any], owner: dict[str, Any], target: dict[str, Any]) -> bool:
    sources = _direct_sources(field)
    target_name = _field_name(target)
    # 相同的上游键，或者本字段直接来自目标列。历史快照只接受同表的月份归档。
    if sources and sources == _direct_sources(target):
        return True
    origins = {(table.rsplit(".", 1)[-1], name) for table, name in sources}
    name = str(owner["table_name"])
    return (name, target_name) in origins and origins <= {(name, target_name), (name + "_YYYY_MM", target_name)}


def scope_dimension_issue(request: str, filters: list[dict[str, Any]], table: dict[str, Any],
                          fields: list[dict[str, Any]], tables: list[dict[str, Any]],
                          fields_by_table: dict[int, list[dict[str, Any]]], *, role: str = "base") -> str:
    """无实体前缀的状态标志不能从已知的其它行粒度直接解释为需求实体的状态。"""
    scope = _LEADING_SCOPE.match(re.sub(r"\s+", "", request))
    dimension = str(table.get("dimension") or "")
    if not scope or not re.search(r"项目|产品|合同|客户|账户|资产", dimension):
        return ""
    entity = scope["entity"]
    if dimension.strip() == entity:
        return ""
    active = bool(_ACTIVE_SCOPE_LABEL.fullmatch(scope["label"]))
    for option in _scope_options(role, fields, scope["label"], entity, active_scope=active):
        selected = option["selection"]
        if not any(all(condition.get(k) == selected[k] for k in ("table", "field", "op", "value"))
                   for condition in filters):
            continue
        field = next(item for item in fields if _field_name(item) == selected["field"])
        if _field_comment(field).startswith(entity):
            continue
        for owner in tables:
            if str(owner.get("dimension") or "").strip() != entity:
                continue
            owner_fields = fields_by_table.get(int(owner["id"]), [])
            choices = _scope_options("related", owner_fields, scope["label"], entity, active_scope=active)
            selection = _unique_scope_binding(scope, choices, owner_fields)
            if selection and any(_field_name(other) == selection["field"] and _same_documented_value(field, owner, other)
                                 for other in owner_fields):
                break
        else:
            return f"文档中「{dimension}」的「{_field_comment(field)}」缺少对应{entity}状态的依据，请核对范围字段和关联。"
    return ""


def documented_aggregate_join(owner: dict[str, Any], owner_fields: list[dict[str, Any]],
                              detail: dict[str, Any], detail_fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the documented detail-to-summary keys for one reporting date."""
    if not owner.get("data_source_name") or owner["data_source_name"] != detail.get("data_source_name"):
        return None
    owner_date, _ = resolve_report_date(owner_fields)
    detail_date, _ = resolve_report_date(detail_fields)
    parent_day = next((field for field in owner_fields if _field_name(field) == owner_date), None)
    detail_day = next((field for field in detail_fields if _field_name(field) == detail_date), None)
    if not parent_day or not detail_day or not _same_documented_value(detail_day, owner, parent_day):
        return None
    owner_keys = [field for field in owner_fields if field.get("is_pk") == "Y" and field != parent_day]
    detail_keys = [field for field in detail_fields if field.get("is_pk") == "Y" and field != detail_day]
    if not owner_keys or len(detail_keys) <= len(owner_keys):
        return None
    on = []
    for key in owner_keys:
        family = type_family(key.get("data_type"))
        matches = [field for field in detail_keys if family and family == type_family(field.get("data_type"))
                   and _same_documented_value(field, owner, key)]
        if len(matches) != 1:
            return None
        on.append({"left": _field_name(key), "right": _field_name(matches[0])})
    if len({key["right"] for key in on}) != len(on):
        return None
    return {"table_name": detail["table_name"], "on": on, "report_date_field": detail_date,
            "relationship_confirmed": True, "unmatched_policy": "review", "right_aggregate": "sum"}


def metric_scope_binding(request: str, table: dict[str, Any], fields: list[dict[str, Any]],
                         owner: dict[str, Any], owner_fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    """在指标所在表绑定范围。关联只认需求中的实体、文档直取的实体键及同日报送口径。"""
    compact = re.sub(r"\s+", "", request)
    scope = _LEADING_SCOPE.match(compact)
    if not scope or str(owner.get("dimension") or "").strip() != scope["entity"]:
        return None
    comparison = _documented_comparison(compact, fields, scope)
    if not comparison:
        return None
    entity = scope["entity"]
    active = bool(_ACTIVE_SCOPE_LABEL.fullmatch(scope["label"]))
    def selections(role, columns):
        return _scope_options(role, columns, scope["label"], entity, active_scope=active)
    owner_selection = _unique_scope_binding(scope, selections("related", owner_fields), owner_fields)
    if not owner_selection:
        return None
    owner_field = next(field for field in owner_fields if _field_name(field) == owner_selection["field"])
    local_options = selections("base", fields)
    local = _unique_scope_binding(scope, local_options, fields)
    if local:
        field = next(item for item in fields if _field_name(item) == local["field"])
        if (str(table.get("dimension") or "").strip() == entity or _field_comment(field).startswith(entity)
                or _same_documented_value(field, owner, owner_field)):
            return {**comparison, "entity": entity, "filter": local}
    if local_options and not local:
        return None
    base_date, _ = resolve_report_date(fields)
    owner_date, _ = resolve_report_date(owner_fields)
    left_day = next((item for item in fields if _field_name(item) == base_date), None)
    right_day = next((item for item in owner_fields if _field_name(item) == owner_date), None)
    if not left_day or not right_day or not _same_documented_value(left_day, owner, right_day):
        return None
    owner_keys = [item for item in owner_fields if item.get("is_pk") == "Y" and item != right_day]
    if len(owner_keys) != 1:
        return None
    target = owner_keys[0]
    if entity == "项目":
        if target not in project_code_fields(owner_fields):
            return None
    elif not re.search(re.escape(entity) + r"(?:内部)?(?:编号|编码|代码|标识|ID|号)", _field_comment(target), re.I):
        return None
    matches = [item for item in fields if type_family(item.get("data_type"))
               and type_family(item.get("data_type")) == type_family(target.get("data_type"))
               and _same_documented_value(item, owner, target)]
    if len(matches) != 1:
        return None
    return {**comparison, "entity": entity, "filter": owner_selection, "join": {
        "table_name": owner["table_name"], "on": [{"left": _field_name(matches[0]), "right": _field_name(target)}],
        "report_date_field": owner_date, "relationship_confirmed": True, "unmatched_policy": "exclude",
    }}


_UNIT_SCALE = {"元": 1, "千元": 1000, "万元": 10000, "亿元": 100000000}
_UNIT = r"亿元|万元|千元|元|%|％|天|个月|年|笔|份"
_LITERAL_UNIT = re.compile(rf"(?P<value>-?\d+(?:\.\d+)?)(?P<unit>{_UNIT})")
_NUMBER_LITERAL = r"-?\d+(?:\.\d+)?"
_RANGE_START = r"(?:必须|应当|应该|应|须|需)?(?:处于|位于|介于|落在|在)"
_FIELD_OP = {"早于": "lt", "晚于": "gt", "小于": "lt", "低于": "lt", "大于": "gt", "高于": "gt", "等于": "eq"}
_ABNORMAL = r"(?:时|则)?(?:列为|记为|视为|判为|判定为|为)?异常"


def _storage_units(subject: str, candidate: dict[str, Any], fields: list[dict[str, Any]]) -> str | None:
    """Translate stated threshold units only when the document defines the operand's storage unit."""
    expression = candidate.get("expression") or {}
    names = {part.get("left") for part in expression.get("conditions", [expression]) if isinstance(part, dict)}
    if len(names) != 1:
        return None
    field = next((field for field in fields if _field_name(field) in names), {})
    caption = _field_comment(field)
    text = caption + " " + str(field.get("logic") or "")
    units = set(re.findall(rf"(?:单位[：:为是]\s*|[（(])({_UNIT})(?=[）)，,。；;\s]|$)", text))
    if len(units) != 1:
        return None
    stored = units.pop().replace("％", "%")
    # In “1至10万元” the trailing unit qualifies both endpoints.
    subject = re.sub(rf"({_RANGE_START})({_NUMBER_LITERAL})(到|至|和|与|~|～|-)({_NUMBER_LITERAL})({_UNIT})",
                     r"\1\2\5\3\4\5", subject)
    for literal in _LITERAL_UNIT.finditer(subject):
        source = literal["unit"].replace("％", "%")
        if source != stored and not (source in _UNIT_SCALE and stored in _UNIT_SCALE):
            return None
    def convert(match: re.Match) -> str:
        amount = Decimal(match["value"]) * _UNIT_SCALE.get(match["unit"], 1) / _UNIT_SCALE.get(stored, 1)
        return format(amount, "f")
    return _LITERAL_UNIT.sub(convert, subject)


def _field_group_issue(subject: str, expression: dict[str, Any], fields: list[dict[str, Any]]) -> str | None:
    """Compare an expressly stated violation against each named reference column, in either operand order."""
    compact = subject.rstrip("。.!！")
    operands = rf"(?P<op>{'|'.join(_FIELD_OP)})(?P<right>[\w、]+?)"
    group = re.fullmatch(rf"(?:当)?(?P<left>\w+?)(?:同时|分别)?{operands}{_ABNORMAL}", compact)
    if not group:
        group = re.fullmatch(rf"(?P<left>\w+?)(?P<deny>不得|不能|不应)(?P<joint>同时)?{operands}", compact)
    if not group or re.match(_NUMBER_LITERAL, group["right"]):
        return None
    rights = re.split(r"(或者|或|和|以及|与|及|、)", group["right"])
    if len(rights) < 3:
        return None
    operators = {"any" if separator.startswith("或") else "all" for separator in rights[1::2]}
    if group.groupdict().get("deny") and len(operators) == 1 and not group["joint"]:
        operators = {"any"}
    terms = [group["left"], *rights[::2]]
    references = []
    for term in terms:
        names = [_field_name(f) for f in fields if term in (_field_name(f), _field_comment(f))]
        if len(names) != 1:
            return f"请核对组合比较中「{term}」的文档字段。"
        references.append(names[0])
    op = _FIELD_OP[group["op"]]
    inverse = {"lt": "gt", "gt": "lt", "eq": "eq"}[op]
    conditions = list(expression.get("conditions") or [])
    issue = "请完整保留需求指定的每个比较字段、方向及任一或全部关系。"
    if len(operators) != 1 or expression.get("logic") not in operators or len(conditions) != len(rights[::2]):
        return issue
    left = references[0]
    for right in references[1:]:
        matches = [(left, op, right), (right, inverse, left)]
        matched = next((c for c in conditions if isinstance(c, dict) and c.get("right_type", "field") == "field"
                        and c.get("right_table", "base") == "base" and (c.get("left"), c.get("op"), c.get("right")) in matches), None)
        if not matched:
            return issue
        conditions.remove(matched)
    return ""


def _check_numeric_requirement(candidate: dict[str, Any], roles: dict[str, list[dict[str, Any]]],
                               request: str, scope: re.Match | None, filters: list[dict[str, Any]]) -> str:
    subject = request[scope.end():].lstrip("的，,：:") if scope else request
    expression = candidate.get("expression") or {}
    plain = plain_null_check(subject, roles["base"])
    if plain:
        return plain.coverage_issue({"expression": expression})
    positive = re.fullmatch(rf"(?:当)?(?P<term>\w+?)(?P<op>大于|小于|高于|低于|超过|等于)"
                            rf"(?P<tail>{_NUMBER_LITERAL}.*?){_ABNORMAL}[。.!！]?", subject)
    if positive and (not re.search(r"不|不得", positive["term"][-3:])
                     and re.search(r"或|且|同时", positive["tail"])):
        subject = positive["term"] + "不得" + positive["op"] + positive["tail"]
    field_issue = _field_group_issue(subject, expression, roles["base"])
    if field_issue is not None:
        return field_issue
    threshold_with_unit = re.search(rf"(?:超过|大于|小于|高于|低于|等于|{_RANGE_START}|到|至|~|～)"
                                    rf"{_NUMBER_LITERAL}(?:{_UNIT})", subject)
    if threshold_with_unit:
        subject = _storage_units(subject, candidate, roles["base"])
        if not subject:
            return "请核对阈值单位及对应字段的存储单位。"
    mixed = parse_mixed_group(subject)
    group = mixed or parse_numeric_group(subject)
    if not group and re.search(rf"{_RANGE_START}{_NUMBER_LITERAL}(?:到|至|和|与|~|～|-){_NUMBER_LITERAL}", subject):
        return "请核对上下限、端点及附加条件后再生成预览。"
    if not group and re.search(NONEMPTY_REQUIREMENT, subject) and re.search(r"[，,；;、]|或|并|且|同时", subject):
        return "请核对非空要求、比较条件及其他限定，完整确认后再生成预览。"
    if group:
        logic, expected = group
        conditions = expression.get("conditions")
        if expression.get("logic") != logic or not isinstance(conditions, list) or len(conditions) != len(expected):
            return "校验条件未完整保留需求中的所有比较及其任一或全部关系，请核对后重新分析。"
        unmatched = list(conditions)
        assigned_fields = {}
        for term, op, threshold in expected:
            exact = [_field_name(f) for f in roles["base"] if term in (_field_name(f), _field_comment(f))]
            field = (exact[0] if len(exact) == 1 else documented_number_field(roles["base"], term)) or assigned_fields.get(term)
            allowed = None
            if mixed and not field:
                allowed = {_field_name(f) for f in metric_choices(term, roles["base"])}
            matched = next((item for item in unmatched if isinstance(item, dict)
                            and item.get("op") == op and (op == "is_null" or (
                                item.get("right_type") == "value" and item.get("right") == threshold))
                            and (not field or item.get("left") == field)
                            and (allowed is None or item.get("left") in allowed)), None)
            if matched is None:
                return f"「{term}」的比较字段、方向或阈值与需求不一致，请核对后再生成预览。"
            assigned_fields[term] = matched.get("left")
            unmatched.remove(matched)
        return ""
    comparison = number_comparison_prefix(subject)
    if not comparison or len(comparison[0]) != 1:
        return ""
    terms, op, constant, remainder = comparison
    if not expression:
        return ""
    if remainder and not re.match(r"[，,；;]|且|并且|同时", remainder):
        return "需求中的阈值单位或附加条件需要明确后，才能生成完整预览。"
    if re.search(r"或(?:者)?|否则", remainder):
        return "当前规则无法完整表达需求中的任选或分支条件，请拆分后重新分析。"
    if any(expression.get(key) != value for key, value in {"right_type": "value", "op": op, "right": constant}.items()):
        return "校验条件与需求中的比较方向或阈值不一致，请核对后重新分析。"
    field = documented_number_field(roles["base"], terms[0])
    if field and expression.get("left") != field:
        return "比较字段与需求中的指标不一致，请核对后重新分析。"
    for clause in re.split(r"[，,；;]|并且|同时|且", remainder):
        if not clause:
            continue
        if candidate.get("null_policy") == "review" and re.fullmatch(r"(?:也)?(?:核查|检查|校验|核实)(?:缺值|缺失值|空值)", clause):
            continue
        retained = any(
            choice["selection"] == condition
            for condition in filters
            for choice in _requested_filter_choices(
                condition["table"],
                [item for item in roles[condition["table"]] if _field_name(item) == condition["field"]],
                condition, clause,
            )
        )
        if not retained:
            return f"还未确定「{clause}」对应的字段和取值，请核对后再生成预览。"
    return ""


def check_request_coverage(definition: dict[str, Any], base_fields: list[dict[str, Any]],
                           related_fields: list[dict[str, Any]], *, scope_confirmed: bool = False, dimension: str = "") -> str:
    """Check an edited or retried AI definition against the original request."""
    description = str(definition.get("description") or "")
    original = re.sub(r"；候选方案：[^；]+（[^；]*）(?:；依据：文档同义指标[^；]+)?$", "", description)
    request = re.sub(r"\s+", "", original)
    numeric = category_numeric_check(request, base_fields, dictionary_options, dimension=dimension)
    if numeric:
        return numeric.coverage_issue(definition)
    conditional = conditional_null_check(request, base_fields, dictionary_options, dimension=dimension)
    if conditional:
        return conditional.coverage_issue(definition)
    plain = plain_null_check(request, base_fields)
    if plain:
        return plain.coverage_issue(definition)
    roles = {"base": base_fields, "related": related_fields}
    # Drafts can retain a proposed filter while it is awaiting confirmation.
    # The review and execution gates still require the original confirmed flag.
    filters = [{**item, "confirmed": True} for item in definition.get("filters") or []]
    parts = _scope_clauses(request, roles, scope_confirmed)
    problem = _scope_clause_issue(parts, roles, filters)
    if problem:
        return problem
    request = parts.expression_request
    scope = _LEADING_SCOPE.match(request)
    if scope:
        qualifier, entity = scope["label"], scope["entity"]
        active = bool(_ACTIVE_SCOPE_LABEL.fullmatch(qualifier))
        if not (scope_confirmed and active):
            selections = []
            for role, fields in roles.items():
                options = _scope_options(role, fields, qualifier, entity, active_scope=active)
                if len(options) != 1 or _unique_scope_binding(scope, options, fields) is not None:
                    selections.extend(option["selection"] for option in options)
            if (selections or _LIMITING_QUALIFIER.search(qualifier)) and not any(item in filters for item in selections):
                return f"需求中的「{qualifier}」范围还未落实到筛选条件。"
    return _check_numeric_requirement(definition, roles, request, scope, filters)


def _documented_review_refs(details: str, table: str, fields: dict[str, dict[str, Any]],
                            bound: str, value: Any) -> bool:
    """选项必须都是本表已知字段，括注只能说明文档字段名及其真实字典码。"""
    names = []
    for item in re.split(r"\s*(?:或者|或|、)\s*", details):
        ref = _FIELD_REF.fullmatch(item.strip())
        if not ref or (ref["table"] and ref["table"] != table) or ref["field"] not in fields:
            return False
        name = ref["field"]
        names.append(name)
        if ref["label"]:
            label, sep, code = ref["label"].partition("=")
            if label.strip() != _field_comment(fields[name]):
                return False
            if sep and (not any(str(entry["value"]) == code.strip() for entry in dictionary_options(fields[name]))
                        or (name == bound and str(value) != code.strip())):
                return False
    return bound in names


def _reconcile_base_field_reviews(candidate: dict[str, Any], fields: list[dict[str, Any]], table: str,
                                 request: str, scope: re.Match | None, options: list[dict[str, Any]]) -> bool:
    """仅消解已由需求、全量文档和最终谓词共同唯一确定的字段身份子句。"""
    filters = candidate.get("filters") or []
    selection = _unique_scope_binding(scope, options, fields)
    scope_bound = selection is not None and selection in filters
    bindings = []
    if scope and scope_bound:
        bindings.append((scope["label"], selection["field"], selection["value"], r"判定|判断|状态|筛选"))
    check = _documented_comparison(request, fields, scope)
    expression = candidate.get("expression") or {}
    measure_bound = bool(check and all(expression.get(key) == value for key, value in check["expression"].items()))
    if measure_bound:
        bindings.append((check["term"], expression["left"], None, r"金额|数值|指标|比较"))
    # 没有完整、唯一的字段证据时，模型选择了一个表里存在的列也不能消解提问。
    by_name = {_field_name(field): field for field in fields}
    patterns = [
        (re.compile(r"(?:请|还|仍)?(?:需要?|待|尚待)?(?:确认|明确|核对)?\s*['\"“‘「]?"
                    + re.escape(term) + r"['\"”’」]?\s*(?:的|对应|采用|使用|用)(?:的|哪一?个)?(?:"
                    + kinds + r")?(?:字段|列)(?:名称|名)?(?:[：:]\s*(?P<refs>.+))?[？?]?$"), name, value)
        for term, name, value, kinds in bindings
    ]
    remaining = []
    for issue in candidate.get("uncertainties") or []:
        parts = [part.strip() for part in re.split(r"(?:[，,；;。\n]+\s*)?(?:以及|并且|同时)|[，,；;。\n]+", issue)
                 if part.strip()]
        kept = []
        for part in parts:
            for pattern, name, value in patterns:
                match = pattern.fullmatch(part)
                if match and (not match["refs"] or _documented_review_refs(match["refs"], table, by_name, name, value)):
                    break
            else:
                kept.append(part)
        if len(kept) == len(parts):
            remaining.append(issue)
        elif kept:
            remaining.append("；".join(kept))
    candidate["uncertainties"] = list(dict.fromkeys(remaining))
    return measure_bound and (not scope or scope_bound) and len(filters) == int(scope_bound)


def ground_candidate_query(candidate: dict[str, Any], draft: dict[str, Any], base_fields: list[dict[str, Any]],
                           related_fields: list[dict[str, Any]], request: str, *, scope_confirmed: bool = False,
                           documented_join: dict[str, Any] | None = None, dimension: str = "",
                           document_scope: str = "") -> bool:
    """按真实文档生成选项，并返回是否已用全量字段独立核实单表比较和筛选字段。"""
    raw_filters = draft.get("filters", [])
    if not isinstance(raw_filters, list) or len(raw_filters) > 8 or any(not isinstance(item, dict) for item in raw_filters):
        raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    roles = {"base": base_fields, "related": related_fields}
    questions = candidate.setdefault("questions", [])
    uncertainties = candidate.setdefault("uncertainties", [])
    numeric = category_numeric_check(request, base_fields, dictionary_options, dimension=dimension)
    if numeric and not draft.get("join"):
        return numeric.bind_questions(candidate, base_fields, draft, document_scope=document_scope)
    conditional = conditional_null_check(request, base_fields, dictionary_options, dimension=dimension)
    if conditional and not draft.get("join"):
        selections = conditional.selections
        candidate["filters"] = [{**selections[0], "confirmed": len(selections) == 1}] if selections else []
        question = conditional.scope_question(base_fields, raw_filters)
        if question:
            uncertainties.append(question["uncertainty"])
            questions.append(question)
        measure_question = next((q for q in questions if q["id"] == "expression.left"), None)
        measure_names = {field["field_name"] for field in conditional.measures}
        if measure_question and (candidate.get("expression") or {}).get("op") == "is_null":
            options = [o for o in measure_question["options"] if o["value"] in measure_names]
            if options:
                measure_question["options"] = options
                if candidate["expression"].get("left") not in measure_names:
                    candidate["expression"]["left"] = options[0]["value"]
        problem = conditional.coverage_issue(candidate)
        if problem:
            uncertainties.append(problem)
            candidate["preview_error"] = problem
            candidate["status"] = "needs_clarification"
            return False
        bind_verified_null_fields(candidate, conditional, base_fields, table=(draft.get("target") or {}).get("table") or "",
                                  document_scope=document_scope)
        return True

    plain = None if conditional else plain_null_check(request, base_fields)
    if plain:
        expression = candidate.get("expression") or {}
        chosen = expression.get("left")
        names = {field["field_name"] for field in plain.measures}
        recommended = chosen in names
        if not recommended and plain.measures and expression.get("op") == "is_null":
            expression["left"] = plain.measures[0]["field_name"]
        candidate.pop("filters", None)
        problem = plain.coverage_issue({**candidate, "join": draft.get("join") or candidate.get("join")})
        if problem:
            uncertainties.append(problem)
            candidate["preview_error"] = problem
            candidate["status"] = "needs_clarification"
            return False
        reconcile_field_choices(candidate, base_fields, request)
        bind_verified_null_fields(candidate, plain, base_fields, recommended=recommended,
                                  table=(draft.get("target") or {}).get("table") or "", document_scope=document_scope)
        return True

    def add_question(key: str, text: str, options: list[dict[str, Any]], *, uncertainty: str = "") -> None:
        if not options:
            if text not in uncertainties:
                uncertainties.append(text)
            return
        question: dict[str, Any] = {"id": key, "text": text, "options": options}
        if uncertainty:
            question["uncertainty"] = uncertainty
            if uncertainty not in uncertainties:
                uncertainties.append(uncertainty)
        questions.append(question)

    scope_roles = {role: fields for role, fields in roles.items() if role == "base" or draft.get("join")}
    parts = _scope_clauses(re.sub(r"\s+", "", request), scope_roles, scope_confirmed)
    compact_request = parts.remaining
    filter_request = compact_request if parts.groups or parts.all_states else request
    scope_match = _LEADING_SCOPE.match(compact_request)
    qualifier = scope_match["label"] if scope_match else ""
    entity = scope_match["entity"] if scope_match else ""
    active_scope = bool(_ACTIVE_SCOPE_LABEL.fullmatch(qualifier)) if scope_match else _active_scope_requested(compact_request)
    if active_scope and scope_confirmed:
        qualifier = ""
        active_scope = False
    scope_options = {
        role: _scope_options(role, fields, qualifier, entity, active_scope=active_scope) for role, fields in roles.items()
        if role == "base" or draft.get("join")
    }
    if _LIMITING_QUALIFIER.search(qualifier) and not any(scope_options.values()):
        message = f"当前文档缺少可核对的{_scope_label(qualifier)}字段和取值，请补充后再生成预览。"
        uncertainties.append(message)
        candidate.setdefault("preview_error", message)
    scope_names = {
        role: {option["selection"]["field"] for option in options} for role, options in scope_options.items()
    }
    # 先补齐需求中已明确的范围。模型另加的谓词须按需求独立核对。
    has_status_filter = any(
        raw.get("table", "base") == role and raw.get("op") == "eq" and any(
            _field_name(field) in scope_names[role] and raw.get("field") in (_field_name(field), _field_comment(field))
            for field in roles[role]
        )
        for role in scope_options for raw in raw_filters
    )
    if not has_status_filter:
        scope = next((options for options in scope_options.values() if options), [])
        if scope:
            raw_filters = [scope[0]["selection"], *raw_filters]
    filters = []
    for label, options in parts.groups:
        if not options:
            continue
        index = len(filters)
        filters.append({**options[0]["selection"], "confirmed": len(options) == 1})
        if len(options) > 1:
            add_question(f"filters.{index}", f"「{label}」采用哪个筛选口径？",
                         [{**option, "value": str(i)} for i, option in enumerate(options)])
    for raw in raw_filters:
        index = len(filters)
        role = raw.get("table", "base")
        if not isinstance(role, str) or role not in roles or (role == "related" and not draft.get("join")):
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        fields = roles[role]
        name = raw.get("field")
        op = raw.get("op")
        if not isinstance(name, str) or not name or not isinstance(op, str) or op not in _FILTER_OPERATORS:
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        matches = [field for field in fields if name in (field["field_name"], field.get("field_cn"))]
        meanings = {field.get("field_cn") for field in matches if field.get("field_cn")}
        alternatives = [field for field in fields if field in matches or field.get("field_cn") in meanings]
        choices = _requested_filter_choices(role, alternatives, raw, filter_request)
        named_condition = any(
            re.search(_named_filter_pattern(field, operator), filter_request)
            for field in matches or [{"field_name": name}] for operator in _FILTER_OPERATORS
        )
        options = scope_options.get(role, [])
        if op == "eq" and not named_condition and not choices and any(
            _field_name(field) in scope_names.get(role, set()) for field in matches
        ):
            requires_choice = len(options) > 1
            if not requires_choice and scope_match and _unique_scope_binding(scope_match, options, fields) is None:
                message = f"「{qualifier}」的文档状态字段或字典值有歧义，请核对后再生成预览。"
                uncertainties.append(message)
                candidate.setdefault("preview_error", message)
                continue
            filters.append({**options[0]["selection"], "confirmed": not requires_choice})
            if active_scope:
                _bind_active_scope_review(uncertainties, requires_choice=requires_choice)
            if requires_choice:
                add_question(f"filters.{index}", "采用哪个筛选口径？", options[:100],
                             uncertainty=_ACTIVE_SCOPE_REVIEW if active_scope else "")
                if active_scope:
                    questions[-1]["remember_scope"] = "active_status"
            continue
        if choices:
            requires_choice = len(choices) > 1
            filters.append({**choices[0]["selection"], "confirmed": not requires_choice})
            if requires_choice:
                add_question(f"filters.{index}", "采用哪个筛选口径？", choices[:100])
        elif named_condition:
            label = (_field_comment(matches[0]) or name) if matches else name
            message = (f"请明确「{label}」的筛选取值，补充后再生成规则。" if matches else
                       f"当前文档找不到筛选字段「{label}」，请核对选择的表或补充字段说明。")
            uncertainties.append(message)
            candidate.setdefault("preview_error", message)
    if re.search(_EXCLUSION_PREFIX + _EXCLUSION_WORD, request) and not any(
        item["op"] in {"neq", "not_in"} for item in filters
    ):
        message = "需求包含排除条件，请补充对应的筛选字段和取值后再生成规则。"
        uncertainties.append(message)
        candidate.setdefault("preview_error", message)
    if len(filters) > 8:
        message = "这条需求包含超过 8 项筛选条件，请拆分校验规则。"
        uncertainties.append(message)
        candidate.setdefault("preview_error", message)
    if filters or "filters" in draft:
        candidate["filters"] = filters
    confirmed_filters = [{**item, "confirmed": True} for item in filters]
    subject = compact_request[scope_match.end():].lstrip("的，,：:") if scope_match else compact_request
    bind_document_metric_questions(candidate, roles, subject)
    mismatch = (_scope_clause_issue(parts, roles, confirmed_filters)
                or _check_numeric_requirement(candidate, roles, parts.expression_request, scope_match, filters))
    if mismatch:
        uncertainties.append(mismatch)
        candidate.setdefault("preview_error", mismatch)
    elif parts.all_states or (parts.groups and any(
        item["confirmed"] and option["selection"] == item
        for item in filters for option in _scope_options(item["table"], roles[item["table"]], "", "", active_scope=True)
    )):
        # The generic prompt review is triggered by the word 存续 alone. Keep independent model questions.
        from .generation_policy import request_reviews
        generic = {item.rstrip("。") for item in request_reviews("存续")}
        uncertainties[:] = [item for item in uncertainties if item.rstrip("。") not in generic]
    if candidate.get("preview_error"):
        candidate["status"] = "needs_clarification"

    raw_join = draft.get("join")
    if raw_join is None:
        reconcile_field_choices(candidate, base_fields, request)
        return _reconcile_base_field_reviews(candidate, base_fields, str((draft.get("target") or {}).get("table") or ""),
                                             compact_request, scope_match, scope_options.get("base", []))
    return bind_model_join(candidate, raw_join, base_fields, related_fields, documented_join=documented_join)


def bind_model_join(candidate: dict[str, Any], raw_join: dict, base_fields: list[dict],
                    related_fields: list[dict], *, documented_join: dict | None = None,
                    accept_model_decisions: bool = False) -> bool:
    """Bind actual fields; semantic generation can carry the model's explicit execution choices."""
    def add_question(key: str, text: str, options: list[dict]) -> None:
        if options:
            candidate.setdefault("questions", []).append({"id": key, "text": text, "options": options})
        elif text not in candidate.setdefault("uncertainties", []):
            candidate["uncertainties"].append(text)

    if not isinstance(raw_join, dict) or not related_fields:
        raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    if documented_join and raw_join == documented_join:
        candidate["join"] = documented_join
        filters = candidate.get("filters") or []
        return bool(not candidate.get("preview_error") and filters and all(item["confirmed"] for item in filters))
    join = {**raw_join, "relationship_confirmed": False, "unmatched_policy": "unresolved"}
    base_names = {field["field_name"] for field in base_fields}
    related_names = {field["field_name"] for field in related_fields}
    on = raw_join.get("on", [])
    valid_on = isinstance(on, list) and 1 <= len(on) <= 4 and all(
        isinstance(pair, dict) and pair.get("left") in base_names and pair.get("right") in related_names for pair in on)
    related_date_field, _related_date_choices = resolve_report_date(
        related_fields, raw_join.get("report_date_field") if accept_model_decisions else "")
    date_field = (next((field for field in related_fields if _field_name(field) == related_date_field), None)
                  if related_date_field else None)
    date_label = _field_comment(date_field) if date_field else ""
    base_table = str((candidate.get("target") or {}).get("table") or candidate.get("table_name") or "")
    related_table = str(raw_join.get("table_name") or "")
    base_label = table_label(candidate.get("table_name_cn"), "本次检查的信息")
    related_label = table_label(candidate.get("related_table_name_cn"), "对应信息")
    labels = {"base_label": base_label, "related_label": related_label}
    options = []
    if valid_on:
        options.append({
            "value": "confirm",
            "label": join_relationship_label(base_fields, related_fields, on, date_label=date_label, **labels),
            "description": join_relationship_description(
                base_fields, related_fields, on, date_label=date_label,
                base_table=base_table, related_table=related_table,
            ),
            "selection": {"on": on, "relationship_confirmed": True},
        })
    else:
        base_keys = [field for field in base_fields if field.get("is_pk") == "Y"]
        related_keys = [field for field in related_fields if field.get("is_pk") == "Y"]
        if len(base_keys) == len(related_keys) == 1:
            proposed = [{"left": base_keys[0]["field_name"], "right": related_keys[0]["field_name"]}]
            join["on"] = proposed
            options.append({
                "value": "confirm",
                "label": join_relationship_label(base_fields, related_fields, proposed, date_label=date_label, **labels),
                "description": (
                    "两侧均为文档主键；仍需确认业务含义一致，不能仅据主键名称认定可关联。"
                    + join_relationship_description(
                        base_fields, related_fields, proposed, date_label=date_label,
                        base_table=base_table, related_table=related_table,
                    )
                ),
                "selection": {"on": proposed, "relationship_confirmed": True},
            })
    if accept_model_decisions and valid_on and raw_join.get("relationship_confirmed") is True:
        join["relationship_confirmed"] = True
    else:
        add_question("join.relationship_confirmed", f"是否按以下方式找到同一报送日期的{related_label}？", options)
    join["report_date_field"] = related_date_field
    if not join["report_date_field"]:
        add_question("join.report_date_field", "关联表按哪个业务日期与主表对齐？", date_options(related_fields))
    options = [join_unmatched_option(join.get("right_aggregate"))]
    if join.get("right_aggregate") == "sum":
        options.append(join_unmatched_option())
    selected = next((item for item in options if item["value"] == raw_join.get("unmatched_policy")), None)
    if accept_model_decisions and selected:
        join["unmatched_policy"] = selected["value"]
        candidate.setdefault("notices", []).append(f"缺少同日{related_label}的记录：{selected['label']}。")
    else:
        add_question("join.unmatched_policy", join_unmatched_question(base_label, related_label), options)
    candidate["join"] = join
    candidate["can_enable"] = False
    return False
