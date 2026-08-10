from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Mapping


class RecordStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    VOIDED = "voided"


STATUS_LABELS = {
    RecordStatus.DRAFT: "草稿",
    RecordStatus.PENDING: "待确认",
    RecordStatus.PROCESSING: "处理中",
    RecordStatus.COMPLETED: "已完成",
    RecordStatus.VOIDED: "已作废",
}

DIMENSIONS = frozenset({"project", "fund", "asset", "finance"})

DIMENSION_LABELS = {
    "project": "项目端",
    "fund": "资金端",
    "asset": "资产端",
    "finance": "财务端",
}


class DomainError(RuntimeError):
    status = 400
    code = "invalid_request"
    message = "请求参数无效"

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        *,
        fields: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.code = code or self.code
        self.message = message or self.message
        self.fields = dict(fields or {})


class ValidationError(DomainError):
    pass


class PermissionDeniedError(DomainError):
    status = 403
    code = "record_edit_forbidden"
    message = "无权修改该记录"


class RecordNotFoundError(DomainError):
    status = 404
    code = "record_not_found"
    message = "记录不存在"


class VersionConflictError(DomainError):
    status = 409
    code = "record_version_conflict"
    message = "记录已被其他人更新，请刷新后重试"


class InvalidTransitionError(DomainError):
    status = 409
    code = "invalid_status_transition"
    message = "处理状态流转无效"


class PlatformUnavailableError(DomainError):
    status = 503
    code = "platform_service_unavailable"
    message = "平台目录服务暂时不可用，请稍后重试"


@dataclass(frozen=True)
class RecordInput:
    save_mode: str
    report_process_codes: tuple[str, ...]
    reports: tuple[str, ...] = ()
    summary: str = ""
    processing_content: str = ""
    processing_script: str | None = None
    report_period: date | None = None
    special_handling_at: datetime | None = None
    handler_user_id: str | None = None
    row_version: int | None = None
    dimension: str | None = None
    governance_owner_user_id: str | None = None
    table_name: str | None = None
    field_name: str | None = None
    value_before: str | None = None
    value_after: str | None = None

    @property
    def report_process_code(self) -> str:
        return self.report_process_codes[0] if self.report_process_codes else ""


@dataclass(frozen=True)
class PageQuery:
    page: int = 1
    page_size: int = 10
    sort: str = "special_handling_at_desc"
    filters: Mapping[str, Any] = field(default_factory=dict)


def public_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): public_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [public_value(item) for item in value]
    return value
