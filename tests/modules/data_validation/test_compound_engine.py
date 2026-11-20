from copy import deepcopy
from itertools import product
import sqlite3
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.query_samples import default_cases, evaluate_case_with_kind
from auto_check.modules.data_validation.query_spec import (
    apply_numeric_null_policy, canonicalize_definition, query_ready, referenced_columns, validate_spec_against_columns,
)


DAY = "2026-10-31"
BASE = [{"column_name": name, "data_type": kind} for name, kind in [
    ("id", "integer"), ("asof", "date"), ("kind", "varchar"), ("nav", "numeric"), ("amount", "numeric"),
]]
RELATED = [{"column_name": name, "data_type": kind} for name, kind in [
    ("owner", "integer"), ("asof", "date"), ("lower_bound", "numeric"), ("upper_bound", "numeric"),
]]


def constant(op, value, left="nav"):
    return {"left": left, "op": op, "right_type": "value", "right": value}


def rule(dialect="mysql", *, logic="any", conditions=None, policy="skip"):
    return {
        "name": "区间核查", "table_name": "projects", "rule_type": "field_compare",
        "business_key": "id", "report_date_field": "asof", "include_result_fields": True,
        "dialect": dialect, "null_policy": policy, "equality_policy": "allow_equal",
        "violation_message": "区间异常", "expression": {"logic": logic,
            "conditions": conditions if conditions is not None else [constant("gt", 1), constant("lt", 0)]},
        "filters": [{"table": "base", "field": "kind", "op": "eq", "value": "非净值型", "confirmed": True}],
    }


def run_sql(definition, base, related=()):
    sql, params = compile_rule({"definition": definition})
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE projects (id integer, asof date, kind text, nav numeric, amount numeric)")
        db.execute("CREATE TABLE bounds (owner integer, asof date, lower_bound numeric, upper_bound numeric)")
        db.executemany("INSERT INTO projects VALUES (?,?,?,?,?)", base)
        db.executemany("INSERT INTO bounds VALUES (?,?,?,?)", related)
        return [dict(row) for row in db.execute(sql, {**params, "report_date": DAY})]


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_nav_bounds_and_scope_match_sql_and_samples(dialect):
    spec = rule(dialect)
    assert query_ready(spec)
    validate_spec_against_columns(spec, BASE)
    sql, params = compile_rule({"definition": spec})
    assert "非净值型" not in sql
    assert params["right_value_1"] == 1 and params["right_value_2"] == 0
    base = [(i, DAY, "非净值型", v, None) for i, v in enumerate([-0.01, 0, 0.5, 1, 1.01, None])]
    base.extend([(6, DAY, "净值型", 2, None), (7, "2026-10-30", "非净值型", -1, None)])
    rows = run_sql(spec, base)
    assert [(r["business_key"], r["checked_value"]) for r in rows] == [(0, -0.01), (4, 1.01)]
    cases = default_cases(spec, BASE)
    assert {(c["row"]["base"]["nav"], c["expected_count"]) for c in cases} >= {
        (0, 0), (1, 0), (0.5, 0), (-1, 1), (2, 1), (None, 0)}
    for row_id, day, kind, nav, _ in base:
        sample = {"report_date": DAY, "base": {"asof": day, "nav": nav, "kind": kind}, "related": []}
        assert evaluate_case_with_kind(spec, sample)[0] == (row_id in (0, 4))


@pytest.mark.parametrize("logic,policy,expected", [
    ("any", "review", ["numeric", "missing_value", "numeric", None]),
    ("all", "review", ["missing_value", None, "numeric", None]),
    ("any", "zero", ["numeric", None, "numeric", None]),
    ("all", "zero", [None, None, "numeric", None]),
    ("any", "skip", ["comparison", None, "comparison", None]),
    ("all", "skip", [None, None, "comparison", None]),
])
def test_group_null_truth_table_and_definite_hit_precedence(logic, policy, expected):
    spec = rule(logic=logic, policy=policy, conditions=[constant("gt", 1), constant("gt", 0, "amount")])
    base = [(i, DAY, "非净值型", nav, amount) for i, (nav, amount) in enumerate([(2, None), (None, 0), (2, 1), (1, 0)])]
    rows = run_sql(spec, base)
    assert {r["business_key"]: r["issue_kind"] for r in rows} == {i: k for i, k in enumerate(expected) if k}
    for row_id, day, kind, nav, amount in base:
        sample = {"base": dict(asof=day, kind=kind, nav=nav, amount=amount), "related": [], "report_date": DAY}
        assert evaluate_case_with_kind(spec, sample) == (int(bool(expected[row_id])), expected[row_id])


def test_unary_member_controls_its_own_null_check_and_binary_policy_is_inferred():
    spec = rule(conditions=[{"left": "nav", "op": "is_null"}, constant("lt", 0)])
    inferred = apply_numeric_null_policy(spec, BASE, request_text="净值为空或小于零")
    assert inferred["null_policy"] == "review"
    base = [(0, DAY, "非净值型", None, None), (1, DAY, "非净值型", 0, None)]
    assert [r["business_key"] for r in run_sql(inferred, base)] == [0]
    value_only = apply_numeric_null_policy(rule(), BASE, request_text="净值不得大于1或小于0")
    assert value_only["null_policy"] == "zero"
    conflict = rule(conditions=[constant("gt", 0), {"left": "nav", "op": "lt", "right": "amount"}])
    unresolved = apply_numeric_null_policy(conflict, BASE, request_text="净值不得大于0或小于金额")
    assert unresolved["null_policy"] == "unresolved" and not query_ready(unresolved)


def test_all_conditions_require_one_matching_related_row_and_drift_fails_closed():
    conditions = [{"left": "nav", "op": op, "right_table": "related", "right": field} for op, field in [
        ("gt", "lower_bound"), ("lt", "upper_bound")]]
    spec = rule(logic="all", conditions=conditions, policy="review")
    spec["join"] = {"table_name": "bounds", "on": [{"left": "id", "right": "owner"}],
                    "report_date_field": "asof", "unmatched_policy": "exclude", "relationship_confirmed": True}
    validate_spec_against_columns(spec, BASE, RELATED)
    assert set(referenced_columns(spec)["related"]) == {"owner", "asof", "lower_bound", "upper_bound"}
    base = [(i, DAY, "非净值型", 0.5, None) for i in range(5)]
    related = [(0, DAY, 0, 0), (0, DAY, 1, 1), (1, DAY, 0, 1), (1, DAY, 0, 1),
               (2, DAY, None, 1), (2, DAY, 0, 1), (3, DAY, 0, None), (4, "2026-09-30", 0, 1)]
    expected = {1: "numeric", 2: "numeric", 3: "missing_value"}
    rows = run_sql(spec, base, related)
    assert [(r["business_key"], r["issue_kind"]) for r in rows] == list(expected.items())
    for row_id, day, kind, nav, _ in base:
        sample = {"base": dict(id=row_id, asof=day, kind=kind, nav=nav),
                  "related": [dict(owner=o, asof=d, lower_bound=l, upper_bound=u) for o, d, l, u in related],
                  "report_date": DAY}
        assert evaluate_case_with_kind(spec, sample) == (int(row_id in expected), expected.get(row_id))
    metadata = SimpleNamespace(describe_table=lambda source, table: {"columns": BASE if table == "projects" else RELATED[:-1]})
    assert execute_version({"definition": spec}, {"report_date": DAY}, metadata).error_code == "MAPPING_DRIFT"
    spec["join"]["right_aggregate"] = "sum"
    spec["join"]["unmatched_policy"] = "review"
    with pytest.raises(AppError):
        compile_rule({"definition": spec})


@pytest.mark.parametrize("change", [
    {"logic": "or"}, {"conditions": []}, {"conditions": [constant("lt", 0)]},
    {"conditions": [constant("lt", 0)] * 9}, {"left": "nav"}, {"left": "nav", "op": "is_null"},
    {"conditions": [constant("gt", 1), {"logic": "any", "conditions": [constant("gt", 0)]}]},
    {"conditions": [constant("gt", 1), constant("lt", float("nan"))]},
    {"conditions": [constant("gt", 1), constant("lt", "x")]},
    {"conditions": [constant("gt", 1), {"left": "nav", "op": "is_null", "right": "amount"}]},
    {"conditions": [constant("gt", 1), {"left": "nav", "op": "lt", "right": "limit", "right_table": "related"}]},
])
def test_invalid_member_or_connector_never_executes_a_reduced_group(change):
    spec = rule()
    spec["expression"].update(deepcopy(change))
    assert not query_ready(spec)
    with pytest.raises(AppError):
        compile_rule({"definition": spec})


def test_canonicalization_cannot_replace_a_group_with_an_outer_unary_predicate():
    spec = rule()
    spec["expression"].update(left="nav", op="is_null")
    with pytest.raises(AppError):
        canonicalize_definition(spec)


@pytest.mark.parametrize("logic", ["any", "all"])
@pytest.mark.parametrize("policy,handling", [
    ("skip", {}), ("zero", {"left": "zero", "right": "zero"}), ("review", {}),
    ("review", {"left": "zero", "right": "review"}), ("review", {"left": "review", "right": "zero"}),
])
def test_mixed_base_related_and_constant_members_match_sql_for_nulls_and_repeated_rows(logic, policy, handling):
    spec = rule(logic=logic, policy=policy, conditions=[
        {"left": "nav", "op": "gt", "right_table": "related", "right": "lower_bound"},
        {"left": "nav", "op": "lte", "right": "amount"}, constant("neq", 0, "amount"),
        {"left": "amount", "op": "is_not_null"},
    ])
    if handling:
        spec["null_handling"] = handling
    spec["join"] = {"table_name": "bounds", "on": [{"left": "id", "right": "owner"}],
                    "report_date_field": "asof", "unmatched_policy": "exclude", "relationship_confirmed": True}
    expected = {}
    base = []
    related = []
    for i, (nav, amount, first, second) in enumerate(product([None, -1, 0, 1], repeat=4)):
        base.append((i, DAY, "非净值型", nav, amount))
        related.extend([(i, DAY, first, 0), (i, DAY, second, 0)])
        sample = {"report_date": DAY, "base": dict(id=i, asof=DAY, kind="非净值型", nav=nav, amount=amount),
                  "related": [dict(owner=i, asof=DAY, lower_bound=v) for v in (first, second)]}
        hit, kind = evaluate_case_with_kind(spec, sample)
        if hit:
            expected[i] = kind
    rows = run_sql(spec, base, related)
    assert len(rows) == len(expected)
    assert {r["business_key"]: r["issue_kind"] for r in rows} == expected
    for case in default_cases(spec, BASE, RELATED):
        assert evaluate_case_with_kind(spec, case["row"]) == (case["expected_count"], case.get("expected_issue_kind"))


@pytest.mark.parametrize("overrides", [
    {"null_policy": "violate"}, {"null_policy": "invalid"}, {"rule_type": "not_null", "field": "nav"},
    {"null_policy": "skip", "null_handling": {"left": "zero"}},
    {"null_policy": "zero", "null_handling": {"right": "review"}},
])
def test_invalid_group_policies_and_rule_types_are_rejected_before_compilation(overrides):
    spec = {**rule(), **overrides}
    assert not query_ready(spec)
    with pytest.raises(AppError):
        compile_rule({"definition": spec})


def test_type_drift_and_cached_single_condition_sql_are_rejected():
    spec = rule()
    spec["expression"]["conditions"][1] = {"left": "amount", "op": "lt", "right": "kind"}
    with pytest.raises(AppError):
        validate_spec_against_columns(spec, BASE)
    spec = rule()
    old_sql, _ = compile_rule({"definition": {**spec, "expression": constant("gt", 1)}})
    metadata = SimpleNamespace(describe_table=lambda source, table: {"columns": BASE})
    result = execute_version({"definition": spec, "sql_text": old_sql}, {"report_date": DAY}, metadata)
    assert result.error_code == "MAPPING_DRIFT"
