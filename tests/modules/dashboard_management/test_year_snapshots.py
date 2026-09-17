from __future__ import annotations

from datetime import datetime, time

import pytest


NOW = datetime(2026, 9, 15, 10, 30)


def test_monthly_trust_rows_accept_supported_formats_and_filter_other_periods() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        normalize_snapshot_rows,
    )

    rows = normalize_snapshot_rows(
        "monthly_trust_projects",
        (
            {"month": "8月", "single_trust_count": 8},
            {"month": "09月", "single_trust_count": 9},
            {"month": "2026-07", "single_trust_count": 7},
            {"month": "2025-12", "single_trust_count": 12},
            {"month": "10月", "single_trust_count": 10},
            {"month": "未知", "single_trust_count": 0},
        ),
        NOW,
    )

    assert [(row.period_year, row.period_type, row.period_value) for row in rows] == [
        (2026, "month", 7),
        (2026, "month", 8),
        (2026, "month", 9),
    ]
    assert [row.row["month"] for row in rows] == ["7月", "8月", "9月"]


def test_year_month_regions_keep_contract_and_full_completion_datetime() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        normalize_snapshot_rows,
    )

    completion = normalize_snapshot_rows(
        "report_reconciliation_completion_time",
        (
            {
                "month": "2026-08",
                "reconciliation_completed_at": "2026-08-01T14:45:32",
            },
            {
                "month": "2026-09",
                "reconciliation_completed_at": datetime(2026, 9, 2, 8, 5),
            },
        ),
        NOW,
    )
    validation = normalize_snapshot_rows(
        "report_validation_issue_handling",
        ({"month": "2026-06", "validation_issue_count": 23},),
        NOW,
    )

    assert [row.row for row in completion] == [
        {
            "month": "2026-08",
            "reconciliation_completed_time": "14:45",
            "reconciliation_completed_at": "2026-08-01T14:45:32",
        },
        {
            "month": "2026-09",
            "reconciliation_completed_time": "08:05",
            "reconciliation_completed_at": "2026-09-02T08:05:00",
        },
    ]
    assert validation[0].row == {"month": "2026-06", "validation_issue_count": 23}


def test_quarter_rows_accept_supported_formats_and_filter_future_quarter() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        normalize_snapshot_rows,
    )

    rows = normalize_snapshot_rows(
        "quarterly_special_processing",
        (
            {"quarter": "2026年第2季度", "special_processing_count": 34},
            {"quarter": "第1季度", "special_processing_count": 31},
            {"quarter": "第3季度", "special_processing_count": 8},
            {"quarter": "第4季度", "special_processing_count": 99},
            {"quarter": "2025年第4季度", "special_processing_count": 88},
        ),
        NOW,
    )

    assert [(row.period_year, row.period_type, row.period_value) for row in rows] == [
        (2026, "quarter", 1),
        (2026, "quarter", 2),
        (2026, "quarter", 3),
    ]
    assert [row.row["quarter"] for row in rows] == ["第1季度", "第2季度", "第3季度"]


def test_duplicate_snapshot_period_is_rejected_without_choosing_a_row() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        SnapshotValidationError,
        normalize_snapshot_rows,
    )

    with pytest.raises(SnapshotValidationError, match="重复周期"):
        normalize_snapshot_rows(
            "monthly_trust_projects",
            (
                {"month": "8月", "single_trust_count": 1},
                {"month": "2026-08", "single_trust_count": 2},
            ),
            NOW,
        )


@pytest.mark.parametrize("value", ["10:00", time(10, 0), None, "not-a-time"])
def test_new_reconciliation_rows_reject_missing_or_time_only_completion(value) -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        SnapshotValidationError,
        normalize_snapshot_rows,
    )

    with pytest.raises(SnapshotValidationError, match="完整日期时间"):
        normalize_snapshot_rows(
            "report_reconciliation_completion_time",
            ({"month": "2026-08", "reconciliation_completed_at": value},),
            NOW,
        )


def test_january_accepts_previous_december_late_completion_without_mixing_year() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import normalize_snapshot_rows

    rows = normalize_snapshot_rows(
        "report_reconciliation_completion_time",
        ({
            "month": "2026-12",
            "reconciliation_completed_at": "2027-01-03T01:15:00",
        },),
        datetime(2027, 1, 4, 9, 0),
    )

    assert rows[0].period_year == 2026
    assert rows[0].period_value == 12
    assert rows[0].row["reconciliation_completed_time"] == "01:15"
    assert rows[0].row["reconciliation_completed_at"] == "2027-01-03T01:15:00"


@pytest.mark.parametrize(
    ("now", "month"),
    [
        (datetime(2027, 2, 1, 9, 0), "2026-12"),
        (datetime(2027, 1, 4, 9, 0), "2026-11"),
    ],
)
def test_previous_year_rows_outside_january_december_window_are_ignored(now, month) -> None:
    from auto_check.modules.dashboard_management.year_snapshots import normalize_snapshot_rows

    assert normalize_snapshot_rows(
        "report_reconciliation_completion_time",
        ({
            "month": month,
            "reconciliation_completed_at": "2027-01-03T01:15:00",
        },),
        now,
    ) == ()


def test_legacy_time_only_snapshot_is_exposed_without_fabricated_date() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        normalize_reconciliation_completion_row,
    )

    assert normalize_reconciliation_completion_row(
        {"month": "2026-01", "reconciliation_completed_at": "21:00"},
        allow_legacy_time=True,
    ) == {
        "month": "2026-01",
        "reconciliation_completed_time": "21:00",
        "reconciliation_completed_at": None,
    }


def test_non_snapshot_region_is_rejected() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        SnapshotValidationError,
        normalize_snapshot_rows,
    )

    with pytest.raises(SnapshotValidationError, match="不支持快照"):
        normalize_snapshot_rows("annual_supplement_completed", (), NOW)
