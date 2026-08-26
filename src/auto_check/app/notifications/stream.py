"""有界、按用户隔离的进程内 SSE Hub。"""

from __future__ import annotations

import queue
import threading
from collections import defaultdict
from typing import Any

from auto_check.app.notifications.contracts import NotificationStreamEvent

_CLOSE_SENTINEL = object()


class NotificationStreamLimitError(RuntimeError):
    """SSE 连接数超限。"""


class NotificationSubscription:
    def __init__(self, user_id: str, queue: queue.Queue, hub: "NotificationStreamHub") -> None:
        self._user_id = user_id
        self._queue = queue
        self._hub = hub
        self._closed = False

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def queue(self) -> queue.Queue:
        return self._queue

    @property
    def closed(self) -> bool:
        return self._closed

    def next(self, timeout_seconds: float = 20.0) -> NotificationStreamEvent | None:
        if self._closed:
            return None
        try:
            item = self._queue.get(timeout=timeout_seconds)
            if item is _CLOSE_SENTINEL:
                self._closed = True
                return NotificationStreamEvent(type="close")
            return item
        except queue.Empty:
            return None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._hub._remove_subscription(self)


class NotificationStreamHub:
    def __init__(self, max_per_user: int = 5, max_total: int = 200, queue_size: int = 100) -> None:
        self._max_per_user = max_per_user
        self._max_total = max_total
        self._queue_size = queue_size
        self._lock = threading.RLock()
        self._subscriptions: dict[str, list[NotificationSubscription]] = defaultdict(list)
        self._total = 0
        self._closed = False

    def subscribe(self, user_id: str) -> NotificationSubscription:
        with self._lock:
            if self._closed:
                raise NotificationStreamLimitError("hub is closed")
            if self._total >= self._max_total:
                raise NotificationStreamLimitError(f"global connection limit {self._max_total} reached")
            user_subs = self._subscriptions[user_id]
            if len(user_subs) >= self._max_per_user:
                raise NotificationStreamLimitError(f"per-user connection limit {self._max_per_user} reached for {user_id!r}")
            q: queue.Queue = queue.Queue(maxsize=self._queue_size)
            sub = NotificationSubscription(user_id, q, self)
            user_subs.append(sub)
            self._total += 1
            return sub

    def _remove_subscription(self, subscription: NotificationSubscription) -> None:
        with self._lock:
            if subscription._closed and subscription in self._subscriptions.get(subscription.user_id, []):
                self._subscriptions[subscription.user_id].remove(subscription)
                self._total -= 1
                if not self._subscriptions[subscription.user_id]:
                    del self._subscriptions[subscription.user_id]

    def publish(self, user_id: str, event: NotificationStreamEvent) -> None:
        with self._lock:
            subs = list(self._subscriptions.get(user_id, []))
        for sub in subs:
            if sub.closed:
                continue
            try:
                sub.queue.put_nowait(event)
            except queue.Full:
                # Clear queue and put resync
                while not sub.queue.empty():
                    try:
                        sub.queue.get_nowait()
                    except queue.Empty:
                        break
                try:
                    sub.queue.put_nowait(NotificationStreamEvent(type="resync"))
                except queue.Full:
                    pass

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            all_subs = []
            for subs in self._subscriptions.values():
                all_subs.extend(subs)
            self._subscriptions.clear()
            self._total = 0
        for sub in all_subs:
            try:
                sub.queue.put_nowait(_CLOSE_SENTINEL)
            except queue.Full:
                pass
