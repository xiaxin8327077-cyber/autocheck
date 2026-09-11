from __future__ import annotations

from typing import Any, Mapping

from .bilingual_names import shortest_bilingual_summary
from .contracts import DIMENSION_LABELS


def ownership_system_field_summary(record: Mapping[str, Any]) -> str:
    """生成待办和通知共用的“维度 · 系统 · 字段”摘要。"""
    dimension = str(record.get("dimension") or "").strip()
    dimension_label = DIMENSION_LABELS.get(dimension, dimension or "未分维度")
    business_system = str(
        record.get("business_system_name_snapshot")
        or record.get("business_system_code")
        or ""
    ).strip()
    field_name = shortest_bilingual_summary(record.get("field_name")) or "未填字段"
    parts = [dimension_label]
    if business_system:
        parts.append(business_system)
    parts.append(field_name)
    return " · ".join(parts)
