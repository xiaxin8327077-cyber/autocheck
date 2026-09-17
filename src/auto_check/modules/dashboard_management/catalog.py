from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BoardSeed:
    code: str
    name: str
    display_order: int


@dataclass(frozen=True)
class RegionSeed:
    board_code: str
    code: str
    name: str
    shape: Literal["scalar", "list"]
    system_supported: bool
    default_mode: Literal["system", "sql"]
    display_order: int
    description: str


@dataclass(frozen=True)
class FieldSeed:
    region_code: str
    alias: str
    name: str
    value_type: str
    nullable: bool
    display_order: int
    description: str


BOARD_CATALOG = (
    BoardSeed("report_submission", "金融监管报表报送大屏", 10),
    BoardSeed("reporting_process", "金融监管报送流程大屏", 20),
)

BUILTIN_REGION_SEEDS = (
    RegionSeed("report_submission", "annual_supplement_completed", "本年度完成补录任务", "scalar", True, "system", 10, "本年度已完成补录任务数。"),
    RegionSeed("report_submission", "monthly_report_validation_remaining", "当月报表检验还剩", "scalar", True, "system", 20, "当月待完成报表校验数量。"),
    RegionSeed("report_submission", "monthly_trust_projects", "月度信托项目数量", "list", False, "sql", 30, "按月统计各类信托项目数量。"),
    RegionSeed("report_submission", "report_reconciliation_completion_time", "报表对账完成时间", "list", True, "system", 40, "按月汇总报表对账完成时间。"),
    RegionSeed("report_submission", "report_validation_issue_handling", "报表校验问题处理", "list", False, "sql", 50, "按月统计报表校验问题数量。"),
    RegionSeed("report_submission", "quarterly_special_processing", "季度报表特殊处理", "list", True, "system", 60, "按季度统计待确认和已确认的特殊处理数量。"),
    RegionSeed("report_submission", "monthly_report_submission_time_comparison", "当月报表报送时间对比", "list", True, "system", 70, "比较实际出表日期与要求报送日期。"),
    RegionSeed("reporting_process", "regulatory_report_count", "监管报送报表数量", "list", False, "sql", 10, "按报表类型统计监管报送报表数量。"),
    RegionSeed("reporting_process", "monthly_regulatory_report_time", "当月监管报送报表时间", "list", True, "system", 20, "按报表类型展示当月报送日期。"),
    RegionSeed("reporting_process", "report_validation_statistics", "报表校验统计", "list", False, "sql", 30, "按报表类型统计校验数量。"),
)

BUILTIN_FIELD_SEEDS = (
    FieldSeed("annual_supplement_completed", "completed_supplement_count", "完成补录任务数", "integer", False, 10, "本年度完成补录任务数。"),
    FieldSeed("monthly_report_validation_remaining", "remaining_validation_count", "剩余校验数量", "integer", False, 10, "当月剩余校验数量。"),
    FieldSeed("monthly_trust_projects", "month", "月份", "string", False, 10, "统计月份。格式：1月～12月，例如：8月。"),
    FieldSeed("monthly_trust_projects", "single_trust_count", "单一信托项目数量", "integer", False, 20, "单一信托项目数量。"),
    FieldSeed("monthly_trust_projects", "collective_trust_count", "集合信托项目数量", "integer", False, 30, "集合信托项目数量。"),
    FieldSeed("monthly_trust_projects", "property_trust_count", "财产权信托项目数量", "integer", False, 40, "财产权信托项目数量。"),
    FieldSeed("report_reconciliation_completion_time", "month", "月份", "string", False, 10, "统计月份。格式：YYYY-MM，例如：2026-08。"),
    FieldSeed("report_reconciliation_completion_time", "reconciliation_completed_time", "对账完成时间", "string", False, 20, "页面展示时分。格式：HH:mm，例如：09:30。"),
    FieldSeed("report_reconciliation_completion_time", "reconciliation_completed_at", "实际对账完成日期时间", "datetime", True, 30, "实际完成日期时间。格式：YYYY-MM-DDTHH:mm:ss；历史未知日期时为 null。"),
    FieldSeed("report_validation_issue_handling", "month", "月份", "string", False, 10, "统计月份。格式：YYYY-MM，例如：2026-08。"),
    FieldSeed("report_validation_issue_handling", "validation_issue_count", "校验问题数量", "integer", False, 20, "报表校验问题数量。"),
    FieldSeed("quarterly_special_processing", "quarter", "季度", "string", False, 10, "统计季度。"),
    FieldSeed("quarterly_special_processing", "special_processing_count", "特殊处理数量", "integer", False, 20, "待确认和已确认的特殊处理数量。"),
    FieldSeed("monthly_report_submission_time_comparison", "report_type", "报表类型", "string", False, 10, "报表类型。"),
    FieldSeed("monthly_report_submission_time_comparison", "actual_report_generated_at", "实际出表日期", "date", True, 20, "实际出表日期。"),
    FieldSeed("monthly_report_submission_time_comparison", "required_submission_at", "要求报送日期", "date", True, 30, "要求报送日期。"),
    FieldSeed("regulatory_report_count", "report_type", "报表类型", "string", False, 10, "报表类型。"),
    FieldSeed("regulatory_report_count", "report_count", "报表数量", "integer", False, 20, "监管报送报表数量。"),
    FieldSeed("monthly_regulatory_report_time", "report_type", "报表类型", "string", False, 10, "报表类型。"),
    FieldSeed("monthly_regulatory_report_time", "reporting_date", "报送日期", "date", True, 20, "当月监管报送日期。"),
    FieldSeed("report_validation_statistics", "report_type", "报表类型", "string", False, 10, "报表类型。"),
    FieldSeed("report_validation_statistics", "validation_count", "校验数量", "integer", False, 20, "报表校验数量。"),
)
