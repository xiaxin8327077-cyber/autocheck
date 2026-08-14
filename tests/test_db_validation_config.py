from auto_check.app.config import (
    ConfigStore,
    DataSourceConfig,
    DataSourceEntry,
    DbValidationDatasetSettings,
    DbValidationSettings,
    NamedConfig,
    db_validation_settings_from_dict,
    load_store,
    save_store,
)
from mysql_config_test_support import MemoryApplicationDatabase


def test_store_persists_db_validation_settings(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(
        data_sources=[
            DataSourceEntry(
                id="detail-source",
                name="逐笔库",
                config=DataSourceConfig("postgresql", "127.0.0.1", 5432, "detaildb", "dws", "reader", "p"),
            ),
            DataSourceEntry(
                id="public-source",
                name="公开信息库",
                config=DataSourceConfig("postgresql", "127.0.0.1", 5432, "publicdb", "dws", "reader", "p"),
            ),
            DataSourceEntry(
                id="metadata-source",
                name="字段匹配库",
                config=DataSourceConfig("postgresql", "127.0.0.1", 5432, "metadb", "test", "reader", "p"),
            ),
        ],
        db_validation=DbValidationSettings(
            detail=DbValidationDatasetSettings(
                source_id="detail-source",
                sys_manage_id="DETAIL_SYS1;DETAIL_SYS2",
                classification_id="DETAIL_CLASS",
            ),
            public_info=DbValidationDatasetSettings(
                source_id="public-source",
                sys_manage_id="PUBLIC_SYS",
                classification_id="PUBLIC_CLASS1;PUBLIC_CLASS2",
            ),
            field_mapping_source_id="metadata-source",
            baseinfo_table="xt_reg_table_baseinfo_custom",
            field_info_table="xt_reg_table_field_info_custom",
        )
    )

    database = MemoryApplicationDatabase()
    save_store(store, path, database=database)
    loaded = load_store(path, database=database)

    assert loaded.db_validation == store.db_validation


def test_db_validation_settings_defaults_are_usable():
    settings = ConfigStore().db_validation

    assert settings.detail.source_id == ""
    assert settings.public_info.source_id == ""
    assert settings.template.source_id == ""
    assert settings.field_mapping_source_id == ""
    assert settings.baseinfo_table == "xt_reg_table_baseinfo"
    assert settings.field_info_table == "xt_reg_table_field_info"
    assert settings.public_info_table == ""


def test_db_validation_settings_drops_legacy_public_info_table(tmp_path):
    settings = db_validation_settings_from_dict({"public_info_table": "legacy_public_table"})

    assert settings.public_info_table == "legacy_public_table"

    store = ConfigStore(db_validation=settings)
    database = MemoryApplicationDatabase()
    save_store(store, tmp_path / "config.json", database=database)
    reloaded = load_store(tmp_path / "config.json", database=database)

    assert reloaded.db_validation.public_info_table == ""


def test_db_validation_settings_migrates_old_config_source_pair(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(
        configs=[
            NamedConfig(
                name="local",
                dws=DataSourceConfig("postgresql", "127.0.0.1", 5432, "detaildb", "dws", "reader", "p"),
                business=DataSourceConfig("postgresql", "127.0.0.1", 5432, "bizdb", "dws", "reader", "p"),
                is_default=True,
            ),
            NamedConfig(
                name="metadata",
                dws=DataSourceConfig("postgresql", "127.0.0.1", 5432, "metadb", "test", "reader", "p"),
                business=DataSourceConfig("postgresql", "127.0.0.1", 5432, "unused", "dws", "reader", "p"),
            ),
        ],
        db_validation=DbValidationSettings(
            detail=DbValidationDatasetSettings(config_name="local", source="business"),
            public_info=DbValidationDatasetSettings(config_name="local", source="dws"),
            field_mapping_config_name="metadata",
            field_mapping_source="dws",
        ),
    )
    database = MemoryApplicationDatabase()
    save_store(store, path, database=database)

    loaded = load_store(path, database=database)

    assert loaded.db_validation.detail.source_id == "legacy:local:business"
    assert loaded.db_validation.public_info.source_id == "legacy:local:dws"
    assert loaded.db_validation.field_mapping_source_id == "legacy:metadata:dws"
