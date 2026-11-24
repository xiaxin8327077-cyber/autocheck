import sqlite3
from decimal import Decimal

import pytest

from auto_check.modules.data_validation.candidate_preview import preview_definition, run_preview_cases
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_samples import evaluate_case_with_kind
from auto_check.modules.data_validation.query_spec import validate_spec_against_columns
from tests.modules.data_validation.test_text_predicates import register_literal_position_dialects


DAY = "2026-11-23"
WORDS = ["%", "‰", "_", "A!'", "X\\Y", "center", "市院"]
COLUMNS = [{"column_name": name, "data_type": kind} for name, kind in
           [("id", "varchar"), ("day", "date"), ("notes", "text"), ("label", "text"), ("amount", "numeric")]]


def rule(dialect, op, logic=None):
    expr = {"left": "notes", "op": op, "right_type": "value", "right": WORDS}
    if logic:
        expr = {"logic": logic, "conditions": [expr, {"left": "label", "op": "eq", "right_type": "value", "right": "Y"}]}
    return {"rule_type": "field_compare", "table_name": "registry", "business_key": "id",
            "report_date_field": "day", "dialect": dialect, "null_policy": "skip",
            "equality_policy": "allow_equal", "expression": expr, "violation_message": "核查备注"}


@pytest.mark.parametrize("dialect", ["postgresql", "mysql"])
@pytest.mark.parametrize("op", ["contains_any", "not_contains_any"])
@pytest.mark.parametrize("logic", [None, "any", "all"])
def test_literal_keyword_expression_is_the_violation_and_runs_in_single_and_grouped_rules(dialect, op, logic):
    definition = rule(dialect, op, logic)
    preview = preview_definition(definition, COLUMNS)
    assert "JOIN" not in preview["sql_preview"].upper() and preview["sql_display_params"].keys() == {"report_date"}
    assert run_preview_cases(preview)["failed_count"] == 0
    values = [("3%", "Y"), ("2‰", "N"), ("A_B", "N"), ("XA!'B", "Y"), ("X\\Y", "N"),
              ("CENTER", "Y"), ("center", "N"), ("市院校", "N"), ("", "N"), (None, "N"), (" plain ", "N")]
    expected = []
    for index, (notes, label) in enumerate(values):
        hit = bool(notes) and (any(word in notes for word in WORDS) == (op == "contains_any"))
        hit = (hit or label == "Y") if logic == "any" else (hit and label == "Y") if logic == "all" else hit
        if hit:
            expected.append(str(index))
        sample = {"base": {"day": DAY, "notes": notes, "label": label}, "report_date": DAY, "related": []}
        assert evaluate_case_with_kind(definition, sample)[0] == int(hit)
    with sqlite3.connect(":memory:") as db:
        register_literal_position_dialects(db)
        db.execute("CREATE TABLE registry(id text, day date, notes text, label text)")
        db.executemany("INSERT INTO registry VALUES (?,?,?,?)", [(str(i), DAY, *v) for i,v in enumerate(values)])
        results = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": DAY}).fetchall()
    assert [row[0] for row in results] == expected


@pytest.mark.parametrize("changes", [{"left": "day"}, {"right": []}, {"right": [""]}, {"right": [2]},
                                    {"right_type": "field", "right": "notes"}, {"right": "%|‰"}])
def test_reject_malformed_keyword_expression_and_unsupported_columns(changes):
    definition = rule("postgresql", "contains_any")
    definition["expression"].update(changes)
    with pytest.raises(AppError):
        validate_spec_against_columns(definition, COLUMNS)


@pytest.mark.parametrize("keywords", [["%", "‰"], ["12"]])
def test_numeric_keyword_comparison_uses_numeric_witnesses_and_decimal_projection(keywords):
    definition = rule("postgresql", "contains_any")
    definition["expression"].update(left="amount", right=keywords)
    preview = preview_definition(definition, COLUMNS)
    result = run_preview_cases(preview)
    assert result["failed_count"] == result["not_run_count"] == 0
    samples = [c["row"]["base"]["amount"] for c in preview["cases"]]
    assert all(v is None or type(v) in (float, int) for v in samples)
    assert any(c["expected_count"] for c in preview["cases"]) == ("12" in keywords)
    sample = {"report_date": DAY, "base": {"day": DAY, "amount": Decimal("12.0000")}, "related": []}
    assert evaluate_case_with_kind(definition, sample)[0] == int("12" in keywords)


def test_fixed_decimal_sample_respects_scale_and_refuses_text_in_numeric_field():
    definition = rule("postgresql", "contains_any")
    definition["expression"].update(left="amount", right=[".0000"])
    columns = [{**c, "data_type": "numeric(19,4)"} if c["column_name"] == "amount" else c for c in COLUMNS]
    preview = preview_definition(definition, columns)
    sample = {"name": "整数投影保留声明精度", "row": {"base": {"amount": 2, "day": DAY},
              "report_date": DAY, "related": []}, "expected_count": 1}
    assert run_preview_cases(preview, [sample])["passed_count"] == 1
    sample["row"]["base"]["amount"] = "2%"
    with pytest.raises(AppError):
        run_preview_cases(preview, [sample])


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_project_query_finds_literal_percent_and_keeps_existing_detail_join(dialect):
    from tests.modules.data_validation.test_project_driver_sql import DAY as anchor, DETAIL, PROJECT, database, detail_rule
    definition = detail_rule(dialect)
    definition.update(project_driver={"version": 3, "table_role": "related"}, null_policy="skip",
                      expression={"left": "num", "op": "contains_any", "right_type": "value", "right": ["%", "‰"]})
    preview = preview_definition(definition, DETAIL, PROJECT)
    assert run_preview_cases(preview)["failed_count"] == 0
    with database() as db:
        register_literal_position_dialects(db)
        db.execute("INSERT INTO lines VALUES(?,?,?,?,?)", ("A", anchor, "合成‰", 1, 1))
        rows = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": anchor}).fetchall()
    assert len(rows) == 1 and rows[0][0] == "合成‰"
    assert preview["sql_preview"].upper().count(" JOIN ") == 1


def test_keyword_array_roundtrips_saved_versions_and_confirmed_test():
    from tests.modules.data_validation.support import user
    from tests.modules.data_validation.test_ai_service import _rules_with_doc

    columns = [(c["column_name"], cn, c["data_type"], "Y" if cn == "编号" else "") for c, cn in
               zip(COLUMNS, ["编号", "数据日期", "备注", "标签", "数量"])]
    rules, _ = _rules_with_doc([], fields=columns)
    rules.metadata.describe_table = lambda *_: {"columns": COLUMNS}
    definition = {**rule("postgresql", "not_contains_any"), "table_name": "test_table",
                  "source_id": "src", "generation_mode": "manual"}
    saved = rules.save_draft(user(), definition)
    first = rules.storage.latest_version(saved["id"])
    rules.save_draft(user(), {**first["definition"], "name": "调整说明"}, saved["id"])
    second = rules.storage.latest_version(saved["id"])
    assert second["definition"]["expression"] == first["definition"]["expression"] == definition["expression"]
    checked = rules.run_tests(user(), saved["id"], 2)
    assert checked["failed_count"] == checked["not_run_count"] == 0 and checked["passed_count"] >= 3
    rules.confirm_rule(user(), saved["id"], 2, second["content_sha256"])
    assert rules.storage.get_rule(saved["id"])["current_version_id"] == second["id"]
