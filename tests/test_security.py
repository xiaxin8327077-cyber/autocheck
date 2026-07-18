import json
import http.client
from io import BytesIO
import sys
import threading
import zipfile

import pytest
from Cryptodome.Cipher import PKCS1_OAEP
from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import RSA

from auto_check.app.config import ConfigStore, DataSourceConfig, DefaultSettings, NamedConfig, load_store, save_store
from auto_check.app.security import AuthManager, hash_password, sanitize_error_message
from auto_check.app.server import ApiRouter, AutoCheckRequestHandler, ThreadingHTTPServer, web_root
from mysql_config_test_support import MemoryApplicationDatabase


@pytest.fixture(autouse=True)
def shared_application_database(monkeypatch):
    database = MemoryApplicationDatabase()
    original_auth_init = AuthManager.__init__
    original_router_init = ApiRouter.__init__
    original_load_store = load_store
    original_save_store = save_store

    def auth_init(self, config_path, *, database_override=None, database=None):
        original_auth_init(self, config_path, database=database or database_override or shared_database)

    def router_init(self, *args, **kwargs):
        kwargs.setdefault("application_database", database)
        original_router_init(self, *args, **kwargs)

    def test_load_store(path=None, *, database=None):
        return original_load_store(path, database=database or shared_database)

    def test_save_store(store, path=None, *, database=None):
        return original_save_store(store, path, database=database or shared_database)

    shared_database = database
    monkeypatch.setattr(AuthManager, "__init__", auth_init)
    monkeypatch.setattr(ApiRouter, "__init__", router_init)
    monkeypatch.setattr(sys.modules[__name__], "load_store", test_load_store)
    monkeypatch.setattr(sys.modules[__name__], "save_store", test_save_store)
    return database


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content.encode("utf-8"))
    return buffer.getvalue()


def _start_auth_test_server(config_path):
    router = ApiRouter(config_path=config_path)

    class Handler(AutoCheckRequestHandler):
        pass

    Handler.router = router
    Handler.web_dir = web_root()
    Handler.auth_manager = AuthManager(router.config_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _start_static_test_server(config_path, web_dir):
    router = ApiRouter(config_path=config_path)

    class Handler(AutoCheckRequestHandler):
        pass

    Handler.router = router
    Handler.web_dir = web_dir
    Handler.auth_manager = AuthManager(router.config_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _json_request(server, method: str, path: str, body: dict | None = None, headers: dict | None = None):
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    conn.request(method, path, body=payload if method != "GET" else None, headers=request_headers)
    response = conn.getresponse()
    data = response.read().decode("utf-8")
    headers_map = {key.lower(): value for key, value in response.getheaders()}
    conn.close()
    return response.status, json.loads(data or "{}"), headers_map


def _encrypted_password(server, password: str) -> str:
    status, payload, _ = _json_request(server, "GET", "/api/auth/key")
    assert status == 200
    assert payload["public_key_jwk"]["kty"] == "RSA"
    assert payload["public_key_jwk"]["alg"] == "RSA-OAEP-256"
    key = RSA.import_key(payload["public_key_pem"])
    cipher = PKCS1_OAEP.new(key, hashAlgo=SHA256)
    return cipher.encrypt(password.encode("utf-8")).hex()


def test_auth_manager_sets_password_hash_and_validates_sessions(tmp_path, shared_application_database):
    config_path = tmp_path / "config.json"
    auth = AuthManager(config_path)

    assert auth.setup_required() is True
    auth.set_admin_password("StrongerPass123")

    rows = shared_application_database.connection.tables["users"]
    assert len(rows) == 1
    assert rows[0]["username"] == "admin"
    assert rows[0]["display_name"] == "管理员"
    assert rows[0]["role"] == "admin"
    assert rows[0]["password_hash"].startswith("pbkdf2_sha256$")
    assert "StrongerPass123" not in rows[0]["password_hash"]
    assert not config_path.exists()

    assert auth.login("admin", "wrong") is None
    session = auth.login("admin", "StrongerPass123")
    assert session is not None
    assert session.username == "admin"
    assert session.display_name == "管理员"
    assert session.role == "admin"
    assert auth.validate_session(session.session_id) is not None
    auth.logout(session.session_id)
    assert auth.validate_session(session.session_id) is None


def test_validate_session_does_not_write_user_storage(tmp_path, shared_application_database):
    auth = AuthManager(tmp_path / "config.json")
    auth.set_admin_password("StrongerPass123")
    session = auth.login("admin", "StrongerPass123")
    assert session is not None
    transaction_count = shared_application_database.transaction_count

    validated = auth.validate_session(session.session_id)

    assert validated is not None
    assert validated.username == "admin"
    assert shared_application_database.transaction_count == transaction_count


def test_auth_manager_persists_users_to_mysql_across_instances(tmp_path, shared_application_database):
    config_path = tmp_path / "config.json"
    auth = AuthManager(config_path)
    auth.set_admin_password("StrongerPass123")
    auth.create_user(username="operator", password="Operator123", role="user", display_name="Operator")

    restarted = AuthManager(config_path)
    session = restarted.login("operator", "Operator123")

    assert session is not None
    assert session.display_name == "Operator"
    assert session.role == "user"
    assert {row["username"] for row in shared_application_database.connection.tables["users"]} == {"admin", "operator"}
    assert not config_path.exists()


def test_auth_manager_persists_native_mysql_user_fields(tmp_path, shared_application_database):
    manager = AuthManager(tmp_path / "config.json")
    manager.set_admin_password("Admin123")
    manager.create_user(username="alice", password="Alice123", role="user")

    rows = sorted(shared_application_database.connection.tables["users"], key=lambda row: row["username"])
    assert [(row["username"], row["role"], row["enabled"]) for row in rows] == [
        ("admin", "admin", True),
        ("alice", "user", True),
    ]
    assert all(row["created_at"].__class__.__name__ == "datetime" for row in rows)
    assert all(row["updated_at"].__class__.__name__ == "datetime" for row in rows)


def test_deleting_user_prunes_interface_preferences_in_same_user_transaction(
    tmp_path, shared_application_database
):
    from auto_check.app.storage_user_interface_preferences import save_user_interface_preferences

    manager = AuthManager(tmp_path / "config.json")
    manager.set_admin_password("Admin123")
    admin = manager.list_users()[0]
    operator = manager.create_user(
        username="operator",
        password="Operator123",
        role="user",
    )

    with shared_application_database.transaction() as connection:
        save_user_interface_preferences(
            connection,
            admin["id"],
            radius_px=4,
            theme_gradient_enabled=False,
            line_chart_style="straight",
        )
        save_user_interface_preferences(
            connection,
            operator["id"],
            radius_px=12,
            theme_gradient_enabled=False,
            line_chart_style="straight",
        )

    transaction_count = shared_application_database.transaction_count
    manager.delete_user(operator["id"], current_user_id=admin["id"])

    assert shared_application_database.transaction_count == transaction_count + 1
    rows = shared_application_database.connection.tables["user_interface_preferences"]
    assert [(row["user_id"], row["radius_px"]) for row in rows] == [(admin["id"], 4)]


def test_user_replacement_rolls_back_when_interface_preferences_prune_fails(
    tmp_path, shared_application_database, monkeypatch
):
    import auto_check.app.storage_user_interface_preferences as preference_storage

    manager = AuthManager(tmp_path / "config.json")
    manager.set_admin_password("Admin123")
    admin = manager.list_users()[0]
    operator = manager.create_user(
        username="operator",
        password="Operator123",
        role="user",
    )
    original_user_ids = {
        row["id"] for row in shared_application_database.connection.tables["users"]
    }

    def fail_prune(connection, active_user_ids):
        raise RuntimeError("prune failed")

    monkeypatch.setattr(
        preference_storage,
        "prune_user_interface_preferences",
        fail_prune,
    )

    with pytest.raises(RuntimeError, match="prune failed"):
        manager.delete_user(operator["id"], current_user_id=admin["id"])

    assert {
        row["id"] for row in shared_application_database.connection.tables["users"]
    } == original_user_ids


def test_auth_manager_user_writes_hold_lock(tmp_path):
    manager = AuthManager(tmp_path / "config.json")
    original_save_users = manager._save_users
    write_checks = []

    def save_users_with_lock_assertion(users):
        write_checks.append(True)
        assert manager._users_lock._is_owned()
        original_save_users(users)

    manager._save_users = save_users_with_lock_assertion

    manager.set_admin_password("Admin123")
    admin = manager.list_users()[0]

    session = manager.login("admin", "Admin123")
    assert session is not None

    operator = manager.create_user(
        username="operator",
        password="Operator123",
        role="user",
        current_user_id=admin["id"],
    )
    manager.update_user(
        operator["id"],
        display_name="Operator Updated",
        current_user_id=admin["id"],
    )
    manager.reset_password(operator["id"], "Operator456", current_user_id=admin["id"])
    manager.delete_user(operator["id"], current_user_id=admin["id"])

    assert len(write_checks) == 6


def test_auth_session_uses_configured_idle_expire_hours_and_renews_on_activity(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    save_store(ConfigStore(default_settings=DefaultSettings(session_expire_hours=2)), config_path)
    auth = AuthManager(config_path)
    auth.set_admin_password("StrongerPass123")

    times = iter([1000.0, 1000.0 + 60 * 60, 1000.0 + 3 * 60 * 60 + 1])
    monkeypatch.setattr("auto_check.app.security.time.time", lambda: next(times))

    session = auth.login("admin", "StrongerPass123")
    assert session is not None
    assert session.expires_at == 1000.0 + 2 * 60 * 60

    renewed = auth.validate_session(session.session_id)
    assert renewed is not None
    assert renewed.expires_at == 1000.0 + 3 * 60 * 60

    assert auth.validate_session(session.session_id) is None


def test_new_auth_passwords_require_six_chars_and_one_letter(tmp_path):
    config_path = tmp_path / "config.json"
    auth = AuthManager(config_path)

    for invalid_password in ["123456", "abc12"]:
        with pytest.raises(ValueError, match="password must be at least 6 characters and include a letter"):
            auth.set_admin_password(invalid_password)

    auth.set_admin_password("abc123")
    assert auth.login("admin", "abc123") is not None

    for invalid_password in ["123456", "abc12"]:
        with pytest.raises(ValueError, match="password must be at least 6 characters and include a letter"):
            auth.create_user(username=f"user_{invalid_password}", password=invalid_password, role="user")

    operator = auth.create_user(username="operator", password="op123a", role="user")
    with pytest.raises(ValueError, match="password must be at least 6 characters and include a letter"):
        auth.reset_password(operator["id"], "123456")

    auth.reset_password(operator["id"], "xy789z")
    assert auth.login("operator", "xy789z") is not None


def test_auth_does_not_automatically_migrate_config_json(tmp_path, shared_application_database):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"auth": {"admin_password_hash": hash_password("Admin123")}}),
        encoding="utf-8",
    )

    manager = AuthManager(config_path)

    assert manager.setup_required() is True
    assert manager.login("admin", "Admin123") is None
    assert shared_application_database.connection.tables["users"] == []


def test_manually_imported_mysql_users_are_immediately_valid(tmp_path, shared_application_database):
    from auto_check.app.storage_users import replace_users

    with shared_application_database.transaction() as connection:
        replace_users(
            connection,
            [
                {
                    "id": "u-admin",
                    "username": "admin",
                    "display_name": "管理员",
                    "role": "admin",
                    "password_hash": hash_password("Admin123"),
                    "enabled": True,
                    "created_at": "2026-07-01 10:00:00",
                    "updated_at": "2026-07-01 10:00:00",
                    "last_login_at": "",
                }
            ],
        )

    manager = AuthManager(tmp_path / "config.json")
    session = manager.login("admin", "Admin123")

    assert session is not None
    assert session.display_name == "管理员"

def test_login_failure_response_does_not_enumerate_accounts(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        encrypted = _encrypted_password(server, "StrongerPass123")
        status, payload, _ = _json_request(server, "POST", "/api/auth/setup", {"password_encrypted": encrypted})
        assert status == 200

        wrong_admin_password = _encrypted_password(server, "WrongPass123")
        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {"username": "admin", "password_encrypted": wrong_admin_password},
        )
        assert status == 401
        assert payload["error"] == "invalid credentials"

        missing_user_password = _encrypted_password(server, "Whatever123")
        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {"username": "missing-user", "password_encrypted": missing_user_password},
        )
        assert status == 401
        assert payload["error"] == "invalid credentials"
    finally:
        server.shutdown()
        server.server_close()


def test_auth_logout_requires_csrf_and_clears_session_cookie(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        encrypted = _encrypted_password(server, "StrongerPass123")
        status, payload, headers = _json_request(server, "POST", "/api/auth/setup", {"password_encrypted": encrypted})
        assert status == 200
        cookie = headers["set-cookie"].split(";", 1)[0]
        csrf_token = payload["csrf_token"]

        status, payload, _ = _json_request(server, "POST", "/api/auth/logout", {}, {"Cookie": cookie})
        assert status == 403
        assert payload["error"] == "invalid csrf token"

        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/logout",
            {},
            {"Cookie": cookie, "X-CSRF-Token": csrf_token},
        )
        assert status == 200
        assert payload["ok"] is True
        assert "Max-Age=0" in headers["set-cookie"]

        status, payload, _ = _json_request(server, "GET", "/api/auth/status", None, {"Cookie": cookie})
        assert status == 200
        assert payload["authenticated"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_auth_password_endpoints_reject_plaintext_passwords(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, _ = _json_request(server, "POST", "/api/auth/setup", {"password": "StrongerPass123"})
        assert status == 400
        assert payload["error"] == "encrypted password is required"

        encrypted = _encrypted_password(server, "StrongerPass123")
        status, payload, headers = _json_request(server, "POST", "/api/auth/setup", {"password_encrypted": encrypted})
        assert status == 200
        cookie = headers["set-cookie"].split(";", 1)[0]

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {"username": "admin", "password": "StrongerPass123"},
        )
        assert status == 400
        assert payload["error"] == "encrypted password is required"

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {"username": "admin", "password_encrypted": _encrypted_password(server, "StrongerPass123")},
            {"Cookie": cookie},
        )
        assert status == 200
        assert payload["user"]["username"] == "admin"
        assert payload["user"]["role"] == "admin"
        assert payload["user"]["id"]
    finally:
        server.shutdown()
        server.server_close()


def test_interface_settings_http_requires_login_uses_csrf_and_isolates_users(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, _ = _json_request(server, "GET", "/api/settings/interface")
        assert status == 401
        assert payload == {"error": "login required"}

        status, admin_login, headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        assert status == 200
        admin_cookie = headers["set-cookie"].split(";", 1)[0]
        admin_headers = {
            "Cookie": admin_cookie,
            "X-CSRF-Token": admin_login["csrf_token"],
        }

        status, payload, _ = _json_request(
            server, "GET", "/api/settings/interface", None, admin_headers
        )
        assert status == 200
        assert payload == {
            "settings": {
                "radius_px": 4,
                "theme_gradient_enabled": False,
                "line_chart_style": "straight",
            }
        }

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/settings/interface",
            {"radius_px": 6, "theme_gradient_enabled": True, "line_chart_style": "smooth"},
            admin_headers,
        )
        assert status == 200
        assert payload == {
            "settings": {
                "radius_px": 6,
                "theme_gradient_enabled": True,
                "line_chart_style": "smooth",
            }
        }

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "operator",
                "role": "user",
                "password_encrypted": _encrypted_password(server, "Operator123"),
                "enabled": True,
            },
            admin_headers,
        )
        assert status == 200

        status, operator_login, headers = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {
                "username": "operator",
                "password_encrypted": _encrypted_password(server, "Operator123"),
            },
        )
        assert status == 200
        operator_cookie = headers["set-cookie"].split(";", 1)[0]

        status, payload, _ = _json_request(
            server,
            "GET",
            "/api/settings/interface",
            None,
            {"Cookie": operator_cookie},
        )
        assert status == 200
        assert payload == {
            "settings": {
                "radius_px": 4,
                "theme_gradient_enabled": False,
                "line_chart_style": "straight",
            }
        }

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/settings/interface",
            None,
            {"Cookie": operator_cookie},
        )
        assert status == 403
        assert payload == {"error": "invalid csrf token"}

        operator_headers = {
            "Cookie": operator_cookie,
            "X-CSRF-Token": operator_login["csrf_token"],
        }
        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/settings/interface",
            {"radius_px": 12, "theme_gradient_enabled": False, "line_chart_style": "straight"},
            operator_headers,
        )
        assert status == 200
        assert payload == {
            "settings": {
                "radius_px": 12,
                "theme_gradient_enabled": False,
                "line_chart_style": "straight",
            }
        }

        status, payload, _ = _json_request(
            server, "GET", "/api/settings/interface", None, operator_headers
        )
        assert status == 200
        assert payload == {
            "settings": {
                "radius_px": 12,
                "theme_gradient_enabled": False,
                "line_chart_style": "straight",
            }
        }

        status, payload, _ = _json_request(
            server, "GET", "/api/settings/interface", None, admin_headers
        )
        assert status == 200
        assert payload == {
            "settings": {
                "radius_px": 6,
                "theme_gradient_enabled": True,
                "line_chart_style": "smooth",
            }
        }
    finally:
        server.shutdown()
        server.server_close()


def test_admin_can_manage_users_and_plaintext_user_passwords_are_rejected(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        assert status == 200
        admin_cookie = headers["set-cookie"].split(";", 1)[0]
        csrf = payload["csrf_token"]
        admin_headers = {"Cookie": admin_cookie, "X-CSRF-Token": csrf}

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {"username": "operator", "role": "user", "password": "Operator123", "enabled": True},
            admin_headers,
        )
        assert status == 400
        assert payload["error"] == "encrypted password is required"

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "operator",
                "role": "user",
                "password_encrypted": _encrypted_password(server, "Operator123"),
                "enabled": True,
            },
            admin_headers,
        )
        assert status == 200
        operator_id = payload["user"]["id"]
        assert payload["user"]["username"] == "operator"
        assert payload["user"]["display_name"] == "operator"
        assert payload["user"]["role"] == "user"
        assert "password_hash" not in json.dumps(payload, ensure_ascii=False)

        status, payload, _ = _json_request(server, "GET", "/api/users", None, admin_headers)
        assert status == 200
        assert {user["username"] for user in payload["users"]} == {"admin", "operator"}

        status, payload, _ = _json_request(
            server,
            "POST",
            f"/api/users/{operator_id}/reset-password",
            {"password_encrypted": _encrypted_password(server, "Operator456")},
            admin_headers,
        )
        assert status == 200

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{operator_id}",
            {"role": "user", "enabled": False},
            admin_headers,
        )
        assert status == 200
        assert payload["user"]["enabled"] is False

        status, payload, _ = _json_request(server, "DELETE", f"/api/users/{operator_id}", None, admin_headers)
        assert status == 200
        assert payload["ok"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_regular_user_cannot_access_user_management_and_admin_self_protection(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        admin_cookie = headers["set-cookie"].split(";", 1)[0]
        admin_headers = {"Cookie": admin_cookie, "X-CSRF-Token": payload["csrf_token"]}

        status, create_payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "operator",
                "role": "user",
                "password_encrypted": _encrypted_password(server, "Operator123"),
                "enabled": True,
            },
            admin_headers,
        )
        assert status == 200

        status, user_login, user_headers = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {"username": "operator", "password_encrypted": _encrypted_password(server, "Operator123")},
        )
        assert status == 200
        user_auth_headers = {
            "Cookie": user_headers["set-cookie"].split(";", 1)[0],
            "X-CSRF-Token": user_login["csrf_token"],
        }

        status, payload, _ = _json_request(server, "GET", "/api/users", None, user_auth_headers)
        assert status == 403
        assert payload["error"] == "admin role required"

        status, admin_status, _ = _json_request(server, "GET", "/api/auth/status", None, admin_headers)
        admin_id = admin_status["user"]["id"]
        status, payload, _ = _json_request(server, "DELETE", f"/api/users/{admin_id}", None, admin_headers)
        assert status == 400
        assert payload["error"] == "cannot delete yourself"

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{admin_id}",
            {"role": "admin", "enabled": False},
            admin_headers,
        )
        assert status == 400
        assert payload["error"] == "cannot disable yourself"
    finally:
        server.shutdown()
        server.server_close()


def test_only_initial_admin_account_cannot_be_disabled_or_deleted(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        assert status == 200
        admin_headers = {"Cookie": headers["set-cookie"].split(";", 1)[0], "X-CSRF-Token": payload["csrf_token"]}

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "auditor",
                "role": "admin",
                "password_encrypted": _encrypted_password(server, "Auditor123"),
                "enabled": True,
            },
            admin_headers,
        )
        assert status == 200
        auditor_id = payload["user"]["id"]

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{auditor_id}",
            {"enabled": False},
            admin_headers,
        )
        assert status == 200
        assert payload["user"]["enabled"] is False

        status, payload, _ = _json_request(server, "DELETE", f"/api/users/{auditor_id}", None, admin_headers)
        assert status == 200
        assert payload["ok"] is True

        status, admin_status, _ = _json_request(server, "GET", "/api/auth/status", None, admin_headers)
        initial_admin_id = admin_status["user"]["id"]
        assert admin_status["user"]["username"] == "admin"

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "auditor2",
                "role": "admin",
                "password_encrypted": _encrypted_password(server, "Auditor456"),
                "enabled": True,
            },
            admin_headers,
        )
        assert status == 200
        auditor2_id = payload["user"]["id"]
        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {"username": "auditor2", "password_encrypted": _encrypted_password(server, "Auditor456")},
        )
        assert status == 200
        auditor_headers = {"Cookie": headers["set-cookie"].split(";", 1)[0], "X-CSRF-Token": payload["csrf_token"]}

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{initial_admin_id}",
            {"enabled": False},
            auditor_headers,
        )
        assert status == 400
        assert payload["error"] == "initial admin cannot be disabled"

        status, payload, _ = _json_request(server, "DELETE", f"/api/users/{initial_admin_id}", None, auditor_headers)
        assert status == 400
        assert payload["error"] == "initial admin cannot be deleted"

        status, payload, _ = _json_request(server, "DELETE", f"/api/users/{auditor2_id}", None, admin_headers)
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_initial_admin_cannot_be_demoted_and_can_change_own_password(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        assert status == 200
        admin_headers = {"Cookie": headers["set-cookie"].split(";", 1)[0], "X-CSRF-Token": payload["csrf_token"]}

        status, admin_status, _ = _json_request(server, "GET", "/api/auth/status", None, admin_headers)
        assert status == 200
        initial_admin_id = admin_status["user"]["id"]

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{initial_admin_id}",
            {"role": "user", "enabled": True},
            admin_headers,
        )
        assert status == 400
        assert payload["error"] == "initial admin role cannot be changed"

        status, payload, _ = _json_request(
            server,
            "POST",
            f"/api/users/{initial_admin_id}/reset-password",
            {"password_encrypted": _encrypted_password(server, "AdminPass456")},
            admin_headers,
        )
        assert status == 200

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {"username": "admin", "password_encrypted": _encrypted_password(server, "AdminPass456")},
        )
        assert status == 200
        assert payload["user"]["username"] == "admin"
    finally:
        server.shutdown()
        server.server_close()


def test_delegated_admin_can_only_manage_regular_users(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        assert status == 200
        admin_headers = {"Cookie": headers["set-cookie"].split(";", 1)[0], "X-CSRF-Token": payload["csrf_token"]}

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "auditor",
                "role": "admin",
                "password_encrypted": _encrypted_password(server, "Auditor123"),
                "enabled": True,
            },
            admin_headers,
        )
        assert status == 200
        delegated_admin_id = payload["user"]["id"]

        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {"username": "auditor", "password_encrypted": _encrypted_password(server, "Auditor123")},
        )
        assert status == 200
        delegated_headers = {"Cookie": headers["set-cookie"].split(";", 1)[0], "X-CSRF-Token": payload["csrf_token"]}

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "another_admin",
                "role": "admin",
                "password_encrypted": _encrypted_password(server, "Another123"),
                "enabled": True,
            },
            delegated_headers,
        )
        assert status == 400
        assert payload["error"] == "only initial admin can create admin users"

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{delegated_admin_id}",
            {"role": "user", "enabled": True},
            delegated_headers,
        )
        assert status == 400
        assert payload["error"] == "delegated admin cannot edit admin users"

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "operator",
                "role": "user",
                "password_encrypted": _encrypted_password(server, "Operator123"),
                "enabled": True,
            },
            delegated_headers,
        )
        assert status == 200
        operator_id = payload["user"]["id"]

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{operator_id}",
            {"role": "admin", "enabled": True},
            delegated_headers,
        )
        assert status == 400
        assert payload["error"] == "only initial admin can create admin users"

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{operator_id}",
            {"role": "user", "enabled": False},
            delegated_headers,
        )
        assert status == 200
        assert payload["user"]["enabled"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_admin_can_create_and_update_user_display_name(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        assert status == 200
        assert payload["user"]["display_name"] == "管理员"
        admin_headers = {"Cookie": headers["set-cookie"].split(";", 1)[0], "X-CSRF-Token": payload["csrf_token"]}

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "operator",
                "display_name": "张三",
                "role": "user",
                "password_encrypted": _encrypted_password(server, "Operator123"),
                "enabled": True,
            },
            admin_headers,
        )
        assert status == 200
        operator_id = payload["user"]["id"]
        assert payload["user"]["display_name"] == "张三"

        status, payload, _ = _json_request(
            server,
            "PUT",
            f"/api/users/{operator_id}",
            {"display_name": "李四", "role": "user", "enabled": True},
            admin_headers,
        )
        assert status == 200
        assert payload["user"]["display_name"] == "李四"

        status, payload, _ = _json_request(server, "GET", "/api/users", None, admin_headers)
        assert status == 200
        assert {user["display_name"] for user in payload["users"]} >= {"管理员", "李四"}
    finally:
        server.shutdown()
        server.server_close()


def test_config_list_redacts_passwords_and_blank_password_keeps_existing(tmp_path):
    config_path = tmp_path / "config.json"
    save_store(
        ConfigStore(
            configs=[
                NamedConfig(
                    name="local",
                    dws=DataSourceConfig("postgresql", "localhost", 5432, "dwdb", "dws", "u", "p"),
                    business=DataSourceConfig("mysql", "localhost", 3306, "bizdb", "", "u2", "p2"),
                    is_default=True,
                )
            ],
            default_name="local",
        ),
        config_path,
    )
    router = ApiRouter(config_path=config_path)

    status, payload = router.handle("GET", "/api/configs", None)

    assert status == 200
    sources = {source["id"]: source for source in payload["data_sources"]}
    dws = sources["legacy:local:dws"]
    business = sources["legacy:local:business"]
    assert "password" not in dws
    assert "password" not in business
    assert dws["password_set"] is True
    assert business["password_set"] is True

    status, payload = router.handle(
        "POST",
        "/api/configs",
        {
            "editing_name": "local",
            "name": "local",
            "dws": {
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "dwdb2",
                "schema": "dws",
                "username": "u",
                "password": "",
            },
            "business": {
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database": "bizdb2",
                "schema": "",
                "username": "u2",
                "password": "",
            },
        },
    )

    assert status == 200
    loaded = load_store(config_path)
    assert loaded.configs[0].dws.password == "p"
    assert loaded.configs[0].business.password == "p2"


def test_config_password_transport_requires_encrypted_values(tmp_path, shared_application_database):
    config_path = tmp_path / "config.json"
    server = _start_auth_test_server(config_path)
    try:
        status, payload, headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        assert status == 200
        cookie = headers["set-cookie"].split(";", 1)[0]
        auth_headers = {"Cookie": cookie, "X-CSRF-Token": payload["csrf_token"]}

        plaintext_body = {
            "name": "local",
            "dws": {
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "dwdb",
                "schema": "dws",
                "username": "u",
                "password": "dws-secret",
            },
            "business": {
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database": "bizdb",
                "schema": "",
                "username": "u2",
                "password": "biz-secret",
            },
        }
        status, payload, _ = _json_request(server, "POST", "/api/configs", plaintext_body, auth_headers)
        assert status == 400
        assert payload["error"] == "encrypted database password is required"

        status, payload, _ = _json_request(server, "POST", "/api/test-connection", plaintext_body, auth_headers)
        assert status == 400
        assert payload["error"] == "encrypted database password is required"

        encrypted_body = {
            "name": "local",
            "dws": {
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "dwdb",
                "schema": "dws",
                "username": "u",
                "password_encrypted": _encrypted_password(server, "dws-secret"),
            },
            "business": {
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database": "bizdb",
                "schema": "",
                "username": "u2",
                "password_encrypted": _encrypted_password(server, "biz-secret"),
            },
        }
        status, payload, _ = _json_request(server, "POST", "/api/configs", encrypted_body, auth_headers)
        assert status == 200

        loaded = load_store(config_path)
        saved = next(config for config in loaded.configs if config.name == "local")
        assert saved.dws.password == "dws-secret"
        assert saved.business.password == "biz-secret"
        assert not config_path.exists()
        rows = shared_application_database.connection.tables["data_sources"]
        assert len(rows) == 2
        raw = json.dumps(rows, ensure_ascii=False, default=str)
        assert "dws-secret" not in raw
        assert "biz-secret" not in raw
        assert all(row["password_encrypted"] for row in rows)
    finally:
        server.shutdown()
        server.server_close()


def test_legacy_config_endpoint_rejects_plaintext_passwords(tmp_path):
    router = ApiRouter(config_path=tmp_path / "config.json")

    status, payload = router.handle(
        "POST",
        "/api/config",
        {
            "dws": {
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "dwdb",
                "schema": "dws",
                "username": "u",
                "password": "dws-secret",
            },
            "business": {
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database": "bizdb",
                "schema": "",
                "username": "u2",
                "password": "biz-secret",
            },
        },
    )

    assert status == 400
    assert payload["error"] == "encrypted database password is required"


def test_config_export_is_redacted(tmp_path):
    config_path = tmp_path / "config.json"
    save_store(
        ConfigStore(
            configs=[
                NamedConfig(
                    name="local",
                    dws=DataSourceConfig("postgresql", "localhost", 5432, "dwdb", "dws", "u", "p"),
                    business=DataSourceConfig("mysql", "localhost", 3306, "bizdb", "", "u2", "p2"),
                    is_default=True,
                )
            ],
            default_name="local",
        ),
        config_path,
    )
    router = ApiRouter(config_path=config_path)

    status, payload = router.handle("GET", "/api/configs/export", None)

    assert status == 200
    text = json.dumps(payload, ensure_ascii=False)
    assert '"password"' not in text
    assert '"password_set": true' in text
    assert "p2" not in text


def test_pbc_upload_rejects_oversized_payload(tmp_path):
    router = ApiRouter(config_path=tmp_path / "config.json", max_upload_bytes=16)

    status, payload = router.handle_pbc_import_upload(
        "public_information.csv",
        b"Product Code,Product Name\nP1,Product One\n",
    )

    assert status == 413
    assert payload["error"] == "uploaded file is too large"


def test_pbc_upload_accepts_archive_when_compressed_file_is_under_50mb(tmp_path):
    router = ApiRouter(config_path=tmp_path / "config.json")
    header = b"Product Code,Product Name\n"
    repeated_row = b"P1,Product One\n"
    content = header + repeated_row * ((50 * 1024 * 1024) // len(repeated_row) + 1)
    archive = _zip_bytes({"large_public_information.csv": content.decode("utf-8")})

    assert len(archive) < 50 * 1024 * 1024
    assert len(content) > 50 * 1024 * 1024

    status, payload = router.handle_pbc_import_upload("pbc.zip", archive)

    assert status == 200
    assert payload["columns"] == ["Product Code", "Product Name"]
    assert payload["files"][0]["name"] == "large_public_information.csv"


def test_archive_member_limits_block_suspicious_payloads(tmp_path):
    router = ApiRouter(config_path=tmp_path / "config.json", max_archive_member_bytes=8)

    status, payload = router.handle_pbc_import_upload(
        "pbc.zip",
        _zip_bytes({"fund.csv": "Product Code,Product Name\nP1,Product One\n"}),
    )

    assert status == 400
    assert "too large" in payload["error"]


def test_error_message_sanitizer_hides_passwords_and_sql_details():
    raw = "password=abc123; SELECT * FROM secret_table WHERE user='u'"

    assert sanitize_error_message(raw) == "操作失败，请检查输入或联系管理员"


def test_static_file_server_blocks_sibling_prefix_path_traversal(tmp_path):
    web_dir = tmp_path / "web"
    sibling_dir = tmp_path / "web-secret"
    web_dir.mkdir()
    sibling_dir.mkdir()
    (web_dir / "index.html").write_text("OK", encoding="utf-8")
    (sibling_dir / "secret.txt").write_text("TOP_SECRET", encoding="utf-8")
    server = _start_static_test_server(tmp_path / "config.json", web_dir)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/../web-secret/secret.txt")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        conn.close()

        assert response.status == 404
        assert "TOP_SECRET" not in body
    finally:
        server.shutdown()
        server.server_close()
