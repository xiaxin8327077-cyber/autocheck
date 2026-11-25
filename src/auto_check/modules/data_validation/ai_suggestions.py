"""通用 AI 建议：只依据授权文档事实与当前候选，不调用模型、不读取业务数据。

建议用于人工核实与后续 preview，不自动创建或启用规则，也不进入主规则门禁。
模型输出只作为线索：引用必须逐条命中真实文档，支持程度由引擎能力保守重算。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Iterable

from .ai_service import model_expression, refine_candidate
from .candidate_choices import field_label, grain_label, semantic_core
from .contracts import AppError
from .document_evidence import referenced_fields
from .formula import is_arithmetic
from .query_grounding import dictionary_options, documented_aggregate_join, is_period_date_field, resolve_report_date
from .query_samples import filter_matches
from .query_spec import COMPARISON_OPS, MAX_FILTERS, UNARY_OPS, comparison_conditions, is_finite_number, type_family, _validate_filter_value
from .semantic_grounding import _document_codes, _explicit_filter, _Unbound

CATEGORIES = (
    "coverage_gap",
    "consistency",
    "dictionary",
    "integrity",
    "period",
    "type_semantics",
    "unsupported_requirement",
)
KINDS = (
    "field_compare_unary",
    "field_compare_binary",
    "filter_and",
    "two_table_exists",
    "aggregate_consistency",
    "unique",
    "cross_table_exists",
    "enum",
    "review",
)
SUPPORT_LEVELS = ("supported", "needs_confirmation", "unsupported")
PROVENANCES = ("model", "document")

MAX_TITLE_LENGTH = 120
MAX_REASON_LENGTH = 400
MAX_ITEM_LENGTH = 200
MAX_ITEMS = 6
MAX_REFERENCES = 16
MAX_SUGGESTIONS = 10

CategoryTableSelector = Callable[[list[dict], set[str]], list[dict]]

# 只识别明确的运算意图声明（结构化操作或 SQL 聚合函数），不识别中文业务词，
# 避免把“汇总表字段非空”“累计金额比较”等既存列误判为需要聚合。
_DECLARED_AGGREGATION = re.compile(
    r"\b(?:sum|avg|count|min|max|median|stddev|variance|aggregate|aggregation|group\s+by)\b",
    re.I | re.ASCII,
)
_WHITESPACE = re.compile(r"\s+")

_CATEGORY_PRIORITY = {
    "unsupported_requirement": 0,
    "consistency": 1,
    "coverage_gap": 2,
    "integrity": 3,
    "dictionary": 4,
    "period": 5,
    "type_semantics": 6,
}


def _bounded_text(value: Any, limit: int) -> str:
    return _WHITESPACE.sub(" ", str(value if value is not None else "").strip())[:limit]


def _model_text(value: Any, limit: int) -> str:
    """模型自由文本只接受字符串；其他类型视为缺失，不崩溃。"""
    return _bounded_text(value, limit) if isinstance(value, str) else ""


def _key_text(value: Any) -> str:
    return _WHITESPACE.sub("", str(value if value is not None else ""))


def _normalize_name(value: Any) -> str:
    # 只做去首尾空白；不去引号、反引号，避免宽容到绕过白名单。
    return str(value if value is not None else "").strip()


def _string_list(value: Any) -> list[str]:
    """逐条容错：只接收 str 或 str 列表/元组；嵌套结构与非字符串直接忽略。"""
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = _bounded_text(item, MAX_ITEM_LENGTH)
        if text and text not in result:
            result.append(text)
        if len(result) >= MAX_ITEMS:
            break
    return result


class _DocumentIndex:
    """授权活动文档的真实表/字段白名单索引。"""

    def __init__(self, tables: Any, fields_by_table: Any) -> None:
        self.tables_by_name: dict[str, dict[str, Any]] = {}
        self.documents_by_name: dict[str, list[dict]] = {}
        for table in tables if isinstance(tables, list) else []:
            if not isinstance(table, dict):
                continue
            name = _normalize_name(table.get("table_name"))
            if name:
                self.tables_by_name[name.lower()] = table
                self.documents_by_name.setdefault(name.lower(), []).append(table)
        self.fields_by_table: dict[int, list[dict[str, Any]]] = {}
        self.fields_by_key: dict[tuple[int, str], dict[str, Any]] = {}
        for table_id, fields in (fields_by_table or {}).items():
            try:
                key = int(table_id)
            except (TypeError, ValueError):
                continue
            bucket: list[dict[str, Any]] = []
            for field in fields if isinstance(fields, list) else []:
                if not isinstance(field, dict):
                    continue
                name = _normalize_name(field.get("field_name"))
                if not name:
                    continue
                bucket.append(field)
                self.fields_by_key[(key, name.lower())] = field
            self.fields_by_table[key] = bucket

    def table(self, name: Any) -> dict[str, Any] | None:
        return self.tables_by_name.get(_normalize_name(name).lower())

    def table_id(self, table: dict[str, Any]) -> int | None:
        try:
            return int(table.get("id"))
        except (TypeError, ValueError):
            return None

    def fields(self, table: dict[str, Any]) -> list[dict[str, Any]]:
        table_id = self.table_id(table)
        return self.fields_by_table.get(table_id, []) if table_id is not None else []

    def field(self, table: dict[str, Any], name: Any) -> dict[str, Any] | None:
        table_id = self.table_id(table)
        if table_id is None:
            return None
        return self.fields_by_key.get((table_id, _normalize_name(name).lower()))


def _reference(table: dict[str, Any], field: dict[str, Any]) -> dict[str, str]:
    return {
        "table_name": str(table.get("table_name") or ""),
        "field_name": str(field.get("field_name") or ""),
    }


def _references(pairs: Iterable[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for table, field in pairs:
        if not isinstance(table, dict) or not isinstance(field, dict):
            continue
        ref = _reference(table, field)
        if not ref["table_name"] or not ref["field_name"]:
            continue
        key = (ref["table_name"].lower(), ref["field_name"].lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
        if len(result) >= MAX_REFERENCES:
            break
    return result


def _scope_fingerprint(definition: dict[str, Any]) -> str:
    """内部上下文指纹：来源、映射版本、期间、方言、报送分类。不输出到建议。"""
    return "|".join(
        str(definition.get(key) or "")
        for key in ("source_id", "mapping_version", "report_date_field", "dialect", "report_category")
    )


def _model_items(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        for key in ("ai_suggestions", "suggestions"):
            if isinstance(raw.get(key), list):
                return raw[key]
        return []
    if isinstance(raw, list):
        return raw
    return []


def _model_references(
    raw: Any, index: _DocumentIndex, category_codes: set[str] | None, select_category_tables: CategoryTableSelector | None,
) -> tuple[list[dict[str, str]], dict[str, dict | None]] | None:
    """同一物理表的所有引用须出现在同一份授权文档；保留未能唯一定位的文档归属。"""
    if not isinstance(raw, list) or not raw or len(raw) > MAX_REFERENCES:
        return None
    names: dict[str, list[str]] = {}
    ordered: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        table = _normalize_name(item.get("table_name")).lower()
        field = _normalize_name(item.get("field_name")).lower()
        names.setdefault(table, []).append(field)
        ordered.append((table, field))
    documents: dict[str, dict | None] = {}
    canonical = {}
    for name, fields in names.items():
        matches = index.documents_by_name.get(name, [])
        scoped = True
        if category_codes is None:
            matches = matches[-1:]  # 兼容旧的文档建议入口。
        elif len(matches) > 1 and len(category_codes) == 1 and "" not in category_codes and select_category_tables:
            selected = select_category_tables(matches, category_codes)
            scoped = bool(selected)
            matches = selected or matches
        matches = [doc for doc in matches if all(index.field(doc, field) for field in fields)]
        if not matches:
            return None
        # 各文档可能仅标识符大小写不同；选择稳定的显示拼写，不以此选择核验依据。
        for field in fields:
            canonical[name, field] = min(
                (doc["table_name"], index.field(doc, field)["field_name"]) for doc in matches
            )
        documents[name] = matches[0] if len(matches) == 1 and scoped else None
    unique_refs = dict.fromkeys(canonical[key] for key in ordered)
    return [{"table_name": table, "field_name": field} for table, field in unique_refs], documents


def _declared_aggregates(item: dict[str, Any]) -> set[str]:
    """只识别明确声明的聚合运算，不扫描中文业务名词。"""
    operations = item.get("operations")
    if operations is None:
        operations = item.get("ops")
    if operations is None:
        operations = item.get("requires")
    tokens: list[str] = []
    if isinstance(operations, str):
        tokens.append(operations)
    elif isinstance(operations, (list, tuple)):
        tokens.extend(str(value) for value in operations if isinstance(value, str))
    kind = item.get("kind")
    title = item.get("title")
    reason = item.get("reason")
    text = " ".join([
        *tokens,
        kind if isinstance(kind, str) else "",
        title if isinstance(title, str) else "",
        reason if isinstance(reason, str) else "",
    ])
    operations = {match.group().lower() for match in _DECLARED_AGGREGATION.finditer(text)}
    if item.get("requires_aggregation") is True:
        operations.add("aggregate")
    return operations


def _infer_category(item: dict[str, Any], references: list[dict[str, str]], *, model_only: bool) -> str:
    category = item.get("category")
    if category in CATEGORIES and not (model_only and category == "unsupported_requirement"):
        return category
    if len({ref["table_name"].lower() for ref in references}) > 1:
        return "consistency"
    kind = item.get("kind")
    if kind == "unique":
        return "integrity"
    if kind in ("enum", "filter_and"):
        return "dictionary"
    return "coverage_gap"


def _infer_kind(category: str) -> str:
    return {
        "coverage_gap": "field_compare_unary",
        "consistency": "two_table_exists",
        "dictionary": "enum",
        "integrity": "unique",
        "period": "review",
        "type_semantics": "field_compare_binary",
        "unsupported_requirement": "review",
    }.get(category, "review")


def _support_level(*, category: str, kind: str, provenance: str) -> str:
    """supported 只表示引擎能表达，不表示可直接采用或可启用。"""
    if category == "unsupported_requirement":
        return "unsupported"
    if category == "integrity":
        # 文档直接标记完整主键，唯一性可由引擎表达；模型自述不算已确认。
        return "supported" if kind == "unique" and provenance == "document" else "needs_confirmation"
    # 业务必填解释、字典口径、期间、类型语义、跨对象一致性均保守需人工确认。
    return "needs_confirmation"


def _suggestion(
    *,
    category: str,
    kind: str,
    title: str,
    reason: str,
    references: list[dict[str, str]],
    preconditions: list[str],
    limitations: list[str],
    support_level: str,
    provenance: str,
    scope: str = "",
    include_unary_definition: bool = True,
) -> dict[str, Any]:
    item = {
        "id": "",
        "category": category,
        "kind": kind,
        "title": _bounded_text(title, MAX_TITLE_LENGTH),
        "reason": _bounded_text(reason, MAX_REASON_LENGTH),
        "references": references[:MAX_REFERENCES],
        "preconditions": _string_list(preconditions),
        "support_level": support_level,
        "limitations": _string_list(limitations),
        "provenance": provenance,
        "_scope": scope,
    }
    # 只对完全由真实字段决定的一元非空检查给出受限 definition；不含 SQL。
    if include_unary_definition and kind == "field_compare_unary" and references:
        item["definition"] = {
            "rule_type": "field_compare",
            "table_name": references[0]["table_name"],
            "expression": {"left": references[0]["field_name"], "op": "is_null"},
            "null_policy": "violate",
            "equality_policy": "allow_equal",
        }
    raw = "|".join([
        category,
        kind,
        *[f"{ref['table_name']}.{ref['field_name']}" for ref in item["references"]],
        _key_text(item["title"]),
    ])
    item["id"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return item


def _model_capability_limit(
    references: list[dict[str, str]], tables: dict[str, dict | None], index: _DocumentIndex,
    aggregate: bool, operations: set[str],
) -> str:
    if len(tables) > 2:
        return "当前规则最多支持两张表。"
    sources = {table["data_source_name"] for table in tables.values() if table and table.get("data_source_name")}
    if len(sources) > 1:
        return "当前规则无法跨数据源关联。"
    if not aggregate:
        return ""
    if operations & {"avg", "count", "min", "max", "median", "stddev", "variance"}:
        return "当前汇总比较仅支持右表求和。"
    if any(table is None for table in tables.values()):
        return ""
    numeric_tables = {
        ref["table_name"] for ref in references
        if type_family(index.field(tables[ref["table_name"].lower()], ref["field_name"]).get("data_type")) == "number"
    }
    if len(numeric_tables) != 2:
        return "汇总比较需要主表数值字段和关联明细表数值字段。"
    return ""


def _possible_scope(filters, field):
    if len(filters) == 1 and filters[0]["op"] in UNARY_OPS:
        return True
    for item in filters:
        op, value = item["op"], item["value"]
        if op in ("eq", "in", "is_null"):
            values = value if op == "in" else [value]
            return any(all(filter_matches(f["op"], value, f["value"]) for f in filters) for value in values)
    if field.get("dictionary"):
        return any(all(filter_matches(f["op"], value, f["value"]) for f in filters)
                   for value in [None, *_document_codes(field)])
    if type_family(field.get("data_type")) == "number":
        low = max(((f["value"], f["op"] == "gt") for f in filters if f["op"] in ("gt", "gte")), default=None)
        high = min(((f["value"], f["op"] == "lte") for f in filters if f["op"] in ("lt", "lte")), default=None)
        if low and high and low[0] >= high[0]:
            return low[0] == high[0] and not low[1] and high[1] and all(
                filter_matches(f["op"], low[0], f["value"]) for f in filters)
    return True


def _scope_replacements(raw, index, category_codes, select_category_tables, confirmed_fields):
    if raw == []:
        return [], ""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_FILTERS or any(
            not isinstance(item, dict) or not {"table_name", "field_name", "op"} <= item.keys() for item in raw):
        raise _Unbound("建议更换的筛选条件格式不完整。")
    binding = _model_references(raw, index, category_codes, select_category_tables)
    if binding is None:
        raise _Unbound("建议更换的筛选字段缺少文档依据。")
    _, documents = binding
    replacements, labels, groups = [], [], {}
    for item in raw:
        doc = documents[_normalize_name(item["table_name"]).lower()]
        field = index.field(doc, item["field_name"]) if doc else None
        if not field or (doc["table_name"], field["field_name"]) not in confirmed_fields:
            raise _Unbound("建议更换的筛选字段应对应已核实的主方案范围。")
        raw_filter = {"field": field["field_name"], "op": item["op"], **({"value": item["value"]} if "value" in item else {})}
        bound = _explicit_filter(raw_filter, {"base": {field["field_name"]: field}})
        replacement = {**_reference(doc, field), "op": bound["op"], "value": bound["value"]}
        if replacement in replacements:
            continue
        replacements.append(replacement)
        groups.setdefault((doc["table_name"], field["field_name"]), (field, []))[1].append(bound)
        dictionary = {option["value"]: option["label"] for option in dictionary_options(field)}
        values = bound["value"] if isinstance(bound["value"], list) else [bound["value"]]
        text = "、".join(dictionary.get(value, str(value)) for value in values if value is not None)
        operators = {"eq": "：", "in": "：", "neq": "不等于", "not_in": "排除", "gt": "大于", "gte": "大于等于",
                     "lt": "小于", "lte": "小于等于", "is_null": "为空", "is_not_null": "非空", "contains": "包含",
                     "not_contains": "不包含", "contains_any": "包含任一", "not_contains_any": "不包含任一"}
        labels.append((field_label(field) or field["field_name"]) + operators.get(bound["op"], "：") + text)
    if any(not _possible_scope(filters, field) for field, filters in groups.values()):
        raise _Unbound("建议更换后的同一字段筛选条件无法同时满足，请核实适用范围。")
    return replacements, "，".join(labels)


def confirmed_scope_fields(candidates):
    result = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        definition = (candidate.get("preview") or {}).get("definition") or candidate
        owners = {"base": definition.get("table_name"), "related": (definition.get("join") or {}).get("table_name")}
        result.update((owners.get(f.get("table", "base")), f["field"])
                      for f in definition.get("filters") or [] if isinstance(f, dict)
                      and f.get("confirmed") is True and isinstance(f.get("field"), str))
    return result


def scope_declaration_missing(suggestion, confirmed_fields):
    refs = suggestion.get("references")
    if ("scope_replacements" in suggestion or suggestion.get("kind") == "aggregate_consistency"
            or not isinstance(refs, list)):
        return False
    fields = {(_normalize_name(table).lower(), name.lower()) for table, name in confirmed_fields}
    return any((_normalize_name(ref.get("table_name")).lower(), _normalize_name(ref.get("field_name")).lower()) in fields
               for ref in refs if isinstance(ref, dict))


def valid_check_target_structure(target):
    return (isinstance(target, dict) and isinstance(target.get("table_name"), str)
            and isinstance(target.get("expression"), dict) and bool(target["expression"]))


def check_target_missing(suggestion):
    return (bool(suggestion.get("scope_replacements"))
            and suggestion.get("kind") in ("field_compare_unary", "field_compare_binary")
            and not valid_check_target_structure(suggestion.get("check_target")))


def _bound_check_target(raw, index, documents, references, kind):
    if not isinstance(raw, dict) or not isinstance(raw.get("expression"), dict):
        raise _Unbound("请补充建议独立的检查字段、异常条件和比较值。")
    base = documents.get(_normalize_name(raw.get("table_name")).lower())
    related_name = _normalize_name(raw.get("related_table_name")).lower()
    related = documents.get(related_name) if related_name else None
    if base is None or related_name and (related is None or base == related):
        raise _Unbound("请核实建议检查指标的真实文档表及其归属。")
    def columns(doc):
        return [{**field, "column_name": field["field_name"]} for field in (index.fields(doc) if doc else [])]

    try:
        refined = refine_candidate({"rule_type": "field_compare", "expression": raw["expression"]},
                                   columns=columns(base), related_columns=columns(related), dialect="", existing=[])
        if refined.get("uncertainties"):
            raise _Unbound("请核实建议检查指标的真实字段。")
        expression = refined["expression"]
        terms = comparison_conditions(refined)
        for term in terms:
            if is_arithmetic(term) or term["op"] in UNARY_OPS:
                continue
            field = index.field(base, term["left"])
            if term.get("right_type") == "value":
                _validate_filter_value({"op": term["op"], "value": term["right"]}, field["data_type"])
            else:
                right = index.field(related if term.get("right_table") == "related" else base, term["right"])
                if not right or type_family(field.get("data_type")) != type_family(right.get("data_type")):
                    raise _Unbound("建议中参与比较的指标类型不一致。")
    except AppError as exc:
        raise _Unbound("请核实建议的检查字段、比较操作和取值类型。") from exc
    fields = referenced_fields({"expression": expression})
    owners = {"base": base["table_name"], "related": related["table_name"] if related else None}
    actual = {(owners[role], name) for role, names in fields.items() for name in names}
    cited = {(ref["table_name"], ref["field_name"]) for ref in references}
    if (not actual or not actual <= cited
            or kind == "field_compare_unary" and any(term["op"] not in UNARY_OPS for term in terms)):
        raise _Unbound("建议检查条件必须使用建议所引用的真实指标并符合所声明的检查类型。")
    return {"table_name": base["table_name"], "expression": expression,
            **({"related_table_name": related["table_name"]} if fields["related"] else {})}


def _has_check_target_alias(item):
    return (isinstance(item, dict) and item.get("kind") in ("field_compare_unary", "field_compare_binary")
            and isinstance(item.get("expression"), dict) and not valid_check_target_structure(item.get("check_target")))


def _normalize_check_target_alias(item, index, documents, references):
    expression = model_expression(item["expression"])
    fields = referenced_fields({"expression": expression})
    refs_by_table = {}
    for ref in references:
        refs_by_table.setdefault(ref["table_name"], set()).add(ref["field_name"].lower())

    def owner(names):
        names = {name.lower() for name in names}
        matches = [table for table, refs in refs_by_table.items() if names <= refs]
        return matches[0] if names and len(matches) == 1 else None

    base = owner(fields["base"])
    related = owner(fields["related"])
    if not base or fields["related"] and (not related or related == base):
        return item
    target = {"table_name": base, "expression": expression}
    if related:
        target["related_table_name"] = related
    try:
        target = _bound_check_target(target, index, documents, references, item["kind"])
    except _Unbound:
        return item
    return {**item, "check_target": target}


def normalize_suggestion_check_targets(items, *, tables, fields_by_table, candidates, select_category_tables=None):
    """Bind a typed expression returned at the suggestion level to its documented operands."""
    if not any(_has_check_target_alias(item) for item in items):
        return items
    index = _DocumentIndex(tables, fields_by_table)
    category_codes = {str(candidate.get("report_category") or "") for candidate in candidates}
    normalized = []
    for item in items:
        binding = (_model_references(item.get("references"), index, category_codes, select_category_tables)
                   if _has_check_target_alias(item) else None)
        if binding:
            references, documents = binding
            item = _normalize_check_target_alias(item, index, documents, references)
        normalized.append(item)
    return normalized


def _model_suggestion(
    item: Any, index: _DocumentIndex, category_codes: set[str] | None, select_category_tables: CategoryTableSelector | None,
    confirmed_fields=(),
) -> dict[str, Any] | None:
    model_only = category_codes is not None
    if not isinstance(item, dict):
        return None
    title = _model_text(item.get("title"), MAX_TITLE_LENGTH) or _model_text(
        item.get("reason"), MAX_TITLE_LENGTH,
    )
    if not title:
        return None
    reason = _model_text(item.get("reason"), MAX_REASON_LENGTH) or title
    binding = _model_references(item.get("references"), index, category_codes, select_category_tables)
    if binding is None:
        return None
    references, documents = binding
    if model_only and _has_check_target_alias(item):
        item = _normalize_check_target_alias(item, index, documents, references)
    ambiguous = [name for name, doc in documents.items() if doc is None]
    category = _infer_category(item, references, model_only=model_only)
    operations = _declared_aggregates(item)
    if operations and not model_only:
        category = "unsupported_requirement"
    kind = item.get("kind") if item.get("kind") in KINDS else _infer_kind(category)
    limitations = _string_list(item.get("limitations"))
    if item.get("sql") not in (None, ""):
        limitations.append("未采纳模型返回的 SQL，建议仅作人工核实")
    preconditions = _string_list(item.get("preconditions"))
    if model_only:
        aggregate = kind == "aggregate_consistency" or bool(operations)
        limit = _model_capability_limit(references, documents, index, aggregate, operations)
        if limit:
            category = "unsupported_requirement"
            limitations.insert(0, limit)
        elif aggregate:
            category, kind = "consistency", "aggregate_consistency"
        if ambiguous:
            preconditions.insert(0, f"需确认同名表 {'、'.join(ambiguous)} 对应的报送文档，再核实字段类型与口径。")
    suggestion = _suggestion(
        category=category,
        kind=kind,
        title=title,
        reason=reason,
        references=references,
        preconditions=preconditions,
        limitations=limitations,
        support_level=_support_level(category=category, kind=kind, provenance="model"),
        provenance="model",
        include_unary_definition=not model_only,
    )
    if ambiguous:
        suggestion["references_ambiguous"] = True
    if model_only:
        if references and not ambiguous and not limit and kind != "review":
            # An invitation to a separate grounded analysis, never an executable definition.
            suggestion["adoption"] = {"operations": sorted(operations), "preconditions": preconditions}
            if item.get("_scope_replacement_repeats_parent"):
                suggestion.pop("adoption", None)
                suggestion["support_level"] = "needs_confirmation"
                suggestion.setdefault("limitations", []).append("建议声明更换范围，但与相关主方案的原范围相同，请核实实际检查目标。")
            elif scope_declaration_missing(item, confirmed_fields):
                suggestion.pop("adoption", None)
                suggestion["support_level"] = "needs_confirmation"
                suggestion.setdefault("limitations", []).append("建议对已选筛选范围是保留还是更换，尚需核实。")
            elif "scope_replacements" in item:
                try:
                    replacements, caption = _scope_replacements(item["scope_replacements"], index, category_codes,
                                                                 select_category_tables, confirmed_fields)
                    raw_target = item.get("check_target")
                    explicit_goal = category != "period" and valid_check_target_structure(raw_target)
                    check_target = (_bound_check_target(item.get("check_target"), index, documents, references, kind)
                                    if (replacements or explicit_goal) and kind in ("field_compare_unary", "field_compare_binary") else None)
                except _Unbound as exc:
                    suggestion.pop("adoption", None)
                    suggestion["support_level"] = "needs_confirmation"
                    suggestion.setdefault("limitations", []).append(str(exc))
                else:
                    suggestion["scope_replacements"] = replacements
                    if check_target:
                        suggestion["check_target"] = check_target
                    if replacements:
                        caption = f"（{caption[:80]}）"
                        suggestion["title"] = title[:MAX_TITLE_LENGTH - len(caption)] + caption
        content = json.dumps(suggestion, ensure_ascii=False, sort_keys=True).encode("utf-8")
        suggestion["id"] = hashlib.sha256(content).hexdigest()[:12]
    return suggestion


def _expression_fields(
    candidate: dict[str, Any], index: _DocumentIndex, table: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """返回 (左字段, 右字段, 右字段所属表)；右字段缺失时右表为 None。"""
    expression = candidate.get("expression") if isinstance(candidate.get("expression"), dict) else {}
    left = index.field(table, expression.get("left"))
    right: dict[str, Any] | None = None
    right_table: dict[str, Any] | None = None
    if expression.get("right_type") == "field" and expression.get("right"):
        if expression.get("right_table") == "related":
            join = candidate.get("join") if isinstance(candidate.get("join"), dict) else None
            other = index.table(join.get("table_name")) if join else None
            if other is not None:
                right = index.field(other, expression.get("right"))
                right_table = other if right is not None else None
        else:
            right = index.field(table, expression.get("right"))
            right_table = table if right is not None else None
    return left, right, right_table


def _zero_flag_state(expression: dict[str, Any]) -> str:
    """NULL 按 0 参与比较时，条件在 0 处是否已判异常：flagged/unflagged/unknown。"""
    if expression.get("right_type") != "value":
        return "unknown"
    op = expression.get("op")
    value = expression.get("right")
    if op not in COMPARISON_OPS or not is_finite_number(value):
        return "unknown"
    if op == "eq":
        return "flagged" if value == 0 else "unflagged"
    if op == "neq":
        return "flagged" if value != 0 else "unflagged"
    if op == "lt":
        return "flagged" if value > 0 else "unflagged"
    if op == "lte":
        return "flagged" if value >= 0 else "unflagged"
    if op == "gt":
        return "flagged" if value < 0 else "unflagged"
    if op == "gte":
        return "flagged" if value <= 0 else "unflagged"
    return "unknown"


def _candidate_field_refs(
    candidate: dict[str, Any], index: _DocumentIndex,
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    table = index.table(candidate.get("table_name"))
    if table is None:
        return [], None
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def add(name: Any, target: dict[str, Any] | None = None) -> None:
        field = index.field(target or table, name)
        if field is not None:
            pairs.append((target or table, field))

    left, right, right_table = _expression_fields(candidate, index, table)
    if left is not None:
        pairs.append((table, left))
    if right is not None and right_table is not None:
        pairs.append((right_table, right))
    for item in candidate.get("filters") or []:
        if isinstance(item, dict) and item.get("table") != "related":
            add(item.get("field"))
    join = candidate.get("join") if isinstance(candidate.get("join"), dict) else None
    if join:
        other = index.table(join.get("table_name"))
        if other is not None:
            for pair in join.get("on") or []:
                if isinstance(pair, dict):
                    add(pair.get("left"))
                    add(pair.get("right"), other)
            add(join.get("report_date_field"), other)
    add(candidate.get("business_key"))
    add(candidate.get("report_date_field"))
    return _references(pairs), table


def _document_suggestions(candidates: Any, index: _DocumentIndex) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        references, table = _candidate_field_refs(candidate, index)
        if not references or table is None:
            continue
        scope = _scope_fingerprint(candidate)
        fields = index.fields(table)
        by_name = {_normalize_name(field.get("field_name")).lower(): field for field in fields}
        expression = candidate.get("expression") if isinstance(candidate.get("expression"), dict) else {}
        unary = expression.get("op") in UNARY_OPS
        left, right, right_table = _expression_fields(candidate, index, table)
        affected = [field for field in (left, right) if field is not None]
        null_policy = str(candidate.get("null_policy") or "")

        # 文档 nullable=N：只作用于实际被该 null_policy 影响的 expression 字段。
        if not unary and null_policy == "skip":
            for field in affected:
                if str(field.get("nullable") or "").strip().upper() != "N":
                    continue
                ref = _reference(table, field)
                label = field_label(field) or ref["field_name"]
                result.append(_suggestion(
                    category="coverage_gap",
                    kind="field_compare_unary",
                    title=f"文档标记“{label}”不可为空，但当前候选跳过空值",
                    reason=(
                        f"{ref['table_name']}.{ref['field_name']} 在文档中 nullable=N；"
                        "当前候选 null_policy=skip 会漏掉空值记录。"
                    ),
                    references=[ref],
                    preconditions=["需确认文档 nullable=N 等价于业务必填"],
                    limitations=["建议仅供人工核实，不自动创建或启用"],
                    support_level="needs_confirmation",
                    provenance="document",
                    scope=scope,
                ))
        elif not unary and null_policy == "zero":
            # 数值比较 NULL 按 0 参与；nullable=N 的完整性约束不因 0 化而视为满足。
            state = _zero_flag_state(expression)
            if state == "unflagged":
                detail = "该比较条件在 0 处未判异常，可能漏掉缺失记录"
            elif state == "flagged":
                detail = "该比较条件在 0 处已判异常，但按 0 参与比较不等于允许原值缺失"
            else:
                detail = "当前无法判断该比较条件在 0 处是否判异常"
            preconditions = [
                "需确认文档 nullable=N 等价于业务必填",
                "需确认按 0 参与比较符合业务口径",
            ]
            if state == "unknown":
                preconditions.append("需确认比较条件在 0 处是否判异常")
            for field in affected:
                if type_family(field.get("data_type")) != "number":
                    continue
                if str(field.get("nullable") or "").strip().upper() != "N":
                    continue
                ref = _reference(table, field)
                label = field_label(field) or ref["field_name"]
                result.append(_suggestion(
                    category="coverage_gap",
                    kind="field_compare_unary",
                    title=f"文档标记“{label}”不可为空，按 0 参与比较不能替代原值完整性",
                    reason=(
                        f"{ref['table_name']}.{ref['field_name']} 在文档中 nullable=N；"
                        f"当前数值比较 null_policy=zero 把 NULL 按 0 参与比较，{detail}；"
                        "文档的完整性约束不因比较时按 0 参与而视为满足。"
                    ),
                    references=[ref],
                    preconditions=preconditions,
                    limitations=[
                        "建议仅供人工核实，不自动创建或启用",
                        "不据此推断该字段必须非负或 NULL 一律非法",
                    ],
                    support_level="needs_confirmation",
                    provenance="document",
                    scope=scope,
                ))

        # 完整主键组：一条建议；超过引用上限时不给伪完整建议。
        primary_key = [
            field for field in fields
            if str(field.get("is_pk") or "").strip().upper() == "Y"
        ]
        if primary_key and len(primary_key) <= MAX_REFERENCES:
            key_refs = [_reference(table, field) for field in primary_key]
            labels = "、".join(field_label(field) or str(field.get("field_name")) for field in primary_key)
            date_field = by_name.get(_normalize_name(candidate.get("report_date_field")).lower())
            period_text = (
                f"期间字段：{candidate.get('report_date_field')}"
                if date_field is not None and type_family(date_field.get("data_type")) == "date"
                else "需确认唯一性检查的期间口径"
            )
            result.append(_suggestion(
                category="integrity",
                kind="unique",
                title=f"文档主键“{labels}”可核实唯一性",
                reason=(
                    f"完整主键组（{labels}）在文档中标记为主键；"
                    "当前候选未包含唯一性检查。"
                ),
                references=key_refs,
                preconditions=[
                    "需确认完整主键组与业务唯一性口径一致",
                    period_text,
                ],
                limitations=[
                    "唯一性可由引擎表达，但 AI 预览当前主要支持 field_compare，需人工采用",
                    "旧 unique 模板不含 report_date 期间过滤，不能视为已按同期间核实",
                ],
                support_level="supported",
                provenance="document",
                scope=scope,
            ))

        # 文档字典：筛选取值需与字典口径确认。
        for item in candidate.get("filters") or []:
            if not isinstance(item, dict) or item.get("table") == "related":
                continue
            field = by_name.get(_normalize_name(item.get("field")).lower())
            if field is None:
                continue
            dictionary = str(field.get("dictionary") or "").strip()
            if not dictionary:
                continue
            label = field_label(field) or str(field.get("field_name") or "")
            result.append(_suggestion(
                category="dictionary",
                kind="enum",
                title=f"筛选字段“{label}”有文档字典，需核对取值",
                reason=(
                    f"{field['field_name']} 的文档字典为“{dictionary[:120]}”，"
                    "当前筛选值需与字典口径确认。"
                ),
                references=[_reference(table, field)],
                preconditions=["需确认筛选取值与文档字典一致"],
                limitations=["建议仅供人工核实，不自动创建或启用"],
                support_level="needs_confirmation",
                provenance="document",
                scope=scope,
            ))

        # 期间：候选必须绑定真实 DATE 字段，不猜测日期字段。
        date_field = by_name.get(_normalize_name(candidate.get("report_date_field")).lower())
        if date_field is None or type_family(date_field.get("data_type")) != "date":
            result.append(_suggestion(
                category="period",
                kind="review",
                title="当前候选缺少可核实的业务日期字段",
                reason="候选未绑定文档中的 DATE 类型业务日期，无法按期筛选记录。",
                references=references[:1],
                preconditions=["需确认代表业务期间的日期字段"],
                limitations=["不猜测日期字段；无日期字段时提示补充文档"],
                support_level="needs_confirmation",
                provenance="document",
                scope=scope,
            ))

        # 类型语义：比较双方类型家族不一致，或数值常量比较非数值字段。
        if not unary and expression:
            if left is not None and right is not None:
                left_family = type_family(left.get("data_type"))
                right_family = type_family(right.get("data_type"))
                if left_family and right_family and left_family != right_family:
                    result.append(_suggestion(
                        category="type_semantics",
                        kind="review",
                        title="比较字段类型家族不一致，需确认口径",
                        reason=(
                            f"{left['field_name']}（{left_family}）与 "
                            f"{right['field_name']}（{right_family}）类型家族不同。"
                        ),
                        references=_references([(table, left), (right_table or table, right)]),
                        preconditions=["需确认两者业务口径与类型转换"],
                        limitations=["建议仅供人工核实"],
                        support_level="needs_confirmation",
                        provenance="document",
                        scope=scope,
                    ))
            elif left is not None and expression.get("right_type") == "value" \
                    and type_family(left.get("data_type")) in ("string", "date"):
                result.append(_suggestion(
                    category="type_semantics",
                    kind="review",
                    title="数值常量比较非数值字段，需确认口径",
                    reason=(
                        f"{left['field_name']} 的文档类型为 "
                        f"{type_family(left.get('data_type'))}，与数值常量比较可能不符口径。"
                    ),
                    references=[_reference(table, left)],
                    preconditions=["需确认该字段可与数值常量比较"],
                    limitations=["建议仅供人工核实"],
                    support_level="needs_confirmation",
                    provenance="document",
                    scope=scope,
                ))

        # 候选自带的超出能力要求：如实转述，不扩大也不缩小。
        unsupported = candidate.get("unsupported_requirements")
        if isinstance(unsupported, (list, tuple)):
            strings = [
                _bounded_text(item, MAX_ITEM_LENGTH)
                for item in unsupported if isinstance(item, str) and str(item).strip()
            ]
            if strings:
                result.append(_suggestion(
                    category="unsupported_requirement",
                    kind="review",
                    title="当前候选包含引擎不支持的要求",
                    reason="；".join(strings)[:MAX_REASON_LENGTH],
                    references=references,
                    preconditions=[],
                    limitations=strings,
                    support_level="unsupported",
                    provenance="document",
                    scope=scope,
                ))

    result.extend(_consistency_suggestions(candidates, index))
    return result


def _consistency_suggestions(candidates: Any, index: _DocumentIndex) -> list[dict[str, Any]]:
    """不同真实对象间共享语义时给出人工核实建议；未知粒度不删除建议。"""
    items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        table = index.table(candidate.get("table_name"))
        if table is None:
            continue
        expression = candidate.get("expression") if isinstance(candidate.get("expression"), dict) else {}
        field = index.field(table, expression.get("left")) if expression.get("left") else None
        if field is not None:
            items.append((table, field))
    result: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for left_index in range(len(items)):
        for right_index in range(left_index + 1, len(items)):
            left_table, left_field = items[left_index]
            right_table, right_field = items[right_index]
            if left_table is right_table and left_field is right_field:
                continue
            core = semantic_core(field_label(left_field), field_label(right_field))
            if len(core) < 3:
                continue
            references = _references([(left_table, left_field), (right_table, right_field)])
            key = tuple((ref["table_name"].lower(), ref["field_name"].lower()) for ref in references)
            if key in seen:
                continue
            seen.add(key)
            left_grain = grain_label(left_table) or "粒度未标注"
            right_grain = grain_label(right_table) or "粒度未标注"
            result.append(_suggestion(
                category="consistency",
                kind="two_table_exists" if left_table is not right_table else "review",
                title=f"“{core}”在多个真实对象中出现，口径需核实",
                reason=(
                    f"{left_table['table_name']}.{left_field['field_name']} 与 "
                    f"{right_table['table_name']}.{right_field['field_name']} 共享业务语义“{core}”，"
                    "但对象、粒度、单位与币种未证实一致。"
                ),
                references=references,
                preconditions=[
                    "需确认两者业务定义、单位、币种与粒度一致",
                    f"当前粒度：{left_grain} / {right_grain}",
                ],
                limitations=["跨对象一致性仅供人工核实", "需要聚合或一对多汇总时当前引擎不支持"],
                support_level="needs_confirmation",
                provenance="document",
            ))
            if len(result) >= 2:
                return result
    return result


def _same_measure_suggestions(candidates: list[dict[str, Any]], index: _DocumentIndex) -> list[dict[str, Any]]:
    """Only suggest a same-period correspondence backed by keys and explicit metric lineage."""
    def lineage(field):
        return tuple(_key_text(field.get(key)).lower() for key in ("source_table", "source_field"))

    def data_type(field):
        return _key_text(field.get("data_type")).lower()

    def key_types(fields, date):
        return {_normalize_name(field["field_name"]).lower(): data_type(field) for field in fields
                if field.get("is_pk") == "Y" and field["field_name"] != date}

    result = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("rule_type") != "field_compare":
            continue
        table = index.table(candidate.get("table_name"))
        if table is None:
            continue
        field, _, _ = _expression_fields(candidate, index, table)
        dimension, period, source = (_key_text(table.get(key)) for key in ("dimension", "period", "data_source_name"))
        original = lineage(field) if field else ()
        if not field or not (dimension and period and source and all(original)):
            continue
        main_date = candidate.get("report_date_field")
        date_field = index.field(table, main_date)
        if date_field is None or not is_period_date_field(date_field):
            continue
        keys = key_types(index.fields(table), main_date)
        if not keys or not all(keys.values()):
            continue
        for other in index.tables_by_name.values():
            if other is table or tuple(_key_text(other.get(key)) for key in ("dimension", "period", "data_source_name", "scope")) != (
                dimension, period, source, _key_text(table.get("scope")),
            ):
                continue
            fields = index.fields(other)
            other_date, _ = resolve_report_date(fields)
            if not other_date or key_types(fields, other_date) != keys:
                continue
            other_date_field = index.field(other, other_date)
            if not other_date_field or _key_text(field_label(other_date_field)) != _key_text(field_label(date_field)):
                continue
            for counterpart in fields:
                if (lineage(counterpart) != original or data_type(counterpart) != data_type(field)
                        or _key_text(field_label(counterpart)) != _key_text(field_label(field))
                        or _key_text(counterpart.get("logic")) != _key_text(field.get("logic"))):
                    continue
                refs = _references([(table, field), (other, counterpart)])
                label = field_label(field)
                result.append(_suggestion(
                    category="consistency", kind="two_table_exists",
                    title=f"可检查两张表的“{label}”是否一致",
                    reason="两列的文档来源字段、取数逻辑、数据类型及粒度一致，可按对应键核对同期间字段值。",
                    references=refs, preconditions=[],
                    limitations=[f"按同期间（{main_date} ↔ {other_date}）及文档键（{'、'.join(sorted(keys))}）比较匹配记录",
                                 "仅为建议，未读取真实业务行，不自动创建或执行"],
                    support_level="supported", provenance="document", scope=_scope_fingerprint(candidate),
                ))
                if len(result) >= MAX_SUGGESTIONS:
                    return result
    return result


def _scoped_candidate_suggestion(candidates: list[dict[str, Any]], index: _DocumentIndex) -> dict[str, Any] | None:
    """Propose a separate comparison for related metrics with a documented detail grain."""
    if not candidates or not isinstance(candidates[0], dict):
        return None
    primary = candidates[0]
    expression = primary.get("expression") or {}
    request = primary.get("description")
    source = primary.get("source_id")
    if (not request or not source or expression.get("right_type") != "value" or primary.get("join")
            or not primary.get("filters") or any(item.get("table") != "base" or not item.get("confirmed")
                                                 for item in primary["filters"])):
        return None
    owner = index.table(primary.get("table_name"))
    owner_field = index.field(owner, expression.get("left")) if owner else None
    if not owner_field or type_family(owner_field.get("data_type")) != "number" or not primary.get("can_enable"):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("can_enable"):
            continue
        filters = candidate.get("filters") or []
        check = candidate.get("expression") or {}
        if (candidate.get("description") != request or candidate.get("source_id") != source
                or any(check.get(key) != expression.get(key) for key in ("op", "right_type", "right"))
                or not filters or not all(item.get("confirmed") for item in filters)
                or not (candidate.get("preview") or {}).get("sql_preview")):
            continue
        table = index.table(candidate.get("table_name"))
        field = index.field(table, check.get("left")) if table else None
        grain = grain_label(table) if table else ""
        if (not field or table is owner or not grain or grain == grain_label(owner)
                or type_family(field.get("data_type")) != "number"
                or not re.search(r"余额|金额|本金|规模|份额|数量", field_label(field))
                or re.search(r"比例|净值|单价|利率|收益率|平均|单位价值", field_label(field))):
            continue
        join = documented_aggregate_join(owner, index.fields(owner), table, index.fields(table))
        if not join:
            continue
        keys = "、".join(pair["right"] for pair in join["on"])
        owner_label = field_label(owner_field)
        detail_label = field_label(field)
        title = f"核对{owner_label}与{detail_label}合计是否一致"
        suggestion = _suggestion(
            category="consistency", kind="aggregate_consistency", title=title,
            reason=f"按文档中的{keys}和数据日期汇总明细，再与主表对应记录比较。",
            references=_references([(owner, owner_field), (table, field)]),
            preconditions=[], limitations=["沿用主方案的检查范围；缺少一侧数据时提示核实。"],
            support_level="supported", provenance="document", scope=_scope_fingerprint(primary),
        )
        base = primary["preview"]["definition"] if primary.get("preview", {}).get("definition") else primary
        suggestion["definition"] = {
            **{key: base[key] for key in ("source_id", "dialect", "mapping_version", "report_category", "table_name",
                                          "business_key", "report_date_field", "project_context") if key in base},
            "name": title, "description": title, "rule_type": "field_compare", "generation_mode": "ai",
            "expression": {"left": owner_field["field_name"], "right": field["field_name"], "op": "neq",
                           "right_type": "field", "right_table": "related"},
            "filters": [item for item in base.get("filters", []) if item.get("table") == "base"],
            "join": join, "null_policy": "review", "equality_policy": "allow_equal",
            "violation_message": f"{owner_label}与{detail_label}合计不一致，请核实。",
        }
        return suggestion
    return None


def _existing_signatures(existing_rules: Any) -> set[tuple[Any, ...]]:
    signatures: set[tuple[Any, ...]] = set()
    for rule in existing_rules or ():
        if not isinstance(rule, dict):
            continue
        definition = rule.get("definition")
        if not isinstance(definition, dict):
            continue
        scope = _scope_fingerprint(definition)
        table = str(definition.get("table_name") or "").lower()
        rule_type = str(definition.get("rule_type") or "")
        expression = definition.get("expression") if isinstance(definition.get("expression"), dict) else {}
        if rule_type == "field_compare":
            op = expression.get("op")
            if op in UNARY_OPS:
                signatures.add((scope, table, op, str(expression.get("left") or "").lower()))
            elif expression.get("right_type") == "value":
                signatures.add((
                    scope, table, "compare", str(expression.get("left") or "").lower(),
                    str(expression.get("op") or ""), "value", str(expression.get("right")),
                ))
            else:
                signatures.add((
                    scope, table, "compare", str(expression.get("left") or "").lower(),
                    str(expression.get("op") or ""), "field", str(expression.get("right") or "").lower(),
                ))
        elif rule_type == "unique":
            keys = tuple(sorted(str(key).lower() for key in (definition.get("keys") or [])))
            signatures.add((scope, table, "unique", keys))
        elif rule_type == "enum":
            signatures.add((scope, table, "enum", str(definition.get("field") or "").lower()))
        elif rule_type == "not_null":
            signatures.add((scope, table, "is_null", str(definition.get("field") or "").lower()))
        elif rule_type == "cross_table_exists":
            signatures.add((
                scope, table, "cross_table_exists",
                str(definition.get("other_table") or "").lower(),
                str(definition.get("key") or "").lower(),
            ))
        for item in definition.get("filters") or []:
            if isinstance(item, dict):
                signatures.add((
                    scope, table, "filter", str(item.get("field") or "").lower(),
                    str(item.get("op") or ""),
                    json.dumps(item.get("value"), ensure_ascii=False, sort_keys=True),
                ))
    return signatures


def _signature(item: dict[str, Any]) -> tuple[Any, ...] | None:
    references = item.get("references") or []
    if not references:
        return None
    scope = str(item.get("_scope") or "")
    table = str(references[0].get("table_name") or "").lower()
    field = str(references[0].get("field_name") or "").lower()
    if item.get("category") == "coverage_gap" and item.get("kind") == "field_compare_unary":
        return (scope, table, "is_null", field)
    if item.get("kind") == "unique":
        return (scope, table, "unique", tuple(sorted(str(ref.get("field_name") or "").lower() for ref in references)))
    if item.get("kind") == "enum":
        return (scope, table, "enum", field)
    return None


def _dedupe_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(item.get("_scope") or ""),
        item.get("category"),
        item.get("kind") or "",
        tuple((ref["table_name"].lower(), ref["field_name"].lower()) for ref in item.get("references") or []),
        _key_text(item.get("title")),
    )


def _echoes_previewed_request(item: dict[str, Any], request: str, candidates: list[dict[str, Any]]) -> bool:
    """An unchanged task over already previewed fields is not an additional check."""
    def task_text(value: str) -> str:
        # Quoted text can contain meaningful punctuation; do not normalize it or case.
        if not isinstance(value, str) or any(mark in value for mark in ('"', "'", "“", "”", "‘", "’", "「", "」")):
            return ""
        return re.sub(r"[\s,，。；;!?！？]+", "", value)

    key = task_text(request)
    if (not key or task_text(item.get("title", "")) != key or item.get("category") == "period"
            or item.get("kind") not in {"field_compare_unary", "field_compare_binary"}
            or (item.get("adoption") or {}).get("operations")):
        return False
    refs = {(r["table_name"], r["field_name"]) for r in item.get("references") or []}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        preview = candidate.get("preview") or {}
        definition = preview.get("definition")
        if not preview.get("sql_preview") or not isinstance(definition, dict):
            continue
        owners = {"base": definition.get("table_name"), "related": (definition.get("join") or {}).get("table_name")}
        expression = definition.get("expression") or {}
        parts = expression.get("conditions", [expression])
        if not isinstance(parts, list) or any(not isinstance(p, dict) or not isinstance(p.get("left"), str)
                                               or p.get("right_type") == "formula" for p in parts):
            continue
        operands = {(owners["base"], p["left"]) for p in parts}
        operands.update((owners.get(p.get("right_table", "base")), p["right"]) for p in parts
                        if p.get("right_type") == "field" and isinstance(p.get("right"), str))
        used = operands | {(owners.get(f.get("table", "base")), f.get("field")) for f in definition.get("filters") or []}
        if refs and refs <= used and refs & operands:
            return True
    return False


def build_ai_suggestions(
    model_suggestions: Any,
    *,
    tables: list[dict[str, Any]],
    fields_by_table: dict[int, list[dict[str, Any]]],
    candidates: list[dict[str, Any]],
    request_text: str = "",
    limit: int = 3,
    existing_rules: Iterable[dict[str, Any]] = (),
    actionable_only: bool = False,
    default_business_scope: bool = True,
    model_only: bool = False,
    select_category_tables: CategoryTableSelector | None = None,
) -> list[dict[str, Any]]:
    """核实模型建议；兼容旧调用方的文档候选及可采纳筛选。"""
    index = _DocumentIndex(tables, fields_by_table)
    main_refs: set[tuple[str, str]] = set()
    filter_actionable = actionable_only and not model_only
    if filter_actionable:
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("rule_type") != "field_compare":
                continue
            table = index.table(candidate.get("table_name"))
            if table is None:
                continue
            left, _, _ = _expression_fields(candidate, index, table)
            if left is not None:
                ref = _reference(table, left)
                main_refs.add((ref["table_name"].lower(), ref["field_name"].lower()))
        if not main_refs:
            return []
    try:
        capacity = int(limit)
    except (TypeError, ValueError):
        capacity = 3
    capacity = max(0, min(capacity, MAX_SUGGESTIONS))
    if capacity == 0:
        return []
    existing = set() if model_only else _existing_signatures(existing_rules)

    collected: list[dict[str, Any]] = []
    if filter_actionable and default_business_scope:
        scoped = _scoped_candidate_suggestion(candidates, index)
        if scoped is not None:
            collected.append(scoped)
    category_codes = {str(candidate.get("report_category") or "") for candidate in candidates if isinstance(candidate, dict)}
    confirmed_fields = confirmed_scope_fields(candidates) if model_only else set()
    for item in _model_items(model_suggestions):
        suggestion = _model_suggestion(item, index, category_codes if model_only else None, select_category_tables, confirmed_fields)
        if suggestion is not None:
            collected.append(suggestion)
    if filter_actionable:
        collected.extend(_same_measure_suggestions(candidates, index))
    if not model_only:
        collected.extend(sorted(
            _document_suggestions(candidates, index),
            key=lambda item: _CATEGORY_PRIORITY.get(item.get("category"), 9),
        ))

    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for suggestion in collected:
        if model_only and _echoes_previewed_request(suggestion, request_text, candidates):
            continue
        if filter_actionable and (
            suggestion.get("support_level") != "supported"
            or not any((ref["table_name"].lower(), ref["field_name"].lower()) in main_refs
                       for ref in suggestion["references"])
        ):
            continue
        key = (suggestion["id"],) if model_only else _dedupe_key(suggestion)
        if key in seen:
            continue
        signature = _signature(suggestion)
        if signature is not None and signature in existing:
            continue
        seen.add(key)
        result.append({name: value for name, value in suggestion.items() if not name.startswith("_")})
        if len(result) >= capacity:
            break
    return result
