from copy import deepcopy
import sqlite3
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.candidate_preview import preview_definition, run_preview_cases
from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.query_samples import evaluate_case_with_kind
from auto_check.modules.data_validation.query_spec import apply_numeric_null_policy, query_ready, validate_spec_against_columns


def cols(names):
    return [{"column_name": name, "data_type": kind} for name, kind in names]


BASE = cols([("owner_id", "varchar"), ("asof", "date"), ("amount", "numeric"), ("active", "integer")])
RELATED = cols([("owner_ref", "varchar"), ("report_day", "date"), ("part", "numeric"), ("included", "integer")])
DAY = "2026-11-01"


def definition(dialect):
    return {
        "name": "总额复核", "rule_type": "field_compare", "dialect": dialect, "table_name": "owners",
        "business_key": "owner_id", "report_date_field": "asof", "violation_message": "合计不符",
        "equality_policy": "allow_equal", "null_policy": "review", "include_result_fields": True,
        "expression": {"left": "amount", "op": "neq", "right_type": "field", "right_table": "related", "right": "part"},
        "filters": [{"table": table, "field": name, "op": "eq", "value": 1, "confirmed": True}
                    for table, name in [("base", "active"), ("related", "included")]],
        "join": {"table_name": "details", "on": [{"left": "owner_id", "right": "owner_ref"}],
                 "report_date_field": "report_day", "relationship_confirmed": True,
                 "unmatched_policy": "review", "right_aggregate": "sum"},
    }


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_related_sum_counts_all_same_period_details_and_reports_incomplete_evidence(dialect):
    rule = definition(dialect)
    preview = preview_definition(rule, BASE, RELATED)
    assert query_ready(rule)
    assert preview["content_sha256"] == preview_definition(preview["definition"], BASE, RELATED)["content_sha256"]
    tested = run_preview_cases(preview)
    assert tested["passed_count"] >= 5 and tested["not_run_count"] == tested["failed_count"] == 0
    base_rows = [(key, DAY, amount, active) for key, amount, active in [
        ("balanced", 8, 1), ("mismatch", 8, 1), ("empty", 0, 1), ("partial", 2, 1),
        ("unknown", None, 1), ("inactive", 8, 0), ("zero", 0, 1), ("all_null", 0, 1)]]
    detail_rows = [(key, day, amount, state) for key, day, amount, state in [
        ("balanced", DAY, 4, 1), ("balanced", DAY, 4, 1), ("balanced", "2025-11-01", 99, 1),
        ("balanced", DAY, 1, 0), ("mismatch", DAY, 2, 1), ("mismatch", DAY, 4, 1),
        ("partial", DAY, 2, 1), ("partial", DAY, None, 1), ("unknown", DAY, 7, 1),
        ("zero", DAY, -2, 1), ("zero", DAY, 2, 1), ("all_null", DAY, None, 1)]]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE owners(owner_id text, asof date, amount numeric, active integer)")
        db.execute("CREATE TABLE details(owner_ref text, report_day date, part numeric, included integer)")
        db.executemany("INSERT INTO owners VALUES (?,?,?,?)", base_rows)
        db.executemany("INSERT INTO details VALUES (?,?,?,?)", detail_rows)
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": DAY}).fetchall()
        def execute_sql(source_id, sql, params, **limits):
            cursor = db.execute(sql, params)
            return SimpleNamespace(columns=[item[0] for item in cursor.description], rows=cursor.fetchall(), truncated=False)
        metadata = SimpleNamespace(
            describe_table=lambda source_id, table: {"columns": {"owners": BASE, "details": RELATED}[table]},
            execute_select=execute_sql,
        )
        run = execute_version({"definition": preview["definition"], "sql_text": preview["sql_preview"]},
                              {"report_date": DAY}, metadata)
    expected = {"mismatch": ("numeric", 8, 6), "empty": ("missing_value", 0, None),
                "partial": ("missing_value", 2, None), "unknown": ("missing_value", None, 7),
                "all_null": ("missing_value", 0, None)}
    assert len(rows) == len(expected)
    assert run.status == "VIOLATION" and run.violation_count == len(expected)
    assert {r["business_key"]: r["issue_kind"] for r in run.rows} == {k: v[0] for k, v in expected.items()}
    assert {r["owner_id"]: (r["异常类型"], r["amount"], r["part"]) for r in rows} == expected
    assert all(r["asof"] == DAY for r in rows)
    for key, date, amount, active in base_rows:
        nested = {"report_date": DAY, "base": dict(owner_id=key, asof=date, amount=amount, active=active),
                  "related": [dict(owner_ref=k, report_day=d, part=v, included=i) for k, d, v, i in detail_rows]}
        assert evaluate_case_with_kind(rule, nested) == ((1, expected[key][0]) if key in expected else (0, None))


def test_aggregate_rejects_unsupported_shapes_and_never_inherits_input_null_to_zero():
    rule = definition("mysql")
    columns = [{**column, "logic": "空值视为0"} for column in BASE]
    rebound = apply_numeric_null_policy(rule, columns, RELATED)
    assert rebound["null_handling"] == {"left": "review", "right": "review"}
    for field, value in [("right_aggregate", "avg"), ("unmatched_policy", "exclude")]:
        altered = deepcopy(rule)
        altered["join"][field] = value
        with pytest.raises(AppError):
            compile_rule({"definition": altered})
    for changes in [{"right_table": "base"}, {"op": "is_null"}, {"op": "eq"}]:
        altered = deepcopy(rule)
        altered["expression"].update(changes)
        with pytest.raises(AppError):
            compile_rule({"definition": altered})
    non_numeric = [{**column, "data_type": "varchar"} if column["column_name"] == "part" else column for column in RELATED]
    with pytest.raises(AppError):
        validate_spec_against_columns(rule, BASE, non_numeric)


def test_sum_spec_preserves_exact_decimal_comparison_and_has_distinct_version_hash():
    rule = definition("postgresql")
    cases = {"report_date": DAY, "base": dict(owner_id="x", asof=DAY, amount=0.3, active=1),
             "related": [dict(owner_ref="x", report_day=DAY, part=v, included=1) for v in [0.1, 0.2]]}
    assert evaluate_case_with_kind(rule, cases) == (0, None)
    legacy = deepcopy(rule)
    del legacy["join"]["right_aggregate"]
    legacy["join"]["unmatched_policy"] = "exclude"
    assert evaluate_case_with_kind(legacy, cases) == (1, "numeric")
    assert preview_definition(legacy, BASE, RELATED)["content_sha256"] != preview_definition(rule, BASE, RELATED)["content_sha256"]
    rule["join"]["relationship_confirmed"] = False
    assert not query_ready(rule)


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_explicit_zero_sum_treats_null_amounts_as_zero_but_keeps_absent_details_for_review(dialect):
    rule = definition(dialect)
    rule["null_policy"] = "zero"
    preview = preview_definition(rule, BASE, RELATED)
    tested = run_preview_cases(preview)
    assert tested["failed_count"] == tested["not_run_count"] == 0
    cases = [
        (None, [None], (0, None)),
        (0, [None, 0], (0, None)),
        (3, [None, 3], (0, None)),
        (None, [3], (1, "numeric")),
        (3, [None], (1, "numeric")),
        (None, [], (1, "missing_value")),
        (0, [], (1, "missing_value")),
    ]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE owners(owner_id text, asof date, amount numeric, active integer)")
        db.execute("CREATE TABLE details(owner_ref text, report_day date, part numeric, included integer)")
        for number, (amount, parts, expected) in enumerate(cases):
            key = str(number)
            db.execute("INSERT INTO owners VALUES (?,?,?,1)", (key, DAY, amount))
            db.executemany("INSERT INTO details VALUES (?,?,?,1)", [(key, DAY, value) for value in parts])
            nested = {"report_date": DAY, "base": dict(owner_id=key, asof=DAY, amount=amount, active=1),
                      "related": [dict(owner_ref=key, report_day=DAY, part=value, included=1) for value in parts]}
            assert evaluate_case_with_kind(rule, nested) == expected
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": DAY}).fetchall()
    aliases = preview["definition"]["result_aliases"]
    assert {row[aliases["business_key"]]: row[aliases["issue_kind"]] for row in rows} == {
        str(number): expected[1] for number, (_, _, expected) in enumerate(cases) if expected[0]}
    assert preview["content_sha256"] == preview_definition(preview["definition"], BASE, RELATED)["content_sha256"]
