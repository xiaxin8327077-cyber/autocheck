import pytest

from auto_check.modules.data_validation.candidate_preview import candidate_definition, run_preview_cases
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_samples import default_cases, evaluate_case_with_kind


def columns(**types):
    return [{"column_name": key, "data_type": value} for key, value in types.items()]


PROJECT = columns(tcmp="varchar", pname="varchar", pdata="date", scope="varchar", total="numeric")
DETAIL = columns(ref="varchar", did="varchar", ddata="date", active="integer", amount="numeric", scope="varchar")
DAY = "2026-11-01"


def rule(role="related"):
    base_project = role == "base"
    return {
        "name": "资产核查", "rule_type": "field_compare", "dialect": "mysql",
        "table_name": "projects" if base_project else "assets", "source_id": "local",
        "business_key": "tcmp" if base_project else "did", "report_date_field": "pdata" if base_project else "ddata",
        "null_policy": "zero", "equality_policy": "allow_equal", "violation_message": "金额异常",
        "expression": ({"left": "total", "op": "neq", "right_type": "field", "right_table": "related", "right": "amount"}
                       if base_project else {"left": "amount", "op": "eq", "right_type": "value", "right": 0}),
        "filters": [{"table": role, "field": "scope", "op": "eq", "value": "A", "confirmed": True},
                    {"table": "related" if base_project else "base", "field": "active", "op": "eq", "value": 1, "confirmed": True}],
        "project_driver": {"version": 1, "table_role": role},
        "project_context": ({"mode": "base", "code_field": "tcmp", "name_field": "pname", "confirmed": True}
                            if base_project else {"mode": "lookup", "table_name": "projects", "code_field": "ref",
                                  "name_field": "pname", "key": {"left": "ref", "right": "tcmp"}, "date_field": "pdata",
                                  "confirmed": True, "unique_evidence": {"kind": "pk", "fields": ["tcmp", "pdata"], "confirmed": True}}),
        "join": {"table_name": "assets" if base_project else "projects",
                 "report_date_field": "ddata" if base_project else "pdata",
                 "on": [{"left": "tcmp", "right": "ref"} if base_project else {"left": "ref", "right": "tcmp"}],
                 "relationship_confirmed": True, "unmatched_policy": "exclude"},
    }


def detail(amount=0, **other):
    return {"ref": "甲", "did": None, "amount": amount, "scope": "B", "active": 1, "ddata": DAY, **other}


def sample(details, **project):
    return {"report_date": DAY, "project": {"tcmp": "甲", "pname": "项目甲", "pdata": DAY, "scope": "A", **project},
            "details": details}


@pytest.mark.parametrize(("row", "expected"), [
    (sample([]), (1, "missing_record")),
    (sample([detail(ddata="2026-10-01")]), (1, "missing_record")),
    (sample([detail(ref="乙")]), (1, "missing_record")),
    (sample([detail(active=0)]), (0, None)),
    (sample([detail(0), detail(None), detail(0), detail(-4)]), (3, "numeric")),
    (sample([], scope="B"), (0, None)), (sample([detail()], pdata="2026-10-01"), (0, None)),
    (sample([], tcmp="  "), (1, "comparison")),
])
def test_project_scope_precedes_raw_matching_and_each_detail_counts(row, expected):
    assert evaluate_case_with_kind(rule(), row) == expected


def test_unary_and_group_evaluate_each_physical_detail():
    data = sample([detail(0), detail(None), detail(-2), detail(-2), detail(4)])
    config = rule()
    config.update(expression={"left": "amount", "op": "is_null"}, null_policy="skip")
    assert evaluate_case_with_kind(config, data) == (1, "comparison")
    config.update(expression={"logic": "any", "conditions": [
        {"left": "amount", "op": "is_null"}, {"left": "amount", "op": "lt", "right_type": "value", "right": 0}]},
        null_policy="zero")
    assert evaluate_case_with_kind(config, data) == (3, "numeric")
    config.update(expression={"left": "amount", "op": "eq", "right_type": "value", "right": 0}, null_policy="review")
    assert evaluate_case_with_kind(config, data) == (2, None)


def test_project_base_rows_and_decimal_sum_keep_absence_separate():
    config = rule("base")
    assert evaluate_case_with_kind(config, sample([detail(2), detail(2)], total=7)) == (2, "numeric")
    config["join"].update(right_aggregate="sum", unmatched_policy="review")
    for total, parts, expected in [
        (0.3, [detail(0.1), detail(0.2), detail(None)], (0, None)), (0, [], (1, "missing_record")),
        (4, [detail(2), detail(2)], (0, None)), (4, [detail(None)], (1, "numeric")),
        (0, [detail(active=0)], (0, None)),
    ]:
        assert evaluate_case_with_kind(config, sample(parts, total=total)) == expected
    del config["join"]
    config.update(expression={"left": "total", "op": "eq", "right_type": "value", "right": 0},
                  filters=config["filters"][:1])
    assert evaluate_case_with_kind(config, sample([], total=None)) == (1, "numeric")


def test_default_project_samples_exercise_multiple_hits_and_real_absence():
    config = rule()
    assert candidate_definition(config).get("project_driver") == config["project_driver"]
    cases = default_cases(config, DETAIL, PROJECT)
    assert all(set(c["row"]) == {"project", "details", "report_date"} for c in cases)
    assert any(c["expected_count"] == 2 and c["row"]["details"][0] == c["row"]["details"][1] for c in cases)
    assert any(not c["row"]["details"] and c.get("expected_issue_kind") == "missing_record" for c in cases)
    assert any(c["row"]["details"] and c["row"]["details"][0]["did"] is None and c["expected_count"] for c in cases)
    assert any(c["row"]["details"] and c["row"]["details"][0]["scope"] != c["row"]["project"]["scope"]
               and c["expected_count"] for c in cases)


def test_manual_project_samples_validate_count_types_fields_and_kind():
    config = rule()
    cases = [{"name": "重复明细", "row": sample([detail(), detail()]), "expected_count": 2,
              "expected_issue_kind": "numeric"}]
    preview = {"definition": config, "cases": cases, "content_sha256": "version",
               "columns": DETAIL, "related_columns": PROJECT}
    result = run_preview_cases(preview)
    assert result["passed_count"] == 1 and result["cases"][0]["actual_issue_kind"] == "numeric"
    wrong_kind = [{**cases[0], "expected_issue_kind": "missing_record"}]
    assert run_preview_cases(preview, wrong_kind)["failed_count"] == 1
    for invalid in [detail(amount="0"), detail(amount=True), detail(amount=float("nan")), detail(active=2.5),
                    detail(active=float("inf")), detail(ref=3), detail(ddata="2026-02-31"),
                    detail(unknown="x"), {k: v for k, v in detail().items() if k != "amount"}]:
        with pytest.raises(AppError):
            run_preview_cases(preview, [{**cases[0], "row": sample([invalid])}])
    for row in [sample([detail()] * 21), {**sample([]), "report_date": "x"}, {**sample([]), "project": []}]:
        with pytest.raises(AppError):
            run_preview_cases(preview, [{**cases[0], "row": row}])
    for invalid_count in [-1, True, 21]:
        with pytest.raises(AppError):
            run_preview_cases(preview, [{**cases[0], "expected_count": invalid_count}])


@pytest.mark.parametrize("dialect", ["postgresql", "mysql"])
@pytest.mark.parametrize("mode", ["detail", "single", "aggregate", "group"])
def test_default_cases_and_formatted_sql_match_compiled_project_query(dialect, mode):
    import sqlite3

    from auto_check.modules.data_validation.candidate_preview import preview_definition

    config = rule("base" if mode in {"single", "aggregate"} else "related")
    config["dialect"] = dialect
    if mode == "single":
        config.pop("join")
        config["filters"] = config["filters"][:1]
        config["expression"] = {"left": "total", "op": "neq", "right_type": "value", "right": 0}
    if mode == "aggregate":
        config["join"].update(right_aggregate="sum", unmatched_policy="review")
    if mode == "group":
        config["expression"] = {"logic": "any", "conditions": [
            {"left": "amount", "op": "lt", "right_type": "value", "right": 0},
            {"left": "did", "op": "is_null"}]}
    left, right = (PROJECT, DETAIL) if mode in {"single", "aggregate"} else (DETAIL, PROJECT)
    preview = preview_definition(config, left, right if mode != "single" else None)
    receipt = run_preview_cases(preview)
    assert receipt["passed_count"] == len(preview["cases"])
    assert preview["content_sha256"] == preview_definition(preview["definition"], left, right if mode != "single" else None)["content_sha256"]
    kind = preview["definition"]["result_aliases"]["issue_kind"]
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE projects(tcmp text, pname text, pdata date, scope text, total numeric)")
        db.execute("CREATE TABLE assets(ref text, did text, ddata date, active integer, amount numeric, scope text)")
        for case in receipt["cases"]:
            row = case["row"]
            db.execute("DELETE FROM projects")
            db.execute("DELETE FROM assets")
            for table, columns_, records in [("projects", PROJECT, [row["project"]]), ("assets", DETAIL, row["details"])]:
                names = [column["column_name"] for column in columns_]
                db.executemany("INSERT INTO " + table + " VALUES (" + ",".join("?" for _ in names) + ")",
                               [[record.get(name) for name in names] for record in records])
            outputs = db.execute(preview["sql_preview"], {**preview["sql_params"], "report_date": row["report_date"]}).fetchall()
            assert len(outputs) == case["actual_count"], case["name"]
            kinds = {result[kind] for result in outputs}
            assert (next(iter(kinds)) if len(kinds) == 1 else None) == case["actual_issue_kind"], case["name"]
            displayed = db.execute(preview["sql_display"], {"report_date": row["report_date"]}).fetchall()
            assert displayed == outputs


def test_same_physical_name_on_both_sides_yields_an_actual_inequality_witness():
    config = rule("base")
    config["expression"]["left"] = "amount"
    project_cols = [*PROJECT, {"column_name": "amount", "data_type": "numeric"}]
    cases = default_cases(config, project_cols, DETAIL)
    assert any(c["expected_count"] == 2 and c["expected_issue_kind"] == "numeric" for c in cases)
    assert any(c["row"]["details"] and c["row"]["details"][0]["amount"] < 0
               for c in cases if c["row"]["details"] and c["row"]["details"][0]["amount"] is not None)


def test_integer_measure_defaults_remain_valid_with_fractional_comparison_value():
    config = rule()
    config["expression"]["right"] = 0.5
    base_cols = [{**col, "data_type": "integer"} if col["column_name"] == "amount" else col for col in DETAIL]
    cases = default_cases(config, base_cols, PROJECT)
    assert all(type(detail["amount"]) is int or detail["amount"] is None for case in cases for detail in case["row"]["details"])
