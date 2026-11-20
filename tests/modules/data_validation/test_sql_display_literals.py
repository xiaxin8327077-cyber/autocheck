import sqlite3
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.sql_display import inline_sql_parameters


def test_string_membership_and_numeric_zero_keep_sqlite_semantics() -> None:
    sql = (
        'SELECT t."c_oper_mode", t."threshold" FROM t '
        'WHERE t."c_oper_mode" IN (:filter_1_0,:filter_1_1) '
        'AND t."threshold" >= :threshold ORDER BY t."c_oper_mode"'
    )
    params = {"filter_1_0": "1", "filter_1_1": "2", "threshold": 0}
    original_sql = sql
    original_params = deepcopy(params)

    displayed = inline_sql_parameters(sql, params, "postgresql")

    assert displayed == (
        'SELECT t."c_oper_mode", t."threshold" FROM t '
        "WHERE t.\"c_oper_mode\" IN ('1','2') "
        'AND t."threshold" >= 0 ORDER BY t."c_oper_mode"'
    )
    assert sql == original_sql
    assert params == original_params
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE t (c_oper_mode TEXT, threshold INTEGER)")
        connection.executemany("INSERT INTO t VALUES (?, ?)", [("1", 0), ("2", 1), ("3", 0)])
        expected = connection.execute(sql, params).fetchall()
        actual = connection.execute(displayed).fetchall()
    assert actual == expected == [("1", 0), ("2", 1)]


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_chinese_quote_null_and_zero_match_bound_sqlite_values(dialect: str) -> None:
    sql = "SELECT :chinese AS chinese, :quote AS quote, :nothing AS null_value, :zero AS zero"
    params = {"chinese": "中文", "quote": "O'Neil", "nothing": None, "zero": 0}

    displayed = inline_sql_parameters(sql, params, dialect)

    assert displayed == "SELECT '中文' AS chinese, 'O''Neil' AS quote, NULL AS null_value, 0 AS zero"
    with sqlite3.connect(":memory:") as connection:
        expected = connection.execute(sql, params).fetchone()
        actual = connection.execute(displayed).fetchone()
    assert actual == expected == ("中文", "O'Neil", None, 0)


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_boolean_and_finite_numeric_literals_are_exact(dialect: str) -> None:
    sql = "SELECT :yes, :no, :integer, :float, :decimal, :exponent"
    params = {
        "yes": True,
        "no": False,
        "integer": -123456789012345678901234567890,
        "float": 0.1,
        "decimal": Decimal("12345678901234567890.0012300"),
        "exponent": Decimal("1E+3"),
    }

    assert inline_sql_parameters(sql, params, dialect) == (
        "SELECT TRUE, FALSE, -123456789012345678901234567890, 0.1, "
        "12345678901234567890.0012300, 1E+3"
    )


def test_postgresql_backslash_uses_an_escaped_e_literal() -> None:
    value = "C:\\temp\\O'Neil"

    assert inline_sql_parameters("SELECT :value", {"value": value}, "postgresql") == (
        r"SELECT E'C:\\temp\\O''Neil'"
    )


def test_mysql_backslash_quote_and_newline_use_utf8mb4_hex() -> None:
    value = "C:\\new\\O'Neil\n"

    assert inline_sql_parameters("SELECT :value", {"value": value}, "mysql") == (
        "SELECT CONVERT(0x433A5C6E65775C4F274E65696C0A USING utf8mb4)"
    )


def test_mysql_control_characters_use_utf8mb4_hex() -> None:
    value = "\\\n\t\x00\x1a"

    assert inline_sql_parameters("SELECT :value", {"value": value}, "mysql") == (
        "SELECT CONVERT(0x5C0A09001A USING utf8mb4)"
    )


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_quoted_tokens_escaped_quotes_unknowns_and_casts_are_not_replaced(dialect: str) -> None:
    sql = (
        "SELECT :filter_1_0, "
        "':filter_1_0', 'it''s :filter_1_0', 'it\\'s :filter_1_0', "
        '"中文:filter_1_0", "双引号"":filter_1_0", "斜杠\\":filter_1_0", '
        "`反引号:filter_1_0`, `反引号``:filter_1_0`, "
        "amount::text, :unknown, :report_date"
    )
    params = {"filter_1_0": "1", "text": "not-a-cast", "report_date": "2026-01-01"}

    displayed = inline_sql_parameters(sql, params, dialect)

    assert displayed == sql.replace(":filter_1_0", "'1'", 1)
    assert "amount::text" in displayed
    assert ":unknown" in displayed
    assert ":report_date" in displayed


def test_only_report_date_is_preserved_and_inputs_are_immutable() -> None:
    sql = "SELECT :report_date, :report_date, :other_date, :missing, :report_date_extra"
    params = {
        "report_date": date(2026, 1, 1),
        "other_date": "2025-12-31",
        "report_date_extra": "extra",
    }
    original_params = deepcopy(params)

    displayed = inline_sql_parameters(sql, params, "mysql")

    assert displayed == "SELECT :report_date, :report_date, '2025-12-31', :missing, 'extra'"
    assert sql == "SELECT :report_date, :report_date, :other_date, :missing, :report_date_extra"
    assert params == original_params


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_execution_display_can_inline_report_date_without_touching_quoted_tokens(dialect):
    sql = "SELECT ':report_date', :report_date, :filter_1_0, :filter_1_1"
    params = {"report_date": "2026-10-31", "filter_1_0": "1", "filter_1_1": "3"}
    assert inline_sql_parameters(sql, params, dialect, preserve_report_date=False) == (
        "SELECT ':report_date', '2026-10-31', '1', '3'"
    )
    assert params["report_date"] == "2026-10-31"


def test_execution_display_refuses_unknown_binding_instead_of_returning_partial_sql():
    with pytest.raises(AppError):
        inline_sql_parameters("SELECT :missing", {}, "postgresql", preserve_report_date=False, require_all_parameters=True)
    assert inline_sql_parameters("SELECT ':missing'", {}, "postgresql", require_all_parameters=True) == "SELECT ':missing'"


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        object(),
        [1],
        {"nested": 1},
        b"bytes",
        date(2026, 1, 1),
    ],
)
def test_rejects_non_finite_and_unsupported_values(value: object) -> None:
    with pytest.raises(AppError) as error:
        inline_sql_parameters("SELECT :value", {"value": value}, "postgresql")
    assert error.value.code == "VALIDATION_ERROR"


@pytest.mark.parametrize("dialect", ["", "sqlite", "POSTGRESQL", None])
def test_rejects_unknown_dialect(dialect: object) -> None:
    with pytest.raises(AppError) as error:
        inline_sql_parameters("SELECT :value", {"value": 1}, dialect)  # type: ignore[arg-type]
    assert error.value.code == "VALIDATION_ERROR"
