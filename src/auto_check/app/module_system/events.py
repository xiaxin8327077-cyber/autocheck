from __future__ import annotations

import json
import re
from dataclasses import dataclass
from threading import RLock
from typing import Callable


_MODULE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_EVENT_NAME_PATTERN = re.compile(r"(system|[a-z][a-z0-9_]*):[a-z][a-z0-9_]*")


def _validate_module_id(owner: str) -> None:
    if not isinstance(owner, str) or not _MODULE_ID_PATTERN.fullmatch(owner):
        raise ValueError("owner must be a valid module namespace")


def _validate_event_name(event_name: str) -> str:
    if not isinstance(event_name, str):
        raise ValueError("event name must use a namespace")
    match = _EVENT_NAME_PATTERN.fullmatch(event_name)
    if match is None:
        raise ValueError("event name must use a namespace")
    return match.group(1)


@dataclass(frozen=True)
class EventDeliveryError:
    owner: str
    message: str


@dataclass(frozen=True)
class EventDeliveryReport:
    delivered: int
    failed: int
    errors: tuple[EventDeliveryError, ...]


@dataclass
class _Subscriber:
    owner: str
    handler: Callable[[object], None]
    active: bool = True


class Subscription:
    """A closeable event subscription."""

    __slots__ = ("_close", "_closed", "_lock")

    def __init__(self, close: Callable[[], None]) -> None:
        self._close = close
        self._closed = False
        self._lock = RLock()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._close()


class EventBus:
    """In-process namespace event notifications with subscriber isolation."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[_Subscriber]] = {}
        self._lock = RLock()

    def subscribe(
        self, event_name: str, handler: Callable[[object], None], owner: str
    ) -> Subscription:
        _validate_event_name(event_name)
        _validate_module_id(owner)
        if not callable(handler):
            raise ValueError("event handler must be callable")
        subscriber = _Subscriber(owner=owner, handler=handler)
        with self._lock:
            subscribers = self._subscribers.setdefault(event_name, [])
            subscribers.append(subscriber)

        def close() -> None:
            with self._lock:
                if not subscriber.active:
                    return
                subscriber.active = False
                if subscriber in subscribers:
                    subscribers.remove(subscriber)
                if not subscribers:
                    self._subscribers.pop(event_name, None)

        return Subscription(close)

    def publish(self, event_name: str, payload: object) -> EventDeliveryReport:
        _validate_event_name(event_name)
        try:
            json.dumps(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("event payload must be JSON serializable") from exc

        delivered = 0
        errors: list[EventDeliveryError] = []
        with self._lock:
            subscribers = tuple(self._subscribers.get(event_name, ()))
        for subscriber in subscribers:
            with self._lock:
                active = subscriber.active
            if not active:
                continue
            try:
                subscriber.handler(payload)
            except Exception as exc:
                errors.append(
                    EventDeliveryError(
                        owner=subscriber.owner,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
            else:
                delivered += 1
        return EventDeliveryReport(delivered=delivered, failed=len(errors), errors=tuple(errors))

    def for_module(self, owner: str) -> ModuleEvents:
        _validate_module_id(owner)
        if owner == "system":
            raise ValueError("system is reserved for platform events")

        def publish_for_owner(event_name: str, payload: object) -> EventDeliveryReport:
            namespace = _validate_event_name(event_name)
            if namespace != owner:
                raise ValueError("module event view can only publish its own namespace")
            return self.publish(event_name, payload)

        def subscribe_for_owner(
            event_name: str, handler: Callable[[object], None]
        ) -> Subscription:
            return self.subscribe(event_name, handler, owner)

        return ModuleEvents(subscribe=subscribe_for_owner, publish=publish_for_owner)


class ModuleEvents:
    """Module-scoped event view that tracks owned subscriptions."""

    __slots__ = ("_publish", "_subscribe", "_subscriptions", "_closed", "_lock")

    def __init__(
        self,
        *,
        subscribe: Callable[[str, Callable[[object], None]], Subscription],
        publish: Callable[[str, object], EventDeliveryReport],
    ) -> None:
        self._subscribe = subscribe
        self._publish = publish
        self._subscriptions: list[Subscription] = []
        self._closed = False
        self._lock = RLock()

    def publish(self, event_name: str, payload: object) -> EventDeliveryReport:
        with self._lock:
            if self._closed:
                raise RuntimeError("module event view is closed")
        return self._publish(event_name, payload)

    def subscribe(self, event_name: str, handler: Callable[[object], None]) -> Subscription:
        subscription = self._subscribe(event_name, handler)
        with self._lock:
            if self._closed:
                subscription.close()
                raise RuntimeError("module event view is closed")
            self._subscriptions.append(subscription)
        return subscription

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscriptions = tuple(self._subscriptions)
            self._subscriptions.clear()
        for subscription in subscriptions:
            subscription.close()
