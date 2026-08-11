"""Versioned report-navigation statistics contract for trusted modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import re
from threading import RLock
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence
import uuid
from zoneinfo import ZoneInfo

from auto_check.app.module_system.services import BoundService, PlatformServiceSpec


REPORT_NAVIGATION_SERVICE = "platform.report_navigation"
REPORT_NAVIGATION_VERSION = 1
PeriodKind = Literal["week", "month", "quarter", "year"]
TodoActionType = Literal["navigate"]
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_CARD_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CLOSED_FACADE_ERROR = "platform service facade is closed"
_LOGGER = logging.getLogger(__name__)


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


class TodoProviderConflictError(RuntimeError):
    pass


class HistoryProviderConflictError(RuntimeError):
    pass


class ProviderManagedCardError(ValueError):
    pass


@dataclass(frozen=True)
class TodoAction:
    type: TodoActionType
    route: str
    query: Mapping[str, Any]


@dataclass(frozen=True)
class TodoItem:
    id: str
    title: str
    summary: str
    assignee_user_id: str
    module_id: str
    created_at: datetime | None
    action: TodoAction
    initiator: str = ""


@dataclass(frozen=True)
class TodoListRequest:
    current_user: Mapping[str, Any]
    now: datetime


class TodoProvider(Protocol):
    def list_todos(self, request: TodoListRequest) -> Sequence[TodoItem]: ...


@dataclass(frozen=True)
class HistoryItem:
    id: str
    title: str
    summary: str
    actor_user_id: str
    module_id: str
    processed_at: datetime
    initiator: str
    action: TodoAction


@dataclass(frozen=True)
class HistoryListRequest:
    current_user: Mapping[str, Any]
    now: datetime


class HistoryProvider(Protocol):
    def list_history(self, request: HistoryListRequest) -> Sequence[HistoryItem]: ...


@dataclass(frozen=True)
class _Registration:
    card_code: str
    owner: str
    token: str
    provider: CardStatisticsProvider
    semantics_version: int
    include_in_collect: bool = True
    refresh_on_dashboard: bool = False


@dataclass(frozen=True)
class _TodoRegistration:
    provider_id: str
    owner: str
    token: str
    provider: TodoProvider
    semantics_version: int


@dataclass(frozen=True)
class _HistoryRegistration:
    provider_id: str
    owner: str
    token: str
    provider: HistoryProvider
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


class TodoProviderRegistry:
    """In-memory todo provider registry scoped to the process lifetime."""

    def __init__(self) -> None:
        self._registrations: dict[str, _TodoRegistration] = {}
        self._lock = RLock()

    def register(
        self,
        *,
        owner: str,
        provider_id: str,
        provider: TodoProvider,
        semantics_version: int,
    ) -> _ProviderHandle:
        validated_provider_id = validate_provider_id(provider_id)
        validated_version = validate_semantics_version(semantics_version)
        if not hasattr(provider, "list_todos") or not callable(provider.list_todos):
            raise ValueError("todo provider must implement list_todos")
        with self._lock:
            current = self._registrations.get(validated_provider_id)
            if current is not None:
                raise TodoProviderConflictError(
                    "todo provider is already claimed"
                    if current.owner != owner
                    else "todo provider is already active"
                )
            token = uuid.uuid4().hex
            registration = _TodoRegistration(
                validated_provider_id,
                owner,
                token,
                provider,
                validated_version,
            )
            self._registrations[validated_provider_id] = registration
        return _ProviderHandle(
            lambda: self._unregister(validated_provider_id, owner, token)
        )

    def active_registrations(self) -> tuple[_TodoRegistration, ...]:
        with self._lock:
            return tuple(self._registrations.values())

    def _unregister(self, provider_id: str, owner: str, token: str) -> None:
        with self._lock:
            current = self._registrations.get(provider_id)
            if current is None or current.token != token:
                return
            del self._registrations[provider_id]


class HistoryProviderRegistry:
    """In-memory history provider registry scoped to the process lifetime."""

    def __init__(self) -> None:
        self._registrations: dict[str, _HistoryRegistration] = {}
        self._lock = RLock()

    def register(
        self,
        *,
        owner: str,
        provider_id: str,
        provider: HistoryProvider,
        semantics_version: int,
    ) -> _ProviderHandle:
        validated_provider_id = validate_provider_id(provider_id)
        validated_version = validate_semantics_version(semantics_version)
        if not hasattr(provider, "list_history") or not callable(provider.list_history):
            raise ValueError("history provider must implement list_history")
        with self._lock:
            current = self._registrations.get(validated_provider_id)
            if current is not None:
                raise HistoryProviderConflictError(
                    "history provider is already claimed"
                    if current.owner != owner
                    else "history provider is already active"
                )
            token = uuid.uuid4().hex
            registration = _HistoryRegistration(
                validated_provider_id,
                owner,
                token,
                provider,
                validated_version,
            )
            self._registrations[validated_provider_id] = registration
        return _ProviderHandle(
            lambda: self._unregister(validated_provider_id, owner, token)
        )

    def active_registrations(self) -> tuple[_HistoryRegistration, ...]:
        with self._lock:
            return tuple(self._registrations.values())

    def _unregister(self, provider_id: str, owner: str, token: str) -> None:
        with self._lock:
            current = self._registrations.get(provider_id)
            if current is None or current.token != token:
                return
            del self._registrations[provider_id]


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
        include_in_collect: bool = True,
        refresh_on_dashboard: bool = False,
    ) -> _ProviderHandle:
        validated_card_code = validate_card_code(card_code)
        validated_version = validate_semantics_version(semantics_version)
        if not callable(provider):
            raise ValueError("card statistics provider must be callable")
        if not isinstance(include_in_collect, bool):
            raise ValueError("include_in_collect must be a bool")
        if not isinstance(refresh_on_dashboard, bool):
            raise ValueError("refresh_on_dashboard must be a bool")
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
                include_in_collect,
                refresh_on_dashboard,
            )
            self._registrations[validated_card_code] = registration
        return _ProviderHandle(
            lambda: self._unregister(validated_card_code, owner, token)
        )

    def active_registrations(self) -> tuple[_Registration, ...]:
        with self._lock:
            return tuple(self._registrations.values())

    def get_owned_registration(self, *, owner: str, card_code: str) -> _Registration | None:
        validated_card_code = validate_card_code(card_code)
        with self._lock:
            current = self._registrations.get(validated_card_code)
            if current is None or current.owner != owner:
                return None
            return current

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
        include_in_collect: bool = True,
        refresh_on_dashboard: bool = False,
    ) -> _ProviderHandle:
        with self._lock:
            self._require_open()
            handle = self._service.register_card_provider(
                owner=self._owner,
                card_code=card_code,
                provider=provider,
                semantics_version=semantics_version,
                include_in_collect=include_in_collect,
                refresh_on_dashboard=refresh_on_dashboard,
            )
            self._handles.append(handle)
            return handle

    def refresh_card_provider(self, *, card_code: str) -> dict[str, Any]:
        with self._lock:
            self._require_open()
            owner = self._owner
        return self._service.refresh_card_provider(owner=owner, card_code=card_code)

    def register_todo_provider(
        self,
        *,
        provider_id: str,
        provider: TodoProvider,
        semantics_version: int,
    ) -> _ProviderHandle:
        with self._lock:
            self._require_open()
            handle = self._service.register_todo_provider(
                owner=self._owner,
                provider_id=provider_id,
                provider=provider,
                semantics_version=semantics_version,
            )
            self._handles.append(handle)
            return handle

    def register_history_provider(
        self,
        *,
        provider_id: str,
        provider: HistoryProvider,
        semantics_version: int,
    ) -> _ProviderHandle:
        with self._lock:
            self._require_open()
            handle = self._service.register_history_provider(
                owner=self._owner,
                provider_id=provider_id,
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


def validate_provider_id(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, str) or not _PROVIDER_ID.fullmatch(value):
        raise ValueError("todo provider id is invalid")
    return value


def validate_semantics_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("semantics version must be a positive integer")
    return value


def validate_todo_action(action: Any, *, label: str = "todo") -> TodoAction:
    if not isinstance(action, TodoAction):
        raise ValueError(f"{label} action is invalid")
    if action.type != "navigate":
        raise ValueError(f"{label} action type is invalid")
    if not isinstance(action.route, str) or not action.route.strip():
        raise ValueError(f"{label} action route is invalid")
    if not isinstance(action.query, Mapping):
        raise ValueError(f"{label} action query is invalid")
    query = {str(key): item for key, item in action.query.items()}
    return TodoAction("navigate", action.route.strip(), query)


def validate_todo_item(value: Any) -> TodoItem:
    if not isinstance(value, TodoItem):
        raise ValueError("todo item is invalid")
    if not isinstance(value.id, str) or not value.id.strip():
        raise ValueError("todo id is invalid")
    if not isinstance(value.title, str) or not value.title.strip():
        raise ValueError("todo title is invalid")
    if not isinstance(value.summary, str):
        raise ValueError("todo summary is invalid")
    if not isinstance(value.assignee_user_id, str) or not value.assignee_user_id.strip():
        raise ValueError("todo assignee is invalid")
    if not isinstance(value.module_id, str) or not value.module_id.strip():
        raise ValueError("todo module id is invalid")
    if not isinstance(value.initiator, str):
        raise ValueError("todo initiator is invalid")
    created_at = value.created_at
    if created_at is not None:
        created_at = normalize_aware_datetime(created_at)
    action = validate_todo_action(value.action, label="todo")
    return TodoItem(
        value.id.strip(),
        value.title.strip(),
        value.summary,
        value.assignee_user_id.strip(),
        value.module_id.strip(),
        created_at,
        action,
        value.initiator,
    )


def validate_history_item(value: Any) -> HistoryItem:
    if not isinstance(value, HistoryItem):
        raise ValueError("history item is invalid")
    if not isinstance(value.id, str) or not value.id.strip():
        raise ValueError("history id is invalid")
    if not isinstance(value.title, str) or not value.title.strip():
        raise ValueError("history title is invalid")
    if not isinstance(value.summary, str):
        raise ValueError("history summary is invalid")
    if not isinstance(value.actor_user_id, str) or not value.actor_user_id.strip():
        raise ValueError("history actor is invalid")
    if not isinstance(value.module_id, str) or not value.module_id.strip():
        raise ValueError("history module id is invalid")
    if not isinstance(value.initiator, str):
        raise ValueError("history initiator is invalid")
    processed_at = normalize_aware_datetime(value.processed_at)
    action = validate_todo_action(value.action, label="history")
    return HistoryItem(
        value.id.strip(),
        value.title.strip(),
        value.summary,
        value.actor_user_id.strip(),
        value.module_id.strip(),
        processed_at,
        value.initiator,
        action,
    )


def collect_todo_payloads(
    registry: TodoProviderRegistry,
    *,
    current_user: Mapping[str, Any] | None,
    now: datetime,
) -> list[dict[str, Any]]:
    user_id = str((current_user or {}).get("id") or "").strip()
    request = TodoListRequest(current_user=dict(current_user or {}), now=now)
    items: list[TodoItem] = []
    for registration in registry.active_registrations():
        try:
            raw_items = registration.provider.list_todos(request)
            if raw_items is None:
                continue
            if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
                raise ValueError("todo provider result must be a sequence")
            for raw in raw_items:
                item = validate_todo_item(raw)
                if item.assignee_user_id == user_id:
                    items.append(item)
        except Exception:
            _LOGGER.exception(
                "todo provider failed: provider_id=%s owner=%s",
                registration.provider_id,
                registration.owner,
            )
    items.sort(
        key=lambda item: item.created_at or datetime.min.replace(tzinfo=SHANGHAI_TZ),
        reverse=True,
    )
    return [todo_item_payload(item) for item in items]


def todo_item_payload(item: TodoItem) -> dict[str, Any]:
    created_at = ""
    if item.created_at is not None:
        created_at = item.created_at.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "module_id": item.module_id,
        "created_at": created_at,
        "initiator": item.initiator,
        "action": {
            "type": item.action.type,
            "route": item.action.route,
            "query": dict(item.action.query),
        },
    }


def history_item_payload(item: HistoryItem) -> dict[str, Any]:
    processed_at = item.processed_at.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "module_id": item.module_id,
        "processed_at": processed_at,
        "initiator": item.initiator,
        "action": {
            "type": item.action.type,
            "route": item.action.route,
            "query": dict(item.action.query),
        },
    }


def collect_history_payloads(
    registry: HistoryProviderRegistry,
    *,
    current_user: Mapping[str, Any] | None,
    now: datetime,
) -> list[dict[str, Any]]:
    user_id = str((current_user or {}).get("id") or "").strip()
    request = HistoryListRequest(current_user=dict(current_user or {}), now=now)
    items: list[HistoryItem] = []
    for registration in registry.active_registrations():
        try:
            raw_items = registration.provider.list_history(request)
            if raw_items is None:
                continue
            if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
                raise ValueError("history provider result must be a sequence")
            for raw in raw_items:
                item = validate_history_item(raw)
                if item.actor_user_id == user_id:
                    items.append(item)
        except Exception:
            _LOGGER.exception(
                "history provider failed: provider_id=%s owner=%s",
                registration.provider_id,
                registration.owner,
            )
    items.sort(key=lambda item: item.processed_at, reverse=True)
    return [history_item_payload(item) for item in items]


def paginate_items(
    items: Sequence[Any],
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size != 10:
        raise ValueError("page_size must be 10")
    if isinstance(page, bool) or not isinstance(page, int):
        raise ValueError("page must be an integer")
    requested_page = 1 if page < 1 else page
    total = len(items)
    start = (requested_page - 1) * page_size
    if start >= total:
        page_items: list[Any] = []
    else:
        page_items = list(items[start : start + page_size])
    return {
        "items": page_items,
        "total": total,
        "page": requested_page,
        "page_size": page_size,
    }


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
