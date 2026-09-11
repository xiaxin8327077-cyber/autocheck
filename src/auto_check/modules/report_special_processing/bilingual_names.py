"""表名/字段名双语规范串解析。

规范格式：单项 ``中文名｜英文名``（全角竖线），多项之间用全角分号 ``；`` 分隔。
解析器只接受规范格式，不做模糊猜测；旧数据（非规范串）由服务层按
"未修改可保留、修改必须升级" 的规则兼容。

分组格式（仅处理字段名使用）：字段按所属处理表分组，组与组之间用双全角分号
``；；`` 分隔，第 N 组对应处理表名的第 N 项；组内仍为规范格式，允许空组
（表示该表暂无关联字段）。规范串禁止空条目，因此旧数据中不会出现 ``；；``，
无分组分隔符的值按单组（历史未关联字段）兼容。
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

BILINGUAL_PART_SEPARATOR = "｜"
BILINGUAL_ITEM_SEPARATOR = "；"
BILINGUAL_GROUP_SEPARATOR = "；；"
MAX_BILINGUAL_ITEMS = 5
MAX_BILINGUAL_PART_LEN = 100
MAX_BILINGUAL_TOTAL_LEN = 4096


class BilingualNameError(ValueError):
    """规范串解析失败；message 面向用户。"""


def parse_bilingual_items(value: str | None) -> tuple[tuple[str, str], ...]:
    """解析规范串为 (中文, 英文) 元组序列；空值返回空元组；非法格式抛 BilingualNameError。"""
    text = str(value or "").strip()
    if not text:
        return ()
    if len(text) > MAX_BILINGUAL_TOTAL_LEN:
        raise BilingualNameError(f"内容最长 {MAX_BILINGUAL_TOTAL_LEN} 个字符")
    items: list[tuple[str, str]] = []
    for chunk in text.split(BILINGUAL_ITEM_SEPARATOR):
        chunk = chunk.strip()
        if not chunk:
            raise BilingualNameError("每项都必须填写，不能有空的条目")
        if BILINGUAL_ITEM_SEPARATOR in chunk:  # pragma: no cover - split 已耗尽
            raise BilingualNameError("条目格式无效")
        if BILINGUAL_PART_SEPARATOR not in chunk:
            raise BilingualNameError("每项必须使用“中文名｜英文名”格式")
        zh, separator, en = chunk.partition(BILINGUAL_PART_SEPARATOR)
        zh = zh.strip()
        en = en.strip()
        if not zh or not en:
            raise BilingualNameError("每项的中英文名都不能为空")
        if BILINGUAL_PART_SEPARATOR in en:
            raise BilingualNameError("名称中不能包含分隔符｜")
        if len(zh) > MAX_BILINGUAL_PART_LEN or len(en) > MAX_BILINGUAL_PART_LEN:
            raise BilingualNameError(f"单个名称最长 {MAX_BILINGUAL_PART_LEN} 个字符")
        items.append((zh, en))
    if not items:
        raise BilingualNameError("内容不能为空")
    if len(items) > MAX_BILINGUAL_ITEMS:
        raise BilingualNameError(f"最多 {MAX_BILINGUAL_ITEMS} 项")
    return tuple(items)


def parse_bilingual_groups(value: str | None) -> tuple[tuple[tuple[str, str], ...], ...]:
    """解析分组规范串。

    - 空值返回空元组。
    - 不含分组分隔符时按单组解析（兼容旧规范串）。
    - 含分组分隔符时逐组解析；允许空组；所有组均为空视为无效。
    """
    text = str(value or "").strip()
    if not text:
        return ()
    if len(text) > MAX_BILINGUAL_TOTAL_LEN:
        raise BilingualNameError(f"内容最长 {MAX_BILINGUAL_TOTAL_LEN} 个字符")
    if BILINGUAL_GROUP_SEPARATOR not in text:
        return (parse_bilingual_items(text),)
    groups: list[tuple[tuple[str, str], ...]] = []
    for chunk in text.split(BILINGUAL_GROUP_SEPARATOR):
        chunk = chunk.strip()
        if not chunk:
            groups.append(())
            continue
        groups.append(parse_bilingual_items(chunk))
    if len(groups) > MAX_BILINGUAL_ITEMS:
        raise BilingualNameError(f"最多 {MAX_BILINGUAL_ITEMS} 个分组")
    if not any(groups):
        raise BilingualNameError("至少需要填写一个字段")
    return tuple(groups)


def serialize_bilingual_groups(groups: Iterable[Sequence[Sequence[str]]]) -> str:
    """按分组规范序列化；每组内部忽略中英文均为空的行，空组保留占位。"""
    return BILINGUAL_GROUP_SEPARATOR.join(
        serialize_bilingual_items(group) for group in groups
    )


def flatten_bilingual_groups(groups: Iterable[Sequence[Sequence[str]]]) -> tuple[tuple[str, str], ...]:
    """把分组条目摊平为单项序列（用于摘要与展示）。"""
    items: list[tuple[str, str]] = []
    for group in groups:
        for item in group:
            zh = str(item[0] if len(item) > 0 else "").strip()
            en = str(item[1] if len(item) > 1 else "").strip()
            items.append((zh, en))
    return tuple(items)


def is_canonical_bilingual(value: str | None) -> bool:
    """判断原值是否为可解析的规范双语串（用于旧值兼容比较）。"""
    try:
        return bool(parse_bilingual_items(value))
    except BilingualNameError:
        return False


def serialize_bilingual_items(items: Sequence[Sequence[str]]) -> str:
    """按规范序列化；输入为 (中文, 英文) 序列，忽略两者均为空的行。"""
    parts = []
    for item in items:
        zh = str(item[0] if len(item) > 0 else "").strip()
        en = str(item[1] if len(item) > 1 else "").strip()
        if not zh and not en:
            continue
        parts.append(f"{zh}{BILINGUAL_PART_SEPARATOR}{en}")
    return BILINGUAL_ITEM_SEPARATOR.join(parts)


def normalize_bilingual_value(value: str | None) -> str:
    """把规范串重新规范化（去首尾空白）；非规范值原样返回，用于新旧比较。"""
    text = str(value or "").strip()
    try:
        if BILINGUAL_GROUP_SEPARATOR in text:
            return serialize_bilingual_groups(parse_bilingual_groups(text))
        items = parse_bilingual_items(text)
    except BilingualNameError:
        return text
    return serialize_bilingual_items(items)


def bilingual_summary(value: str | None, *, which: str = "项") -> str:
    """生成人类摘要：首个中文名，多项追加“等 N 项”；无法解析的旧值返回原串。

    分组串按组摊平后统计（跨表字段合并计数）。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        if BILINGUAL_GROUP_SEPARATOR in text:
            items: Iterable[tuple[str, str]] = flatten_bilingual_groups(parse_bilingual_groups(text))
        else:
            items = parse_bilingual_items(text)
    except BilingualNameError:
        return text
    items = tuple(items)
    if not items:
        return text
    if len(items) == 1:
        return items[0][0]
    return f"{items[0][0]} 等 {len(items)} {which}"


def _display_width(value: str) -> int:
    """按页面近似视觉宽度计数：ASCII/半角为 1，其余字符为 2。"""
    return sum(1 if ord(char) <= 0x00FF else 2 for char in value)


def _bilingual_display_labels(value: str | None) -> tuple[str, ...]:
    """提取字段显示名序列，保留原字段数量与顺序。"""
    text = str(value or "").strip()
    if not text:
        return ()

    labels: list[str] = []
    try:
        groups = parse_bilingual_groups(text)
        labels = [
            str(chinese or english or "").strip()
            for chinese, english in flatten_bilingual_groups(groups)
        ]
    except BilingualNameError:
        for chunk in re.split(r"[\r\n；、，,]+", text):
            item = chunk.strip()
            if not item:
                continue
            chinese, separator, english = item.partition(BILINGUAL_PART_SEPARATOR)
            labels.append((chinese if separator else item).strip() or english.strip())

    return tuple(label for label in labels if label)


def shortest_bilingual_name(value: str | None) -> str:
    """返回最短的字段显示名，规范双语串优先中文，旧串保守兼容。"""
    text = str(value or "").strip()
    if not text:
        return ""

    labels = _bilingual_display_labels(text)

    unique_labels = list(dict.fromkeys(label for label in labels if label))
    if not unique_labels:
        return text
    return min(
        enumerate(unique_labels),
        key=lambda item: (_display_width(item[1]), item[0]),
    )[1]


def shortest_bilingual_summary(value: str | None, *, which: str = "字段") -> str:
    """最短字段名作为摘要主文案，多字段时保留原“等 N 字段”总数提示。"""
    name = shortest_bilingual_name(value)
    if not name:
        return ""
    field_count = len(_bilingual_display_labels(value))
    if field_count <= 1:
        return name
    return f"{name} 等 {field_count} {which}"
