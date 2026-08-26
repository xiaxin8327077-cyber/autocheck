"""通知服务编排：校验、持久化、SSE 分发和清理。"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Callable, Mapping

from auto_check.app.notifications.contracts import (
    NotificationPublishRequest,
    NotificationPublishResult,
    NotificationStreamEvent,
    NotificationStreamPublisher,
    validate_publish_request,
    validate_source_module,
)
from auto_check.app.notifications.storage import NotificationStorage

_CLEANUP_INTERVAL_SECONDS = 6 * 3600  # 6 hours


class NotificationService:
    def __init__(
        self,
        storage: NotificationStorage,
        user_directory: Any,
        stream_publisher: NotificationStreamPublisher,
        *,
        now: Callable[[], datetime],
    ) -> None:
        self._storage = storage
        self._users = user_directory
        self._stream = stream_publisher
        self._now = now
        self._cleanup_stop = threading.Event()
        self._cleanup_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.published_sources: list[str] = []
        self._logger = logging.getLogger("auto_check.notifications")

    def publish(
        self,
        source_module: str,
        request: NotificationPublishRequest,
    ) -> NotificationPublishResult:
        source_module = validate_source_module(source_module)
        request = validate_publish_request(request)
        self._validate_recipients(request.recipient_user_ids)
        now = self._now()
        result = self._storage.create_or_get(source_module, request, now)
        if result.created:
            with self._lock:
                self.published_sources.append(source_module)
            self._emit_events(request, result, now)
        return result

    def _validate_recipients(self, recipient_user_ids: tuple[str, ...]) -> None:
        for user_id in recipient_user_ids:
            user = self._users.get_user(user_id)
            if user is None:
                raise ValueError(f"recipient user {user_id!r} does not exist or is disabled")
            if isinstance(user, Mapping):
                if not user.get("enabled", True):
                    raise ValueError(f"recipient user {user_id!r} does not exist or is disabled")
            elif not getattr(user, "active", False):
                raise ValueError(f"recipient user {user_id!r} does not exist or is disabled")

    def _emit_events(
        self,
        request: NotificationPublishRequest,
        result: NotificationPublishResult,
        now: datetime,
    ) -> None:
        for user_id in request.recipient_user_ids:
            try:
                unread_count = self._storage.unread_count(user_id, now)
            except Exception:
                unread_count = None
            try:
                notification = self._storage.get_for_user(user_id, result.notification_id, now)
            except Exception:
                notification = None
            event = NotificationStreamEvent(
                type="notification",
                notification=notification,
                unread_count=unread_count,
            )
            try:
                self._stream.publish(user_id, event)
            except Exception:
                self._logger.warning("SSE publish failed for user %s", user_id)

    def start_cleanup(self) -> None:
        with self._lock:
            if self._cleanup_thread is not None:
                return
            self._cleanup_stop.clear()
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                name="notification-cleanup",
                daemon=True,
            )
            self._cleanup_thread.start()

    def stop(self) -> None:
        with self._lock:
            self._cleanup_stop.set()
            thread = self._cleanup_thread
            self._cleanup_thread = None
        if thread is not None:
            thread.join(timeout=5.0)

    def _cleanup_loop(self) -> None:
        self.cleanup_expired()
        while not self._cleanup_stop.wait(_CLEANUP_INTERVAL_SECONDS):
            self.cleanup_expired()

    def cleanup_expired(self) -> int:
        total = 0
        while True:
            deleted = self._storage.delete_expired_batch(self._now(), limit=1000)
            total += deleted
            if deleted < 1000:
                break
        return total
