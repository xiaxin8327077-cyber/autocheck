from __future__ import annotations

import ipaddress
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Callable, Mapping

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    and_,
    delete,
    func,
    insert,
    select,
)

from .validator import ValidationError

METADATA = MetaData()
IDENTIFIER_TYPE = BigInteger().with_variant(Integer, "sqlite")

RETENTION_DAYS = 30
SUMMARY_HOURS = 24
ALLOWED_RESULTS = frozenset({"success", "partial", "error"})
ALLOWED_BOARDS = frozenset({"report_submission", "reporting_process"})
EXTERNAL_ENDPOINTS = (
    {"path": "/api/external/v1/dashboard-management/boards/report_submission/preview", "board_code": "report_submission", "name": "金融监管报表报送大屏"},
    {"path": "/api/external/v1/dashboard-management/boards/reporting_process/preview", "board_code": "reporting_process", "name": "金融监管报送流程大屏"},
)
PLATFORM_REJECTION_SUMMARIES = {
    "token_missing_or_malformed": (401, "未携带 Token 或 Authorization 格式错误"),
    "token_invalid": (401, "Token 无效"),
    "method_not_allowed": (405, "请求方法不允许"),
    "rate_limit_exceeded": (429, "请求过于频繁，请稍后重试"),
    "external_api_disabled": (503, "外部接口未配置"),
    "rate_limit_unavailable": (503, "外部接口访问频率控制暂时不可用"),
}

EXTERNAL_API_CALLS = Table(
    "dashboard_management_external_api_calls",
    METADATA,
    Column("id", IDENTIFIER_TYPE, primary_key=True, autoincrement=True),
    Column("called_at", DateTime, nullable=False),
    Column("board_code", String(64), nullable=False),
    Column("http_status", Integer, nullable=False),
    Column("result_status", String(16), nullable=False),
    Column("failed_region_count", Integer, nullable=False, default=0),
    Column("duration_ms", BigInteger, nullable=False),
    Column("request_id", String(64), nullable=False),
    Column("caller_ip", String(45), nullable=False),
    Column("error_code", String(64), nullable=True),
    Column("error_message", String(500), nullable=True),
)


@dataclass(frozen=True)
class ExternalApiCallRecord:
    called_at: datetime
    board_code: str
    http_status: int
    result_status: str
    failed_region_count: int
    duration_ms: int
    request_id: str
    caller_ip: str
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ExternalApiCallQuery:
    page: int = 1
    page_size: int = 10
    board_code: str = ""
    result_status: str = ""
    caller_ip: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None


def _query_from_mapping(value: Mapping[str, Any]) -> ExternalApiCallQuery:
    return ExternalApiCallQuery(
        page=int(value.get("page") or 1),
        page_size=int(value.get("page_size") or 10),
        board_code=str(value.get("board_code") or ""),
        result_status=str(value.get("result_status") or ""),
        caller_ip=str(value.get("caller_ip") or ""),
        started_at=value.get("started_at") or None,
        ended_at=value.get("ended_at") or None,
    )


class ExternalApiMonitoringStore:
    """Persistence for authenticated external dashboard API call records."""

    def __init__(self, database) -> None:
        self._database = database

    def record_and_cleanup(self, record: ExternalApiCallRecord, cutoff: datetime) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                delete(EXTERNAL_API_CALLS).where(EXTERNAL_API_CALLS.c.called_at < cutoff)
            )
            connection.execute(insert(EXTERNAL_API_CALLS), {
                "called_at": record.called_at,
                "board_code": record.board_code,
                "http_status": record.http_status,
                "result_status": record.result_status,
                "failed_region_count": record.failed_region_count,
                "duration_ms": record.duration_ms,
                "request_id": record.request_id,
                "caller_ip": record.caller_ip,
                "error_code": record.error_code,
                "error_message": record.error_message,
            })

    def summary(self, since: datetime, cutoff: datetime) -> Mapping[str, Any]:
        self._cleanup(cutoff)
        recent = EXTERNAL_API_CALLS.c.called_at >= since
        with self._database.connect() as connection:
            total = connection.execute(
                select(func.count()).select_from(EXTERNAL_API_CALLS).where(recent)
            ).scalar_one()
            success = connection.execute(
                select(func.count()).select_from(EXTERNAL_API_CALLS).where(
                    recent,
                    EXTERNAL_API_CALLS.c.result_status == "success"
                )
            ).scalar_one()
            partial = connection.execute(
                select(func.count()).select_from(EXTERNAL_API_CALLS).where(
                    recent,
                    EXTERNAL_API_CALLS.c.result_status == "partial"
                )
            ).scalar_one()
            failed = connection.execute(
                select(func.count()).select_from(EXTERNAL_API_CALLS).where(
                    recent,
                    EXTERNAL_API_CALLS.c.result_status == "error"
                )
            ).scalar_one()
            average = connection.execute(
                select(func.avg(EXTERNAL_API_CALLS.c.duration_ms)).select_from(
                    EXTERNAL_API_CALLS
                ).where(recent)
            ).scalar_one()
            last_called = connection.execute(
                select(EXTERNAL_API_CALLS.c.called_at).order_by(
                    EXTERNAL_API_CALLS.c.called_at.desc()
                ).limit(1)
            ).scalar_one_or_none()
            last_success = connection.execute(
                select(EXTERNAL_API_CALLS.c.called_at).select_from(EXTERNAL_API_CALLS).where(
                    EXTERNAL_API_CALLS.c.result_status == "success"
                ).order_by(EXTERNAL_API_CALLS.c.called_at.desc()).limit(1)
            ).scalar_one_or_none()
        return {
            "total": int(total),
            "success": int(success),
            "partial": int(partial),
            "failed": int(failed),
            "average_duration_ms": int(average or 0),
            "last_called_at": last_called,
            "last_success_at": last_success,
        }

    def list_calls(self, query: Mapping[str, Any] | ExternalApiCallQuery, cutoff: datetime) -> Mapping[str, Any]:
        self._cleanup(cutoff)
        parsed = _query_from_mapping(query) if isinstance(query, Mapping) else query
        conditions = []
        if parsed.board_code:
            conditions.append(EXTERNAL_API_CALLS.c.board_code == parsed.board_code)
        if parsed.result_status:
            conditions.append(EXTERNAL_API_CALLS.c.result_status == parsed.result_status)
        if parsed.caller_ip:
            conditions.append(EXTERNAL_API_CALLS.c.caller_ip == parsed.caller_ip)
        if parsed.started_at:
            conditions.append(EXTERNAL_API_CALLS.c.called_at >= parsed.started_at)
        if parsed.ended_at:
            conditions.append(EXTERNAL_API_CALLS.c.called_at <= parsed.ended_at)
        where = and_(*conditions) if conditions else None

        with self._database.connect() as connection:
            total = connection.execute(
                select(func.count()).select_from(EXTERNAL_API_CALLS).where(where)
            ).scalar_one() if where is not None else connection.execute(
                select(func.count()).select_from(EXTERNAL_API_CALLS)
            ).scalar_one()
            page = max(1, parsed.page)
            page_size = max(1, min(100, parsed.page_size))
            total_pages = max(1, (int(total) + page_size - 1) // page_size)
            if page > total_pages:
                page = total_pages
            offset = (page - 1) * page_size
            statement = select(EXTERNAL_API_CALLS).order_by(
                EXTERNAL_API_CALLS.c.called_at.desc(),
                EXTERNAL_API_CALLS.c.id.desc(),
            ).limit(page_size).offset(offset)
            if where is not None:
                statement = statement.where(where)
            rows = connection.execute(statement).mappings().all()

        return {
            "items": [dict(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": int(total),
            "total_pages": total_pages,
        }

    def _cleanup(self, cutoff: datetime) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                delete(EXTERNAL_API_CALLS).where(EXTERNAL_API_CALLS.c.called_at < cutoff)
            )


@dataclass
class ExternalApiCallTrace:
    board_code: str
    caller_ip: str
    request_id: str
    started_at: datetime
    started_tick: float


def _classify(response) -> tuple[str, int, str | None, str | None]:
    body = response.body if isinstance(response.body, Mapping) else {}
    if response.status == 200 and body.get("status") in {"success", "partial"}:
        result = str(body["status"])
        regions = body.get("data", {}).get("regions", [])
        failed = sum(1 for region in regions if region.get("status") == "error")
        return result, failed, None, None
    error = body.get("error", {}) if isinstance(body.get("error"), Mapping) else {}
    return "error", 0, str(error.get("code") or "internal_error"), str(error.get("message") or "系统暂时无法处理该请求")


def _validate_ip(value: str) -> str:
    if not value:
        return ""
    if value == "unknown":
        return value
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        raise ValidationError(f"caller_ip 无效", fields={"caller_ip": "caller_ip 无效"}) from None


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_naive_utc(value).replace(tzinfo=timezone.utc).isoformat()


def _validate_datetime(value: Any, field: str) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _as_naive_utc(value)
    if isinstance(value, str):
        try:
            return _as_naive_utc(datetime.fromisoformat(value))
        except ValueError:
            raise ValidationError(f"{field} 无效", fields={field: f"{field} 无效"}) from None
    raise ValidationError(f"{field} 无效", fields={field: f"{field} 无效"})


class ExternalApiMonitoringService:
    """Domain service for external API call monitoring with 30-day retention."""

    def __init__(
        self,
        store,
        *,
        status_facade,
        logger,
        utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        monotonic_now: Callable[[], float] = monotonic,
    ) -> None:
        self._store = store
        self._status_facade = status_facade
        self._logger = logger
        self._utc_now = utc_now
        self._monotonic_now = monotonic_now

    def begin_call(self, board_code: str, caller_ip: str, request_id: str) -> ExternalApiCallTrace:
        return ExternalApiCallTrace(
            board_code=board_code,
            caller_ip=_validate_ip(caller_ip) or "unknown",
            request_id=request_id,
            started_at=_as_naive_utc(self._utc_now()),
            started_tick=self._monotonic_now(),
        )

    def finish_call(self, trace: ExternalApiCallTrace, response) -> None:
        try:
            result_status, failed_count, error_code, error_message = _classify(response)
            duration_ms = max(
                0,
                math.ceil((self._monotonic_now() - trace.started_tick) * 1000),
            )
            record = ExternalApiCallRecord(
                called_at=trace.started_at,
                board_code=trace.board_code,
                http_status=response.status,
                result_status=result_status,
                failed_region_count=failed_count,
                duration_ms=duration_ms,
                request_id=trace.request_id,
                caller_ip=trace.caller_ip,
                error_code=error_code[:64] if error_code else None,
                error_message=error_message[:500] if error_message else None,
            )
            cutoff = _as_naive_utc(self._utc_now()) - timedelta(days=RETENTION_DAYS)
            self._store.record_and_cleanup(record, cutoff)
        except Exception:
            self._logger.warning("external api call record failed", exc_info=True)

    def record_rejection(self, board_code: str, event: Any, request_id: str) -> None:
        """Persist one sanitized platform-stage rejection for an exact board route."""
        try:
            if board_code not in ALLOWED_BOARDS:
                raise ValueError("unsupported board code")
            summary = PLATFORM_REJECTION_SUMMARIES.get(str(event.error_code))
            if summary is None or event.http_status != summary[0]:
                raise ValueError("unsupported platform rejection")
            duration_ms = event.duration_ms
            if type(duration_ms) is not int or duration_ms < 0:
                raise ValueError("invalid rejection duration")
            safe_request_id = str(request_id)
            if not safe_request_id or len(safe_request_id) > 64:
                raise ValueError("invalid rejection request id")
            now = _as_naive_utc(self._utc_now())
            record = ExternalApiCallRecord(
                called_at=now,
                board_code=board_code,
                http_status=summary[0],
                result_status="error",
                failed_region_count=0,
                duration_ms=duration_ms,
                request_id=safe_request_id,
                caller_ip=_validate_ip(str(event.client_ip)) or "unknown",
                error_code=str(event.error_code)[:64],
                error_message=summary[1],
            )
            self._store.record_and_cleanup(
                record,
                now - timedelta(days=RETENTION_DAYS),
            )
        except Exception:
            self._logger.warning("external api rejection record failed", exc_info=True)

    def monitor_summary(
        self,
        credential_status: Mapping[str, Any] | None = None,
        access_status: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        now = _as_naive_utc(self._utc_now())
        since = now - timedelta(hours=SUMMARY_HOURS)
        cutoff = now - timedelta(days=RETENTION_DAYS)
        stats = self._store.summary(since, cutoff)
        token_configured = self._status_facade.get_status().token_configured
        source = "none"
        token_generated_at = None
        if credential_status is not None:
            configured = credential_status.get("configured", False)
            source = credential_status.get("source", "none")
            token_configured = bool(configured)
            if source == "managed":
                token_generated_at = _utc_iso(credential_status.get("generated_at"))
        # 白名单状态由调用方读取；读取失败时调用方在进入本方法前已转换为 503，
        # 因此这里不会把读取失败错误展示成“未启用”。
        whitelist_enabled = bool((access_status or {}).get("enabled", False))
        whitelist_count = int((access_status or {}).get("count", 0) or 0)
        return {
            "enabled": token_configured,
            "token_configured": token_configured,
            "token_source": source,
            "token_generated_at": token_generated_at,
            "ip_whitelist_enabled": whitelist_enabled,
            "ip_whitelist_count": whitelist_count,
            "endpoints": [dict(item) for item in EXTERNAL_ENDPOINTS],
            "last_called_at": _utc_iso(stats["last_called_at"]),
            "last_success_at": _utc_iso(stats["last_success_at"]),
            "last_24_hours": {
                "total": stats["total"],
                "success": stats["success"],
                "partial": stats["partial"],
                "failed": stats["failed"],
                "average_duration_ms": stats["average_duration_ms"],
            },
            "retention_days": RETENTION_DAYS,
        }

    def list_calls(self, query: Mapping[str, str]) -> Mapping[str, Any]:
        raw_page = query.get("page")
        raw_page_size = query.get("page_size")
        try:
            page = int(raw_page) if raw_page is not None and raw_page != "" else 1
        except (TypeError, ValueError):
            raise ValidationError("page 无效", fields={"page": "page 无效"}) from None
        try:
            page_size = int(raw_page_size) if raw_page_size is not None and raw_page_size != "" else 10
        except (TypeError, ValueError):
            raise ValidationError("page_size 无效", fields={"page_size": "page_size 无效"}) from None
        if page < 1:
            raise ValidationError("page 无效", fields={"page": "page 无效"})
        if page_size < 1 or page_size > 100:
            raise ValidationError("page_size 无效", fields={"page_size": "page_size 无效"})
        board_code = str(query.get("board_code") or "")
        if board_code and board_code not in ALLOWED_BOARDS:
            raise ValidationError("board_code 无效", fields={"board_code": "board_code 无效"})
        result_status = str(query.get("result_status") or "")
        if result_status and result_status not in ALLOWED_RESULTS:
            raise ValidationError("result_status 无效", fields={"result_status": "result_status 无效"})
        caller_ip = _validate_ip(str(query.get("caller_ip") or ""))
        started_at = _validate_datetime(query.get("started_at"), "started_at")
        ended_at = _validate_datetime(query.get("ended_at"), "ended_at")
        if started_at is not None and ended_at is not None and started_at > ended_at:
            raise ValidationError(
                "开始时间不能晚于结束时间",
                fields={"started_at": "开始时间不能晚于结束时间"},
            )
        parsed = ExternalApiCallQuery(
            page=page,
            page_size=page_size,
            board_code=board_code,
            result_status=result_status,
            caller_ip=caller_ip,
            started_at=started_at,
            ended_at=ended_at,
        )
        cutoff = _as_naive_utc(self._utc_now()) - timedelta(days=RETENTION_DAYS)
        result = self._store.list_calls(parsed, cutoff)
        return {
            **result,
            "items": [
                {
                    **item,
                    "called_at": _utc_iso(item.get("called_at")),
                }
                for item in result["items"]
            ],
        }
