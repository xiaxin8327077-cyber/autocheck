from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Mapping, Sequence

from sqlalchemy import text

from .sql_executor import QueryPreview, _convert_value, _field_value
from .validator import ValidationError


SYSTEM_PREVIEW_LIMIT = 10

SYSTEM_TABLE_DISPLAY_NAMES = {
    "report_nav_card_snapshots": "报送导航统计卡快照",
    "run_headers": "核对任务运行记录",
    "reconcile_runs": "自动对数运行摘要",
    "report_special_processing_records": "报表特殊处理记录",
    "report_nav_processes": "报送导航流程配置",
    "report_nav_process_months": "报送流程适用月份",
    "report_nav_process_snapshots": "报送导航流程统计快照",
    "report_nav_monthly_schedules": "报送导航月度报送计划",
}


@dataclass(frozen=True)
class SystemQueryDefinition:
    feature: str
    description: str
    tables: tuple[str, ...]
    fields: tuple[tuple[str, str], ...]
    sql: str

    def public_value(self, database: Any) -> dict[str, Any]:
        config = getattr(database, "config", None)
        database_name = str(getattr(config, "database", "") or "AutoCheck 系统库")
        table_comments = "\n".join(
            f"-- 数据表：{SYSTEM_TABLE_DISPLAY_NAMES.get(table_name, table_name)}（{table_name}）"
            for table_name in self.tables
        )
        field_comments = "\n".join(
            f"-- 字段：{display_name}（{alias}）"
            for alias, display_name in self.fields
        )
        return {
            "type": "system_database",
            "feature": self.feature,
            "description": self.description,
            "database": database_name,
            "tables": list(self.tables),
            "table_details": [
                {
                    "name": table_name,
                    "display_name": SYSTEM_TABLE_DISPLAY_NAMES.get(table_name, table_name),
                }
                for table_name in self.tables
            ],
            "sql": f"{table_comments}\n{field_comments}\n{self.sql}",
        }


def _sql(value: str) -> str:
    return dedent(value).strip()


SYSTEM_QUERY_DEFINITIONS: dict[str, SystemQueryDefinition] = {
    "annual_supplement_completed": SystemQueryDefinition(
        feature="报送导航 / 补录任务统计",
        description="读取报送导航年度统计卡中的已完成补录任务数量。",
        tables=("report_nav_card_snapshots",),
        fields=(("completed_supplement_count", "完成补录任务数"),),
        sql=_sql(
            """
            SELECT completed_count AS completed_supplement_count
            FROM report_nav_card_snapshots
            WHERE stat_period = 'year'
              AND card_code = 'supplement_tasks'
            """
        ),
    ),
    "monthly_report_validation_remaining": SystemQueryDefinition(
        feature="报送导航 / 报表校验统计",
        description="读取报送导航当月报表校验统计卡中的未完成数量。",
        tables=("report_nav_card_snapshots",),
        fields=(("remaining_validation_count", "剩余校验数量"),),
        sql=_sql(
            """
            SELECT incomplete_count AS remaining_validation_count
            FROM report_nav_card_snapshots
            WHERE stat_period = 'month'
              AND card_code = 'report_check'
            """
        ),
    ),
    "report_reconciliation_completion_time": SystemQueryDefinition(
        feature="核对历史 / 自动对数",
        description="按报送期读取自动对数历史中总差异为 0 的最早执行时间。",
        tables=("run_headers", "reconcile_runs"),
        fields=(("month", "月份"), ("reconciliation_completed_at", "对账完成时间")),
        sql=_sql(
            """
            SELECT DATE_FORMAT(header.run_date, '%Y-%m') AS month,
                   MIN(header.run_at) AS reconciliation_completed_at
            FROM run_headers AS header
            INNER JOIN reconcile_runs AS reconcile
                    ON reconcile.id = header.id
            WHERE header.kind = 'reconcile'
              AND header.run_date IS NOT NULL
              AND header.run_at IS NOT NULL
              AND reconcile.total_count = 0
              AND YEAR(header.run_date) = YEAR(CURRENT_DATE)
            GROUP BY DATE_FORMAT(header.run_date, '%Y-%m')
            ORDER BY month
            """
        ),
    ),
    "quarterly_special_processing": SystemQueryDefinition(
        feature="报表特殊处理录入 / 特殊处理记录",
        description="按季度统计本年度待确认和已确认的报表特殊处理记录。",
        tables=("report_special_processing_records",),
        fields=(("quarter", "季度"), ("special_processing_count", "特殊处理数量")),
        sql=_sql(
            """
            SELECT CONCAT(YEAR(special_handling_at), '年第',
                          QUARTER(special_handling_at), '季度') AS quarter,
                   COUNT(*) AS special_processing_count
            FROM report_special_processing_records
            WHERE special_handling_at IS NOT NULL
              AND status IN ('pending', 'completed')
              AND YEAR(special_handling_at) = YEAR(CURRENT_DATE)
            GROUP BY YEAR(special_handling_at), QUARTER(special_handling_at)
            ORDER BY YEAR(special_handling_at), QUARTER(special_handling_at)
            """
        ),
    ),
    "monthly_report_submission_time_comparison": SystemQueryDefinition(
        feature="报送导航 / 流程完成与月度报送计划",
        description="对比当月各报送流程的实际完成日期与计划报送日期。",
        tables=(
            "report_nav_processes",
            "report_nav_process_months",
            "report_nav_process_snapshots",
            "report_nav_monthly_schedules",
        ),
        fields=(
            ("report_type", "报表类型"),
            ("actual_report_generated_at", "实际出表日期"),
            ("required_submission_at", "要求报送日期"),
        ),
        sql=_sql(
            """
            SELECT process.process_name AS report_type,
                   DATE(snapshot.completed_at) AS actual_report_generated_at,
                   schedule.report_date AS required_submission_at
            FROM report_nav_processes AS process
            INNER JOIN report_nav_process_months AS active_month
                    ON active_month.process_code = process.process_code
                   AND active_month.month_no = MONTH(CURRENT_DATE)
            LEFT JOIN report_nav_process_snapshots AS snapshot
                   ON snapshot.process_code = process.process_code
                  AND snapshot.report_month = DATE_FORMAT(CURRENT_DATE, '%Y-%m')
            LEFT JOIN report_nav_monthly_schedules AS schedule
                   ON schedule.process_code = process.process_code
                  AND schedule.report_month = DATE_FORMAT(CURRENT_DATE, '%Y-%m')
            WHERE process.enabled = 1
              AND process.process_name <> '人行大集中'
            ORDER BY process.display_order, process.process_code
            """
        ),
    ),
    "monthly_regulatory_report_time": SystemQueryDefinition(
        feature="报送导航 / 月度报送计划",
        description="读取报送导航中当月各报送流程的计划报送日期。",
        tables=(
            "report_nav_processes",
            "report_nav_process_months",
            "report_nav_monthly_schedules",
        ),
        fields=(("report_type", "报表类型"), ("reporting_date", "报送日期")),
        sql=_sql(
            """
            SELECT process.process_name AS report_type,
                   schedule.report_date AS reporting_date
            FROM report_nav_processes AS process
            INNER JOIN report_nav_process_months AS active_month
                    ON active_month.process_code = process.process_code
                   AND active_month.month_no = MONTH(CURRENT_DATE)
            LEFT JOIN report_nav_monthly_schedules AS schedule
                   ON schedule.process_code = process.process_code
                  AND schedule.report_month = DATE_FORMAT(CURRENT_DATE, '%Y-%m')
            WHERE process.enabled = 1
            ORDER BY process.display_order, process.process_code
            """
        ),
    ),
}


@dataclass(frozen=True)
class SystemPreviewResult:
    preview: QueryPreview
    source: Mapping[str, Any]


class SystemDataPreviewExecutor:
    def __init__(self, preview_limit: int = SYSTEM_PREVIEW_LIMIT) -> None:
        self.preview_limit = preview_limit

    def source_for(self, database: Any, region_code: str) -> dict[str, Any] | None:
        definition = SYSTEM_QUERY_DEFINITIONS.get(region_code)
        return definition.public_value(database) if definition else None

    def execute(
        self,
        database: Any,
        region_code: str,
        fields: Sequence[Any],
        shape: str,
    ) -> SystemPreviewResult:
        definition = SYSTEM_QUERY_DEFINITIONS.get(region_code)
        if definition is None:
            raise ValidationError("该数据区域暂不支持系统数据")
        active_fields = [field for field in fields if _field_value(field, "enabled", True)]
        if not active_fields:
            raise ValidationError("数据区域至少需要一个启用字段")
        if shape not in {"scalar", "list"}:
            raise ValidationError("数据区域形态无效")
        try:
            with database.connect() as connection:
                result = connection.execute(text(definition.sql))
                columns = tuple(str(column) for column in result.keys())
                raw_rows = list(result.fetchmany(self.preview_limit + 1))
        except ValidationError:
            raise
        except Exception:
            raise ValidationError("系统数据读取失败，请确认对应功能及数据表已初始化") from None

        normalized_columns = [column.lower() for column in columns]
        if len(set(normalized_columns)) != len(normalized_columns):
            raise ValidationError("系统查询结果包含重复列名")
        positions = {name: index for index, name in enumerate(normalized_columns)}
        aliases = [str(_field_value(field, "field_alias")) for field in active_fields]
        missing = [alias for alias in aliases if alias not in positions]
        if missing:
            raise ValidationError(
                "系统查询结果缺少必需字段：" + "、".join(missing),
                fields={alias: "系统查询结果缺少该字段" for alias in missing},
            )
        if shape == "scalar" and len(raw_rows) > 1:
            raise ValidationError("单值数据区域最多只能返回一行")
        rows = tuple(
            {
                alias: _convert_value(row[positions[alias]], field)
                for alias, field in zip(aliases, active_fields)
            }
            for row in raw_rows[: self.preview_limit]
        )
        return SystemPreviewResult(
            preview=QueryPreview(
                columns=tuple(aliases),
                rows=rows,
                has_more=len(raw_rows) > self.preview_limit,
                returned_count=len(rows),
                tested_signature="",
            ),
            source=definition.public_value(database),
        )
