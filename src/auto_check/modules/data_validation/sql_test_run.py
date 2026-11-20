"""未保存候选的有界只读 SQL 试运行，不写规则或正式执行结果。"""

from __future__ import annotations

import threading
from datetime import date
from types import SimpleNamespace
from typing import Any

from auto_check.app.module_system.permissions import default_permission_evaluator

from .contracts import AppError
from .executor import execute_version
from .issue_query_results import output_projection

MAX_ROWS = 10
TIMEOUT_SECONDS = 30
_SLOTS = threading.BoundedSemaphore(2)


class _SampleSource:
    def __init__(self, metadata):
        self.metadata = metadata
        self.columns = ()

    def __getattr__(self, name):
        return getattr(self.metadata, name)

    def execute_select(self, source_id, sql, params, *, timeout_seconds, max_rows):
        # execute_version 已校验后端编译 SQL；数据库端再限制读取，额外一行仅检测截断。
        limited_sql = f"SELECT * FROM (\n{sql.rstrip().rstrip(';')}\n) AS dv_sql_test\nLIMIT {MAX_ROWS + 1}"
        try:
            result = self.metadata.execute_select(source_id, limited_sql, params,
                timeout_seconds=TIMEOUT_SECONDS, max_rows=MAX_ROWS)
        except Exception as exc:
            if (getattr(exc, "sqlstate", None) == "57014" or getattr(exc, "pgcode", None) == "57014"
                    or (exc.args and exc.args[0] == 3024)):
                raise TimeoutError() from None
            raise
        self.columns = tuple(result.columns)
        rows = tuple(result.rows)
        return SimpleNamespace(columns=self.columns, rows=rows[:MAX_ROWS],
                               truncated=bool(result.truncated or len(rows) > MAX_ROWS))


def run_candidate_sql(service, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not all(default_permission_evaluator(user, permission) for permission in (
            "data_validation.test", "data_validation.run", "data_validation.view_results")):
        raise AppError("FORBIDDEN")
    definition = payload.get("definition")
    value = payload.get("report_date")
    expected_hash = payload.get("expected_hash")
    if (not isinstance(definition, dict) or definition.get("rule_type") != "field_compare"
            or not isinstance(value, str) or not isinstance(expected_hash, str) or not expected_hash):
        raise AppError("VALIDATION_ERROR")
    try:
        report_date = date.fromisoformat(value)
    except ValueError:
        raise AppError("VALIDATION_ERROR") from None
    if report_date.isoformat() != value:
        raise AppError("VALIDATION_ERROR")
    if not _SLOTS.acquire(blocking=False):
        raise AppError("SQL_TEST_LIMIT_REACHED")
    try:
        # 使用当前活动文档重编译；客户端 SQL、参数与行数上限均不参与执行。
        preview = service.preview_candidate(user, {"definition": definition}, require_ai_review=True)
        if preview.get("content_sha256") != expected_hash:
            raise AppError("CONFLICT_VERSION")
        if service.metadata is None:
            raise AppError("SOURCE_UNAVAILABLE")
        source = _SampleSource(service.metadata)
        version = {"definition": preview["definition"], "sql_text": preview["sql_preview"]}
        try:
            result = execute_version(version, {"report_date": report_date,
                "max_rows": MAX_ROWS, "timeout_seconds": TIMEOUT_SECONDS}, source)
        except AppError:
            raise
        except TimeoutError:
            raise AppError("TIMEOUT") from None
        except Exception:
            raise AppError("SOURCE_UNAVAILABLE") from None
        if result.status not in {"PASS", "VIOLATION"}:
            raise AppError(result.error_code or "SOURCE_UNAVAILABLE")
        columns, _ = output_projection(preview["definition"], preview["sql_preview"], True,
            source.columns, preview.get("columns") or [], preview.get("related_columns") or [])
        return {"columns": columns, "rows": list(result.query_results[:MAX_ROWS]),
                "row_count": len(result.query_results[:MAX_ROWS]), "max_rows": MAX_ROWS,
                "truncated": result.truncated, "report_date": report_date.isoformat(), "persisted": False}
    finally:
        _SLOTS.release()
