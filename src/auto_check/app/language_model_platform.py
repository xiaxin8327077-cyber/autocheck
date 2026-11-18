"""Versioned language-model calls for modules. Secrets stay in this service."""

from __future__ import annotations

from dataclasses import dataclass
import json
from threading import RLock
from typing import Any, Callable, Mapping, Sequence
from urllib import request as urllib_request

from auto_check.app.language_model_settings import load_language_model_secrets
from auto_check.app.module_system.services import BoundService, PlatformServiceSpec
from auto_check.app.security import decrypt_secret

LANGUAGE_MODEL_SERVICE = "platform.language_models"
LANGUAGE_MODEL_VERSION = 1
_CLOSED_FACADE_ERROR = "platform service facade is closed"
_MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"

HttpPost = Callable[[str, Mapping[str, str], bytes, float], str]


@dataclass(frozen=True)
class PublicLanguageModel:
    id: str
    name: str
    model_name: str
    is_default: bool


class _LanguageModelFacade:
    def __init__(self, application_database: Any, http_post: HttpPost) -> None:
        self._database = application_database
        self._http_post = http_post
        self._closed = False
        self._lock = RLock()

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
                )
                for item in self._models()
                if item.get("enabled")
            )

    def complete(
        self,
        model_id: str,
        messages: Sequence[Mapping[str, str]],
        *,
        timeout_seconds: float,
    ) -> str:
        with self._lock:
            self._require_open()
            selected = self._select(str(model_id or ""))
            if selected is None:
                raise RuntimeError(_MODEL_UNAVAILABLE)
            url = f"{str(selected['base_url']).rstrip('/')}/chat/completions"
            body = json.dumps(
                {"model": selected["model_name"], "messages": [dict(item) for item in messages]},
                ensure_ascii=False,
            ).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {decrypt_secret(str(selected['api_key_encrypted']))}",
                "Content-Type": "application/json",
            }
            try:
                raw = self._http_post(url, headers, body, float(timeout_seconds))
                payload = json.loads(raw)
                return str(payload["choices"][0]["message"]["content"])
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(_MODEL_UNAVAILABLE) from exc

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


def create_language_model_service(
    application_database: Any,
    *,
    http_post: HttpPost | None = None,
) -> PlatformServiceSpec:
    """Create the v1 shared language-model platform service."""

    sender = http_post or _post_json

    def bind(_owner: str) -> BoundService:
        facade = _LanguageModelFacade(application_database, sender)
        return BoundService(value=facade, close=facade._close)

    return PlatformServiceSpec(
        name=LANGUAGE_MODEL_SERVICE,
        version=LANGUAGE_MODEL_VERSION,
        binder=bind,
    )


def _post_json(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> str:
    outgoing = urllib_request.Request(url, data=body, headers=dict(headers), method="POST")
    with urllib_request.urlopen(outgoing, timeout=timeout) as response:
        return response.read().decode("utf-8")
