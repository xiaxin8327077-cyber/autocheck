import json
import shutil
import sqlite3
import subprocess

import pytest

from auto_check.modules.data_validation.candidate_preview import preview_definition, run_preview_cases
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.project_driver_samples import evaluate_project_case
from auto_check.modules.data_validation.query_samples import evaluate_case_with_kind
from auto_check.modules.data_validation.sql_guard import guard_generated_sql
from tests.modules.data_validation.test_frontend_multi_behavior import copy_web_modules
from tests.modules.data_validation.test_project_driver_binding import bind, definition as project_definition
from tests.modules.data_validation.test_related_sum import BASE, RELATED, DAY, definition


@pytest.mark.parametrize("driver", [None, 1, 2, 3])
@pytest.mark.parametrize("dialect", ["postgresql", "mysql"])
@pytest.mark.parametrize("policy", ["zero", "review"])
def test_explicit_exclude_compares_only_eligible_same_period_groups(driver, dialect, policy):
    rule = definition(dialect)
    rule["join"]["unmatched_policy"] = "exclude"
    rule["null_policy"] = policy
    columns = BASE + [{"column_name": "label", "data_type": "varchar"}]
    if driver:
        rule["project_driver"] = {"version": driver, "table_role": "base"}
        rule["project_context"] = {"mode": "base", "code_field": "owner_id", "name_field": "label", "confirmed": True}
    preview = preview_definition(rule, columns, RELATED)
    sql = preview["sql_preview"]
    assert "INNER JOIN" in sql and "LEFT JOIN" not in sql
    tests = run_preview_cases(preview)
    assert tests["passed_count"] and tests["failed_count"] == tests["not_run_count"] == 0
    rows = [
        ("absent", 12, [], None),
        ("old", 12, [("2001-01-01", 1, 1)], None),
        ("filtered", 12, [(DAY, 10, 0)], None),
        ("equal", 10, [(DAY, 5, 1), (DAY, 5, 1)], None),
        ("delta", 10, [(DAY, 5, 1)], "numeric"),
        ("null", 0, [(DAY, None, 1)], None if policy == "zero" else "missing_value"),
    ]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE owners(owner_id TEXT, asof TEXT, amount NUMERIC, active INTEGER, label TEXT)")
        db.execute("CREATE TABLE details(owner_ref TEXT, report_day TEXT, part NUMERIC, included INTEGER)")
        for key, total, parts, expected in rows:
            base = dict(owner_id=key, asof=DAY, amount=total, active=1, label=key)
            db.execute("INSERT INTO owners VALUES (:owner_id,:asof,:amount,:active,:label)", base)
            details = [dict(owner_ref=key, report_day=day, part=val, included=eligible)
                       for day, val, eligible in parts]
            db.executemany("INSERT INTO details VALUES (:owner_ref,:report_day,:part,:included)", details)
            if driver:
                observed = evaluate_project_case(rule, {"report_date": DAY, "project": base, "details": details})
            else:
                observed = evaluate_case_with_kind(rule, {"report_date": DAY, "base": base, "related": details})
            assert observed == (int(expected is not None), expected)
        hits = db.execute(sql, {**preview["sql_params"], "report_date": DAY}).fetchall()
    aliases = preview["definition"]["result_aliases"]
    assert {row[aliases["business_key"]]: row[aliases["issue_kind"]] for row in hits} == {
        key: expected for key, _, _, expected in rows if expected
    }


def test_project_binding_preserves_explicit_sum_exclusion():
    model = project_definition("project_snapshot", business_key="project_key", filters=[], expression={
        "left": "project_received", "op": "neq", "right_type": "field",
        "right_table": "related", "right": "funding_received",
    })
    model["join"] = {"table_name": "funding_rows", "on": [{"left": "project_key", "right": "funding_owner"}],
                     "report_date_field": "day", "right_aggregate": "sum", "unmatched_policy": "exclude"}
    assert bind(model)["definition"]["join"]["unmatched_policy"] == "exclude"


def test_generated_grouped_join_requires_exact_compilation_and_known_tables():
    rule = definition("postgresql")
    rule["join"]["unmatched_policy"] = "exclude"
    preview = preview_definition(rule, BASE, RELATED)
    cols = {col["column_name"] for col in [*BASE, *RELATED]}
    for sql, tables in [(preview["sql_preview"] + " ", {"owners", "details"}), (preview["sql_preview"], {"owners"})]:
        with pytest.raises(AppError, match="SQL_POLICY_DENIED"):
            guard_generated_sql("postgresql", sql, cols, tables, definition=preview["definition"])


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js 不可用")
def test_workbench_readiness_accepts_both_confirmed_aggregate_policies(tmp_path):
    copy_web_modules(tmp_path)
    rule = definition("postgresql")
    modules = (tmp_path / "state.mjs").as_uri()
    code = f"import {{ruleScopeIssues}} from {json.dumps(modules)}; const rule={json.dumps(rule)};" + """
        const blocked = ["exclude", "review", "unresolved"].map(policy => {
          rule.join.unmatched_policy = policy;
          return ruleScopeIssues(rule).some(message => message.includes("关联未匹配"));
        });
        console.log(JSON.stringify(blocked));
    """
    result = subprocess.run(["node", "--input-type=module", "-e", code], check=True, capture_output=True,
                            encoding="utf-8", timeout=15)
    assert json.loads(result.stdout) == [False, False, True]
