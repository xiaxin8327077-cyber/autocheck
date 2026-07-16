from datetime import date, datetime
import importlib
from pathlib import Path

from mysql_config_test_support import MemoryApplicationDatabase


ROOT = Path(__file__).resolve().parents[1]
STORAGE_MODULE = ROOT / "src" / "auto_check" / "app" / "storage_report_navigation.py"


def _storage():
    assert STORAGE_MODULE.exists(), "report navigation storage module is missing"
    return importlib.import_module("auto_check.app.storage_report_navigation")


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

