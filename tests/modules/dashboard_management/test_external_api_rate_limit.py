from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from auto_check.modules.dashboard_management.external_api_rate_limit import (
    DashboardExternalApiRateLimiter,
)


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_limiter_allows_ten_requests_then_returns_retry_after():
    clock = Clock()
    limiter = DashboardExternalApiRateLimiter(monotonic=clock)

    decisions = [limiter.check("192.168.1.20") for _ in range(11)]

    assert [decision.allowed for decision in decisions[:10]] == [True] * 10
    assert decisions[10].allowed is False
    assert decisions[10].retry_after_seconds == 60

    clock.advance(59.2)
    almost_ready = limiter.check("192.168.1.20")
    assert almost_ready.allowed is False
    assert almost_ready.retry_after_seconds == 1

    clock.advance(0.8)
    assert limiter.check("192.168.1.20").allowed is True


def test_limiter_keeps_source_ips_independent():
    clock = Clock()
    limiter = DashboardExternalApiRateLimiter(limit=1, monotonic=clock)

    assert limiter.check("192.168.1.20").allowed is True
    assert limiter.check("192.168.1.20").allowed is False
    assert limiter.check("192.168.1.21").allowed is True


def test_limiter_bounds_source_bucket_count_with_lru_eviction():
    clock = Clock()
    limiter = DashboardExternalApiRateLimiter(
        limit=1,
        max_buckets=2,
        monotonic=clock,
    )

    assert limiter.check("192.168.1.20").allowed is True
    assert limiter.check("192.168.1.21").allowed is True
    assert limiter.check("192.168.1.22").allowed is True
    # 20 是最久未使用的桶，容量达到上限时已被回收。
    assert limiter.check("192.168.1.20").allowed is True


def test_limiter_serializes_concurrent_requests_for_the_same_ip():
    clock = Clock()
    limiter = DashboardExternalApiRateLimiter(monotonic=clock)

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(executor.map(limiter.check, ["192.168.1.20"] * 20))

    assert sum(decision.allowed for decision in decisions) == 10
    assert sum(not decision.allowed for decision in decisions) == 10


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"window_seconds": 0},
        {"max_buckets": 0},
    ],
)
def test_limiter_rejects_non_positive_configuration(kwargs):
    with pytest.raises(ValueError):
        DashboardExternalApiRateLimiter(**kwargs)
