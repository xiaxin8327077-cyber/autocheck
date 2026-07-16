import pytest
from contextlib import contextmanager

import auto_check.app.db as db_module
from auto_check.app.config import DataSourceConfig
from auto_check.app.db import (
    DatabaseClient,
    build_clear_table_sql,
    build_insert_sql,
    ensure_select_only,
    qualified_name,
)
from auto_check.app.pbc_import import parse_table_ref


def test_ensure_select_only_allows_select_and_with():
    ensure_select_only("select * from table_name")
    ensure_select_only("  WITH data AS (select 1) select * from data")


def test_ensure_select_only_rejects_writes():
    with pytest.raises(ValueError, match="Only SELECT"):
        ensure_select_only("delete from table_name")


def test_ensure_select_only_rejects_stacked_or_write_keywords():
    for sql in [
        "SELECT 1; DROP TABLE users",
        "WITH deleted AS (DELETE FROM users RETURNING *) SELECT * FROM deleted",
        "SELECT * FROM users WHERE id = 1 -- DROP TABLE users",
    ]:
        with pytest.raises(ValueError, match="Only SELECT"):
            ensure_select_only(sql)


def test_qualified_name_quotes_schema_for_postgresql():
    config = DataSourceConfig("postgresql", "localhost", 5432, "db", "dws", "u", "p")

    assert qualified_name(config, "fa_accountbalance_dws") == '"dws"."fa_accountbalance_dws"'


def test_qualified_name_quotes_database_for_mysql():
    config = DataSourceConfig("mysql", "localhost", 3306, "biz", "", "u", "p")

    assert qualified_name(config, "currency_report_duration") == "`biz`.`currency_report_duration`"


def test_quote_identifier_accepts_plain_configured_names_and_rejects_sql_fragments():
    assert hasattr(db_module, "quote_identifier"), "quote_identifier is missing"
    assert db_module.quote_identifier("mysql", "ck_result") == "`ck_result`"
    assert db_module.quote_identifier("postgresql", "version_num") == '"version_num"'

    for unsafe in ("ck_result; DROP TABLE users", "table name", "schema.table", "a`b"):
        with pytest.raises(ValueError, match="非法标识符"):
            db_module.quote_identifier("mysql", unsafe)


def test_import_sql_quotes_table_and_column_identifiers():
    table = parse_table_ref("dws.aainfo")

    assert build_insert_sql("postgresql", table, ["product_code", "product_name"]) == (
        'INSERT INTO "dws"."aainfo" ("product_code", "product_name") VALUES (%s, %s)'
    )
    assert build_insert_sql("mysql", table, ["product_code", "product_name"]) == (
        "INSERT INTO `dws`.`aainfo` (`product_code`, `product_name`) VALUES (%s, %s)"
    )
    assert build_clear_table_sql("postgresql", table) == 'TRUNCATE TABLE "dws"."aainfo"'


def test_bulk_insert_reuses_one_connection_for_large_import(monkeypatch):
    config = DataSourceConfig("postgresql", "localhost", 5432, "db", "dws", "u", "p")
    client = DatabaseClient(config)
    table = parse_table_ref("dws.aainfo")
    state = {"connects": 0, "commits": 0, "batches": []}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, _sql, rows):
            state["batches"].append(len(rows))

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            state["commits"] += 1

    @contextmanager
    def fake_connect(_self):
        state["connects"] += 1
        yield FakeConnection()

    monkeypatch.setattr(DatabaseClient, "_connect", fake_connect)

    rows = ((idx, f"P{idx}") for idx in range(10005))
    inserted = client.insert_row_batches(table, ["id", "product_code"], rows, batch_size=5000)

    assert inserted == 10005
    assert state["connects"] == 1
    assert state["commits"] == 1
    assert state["batches"] == [5000, 5000, 5]


def test_write_operations_qualify_single_part_table_with_config_schema(monkeypatch):
    config = DataSourceConfig("postgresql", "localhost", 5432, "db", "dws", "u", "p")
    client = DatabaseClient(config)
    table = parse_table_ref("public_information_rh")
    state = {"execute_sql": "", "insert_sql": ""}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql):
            state["execute_sql"] = sql

        def executemany(self, sql, rows):
            state["insert_sql"] = sql

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    @contextmanager
    def fake_connect(_self):
        yield FakeConnection()

    monkeypatch.setattr(DatabaseClient, "_connect", fake_connect)

    client.clear_table(table)
    client.insert_row_batches(table, ["productcode"], [("P1",)])

    assert state["execute_sql"] == 'TRUNCATE TABLE "dws"."public_information_rh"'
    assert state["insert_sql"] == 'INSERT INTO "dws"."public_information_rh" ("productcode") VALUES (%s)'


def test_write_operations_keep_explicit_schema_table(monkeypatch):
    config = DataSourceConfig("postgresql", "localhost", 5432, "db", "dws", "u", "p")
    client = DatabaseClient(config)
    table = parse_table_ref("test.public_information_rh")
    state = {"execute_sql": "", "insert_sql": ""}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql):
            state["execute_sql"] = sql

        def executemany(self, sql, rows):
            state["insert_sql"] = sql

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    @contextmanager
    def fake_connect(_self):
        yield FakeConnection()

    monkeypatch.setattr(DatabaseClient, "_connect", fake_connect)

    client.clear_table(table)
    client.insert_row_batches(table, ["productcode"], [("P1",)])

    assert state["execute_sql"] == 'TRUNCATE TABLE "test"."public_information_rh"'
    assert state["insert_sql"] == 'INSERT INTO "test"."public_information_rh" ("productcode") VALUES (%s)'
