from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def test_builtin_catalog_has_two_boards_ten_regions_and_twenty_two_fields() -> None:
    from auto_check.modules.dashboard_management.catalog import (
        BOARD_CATALOG,
        BUILTIN_FIELD_SEEDS,
        BUILTIN_REGION_SEEDS,
    )

    assert [board.code for board in BOARD_CATALOG] == ["report_submission", "reporting_process"]
    assert len(BUILTIN_REGION_SEEDS) == 10
    assert len(BUILTIN_FIELD_SEEDS) == 22
    trust = next(item for item in BUILTIN_REGION_SEEDS if item.code == "monthly_trust_projects")
    assert trust.shape == "list"
    assert trust.system_supported is False
    assert trust.default_mode == "sql"


def test_builtin_catalog_is_immutable_and_uses_stable_unique_aliases() -> None:
    from auto_check.modules.dashboard_management.catalog import (
        BOARD_CATALOG,
        BUILTIN_FIELD_SEEDS,
        BUILTIN_REGION_SEEDS,
    )

    with pytest.raises(FrozenInstanceError):
        BOARD_CATALOG[0].name = "changed"  # type: ignore[misc]
    assert {item.board_code for item in BUILTIN_REGION_SEEDS} == {
        "report_submission", "reporting_process"
    }
    aliases = [(item.region_code, item.alias) for item in BUILTIN_FIELD_SEEDS]
    assert len(aliases) == len(set(aliases))
    assert [
        item.alias for item in BUILTIN_FIELD_SEEDS if item.region_code == "monthly_trust_projects"
    ] == ["month", "single_trust_count", "collective_trust_count", "property_trust_count"]


def test_builtin_month_fields_describe_the_required_display_format() -> None:
    from auto_check.modules.dashboard_management.catalog import BUILTIN_FIELD_SEEDS

    month_descriptions = {
        item.region_code: item.description
        for item in BUILTIN_FIELD_SEEDS
        if item.alias == "month"
    }

    assert month_descriptions == {
        "monthly_trust_projects": (
            "接口展示格式：1月～12月，例如：8月。"
            "来源 SQL 推荐返回 YYYY-MM，例如：2026-08，用于明确年份；"
            "兼容仅月份时须由 SQL 限定业务年份。"
        ),
        "report_reconciliation_completion_time": "统计月份。格式：YYYY-MM，例如：2026-08。",
        "report_validation_issue_handling": "统计月份。格式：YYYY-MM，例如：2026-08。",
    }


def test_reconciliation_completion_fields_separate_display_time_and_full_datetime() -> None:
    from auto_check.modules.dashboard_management.catalog import BUILTIN_FIELD_SEEDS

    fields = [
        item
        for item in BUILTIN_FIELD_SEEDS
        if item.region_code == "report_reconciliation_completion_time"
    ]

    assert [
        (item.alias, item.value_type, item.nullable, item.display_order)
        for item in fields
    ] == [
        ("month", "string", False, 10),
        ("reconciliation_completed_time", "string", False, 20),
        ("reconciliation_completed_at", "datetime", True, 30),
    ]
