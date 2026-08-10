from __future__ import annotations

from dataclasses import fields

import pytest

from auto_check.app.module_system.services import ServiceRegistry
from auto_check.app.platform_services import PublicUser, create_user_directory_service
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
