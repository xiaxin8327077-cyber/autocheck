from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Mapping, Protocol, Sequence

from auto_check.app.config import DataSourceEntry
from auto_check.app.db import DatabaseClient, qualified_name, quote_identifier
from auto_check.app.storage_report_navigation import ScheduleConfig, StepConfig, StepSourceConfig


COMPLETED = "completed"
INCOMPLETE = "incomplete"
WAITING_REPORT_PERIOD = "waiting_report_period"
ERROR = "error"


@dataclass(frozen=True)
class EvaluationResult:
    status: str
    message: str
    error: str = ""


class QueryExecutor(Protocol):
    def qualified_table(self, source: StepSourceConfig) -> str: ...

    def quote_column(self, source: StepSourceConfig, column_name: str) -> str: ...

    def fetch_one(
        self, source: StepSourceConfig, sql: str, params: Sequence[Any] = ()
    ) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class EvaluationContext:
    step: StepConfig
    business_report_date: date | None
    current: datetime
    query: QueryExecutor
    dependency_statuses: Mapping[str, str]
    schedule: ScheduleConfig | None


class ConfiguredQueryExecutor:
    def __init__(
        self,
        data_sources: Sequence[DataSourceEntry],
        *,
        client_factory: Callable[[Any], DatabaseClient] = DatabaseClient,
    ):
        self._sources = {entry.name: entry.config for entry in data_sources}
        self._client_factory = client_factory

    def _config(self, source: StepSourceConfig):
        config = self._sources.get(source.data_source_name)
        if config is None:
            raise ValueError(f"数据源不存在：{source.data_source_name}")
        return config

    def qualified_table(self, source: StepSourceConfig) -> str:
        config = self._config(source)
        parts = source.table_name.split(".")
        if len(parts) == 1:
            quote_identifier(config.db_type, parts[0])
            return qualified_name(config, parts[0])
        if len(parts) == 2:
            return ".".join(quote_identifier(config.db_type, part) for part in parts)
        raise ValueError(f"非法表名：{source.table_name}")

    def quote_column(self, source: StepSourceConfig, column_name: str) -> str:
        return quote_identifier(self._config(source).db_type, column_name)

    def fetch_one(
        self, source: StepSourceConfig, sql: str, params: Sequence[Any] = ()
    ) -> Mapping[str, Any] | None:
        return self._client_factory(self._config(source)).fetch_one(sql, params)


def format_business_report_date(value: date, style: str) -> str:
    if style == "date":
        return value.strftime("%Y-%m-%d")
    if style == "underscore":
        return value.strftime("%Y_%m_%d")
    if style == "version":
        return value.strftime("V.%Y%m%d")
    raise ValueError(f"未知报告期格式：{style}")


def scope_without_exceptions(row: Mapping[str, Any] | None) -> EvaluationResult:
    scope_count = _integer((row or {}).get("scope_count"))
    exception_count = _integer((row or {}).get("exception_count"))
    if scope_count <= 0:
        return EvaluationResult(INCOMPLETE, "当前范围无数据")
    if exception_count > 0:
        return EvaluationResult(INCOMPLETE, f"存在 {exception_count} 条异常数据")
    return EvaluationResult(COMPLETED, "自动判断完成")


def evaluate(context: EvaluationContext) -> EvaluationResult:
    evaluator = EVALUATORS.get(context.step.evaluator_key)
    if evaluator is None:
        return EvaluationResult(ERROR, "判断器未配置", f"未知判断器：{context.step.evaluator_key}")
    try:
        return evaluator(context)
    except Exception as exc:
        return EvaluationResult(ERROR, "判断异常", str(exc))


def evaluate_default_completed(context: EvaluationContext) -> EvaluationResult:
    if context.step.default_completed:
        return EvaluationResult(COMPLETED, "默认完成")
    return EvaluationResult(INCOMPLETE, "未设置默认完成")


def evaluate_dependency_completed(context: EvaluationContext) -> EvaluationResult:
    if not context.step.dependencies:
        return EvaluationResult(INCOMPLETE, "未配置依赖步骤")
    incomplete = [
        code
        for code in context.step.dependencies
        if context.dependency_statuses.get(code) != COMPLETED
    ]
    if incomplete:
        return EvaluationResult(INCOMPLETE, f"等待依赖步骤：{', '.join(incomplete)}")
    return EvaluationResult(COMPLETED, "依赖步骤已完成")


def evaluate_date_reached(context: EvaluationContext) -> EvaluationResult:
    if context.schedule is None:
        return EvaluationResult(INCOMPLETE, "报送日期待维护")
    if context.current.date() >= context.schedule.report_date:
        return EvaluationResult(COMPLETED, "已到报送日期")
    return EvaluationResult(INCOMPLETE, f"等待报送日期 {context.schedule.report_date.isoformat()}")


def evaluate_all_rows_match_report_date(context: EvaluationContext) -> EvaluationResult:
    report_date = _require_report_date(context)
    source = _source(context, "primary")
    period = _column(context, source, "period_field")
    sql = (
        f"SELECT COUNT(*) AS scope_count, "
        f"SUM(CASE WHEN {period} IS NULL OR {period} <> %s THEN 1 ELSE 0 END) AS exception_count "
        f"FROM {_table(context, source)}"
    )
    return scope_without_exceptions(
        context.query.fetch_one(source, sql, (format_business_report_date(report_date, "date"),))
    )


def evaluate_amounts_equal(context: EvaluationContext) -> EvaluationResult:
    report_date = _require_report_date(context)
    source = _source(context, "primary")
    period = _column(context, source, "period_field")
    left = _column(context, source, "left_amount_field")
    right = _column(context, source, "right_amount_field")
    sql = (
        f"SELECT COUNT(*) AS scope_count, "
        f"SUM(CASE WHEN {left} IS NULL OR {right} IS NULL OR {left} <> {right} THEN 1 ELSE 0 END) AS exception_count "
        f"FROM {_table(context, source)} WHERE {period} = %s"
    )
    return scope_without_exceptions(context.query.fetch_one(source, sql, (report_date,)))


def evaluate_no_blank_fields_and_no_ck(context: EvaluationContext) -> EvaluationResult:
    report_date = _require_report_date(context)
    duration = _source(context, "duration")
    period = _column(context, duration, "period_field")
    region = _column(context, duration, "region_field")
    customer_type = _column(context, duration, "customer_type_field")
    duration_sql = (
        f"SELECT COUNT(*) AS scope_count, "
        f"SUM(CASE WHEN {region} IS NULL OR TRIM({region}) = '' OR {customer_type} IS NULL OR TRIM({customer_type}) = '' THEN 1 ELSE 0 END) AS exception_count "
        f"FROM {_table(context, duration)} WHERE {period} = %s"
    )
    duration_result = scope_without_exceptions(
        context.query.fetch_one(duration, duration_sql, (report_date,))
    )
    if duration_result.status != COMPLETED:
        return duration_result
    return _evaluate_no_ck(context, _source(context, "ck_result"), report_date)


def evaluate_no_ck_and_min_time(context: EvaluationContext) -> EvaluationResult:
    report_date = _require_report_date(context)
    ck_result = _evaluate_no_ck(context, _source(context, "ck_result"), report_date)
    if ck_result.status != COMPLETED:
        return ck_result
    return _evaluate_min_time_current_month(context, _source(context, "spv_detail"))


def evaluate_no_pending_status(context: EvaluationContext) -> EvaluationResult:
    report_date = _require_report_date(context)
    start, end = _month_bounds(report_date)
    pending_values = context.step.values.get("pending_status", ())
    if not pending_values:
        raise ValueError("未配置待处理状态")
    for source in context.step.sources:
        period = _column(context, source, "period_field")
        status = _column(context, source, "status_field")
        placeholders = ", ".join(["%s"] * len(pending_values))
        sql = (
            f"SELECT COUNT(*) AS scope_count, "
            f"SUM(CASE WHEN {status} IN ({placeholders}) THEN 1 ELSE 0 END) AS exception_count "
            f"FROM {_table(context, source)} WHERE {period} >= %s AND {period} < %s"
        )
        result = scope_without_exceptions(
            context.query.fetch_one(source, sql, (*pending_values, start, end))
        )
        if result.status != COMPLETED:
            return result
    return EvaluationResult(COMPLETED, "两张表均无待确认或待补充数据")


def evaluate_month_rows_or_dependency(context: EvaluationContext) -> EvaluationResult:
    report_date = _require_report_date(context)
    source = _source(context, "primary")
    date_field = _column(context, source, "date_field")
    start, end = _month_bounds(report_date)
    row = context.query.fetch_one(
        source,
        f"SELECT COUNT(*) AS row_count FROM {_table(context, source)} WHERE {date_field} >= %s AND {date_field} < %s",
        (start, end),
    )
    if _integer((row or {}).get("row_count")) > 0:
        return EvaluationResult(COMPLETED, "当前报告期存在维度变化数据")
    return evaluate_dependency_completed(context)


def evaluate_minimum_time_in_current_month(context: EvaluationContext) -> EvaluationResult:
    return _evaluate_min_time_current_month(context, _source(context, "primary"))


def evaluate_all_versions_present(context: EvaluationContext) -> EvaluationResult:
    return _evaluate_versions(context, require_all=True)


def evaluate_version_present(context: EvaluationContext) -> EvaluationResult:
    return _evaluate_versions(context, require_all=False)


def evaluate_quarterly_rows_exist(context: EvaluationContext) -> EvaluationResult:
    active_months = {_integer(value) for value in context.step.values.get("active_month", ())}
    if context.current.month not in active_months:
        return EvaluationResult(COMPLETED, "非季度报送月，默认完成")
    source = _source(context, "primary")
    date_field = _column(context, source, "date_field")
    start, end = _month_bounds(context.current.date())
    row = context.query.fetch_one(
        source,
        f"SELECT COUNT(*) AS row_count FROM {_table(context, source)} WHERE {date_field} >= %s AND {date_field} < %s",
        (start, end),
    )
    return _rows_exist(row)


def evaluate_current_month_rows_in_all_sources(context: EvaluationContext) -> EvaluationResult:
    start, end = _month_bounds(context.current.date())
    for source in context.step.sources:
        date_field = _column(context, source, "date_field")
        row = context.query.fetch_one(
            source,
            f"SELECT COUNT(*) AS row_count FROM {_table(context, source)} WHERE {date_field} >= %s AND {date_field} < %s",
            (start, end),
        )
        result = _rows_exist(row)
        if result.status != COMPLETED:
            return result
    return EvaluationResult(COMPLETED, "所有来源在当前月份均有数据")


def _evaluate_no_ck(
    context: EvaluationContext, source: StepSourceConfig, report_date: date
) -> EvaluationResult:
    period = _column(context, source, "period_field")
    check_id = _column(context, source, "check_id_field")
    target_values = context.step.values.get("target_ck_id", ())
    if len(target_values) != 1:
        raise ValueError("必须配置一个 target_ck_id")
    sql = (
        f"SELECT COUNT(*) AS scope_count, "
        f"SUM(CASE WHEN {check_id} = %s THEN 1 ELSE 0 END) AS exception_count "
        f"FROM {_table(context, source)} WHERE {period} = %s"
    )
    return scope_without_exceptions(
        context.query.fetch_one(
            source,
            sql,
            (target_values[0], format_business_report_date(report_date, "underscore")),
        )
    )


def _evaluate_min_time_current_month(
    context: EvaluationContext, source: StepSourceConfig
) -> EvaluationResult:
    time_field = _column(context, source, "time_field")
    row = context.query.fetch_one(
        source,
        f"SELECT COUNT(*) AS row_count, MIN({time_field}) AS minimum_time FROM {_table(context, source)}",
    )
    if _integer((row or {}).get("row_count")) <= 0:
        return EvaluationResult(INCOMPLETE, "当前范围无数据")
    minimum = _as_datetime((row or {}).get("minimum_time"))
    if (minimum.year, minimum.month) != (context.current.year, context.current.month):
        return EvaluationResult(INCOMPLETE, "最早数据时间不在当前月份")
    return EvaluationResult(COMPLETED, "当前月份数据已生成")


def _evaluate_versions(context: EvaluationContext, *, require_all: bool) -> EvaluationResult:
    report_date = _require_report_date(context)
    source = _source(context, "primary")
    manage_code = _column(context, source, "manage_code_field")
    version = _column(context, source, "version_field")
    codes = context.step.values.get("manage_code", ())
    if not codes:
        raise ValueError("未配置 manage_code")
    placeholders = ", ".join(["%s"] * len(codes))
    sql = (
        f"SELECT COUNT(DISTINCT {manage_code}) AS matched_count FROM {_table(context, source)} "
        f"WHERE {manage_code} IN ({placeholders}) AND {version} = %s"
    )
    row = context.query.fetch_one(
        source,
        sql,
        (*codes, format_business_report_date(report_date, "version")),
    )
    matched = _integer((row or {}).get("matched_count"))
    required = len(codes) if require_all else 1
    if matched >= required:
        return EvaluationResult(COMPLETED, "报送版本已归档")
    return EvaluationResult(INCOMPLETE, "报送版本尚未全部归档")


def _source(context: EvaluationContext, role: str) -> StepSourceConfig:
    source = next((item for item in context.step.sources if item.source_role == role), None)
    if source is None:
        raise ValueError(f"未配置数据来源角色：{role}")
    return source


def _column(context: EvaluationContext, source: StepSourceConfig, role: str) -> str:
    column_name = source.fields.get(role)
    if not column_name:
        raise ValueError(f"未配置字段角色：{role}")
    return context.query.quote_column(source, column_name)


def _table(context: EvaluationContext, source: StepSourceConfig) -> str:
    return context.query.qualified_table(source)


def _require_report_date(context: EvaluationContext) -> date:
    if context.business_report_date is None:
        raise WaitingForReportPeriod("等待自动对数报告期")
    return context.business_report_date


def _month_bounds(value: date) -> tuple[date, date]:
    start = value.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, end


def _rows_exist(row: Mapping[str, Any] | None) -> EvaluationResult:
    if _integer((row or {}).get("row_count")) > 0:
        return EvaluationResult(COMPLETED, "当前月份存在数据")
    return EvaluationResult(INCOMPLETE, "当前范围无数据")


def _integer(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if value in (None, ""):
        raise ValueError("时间字段为空")
    return datetime.fromisoformat(str(value))


class WaitingForReportPeriod(RuntimeError):
    pass


def _evaluate_with_report_period_status(evaluator: Callable[[EvaluationContext], EvaluationResult]):
    def wrapped(context: EvaluationContext) -> EvaluationResult:
        try:
            return evaluator(context)
        except WaitingForReportPeriod as exc:
            return EvaluationResult(WAITING_REPORT_PERIOD, str(exc))

    return wrapped


EVALUATORS: dict[str, Callable[[EvaluationContext], EvaluationResult]] = {
    "all_rows_match_report_date": _evaluate_with_report_period_status(evaluate_all_rows_match_report_date),
    "amounts_equal": _evaluate_with_report_period_status(evaluate_amounts_equal),
    "no_blank_fields_and_no_ck": _evaluate_with_report_period_status(evaluate_no_blank_fields_and_no_ck),
    "no_ck_and_min_time": _evaluate_with_report_period_status(evaluate_no_ck_and_min_time),
    "no_pending_status": _evaluate_with_report_period_status(evaluate_no_pending_status),
    "month_rows_or_dependency": _evaluate_with_report_period_status(evaluate_month_rows_or_dependency),
    "default_completed": evaluate_default_completed,
    "minimum_time_in_current_month": evaluate_minimum_time_in_current_month,
    "dependency_completed": evaluate_dependency_completed,
    "all_versions_present": _evaluate_with_report_period_status(evaluate_all_versions_present),
    "date_reached": evaluate_date_reached,
    "quarterly_rows_exist": evaluate_quarterly_rows_exist,
    "current_month_rows_in_all_sources": evaluate_current_month_rows_in_all_sources,
    "version_present": _evaluate_with_report_period_status(evaluate_version_present),
}
