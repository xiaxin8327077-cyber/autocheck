from __future__ import annotations

from dataclasses import fields

import pytest

from auto_check.app.module_system.services import ServiceRegistry
from auto_check.app.platform_services import (
    PublicDictionaryItem,
    PublicUser,
    create_dictionary_service,
    create_user_directory_service,
)
from auto_check.app.security import AuthManager
from mysql_config_test_support import MemoryApplicationDatabase


def test_user_directory_returns_only_enabled_whitelisted_users_and_is_revoked_on_close(
    tmp_path,
):
    database = MemoryApplicationDatabase()
    auth_manager = AuthManager(tmp_path / "config.json", database=database)
    auth_manager.set_admin_password("AdminPass123")
    active = auth_manager.create_user(
        username="active_user",
        display_name="Active User",
        password="UserPass123",
        role="user",
        enabled=True,
    )
    disabled = auth_manager.create_user(
        username="disabled_user",
        display_name="Disabled User",
        password="UserPass123",
        role="user",
        enabled=False,
    )
    registry = ServiceRegistry()
    registry.register_platform(create_user_directory_service(auth_manager))
    services = registry.for_module(
        "alpha",
        service_dependencies={"platform.user_directory": 1},
    )

    directory = services.resolve("platform.user_directory", 1)
    users = directory.list_active_users()

    assert {field.name for field in fields(PublicUser)} == {
        "id",
        "username",
        "display_name",
        "active",
        "role",
    }
    assert all(type(user) is PublicUser and user.active is True for user in users)
    assert [user.username for user in users] == ["active_user", "admin"]
    assert directory.get_user(active["id"]) == PublicUser(
        id=active["id"],
        username="active_user",
        display_name="Active User",
        active=True,
        role="user",
    )
    assert directory.get_user(disabled["id"]) is None
    assert directory.get_user("missing") is None
    assert not any(
        hasattr(directory, name)
        for name in ("create_user", "update_user", "delete_user", "reset_password")
    )

    services.close()

    with pytest.raises(RuntimeError, match="platform service facade is closed"):
        directory.list_active_users()
    with pytest.raises(RuntimeError, match="platform service facade is closed"):
        directory.get_user(active["id"])


def test_public_user_includes_role(tmp_path):
    database = MemoryApplicationDatabase()
    auth_manager = AuthManager(tmp_path / "config.json", database=database)
    auth_manager.set_admin_password("AdminPass123")
    created = auth_manager.create_user(
        username="role_user",
        display_name="Role User",
        password="UserPass123",
        role="user",
        enabled=True,
    )
    registry = ServiceRegistry()
    registry.register_platform(create_user_directory_service(auth_manager))
    services = registry.for_module(
        "alpha",
        service_dependencies={"platform.user_directory": 1},
    )
    directory = services.resolve("platform.user_directory", 1)

    users = directory.list_active_users()
    by_id = {user.id: user for user in users}

    assert "role" in {field.name for field in fields(PublicUser)}
    assert by_id[created["id"]].role == "user"
    assert by_id[created["id"]] == PublicUser(
        id=created["id"],
        username="role_user",
        display_name="Role User",
        active=True,
        role="user",
    )
    admin = next(user for user in users if user.username == "admin")
    assert admin.role == "admin"


def _seed_dictionary_db():
    from auto_check.app.storage_dictionaries import create_dictionary, create_dictionary_item

    database = MemoryApplicationDatabase()
    with database.transaction() as connection:
        create_dictionary(connection, code="business_system", name="业务系统", updated_by="admin")
        create_dictionary_item(
            connection, dictionary_code="business_system", item_code="valuation",
            item_name="估值系统", sort_order=20, updated_by="admin",
        )
        create_dictionary_item(
            connection, dictionary_code="business_system", item_code="ta",
            item_name="TA估值", sort_order=10, updated_by="admin",
        )
        create_dictionary_item(
            connection, dictionary_code="business_system", item_code="off",
            item_name="停用项", enabled=False, updated_by="admin",
        )
    return database


def test_dictionary_service_lists_active_items_in_order_and_is_revocable():
    registry = ServiceRegistry()
    registry.register_platform(create_dictionary_service(_seed_dictionary_db()))
    services = registry.for_module("alpha", service_dependencies={"platform.dictionary": 1})
    dictionary = services.resolve("platform.dictionary", 1)

    items = dictionary.list_active_items("business_system")
    assert [item.code for item in items] == ["ta", "valuation"]
    assert all(isinstance(item, PublicDictionaryItem) for item in items)
    assert items[0].label == "TA估值"
    assert items[0].sort_order == 10
    hit = dictionary.get_active_item("business_system", "valuation")
    assert hit is not None and hit.label == "估值系统"
    assert dictionary.get_active_item("business_system", "off") is None
    assert dictionary.get_active_item("business_system", "ghost") is None
    assert dictionary.list_active_items("unknown_dict") == ()

    services.close()
    with pytest.raises(RuntimeError, match="closed"):
        dictionary.list_active_items("business_system")


def test_dictionary_service_hides_items_of_disabled_dictionary():
    from auto_check.app.storage_dictionaries import update_dictionary

    database = _seed_dictionary_db()
    with database.transaction() as connection:
        update_dictionary(connection, "business_system", enabled=False, updated_by="admin")
    registry = ServiceRegistry()
    registry.register_platform(create_dictionary_service(database))
    services = registry.for_module("alpha", service_dependencies={"platform.dictionary": 1})
    dictionary = services.resolve("platform.dictionary", 1)
    assert dictionary.list_active_items("business_system") == ()
    assert dictionary.get_active_item("business_system", "ta") is None


def test_dictionary_service_binds_independent_facades_per_owner():
    registry = ServiceRegistry()
    registry.register_platform(create_dictionary_service(_seed_dictionary_db()))
    first = registry.for_module("alpha", service_dependencies={"platform.dictionary": 1})
    second = registry.for_module("beta", service_dependencies={"platform.dictionary": 1})
    facade_a = first.resolve("platform.dictionary", 1)
    facade_b = second.resolve("platform.dictionary", 1)
    assert facade_a is not facade_b
    first.close()
    with pytest.raises(RuntimeError, match="closed"):
        facade_a.list_active_items("business_system")
    assert facade_b.list_active_items("business_system")
