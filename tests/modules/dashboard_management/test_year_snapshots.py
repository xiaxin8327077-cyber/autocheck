from __future__ import annotations

from datetime import datetime

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


def test_year_month_regions_keep_contract_and_normalize_completion_time() -> None:
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
            {"month": "2026-10", "reconciliation_completed_at": "10:00"},
            {"month": "2025-12", "reconciliation_completed_at": "20:00"},
        ),
        NOW,
    )
    validation = normalize_snapshot_rows(
        "report_validation_issue_handling",
        ({"month": "2026-06", "validation_issue_count": 23},),
        NOW,
    )

    assert [row.row for row in completion] == [
        {"month": "2026-08", "reconciliation_completed_at": "14:45"},
        {"month": "2026-09", "reconciliation_completed_at": "08:05"},
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


def test_invalid_completion_time_row_is_ignored_and_non_snapshot_region_is_rejected() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        SnapshotValidationError,
        normalize_snapshot_rows,
    )

    assert normalize_snapshot_rows(
        "report_reconciliation_completion_time",
        ({"month": "2026-08", "reconciliation_completed_at": "not-a-time"},),
        NOW,
    ) == ()
    with pytest.raises(SnapshotValidationError, match="不支持快照"):
        normalize_snapshot_rows("annual_supplement_completed", (), NOW)
