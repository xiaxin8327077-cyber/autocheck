from __future__ import annotations

import json

import pytest

from auto_check.app.language_model_platform import create_language_model_service
from auto_check.app.language_model_settings import (
    list_language_models,
    save_language_model,
    update_language_model,
)
from auto_check.app.module_system.services import ServiceRegistry
from auto_check.app.server import ApiRouter
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
