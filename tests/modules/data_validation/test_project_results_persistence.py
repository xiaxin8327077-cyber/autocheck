"""项目结果逐条持久化与导出：真实明细、事务边界、防注入。"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import event

from auto_check.modules.data_validation import exports
from auto_check.modules.data_validation.module import DataValidationModule
from auto_check.modules.data_validation.storage import ISSUES, RULES, TASK_RULES, VERSIONS, RuleStorage
from tests.modules.data_validation.support import MemoryDatabase


MODULE_DIR = Path(__file__).resolve().parents[3] / "src" / "auto_check" / "modules" / "data_validation"


def _storage() -> tuple[MemoryDatabase, RuleStorage]:
    database = MemoryDatabase()
    return database, RuleStorage(database)


def _queued_task_rule(storage: RuleStorage) -> dict:
    rule = storage.create_rule(
        creator_user_id="1", name="期限规则", description="", definition={
            "rule_type": "field_compare", "source_id": "src", "table_name": "t",
            "expression": {"left": "a", "op": "eq", "right_type": "value", "right": 0},
        },
        sql_text="SELECT 1", mapping_version="doc-v1-x", content_sha256="h", generation_mode="manual",
    )
    storage.set_status(int(rule["id"]), "enabled", int(rule["version_id"]))
    task = storage.create_task(
        creator_user_id="1", source_id="src", report_period="2026-09-30",
        params={"report_period": "2026-09-30"},
        rules=[{
            "rule_id": int(rule["id"]), "version_id": int(rule["version_id"]), "version_no": 1,
            "content_sha256": "h", "sql_summary": "SELECT 1",
        }],
    )
    return storage.task_rules(int(task["id"]))[0]


def _issue(**overrides):
    row = {
        "business_key": "P001", "project_code": "000123",
        "project_name": "某项目", "project_name_status": "ok", "issue_kind": "numeric", "message": "金额异常",
    }
    row.update(overrides)
    return row


def _rows(storage: RuleStorage, task_id: int) -> list[dict]:
    return storage.list_issues(int(task_id))["items"]


def test_record_rule_result_persists_real_rows_and_same_transaction_truncated():
    _database, storage = _storage()
    item = _queued_task_rule(storage)
    task_id = int(item["task_id"])
    ok = storage.record_rule_result(
        int(item["id"]), status="VIOLATION", error_code="", violation_count=3, truncated=True,
        issues=[
            _issue(business_key="P001", project_code="000123", project_name="项目一", project_name_status="ok"),
            _issue(business_key="0", project_code="0", project_name="零号项目"),
            _issue(business_key="000123", project_code="000123", project_name=None,
                   project_name_status="missing_null", issue_kind="missing_value"),
        ],
    )
    assert ok is True
    updated = storage.task_rules(task_id)[0]
    assert updated["status"] == "VIOLATION" and updated["violation_count"] == 3 and updated["truncated"] == 1
    assert storage.get_task(task_id)["truncated"] == 1

    rows = _rows(storage, task_id)
    assert [row["business_key"] for row in rows] == ["P001", "0", "000123"]
    assert [row["project_code"] for row in rows] == ["000123", "0", "000123"]
    assert [row["project_name"] for row in rows] == ["项目一", "零号项目", None]
    assert rows[0]["project_name_status"] == "ok"
    assert rows[1]["project_name_status"] == "ok"
    assert rows[2]["project_name_status"] == "missing_null"
    assert [row["issue_kind"] for row in rows] == ["numeric", "numeric", "missing_value"]


def test_record_rule_result_rejects_duplicate_or_cancelled_completion_without_overwrite():
    _database, storage = _storage()
    item = _queued_task_rule(storage)
    first = storage.record_rule_result(
        int(item["id"]), status="PASS", error_code="", violation_count=0, truncated=False, issues=[],
    )
    assert first is True
    duplicate = storage.record_rule_result(
        int(item["id"]), status="VIOLATION", error_code="", violation_count=1, truncated=False,
        issues=[_issue()],
    )
    assert duplicate is False
    assert storage.task_rules(int(item["task_id"]))[0]["status"] == "PASS"
    assert _rows(storage, item["task_id"]) == []

    storage.update_task_rule(int(item["id"]), status="CANCELLED")
    late = storage.record_rule_result(
        int(item["id"]), status="VIOLATION", error_code="", violation_count=1, truncated=False,
        issues=[_issue()],
    )
    assert late is False
    assert storage.task_rules(int(item["task_id"]))[0]["status"] == "CANCELLED"
    assert _rows(storage, item["task_id"]) == []


def test_missing_detail_retains_its_kind_and_project_without_a_fabricated_detail_key():
    _, storage = _storage()
    item = _queued_task_rule(storage)
    assert storage.record_rule_result(
        int(item["id"]), status="VIOLATION", error_code="", violation_count=1, truncated=False,
        issues=[_issue(business_key=None, issue_kind="missing_record", message="没有对应明细记录")],
    )
    rows = _rows(storage, item["task_id"])
    assert rows[0]["business_key"] == ""
    assert rows[0]["project_code"] == "000123"
    assert rows[0]["issue_kind"] == "missing_record"
    exported = list(csv.DictReader(io.StringIO(exports.issues_csv({"id": item["task_id"]}, rows).decode("utf-8"))))
    assert exported[0]["issue_kind"] == "missing_record"
    assert exported[0]["business_key"] == ""

def test_record_rule_result_validates_count_and_outcome_shape():
    _database, storage = _storage()
    item = _queued_task_rule(storage)
    with pytest.raises(ValueError):
        storage.record_rule_result(
            int(item["id"]), status="PASS", error_code="", violation_count=1, truncated=False,
            issues=[_issue()],
        )
    with pytest.raises(ValueError):
        storage.record_rule_result(
            int(item["id"]), status="VIOLATION", error_code="", violation_count=2, truncated=False,
            issues=[_issue()],
        )
    assert storage.record_rule_result(
        int(item["id"]), status="ERROR", error_code="MAPPING_DRIFT", violation_count=0,
        truncated=False, issues=[],
    ) is True


def test_record_rule_result_rolls_back_all_on_second_insert_failure():
    database, storage = _storage()
    item = _queued_task_rule(storage)
    task_id = int(item["task_id"])
    state = {"inserts": 0}

    def fail_second_insert(_conn, _cursor, statement, parameters, _context, _executemany):
        normalized = statement.upper()
        if "INSERT" in normalized and "DATA_VALIDATION_ISSUES" in normalized:
            state["inserts"] += 1
            # SQLAlchemy 对多行使用 executemany：这里模拟第二行明细写入失败。
            if isinstance(parameters, (list, tuple)) and len(parameters) >= 2:
                raise RuntimeError("第二条明细写入失败")

    event.listen(database.engine, "before_cursor_execute", fail_second_insert)
    try:
        with pytest.raises(RuntimeError):
            storage.record_rule_result(
                int(item["id"]), status="VIOLATION", error_code="", violation_count=2, truncated=True,
                issues=[_issue(), _issue(business_key="P002")],
            )
    finally:
        event.remove(database.engine, "before_cursor_execute", fail_second_insert)

    assert state["inserts"] == 1
    assert storage.task_rules(task_id)[0]["status"] == "queued"
    assert storage.task_rules(task_id)[0]["violation_count"] == 0
    assert storage.get_task(task_id)["truncated"] == 0
    assert _rows(storage, task_id) == []


def test_legacy_issue_without_collection_flag_is_not_presented_as_ok():
    database, storage = _storage()
    item = _queued_task_rule(storage)
    with database.begin() as connection:
        connection.execute(ISSUES.insert().values(
            task_id=int(item["task_id"]), rule_id=int(item["rule_id"]),
            version_no=int(item["version_no"]), business_key="LEGACY",
            message="历史明细", created_at="2026-01-01T00:00:00",
        ))
    row = _rows(storage, item["task_id"])[0]
    assert row["project_code"] is None and row["project_name"] is None
    assert row["project_name_status"] == "legacy_unavailable"
    assert row["issue_kind"] == "legacy"

    storage.add_issue(
        task_id=int(item["task_id"]), rule_id=int(item["rule_id"]), version_no=1,
        business_key="NEW", message="新明细",
    )
    new_row = next(row for row in _rows(storage, item["task_id"]) if row["business_key"] == "NEW")
    assert new_row["project_name_status"] == "not_required"
    assert new_row["issue_kind"] == "comparison"


def _export_task() -> dict:
    return {"id": 7, "truncated": False}


def _export_issues() -> list[dict]:
    return [
        {
            "rule_code": "DV000001", "business_key": "CONTRACT-P001",
            "project_code": "000123", "project_name": "正常中文项目",
            "project_name_status": "ok", "message": "金额异常",
        },
        {
            "rule_code": "DV000001", "business_key": "000000",
            "project_code": "000000", "project_name": "=CMD|' /C calc'!A1",
            "project_name_status": "ok", "message": "@cmd",
        },
        {
            "rule_code": "DV000001", "business_key": "P003",
            "project_code": "000124", "project_name": "\ufeff\t+SUM(A1)",
            "project_name_status": "missing", "message": "-危险",
        },
    ]


def test_csv_export_keeps_project_columns_and_blocks_formula_injection():
    payload = exports.issues_csv(_export_task(), _export_issues())
    text = payload.decode("utf-8")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[0][:6] == ["task_id", "rule_code", "business_key", "project_code", "project_name", "project_name_status"]
    assert [row[2] for row in reader[1:]] == ["CONTRACT-P001", "000000", "P003"]
    assert [row[3] for row in reader[1:]] == ["000123", "000000", "000124"]
    assert reader[1][4] == "正常中文项目"
    assert reader[2][4].startswith("'") and reader[2][4].endswith("/C calc'!A1")
    assert reader[3][4].startswith("'") and reader[3][4].endswith("+SUM(A1)")
    assert [row[5] for row in reader[1:]] == ["ok", "ok", "missing"]
    assert reader[-1][-1] == "false"


def test_xlsx_export_forces_text_cells_and_preserves_contract_business_key():
    payload = exports.issues_xlsx(_export_task(), _export_issues())
    workbook = load_workbook(io.BytesIO(payload))
    sheet = workbook.active
    header = [cell.value for cell in sheet[1]]
    assert header[:6] == ["task_id", "rule_code", "business_key", "project_code", "project_name", "project_name_status"]
    body = list(sheet.iter_rows(min_row=2))
    assert [row[2].value for row in body] == ["CONTRACT-P001", "000000", "P003"]
    assert [row[4].value for row in body] == ["正常中文项目", "=CMD|' /C calc'!A1", "\ufeff\t+SUM(A1)"]
    for row in body:
        for cell in row:
            if isinstance(cell.value, str):
                assert cell.data_type == "s"
    workbook.close()


def test_parent_cancellation_blocks_late_queued_rule_completion():
    _database, storage = _storage()
    item = _queued_task_rule(storage)
    storage.update_task(int(item["task_id"]), status="cancelled")
    assert storage.record_rule_result(
        int(item["id"]), status="VIOLATION", error_code="", violation_count=1,
        truncated=False, issues=[_issue()],
    ) is False
    assert _rows(storage, item["task_id"]) == []


def test_actual_second_row_database_failure_rolls_back_first_insert_and_outcome():
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    database, storage = _storage()
    item = _queued_task_rule(storage)
    with database.begin() as connection:
        connection.execute(text(
            "CREATE TRIGGER data_validation_fail_second_issue BEFORE INSERT ON data_validation_issues "
            "WHEN NEW.business_key = 'P002' BEGIN SELECT RAISE(ABORT, 'second detail failure'); END"
        ))
    with pytest.raises(IntegrityError, match="second detail failure"):
        storage.record_rule_result(
            int(item["id"]), status="VIOLATION", error_code="", violation_count=2,
            truncated=True, issues=[_issue(), _issue(business_key="P002")],
        )
    assert _rows(storage, item["task_id"]) == []
    assert storage.task_rules(int(item["task_id"]))[0]["status"] == "queued"
    assert storage.get_task(int(item["task_id"]))["truncated"] == 0


def test_invalid_result_types_and_fake_resolved_project_identity_are_rejected():
    _database, storage = _storage()
    item = _queued_task_rule(storage)
    for issue in [_issue(issue_kind="untrusted"), _issue(project_name_status="invented"),
                  _issue(project_name=None, project_name_status="ok")]:
        with pytest.raises(ValueError):
            storage.record_rule_result(
                int(item["id"]), status="VIOLATION", error_code="", violation_count=1,
                truncated=False, issues=[issue],
            )
    assert _rows(storage, item["task_id"]) == []


def test_missing_value_kind_survives_both_exports_without_looking_like_numeric_mismatch():
    task = _export_task()
    rows = [_issue(issue_kind="missing_value", message="金额缺失，未作数值比较"),
            _issue(issue_kind="numeric", message="数值不符")]
    csv_rows = list(csv.DictReader(io.StringIO(exports.issues_csv(task, rows).decode("utf-8"))))
    assert [row["issue_kind"] for row in csv_rows] == ["missing_value", "numeric"]
    workbook = load_workbook(io.BytesIO(exports.issues_xlsx(task, rows)))
    values = list(workbook.active.values)
    column = values[0].index("issue_kind")
    assert [row[column] for row in values[1:]] == ["missing_value", "numeric"]
    workbook.close()


def test_manifest_registry_and_migration_are_module_scoped_v10():
    manifest = json.loads((MODULE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] >= 10

    captured: dict[str, set[str]] = {}

    class Registry:
        def add(self, name, columns):
            captured[name] = set(columns)

    DataValidationModule().register_schema(Registry())
    assert {"project_code", "project_name", "project_name_status"} <= captured["data_validation_issues"]

    migration = (MODULE_DIR / "migrations" / "010_project_context.sql").read_text(encoding="utf-8")
    altered = [line.split("ALTER TABLE", 1)[1].strip().split(" ", 1)[0]
               for line in migration.splitlines() if line.strip().upper().startswith("ALTER TABLE")]
    assert altered == ["data_validation_issues"] * 4
    assert "issue_kind" in captured["data_validation_issues"]
    assert migration.count("legacy_unavailable") == 1
    assert "project_code TEXT" in migration and "project_name TEXT" in migration
