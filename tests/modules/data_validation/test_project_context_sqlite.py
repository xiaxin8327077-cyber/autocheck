import sqlite3

from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.project_context import project_row_status


def _definition(mode="lookup"):
    context = {
        "mode": mode, "code_field": "project_code", "name_field": "project_name", "confirmed": True,
    }
    if mode == "lookup":
        context.update({
            "table_name": "dim_project",
            "key": {"left": "project_code", "right": "project_code"},
            "date_field": "report_date",
            "unique_evidence": {"kind": "pk", "fields": ["project_code", "report_date"], "confirmed": True},
        })
    return {
        "rule_type": "field_compare", "dialect": "mysql", "table_name": "contract",
        "business_key": "contract_no", "report_date_field": "report_date",
        "violation_message": "金额异常", "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
        "project_context": context,
    }


def _seed(connection):
    connection.executescript("""
        CREATE TABLE contract (contract_no TEXT, project_code TEXT, project_name TEXT, amount REAL, report_date TEXT);
        CREATE TABLE dim_project (project_code TEXT, project_name TEXT, report_date TEXT);
        INSERT INTO contract VALUES ('C1','P1','项目一',10,'2026-09-30');
        INSERT INTO contract VALUES ('C2','P2',NULL,20,'2026-09-30');
        INSERT INTO contract VALUES ('C3','P3','重复甲',30,'2026-09-30');
        INSERT INTO contract VALUES ('C4','P4','',40,'2026-09-30');
        INSERT INTO contract VALUES ('C5','P5',NULL,50,'2026-09-30');
        INSERT INTO contract VALUES ('CX','PX','不违规',0,'2026-09-30');
        INSERT INTO dim_project VALUES ('P1','项目一','2026-09-30');
        INSERT INTO dim_project VALUES ('P3','重复甲','2026-09-30');
        INSERT INTO dim_project VALUES ('P3','重复乙','2026-09-30');
        INSERT INTO dim_project VALUES ('P4','','2026-09-30');
        INSERT INTO dim_project VALUES ('P5',NULL,'2026-09-30');
    """)


def _run(sql, params):
    connection = sqlite3.connect(":memory:")
    try:
        _seed(connection)
        cursor = connection.execute(sql, params)
        columns = tuple(item[0] for item in cursor.description or ())
        return columns, cursor.fetchall()
    finally:
        connection.close()


def test_sqlite_lookup_keeps_every_contract_row_and_marks_missing_duplicate():
    sql, params = compile_rule({"definition": _definition("lookup")})
    columns, rows = _run(sql, {**params, "report_date": "2026-09-30"})
    assert len(rows) == 5  # amount=0 的 CX 仍被业务谓词排除，其余一行不丢
    raw = [dict(zip(columns, row)) for row in rows]
    by_key = {item["business_key"]: item for item in raw}
    assert by_key["C1"]["project_code"] == "P1" and by_key["C1"]["project_name"] == "项目一"
    assert by_key["C1"]["project_match_count"] == 1
    assert by_key["C2"]["project_match_count"] == 0 and by_key["C2"]["project_name"] is None
    assert by_key["C3"]["project_match_count"] == 2 and by_key["C3"]["project_name"] is None
    assert by_key["C4"]["project_name"] == ""
    assert by_key["C5"]["project_name"] is None
    statuses = {
        key: project_row_status(mode="lookup", code=item["project_code"], name=item["project_name"],
                                match_count=item["project_match_count"])
        for key, item in by_key.items()
    }
    assert statuses["C1"] == "ok"
    assert statuses["C2"] == "missing_reference"
    assert statuses["C3"] == "duplicate"
    assert statuses["C4"] == "missing_null"
    assert statuses["C5"] == "missing_null"


def test_sqlite_base_context_projects_existing_columns_without_extra_table():
    sql, params = compile_rule({"definition": _definition("base")})
    columns, rows = _run(sql, {**params, "report_date": "2026-09-30"})
    assert " JOIN " not in sql.upper()
    assert len(rows) == 5
    raw = [dict(zip(columns, row)) for row in rows]
    assert {item["project_code"] for item in raw} == {"P1", "P2", "P3", "P4", "P5"}
