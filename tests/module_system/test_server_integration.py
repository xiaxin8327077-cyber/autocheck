from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from pathlib import Path

import pytest

from auto_check.app.module_system.contracts import ModuleBootstrapContext, ModuleHttpResponse
from auto_check.app.module_system.runtime import ModuleRuntime
from auto_check.app.security import AuthManager
from auto_check.app.server import ApiRouter, AutoCheckRequestHandler, ThreadingHTTPServer, web_root
import auto_check.app.server as server_module
from mysql_config_test_support import MemoryApplicationDatabase


FIXTURE_PARENT = Path(__file__).resolve().parents[1] / "fixtures"


class _StateStore:
    def __init__(self, database):
        self.enabled: dict[str, bool] = {}

    def save_discovered(self, manifest):
        self.enabled.setdefault(manifest.id, True)

    def load_enabled(self, module_id):
        return self.enabled.get(module_id)

    def set_enabled(self, module_id, enabled):
        self.enabled[module_id] = enabled

    def set_status(self, module_id, status, error=""):
        return None


class _MigrationRunner:
    def __init__(self, database, schema_registry=None):
        self.schema_registry = schema_registry

    def run(self, manifest, package_name):
        return manifest.schema_version


def _request(server, method, path, body=None, headers=None):
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    connection.request(
        method,
        path,
        body=payload,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    response = connection.getresponse()
    data = response.read()
    response_headers = {key.lower(): value for key, value in response.getheaders()}
    connection.close()
    return response.status, data, response_headers


def _read_http_response(reader):
    status_line = reader.readline().decode("iso-8859-1").strip()
    status = int(status_line.split(" ", 2)[1])
    headers = {}
    while line := reader.readline():
        decoded = line.decode("iso-8859-1").strip()
        if not decoded:
            break
        name, value = decoded.split(":", 1)
        headers[name.lower()] = value.strip()
    return status, reader.read(int(headers.get("content-length", "0"))), headers


@pytest.fixture
def module_server(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    import auto_check.app.module_system.runtime as runtime_module
    import module_packages.alpha.module as alpha_module

    monkeypatch.setattr(runtime_module, "ModuleStateStore", _StateStore)
    monkeypatch.setattr(runtime_module, "ModuleMigrationRunner", _MigrationRunner)

    def register_routes(self, router):
        def whoami_handler(request):
            route_calls.append(request)
            return ModuleHttpResponse.json(200, {"username": request.current_user["username"]})

        def tiny_handler(request):
            route_calls.append(request)
            return ModuleHttpResponse.json(200, {"ok": True})

        def snapshot_handler(request):
            body = {"top": "before", "nested": {"value": "before"}}
            response = ModuleHttpResponse.json(200, body)
            body["top"] = "after"
            body["nested"]["value"] = "after"
            return response

        router.add(
            "GET",
            "/whoami",
            whoami_handler,
            permission="alpha.view",
            max_body_bytes=0,
        )
        router.add(
            "POST",
            "/tiny",
            tiny_handler,
            permission="alpha.view",
            max_body_bytes=1,
        )
        router.add(
            "POST",
            "/echo",
            tiny_handler,
            permission="alpha.view",
            max_body_bytes=1024,
        )
        router.add(
            "GET",
            "/snapshot",
            snapshot_handler,
            permission="alpha.view",
            max_body_bytes=0,
        )

    route_calls = []
    monkeypatch.setattr(alpha_module.AlphaModule, "register_routes", register_routes)
    database = MemoryApplicationDatabase()
    runtime = ModuleRuntime.build(
        ModuleBootstrapContext(
            application_database=database,
            config_path=tmp_path / "config.json",
            temp_root=tmp_path / "module-data",
            now=lambda: None,
        ),
        package_name="module_packages",
    )
    runtime._loaded = [item for item in runtime._loaded if item.discovered.manifest.id == "alpha"]
    runtime.start()
    router = ApiRouter(
        config_path=tmp_path / "config.json",
        application_database=database,
        module_runtime=runtime,
    )
    auth_manager = AuthManager(router.config_path, database=database)

    class Handler(AutoCheckRequestHandler):
        pass

    Handler.protocol_version = "HTTP/1.1"
    Handler.router = router
    Handler.web_dir = web_root()
    Handler.auth_manager = auth_manager
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.module_route_calls = route_calls
    server.auth_manager = auth_manager
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, auth_manager
    finally:
        server.shutdown()
        server.server_close()
        runtime.stop()


@pytest.fixture
def authenticated_module_server(module_server):
    server, auth_manager = module_server
    auth_manager.set_admin_password("AdminPass123")
    session = auth_manager.login("admin", "AdminPass123")
    assert session is not None
    return server, {
        "Cookie": f"auto_check_session={session.session_id}",
        "X-CSRF-Token": session.csrf_token,
    }


def test_module_list_requires_login(module_server):
    server, _ = module_server
    status, data, headers = _request(server, "GET", "/api/system/modules")

    assert status == 401
    assert json.loads(data) == {"error": "login required"}


def test_authenticated_user_receives_visible_module_list(authenticated_module_server):
    server, auth_headers = authenticated_module_server
    status, data, headers = _request(server, "GET", "/api/system/modules", headers=auth_headers)

    assert status == 200
    payload = json.loads(data)
    assert payload["modules"][0]["id"] == "alpha"
    assert payload["release_notes"] == [
        {
            "module_id": "alpha",
            "module_name": "Alpha",
            "version": "1.0.0",
            "items": ["Alpha module note"],
        }
    ]
    assert payload["module_statuses"][0]["id"] == "alpha"


def test_module_mutation_requires_csrf(authenticated_module_server):
    server, auth_headers = authenticated_module_server
    status, data, headers = _request(
        server,
        "PUT",
        "/api/system/modules/alpha/state",
        {"enabled": False},
        {"Cookie": auth_headers["Cookie"], "X-CSRF-Token": ""},
    )

    assert status == 403


def test_module_api_uses_current_user(authenticated_module_server):
    server, auth_headers = authenticated_module_server
    status, data, headers = _request(
        server,
        "GET",
        "/api/modules/alpha/whoami",
        headers=auth_headers,
    )

    assert status == 200
    assert json.loads(data)["username"] == "admin"


def test_module_asset_blocks_traversal(module_server):
    server, _ = module_server
    status, data, headers = _request(
        server,
        "GET",
        "/module-assets/alpha/%2e%2e/manifest.json",
    )

    assert status == 404


def test_module_asset_uses_etag(module_server):
    server, _ = module_server
    status, data, headers = _request(server, "GET", "/module-assets/alpha/index.js")

    assert status == 200
    assert headers["etag"]
    assert headers["cache-control"] == "private, no-cache"
    status, data, headers = _request(
        server,
        "GET",
        "/module-assets/alpha/index.js",
        headers={"If-None-Match": headers["etag"]},
    )
    assert status == 304
    assert data == b""
    assert headers["cache-control"] == "private, no-cache"
    status, data, headers = _request(
        server,
        "GET",
        "/module-assets/alpha/index.js",
        headers={"If-None-Match": f'"unrelated", W/{headers["etag"]}'},
    )
    assert status == 304
    assert data == b""


def test_module_early_responses_consume_small_request_bodies(authenticated_module_server):
    server, auth_headers = authenticated_module_server

    cases = [
        ("POST", "/api/modules/alpha/tiny", {"value": "x"}, {}, 401),
        (
            "POST",
            "/api/modules/alpha/tiny",
            {"value": "x"},
            {"Cookie": auth_headers["Cookie"], "X-CSRF-Token": ""},
            403,
        ),
        ("POST", "/api/modules/alpha/missing", {}, auth_headers, 404),
        ("PUT", "/api/modules/alpha/whoami", {}, auth_headers, 405),
        ("POST", "/api/modules/alpha/tiny", {"value": "x"}, auth_headers, 413),
    ]
    for method, path, body, headers, expected_status in cases:
        status, _, _ = _request(server, method, path, body, headers)
        assert status == expected_status
        status, data, _ = _request(server, "GET", "/api/modules/alpha/whoami", headers=auth_headers)
        assert status == 200
        assert json.loads(data)["username"] == "admin"


def test_module_route_limit_rejects_declared_body_before_json_parse_or_handler(
    authenticated_module_server, monkeypatch
):
    server, auth_headers = authenticated_module_server
    parsed_bodies = []
    original_loads = server_module.json.loads

    def track_loads(value, *args, **kwargs):
        parsed_bodies.append(value)
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(server_module.json, "loads", track_loads)
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    connection.request(
        "POST",
        "/api/modules/alpha/tiny",
        body=b"x" * 1024,
        headers={"Content-Type": "application/json", **auth_headers},
    )
    response = connection.getresponse()
    response.read()
    connection.close()

    assert response.status == 413
    assert parsed_bodies == []
    assert server.module_route_calls == []


def test_incomplete_early_rejection_has_bounded_drain_and_closes_connection(module_server):
    server, _ = module_server
    connection = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=2)
    reader = connection.makefile("rb")
    try:
        connection.sendall(
            b"POST /api/modules/alpha/tiny HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 1024\r\n\r\n"
        )
        started = time.monotonic()
        status, _, headers = _read_http_response(reader)
        elapsed = time.monotonic() - started
    finally:
        reader.close()
        connection.close()

    assert status == 401
    assert elapsed < 1
    assert headers["connection"].lower() == "close"


def test_slow_early_rejection_body_uses_a_total_drain_deadline(module_server, monkeypatch):
    server, _ = module_server
    monkeypatch.setattr(server_module, "EARLY_DRAIN_TIMEOUT_SECONDS", 0.15)
    connection = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=1)
    reader = connection.makefile("rb")
    sender_errors = []

    def send_remaining_body():
        for _ in range(3):
            time.sleep(0.1)
            try:
                connection.sendall(b"x")
            except OSError as error:
                sender_errors.append(error)
                return

    try:
        connection.sendall(
            b"POST /api/modules/alpha/tiny HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 4\r\n\r\n"
            b"x"
        )
        sender = threading.Thread(target=send_remaining_body)
        started = time.monotonic()
        sender.start()
        status, _, headers = _read_http_response(reader)
        elapsed = time.monotonic() - started
        sender.join(timeout=1)
    finally:
        reader.close()
        connection.close()

    assert status == 401
    assert elapsed < 0.25
    assert headers["connection"].lower() == "close"


def test_complete_early_rejection_drains_before_next_request(module_server):
    server, _ = module_server
    connection = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=2)
    reader = connection.makefile("rb")
    try:
        connection.sendall(
            b"POST /api/modules/alpha/tiny HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 2\r\n\r\n{}"
        )
        first_status, _, first_headers = _read_http_response(reader)
        connection.sendall(b"GET /api/system/modules HTTP/1.1\r\nHost: localhost\r\n\r\n")
        second_status, _, _ = _read_http_response(reader)
    finally:
        reader.close()
        connection.close()

    assert first_status == 401
    assert "connection" not in first_headers
    assert second_status == 401


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        (b"Transfer-Encoding: chunked\r\n", 501),
        (b"Content-Length: nope\r\n", 400),
        (b"Content-Length: 2\r\nContent-Length: 3\r\n", 400),
    ],
)
def test_invalid_body_framing_closes_before_module_dispatch(module_server, headers, expected_status):
    server, _ = module_server
    connection = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=2)
    reader = connection.makefile("rb")
    try:
        connection.sendall(
            b"POST /api/modules/alpha/tiny HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            + headers
            + b"\r\n4\r\nbody\r\n0\r\n\r\n"
            + b"GET /api/modules/alpha/whoami HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )
        status, _, response_headers = _read_http_response(reader)
        remaining = reader.read()
    finally:
        reader.close()
        connection.close()

    assert status == expected_status
    assert response_headers["connection"].lower() == "close"
    assert remaining == b""
    assert server.module_route_calls == []


def test_module_state_write_checks_admin_before_parsing_body(
    authenticated_module_server, monkeypatch
):
    server, admin_headers = authenticated_module_server
    auth_manager = server.auth_manager
    admin_session = auth_manager.validate_session(admin_headers["Cookie"].split("=", 1)[1])
    assert admin_session is not None
    auth_manager.create_user(
        username="operator",
        display_name="Operator",
        password="Operator123",
        role="user",
        enabled=True,
        current_user_id=admin_session.user_id,
    )
    operator_session = auth_manager.login("operator", "Operator123")
    assert operator_session is not None
    parsed_bodies = []
    original_loads = server_module.json.loads

    def track_loads(value, *args, **kwargs):
        parsed_bodies.append(value)
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(server_module.json, "loads", track_loads)
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    connection.request(
        "PUT",
        "/api/system/modules/alpha/state",
        body=b"x" * 1024,
        headers={
            "Content-Type": "application/json",
            "Cookie": f"auto_check_session={operator_session.session_id}",
            "X-CSRF-Token": operator_session.csrf_token,
        },
    )
    response = connection.getresponse()
    response.read()
    connection.close()

    assert response.status == 403
    assert parsed_bodies == []


@pytest.mark.parametrize(
    ("headers", "body", "expected_status"),
    [
        (b"Transfer-Encoding: chunked\r\n", b"4\r\nbody\r\n0\r\n\r\n", 501),
        (b"Content-Length: nope\r\n", b"body", 400),
        (b"Content-Length: 2\r\nContent-Length: 3\r\n", b"body", 400),
        (b"Content-Length: 2\r\n", b"{}", 400),
    ],
)
def test_get_with_invalid_or_nonempty_framing_closes_before_dispatch(
    authenticated_module_server, headers, body, expected_status
):
    server, auth_headers = authenticated_module_server
    connection = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=2)
    reader = connection.makefile("rb")
    try:
        connection.sendall(
            b"GET /api/modules/alpha/whoami HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            + f"Cookie: {auth_headers['Cookie']}\r\n".encode("ascii")
            + headers
            + b"\r\n"
            + body
            + b"GET /api/modules/alpha/whoami HTTP/1.1\r\n"
            + b"Host: localhost\r\n"
            + f"Cookie: {auth_headers['Cookie']}\r\n\r\n".encode("ascii")
        )
        status, _, response_headers = _read_http_response(reader)
        remaining = reader.read()
    finally:
        reader.close()
        connection.close()

    assert status == expected_status
    assert response_headers["connection"].lower() == "close"
    assert remaining == b""
    assert server.module_route_calls == []


def test_get_without_body_framing_continues_to_dispatch(authenticated_module_server):
    server, auth_headers = authenticated_module_server

    status, data, _ = _request(server, "GET", "/api/modules/alpha/whoami", headers=auth_headers)

    assert status == 200
    assert json.loads(data)["username"] == "admin"
    assert len(server.module_route_calls) == 1


def test_authenticated_module_body_read_timeout_is_bounded_and_closes_connection(
    authenticated_module_server, monkeypatch
):
    server, auth_headers = authenticated_module_server
    monkeypatch.setattr(server_module, "MODULE_BODY_READ_TIMEOUT_SECONDS", 0.1)
    connection = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=1)
    reader = connection.makefile("rb")
    try:
        connection.sendall(
            b"POST /api/modules/alpha/echo HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 20\r\n"
            + f"Cookie: {auth_headers['Cookie']}\r\n".encode("ascii")
            + f"X-CSRF-Token: {auth_headers['X-CSRF-Token']}\r\n\r\n".encode("ascii")
            + b"{"
        )
        status, _, response_headers = _read_http_response(reader)
    finally:
        reader.close()
        connection.close()

    assert status == 408
    assert response_headers["connection"].lower() == "close"
    assert server.module_route_calls == []


def test_slow_module_body_exceeds_total_deadline_without_dispatch(
    authenticated_module_server, monkeypatch
):
    server, auth_headers = authenticated_module_server
    monkeypatch.setattr(server_module, "MODULE_BODY_READ_TIMEOUT_SECONDS", 0.2)
    connection = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=1)
    reader = connection.makefile("rb")
    try:
        connection.sendall(
            b"POST /api/modules/alpha/echo HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 4\r\n"
            + f"Cookie: {auth_headers['Cookie']}\r\n".encode("ascii")
            + f"X-CSRF-Token: {auth_headers['X-CSRF-Token']}\r\n\r\n".encode("ascii")
            + b"{"
        )
        for chunk in (b"}", b" "):
            time.sleep(0.08)
            connection.sendall(chunk)
        connection.settimeout(0.12)
        status, _, response_headers = _read_http_response(reader)
    finally:
        reader.close()
        connection.close()

    assert status == 408
    assert response_headers["connection"].lower() == "close"
    assert server.module_route_calls == []


def test_module_api_sends_the_verified_response_snapshot(authenticated_module_server):
    server, auth_headers = authenticated_module_server

    status, data, _ = _request(server, "GET", "/api/modules/alpha/snapshot", headers=auth_headers)

    assert status == 200
    assert json.loads(data) == {"top": "before", "nested": {"value": "before"}}


def test_authenticated_module_api_forces_private_no_store_cache(authenticated_module_server):
    server, auth_headers = authenticated_module_server

    status, _, headers = _request(
        server,
        "GET",
        "/api/modules/alpha/whoami",
        headers=auth_headers,
    )

    assert status == 200
    assert headers["cache-control"] == "private, no-store"


def test_short_module_body_is_rejected_before_dispatch(authenticated_module_server):
    server, auth_headers = authenticated_module_server
    connection = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=2)
    reader = connection.makefile("rb")
    try:
        connection.sendall(
            b"POST /api/modules/alpha/echo HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 4\r\n"
            + f"Cookie: {auth_headers['Cookie']}\r\n".encode("ascii")
            + f"X-CSRF-Token: {auth_headers['X-CSRF-Token']}\r\n\r\n".encode("ascii")
            + b"{}"
        )
        connection.shutdown(socket.SHUT_WR)
        status, _, response_headers = _read_http_response(reader)
    finally:
        reader.close()
        connection.close()

    assert status == 400
    assert response_headers["connection"].lower() == "close"
    assert server.module_route_calls == []
