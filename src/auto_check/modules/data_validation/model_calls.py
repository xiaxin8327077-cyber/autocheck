"""Model calls and safe, traceable module-level error classification."""
from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from threading import Event
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from uuid import uuid4

from .analysis_jobs import AnalysisCancelled, AnalysisControl
from .contracts import AppError

LOGGER = logging.getLogger("auto_check.modules.data_validation")
SYNC_GENERATION_TIMEOUT_SECONDS = 120
SUPPLEMENT_TIMEOUT_SECONDS = 20


def model_error(exc: Exception, stage: str, *, analysis_id="", round_number=None) -> AppError:
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
    return failure(code, stage, analysis_id=analysis_id, round_number=round_number)


def failure(code: str, stage: str, *, category: str = "", analysis_id: str = "", round_number: int | None = None,
            repair_hint: str = "") -> AppError:
    reference = uuid4().hex[:12]
    # Never log exception messages, request bodies, URLs, credentials or model output.
    LOGGER.warning("Model call failed code=%s stage=%s reference=%s category=%s analysis=%s round=%s",
                   code, stage, reference, category or code.lower(), analysis_id or "-", round_number if round_number is not None else "-")
    error = AppError(code, stage=stage, reference=reference)
    error.category = category or code.lower()
    error.repair_hint = repair_hint
    return error


def _check_active(event, stage):
    if isinstance(event, AnalysisControl):
        event.check(stage)
    elif event is not None and event.is_set():
        raise AnalysisCancelled()


def complete_text(model: Any, model_id: str, prompt: str, *, stage: str, timeout: float | None,
                  cancel_event: Event | None = None, model_stage: str = "", analysis_id="", round_number=None) -> str:
    timeout = SYNC_GENERATION_TIMEOUT_SECONDS if timeout is None else timeout
    control = (cancel_event.model_call(model_stage or stage, stage, timeout)
               if isinstance(cancel_event, AnalysisControl) else nullcontext(timeout))
    with control as remaining:
        if isinstance(cancel_event, AnalysisControl):
            analysis_id, round_number = cancel_event.analysis_id, cancel_event.model_round
        return _complete_text(model, model_id, prompt, stage, remaining, cancel_event, analysis_id, round_number)


def _complete_text(model, model_id, prompt, stage, timeout, cancel_event, analysis_id, round_number):
    _check_active(cancel_event, stage)
    options = {"cancel_event": cancel_event} if cancel_event is not None else {}
    try:
        raw = model.complete(model_id, [{"role": "user", "content": prompt}], timeout_seconds=timeout, **options)
    except Exception as exc:
        _check_active(cancel_event, stage)
        raise model_error(exc, stage, analysis_id=analysis_id, round_number=round_number) from exc
    _check_active(cancel_event, stage)
    if not isinstance(raw, str) or not raw.strip() or raw.strip() == "None":
        raise failure("MODEL_RESPONSE_INVALID", stage, analysis_id=analysis_id, round_number=round_number)
    return raw


def semantic_completion(model, model_id, prompt, *, stage, public_stage, round_number, analysis_id, options, cancel_event,
                        usage_observer=None):
    timeout = SUPPLEMENT_TIMEOUT_SECONDS if stage == "supplement_suggestions" else SYNC_GENERATION_TIMEOUT_SECONDS
    _check_active(cancel_event, public_stage)
    trace = {"analysis_id": analysis_id, "round_number": round_number}
    if not callable(getattr(model, "complete_with_options", None)):
        raise failure("MODEL_UNAVAILABLE", public_stage, category="bounded_completion_unavailable", **trace)
    started = monotonic()
    usage = {}
    billed_tokens = None
    status = "failed"
    try:
        control = (cancel_event.model_call(stage, public_stage, timeout)
                   if isinstance(cancel_event, AnalysisControl) else nullcontext(timeout))
        with control as remaining:
            reply = model.complete_with_options(model_id, [{"role": "user", "content": prompt}],
                                                timeout_seconds=remaining, cancel_event=cancel_event, options=options)
        _check_active(cancel_event, public_stage)
        if not isinstance(reply, dict):
            raise failure("MODEL_RESPONSE_INVALID", public_stage, **trace)
        counts = reply.get("usage")
        if isinstance(counts, dict):
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens",
                        "prompt_cache_miss_tokens", "reasoning_tokens", "cached_tokens"):
                if type(counts.get(key)) is int and counts[key] >= 0:
                    usage[key] = counts[key]
            for container, key in (("completion_tokens_details", "reasoning_tokens"), ("prompt_tokens_details", "cached_tokens")):
                detail = counts.get(container)
                if isinstance(detail, dict) and type(detail.get(key)) is int and detail[key] >= 0:
                    usage[key] = detail[key]
        content = reply.get("content")
        # Standard completion_tokens already includes reasoning. Contradictory diagnostics
        # cannot establish a smaller debit than the allocation sent to the gateway.
        completed = usage.get("completion_tokens")
        if completed and completed >= usage.get("reasoning_tokens", 0):
            if ("total_tokens" not in usage or "prompt_tokens" not in usage
                    or usage["total_tokens"] == usage["prompt_tokens"] + completed):
                billed_tokens = completed
        if reply.get("finish_reason") == "length":
            status = "incomplete"
            raise failure("MODEL_OUTPUT_LIMIT", public_stage, **trace)
        if reply.get("finish_reason") not in ("stop", None, ""):
            status = "incomplete"
            raise failure("MODEL_RESPONSE_INVALID", public_stage, **trace)
        if not isinstance(content, str) or not content.strip():
            status = "empty"
            raise failure("MODEL_RESPONSE_INVALID", public_stage, **trace)
        status = "received"
        return content
    except (AppError, AnalysisCancelled):
        raise
    except Exception as exc:
        _check_active(cancel_event, public_stage)
        raise model_error(exc, public_stage, **trace) from exc
    finally:
        if usage_observer is not None:
            usage_observer(billed_tokens)
        LOGGER.info("Semantic model analysis=%s round=%d stage=%s status=%s duration_ms=%d usage=%s",
                    analysis_id, round_number, stage, status, round((monotonic() - started) * 1000), usage)
