from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields

import pytest

from auto_check.app.config import DataSourceConfig, DataSourceEntry
from auto_check.app.data_source_platform import (
    PublicDataSource,
    _bind_named_params,
    create_data_source_service,
)
from auto_check.app.module_system.services import ServiceRegistry


SECRET = "super-secret-password"
HOST = "10.1.2.3"
USERNAME = "db_admin"


class _ApplicationDatabase:
    @contextmanager
    def connect(self):
        yield object()


def _entry() -> DataSourceEntry:
    return DataSourceEntry(
        id="src-1",
        name="报表库",
        config=DataSourceConfig(
            db_type="mysql",
            host=HOST,
            port=3306,
            database="biz",
            schema="biz",
            username=USERNAME,
            password=SECRET,
        ),
    )


def _install_sources(monkeypatch, entries: list[DataSourceEntry]) -> None:
    monkeypatch.setattr(
        "auto_check.app.data_source_platform.load_data_sources",
        lambda _connection: list(entries),
    )


def _facade(monkeypatch, connector=None):
    _install_sources(monkeypatch, [_entry()])
    registry = ServiceRegistry()
    registry.register_platform(
        create_data_source_service(_ApplicationDatabase(), connector=connector)
    )
    services = registry.for_module(
        "data_validation",
        service_dependencies={"platform.data_sources": 1},
    )
    return services, services.resolve("platform.data_sources", 1)


def test_list_sources_omits_credentials(monkeypatch):
    _services, facade = _facade(monkeypatch)
    sources = facade.list_sources()

    assert {field.name for field in fields(PublicDataSource)} == {
        "id",
        "name",
        "dialect",
        "database_name",
        "schema_name",
    }
    assert sources == (
        PublicDataSource(
            id="src-1",
            name="报表库",
            dialect="mysql",
            database_name="biz",
            schema_name="biz",
        ),
    )
    visible = repr(facade) + repr(sources)
    assert SECRET not in visible
    assert HOST not in visible
    assert USERNAME not in visible


def test_describe_table_mapping_version_changes_when_column_changes(monkeypatch):
    columns = [("id", "int", "", "YES")]

    def connector(_config, _sql, _params, _timeout_seconds, _max_rows):
        return (("column_name", "data_type", "comment", "nullable"), tuple(columns))

    _services, facade = _facade(monkeypatch, connector)
    first = facade.describe_table("src-1", "loan")
    columns.append(("customer_name", "varchar", "客户名称", "NO"))
    second = facade.describe_table("src-1", "loan")

    assert first["mapping_version"] != second["mapping_version"]
    assert [column["column_name"] for column in second["columns"]] == [
        "id",
        "customer_name",
    ]


def test_execute_select_rejects_write_before_connect(monkeypatch):
    calls: list[str] = []

    def connector(_config, sql, _params, _timeout_seconds, _max_rows):
        calls.append(sql)
        raise AssertionError("business connection must not be opened")

    _services, facade = _facade(monkeypatch, connector)
    statements = (
        "DELETE FROM loan",
        "SELECT 1; DELETE FROM loan",
        "SELECT pg_read_file('a')",
    )
    for statement in statements:
        with pytest.raises(ValueError, match="SQL_POLICY_DENIED"):
            facade.execute_select(
                "src-1",
                statement,
                {},
                timeout_seconds=5,
                max_rows=10,
            )
    assert calls == []


def test_execute_select_marks_truncation(monkeypatch):
    def connector(_config, _sql, _params, _timeout_seconds, _max_rows):
        return (("business_key",), (("a",), ("b",)))

    _services, facade = _facade(monkeypatch, connector)
    result = facade.execute_select(
        "src-1",
        "SELECT business_key FROM loan",
        {},
        timeout_seconds=5,
        max_rows=1,
    )

    assert result.truncated is True
    assert result.columns == ("business_key",)
    assert result.rows == (("a",),)


def test_closed_facade_rejects_calls(monkeypatch):
    services, facade = _facade(monkeypatch, lambda *_args: ((), ()))
    services.close()

    with pytest.raises(RuntimeError, match="platform service facade is closed"):
        facade.list_sources()
    with pytest.raises(RuntimeError, match="platform service facade is closed"):
        facade.list_tables("src-1", keyword="", page=1, page_size=20)
    with pytest.raises(RuntimeError, match="platform service facade is closed"):
        facade.describe_table("src-1", "loan")
    with pytest.raises(RuntimeError, match="platform service facade is closed"):
        facade.execute_select(
            "src-1",
            "SELECT 1",
            {},
            timeout_seconds=5,
            max_rows=1,
        )


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_binding_only_substitutes_unquoted_names_and_preserves_order(dialect):
    sql = """SELECT 'status:active 50%', 'O''Brien:code', "col"":literal", :day, :value, :day"""
    expected = """SELECT 'status:active 50%%', 'O''Brien:code', "col"":literal", %s, %s, %s"""
    assert _bind_named_params(sql, {"value": None, "day": "2026-11-20"}, dialect) == (
        expected, ("2026-11-20", None, "2026-11-20"),
    )


@pytest.mark.parametrize("dialect,sql,expected", [
    ("mysql", "SELECT 10--:n", "SELECT 10--%s"),
    ("mysql", "SELECT 10--- :unused\n + :n", "SELECT 10--- :unused\n + %s"),
    ("mysql", "SELECT :n # :unused%\n", "SELECT %s # :unused%%\n"),
    ("mysql", "SELECT `o``:id`, :n",
     "SELECT `o``:id`, %s"),
    ("mysql", "SELECT :n /* note :other */", "SELECT %s /* note :other */"),
    ("postgresql", "SELECT 10--note :skip\r + :n", "SELECT 10--note :skip\r + %s"),
    ("postgresql", "SELECT /* outer /* inner */ :skip */ :n", "SELECT /* outer /* inner */ :skip */ %s"),
    ("postgresql", "SELECT :n::integer, $$:quoted %$$, $甲$:q$甲$",
     "SELECT %s::integer, $$:quoted %%$$, $甲$:q$甲$"),
    ("postgresql", "SELECT col$tag$ || :n", "SELECT col$tag$ || %s"),
    ("postgresql", "SELECT 7 # :n", "SELECT 7 # %s"),
    ("postgresql", r"SELECT E'O\'Brien:ignored', :n", r"SELECT E'O\'Brien:ignored', %s"),
    ("postgresql", "SELECT E'first' -- joined\n" + r"'O\'Brien:ignored', :n",
     "SELECT E'first' -- joined\n" + r"'O\'Brien:ignored', %s"),
])
def test_named_parameter_dialect_syntax(dialect, sql, expected):
    assert _bind_named_params(sql, {"n": 3}, dialect) == (expected, (3,))


@pytest.mark.parametrize("dialect,sql", [
    ("mysql", "SELECT ':missing', :required"),
    ("postgresql", 'SELECT "a:b", :required::date'),
    ("mysql", "SELECT 1 /*!80000 + :conditional */"),
    ("postgresql", "SELECT $tag$unfinished"),
])
def test_binding_refuses_missing_or_ambiguous_parameters(dialect, sql):
    with pytest.raises(ValueError, match="VALIDATION_ERROR"):
        _bind_named_params(sql, {}, dialect)


@pytest.mark.parametrize("dialect,mode,sql,expected", [
    ("mysql", "", r"SELECT 'O\'Brien:id', :n", r"SELECT 'O\'Brien:id', %s"),
    ("mysql", "NO_BACKSLASH_ESCAPES", r"SELECT 'tail\', :n", r"SELECT 'tail\', %s"),
    ("mysql", "ANSI_QUOTES", r'''SELECT "column\", :n''', r'''SELECT "column\", %s'''),
    ("postgresql", "on", r"SELECT 'tail\', :n::integer", r"SELECT 'tail\', %s::integer"),
    ("postgresql", "off", r"SELECT 'O\'Brien:id', :n", r"SELECT 'O\'Brien:id', %s"),
    ("mysql", "", "SELECT 'x:y', :n", "SELECT 'x:y', %s"),
    ("postgresql", "on", "SELECT 'x:y', :n", "SELECT 'x:y', %s"),
])
def test_source_query_uses_session_quoting_and_driver_format(monkeypatch, dialect, mode, sql, expected):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from auto_check.app import data_source_platform as platform

    cursor = MagicMock()
    cursor.fetchone.return_value = (mode,)
    cursor.description = (("value",),)
    cursor.fetchmany.return_value = [(2,)]
    info = MagicMock()
    info.parameter_status.return_value = mode
    connection = SimpleNamespace(cursor=lambda: cursor, info=info)
    monkeypatch.setattr(platform, "_connect", lambda *_args: nullcontext(connection))
    monkeypatch.setattr(platform, "_apply_timeout", lambda *_args: None)
    assert platform.query_business_source(SimpleNamespace(db_type=dialect), sql, {"n": 2}, 5, 1) == (
        ("value",), ((2,),),
    )
    assert cursor.execute.call_args_list[-1].args == (expected, (2,))
    if dialect == "mysql" and "\\" in sql:
        assert cursor.execute.call_args_list[0].args == ("SELECT @@SESSION.sql_mode",)
    else:
        assert cursor.execute.call_count == 1
    if dialect == "postgresql" and "\\" in sql:
        info.parameter_status.assert_called_once_with("standard_conforming_strings")
    else:
        info.parameter_status.assert_not_called()
