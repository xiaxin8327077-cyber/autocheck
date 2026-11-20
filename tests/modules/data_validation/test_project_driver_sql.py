import hashlib
import sqlite3
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.query_samples import evaluate_case_with_kind
from auto_check.modules.data_validation.result_aliases import build_result_aliases
from auto_check.modules.data_validation.sql_guard import guard_generated_sql


def cols(*items):
    return [{"column_name": name, "data_type": kind, "comment": label} for name, kind, label in items]


PROJECT = cols(("code", "varchar", "TCMP编号"), ("title", "varchar", "项目名称"), ("day", "date", "项目数据日期"),
               ("enabled", "int", "项目标志"), ("total", "numeric", "项目合计"))
DETAIL = cols(("owner", "varchar", "明细项目编号"), ("stamp", "date", "明细日期"), ("num", "varchar", "合同号"),
              ("amount", "numeric", "期末余额"), ("allowed", "int", "参与范围"))
DAY = "2026-11-01"


def detail_rule(dialect):
    return {"rule_type": "field_compare", "source_id": "src", "dialect": dialect, "table_name": "lines",
            "business_key": "num", "report_date_field": "stamp", "null_policy": "zero",
            "equality_policy": "allow_equal", "violation_message": "金额异常", "include_result_fields": True,
            "project_driver": {"version": 1, "table_role": "related"},
            "expression": {"left": "amount", "op": "lte", "right_type": "value", "right": 0},
            "join": {"table_name": "projects", "on": [{"left": "owner", "right": "code"}],
                     "relationship_confirmed": True, "unmatched_policy": "exclude", "report_date_field": "day"},
            "project_context": {"mode": "lookup", "code_field": "owner", "name_field": "title", "table_name": "projects",
                                "key": {"left": "owner", "right": "code"}, "date_field": "day", "confirmed": True,
                                "unique_evidence": {"kind": "pk", "fields": ["code", "day"], "confirmed": True}},
            "filters": [{"table": role, "field": col, "op": "eq", "value": 1, "confirmed": True}
                        for role, col in [("base", "allowed"), ("related", "enabled")]]}


def database():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE projects(code text,title text,day date,enabled integer,total numeric)")
    db.execute("CREATE TABLE lines(owner text,stamp date,num text,amount numeric,allowed integer)")
    db.executemany("INSERT INTO projects VALUES(?,?,?,?,?)", [
        (key, key + "名称", DAY, active, total) for key, active, total in [
            ("A", 1, -2), ("B", 1, 0), ("C", 1, 0), ("D", 1, 0), ("E", 0, 0),
            ("F", 1, 0), ("F", 1, 0), ("G", 1, 0), ("H", 1, 0)]])
    db.executemany("INSERT INTO lines VALUES(?,?,?,?,?)", [
        ("A", DAY, "a1", -1, 1), ("A", DAY, "a2", -1, 1), ("B", "2026-10-31", "old", 9, 1),
        ("C", DAY, None, None, 1), ("D", DAY, "skip", 0, 0), ("E", DAY, "e", 0, 1),
        ("F", DAY, "f1", 0, 1), ("F", DAY, "f2", 0, 1), ("G", DAY, "g", 1, 1), ("H", DAY, "h", 1, 1)])
    return db


def actual(rule, base, related, *, extra_projects=()):
    rule["result_aliases"] = build_result_aliases(rule, base, related)
    sql, params = compile_rule({"definition": rule})
    with database() as db:
        db.executemany("INSERT INTO projects VALUES(?,?,?,?,?)", extra_projects)
        def select(source, statement, values, **limits):
            cursor = db.execute(statement, values)
            return SimpleNamespace(columns=[entry[0] for entry in cursor.description], rows=cursor.fetchall(), truncated=False)
        metadata = SimpleNamespace(
            describe_table=lambda src, table: {"columns": PROJECT if table == "projects" else DETAIL}, execute_select=select)
        run = execute_version({"definition": rule, "sql_text": sql}, {"report_date": DAY}, metadata)
        assert run.status == "VIOLATION", run.error_code
        assert all("status" not in evidence for evidence in run.query_results)
        tampered = execute_version({"definition": rule, "sql_text": sql + " "}, {"report_date": DAY}, metadata)
        assert tampered.status == "ERROR"
    return sql, run


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_detail_project_driver_uses_real_rows_and_project_identity(dialect):
    rule = detail_rule(dialect)
    sql, run = actual(rule, DETAIL, PROJECT)
    assert "LEFT JOIN" in sql
    assert sorted((r["project_code"], r["business_key"] or "", r["issue_kind"], r["project_name_status"]) for r in run.rows) == [
        ("A", "a1", "numeric", "ok"), ("A", "a2", "numeric", "ok"),
        ("B", "", "missing_record", "ok"), ("C", "", "numeric", "ok"), ("F", "", "comparison", "duplicate")]
    assert all(r["project_name"] == r["project_code"] + "名称" for r in run.rows if r["project_code"] != "F")
    assert rule["result_aliases"]["data_date"] == "项目数据日期"
    assert rule["result_aliases"]["project_code"] == "TCMP编号"
    with pytest.raises(AppError):
        guard_generated_sql(dialect, sql, {"lines", "projects"})
    with pytest.raises(AppError):
        guard_generated_sql(dialect, sql.replace("LEFT JOIN", "INNER JOIN"), {"lines", "projects"}, definition=rule)
    with pytest.raises(AppError):
        guard_generated_sql(dialect, sql, {c["column_name"] for c in [*DETAIL, *PROJECT]}, {"lines"}, definition=rule)


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_sum_driver_excludes_filtered_projects_but_reports_true_absence(dialect):
    rule = detail_rule(dialect)
    rule.update(table_name="projects", business_key="code", report_date_field="day",
                project_driver={"version": 1, "table_role": "base"},
                project_context={"mode": "base", "code_field": "code", "name_field": "title", "confirmed": True},
                expression={"left": "total", "op": "neq", "right_type": "field", "right_table": "related", "right": "amount"})
    rule["join"].update(table_name="lines", on=[{"left": "code", "right": "owner"}], report_date_field="stamp",
                        right_aggregate="sum", unmatched_policy="review")
    for item in rule["filters"]:
        item["table"] = "base" if item["table"] == "related" else "related"
    _, run = actual(rule, PROJECT, DETAIL)
    assert sorted((r["project_code"], r["issue_kind"]) for r in run.rows) == [
        ("B", "missing_record"), ("F", "comparison"), ("G", "numeric"), ("H", "numeric")]


@pytest.mark.parametrize("grouped", [False, True])
def test_project_false_subrule_unary_and_grouped_unknowns_keep_matched_detail_grain(grouped):
    rule = detail_rule("postgresql")
    if grouped:
        rule.update(null_policy="review", expression={"logic": "any", "conditions": [
            {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
            {"left": "amount", "op": "lt", "right_type": "value", "right": 0}]})
    else:
        rule.update(null_policy="violate", expression={"left": "amount", "op": "is_null"})
    _, run = actual(rule, DETAIL, PROJECT)
    assert [r["issue_kind"] for r in run.rows if r["project_code"] == "C"] == [
        "missing_value" if grouped else "comparison"]
    assert [r["issue_kind"] for r in run.rows if r["project_code"] == "B"] == ["missing_record"]
    assert not [r for r in run.rows if r["project_code"] == "D"]


def test_project_only_driver_runs_once_per_valid_project_and_exposes_duplicate_source_keys():
    rule = detail_rule("mysql")
    rule.pop("join")
    rule.update(table_name="projects", business_key="code", report_date_field="day", filters=[],
                project_driver={"version": 1, "table_role": "base"},
                project_context={"mode": "base", "code_field": "code", "name_field": "title", "confirmed": True},
                expression={"left": "total", "op": "lt", "right_type": "value", "right": 0})
    sql, run = actual(rule, PROJECT, [])
    assert hashlib.sha256(sql.encode()).hexdigest() == "9b5f63fdd4c6be5417614d7b68d75932fbca73a8f92dacd5cbffb022dabaca8e"
    assert "LEFT JOIN" not in sql
    assert sorted((r["project_code"], r["issue_kind"], r["project_name_status"]) for r in run.rows) == [
        ("A", "numeric", "ok"), ("F", "comparison", "duplicate")]


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
@pytest.mark.parametrize("expression,policy,hit", [
    ({"left": "start_day", "op": "is_null"}, "violate", {None, "D"}),
    ({"left": "start_day", "op": "gt", "right_type": "field", "right": "end_day"}, "skip", {"D"}),
    ({"left": "total", "op": "lt", "right_type": "value", "right": 0}, "zero", {"D"}),
])
def test_new_project_rows_use_a_single_filtered_scan(dialect, expression, policy, hit):
    rule = detail_rule(dialect)
    rule.pop("join")
    rule.update(table_name="projects", business_key="code", report_date_field="day",
                filters=[{"table": "base", "field": "enabled", "op": "eq", "value": 1, "confirmed": True}],
                project_driver={"version": 2, "table_role": "base"}, null_policy=policy, expression=expression,
                project_context={"mode": "base", "code_field": "code", "name_field": "title", "confirmed": True})
    columns = PROJECT + cols(("start_day", "date", "项目起始日期"), ("end_day", "date", "预计结束日期"))
    rule["result_aliases"] = build_result_aliases(rule, columns)
    sql, params = compile_rule({"definition": rule})
    assert sql.upper().count("SELECT") == 1
    assert all(fragment not in sql.upper() for fragment in ("COUNT(", "JOIN ", "UNION", "GROUP BY", "HAVING"))
    assert not any(key.startswith("dv_") for key in params)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE projects(code text,title text,day date,enabled int,total numeric,start_day date,end_day date)")
        db.executemany("INSERT INTO projects VALUES(?,?,?,?,?,?,?)", [
            (None, "无编号", DAY, 1, 1, None, DAY), ("D", "同编号", DAY, 1, 1, None, DAY),
            ("D", "同编号", DAY, 1, -2, "2026-11-02", DAY), ("X", "范围外", DAY, 0, -1, None, DAY),
            ("X", "上期", "2026-10-31", 1, -1, None, DAY)])
        def select(_src, statement, values, **_limits):
            cursor = db.execute(statement, values)
            names = [col[0] for col in cursor.description]
            assert set(names) == {"TCMP编号", "项目名称", "项目数据日期", "异常说明",
                                  *[f["comment"] for f in columns if f["column_name"] in (expression["left"], expression.get("right"))]}
            return SimpleNamespace(columns=names, rows=cursor.fetchall(), truncated=False)
        metadata = SimpleNamespace(describe_table=lambda *_: {"columns": columns}, execute_select=select)
        result = execute_version({"definition": rule, "sql_text": sql}, {"report_date": DAY}, metadata)
    assert result.violation_count == len(hit) and {row["business_key"] for row in result.rows} == hit
    assert {row["project_code"] for row in result.rows} == hit
    assert all(row["violation_message"] == rule["violation_message"] for row in result.rows)
    normal = {"code": None, "title": "无编号", "day": DAY, "enabled": 1, "total": 1, "start_day": DAY, "end_day": DAY}
    assert evaluate_case_with_kind(rule, {"report_date": DAY, "project": normal, "details": []}) == (0, None)


def test_blank_project_keys_are_source_issues_only_within_the_project_scope():
    rule = detail_rule("postgresql")
    _, run = actual(rule, DETAIL, PROJECT, extra_projects=[
        (None, "无编号", DAY, 1, 0), ("", "空编号", DAY, 1, 0),
        ("  ", "空格编号", DAY, 1, 0), (" ", "范围外", DAY, 0, 0)])
    issues = [row for row in run.rows if row["project_name_status"] == "missing_code"]
    assert {row["project_code"] for row in issues} == {None, "", "  "}
    assert len(issues) == 3
    assert all(row["issue_kind"] == "comparison" and "缺少项目编号" in row["violation_message"] for row in issues)


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_v2_detail_keeps_each_real_row_and_missing_details_without_project_key_diagnostics(dialect):
    rule = detail_rule(dialect)
    rule["project_driver"]["version"] = 2
    sql, run = actual(rule, DETAIL, PROJECT, extra_projects=[(None, "未匹配项目", DAY, 1, 0)])
    assert all(word not in sql for word in ("COUNT(", "UNION", "GROUP BY", "HAVING", "dv_duplicate_project", "dv_missing_project_code"))
    assert "project_match_count" not in rule["result_aliases"]
    assert sorted((r["business_key"], r["issue_kind"]) for r in run.rows if r["project_code"] == "F") == [
        ("f1", "numeric"), ("f1", "numeric"), ("f2", "numeric"), ("f2", "numeric")]
    assert {r["project_code"] for r in run.rows if r["issue_kind"] == "missing_record"} == {"B", None}
    assert not any(r["project_code"] == "D" for r in run.rows)


@pytest.mark.parametrize("policy", ["zero", "review"])
def test_v2_sum_aggregates_details_once_before_comparing_each_project_row(policy):
    rule = detail_rule("postgresql")
    rule.update(table_name="projects", business_key="code", report_date_field="day", null_policy=policy,
                project_driver={"version": 2, "table_role": "base"},
                project_context={"mode": "base", "code_field": "code", "name_field": "title", "confirmed": True},
                expression={"left": "total", "op": "neq", "right_type": "field", "right_table": "related", "right": "amount"})
    rule["join"].update(table_name="lines", on=[{"left": "code", "right": "owner"}],
                        report_date_field="stamp", right_aggregate="sum", unmatched_policy="review")
    for item in rule["filters"]:
        item["table"] = "base" if item["table"] == "related" else "related"
    sql, run = actual(rule, PROJECT, DETAIL, extra_projects=[("A", "A名称", DAY, 1, -2), ("G", "G名称", DAY, 1, 0)])
    assert "UNION" not in sql and sql.count("GROUP BY") == 1 and "HAVING" not in sql
    hits = [(r["project_code"], r["issue_kind"]) for r in run.rows]
    assert hits.count(("G", "numeric")) == 2 and ("H", "numeric") in hits
    assert ("B", "missing_record") in hits
    assert (("C", "missing_value") in hits) == (policy == "review")
    assert not any(key in ("A", "D", "F") for key, _ in hits)


def test_sample_counts_match_real_sql_for_each_project_including_multirow_and_filtered_details():
    rule = detail_rule("postgresql")
    _, run = actual(rule, DETAIL, PROJECT)
    with database() as db:
        db.row_factory = sqlite3.Row
        for project in db.execute("SELECT * FROM projects WHERE code <> 'F'"):
            details = db.execute("SELECT * FROM lines WHERE owner = ?", (project["code"],))
            case = {"report_date": DAY, "project": dict(project), "details": [dict(d) for d in details]}
            observed = [r for r in run.rows if r["project_code"] == project["code"]]
            assert evaluate_case_with_kind(rule, case) == (len(observed), observed[0]["issue_kind"] if observed else None)


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_project_amount_compared_to_each_detail_preserves_two_identical_violations(dialect):
    rule = detail_rule(dialect)
    rule.update(table_name="projects", business_key="code", report_date_field="day",
                project_driver={"version": 1, "table_role": "base"},
                project_context={"mode": "base", "code_field": "code", "name_field": "title", "confirmed": True},
                expression={"left": "total", "op": "neq", "right_type": "field", "right_table": "related", "right": "amount"})
    rule["join"].update(table_name="lines", on=[{"left": "code", "right": "owner"}], report_date_field="stamp")
    for item in rule["filters"]:
        item["table"] = "base" if item["table"] == "related" else "related"
    _, run = actual(rule, PROJECT, DETAIL)
    assert sorted((r["project_code"], r["issue_kind"]) for r in run.rows) == [
        ("A", "numeric"), ("A", "numeric"), ("B", "missing_record"), ("F", "comparison"),
        ("G", "numeric"), ("H", "numeric")]
    assert rule["result_aliases"]["comparison_value"] == "期末余额"
    with database() as db:
        db.row_factory = sqlite3.Row
        for project in db.execute("SELECT * FROM projects WHERE code <> 'F'"):
            details = db.execute("SELECT * FROM lines WHERE owner = ?", (project["code"],))
            case = {"report_date": DAY, "project": dict(project), "details": [dict(d) for d in details]}
            matched = [r for r in run.rows if r["project_code"] == project["code"]]
            assert evaluate_case_with_kind(rule, case) == (len(matched), matched[0]["issue_kind"] if matched else None)
