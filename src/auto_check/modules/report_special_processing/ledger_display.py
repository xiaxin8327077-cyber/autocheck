"""台账与 Excel 共用的只读展示数据，不改变保存的字段或关联快照。"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .bilingual_names import parse_bilingual_groups


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def display_width(value: str) -> int:
    return sum(1 if ord(char) <= 0xFF else 2 for char in value)


def _legacy_fields(value: Any) -> list[str]:
    text = _text(value).strip()
    if not text:
        return ["未设置字段"]
    try:
        return [zh or en for group in parse_bilingual_groups(text) for zh, en in group]
    except ValueError:
        return [text]


def change_groups(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    structured = record.get("structured_content")
    tables = structured.get("tables") if isinstance(structured, Mapping) else None
    items: list[tuple[list[str], str, str]] = []
    if isinstance(tables, list):
        for table in tables:
            fields = table.get("fields") if isinstance(table, Mapping) else None
            for field in fields if isinstance(fields, list) else []:
                field = field if isinstance(field, Mapping) else {}
                label = (
                    _text(field.get("chinese_column_name")).strip()
                    or _text(field.get("column_name")).strip()
                    or "未设置字段"
                )
                items.append(([label], _text(field.get("value_before")), _text(field.get("value_after"))))
    else:
        fields = _legacy_fields(record.get("field_name"))
        before, after = _text(record.get("value_before")), _text(record.get("value_after"))
        before_lines, after_lines = before.split("\n"), after.split("\n")
        if len(fields) == len(before_lines) == len(after_lines) and len(fields) > 1:
            items.extend(([field], left, right) for field, left, right in zip(fields, before_lines, after_lines))
        else:
            # 无法可靠对应的旧记录保留完整值，不能猜测字段归属。
            items.append((fields, before, after))
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for fields, before, after in items:
        group = groups.setdefault((before, after), {"fields": [], "before": before, "after": after})
        for field in fields:
            if field not in group["fields"]:
                group["fields"].append(field)
    result = list(groups.values()) or [{"fields": ["暂无修改字段"], "before": "", "after": ""}]
    # 按显示宽度从短到长；同宽保持原顺序，前端和导出不依赖宿主区域设置。
    return sorted(result, key=lambda group: display_width("、".join(group["fields"])))


def ledger_display(record: Mapping[str, Any]) -> dict[str, Any]:
    processes = record.get("report_processes") or []
    names = [
        _text(item.get("name")).strip()
        for item in processes if isinstance(item, Mapping) and _text(item.get("name")).strip()
    ] if isinstance(processes, list) else []
    if not names:
        snapshot = _text(record.get("report_process_name_snapshot") or record.get("report_process_name"))
        names = [name.strip() for name in snapshot.split("；") if name.strip()]
    handled_at = record.get("special_handling_at")
    if isinstance(handled_at, datetime):
        if handled_at.tzinfo is not None:
            handled_at = handled_at.astimezone(ZoneInfo("Asia/Shanghai"))
        time_text = handled_at.strftime("%Y-%m-%d %H:%M:%S")
    else:
        time_text = _text(handled_at).replace("T", " ")
        time_text = re.sub(r"\.\d+(?=(?:Z|[+-]\d{2}:?\d{2})?$)", "", time_text)
        time_text = re.sub(r"(?:Z|[+-]\d{2}:?\d{2})$", "", time_text).strip()
    return {
        "change_groups": change_groups(record),
        "process_names": sorted(names, key=display_width),
        "handled_at": time_text,
    }
