from __future__ import annotations

import math
import time
from collections import OrderedDict, deque
from threading import Lock
from typing import Callable

from auto_check.app.module_system.routing import ExternalRateLimitDecision


DEFAULT_LIMIT = 10
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_BUCKETS = 4096


class DashboardExternalApiRateLimiter:
    """Thread-safe per-IP sliding window shared by both dashboard routes."""

    def __init__(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        max_buckets: int = DEFAULT_MAX_BUCKETS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        if type(window_seconds) is not int or window_seconds < 1:
            raise ValueError("window_seconds must be a positive integer")
        if type(max_buckets) is not int or max_buckets < 1:
            raise ValueError("max_buckets must be a positive integer")
        if not callable(monotonic):
            raise ValueError("monotonic must be callable")
        self._limit = limit
        self._window_seconds = window_seconds
        self._max_buckets = max_buckets
        self._monotonic = monotonic
        self._buckets: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def check(self, client_ip: str) -> ExternalRateLimitDecision:
        key = client_ip.strip() if isinstance(client_ip, str) else ""
        if not key:
            key = "unknown"
        now = float(self._monotonic())
        cutoff = now - self._window_seconds

        with self._lock:
            bucket = self._buckets.pop(key, None)
            if bucket is None:
                if len(self._buckets) >= self._max_buckets:
                    self._buckets.popitem(last=False)
                bucket = deque()
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            self._buckets[key] = bucket

            if len(bucket) < self._limit:
                bucket.append(now)
                return ExternalRateLimitDecision(allowed=True)

            retry_after = max(
                1,
                math.ceil(self._window_seconds - (now - bucket[0])),
            )
            return ExternalRateLimitDecision(
                allowed=False,
                retry_after_seconds=retry_after,
            )
