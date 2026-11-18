"""Document-backed choices for bounded query scopes. Never infer a status code from convention."""
from __future__ import annotations

import math
import re
from typing import Any

from .model_calls import failure
from .query_spec import base_type

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
    for table in tables:
        ranked = []
        for position, field in enumerate(fields_by_table.get(int(table["id"]), [])):
            label = f"{field.get('field_name') or ''} {field.get('field_cn') or ''}"
            dictionary = str(field.get("dictionary") or "")
            score = sum(len(token) for token in wanted if token in label)
            score += sum(2 * len(token) for token in wanted if token in dictionary)
            entries = dictionary_options(field) if project_state else []
            status_evidence = any(_ACTIVE_STATUS_LABEL.fullmatch(item["label"]) for item in entries)
            if score or status_evidence:
                ranked.append((not status_evidence, -score, position, field))
        hints = []
        for _status_rank, _score, _position, field in sorted(ranked, key=lambda item: item[:3])[:4]:
            entries = dictionary_options(field)
            labels = [f"{item['value']}={item['label']}" for item in entries
                      if item["label"] in request or (project_state and _ACTIVE_STATUS_LABEL.fullmatch(item["label"]))][:3]
            hints.append(f"{field['field_name']}:{str(field.get('field_cn') or '')[:40]}" + ("[" + ",".join(labels) + "]" if labels else ""))
        if hints:
            lines.append(f"{table['table_name']}|" + " / ".join(hints))
    return "\n".join(lines)[:16000]


_ACTIVE_SCOPE_REVIEW = "请确认存续范围的状态字段与状态码"
_SCOPE_REVIEW_PART = re.compile(r"状态|字典|代码|取值|存续(?:范围|口径)|筛选口径|如何判定|如何界定|定义")
_FILTER_WORD = re.compile(r"筛选|过滤|判定|识别")
_CHOICE_WORD = re.compile(r"哪(?:一)?(?:个|列|项|种|套|字段)|用哪|按哪|如何|怎么|(?:尚?未|无法|需要?|待|请)确认")
_INDEPENDENT_REVIEW_PART = re.compile(
    r"关联|联接|匹配|日期|期间|时点|截止|跨期|币种|单位|汇总|聚合|例外|除外|排除|粒度|另[一有]|其他|额外",
)
_REVIEW_SPLIT = re.compile(
    r"[；;。\n，,]|(?:以及|并且|同时|另需|与|和)\s*(?=(?:还|需|待|请|未|无法|确认|核对|确定)*"
    r"(?:关联|日期|业务日期|截止日期))",
)


def _bind_active_scope_review(uncertainties: list[str]) -> None:
    # 选表、生成和系统提醒可能都在问同一个状态口径。保留单个稳定的复核项，
    # 让表单只在选中真实字典条件时记录证据；独立问题仍须单独处理。
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
    uncertainties[:] = list(dict.fromkeys([_ACTIVE_SCOPE_REVIEW, *remaining]))


_ACTIVE_STATUS_LABEL = re.compile(r"存续(?:\s*[（(]\s*未完结\s*[）)])?|未完结")
_PROJECT_STATE_TERMS = re.compile(r"项目状态|是否(?:仍|已|尚)?(?:存续|未完结|完结)|未完结|存续")


def _active_scope_requested(request: str) -> bool:
    # 问“是否存续/是否完结”只提示相关字段，不等同于“仅查存续项目”。
    request = re.sub(r"是否(?:仍|已|尚)?(?:存续|未完结|完结)", "", request)
    return bool(re.search(r"(?<![非不])存续|未完结", request))


def _active_scope_options(role: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enumerate documented alternatives in table order, independent of the model's starting field."""
    options = []
    seen = set()
    for field in fields:
        name = _field_name(field)
        for entry in dictionary_options(field):
            value, label = entry["value"], entry["label"]
            if not name or (name, value) in seen or not _ACTIVE_STATUS_LABEL.fullmatch(label):
                continue
            seen.add((name, value))
            options.append({
                "value": str(len(options)),
                "label": f"{_field_comment(field) or name}（{name}）等于 {value}—{label}",
                "description": str(field.get("logic") or "依据文档字典，请确认采用此业务口径。")[:2000],
                "selection": {"table": role, "field": name, "op": "eq", "value": value, "confirmed": True},
            })
    return options


def ground_candidate_query(candidate: dict[str, Any], draft: dict[str, Any], base_fields: list[dict[str, Any]],
                           related_fields: list[dict[str, Any]], request: str, *, scope_confirmed: bool = False) -> None:
    """Attach real choices, resetting every model-supplied user-confirmation assertion."""
    raw_filters = draft.get("filters", [])
    if not isinstance(raw_filters, list) or len(raw_filters) > 8 or any(not isinstance(item, dict) for item in raw_filters):
        raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    roles = {"base": base_fields, "related": related_fields}
    questions = candidate.setdefault("questions", [])
    uncertainties = candidate.setdefault("uncertainties", [])

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

    active_options = {
        role: _active_scope_options(role, fields) for role, fields in roles.items()
        if not scope_confirmed and _active_scope_requested(request) and (role == "base" or draft.get("join"))
    }
    active_names = {
        role: {option["selection"]["field"] for option in options} for role, options in active_options.items()
    }
    # 补足模型省略的范围，但不覆盖模型已经给出的独立状态谓词（如 IN、NEQ）。
    has_status_filter = any(
        raw.get("table", "base") == role and any(
            _field_name(field) in active_names[role] and raw.get("field") in (_field_name(field), _field_comment(field))
            for field in roles[role]
        )
        for role in active_options for raw in raw_filters
    )
    if not has_status_filter and len(raw_filters) < 8:
        scope = next((options for options in active_options.values() if options), [])
        if scope:
            raw_filters = [scope[0]["selection"], *raw_filters]
    filters = []
    operator_names = {"eq": "等于", "neq": "不等于", "lt": "小于", "lte": "小于或等于", "gt": "大于", "gte": "大于或等于", "in": "属于", "not_in": "不属于", "is_null": "为空", "is_not_null": "不为空"}
    for index, raw in enumerate(raw_filters):
        role = raw.get("table", "base")
        if not isinstance(role, str) or role not in roles or (role == "related" and not draft.get("join")):
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        fields = roles[role]
        name = raw.get("field")
        if not isinstance(name, str) or not isinstance(raw.get("op"), str) or raw.get("op") not in operator_names:
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        matches = [field for field in fields if name in (field["field_name"], field.get("field_cn"))]
        options = active_options.get(role, [])
        matched_names = {_field_name(field) for field in matches}
        status_matches = [item["selection"] for item in options if item["selection"]["field"] in matched_names]
        explicit_code = re.search(r"(?:状态|标识|[a-z_][a-z0-9_]*)\s*(?:为|等于|[=:：])\s*['\"]?\d", request, re.I)
        if raw["op"] == "eq" and status_matches and (
            not explicit_code or any(str(item["value"]) == str(raw.get("value")) for item in status_matches)
        ):
            # 候选字段不同，已知需求仍是同一张表的存续范围，用户必须明确选择。
            filters.append({**options[0]["selection"], "confirmed": False})
            _bind_active_scope_review(uncertainties)
            title = "采用哪个筛选口径？" if len(options) > 1 else "请确认存续筛选口径"
            add_question(f"filters.{index}", title, options[:100], uncertainty=_ACTIVE_SCOPE_REVIEW)
            questions[-1]["remember_scope"] = "active_status"
            continue
        meanings = {field.get("field_cn") for field in matches if field.get("field_cn")}
        alternatives = [field for field in fields if field in matches or (meanings and field.get("field_cn") in meanings)]
        intent_labels = {entry["label"] for field in alternatives for entry in dictionary_options(field)
                         if len(entry["label"]) >= 2 and entry["label"] in request}
        # The chosen value can identify a label, but cannot decide between two documented definitions.
        for field in matches:
            intent_labels.update(entry["label"] for entry in dictionary_options(field) if entry["value"] == raw.get("value"))
        choices = []
        for field in alternatives if raw["op"] in {"eq", "neq"} else []:
            for entry in dictionary_options(field):
                if entry["label"] not in intent_labels:
                    continue
                replacement = {"table": role, "field": field["field_name"], "op": raw["op"], "value": entry["value"], "confirmed": True}
                choices.append({"value": str(len(choices)), "label": f"{field.get('field_cn') or field['field_name']}（{field['field_name']}）{operator_names[raw['op']]} {entry['value']}—{entry['label']}",
                                "description": str(field.get("logic") or "依据文档字典，请确认采用此业务口径。")[:240], "selection": replacement})
        normalized = {**raw, "table": role, "confirmed": False}
        if len(matches) == 1:
            normalized["field"] = matches[0]["field_name"]
        if not choices and matches:
            if len(str(raw.get("value", ""))) > 200:
                raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
            for field in matches:
                replacement = {**normalized, "field": field["field_name"], "confirmed": True}
                choices.append({"value": f"confirm-{len(choices)}", "label": f"仅检查{field.get('field_cn') or field['field_name']}（{field['field_name']}）{operator_names[raw['op']]} {raw.get('value', '')}的记录",
                                "description": "请核实该条件和取值含义；文档未必已定义此取值，不能把模型建议当成事实。", "selection": replacement})
        if not choices:
            raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
        filters.append(normalized)
        add_question(f"filters.{index}", "采用哪个筛选口径？", choices[:100])
    if filters or "filters" in draft:
        candidate["filters"] = filters

    raw_join = draft.get("join")
    if raw_join is None:
        return
    if not isinstance(raw_join, dict) or not related_fields:
        raise failure("MODEL_RESPONSE_INVALID", "generate_rule")
    join = {**raw_join, "relationship_confirmed": False, "unmatched_policy": "unresolved"}
    base_names = {field["field_name"] for field in base_fields}
    related_names = {field["field_name"] for field in related_fields}
    on = raw_join.get("on", [])
    valid_on = isinstance(on, list) and 1 <= len(on) <= 4 and all(
        isinstance(pair, dict) and pair.get("left") in base_names and pair.get("right") in related_names for pair in on)
    options = []
    if valid_on:
        options.append({"value": "confirm", "label": "按以下字段对应关系关联：" + "；".join(f"{pair['left']} ↔ {pair['right']}" for pair in on),
                        "description": "文档证实这些字段存在，但同名不代表关联语义已证实；请确认粒度、键含义及同日对应关系。",
                        "selection": {"on": on, "relationship_confirmed": True}})
    else:
        base_keys = [field for field in base_fields if field.get("is_pk") == "Y"]
        related_keys = [field for field in related_fields if field.get("is_pk") == "Y"]
        if len(base_keys) == len(related_keys) == 1:
            proposed = [{"left": base_keys[0]["field_name"], "right": related_keys[0]["field_name"]}]
            join["on"] = proposed
            options.append({"value": "confirm", "label": f"主表{base_keys[0].get('field_cn') or proposed[0]['left']} ↔ 关联表{related_keys[0].get('field_cn') or proposed[0]['right']}",
                            "description": "两侧均为文档主键；仍需确认业务含义一致，不能仅据主键名称认定可关联。",
                            "selection": {"on": proposed, "relationship_confirmed": True}})
    add_question("join.relationship_confirmed", "这两张表按什么关系对应？", options)
    related_date_field, _related_date_choices = resolve_report_date(related_fields)
    join["report_date_field"] = related_date_field
    if not join["report_date_field"]:
        add_question("join.report_date_field", "关联表按哪个业务日期与主表对齐？", date_options(related_fields))
    add_question("join.unmatched_policy", "主表记录找不到同日关联信息时怎么处理？", [
        {"value": "exclude", "label": "本条仅检查有同日关联信息的记录",
         "description": "无关联记录不代表正确，本规则会排除它们；关联完整性需要另行检查。"}])
    candidate["join"] = join
    candidate["can_enable"] = False
