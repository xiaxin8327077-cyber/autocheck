from __future__ import annotations

import json
import shutil
import socket
import ssl
import subprocess
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from auto_check.app import language_model_platform
from auto_check.app.language_model_platform import create_language_model_service
from auto_check.app.language_model_settings import (
    delete_language_model,
    list_language_models,
    save_language_model,
    update_language_model,
)
from auto_check.app.module_system.services import ServiceRegistry
from auto_check.app.server import ApiRouter, AutoCheckRequestHandler
from mysql_config_test_support import MemoryApplicationDatabase

INTRANET_KEY = "key-intranet"
EXTERNAL_KEY = "key-external"
EXTERNAL_URL = "https://api.example.com/v1"


def _database() -> MemoryApplicationDatabase:
    return MemoryApplicationDatabase()


def _save_pair(database: MemoryApplicationDatabase) -> tuple[dict, dict]:
    intranet = save_language_model(
        database,
        {
            "name": "内网模型",
            "base_url": "http://10.0.0.8/v1",
            "model_name": "qwen",
            "api_key": INTRANET_KEY,
            "enabled": True,
            "is_default": True,
        },
    )
    external = save_language_model(
        database,
        {
            "name": "外部模型",
            "base_url": EXTERNAL_URL,
            "model_name": "gpt",
            "api_key": EXTERNAL_KEY,
            "enabled": True,
            "is_default": True,
        },
    )
    return intranet, external


def _facade(database: MemoryApplicationDatabase, http_post):
    registry = ServiceRegistry()
    registry.register_platform(create_language_model_service(database, http_post=http_post))
    services = registry.for_module(
        "data_validation",
        service_dependencies={"platform.language_models": 1},
    )
    return services.resolve("platform.language_models", 1)


def test_save_two_models_and_keep_one_default():
    database = _database()
    intranet, external = _save_pair(database)
    listed = list_language_models(database)
    by_id = {item["id"]: item for item in listed}

    assert by_id[intranet["id"]]["is_default"] is False
    assert by_id[external["id"]]["is_default"] is True
    assert by_id[external["id"]]["has_api_key"] is True
    visible = json.dumps(listed, ensure_ascii=False)
    assert INTRANET_KEY not in visible
    assert EXTERNAL_KEY not in visible


@pytest.mark.parametrize("change", [{"base_url": "https://replacement.example.com/v1"}, {"api_key": "replacement-key"}])
def test_public_model_fingerprint_changes_with_endpoint_or_key_without_exposing_them(change):
    database = _database()
    _intranet, external = _save_pair(database)
    facade = _facade(database, None)
    before = next(item for item in facade.list_enabled() if item.id == external["id"])
    assert len(before.configuration_fingerprint) == 64
    assert next(item for item in facade.list_enabled() if item.id == external["id"]).configuration_fingerprint == before.configuration_fingerprint
    update_language_model(database, external["id"], change)
    after = next(item for item in facade.list_enabled() if item.id == external["id"])
    assert (after.id, after.name, after.model_name) == (before.id, before.name, before.model_name)
    assert after.configuration_fingerprint != before.configuration_fingerprint
    assert not hasattr(after, "base_url") and not hasattr(after, "api_key_encrypted")
    assert EXTERNAL_KEY not in repr(after) and "replacement-key" not in repr(after)


def test_blank_key_keeps_existing_secret():
    database = _database()
    intranet, _external = _save_pair(database)
    update_language_model(
        database,
        intranet["id"],
        {"name": "内网模型改名", "api_key": ""},
    )
    seen: list[dict[str, str]] = []

    def http_post(_url, headers, _body, _timeout):
        seen.append(headers)
        return json.dumps({"choices": [{"message": {"content": "ok"}}]})

    facade = _facade(database, http_post)
    text = facade.complete(
        intranet["id"],
        [{"role": "user", "content": "hi"}],
        timeout_seconds=5,
    )

    assert text == "ok"
    assert seen[0]["Authorization"] == f"Bearer {INTRANET_KEY}"


def test_disable_default_clears_default():
    database = _database()
    _intranet, external = _save_pair(database)
    update_language_model(database, external["id"], {"enabled": False})
    listed = list_language_models(database)

    assert all(item["is_default"] is False for item in listed)
    assert next(item for item in listed if item["id"] == external["id"])["enabled"] is False


def test_non_admin_cannot_read_model_settings(tmp_path):
    database = _database()
    _save_pair(database)
    router = ApiRouter(config_path=tmp_path / "config.json", application_database=database)

    status, payload = router.handle(
        "GET",
        "/api/settings/language-models",
        None,
        current_user={"id": "2", "role": "user"},
    )

    assert status == 403
    visible = json.dumps(payload, ensure_ascii=False)
    assert EXTERNAL_KEY not in visible
    assert EXTERNAL_URL not in visible


def test_complete_uses_selected_model_only():
    database = _database()
    _intranet, external = _save_pair(database)
    urls: list[str] = []

    def http_post(url, _headers, body, _timeout):
        urls.append(url)
        sent = json.loads(body.decode("utf-8"))
        assert sent["model"] == "gpt"
        return json.dumps({"choices": [{"message": {"content": "外部结果"}}]})

    facade = _facade(database, http_post)
    assert facade.complete(external["id"], [{"role": "user", "content": "hi"}], timeout_seconds=5) == "外部结果"
    assert urls == [f"{EXTERNAL_URL}/chat/completions"]


def _enable_local_tls(server, tmp_path, monkeypatch):
    openssl = shutil.which("openssl")
    git = shutil.which("git")
    if not openssl and git:
        bundled = Path(git).resolve().parent.parent / "mingw64" / "bin" / "openssl.exe"
        if bundled.is_file():
            openssl = str(bundled)
    if not openssl:
        pytest.skip("local TLS fixture needs the OpenSSL CLI")
    certificate, key = tmp_path / "model.pem", tmp_path / "model.key"
    subprocess.run([
        openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
        "-keyout", str(key), "-out", str(certificate),
    ], check=True, capture_output=True)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    monkeypatch.setenv("SSL_CERT_FILE", str(certificate))


@pytest.fixture
def stalled_model(monkeypatch, request, tmp_path):
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    waiting = Event()
    disconnected = Event()

    class ModelHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            mode = payload["messages"][0]["content"]
            if mode == "quick":
                response = b'{"choices":[{"message":{"content":"done"}}]}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
            if mode == "body":
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b"{")
            waiting.set()
            self.connection.settimeout(8)
            try:
                if self.connection.recv(1) == b"":
                    disconnected.set()
            except ConnectionResetError:
                disconnected.set()
            except TimeoutError:
                pass

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler) as server:
        mode = getattr(request, "param", "http")
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        if mode == "https":
            _enable_local_tls(server, tmp_path, monkeypatch)
            base_url = f"https://127.0.0.1:{server.server_port}/v1"
        if mode == "http-proxy":
            monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{server.server_port}")
            base_url = "http://test-model.invalid/v1"
        runner = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        runner.start()
        try:
            database = _database()
            _, model = _save_pair(database)
            update_language_model(database, model["id"], {"base_url": base_url})
            bound = create_language_model_service(database).binder("data_validation")
            yield bound, model["id"], waiting, disconnected
        finally:
            server.shutdown()
            runner.join()


@pytest.mark.parametrize("stage", ["headers", "body"])
@pytest.mark.parametrize("stalled_model", ["http", "https", "http-proxy"], indirect=True)
def test_cancel_waiting_model_disconnects_and_allows_another_call(stalled_model, stage):
    bound, model_id, waiting, disconnected = stalled_model
    cancel = Event()

    def chat(prompt, **kwargs):
        return bound.value.complete(model_id, [{"role": "user", "content": prompt}], **kwargs)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(chat, stage, timeout_seconds=None, cancel_event=cancel)
        try:
            assert waiting.wait(3), "model request did not arrive"
            assert pool.submit(chat, "quick", timeout_seconds=2).result(timeout=3) == "done"
        finally:
            cancel.set()
        with pytest.raises(RuntimeError, match="MODEL_CANCELLED"):
            pending.result(timeout=3)
        assert disconnected.wait(2), "upstream connection was left open"


def test_closing_facade_disconnects_inflight_request(stalled_model):
    bound, model_id, waiting, disconnected = stalled_model
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(bound.value.complete, model_id, [{"role": "user", "content": "headers"}], timeout_seconds=20)
        assert waiting.wait(3)
        pool.submit(bound.close).result(timeout=3)
        with pytest.raises(RuntimeError, match="closed"):
            pending.result(timeout=3)
        assert disconnected.wait(2)
        with pytest.raises(RuntimeError, match="closed"):
            bound.value.list_enabled()


@pytest.mark.parametrize("stalled_model", ["https"], indirect=True)
def test_model_request_rejects_untrusted_certificate(stalled_model, monkeypatch):
    bound, model_id, _, _ = stalled_model
    monkeypatch.delenv("SSL_CERT_FILE")
    with pytest.raises(RuntimeError, match="MODEL_UNAVAILABLE") as error:
        bound.value.complete(model_id, [{"role": "user", "content": "quick"}], timeout_seconds=2)
    assert isinstance(error.value.__cause__.reason, ssl.SSLCertVerificationError)


def test_cancel_during_connection_setup_skips_post(stalled_model, monkeypatch):
    bound, model_id, waiting, _ = stalled_model
    connected, resume, cancelled = Event(), Event(), Event()
    create_connection = socket.create_connection

    def delayed_connect(*args, **kwargs):
        sock = create_connection(*args, **kwargs)
        connected.set()
        resume.wait(3)
        return sock

    monkeypatch.setattr(socket, "create_connection", delayed_connect)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(bound.value.complete, model_id, [{"role": "user", "content": "headers"}],
                              timeout_seconds=None, cancel_event=cancelled)
        try:
            assert connected.wait(3)
            cancelled.set()
        finally:
            resume.set()
        with pytest.raises(RuntimeError, match="MODEL_CANCELLED"):
            pending.result(timeout=3)
        assert not waiting.wait(0.1)


def test_pre_cancelled_model_skips_network_and_timeouts_remain_per_request():
    database = _database()
    _, model = _save_pair(database)
    observed = []

    def http_post(url, headers, body, timeout):
        observed.append(timeout)
        return '{"choices":[{"message":{"content":"done"}}]}'

    facade = _facade(database, http_post)
    cancelled = Event()
    cancelled.set()
    with pytest.raises(RuntimeError, match="MODEL_CANCELLED"):
        facade.complete(model["id"], [], timeout_seconds=None, cancel_event=cancelled)
    assert observed == []
    assert facade.complete(model["id"], [], timeout_seconds=None) == "done"
    assert facade.complete(model["id"], [], timeout_seconds=7) == "done"
    assert observed == [None, 7]


def test_missing_model_does_not_call_network():
    calls: list[str] = []

    def http_post(url, _headers, _body, _timeout):
        calls.append(url)
        return "{}"

    empty = _database()
    with pytest.raises(RuntimeError, match="MODEL_UNAVAILABLE"):
        _facade(empty, http_post).complete("", [{"role": "user", "content": "hi"}], timeout_seconds=5)

    database = _database()
    intranet, external = _save_pair(database)
    update_language_model(database, intranet["id"], {"enabled": False})
    update_language_model(database, external["id"], {"enabled": False})
    facade = _facade(database, http_post)
    with pytest.raises(RuntimeError, match="MODEL_UNAVAILABLE"):
        facade.complete("", [{"role": "user", "content": "hi"}], timeout_seconds=5)
    with pytest.raises(RuntimeError, match="MODEL_UNAVAILABLE"):
        facade.complete(intranet["id"], [{"role": "user", "content": "hi"}], timeout_seconds=5)
    with pytest.raises(RuntimeError, match="MODEL_UNAVAILABLE"):
        facade.complete("missing", [{"role": "user", "content": "hi"}], timeout_seconds=5)
    assert calls == []


def test_full_chat_completions_address_is_used_as_written():
    database = _database()
    _, model = _save_pair(database)
    full_url = f"{EXTERNAL_URL}/chat/completions"
    update_language_model(database, model["id"], {"base_url": full_url})

    def http_post(url, _headers, _body, _timeout):
        assert url == full_url
        return '{"choices":[{"message":{"content":"OK"}}]}'

    assert _facade(database, http_post).complete(model["id"], [], timeout_seconds=5) == "OK"










def test_removed_local_seed_model_stays_deleted_on_catalog_reload(tmp_path, monkeypatch):
    path = tmp_path / "test-language-models.json"
    path.write_text(json.dumps({"models": [{"name": "本地测试", "base_url": EXTERNAL_URL,
                                           "model_name": "gpt", "api_key": EXTERNAL_KEY}]}), encoding="utf-8")
    monkeypatch.setenv("AUTO_CHECK_TEST_LANGUAGE_MODELS", str(path))
    database = _database()
    (seed,) = list_language_models(database)
    delete_language_model(database, seed["id"])
    assert list_language_models(database) == []
    assert _facade(database, None).list_enabled() == ()


def test_local_test_model_file_imports_without_exposing_secret(tmp_path, monkeypatch):
    path = tmp_path / "test-language-models.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "name": "测试模型（仅测试，非生产）",
                        "base_url": "https://note3-prev-api.askdiandian.com/v1",
                        "model_name": "dots3-note-prev",
                        "api_key": "local-test-secret",
                        "enabled": True,
                        "is_default": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTO_CHECK_TEST_LANGUAGE_MODELS", str(path))
    database = _database()

    first = list_language_models(database)
    second = list_language_models(database)

    assert len(first) == 1
    assert len(second) == 1
    assert first[0]["name"] == "测试模型（仅测试，非生产）"
    assert first[0]["base_url"] == "https://note3-prev-api.askdiandian.com/v1"
    assert first[0]["model_name"] == "dots3-note-prev"
    assert first[0]["has_api_key"] is True
    assert first[0]["is_default"] is True
    assert "local-test-secret" not in json.dumps(first, ensure_ascii=False)


def test_language_model_settings_card_is_admin_only():
    html = open("src/auto_check/web/index.html", encoding="utf-8").read()
    script = open("src/auto_check/web/app.js", encoding="utf-8").read()
    card_at = html.index("模型配置")
    source_at = html.index("数据源配置")
    assert card_at > source_at
    assert 'id="languageModelCard"' in html
    assert "admin-only" in html[html.index('id="languageModelCard"') - 200 : html.index('id="languageModelCard"')]
    assert "/api/settings/language-models" in script
    assert "languageModelModal" in html
    overlay_handler = script[script.index("languageModelModal") : script.index("languageModelModal") + 800]
    assert "languageModelModal.addEventListener" not in script
    assert "点击遮罩" not in overlay_handler
