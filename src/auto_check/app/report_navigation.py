from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
import threading
from typing import Any, Callable, Mapping, Protocol, Sequence
import uuid

from sqlalchemy import select

from auto_check.app.app_database import ApplicationDatabase
from auto_check.app.config import DataSourceEntry, load_store
from auto_check.app.db import DatabaseClient, qualified_name, quote_identifier
from auto_check.app.storage_history import RUN_HEADERS
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


@dataclass(frozen=True)
class CollectionResult:
    status: str
    report_month: str
    run_id: int | None
    completed_processes: int
    failed_steps: int
    error_message: str = ""


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


PERIODS = ("week", "month", "quarter", "year")


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


def latest_business_report_date(database: ApplicationDatabase) -> date | None:
    with database.connect() as connection:
        rows = connection.execute(
            select(RUN_HEADERS.c.run_date).where(RUN_HEADERS.c.kind == "reconcile")
        ).mappings().all()
    values = [_coerce_date(row.get("run_date")) for row in rows]
    return max((value for value in values if value is not None), default=None)


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

    @property
    def interval_minutes(self) -> int:
        return self.store.scheduler_interval_minutes()

    def _default_query_executor(self) -> QueryExecutor:
        config_store = load_store(self.config_path, database=self.database)
        return ConfiguredQueryExecutor(config_store.data_sources)

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
        try:
            business_report_date = latest_business_report_date(self.database)
            run_id = self.store.start_run(
                trigger_type, report_month, business_report_date, current
            )
            processes = self.store.load_configuration(report_month)
            overrides = self.store.load_overrides(report_month)
            query = self._query_executor_factory()
            completed_processes = 0
            failed_steps = 0
            process_statuses: list[str] = []

            for process in processes:
                schedule = self.store.ensure_schedule(
                    report_month, process.process_code, now=current
                )
                dependency_statuses: dict[str, str] = {}
                completed_steps = 0
                has_error = False
                for step in process.steps:
                    automatic = self._evaluator(
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
                    is_manual = bool(override and override.completed)
                    effective_status = COMPLETED if is_manual else automatic.status
                    completion_source = "manual" if is_manual else "auto"
                    if effective_status == COMPLETED:
                        completed_steps += 1
                    if automatic.status == ERROR:
                        failed_steps += 1
                        has_error = True
                    dependency_statuses[step.step_code] = effective_status
                    self.store.save_step_snapshot(
                        StepSnapshot(
                            report_month=report_month,
                            step_code=step.step_code,
                            auto_status=automatic.status,
                            effective_status=effective_status,
                            completion_source=completion_source,
                            status_message="管理员手动完成" if is_manual else automatic.message,
                            error_message=automatic.error,
                            auto_completed_at=current if automatic.status == COMPLETED else None,
                            evaluated_at=current,
                            run_id=run_id,
                        )
                    )
                total_steps = len(process.steps)
                if total_steps > 0 and completed_steps == total_steps:
                    process_status = COMPLETED
                    completed_processes += 1
                elif has_error:
                    process_status = ERROR
                else:
                    process_status = INCOMPLETE
                process_statuses.append(process_status)
                self.store.save_process_snapshot(
                    ProcessSnapshot(
                        report_month=report_month,
                        process_code=process.process_code,
                        total_steps=total_steps,
                        completed_steps=completed_steps,
                        status=process_status,
                        completed_at=current if process_status == COMPLETED else None,
                        evaluated_at=current,
                        run_id=run_id,
                    )
                )

            self._save_card_snapshots(
                query=query,
                processes_total=len(processes),
                processes_completed=completed_processes,
                current=current,
                run_id=run_id,
            )
            release_status = "partial" if failed_steps else "completed"
            self.store.finish_run(
                run_id,
                finished_at=current,
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
            )
        except Exception as exc:
            release_error = str(exc)
            if run_id is not None:
                self.store.finish_run(
                    run_id,
                    finished_at=current,
                    status="failed",
                    completed_processes=0,
                    failed_steps=0,
                    error_message=release_error,
                )
            return CollectionResult("failed", report_month, run_id, 0, 0, release_error)
        finally:
            self.store.release_scheduler_lock(
                owner,
                current,
                status=release_status,
                error_message=release_error,
            )

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
            card_payload.append(
                {
                    "card_code": card_code,
                    "name": name,
                    "total_count": snapshot.total_count if snapshot else 0,
                    "completed_count": snapshot.completed_count if snapshot else 0,
                    "incomplete_count": snapshot.incomplete_count if snapshot else 0,
                    "completion_rate": float(snapshot.completion_rate) if snapshot else 0.0,
                    "evaluated_at": _datetime_text(snapshot.evaluated_at) if snapshot else "",
                }
            )
        process_payload = []
        for process in processes:
            process_snapshot = process_snapshots.get(process.process_code)
            schedule = schedules.get(process.process_code)
            steps = []
            for step in process.steps:
                snapshot = step_snapshots.get(step.step_code)
                override = overrides.get(step.step_code)
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
                        ),
                    }
                )
            process_payload.append(
                {
                    "process_code": process.process_code,
                    "process_name": process.process_name,
                    "status": process_snapshot.status if process_snapshot else "pending",
                    "total_steps": process_snapshot.total_steps if process_snapshot else len(process.steps),
                    "completed_steps": process_snapshot.completed_steps if process_snapshot else 0,
                    "completed_at": _datetime_text(process_snapshot.completed_at) if process_snapshot else "",
                    "report_date": schedule.report_date.isoformat() if schedule else "",
                    "report_date_source": schedule.source_type if schedule else "",
                    "schedule_editable": is_admin,
                    "steps": steps,
                }
            )
        business_report_date = latest_business_report_date(self.database)
        return {
            "period": period,
            "report_month": report_month,
            "business_report_date": business_report_date.isoformat() if business_report_date else "",
            "cards": card_payload,
            "processes": process_payload,
            "last_run": _run_payload(last_run),
        }

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
        if step is None or not step.manual_completion_allowed:
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
        process = next(
            (
                item
                for item in self.store.load_configuration(report_month)
                if item.process_code == changed_step.process_code
            ),
            None,
        )
        if process is None:
            raise ValueError("步骤所属节点在当前月份不可用")
        completed_steps = sum(
            1
            for step in process.steps
            if snapshots.get(step.step_code)
            and snapshots[step.step_code].effective_status == COMPLETED
        )
        total_steps = len(process.steps)
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
            f"SELECT COUNT(*) AS total_count, "
            f"SUM(CASE WHEN {status_field} = %s THEN 1 ELSE 0 END) AS completed_count, "
            f"SUM(CASE WHEN {status_field} IS NULL OR {status_field} <> %s THEN 1 ELSE 0 END) AS incomplete_count "
            f"FROM {query.qualified_table(source)} "
            f"WHERE {deleted_field} = %s AND {date_field} >= %s AND {date_field} < %s"
        )
        for period in PERIODS:
            start, end = period_bounds(period, current.date())
            row = query.fetch_one(
                source,
                sql,
                (completed_status, completed_status, valid_deleted, start, end),
            ) or {}
            self.store.save_card_snapshot(
                _card_snapshot(
                    period,
                    "supplement_tasks",
                    _integer(row.get("total_count")),
                    _integer(row.get("completed_count")),
                    _integer(row.get("incomplete_count")),
                    current,
                    run_id,
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
            for card_code in ("data_governance", "special_governance"):
                self.store.save_card_snapshot(
                    _card_snapshot(period, card_code, 0, 0, 0, current, run_id)
                )


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
