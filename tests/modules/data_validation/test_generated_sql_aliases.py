import csv
import io
import sqlite3
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.candidate_preview import preview_definition
from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.exports import issues_csv
from auto_check.modules.data_validation.issue_query_results import collect_row, output_projection
from auto_check.app.data_source_platform import _bind_named_params, ensure_readonly_sql
from tests.modules.data_validation.support import Metadata, loan_definition, service, user
from tests.modules.data_validation.test_execution_result_details import registered
from tests.modules.data_validation.test_related_sum import BASE, DAY, RELATED, definition


def driver(db, columns):
    def execute(_source, sql, params, **_limits):
        cursor = db.execute(sql, params)
        return SimpleNamespace(columns=[c[0] for c in cursor.description], rows=cursor.fetchall(), truncated=False)
    return SimpleNamespace(describe_table=lambda _s, t: {"columns": columns[t]}, execute_select=execute)


@pytest.mark.parametrize("dialect,quote", [("mysql", chr(96)), ("postgresql", '"')])
def test_generated_aliases_execute_snapshot_and_export_with_source_labels(dialect, quote):
    label = '金额' + quote + '本期'
    base = [{**col, "comment": {"owner_id": "账簿编号", "asof": "业务日期", "amount": label}.get(col["column_name"], "")}
            for col in BASE]
    related = [{**col, "comment": label if col["column_name"] == "part" else ""} for col in RELATED]
    rule = {**definition(dialect), "source_id": "src"}
    preview = preview_definition(rule, base, related)
    sql = preview["sql_preview"]
    assert 'AS ' + quote + label.replace(quote, quote * 2) + quote in sql
    assert compile_rule({"definition": preview["definition"]}) == (sql, preview["sql_params"])
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE owners(owner_id,asof,amount,active)")
        db.execute("CREATE TABLE details(owner_ref,report_day,part,included)")
        db.execute("INSERT INTO owners VALUES('001',?,0,1)", [DAY])
        metadata = driver(db, {"owners": base, "details": related})
        _, rules = service(metadata=metadata)
        rid = registered(rules.storage, preview["definition"], sql)
        task = rules.start_task(user(), {"rule_ids": [rid], "report_period": DAY})
        issue, = rules.list_task_issues(user(), task["id"])["items"]
    assert issue["business_key"] == "001" and issue["issue_kind"] == "missing_value"
    values = issue["query_result"]["values"]
    columns = issue["query_result"]["columns"]
    compared = next(c["name"] for c in columns if c.get("source_field") == "part")
    assert compared != label and label in compared
    assert (values[label], values[compared], values["业务日期"], values["账簿编号"]) == (0, None, DAY, "001")
    assert values["异常类型"] == "missing_value" and values["关联记录数"] == 0
    assert not set(values) & {"issue_kind", "business_key", "related_count", "checked_value"}
    assert {c["name"] for c in columns} == {c["label"] for c in columns} == set(values)
    row, = csv.DictReader(io.StringIO(rules.export_issues(user(), task["id"], "csv")["content"].decode()))
    assert row[label] == "0" and row[compared] == "NULL"
    assert row["校验字段"] == f"{label}（amount）"
    assert row["比较字段"] == f"{compared}（part）"
    assert {c["role"]: c["name"] for c in columns if "role" in c} == {
        "checked_value": label, "comparison_value": compared}


def test_compound_projection_uses_physical_fallback_and_preserves_legacy_sql():
    rule = {**definition("mysql"), "null_policy": "skip", "join": None, "filters": [],
            "expression": {"logic": "any", "conditions": [
                {"left": "amount", "op": "lt", "right_type": "value", "right": 0},
                {"left": "amount", "op": "is_null"}]}}
    old_sql, _ = compile_rule({"definition": rule})
    assert preview_definition(rule, BASE, preserve_result_fields=True)["sql_preview"] == old_sql
    current = preview_definition(rule, BASE)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE owners(owner_id,asof,amount,active)")
        db.execute("INSERT INTO owners VALUES('001',?,NULL,1)", [DAY])
        meta = driver(db, {"owners": BASE})
        for definition_, sql, names in [(rule, old_sql, ("business_key", "checked_value", "issue_kind")),
                                       (current["definition"], current["sql_preview"], ("owner_id", "amount", "异常类型"))]:
            run = execute_version({"definition": definition_, "sql_text": sql}, {"report_date": DAY}, meta)
            assert run.status == "VIOLATION"
            values, = [r["values"] for r in run.query_results]
            assert (values[names[0]], values[names[1]], values[names[2]]) == ("001", None, "comparison")


def test_new_manual_unique_rule_derives_every_alias_from_source_and_rejects_client_labels():
    meta = Metadata()
    _, rules = service(metadata=meta)
    rule = loan_definition(rule_type="unique", keys=["issue_date", "project_code"],
                           result_aliases={"business_key": "伪造表头"})
    saved = rules.save_draft(user(), rule)
    version = rules.storage.latest_version(saved["id"])
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE loan(project_code,issue_date)")
        db.executemany("INSERT INTO loan VALUES (?,?)", [("A", "2026-11-01")] * 2)
        cursor = db.execute(version["sql_text"])
        assert [c[0] for c in cursor.description] == ["发放日", "贷款业务编号", "异常说明"]
        assert cursor.fetchone()[:2] == ("2026-11-01", "A")


@pytest.mark.parametrize("label", ["备注:code", "备注; ALTER", "备注--说明"])
def test_platform_sensitive_metadata_uses_physical_alias_without_changing_bindings(label):
    base = [{**col, "comment": label if col["column_name"] == "amount" else ""} for col in BASE]
    preview = preview_definition(definition("mysql"), base, RELATED)
    assert preview["definition"]["result_aliases"]["checked_value"] == "amount"
    ensure_readonly_sql(preview["sql_preview"])
    _bind_named_params(preview["sql_preview"], preview["sql_params"])


def test_truncated_homonymous_labels_are_distinct_in_postgres():
    caption = "期末实际持有份额" * 6
    base = [{**col, "comment": caption} for col in BASE]
    related = [{**col, "comment": caption} for col in RELATED]
    aliases = preview_definition(definition("postgresql"), base, related)["definition"]["result_aliases"]
    assert all(len(name.encode()) <= 63 for name in aliases.values())
    assert len(aliases) == len(set(aliases.values()))


def test_new_version_cannot_run_persisted_sql_with_a_different_output_contract():
    rule = {**definition("mysql"), "join": None, "filters": [], "null_policy": "skip",
            "expression": {"left": "amount", "op": "lt", "right_type": "value", "right": 0}}
    preview = preview_definition(rule, BASE)
    old_sql, _ = compile_rule({"definition": rule})
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE owners(owner_id,asof,amount,active)")
        run = execute_version({"definition": preview["definition"], "sql_text": old_sql},
                              {"report_date": DAY}, driver(db, {"owners": BASE}))
    assert run.error_code == "MAPPING_DRIFT"


def test_project_roles_remain_available_when_the_business_key_is_the_project_code():
    base = [{"column_name": name, "comment": label, "data_type": kind} for name, label, kind in (
        ("id", "项目编号", "varchar"), ("title", "项目名称", "varchar"), ("d", "数据日期", "date"), ("n", "金额", "numeric"))]
    rule = {**loan_definition(), "business_key": "id", "report_date_field": "d",
            "project_context": {"mode": "base", "code_field": "id", "name_field": "title", "confirmed": True},
            "expression": {"left": "n", "op": "is_null"}, "null_policy": "violate"}
    preview = preview_definition(rule, base)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE loan(id,title,d,n)")
        db.execute("INSERT INTO loan VALUES('0001','产品甲',?,NULL)", [DAY])
        run = execute_version({"definition": preview["definition"], "sql_text": preview["sql_preview"]},
                              {"report_date": DAY}, driver(db, {"loan": base}))
    row, = run.rows
    assert (row["business_key"], row["project_code"], row["project_name"], row["project_name_status"]) == (
        "0001", "0001", "产品甲", "ok")
    values = run.query_results[0]["values"]
    assert values["项目编号"] == values["项目编号（项目编号）"] == "0001"
    assert values["项目名称"] == "产品甲" and values["金额"] is None


def test_mixed_export_resolves_roles_per_row_and_preserves_custom_aliases():
    modern = {"columns": [{"name": "余额", "label": "余额", "source_field": "amount", "role": "checked_value"}],
              "values": {"余额": 0}}
    old = {"columns": [{"name": "checked_value", "label": "checked_value", "source_field": "qty"}],
           "values": {"checked_value": None}}
    sql = 'SELECT item AS "校验字段", units AS comparison_value FROM inventory'
    columns, status = output_projection({"table_name": "inventory", "rule_type": "custom_sql"}, sql, False,
                                       ["校验字段", "comparison_value"], [], [])
    assert not any("role" in c for c in columns)
    custom = collect_row(columns, status, {"校验字段": "直接选取值", "comparison_value": 17})
    export = issues_csv({"id": 1}, [{"query_result": r} for r in (modern, old, custom)])
    first, second, last = csv.DictReader(io.StringIO(export.decode()))
    assert first["校验字段"] == "余额（amount）" and first["余额"] == "0"
    assert second["校验字段"] == "checked_value（qty）" and second["checked_value"] == "NULL"
    assert last["校验字段"] == "" and last["sql.校验字段"] == "直接选取值"
    assert last["比较字段"] == "comparison_value（units）" and last["comparison_value"] == "17"
