"""Owned, bounded file output for the analysis module's structured diagnostics."""

import copy
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
from threading import RLock
from traceback import walk_tb

from sqlalchemy.exc import DBAPIError


LOGGER = logging.getLogger("auto_check.modules.data_validation")
MAX_LOG_BYTES = 1024 * 1024
_LOCK = RLock()
_previous_level = None
_BATCH_SAVE_FAILURE = "Batch save result unknown reference=%s stage=%s type=%s driver_code=%s frames=%s"
_FRAME = r"[A-Za-z_][A-Za-z0-9_]{0,79}\.py:[0-9]{1,6}"
_EVENTS = {
    "Model call failed code=%s stage=%s reference=%s category=%s analysis=%s round=%s":
        ("code", "stage", "reference", "category", "analysis", "round"),
    "Semantic model analysis=%s round=%d stage=%s status=%s duration_ms=%d usage=%s":
        ("analysis", "round", "stage", "status", "duration_ms", "usage"),
    "Semantic review analysis=%s round=%d stage=generate_rule category=%s path=%s":
        ("analysis", "round", "category", "path"),
    "AI analysis failed reference=%s type=%s": ("reference", "type"),
    _BATCH_SAVE_FAILURE: ("reference", "stage", "type", "driver_code", "frames"),
    "AI analysis limit code=%s analysis=%s round=%d phase=%s reference=%s":
        ("code", "analysis", "round", "phase", "reference"),
    'Semantic JSON invalid reference=%s analysis=%s round=%d stage=%s chars=%d reason=%s line=%d column=%d':
        ('reference', 'analysis', 'round', 'stage', 'chars', 'reason', 'line', 'column'),
}
_CODES = {"MODEL_TIMEOUT", "MODEL_UNAVAILABLE", "MODEL_REQUEST_FAILED", "MODEL_RESPONSE_INVALID", "MODEL_OUTPUT_LIMIT",
          "ANALYSIS_TIMEOUT", "ANALYSIS_ROUND_LIMIT", "ANALYSIS_OUTPUT_LIMIT"}
_ENUMS = {
    "code": _CODES,
    "category": {code.lower() for code in _CODES} | {
        "structure", "unknown_field", "dictionary_partition", "field_binding", "rule_validation",
        "invalid_json_object", "selection_structure", "candidate_targets_structure",
        "missing_target_and_explanation", "target_document_binding", "MODEL_RESPONSE_INVALID", "VALIDATION_ERROR"},
    "stage": {"select_table", "generate_rule", "test_model", "select_and_generate", "review_interpretations", "repair_rule", "repair_json", "batch_save"},
    "status": {"failed", "received", "incomplete", "empty"},
    "phase": {"preparing", "model_wait", "local_check", "publishing"},
    'reason': {'syntax', 'object_required'},
    "type": {"RuntimeError", "ValueError", "TypeError", "KeyError", "OSError", "OperationalError",
             "IntegrityError", "TimeoutError", "AssertionError", "AttributeError", "IndexError",
             "DataError", "ProgrammingError", "DatabaseError", "InterfaceError", "InternalError"},
}
_USAGE_KEYS = {"prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens",
               "prompt_cache_miss_tokens", "reasoning_tokens", "cached_tokens"}
_PATH_PARTS = {"draft", "plans", "semantic_intent", "metrics", "scopes", "open_questions", "rule_name",
               "violation_message", "memberships", "field"}


def _safe_value(field, value):
    if field in _ENUMS:
        return value if type(value) is str and value in _ENUMS[field] else "other"
    if field == "usage":
        return {key: value[key] for key in sorted(_USAGE_KEYS)
                if type(value) is dict and type(value.get(key)) is int and 0 <= value[key] < 2**63}
    if field in {"round", "duration_ms", 'chars', 'line', 'column'}:
        return value if type(value) is int and 0 <= value < 2**63 else ("-" if value == "-" else 0)
    if field == "driver_code":
        return value if type(value) is int and 1 <= value <= 99999 else "-"
    if field == "frames":
        return value if type(value) is str and re.fullmatch(rf"{_FRAME}(?: -> {_FRAME}){{0,7}}", value) else "-"
    if type(value) is not str or len(value) > 120:
        return "-"
    if field == "reference" and re.fullmatch("[0-9a-f]{12}", value):
        return value
    if field == "analysis" and re.fullmatch("[a-zA-Z0-9_-]{32}", value):
        return value[:8]
    if field == "analysis" and re.fullmatch("[a-zA-Z0-9_-]{8}|[0-9a-f]{12}", value):
        return value
    if field == "path" and all(p in _PATH_PARTS or re.fullmatch("[0-9]{1,3}", p) for p in value.split(".")):
        return value
    return "-"


def log_batch_save_error(error: Exception, reference: str) -> None:
    frames = []
    for frame, line in walk_tb(error.__traceback__):
        filename = os.path.basename(frame.f_code.co_filename.replace("\\", "/"))
        location = f"{filename}:{line}"
        if re.fullmatch(_FRAME, location):
            frames.append(location)
    driver_args = getattr(error.orig, "args", ()) if isinstance(error, DBAPIError) else ()
    LOGGER.error(
        _BATCH_SAVE_FAILURE, reference, "batch_save", _safe_value("type", type(error).__name__),
        _safe_value("driver_code", driver_args[0] if driver_args else None), " -> ".join(frames[-8:]),
    )


class _AnalysisFile(RotatingFileHandler):
    def emit(self, record):
        # Never format arbitrary messages, raw argument objects, or attached tracebacks.
        if self._closed:
            return
        fields = _EVENTS.get(record.msg) if type(record.msg) is str and record.name == LOGGER.name else None
        if not fields or type(record.args) is not tuple or len(fields) != len(record.args):
            return
        safe = copy.copy(record)
        safe.args = tuple(_safe_value(field, value) for field, value in zip(fields, record.args))
        safe.exc_info = safe.exc_text = safe.stack_info = None
        super().emit(safe)

    def handleError(self, record):
        if not self.write_warning_sent:
            self.write_warning_sent = True
            self.host_logger.warning("AI 分析诊断文件写入失败，请检查日志目录权限与可用空间")


def start_diagnostics(context):
    global _previous_level
    override = os.environ.get("AUTO_CHECK_ANALYSIS_LOG_DIR")
    if override is None:
        directory = Path(context.config_path).absolute().parent / "logs" / "data_validation"
    else:
        directory = Path(override)
        if not directory.is_absolute():
            context.logger.warning("AUTO_CHECK_ANALYSIS_LOG_DIR 须设置为绝对目录，AI 分析诊断文件未启用")
            return None
    with _LOCK:
        try:
            path = Path(os.path.abspath(directory / "analysis.log"))
            for handler in LOGGER.handlers:
                if isinstance(handler, _AnalysisFile) and Path(handler.baseFilename) == path:
                    handler.owners += 1
                    return handler
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = _AnalysisFile(path, maxBytes=MAX_LOG_BYTES, backupCount=3, encoding="utf-8")
        except (OSError, ValueError):
            context.logger.warning("AI 分析诊断文件无法打开，请检查日志目录权限与可用空间")
            return None
        handler.host_logger = context.logger
        handler.write_warning_sent = False
        handler.owners = 1
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        if _previous_level is None:
            _previous_level = LOGGER.level
            LOGGER.setLevel(logging.INFO)
        LOGGER.addHandler(handler)
        return handler


def stop_diagnostics(handler):
    global _previous_level
    if handler is None:
        return
    with _LOCK:
        handler.owners -= 1
        if handler.owners:
            return
        LOGGER.removeHandler(handler)
        handler.close()
        if not any(isinstance(active, _AnalysisFile) for active in LOGGER.handlers):
            LOGGER.setLevel(_previous_level)
            _previous_level = None
