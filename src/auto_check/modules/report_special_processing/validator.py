from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .contracts import PageQuery, RecordInput, RecordStatus, ValidationError


SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_REPORTS = 50
MAX_SCRIPT_BYTES = 512 * 1024
MAX_REQUEST_BYTES = 1024 * 1024
SORTS = frozenset(
    {"special_handling_at_desc", "updated_at_desc", "created_at_desc"}
)
_RECORD_FIELDS = frozenset(
    {
        "save_mode",
        "report_process_code",
        "report_period",
        "reports",
        "summary",
        "processing_content",
        "processing_script",
        "special_handling_at",
        "handler_user_id",
        "row_version",
    }
)


def _error(field: str, message: str = "字段无效") -> ValidationError:
    return ValidationError(fields={field: message})


def _text(value: Any, field: str, maximum: int, *, required: bool) -> str:
    if value is None:
        if required:
            raise _error(field, "不能为空")
        return ""
    if not isinstance(value, str):
        raise _error(field)
    normalized = value.strip()
    if required and not normalized:
        raise _error(field, "不能为空")
    if len(normalized) > maximum:
        raise _error(field, f"最多 {maximum} 个字符")
    return normalized


def _optional_date(value: Any, field: str, *, required: bool) -> date | None:
    if value is None or value == "":
        if required:
            raise _error(field, "不能为空")
        return None
    if not isinstance(value, str):
        raise _error(field)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _error(field, "日期格式无效") from None


def _optional_datetime(value: Any, field: str, *, required: bool) -> datetime | None:
    if value is None or value == "":
        if required:
            raise _error(field, "不能为空")
        return None
    if not isinstance(value, str):
        raise _error(field)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _error(field, "时间格式无效") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(field, "时间必须包含时区")
    return parsed.astimezone(SHANGHAI)


def _reports(value: Any, *, required: bool) -> tuple[str, ...]:
    if value is None:
        value = []
    if not isinstance(value, list) or len(value) > MAX_REPORTS:
        raise _error("reports")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise _error("reports")
        name = re.sub(r"\s+", " ", item.strip())
        if not name or len(name) > 200:
            raise _error("reports")
        normalized.append(name)
    if required and not normalized:
        raise _error("reports", "至少填写一项")
    if len(set(normalized)) != len(normalized):
        raise _error("reports", "报表名称不能重复")
    return tuple(normalized)


def validate_record_input(payload: Mapping[str, Any]) -> RecordInput:
    if not isinstance(payload, Mapping) or any(key not in _RECORD_FIELDS for key in payload):
        raise ValidationError()
    save_mode = payload.get("save_mode")
    if save_mode not in {"draft", "record"}:
        raise _error("save_mode")
    formal = save_mode == "record"
    process_code = _text(payload.get("report_process_code"), "report_process_code", 64, required=True)
    script = payload.get("processing_script")
    if script is None or script == "":
        script = None
    elif not isinstance(script, str) or len(script.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise _error("processing_script", "脚本最大 512 KiB")
    handler = _text(payload.get("handler_user_id"), "handler_user_id", 64, required=formal) or None
    row_version = payload.get("row_version")
    if row_version is not None and (type(row_version) is not int or row_version < 1):
        raise _error("row_version")
    return RecordInput(
        save_mode=save_mode,
        report_process_code=process_code,
        reports=_reports(payload.get("reports"), required=formal),
        summary=_text(payload.get("summary"), "summary", 200, required=formal),
        processing_content=_text(
            payload.get("processing_content"), "processing_content", 20_000, required=formal
        ),
        processing_script=script,
        report_period=_optional_date(payload.get("report_period"), "report_period", required=formal),
        special_handling_at=_optional_datetime(
            payload.get("special_handling_at"), "special_handling_at", required=formal
        ),
        handler_user_id=handler,
        row_version=row_version,
    )


def validate_page_query(query: Mapping[str, str]) -> PageQuery:
    try:
        page = int(query.get("page", "1"))
        page_size = int(query.get("page_size", "20"))
    except (TypeError, ValueError):
        raise ValidationError() from None
    sort = str(query.get("sort", "special_handling_at_desc"))
    if page < 1 or not 1 <= page_size <= 100 or sort not in SORTS:
        raise ValidationError()
    keyword = str(query.get("keyword", "")).strip()
    if len(keyword) > 100:
        raise _error("keyword")
    filters = {
        key: value
        for key in (
            "report_process_code",
            "report_period",
            "status",
            "handler_user_id",
            "keyword",
            "special_handling_from",
            "special_handling_to",
        )
        if (value := query.get(key)) not in {None, ""}
    }
    if "status" in filters and filters["status"] not in {item.value for item in RecordStatus}:
        raise _error("status")
    return PageQuery(page=page, page_size=page_size, sort=sort, filters=filters)


def validate_action(payload: Mapping[str, Any], *, require_reason: bool = False) -> tuple[int, str]:
    if not isinstance(payload, Mapping):
        raise ValidationError()
    version = payload.get("row_version")
    if type(version) is not int or version < 1:
        raise _error("row_version")
    reason = _text(payload.get("reason"), "reason", 500, required=require_reason)
    return version, reason
