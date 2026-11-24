import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.candidate_preview import preview_definition, run_preview_cases
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.formula import compile_formula, evaluate_formula, formula_fields
from auto_check.modules.data_validation.query_samples import evaluate_case_with_kind
from auto_check.modules.data_validation.query_spec import apply_numeric_null_policy, referenced_columns, validate_spec_against_columns


def binary(op, left, right):
    return {"op": op, "left": left, "right": right}


def field(name):
    return {"field": name}


DAY = "2026-10-01"
FIELDS = ["closing", "opening", "arrivals", "departures", "capacity"]
COLUMNS = [{"column_name": name, "data_type": typ} for name, typ in
           [("item", "varchar"), ("day", "date"), *((name, "numeric") for name in FIELDS)]]
FLOW = binary("-", binary("+", field("opening"), field("arrivals")), field("departures"))
RATE = binary("/", binary("*", FLOW, {"value": 2}), field("capacity"))


def definition(dialect="postgresql", policy="review", tree=None):
    return {
        "name": "库存复核", "rule_type": "field_compare", "dialect": dialect, "table_name": "inventory",
        "business_key": "item", "report_date_field": "day", "violation_message": "库存不符",
        "equality_policy": "allow_equal", "null_policy": policy, "include_result_fields": True,
        "expression": {"left": "closing", "op": "neq", "right_type": "formula", "right": tree or RATE},
    }


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
@pytest.mark.parametrize("policy", ["review", "zero", "skip"])
def test_compiled_formula_matches_samples_including_fractional_division_and_nulls(dialect, policy):
    rule = definition(dialect, policy)
    assert set(FIELDS) <= set(referenced_columns(rule)["base"])
    preview = preview_definition(rule, COLUMNS)
    sql = preview["sql_preview"]
    assert " JOIN " not in sql.upper() and "NULLIF(" in sql.upper()
    assert preview["content_sha256"] == preview_definition(preview["definition"], COLUMNS)["content_sha256"]
    tested = run_preview_cases(preview)
    assert tested["passed_count"] >= 3 and tested["failed_count"] == tested["not_run_count"] == 0
    equal = next(case for case in preview["cases"] if case["name"] == "等于计算值")
    assert equal["expected_count"] == 0
    expected_null = {"review": "missing_value", "zero": "numeric", "skip": None}[policy]
    expected_den = {"review": "missing_value", "zero": "calculation_error", "skip": None}[policy]
    rows = [
        ("balanced", DAY, 2.5, 4, 3, 2, 4, None),
        ("mismatch", DAY, 2, 4, 3, 2, 4, "numeric"),
        ("zero", DAY, 0, 4, 3, 2, 0, "calculation_error"),
        ("zero-and-missing", DAY, 0, None, 3, 2, 0, "calculation_error"),
        ("missing-addend", DAY, 2.5, 4, None, 2, 4, expected_null),
        ("missing-den", DAY, 2.5, 4, 3, 2, None, expected_den),
        ("old", "2026-09-01", 2, 4, 3, 2, 0, None),
    ]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE inventory(item text, day date, closing numeric, opening numeric, "
                   "arrivals numeric, departures numeric, capacity numeric)")
        db.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?,?)", [row[:-1] for row in rows])
        actual = db.execute(sql, {**preview["sql_params"], "report_date": DAY}).fetchall()
    aliases = preview["definition"]["result_aliases"]
    assert {row[aliases["business_key"]]: row[aliases["issue_kind"]] for row in actual} == {
        row[0]: row[-1] for row in rows if row[-1]}
    for row in actual:
        if row[aliases["issue_kind"]] == "calculation_error":
            assert "公式无法计算" in row[aliases["violation_message"]]
    for row in rows:
        sample = {"report_date": DAY, "base": dict(zip(("item", "day", *FIELDS), row[:-1])), "related": []}
        assert evaluate_case_with_kind(rule, sample) == (int(bool(row[-1])), row[-1])


def test_formula_tree_rejects_unsafe_nodes_and_non_numeric_document_fields():
    for replacement in [field("unknown"), field("item"), {"value": True}, {"value": "3.14"},
                        {"value": float("inf")}, {"sql": "opening"}, field("inventory.opening"),
                        binary("**", field("opening"), {"value": 2})]:
        rule = definition(tree=binary("+", replacement, field("arrivals")))
        with pytest.raises(AppError):
            validate_spec_against_columns(rule, COLUMNS)


def test_formula_sample_keeps_decimal_precision_and_inner_division_failure():
    rule = definition(tree=FLOW)
    base = dict(item="x", day=DAY, closing=Decimal("0.28"), opening=Decimal("0.1"),
                arrivals=Decimal("0.2"), departures=Decimal("0.02"))
    sample = {"report_date": DAY, "base": base, "related": []}
    assert evaluate_case_with_kind(rule, sample) == (0, None)
    rule["expression"]["right"] = binary("+", binary("/", {"value": 1}, {"value": 0}), field("opening"))
    assert evaluate_case_with_kind(rule, sample) == (1, "calculation_error")


def test_formula_core_preserves_field_order_signs_and_constant_binding():
    rule = definition()
    assert formula_fields(RATE) == ["opening", "arrivals", "departures", "capacity"]
    params = {}
    rendered = compile_formula(rule, lambda name: f't."{name}"', params, "'库存不符'")
    assert params == {"formula_value_1": 2}
    assert set(FIELDS) == {name for name in FIELDS if name in rendered.hit}
    base = dict(closing=2.5, opening=4, arrivals=3, departures=2, capacity=4)
    assert evaluate_formula(rule, base) == (0, None)
    for name in FIELDS:
        assert evaluate_formula(rule, {**base, name: base[name] + 1}) == (1, "numeric")
    assert evaluate_formula(rule, {**base, "capacity": 0}) == (1, "calculation_error")
    assert evaluate_formula(rule, {**base, "capacity": None}) == (1, "missing_value")
    assert evaluate_formula({**rule, "null_policy": "zero"}, {**base, "capacity": None}) == (1, "calculation_error")
    assert evaluate_formula({**rule, "null_policy": "skip"}, {**base, "capacity": None}) == (0, None)


@pytest.mark.parametrize("two_sides", [False, True])
def test_left_formula_compares_with_a_constant_or_another_formula(two_sides):
    rule = definition()
    rule["expression"] = {"left_type": "formula", "left": RATE, "op": "gt",
                          "right_type": "formula" if two_sides else "value",
                          "right": binary("+", field("closing"), {"value": 0.5}) if two_sides else 2.5}
    preview = preview_definition(rule, COLUMNS)
    assert preview["sql_display_params"].keys() == {"report_date"}
    assert ":formula_value" not in preview["sql_display"]
    labels = preview["definition"]["result_aliases"]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE inventory(item text, day date, closing numeric, opening numeric, "
                   "arrivals numeric, departures numeric, capacity numeric)")
        db.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?,?)", [
            ("equal", DAY, 2, 4, 3, 2, 4), ("greater", DAY, 2, 5, 3, 2, 4), ("unknown", DAY, 2, 5, 3, 2, 0)])
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": DAY}).fetchall()
    assert {row[labels["business_key"]]: (row[labels["issue_kind"]], row[labels["checked_value"]],
                                           row[labels["comparison_value"]]) for row in rows} == {
        "greater": ("numeric", 3, 2.5), "unknown": ("calculation_error", None, 2.5)}


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_project_driver_only_joins_project_context_and_keeps_formula_on_one_detail(dialect):
    from tests.modules.data_validation.test_project_driver_sql import DAY as project_day, DETAIL, PROJECT, database, detail_rule

    rule = detail_rule(dialect)
    rule["project_driver"] = {"version": 3, "table_role": "related"}
    rule["expression"] = {"left": "amount", "op": "neq", "right_type": "formula",
                          "right": binary("/", field("allowed"), field("amount"))}
    preview = preview_definition(rule, DETAIL, PROJECT)
    tested = run_preview_cases(preview)
    assert tested["passed_count"] >= 3 and tested["failed_count"] == tested["not_run_count"] == 0
    sql = preview["sql_preview"]
    assert sql.upper().count(" JOIN ") == 1 and "INNER JOIN" in sql.upper()
    aliases = preview["definition"]["result_aliases"]
    with database() as db:
        db.row_factory = sqlite3.Row
        matches = db.execute(sql, {**preview["sql_params"], "report_date": project_day}).fetchall()
    assert {row[aliases["project_code"]] for row in matches} == {"C", "F"}
    assert all(row[aliases["issue_kind"]] == "calculation_error" for row in matches)


@pytest.mark.parametrize("all_zero", [True, False])
def test_each_documented_null_to_zero_leaf_keeps_its_own_evidence_after_rebinding(all_zero):
    columns = [{**c, "logic": "空值视为0" if all_zero or c["column_name"] == "arrivals" else "直取"}
               for c in COLUMNS]
    rule = apply_numeric_null_policy(definition(tree=FLOW), columns)
    assert rule["null_policy"] == ("zero" if all_zero else "review")
    assert apply_numeric_null_policy(rule, columns) == rule
    row = dict(day=DAY, closing=1, opening=3, arrivals=None, departures=2)
    assert evaluate_formula(rule, row) == (0, None)
    assert evaluate_formula(rule, {**row, "opening": None}) == (1, "numeric" if all_zero else "missing_value")


def test_formula_draft_edit_reload_test_confirm_and_execution_use_same_tree(monkeypatch):
    from auto_check.modules.data_validation.executor import execute_version
    from tests.modules.data_validation.support import user
    from tests.modules.data_validation.test_ai_service import _rules_with_doc

    labels = ["编号", "数据日期", "期末库存", "期初库存", "到货数量", "发货数量", "容量"]
    docs = [(col["column_name"], label, col["data_type"], "Y" if label == "编号" else "")
            for col, label in zip(COLUMNS, labels)]
    rules, _ = _rules_with_doc([], fields=docs)
    rule = {**definition(), "source_id": "src", "table_name": "test_table", "generation_mode": "manual"}
    monkeypatch.setattr(rules.metadata, "describe_table", lambda *_: {"columns": COLUMNS})
    saved = rules.save_draft(user(), rule)
    first = rules.storage.latest_version(saved["id"])
    rules.save_draft(user(), {**first["definition"], "name": "库存复核（更新）"}, saved["id"])
    latest = rules.storage.latest_version(saved["id"])
    assert latest["definition"]["expression"] == first["definition"]["expression"] == rule["expression"]
    result = rules.run_tests(user(), saved["id"], 2)
    assert result["passed_count"] >= 3 and result["failed_count"] == result["not_run_count"] == 0
    rules.confirm_rule(user(), saved["id"], 2, latest["content_sha256"])
    assert rules.storage.get_rule(saved["id"])["current_version_id"] == latest["id"]
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE test_table(item text, day date, closing numeric, opening numeric, "
                   "arrivals numeric, departures numeric, capacity numeric)")
        db.executemany("INSERT INTO test_table VALUES (?,?,?,?,?,?,?)", [
            ("ok", DAY, 2.5, 4, 3, 2, 4), ("different", DAY, 0, 4, 3, 2, 4), ("error", DAY, 0, 4, 3, 2, 0)])
        def select(_source, sql, params, **limits):
            cursor = db.execute(sql, params)
            return SimpleNamespace(columns=[col[0] for col in cursor.description], rows=cursor.fetchall(), truncated=False)
        monkeypatch.setattr(rules.metadata, "execute_select", select, raising=False)
        actual = execute_version(latest, {"report_date": DAY}, rules.metadata)
    assert actual.status == "VIOLATION" and {row["business_key"]: row["issue_kind"] for row in actual.rows} == {
        "different": "numeric", "error": "calculation_error"}
    assert {"期末库存", "期初库存", "到货数量", "发货数量", "容量", "比较值"} <= set(actual.query_results[0]["values"])


def test_thirty_term_left_associative_formula_projects_every_documented_input():
    names = [f"component_{n}" for n in range(30)]
    tree = field(names[0])
    for name in names[1:]:
        tree = binary("+", tree, field(name))
    rule = definition(tree=tree)
    cols = COLUMNS + [{"column_name": name, "data_type": "decimal"} for name in names]
    preview = preview_definition(rule, cols)
    assert set(names) <= set(preview["definition"]["result_aliases"].values())
    tested = run_preview_cases(preview)
    assert tested["passed_count"] >= 30 and tested["failed_count"] == tested["not_run_count"] == 0
    sample = {"report_date": DAY, "base": {"closing": 30, "day": DAY, **dict.fromkeys(names, 1)}, "related": []}
    assert evaluate_case_with_kind(rule, sample) == (0, None)


def test_postgres_promotes_intermediate_integer_operations_before_overflow():
    from auto_check.modules.data_validation.compiler import compile_rule

    # A decimal parent cannot recover from overflow in either independent integer child.
    tree = binary("-", binary("*", field("a"), field("b")), binary("+", field("a"), field("b")))
    sql, _ = compile_rule({"definition": definition(tree=tree)})
    assert 'CAST(t."a" AS NUMERIC) * t."b"' in sql
    assert 'CAST(t."a" AS NUMERIC) + t."b"' in sql


@pytest.mark.parametrize("logic", ["any", "all"])
@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_grouped_sql_preserves_three_valued_logic_and_independent_division_errors(logic, dialect):
    rule = definition(dialect)
    first = rule["expression"]
    rule["expression"] = {"logic": logic, "conditions": [first, {"left": "closing", "op": "gt", "right_type": "value", "right": 1}]}
    preview = preview_definition(rule, COLUMNS)
    labels = preview["definition"]["result_aliases"]
    rows = [("balanced", DAY, 2.5, 4, 3, 2, 4), ("negative", DAY, -1, 4, 3, 2, 4),
            ("missing", DAY, 2, 4, None, 2, 4), ("zero", DAY, -1, 4, 3, 2, 0)]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE inventory(item text, day date, closing numeric, opening numeric, "
                   "arrivals numeric, departures numeric, capacity numeric)")
        db.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?,?)", rows)
        actual = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": DAY}).fetchall()
    expected = ({"balanced": "numeric", "negative": "numeric", "missing": "numeric", "zero": "calculation_error"}
                if logic == "any" else {"missing": "missing_value", "zero": "calculation_error"})
    assert {r[labels["business_key"]]: r[labels["issue_kind"]] for r in actual} == expected
    for key, day, *numbers in rows:
        sample = {"report_date": day, "base": {**dict(zip(FIELDS, numbers)), "day": day}, "related": []}
        assert evaluate_case_with_kind(rule, sample) == (int(key in expected), expected.get(key))
