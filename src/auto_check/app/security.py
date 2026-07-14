from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from Cryptodome.Cipher import AES
from Cryptodome.Cipher import PKCS1_OAEP
from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import RSA

from auto_check.app.app_database import ApplicationDatabase
from auto_check.app.time_utils import beijing_timestamp


PBKDF2_ITERATIONS = 260_000
DEFAULT_SESSION_EXPIRE_HOURS = 8
GENERIC_ERROR_MESSAGE = "操作失败，请检查输入或联系管理员"
PASSWORD_RULE_ERROR = "password must be at least 6 characters and include a letter"
DANGEROUS_ERROR_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|select\s+|insert\s+|update\s+|delete\s+|drop\s+|truncate\s+|alter\s+|create\s+|grant\s+|revoke\s+|where\s+|from\s+)"
)


@dataclass(frozen=True)
class AuthSession:
    session_id: str
    csrf_token: str
    expires_at: float
    last_activity_at: float
    user_id: str
    username: str
    display_name: str
    role: str


def _b64url_uint(value: int) -> str:
    size = max(1, (value.bit_length() + 7) // 8)
    raw = value.to_bytes(size, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class AuthManager:
    def __init__(self, config_path: str | Path, *, database: ApplicationDatabase):
        self.config_path = Path(config_path)
        self.database = database
        self._sessions: dict[str, AuthSession] = {}
        self._users_lock = RLock()
        self._rsa_key = RSA.generate(2048)

    def setup_required(self) -> bool:
        return not any(user.get("enabled", True) for user in self._users())

    def set_admin_password(self, password: str) -> None:
        validate_auth_password(password)
        now = _now()
        with self._users_lock:
            self._save_users(
                [
                    {
                        "id": secrets.token_hex(12),
                        "username": "admin",
                        "display_name": "管理员",
                        "role": "admin",
                        "password_hash": hash_password(password),
                        "enabled": True,
                        "created_at": now,
                        "updated_at": now,
                        "last_login_at": "",
                    }
                ]
            )
    def login(self, username: str, password: str | None = None) -> AuthSession | None:
        if password is None:
            password = username
            username = "admin"
        user = self._find_user_by_username(username)
        if not user or not user.get("enabled", True) or not verify_password(str(password or ""), str(user.get("password_hash", ""))):
            return None
        self._update_user(str(user["id"]), {"last_login_at": _now()})
        now = time.time()
        session = AuthSession(
            session_id=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            expires_at=now + self._session_ttl_seconds(),
            last_activity_at=now,
            user_id=str(user["id"]),
            username=str(user["username"]),
            display_name=_normalize_display_name(user.get("display_name"), str(user["username"])),
            role=_normalize_role(user.get("role")),
        )
        self._sessions[session.session_id] = session
        return session

    def login_failure_reason(self, username: str, password: str) -> str:
        return "invalid credentials"

    def validate_session(self, session_id: str) -> AuthSession | None:
        session = self._sessions.get(str(session_id or ""))
        if session is None:
            return None
        now = time.time()
        ttl = self._session_ttl_seconds()
        if session.last_activity_at + ttl < now:
            self._sessions.pop(session.session_id, None)
            return None
        session = AuthSession(
            session_id=session.session_id,
            csrf_token=session.csrf_token,
            expires_at=now + ttl,
            last_activity_at=now,
            user_id=session.user_id,
            username=session.username,
            display_name=session.display_name,
            role=session.role,
        )
        self._sessions[session.session_id] = session
        return session

    def logout(self, session_id: str) -> None:
        self._sessions.pop(str(session_id or ""), None)

    def public_key_pem(self) -> str:
        return self._rsa_key.public_key().export_key(format="PEM").decode("ascii")

    def public_key_jwk(self) -> dict[str, Any]:
        public_key = self._rsa_key.public_key()
        return {
            "kty": "RSA",
            "n": _b64url_uint(int(public_key.n)),
            "e": _b64url_uint(int(public_key.e)),
            "alg": "RSA-OAEP-256",
            "key_ops": ["encrypt"],
            "ext": True,
        }

    def decrypt_transport_password(self, value: str) -> str:
        if not value:
            raise ValueError("encrypted password is required")
        try:
            ciphertext = bytes.fromhex(str(value))
            cipher = PKCS1_OAEP.new(self._rsa_key, hashAlgo=SHA256)
            return cipher.decrypt(ciphertext).decode("utf-8")
        except Exception as exc:
            raise ValueError("encrypted password is invalid") from exc

    def list_users(self) -> list[dict[str, Any]]:
        return [
            _public_user(user)
            for user in sorted(
                self._users(),
                key=lambda item: (
                    str(item.get("display_name") or item.get("username") or "").lower(),
                    str(item.get("username", "")).lower(),
                ),
            )
        ]

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str,
        enabled: bool = True,
        display_name: str = "",
        current_user_id: str = "",
    ) -> dict[str, Any]:
        username = _normalize_username(username)
        display_name = _normalize_display_name(display_name, username)
        normalized_role = _normalize_role(role)
        validate_auth_password(password)
        with self._users_lock:
            if self._find_user_by_username(username):
                raise ValueError("username already exists")
            users = self._users()
            actor = _find_user_by_id(users, current_user_id)
            if current_user_id and normalized_role == "admin" and not _is_initial_admin(actor or {}):
                raise ValueError("only initial admin can create admin users")
            now = _now()
            user = {
                "id": secrets.token_hex(12),
                "username": username,
                "display_name": display_name,
                "role": normalized_role,
                "password_hash": hash_password(password),
                "enabled": bool(enabled),
                "created_at": now,
                "updated_at": now,
                "last_login_at": "",
            }
            users.append(user)
            self._save_users(users)
            return _public_user(user)

    def update_user(
        self,
        user_id: str,
        *,
        role: str | None = None,
        enabled: bool | None = None,
        display_name: str | None = None,
        current_user_id: str = "",
    ) -> dict[str, Any]:
        with self._users_lock:
            users = self._users()
            index = _find_user_index(users, user_id)
            if index < 0:
                raise ValueError("user not found")
            user = dict(users[index])
            actor = _find_user_by_id(users, current_user_id)
            actor_is_initial_admin = _is_initial_admin(actor or {})
            target_was_admin = _normalize_role(user.get("role")) == "admin"
            normalized_role = _normalize_role(role) if role is not None else ("admin" if target_was_admin else "user")
            if enabled is False and str(user.get("id")) == str(current_user_id):
                raise ValueError("cannot disable yourself")
            if enabled is False and _is_initial_admin(user):
                raise ValueError("initial admin cannot be disabled")
            if _is_initial_admin(user) and role is not None and normalized_role != "admin":
                raise ValueError("initial admin role cannot be changed")
            if current_user_id and not actor_is_initial_admin:
                if target_was_admin:
                    raise ValueError("delegated admin cannot edit admin users")
                if normalized_role == "admin":
                    raise ValueError("only initial admin can create admin users")
            if role is not None:
                user["role"] = normalized_role
            if display_name is not None:
                user["display_name"] = _normalize_display_name(display_name, str(user.get("username", "")))
            if enabled is not None:
                user["enabled"] = bool(enabled)
            user["updated_at"] = _now()
            updated = list(users)
            updated[index] = user
            _ensure_enabled_admin_exists(updated)
            self._save_users(updated)
            if enabled is False:
                self._drop_sessions_for_user(str(user["id"]))
            return _public_user(user)

    def reset_password(self, user_id: str, password: str, *, current_user_id: str = "", preserve_session_id: str = "") -> dict[str, Any]:
        validate_auth_password(password)
        with self._users_lock:
            users = self._users()
            index = _find_user_index(users, user_id)
            if index < 0:
                raise ValueError("user not found")
            user = dict(users[index])
            actor = _find_user_by_id(users, current_user_id)
            if current_user_id and not _is_initial_admin(actor or {}) and _normalize_role(user.get("role")) == "admin":
                raise ValueError("delegated admin cannot edit admin users")
            user["password_hash"] = hash_password(password)
            user["updated_at"] = _now()
            users[index] = user
            self._save_users(users)
            self._drop_sessions_for_user(str(user["id"]), preserve_session_id=preserve_session_id)
            return _public_user(user)

    def delete_user(self, user_id: str, *, current_user_id: str = "") -> None:
        if str(user_id) == str(current_user_id):
            raise ValueError("cannot delete yourself")
        with self._users_lock:
            users = self._users()
            index = _find_user_index(users, user_id)
            if index < 0:
                raise ValueError("user not found")
            removed = users[index]
            if _is_initial_admin(removed):
                raise ValueError("initial admin cannot be deleted")
            actor = _find_user_by_id(users, current_user_id)
            if current_user_id and not _is_initial_admin(actor or {}) and _normalize_role(removed.get("role")) == "admin":
                raise ValueError("delegated admin cannot edit admin users")
            updated = [user for user in users if str(user.get("id")) != str(user_id)]
            _ensure_enabled_admin_exists(updated)
            self._save_users(updated)
            self._drop_sessions_for_user(str(removed["id"]))

    def _drop_sessions_for_user(self, user_id: str, *, preserve_session_id: str = "") -> None:
        for session_id, session in list(self._sessions.items()):
            if session.user_id == user_id and session_id != preserve_session_id:
                self._sessions.pop(session_id, None)

    def _users(self) -> list[dict[str, Any]]:
        return self._auth_payload().get("users", [])

    def _find_user_by_username(self, username: str) -> dict[str, Any] | None:
        normalized = _normalize_username(username or "admin")
        for user in self._users():
            if str(user.get("username", "")).lower() == normalized.lower():
                return user
        return None

    def _update_user(self, user_id: str, updates: dict[str, Any]) -> None:
        with self._users_lock:
            users = self._users()
            index = _find_user_index(users, user_id)
            if index < 0:
                return
            user = dict(users[index])
            user.update(updates)
            users[index] = user
            self._save_users(users)

    def _save_users(self, users: list[dict[str, Any]]) -> None:
        from auto_check.app.storage_users import replace_users

        normalized_users = [_normalize_user(user) for user in users]
        with self.database.transaction() as connection:
            replace_users(connection, normalized_users)

    def _auth_payload(self) -> dict[str, Any]:
        from auto_check.app.storage_users import load_users

        with self.database.connect() as connection:
            users = load_users(connection)
        return {"users": [_normalize_user(user) for user in users]}

    def _session_ttl_seconds(self) -> int:
        from auto_check.app.config import load_store

        settings = load_store(self.config_path, database=self.database).default_settings
        try:
            hours = int(settings.session_expire_hours)
        except (AttributeError, TypeError, ValueError):
            hours = DEFAULT_SESSION_EXPIRE_HOURS
        hours = min(max(hours, 1), 168)
        return hours * 60 * 60
def hash_password(password: str, *, salt: str | None = None) -> str:
    salt_value = salt or secrets.token_urlsafe(24)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt_value.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_value}${base64.urlsafe_b64encode(digest).decode('ascii')}"


def validate_auth_password(password: str) -> None:
    value = str(password or "")
    if len(value) < 6 or re.search(r"[A-Za-z]", value) is None:
        raise ValueError(PASSWORD_RULE_ERROR)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, digest_text = str(stored_hash).split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            str(password).encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations_text),
        )
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except Exception:
        return False
    return hmac.compare_digest(digest, expected)


def _now() -> str:
    return beijing_timestamp()


def _normalize_username(username: str) -> str:
    value = str(username or "").strip()
    if not value:
        raise ValueError("username is required")
    if len(value) > 64:
        raise ValueError("username is too long")
    if not re.match(r"^[A-Za-z0-9_.-]+$", value):
        raise ValueError("username contains unsupported characters")
    return value


def _normalize_display_name(display_name: Any, username: str) -> str:
    value = str(display_name or "").strip()
    if not value:
        value = "管理员" if str(username or "").lower() == "admin" else str(username or "").strip()
    if len(value) > 64:
        raise ValueError("display name is too long")
    return value


def _normalize_role(role: Any) -> str:
    value = str(role or "user").strip()
    if value not in {"admin", "user"}:
        raise ValueError("role must be admin or user")
    return value


def _normalize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user.get("id") or secrets.token_hex(12)),
        "username": str(user.get("username") or "admin"),
        "display_name": _normalize_display_name(user.get("display_name"), str(user.get("username") or "admin")),
        "role": _normalize_role(user.get("role", "user")),
        "password_hash": str(user.get("password_hash", "")),
        "enabled": bool(user.get("enabled", True)),
        "created_at": str(user.get("created_at", "")),
        "updated_at": str(user.get("updated_at", "")),
        "last_login_at": str(user.get("last_login_at", "")),
    }


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_user(user)
    return {
        "id": normalized["id"],
        "username": normalized["username"],
        "display_name": normalized["display_name"],
        "role": normalized["role"],
        "enabled": normalized["enabled"],
        "created_at": normalized["created_at"],
        "updated_at": normalized["updated_at"],
        "last_login_at": normalized["last_login_at"],
    }


def _find_user_index(users: list[dict[str, Any]], user_id: str) -> int:
    for index, user in enumerate(users):
        if str(user.get("id")) == str(user_id):
            return index
    return -1


def _find_user_by_id(users: list[dict[str, Any]], user_id: str) -> dict[str, Any] | None:
    index = _find_user_index(users, user_id)
    return users[index] if index >= 0 else None


def _ensure_enabled_admin_exists(users: list[dict[str, Any]]) -> None:
    if not any(_normalize_role(user.get("role")) == "admin" and bool(user.get("enabled", True)) for user in users):
        raise ValueError("at least one enabled admin is required")


def _is_initial_admin(user: dict[str, Any]) -> bool:
    return _normalize_username(str(user.get("username") or "")) == "admin"


def _secret_key() -> bytes:
    raw = os.environ.get("AUTO_CHECK_SECRET_KEY", "")
    if raw:
        return hashlib.sha256(raw.encode("utf-8")).digest()
    fallback = f"auto-check-local-{Path.home()}".encode("utf-8")
    return hashlib.sha256(fallback).digest()


def encrypt_secret(value: str) -> str:
    nonce = secrets.token_bytes(12)
    cipher = AES.new(_secret_key(), AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(str(value).encode("utf-8"))
    return "aesgcm$" + base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        prefix, encoded = str(value).split("$", 1)
        if prefix != "aesgcm":
            raise ValueError("unsupported encrypted secret")
        payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
        nonce, tag, ciphertext = payload[:12], payload[12:28], payload[28:]
        cipher = AES.new(_secret_key(), AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except Exception as exc:
        raise ValueError("encrypted secret cannot be decrypted with the current key") from exc


def sanitize_error_message(message: str) -> str:
    text = str(message or "")
    if DANGEROUS_ERROR_RE.search(text):
        return GENERIC_ERROR_MESSAGE
    return text[:200] or GENERIC_ERROR_MESSAGE
