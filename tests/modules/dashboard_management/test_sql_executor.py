from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
import sys

import pytest

from auto_check.app.config import DataSourceConfig, DataSourceEntry


class _Cursor:
    def __init__(self, columns, rows, calls):
        self.description = [(column,) for column in columns]
        self._rows = rows
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchmany(self, limit):
        self.calls.append(("fetchmany", limit))
        return self._rows[:limit]


class _Connection:
    def __init__(self, columns, rows):
        self.calls = []
        self.cursor_instance = _Cursor(columns, rows, self.calls)
        self.closed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _source(db_type="postgresql"):
    return DataSourceEntry(
        id="source-1",
        name="安全数据源",
        config=DataSourceConfig(db_type, "db.internal", 5432, "dashboard", "public", "reader", "secret"),
    )


def _fields(*items):
    return [
        {"field_alias": alias, "value_type": value_type, "nullable": nullable, "enabled": True}
        for alias, value_type, nullable in items
    ]


def _install_driver(monkeypatch, db_type, connection):
    module_name = "psycopg" if db_type == "postgresql" else "pymysql"
    captured = {}

    def connect(**kwargs):
        captured.update(kwargs)
        return connection

    monkeypatch.setitem(sys.modules, module_name, SimpleNamespace(connect=connect))
    return captured


@pytest.mark.parametrize("sql", [
    "DELETE FROM t",
    "SELECT 1; SELECT 2",
    "WITH changed AS (UPDATE t SET x=1 RETURNING *) SELECT * FROM changed",
    "WITH safe_cte AS (SELECT 1) VALUES (1)",
    "CALL refresh_dashboard()",
])
def test_preview_rejects_non_readonly_sql_before_connecting(sql, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor
    from auto_check.modules.dashboard_management.validator import ValidationError

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, "postgresql", connection)

    with pytest.raises(ValidationError, match="只允许单条只读查询"):
        SqlPreviewExecutor().execute(_source(), sql, _fields(("value", "integer", False)), "list")
    assert connection.calls == []


def test_preview_validates_columns_converts_values_and_truncates(monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    rows = [
        ("7", "12.50", "true", "2026-09-14", "2026-09-14T10:11:12", "x", "ignored")
        for _ in range(11)
    ]
    connection = _Connection(
        ["count", "amount", "ready", "business_date", "updated_at", "name", "extra"], rows,
    )
    captured = _install_driver(monkeypatch, "postgresql", connection)
    preview = SqlPreviewExecutor().execute(_source(), "SELECT safe_values", _fields(
        ("count", "integer", False), ("amount", "decimal", False), ("ready", "boolean", False),
        ("business_date", "date", False), ("updated_at", "datetime", False), ("name", "string", False),
    ), "list")

    assert preview.columns == ("count", "amount", "ready", "business_date", "updated_at", "name")
    assert len(preview.rows) == 10 and preview.has_more is True and preview.returned_count == 10
    assert preview.rows[0] == {
        "count": 7, "amount": "12.50", "ready": True, "business_date": "2026-09-14",
        "updated_at": "2026-09-14T10:11:12", "name": "x",
    }
    assert connection.calls[-1] == ("fetchmany", 11)
    assert connection.calls[:3] == [
        ("BEGIN READ ONLY", None),
        ("SELECT set_config('statement_timeout', %s, true)", ("10000",)),
        ("SELECT set_config('search_path', %s, true)", ("pg_catalog",)),
    ]
    assert captured["connect_timeout"] == 5
    assert preview.tested_signature == SqlPreviewExecutor.signature_for(_source(), " SELECT   safe_values ", _fields(
        ("count", "integer", False), ("amount", "decimal", False), ("ready", "boolean", False),
        ("business_date", "date", False), ("updated_at", "datetime", False), ("name", "string", False),
    ), "list")


@pytest.mark.parametrize("columns,rows,shape,match", [
    (["value", "VALUE"], [(1, 2)], "list", "重复"),
    (["other"], [(1,)], "list", "缺少"),
    (["value"], [(1,), (2,)], "scalar", "单值"),
    (["value"], [(None,)], "list", "不能为空"),
])
def test_preview_rejects_invalid_result_shape_and_nulls(columns, rows, shape, match, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor
    from auto_check.modules.dashboard_management.validator import ValidationError

    connection = _Connection(columns, rows)
    _install_driver(monkeypatch, "postgresql", connection)
    with pytest.raises(ValidationError, match=match):
        SqlPreviewExecutor().execute(_source(), "SELECT value", _fields(("value", "integer", False)), shape)


def test_preview_supports_native_six_types_and_mysql_readonly_session(monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    connection = _Connection(
        ["text", "integer", "decimal", "boolean", "day", "moment"],
        [("x", 2, Decimal("3.40"), False, date(2026, 9, 14), datetime(2026, 9, 14, 10, 0))],
    )
    captured = _install_driver(monkeypatch, "mysql", connection)
    preview = SqlPreviewExecutor().execute(_source("mysql"), "SELECT safe_values", _fields(
        ("text", "string", True), ("integer", "integer", False), ("decimal", "decimal", False),
        ("boolean", "boolean", False), ("day", "date", False), ("moment", "datetime", False),
    ), "list")

    assert preview.rows[0] == {
        "text": "x", "integer": 2, "decimal": "3.40", "boolean": False,
        "day": "2026-09-14", "moment": "2026-09-14T10:00:00",
    }
    assert captured["read_timeout"] == 10
    assert connection.calls[:3] == [
        ("SET SESSION sql_mode = %s", ("STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION",)),
        ("SET SESSION TRANSACTION READ ONLY", None),
        ("START TRANSACTION READ ONLY", None),
    ]


@pytest.mark.parametrize("db_type,sql", [
    (
        "mysql",
        """-- 季度特殊处理统计
        SELECT CONCAT(YEAR(special_handling_at), '年第', QUARTER(special_handling_at), '季度') AS quarter,
               COUNT(*) AS special_processing_count
        FROM report_special_processing_records
        WHERE special_handling_at IS NOT NULL
        GROUP BY YEAR(special_handling_at), QUARTER(special_handling_at)
        ORDER BY YEAR(special_handling_at), QUARTER(special_handling_at)""",
    ),
    ("postgresql", "SELECT custom_dashboard_function(value) AS value FROM dashboard_rows"),
    ("postgresql", "SELECT 1 /* safe ; DELETE FROM hidden_table */ AS value"),
    ("mysql", "SELECT 1 AS value; # trailing comment"),
])
def test_preview_accepts_any_single_select_query(db_type, sql, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    columns = ["quarter", "special_processing_count"] if "special_processing_count" in sql else ["value"]
    rows = [("2026年第3季度", 1)] if len(columns) == 2 else [(1,)]
    fields = (
        _fields(("quarter", "string", False), ("special_processing_count", "integer", False))
        if len(columns) == 2
        else _fields(("value", "integer", False))
    )
    connection = _Connection(columns, rows)
    _install_driver(monkeypatch, db_type, connection)

    preview = SqlPreviewExecutor().execute(_source(db_type), sql, fields, "list")

    assert preview.rows
    assert connection.calls[-1] == ("fetchmany", 11)


def test_preview_desensitizes_driver_errors(monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor
    from auto_check.modules.dashboard_management.validator import ValidationError

    class BrokenConnection:
        def cursor(self):
            raise RuntimeError("postgresql://reader:secret@db.internal:5432/dashboard C:/private/driver.py")

        def close(self):
            pass

    _install_driver(monkeypatch, "postgresql", BrokenConnection())
    with pytest.raises(ValidationError, match="查询执行失败") as error:
        SqlPreviewExecutor().execute(_source(), "SELECT safe", _fields(("value", "integer", True)), "list")
    rendered = str(error.value)
    assert "secret" not in rendered and "db.internal" not in rendered and "C:/" not in rendered


@pytest.mark.parametrize(
    ("driver_message", "expected"),
    [
        ('relation "missing_table" does not exist', "查询失败：数据表不存在：missing_table"),
        ("Table 'reporting.missing_table' doesn't exist", "查询失败：数据表不存在：reporting.missing_table"),
        ("Unknown column 'bad_field' in 'field list'", "查询失败：字段不存在：bad_field"),
        ('column "bad_field" does not exist', "查询失败：字段不存在：bad_field"),
        ('syntax error at or near "FROM"', "查询失败：SQL 语法错误，请检查查询语句"),
        ("connection timed out for host db.internal", "查询失败：数据库连接或查询超时"),
        ("Access denied for user 'reader'@'db.internal'", "查询失败：数据库认证或查询权限不足"),
        ("invalid input syntax for type date: 2026/99/99", "查询失败：查询值或日期格式不符合数据库要求"),
    ],
)
def test_preview_returns_safe_specific_driver_error(driver_message, expected, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor
    from auto_check.modules.dashboard_management.validator import ValidationError

    class BrokenConnection:
        def cursor(self):
            raise RuntimeError(driver_message)

        def close(self):
            pass

    _install_driver(monkeypatch, "postgresql", BrokenConnection())
    with pytest.raises(ValidationError) as error:
        SqlPreviewExecutor().execute(
            _source(), "SELECT safe", _fields(("value", "integer", True)), "list"
        )

    rendered = str(error.value)
    assert rendered == expected
    assert "db.internal" not in rendered


def test_postgresql_plain_string_backslash_cannot_hide_second_dblink_statement(monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor
    from auto_check.modules.dashboard_management.validator import ValidationError

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, "postgresql", connection)
    sql = "SELECT 'safe\\'; SELECT dblink_exec('hidden') AS value"

    with pytest.raises(ValidationError, match="只允许单条只读查询"):
        SqlPreviewExecutor().execute(_source(), sql, _fields(("value", "integer", False)), "list")
    assert connection.calls == []


@pytest.mark.parametrize("sql", [
    "SELECT value INTO OUTFILE 'safe' FROM dashboard_rows",
    "SELECT value FROM dashboard_rows FOR UPDATE",
    "SELECT value FROM dashboard_rows FOR SHARE",
    "SELECT value FROM dashboard_rows LOCK IN SHARE MODE",
    "WITH c AS (SELECT 1) VALUES ($$) SELECT $$",
])
def test_preview_rejects_query_write_and_locking_escape_hatches(sql, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor
    from auto_check.modules.dashboard_management.validator import ValidationError

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, "postgresql", connection)

    with pytest.raises(ValidationError, match="只允许单条只读查询"):
        SqlPreviewExecutor().execute(_source(), sql, _fields(("value", "integer", False)), "list")
    assert connection.calls == []


@pytest.mark.parametrize("db_type,sql", [
    ("postgresql", "SELECT $$-- literal; DELETE$$ AS value"),
    ("postgresql", "SELECT 'a;b -- /* */ DELETE' AS value"),
    ("postgresql", "SELECT E'a\\'; DELETE' AS value"),
    ("postgresql", 'SELECT "DELETE;--" AS value'),
    ("mysql", "SELECT `value` AS value"),
    ("postgresql", "SELECT value FROM (SELECT 1 AS value) AS dashboard_rows"),
    ("postgresql", "SELECT COALESCE(ROUND(AVG(value), 2), 0) AS value FROM public.dashboard_rows"),
])
def test_preview_accepts_masked_literals_identifiers_and_query_functions(db_type, sql, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, db_type, connection)

    preview = SqlPreviewExecutor().execute(_source(db_type), sql, _fields(("value", "integer", False)), "list")
    assert preview.rows == ({"value": 1},)
    assert connection.calls[-1] == ("fetchmany", 11)


def test_preview_accepts_recursive_cte_column_list_and_standard_operators(monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, "postgresql", connection)
    sql = "WITH RECURSIVE c(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM c WHERE n < 3) SELECT n || '' AS value FROM c"

    preview = SqlPreviewExecutor().execute(_source(), sql, _fields(("value", "integer", False)), "list")
    assert preview.rows == ({"value": 1},)


@pytest.mark.parametrize("sql", [
    "SELECT CASE WHEN value IN (1, 2) THEN value ELSE 0 END AS value FROM public.dashboard_rows",
    "SELECT value AS value FROM public.dashboard_rows WHERE EXISTS (SELECT 1 FROM public.other_rows)",
    "SELECT SUM(value) FILTER (WHERE value > 0) OVER (PARTITION BY category) AS value FROM public.dashboard_rows",
    "SELECT value AS value FROM (SELECT 1 AS value) AS derived_rows",
])
def test_preview_accepts_only_structurally_identified_syntax_parentheses(sql, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, "postgresql", connection)
    preview = SqlPreviewExecutor().execute(_source(), sql, _fields(("value", "integer", False)), "list")
    assert preview.rows == ({"value": 1},)


@pytest.mark.parametrize("sql", [
    "SELECT EXTRACT(YEAR FROM report_date) AS value FROM public.dashboard_rows",
    "SELECT TRIM(BOTH ' ' FROM value) AS value FROM public.dashboard_rows",
])
def test_preview_does_not_treat_function_internal_from_as_query_source(sql, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, "postgresql", connection)
    preview = SqlPreviewExecutor().execute(_source(), sql, _fields(("value", "integer", False)), "list")
    assert preview.rows == ({"value": 1},)


@pytest.mark.parametrize("sql", [
    "SELECT CAST(value AS custom_type) AS value FROM dashboard_rows",
    "SELECT CONVERT(value, custom_type) AS value FROM dashboard_rows",
    "SELECT value::integer AS value FROM dashboard_rows",
    "SELECT OPERATOR(public.+)(value, 1) AS value FROM dashboard_rows",
    "SELECT value -> 'key' AS value FROM dashboard_rows",
    "SELECT 危险函数() AS value",
    'SELECT "危险函数"() AS value',
])
def test_preview_defers_query_function_cast_and_operator_syntax_to_database(sql, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, "postgresql", connection)
    preview = SqlPreviewExecutor().execute(_source(), sql, _fields(("value", "integer", False)), "list")
    assert preview.rows == ({"value": 1},)


@pytest.mark.parametrize("sql", [
    "SELECT CAST(value AS DECIMAL(18, 2)) AS value FROM dashboard_rows",
    "SELECT CONVERT(value, VARCHAR(64)) AS value FROM dashboard_rows",
])
def test_preview_accepts_builtin_cast_targets_and_precision(sql, monkeypatch):
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    connection = _Connection(["value"], [(1,)])
    _install_driver(monkeypatch, "mysql", connection)
    preview = SqlPreviewExecutor().execute(_source("mysql"), sql, _fields(("value", "integer", False)), "list")
    assert preview.rows == ({"value": 1},)
