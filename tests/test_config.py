from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.dialects import mysql

import auto_check.app.config as config_module
from auto_check.app.config import (
    AppConfig,
    ConfigStore,
    DataSourceConfig,
    DataSourceEntry,
    DbValidationDatasetSettings,
    DbValidationSettings,
    DefaultSettings,
    FlowChainConfig,
    FlowChainStep,
    FlowToolSettings,
    NamedConfig,
    PbcImportToolSettings,
    ReconcileDataSourceSettings,
    default_config,
    flow_tool_settings_from_dict,
    load_config,
    load_store,
    resolve_data_source,
    save_config,
    save_store,
)
from auto_check.app.reconcile_schema import (
    ReconcileSchemaSettings,
    ReconcileSourceRef,
    ReconcileTableSchema,
)
from auto_check.app.storage_config import (
    load_config_snapshot,
    load_data_sources,
    load_setting,
    save_config_snapshot,
    save_data_sources,
    save_setting,
)


class _MemoryResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None):
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> _MemoryResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class _MySqlContractConnection:
    """Small in-memory executor that first compiles every statement as real MySQL SQL."""

    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {
            "data_sources": [],
            "app_settings": [],
            "config_snapshots": [],
        }
        self.sql: list[str] = []
        self.executed_params: list[dict[str, Any]] = []

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> _MemoryResult:
        if isinstance(statement, str):
            raise AssertionError("configuration repository must use SQLAlchemy Core statements")
        compiled = statement.compile(dialect=mysql.dialect())
        sql = str(compiled)
        params = dict(compiled.params)
        if parameters:
            params.update(parameters)
        self.sql.append(sql)
        self.executed_params.append(params)

        table = statement.get_final_froms()[0] if getattr(statement, "is_select", False) else statement.table
        table_name = table.name
        if getattr(statement, "is_delete", False):
            self._delete(table_name, params)
            return _MemoryResult()
        if getattr(statement, "is_insert", False):
            self._insert(table_name, table, params)
            return _MemoryResult()
        if getattr(statement, "is_select", False):
            return self._select(table_name, sql, params)
        raise AssertionError(f"unsupported SQLAlchemy statement: {statement!r}")

    def _delete(self, table_name: str, params: dict[str, Any]) -> None:
        retained_ids = next((value for value in params.values() if isinstance(value, list)), None)
        if retained_ids is None:
            self.tables[table_name] = []
            return
        retained = {str(value) for value in retained_ids}
        self.tables[table_name] = [
            row for row in self.tables[table_name] if str(row.get("id")) in retained
        ]

    def _insert(self, table_name: str, table: Any, params: dict[str, Any]) -> None:
        row = {column.name: params[column.name] for column in table.columns if column.name in params}
        if table_name == "config_snapshots" and "id" not in row:
            row["id"] = len(self.tables[table_name]) + 1
        key_name = "key" if table_name == "app_settings" else "id"
        existing = next(
            (item for item in self.tables[table_name] if item.get(key_name) == row.get(key_name)),
            None,
        )
        if existing is None:
            self.tables[table_name].append(row)
        else:
            created_at = existing.get("created_at")
            existing.update(row)
            if created_at is not None:
                existing["created_at"] = created_at

    def _select(self, table_name: str, sql: str, params: dict[str, Any]) -> _MemoryResult:
        rows = [dict(row) for row in self.tables[table_name]]
        if "count(" in sql.lower():
            return _MemoryResult(scalar=len(rows))
        if table_name == "app_settings" and params:
            key = next(iter(params.values()))
            rows = [row for row in rows if row["key"] == key]
        if table_name == "data_sources":
            rows.sort(key=lambda row: (row["name"], row["id"]))
        if table_name == "config_snapshots":
            rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
        return _MemoryResult(rows=rows)


class _MemoryApplicationDatabase:
    def __init__(self):
        self.connection = _MySqlContractConnection()
        self.transaction_count = 0

    @contextmanager
    def connect(self):
        yield self.connection

    @contextmanager
    def transaction(self):
        before = copy.deepcopy(self.connection.tables)
        self.transaction_count += 1
        try:
            yield self.connection
        except Exception:
            self.connection.tables = before
            raise


@pytest.fixture
def app_database() -> _MemoryApplicationDatabase:
    return _MemoryApplicationDatabase()


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "app_database": {
                    "backend": "mysql",
                    "host": "127.0.0.1",
                    "port": 3306,
                    "database": "auto_check",
                    "username": "auto_check_app",
                    "password": "bootstrap-secret",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _sample_store() -> ConfigStore:
    return ConfigStore(
        data_sources=[
            DataSourceEntry(
                id="source-dws",
                name="DWS",
                config=DataSourceConfig(
                    "postgresql", "127.0.0.1", 5432, "dwdb", "dws", "reader", "DwsSecret1"
                ),
                is_default=True,
            ),
            DataSourceEntry(
                id="source-report",
                name="Report",
                config=DataSourceConfig(
                    "mysql", "127.0.0.2", 3306, "reportdb", "", "writer", "ReportSecret1"
                ),
            ),
        ],
        reconcile_data_sources=ReconcileDataSourceSettings(
            dws_source_id="source-dws",
            business_source_id="source-report",
        ),
        default_name="DWS",
        default_settings=DefaultSettings(
            session_expire_hours=6,
            page_size=30,
            combination_limit=25,
            auto_refresh_home=True,
            visual_effects=False,
            theme="light",
            dark_mode=True,
        ),
        pbc_import_tool=PbcImportToolSettings(
            recent_tables=["dws.aainfo", "dws.public_information_rh"],
            last_config_name="DWS",
            last_source="business",
        ),
        db_validation=DbValidationSettings(
            detail=DbValidationDatasetSettings(
                source_id="source-dws",
                sys_manage_id="DETAIL_SYS",
                classification_id="DETAIL_CLASS",
            ),
            public_info=DbValidationDatasetSettings(source_id="source-report"),
            template=DbValidationDatasetSettings(source_id="source-dws"),
            field_mapping_source_id="source-dws",
            baseinfo_table="xt_reg_table_baseinfo_custom",
            field_info_table="xt_reg_table_field_info_custom",
            public_info_table="public_information_rh_custom",
        ),
        flow_tool=FlowToolSettings(
            source_id="source-dws",
            execute_url="http://127.0.0.1:9000/execute",
            poll_interval_seconds=3,
            step_timeout_minutes=20,
            chains=[
                FlowChainConfig(
                    id="chain-1",
                    name="每日链路",
                    enabled=True,
                    steps=[FlowChainStep(flow_id="flow-a", name="步骤A")],
                )
            ],
        ),
        reconcile_schema=ReconcileSchemaSettings(
            strict=True,
            tables={
                "account_balance": ReconcileTableSchema(
                    source_ref=ReconcileSourceRef(id="source-dws", name="DWS"),
                    table="fa_accountbalance_dws",
                    fields={"project_code": "projectcode"},
                )
            },
        ),
    )


def test_configuration_repository_uses_mysql_core_contract(app_database, monkeypatch):
    monkeypatch.setenv("AUTO_CHECK_SECRET_KEY", "unit-test-secret")
    store = _sample_store()

    with app_database.transaction() as connection:
        save_data_sources(connection, store.data_sources)
        save_setting(connection, "stable", {"b": 2, "a": [1, {"z": False}]})
        save_config_snapshot(connection, {"b": 2, "a": 1})

    with app_database.connect() as connection:
        sources = load_data_sources(connection)
        setting = load_setting(connection, "stable", {})
        snapshot = load_config_snapshot(connection)

    assert sources == store.data_sources
    assert setting == {"a": [1, {"z": False}], "b": 2}
    assert snapshot["payload"] == {"a": 1, "b": 2}
    assert len(snapshot["fingerprint"]) == 64
    assert isinstance(snapshot["created_at"], datetime)
    assert app_database.transaction_count == 1

    statements = "\n".join(app_database.connection.sql)
    assert "ON DUPLICATE KEY UPDATE" in statements
    assert "rowid" not in statements.lower()
    assert "ORDER BY" in statements
    assert "CREATE " not in statements.upper()
    assert app_database.connection.tables["app_settings"][0]["value_json"] == (
        '{"a":[1,{"z":false}],"b":2}'
    )
    assert app_database.connection.tables["config_snapshots"][0]["payload_json"] == (
        '{"a":1,"b":2}'
    )
    encrypted = [row["password_encrypted"] for row in app_database.connection.tables["data_sources"]]
    assert all(value.startswith("aesgcm$") for value in encrypted)
    assert all("Secret1" not in value for value in encrypted)
    datetime_values = [
        value
        for params in app_database.connection.executed_params
        for value in params.values()
        if isinstance(value, datetime)
    ]
    assert datetime_values


def test_store_round_trip_keeps_all_dynamic_settings_in_mysql(app_database, config_path):
    store = _sample_store()

    save_store(store, config_path, database=app_database)
    loaded = load_store(config_path, database=app_database)

    assert loaded == store
    assert resolve_data_source(loaded, "source-dws").db_type == "postgresql"
    assert resolve_data_source(loaded, "source-report").db_type == "mysql"
    assert len(app_database.connection.tables["config_snapshots"]) == 1


def test_save_store_does_not_overwrite_bootstrap_config(app_database, config_path):
    before = config_path.read_bytes()

    save_store(_sample_store(), config_path, database=app_database)

    assert config_path.read_bytes() == before


def test_runtime_ignores_legacy_dynamic_json_and_never_reads_sqlite(
    app_database, config_path, monkeypatch
):
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["data_sources"] = [
        {
            "id": "legacy-json",
            "name": "must be ignored",
            "db_type": "postgresql",
            "host": "legacy",
            "port": 5432,
            "database": "legacy",
            "schema": "dws",
            "username": "legacy",
            "password": "legacy",
        }
    ]
    payload["default_settings"] = {"page_size": 99}
    config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def fail_sqlite(*_args, **_kwargs):
        raise AssertionError("runtime configuration must not access SQLite/app_kv")

    monkeypatch.setattr(config_module, "_connect", fail_sqlite, raising=False)
    monkeypatch.setattr(config_module, "read_app_value", fail_sqlite, raising=False)

    loaded = load_store(config_path, database=app_database)

    assert loaded.data_sources == []
    assert loaded.default_settings.page_size == DefaultSettings().page_size
    assert not (config_path.parent / "auto-check.db").exists()


def test_save_store_never_creates_sqlite_database(app_database, config_path):
    save_store(_sample_store(), config_path, database=app_database)

    assert not (config_path.parent / "auto-check.db").exists()
    assert "app_kv" not in "\n".join(app_database.connection.sql)


def test_save_and_load_single_config_round_trip(app_database, config_path):
    config = AppConfig(
        dws=DataSourceConfig(
            "postgresql", "127.0.0.1", 5432, "dwsdb", "dws", "user1", "pass1"
        ),
        business=DataSourceConfig(
            "mysql", "127.0.0.2", 3306, "bizdb", "", "user2", "pass2"
        ),
    )

    save_config(config, config_path, database=app_database)
    loaded = load_config(config_path, database=app_database)

    assert loaded == config


def test_empty_mysql_configuration_returns_defaults_without_fallback(app_database, config_path):
    loaded = load_config(config_path, database=app_database)

    assert loaded == default_config()
    assert not (config_path.parent / "auto-check.db").exists()


def test_grouped_legacy_model_is_normalized_before_mysql_save(app_database, config_path):
    store = ConfigStore(
        configs=[
            NamedConfig(
                name="对账数据源",
                dws=DataSourceConfig(
                    "postgresql", "127.0.0.1", 5432, "dwsdb", "dws", "reader", "dws-secret"
                ),
                business=DataSourceConfig(
                    "mysql", "127.0.0.2", 3306, "bizdb", "", "writer", "biz-secret"
                ),
                is_default=True,
            ),
            NamedConfig(
                name="逐笔校验数据源",
                dws=DataSourceConfig(
                    "postgresql", "127.0.0.3", 5432, "metadb", "test", "meta", "meta-secret"
                ),
                business=DataSourceConfig(
                    "postgresql", "127.0.0.4", 5432, "unused", "dws", "unused", "unused-secret"
                ),
            ),
        ],
        default_name="对账数据源",
        db_validation=DbValidationSettings(
            detail=DbValidationDatasetSettings(
                config_name="逐笔校验数据源",
                source="dws",
                sys_manage_id="DETAIL_SYS",
                classification_id="DETAIL_CLASS",
            ),
            field_mapping_config_name="逐笔校验数据源",
            field_mapping_source="dws",
        ),
    )

    save_store(store, config_path, database=app_database)
    loaded = load_store(config_path, database=app_database)

    assert {entry.id for entry in loaded.data_sources} == {
        "legacy:对账数据源:dws",
        "legacy:对账数据源:business",
        "legacy:逐笔校验数据源:dws",
        "legacy:逐笔校验数据源:business",
    }
    assert loaded.reconcile_data_sources == ReconcileDataSourceSettings(
        dws_source_id="legacy:对账数据源:dws",
        business_source_id="legacy:对账数据源:business",
    )
    assert loaded.db_validation.detail.source_id == "legacy:逐笔校验数据源:dws"
    assert loaded.db_validation.field_mapping_source_id == "legacy:逐笔校验数据源:dws"
    assert resolve_data_source(loaded, "legacy:对账数据源:dws").password == "dws-secret"
    assert resolve_data_source(loaded, "legacy:对账数据源:business").password == "biz-secret"


def test_configuration_api_requires_explicit_shared_database(config_path):
    with pytest.raises(RuntimeError, match="ApplicationDatabase"):
        load_store(config_path)

    with pytest.raises(RuntimeError, match="ApplicationDatabase"):
        save_store(ConfigStore(), config_path)


def test_default_config_has_two_supported_source_types():
    config = default_config()

    assert config.dws.db_type == "postgresql"
    assert config.business.db_type == "mysql"
    assert config.dws.schema == "dws"
    assert config.business.schema == ""


def test_store_persists_default_settings(app_database, config_path):
    store = ConfigStore(
        default_settings=DefaultSettings(
            session_expire_hours=12,
            page_size=20,
            combination_limit=50,
            auto_refresh_home=True,
            theme="space-tech",
            dark_mode=True,
        )
    )

    save_store(store, config_path, database=app_database)
    loaded = load_store(config_path, database=app_database)

    assert loaded.default_settings == store.default_settings


def test_store_persists_pbc_import_tool_settings(app_database, config_path):
    store = ConfigStore(
        pbc_import_tool=PbcImportToolSettings(
            recent_tables=["dws.public_information_th", "dws.aainfo"],
            last_config_name="local",
            last_source="dws",
        )
    )

    save_store(store, config_path, database=app_database)
    loaded = load_store(config_path, database=app_database)

    assert loaded.pbc_import_tool == store.pbc_import_tool


def test_store_persists_reconcile_schema_settings(app_database, config_path):
    store = ConfigStore(
        reconcile_schema=ReconcileSchemaSettings(
            version=1,
            strict=True,
            tables={
                "fa_valuation": ReconcileTableSchema(
                    source_ref=ReconcileSourceRef(
                        id="source-dws", name="生产DWS", match_by="id_then_name"
                    ),
                    table="dw.fa_valuation_custom",
                    display_name="FA估值自定义表",
                    fields={
                        "project_code": "proj_code",
                        "valuation_date": "val_date",
                        "account_code": "acct_code",
                        "account_name": "acct_name",
                        "market_value": "market_amt",
                    },
                )
            },
        )
    )

    save_store(store, config_path, database=app_database)
    loaded = load_store(config_path, database=app_database)

    table = loaded.reconcile_schema.tables["fa_valuation"]
    assert table.source_ref.id == "source-dws"
    assert table.table == "dw.fa_valuation_custom"
    assert table.fields["market_value"] == "market_amt"
    assert loaded.reconcile_schema.strict is True


def test_load_store_ignores_reconcile_schema_yaml_until_page_initializes_it(
    app_database, config_path
):
    save_store(ConfigStore(), config_path, database=app_database)
    config_path.with_name("reconcile-schema.yaml").write_text(
        """
reconcile_schema:
  version: 1
  tables:
    fa_valuation:
      source_ref:
        id: "source-dws"
        name: "DWS"
      table: custom.fa_valuation_custom
      fields:
        project_code: proj_code
""".strip(),
        encoding="utf-8",
    )

    loaded = load_store(config_path, database=app_database)

    assert loaded.reconcile_schema.tables == {}


def test_load_store_keeps_mysql_reconcile_schema_when_yaml_template_exists(
    app_database, config_path
):
    save_store(
        ConfigStore(
            reconcile_schema=ReconcileSchemaSettings(
                version=1,
                strict=True,
                tables={
                    "fa_valuation": ReconcileTableSchema(
                        source_ref=ReconcileSourceRef(id="system-dws", name="system"),
                        table="system.fa_valuation",
                        fields={"market_value": "system_amt"},
                    )
                },
            )
        ),
        config_path,
        database=app_database,
    )
    config_path.with_name("reconcile-schema.yaml").write_text(
        """
reconcile_schema:
  version: 1
  tables:
    fa_valuation:
      source_ref:
        id: "yaml-dws"
      table: yaml.fa_valuation
      fields:
        market_value: yaml_amt
""".strip(),
        encoding="utf-8",
    )

    loaded = load_store(config_path, database=app_database)

    table = loaded.reconcile_schema.tables["fa_valuation"]
    assert table.source_ref.id == "system-dws"
    assert table.table == "system.fa_valuation"
    assert table.fields["market_value"] == "system_amt"
    assert loaded.reconcile_schema.strict is True


def test_store_persists_flow_tool_settings_without_schedule_fields(app_database, config_path):
    store = ConfigStore(
        flow_tool=FlowToolSettings(
            source_id="source-report",
            execute_url="http://192.168.107.81/assmag/spiderFlow/spider/testRun",
            flow_table="sp_flow",
            task_table="sp_task",
            poll_interval_seconds=3,
            step_timeout_minutes=45,
            chains=[
                FlowChainConfig(
                    id="chain-zgxg-1",
                    name="资管新规1",
                    enabled=True,
                    steps=[
                        FlowChainStep(flow_id="flow-a", name="流程A"),
                        FlowChainStep(flow_id="flow-b", name="流程B"),
                    ],
                ),
                FlowChainConfig(
                    id="chain-zgxg-2",
                    name="资管新规2",
                    enabled=False,
                    steps=[FlowChainStep(flow_id="flow-c", name="流程C")],
                ),
            ],
        )
    )

    save_store(store, config_path, database=app_database)
    loaded = load_store(config_path, database=app_database)
    snapshot = load_config_snapshot(app_database.connection)

    assert loaded.flow_tool == store.flow_tool
    chain_payload = snapshot["payload"]["flow_tool"]["chains"][0]
    assert "schedule_enabled" not in chain_payload
    assert "schedule_cron" not in chain_payload
    assert "schedule_time" not in chain_payload


def test_legacy_flow_chain_schedule_fields_are_ignored_by_parser():
    settings = flow_tool_settings_from_dict(
        {
            "source_id": "source-report",
            "chains": [
                {
                    "id": "chain-zgxg-1",
                    "name": "资管新规1",
                    "enabled": True,
                    "schedule_enabled": True,
                    "schedule_cron": "0 7 * * *",
                    "schedule_time": "07:00",
                    "steps": [{"flow_id": "flow-a", "name": "流程A"}],
                }
            ],
        }
    )

    chain = settings.chains[0]
    assert chain.id == "chain-zgxg-1"
    assert chain.enabled is True
    assert not hasattr(chain, "schedule_enabled")
    assert not hasattr(chain, "schedule_cron")
    assert not hasattr(chain, "schedule_time")


def test_store_persists_single_data_sources_and_validation_fields(app_database, config_path):
    store = ConfigStore(
        data_sources=[
            DataSourceEntry(
                id="source-detail",
                name="逐笔库",
                config=DataSourceConfig(
                    "postgresql", "127.0.0.1", 5432, "detaildb", "dws", "reader", "secret"
                ),
                is_default=True,
            ),
            DataSourceEntry(
                id="source-business",
                name="报表库",
                config=DataSourceConfig(
                    "mysql", "127.0.0.2", 3306, "bizdb", "", "writer", "biz-secret"
                ),
            ),
        ],
        reconcile_data_sources=ReconcileDataSourceSettings(
            dws_source_id="source-detail",
            business_source_id="source-business",
        ),
        db_validation=DbValidationSettings(
            detail=DbValidationDatasetSettings(
                source_id="source-detail",
                sys_manage_id="DETAIL_SYS",
                classification_id="DETAIL_CLASS",
            ),
            public_info=DbValidationDatasetSettings(
                source_id="source-business",
                sys_manage_id="PUBLIC_SYS",
                classification_id="PUBLIC_CLASS",
            ),
            template=DbValidationDatasetSettings(
                source_id="source-detail",
                sys_manage_id="TEMPLATE_SYS",
                classification_id="TEMPLATE_CLASS",
            ),
            field_mapping_source_id="source-detail",
            baseinfo_table="xt_reg_table_baseinfo_custom",
            field_info_table="xt_reg_table_field_info_custom",
            public_info_table="public_information_rh_custom",
        ),
    )

    save_store(store, config_path, database=app_database)
    loaded = load_store(config_path, database=app_database)

    assert {entry.id: entry for entry in loaded.data_sources} == {
        entry.id: entry for entry in store.data_sources
    }
    assert loaded.reconcile_data_sources == store.reconcile_data_sources
    assert loaded.db_validation == store.db_validation
    assert resolve_data_source(loaded, "source-detail").database == "detaildb"
