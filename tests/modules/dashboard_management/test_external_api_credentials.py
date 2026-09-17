from __future__ import annotations

import hashlib
import os
import secrets
from contextlib import contextmanager
from datetime import datetime
from unittest import mock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool


class _ExternalApiStatusFacade:
    @staticmethod
    def get_status():
        return type(
            "Status",
            (),
            {"token_configured": bool(os.environ.get("AUTO_CHECK_EXTERNAL_API_TOKEN", "").strip())},
        )()

    @staticmethod
    def verify_candidate(candidate):
        configured = os.environ.get("AUTO_CHECK_EXTERNAL_API_TOKEN", "").strip()
        return bool(candidate and configured) and secrets.compare_digest(candidate, configured)


class _Database:
    def __init__(self) -> None:
        self._engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        event.listen(
            self._engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )

    @contextmanager
    def connect(self):
        with self._engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self):
        with self._engine.begin() as connection:
            yield connection


@pytest.fixture
def database():
    from auto_check.modules.dashboard_management.external_api_credentials import METADATA

    database = _Database()
    METADATA.create_all(database._engine)
    return database


@pytest.fixture
def service(database):
    from auto_check.modules.dashboard_management.external_api_credentials import (
        DashboardExternalApiCredentialService,
    )

    return DashboardExternalApiCredentialService(database, _ExternalApiStatusFacade())


def test_status_none_when_no_credential_no_env(service, monkeypatch):
    monkeypatch.delenv("AUTO_CHECK_EXTERNAL_API_TOKEN", raising=False)
    status = service.status()
    assert status.configured is False
    assert status.source == "none"
    assert status.generated_at is None


def test_status_environment_when_no_db_credential_but_env_set(service, monkeypatch):
    monkeypatch.setenv("AUTO_CHECK_EXTERNAL_API_TOKEN", "env-token-value")
    status = service.status()
    assert status.configured is True
    assert status.source == "environment"
    assert status.generated_at is None


def test_status_managed_when_db_credential_exists(service, monkeypatch):
    monkeypatch.setenv("AUTO_CHECK_EXTERNAL_API_TOKEN", "env-token-value")
    generated = service.generate("admin")
    status = service.status()
    assert status.configured is True
    assert status.source == "managed"
    assert status.generated_at == generated.generated_at


def test_generate_returns_url_safe_token_and_stores_digest_only(service, monkeypatch):
    monkeypatch.delenv("AUTO_CHECK_EXTERNAL_API_TOKEN", raising=False)
    result = service.generate("admin")
    assert isinstance(result.token, str) and len(result.token) > 0
    assert isinstance(result.generated_at, datetime)
    assert result.rotated is False

    # Verify only digest is stored, not plaintext
    with service._database.connect() as connection:  # type: ignore[attr-defined]
        from auto_check.modules.dashboard_management.external_api_credentials import (
            EXTERNAL_API_CREDENTIALS,
        )

        row = connection.execute(
            EXTERNAL_API_CREDENTIALS.select()
        ).mappings().first()
        assert row is not None
        expected_digest = hashlib.sha256(result.token.encode("utf-8")).hexdigest()
        assert row["token_digest"] == expected_digest
        assert row["token_fingerprint"] is not None
        assert len(row["token_fingerprint"]) == 16
        # No plaintext column exists
        assert "token" not in row
        assert "plaintext_token" not in row


def test_generate_rotation_replaces_old_digest(service, monkeypatch):
    monkeypatch.delenv("AUTO_CHECK_EXTERNAL_API_TOKEN", raising=False)
    first = service.generate("admin")
    second = service.generate("operator")

    assert second.rotated is True
    assert secrets.compare_digest(
        hashlib.sha256(first.token.encode("utf-8")).hexdigest(),
        hashlib.sha256(second.token.encode("utf-8")).hexdigest(),
    ) is False

    with service._database.connect() as connection:  # type: ignore[attr-defined]
        from auto_check.modules.dashboard_management.external_api_credentials import (
            EXTERNAL_API_CREDENTIALS,
        )

        rows = connection.execute(EXTERNAL_API_CREDENTIALS.select()).mappings().all()
        assert len(rows) == 1
        assert rows[0]["updated_by"] == "operator"


def test_generate_db_failure_keeps_old_credential(service, monkeypatch):
    monkeypatch.delenv("AUTO_CHECK_EXTERNAL_API_TOKEN", raising=False)
    original = service.generate("admin")
    original_digest = hashlib.sha256(original.token.encode("utf-8")).hexdigest()

    def fail_refresh(*args, **kwargs):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(
        service._repository, "replace_digest", fail_refresh  # type: ignore[attr-defined]
    )

    with pytest.raises(RuntimeError, match="database write failed"):
        service.generate("admin")

    # Old credential should still authenticate
    decision = service.authenticate(original.token)
    assert decision.authenticated is True


def test_authenticate_uses_compare_digest_for_managed(service, monkeypatch):
    monkeypatch.delenv("AUTO_CHECK_EXTERNAL_API_TOKEN", raising=False)
    result = service.generate("admin")

    assert service.authenticate(result.token).authenticated is True
    assert service.authenticate("wrong-token").authenticated is False
    assert service.authenticate("").authenticated is False
    assert service.authenticate(None).authenticated is False  # type: ignore[arg-type]


def test_managed_credential_rejects_environment_token(service, monkeypatch):
    monkeypatch.setenv("AUTO_CHECK_EXTERNAL_API_TOKEN", "env-token-value")
    result = service.generate("admin")

    # Environment token should fail when managed credential exists
    assert service.authenticate("env-token-value").authenticated is False
    # Only the managed token works
    assert service.authenticate(result.token).authenticated is True


def test_authenticate_without_managed_uses_environment_fallback(
    service, monkeypatch
):
    monkeypatch.setenv("AUTO_CHECK_EXTERNAL_API_TOKEN", "env-token-value")

    assert service.authenticate("env-token-value").authenticated is True
    assert service.authenticate("wrong-token").authenticated is False
    assert service.authenticate("").authenticated is False


def test_status_and_errors_contain_no_sensitive_data(service, monkeypatch):
    monkeypatch.setenv("AUTO_CHECK_EXTERNAL_API_TOKEN", "secret-env-token")
    service.generate("admin")

    status = service.status()
    status_text = str(status)
    assert "secret-env-token" not in status_text
    assert "token" not in status_text.lower() or "external" in status_text.lower()

    decision = service.authenticate("wrong")
    decision_text = str(decision)
    assert "secret-env-token" not in decision_text
