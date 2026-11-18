import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_spec import validate_query_spec, validate_spec_against_columns
from tests.modules.data_validation.support import loan_definition


COLUMNS = [{"column_name": "amount", "data_type": "numeric"}, {"column_name": "status", "data_type": "varchar"},
           {"column_name": "report_date", "data_type": "date"}, {"column_name": "project_code", "data_type": "varchar"}]


def definition(**updates):
    return loan_definition(expression={"left": "amount", "op": "eq", "right_type": "value", "right": 0}, **updates)


@pytest.mark.parametrize("field", ["amount", "status", "report_date"])
@pytest.mark.parametrize("op", ["is_null", "is_not_null"])
def test_null_filter_has_no_literal_to_validate(field, op):
    item = {"table": "base", "field": field, "op": op, "value": None, "confirmed": True}
    assert validate_spec_against_columns(definition(filters=[item]), COLUMNS)["filters"][0] == item


@pytest.mark.parametrize("bad", [[], {}, False, 12])
def test_bad_operator_json_is_validation_error_not_type_error(bad):
    with pytest.raises(AppError) as error:
        validate_query_spec(definition(filters=[{"field": "status", "op": bad, "value": "A"}]))
    assert error.value.code == "VALIDATION_ERROR"


@pytest.mark.parametrize("extra", ["source_id", "join_type", "sql", "where"])
def test_unknown_join_semantics_are_not_silently_discarded(extra):
    join = {"table_name": "states", "on": [{"left": "project_code", "right": "project_code"}],
            "report_date_field": "report_date", "relationship_confirmed": True, "unmatched_policy": "exclude", extra: "other"}
    with pytest.raises(AppError):
        validate_query_spec(definition(join=join))


@pytest.mark.parametrize("bad", [{}, False, 0, ""])
def test_invalid_falsey_filter_containers_are_not_treated_as_no_filter(bad):
    with pytest.raises(AppError):
        validate_query_spec(definition(filters=bad))


@pytest.mark.parametrize("date", ["2026-11-17", "2024-02-29"])
def test_real_calendar_date_filter_is_accepted(date):
    validate_spec_against_columns(definition(filters=[{"field": "report_date", "op": "eq", "value": date}]), COLUMNS)


@pytest.mark.parametrize("date", ["2026-99-99", "2025-02-29", "2026-11-31"])
def test_impossible_date_filters_are_rejected(date):
    with pytest.raises(AppError):
        validate_spec_against_columns(definition(filters=[{"field": "report_date", "op": "eq", "value": date}]), COLUMNS)


@pytest.mark.parametrize("amount_type", ["double precision", "float8", "numeric(24,6)"])
def test_postgres_real_metadata_aliases_support_typed_scope(amount_type):
    columns = [{**column, "data_type": amount_type if column["column_name"] == "amount" else
                "character varying" if column["column_name"] == "status" else column["data_type"]}
               for column in COLUMNS]
    validate_spec_against_columns(definition(filters=[{"field": "status", "op": "eq", "value": "1", "confirmed": True}]), columns)


@pytest.mark.parametrize("amount_type", ["varchar", "json", "unknown_type"])
def test_new_numeric_comparison_rejects_non_numeric_actual_left_type(amount_type):
    columns = [{**column, "data_type": amount_type if column["column_name"] == "amount" else column["data_type"]}
               for column in COLUMNS]
    with pytest.raises(AppError):
        validate_spec_against_columns(definition(filters=[{"field": "status", "op": "eq", "value": "1", "confirmed": True}]), columns)
