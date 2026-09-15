from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import re
from typing import Any, Mapping, Sequence


MONTHLY_TRUST_PROJECTS = "monthly_trust_projects"
REPORT_RECONCILIATION_COMPLETION_TIME = "report_reconciliation_completion_time"
REPORT_VALIDATION_ISSUE_HANDLING = "report_validation_issue_handling"
QUARTERLY_SPECIAL_PROCESSING = "quarterly_special_processing"

SNAPSHOT_REGION_CODES = frozenset({
    MONTHLY_TRUST_PROJECTS,
    REPORT_RECONCILIATION_COMPLETION_TIME,
    REPORT_VALIDATION_ISSUE_HANDLING,
    QUARTERLY_SPECIAL_PROCESSING,
})

_MONTH_ONLY = re.compile(r"^(?P<month>0?[1-9]|1[0-2])月$")
_YEAR_MONTH = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
_QUARTER_ONLY = re.compile(r"^第(?P<quarter>[1-4])季度$")
_YEAR_QUARTER = re.compile(r"^(?P<year>\d{4})年第(?P<quarter>[1-4])季度$")


class SnapshotValidationError(ValueError):
    """Raised when a snapshot-enabled region cannot be normalized safely."""


@dataclass(frozen=True)
class SnapshotRow:
    period_year: int
    period_type: str
    period_value: int
    row: Mapping[str, Any]


INITIAL_2026_SNAPSHOT_ROWS: Mapping[str, tuple[SnapshotRow, ...]] = {
    MONTHLY_TRUST_PROJECTS: tuple(
        SnapshotRow(2026, "month", month, {
            "month": f"{month}月",
            "single_trust_count": single,
            "collective_trust_count": collective,
            "property_trust_count": property_count,
        })
        for month, single, collective, property_count in (
            (1, 7, 28, 53),
            (2, 7, 30, 41),
            (3, 9, 48, 130),
            (4, 1, 41, 70),
            (5, 3, 18, 37),
            (6, 4, 52, 77),
        )
    ),
    REPORT_RECONCILIATION_COMPLETION_TIME: tuple(
        SnapshotRow(2026, "month", month, {
            "month": f"2026-{month:02d}",
            "reconciliation_completed_at": completed_at,
        })
        for month, completed_at in (
            (1, "21:00"),
            (2, "20:00"),
            (3, "19:00"),
            (4, "01:00"),
            (5, "23:00"),
            (6, "20:00"),
        )
    ),
    REPORT_VALIDATION_ISSUE_HANDLING: tuple(
        SnapshotRow(2026, "month", month, {
            "month": f"2026-{month:02d}",
            "validation_issue_count": issue_count,
        })
        for month, issue_count in (
            (1, 75),
            (2, 52),
            (3, 42),
            (4, 60),
            (5, 16),
            (6, 23),
            (7, 25),
            (8, 20),
        )
    ),
    QUARTERLY_SPECIAL_PROCESSING: tuple(
        SnapshotRow(2026, "quarter", quarter, {
            "quarter": f"第{quarter}季度",
            "special_processing_count": count,
        })
        for quarter, count in ((1, 31), (2, 34))
    ),
}


def normalize_snapshot_rows(
    region_code: str,
    rows: Sequence[Mapping[str, Any]],
    now: datetime,
) -> tuple[SnapshotRow, ...]:
    if region_code not in SNAPSHOT_REGION_CODES:
        raise SnapshotValidationError("该数据区域不支持快照")

    normalized: list[SnapshotRow] = []
    seen: set[tuple[int, str, int]] = set()
    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            continue
        item = _normalize_row(region_code, raw_row, now)
        if item is None:
            continue
        key = (item.period_year, item.period_type, item.period_value)
        if key in seen:
            raise SnapshotValidationError("快照区域返回了重复周期")
        seen.add(key)
        normalized.append(item)
    return tuple(
        sorted(
            normalized,
            key=lambda item: (item.period_year, item.period_type, item.period_value),
        )
    )


def _normalize_row(
    region_code: str, raw_row: Mapping[str, Any], now: datetime
) -> SnapshotRow | None:
    row = dict(raw_row)
    if region_code == QUARTERLY_SPECIAL_PROCESSING:
        period = _quarter_period(row.get("quarter"), now)
        if period is None:
            return None
        year, quarter = period
        row["quarter"] = f"第{quarter}季度"
        return SnapshotRow(year, "quarter", quarter, row)

    allow_month_only = region_code == MONTHLY_TRUST_PROJECTS
    period = _month_period(row.get("month"), now, allow_month_only=allow_month_only)
    if period is None:
        return None
    year, month = period
    row["month"] = f"{month}月" if allow_month_only else f"{year:04d}-{month:02d}"
    if region_code == REPORT_RECONCILIATION_COMPLETION_TIME:
        try:
            row["reconciliation_completed_at"] = _completion_time(
                row.get("reconciliation_completed_at")
            )
        except (TypeError, ValueError):
            return None
    return SnapshotRow(year, "month", month, row)


def _month_period(
    value: Any, now: datetime, *, allow_month_only: bool
) -> tuple[int, int] | None:
    text = str(value or "").strip()
    match = _YEAR_MONTH.fullmatch(text)
    if match is not None:
        year = int(match.group("year"))
        month = int(match.group("month"))
    elif allow_month_only:
        match = _MONTH_ONLY.fullmatch(text)
        if match is None:
            return None
        year = now.year
        month = int(match.group("month"))
    else:
        return None
    if year != now.year or month > now.month:
        return None
    return year, month


def _quarter_period(value: Any, now: datetime) -> tuple[int, int] | None:
    text = str(value or "").strip()
    match = _YEAR_QUARTER.fullmatch(text)
    if match is not None:
        year = int(match.group("year"))
        quarter = int(match.group("quarter"))
    else:
        match = _QUARTER_ONLY.fullmatch(text)
        if match is None:
            return None
        year = now.year
        quarter = int(match.group("quarter"))
    current_quarter = (now.month - 1) // 3 + 1
    if year != now.year or quarter > current_quarter:
        return None
    return year, quarter


def _completion_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    text = str(value).strip()
    if not text:
        return None
    try:
        if "T" in text or " " in text:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.strftime("%H:%M")
        return time.fromisoformat(text).strftime("%H:%M")
    except ValueError:
        raise ValueError("对账完成时间格式无效") from None
