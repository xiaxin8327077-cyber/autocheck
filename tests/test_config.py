import json
import sqlite3

from auto_check.app.config import (
    AppConfig,
    ConfigStore,
    DataSourceEntry,
    DataSourceConfig,
    DefaultSettings,
    DbValidationDatasetSettings,
    DbValidationSettings,
    FlowChainConfig,
    FlowChainStep,
    FlowToolSettings,
    NamedConfig,
    PbcImportToolSettings,
    ReconcileDataSourceSettings,
    default_config,
    load_config,
    load_store,
    resolve_data_source,
    save_config,
    save_store,
)
from auto_check.app.reconcile_schema import (
    ReconcileSourceRef,
    ReconcileTableSchema,
    ReconcileSchemaSettings,
)
from auto_check.app.local_store import db_path_for_config, read_app_value, write_app_value


def test_local_store_creates_v2_storage_schema(tmp_path):
    import sqlite3

    from auto_check.app.storage_schema import CURRENT_SCHEMA_VERSION, get_schema_version

    path = tmp_path / "config.json"
    read_app_value(path, "missing")

    db_path = db_path_for_config(path)
    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "schema_migrations" in tables
    assert "storage_migration_runs" in tables
    assert "data_sources" in tables
    assert "users" in tables
    assert "run_headers" in tables
    assert "reconcile_results" in tables
    assert "db_validation_runs" in tables
    assert "db_validation_selected_tables" in tables
    assert "db_validation_warnings" in tables
    assert "db_validation_result_rows" in tables
    assert "flow_chain_runs" in tables
    assert "flow_chain_run_steps" in tables
    assert "flow_chain_run_logs" in tables
    assert "flow_chain_run_details" in tables
    assert get_schema_version(db_path) == CURRENT_SCHEMA_VERSION


def test_local_store_adds_remaining_history_tables_to_existing_v2_database(tmp_path):
    from auto_check.app.storage_schema import CURRENT_SCHEMA_VERSION

    path = tmp_path / "config.json"
    db_path = db_path_for_config(path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, '2026-07-03 10:00:00')",
            (CURRENT_SCHEMA_VERSION,),
        )

    read_app_value(path, "missing")

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {
        "db_validation_runs",
        "db_validation_selected_tables",
        "db_validation_warnings",
        "db_validation_result_rows",
        "flow_chain_runs",
        "flow_chain_run_steps",
        "flow_chain_run_logs",
        "flow_chain_run_details",
    } <= tables


def test_read_app_value_does_not_run_schema_migration_when_database_is_current_and_locked(tmp_path):
    path = tmp_path / "config.json"
    db_path = db_path_for_config(path)
    committed_payload = {"default_settings": {"session_expire_hours": 8}, "marker": "committed"}
    write_app_value(path, "config_store", committed_payload)

    writer = sqlite3.connect(db_path, timeout=1)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("BEGIN IMMEDIATE")
    writer.execute(
        "UPDATE app_kv SET value = ? WHERE key = 'config_store'",
        (json.dumps({"marker": "uncommitted"}, ensure_ascii=False),),
    )
    try:
        assert read_app_value(path, "config_store") == committed_payload
    finally:
        writer.rollback()
        writer.close()


def test_load_config_from_normalized_sqlite_does_not_write_snapshot_when_locked(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(
        data_sources=[
            DataSourceEntry(
                id="source-dws",
                name="local DWS",
                config=DataSourceConfig("postgresql", "localhost", 5432, "dwdb", "dws", "reader", "secret"),
                is_default=True,
            ),
            DataSourceEntry(
                id="source-business",
                name="local business",
                config=DataSourceConfig("mysql", "localhost", 3306, "bizdb", "", "writer", "biz-secret"),
            ),
        ],
        reconcile_data_sources=ReconcileDataSourceSettings(
            dws_source_id="source-dws",
            business_source_id="source-business",
        ),
    )
    save_store(store, path)

    db_path = db_path_for_config(path)
    writer = sqlite3.connect(db_path, timeout=1)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("BEGIN IMMEDIATE")
    writer.execute(
        "UPDATE app_kv SET value = ? WHERE key = 'config_store'",
        (json.dumps({"marker": "uncommitted"}, ensure_ascii=False),),
    )
    try:
        loaded = load_config(path)
    finally:
        writer.rollback()
        writer.close()

    assert loaded.dws.database == "dwdb"
    assert loaded.business.database == "bizdb"


def test_local_store_backs_up_existing_database_before_schema_migration(tmp_path):
    path = tmp_path / "config.json"
    db_path = db_path_for_config(path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE app_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO app_kv(key, value, updated_at) VALUES ('legacy', '{\"ok\": true}', '2026-07-03 10:00:00')"
        )

    read_app_value(path, "missing")

    backups = list(tmp_path.glob("backup-before-storage-v2-*/auto-check.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        legacy_value = connection.execute(
            "SELECT value FROM app_kv WHERE key = 'legacy'"
        ).fetchone()[0]

    assert "app_kv" in tables
    assert "data_sources" not in tables
    assert legacy_value == '{"ok": true}'


def test_default_config_has_two_sources():
    config = default_config()

    assert config.dws.db_type == "postgresql"
    assert config.business.db_type == "mysql"
    assert config.dws.schema == "dws"
    assert config.business.schema == ""


def test_save_and_load_config_round_trip(tmp_path):
    config = AppConfig(
        dws=DataSourceConfig(
            db_type="postgresql",
            host="127.0.0.1",
            port=5432,
            database="dwsdb",
            schema="dws",
            username="user1",
            password="pass1",
        ),
        business=DataSourceConfig(
            db_type="mysql",
            host="127.0.0.2",
            port=3306,
            database="bizdb",
            schema="",
            username="user2",
            password="pass2",
        ),
    )
    path = tmp_path / "config.json"

    save_config(config, path)
    loaded = load_config(path)

    assert loaded == config


def test_load_missing_config_returns_defaults(tmp_path):
    loaded = load_config(tmp_path / "missing.json")

    assert loaded == default_config()


def test_store_persists_default_settings(tmp_path):
    path = tmp_path / "config.json"
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

    save_store(store, path)
    loaded = load_store(path)

    assert loaded.default_settings == store.default_settings


def test_store_persists_pbc_import_tool_settings(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(
        pbc_import_tool=PbcImportToolSettings(
            recent_tables=["dws.public_information_th", "dws.aainfo"],
            last_config_name="local",
            last_source="dws",
        )
    )

    save_store(store, path)
    loaded = load_store(path)

    assert loaded.pbc_import_tool == store.pbc_import_tool


def test_store_persists_reconcile_schema_settings(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(
        reconcile_schema=ReconcileSchemaSettings(
            version=1,
            strict=True,
            tables={
                "fa_valuation": ReconcileTableSchema(
                    source_ref=ReconcileSourceRef(id="source-dws", name="生产DWS", match_by="id_then_name"),
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

    save_store(store, path)
    loaded = load_store(path)

    assert loaded.reconcile_schema.tables["fa_valuation"].source_ref.id == "source-dws"
    assert loaded.reconcile_schema.tables["fa_valuation"].table == "dw.fa_valuation_custom"
    assert loaded.reconcile_schema.tables["fa_valuation"].fields["market_value"] == "market_amt"
    assert loaded.reconcile_schema.strict is True


def test_load_store_ignores_reconcile_schema_yaml_until_page_initializes_it(tmp_path):
    path = tmp_path / "config.json"
    save_store(ConfigStore(), path)
    path.with_name("reconcile-schema.yaml").write_text(
        """
reconcile_schema:
  version: 1
  tables:
    fa_valuation:
      # Inline comments are allowed in the production yaml.
      source_ref:
        id: "source-dws"
        name: "DWS"
        match_by: id_then_name
      table: custom.fa_valuation_custom
      display_name: FA valuation override
      fields:
        project_code: proj_code        # project
        valuation_date: val_date
        account_code: acct_code
        account_name: acct_name
        market_value: market_amt
""".strip(),
        encoding="utf-8",
    )

    loaded = load_store(path)

    assert loaded.reconcile_schema.tables == {}


def test_load_store_keeps_system_reconcile_schema_when_yaml_template_exists(tmp_path):
    path = tmp_path / "config.json"
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
        path,
    )
    path.with_name("reconcile-schema.yaml").write_text(
        """
reconcile_schema:
  version: 1
  tables:
    fa_valuation:
      source_ref:
        id: "yaml-dws"
        name: "yaml"
      table: yaml.fa_valuation
      fields:
        market_value: yaml_amt
""".strip(),
        encoding="utf-8",
    )

    loaded = load_store(path)

    table = loaded.reconcile_schema.tables["fa_valuation"]
    assert table.source_ref.id == "system-dws"
    assert table.table == "system.fa_valuation"
    assert table.fields["market_value"] == "system_amt"
    assert loaded.reconcile_schema.strict is True


def test_store_persists_flow_tool_settings(tmp_path):
    path = tmp_path / "config.json"
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

    save_store(store, path)
    loaded = load_store(path)

    assert loaded.flow_tool == store.flow_tool
    saved_payload = json.loads(path.read_text(encoding="utf-8"))
    chain_payload = saved_payload["flow_tool"]["chains"][0]
    assert "schedule_enabled" not in chain_payload
    assert "schedule_cron" not in chain_payload
    assert "schedule_time" not in chain_payload


def test_store_ignores_legacy_flow_chain_schedule_fields(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "data_sources": [
                    {
                        "id": "source-report",
                        "name": "申报平台库",
                        "db_type": "mysql",
                        "host": "192.168.107.81",
                        "port": 3306,
                        "database": "reg-report-analysis",
                        "schema": "",
                        "username": "u",
                        "password": "p",
                        "is_default": True,
                    }
                ],
                "flow_tool": {
                    "source_id": "source-report",
                    "execute_url": "http://192.168.107.81/assmag/spiderFlow/spider/testRun",
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
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = load_store(path)
    chain = loaded.flow_tool.chains[0]

    assert chain.id == "chain-zgxg-1"
    assert chain.enabled is True
    assert not hasattr(chain, "schedule_enabled")
    assert not hasattr(chain, "schedule_cron")
    assert not hasattr(chain, "schedule_time")


def test_store_migrates_grouped_configs_to_single_data_sources(tmp_path):
    path = tmp_path / "config.json"
    legacy_store = ConfigStore(
        configs=[
            NamedConfig(
                name="对账数据源",
                dws=DataSourceConfig("postgresql", "127.0.0.1", 5432, "dwsdb", "dws", "reader", "dws-secret"),
                business=DataSourceConfig("mysql", "127.0.0.2", 3306, "bizdb", "", "writer", "biz-secret"),
                is_default=True,
            ),
            NamedConfig(
                name="逐笔校验数据源",
                dws=DataSourceConfig("postgresql", "127.0.0.3", 5432, "metadb", "test", "meta", "meta-secret"),
                business=DataSourceConfig("postgresql", "127.0.0.4", 5432, "unused", "dws", "unused", "unused-secret"),
                is_default=False,
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
    save_store(legacy_store, path)

    loaded = load_store(path)

    assert [entry.id for entry in loaded.data_sources] == [
        "legacy:对账数据源:dws",
        "legacy:对账数据源:business",
        "legacy:逐笔校验数据源:dws",
        "legacy:逐笔校验数据源:business",
    ]
    assert loaded.reconcile_data_sources == ReconcileDataSourceSettings(
        dws_source_id="legacy:对账数据源:dws",
        business_source_id="legacy:对账数据源:business",
    )
    assert loaded.db_validation.detail.source_id == "legacy:逐笔校验数据源:dws"
    assert loaded.db_validation.field_mapping_source_id == "legacy:逐笔校验数据源:dws"

    raw = path.read_text(encoding="utf-8")
    assert '"data_sources"' in raw
    assert '"configs"' not in raw
    assert "dws-secret" not in raw
    assert "biz-secret" not in raw


def test_store_persists_single_data_sources(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(
        data_sources=[
            DataSourceEntry(
                id="source-detail",
                name="逐笔库",
                config=DataSourceConfig("postgresql", "127.0.0.1", 5432, "detaildb", "dws", "reader", "secret"),
                is_default=True,
            ),
            DataSourceEntry(
                id="source-business",
                name="报表库",
                config=DataSourceConfig("mysql", "127.0.0.2", 3306, "bizdb", "", "writer", "biz-secret"),
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
        )
    )

    save_store(store, path)
    loaded = load_store(path)

    assert loaded.data_sources == store.data_sources
    assert loaded.reconcile_data_sources == store.reconcile_data_sources
    assert loaded.db_validation == store.db_validation
    assert resolve_data_source(loaded, "source-detail").database == "detaildb"


def test_store_persists_data_sources_to_normalized_tables(tmp_path):
    import sqlite3

    path = tmp_path / "config.json"
    dws = DataSourceEntry(
        id="source-dws",
        name="DWS",
        config=DataSourceConfig(
            db_type="postgresql",
            host="127.0.0.1",
            port=5432,
            database="dw",
            schema="dws",
            username="u",
            password="Pass123",
        ),
        is_default=True,
    )
    report = DataSourceEntry(
        id="source-report",
        name="Report",
        config=DataSourceConfig(
            db_type="mysql",
            host="10.0.0.2",
            port=3306,
            database="report",
            schema="",
            username="r",
            password="Report123",
        ),
    )

    save_store(
        ConfigStore(
            data_sources=[dws, report],
            default_name="DWS",
            reconcile_data_sources=ReconcileDataSourceSettings(
                dws_source_id="source-dws",
                business_source_id="source-report",
            ),
        ),
        path,
    )

    with sqlite3.connect(db_path_for_config(path)) as connection:
        rows = connection.execute(
            "SELECT id, name, db_type, host, port, database_name, schema_name, username, password_encrypted "
            "FROM data_sources ORDER BY id"
        ).fetchall()

    assert [row[0] for row in rows] == ["source-dws", "source-report"]
    assert rows[0][8].startswith("aesgcm$")
    assert read_app_value(path, "config_store") is not None

    path.unlink()
    loaded = load_store(path)
    assert [entry.id for entry in loaded.data_sources] == ["source-dws", "source-report"]
    assert loaded.data_sources[0].config.password == "Pass123"
    assert loaded.reconcile_data_sources.dws_source_id == "source-dws"


def test_store_encrypts_saved_passwords_on_disk(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setenv("AUTO_CHECK_SECRET_KEY", "unit-test-secret")
    store = ConfigStore(
        configs=[
            NamedConfig(
                name="secure",
                dws=DataSourceConfig("postgresql", "127.0.0.1", 5432, "dwsdb", "dws", "reader", "dws-secret"),
                business=DataSourceConfig("mysql", "127.0.0.1", 3306, "bizdb", "", "writer", "biz-secret"),
                is_default=True,
            )
        ],
        default_name="secure",
    )

    save_store(store, path)

    raw = path.read_text(encoding="utf-8")
    assert "dws-secret" not in raw
    assert "biz-secret" not in raw
    assert '"password_encrypted"' in raw

    loaded = load_store(path)
    assert resolve_data_source(loaded, "legacy:secure:dws").password == "dws-secret"
    assert resolve_data_source(loaded, "legacy:secure:business").password == "biz-secret"


def test_store_persists_to_sqlite_and_can_load_without_json_snapshot(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(
        data_sources=[
            DataSourceEntry(
                id="source-dws",
                name="local DWS",
                config=DataSourceConfig("postgresql", "localhost", 5432, "dwdb", "dws", "reader", "secret"),
                is_default=True,
            ),
            DataSourceEntry(
                id="source-business",
                name="local business",
                config=DataSourceConfig("mysql", "localhost", 3306, "bizdb", "", "writer", "biz-secret"),
            ),
        ],
        reconcile_data_sources=ReconcileDataSourceSettings(
            dws_source_id="source-dws",
            business_source_id="source-business",
        ),
        default_settings=DefaultSettings(session_expire_hours=6, page_size=30),
    )

    save_store(store, path)

    assert db_path_for_config(path).exists()
    assert read_app_value(path, "config_store") is not None

    path.unlink()
    loaded = load_store(path)

    assert loaded.data_sources == store.data_sources
    assert loaded.reconcile_data_sources == store.reconcile_data_sources
    assert loaded.default_settings == store.default_settings


def test_load_store_migrates_existing_json_config_to_sqlite(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        """
{
  "data_sources": [
    {
      "id": "source-dws",
      "name": "legacy DWS",
      "db_type": "postgresql",
      "host": "127.0.0.1",
      "port": 5432,
      "database": "dwdb",
      "schema": "dws",
      "username": "reader",
      "password": ""
    },
    {
      "id": "source-business",
      "name": "legacy business",
      "db_type": "mysql",
      "host": "127.0.0.2",
      "port": 3306,
      "database": "bizdb",
      "schema": "",
      "username": "writer",
      "password": ""
    }
  ],
  "reconcile_data_sources": {
    "dws_source_id": "source-dws",
    "business_source_id": "source-business"
  },
  "default_settings": {
    "session_expire_hours": 10,
    "page_size": 25
  }
}
""".strip(),
        encoding="utf-8",
    )

    loaded = load_store(path)

    assert db_path_for_config(path).exists()
    assert loaded.reconcile_data_sources.dws_source_id == "source-dws"
    assert loaded.default_settings.session_expire_hours == 10

    path.unlink()
    loaded_from_db = load_store(path)
    assert loaded_from_db.reconcile_data_sources.dws_source_id == "source-dws"
    assert loaded_from_db.default_settings.page_size == 25


def test_store_migrates_from_config_json_when_sqlite_is_empty(tmp_path):
    import sqlite3

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "data_sources": [
                    {
                        "id": "source-json",
                        "name": "JSON source",
                        "db_type": "postgresql",
                        "host": "127.0.0.1",
                        "port": 5432,
                        "database": "json_db",
                        "schema": "dws",
                        "username": "postgres",
                        "password": "Json123",
                        "is_default": True,
                    }
                ],
                "reconcile_data_sources": {
                    "dws_source_id": "source-json",
                    "business_source_id": "source-json",
                },
                "default_settings": {"page_size": 20},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = load_store(path)

    assert store.data_sources[0].id == "source-json"
    assert store.data_sources[0].config.password == "Json123"
    with sqlite3.connect(db_path_for_config(path)) as connection:
        source_count = connection.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]
        migration = connection.execute(
            "SELECT status, migrated_count FROM storage_migration_runs WHERE source_type = 'config_json'"
        ).fetchone()

    assert source_count == 1
    assert migration == ("completed", 1)


def test_store_migrates_sqlite_config_store_with_data_sources_to_normalized_tables(tmp_path):
    path = tmp_path / "config.json"
    write_app_value(
        path,
        "config_store",
        {
            "data_sources": [
                {
                    "id": "source-sqlite",
                    "name": "SQLite legacy source",
                    "db_type": "mysql",
                    "host": "10.8.0.15",
                    "port": 3306,
                    "database": "legacy_db",
                    "schema": "",
                    "username": "reader",
                    "password": "Legacy123",
                    "is_default": True,
                }
            ],
            "reconcile_data_sources": {
                "dws_source_id": "source-sqlite",
                "business_source_id": "source-sqlite",
            },
            "default_settings": {"page_size": 50},
        },
    )

    store = load_store(path)

    assert store.data_sources[0].id == "source-sqlite"
    assert store.data_sources[0].config.password == "Legacy123"
    with sqlite3.connect(db_path_for_config(path)) as connection:
        source_count = connection.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]
        setting_count = connection.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0]
        migration = connection.execute(
            "SELECT status, migrated_count FROM storage_migration_runs WHERE source_type = 'config_store'"
        ).fetchone()

    assert source_count == 1
    assert setting_count > 0
    assert migration == ("completed", 1)


def test_load_store_does_not_treat_auth_only_json_as_legacy_data_source_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        """
{
  "auth": {
    "users": [
      {
        "id": "admin",
        "username": "admin",
        "display_name": "管理员",
        "role": "admin",
        "password_hash": "pbkdf2_sha256$260000$salt$digest",
        "enabled": true
      }
    ]
  }
}
""".strip(),
        encoding="utf-8",
    )

    loaded = load_store(path)

    assert loaded.data_sources == []
    assert read_app_value(path, "auth")["users"][0]["username"] == "admin"
