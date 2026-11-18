"""Shared language-model catalog stored in application settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from auto_check.app.security import encrypt_secret
from auto_check.app.storage_config import load_setting, save_setting

LANGUAGE_MODEL_SETTING_KEY = "language_models"


def list_language_models(database: Any) -> list[dict[str, Any]]:
    _import_local_test_models(database)
    with database.connect() as connection:
        return [_public_model(item) for item in _load_models(connection)]


def save_language_model(database: Any, payload: dict[str, Any]) -> dict[str, Any]:
    with database.transaction() as connection:
        models = _load_models(connection)
        record = _build_record(payload, current=None, models=models)
        if record["is_default"]:
            _clear_defaults(models)
        models.append(record)
        _store(connection, models)
    return _public_model(record)


def update_language_model(database: Any, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with database.transaction() as connection:
        models = _load_models(connection)
        index = _index_of(models, model_id)
        current = models[index]
        record = _build_record(payload, current=current, models=models)
        if record["is_default"]:
            _clear_defaults(models)
        models[index] = record
        _store(connection, models)
    return _public_model(record)


def delete_language_model(database: Any, model_id: str) -> None:
    with database.transaction() as connection:
        models = _load_models(connection)
        index = _index_of(models, model_id)
        del models[index]
        _store(connection, models)


def load_language_model_secrets(database: Any) -> list[dict[str, Any]]:
    _import_local_test_models(database)
    with database.connect() as connection:
        return [dict(item) for item in _load_models(connection)]


def _import_local_test_models(database: Any) -> None:
    """Import a machine-local test catalog. Production intranet models stay in the database."""

    path = _local_test_model_path()
    if path is None:
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    incoming = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(incoming, list):
        return
    with database.transaction() as connection:
        models = _load_models(connection)
        changed = False
        for item in incoming:
            if not isinstance(item, dict):
                continue
            try:
                base_url = _required_base_url(item, None)
                model_name = _required_model_name(item, None)
            except ValueError:
                continue
            if any(
                str(existing.get("base_url") or "") == base_url
                and str(existing.get("model_name") or "") == model_name
                for existing in models
            ):
                continue
            wants_default = bool(item.get("is_default")) and not any(
                existing.get("enabled") and existing.get("is_default") for existing in models
            )
            record = _build_record(
                {**item, "base_url": base_url, "model_name": model_name, "is_default": wants_default},
                current=None,
                models=models,
            )
            if record["is_default"]:
                _clear_defaults(models)
            models.append(record)
            changed = True
        if changed:
            _store(connection, models)


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


def _load_models(connection: Any) -> list[dict[str, Any]]:
    stored = load_setting(connection, LANGUAGE_MODEL_SETTING_KEY, {"models": []})
    models = stored.get("models") if isinstance(stored, dict) else []
    if not isinstance(models, list):
        return []
    return [dict(item) for item in models if isinstance(item, dict)]


def _store(connection: Any, models: list[dict[str, Any]]) -> None:
    save_setting(connection, LANGUAGE_MODEL_SETTING_KEY, {"models": models})


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
    if not (value.startswith("http://") or value.startswith("https://")) or any(
        character.isspace() for character in value
    ):
        raise ValueError("模型地址必须以 http:// 或 https:// 开头")
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
