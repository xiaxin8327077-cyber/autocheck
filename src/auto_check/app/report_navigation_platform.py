"""Versioned report-navigation statistics contract for trusted modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from threading import RLock
from typing import Any, Callable, Literal, Protocol
import uuid
from zoneinfo import ZoneInfo

from auto_check.app.module_system.services import BoundService, PlatformServiceSpec


REPORT_NAVIGATION_SERVICE = "platform.report_navigation"
REPORT_NAVIGATION_VERSION = 1
PeriodKind = Literal["week", "month", "quarter", "year"]
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_CARD_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CLOSED_FACADE_ERROR = "platform service facade is closed"


@dataclass(frozen=True)
class ReportProcess:
    code: str
    name: str
    order: int
    active: bool


@dataclass(frozen=True)
class CardStatisticsRequest:
    card_code: str
    period_kind: PeriodKind
    period_start: datetime
    period_end_exclusive: datetime
    previous_period_start: datetime
    previous_period_end_exclusive: datetime
    as_of: datetime


@dataclass(frozen=True)
class CardStatisticsResult:
    total: int
    completed: int
    incomplete: int
    previous_completed: int
    generated_at: datetime
    semantics_version: int


class CardStatisticsProvider(Protocol):
    def __call__(self, request: CardStatisticsRequest) -> CardStatisticsResult: ...


class CardProviderConflictError(RuntimeError):
    pass


class ProviderManagedCardError(ValueError):
    pass


@dataclass(frozen=True)
class _Registration:
    card_code: str
    owner: str
    token: str
    provider: CardStatisticsProvider
    semantics_version: int


class _ProviderHandle:
    def __init__(self, close_callback: Callable[[], None]) -> None:
        self._close_callback = close_callback
        self._closed = False
        self._lock = RLock()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._close_callback()


class CardProviderRegistry:
    """In-process provider registry backed by persistent ownership claims."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._registrations: dict[str, _Registration] = {}
        self._lock = RLock()

    def register(
        self,
        *,
        owner: str,
        card_code: str,
        provider: CardStatisticsProvider,
        semantics_version: int,
    ) -> _ProviderHandle:
        validated_card_code = validate_card_code(card_code)
        validated_version = validate_semantics_version(semantics_version)
        if not callable(provider):
            raise ValueError("card statistics provider must be callable")
        with self._lock:
            current = self._registrations.get(validated_card_code)
            if current is not None:
                raise CardProviderConflictError(
                    "card statistics provider is already claimed"
                    if current.owner != owner
                    else "card statistics provider is already active"
                )
            token = uuid.uuid4().hex
            claimed = self._store.claim_card_provider(
                validated_card_code,
                owner,
                token,
                validated_version,
            )
            if not claimed:
                raise CardProviderConflictError(
                    "card statistics provider is already claimed"
                )
            registration = _Registration(
                validated_card_code,
                owner,
                token,
                provider,
                validated_version,
            )
            self._registrations[validated_card_code] = registration
        return _ProviderHandle(
            lambda: self._unregister(validated_card_code, owner, token)
        )

    def active_registrations(self) -> tuple[_Registration, ...]:
        with self._lock:
            return tuple(self._registrations.values())

    def is_current(self, card_code: str, token: str) -> bool:
        with self._lock:
            current = self._registrations.get(card_code)
            return current is not None and current.token == token

    def apply_if_current(
        self, registration: _Registration, callback: Callable[[], None]
    ) -> bool:
        with self._lock:
            current = self._registrations.get(registration.card_code)
            if current is None or current.token != registration.token:
                return False
            return callback() is not False

    def _unregister(self, card_code: str, owner: str, token: str) -> None:
        with self._lock:
            current = self._registrations.get(card_code)
            if current is None or current.token != token:
                return
            del self._registrations[card_code]
            self._store.deactivate_card_provider(card_code, owner, token)


class _ReportNavigationFacade:
    def __init__(self, service: Any, owner: str) -> None:
        self._service = service
        self._owner = owner
        self._handles: list[_ProviderHandle] = []
        self._closed = False
        self._lock = RLock()

    def list_report_processes(self) -> tuple[ReportProcess, ...]:
        with self._lock:
            self._require_open()
        return self._service.list_report_processes()

    def register_card_provider(
        self,
        *,
        card_code: str,
        provider: CardStatisticsProvider,
        semantics_version: int,
    ) -> _ProviderHandle:
        with self._lock:
            self._require_open()
            handle = self._service.register_card_provider(
                owner=self._owner,
                card_code=card_code,
                provider=provider,
                semantics_version=semantics_version,
            )
            self._handles.append(handle)
            return handle

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError(_CLOSED_FACADE_ERROR)

    def _close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            handles = tuple(self._handles)
            self._handles.clear()
        for handle in handles:
            handle.close()


def validate_card_code(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, str) or not _CARD_CODE.fullmatch(value):
        raise ValueError("card code is invalid")
    return value


def validate_semantics_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("semantics version must be a positive integer")
    return value


def validate_statistics_result(
    value: Any, *, semantics_version: int
) -> CardStatisticsResult:
    if not isinstance(value, CardStatisticsResult):
        raise ValueError("provider result is invalid")
    for count in (
        value.total,
        value.completed,
        value.incomplete,
        value.previous_completed,
    ):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("provider counts must be non-negative integers")
    if value.total != value.completed + value.incomplete:
        raise ValueError("provider total must equal completed plus incomplete")
    if value.semantics_version != semantics_version:
        raise ValueError("provider semantics version mismatch")
    generated_at = normalize_aware_datetime(value.generated_at)
    return CardStatisticsResult(
        value.total,
        value.completed,
        value.incomplete,
        value.previous_completed,
        generated_at,
        value.semantics_version,
    )


def normalize_aware_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("provider datetimes must be timezone-aware")
    return value.astimezone(SHANGHAI_TZ)


def create_report_navigation_service(service: Any) -> PlatformServiceSpec:
    def bind(owner: str) -> BoundService:
        facade = _ReportNavigationFacade(service, owner)
        return BoundService(value=facade, close=facade._close)

    return PlatformServiceSpec(
        name=REPORT_NAVIGATION_SERVICE,
        version=REPORT_NAVIGATION_VERSION,
        binder=bind,
    )
