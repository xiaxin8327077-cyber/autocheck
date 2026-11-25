"""数据校验模块的相对路由。"""

from __future__ import annotations

import base64
import logging
from traceback import extract_tb
from typing import Any, Callable
from uuid import uuid4

from auto_check.app.module_system.contracts import ModuleHttpResponse, ModuleRequest

from .contracts import AppError
from .diagnostic_logging import log_batch_save_error
from .service import DataValidationService
from .sql_test_run import run_candidate_sql

LOGGER = logging.getLogger("auto_check.modules.data_validation")


_ERROR_STATUSES = {
    "FORBIDDEN": 403,
    "RULE_NOT_FOUND": 404,
    "TASK_NOT_FOUND": 404,
    "TASK_EXECUTOR_UNAVAILABLE": 503,
    "CONFLICT_VERSION": 409,
    "ANALYSIS_CONTEXT_CHANGED": 409,
    "RULE_DELETED": 409,
}


def register_routes(router: Any, service_getter: Callable[[], DataValidationService]) -> None:
    def wrap(permission: str, method: str, path: str, handler: Callable[[ModuleRequest], Any], body: int = 1_000_000) -> None:
        def endpoint(request: ModuleRequest) -> ModuleHttpResponse:
            try:
                return ModuleHttpResponse.json(200, {"data": handler(request)})
            except AppError as exc:
                status = _ERROR_STATUSES.get(exc.code, 400)
                error = {"code": exc.code, "message": exc.code}
                if exc.stage:
                    error["stage"] = exc.stage
                if exc.reference:
                    error["reference"] = exc.reference
                return ModuleHttpResponse.json(status, {"error": error})
            except Exception as exc:
                if path == "/ai/candidates/batch-save":
                    reference = uuid4().hex[:12]
                    log_batch_save_error(exc, reference)
                    return ModuleHttpResponse.json(500, {"error": {
                        "code": "BATCH_SAVE_RESULT_UNKNOWN",
                        "message": "批量保存结果待确认，请再次点击保存按钮核实。",
                        "stage": "batch_save",
                        "reference": reference,
                    }})
                if path != "/ai/preview":
                    raise
                reference = uuid4().hex[:12]
                frames = " -> ".join(f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{frame.lineno}"
                                     for frame in extract_tb(exc.__traceback__)[-8:])
                LOGGER.error("Preview failed reference=%s type=%s frames=%s", reference, type(exc).__name__, frames)
                return ModuleHttpResponse.json(500, {"error": {
                    "code": "PREVIEW_FAILED", "message": "SQL 预览失败，请重试；如仍失败请提供错误编号。",
                    "reference": reference,
                }})
        router.add(method, path, endpoint, permission=permission, max_body_bytes=body)

    wrap("data_validation.view", "GET", "/rules", lambda request: service_getter().list_rules(_user(request), dict(request.query)), 0)
    wrap("data_validation.run", "GET", "/rules/execution-selection", lambda request: service_getter().execution_selection(_user(request), dict(request.query)), 0)
    wrap("data_validation.ai_use", "GET", "/models", lambda request: service_getter().list_models(), 0)
    wrap("data_validation.view_results", "GET", "/tasks/{task_id}/issues", lambda request: service_getter().list_task_issues(_user(request), int(request.path_params["task_id"]), dict(request.query)), 0)
    wrap("data_validation.view", "GET", "/rules/stats", lambda request: service_getter().rule_stats(_user(request)), 0)
    wrap("data_validation.view", "GET", "/report-categories", lambda request: service_getter().list_report_categories(), 0)
    wrap("data_validation.view", "GET", "/rules/{rule_id}/history", lambda request: service_getter().list_rule_history(_user(request), int(request.path_params["rule_id"]), dict(request.query)), 0)
    wrap("data_validation.view", "GET", "/rules/{rule_id}", lambda request: service_getter().get_rule(_user(request), int(request.path_params["rule_id"])), 0)
    wrap("data_validation.view", "GET", "/sources", lambda request: service_getter().list_selectable_sources(), 0)
    wrap("data_validation.view", "GET", "/sources/{source_id}/tables/{table_name}", lambda request: service_getter().describe_source_table(request.path_params["source_id"], request.path_params["table_name"]), 0)
    wrap("data_validation.view_results", "GET", "/tasks", lambda request: service_getter().list_recent_tasks(_user(request), dict(request.query)), 0)
    wrap("data_validation.view_results", "GET", "/tasks/progress", lambda request: service_getter().task_progress(_user(request), dict(request.query)), 0)
    wrap("data_validation.view_results", "GET", "/tasks/{task_id}", lambda request: service_getter().task_detail(_user(request), int(request.path_params["task_id"]), dict(request.query)), 0)
    wrap("data_validation.manage", "POST", "/rules", lambda request: service_getter().save_draft(_user(request), dict(request.body or {})))
    wrap("data_validation.manage", "PUT", "/rules/{rule_id}", lambda request: service_getter().save_draft(_user(request), dict(request.body or {}), int(request.path_params["rule_id"])))
    wrap("data_validation.manage", "DELETE", "/rules/{rule_id}", lambda request: service_getter().delete_rule(_user(request), int(request.path_params["rule_id"])), 1024)
    wrap("data_validation.manage", "POST", "/rules/{rule_id}/copy", lambda request: service_getter().copy_rule(_user(request), int(request.path_params["rule_id"])))
    wrap("data_validation.manage", "POST", "/rules/{rule_id}/disable", lambda request: service_getter().disable_rule(_user(request), int(request.path_params["rule_id"]), expected_rule=(request.body or {}).get("expected_rule")))
    wrap("data_validation.ai_use", "POST", "/ai/parse-rule", lambda request: service_getter().parse_rule_request(_user(request), {**(request.body or {}), "analysis_protocol": 2}))
    wrap("data_validation.ai_use", "POST", "/ai/analyses", lambda request: service_getter().start_analysis(_user(request), {**(request.body or {}), "analysis_protocol": 2}))
    wrap("data_validation.ai_use", "GET", "/ai/analyses/{analysis_id}", lambda request: service_getter().get_analysis(_user(request), str(request.path_params["analysis_id"])))
    wrap("data_validation.ai_use", "DELETE", "/ai/analyses/{analysis_id}", lambda request: service_getter().cancel_analysis(_user(request), str(request.path_params["analysis_id"])))
    wrap("data_validation.manage", "POST", "/ai/candidates/batch-save", lambda request: service_getter().batch_save_candidates(_user(request), dict(request.body or {})))
    wrap("data_validation.ai_use", "POST", "/ai/preview", lambda request: service_getter().preview_candidate(_user(request), dict(request.body or {}), return_questions=True))
    wrap("data_validation.test", "POST", "/ai/tests", lambda request: service_getter().test_candidate(_user(request), dict(request.body or {})))
    wrap("data_validation.test", "POST", "/ai/sql-test", lambda request: run_candidate_sql(service_getter(), _user(request), dict(request.body or {})))
    wrap("data_validation.ai_use", "POST", "/models/test", lambda request: service_getter().test_model(_user(request), str((request.body or {}).get("model_id") or "")))
    wrap("data_validation.test", "POST", "/rules/{rule_id}/tests", lambda request: service_getter().run_tests(_user(request), int(request.path_params["rule_id"]), int((request.body or {})["version_no"]), (request.body or {}).get("cases")))
    wrap("data_validation.confirm", "POST", "/rules/{rule_id}/confirm", lambda request: service_getter().confirm_rule(_user(request), int(request.path_params["rule_id"]), int((request.body or {})["version_no"]), str((request.body or {})["expected_hash"]), expected_rule=(request.body or {}).get("expected_rule")))
    wrap("data_validation.run", "POST", "/tasks", lambda request: service_getter().start_task(_user(request), dict(request.body or {})), 2_500_000)
    wrap("data_validation.run", "POST", "/tasks/{task_id}/pause", lambda request: service_getter().pause_task(_user(request), int(request.path_params["task_id"])))
    wrap("data_validation.run", "POST", "/tasks/{task_id}/resume", lambda request: service_getter().resume_task(_user(request), int(request.path_params["task_id"])))
    wrap("data_validation.run", "POST", "/tasks/{task_id}/cancel", lambda request: service_getter().cancel_task(_user(request), int(request.path_params["task_id"])))
    wrap("data_validation.run", "POST", "/tasks/{task_id}/retry", lambda request: service_getter().retry_failed(_user(request), int(request.path_params["task_id"])))
    wrap("data_validation.export", "POST", "/exports", lambda request: _export(service_getter(), request))
    wrap("data_validation.export", "POST", "/rule-packs/export", lambda request: {"content": service_getter().export_rule_pack(_user(request), list((request.body or {}).get("rule_ids") or [])).decode("utf-8")})
    wrap("data_validation.manage", "POST", "/rule-packs/import", lambda request: service_getter().import_rule_pack(_user(request), str((request.body or {}).get("content") or "").encode("utf-8")))
    wrap("data_validation.admin", "GET", "/settings/documents", lambda request: service_getter().list_documents(), 0)
    wrap(
        "data_validation.admin", "POST", "/settings/documents",
        lambda request: service_getter().import_document(
            _user(request),
            str((request.body or {}).get("file_name") or "document.xlsx"),
            _document_bytes(request.body or {}),
            str((request.body or {}).get("name") or ""),
        ),
        20_000_000,
    )
    wrap(
        "data_validation.admin", "POST", "/settings/documents/{document_id}/activate",
        lambda request: service_getter().activate_document(_user(request), int(request.path_params["document_id"])),
    )
    wrap("data_validation.admin", "GET", "/settings/knowledge", lambda request: service_getter().knowledge.settings(), 0)
    wrap("data_validation.admin", "POST", "/settings/knowledge/preview",
         lambda request: service_getter().knowledge.preview(dict(request.body or {})), 100_000)
    wrap("data_validation.admin", "PUT", "/settings/knowledge",
         lambda request: service_getter().knowledge.save(_user(request), dict(request.body or {})), 100_000)
    wrap("data_validation.admin", "POST", "/settings/knowledge/activation",
         lambda request: service_getter().knowledge.save(_user(request), dict(request.body or {}), activation=True), 1024)
    wrap("data_validation.admin", "GET", "/settings/prompts", lambda request: service_getter().list_prompts(), 0)
    wrap(
        "data_validation.admin", "POST", "/settings/prompts",
        lambda request: service_getter().save_prompt(
            _user(request), str((request.body or {}).get("stage") or ""), str((request.body or {}).get("content") or ""),
        ),
    )
    wrap(
        "data_validation.admin", "POST", "/settings/prompts/{stage}/reset",
        lambda request: service_getter().reset_prompt(_user(request), str(request.path_params["stage"])),
    )
    wrap("data_validation.admin", "GET", "/settings/source-rules", lambda request: service_getter().list_source_rules(), 0)
    wrap(
        "data_validation.admin", "POST", "/settings/source-rules",
        lambda request: service_getter().save_source_rules(
            _user(request), list((request.body or {}).get("rules") or []),
        ),
    )


def _user(request: ModuleRequest) -> dict[str, Any]:
    return dict(request.current_user)


def _export(service: DataValidationService, request: ModuleRequest) -> dict[str, Any]:
    body = request.body or {}
    result = service.export_issues(_user(request), int(body["task_id"]), str(body.get("file_type") or "csv"), body)
    return {"truncated": result["truncated"], "content": result["content"].decode("utf-8", errors="replace")}


def _document_bytes(body: dict[str, Any]) -> bytes:
    encoded = str(body.get("content_base64") or "")
    if not encoded:
        return b""
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        from .contracts import AppError
        raise AppError("VALIDATION_ERROR") from exc
