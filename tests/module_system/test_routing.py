from __future__ import annotations

import pytest

from auto_check.app.module_system.contracts import ModuleHttpResponse, ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouteConflict, ModuleRouter


ADMIN = {"id": "1", "role": "admin"}
USER = {"id": "2", "role": "user"}


def _rejecting_authenticator(candidate: str) -> "ExternalAuthDecision":
    from auto_check.app.module_system.routing import ExternalAuthDecision
    return ExternalAuthDecision(configured=False, authenticated=False)


def _request(method: str, path: str, user=USER) -> ModuleRequest:
    return ModuleRequest(method, path, {}, {}, None, user)


def test_admin_has_all_module_permissions_and_user_has_view_only():
    assert default_permission_evaluator(ADMIN, "custom_reports.publish") is True
    assert default_permission_evaluator(USER, "custom_reports.view") is True
    assert default_permission_evaluator(USER, "custom_reports.publish") is False
    assert default_permission_evaluator(None, "custom_reports.view") is False


def test_router_matches_relative_path_and_decodes_parameter(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add(
        "GET",
        "/templates/{template_id}",
        lambda request: ModuleHttpResponse.json(200, {"id": request.path_params["template_id"]}),
        permission="custom_reports.view",
        max_body_bytes=0,
    )

    response = router.dispatch(_request("GET", "/api/modules/custom-reports/templates/abc%201"))

    assert response is not None
    assert response.status == 200
    assert response.body == {"id": "abc 1"}


def test_router_returns_forbidden_before_handler(valid_manifest):
    called = False

    def handler(request):
        nonlocal called
        called = True
        return ModuleHttpResponse.json(200, {})

    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add("POST", "/publish", handler, permission="custom_reports.publish", max_body_bytes=1024)

    response = router.dispatch(_request("POST", "/api/modules/custom-reports/publish"))

    assert response.status == 403
    assert response.body == {"error": "permission denied"}
    assert called is False


def test_router_rejects_duplicate_method_and_path(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    handler = lambda request: ModuleHttpResponse.json(200, {})
    router.add("GET", "/templates", handler, permission="custom_reports.view", max_body_bytes=0)

    with pytest.raises(ModuleRouteConflict):
        router.add("GET", "/templates", handler, permission="custom_reports.view", max_body_bytes=0)


def test_router_rejects_non_relative_paths_and_undeclared_permissions(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    handler = lambda request: ModuleHttpResponse.json(200, {})

    with pytest.raises(ValueError, match="relative"):
        router.add("GET", "templates", handler, permission="custom_reports.view", max_body_bytes=0)
    with pytest.raises(ValueError, match="relative"):
        router.add("GET", "/api/templates", handler, permission="custom_reports.view", max_body_bytes=0)
    with pytest.raises(ValueError, match="declared"):
        router.add("GET", "/templates", handler, permission="custom_reports.delete", max_body_bytes=0)


def test_router_returns_none_for_unknown_path_and_does_not_match_multiple_segments(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add(
        "GET",
        "/templates/{template_id}",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
    )

    assert router.dispatch(_request("GET", "/api/modules/custom-reports/missing")) is None
    assert router.dispatch(_request("GET", "/api/modules/custom-reports/templates/first/second")) is None


def test_router_returns_allowed_methods_for_matching_path(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    handler = lambda request: ModuleHttpResponse.json(200, {})
    router.add("GET", "/templates", handler, permission="custom_reports.view", max_body_bytes=0)
    router.add("POST", "/templates", handler, permission="custom_reports.publish", max_body_bytes=0)

    response = router.dispatch(_request("PUT", "/api/modules/custom-reports/templates", ADMIN))

    assert response.status == 405
    assert response.body == {"error": "method not allowed"}
    assert response.headers == (("Allow", "GET, POST"),)


def test_router_rejects_requests_larger_than_the_route_limit(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add(
        "POST",
        "/templates",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.publish",
        max_body_bytes=4,
    )

    response = router.dispatch(
        _request("POST", "/api/modules/custom-reports/templates", ADMIN), body_size=5
    )

    assert response == ModuleHttpResponse.json(413, {"error": "request body too large"})


def test_router_preflight_exposes_route_body_limit_without_calling_handler(valid_manifest):
    called = False

    def handler(request):
        nonlocal called
        called = True
        return ModuleHttpResponse.json(200, {})

    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add("POST", "/tiny", handler, permission="custom_reports.publish", max_body_bytes=1)

    preflight = router.preflight("POST", "/api/modules/custom-reports/tiny")

    assert preflight.status == 200
    assert preflight.max_body_bytes == 1
    assert called is False


def test_router_maps_value_error_to_sanitized_bad_request(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    def handler(request):
        raise ValueError("password=not-for-response")

    router.add("GET", "/templates", handler, permission="custom_reports.view", max_body_bytes=0)

    response = router.dispatch(_request("GET", "/api/modules/custom-reports/templates"))

    assert response.status == 400
    assert response.body == {"error": "invalid request"}


def test_router_sanitizes_unexpected_errors_and_includes_tracking_fields(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    def handler(request):
        raise RuntimeError("password=not-for-response")

    router.add("GET", "/templates", handler, permission="custom_reports.view", max_body_bytes=0)

    response = router.dispatch(_request("GET", "/api/modules/custom-reports/templates"))

    assert response.status == 500
    assert response.body["error"] == "internal server error"
    assert response.body["module_id"] == "custom_reports"
    assert isinstance(response.body["error_id"], str)
    assert response.body["error_id"]
    assert "password" not in str(response.body)


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: object(),
        lambda request: ModuleHttpResponse(99, {}, "application/json"),
        lambda request: ModuleHttpResponse(200, b"ok", "text/plain\r\nX-Injected: yes"),
        lambda request: ModuleHttpResponse.bytes(
            200,
            b"ok",
            content_type="text/plain",
            headers=(("Content-Length", "2"),),
        ),
        lambda request: ModuleHttpResponse.bytes(
            200,
            b"ok",
            content_type="text/plain",
            headers=(("ETag", '"safe"\r\nX-Injected: yes'),),
        ),
    ],
)
def test_router_sanitizes_invalid_module_response_contracts(valid_manifest, handler):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add("GET", "/download", handler, permission="custom_reports.view", max_body_bytes=0)

    response = router.dispatch(_request("GET", "/api/modules/custom-reports/download"))

    assert response.status == 500
    assert response.body["error"] == "internal server error"
    assert response.body["module_id"] == "custom_reports"


def test_router_allows_documented_module_download_headers(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add(
        "GET",
        "/download",
        lambda request: ModuleHttpResponse.bytes(
            200,
            b"ok",
            content_type="text/plain; charset=utf-8",
            headers=(
                ("Content-Disposition", 'attachment; filename="result.txt"'),
                ("ETag", '"result"'),
            ),
        ),
        permission="custom_reports.view",
        max_body_bytes=0,
    )

    response = router.dispatch(_request("GET", "/api/modules/custom-reports/download"))

    assert response.status == 200
    assert response.body == b"ok"
    assert response.headers == (
        ("Content-Disposition", 'attachment; filename="result.txt"'),
        ("ETag", '"result"'),
    )


def test_external_dispatch_only_matches_routes_explicitly_marked_external(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add(
        "GET",
        "/internal-only",
        lambda request: ModuleHttpResponse.json(200, {"route": "internal"}),
        permission="custom_reports.view",
        max_body_bytes=0,
    )
    router.add(
        "GET",
        "/published",
        lambda request: ModuleHttpResponse.json(
            200,
            {"route": "external", "current_user": dict(request.current_user)},
        ),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=_rejecting_authenticator,
    )

    hidden = router.dispatch_external(
        _request("GET", "/api/external/v1/custom-reports/internal-only", user={})
    )
    published = router.dispatch_external(
        _request("GET", "/api/external/v1/custom-reports/published", user={})
    )

    assert hidden is None
    assert published is not None
    assert published.status == 200
    assert published.body == {"route": "external", "current_user": {}}


def test_external_dispatch_propagates_client_ip_to_handler(valid_manifest):
    captured = {}

    def handler(request):
        captured["client_ip"] = request.client_ip
        return ModuleHttpResponse.json(200, {"client_ip": request.client_ip})

    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add(
        "GET",
        "/published",
        handler,
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=_rejecting_authenticator,
    )

    response = router.dispatch_external(
        ModuleRequest(
            "GET",
            "/api/external/v1/custom-reports/published",
            {},
            {},
            None,
            {},
            client_ip="2001:db8::7",
        )
    )

    assert response.status == 200
    assert captured["client_ip"] == "2001:db8::7"
    assert response.body == {"client_ip": "2001:db8::7"}


def test_external_route_registration_only_accepts_get(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    with pytest.raises(ValueError, match="GET"):
        router.add(
            "POST",
            "/published",
            lambda request: ModuleHttpResponse.json(200, {}),
            permission="custom_reports.publish",
            max_body_bytes=0,
            external=True,
        external_authenticator=_rejecting_authenticator,
    )


def test_external_preflight_reports_only_explicit_external_routes(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    router.add(
        "GET",
        "/published",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=_rejecting_authenticator,
    )
    router.add(
        "GET",
        "/internal-only",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
    )

    assert router.external_preflight(
        "GET", "/api/external/v1/custom-reports/published"
    ).status == 200
    assert router.external_preflight(
        "POST", "/api/external/v1/custom-reports/published"
    ).status == 405
    assert router.external_preflight(
        "GET", "/api/external/v1/custom-reports/internal-only"
    ).status == 404


def test_external_preflight_exposes_rate_limiter_and_rejection_observer(valid_manifest):
    from auto_check.app.module_system.routing import (
        ExternalRateLimitDecision,
        ExternalRejectionEvent,
    )

    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    def limiter(client_ip: str) -> ExternalRateLimitDecision:
        return ExternalRateLimitDecision(allowed=client_ip == "127.0.0.1")

    observed: list[ExternalRejectionEvent] = []
    observer = observed.append
    router.add(
        "GET",
        "/published",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=_rejecting_authenticator,
        external_rate_limiter=limiter,
        external_rejection_observer=observer,
    )

    get_preflight = router.external_preflight(
        "GET", "/api/external/v1/custom-reports/published"
    )
    method_preflight = router.external_preflight(
        "POST", "/api/external/v1/custom-reports/published"
    )

    assert get_preflight.external_rate_limiter is limiter
    assert get_preflight.external_rejection_observer is observer
    assert method_preflight.status == 405
    assert method_preflight.external_rejection_observer is observer


def test_internal_route_rejects_external_security_callbacks(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    with pytest.raises(ValueError, match="external_rate_limiter"):
        router.add(
            "GET",
            "/internal-only",
            lambda request: ModuleHttpResponse.json(200, {}),
            permission="custom_reports.view",
            max_body_bytes=0,
            external_rate_limiter=lambda client_ip: None,
        )

    with pytest.raises(ValueError, match="external_rejection_observer"):
        router.add(
            "GET",
            "/internal-only",
            lambda request: ModuleHttpResponse.json(200, {}),
            permission="custom_reports.view",
            max_body_bytes=0,
            external_rejection_observer=lambda event: None,
        )


def test_external_route_keeps_internal_permission_checks(valid_manifest):
    router = ModuleRouter(valid_manifest, lambda current_user, permission: False)
    router.add(
        "GET",
        "/published",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=_rejecting_authenticator,
    )

    internal = router.dispatch(
        _request("GET", "/api/modules/custom-reports/published", user={})
    )
    external = router.dispatch_external(
        _request("GET", "/api/external/v1/custom-reports/published", user={})
    )

    assert internal.status == 403
    assert external.status == 200


def test_external_route_must_register_authenticator(valid_manifest):
    from auto_check.app.module_system.routing import ExternalAuthDecision

    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    def authenticator(candidate: str) -> ExternalAuthDecision:
        return ExternalAuthDecision(configured=True, authenticated=bool(candidate))

    router.add(
        "GET",
        "/published",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=authenticator,
    )

    preflight = router.external_preflight("GET", "/api/external/v1/custom-reports/published")
    assert preflight.status == 200
    assert preflight.external_authenticator is authenticator


def test_internal_route_rejects_external_authenticator(valid_manifest):
    from auto_check.app.module_system.routing import ExternalAuthDecision

    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    def authenticator(candidate: str) -> ExternalAuthDecision:
        return ExternalAuthDecision(configured=True, authenticated=False)

    with pytest.raises(ValueError, match="external_authenticator"):
        router.add(
            "GET",
            "/internal-only",
            lambda request: ModuleHttpResponse.json(200, {}),
            permission="custom_reports.view",
            max_body_bytes=0,
            external=False,
            external_authenticator=authenticator,
        )


def test_external_route_requires_authenticator(valid_manifest):
    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    with pytest.raises(ValueError, match="authenticator"):
        router.add(
            "GET",
            "/published",
            lambda request: ModuleHttpResponse.json(200, {}),
            permission="custom_reports.view",
            max_body_bytes=0,
            external=True,
        )


def test_external_preflight_does_not_invoke_authenticator(valid_manifest):
    from auto_check.app.module_system.routing import ExternalAuthDecision

    router = ModuleRouter(valid_manifest, default_permission_evaluator)
    calls = []

    def authenticator(candidate: str) -> ExternalAuthDecision:
        calls.append(candidate)
        return ExternalAuthDecision(configured=True, authenticated=True)

    router.add(
        "GET",
        "/published",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=authenticator,
    )

    router.external_preflight("GET", "/api/external/v1/custom-reports/published")
    assert calls == []


def test_external_preflight_unknown_path_returns_404(valid_manifest):
    from auto_check.app.module_system.routing import ExternalAuthDecision

    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    router.add(
        "GET",
        "/published",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=lambda c: ExternalAuthDecision(configured=True, authenticated=True),
    )

    assert router.external_preflight("GET", "/api/external/v1/custom-reports/unknown").status == 404


def test_external_preflight_method_mismatch_keeps_allow(valid_manifest):
    from auto_check.app.module_system.routing import ExternalAuthDecision

    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    router.add(
        "GET",
        "/published",
        lambda request: ModuleHttpResponse.json(200, {}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=lambda c: ExternalAuthDecision(configured=True, authenticated=True),
    )

    preflight = router.external_preflight("POST", "/api/external/v1/custom-reports/published")
    assert preflight.status == 405
    assert dict(preflight.headers).get("Allow") == "GET"


def test_different_external_routes_get_distinct_authenticators(valid_manifest):
    from auto_check.app.module_system.routing import ExternalAuthDecision

    router = ModuleRouter(valid_manifest, default_permission_evaluator)

    def auth_a(candidate: str) -> ExternalAuthDecision:
        return ExternalAuthDecision(configured=True, authenticated=False)

    def auth_b(candidate: str) -> ExternalAuthDecision:
        return ExternalAuthDecision(configured=True, authenticated=True)

    router.add(
        "GET",
        "/route-a",
        lambda request: ModuleHttpResponse.json(200, {"route": "a"}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=auth_a,
    )
    router.add(
        "GET",
        "/route-b",
        lambda request: ModuleHttpResponse.json(200, {"route": "b"}),
        permission="custom_reports.view",
        max_body_bytes=0,
        external=True,
        external_authenticator=auth_b,
    )

    preflight_a = router.external_preflight("GET", "/api/external/v1/custom-reports/route-a")
    preflight_b = router.external_preflight("GET", "/api/external/v1/custom-reports/route-b")
    assert preflight_a.external_authenticator is auth_a
    assert preflight_b.external_authenticator is auth_b
