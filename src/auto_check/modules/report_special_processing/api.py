from __future__ import annotations

import uuid
from typing import Any, Callable, Mapping
from urllib.parse import quote

from auto_check.app.module_system.contracts import ModuleHttpResponse, ModuleRequest

from .contracts import DomainError, ValidationError, public_value
from .validator import MAX_REQUEST_BYTES


def _request_id() -> str:
    return f"req-{uuid.uuid4().hex}"


def _success(data: Any, request_id: str, *, status: int = 200) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(
        status,
        {"data": public_value(data), "meta": {"request_id": request_id}},
    )


def _error(error: DomainError, request_id: str) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(
        error.status,
        {
            "error": {
                "code": error.code,
                "message": error.message,
                "fields": dict(error.fields),
            },
            "meta": {"request_id": request_id},
        },
    )


def _internal_error(request_id: str) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(
        500,
        {
            "error": {
                "code": "internal_error",
                "message": "系统暂时无法处理该请求",
                "fields": {},
            },
            "meta": {"request_id": request_id, "error_id": f"err-{uuid.uuid4().hex}"},
        },
    )


def _id(request: ModuleRequest) -> int:
    try:
        value = int(request.path_params["id"])
    except (KeyError, TypeError, ValueError):
        raise ValidationError(fields={"id": "记录编号无效"}) from None
    if value < 1:
        raise ValidationError(fields={"id": "记录编号无效"})
    return value


def _body(request: ModuleRequest) -> Mapping[str, Any]:
    if request.body is None or not isinstance(request.body, Mapping):
        raise ValidationError()
    return request.body


def _export_response(filename: str, payload: bytes, request_id: str) -> ModuleHttpResponse:
    del request_id
    return ModuleHttpResponse.bytes(
        200,
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=(
            ("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}"),
        ),
    )


def register_routes(router: Any, service_provider: Callable[[], Any]) -> None:
    def handle(callback: Callable[[Any, ModuleRequest, str], Any], *, status: int = 200):
        def handler(request: ModuleRequest) -> ModuleHttpResponse:
            request_id = _request_id()
            try:
                data = callback(service_provider(), request, request_id)
                if isinstance(data, ModuleHttpResponse):
                    return data
                return _success(data, request_id, status=status)
            except DomainError as error:
                return _error(error, request_id)
            except Exception:
                return _internal_error(request_id)

        return handler

    page_view = "report_special_processing.view"
    detail = "report_special_processing.detail"
    create = "report_special_processing.create"
    edit = "report_special_processing.edit"
    confirm = "report_special_processing.confirm"
    void = "report_special_processing.void"
    reopen = "report_special_processing.reopen"
    delete = "report_special_processing.delete"
    routes = (
        ("GET", "/catalog", lambda service, request, rid: service.catalog(request.current_user), page_view, 0, 200),
        ("GET", "/records", lambda service, request, rid: service.list_records(request.query, request.current_user), detail, 0, 200),
        (
            "GET",
            "/records/export",
            lambda service, request, rid: _export_response(
                *service.export_records(request.query),
                rid,
            ),
            detail,
            0,
            200,
        ),
        ("POST", "/records", lambda service, request, rid: service.create(_body(request), request.current_user, request_id=rid), create, MAX_REQUEST_BYTES, 201),
        ("GET", "/records/{id}", lambda service, request, rid: service.get(_id(request), request.current_user), detail, 0, 200),
        ("PUT", "/records/{id}", lambda service, request, rid: service.update(_id(request), _body(request), request.current_user, request_id=rid), edit, MAX_REQUEST_BYTES, 200),
        ("POST", "/records/{id}/status", lambda service, request, rid: service.change_status(_id(request), _body(request), request.current_user, request_id=rid), confirm, MAX_REQUEST_BYTES, 200),
        ("POST", "/records/{id}/void", lambda service, request, rid: service.void(_id(request), _body(request), request.current_user, request_id=rid), void, MAX_REQUEST_BYTES, 200),
        ("DELETE", "/records/{id}", lambda service, request, rid: service.delete(_id(request), _body(request), request.current_user, request_id=rid), delete, MAX_REQUEST_BYTES, 200),
        ("POST", "/records/{id}/reopen", lambda service, request, rid: service.reopen(_id(request), _body(request), request.current_user, request_id=rid), reopen, MAX_REQUEST_BYTES, 200),
        ("GET", "/records/{id}/audit", lambda service, request, rid: service.audit(_id(request), request.query), detail, 0, 200),
        ("GET", "/summary", lambda service, request, rid: service.summary(request.query), detail, 0, 200),
    )
    for method, path, callback, permission, maximum, status in routes:
        router.add(
            method,
            path,
            handle(callback, status=status),
            permission=permission,
            max_body_bytes=maximum,
        )
