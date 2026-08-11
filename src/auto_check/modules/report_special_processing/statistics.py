from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from auto_check.app.report_navigation_platform import (
    CardStatisticsRequest,
    CardStatisticsResult,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
SEMANTICS_VERSION = 1


def status_metrics(counts: Mapping[str, int]) -> dict[str, int]:
    completed = int(counts.get("completed", 0))
    incomplete = int(counts.get("pending", 0)) + int(counts.get("processing", 0))
    return {
        "total": completed + incomplete,
        "completed": completed,
        "incomplete": incomplete,
    }


class SpecialHandlingStatistics:
    def __init__(self, storage: Any, *, now: Any) -> None:
        self._storage = storage
        self._now = now

    def __call__(self, request: CardStatisticsRequest) -> CardStatisticsResult:
        current = status_metrics(
            self._storage.count_by_handling_period(
                request.period_start, request.period_end_exclusive
            )
        )
        previous = status_metrics(
            self._storage.count_by_handling_period(
                request.previous_period_start,
                request.previous_period_end_exclusive,
            )
        )
        generated_at = self._now()
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            generated_at = generated_at.replace(tzinfo=SHANGHAI)
        return CardStatisticsResult(
            total=current["total"],
            completed=current["completed"],
            incomplete=current["incomplete"],
            previous_completed=previous["completed"],
            generated_at=generated_at.astimezone(SHANGHAI),
            semantics_version=SEMANTICS_VERSION,
        )
