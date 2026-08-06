from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .contracts import STATUS_LABELS, RecordStatus


SHANGHAI = ZoneInfo("Asia/Shanghai")
EXPORT_HEADERS = (
    "所属报送期",
    "关联报送",
    "涉及报表",
    "处理摘要",
    "处理说明",
    "处理脚本",
    "处理时间",
    "处理人",
    "状态",
)
MAX_EXPORT_ROWS = 5_000


def _period_text(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "").strip()


def _datetime_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        local = value
        if local.tzinfo is not None:
            local = local.astimezone(SHANGHAI).replace(tzinfo=None)
        return local.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value)
    return (
        text.replace("T", " ")
        .split(".", 1)[0]
        .replace("+08:00", "")
        .replace("Z", "")
        .strip()
    )


def _reports_text(value: Any) -> str:
    if not value:
        return ""
    names: list[str] = []
    for item in value:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, Mapping):
            name = str(item.get("report_name") or item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if name:
            names.append(name)
    return "、".join(names)


def _status_text(value: Any) -> str:
    code = str(value or "").strip()
    try:
        return STATUS_LABELS[RecordStatus(code)]
    except ValueError:
        return code


def export_rows(records: Sequence[Mapping[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for record in records:
        rows.append(
            [
                _period_text(record.get("report_period")),
                str(record.get("report_process_name_snapshot") or record.get("report_process_name") or ""),
                _reports_text(record.get("reports")),
                str(record.get("summary") or ""),
                str(record.get("processing_content") or ""),
                str(record.get("processing_script") or ""),
                _datetime_text(record.get("special_handling_at")),
                str(
                    record.get("handler_display_name_snapshot")
                    or record.get("handler_username_snapshot")
                    or ""
                ),
                _status_text(record.get("status")),
            ]
        )
    return rows


def build_export_xlsx(records: Sequence[Mapping[str, Any]], *, title: str = "报表特殊处理") -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "报表特殊处理"
    sheet.append(list(EXPORT_HEADERS))
    for row in export_rows(records):
        sheet.append(row)
    sheet.freeze_panes = "A2"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
