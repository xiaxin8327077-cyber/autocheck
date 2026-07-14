import pytest

from auto_check.app.server import ApiRouter, STORAGE_ADMIN_DISABLED_ERROR
from mysql_config_test_support import MemoryApplicationDatabase


ADMIN_USER = {"id": "u-admin", "username": "admin", "display_name": "Admin", "role": "admin"}
NORMAL_USER = {"id": "u-user", "username": "user", "display_name": "User", "role": "user"}


def _router(config_path):
    return ApiRouter(config_path=config_path, application_database=MemoryApplicationDatabase())


def _legacy_db_path(config_path):
    return config_path.with_name("auto-check.db")


def test_admin_storage_router_requires_login_and_admin_role(tmp_path):
    config_path = tmp_path / "config.json"
    router = _router(config_path)

    assert router.handle("GET", "/api/admin/storage/tables", None, current_user=None)[0] == 401
    assert router.handle("GET", "/api/admin/storage/tables", None, current_user=NORMAL_USER)[0] == 403

    status, payload = router.handle("GET", "/api/admin/storage/tables", None, current_user=ADMIN_USER)

    assert status == 410
    assert payload["error"] == STORAGE_ADMIN_DISABLED_ERROR
    assert not _legacy_db_path(config_path).exists()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/admin/storage/health"),
        ("GET", "/api/admin/storage/tables"),
        ("GET", "/api/admin/storage/history-migration"),
        ("POST", "/api/admin/storage/history-migration"),
        ("POST", "/api/admin/storage/backup"),
        ("GET", "/api/admin/storage/tables/data_sources/schema"),
        ("GET", "/api/admin/storage/tables/data_sources/rows"),
    ],
)
def test_admin_storage_runtime_routes_are_disabled(tmp_path, method, path):
    config_path = tmp_path / "config.json"
    router = _router(config_path)

    status, payload = router.handle(method, path, {}, current_user=ADMIN_USER)

    assert status == 410
    assert payload["error"] == STORAGE_ADMIN_DISABLED_ERROR
    assert not _legacy_db_path(config_path).exists()


def test_admin_storage_exports_are_disabled(tmp_path):
    config_path = tmp_path / "config.json"
    router = _router(config_path)

    with pytest.raises(RuntimeError, match=STORAGE_ADMIN_DISABLED_ERROR):
        router.get_storage_schema_export(current_user=ADMIN_USER)
    with pytest.raises(RuntimeError, match=STORAGE_ADMIN_DISABLED_ERROR):
        router.get_storage_table_data_export("data_sources", current_user=ADMIN_USER)

    assert not _legacy_db_path(config_path).exists()
