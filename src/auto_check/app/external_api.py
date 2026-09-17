"""Single source for the external API token and its read-only status service.

The Bearer token is only read here so the HTTP authentication entry point and the
``platform.external_api_status`` v2 service can never drift apart. No token value,
digest or length ever leaves this module: the status service exposes a single
``token_configured`` boolean and a constant-time ``verify_candidate`` helper.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Mapping

from auto_check.app.module_system.services import BoundService, PlatformServiceSpec


EXTERNAL_API_STATUS_SERVICE = "platform.external_api_status"
EXTERNAL_API_STATUS_VERSION = 2
EXTERNAL_API_TOKEN_ENV = "AUTO_CHECK_EXTERNAL_API_TOKEN"


def read_external_api_token(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    return str(source.get(EXTERNAL_API_TOKEN_ENV, "")).strip()


@dataclass(frozen=True)
class ExternalApiStatusSnapshot:
    token_configured: bool


class _ExternalApiStatusFacade:
    """Read-only, revocable view over the external API token configuration."""

    def __init__(self, token_reader: Callable[[], str]) -> None:
        self._token_reader = token_reader
        self._closed = False
        self._lock = RLock()

    def get_status(self) -> ExternalApiStatusSnapshot:
        with self._lock:
            self._require_open()
            return ExternalApiStatusSnapshot(token_configured=bool(str(self._token_reader()).strip()))

    def verify_candidate(self, candidate: str) -> bool:
        """Constant-time comparison of a candidate token against the current value.

        Never exposes the configured token, its length or its digest. Returns
        ``False`` for any empty or non-string candidate, or when no token is
        configured.
        """
        if not isinstance(candidate, str) or not candidate:
            return False
        with self._lock:
            self._require_open()
            configured = str(self._token_reader()).strip()
            if not configured:
                return False
            return secrets.compare_digest(candidate, configured)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("platform service facade is closed")

    def _close(self) -> None:
        with self._lock:
            self._closed = True


def create_external_api_status_service(
    token_reader: Callable[[], str] = read_external_api_token,
) -> PlatformServiceSpec:
    """Create the v2 external-api-status platform service."""

    def bind(_owner: str) -> BoundService:
        facade = _ExternalApiStatusFacade(token_reader)
        return BoundService(value=facade, close=facade._close)

    return PlatformServiceSpec(
        name=EXTERNAL_API_STATUS_SERVICE,
        version=EXTERNAL_API_STATUS_VERSION,
        binder=bind,
    )
