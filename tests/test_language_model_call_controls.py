import json
from threading import Event

import pytest

from auto_check.app.language_model_platform import create_language_model_service
from auto_check.app.module_system.services import ServiceRegistry
from tests.test_language_model_settings import _database, _facade, _save_pair


@pytest.mark.parametrize("effort", ["low", "none"])
def test_v2_controls_preserve_old_consumer_and_return_only_safe_diagnostics(effort):
    database = _database()
    _, selected = _save_pair(database)
    requests = []

    def post(_url, _headers, body, timeout):
        requests.append((json.loads(body), timeout))
        return json.dumps({
            "model": "served-model", "choices": [{"finish_reason": "stop", "message": {
                "content": '{"ok":true}', "reasoning_content": "private reasoning",
            }}],
            "usage": {"prompt_tokens": 90, "completion_tokens": 12, "total_tokens": 102,
                      "prompt_cache_hit_tokens": 64, "completion_tokens_details": {"reasoning_tokens": 4},
                      "untrusted": "private metadata"},
        })

    registry = ServiceRegistry()
    registry.register_platform(create_language_model_service(database, http_post=post))
    services = registry.for_module("data_validation", service_dependencies={"platform.language_models": 1})
    old = services.resolve("platform.language_models", 1)
    new = services.resolve("platform.language_models", 2)
    assert old is new
    assert old.complete(selected["id"], [], timeout_seconds=7) == '{"ok":true}'
    assert requests[0] == ({"model": "gpt", "messages": []}, 7)
    options = {"thinking": {"type": "enabled"}, "reasoning_effort": effort,
               "response_format": {"type": "json_object"}, "max_tokens": 2048}
    result = new.complete_with_options(selected["id"], [], timeout_seconds=None, options=options)
    assert requests[1] == ({"model": "gpt", "messages": [], **options}, None)
    assert result["content"] == '{"ok":true}' and result["finish_reason"] == "stop"
    assert result["model"] == "served-model" and result["duration_ms"] >= 0
    assert result["usage"] == {"prompt_tokens": 90, "completion_tokens": 12, "total_tokens": 102,
                               "prompt_cache_hit_tokens": 64, "completion_tokens_details": {"reasoning_tokens": 4}}
    assert set(result) == {"content", "finish_reason", "usage", "model", "duration_ms"}
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("temperature", [0, 0.5, 2])
def test_temperature_is_sent_only_when_requested(temperature):
    database = _database()
    _, selected = _save_pair(database)
    bodies = []

    def post(_url, _headers, body, _timeout):
        bodies.append(json.loads(body))
        return '{"choices":[{"message":{"content":"OK"}}]}'

    facade = _facade(database, post)
    facade.complete_with_options(selected["id"], [], timeout_seconds=5, options={"temperature": temperature})
    facade.complete_with_options(selected["id"], [], timeout_seconds=5)
    assert bodies == [{"model": "gpt", "messages": [], "temperature": temperature},
                      {"model": "gpt", "messages": []}]


@pytest.mark.parametrize("options", [
    {"model": "other"}, {"headers": {"Authorization": "injected"}},
    {"thinking": {"type": "enabled", "extra": True}}, {"thinking": {"type": "unknown"}},
    {"reasoning_effort": "invented"}, {"response_format": {"type": "text"}},
    {"max_tokens": True}, {"max_tokens": 0}, {"max_tokens": "2000"},
    {"unknown_option": 0}, {"temperature": True}, {"temperature": "0"}, {"temperature": None},
    {"temperature": -0.01}, {"temperature": 2.01}, {"temperature": float("nan")},
    {"temperature": float("inf")}, {"temperature": float("-inf")},
])
def test_invalid_controls_are_rejected_before_network(options):
    database = _database()
    _, selected = _save_pair(database)
    calls = []
    facade = _facade(database, lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="MODEL_OPTIONS_INVALID"):
        facade.complete_with_options(selected["id"], [], timeout_seconds=5, options=options)
    assert calls == []


def test_diagnostics_keep_truncation_and_tolerate_missing_usage():
    database = _database()
    _, selected = _save_pair(database)
    facade = _facade(database, lambda *_: '{"choices":[{"finish_reason":"length","message":{"content":"{"}}]}')
    result = facade.complete_with_options(selected["id"], [], timeout_seconds=5)
    assert result["content"] == "{" and result["finish_reason"] == "length"
    assert result["usage"] == {} and result["model"] is None


def test_controlled_response_does_not_stringify_private_content_blocks_or_model_objects():
    database = _database()
    _, selected = _save_pair(database)
    payload = {"choices": [{"message": {"content": [{"type": "thinking", "thinking": "private-marker"},
                                                   {"type": "text", "text": "OK"}]}}],
               "model": {"internal": "private-marker"}}
    facade = _facade(database, lambda *_: json.dumps(payload))
    with pytest.raises(RuntimeError, match="MODEL_UNAVAILABLE") as error:
        facade.complete_with_options(selected["id"], [], timeout_seconds=5)
    assert "private-marker" not in str(error.value)
    payload["choices"][0]["message"]["content"] = "OK"
    result = facade.complete_with_options(selected["id"], [], timeout_seconds=5)
    assert result["content"] == "OK" and result["model"] is None
    assert "private-marker" not in json.dumps(result)


def test_controlled_call_honors_pre_cancel_and_closed_service():
    database = _database()
    _, selected = _save_pair(database)
    calls = []
    facade = _facade(database, lambda *args: calls.append(args))
    cancelled = Event()
    cancelled.set()
    with pytest.raises(RuntimeError, match="MODEL_CANCELLED"):
        facade.complete_with_options(selected["id"], [], timeout_seconds=None, cancel_event=cancelled)
    facade._close()
    with pytest.raises(RuntimeError, match="platform service facade is closed"):
        facade.complete_with_options(selected["id"], [], timeout_seconds=None)
    assert calls == []
