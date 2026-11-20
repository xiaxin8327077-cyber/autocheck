"""Shared language-model catalog stored in application settings."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from auto_check.app.security import decrypt_secret, encrypt_secret
from auto_check.app.storage_config import load_setting, save_setting

LANGUAGE_MODEL_SETTING_KEY = "language_models"


def list_language_models(database: Any) -> list[dict[str, Any]]:
    _import_local_test_models(database)
    with database.connect() as connection:
        return [_public_model(item) for item in _load_catalog(connection)["models"]]


def save_language_model(database: Any, payload: dict[str, Any]) -> dict[str, Any]:
    with database.transaction() as connection:
        catalog = _load_catalog(connection, for_update=True)
        models = catalog["models"]
        record = _build_record(payload, current=None, models=models)
        if record["is_default"]:
            _clear_defaults(models)
        models.append(record)
        save_setting(connection, LANGUAGE_MODEL_SETTING_KEY, catalog)
    return _public_model(record)


def update_language_model(database: Any, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with database.transaction() as connection:
        catalog = _load_catalog(connection, for_update=True)
        models = catalog["models"]
        index = _index_of(models, model_id)
        current = models[index]
        record = _build_record(payload, current=current, models=models)
        if record["is_default"]:
            _clear_defaults(models)
        models[index] = record
        save_setting(connection, LANGUAGE_MODEL_SETTING_KEY, catalog)
    return _public_model(record)


def delete_language_model(database: Any, model_id: str) -> None:
    with database.transaction() as connection:
        catalog = _load_catalog(connection, for_update=True)
        models = catalog["models"]
        removed = models.pop(_index_of(models, model_id))
        fingerprint = _model_fingerprint(removed)
        if fingerprint not in catalog["excluded_local_models"]:
            catalog["excluded_local_models"].append(fingerprint)
        save_setting(connection, LANGUAGE_MODEL_SETTING_KEY, catalog)


def load_language_model_secrets(database: Any) -> list[dict[str, Any]]:
    _import_local_test_models(database)
    with database.connect() as connection:
        return _load_catalog(connection)["models"]


def reveal_language_model_key(database: Any, model_id: str) -> str:
    return _decrypt_model_key(_read_model(database, model_id))


def resolve_language_model_test_config(database: Any, payload: dict[str, Any]) -> tuple[str, str, str]:
    model_id = str(payload.get("id") or "")
    current = _read_model(database, model_id) if model_id else None
    url = language_model_chat_endpoint(_required_base_url(payload, current))
    model_name = _required_model_name(payload, current)
    key = str(payload.get("api_key") or "")
    if not key and current:
        if url != language_model_chat_endpoint(str(current.get("base_url") or "")):
            raise ValueError("测试新的接口地址时，请输入访问密钥")
        key = _decrypt_model_key(current)
    if not key:
        raise ValueError("访问密钥不能为空")
    return url, model_name, key


def language_model_chat_endpoint(base_url: str) -> str:
    invalid = "请输入有效的 http:// 或 https:// 模型接口地址"
    try:
        url = urlsplit(base_url)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username is not None
                or url.fragment or url.port == 0 or any(character.isspace() for character in base_url)):
            raise ValueError(invalid)
    except ValueError:
        raise ValueError(invalid) from None
    path = url.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path += "/chat/completions"
    return urlunsplit(url._replace(path=path))


def _read_model(database: Any, model_id: str) -> dict[str, Any]:
    with database.connect() as connection:
        models = _load_catalog(connection)["models"]
    return models[_index_of(models, model_id)]


def _decrypt_model_key(model: dict[str, Any]) -> str:
    try:
        return decrypt_secret(str(model.get("api_key_encrypted") or ""))
    except ValueError:
        raise ValueError("已保存的密钥无法读取，请重新输入访问密钥") from None


def _import_local_test_models(database: Any) -> None:
    """Import a machine-local test catalog. Production intranet models stay in the database."""
    incoming = _read_local_test_models()
    if not incoming:
        return
    with database.transaction() as connection:
        catalog = _load_catalog(connection, for_update=True)
        models = catalog["models"]
        existing = set(catalog["excluded_local_models"])
        existing.update(_model_fingerprint(item) for item in models)
        changed = False
        for item in incoming:
            fingerprint = _model_fingerprint(item)
            if fingerprint in existing:
                continue
            try:
                base_url = _required_base_url(item, None)
                model_name = _required_model_name(item, None)
                wants_default = bool(item.get("is_default")) and not any(
                    stored.get("enabled") and stored.get("is_default") for stored in models
                )
                record = _build_record(
                    {**item, "base_url": base_url, "model_name": model_name, "is_default": wants_default},
                    current=None,
                    models=models,
                )
            except ValueError:
                continue
            if record["is_default"]:
                _clear_defaults(models)
            models.append(record)
            existing.add(fingerprint)
            changed = True
        if changed:
            save_setting(connection, LANGUAGE_MODEL_SETTING_KEY, catalog)


def _read_local_test_models() -> list[dict[str, Any]]:
    path = _local_test_model_path()
    if path is None:
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    models = payload.get("models") if isinstance(payload, dict) else None
    return [item for item in models if isinstance(item, dict)] if isinstance(models, list) else []


def _model_fingerprint(model: dict[str, Any]) -> str:
    url = str(model.get("base_url") or "").strip()
    try:
        url = language_model_chat_endpoint(url)
    except ValueError:
        pass
    name = str(model.get("model_name") or "").strip()
    return sha256(json.dumps([url, name]).encode("utf-8")).hexdigest()


def _local_test_model_path() -> Path | None:
    explicit = os.environ.get("AUTO_CHECK_TEST_LANGUAGE_MODELS", "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return None
    path = Path(appdata) / "auto-check" / "test-language-models.json"
    return path if path.is_file() else None


def _load_catalog(connection: Any, *, for_update: bool = False) -> dict[str, Any]:
    stored = load_setting(connection, LANGUAGE_MODEL_SETTING_KEY, {}, for_update=for_update)
    if not isinstance(stored, dict):
        stored = {}
    models = stored.get("models")
    excluded = stored.get("excluded_local_models")
    return {
        "models": [dict(item) for item in models if isinstance(item, dict)] if isinstance(models, list) else [],
        "excluded_local_models": [item for item in excluded if isinstance(item, str)] if isinstance(excluded, list) else [],
    }


def _index_of(models: list[dict[str, Any]], model_id: str) -> int:
    wanted = str(model_id or "")
    for index, item in enumerate(models):
        if str(item.get("id") or "") == wanted:
            return index
    raise KeyError(wanted)


def _clear_defaults(models: list[dict[str, Any]]) -> None:
    for item in models:
        item["is_default"] = False


def _build_record(
    payload: dict[str, Any],
    *,
    current: dict[str, Any] | None,
    models: list[dict[str, Any]],
) -> dict[str, Any]:
    name = _required_name(payload, current)
    _ensure_unique_name(name, models, current)
    base_url = _required_base_url(payload, current)
    model_name = _required_model_name(payload, current)
    enabled = _enabled_value(payload, current)
    is_default = _default_value(payload, current, enabled)
    return {
        "id": str(current["id"]) if current else uuid4().hex,
        "name": name,
        "base_url": base_url,
        "model_name": model_name,
        "api_key_encrypted": _secret_value(payload, current),
        "enabled": enabled,
        "is_default": is_default,
    }


def _required_name(payload: dict[str, Any], current: dict[str, Any] | None) -> str:
    if "name" in payload or current is None:
        name = str(payload.get("name") or "").strip()
    else:
        name = str(current.get("name") or "").strip()
    if not name:
        raise ValueError("模型名称不能为空")
    return name


def _ensure_unique_name(
    name: str,
    models: list[dict[str, Any]],
    current: dict[str, Any] | None,
) -> None:
    current_id = str(current["id"]) if current else ""
    for item in models:
        if str(item.get("id") or "") == current_id:
            continue
        if str(item.get("name") or "").strip() == name:
            raise ValueError("模型名称已存在")


def _required_base_url(payload: dict[str, Any], current: dict[str, Any] | None) -> str:
    if "base_url" in payload or current is None:
        value = str(payload.get("base_url") or "").strip()
    else:
        value = str(current.get("base_url") or "").strip()
    language_model_chat_endpoint(value)
    return value.rstrip("/")


def _required_model_name(payload: dict[str, Any], current: dict[str, Any] | None) -> str:
    if "model_name" in payload or current is None:
        value = str(payload.get("model_name") or "").strip()
    else:
        value = str(current.get("model_name") or "").strip()
    if not value:
        raise ValueError("模型名不能为空")
    return value


def _enabled_value(payload: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if "enabled" in payload:
        return bool(payload.get("enabled"))
    if current is None:
        return True
    return bool(current.get("enabled"))


def _default_value(
    payload: dict[str, Any],
    current: dict[str, Any] | None,
    enabled: bool,
) -> bool:
    if not enabled:
        return False
    if "is_default" in payload:
        return bool(payload.get("is_default"))
    if current is None:
        return False
    return bool(current.get("is_default"))


def _secret_value(payload: dict[str, Any], current: dict[str, Any] | None) -> str:
    supplied = str(payload.get("api_key") or "")
    if supplied:
        return encrypt_secret(supplied)
    if current and str(current.get("api_key_encrypted") or ""):
        return str(current["api_key_encrypted"])
    raise ValueError("访问密钥不能为空")


def _public_model(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "base_url": str(item.get("base_url") or ""),
        "model_name": str(item.get("model_name") or ""),
        "enabled": bool(item.get("enabled")),
        "is_default": bool(item.get("is_default")),
        "has_api_key": bool(item.get("api_key_encrypted")),
    }
