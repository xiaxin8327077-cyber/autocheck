from __future__ import annotations

import json
import ssl
from collections.abc import Mapping
from pathlib import Path

import pytest

from auto_check.app.app_database import (
    CURRENT_APP_SCHEMA_VERSION,
    EXPECTED_APP_SCHEMA,
    ApplicationDatabase,
    ApplicationDatabaseConfig,
    ApplicationSchemaError,
)


def _write_config(path: Path, **overrides: object) -> dict[str, object]:
    node: dict[str, object] = {
        "backend": "mysql",
        "host": "127.0.0.1",
        "port": 3306,
        "database": "auto_check",
        "username": "auto_check_app",
        "password": "p@ss:/%{secret}",
        "charset": "utf8mb4",
        "connect_timeout": 12,
        "pool_size": 7,
        "pool_max_overflow": 3,
        "ssl": True,
        "ssl_ca": "C:/certs/mysql-ca.pem",
    }
    node.update(overrides)
    path.write_text(json.dumps({"app_database": node}), encoding="utf-8")
    return node


class _FakeResult:
    def __init__(self, *, rows: list[tuple[object, ...]] | None = None, scalar: object = None):
        self._rows = rows or []
        self._scalar = scalar

    def all(self) -> list[tuple[object, ...]]:
        return self._rows

    def scalar_one(self) -> object:
        if self._scalar is not None:
            return self._scalar
        return self._rows[0][0]

    def scalar_one_or_none(self) -> object:
        return self._scalar


class _FakeConnection:
    def __init__(self, *, version: int | None = CURRENT_APP_SCHEMA_VERSION):
        self.version = version
        self.schema = {table: set(columns) for table, columns in EXPECTED_APP_SCHEMA.items()}
        self.statements: list[tuple[str, Mapping[str, object]]] = []

    def execute(self, statement: object, parameters: Mapping[str, object] | None = None) -> _FakeResult:
        sql = str(statement)
        self.statements.append((sql, parameters or {}))
        normalized = " ".join(sql.lower().split())
        if "information_schema.tables" in normalized:
            return _FakeResult(rows=[(table,) for table in self.schema])
        if "information_schema.columns" in normalized:
            return _FakeResult(
                rows=[
                    (table, column)
                    for table, columns in self.schema.items()
                    for column in columns
                ]
            )
        if "max(version)" in normalized:
            return _FakeResult(scalar=self.version)
        if normalized == "select 1":
            return _FakeResult(scalar=1)
        raise AssertionError(f"unexpected SQL: {sql}")


class _ConnectionContext:
    def __init__(self, connection: _FakeConnection):
        self.connection = connection
        self.exited = False

    def __enter__(self) -> _FakeConnection:
        return self.connection

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.exited = True


class _FakeEngine:
    def __init__(self, connection: _FakeConnection | None = None):
        self.connection = connection or _FakeConnection()
        self.connect_contexts: list[_ConnectionContext] = []
        self.transaction_contexts: list[_ConnectionContext] = []
        self.disposed = False

    def connect(self) -> _ConnectionContext:
        context = _ConnectionContext(self.connection)
        self.connect_contexts.append(context)
        return context

    def begin(self) -> _ConnectionContext:
        context = _ConnectionContext(self.connection)
        self.transaction_contexts.append(context)
        return context

    def dispose(self) -> None:
        self.disposed = True


def _config() -> ApplicationDatabaseConfig:
    return ApplicationDatabaseConfig(
        host="127.0.0.1",
        port=3306,
        database="auto_check",
        username="auto_check_app",
        password="secret",
    )


def _assert_no_ddl(connection: _FakeConnection) -> None:
    ddl_words = {"alter", "create", "drop", "rename", "truncate"}
    assert all(sql.lstrip().split(maxsplit=1)[0].lower() not in ddl_words for sql, _ in connection.statements)


def test_application_database_config_repr_does_not_include_plaintext_password():
    config = _config()

    assert config.password not in repr(config)


def test_from_config_path_loads_valid_mysql_config_and_engine_options(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    expected = _write_config(config_path)
    captured: dict[str, object] = {}
    engine = _FakeEngine()

    def fake_create_engine(url: object, **options: object) -> _FakeEngine:
        captured.update(url=url, options=options)
        return engine

    monkeypatch.setattr("auto_check.app.app_database.create_engine", fake_create_engine)

    database = ApplicationDatabase.from_config_path(config_path)

    assert database.config == ApplicationDatabaseConfig(
        host=expected["host"],
        port=expected["port"],
        database=expected["database"],
        username=expected["username"],
        password=expected["password"],
        charset=expected["charset"],
        connect_timeout=expected["connect_timeout"],
        pool_size=expected["pool_size"],
        pool_max_overflow=expected["pool_max_overflow"],
        ssl=expected["ssl"],
        ssl_ca=expected["ssl_ca"],
    )
    assert captured["options"] == {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 7,
        "max_overflow": 3,
        "connect_args": {
            "connect_timeout": 12,
            "ssl": {
                "ca": "C:/certs/mysql-ca.pem",
                "check_hostname": True,
                "verify_mode": ssl.CERT_REQUIRED,
            },
        },
    }


def test_from_config_path_requires_ssl_ca_when_ssl_enabled(tmp_path):
    config_path = tmp_path / "config.json"
    _write_config(config_path, ssl=True, ssl_ca="")

    with pytest.raises(ValueError, match="ssl_ca"):
        ApplicationDatabase.from_config_path(config_path)


def test_from_config_path_requires_app_database_node(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="app_database"):
        ApplicationDatabase.from_config_path(config_path)


def test_from_config_path_accepts_utf8_bom_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    node = _write_config(config_path)
    config_path.write_text(json.dumps({"app_database": node}), encoding="utf-8-sig")
    monkeypatch.setattr("auto_check.app.app_database.create_engine", lambda *_args, **_kwargs: _FakeEngine())

    database = ApplicationDatabase.from_config_path(config_path)

    assert database.config.database == "auto_check"
    assert database.config.username == "auto_check_app"


def test_from_config_path_requires_mysql_backend(tmp_path):
    config_path = tmp_path / "config.json"
    _write_config(config_path, backend="postgresql")

    with pytest.raises(ValueError, match="仅支持 mysql"):
        ApplicationDatabase.from_config_path(config_path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"port": 0}, "port"),
        ({"port": 65536}, "port"),
        ({"port": True}, "port"),
        ({"connect_timeout": 0}, "connect_timeout"),
        ({"pool_size": 0}, "pool_size"),
        ({"pool_max_overflow": -1}, "pool_max_overflow"),
    ],
)
def test_from_config_path_rejects_invalid_numeric_values(tmp_path, overrides, message):
    config_path = tmp_path / "config.json"
    _write_config(config_path, **overrides)

    with pytest.raises(ValueError, match=message):
        ApplicationDatabase.from_config_path(config_path)


def test_url_create_preserves_special_password_without_interpolation_or_leak(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    node = _write_config(config_path)
    captured: dict[str, object] = {}

    def fake_create_engine(url: object, **options: object) -> _FakeEngine:
        captured["url"] = url
        return _FakeEngine()

    monkeypatch.setattr("auto_check.app.app_database.create_engine", fake_create_engine)

    ApplicationDatabase.from_config_path(config_path)

    url = captured["url"]
    assert url.drivername == "mysql+pymysql"
    assert url.password == node["password"]
    assert url.query["charset"] == "utf8mb4"
    assert node["password"] not in str(url)
    assert "***" in str(url)


def test_expected_schema_is_immutable_and_contains_33_business_tables():
    assert len(EXPECTED_APP_SCHEMA) == 34
    assert "app_schema_version" in EXPECTED_APP_SCHEMA
    assert "storage_migration_runs" in EXPECTED_APP_SCHEMA
    assert all(isinstance(columns, frozenset) for columns in EXPECTED_APP_SCHEMA.values())

    with pytest.raises(TypeError):
        EXPECTED_APP_SCHEMA["users"] = frozenset()


def test_connection_runs_select_one_and_closes_connection_context():
    engine = _FakeEngine()
    database = ApplicationDatabase(_config(), engine=engine)

    database.test_connection()

    assert [" ".join(sql.split()).upper() for sql, _ in engine.connection.statements] == ["SELECT 1"]
    assert engine.connect_contexts[0].exited is True


def test_connect_and_transaction_yield_engine_connections_and_close_disposes_engine():
    engine = _FakeEngine()
    database = ApplicationDatabase(_config(), engine=engine)

    with database.connect() as connection:
        assert connection is engine.connection
    with database.transaction() as connection:
        assert connection is engine.connection
    database.close()

    assert engine.connect_contexts[0].exited is True
    assert engine.transaction_contexts[0].exited is True
    assert engine.disposed is True


def test_validate_schema_accepts_current_complete_schema_without_ddl():
    engine = _FakeEngine()
    database = ApplicationDatabase(_config(), engine=engine)

    database.validate_schema()

    assert all(parameters == {"database": "auto_check"} for _, parameters in engine.connection.statements[:2])
    _assert_no_ddl(engine.connection)


@pytest.mark.parametrize("version", [None, 0, CURRENT_APP_SCHEMA_VERSION + 1])
def test_validate_schema_rejects_schema_version_mismatch_without_ddl(version):
    connection = _FakeConnection(version=version)
    database = ApplicationDatabase(_config(), engine=_FakeEngine(connection))

    with pytest.raises(ApplicationSchemaError, match="版本"):
        database.validate_schema()

    _assert_no_ddl(connection)


def test_validate_schema_rejects_missing_table_without_ddl():
    connection = _FakeConnection()
    del connection.schema["users"]
    database = ApplicationDatabase(_config(), engine=_FakeEngine(connection))

    with pytest.raises(ApplicationSchemaError, match="users"):
        database.validate_schema()

    _assert_no_ddl(connection)


def test_validate_schema_rejects_missing_column_without_ddl():
    connection = _FakeConnection()
    connection.schema["users"].remove("password_hash")
    database = ApplicationDatabase(_config(), engine=_FakeEngine(connection))

    with pytest.raises(ApplicationSchemaError, match="users.password_hash"):
        database.validate_schema()

    _assert_no_ddl(connection)
