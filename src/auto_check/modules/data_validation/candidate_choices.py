"""文档内真实候选对象的确定性发现：同义指标的项目/合同粒度差异转为可选项。

只做本地文档证据匹配，不调用模型、不读取业务库、不编造表字段。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .contracts import PBC_REPORT_CATEGORIES, PBC_SHARED_CATEGORY
from .query_spec import type_family

_PROJECT_GRAIN = re.compile(r"项目")
_CONTRACT_GRAIN = re.compile(r"合同|合约|协议")
TARGET_SELECT = re.compile(
    r"无法确定.{0,40}(?:规模|余额|指标|对象|字段)"
    r"|对应多个字段|多个候选|目标对象不明确|选择哪个(?:对象|字段|口径)|哪个(?:对象|字段|口径)",
)
# 真正的未决关注点：整句保留，不因同时出现日期措辞而误删，也不让伪日期问题漏网。
PROTECTED_UNCERTAINTY = re.compile(
    r"币种|单位|截止|跨期|范围|关联|汇总|聚合|例外|筛选|粒度",
)
DATE_MECHANISM = re.compile(
    r"(?:未指定|未明确|尚未确认)?(?:业务日期|报送日期|报告日期|校验日期)(?:口径)?"
    r"|是否需(?:要)?(?:按|用)?(?:特定|具体)?(?:业务)?日期(?:数据|过滤|筛选)",
)
_PARENTHETICAL = re.compile(r"[（(][^）)]*[）)]")
_PUNCTUATION = re.compile(r"[\s　,，、/·\-_]")


def normalize_comment(value: Any) -> str:
    """去掉括号说明与标点空白，保留可比的业务短语。"""
    return _PUNCTUATION.sub("", _PARENTHETICAL.sub("", str(value or "")))


def semantic_core(left: Any, right: Any) -> str:
    """两个中文标签的最长公共连续业务短语（用于有界相关判断）。"""
    first, second = normalize_comment(left), normalize_comment(right)
    if not first or not second:
        return ""
    best = ""
    previous = [""] * len(second)
    for char_left in first:
        current = [""] * len(second)
        for index, char_right in enumerate(second):
            if char_left == char_right:
                current[index] = (previous[index - 1] if index else "") + char_left
                if len(current[index]) > len(best):
                    best = current[index]
        previous = current
    return best


def field_label(field: dict[str, Any]) -> str:
    return str(
        field.get("field_cn") or field.get("comment")
        or field.get("field_name") or field.get("column_name") or ""
    )


def document_category(scope, categories: list[dict]) -> dict | None:
    if not scope:
        return None
    codes = {PBC_SHARED_CATEGORY if code in PBC_REPORT_CATEGORIES else code for code in scope}
    return next((item for item in categories if codes == {item["code"]}), None)


def requested_category_codes(request: str, categories: list[dict]) -> set[str]:
    compact = re.sub(r"\s+", "", request).casefold()
    codes = set()
    for item in categories:
        for name in (item["name"], item["code"]):
            label = re.sub(r"\s+", "", name).casefold()
            if not label:
                continue
            if name.isascii():
                if re.search(r"(?<![a-z0-9_])" + re.escape(name.strip()) + r"(?![a-z0-9_])", request, re.I):
                    codes.add(item["code"])
            elif label in compact:
                codes.add(item["code"])
    return codes


def check_without_category_prefix(request: str, categories: list[dict]) -> str:
    names = sorted({value for category in categories for value in (category["name"], category["code"]) if value}, key=len, reverse=True)
    if not names:
        return request
    return re.sub(r"^\s*(?:按照|按|在)?(?:" + "|".join(map(re.escape, names)) + r")(?:分类)?(?:中)?(?:的|[，,:：])\s*", "", request, count=1, flags=re.I)


def other_category_expression(expression: dict, base_fields: list[dict], other_fields: list[dict], request: str) -> dict | None:
    """Rebind every operand by its actual document label; a shared physical column alone proves nothing."""
    by_name = {field["field_name"]: field for field in base_fields}
    bound = []
    explicit_subject = False
    for part in expression.get("conditions", [expression]):
        clone = dict(part)
        sides = ["left", "right"] if part.get("right") and part.get("right_type", "field") == "field" else ["left"]
        for side in sides:
            field = by_name.get(part.get(side))
            if not field or not field.get("field_cn") or part.get("right_table", "base") != "base":
                return None
            name = field["field_cn"].strip()
            explicit_subject |= name in request or bool(re.search(r"(?<![A-Za-z0-9_])" + re.escape(field["field_name"]) + r"(?![A-Za-z0-9_])", request))
            matches = [other for other in other_fields if str(other.get("field_cn") or "").strip() == name
                       and type_family(other.get("data_type")) == type_family(field.get("data_type"))]
            if len(matches) != 1:
                return None
            clone[side] = matches[0]["field_name"]
        bound.append(clone)
    if not explicit_subject or not bound:
        return None
    return {**expression, "conditions": bound} if "conditions" in expression else bound[0]


def confirm_option_category(candidate: dict, meta: dict, category: dict, table: dict) -> None:
    scope = str(table.get("scope") or table.get("dimension") or "")
    question = f"是否按「{category['name']}」的 {table['table_name']} 检查？"
    candidate.setdefault("questions", []).append({"id": "report_category", "text": question, "uncertainty": question,
        "options": [{"value": category["code"], "label": category["name"] + (f"（{scope}）" if scope else "")}]})
    candidate.setdefault("uncertainties", []).append(question)
    candidate["uncertainty_resolutions"] = [""] * len(candidate["uncertainties"])
    candidate.update(report_category=category["code"], report_category_name=category["name"])
    meta["table_label"] = f"{category['name']} · {meta['table_label']}"
    meta["match_reason"] = f"报送分类为{category['name']}" + (f"，文档范围为{scope}" if scope else "")


def counterpart_fields(fields: list[dict[str, Any]], base_field: dict[str, Any]) -> list[dict[str, Any]]:
    """有界语义匹配：要求真实非空中文标签存在 >=3 字公共业务短语。

    既覆盖英文名不同、中文限定不同的项目/合同/余额字段，也排除仅英文同名
    但中文含义不同的字段。
    """
    base_label = field_label(base_field)
    if not normalize_comment(base_label):
        return []
    matches = []
    for field in fields:
        other_label = field_label(field)
        if normalize_comment(other_label) and len(semantic_core(base_label, other_label)) >= 3:
            matches.append(field)
    return matches


def grain_label(table: dict[str, Any]) -> str:
    """优先结构化 dimension；合同依据明确时不因 source_desc 提到项目而反转。"""
    dimension = str(table.get("dimension") or "").strip()
    if dimension:
        components = re.split(r"[，,；;]", dimension, maxsplit=1)[0].strip()
        if re.search(r"[＋+、]", components):
            return components
        has_project = bool(_PROJECT_GRAIN.search(dimension))
        has_contract = bool(_CONTRACT_GRAIN.search(dimension))
        if has_project and not has_contract:
            return "项目级"
        if has_contract and not has_project:
            return "合同级"
        if has_project and has_contract:
            return ""
    # source_desc 只作来源叙述，不参与粒度定性；标题/范围冲突时保持未知。
    text = " ".join(
        str(table.get(key) or "")
        for key in ("table_name_cn", "scope", "table_name")
    )
    has_project = bool(_PROJECT_GRAIN.search(text))
    has_contract = bool(_CONTRACT_GRAIN.search(text))
    if has_project and has_contract:
        return ""
    if has_contract:
        return "合同级"
    if has_project:
        return "项目级"
    return ""


def document_display(table: dict, related: dict | None = None) -> dict:
    """Display facts from the resolved document tables, outside the executable definition."""
    return {"table_name_cn": table.get("table_name_cn") or "", "grain": grain_label(table),
            "document_scope": table.get("scope") or "", "related_table_name_cn": (related or {}).get("table_name_cn") or ""}


def recommended_index(grains: list[str], request_text: str) -> int | None:
    """需求明确提到“项目”时优先项目级；否则不做主观推荐。"""
    if "项目" in request_text:
        for index, grain in enumerate(grains):
            if grain == "项目级":
                return index
    return None


def option_id(source_id: str, table_name: str, field_name: str, request_text: str,
              mapping_version: str = "", expression_key: str = "") -> str:
    raw = (
        f"{source_id}|{mapping_version}|{table_name}|{field_name}"
        f"|{expression_key}|{request_text}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def difference_lines(table_label: str, grain: str, field_label: str, base_field_label: str = "") -> list[str]:
    lines = [f"目标对象：{table_label}"]
    if grain:
        lines.append(f"数据粒度：{grain}")
    if field_label:
        lines.append(f"比较字段：{field_label}")
    if base_field_label and field_label:
        core = semantic_core(base_field_label, field_label)
        lines.append(
            f"口径差异：与基准仅共享{('“' + core + '”') if core else '少量文字'}，"
            "规模/余额等限定不同，不声明二者等价",
        )
    return lines


def target_ambiguity_indices(values: list[str]) -> list[int]:
    """仅把可由真实候选选择解决的目标歧义整句转为方案差异。"""
    indices = []
    for index, value in enumerate(values):
        text = str(value)
        if PROTECTED_UNCERTAINTY.search(text):
            continue
        if TARGET_SELECT.search(text):
            indices.append(index)
    return indices


def resolve_uncertainty_clauses(values: list[str], *, has_candidates: bool, has_period: bool) -> list[str]:
    """分句消解：目标选择/日期机制问法有事实答案时消除，真未决整句保留。

    先按 ；。 分句；含币种/单位/截止/跨期/范围/关联/汇总/例外/筛选/粒度的句子
    永不整句删除，只在其中去除目标/日期子句。其余句子若整体是目标选择或
    平台日期机制问法（含其字段清单片段），整句消除。
    """
    resolved: list[str] = []
    for value in values:
        kept_sentences: list[str] = []
        for sentence in re.split(r"[；;。]", str(value)):
            sentence = sentence.strip()
            if not sentence:
                continue
            if PROTECTED_UNCERTAINTY.search(sentence):
                # 含真实未决关注点的句子整体保留，避免把单位/范围与日期混在一起时误删。
                kept_sentences.append(sentence)
                continue
            if has_candidates and TARGET_SELECT.search(sentence):
                continue
            if has_period and DATE_MECHANISM.search(sentence):
                continue
            inner = [
                clause.strip() for clause in re.split(r"[，,]", sentence)
                if clause.strip()
                and not (has_candidates and TARGET_SELECT.search(clause))
                and not (has_period and DATE_MECHANISM.search(clause))
            ]
            if inner:
                kept_sentences.append("，".join(inner))
        joined = "；".join(kept_sentences)
        if joined:
            resolved.append(joined)
    return resolved
