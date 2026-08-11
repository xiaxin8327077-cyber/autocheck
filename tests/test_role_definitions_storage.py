"""角色定义存储（role_definitions）测试：自定义角色 CRUD。"""

import pytest
from mysql_config_test_support import MemoryApplicationDatabase

from auto_check.app.capabilities import SYSTEM_ROLES
from auto_check.app.storage_role_definitions import (
    count_users_by_role,
    create_role_definition,
    delete_role_definition,
    load_custom_role_codes,
    load_custom_role_remarks,
    load_role_definitions,
    update_role_definition,
)


def _db():
    return MemoryApplicationDatabase()


def test_load_role_definitions_includes_system_roles():
    db = _db()
    with db.connect() as connection:
        defs = load_role_definitions(connection)
    codes = [d["role_code"] for d in defs]
    # 系统内建角色在前
    assert "admin" in codes
    assert all(d["is_system"] for d in defs)
    assert set(codes) == set(SYSTEM_ROLES)


def test_create_role_definition_generates_custom_code():
    db = _db()
    with db.transaction() as connection:
        created = create_role_definition(connection, display_name="审计员", remark="自定义审计", updated_by="admin")
    assert created["role_code"].startswith("custom_")
    assert created["display_name"] == "审计员"
    assert created["remark"] == "自定义审计"
    assert created["is_system"] is False
    with db.connect() as connection:
        defs = load_role_definitions(connection)
    custom = [d for d in defs if not d["is_system"]]
    assert len(custom) == 1
    assert custom[0]["role_code"] == created["role_code"]


def test_create_role_definition_auto_increments_code():
    db = _db()
    with db.transaction() as connection:
        c1 = create_role_definition(connection, display_name="角色A", updated_by="admin")
        c2 = create_role_definition(connection, display_name="角色B", updated_by="admin")
    assert c1["role_code"] != c2["role_code"]
    with db.connect() as connection:
        codes = load_custom_role_codes(connection)
    assert set(codes) == {c1["role_code"], c2["role_code"]}


def test_create_role_definition_requires_display_name():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="display name is required"):
            create_role_definition(connection, display_name="  ", updated_by="admin")


def test_update_role_definition_changes_name_and_remark():
    db = _db()
    with db.transaction() as connection:
        created = create_role_definition(connection, display_name="原名", updated_by="admin")
        updated = update_role_definition(connection, created["role_code"], display_name="新名", remark="新备注", updated_by="admin")
    assert updated["display_name"] == "新名"
    assert updated["remark"] == "新备注"
    with db.connect() as connection:
        defs = load_role_definitions(connection)
    custom = [d for d in defs if d["role_code"] == created["role_code"]][0]
    assert custom["display_name"] == "新名"


def test_update_role_definition_rejects_system_role_name_change():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="system role"):
            update_role_definition(connection, "admin", display_name="超级管理员", updated_by="admin")


def test_update_role_definition_rejects_unknown_role():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="not found"):
            update_role_definition(connection, "custom_ghost", display_name="x", updated_by="admin")


def test_create_role_definition_rejects_long_remark():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="remark must be at most 20"):
            create_role_definition(
                connection,
                display_name="超长备注角色",
                remark="一二三四五六七八九十一二三四五六七八九十超",
                updated_by="admin",
            )


def test_delete_role_definition_succeeds_when_no_users():
    db = _db()
    with db.transaction() as connection:
        created = create_role_definition(connection, display_name="临时角色", updated_by="admin")
        delete_role_definition(connection, created["role_code"])
    with db.connect() as connection:
        codes = load_custom_role_codes(connection)
    assert created["role_code"] not in codes


def test_delete_role_definition_rejects_system_role():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="system role"):
            delete_role_definition(connection, "admin")


def test_delete_removed_builtin_role_definition_succeeds():
    from auto_check.app.storage_role_definitions import ROLE_DEFINITIONS_TABLE, purge_removed_builtin_role_definitions

    db = _db()
    with db.transaction() as connection:
        connection.execute(
            ROLE_DEFINITIONS_TABLE.insert().values(
                role_code="governance",
                display_name="数据治理",
                remark="预留角色",
                is_system=0,
                created_by="admin",
                created_at="2026-08-07 00:00:00",
                updated_by="admin",
                updated_at="2026-08-07 00:00:00",
            )
        )
        delete_role_definition(connection, "governance")
    with db.connect() as connection:
        assert "governance" not in load_custom_role_codes(connection)


def test_purge_removed_builtin_role_definitions_clears_leftovers():
    from auto_check.app.storage_role_definitions import ROLE_DEFINITIONS_TABLE, purge_removed_builtin_role_definitions

    db = _db()
    with db.transaction() as connection:
        connection.execute(
            ROLE_DEFINITIONS_TABLE.insert().values(
                role_code="regulatory_report",
                display_name="监管报表",
                remark="预留角色",
                is_system=0,
                created_by="admin",
                created_at="2026-08-07 00:00:00",
                updated_by="admin",
                updated_at="2026-08-07 00:00:00",
            )
        )
        removed = purge_removed_builtin_role_definitions(connection)
    assert removed == 1
    with db.connect() as connection:
        assert "regulatory_report" not in load_custom_role_codes(connection)


def test_delete_role_definition_rejects_when_users_exist():
    db = _db()
    with db.transaction() as connection:
        created = create_role_definition(connection, display_name="在用角色", updated_by="admin")
        # 模拟有用户使用该角色
        from auto_check.app.storage_users import USERS
        connection.execute(
            USERS.insert().values(
                id="u-custom-1",
                username="custom_user",
                display_name="自定义用户",
                role=created["role_code"],
                password_hash="x",
                enabled=True,
                created_at="2026-08-07 00:00:00",
                updated_at="2026-08-07 00:00:00",
                last_login_at="",
            )
        )
        with pytest.raises(ValueError, match="in use"):
            delete_role_definition(connection, created["role_code"])


def test_load_custom_role_remarks():
    db = _db()
    with db.transaction() as connection:
        create_role_definition(connection, display_name="审计员", remark="审计备注", updated_by="admin")
        create_role_definition(connection, display_name="空备注", remark="", updated_by="admin")
    with db.connect() as connection:
        remarks = load_custom_role_remarks(connection)
    assert len(remarks) == 2
    assert "审计备注" in remarks.values()
    assert "" in remarks.values()
    assert "空备注" not in remarks.values()


def test_create_role_definition_rejects_long_display_name():
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="display name must be at most 10"):
            create_role_definition(
                connection,
                display_name="一二三四五六七八九十一",
                updated_by="admin",
            )


def test_count_users_by_role():
    db = _db()
    with db.connect() as connection:
        assert count_users_by_role(connection, "user") == 0
        assert count_users_by_role(connection, "custom_ghost") == 0