from datetime import date, datetime
import importlib.util
from pathlib import Path
import re

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_report_navigation_seed.py"
SEED_SQL = ROOT / "sql" / "app_storage" / "mysql" / "003_report_navigation_seed.sql"


def _load_script_module():
    assert SCRIPT_PATH.exists(), "report navigation seed builder is missing"
    spec = importlib.util.spec_from_file_location("build_report_navigation_seed", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_workbook(path: Path, rows: list[tuple[object, object]]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "工作日数据"
    sheet.append(["报送类型", "报送日期"])
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)
    return path


def test_schedule_rows_use_monthly_max_for_1104(tmp_path):
    module = _load_script_module()
    source = _write_workbook(
        tmp_path / "工作日数据.xlsx",
        [(1104, datetime(2026, 7, 6)), (1104, datetime(2026, 7, 10))],
    )

    rows = [row for row in module.load_schedule_rows(source) if row.process_code == "jr_1104"]

    assert [(row.report_month, row.report_date) for row in rows] == [
        ("2026-07", date(2026, 7, 10))
    ]


def test_schedule_rows_add_pbc_central_defaults_and_filter_five_articles(tmp_path):
    module = _load_script_module()
    source = _write_workbook(
        tmp_path / "工作日数据.xlsx",
        [
            ("人行模板\\逐笔", datetime(2026, 1, 5)),
            ("五篇大文章", datetime(2026, 1, 20)),
            ("五篇大文章", datetime(2026, 2, 20)),
            ("五篇大文章", datetime(2026, 4, 20)),
            ("五篇大文章", datetime(2026, 7, 20)),
            ("五篇大文章", datetime(2026, 10, 20)),
        ],
    )

    rows = module.load_schedule_rows(source)

    central = [row for row in rows if row.process_code == "pbc_central"]
    five_articles = [row for row in rows if row.process_code == "five_articles"]
    assert len(central) == 12
    assert all(row.report_date.day == 1 for row in central)
    assert {row.report_date.month for row in five_articles} == {1, 4, 7, 10}


def test_seed_contains_complete_relational_configuration_without_existing_table_writes():
    assert SEED_SQL.exists(), "report navigation seed SQL is missing"
    sql = SEED_SQL.read_text(encoding="utf-8")

    assert "app_schema_version" not in sql
    assert "INSERT INTO `report_nav_processes`" in sql
    assert "INSERT INTO `report_nav_process_months`" in sql
    assert "INSERT INTO `report_nav_steps`" in sql
    assert "INSERT INTO `report_nav_step_dependencies`" in sql
    assert "INSERT INTO `report_nav_step_sources`" in sql
    assert "INSERT INTO `report_nav_step_fields`" in sql
    assert "INSERT INTO `report_nav_step_values`" in sql
    assert "INSERT INTO `report_nav_monthly_schedules`" in sql
    assert "INSERT INTO `report_nav_scheduler_state`" in sql
    assert len(re.findall(r"\('2026-(?:01|04|07|10)', 'five_articles',", sql)) == 4
    for process_code in (
        "pbc_central",
        "pbc_template",
        "jr_1104",
        "full_elements",
        "citic_registration",
        "east5",
        "five_articles",
    ):
        assert process_code in sql
