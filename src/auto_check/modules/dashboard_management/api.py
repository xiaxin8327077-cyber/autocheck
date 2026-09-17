from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from importlib import resources
from typing import Any, Callable, Mapping

from auto_check.app.module_system.contracts import ModuleHttpResponse, ModuleRequest

from .validator import DomainError, ValidationError, validate_board_code


MAX_BODY_BYTES = 64 * 1024
SCREEN_FILES = {
    "report_submission": "financial-report.html",
    "reporting_process": "financial-report-flow.html",
}
LOGGER = logging.getLogger(__name__)


def _public_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _public_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_public_value(item) for item in value]
    return value


def _request_id() -> str:
    return f"req-{uuid.uuid4().hex}"


def _success(data: Any, request_id: str, *, status: int = 200) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(status, {"data": _public_value(data), "meta": {"request_id": request_id}})


def _board_success(data: Mapping[str, Any], request_id: str) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(200, {
        "status": str(data["status"]),
        "generated_at": str(data["generated_at"]),
        "data": _public_value({
            "data_year": int(data["data_year"]),
            "board": data["board"],
            "regions": data["regions"],
        }),
        "meta": {"request_id": request_id},
    })


def _error(error: DomainError, request_id: str) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(error.status, {
        "error": {"code": error.code, "message": error.message, "fields": dict(error.fields)},
        "meta": {"request_id": request_id},
    })


def _internal_error(request_id: str) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(500, {
        "error": {"code": "internal_error", "message": "系统暂时无法处理该请求", "fields": {}},
        "meta": {"request_id": request_id, "error_id": f"err-{uuid.uuid4().hex}"},
    })


def _monitor_unavailable(request_id: str) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(503, {
        "error": {
            "code": "service_unavailable",
            "message": "接口监控服务暂时不可用",
            "fields": {},
        },
        "meta": {"request_id": request_id},
    })


def _body(request: ModuleRequest) -> Mapping[str, Any]:
    if request.body is None or not isinstance(request.body, Mapping):
        raise ValidationError()
    return request.body


def _screen_response(request: ModuleRequest) -> ModuleHttpResponse:
    request_id = _request_id()
    try:
        board_code = validate_board_code(request.path_params["board_code"])
        content = resources.files(__package__).joinpath(
            "web", "screens", SCREEN_FILES[board_code]
        ).read_bytes()
        return ModuleHttpResponse.bytes(200, content, content_type="text/html; charset=utf-8")
    except DomainError as error:
        return _error(error, request_id)
    except Exception:
        return _internal_error(request_id)


def _id(request: ModuleRequest, name: str) -> int:
    try:
        value = int(request.path_params[name])
    except (KeyError, TypeError, ValueError):
        raise ValidationError(f"{name}无效", fields={name: f"{name}无效"}) from None
    if value < 1:
        raise ValidationError(f"{name}无效", fields={name: f"{name}无效"})
    return value


def register_routes(
    router: Any,
    service_provider: Callable[[], Any],
    monitoring_provider: Callable[[], Any] | None = None,
    credential_service_provider: Callable[[], Any] | None = None,
) -> None:
    def handle(callback: Callable[[Any, ModuleRequest], Any], *, status: int = 200):
        def handler(request: ModuleRequest) -> ModuleHttpResponse:
            request_id = _request_id()
            try:
                return _success(callback(service_provider(), request), request_id, status=status)
            except DomainError as error:
                return _error(error, request_id)
            except Exception:
                return _internal_error(request_id)

        return handler

    def board_preview(request: ModuleRequest) -> ModuleHttpResponse:
        request_id = _request_id()
        try:
            board_code = request.path_params["board_code"]
            service = service_provider()
            return _board_success(
                service.preview_board_data(board_code, request.current_user), request_id
            )
        except DomainError as error:
            return _error(error, request_id)
        except Exception:
            return _internal_error(request_id)

    def external_board_preview(request: ModuleRequest, board_code: str) -> ModuleHttpResponse:
        request_id = _request_id()
        monitor = None
        trace = None
        try:
            monitor = monitoring_provider() if monitoring_provider else None
            trace = monitor.begin_call(board_code, request.client_ip, request_id) if monitor else None
        except Exception:
            LOGGER.warning("external api call monitoring begin failed", exc_info=True)
        try:
            response = _board_success(
                service_provider().preview_external_board_data(board_code), request_id
            )
        except DomainError as error:
            response = _error(error, request_id)
        except Exception:
            response = _internal_error(request_id)
        if trace is not None:
            try:
                monitor.finish_call(trace, response)
            except Exception:
                LOGGER.warning("external api call monitoring finish failed", exc_info=True)
        return response

    def generate_external_api_token(request: ModuleRequest) -> ModuleHttpResponse:
        request_id = _request_id()
        credential_service = credential_service_provider() if credential_service_provider else None
        if credential_service is None:
            return _monitor_unavailable(request_id)
        try:
            body = _body(request)
            if body != {}:
                return ModuleHttpResponse.json(400, {
                    "error": {"code": "invalid_request", "message": "请求体必须为空对象 {}", "fields": {}},
                    "meta": {"request_id": request_id},
                })
            result = credential_service.generate(_operator(request))
        except DomainError as error:
            return _error(error, request_id)
        except Exception as error:
            LOGGER.warning(
                "external api token generation failed (%s)",
                type(error).__name__,
            )
            return _internal_error(request_id)
        return ModuleHttpResponse.json(200, {
            "token": result.token,
            "generated_at": _datetime_text(result.generated_at),
            "rotated": result.rotated,
            "meta": {"request_id": request_id},
        })

    def _operator(request: ModuleRequest) -> str:
        user = request.current_user or {}
        return str(user.get("username") or user.get("id") or "")

    def _datetime_text(value: Any) -> str:
        if isinstance(value, datetime):
            from datetime import timezone as _tz
            if value.tzinfo is not None:
                value = value.astimezone(_tz.utc).replace(tzinfo=None)
            return value.isoformat()
        return str(value)

    def monitor_handle(callback: Callable[[Any, ModuleRequest], Any]):
        def handler(request: ModuleRequest) -> ModuleHttpResponse:
            request_id = _request_id()
            try:
                monitoring = monitoring_provider() if monitoring_provider else None
                if monitoring is None:
                    return _monitor_unavailable(request_id)
                return _success(callback(monitoring, request), request_id)
            except DomainError as error:
                return _error(error, request_id)
            except Exception:
                LOGGER.warning("external api monitoring query failed", exc_info=True)
                return _monitor_unavailable(request_id)

        return handler

    view = "dashboard_management.view"
    manage = "dashboard_management.manage"
    test_sql = "dashboard_management.test_sql"
    monitor_permission = "dashboard_management.external_api_monitor"
    routes = (
        (
            "GET", "/boards",
            lambda service, request: service.catalog("report_submission", request.current_user)["boards"],
            view, 0, 200,
        ),
        (
            "GET", "/boards/{board_code}/catalog",
            lambda service, request: service.catalog(request.path_params["board_code"], request.current_user),
            view, 0, 200,
        ),
        (
            "POST", "/boards/{board_code}/regions",
            lambda service, request: service.create_region(
                request.path_params["board_code"], _body(request), request.current_user,
            ),
            manage, MAX_BODY_BYTES, 201,
        ),
        (
            "PUT", "/regions/{region_id}",
            lambda service, request: service.update_region(
                _id(request, "region_id"), _body(request), request.current_user,
            ),
            manage, MAX_BODY_BYTES, 200,
        ),
        (
            "DELETE", "/regions/{region_id}",
            lambda service, request: service.delete_region(
                _id(request, "region_id"), _body(request), request.current_user,
            ),
            manage, MAX_BODY_BYTES, 200,
        ),
        (
            "POST", "/regions/{region_id}/fields",
            lambda service, request: service.create_field(
                _id(request, "region_id"), _body(request), request.current_user,
            ),
            manage, MAX_BODY_BYTES, 201,
        ),
        (
            "PUT", "/fields/{field_id}",
            lambda service, request: service.update_field(
                _id(request, "field_id"), _body(request), request.current_user,
            ),
            manage, MAX_BODY_BYTES, 200,
        ),
        (
            "GET", "/datasources",
            lambda service, request: service.list_datasources(),
            view, 0, 200,
        ),
        (
            "POST", "/regions/{region_id}/source/test",
            lambda service, request: service.test_sql(
                _id(request, "region_id"), _body(request), request.current_user,
            ),
            test_sql, MAX_BODY_BYTES, 200,
        ),
        (
            "POST", "/regions/{region_id}/source/system-preview",
            lambda service, request: service.preview_system_data(
                _id(request, "region_id"), request.current_user,
            ),
            test_sql, 0, 200,
        ),
        (
            "PUT", "/regions/{region_id}/source",
            lambda service, request: service.save_source_config(
                _id(request, "region_id"), _body(request), request.current_user,
            ),
            manage, MAX_BODY_BYTES, 200,
        ),
    )
    for method, path, callback, permission, max_body_bytes, status in routes:
        router.add(
            method,
            path,
            handle(callback, status=status),
            permission=permission,
            max_body_bytes=max_body_bytes,
        )
    router.add(
        "GET",
        "/boards/{board_code}/preview",
        board_preview,
        permission=view,
        max_body_bytes=0,
    )
    router.add(
        "GET",
        "/boards/{board_code}/screen",
        _screen_response,
        permission=view,
        max_body_bytes=0,
    )

    def _make_external_authenticator() -> Any:
        from auto_check.app.module_system.routing import ExternalAuthDecision

        if credential_service_provider is None:
            def _unconfigured(candidate: str) -> ExternalAuthDecision:
                return ExternalAuthDecision(configured=False, authenticated=False)

            return _unconfigured

        def _authenticate(candidate: str) -> Any:
            service = credential_service_provider()
            if service is None:
                return ExternalAuthDecision(configured=False, authenticated=False)
            return service.authenticate(candidate)

        return _authenticate

    external_authenticator = _make_external_authenticator()

    router.add(
        "GET",
        "/boards/report_submission/preview",
        lambda request: external_board_preview(request, "report_submission"),
        permission=view,
        max_body_bytes=0,
        external=True,
        external_authenticator=external_authenticator,
    )
    router.add(
        "GET",
        "/boards/reporting_process/preview",
        lambda request: external_board_preview(request, "reporting_process"),
        permission=view,
        max_body_bytes=0,
        external=True,
        external_authenticator=external_authenticator,
    )
    router.add(
        "GET",
        "/external-api/monitor/summary",
        monitor_handle(lambda monitoring, request: monitoring.monitor_summary(
            credential_status=_credential_status(credential_service_provider),
        )),
        permission=monitor_permission,
        max_body_bytes=0,
    )
    router.add(
        "GET",
        "/external-api/monitor/calls",
        monitor_handle(lambda monitoring, request: monitoring.list_calls(request.query)),
        permission=monitor_permission,
        max_body_bytes=0,
    )

    token_manage = "dashboard_management.external_api_token_manage"
    router.add(
        "POST",
        "/external-api/token/generate",
        generate_external_api_token,
        permission=token_manage,
        max_body_bytes=64,
    )


def _credential_status(credential_service_provider: Callable[[], Any] | None) -> dict[str, Any]:
    if credential_service_provider is None:
        return {"configured": False, "source": "none"}
    try:
        status = credential_service_provider().status()
        return {
            "configured": status.configured,
            "source": status.source,
            "generated_at": status.generated_at,
        }
    except Exception:
        return {"configured": False, "source": "none", "generated_at": None}
