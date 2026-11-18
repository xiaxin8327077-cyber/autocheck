"""Bounded model calls and safe, traceable module-level error classification."""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from uuid import uuid4

from .contracts import AppError

LOGGER = logging.getLogger("auto_check.modules.data_validation")
GENERATION_TIMEOUT_SECONDS = 120


def model_error(exc: Exception, stage: str) -> AppError:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not item for item in chain):
        chain.append(current)
        current = current.__cause__ or (current.reason if isinstance(current, URLError) and isinstance(current.reason, BaseException) else None)
    if any(isinstance(item, TimeoutError) for item in chain):
        code = "MODEL_TIMEOUT"
    elif any(isinstance(item, HTTPError) for item in chain):
        code = "MODEL_REQUEST_FAILED"
    elif any(isinstance(item, (json.JSONDecodeError, KeyError, IndexError, TypeError)) for item in chain):
        code = "MODEL_RESPONSE_INVALID"
    else:
        code = "MODEL_UNAVAILABLE"
    return failure(code, stage)


def failure(code: str, stage: str) -> AppError:
    reference = uuid4().hex[:12]
    # Never log exception messages, request bodies, URLs, credentials or model output.
    LOGGER.warning("Model call failed code=%s stage=%s reference=%s", code, stage, reference)
    return AppError(code, stage=stage, reference=reference)


def complete_text(model: Any, model_id: str, prompt: str, *, stage: str, timeout: float) -> str:
    try:
        raw = model.complete(model_id, [{"role": "user", "content": prompt}], timeout_seconds=timeout)
    except Exception as exc:
        raise model_error(exc, stage) from exc
    if not isinstance(raw, str) or not raw.strip() or raw.strip() == "None":
        raise failure("MODEL_RESPONSE_INVALID", stage)
    return raw
