"""Versioned language-model calls for modules. Secrets stay in this service."""

from __future__ import annotations

from contextlib import contextmanager, suppress
from dataclasses import dataclass
from hashlib import sha256
import json
import socket
from threading import Event, RLock, Thread
from time import perf_counter
from typing import Any, Callable, Iterator, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib import request as urllib_request

from auto_check.app.language_model_settings import (
    language_model_chat_endpoint, load_language_model_secrets, resolve_language_model_test_config,
)
from auto_check.app.module_system.services import BoundService, PlatformServiceSpec
from auto_check.app.security import decrypt_secret

LANGUAGE_MODEL_SERVICE = "platform.language_models"
LANGUAGE_MODEL_VERSION = 2
_CLOSED_FACADE_ERROR = "platform service facade is closed"
_MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
_MODEL_CANCELLED = "MODEL_CANCELLED"
_MODEL_CONNECT_TIMEOUT = 120.0
_MODEL_TEST_TIMEOUT = 15
_MODEL_TEST_MAX_RESPONSE_BYTES = 64 * 1024

HttpPost = Callable[[str, Mapping[str, str], bytes, float | None], str]


@dataclass(frozen=True)
class PublicLanguageModel:
    id: str
    name: str
    model_name: str
    is_default: bool
    configuration_fingerprint: str = ""


class _ModelRequest:
    """Own one upstream connection, including while urllib is reading its headers or body."""

    def __init__(self, cancel_event: Event | None) -> None:
        self._lock = RLock()
        self._socket: socket.socket | None = None
        self._cancel_event = cancel_event
        self._cancel_reason: str | None = None
        self._finished = Event()

    def connect(self, address, timeout, source_address):
        with self._lock:
            self._check_cancelled()
        # Bound TCP setup even for unlimited reads. Cancellation during DNS or
        # TCP setup is checked again before urllib can write any request bytes.
        connect_timeout = _MODEL_CONNECT_TIMEOUT if timeout is None else timeout
        sock = socket.create_connection(address, connect_timeout, source_address)
        try:
            with self._lock:
                self._check_cancelled()
                sock.settimeout(timeout)
                # urllib transfers ownership to HTTPResponse. Keep a separate handle
                # to the same TCP connection through CONNECT, TLS, and response.read().
                if self._socket is not None:
                    self._socket.close()
                self._socket = sock.dup()
        except BaseException:
            sock.close()
            raise
        return sock

    def cancel(self, reason: str) -> None:
        with self._lock:
            if self._cancel_reason is not None:
                return
            self._cancel_reason = reason
            if self._socket is not None:
                with suppress(OSError):
                    self._socket.shutdown(socket.SHUT_RDWR)

    def _check_cancelled(self) -> None:
        if self._cancel_reason is not None:
            raise RuntimeError(self._cancel_reason)
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise RuntimeError(_MODEL_CANCELLED)

    @contextmanager
    def monitor(self) -> Iterator[None]:
        watcher = None
        if self._cancel_event is not None:
            watcher = Thread(target=self._watch_cancellation, args=(self._cancel_event,),
                             name="language-model-cancel", daemon=True)
            watcher.start()
        try:
            with self._lock:
                self._check_cancelled()
            yield
        finally:
            self._finished.set()
            if watcher is not None:
                watcher.join()
            with self._lock:
                if self._socket is not None:
                    self._socket.close()
                    self._socket = None
                self._check_cancelled()

    def _watch_cancellation(self, event: Event) -> None:
        while not self._finished.wait(0.05):
            if event.is_set():
                self.cancel(_MODEL_CANCELLED)
                return

    def post(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float | None) -> str:
        opener = urllib_request.build_opener(_ModelHTTPHandler(self))
        return _post_json(url, headers, body, timeout, opener=opener.open)


class _ModelHTTPHandler(urllib_request.HTTPHandler, urllib_request.HTTPSHandler):
    """Keep urllib's proxy, HTTPS validation and request handling; track only the socket."""

    def __init__(self, transfer: _ModelRequest) -> None:
        super().__init__()
        self._transfer = transfer

    def do_open(self, http_class, req, **kwargs):
        def connection(host, **options):
            conn = http_class(host, **options)
            conn._create_connection = self._transfer.connect
            return conn

        return super().do_open(connection, req, **kwargs)


class _LanguageModelFacade:
    def __init__(self, application_database: Any, http_post: HttpPost | None) -> None:
        self._database = application_database
        self._http_post = http_post
        self._closed = False
        self._lock = RLock()
        self._active: set[_ModelRequest] = set()

    def __repr__(self) -> str:
        return f"LanguageModelFacade(closed={self._closed})"

    def list_enabled(self) -> tuple[PublicLanguageModel, ...]:
        with self._lock:
            self._require_open()
            return tuple(
                PublicLanguageModel(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    model_name=str(item["model_name"]),
                    is_default=bool(item["is_default"]),
                    configuration_fingerprint=sha256(json.dumps(
                        item, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                    ).encode("ascii")).hexdigest(),
                )
                for item in self._models()
                if item.get("enabled")
            )

    def complete(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, str]],
        *,
        timeout_seconds: float | None,
        cancel_event: Event | None = None,
    ) -> str:
        return str(self._request(model_id, messages, timeout_seconds=timeout_seconds, cancel_event=cancel_event))

    def complete_with_options(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, str]],
        *,
        timeout_seconds: float | None,
        cancel_event: Event | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return safe call diagnostics; controls are explicit and provider support is caller-verified."""
        return self._request(model_id, messages, timeout_seconds=timeout_seconds, cancel_event=cancel_event,
                             options=_call_options(options), diagnostics=True)

    def _request(self, model_id, messages, *, timeout_seconds, cancel_event=None, options=None, diagnostics=False):
        started = perf_counter()
        with self._lock:
            self._require_open()
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError(_MODEL_CANCELLED)
            selected = self._select(str(model_id or ""))
            if selected is None:
                raise RuntimeError(_MODEL_UNAVAILABLE)
            transfer = _ModelRequest(cancel_event)
            self._active.add(transfer)
        try:
            with transfer.monitor():
                payload = _complete_chat_payload(
                    self._http_post or transfer.post, language_model_chat_endpoint(str(selected["base_url"])),
                    selected["model_name"], decrypt_secret(str(selected["api_key_encrypted"])),
                    messages, float(timeout_seconds) if timeout_seconds is not None else None, options=options,
                )
                if diagnostics:
                    return _call_diagnostics(payload, started)
                return payload["choices"][0]["message"]["content"]

        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(_MODEL_UNAVAILABLE) from exc
        finally:
            with self._lock:
                self._active.discard(transfer)

    def _select(self, model_id: str) -> dict[str, Any] | None:
        enabled = [item for item in self._models() if item.get("enabled")]
        if model_id:
            return next((item for item in enabled if str(item.get("id") or "") == model_id), None)
        return next((item for item in enabled if item.get("is_default")), None)

    def _models(self) -> list[dict[str, Any]]:
        return load_language_model_secrets(self._database)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError(_CLOSED_FACADE_ERROR)

    def _close(self) -> None:
        with self._lock:
            self._closed = True
            for transfer in self._active:
                transfer.cancel(_CLOSED_FACADE_ERROR)


def create_language_model_service(
    application_database: Any,
    *,
    http_post: HttpPost | None = None,
) -> PlatformServiceSpec:
    """Create the v2 shared service, preserving the original complete() contract."""

    def bind(_owner: str) -> BoundService:
        facade = _LanguageModelFacade(application_database, http_post)
        return BoundService(value=facade, close=facade._close)

    return PlatformServiceSpec(
        name=LANGUAGE_MODEL_SERVICE,
        version=LANGUAGE_MODEL_VERSION,
        binder=bind,
    )


def test_language_model_connection(database: Any, payload: dict[str, Any]) -> dict[str, Any]:
    url, model_name, key = resolve_language_model_test_config(database, payload)
    started = perf_counter()
    try:
        response = _complete_chat(
            _post_test_json, url, model_name, key, [{"role": "user", "content": "Reply with OK."}], _MODEL_TEST_TIMEOUT,
        )
    except HTTPError as error:
        message = {
            401: "接口拒绝了访问密钥，请检查密钥是否有效",
            403: "接口拒绝访问，请检查密钥和模型权限",
            404: "未找到接口或模型，请检查接口地址和模型名",
            429: "接口请求受限，请稍后重试",
        }.get(error.code, f"接口返回 HTTP {error.code}，请检查接口配置")
    except (TimeoutError, URLError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        message = ("接口响应超时，请稍后重试" if isinstance(reason, TimeoutError)
                   else "无法连接接口，请检查地址和网络")
    except (ValueError, LookupError, TypeError):
        message = "接口未返回有效的模型回复，请检查模型名和接口格式"
    except OSError:
        message = "无法连接接口，请检查地址和网络"
    else:
        if isinstance(response, str) and response.strip():
            return {"ok": True, "duration_ms": round((perf_counter() - started) * 1000)}
        message = "接口未返回可用的模型回复"
    return {"ok": False, "message": message}


def _complete_chat(http_post: HttpPost, url: str, model_name: str, api_key: str,
                   messages: Sequence[Mapping[str, str]], timeout: float | None) -> Any:
    return _complete_chat_payload(http_post, url, model_name, api_key, messages, timeout)["choices"][0]["message"]["content"]


def _complete_chat_payload(http_post: HttpPost, url: str, model_name: str, api_key: str,
                           messages: Sequence[Mapping[str, str]], timeout: float | None, *, options=None) -> dict[str, Any]:
    body = json.dumps({"model": model_name, "messages": [dict(item) for item in messages], **(options or {})},
                      ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    return json.loads(http_post(url, headers, body, timeout))


def _call_options(options: Mapping[str, Any] | None) -> dict[str, Any]:
    if options is None:
        return {}
    allowed = {"thinking", "reasoning_effort", "response_format", "max_tokens", "temperature"}
    if not isinstance(options, Mapping) or set(options) - allowed:
        raise ValueError("MODEL_OPTIONS_INVALID")
    result = dict(options)
    if "thinking" in result:
        value = result["thinking"]
        if not isinstance(value, Mapping) or set(value) != {"type"} or value["type"] not in ("enabled", "disabled"):
            raise ValueError("MODEL_OPTIONS_INVALID")
        result["thinking"] = dict(value)
    if "reasoning_effort" in result and result["reasoning_effort"] not in ("none", "low", "high", "max"):
        raise ValueError("MODEL_OPTIONS_INVALID")
    if "response_format" in result:
        if result["response_format"] != {"type": "json_object"}:
            raise ValueError("MODEL_OPTIONS_INVALID")
        result["response_format"] = {"type": "json_object"}
    if "max_tokens" in result and (type(result["max_tokens"]) is not int or result["max_tokens"] < 1):
        raise ValueError("MODEL_OPTIONS_INVALID")
    if "temperature" in result:
        temperature = result["temperature"]
        if type(temperature) not in (int, float) or not 0 <= temperature <= 2:
            raise ValueError("MODEL_OPTIONS_INVALID")
    return result


def _call_diagnostics(payload: dict[str, Any], started: float) -> dict[str, Any]:
    choice = payload["choices"][0]
    content = choice["message"].get("content")
    if content is not None and not isinstance(content, str):
        raise ValueError("MODEL_RESPONSE_INVALID")
    usage = payload.get("usage")
    safe_usage = {}
    if isinstance(usage, dict):
        keys = ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
        safe_usage = {key: usage[key] for key in keys if type(usage.get(key)) is int and usage[key] >= 0}
        for name, keys in (("completion_tokens_details", ("reasoning_tokens",)),
                           ("prompt_tokens_details", ("cached_tokens",))):
            details = usage.get(name)
            if isinstance(details, dict):
                safe = {key: details[key] for key in keys if type(details.get(key)) is int and details[key] >= 0}
                if safe:
                    safe_usage[name] = safe
    return {"content": content or "",
            "finish_reason": choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None,
            "usage": safe_usage, "model": payload.get("model") if isinstance(payload.get("model"), str) else None,
            "duration_ms": max(0, round((perf_counter() - started) * 1000))}


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # 测试所用密钥只能发送到管理员明确指定的地址。
        return None


def _post_test_json(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> str:
    return _post_json(url, headers, body, timeout, opener=urllib_request.build_opener(_NoRedirect()).open,
                      max_bytes=_MODEL_TEST_MAX_RESPONSE_BYTES)


def _post_json(url: str, headers: Mapping[str, str], body: bytes, timeout: float | None, *,
               opener: Callable[..., Any] | None = None, max_bytes: int | None = None) -> str:
    outgoing = urllib_request.Request(url, data=body, headers=dict(headers), method="POST")
    with (opener or urllib_request.urlopen)(outgoing, timeout=timeout) as response:
        content = response.read() if max_bytes is None else response.read(max_bytes + 1)
        if max_bytes is not None and len(content) > max_bytes:
            raise ValueError("model test response exceeds the size limit")
        return content.decode("utf-8")
