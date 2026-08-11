from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    delete,
    select,
    text,
)
from sqlalchemy.dialects.mysql import insert as mysql_insert

from auto_check.app.app_database import ApplicationDatabase
from auto_check.app.time_utils import beijing_now


METADATA = MetaData()

REPORT_NAV_PROCESSES = Table(
    "report_nav_processes",
    METADATA,
    Column("process_code", String(64), primary_key=True),
    Column("process_name", String(128), nullable=False),
    Column("display_order", Integer, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("allow_manual_step_completion", Boolean, nullable=False),
)
REPORT_NAV_PROCESS_MONTHS = Table(
    "report_nav_process_months",
    METADATA,
    Column("process_code", String(64), primary_key=True),
    Column("month_no", SmallInteger, primary_key=True),
)
REPORT_NAV_STEPS = Table(
    "report_nav_steps",
    METADATA,
    Column("step_code", String(64), primary_key=True),
    Column("process_code", String(64), nullable=False),
    Column("step_name", String(255), nullable=False),
    Column("display_order", Integer, nullable=False),
    Column("evaluator_key", String(64), nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("default_completed", Boolean, nullable=False),
    Column("manual_completion_allowed", Boolean, nullable=False),
)
REPORT_NAV_STEP_DEPENDENCIES = Table(
    "report_nav_step_dependencies",
    METADATA,
    Column("step_code", String(64), primary_key=True),
    Column("depends_on_step_code", String(64), primary_key=True),
)
REPORT_NAV_STEP_SOURCES = Table(
    "report_nav_step_sources",
    METADATA,
    Column("id", BigInteger, primary_key=True),
    Column("step_code", String(64), nullable=False),
    Column("source_role", String(64), nullable=False),
    Column("data_source_name", String(128), nullable=False),
    Column("table_name", String(255), nullable=False),
    Column("display_order", Integer, nullable=False),
    Column("enabled", Boolean, nullable=False),
)
REPORT_NAV_STEP_FIELDS = Table(
    "report_nav_step_fields",
    METADATA,
    Column("id", BigInteger, primary_key=True),
    Column("step_source_id", BigInteger, nullable=False),
    Column("field_role", String(64), nullable=False),
    Column("column_name", String(128), nullable=False),
)
REPORT_NAV_STEP_VALUES = Table(
    "report_nav_step_values",
    METADATA,
    Column("id", BigInteger, primary_key=True),
    Column("step_code", String(64), nullable=False),
    Column("value_role", String(64), nullable=False),
    Column("value_text", String(255), nullable=False),
    Column("value_type", String(32), nullable=False),
    Column("display_order", Integer, nullable=False),
)
REPORT_NAV_STEP_OVERRIDES = Table(
    "report_nav_step_overrides",
    METADATA,
    Column("report_month", String(7), primary_key=True),
    Column("step_code", String(64), primary_key=True),
    Column("completed", Boolean, nullable=False),
    Column("operator_id", String(64), nullable=False),
    Column("operator_username", String(128), nullable=False),
    Column("operator_name", String(128), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
REPORT_NAV_STEP_SNAPSHOTS = Table(
    "report_nav_step_snapshots",
    METADATA,
    Column("report_month", String(7), primary_key=True),
    Column("step_code", String(64), primary_key=True),
    Column("auto_status", String(32), nullable=False),
    Column("effective_status", String(32), nullable=False),
    Column("completion_source", String(32), nullable=False),
    Column("status_message", String(255), nullable=False),
    Column("error_message", Text),
    Column("auto_completed_at", DateTime),
    Column("evaluated_at", DateTime, nullable=False),
    Column("run_id", BigInteger),
)
REPORT_NAV_PROCESS_SNAPSHOTS = Table(
    "report_nav_process_snapshots",
    METADATA,
    Column("report_month", String(7), primary_key=True),
    Column("process_code", String(64), primary_key=True),
    Column("total_steps", Integer, nullable=False),
    Column("completed_steps", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("completed_at", DateTime),
    Column("evaluated_at", DateTime, nullable=False),
    Column("run_id", BigInteger),
)
REPORT_NAV_CARD_SNAPSHOTS = Table(
    "report_nav_card_snapshots",
    METADATA,
    Column("stat_period", String(16), primary_key=True),
    Column("card_code", String(64), primary_key=True),
    Column("total_count", Integer, nullable=False),
    Column("completed_count", Integer, nullable=False),
    Column("incomplete_count", Integer, nullable=False),
    Column("comparison_delta", Integer),
    Column("completion_rate", Numeric(7, 4), nullable=False),
    Column("evaluated_at", DateTime, nullable=False),
    Column("run_id", BigInteger),
)
REPORT_NAV_CARD_MANUAL_VALUES = Table(
    "report_nav_card_manual_values",
    METADATA,
    Column("stat_period", String(16), primary_key=True),
    Column("card_code", String(64), primary_key=True),
    Column("completed_count", Integer, nullable=False),
    Column("incomplete_count", Integer, nullable=False),
    Column("operator_id", String(64), nullable=False),
    Column("operator_username", String(128), nullable=False),
    Column("operator_name", String(128), nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
REPORT_NAV_CARD_MANUAL_HISTORY = Table(
    "report_nav_card_manual_history",
    METADATA,
    Column("stat_period", String(16), primary_key=True),
    Column("period_key", String(16), primary_key=True),
    Column("card_code", String(64), primary_key=True),
    Column("completed_count", Integer, nullable=False),
    Column("incomplete_count", Integer, nullable=False),
    Column("operator_id", String(64), nullable=False),
    Column("operator_username", String(128), nullable=False),
    Column("operator_name", String(128), nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
REPORT_NAV_MONTHLY_SCHEDULES = Table(
    "report_nav_monthly_schedules",
    METADATA,
    Column("report_month", String(7), primary_key=True),
    Column("process_code", String(64), primary_key=True),
    Column("report_date", Date, nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("source_year", SmallInteger),
    Column("owner_name", String(128)),
    Column("updated_by", String(128), nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
REPORT_NAV_WORK_CALENDAR = Table(
    "report_nav_work_calendar",
    METADATA,
    Column("calendar_date", Date, primary_key=True),
    Column("calendar_year", SmallInteger, nullable=False),
    Column("day_type", String(32), nullable=False),
    Column("day_name", String(64), nullable=False),
    Column("source_document", String(255), nullable=False),
    Column("updated_by", String(128), nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
REPORT_NAV_STAT_RUNS = Table(
    "report_nav_stat_runs",
    METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("trigger_type", String(32), nullable=False),
    Column("report_month", String(7), nullable=False),
    Column("business_report_date", Date),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime),
    Column("status", String(32), nullable=False),
    Column("completed_processes", Integer, nullable=False),
    Column("failed_steps", Integer, nullable=False),
    Column("failed_providers", Integer, nullable=False),
    Column("error_message", Text),
)
REPORT_NAV_SCHEDULER_STATE = Table(
    "report_nav_scheduler_state",
    METADATA,
    Column("id", SmallInteger, primary_key=True),
    Column("enabled", Boolean, nullable=False),
    Column("interval_minutes", Integer, nullable=False),
    Column("next_run_at", DateTime),
    Column("lock_owner", String(64)),
    Column("lock_until", DateTime),
    Column("last_started_at", DateTime),
    Column("last_finished_at", DateTime),
    Column("last_status", String(32)),
    Column("last_error", Text),
    Column("updated_at", DateTime, nullable=False),
)
REPORT_NAV_CARD_PROVIDER_STATES = Table(
    "report_nav_card_provider_states",
    METADATA,
    Column("card_code", String(64), primary_key=True),
    Column("owner", String(64), nullable=False),
    Column("registration_token", String(64), nullable=False),
    Column("semantics_version", Integer, nullable=False),
    Column("provider_active", Boolean, nullable=False),
    Column("stale", Boolean, nullable=False),
    Column("last_attempt_at", DateTime),
    Column("last_success_at", DateTime),
    Column("last_success_period_key", String(16)),
    Column("last_error", Text),
    Column("updated_at", DateTime, nullable=False),
)


@dataclass(frozen=True)
class StepSourceConfig:
    id: int
    source_role: str
    data_source_name: str
    table_name: str
    display_order: int
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StepConfig:
    step_code: str
    process_code: str
    step_name: str
    display_order: int
    evaluator_key: str
    default_completed: bool
    manual_completion_allowed: bool
    dependencies: tuple[str, ...] = ()
    sources: tuple[StepSourceConfig, ...] = ()
    values: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ProcessConfig:
    process_code: str
    process_name: str
    display_order: int
    allow_manual_step_completion: bool
    steps: tuple[StepConfig, ...] = ()


@dataclass(frozen=True)
class ReportProcessRecord:
    process_code: str
    process_name: str
    display_order: int
    active: bool


@dataclass(frozen=True)
class ManualOverride:
    report_month: str
    step_code: str
    completed: bool
    operator_id: str
    operator_username: str
    operator_name: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ScheduleConfig:
    report_month: str
    process_code: str
    report_date: date
    source_type: str
    source_year: int | None
    updated_by: str
    updated_at: datetime
    owner_name: str = ""


@dataclass(frozen=True)
class StepSnapshot:
    report_month: str
    step_code: str
    auto_status: str
    effective_status: str
    completion_source: str
    status_message: str
    error_message: str
    auto_completed_at: datetime | None
    evaluated_at: datetime
    run_id: int | None


@dataclass(frozen=True)
class ProcessSnapshot:
    report_month: str
    process_code: str
    total_steps: int
    completed_steps: int
    status: str
    completed_at: datetime | None
    evaluated_at: datetime
    run_id: int | None


@dataclass(frozen=True)
class CardSnapshot:
    stat_period: str
    card_code: str
    total_count: int
    completed_count: int
    incomplete_count: int
    completion_rate: Decimal
    evaluated_at: datetime
    run_id: int | None
    comparison_delta: int | None = None


@dataclass(frozen=True)
class ManualCardValue:
    stat_period: str
    card_code: str
    completed_count: int
    incomplete_count: int
    operator_id: str
    operator_username: str
    operator_name: str
    updated_at: datetime


@dataclass(frozen=True)
class ManualCardHistoryValue:
    stat_period: str
    period_key: str
    card_code: str
    completed_count: int
    incomplete_count: int
    operator_id: str
    operator_username: str
    operator_name: str
    updated_at: datetime


@dataclass(frozen=True)
class CardProviderState:
    card_code: str
    owner: str
    registration_token: str
    semantics_version: int
    provider_active: bool
    stale: bool
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_success_period_key: str
    last_error: str
    updated_at: datetime


class ReportNavigationStore:
    def __init__(self, database: ApplicationDatabase):
        self.database = database

    def load_report_processes(self) -> tuple[ReportProcessRecord, ...]:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_PROCESSES)
        return tuple(
            ReportProcessRecord(
                process_code=str(row["process_code"]),
                process_name=str(row["process_name"]),
                display_order=int(row["display_order"]),
                active=bool(row.get("enabled")),
            )
            for row in sorted(
                rows,
                key=lambda row: (int(row.get("display_order") or 0), str(row.get("process_code") or "")),
            )
        )

    def load_configuration(self, report_month: str) -> list[ProcessConfig]:
        month_no = _parse_report_month(report_month)[1]
        with self.database.connect() as connection:
            process_rows = _rows(connection, REPORT_NAV_PROCESSES)
            month_rows = _rows(connection, REPORT_NAV_PROCESS_MONTHS)
            step_rows = _rows(connection, REPORT_NAV_STEPS)
            dependency_rows = _rows(connection, REPORT_NAV_STEP_DEPENDENCIES)
            source_rows = _rows(connection, REPORT_NAV_STEP_SOURCES)
            field_rows = _rows(connection, REPORT_NAV_STEP_FIELDS)
            value_rows = _rows(connection, REPORT_NAV_STEP_VALUES)

        enabled_processes = {
            str(row["process_code"]): row
            for row in process_rows
            if bool(row.get("enabled"))
        }
        active_process_codes = {
            str(row["process_code"])
            for row in month_rows
            if int(row.get("month_no") or 0) == month_no
            and str(row.get("process_code")) in enabled_processes
        }
        dependencies: dict[str, list[str]] = {}
        for row in dependency_rows:
            dependencies.setdefault(str(row["step_code"]), []).append(str(row["depends_on_step_code"]))
        fields_by_source: dict[int, dict[str, str]] = {}
        for row in field_rows:
            fields_by_source.setdefault(int(row["step_source_id"]), {})[
                str(row["field_role"])
            ] = str(row["column_name"])
        sources_by_step: dict[str, list[StepSourceConfig]] = {}
        for row in sorted(source_rows, key=lambda item: int(item.get("display_order") or 0)):
            if not bool(row.get("enabled")):
                continue
            source_id = int(row["id"])
            sources_by_step.setdefault(str(row["step_code"]), []).append(
                StepSourceConfig(
                    id=source_id,
                    source_role=str(row["source_role"]),
                    data_source_name=str(row["data_source_name"]),
                    table_name=str(row["table_name"]),
                    display_order=int(row["display_order"]),
                    fields=dict(fields_by_source.get(source_id, {})),
                )
            )
        values_by_step: dict[str, dict[str, list[tuple[int, str]]]] = {}
        for row in value_rows:
            step_values = values_by_step.setdefault(str(row["step_code"]), {})
            step_values.setdefault(str(row["value_role"]), []).append(
                (int(row.get("display_order") or 0), str(row["value_text"]))
            )

        steps_by_process: dict[str, list[StepConfig]] = {}
        for row in sorted(step_rows, key=lambda item: int(item.get("display_order") or 0)):
            process_code = str(row["process_code"])
            if process_code not in active_process_codes or not bool(row.get("enabled")):
                continue
            step_code = str(row["step_code"])
            normalized_values = {
                role: tuple(value for _, value in sorted(entries))
                for role, entries in values_by_step.get(step_code, {}).items()
            }
            steps_by_process.setdefault(process_code, []).append(
                StepConfig(
                    step_code=step_code,
                    process_code=process_code,
                    step_name=str(row["step_name"]),
                    display_order=int(row["display_order"]),
                    evaluator_key=str(row["evaluator_key"]),
                    default_completed=bool(row.get("default_completed")),
                    manual_completion_allowed=bool(row.get("manual_completion_allowed")),
                    dependencies=tuple(dependencies.get(step_code, ())),
                    sources=tuple(sources_by_step.get(step_code, ())),
                    values=normalized_values,
                )
            )

        return [
            ProcessConfig(
                process_code=process_code,
                process_name=str(enabled_processes[process_code]["process_name"]),
                display_order=int(enabled_processes[process_code]["display_order"]),
                allow_manual_step_completion=bool(
                    enabled_processes[process_code].get("allow_manual_step_completion")
                ),
                steps=tuple(steps_by_process.get(process_code, ())),
            )
            for process_code in sorted(
                active_process_codes,
                key=lambda code: int(enabled_processes[code].get("display_order") or 0),
            )
        ]

    def load_overrides(self, report_month: str) -> dict[str, ManualOverride]:
        _parse_report_month(report_month)
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_STEP_OVERRIDES)
        return {
            str(row["step_code"]): ManualOverride(
                report_month=str(row["report_month"]),
                step_code=str(row["step_code"]),
                completed=bool(row["completed"]),
                operator_id=str(row.get("operator_id") or ""),
                operator_username=str(row.get("operator_username") or ""),
                operator_name=str(row.get("operator_name") or ""),
                created_at=_as_datetime(row["created_at"]),
                updated_at=_as_datetime(row["updated_at"]),
            )
            for row in rows
            if str(row.get("report_month")) == report_month
        }

    def load_step_config(self, step_code: str) -> StepConfig | None:
        with self.database.connect() as connection:
            step_rows = _rows(connection, REPORT_NAV_STEPS)
            dependency_rows = _rows(connection, REPORT_NAV_STEP_DEPENDENCIES)
            source_rows = _rows(connection, REPORT_NAV_STEP_SOURCES)
            field_rows = _rows(connection, REPORT_NAV_STEP_FIELDS)
            value_rows = _rows(connection, REPORT_NAV_STEP_VALUES)
        row = next((item for item in step_rows if str(item.get("step_code")) == step_code), None)
        if row is None:
            return None
        fields_by_source: dict[int, dict[str, str]] = {}
        for field_row in field_rows:
            fields_by_source.setdefault(int(field_row["step_source_id"]), {})[
                str(field_row["field_role"])
            ] = str(field_row["column_name"])
        sources = tuple(
            StepSourceConfig(
                id=int(source["id"]),
                source_role=str(source["source_role"]),
                data_source_name=str(source["data_source_name"]),
                table_name=str(source["table_name"]),
                display_order=int(source["display_order"]),
                fields=dict(fields_by_source.get(int(source["id"]), {})),
            )
            for source in sorted(source_rows, key=lambda item: int(item.get("display_order") or 0))
            if str(source.get("step_code")) == step_code and bool(source.get("enabled"))
        )
        grouped_values: dict[str, list[tuple[int, str]]] = {}
        for value in value_rows:
            if str(value.get("step_code")) != step_code:
                continue
            grouped_values.setdefault(str(value["value_role"]), []).append(
                (int(value.get("display_order") or 0), str(value["value_text"]))
            )
        return StepConfig(
            step_code=step_code,
            process_code=str(row["process_code"]),
            step_name=str(row["step_name"]),
            display_order=int(row["display_order"]),
            evaluator_key=str(row["evaluator_key"]),
            default_completed=bool(row.get("default_completed")),
            manual_completion_allowed=bool(row.get("manual_completion_allowed")),
            dependencies=tuple(
                str(item["depends_on_step_code"])
                for item in dependency_rows
                if str(item.get("step_code")) == step_code
            ),
            sources=sources,
            values={
                role: tuple(text_value for _, text_value in sorted(entries))
                for role, entries in grouped_values.items()
            },
        )

    def set_manual_complete(
        self,
        report_month: str,
        step_code: str,
        user: Mapping[str, Any],
        *,
        now: datetime,
    ) -> None:
        _parse_report_month(report_month)
        step = self._load_step(step_code)
        if not step or not bool(step.get("manual_completion_allowed")):
            raise ValueError("该步骤不允许手动完成")
        existing = self.load_overrides(report_month).get(step_code)
        values = {
            "report_month": report_month,
            "step_code": step_code,
            "completed": True,
            "operator_id": str(user.get("id") or ""),
            "operator_username": str(user.get("username") or ""),
            "operator_name": str(user.get("display_name") or user.get("username") or ""),
            "created_at": existing.created_at if existing else now,
            "updated_at": now,
        }
        statement = mysql_insert(REPORT_NAV_STEP_OVERRIDES).values(**values)
        statement = statement.on_duplicate_key_update(
            completed=statement.inserted.completed,
            operator_id=statement.inserted.operator_id,
            operator_username=statement.inserted.operator_username,
            operator_name=statement.inserted.operator_name,
            updated_at=statement.inserted.updated_at,
        )
        with self.database.transaction() as connection:
            connection.execute(statement)

    def cancel_manual_complete(self, report_month: str, step_code: str) -> None:
        _parse_report_month(report_month)
        statement = delete(REPORT_NAV_STEP_OVERRIDES).where(
            REPORT_NAV_STEP_OVERRIDES.c.report_month == report_month,
            REPORT_NAV_STEP_OVERRIDES.c.step_code == step_code,
        )
        with self.database.transaction() as connection:
            connection.execute(statement)

    def upsert_schedule(
        self,
        report_month: str,
        process_code: str,
        report_date: date,
        *,
        source_type: str,
        source_year: int | None,
        updated_by: str,
        now: datetime,
    ) -> None:
        year, month = _parse_report_month(report_month)
        if (report_date.year, report_date.month) != (year, month):
            raise ValueError("报送日期必须属于对应报送月份")
        values = {
            "report_month": report_month,
            "process_code": process_code,
            "report_date": report_date,
            "source_type": source_type,
            "source_year": source_year,
            "updated_by": updated_by,
            "updated_at": now,
        }
        statement = mysql_insert(REPORT_NAV_MONTHLY_SCHEDULES).values(**values)
        statement = statement.on_duplicate_key_update(
            report_date=statement.inserted.report_date,
            source_type=statement.inserted.source_type,
            source_year=statement.inserted.source_year,
            updated_by=statement.inserted.updated_by,
            updated_at=statement.inserted.updated_at,
        )
        with self.database.transaction() as connection:
            connection.execute(statement)

    def load_schedule(self, report_month: str, process_code: str) -> ScheduleConfig | None:
        _parse_report_month(report_month)
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_MONTHLY_SCHEDULES)
        row = next(
            (
                item
                for item in rows
                if str(item.get("report_month")) == report_month
                and str(item.get("process_code")) == process_code
            ),
            None,
        )
        return _schedule_from_row(row) if row else None

    def load_work_calendar(self, year: int) -> dict[str, Any]:
        if year < 2000 or year > 9999:
            raise ValueError("工作日历年份不正确")
        with self.database.connect() as connection:
            rows = [
                row
                for row in _rows(connection, REPORT_NAV_WORK_CALENDAR)
                if int(row.get("calendar_year") or 0) == year
            ]
        holidays = sorted(
            _as_date(row["calendar_date"]).isoformat()
            for row in rows
            if str(row.get("day_type") or "") == "holiday"
        )
        adjusted_workdays = sorted(
            _as_date(row["calendar_date"]).isoformat()
            for row in rows
            if str(row.get("day_type") or "") == "adjusted_workday"
        )
        return {
            "year": year,
            "configured": bool(rows),
            "holidays": holidays,
            "adjusted_workdays": adjusted_workdays,
        }

    def update_schedule_owner(
        self,
        report_month: str,
        process_code: str,
        owner_name: str,
        *,
        updated_by: str,
        now: datetime,
    ) -> None:
        current = self.load_schedule(report_month, process_code)
        if current is None:
            raise ValueError("报送日期未配置，无法维护负责人")
        values = {
            "report_month": current.report_month,
            "process_code": current.process_code,
            "report_date": current.report_date,
            "source_type": current.source_type,
            "source_year": current.source_year,
            "owner_name": owner_name or None,
            "updated_by": updated_by,
            "updated_at": now,
        }
        statement = mysql_insert(REPORT_NAV_MONTHLY_SCHEDULES).values(**values)
        statement = statement.on_duplicate_key_update(
            owner_name=statement.inserted.owner_name,
            updated_by=statement.inserted.updated_by,
            updated_at=statement.inserted.updated_at,
        )
        with self.database.transaction() as connection:
            connection.execute(statement)

    def ensure_schedule(
        self, report_month: str, process_code: str, *, now: datetime
    ) -> ScheduleConfig | None:
        current = self.load_schedule(report_month, process_code)
        if current is not None:
            return current
        year, month = _parse_report_month(report_month)
        previous = self.load_schedule(f"{year - 1:04d}-{month:02d}", process_code)
        if previous is not None:
            inherited_date = date(year, month, min(previous.report_date.day, monthrange(year, month)[1]))
            self.upsert_schedule(
                report_month,
                process_code,
                inherited_date,
                source_type="inherited",
                source_year=previous.report_date.year,
                updated_by="system",
                now=now,
            )
            return self.load_schedule(report_month, process_code)
        if process_code == "pbc_central":
            self.upsert_schedule(
                report_month,
                process_code,
                date(year, month, 1),
                source_type="default",
                source_year=year,
                updated_by="system",
                now=now,
            )
            return self.load_schedule(report_month, process_code)
        return None

    def save_process_snapshot(
        self,
        snapshot: ProcessSnapshot,
        *,
        preserve_completed_at: bool = True,
    ) -> None:
        existing = self.load_process_snapshot(snapshot.report_month, snapshot.process_code)
        completed_at = snapshot.completed_at
        if (
            preserve_completed_at
            and snapshot.status == "completed"
            and existing
            and existing.status == "completed"
        ):
            completed_at = existing.completed_at
        if snapshot.status != "completed":
            completed_at = None
        values = {
            "report_month": snapshot.report_month,
            "process_code": snapshot.process_code,
            "total_steps": snapshot.total_steps,
            "completed_steps": snapshot.completed_steps,
            "status": snapshot.status,
            "completed_at": completed_at,
            "evaluated_at": snapshot.evaluated_at,
            "run_id": snapshot.run_id,
        }
        statement = mysql_insert(REPORT_NAV_PROCESS_SNAPSHOTS).values(**values)
        statement = statement.on_duplicate_key_update(
            total_steps=statement.inserted.total_steps,
            completed_steps=statement.inserted.completed_steps,
            status=statement.inserted.status,
            completed_at=statement.inserted.completed_at,
            evaluated_at=statement.inserted.evaluated_at,
            run_id=statement.inserted.run_id,
        )
        with self.database.transaction() as connection:
            connection.execute(statement)

    def save_step_snapshot(
        self,
        snapshot: StepSnapshot,
        *,
        preserve_auto_completed_at: bool = True,
    ) -> None:
        existing = self.load_step_snapshot(snapshot.report_month, snapshot.step_code)
        auto_completed_at = snapshot.auto_completed_at
        if (
            preserve_auto_completed_at
            and
            snapshot.auto_status == "completed"
            and existing is not None
            and existing.auto_status == "completed"
        ):
            auto_completed_at = existing.auto_completed_at
        if snapshot.auto_status != "completed":
            auto_completed_at = None
        values = {
            "report_month": snapshot.report_month,
            "step_code": snapshot.step_code,
            "auto_status": snapshot.auto_status,
            "effective_status": snapshot.effective_status,
            "completion_source": snapshot.completion_source,
            "status_message": snapshot.status_message,
            "error_message": snapshot.error_message or None,
            "auto_completed_at": auto_completed_at,
            "evaluated_at": snapshot.evaluated_at,
            "run_id": snapshot.run_id,
        }
        statement = mysql_insert(REPORT_NAV_STEP_SNAPSHOTS).values(**values)
        statement = statement.on_duplicate_key_update(
            auto_status=statement.inserted.auto_status,
            effective_status=statement.inserted.effective_status,
            completion_source=statement.inserted.completion_source,
            status_message=statement.inserted.status_message,
            error_message=statement.inserted.error_message,
            auto_completed_at=statement.inserted.auto_completed_at,
            evaluated_at=statement.inserted.evaluated_at,
            run_id=statement.inserted.run_id,
        )
        with self.database.transaction() as connection:
            connection.execute(statement)

    def load_step_snapshot(self, report_month: str, step_code: str) -> StepSnapshot | None:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_STEP_SNAPSHOTS)
        row = next(
            (
                item
                for item in rows
                if str(item.get("report_month")) == report_month
                and str(item.get("step_code")) == step_code
            ),
            None,
        )
        if row is None:
            return None
        return StepSnapshot(
            report_month=str(row["report_month"]),
            step_code=str(row["step_code"]),
            auto_status=str(row["auto_status"]),
            effective_status=str(row["effective_status"]),
            completion_source=str(row["completion_source"]),
            status_message=str(row.get("status_message") or ""),
            error_message=str(row.get("error_message") or ""),
            auto_completed_at=_optional_datetime(row.get("auto_completed_at")),
            evaluated_at=_as_datetime(row["evaluated_at"]),
            run_id=int(row["run_id"]) if row.get("run_id") is not None else None,
        )

    def load_step_snapshots(self, report_month: str) -> dict[str, StepSnapshot]:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_STEP_SNAPSHOTS)
        return {
            str(row["step_code"]): StepSnapshot(
                report_month=str(row["report_month"]),
                step_code=str(row["step_code"]),
                auto_status=str(row["auto_status"]),
                effective_status=str(row["effective_status"]),
                completion_source=str(row["completion_source"]),
                status_message=str(row.get("status_message") or ""),
                error_message=str(row.get("error_message") or ""),
                auto_completed_at=_optional_datetime(row.get("auto_completed_at")),
                evaluated_at=_as_datetime(row["evaluated_at"]),
                run_id=int(row["run_id"]) if row.get("run_id") is not None else None,
            )
            for row in rows
            if str(row.get("report_month")) == report_month
        }

    def save_card_snapshot(self, snapshot: CardSnapshot) -> None:
        with self.database.transaction() as connection:
            connection.execute(_card_snapshot_upsert(snapshot))

    def load_card_snapshots(self, period: str) -> dict[str, CardSnapshot]:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_CARD_SNAPSHOTS)
        return {
            str(row["card_code"]): CardSnapshot(
                stat_period=str(row["stat_period"]),
                card_code=str(row["card_code"]),
                total_count=int(row["total_count"]),
                completed_count=int(row["completed_count"]),
                incomplete_count=int(row["incomplete_count"]),
                completion_rate=Decimal(str(row["completion_rate"])),
                evaluated_at=_as_datetime(row["evaluated_at"]),
                run_id=int(row["run_id"]) if row.get("run_id") is not None else None,
                comparison_delta=(
                    int(row["comparison_delta"])
                    if row.get("comparison_delta") is not None
                    else None
                ),
            )
            for row in rows
            if str(row.get("stat_period")) == period
        }

    def load_card_provider_state(self, card_code: str) -> CardProviderState | None:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_CARD_PROVIDER_STATES)
        row = next(
            (item for item in rows if str(item.get("card_code") or "") == card_code),
            None,
        )
        return _provider_state_from_row(row) if row is not None else None

    def load_card_provider_states(self) -> dict[str, CardProviderState]:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_CARD_PROVIDER_STATES)
        return {
            str(row["card_code"]): _provider_state_from_row(row)
            for row in rows
        }

    def claim_card_provider(
        self,
        card_code: str,
        owner: str,
        registration_token: str,
        semantics_version: int,
        *,
        now: datetime | None = None,
    ) -> bool:
        timestamp = now or beijing_now()
        statement = text(
            """
            INSERT INTO report_nav_card_provider_states (
                card_code, owner, registration_token, semantics_version,
                provider_active, stale, last_attempt_at, last_success_at,
                last_success_period_key, last_error, updated_at
            ) VALUES (
                :card_code, :owner, :registration_token, :semantics_version,
                1, 1, NULL, NULL, NULL, NULL, :updated_at
            )
            ON DUPLICATE KEY UPDATE
                last_attempt_at=IF(
                    owner=VALUES(owner),
                    IF(semantics_version=VALUES(semantics_version), last_attempt_at, NULL),
                    last_attempt_at
                ),
                last_success_at=IF(
                    owner=VALUES(owner),
                    IF(semantics_version=VALUES(semantics_version), last_success_at, NULL),
                    last_success_at
                ),
                last_success_period_key=IF(
                    owner=VALUES(owner),
                    IF(
                        semantics_version=VALUES(semantics_version),
                        last_success_period_key, NULL
                    ),
                    last_success_period_key
                ),
                last_error=IF(
                    owner=VALUES(owner),
                    IF(semantics_version=VALUES(semantics_version), last_error, NULL),
                    last_error
                ),
                stale=IF(
                    owner=VALUES(owner),
                    IF(semantics_version=VALUES(semantics_version), stale, 1),
                    stale
                ),
                semantics_version=IF(
                    owner=VALUES(owner), VALUES(semantics_version), semantics_version
                ),
                provider_active=IF(
                    owner=VALUES(owner), 1, provider_active
                ),
                registration_token=IF(
                    owner=VALUES(owner), VALUES(registration_token), registration_token
                ),
                updated_at=IF(owner=VALUES(owner), VALUES(updated_at), updated_at)
            """
        )
        with self.database.transaction() as connection:
            connection.execute(
                statement,
                {
                    "card_code": card_code,
                    "owner": owner,
                    "registration_token": registration_token,
                    "semantics_version": semantics_version,
                    "updated_at": timestamp,
                },
            )
            row = connection.execute(
                select(REPORT_NAV_CARD_PROVIDER_STATES).where(
                    REPORT_NAV_CARD_PROVIDER_STATES.c.card_code == card_code
                )
            ).mappings().first()
            return bool(
                row
                and str(row.get("owner") or "") == owner
                and str(row.get("registration_token") or "") == registration_token
            )

    def deactivate_card_provider(
        self,
        card_code: str,
        owner: str,
        registration_token: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        timestamp = now or beijing_now()
        statement = text(
            """
            UPDATE report_nav_card_provider_states
            SET provider_active=0, stale=1, updated_at=:updated_at
            WHERE card_code=:card_code AND owner=:owner
              AND registration_token=:registration_token
            """
        )
        with self.database.transaction() as connection:
            result = connection.execute(
                statement,
                {
                    "card_code": card_code,
                    "owner": owner,
                    "registration_token": registration_token,
                    "updated_at": timestamp,
                },
            )
            return result.rowcount == 1

    def mark_card_provider_failure(
        self,
        card_code: str,
        owner: str,
        registration_token: str,
        semantics_version: int,
        *,
        attempted_at: datetime,
        error_message: str,
    ) -> bool:
        statement = text(
            """
            UPDATE report_nav_card_provider_states
            SET semantics_version=:semantics_version, provider_active=1, stale=1,
                last_attempt_at=:attempted_at, last_error=:last_error,
                updated_at=:attempted_at
            WHERE card_code=:card_code AND owner=:owner
              AND registration_token=:registration_token
            """
        )
        with self.database.transaction() as connection:
            result = connection.execute(
                statement,
                {
                    "card_code": card_code,
                    "owner": owner,
                    "registration_token": registration_token,
                    "semantics_version": semantics_version,
                    "attempted_at": attempted_at,
                    "last_error": error_message,
                },
            )
            return result.rowcount == 1

    def save_card_provider_success(
        self,
        card_code: str,
        owner: str,
        registration_token: str,
        semantics_version: int,
        snapshots: Sequence[CardSnapshot],
        *,
        attempted_at: datetime,
        period_key: str,
    ) -> bool:
        state_statement = text(
            """
            UPDATE report_nav_card_provider_states
            SET semantics_version=:semantics_version, provider_active=1, stale=0,
                last_attempt_at=:attempted_at, last_success_at=:attempted_at,
                last_success_period_key=:period_key, last_error=NULL,
                updated_at=:attempted_at
            WHERE card_code=:card_code AND owner=:owner
              AND registration_token=:registration_token
            """
        )
        with self.database.transaction() as connection:
            result = connection.execute(
                state_statement,
                {
                    "card_code": card_code,
                    "owner": owner,
                    "registration_token": registration_token,
                    "semantics_version": semantics_version,
                    "attempted_at": attempted_at,
                    "period_key": period_key,
                },
            )
            if result.rowcount != 1:
                return False
            for snapshot in snapshots:
                connection.execute(_card_snapshot_upsert(snapshot))
            return True

    def save_manual_card_values(
        self,
        card_code: str,
        values: Mapping[str, Mapping[str, int]],
        current_user: Mapping[str, Any],
        *,
        now: datetime,
        period_keys: Mapping[str, str] | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            for stat_period, counts in values.items():
                row = {
                    "stat_period": stat_period,
                    "card_code": card_code,
                    "completed_count": int(counts["completed_count"]),
                    "incomplete_count": int(counts["incomplete_count"]),
                    "operator_id": str(current_user.get("id") or ""),
                    "operator_username": str(current_user.get("username") or ""),
                    "operator_name": str(current_user.get("display_name") or ""),
                    "updated_at": now,
                }
                statement = mysql_insert(REPORT_NAV_CARD_MANUAL_VALUES).values(**row)
                statement = statement.on_duplicate_key_update(
                    completed_count=statement.inserted.completed_count,
                    incomplete_count=statement.inserted.incomplete_count,
                    operator_id=statement.inserted.operator_id,
                    operator_username=statement.inserted.operator_username,
                    operator_name=statement.inserted.operator_name,
                    updated_at=statement.inserted.updated_at,
                )
                connection.execute(statement)
                period_key = str((period_keys or {}).get(stat_period) or "")
                if period_key:
                    history_row = {**row, "period_key": period_key}
                    history_statement = mysql_insert(REPORT_NAV_CARD_MANUAL_HISTORY).values(**history_row)
                    history_statement = history_statement.on_duplicate_key_update(
                        completed_count=history_statement.inserted.completed_count,
                        incomplete_count=history_statement.inserted.incomplete_count,
                        operator_id=history_statement.inserted.operator_id,
                        operator_username=history_statement.inserted.operator_username,
                        operator_name=history_statement.inserted.operator_name,
                        updated_at=history_statement.inserted.updated_at,
                    )
                    connection.execute(history_statement)

    def load_manual_card_values(self, card_code: str) -> dict[str, ManualCardValue]:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_CARD_MANUAL_VALUES)
        return {
            str(row["stat_period"]): ManualCardValue(
                stat_period=str(row["stat_period"]),
                card_code=str(row["card_code"]),
                completed_count=int(row["completed_count"]),
                incomplete_count=int(row["incomplete_count"]),
                operator_id=str(row.get("operator_id") or ""),
                operator_username=str(row.get("operator_username") or ""),
                operator_name=str(row.get("operator_name") or ""),
                updated_at=_as_datetime(row["updated_at"]),
            )
            for row in rows
            if str(row.get("card_code")) == card_code
        }

    def load_manual_card_history(
        self, card_code: str
    ) -> dict[tuple[str, str], ManualCardHistoryValue]:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_CARD_MANUAL_HISTORY)
        return {
            (str(row["stat_period"]), str(row["period_key"])): ManualCardHistoryValue(
                stat_period=str(row["stat_period"]),
                period_key=str(row["period_key"]),
                card_code=str(row["card_code"]),
                completed_count=int(row["completed_count"]),
                incomplete_count=int(row["incomplete_count"]),
                operator_id=str(row.get("operator_id") or ""),
                operator_username=str(row.get("operator_username") or ""),
                operator_name=str(row.get("operator_name") or ""),
                updated_at=_as_datetime(row["updated_at"]),
            )
            for row in rows
            if str(row.get("card_code")) == card_code
        }

    def load_process_snapshots(self, report_month: str) -> dict[str, ProcessSnapshot]:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_PROCESS_SNAPSHOTS)
        return {
            str(row["process_code"]): ProcessSnapshot(
                report_month=str(row["report_month"]),
                process_code=str(row["process_code"]),
                total_steps=int(row["total_steps"]),
                completed_steps=int(row["completed_steps"]),
                status=str(row["status"]),
                completed_at=_optional_datetime(row.get("completed_at")),
                evaluated_at=_as_datetime(row["evaluated_at"]),
                run_id=int(row["run_id"]) if row.get("run_id") is not None else None,
            )
            for row in rows
            if str(row.get("report_month")) == report_month
        }

    def load_schedules(self, report_month: str) -> dict[str, ScheduleConfig]:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_MONTHLY_SCHEDULES)
        return {
            str(row["process_code"]): _schedule_from_row(row)
            for row in rows
            if str(row.get("report_month")) == report_month
        }

    def process_exists(self, process_code: str) -> bool:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_PROCESSES)
        return any(str(row.get("process_code")) == process_code for row in rows)

    def load_latest_run(self, *, trigger_type: str | None = None) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_STAT_RUNS)
        if trigger_type is not None:
            rows = [row for row in rows if str(row.get("trigger_type") or "") == trigger_type]
        if not rows:
            return None
        return max(rows, key=lambda row: (_as_datetime(row["started_at"]), int(row["id"])))

    def start_run(
        self,
        trigger_type: str,
        report_month: str,
        business_report_date: date | None,
        started_at: datetime,
    ) -> int:
        statement = mysql_insert(REPORT_NAV_STAT_RUNS).values(
            trigger_type=trigger_type,
            report_month=report_month,
            business_report_date=business_report_date,
            started_at=started_at,
            finished_at=None,
            status="running",
            completed_processes=0,
            failed_steps=0,
            failed_providers=0,
            error_message=None,
        )
        with self.database.transaction() as connection:
            result = connection.execute(statement)
            return int(result.inserted_primary_key[0])

    def finish_run(
        self,
        run_id: int,
        *,
        finished_at: datetime,
        status: str,
        completed_processes: int,
        failed_steps: int,
        failed_providers: int = 0,
        error_message: str = "",
    ) -> None:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_STAT_RUNS)
        row = next((item for item in rows if int(item.get("id") or 0) == run_id), None)
        if row is None:
            raise ValueError(f"统计任务不存在：{run_id}")
        values = dict(row)
        values.update(
            finished_at=finished_at,
            status=status,
            completed_processes=completed_processes,
            failed_steps=failed_steps,
            failed_providers=failed_providers,
            error_message=error_message or None,
        )
        statement = mysql_insert(REPORT_NAV_STAT_RUNS).values(**values)
        statement = statement.on_duplicate_key_update(
            finished_at=statement.inserted.finished_at,
            status=statement.inserted.status,
            completed_processes=statement.inserted.completed_processes,
            failed_steps=statement.inserted.failed_steps,
            failed_providers=statement.inserted.failed_providers,
            error_message=statement.inserted.error_message,
        )
        with self.database.transaction() as connection:
            connection.execute(statement)

    def try_acquire_scheduler_lock(
        self, owner: str, now: datetime, lease: Any
    ) -> bool:
        statement = text(
            """
            UPDATE report_nav_scheduler_state
            SET lock_owner=:owner, lock_until=:lock_until,
                last_started_at=:now, updated_at=:now
            WHERE id=1 AND enabled=1
              AND (lock_until IS NULL OR lock_until < :now)
            """
        )
        with self.database.transaction() as connection:
            result = connection.execute(
                statement,
                {"owner": owner, "lock_until": now + lease, "now": now},
            )
            return result.rowcount == 1

    def release_scheduler_lock(
        self,
        owner: str,
        finished_at: datetime,
        *,
        status: str,
        error_message: str = "",
    ) -> None:
        statement = text(
            """
            UPDATE report_nav_scheduler_state
            SET lock_owner=NULL, lock_until=NULL,
                last_finished_at=:finished_at, last_status=:status,
                last_error=:error_message, updated_at=:finished_at
            WHERE id=1 AND lock_owner=:owner
            """
        )
        with self.database.transaction() as connection:
            connection.execute(
                statement,
                {
                    "owner": owner,
                    "finished_at": finished_at,
                    "status": status,
                    "error_message": error_message or None,
                },
            )

    def scheduler_interval_minutes(self) -> int:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_SCHEDULER_STATE)
        row = next((item for item in rows if int(item.get("id") or 0) == 1), None)
        return max(1, int((row or {}).get("interval_minutes") or 10))

    def load_process_snapshot(
        self, report_month: str, process_code: str
    ) -> ProcessSnapshot | None:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_PROCESS_SNAPSHOTS)
        row = next(
            (
                item
                for item in rows
                if str(item.get("report_month")) == report_month
                and str(item.get("process_code")) == process_code
            ),
            None,
        )
        if row is None:
            return None
        return ProcessSnapshot(
            report_month=str(row["report_month"]),
            process_code=str(row["process_code"]),
            total_steps=int(row["total_steps"]),
            completed_steps=int(row["completed_steps"]),
            status=str(row["status"]),
            completed_at=_optional_datetime(row.get("completed_at")),
            evaluated_at=_as_datetime(row["evaluated_at"]),
            run_id=int(row["run_id"]) if row.get("run_id") is not None else None,
        )

    def _load_step(self, step_code: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            rows = _rows(connection, REPORT_NAV_STEPS)
        return next((row for row in rows if str(row.get("step_code")) == step_code), None)


def _rows(connection: Any, table: Table) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(select(table)).mappings().all()]


def _card_snapshot_upsert(snapshot: CardSnapshot):
    values = {
        "stat_period": snapshot.stat_period,
        "card_code": snapshot.card_code,
        "total_count": snapshot.total_count,
        "completed_count": snapshot.completed_count,
        "incomplete_count": snapshot.incomplete_count,
        "comparison_delta": snapshot.comparison_delta,
        "completion_rate": snapshot.completion_rate,
        "evaluated_at": snapshot.evaluated_at,
        "run_id": snapshot.run_id,
    }
    statement = mysql_insert(REPORT_NAV_CARD_SNAPSHOTS).values(**values)
    return statement.on_duplicate_key_update(
        total_count=statement.inserted.total_count,
        completed_count=statement.inserted.completed_count,
        incomplete_count=statement.inserted.incomplete_count,
        comparison_delta=statement.inserted.comparison_delta,
        completion_rate=statement.inserted.completion_rate,
        evaluated_at=statement.inserted.evaluated_at,
        run_id=statement.inserted.run_id,
    )


def _provider_state_from_row(row: Mapping[str, Any]) -> CardProviderState:
    return CardProviderState(
        card_code=str(row["card_code"]),
        owner=str(row["owner"]),
        registration_token=str(row.get("registration_token") or ""),
        semantics_version=int(row["semantics_version"]),
        provider_active=bool(row.get("provider_active")),
        stale=bool(row.get("stale")),
        last_attempt_at=_optional_datetime(row.get("last_attempt_at")),
        last_success_at=_optional_datetime(row.get("last_success_at")),
        last_success_period_key=str(row.get("last_success_period_key") or ""),
        last_error=str(row.get("last_error") or ""),
        updated_at=_as_datetime(row["updated_at"]),
    )


def _parse_report_month(value: str) -> tuple[int, int]:
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except (TypeError, ValueError) as exc:
        raise ValueError("report_month 必须使用 YYYY-MM 格式") from exc
    return parsed.year, parsed.month


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _optional_datetime(value: Any) -> datetime | None:
    return None if value in (None, "") else _as_datetime(value)


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _schedule_from_row(row: Mapping[str, Any]) -> ScheduleConfig:
    return ScheduleConfig(
        report_month=str(row["report_month"]),
        process_code=str(row["process_code"]),
        report_date=_as_date(row["report_date"]),
        source_type=str(row["source_type"]),
        source_year=int(row["source_year"]) if row.get("source_year") is not None else None,
        owner_name=str(row.get("owner_name") or ""),
        updated_by=str(row.get("updated_by") or ""),
        updated_at=_as_datetime(row["updated_at"]),
    )
