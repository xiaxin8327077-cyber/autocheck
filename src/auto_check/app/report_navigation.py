from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from math import ceil
from pathlib import Path
import threading
from time import sleep
from typing import Any, Callable, Mapping, Protocol, Sequence
import uuid

from auto_check.app.app_database import ApplicationDatabase
from auto_check.app.config import DataSourceEntry, load_store
from auto_check.app.db import DatabaseClient, qualified_name, quote_identifier
from auto_check.app.report_navigation_platform import (
    CardProviderRegistry,
    CardStatisticsRequest,
    ProviderManagedCardError,
    ReportProcess,
    SHANGHAI_TZ,
    normalize_aware_datetime,
    validate_statistics_result,
)
from auto_check.app.storage_report_navigation import (
    CardSnapshot,
    ProcessSnapshot,
    ReportNavigationStore,
    ScheduleConfig,
    StepConfig,
    StepSnapshot,
    StepSourceConfig,
)
from auto_check.app.time_utils import beijing_now


COMPLETED = "completed"
INCOMPLETE = "incomplete"
DISPLAY_ONLY = "display_only"
WAITING_REPORT_PERIOD = "waiting_report_period"
ERROR = "error"
MANUAL_REFRESH_COOLDOWN_SECONDS = 300
MANUAL_REFRESH_SETTLE_SECONDS = 0.8


@dataclass(frozen=True)
class EvaluationResult:
    status: str
    message: str
    error: str = ""
    completed_at: datetime | None = None


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


@dataclass(frozen=True)
class CollectionResult:
    status: str
    report_month: str
    run_id: int | None
    completed_processes: int
    failed_steps: int
    error_message: str = ""
    issues: tuple[dict[str, str], ...] = ()
    failed_providers: int = 0
    provider_issues: tuple[dict[str, str], ...] = ()


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


def evaluate_display_only(context: EvaluationContext) -> EvaluationResult:
    return EvaluationResult(DISPLAY_ONLY, "仅展示，不参与完成判断")


def evaluate_all_rows_match_report_date(context: EvaluationContext) -> EvaluationResult:
    return _evaluate_all_rows_match_report_date(context, _source(context, "primary"))


def _evaluate_all_rows_match_report_date(
    context: EvaluationContext, source: StepSourceConfig
) -> EvaluationResult:
    report_date = _require_report_date(context)
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
    return _evaluate_no_ck(
        context,
        _source(context, "ck_result"),
        report_date,
        require_scope=False,
    )


def evaluate_no_ck_and_report_period(context: EvaluationContext) -> EvaluationResult:
    report_date = _require_report_date(context)
    ck_result = _evaluate_no_ck(
        context,
        _source(context, "ck_result"),
        report_date,
        require_scope=False,
    )
    if ck_result.status != COMPLETED:
        return ck_result
    report_period_result = _evaluate_all_rows_match_report_date(
        context,
        _source(context, "spv_detail"),
    )
    if report_period_result.status != COMPLETED:
        return report_period_result
    completion_source = _source(context, "completion_time")
    period = _column(context, completion_source, "period_field")
    create_date = _column(context, completion_source, "create_date_field")
    row = context.query.fetch_one(
        completion_source,
        (
            f"SELECT MAX({create_date}) AS completion_time "
            f"FROM {_table(context, completion_source)} WHERE {period} = %s"
        ),
        (report_date,),
    )
    return EvaluationResult(
        COMPLETED,
        report_period_result.message,
        completed_at=_coerce_datetime((row or {}).get("completion_time")),
    )


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
    context: EvaluationContext,
    source: StepSourceConfig,
    report_date: date,
    *,
    require_scope: bool = True,
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
    row = context.query.fetch_one(
        source,
        sql,
        (target_values[0], format_business_report_date(report_date, "underscore")),
    )
    if require_scope and _integer((row or {}).get("scope_count")) <= 0:
        return EvaluationResult(INCOMPLETE, "当前范围无数据")
    exception_count = _integer((row or {}).get("exception_count"))
    if exception_count > 0:
        return EvaluationResult(INCOMPLETE, f"存在 {exception_count} 条目标校验异常")
    return EvaluationResult(COMPLETED, "报告期内无目标校验异常")


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
    completion_projection = ""
    create_date_field = source.fields.get("create_date_field")
    if create_date_field:
        create_date = context.query.quote_column(source, create_date_field)
        completion_projection = f", MAX({create_date}) AS completion_time"
    sql = (
        f"SELECT COUNT(DISTINCT {manage_code}) AS matched_count{completion_projection} "
        f"FROM {_table(context, source)} "
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
        return EvaluationResult(
            COMPLETED,
            "报送版本已归档",
            completed_at=_coerce_datetime((row or {}).get("completion_time")),
        )
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
        raise WaitingForReportPeriod("等待报送导航报告期")
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
    "no_ck_and_report_period": _evaluate_with_report_period_status(evaluate_no_ck_and_report_period),
    "no_pending_status": _evaluate_with_report_period_status(evaluate_no_pending_status),
    "month_rows_or_dependency": _evaluate_with_report_period_status(evaluate_month_rows_or_dependency),
    "default_completed": evaluate_default_completed,
    "minimum_time_in_current_month": evaluate_minimum_time_in_current_month,
    "dependency_completed": evaluate_dependency_completed,
    "all_versions_present": _evaluate_with_report_period_status(evaluate_all_versions_present),
    "date_reached": evaluate_date_reached,
    "display_only": evaluate_display_only,
    "quarterly_rows_exist": evaluate_quarterly_rows_exist,
    "current_month_rows_in_all_sources": evaluate_current_month_rows_in_all_sources,
    "version_present": _evaluate_with_report_period_status(evaluate_version_present),
}


PERIODS = ("week", "month", "quarter", "year")
GOVERNANCE_CARD_CODES = ("data_governance", "special_governance")


def period_bounds(period: str, today: date) -> tuple[datetime, datetime]:
    if period == "week":
        start_day = today - timedelta(days=today.weekday())
        end_day = start_day + timedelta(days=7)
    elif period == "month":
        start_day = today.replace(day=1)
        end_day = (start_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    elif period == "quarter":
        start_month = ((today.month - 1) // 3) * 3 + 1
        start_day = today.replace(month=start_month, day=1)
        end_month = start_month + 3
        end_year = today.year
        if end_month > 12:
            end_month -= 12
            end_year += 1
        end_day = date(end_year, end_month, 1)
    elif period == "year":
        start_day = date(today.year, 1, 1)
        end_day = date(today.year + 1, 1, 1)
    else:
        raise ValueError("period must be week, month, quarter or year")
    return datetime.combine(start_day, time.min), datetime.combine(end_day, time.min)


def previous_period_bounds(period: str, today: date) -> tuple[datetime, datetime]:
    current_start, _ = period_bounds(period, today)
    current_start_day = current_start.date()
    if period == "week":
        previous_start_day = current_start_day - timedelta(days=7)
    elif period == "month":
        previous_month_end = current_start_day - timedelta(days=1)
        previous_start_day = previous_month_end.replace(day=1)
    elif period == "quarter":
        previous_year = current_start_day.year
        previous_month = current_start_day.month - 3
        if previous_month <= 0:
            previous_month += 12
            previous_year -= 1
        previous_start_day = date(previous_year, previous_month, 1)
    elif period == "year":
        previous_start_day = date(current_start_day.year - 1, 1, 1)
    else:
        raise ValueError("period must be week, month, quarter or year")
    return datetime.combine(previous_start_day, time.min), current_start


def period_storage_key(period: str, value: date) -> str:
    if period == "week":
        iso_year, iso_week, _ = value.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if period == "month":
        return value.strftime("%Y-%m")
    if period == "quarter":
        return f"{value.year}-Q{((value.month - 1) // 3) + 1}"
    if period == "year":
        return str(value.year)
    raise ValueError("period must be week, month, quarter or year")


def report_navigation_business_report_date(current: datetime) -> date:
    return current.date().replace(day=1) - timedelta(days=1)


def _steps_in_dependency_order(steps: Sequence[StepConfig]) -> tuple[StepConfig, ...]:
    pending = list(steps)
    step_codes = {step.step_code for step in pending}
    resolved: set[str] = set()
    ordered: list[StepConfig] = []
    while pending:
        ready = [
            step
            for step in pending
            if all(
                dependency not in step_codes or dependency in resolved
                for dependency in step.dependencies
            )
        ]
        if not ready:
            ordered.extend(pending)
            break
        for step in ready:
            ordered.append(step)
            resolved.add(step.step_code)
            pending.remove(step)
    return tuple(ordered)


class ReportNavigationService:
    def __init__(
        self,
        database: ApplicationDatabase,
        *,
        config_path: str | Path | None = None,
        store: ReportNavigationStore | None = None,
        query_executor_factory: Callable[[], QueryExecutor] | None = None,
        evaluator: Callable[[EvaluationContext], EvaluationResult] = evaluate,
    ):
        self.database = database
        self.config_path = Path(config_path) if config_path is not None else None
        self.store = store or ReportNavigationStore(database)
        self._query_executor_factory = query_executor_factory or self._default_query_executor
        self._evaluator = evaluator
        self._card_providers = CardProviderRegistry(self.store)

    @property
    def interval_minutes(self) -> int:
        return self.store.scheduler_interval_minutes()

    def _default_query_executor(self) -> QueryExecutor:
        config_store = load_store(self.config_path, database=self.database)
        return ConfiguredQueryExecutor(config_store.data_sources)

    def list_report_processes(self) -> tuple[ReportProcess, ...]:
        return tuple(
            ReportProcess(item.process_code, item.process_name, item.display_order, item.active)
            for item in self.store.load_report_processes()
        )

    def register_card_provider(self, **kwargs: Any):
        return self._card_providers.register(**kwargs)

    def collect_once(
        self, *, trigger_type: str = "scheduled", now: datetime | None = None
    ) -> CollectionResult:
        current = now or beijing_now()
        report_month = current.strftime("%Y-%m")
        owner = uuid.uuid4().hex
        if not self.store.try_acquire_scheduler_lock(owner, current, timedelta(minutes=30)):
            return CollectionResult("skipped", report_month, None, 0, 0)
        run_id: int | None = None
        release_status = "failed"
        release_error = ""
        finished_at = current
        try:
            business_report_date = report_navigation_business_report_date(current)
            run_id = self.store.start_run(
                trigger_type, report_month, business_report_date, current
            )
            processes = self.store.load_configuration(report_month)
            overrides = self.store.load_overrides(report_month)
            query = self._query_executor_factory()
            completed_processes = 0
            failed_steps = 0
            issues: list[dict[str, str]] = []
            process_statuses: list[str] = []

            for process in processes:
                judged_steps = [
                    step
                    for step in process.steps
                    if step.evaluator_key != "display_only"
                ]
                schedule = self.store.ensure_schedule(
                    report_month, process.process_code, now=current
                )
                dependency_statuses: dict[str, str] = {}
                automatic_completion_times: dict[str, datetime] = {}
                completed_steps = 0
                has_error = False
                for step in _steps_in_dependency_order(process.steps):
                    display_only = step.evaluator_key == "display_only"
                    logic_result = self._evaluator(
                        EvaluationContext(
                            step=step,
                            business_report_date=business_report_date,
                            current=current,
                            query=query,
                            dependency_statuses=dependency_statuses,
                            schedule=schedule,
                        )
                    )
                    override = overrides.get(step.step_code)
                    is_manual = bool(not display_only and override and override.completed)
                    automatic = logic_result
                    effective_status = COMPLETED if is_manual else automatic.status
                    completion_source = "manual" if is_manual else "auto"
                    if not display_only and effective_status == COMPLETED:
                        completed_steps += 1
                    if automatic.status == ERROR:
                        failed_steps += 1
                        has_error = True
                        issues.append(
                            {
                                "process_code": process.process_code,
                                "process_name": process.process_name,
                                "step_code": step.step_code,
                                "step_name": step.step_name,
                                "error_message": automatic.error or automatic.message or "未知异常",
                            }
                        )
                    dependency_statuses[step.step_code] = effective_status
                    if automatic.completed_at is not None:
                        automatic_completion_times[step.step_code] = automatic.completed_at
                    self.store.save_step_snapshot(
                        StepSnapshot(
                            report_month=report_month,
                            step_code=step.step_code,
                            auto_status=automatic.status,
                            effective_status=effective_status,
                            completion_source=completion_source,
                            status_message="管理员手动完成" if is_manual else automatic.message,
                            error_message=automatic.error,
                            auto_completed_at=(
                                automatic.completed_at or current
                                if automatic.status == COMPLETED
                                else None
                            ),
                            evaluated_at=current,
                            run_id=run_id,
                        ),
                        preserve_auto_completed_at=automatic.completed_at is None,
                    )
                total_steps = len(judged_steps)
                if total_steps > 0 and completed_steps == total_steps:
                    process_status = COMPLETED
                    completed_processes += 1
                elif has_error:
                    process_status = ERROR
                else:
                    process_status = INCOMPLETE
                process_statuses.append(process_status)
                final_step = (
                    max(judged_steps, key=lambda item: item.display_order)
                    if judged_steps
                    else None
                )
                archive_completed_at = (
                    automatic_completion_times.get(final_step.step_code)
                    if final_step is not None
                    else None
                )
                self.store.save_process_snapshot(
                    ProcessSnapshot(
                        report_month=report_month,
                        process_code=process.process_code,
                        total_steps=total_steps,
                        completed_steps=completed_steps,
                        status=process_status,
                        completed_at=(
                            archive_completed_at or current
                            if process_status == COMPLETED
                            else None
                        ),
                        evaluated_at=current,
                        run_id=run_id,
                    ),
                    preserve_completed_at=archive_completed_at is None,
                )

            self._save_card_snapshots(
                query=query,
                processes_total=len(processes),
                processes_completed=completed_processes,
                current=current,
                run_id=run_id,
            )
            provider_issues = self._collect_card_providers(current=current, run_id=run_id)
            failed_providers = len(provider_issues)
            release_status = "partial" if failed_steps or failed_providers else "completed"
            finished_at = current if now is not None else beijing_now()
            self.store.finish_run(
                run_id,
                finished_at=finished_at,
                status=release_status,
                completed_processes=completed_processes,
                failed_steps=failed_steps,
            )
            return CollectionResult(
                release_status,
                report_month,
                run_id,
                completed_processes,
                failed_steps,
                issues=tuple(issues),
                failed_providers=failed_providers,
                provider_issues=tuple(provider_issues),
            )
        except Exception as exc:
            release_error = str(exc)
            finished_at = current if now is not None else beijing_now()
            if run_id is not None:
                self.store.finish_run(
                    run_id,
                    finished_at=finished_at,
                    status="failed",
                    completed_processes=0,
                    failed_steps=0,
                    error_message=release_error,
                )
            return CollectionResult("failed", report_month, run_id, 0, 0, release_error)
        finally:
            self.store.release_scheduler_lock(
                owner,
                finished_at,
                status=release_status,
                error_message=release_error,
            )

    def manual_refresh_state(
        self,
        *,
        current_user: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or beijing_now()
        is_admin = str((current_user or {}).get("role") or "") == "admin"
        last_run = self.store.load_latest_run(trigger_type="manual")
        if not last_run:
            return {
                "allowed": True,
                "running": False,
                "retry_after_seconds": 0,
                "last_finished_at": "",
            }
        started_at = _coerce_datetime(last_run.get("started_at"))
        finished_at = _coerce_datetime(last_run.get("finished_at"))
        running = (
            str(last_run.get("status") or "") == "running"
            and started_at is not None
            and current < started_at + timedelta(minutes=30)
        )
        if running:
            return {
                "allowed": False,
                "running": True,
                "retry_after_seconds": 0,
                "last_finished_at": "",
            }
        retry_after_seconds = 0
        if finished_at is not None and not is_admin:
            retry_after_seconds = max(
                0,
                ceil(
                    (
                        finished_at
                        + timedelta(seconds=MANUAL_REFRESH_COOLDOWN_SECONDS)
                        - current
                    ).total_seconds()
                ),
            )
        return {
            "allowed": retry_after_seconds == 0,
            "running": False,
            "retry_after_seconds": retry_after_seconds,
            "last_finished_at": _datetime_text(finished_at),
        }

    def manual_refresh(
        self,
        *,
        current_user: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        state = self.manual_refresh_state(current_user=current_user, now=now)
        if not state["allowed"]:
            if state["running"]:
                return {
                    "status": "skipped",
                    **state,
                    "issues": [],
                    "error_message": "统计任务正在执行，请等待完成后再刷新",
                }
            wait_minutes = max(1, ceil(int(state["retry_after_seconds"]) / 60))
            return {
                "status": "cooldown",
                **state,
                "issues": [],
                "error_message": f"刷新间隔为 5 分钟，请等待约 {wait_minutes} 分钟后再试",
            }

        if now is None:
            sleep(MANUAL_REFRESH_SETTLE_SECONDS)
        result = self.collect_once(trigger_type="manual", now=now)
        if result.status == "skipped":
            return {
                "status": "skipped",
                "allowed": False,
                "running": True,
                "retry_after_seconds": 0,
                "issues": [],
                "error_message": "统计任务正在执行，请等待完成后再刷新",
            }
        refreshed_state = self.manual_refresh_state(current_user=current_user, now=now)
        error_message = result.error_message
        if result.status == "partial" and not error_message:
            if result.failed_steps:
                error_message = f"刷新完成，但有 {result.failed_steps} 个步骤统计异常，请查看具体问题"
            else:
                error_message = f"刷新完成，但有 {result.failed_providers} 个模块统计异常，请查看具体问题"
        return {
            "status": result.status,
            "run_id": result.run_id,
            "completed_processes": result.completed_processes,
            "failed_steps": result.failed_steps,
            "error_message": error_message,
            "issues": [dict(issue) for issue in result.issues],
            "failed_providers": result.failed_providers,
            "provider_issues": [dict(issue) for issue in result.provider_issues],
            "cooldown_seconds": (
                0
                if str((current_user or {}).get("role") or "") == "admin"
                else MANUAL_REFRESH_COOLDOWN_SECONDS
            ),
            "retry_after_seconds": int(refreshed_state["retry_after_seconds"]),
            "allowed": bool(refreshed_state["allowed"]),
            "running": False,
        }

    def dashboard(
        self,
        *,
        period: str,
        current_user: Mapping[str, Any] | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if period not in PERIODS:
            raise ValueError("period must be week, month, quarter or year")
        current = now or beijing_now()
        report_month = current.strftime("%Y-%m")
        processes = self.store.load_configuration(report_month)
        process_snapshots = self.store.load_process_snapshots(report_month)
        step_snapshots = self.store.load_step_snapshots(report_month)
        overrides = self.store.load_overrides(report_month)
        schedules = self.store.load_schedules(report_month)
        cards = self.store.load_card_snapshots(period)
        provider_states = self.store.load_card_provider_states()
        is_admin = str((current_user or {}).get("role") or "") == "admin"
        last_run = self.store.load_latest_run()
        card_order = (
            ("report_forms", "报送报表"),
            ("supplement_tasks", "补录任务"),
            ("data_governance", "数据治理流程"),
            ("special_governance", "报表特殊治理"),
        )
        card_payload = []
        for card_code, name in card_order:
            snapshot = cards.get(card_code)
            provider_state = provider_states.get(card_code)
            manual_history = (
                self.store.load_manual_card_history(card_code)
                if card_code in GOVERNANCE_CARD_CODES and provider_state is None
                else {}
            )
            current_period_key = period_storage_key(period, current.date())
            previous_period_start, _ = previous_period_bounds(period, current.date())
            previous_period_key = period_storage_key(period, previous_period_start.date())
            manual_value = manual_history.get((period, current_period_key))
            previous_manual_value = manual_history.get((period, previous_period_key))
            if provider_state is not None:
                available = snapshot is not None and provider_state.last_success_at is not None
                total_count = snapshot.total_count if available else None
                completed_count = snapshot.completed_count if available else None
                incomplete_count = snapshot.incomplete_count if available else None
                completion_rate = float(snapshot.completion_rate) if available else None
                evaluated_at = _datetime_text(snapshot.evaluated_at) if available else ""
            elif manual_value is not None:
                completed_count = manual_value.completed_count
                incomplete_count = manual_value.incomplete_count
                total_count = completed_count + incomplete_count
                completion_rate = (
                    float(Decimal(completed_count * 100) / Decimal(total_count))
                    if total_count
                    else 0.0
                )
                evaluated_at = _datetime_text(manual_value.updated_at)
            else:
                total_count = snapshot.total_count if snapshot else 0
                completed_count = snapshot.completed_count if snapshot else 0
                incomplete_count = snapshot.incomplete_count if snapshot else 0
                completion_rate = float(snapshot.completion_rate) if snapshot else 0.0
                evaluated_at = _datetime_text(snapshot.evaluated_at) if snapshot else ""
            card = {
                    "card_code": card_code,
                    "name": name,
                    "total_count": total_count,
                    "completed_count": completed_count,
                    "incomplete_count": incomplete_count,
                    "completion_rate": completion_rate,
                    "evaluated_at": evaluated_at,
                    "comparison_delta": (
                        snapshot.comparison_delta
                        if provider_state is not None and snapshot is not None and available
                        else (
                        snapshot.comparison_delta
                        if card_code == "supplement_tasks" and snapshot is not None
                        else (
                            completed_count - previous_manual_value.completed_count
                            if card_code in GOVERNANCE_CARD_CODES
                            and manual_value is not None
                            and previous_manual_value is not None
                            else None
                        )
                        )
                    ),
                }
            if provider_state is not None:
                card.update(
                    source="provider",
                    available=available,
                    stale=provider_state.stale,
                    provider_active=provider_state.provider_active,
                    snapshot_period_key=(
                        period_storage_key(period, snapshot.evaluated_at.date())
                        if available and snapshot is not None
                        else ""
                    ),
                    semantics_version=provider_state.semantics_version,
                )
            card_payload.append(card)
        card_maintenance = {}
        if is_admin:
            for card_code in GOVERNANCE_CARD_CODES:
                provider_state = provider_states.get(card_code)
                if provider_state is not None:
                    card_maintenance[card_code] = {
                        "editable": False,
                        "source": "provider",
                        "provider_active": provider_state.provider_active,
                    }
                    continue
                saved_values = self.store.load_manual_card_history(card_code)
                card_maintenance[card_code] = {
                    stat_period: {
                        "completed_count": saved_values.get(
                            (stat_period, period_storage_key(stat_period, current.date()))
                        ).completed_count
                        if saved_values.get(
                            (stat_period, period_storage_key(stat_period, current.date()))
                        )
                        else 0,
                        "incomplete_count": saved_values.get(
                            (stat_period, period_storage_key(stat_period, current.date()))
                        ).incomplete_count
                        if saved_values.get(
                            (stat_period, period_storage_key(stat_period, current.date()))
                        )
                        else 0,
                    }
                    for stat_period in PERIODS
                }
        process_payload = []
        for process in processes:
            process_snapshot = process_snapshots.get(process.process_code)
            schedule = schedules.get(process.process_code)
            steps = []
            for step in process.steps:
                snapshot = step_snapshots.get(step.step_code)
                override = overrides.get(step.step_code)
                display_only = step.evaluator_key == "display_only"
                steps.append(
                    {
                        "step_code": step.step_code,
                        "step_name": step.step_name,
                        "status": snapshot.effective_status if snapshot else "pending",
                        "auto_status": snapshot.auto_status if snapshot else "pending",
                        "completion_source": snapshot.completion_source if snapshot else "auto",
                        "status_message": snapshot.status_message if snapshot else "等待首次统计",
                        "error_message": snapshot.error_message if snapshot else "",
                        "manual_completed": bool(override and override.completed),
                        "manual_completion_allowed": bool(
                            is_admin
                            and process.allow_manual_step_completion
                            and step.manual_completion_allowed
                            and not display_only
                        ),
                        "display_only": display_only,
                    }
                )
            judged_steps = [
                step for step in process.steps if step.evaluator_key != "display_only"
            ]
            process_payload.append(
                {
                    "process_code": process.process_code,
                    "process_name": process.process_name,
                    "status": process_snapshot.status if process_snapshot else "pending",
                    "total_steps": process_snapshot.total_steps if process_snapshot else len(judged_steps),
                    "completed_steps": process_snapshot.completed_steps if process_snapshot else 0,
                    "completed_at": _datetime_text(process_snapshot.completed_at) if process_snapshot else "",
                    "report_date": schedule.report_date.isoformat() if schedule else "",
                    "report_date_source": schedule.source_type if schedule else "",
                    "schedule_editable": is_admin,
                    "owner_name": schedule.owner_name if schedule else "",
                    "owner_editable": is_admin,
                    "steps": steps,
                }
            )
        business_report_date = report_navigation_business_report_date(current)
        work_calendar = self.store.load_work_calendar(current.year)
        return {
            "period": period,
            "report_month": report_month,
            "business_report_date": business_report_date.isoformat() if business_report_date else "",
            "cards": card_payload,
            "card_maintenance": card_maintenance,
            "processes": process_payload,
            "work_calendar": work_calendar,
            "last_run": _run_payload(last_run),
            "manual_refresh": self.manual_refresh_state(
                current_user=current_user,
                now=current,
            ),
        }

    def update_card_manual_values(
        self,
        card_code: str,
        values: Mapping[str, Mapping[str, Any]],
        current_user: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if str(current_user.get("role") or "") != "admin":
            raise ValueError("仅管理员可以维护治理统计")
        if card_code not in GOVERNANCE_CARD_CODES:
            raise ValueError("仅支持维护数据治理流程和报表特殊治理")
        if self.store.load_card_provider_state(card_code) is not None:
            raise ProviderManagedCardError("card statistics are managed by a provider")
        if not isinstance(values, Mapping) or set(values) != set(PERIODS):
            raise ValueError("必须同时提供本周、本月、本季度和本年数据")
        normalized: dict[str, dict[str, int]] = {}
        for stat_period in PERIODS:
            row = values.get(stat_period)
            if not isinstance(row, Mapping):
                raise ValueError("统计周期数据格式不正确")
            raw_completed = row.get("completed_count")
            raw_incomplete = row.get("incomplete_count")
            if (
                isinstance(raw_completed, bool)
                or isinstance(raw_incomplete, bool)
                or not isinstance(raw_completed, int)
                or not isinstance(raw_incomplete, int)
            ):
                raise ValueError("已完成和未完成数量必须为整数")
            completed_count = raw_completed
            incomplete_count = raw_incomplete
            if completed_count < 0 or incomplete_count < 0:
                raise ValueError("已完成和未完成数量不能小于 0")
            normalized[stat_period] = {
                "completed_count": completed_count,
                "incomplete_count": incomplete_count,
            }
        current = now or beijing_now()
        self.store.save_manual_card_values(
            card_code,
            normalized,
            current_user,
            now=current,
            period_keys={
                stat_period: period_storage_key(stat_period, current.date())
                for stat_period in PERIODS
            },
        )
        return {"ok": True, "card_code": card_code}

    def set_manual_state(
        self,
        step_code: str,
        action: str,
        report_month: str,
        current_user: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or beijing_now()
        if report_month != current.strftime("%Y-%m"):
            raise ValueError("只允许维护当前月的步骤状态")
        step = self.store.load_step_config(step_code)
        process = next(
            (
                item
                for item in self.store.load_configuration(report_month)
                if item.process_code == (step.process_code if step else "")
            ),
            None,
        )
        if (
            step is None
            or process is None
            or not process.allow_manual_step_completion
            or not step.manual_completion_allowed
        ):
            raise ValueError("步骤不存在或不允许手动完成")
        if action == "manual-complete":
            self.store.set_manual_complete(report_month, step_code, current_user, now=current)
        elif action == "manual-cancel":
            self.store.cancel_manual_complete(report_month, step_code)
        else:
            raise ValueError("无效的人工状态操作")
        self._recalculate_manual_process(report_month, step, current)
        return {"ok": True, "step_code": step_code, "action": action}

    def update_schedule(
        self,
        process_code: str,
        report_month: str,
        report_date_text: str,
        current_user: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or beijing_now()
        try:
            report_date = date.fromisoformat(report_date_text)
            month_start = date.fromisoformat(f"{report_month}-01")
        except ValueError as exc:
            raise ValueError("报送月份或日期格式不正确") from exc
        current_month = current.date().replace(day=1)
        if month_start < current_month:
            raise ValueError("历史月份不允许修改")
        if report_date.strftime("%Y-%m") != report_month:
            raise ValueError("报送日期必须属于对应报送月份")
        if not self.store.process_exists(process_code):
            raise ValueError("报送节点不存在")
        self.store.upsert_schedule(
            report_month,
            process_code,
            report_date,
            source_type="manual",
            source_year=report_date.year,
            updated_by=str(current_user.get("username") or ""),
            now=current,
        )
        return {
            "ok": True,
            "process_code": process_code,
            "report_month": report_month,
            "report_date": report_date.isoformat(),
        }

    def update_schedule_owner(
        self,
        process_code: str,
        report_month: str,
        owner_name: str,
        current_user: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if str(current_user.get("role") or "") != "admin":
            raise ValueError("仅管理员可以维护负责人")
        current = now or beijing_now()
        try:
            month_start = date.fromisoformat(f"{report_month}-01")
        except ValueError as exc:
            raise ValueError("报送月份格式不正确") from exc
        if month_start < current.date().replace(day=1):
            raise ValueError("历史月份不允许修改负责人")
        normalized_owner = str(owner_name or "").strip()
        if len(normalized_owner) > 128:
            raise ValueError("负责人不能超过 128 个字符")
        if not self.store.process_exists(process_code):
            raise ValueError("报送节点不存在")
        self.store.update_schedule_owner(
            report_month,
            process_code,
            normalized_owner,
            updated_by=str(current_user.get("username") or ""),
            now=current,
        )
        return {
            "ok": True,
            "process_code": process_code,
            "report_month": report_month,
            "owner_name": normalized_owner,
        }

    def _recalculate_manual_process(
        self, report_month: str, changed_step: StepConfig, current: datetime
    ) -> None:
        snapshots = self.store.load_step_snapshots(report_month)
        overrides = self.store.load_overrides(report_month)
        existing = snapshots.get(changed_step.step_code)
        if existing is None:
            existing = StepSnapshot(
                report_month,
                changed_step.step_code,
                INCOMPLETE,
                INCOMPLETE,
                "auto",
                "等待首次统计",
                "",
                None,
                current,
                None,
            )
        manual = overrides.get(changed_step.step_code)
        changed = StepSnapshot(
            report_month=existing.report_month,
            step_code=existing.step_code,
            auto_status=existing.auto_status,
            effective_status=COMPLETED if manual and manual.completed else existing.auto_status,
            completion_source="manual" if manual and manual.completed else "auto",
            status_message="管理员手动完成" if manual and manual.completed else existing.status_message,
            error_message=existing.error_message,
            auto_completed_at=existing.auto_completed_at,
            evaluated_at=current,
            run_id=existing.run_id,
        )
        self.store.save_step_snapshot(changed)
        snapshots[changed.step_code] = changed
        configurations = self.store.load_configuration(report_month)
        process = next(
            (
                item
                for item in configurations
                if item.process_code == changed_step.process_code
            ),
            None,
        )
        if process is None:
            raise ValueError("步骤所属节点在当前月份不可用")
        completed_steps = sum(
            1
            for step in process.steps
            if step.evaluator_key != "display_only"
            if snapshots.get(step.step_code)
            and snapshots[step.step_code].effective_status == COMPLETED
        )
        total_steps = sum(
            1 for step in process.steps if step.evaluator_key != "display_only"
        )
        status = COMPLETED if total_steps > 0 and completed_steps == total_steps else INCOMPLETE
        run_id = max(
            (snapshot.run_id or 0 for snapshot in snapshots.values()),
            default=0,
        ) or None
        self.store.save_process_snapshot(
            ProcessSnapshot(
                report_month,
                process.process_code,
                total_steps,
                completed_steps,
                status,
                current if status == COMPLETED else None,
                current,
                run_id,
            )
        )
        process_snapshots = self.store.load_process_snapshots(report_month)
        completed_processes = sum(
            1
            for item in configurations
            if process_snapshots.get(item.process_code)
            and process_snapshots[item.process_code].status == COMPLETED
        )
        for period in PERIODS:
            self.store.save_card_snapshot(
                _card_snapshot(
                    period,
                    "report_forms",
                    len(configurations),
                    completed_processes,
                    len(configurations) - completed_processes,
                    current,
                    run_id,
                )
            )

    def _save_card_snapshots(
        self,
        *,
        query: QueryExecutor,
        processes_total: int,
        processes_completed: int,
        current: datetime,
        run_id: int,
    ) -> None:
        supplement_step = self.store.load_step_config("supplement_tasks_1")
        if supplement_step is None or len(supplement_step.sources) != 1:
            raise ValueError("补录任务统计配置缺失")
        source = supplement_step.sources[0]
        date_field = query.quote_column(source, _required_field(source, "date_field"))
        status_field = query.quote_column(source, _required_field(source, "status_field"))
        deleted_field = query.quote_column(source, _required_field(source, "deleted_field"))
        completed_status = _single_value(supplement_step, "completed_status")
        valid_deleted = _single_value(supplement_step, "valid_deleted_value")
        sql = (
            f"SELECT "
            f"SUM(CASE WHEN {date_field} >= %s AND {date_field} < %s THEN 1 ELSE 0 END) AS total_count, "
            f"SUM(CASE WHEN {date_field} >= %s AND {date_field} < %s AND {status_field} = %s THEN 1 ELSE 0 END) AS completed_count, "
            f"SUM(CASE WHEN {date_field} >= %s AND {date_field} < %s AND ({status_field} IS NULL OR {status_field} <> %s) THEN 1 ELSE 0 END) AS incomplete_count, "
            f"SUM(CASE WHEN {date_field} >= %s AND {date_field} < %s AND {status_field} = %s THEN 1 ELSE 0 END) AS previous_completed_count "
            f"FROM {query.qualified_table(source)} "
            f"WHERE {deleted_field} = %s AND {date_field} >= %s AND {date_field} < %s"
        )
        for period in PERIODS:
            start, end = period_bounds(period, current.date())
            previous_start, previous_end = previous_period_bounds(period, current.date())
            row = query.fetch_one(
                source,
                sql,
                (
                    start,
                    end,
                    start,
                    end,
                    completed_status,
                    start,
                    end,
                    completed_status,
                    previous_start,
                    previous_end,
                    completed_status,
                    valid_deleted,
                    previous_start,
                    end,
                ),
            ) or {}
            completed_count = _integer(row.get("completed_count"))
            previous_completed_count = _integer(row.get("previous_completed_count"))
            self.store.save_card_snapshot(
                _card_snapshot(
                    period,
                    "supplement_tasks",
                    _integer(row.get("total_count")),
                    completed_count,
                    _integer(row.get("incomplete_count")),
                    current,
                    run_id,
                    comparison_delta=completed_count - previous_completed_count,
                )
            )
            self.store.save_card_snapshot(
                _card_snapshot(
                    period,
                    "report_forms",
                    processes_total,
                    processes_completed,
                    processes_total - processes_completed,
                    current,
                    run_id,
                )
            )

    def _collect_card_providers(
        self, *, current: datetime, run_id: int
    ) -> list[dict[str, str]]:
        as_of = (
            current.replace(tzinfo=SHANGHAI_TZ)
            if current.tzinfo is None or current.utcoffset() is None
            else normalize_aware_datetime(current)
        )
        issues: list[dict[str, str]] = []
        for registration in self._card_providers.active_registrations():
            try:
                snapshots: list[CardSnapshot] = []
                for period in PERIODS:
                    start, end = period_bounds(period, current.date())
                    previous_start, previous_end = previous_period_bounds(
                        period, current.date()
                    )
                    request = CardStatisticsRequest(
                        card_code=registration.card_code,
                        period_kind=period,
                        period_start=start.replace(tzinfo=SHANGHAI_TZ),
                        period_end_exclusive=end.replace(tzinfo=SHANGHAI_TZ),
                        previous_period_start=previous_start.replace(tzinfo=SHANGHAI_TZ),
                        previous_period_end_exclusive=previous_end.replace(tzinfo=SHANGHAI_TZ),
                        as_of=as_of,
                    )
                    result = validate_statistics_result(
                        registration.provider(request),
                        semantics_version=registration.semantics_version,
                    )
                    snapshots.append(
                        _card_snapshot(
                            period,
                            registration.card_code,
                            result.total,
                            result.completed,
                            result.incomplete,
                            result.generated_at.replace(tzinfo=None),
                            run_id,
                            comparison_delta=result.completed - result.previous_completed,
                        )
                    )
                self._card_providers.apply_if_current(
                    registration,
                    lambda: self.store.save_card_provider_success(
                        registration.card_code,
                        registration.owner,
                        registration.semantics_version,
                        snapshots,
                        attempted_at=current,
                        period_key=period_storage_key("month", current.date()),
                    ),
                )
            except Exception:
                issue = {
                    "card_code": registration.card_code,
                    "error_message": "provider statistics failed",
                }
                recorded = self._card_providers.apply_if_current(
                    registration,
                    lambda: self.store.mark_card_provider_failure(
                        registration.card_code,
                        registration.owner,
                        registration.semantics_version,
                        attempted_at=current,
                        error_message="provider statistics failed",
                    ),
                )
                if recorded:
                    issues.append(issue)
        return issues


class ReportNavigationScheduler:
    def __init__(
        self,
        service: Any,
        *,
        initial_delay_seconds: float = 30.0,
        interval_seconds: float | None = None,
    ):
        self.service = service
        self.initial_delay_seconds = initial_delay_seconds
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._activity = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="report-navigation-scheduler",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        if self._stop.wait(self.initial_delay_seconds):
            return
        while not self._stop.is_set():
            self.service.collect_once()
            self._activity.set()
            interval = (
                self.interval_seconds
                if self.interval_seconds is not None
                else max(1, int(self.service.interval_minutes)) * 60
            )
            if self._stop.wait(interval):
                return

    def wait_for_activity(self, timeout: float) -> bool:
        active = self._activity.wait(timeout)
        if active:
            self._activity.clear()
        return active

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)


def _datetime_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _date_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _run_payload(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": int(row.get("id") or 0),
        "trigger_type": str(row.get("trigger_type") or ""),
        "report_month": str(row.get("report_month") or ""),
        "business_report_date": _date_text(row.get("business_report_date")),
        "started_at": _datetime_text(row.get("started_at")),
        "finished_at": _datetime_text(row.get("finished_at")),
        "status": str(row.get("status") or ""),
        "completed_processes": int(row.get("completed_processes") or 0),
        "failed_steps": int(row.get("failed_steps") or 0),
        "error_message": str(row.get("error_message") or ""),
    }


def _card_snapshot(
    period: str,
    card_code: str,
    total: int,
    completed: int,
    incomplete: int,
    evaluated_at: datetime,
    run_id: int,
    *,
    comparison_delta: int | None = None,
) -> CardSnapshot:
    rate = Decimal("0") if total <= 0 else (Decimal(completed) * Decimal("100") / Decimal(total))
    return CardSnapshot(
        period,
        card_code,
        total,
        completed,
        incomplete,
        rate.quantize(Decimal("0.0001")),
        evaluated_at,
        run_id,
        comparison_delta,
    )


def _required_field(source: StepSourceConfig, role: str) -> str:
    value = source.fields.get(role)
    if not value:
        raise ValueError(f"未配置字段角色：{role}")
    return value


def _single_value(step: StepConfig, role: str) -> str:
    values = step.values.get(role, ())
    if len(values) != 1:
        raise ValueError(f"必须配置一个业务值：{role}")
    return values[0]


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    return date.fromisoformat(str(value))


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value))
