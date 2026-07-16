from datetime import date, datetime
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


def test_no_ck_rule_requires_current_period_rows_and_maps_query_error():
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

    assert report_module.evaluate(_context(report_module, step, empty_ck)).status == "incomplete"
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


def test_ck_min_time_month_dependency_quarterly_and_waiting_report_period_rules():
    report_module = _report_navigation()
    storage_module = _storage()
    ck_source = _source(storage_module, role="ck_result")
    time_source = storage_module.StepSourceConfig(
        id=2,
        source_role="spv_detail",
        data_source_name="ass_man_reg_24",
        table_name="zgxgzh_spvdetail_zg08",
        display_order=2,
        fields={"time_field": "tbtime"},
    )
    ck_step = _step(
        storage_module,
        "no_ck_and_min_time",
        sources=(ck_source, time_source),
        values={"target_ck_id": ("7118",)},
    )
    assert report_module.evaluate(
        _context(
            report_module,
            ck_step,
            QueueQueryExecutor(
                [
                    {"scope_count": 4, "exception_count": 0},
                    {"row_count": 2, "minimum_time": datetime(2026, 7, 1)},
                ]
            ),
        )
    ).status == "completed"

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
