from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import (
    CHAR,
    DATETIME,
    VARCHAR,
    Column,
    MetaData,
    String,
    Table,
    select,
)


METADATA = MetaData()
IDENTIFIER_TYPE = CHAR(64)
EXTERNAL_API_CREDENTIALS = Table(
    "dashboard_management_external_api_credentials",
    METADATA,
    Column("scope_key", VARCHAR(128), primary_key=True),
    Column("token_digest", CHAR(64), nullable=False),
    Column("token_fingerprint", VARCHAR(16), nullable=False),
    Column("created_by", VARCHAR(128), nullable=False),
    Column("created_at", DATETIME, nullable=False),
    Column("updated_by", VARCHAR(128), nullable=False),
    Column("updated_at", DATETIME, nullable=False),
)

BOARD_PREVIEW_SCOPE = "dashboard_management.board_preview"


@dataclass(frozen=True)
class ExternalApiCredentialStatus:
    configured: bool
    source: Literal["managed", "environment", "none"]
    generated_at: datetime | None


@dataclass(frozen=True)
class GeneratedExternalApiToken:
    token: str
    generated_at: datetime
    rotated: bool


class _CredentialRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def read_status(self) -> tuple[str, datetime] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                select(
                    EXTERNAL_API_CREDENTIALS.c.token_digest,
                    EXTERNAL_API_CREDENTIALS.c.updated_at,
                ).where(
                    EXTERNAL_API_CREDENTIALS.c.scope_key == BOARD_PREVIEW_SCOPE
                )
            ).first()
            return (str(row[0]), row[1]) if row is not None else None

    def read_digest(self) -> str | None:
        status = self.read_status()
        return status[0] if status is not None else None

    def replace_digest(
        self,
        digest: str,
        fingerprint: str,
        operator: str,
        generated_at: datetime,
        rotated: bool,
    ) -> None:
        with self.database.transaction() as connection:
            existing = connection.execute(
                select(EXTERNAL_API_CREDENTIALS.c.scope_key).where(
                    EXTERNAL_API_CREDENTIALS.c.scope_key == BOARD_PREVIEW_SCOPE
                )
            ).first()
            if existing is None:
                connection.execute(
                    EXTERNAL_API_CREDENTIALS.insert().values(
                        scope_key=BOARD_PREVIEW_SCOPE,
                        token_digest=digest,
                        token_fingerprint=fingerprint,
                        created_by=operator,
                        created_at=generated_at,
                        updated_by=operator,
                        updated_at=generated_at,
                    )
                )
            else:
                connection.execute(
                    EXTERNAL_API_CREDENTIALS.update()
                    .where(EXTERNAL_API_CREDENTIALS.c.scope_key == BOARD_PREVIEW_SCOPE)
                    .values(
                        token_digest=digest,
                        token_fingerprint=fingerprint,
                        updated_by=operator,
                        updated_at=generated_at,
                    )
                )


def _compute_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _compute_fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return digest.hex()[:16]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DashboardExternalApiCredentialService:
    def __init__(self, database: Any, status_facade: Any) -> None:
        self._database = database
        self._repository = _CredentialRepository(database)
        self._status_facade = status_facade

    def status(self) -> ExternalApiCredentialStatus:
        managed = self._repository.read_status()
        if managed is not None:
            return ExternalApiCredentialStatus(
                configured=True,
                source="managed",
                generated_at=managed[1],
            )
        if self._status_facade.get_status().token_configured:
            return ExternalApiCredentialStatus(
                configured=True,
                source="environment",
                generated_at=None,
            )
        return ExternalApiCredentialStatus(
            configured=False,
            source="none",
            generated_at=None,
        )

    def authenticate(self, candidate: str) -> "ExternalAuthDecision":
        from auto_check.app.module_system.routing import ExternalAuthDecision

        digest = self._repository.read_digest()
        if digest is not None:
            if not isinstance(candidate, str) or not candidate:
                return ExternalAuthDecision(configured=True, authenticated=False)
            candidate_digest = _compute_digest(candidate)
            return ExternalAuthDecision(
                configured=True,
                authenticated=secrets.compare_digest(candidate_digest, digest),
            )
        if not self._status_facade.get_status().token_configured:
            return ExternalAuthDecision(configured=False, authenticated=False)
        return ExternalAuthDecision(
            configured=True,
            authenticated=self._status_facade.verify_candidate(candidate),
        )

    def generate(self, operator: str) -> GeneratedExternalApiToken:
        token = secrets.token_urlsafe(32)
        digest = _compute_digest(token)
        fingerprint = _compute_fingerprint(token)
        generated_at = _now()
        rotated = self._repository.read_digest() is not None
        self._repository.replace_digest(
            digest=digest,
            fingerprint=fingerprint,
            operator=operator,
            generated_at=generated_at,
            rotated=rotated,
        )
        return GeneratedExternalApiToken(
            token=token,
            generated_at=generated_at,
            rotated=rotated,
        )
