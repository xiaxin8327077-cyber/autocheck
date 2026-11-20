"""AI 确认问题的业务化文案。

这里只生成展示文字；选项值、真实字段键和校验语义仍由调用方原样保留。
"""

from __future__ import annotations

from typing import Any
import re


def table_label(value: Any, fallback: str) -> str:
    label = str(value or '').strip()
    return re.sub(r'\s*[（(][^()（）]*\.ktr[）)]\s*$', '', label, flags=re.I) or fallback


def field_label(field: dict[str, Any] | None) -> str:
    field = field or {}
    return str(
        field.get("field_cn") or field.get("comment")
        or field.get("field_name") or field.get("column_name") or ""
    )


def _field_for(fields: list[dict[str, Any]], name: Any) -> dict[str, Any] | None:
    wanted = str(name or "")
    return next(
        (field for field in fields
         if str(field.get("field_name") or field.get("column_name") or "") == wanted),
        None,
    )


def _qualified(table: str, name: Any) -> str:
    text = str(name or "")
    return f"{table}.{text}" if table and text else text


def join_relationship_label(
    base_fields: list[dict[str, Any]],
    related_fields: list[dict[str, Any]],
    on: list[dict[str, Any]],
    *,
    date_label: str = "",
    base_label: str = "本次检查的信息",
    related_label: str = "对应信息",
) -> str:
    """用真实中文标签说明两侧字段和同一报送日期，不展示物理名。"""
    pairs = []
    for pair in on:
        left = field_label(_field_for(base_fields, pair.get("left"))) or str(pair.get("left") or "")
        right = field_label(_field_for(related_fields, pair.get("right"))) or str(pair.get("right") or "")
        pairs.append(f"{base_label}的「{left}」对应{related_label}的「{right}」")
    return "；".join(pairs) + f"，并限定为同一{date_label or '报送日期'}"


def join_relationship_description(
    base_fields: list[dict[str, Any]],
    related_fields: list[dict[str, Any]],
    on: list[dict[str, Any]],
    *,
    date_label: str = "",
    base_table: str = "",
    related_table: str = "",
) -> str:
    """补充依据保留物理表和字段名，主标题不展示。"""
    basis = "、".join(
        f"{_qualified(base_table, pair.get('left'))} ↔ {_qualified(related_table, pair.get('right'))}"
        for pair in on
    )
    return (
        f"文档已证实上述字段都存在，还需要核实它们是否指向同一个业务对象；"
        f"请确认两侧记录确实属于同一对象，并按同一{date_label or '报送日期'}对应。"
        f"技术依据：{basis}。"
    )


def join_unmatched_question(base_label: str = "本次检查的信息", related_label: str = "对应信息") -> str:
    return f"{base_label}找不到同一报送日期的{related_label}时，本次怎么处理？"


def join_unmatched_option(right_aggregate: Any = "") -> dict[str, str]:
    """缺关联记录必须如实说明暂不检查或待核查，不能暗示算通过。"""
    if str(right_aggregate or "") == "sum":
        return {
            "value": "review",
            "label": "找不到同日汇总明细的记录列为待核查（不能视为通过）",
            "description": "这些记录不会被当作通过；执行结果会把缺少同日汇总明细的主表记录列为待核查。",
        }
    return {
        "value": "exclude",
        "label": "本次暂不检查这些记录，需另行核查（不能视为通过）",
        "description": (
            "本条只检查能找到上述同日信息的记录；其余记录本次不检查，"
            "也不代表符合要求，缺少对应信息的原因请另行核查。"
        ),
    }


def business_key_question(options: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "business_key",
        "text": "核查结果里，用哪个编号方便你查找记录？",
        "options": options,
    }


def business_key_option(name: Any, label: Any = "") -> dict[str, str]:
    value = str(name or "")
    caption = str(label or "") or value
    return {
        "value": value,
        "label": caption,
        "description": (
            f"选择后，核查结果会用「{caption}」标出需要核实的是哪条记录；"
            f"该字段只用于结果定位，不改变校验条件。技术字段：{value}。"
        ),
    }
