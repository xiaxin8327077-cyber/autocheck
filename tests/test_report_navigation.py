from datetime import date, datetime, timedelta
import importlib
from pathlib import Path

from mysql_config_test_support import MemoryApplicationDatabase


ROOT = Path(__file__).resolve().parents[1]
STORAGE_MODULE = ROOT / "src" / "auto_check" / "app" / "storage_report_navigation.py"
REPORT_MODULE = ROOT / "src" / "auto_check" / "app" / "report_navigation.py"


def _storage():
    assert STORAGE_MODULE.exists(), "report navigation storage module is missing"
    return importlib.import_module("auto_check.app.storage_report_navigation")


def _report_navigation():
    assert REPORT_MODULE.exists(), "report navigation evaluator module is missing"
    return importlib.import_module("auto_check.app.report_navigation")


def _database() -> MemoryApplicationDatabase:
    return MemoryApplicationDatabase()


def test_store_loads_month_configuration_with_nested_sources_fields_values_and_dependencies():
    module = _storage()
    database = _database()
    tables = database.connection.tables
    tables["report_nav_processes"].append(
        {
            "process_code": "pbc_template",
            "process_name": "人行模板、逐笔报送",
            "display_order": 20,
            "enabled": 1,
            "allow_manual_step_completion": 1,
        }
    )
    tables["report_nav_process_months"].append({"process_code": "pbc_template", "month_no": 7})
    tables["report_nav_steps"].append(
        {
            "step_code": "pbc_template_6",
            "process_code": "pbc_template",
            "step_name": "归档并上传",
            "display_order": 6,
            "evaluator_key": "all_versions_present",
            "enabled": 1,
            "default_completed": 0,
            "manual_completion_allowed": 1,
        }
    )
    tables["report_nav_step_sources"].append(
        {
            "id": 11,
            "step_code": "pbc_template_6",
            "source_role": "primary",
            "data_source_name": "reg-report-analysis",
            "table_name": "xt_reg_version",
            "display_order": 1,
            "enabled": 1,
        }
    )
    tables["report_nav_step_fields"].extend(
        [
            {"id": 1, "step_source_id": 11, "field_role": "manage_code_field", "column_name": "manage_code"},
            {"id": 2, "step_source_id": 11, "field_role": "version_field", "column_name": "version_num"},
        ]
    )
    tables["report_nav_step_values"].extend(
        [
            {"id": 1, "step_code": "pbc_template_6", "value_role": "manage_code", "value_text": "20002", "value_type": "text", "display_order": 1},
            {"id": 2, "step_code": "pbc_template_6", "value_role": "manage_code", "value_text": "zbbs24", "value_type": "text", "display_order": 2},
        ]
    )
    tables["report_nav_step_dependencies"].append(
        {"step_code": "pbc_template_5", "depends_on_step_code": "pbc_template_6"}
    )

    processes = module.ReportNavigationStore(database).load_configuration("2026-07")

    assert len(processes) == 1
    process = processes[0]
    assert process.process_code == "pbc_template"
    assert [step.step_code for step in process.steps] == ["pbc_template_6"]
    step = process.steps[0]
    assert step.sources[0].data_source_name == "reg-report-analysis"
    assert step.sources[0].fields == {
        "manage_code_field": "manage_code",
        "version_field": "version_num",
    }
    assert step.values == {"manage_code": ("20002", "zbbs24")}


def test_store_sets_and_cancels_manual_completion_for_only_requested_month():
    module = _storage()
    database = _database()
    database.connection.tables["report_nav_steps"].append(
        {
            "step_code": "pbc_template_7",
            "process_code": "pbc_template",
            "step_name": "填写说明",
            "display_order": 7,
            "evaluator_key": "date_reached",
            "enabled": 1,
            "default_completed": 0,
            "manual_completion_allowed": 1,
        }
    )
    store = module.ReportNavigationStore(database)
    user = {"id": "u1", "username": "admin", "display_name": "管理员"}

    store.set_manual_complete("2026-07", "pbc_template_7", user, now=datetime(2026, 7, 16, 9, 30))

    overrides = store.load_overrides("2026-07")
    assert overrides["pbc_template_7"].operator_username == "admin"
    assert store.load_overrides("2026-08") == {}

    store.cancel_manual_complete("2026-07", "pbc_template_7")

    assert store.load_overrides("2026-07") == {}


def test_store_saves_governance_card_values_independently_for_all_four_periods():
    module = _storage()
    database = _database()
    store = module.ReportNavigationStore(database)
    user = {"id": "u1", "username": "admin", "display_name": "管理员"}
    current = datetime(2026, 7, 16, 9, 30)

    store.save_manual_card_values(
        "data_governance",
        {
            "week": {"completed_count": 1, "incomplete_count": 2},
            "month": {"completed_count": 3, "incomplete_count": 4},
            "quarter": {"completed_count": 5, "incomplete_count": 6},
            "year": {"completed_count": 7, "incomplete_count": 8},
        },
        user,
        now=current,
    )

    values = store.load_manual_card_values("data_governance")
    assert set(values) == {"week", "month", "quarter", "year"}
    assert (values["quarter"].completed_count, values["quarter"].incomplete_count) == (5, 6)
    assert values["year"].operator_username == "admin"
    assert store.load_manual_card_values("special_governance") == {}


def test_schedule_inherits_previous_year_and_clamps_leap_day():
    module = _storage()
    database = _database()
    store = module.ReportNavigationStore(database)
    database.connection.tables["report_nav_processes"].append(
        {
            "process_code": "east5",
            "process_name": "East5报送",
            "display_order": 60,
            "enabled": 1,
            "allow_manual_step_completion": 1,
        }
    )
    store.upsert_schedule(
        "2024-02",
        "east5",
        date(2024, 2, 29),
        source_type="imported",
        source_year=2024,
        updated_by="seed",
        now=datetime(2024, 1, 1),
    )

    inherited = store.ensure_schedule("2025-02", "east5", now=datetime(2025, 1, 1))

    assert inherited.report_date == date(2025, 2, 28)
    assert inherited.source_type == "inherited"
    assert inherited.source_year == 2024


def test_process_snapshot_preserves_clears_and_recreates_completion_time():
    module = _storage()
    database = _database()
    store = module.ReportNavigationStore(database)
    first = datetime(2026, 7, 16, 9, 0)
    later = datetime(2026, 7, 16, 10, 0)
    newest = datetime(2026, 7, 16, 11, 0)

    store.save_process_snapshot(
        module.ProcessSnapshot("2026-07", "east5", 1, 1, "completed", first, first, 1)
    )
    store.save_process_snapshot(
        module.ProcessSnapshot("2026-07", "east5", 1, 1, "completed", later, later, 2)
    )
    assert store.load_process_snapshot("2026-07", "east5").completed_at == first

    store.save_process_snapshot(
        module.ProcessSnapshot("2026-07", "east5", 1, 0, "incomplete", None, later, 3)
    )
    assert store.load_process_snapshot("2026-07", "east5").completed_at is None

    store.save_process_snapshot(
        module.ProcessSnapshot("2026-07", "east5", 1, 1, "completed", newest, newest, 4)
    )
    assert store.load_process_snapshot("2026-07", "east5").completed_at == newest


class QueueQueryExecutor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def fetch_one(self, source, sql, params=()):
        self.calls.append((source.source_role, sql, tuple(params)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def qualified_table(self, source):
        return f"`{source.table_name}`"

    def quote_column(self, source, column_name):
        return f"`{column_name}`"


def _source(module, role="primary", fields=None):
    return module.StepSourceConfig(
        id=1,
        source_role=role,
        data_source_name="reg-report-analysis",
        table_name="ck_result",
        display_order=1,
        fields=fields or {"period_field": "period", "check_id_field": "ck_id"},
    )


def _step(module, evaluator_key, *, sources=(), values=None, dependencies=(), default_completed=False):
    return module.StepConfig(
        step_code="test_step",
        process_code="test_process",
        step_name="测试步骤",
        display_order=1,
        evaluator_key=evaluator_key,
        default_completed=default_completed,
        manual_completion_allowed=True,
        dependencies=tuple(dependencies),
        sources=tuple(sources),
        values=values or {},
    )


def _context(report_module, step, executor, *, report_date=date(2026, 6, 30), dependencies=None, schedule=None, now=None):
    return report_module.EvaluationContext(
        step=step,
        business_report_date=report_date,
        current=now or datetime(2026, 7, 16, 9, 0),
        query=executor,
        dependency_statuses=dependencies or {},
        schedule=schedule,
    )


def test_format_business_report_date_supports_all_required_styles():
    module = _report_navigation()

    assert module.format_business_report_date(date(2026, 6, 30), "date") == "2026-06-30"
    assert module.format_business_report_date(date(2026, 6, 30), "underscore") == "2026_06_30"
    assert module.format_business_report_date(date(2026, 6, 30), "version") == "V.20260630"


def test_negative_rule_requires_scope_rows_before_accepting_no_exceptions():
    module = _report_navigation()

    empty = module.scope_without_exceptions({"scope_count": 0, "exception_count": 0})
    clean = module.scope_without_exceptions({"scope_count": 4, "exception_count": 0})
    dirty = module.scope_without_exceptions({"scope_count": 4, "exception_count": 1})

    assert (empty.status, empty.message) == ("incomplete", "当前范围无数据")
    assert clean.status == "completed"
    assert dirty.status == "incomplete"


def test_all_rows_match_report_date_requires_data_and_no_mismatches():
    report_module = _report_navigation()
    storage_module = _storage()
    source = _source(storage_module, fields={"period_field": "reporting_period"})
    step = _step(storage_module, "all_rows_match_report_date", sources=(source,))
    executor = QueueQueryExecutor([{"scope_count": 3, "exception_count": 0}])

    result = report_module.evaluate(_context(report_module, step, executor))

    assert result.status == "completed"
    assert executor.calls[0][2] == ("2026-06-30",)


def test_no_ck_rule_accepts_empty_result_scope_and_maps_query_error():
    report_module = _report_navigation()
    storage_module = _storage()
    duration = _source(
        storage_module,
        role="duration",
        fields={
            "period_field": "caldate",
            "region_field": "c_regioncode",
            "customer_type_field": "c_custtype",
        },
    )
    ck = storage_module.StepSourceConfig(
        id=2,
        source_role="ck_result",
        data_source_name="reg-report-analysis",
        table_name="ck_result",
        display_order=2,
        fields={"period_field": "period", "check_id_field": "ck_id"},
    )
    step = _step(
        storage_module,
        "no_blank_fields_and_no_ck",
        sources=(duration, ck),
        values={"target_ck_id": ("5677",)},
    )
    empty_ck = QueueQueryExecutor(
        [
            {"scope_count": 2, "exception_count": 0},
            {"scope_count": 0, "exception_count": 0},
        ]
    )
    failed = QueueQueryExecutor([RuntimeError("table missing")])

    result = report_module.evaluate(_context(report_module, step, empty_ck))
    assert (result.status, result.message) == ("completed", "报告期内无目标校验异常")
    error = report_module.evaluate(_context(report_module, step, failed))
    assert error.status == "error"
    assert "table missing" in error.error


def test_version_evaluator_requires_every_configured_manage_code():
    report_module = _report_navigation()
    storage_module = _storage()
    source = _source(
        storage_module,
        fields={"manage_code_field": "manage_code", "version_field": "version_num"},
    )
    step = _step(
        storage_module,
        "all_versions_present",
        sources=(source,),
        values={"manage_code": ("20002", "zbbs24")},
    )

    complete = report_module.evaluate(
        _context(report_module, step, QueueQueryExecutor([{"matched_count": 2}]))
    )
    incomplete = report_module.evaluate(
        _context(report_module, step, QueueQueryExecutor([{"matched_count": 1}]))
    )

    assert complete.status == "completed"
    assert incomplete.status == "incomplete"


def test_version_evaluator_returns_latest_update_or_create_time():
    report_module = _report_navigation()
    storage_module = _storage()
    source = _source(
        storage_module,
        fields={
            "manage_code_field": "manage_code",
            "version_field": "version_num",
            "update_date_field": "update_date",
            "create_date_field": "create_date",
        },
    )
    step = _step(
        storage_module,
        "version_present",
        sources=(source,),
        values={"manage_code": ("system1104",)},
    )
    completion_time = datetime(2026, 7, 15, 18, 20, 30)
    executor = QueueQueryExecutor(
        [{"matched_count": 1, "completion_time": completion_time}]
    )

    result = report_module.evaluate(_context(report_module, step, executor))

    assert result.status == "completed"
    assert result.completed_at == completion_time
    assert (
        "MAX(COALESCE(`update_date`, `create_date`)) AS completion_time"
        in executor.calls[0][1]
    )


def test_dependency_default_and_date_evaluators_use_fixed_rules():
    report_module = _report_navigation()
    storage_module = _storage()
    default_step = _step(storage_module, "default_completed", default_completed=True)
    dependency_step = _step(
        storage_module,
        "dependency_completed",
        dependencies=("upload_step",),
    )
    schedule = storage_module.ScheduleConfig(
        report_month="2026-07",
        process_code="pbc_template",
        report_date=date(2026, 7, 20),
        source_type="imported",
        source_year=2026,
        updated_by="seed",
        updated_at=datetime(2026, 7, 1),
    )
    date_step = _step(storage_module, "date_reached")

    assert report_module.evaluate(_context(report_module, default_step, QueueQueryExecutor([]))).status == "completed"
    assert report_module.evaluate(
        _context(
            report_module,
            dependency_step,
            QueueQueryExecutor([]),
            dependencies={"upload_step": "completed"},
        )
    ).status == "completed"
    assert report_module.evaluate(
        _context(
            report_module,
            date_step,
            QueueQueryExecutor([]),
            schedule=schedule,
            now=datetime(2026, 7, 19),
        )
    ).status == "incomplete"
    assert report_module.evaluate(
        _context(
            report_module,
            date_step,
            QueueQueryExecutor([]),
            schedule=schedule,
            now=datetime(2026, 7, 20),
        )
    ).status == "completed"


def test_amount_pending_minimum_time_and_multi_source_rules_cover_empty_and_complete_states():
    report_module = _report_navigation()
    storage_module = _storage()
    amount_source = _source(
        storage_module,
        fields={
            "period_field": "caldate",
            "left_amount_field": "a0001",
            "right_amount_field": "d0000",
        },
    )
    amount_step = _step(storage_module, "amounts_equal", sources=(amount_source,))
    assert report_module.evaluate(
        _context(report_module, amount_step, QueueQueryExecutor([{"scope_count": 0, "exception_count": 0}]))
    ).status == "incomplete"
    assert report_module.evaluate(
        _context(report_module, amount_step, QueueQueryExecutor([{"scope_count": 3, "exception_count": 0}]))
    ).status == "completed"

    pending_sources = tuple(
        storage_module.StepSourceConfig(
            id=index,
            source_role=role,
            data_source_name="currency_report_24",
            table_name=role,
            display_order=index,
            fields={"period_field": "caldate", "status_field": "status"},
        )
        for index, role in enumerate(("straight_flush", "straight_flush_yxzgq"), start=1)
    )
    pending_step = _step(
        storage_module,
        "no_pending_status",
        sources=pending_sources,
        values={"pending_status": ("待确认", "待补充")},
    )
    pending_executor = QueueQueryExecutor(
        [
            {"scope_count": 2, "exception_count": 0},
            {"scope_count": 2, "exception_count": 0},
        ]
    )
    assert report_module.evaluate(_context(report_module, pending_step, pending_executor)).status == "completed"

    time_source = _source(storage_module, fields={"time_field": "tbtime"})
    time_step = _step(storage_module, "minimum_time_in_current_month", sources=(time_source,))
    assert report_module.evaluate(
        _context(
            report_module,
            time_step,
            QueueQueryExecutor([{"row_count": 2, "minimum_time": datetime(2026, 7, 1)}]),
        )
    ).status == "completed"

    all_sources = tuple(
        storage_module.StepSourceConfig(
            id=index,
            source_role=role,
            data_source_name="zxd",
            table_name=role,
            display_order=index,
            fields={"date_field": "createdate"},
        )
        for index, role in enumerate(("asset_credit", "external_data", "basic_info"), start=1)
    )
    all_sources_step = _step(
        storage_module,
        "current_month_rows_in_all_sources",
        sources=all_sources,
    )
    assert report_module.evaluate(
        _context(
            report_module,
            all_sources_step,
            QueueQueryExecutor([{"row_count": 1}, {"row_count": 1}, {"row_count": 1}]),
        )
    ).status == "completed"


def test_ck_report_period_dependency_quarterly_and_waiting_report_period_rules():
    report_module = _report_navigation()
    storage_module = _storage()
    ck_source = _source(storage_module, role="ck_result")
    period_source = storage_module.StepSourceConfig(
        id=2,
        source_role="spv_detail",
        data_source_name="ass_man_reg_24",
        table_name="zgxgzh_spvdetail_zg08",
        display_order=2,
        fields={"period_field": "caldate"},
    )
    ck_step = _step(
        storage_module,
        "no_ck_and_report_period",
        sources=(ck_source, period_source),
        values={"target_ck_id": ("7118",)},
    )
    assert report_module.evaluate(
        _context(
            report_module,
            ck_step,
            QueueQueryExecutor(
                [
                    {"scope_count": 0, "exception_count": None},
                    {"scope_count": 6409, "exception_count": 0},
                ]
            ),
        )
    ).status == "completed"
    assert report_module.evaluate(
        _context(
            report_module,
            ck_step,
            QueueQueryExecutor(
                [
                    {"scope_count": 0, "exception_count": None},
                    {"scope_count": 6409, "exception_count": 1},
                ]
            ),
        )
    ).status == "incomplete"

    month_source = _source(storage_module, fields={"date_field": "chdate"})
    month_step = _step(
        storage_module,
        "month_rows_or_dependency",
        sources=(month_source,),
        dependencies=("pbc_template_6",),
    )
    assert report_module.evaluate(
        _context(
            report_module,
            month_step,
            QueueQueryExecutor([{"row_count": 0}]),
            dependencies={"pbc_template_6": "completed"},
        )
    ).status == "completed"

    quarterly_source = _source(storage_module, fields={"date_field": "createdate"})
    quarterly_step = _step(
        storage_module,
        "quarterly_rows_exist",
        sources=(quarterly_source,),
        values={"active_month": ("1", "4", "7", "10")},
    )
    assert report_module.evaluate(
        _context(
            report_module,
            quarterly_step,
            QueueQueryExecutor([]),
            now=datetime(2026, 8, 1),
        )
    ).status == "completed"
    assert report_module.evaluate(
        _context(
            report_module,
            quarterly_step,
            QueueQueryExecutor([{"row_count": 1}]),
            now=datetime(2026, 7, 1),
        )
    ).status == "completed"

    waiting = report_module.evaluate(
        _context(
            report_module,
            ck_step,
            QueueQueryExecutor([]),
            report_date=None,
        )
    )
    assert (waiting.status, waiting.message) == ("waiting_report_period", "等待自动对数报告期")


def test_period_bounds_cover_week_month_quarter_and_year():
    module = _report_navigation()
    today = date(2026, 7, 16)

    assert module.period_bounds("week", today) == (datetime(2026, 7, 13), datetime(2026, 7, 20))
    assert module.period_bounds("month", today) == (datetime(2026, 7, 1), datetime(2026, 8, 1))
    assert module.period_bounds("quarter", today) == (datetime(2026, 7, 1), datetime(2026, 10, 1))
    assert module.period_bounds("year", today) == (datetime(2026, 1, 1), datetime(2027, 1, 1))


def test_scheduler_lock_skips_active_lease_and_recovers_after_expiry():
    module = _storage()
    database = _database()
    database.connection.tables["report_nav_scheduler_state"].append(
        {
            "id": 1,
            "enabled": 1,
            "interval_minutes": 10,
            "next_run_at": None,
            "lock_owner": None,
            "lock_until": None,
            "last_started_at": None,
            "last_finished_at": None,
            "last_status": None,
            "last_error": None,
            "updated_at": datetime(2026, 7, 16, 9, 0),
        }
    )
    store = module.ReportNavigationStore(database)
    now = datetime(2026, 7, 16, 9, 0)

    assert store.try_acquire_scheduler_lock("worker-a", now, timedelta(minutes=30)) is True
    assert store.try_acquire_scheduler_lock("worker-b", now, timedelta(minutes=30)) is False
    assert store.try_acquire_scheduler_lock(
        "worker-b", now + timedelta(minutes=31), timedelta(minutes=30)
    ) is True


class OrderedEvaluator:
    def __init__(self, report_module):
        self.report_module = report_module
        self.calls = []

    def __call__(self, context):
        self.calls.append(context.step.step_code)
        return self.report_module.EvaluationResult("completed", "完成")


class SupplementQueryExecutor(QueueQueryExecutor):
    def __init__(self):
        super().__init__(
            [
                {"total_count": 4, "completed_count": 1, "incomplete_count": 3},
                {"total_count": 8, "completed_count": 2, "incomplete_count": 6},
                {"total_count": 12, "completed_count": 3, "incomplete_count": 9},
                {"total_count": 16, "completed_count": 4, "incomplete_count": 12},
            ]
        )
        self.active = 0
        self.max_active = 0

    def fetch_one(self, source, sql, params=()):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            return super().fetch_one(source, sql, params)
        finally:
            self.active -= 1


def _seed_collection_configuration(database):
    tables = database.connection.tables
    tables["report_nav_scheduler_state"].append(
        {
            "id": 1,
            "enabled": 1,
            "interval_minutes": 10,
            "next_run_at": None,
            "lock_owner": None,
            "lock_until": None,
            "last_started_at": None,
            "last_finished_at": None,
            "last_status": None,
            "last_error": None,
            "updated_at": datetime(2026, 7, 16, 9, 0),
        }
    )
    tables["report_nav_processes"].extend(
        [
            {"process_code": "p1", "process_name": "节点1", "display_order": 1, "enabled": 1, "allow_manual_step_completion": 1},
            {"process_code": "p2", "process_name": "节点2", "display_order": 2, "enabled": 1, "allow_manual_step_completion": 1},
            {"process_code": "supplement_tasks", "process_name": "补录任务", "display_order": 1000, "enabled": 0, "allow_manual_step_completion": 0},
        ]
    )
    tables["report_nav_process_months"].extend(
        [{"process_code": "p1", "month_no": 7}, {"process_code": "p2", "month_no": 7}]
    )
    tables["report_nav_steps"].extend(
        [
            {"step_code": "p1_s1", "process_code": "p1", "step_name": "步骤1", "display_order": 1, "evaluator_key": "default_completed", "enabled": 1, "default_completed": 1, "manual_completion_allowed": 1},
            {"step_code": "p1_s2", "process_code": "p1", "step_name": "步骤2", "display_order": 2, "evaluator_key": "default_completed", "enabled": 1, "default_completed": 1, "manual_completion_allowed": 1},
            {"step_code": "p2_s1", "process_code": "p2", "step_name": "步骤1", "display_order": 1, "evaluator_key": "default_completed", "enabled": 1, "default_completed": 1, "manual_completion_allowed": 1},
            {"step_code": "supplement_tasks_1", "process_code": "supplement_tasks", "step_name": "统计补录任务", "display_order": 1, "evaluator_key": "supplement_task_counts", "enabled": 0, "default_completed": 0, "manual_completion_allowed": 0},
        ]
    )
    tables["report_nav_step_sources"].append(
        {"id": 50, "step_code": "supplement_tasks_1", "source_role": "primary", "data_source_name": "bl", "table_name": "jsxt_console.rep_data_task_detail", "display_order": 1, "enabled": 1}
    )
    tables["report_nav_step_fields"].extend(
        [
            {"id": 51, "step_source_id": 50, "field_role": "date_field", "column_name": "create_date"},
            {"id": 52, "step_source_id": 50, "field_role": "status_field", "column_name": "status"},
            {"id": 53, "step_source_id": 50, "field_role": "deleted_field", "column_name": "del_flag"},
        ]
    )
    tables["report_nav_step_values"].extend(
        [
            {"id": 51, "step_code": "supplement_tasks_1", "value_role": "completed_status", "value_text": "5", "value_type": "text", "display_order": 1},
            {"id": 52, "step_code": "supplement_tasks_1", "value_role": "valid_deleted_value", "value_text": "0", "value_type": "text", "display_order": 1},
        ]
    )


def test_collection_is_strictly_serial_and_writes_process_and_four_period_card_snapshots():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    evaluator = OrderedEvaluator(report_module)
    query = SupplementQueryExecutor()
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=lambda: query,
        evaluator=evaluator,
    )

    result = service.collect_once(now=datetime(2026, 7, 16, 9, 30))

    assert result.status == "completed"
    assert evaluator.calls == ["p1_s1", "p1_s2", "p2_s1"]
    assert query.max_active == 1
    assert len(query.calls) == 4
    process_rows = database.connection.tables["report_nav_process_snapshots"]
    assert [(row["process_code"], row["status"]) for row in process_rows] == [
        ("p1", "completed"),
        ("p2", "completed"),
    ]
    supplement_cards = [
        row
        for row in database.connection.tables["report_nav_card_snapshots"]
        if row["card_code"] == "supplement_tasks"
    ]
    assert [row["stat_period"] for row in supplement_cards] == [
        "week",
        "month",
        "quarter",
        "year",
    ]


def test_collection_evaluates_forward_dependencies_before_dependent_steps():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    database.connection.tables["report_nav_step_dependencies"].append(
        {"step_code": "p1_s1", "depends_on_step_code": "p1_s2"}
    )
    calls = []

    def evaluator(context):
        calls.append(context.step.step_code)
        if context.step.step_code == "p1_s1":
            return report_module.evaluate_dependency_completed(context)
        return report_module.EvaluationResult("completed", "完成")

    store = storage_module.ReportNavigationStore(database)
    service = report_module.ReportNavigationService(
        database,
        store=store,
        query_executor_factory=SupplementQueryExecutor,
        evaluator=evaluator,
    )

    result = service.collect_once(now=datetime(2026, 7, 16, 9, 30))

    assert result.status == "completed"
    assert calls == ["p1_s2", "p1_s1", "p2_s1"]
    assert store.load_step_snapshot("2026-07", "p1_s1").effective_status == "completed"
    assert store.load_process_snapshot("2026-07", "p1").status == "completed"
    configured = store.load_configuration("2026-07")
    assert [step.step_code for step in configured[0].steps] == ["p1_s1", "p1_s2"]


def test_collection_uses_and_refreshes_final_archive_step_completion_time():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    store = storage_module.ReportNavigationStore(database)
    database.connection.tables["report_nav_monthly_schedules"].append(
        {
            "report_month": "2026-07",
            "process_code": "p1",
            "report_date": date(2026, 7, 10),
            "source_type": "manual",
            "source_year": 2026,
            "updated_by": "admin",
            "updated_at": datetime(2026, 7, 10, 9, 0),
        }
    )
    archive_times = [
        datetime(2026, 7, 15, 18, 20, 30),
        datetime(2026, 7, 15, 18, 25, 40),
    ]

    def evaluator(context):
        completed_at = archive_times[0] if context.step.step_code == "p1_s2" else None
        return report_module.EvaluationResult(
            "completed",
            "完成",
            completed_at=completed_at,
        )

    service = report_module.ReportNavigationService(
        database,
        store=store,
        query_executor_factory=SupplementQueryExecutor,
        evaluator=evaluator,
    )

    service.collect_once(now=datetime(2026, 7, 16, 9, 30))
    first_step = store.load_step_snapshot("2026-07", "p1_s2")
    first_process = store.load_process_snapshot("2026-07", "p1")

    assert first_step.auto_completed_at == archive_times[0]
    assert first_process.completed_at == archive_times[0]

    archive_times.pop(0)
    service.collect_once(now=datetime(2026, 7, 16, 9, 40))
    refreshed_step = store.load_step_snapshot("2026-07", "p1_s2")
    refreshed_process = store.load_process_snapshot("2026-07", "p1")

    assert refreshed_step.auto_completed_at == archive_times[0]
    assert refreshed_process.completed_at == archive_times[0]


def test_collection_continues_after_one_step_error_and_marks_partial_run():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    calls = []

    def evaluator(context):
        calls.append(context.step.step_code)
        if context.step.step_code == "p1_s1":
            return report_module.EvaluationResult("error", "判断异常", "source unavailable")
        return report_module.EvaluationResult("completed", "完成")

    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=SupplementQueryExecutor,
        evaluator=evaluator,
    )

    result = service.collect_once(now=datetime(2026, 7, 16, 9, 30))

    assert result.status == "partial"
    assert result.failed_steps == 1
    assert calls == ["p1_s1", "p1_s2", "p2_s1"]
    assert database.connection.tables["report_nav_stat_runs"][0]["status"] == "partial"


def test_collection_uses_reached_report_date_as_completion_fallback_without_querying_steps():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    report_day = datetime(2026, 7, 16, 21, 0)
    database.connection.tables["report_nav_monthly_schedules"].append(
        {
            "report_month": "2026-07",
            "process_code": "p1",
            "report_date": date(2026, 7, 16),
            "source_type": "manual",
            "source_year": 2026,
            "updated_by": "admin",
            "updated_at": report_day,
        }
    )
    calls = []

    def evaluator(context):
        calls.append(context.step.step_code)
        return report_module.EvaluationResult("incomplete", "未完成")

    store = storage_module.ReportNavigationStore(database)
    service = report_module.ReportNavigationService(
        database,
        store=store,
        query_executor_factory=SupplementQueryExecutor,
        evaluator=evaluator,
    )
    admin = {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}

    same_day = service.collect_once(now=report_day)

    assert same_day.status == "completed"
    assert calls == ["p1_s1", "p1_s2", "p2_s1"]
    assert store.load_process_snapshot("2026-07", "p1").status == "incomplete"

    calls.clear()
    next_day = report_day + timedelta(days=1)
    result = service.collect_once(now=next_day)

    assert result.status == "completed"
    assert calls == ["p1_s1", "p1_s2", "p2_s1"]
    p1 = store.load_process_snapshot("2026-07", "p1")
    assert (p1.status, p1.completed_steps, p1.total_steps) == ("completed", 2, 2)
    assert p1.completed_at == datetime(2026, 7, 16, 20, 0)
    for step_code in ("p1_s1", "p1_s2"):
        step = store.load_step_snapshot("2026-07", step_code)
        assert step.auto_status == "completed"
        assert step.effective_status == "completed"
        assert step.completion_source == "schedule"
        assert step.auto_completed_at == datetime(2026, 7, 16, 20, 0)
        assert "报送日期" in step.status_message

    service.update_schedule(
        "p1",
        "2026-07",
        "2026-07-18",
        admin,
        now=next_day + timedelta(minutes=1),
    )

    rescheduled = store.load_process_snapshot("2026-07", "p1")
    assert rescheduled.status == "incomplete"
    assert rescheduled.completed_at is None

    service.update_schedule(
        "p1",
        "2026-07",
        "2026-07-15",
        admin,
        now=next_day + timedelta(minutes=3),
    )

    refreshed = store.load_process_snapshot("2026-07", "p1")
    assert refreshed.completed_at == datetime(2026, 7, 15, 20, 0)
    assert store.load_step_snapshot(
        "2026-07", "p1_s2"
    ).auto_completed_at == datetime(2026, 7, 15, 20, 0)


def test_scheduler_uses_initial_delay_then_configured_interval_without_parallel_runs():
    module = _report_navigation()

    class Service:
        interval_minutes = 10

        def __init__(self):
            self.calls = 0

        def collect_once(self):
            self.calls += 1

    service = Service()
    scheduler = module.ReportNavigationScheduler(
        service,
        initial_delay_seconds=0.01,
        interval_seconds=0.02,
    )
    scheduler.start()
    try:
        deadline = datetime.now() + timedelta(seconds=1)
        while service.calls < 2 and datetime.now() < deadline:
            scheduler.wait_for_activity(0.02)
    finally:
        scheduler.stop()

    assert service.calls >= 2


def test_service_rejects_invalid_period_historical_schedule_and_non_current_manual_month():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=SupplementQueryExecutor,
    )
    admin = {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}

    for invalid_period in ("", "day", "all"):
        try:
            service.dashboard(period=invalid_period, current_user=admin)
        except ValueError as exc:
            assert "period" in str(exc)
        else:
            raise AssertionError("invalid period should be rejected")

    try:
        service.set_manual_state(
            "p1_s1", "manual-complete", "2026-06", admin, now=datetime(2026, 7, 16)
        )
    except ValueError as exc:
        assert "当前月" in str(exc)
    else:
        raise AssertionError("historical manual month should be rejected")

    try:
        service.update_schedule(
            "p1", "2026-06", "2026-06-20", admin, now=datetime(2026, 7, 16)
        )
    except ValueError as exc:
        assert "历史月份" in str(exc)
    else:
        raise AssertionError("historical schedule should be rejected")


def test_dashboard_returns_selected_period_snapshots_processes_and_latest_run():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=SupplementQueryExecutor,
        evaluator=OrderedEvaluator(report_module),
    )
    current = datetime(2026, 7, 16, 9, 30)
    service.collect_once(now=current)

    payload = service.dashboard(
        period="quarter",
        current_user={"username": "user", "role": "user"},
        now=current,
    )

    assert payload["period"] == "quarter"
    assert payload["report_month"] == "2026-07"
    assert [card["card_code"] for card in payload["cards"]] == [
        "report_forms",
        "supplement_tasks",
        "data_governance",
        "special_governance",
    ]
    supplement = next(card for card in payload["cards"] if card["card_code"] == "supplement_tasks")
    assert (supplement["total_count"], supplement["completed_count"], supplement["incomplete_count"]) == (12, 3, 9)
    assert [process["process_code"] for process in payload["processes"]] == ["p1", "p2"]
    assert payload["last_run"]["status"] == "completed"
    assert payload["manual_refresh"]["allowed"] is True
    assert payload["manual_refresh"]["retry_after_seconds"] == 0


def test_dashboard_returns_database_work_calendar_for_current_year():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    database.connection.tables["report_nav_work_calendar"] = [
        {
            "calendar_date": date(2026, 1, 1),
            "calendar_year": 2026,
            "day_type": "holiday",
            "day_name": "元旦",
            "source_document": "国办发明电〔2025〕7号",
            "updated_by": "system",
            "updated_at": datetime(2025, 11, 4, 17, 0),
        },
        {
            "calendar_date": date(2026, 1, 4),
            "calendar_year": 2026,
            "day_type": "adjusted_workday",
            "day_name": "元旦调休补班",
            "source_document": "国办发明电〔2025〕7号",
            "updated_by": "system",
            "updated_at": datetime(2025, 11, 4, 17, 0),
        },
    ]
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
    )

    payload = service.dashboard(
        period="month",
        current_user={"role": "user"},
        now=datetime(2026, 7, 21, 9, 30),
    )

    assert payload["work_calendar"] == {
        "year": 2026,
        "configured": True,
        "holidays": ["2026-01-01"],
        "adjusted_workdays": ["2026-01-04"],
    }


def test_governance_card_admin_maintenance_updates_all_periods_and_dashboard_uses_selected_value():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=SupplementQueryExecutor,
        evaluator=OrderedEvaluator(report_module),
    )
    admin = {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}
    values = {
        "week": {"completed_count": 1, "incomplete_count": 2},
        "month": {"completed_count": 3, "incomplete_count": 4},
        "quarter": {"completed_count": 5, "incomplete_count": 6},
        "year": {"completed_count": 7, "incomplete_count": 8},
    }

    result = service.update_card_manual_values(
        "special_governance", values, admin, now=datetime(2026, 7, 16, 9, 30)
    )
    payload = service.dashboard(
        period="quarter", current_user=admin, now=datetime(2026, 7, 16, 9, 31)
    )

    assert result == {"ok": True, "card_code": "special_governance"}
    card = next(item for item in payload["cards"] if item["card_code"] == "special_governance")
    assert (card["total_count"], card["completed_count"], card["incomplete_count"]) == (11, 5, 6)
    assert round(card["completion_rate"], 2) == 45.45
    assert payload["card_maintenance"]["special_governance"]["year"] == {
        "completed_count": 7,
        "incomplete_count": 8,
    }


def test_governance_card_maintenance_rejects_non_admin_invalid_card_and_missing_period():
    report_module = _report_navigation()
    storage_module = _storage()
    service = report_module.ReportNavigationService(
        _database(), store=storage_module.ReportNavigationStore(_database())
    )
    values = {
        period: {"completed_count": 0, "incomplete_count": 0}
        for period in ("week", "month", "quarter", "year")
    }
    fractional_values = {period: dict(row) for period, row in values.items()}
    fractional_values["week"]["completed_count"] = 1.5

    for card_code, user, payload in [
        ("data_governance", {"role": "user"}, values),
        ("report_forms", {"role": "admin"}, values),
        ("data_governance", {"role": "admin"}, {"month": values["month"]}),
        ("data_governance", {"role": "admin"}, fractional_values),
    ]:
        try:
            service.update_card_manual_values(card_code, payload, user)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid governance maintenance should be rejected")


def test_manual_refresh_waits_for_source_commit_before_collecting(monkeypatch):
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
    )
    events = []

    monkeypatch.setattr(
        report_module,
        "sleep",
        lambda seconds: events.append(("settle", seconds)),
        raising=False,
    )

    def collect_once(*, trigger_type="scheduled", now=None):
        events.append(("collect", trigger_type))
        return report_module.CollectionResult(
            "completed", "2026-07", 1, 7, 0
        )

    monkeypatch.setattr(service, "collect_once", collect_once)

    payload = service.manual_refresh(current_user={"role": "admin"})

    assert payload["status"] == "completed"
    assert events == [("settle", 0.8), ("collect", "manual")]


def test_manual_refresh_uses_database_cooldown_for_five_minutes_after_completion():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=SupplementQueryExecutor,
        evaluator=OrderedEvaluator(report_module),
    )
    current = datetime(2026, 7, 16, 9, 30)

    first = service.manual_refresh(now=current)
    blocked = service.manual_refresh(now=current + timedelta(minutes=4, seconds=59))
    second = service.manual_refresh(now=current + timedelta(minutes=5))

    assert first["status"] == "completed"
    assert first["cooldown_seconds"] == 300
    assert blocked["status"] == "cooldown"
    assert blocked["retry_after_seconds"] == 1
    assert second["status"] == "completed"
    manual_runs = [
        row
        for row in database.connection.tables["report_nav_stat_runs"]
        if row["trigger_type"] == "manual"
    ]
    assert len(manual_runs) == 2


def test_admin_manual_refresh_bypasses_cooldown_but_keeps_refresh_available():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=SupplementQueryExecutor,
        evaluator=OrderedEvaluator(report_module),
    )
    current = datetime(2026, 7, 16, 9, 30)
    admin = {"role": "admin"}

    first = service.manual_refresh(now=current, current_user=admin)
    second = service.manual_refresh(now=current + timedelta(seconds=1), current_user=admin)

    assert first["status"] == "completed"
    assert first["cooldown_seconds"] == 0
    assert first["retry_after_seconds"] == 0
    assert first["allowed"] is True
    assert second["status"] == "completed"
    manual_runs = [
        row
        for row in database.connection.tables["report_nav_stat_runs"]
        if row["trigger_type"] == "manual"
    ]
    assert len(manual_runs) == 2


def test_dashboard_manual_refresh_state_applies_cooldown_only_to_non_admin():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=SupplementQueryExecutor,
        evaluator=OrderedEvaluator(report_module),
    )
    current = datetime(2026, 7, 16, 9, 30)
    service.manual_refresh(now=current, current_user={"role": "user"})

    user_payload = service.dashboard(
        period="month",
        current_user={"role": "user"},
        now=current + timedelta(seconds=1),
    )
    admin_payload = service.dashboard(
        period="month",
        current_user={"role": "admin"},
        now=current + timedelta(seconds=1),
    )

    assert user_payload["manual_refresh"]["allowed"] is False
    assert user_payload["manual_refresh"]["retry_after_seconds"] == 299
    assert admin_payload["manual_refresh"]["allowed"] is True
    assert admin_payload["manual_refresh"]["retry_after_seconds"] == 0


def test_manual_refresh_returns_collection_error_for_frontend_prompt():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)

    def failing_query_factory():
        raise RuntimeError("业务数据源连接失败")

    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=failing_query_factory,
    )

    payload = service.manual_refresh(now=datetime(2026, 7, 16, 9, 30))

    assert payload["status"] == "failed"
    assert payload["error_message"] == "业务数据源连接失败"
    assert payload["cooldown_seconds"] == 300


def test_manual_refresh_partial_returns_step_issue_details_for_troubleshooting():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)

    def evaluator(context):
        if context.step.step_code == "p1_s1":
            return report_module.EvaluationResult("error", "判断异常", "数据源 source_a 连接失败")
        if context.step.step_code == "p2_s1":
            return report_module.EvaluationResult("error", "判断异常", "表 result_b 不存在")
        return report_module.EvaluationResult("completed", "完成")

    service = report_module.ReportNavigationService(
        database,
        store=storage_module.ReportNavigationStore(database),
        query_executor_factory=SupplementQueryExecutor,
        evaluator=evaluator,
    )

    payload = service.manual_refresh(now=datetime(2026, 7, 16, 9, 30))

    assert payload["status"] == "partial"
    assert payload["failed_steps"] == 2
    assert payload["error_message"] == "刷新完成，但有 2 个步骤统计异常，请查看具体问题"
    assert payload["issues"] == [
        {
            "process_code": "p1",
            "process_name": "节点1",
            "step_code": "p1_s1",
            "step_name": "步骤1",
            "error_message": "数据源 source_a 连接失败",
        },
        {
            "process_code": "p2",
            "process_name": "节点2",
            "step_code": "p2_s1",
            "step_name": "步骤1",
            "error_message": "表 result_b 不存在",
        },
    ]


def test_manual_completion_recalculates_process_and_cancel_restores_automatic_state():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)

    def evaluator(context):
        status = "incomplete" if context.step.step_code == "p1_s2" else "completed"
        return report_module.EvaluationResult(status, status)

    store = storage_module.ReportNavigationStore(database)
    service = report_module.ReportNavigationService(
        database,
        store=store,
        query_executor_factory=SupplementQueryExecutor,
        evaluator=evaluator,
    )
    current = datetime(2026, 7, 16, 9, 30)
    admin = {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}
    service.collect_once(now=current)
    assert store.load_process_snapshot("2026-07", "p1").status == "incomplete"

    service.set_manual_state(
        "p1_s2", "manual-complete", "2026-07", admin, now=current + timedelta(minutes=1)
    )
    completed = store.load_process_snapshot("2026-07", "p1")
    assert completed.status == "completed"
    assert completed.completed_at == current + timedelta(minutes=1)
    assert store.load_card_snapshots("month")["report_forms"].completed_count == 2

    service.set_manual_state(
        "p1_s2", "manual-cancel", "2026-07", admin, now=current + timedelta(minutes=2)
    )
    restored_step = store.load_step_snapshot("2026-07", "p1_s2")
    restored_process = store.load_process_snapshot("2026-07", "p1")
    assert restored_step.effective_status == "incomplete"
    assert restored_step.completion_source == "auto"
    assert restored_process.status == "incomplete"
    assert restored_process.completed_at is None
    assert store.load_card_snapshots("month")["report_forms"].completed_count == 1


def test_schedule_update_accepts_current_or_future_month_and_rejects_cross_month_date():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    store = storage_module.ReportNavigationStore(database)
    service = report_module.ReportNavigationService(database, store=store)
    admin = {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}
    current = datetime(2026, 7, 16, 9, 30)

    service.update_schedule("p1", "2026-07", "2026-07-20", admin, now=current)
    service.update_schedule("p1", "2026-08", "2026-08-21", admin, now=current)

    assert store.load_schedules("2026-07")["p1"].report_date == date(2026, 7, 20)
    assert store.load_schedules("2026-08")["p1"].report_date == date(2026, 8, 21)
    try:
        service.update_schedule("p1", "2026-08", "2026-09-01", admin, now=current)
    except ValueError as exc:
        assert "报送月份" in str(exc)
    else:
        raise AssertionError("cross-month schedule date should be rejected")


def test_schedule_owner_is_saved_and_returned_in_dashboard():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    store = storage_module.ReportNavigationStore(database)
    service = report_module.ReportNavigationService(database, store=store)
    current = datetime(2026, 7, 16, 9, 30)
    admin = {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}
    user = {"id": "u2", "username": "user", "display_name": "用户", "role": "user"}
    store.upsert_schedule(
        "2026-07",
        "p1",
        date(2026, 7, 20),
        source_type="manual",
        source_year=2026,
        updated_by="admin",
        now=current,
    )

    result = service.update_schedule_owner(
        "p1", "2026-07", "  张智核  ", admin, now=current
    )
    admin_payload = service.dashboard(period="month", current_user=admin, now=current)
    user_payload = service.dashboard(period="month", current_user=user, now=current)
    admin_process = next(item for item in admin_payload["processes"] if item["process_code"] == "p1")
    user_process = next(item for item in user_payload["processes"] if item["process_code"] == "p1")

    assert result == {"ok": True, "process_code": "p1", "report_month": "2026-07", "owner_name": "张智核"}
    assert (admin_process["owner_name"], admin_process["owner_editable"]) == ("张智核", True)
    assert (user_process["owner_name"], user_process["owner_editable"]) == ("张智核", False)


def test_schedule_owner_rejects_non_admin_historical_month_and_long_name():
    report_module = _report_navigation()
    storage_module = _storage()
    database = _database()
    _seed_collection_configuration(database)
    service = report_module.ReportNavigationService(
        database, store=storage_module.ReportNavigationStore(database)
    )
    current = datetime(2026, 7, 16, 9, 30)

    invalid_inputs = [
        ("2026-07", "张智核", {"role": "user"}, "管理员"),
        ("2026-06", "张智核", {"role": "admin"}, "历史月份"),
        ("2026-07", "张" * 129, {"role": "admin"}, "128"),
    ]
    for report_month, owner_name, actor, expected in invalid_inputs:
        try:
            service.update_schedule_owner(
                "p1", report_month, owner_name, actor, now=current
            )
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("invalid schedule owner update should be rejected")
