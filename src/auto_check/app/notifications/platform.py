"""platform.notification v1 — 可撤销模块门面。"""

from __future__ import annotations

from threading import RLock
from typing import Callable

from auto_check.app.module_system.services import BoundService, PlatformServiceSpec
from auto_check.app.notifications.contracts import (
    NotificationPublishRequest,
    NotificationPublishResult,
)
from auto_check.app.notifications.service import NotificationService

NOTIFICATION_SERVICE = "platform.notification"
NOTIFICATION_SERVICE_VERSION = 1
_CLOSED_FACADE_ERROR = "platform notification facade is closed"


class _NotificationFacade:
    def __init__(self, service: NotificationService, owner: str) -> None:
        self._service = service
        self._owner = owner
        self._closed = False
        self._lock = RLock()

    def publish(self, request: NotificationPublishRequest) -> NotificationPublishResult:
        with self._lock:
            if self._closed:
                raise RuntimeError(_CLOSED_FACADE_ERROR)
            return self._service.publish(self._owner, request)

    def close(self) -> None:
        with self._lock:
            self._closed = True


def create_notification_platform_service(
    service: NotificationService,
) -> PlatformServiceSpec:
    def bind(owner: str) -> BoundService:
        facade = _NotificationFacade(service, owner)
        return BoundService(value=facade, close=facade.close)

    return PlatformServiceSpec(
        name=NOTIFICATION_SERVICE,
        version=NOTIFICATION_SERVICE_VERSION,
        binder=bind,
    )
