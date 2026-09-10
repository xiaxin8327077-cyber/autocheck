"""系统字典存储层测试：分类/字典项 CRUD、编码校验、启停与只读启用项查询。"""

from __future__ import annotations

from pathlib import Path

import pytest
from mysql_config_test_support import MemoryApplicationDatabase

from auto_check.app import storage_dictionaries
from auto_check.app.app_database import EXPECTED_APP_SCHEMA
from auto_check.app.storage_dictionaries import (
    create_dictionary,
    create_dictionary_item,
    delete_dictionary,
    delete_dictionary_item,
    get_active_dictionary_item,
    list_active_dictionary_items,
    list_dictionaries,
    update_dictionary,
    update_dictionary_item,
)

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_SQL = ROOT / "sql" / "app_storage" / "mysql" / "019_dictionary_management.sql"
REPORT_PERIOD_MIGRATION_SQL = ROOT / "sql" / "app_storage" / "mysql" / "020_report_period_field_dictionary.sql"


def _db() -> MemoryApplicationDatabase:
    return MemoryApplicationDatabase()


def _seed_dictionary(db: MemoryApplicationDatabase) -> None:
    with db.transaction() as connection:
        create_dictionary(
            connection,
            code="business_system",
            name="业务系统",
            description="报表特殊处理等功能使用的所属业务系统",
            system_locked=True,
            sort_order=10,
            updated_by="admin",
        )


def _seed_item(db: MemoryApplicationDatabase, code: str, name: str, **kwargs):
    with db.transaction() as connection:
        return create_dictionary_item(
            connection,
            dictionary_code="business_system",
            item_code=code,
            item_name=name,
            updated_by="admin",
            **kwargs,
        )


# ---------------------------------------------------------------- schema/迁移


def test_expected_app_schema_contains_dictionary_tables():
    assert EXPECTED_APP_SCHEMA["system_dictionaries"] >= {
        "dictionary_code",
        "dictionary_name",
        "description",
        "enabled",
        "system_locked",
        "sort_order",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    }
    assert EXPECTED_APP_SCHEMA["system_dictionary_items"] >= {
        "id",
        "dictionary_code",
        "item_code",
        "item_name",
        "description",
        "enabled",
        "sort_order",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    }


def test_migration_asset_is_idempotent_and_seeds_locked_business_system():
    assert MIGRATION_SQL.exists(), "019_dictionary_management.sql is required"
    text = MIGRATION_SQL.read_text(encoding="utf-8")
    upper = text.upper()
    assert "CREATE TABLE IF NOT EXISTS `system_dictionaries`" in text
    assert "CREATE TABLE IF NOT EXISTS `system_dictionary_items`" in text
    assert "DROP" not in upper
    assert "TRUNCATE" not in upper
    assert "ON DUPLICATE KEY UPDATE" in upper
    assert "business_system" in text
    assert "业务系统" in text


def test_report_period_field_dictionary_migration_is_idempotent_and_seeded():
    assert REPORT_PERIOD_MIGRATION_SQL.exists(), "020_report_period_field_dictionary.sql is required"
    text = REPORT_PERIOD_MIGRATION_SQL.read_text(encoding="utf-8")
    upper = text.upper()
    assert "report_period_field" in text
    assert "报送期字段匹配" in text
    assert "'cldate'" in text
    assert "'caldate'" in text
    assert "ON DUPLICATE KEY UPDATE" in upper
    assert "DROP" not in upper
    assert "TRUNCATE" not in upper


def test_dictionary_category_delete_is_not_exposed():
    names = [name for name in dir(storage_dictionaries) if name.startswith(("delete_", "remove_"))]
    assert names == ["delete_dictionary", "delete_dictionary_item"]


# ---------------------------------------------------------------- 分类 CRUD


def test_create_and_list_dictionary():
    db = _db()
    _seed_dictionary(db)
    with db.connect() as connection:
        dictionaries = list_dictionaries(connection)
    assert [item["code"] for item in dictionaries] == ["business_system"]
    entry = dictionaries[0]
    assert entry["name"] == "业务系统"
    assert entry["system_locked"] is True
    assert entry["enabled"] is True
    assert entry["items"] == []


def test_delete_custom_dictionary_and_reject_locked_dictionary():
    db = _db()
    with db.transaction() as connection:
        create_dictionary(connection, code="custom", name="自定义", updated_by="admin")
        create_dictionary_item(
            connection, dictionary_code="custom", item_code="A", item_name="键值", updated_by="admin",
        )
        delete_dictionary(connection, "custom")
    with db.connect() as connection:
        assert list_dictionaries(connection) == []
    _seed_dictionary(db)
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="系统预置字典不可删除"):
            delete_dictionary(connection, "business_system")


def test_create_dictionary_validates_code_and_name():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="字典编码格式不正确"):
            create_dictionary(connection, code="Bad Code", name="x", updated_by="admin")
        with pytest.raises(ValueError, match="字典名称必填"):
            create_dictionary(connection, code="ok_code", name="  ", updated_by="admin")
        with pytest.raises(ValueError, match="字典名称"):
            create_dictionary(connection, code="ok_code", name="名" * 101, updated_by="admin")
        with pytest.raises(ValueError, match="说明"):
            create_dictionary(connection, code="ok_code", name="n", description="说" * 256, updated_by="admin")
        with pytest.raises(ValueError, match="排序"):
            create_dictionary(connection, code="ok_code", name="n", sort_order=10000, updated_by="admin")


def test_dictionary_code_accepts_pure_digits():
    db = _db()
    with db.transaction() as connection:
        created = create_dictionary(connection, code="100", name="数字字典", updated_by="admin")
    assert created["code"] == "100"


def test_create_dictionary_rejects_duplicate_code():
    db = _db()
    _seed_dictionary(db)
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="已存在"):
            create_dictionary(connection, code="business_system", name="重复", updated_by="admin")


def test_list_dictionaries_sorts_by_sort_order_then_code():
    db = _db()
    with db.transaction() as connection:
        create_dictionary(connection, code="second", name="B", sort_order=20, updated_by="admin")
        create_dictionary(connection, code="first", name="A", sort_order=10, updated_by="admin")
        create_dictionary(connection, code="alpha", name="C", sort_order=10, updated_by="admin")
    with db.connect() as connection:
        codes = [item["code"] for item in list_dictionaries(connection)]
    assert codes == ["alpha", "first", "second"]


def test_list_dictionaries_avoids_n_plus_one_queries():
    db = _db()
    _seed_dictionary(db)
    _seed_item(db, "ta", "TA估值")
    _seed_item(db, "fa", "FA核算")
    db.connection.executed_sql.clear()
    with db.connect() as connection:
        list_dictionaries(connection)
    dictionary_selects = [sql for sql in db.connection.executed_sql if "FROM system_dictionaries" in sql]
    item_selects = [sql for sql in db.connection.executed_sql if "FROM system_dictionary_items" in sql]
    assert len(dictionary_selects) == 1
    assert len(item_selects) == 1


def test_update_dictionary_changes_name_description_sort_and_enabled():
    db = _db()
    _seed_dictionary(db)
    with db.transaction() as connection:
        updated = update_dictionary(
            connection,
            "business_system",
            name="业务系统（新）",
            description="改名",
            sort_order=5,
            enabled=False,
            updated_by="admin",
        )
        dictionaries = list_dictionaries(connection)
    assert updated["name"] == "业务系统（新）"
    assert updated["enabled"] is False
    assert dictionaries[0]["enabled"] is False
    assert dictionaries[0]["sort_order"] == 5


def test_update_dictionary_missing_raises():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="不存在"):
            update_dictionary(connection, "ghost", name="x", updated_by="admin")


# ---------------------------------------------------------------- 字典项 CRUD


def test_create_item_requires_existing_dictionary():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="不存在"):
            create_dictionary_item(
                connection,
                dictionary_code="ghost",
                item_code="ta",
                item_name="TA估值",
                updated_by="admin",
            )


def test_create_update_and_order_items():
    db = _db()
    _seed_dictionary(db)
    with db.transaction() as connection:
        first = create_dictionary_item(
            connection, dictionary_code="business_system", item_code="valuation",
            item_name="估值系统", sort_order=20, updated_by="admin",
        )
        second = create_dictionary_item(
            connection, dictionary_code="business_system", item_code="ta",
            item_name="TA估值", sort_order=10, updated_by="admin",
        )
        with pytest.raises(ValueError, match="已存在"):
            create_dictionary_item(
                connection, dictionary_code="business_system", item_code="ta",
                item_name="重复", updated_by="admin",
            )
    with db.connect() as connection:
        dictionaries = list_dictionaries(connection)
    codes = [item["code"] for item in dictionaries[0]["items"]]
    assert codes == ["ta", "valuation"]
    assert second["id"] != first["id"]
    with db.transaction() as connection:
        updated = update_dictionary_item(
            connection,
            "business_system",
            first["id"],
            item_name="新估值系统",
            sort_order=5,
            enabled=False,
            updated_by="admin",
        )
    assert updated["name"] == "新估值系统"
    assert updated["enabled"] is False
    with db.connect() as connection:
        item = get_active_dictionary_item(connection, "business_system", "valuation")
    assert item is None  # 停用后不可见
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="不存在"):
            update_dictionary_item(connection, "business_system", 9999, item_name="x", updated_by="admin")


def test_item_code_accepts_digits_and_is_unique_only_within_parent_dictionary():
    db = _db()
    with db.transaction() as connection:
        create_dictionary(connection, code="first_dict", name="字典一", updated_by="admin")
        create_dictionary(connection, code="second_dict", name="字典二", updated_by="admin")
        first = create_dictionary_item(
            connection, dictionary_code="first_dict", item_code="1001",
            item_name="数字编码", updated_by="admin",
        )
        second = create_dictionary_item(
            connection, dictionary_code="second_dict", item_code="1001",
            item_name="跨字典同编码", updated_by="admin",
        )
        with pytest.raises(ValueError, match="字典项编码已存在：1001"):
            create_dictionary_item(
                connection, dictionary_code="first_dict", item_code="1001",
                item_name="同字典重复", updated_by="admin",
            )
    assert first["code"] == "1001"
    assert second["code"] == "1001"


def test_item_validators():
    db = _db()
    _seed_dictionary(db)
    with db.transaction() as connection:
        uppercase = create_dictionary_item(
            connection, dictionary_code="business_system", item_code="TA_SYSTEM",
            item_name="大写编码", updated_by="admin",
        )
        assert uppercase["code"] == "TA_SYSTEM"
        with pytest.raises(ValueError, match="字典项编码格式不正确"):
            create_dictionary_item(
                connection, dictionary_code="business_system", item_code="TA-SYSTEM",
                item_name="x", updated_by="admin",
            )
        with pytest.raises(ValueError, match="字典项名称必填"):
            create_dictionary_item(
                connection, dictionary_code="business_system", item_code="ok",
                item_name=" ", updated_by="admin",
            )


def test_delete_dictionary_item():
    db = _db()
    _seed_dictionary(db)
    with db.transaction() as connection:
        item = create_dictionary_item(
            connection, dictionary_code="business_system", item_code="delete_me",
            item_name="待删除", updated_by="admin",
        )
        delete_dictionary_item(connection, "business_system", item["id"])
    with db.connect() as connection:
        assert list_dictionaries(connection)[0]["items"] == []
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="不存在"):
            delete_dictionary_item(connection, "business_system", item["id"])


# ---------------------------------------------------------------- 启用项查询


def test_list_active_items_filters_disabled_dictionary_and_items():
    db = _db()
    _seed_dictionary(db)
    _seed_item(db, "ta", "TA估值", sort_order=20)
    _seed_item(db, "fa", "FA核算", sort_order=10)
    _seed_item(db, "off", "停用项", enabled=False)
    with db.connect() as connection:
        items = list_active_dictionary_items(connection, "business_system")
    assert [item["code"] for item in items] == ["fa", "ta"]
    assert items[0]["name"] == "FA核算"
    assert items[0]["sort_order"] == 10
    with db.transaction() as connection:
        update_dictionary(connection, "business_system", enabled=False, updated_by="admin")
    with db.connect() as connection:
        assert list_active_dictionary_items(connection, "business_system") == []
        assert get_active_dictionary_item(connection, "business_system", "fa") is None


def test_list_active_items_unknown_dictionary_returns_empty():
    db = _db()
    with db.connect() as connection:
        assert list_active_dictionary_items(connection, "ghost") == []
