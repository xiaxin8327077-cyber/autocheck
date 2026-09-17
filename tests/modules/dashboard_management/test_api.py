from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from importlib import resources

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from auto_check.app.module_system.contracts import ModuleHttpResponse, ModuleManifest, ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ExternalAuthDecision, ModuleRouter


class _AccessDatabase:
    def __init__(self) -> None:
        self._engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    @contextmanager
    def connect(self):
        with self._engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self):
        with self._engine.begin() as connection:
            yield connection


def _real_access_service(*, enabled: bool = False, allowed_ips=()):
    """Build a real whitelist service over an isolated in-memory database."""
    from auto_check.modules.dashboard_management.external_api_access import (
        METADATA,
        DashboardExternalApiAccessService,
    )

    database = _AccessDatabase()
    METADATA.create_all(database._engine)
    service = DashboardExternalApiAccessService(
        database,
        utc_now=lambda: datetime(2026, 9, 17, 10, 20, 30),
    )
    if enabled or allowed_ips:
        service.update(enabled=enabled, allowed_ips=list(allowed_ips), operator="admin")
    return service


def _manifest():
    return ModuleManifest.from_mapping(
        json.loads(resources.files("auto_check.modules.dashboard_management").joinpath("manifest.json").read_text(encoding="utf-8"))
    )


class Service:
    def catalog(self, board_code, current_user):
        return {
            "boards": [{"code": "report_submission", "name": "报送", "display_order": 10}],
            "board": {"code": board_code, "name": "报送", "display_order": 10},
            "regions": [],
        }

    def create_region(self, board_code, payload, current_user):
        return {"id": 1, "board_code": board_code, "row_version": 1}

    def preview_board_data(self, board_code, current_user):
        return self.preview_external_board_data(board_code)

    def preview_external_board_data(self, board_code):
        from auto_check.modules.dashboard_management.validator import NotFoundError

        if board_code not in {"report_submission", "reporting_process"}:
            raise NotFoundError("外部看板接口不存在")
        return {
            "status": "partial",
            "generated_at": "2026-09-15T09:30:00",
            "data_year": 2026,
            "board": {"code": board_code, "name": "报送"},
            "regions": [
                {
                    "code": "sample",
                    "status": "error",
                    "error": {"code": "internal_error", "message": "数据读取失败"},
                }
            ],
        }

    def update_region(self, region_id, payload, current_user):
        return {"id": region_id, "row_version": 2}

    def delete_region(self, region_id, payload, current_user):
        return {"id": region_id, "deleted": True}

    def create_field(self, region_id, payload, current_user):
        return {"id": 2, "region_id": region_id, "row_version": 1}

    def update_field(self, field_id, payload, current_user):
        return {"id": field_id, "row_version": 2}

    def list_datasources(self):
        return [{"id": "safe", "name": "安全数据源", "db_type": "postgresql"}]

    def preview_system_data(self, region_id, current_user):
        return {
            "columns": ["value"],
            "rows": [{"value": 1}],
            "source": {"feature": "报送导航", "database": "autocheck"},
        }


def _router(service=None, monitoring=None, access=None):
    from auto_check.modules.dashboard_management.api import register_routes

    router = ModuleRouter(_manifest(), default_permission_evaluator)
    access_service = access if access is not None else _real_access_service()
    register_routes(
        router,
        lambda: service or Service(),
        lambda: monitoring,
        lambda: None,
        lambda: access_service,
    )
    return router


def _router_with_monitoring(monitoring, access=None):
    from auto_check.modules.dashboard_management.api import register_routes

    router = ModuleRouter(_manifest(), default_permission_evaluator)
    access_service = access if access is not None else _real_access_service()
    register_routes(
        router,
        lambda: Service(),
        lambda: monitoring,
        lambda: None,
        lambda: access_service,
    )
    return router


def test_external_authenticator_resolves_credential_service_at_request_time():
    from auto_check.modules.dashboard_management.api import register_routes

    holder = {"service": None}
    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(
        router,
        lambda: Service(),
        lambda: None,
        lambda: holder["service"],
        lambda: _real_access_service(),
    )
    preflight = router.external_preflight(
        "GET",
        "/api/external/v1/dashboard-management/boards/report_submission/preview",
    )

    class CredentialService:
        @staticmethod
        def authenticate(candidate):
            return ExternalAuthDecision(configured=True, authenticated=candidate == "valid")

    holder["service"] = CredentialService()

    assert preflight is not None
    assert preflight.external_authenticator is not None
    assert preflight.external_authenticator("valid") == ExternalAuthDecision(
        configured=True,
        authenticated=True,
    )


def _dispatch(router, method, suffix, *, body=None, user=None, body_size=0, query=None):
    user = dict(user or {"role": "admin"})
    path = _manifest().api_prefix + suffix
    return router.dispatch(
        request=ModuleRequest(method, path, {}, query or {}, body, user),
        body_size=body_size,
    )


def _dispatch_external(router, method, suffix, *, client_ip="", server_ip=""):
    return router.dispatch_external(
        request=ModuleRequest(
            method,
            "/api/external/v1/dashboard-management" + suffix,
            {},
            {},
            None,
            {},
            client_ip=client_ip,
            server_ip=server_ip,
        )
    )


def test_api_registers_exact_routes_with_view_manage_permissions_and_body_limit():
    router = _router()
    viewer = {"role": "user", "capabilities": ["sys.dashboard_management"]}
    manager = {"role": "user", "capabilities": ["sys.dashboard_management.manage"]}

    assert _dispatch(router, "GET", "/boards", user=viewer).status == 200
    assert _dispatch(router, "GET", "/boards/report_submission/catalog", user=viewer).status == 200
    board_preview = _dispatch(router, "GET", "/boards/report_submission/preview", user=viewer)
    assert board_preview.status == 200
    assert board_preview.body["data"]["board"]["code"] == "report_submission"
    screen = _dispatch(router, "GET", "/boards/report_submission/screen", user=viewer)
    assert screen.status == 200
    assert screen.content_type == "text/html; charset=utf-8"
    assert "金融监管报表报送大屏" in screen.wire_body.decode("utf-8")
    assert _dispatch(router, "GET", "/datasources", user=viewer).status == 200
    system_preview = _dispatch(
        router,
        "POST",
        "/regions/1/source/system-preview",
        body={},
        user={"role": "user", "capabilities": ["sys.dashboard_management.test_sql"]},
    )
    assert system_preview.status == 200
    assert system_preview.body["data"]["source"]["database"] == "autocheck"
    assert _dispatch(router, "POST", "/boards/report_submission/regions", body={}, user=viewer).status == 403
    assert _dispatch(router, "POST", "/boards/report_submission/regions", body={
        "name": "自定义区域", "shape": "list", "enabled": True, "display_order": 10, "description": "",
        "fields": [{"field_alias": "initial_value", "name": "初始字段", "value_type": "string", "nullable": False, "enabled": True, "display_order": 10, "description": ""}],
    }, user=manager).status == 201
    assert _dispatch(router, "PUT", "/regions/1", body={}, user=manager).status == 200
    deleted = _dispatch(router, "DELETE", "/regions/1", body={"row_version": 2}, user=manager)
    assert deleted.status == 200 and deleted.body["data"] == {"id": 1, "deleted": True}
    assert _dispatch(router, "POST", "/regions/1/fields", body={}, user=manager).status == 201
    assert _dispatch(router, "PUT", "/fields/2", body={}, user=manager).status == 200
    assert _dispatch(router, "POST", "/boards/report_submission/regions", body={}, body_size=64 * 1024 + 1).status == 413


def test_api_publishes_only_board_preview_with_stable_external_envelope():
    router = _router()

    response = _dispatch_external(
        router, "GET", "/boards/report_submission/preview"
    )

    assert response.status == 200
    assert response.body["status"] == "partial"
    assert response.body["generated_at"] == "2026-09-15T09:30:00"
    assert response.body["data"]["data_year"] == 2026
    assert response.body["data"]["board"]["code"] == "report_submission"
    assert response.body["data"]["regions"][0]["status"] == "error"
    assert response.body["meta"]["request_id"].startswith("req-")
    assert _dispatch_external(router, "GET", "/boards") is None
    assert _dispatch_external(router, "GET", "/datasources") is None


def test_external_board_preview_returns_404_for_unknown_board_code():
    response = _dispatch_external(
        _router(), "GET", "/boards/unknown_board/preview"
    )

    # Unknown board codes no longer match any exact external route.
    assert response is None


def test_internal_and_external_board_preview_publish_the_same_business_payload():
    router = _router()
    internal = _dispatch(router, "GET", "/boards/report_submission/preview")
    external = _dispatch_external(router, "GET", "/boards/report_submission/preview")

    assert internal.status == external.status == 200
    assert internal.body["status"] == external.body["status"]
    assert internal.body["generated_at"] == external.body["generated_at"]
    assert internal.body["data"] == external.body["data"]
    assert internal.body["data"]["data_year"] == 2026
    assert internal.body["meta"]["request_id"].startswith("req-")
    assert external.body["meta"]["request_id"].startswith("req-")


def test_external_preview_returns_403_before_board_query_when_ip_is_not_allowed():
    queried = []

    class Counting(Service):
        def preview_external_board_data(self, board_code):
            queried.append(board_code)
            return super().preview_external_board_data(board_code)

    monitoring = _FakeMonitoring()
    access = _real_access_service(enabled=True, allowed_ips=["192.168.1.10"])
    router = _router(Counting(), monitoring, access)

    denied = _dispatch_external(
        router,
        "GET",
        "/boards/report_submission/preview",
        client_ip="203.0.113.9",
        server_ip="10.0.0.1",
    )

    assert denied.status == 403
    assert denied.body["error"] == {
        "code": "ip_not_allowed",
        "message": "来源 IP 不在白名单中",
        "fields": {},
    }
    assert denied.body["meta"]["request_id"].startswith("req-")
    # 403 必须在调用 preview_external_board_data() 之前产生。
    assert queried == []
    # 403 已进入模块，因此写入调用监控。
    assert monitoring.calls[0][0] == "begin"
    assert monitoring.calls[1] == ("finish", 403)

    allowed = _dispatch_external(
        router,
        "GET",
        "/boards/report_submission/preview",
        client_ip="192.168.1.10",
        server_ip="10.0.0.1",
    )
    assert allowed.status == 200
    assert queried == ["report_submission"]


def test_both_fixed_external_endpoints_enforce_the_ip_whitelist():
    access = _real_access_service(enabled=True, allowed_ips=[])
    router = _router(access=access)

    for suffix in (
        "/boards/report_submission/preview",
        "/boards/reporting_process/preview",
    ):
        response = _dispatch_external(
            router, "GET", suffix, client_ip="203.0.113.9", server_ip="10.0.0.1"
        )
        assert response.status == 403
        assert response.body["error"]["code"] == "ip_not_allowed"


def test_external_preview_allows_loopback_and_matching_server_address():
    access = _real_access_service(enabled=True, allowed_ips=[])
    router = _router(access=access)

    loopback = _dispatch_external(
        router, "GET", "/boards/report_submission/preview", client_ip="127.0.0.1", server_ip="127.0.0.1"
    )
    same_host = _dispatch_external(
        router, "GET", "/boards/report_submission/preview", client_ip="192.168.1.8", server_ip="192.168.1.8"
    )
    other_host = _dispatch_external(
        router, "GET", "/boards/report_submission/preview", client_ip="192.168.1.8", server_ip="192.168.1.9"
    )

    assert loopback.status == same_host.status == 200
    assert other_host.status == 403


def test_internal_preview_is_not_affected_by_the_ip_whitelist():
    access = _real_access_service(enabled=True, allowed_ips=[])
    router = _router(access=access)

    response = _dispatch(router, "GET", "/boards/report_submission/preview")

    assert response.status == 200
    assert response.body["data"]["data_year"] == 2026


def test_external_preview_returns_503_when_access_policy_check_fails():
    class BrokenAccess:
        @staticmethod
        def is_allowed(client_ip, server_ip):
            raise RuntimeError("policy table unavailable")

        @staticmethod
        def status():
            raise RuntimeError("policy table unavailable")

    monitoring = _FakeMonitoring()
    router = _router(monitoring=monitoring, access=BrokenAccess())

    response = _dispatch_external(
        router,
        "GET",
        "/boards/report_submission/preview",
        client_ip="203.0.113.9",
        server_ip="10.0.0.1",
    )

    assert response.status == 503
    assert response.body["error"] == {
        "code": "access_policy_unavailable",
        "message": "外部接口访问策略暂时不可用",
        "fields": {},
    }
    assert "policy table unavailable" not in str(response.body)
    assert monitoring.calls[1] == ("finish", 503)


def test_external_preview_returns_503_when_access_service_is_missing():
    from auto_check.modules.dashboard_management.api import register_routes

    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(router, lambda: Service(), lambda: None, lambda: None, lambda: None)

    response = _dispatch_external(
        router, "GET", "/boards/report_submission/preview", client_ip="203.0.113.9"
    )

    assert response.status == 503
    assert response.body["error"]["code"] == "access_policy_unavailable"


def test_access_policy_failure_log_does_not_include_exception_details(caplog):
    class BrokenAccess:
        @staticmethod
        def is_allowed(client_ip, server_ip):
            raise RuntimeError(
                "postgresql://secret@host/auto_check DROP TABLE dashboard_management_external_api_access_policies"
            )

    with caplog.at_level("WARNING"):
        response = _dispatch_external(
            _router(access=BrokenAccess()),
            "GET",
            "/boards/report_submission/preview",
            client_ip="203.0.113.9",
        )

    assert response.status == 503
    assert "secret" not in caplog.text
    assert "DROP TABLE" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "secret" not in str(response.body)


def test_ip_whitelist_endpoints_require_the_dedicated_capability():
    router = _router()
    authorized = {
        "role": "user",
        "capabilities": ["sys.dashboard_management.external_api_ip_whitelist_manage"],
    }
    other_capability = {
        "role": "user",
        "capabilities": ["sys.dashboard_management.external_api_monitor"],
    }

    assert _dispatch(router, "GET", "/external-api/ip-whitelist", user=authorized).status == 200
    assert _dispatch(router, "GET", "/external-api/ip-whitelist", user=other_capability).status == 403
    assert _dispatch(
        router,
        "PUT",
        "/external-api/ip-whitelist",
        body={"enabled": False, "allowed_ips": []},
        user=other_capability,
    ).status == 403


def test_ip_whitelist_get_and_put_return_normalized_configuration():
    access = _real_access_service()
    router = _router(access=access)
    admin = {"role": "admin", "username": "whitelist-admin"}

    empty = _dispatch(router, "GET", "/external-api/ip-whitelist", user=admin)
    assert empty.status == 200
    assert empty.body["data"] == {"enabled": False, "allowed_ips": [], "updated_at": None}
    assert empty.body["meta"]["request_id"].startswith("req-")

    saved = _dispatch(
        router,
        "PUT",
        "/external-api/ip-whitelist",
        body={
            "enabled": True,
            "allowed_ips": [
                " 192.168.1.10 ",
                "2001:0db8::0010",
                "::ffff:10.0.0.1",
                "192.168.1.10",
                "",
            ],
        },
        user=admin,
    )
    assert saved.status == 200
    assert saved.body["data"] == {
        "enabled": True,
        "allowed_ips": ["192.168.1.10", "2001:db8::10", "10.0.0.1"],
        "updated_at": "2026-09-17T10:20:30",
    }

    fetched = _dispatch(router, "GET", "/external-api/ip-whitelist", user=admin)
    assert fetched.body["data"] == saved.body["data"]


def test_ip_whitelist_put_rejects_missing_unknown_and_invalid_payloads():
    router = _router(access=_real_access_service())
    admin = {"role": "admin"}

    missing = _dispatch(
        router, "PUT", "/external-api/ip-whitelist", body={"enabled": True}, user=admin
    )
    assert missing.status == 400
    assert set(missing.body["error"]["fields"]) == {"allowed_ips"}

    unknown = _dispatch(
        router,
        "PUT",
        "/external-api/ip-whitelist",
        body={"enabled": True, "allowed_ips": [], "extra": 1},
        user=admin,
    )
    assert unknown.status == 400

    scalar = _dispatch(router, "PUT", "/external-api/ip-whitelist", body=[], user=admin)
    assert scalar.status == 400

    bad_enabled = _dispatch(
        router,
        "PUT",
        "/external-api/ip-whitelist",
        body={"enabled": 1, "allowed_ips": []},
        user=admin,
    )
    assert bad_enabled.status == 400
    assert set(bad_enabled.body["error"]["fields"]) == {"enabled"}

    bad_ip = _dispatch(
        router,
        "PUT",
        "/external-api/ip-whitelist",
        body={"enabled": True, "allowed_ips": ["192.168.1.0/24"]},
        user=admin,
    )
    assert bad_ip.status == 400
    assert set(bad_ip.body["error"]["fields"]) == {"allowed_ips"}
    assert "192.168.1.0/24" not in str(bad_ip.body["error"]["fields"]["allowed_ips"])

    too_large = _dispatch(
        router,
        "PUT",
        "/external-api/ip-whitelist",
        body={"enabled": True, "allowed_ips": []},
        user=admin,
        body_size=8192 + 1,
    )
    assert too_large.status == 413


def test_monitor_summary_reports_ip_whitelist_state():
    access = _real_access_service(enabled=True, allowed_ips=["192.168.1.10", "2001:db8::10"])
    router = _router(monitoring=_FakeMonitoring(), access=access)

    response = _dispatch(router, "GET", "/external-api/monitor/summary")

    assert response.status == 200
    assert response.body["data"]["ip_whitelist_enabled"] is True
    assert response.body["data"]["ip_whitelist_count"] == 2


def test_monitor_summary_returns_503_when_whitelist_status_is_unavailable():
    class BrokenAccess:
        @staticmethod
        def status():
            raise RuntimeError("policy table unavailable")

        @staticmethod
        def is_allowed(client_ip, server_ip):
            raise RuntimeError("policy table unavailable")

    router = _router(monitoring=_FakeMonitoring(), access=BrokenAccess())

    response = _dispatch(router, "GET", "/external-api/monitor/summary")

    assert response.status == 503
    assert response.body["error"]["code"] == "service_unavailable"
    assert "policy table unavailable" not in str(response.body)


def test_api_maps_400_401_409_and_500_to_desensitized_domain_responses():
    from auto_check.modules.dashboard_management.validator import ConflictError, DomainError, ValidationError

    class Invalid(Service):
        def create_region(self, board_code, payload, current_user):
            raise ValidationError("字段无效", fields={"name": "字段无效"})

    response = _dispatch(_router(Invalid()), "POST", "/boards/report_submission/regions", body={})
    assert response.status == 400
    assert response.body["error"] == {"code": "invalid_request", "message": "字段无效", "fields": {"name": "字段无效"}}

    class InitialFieldsRequired(Service):
        def create_region(self, board_code, payload, current_user):
            raise ValidationError("至少需要一个启用字段", fields={"fields": "至少需要一个启用字段"})

    response = _dispatch(_router(InitialFieldsRequired()), "POST", "/boards/report_submission/regions", body={})
    assert response.status == 400
    assert response.body["error"]["fields"] == {"fields": "至少需要一个启用字段"}

    class DuplicateInitialField(Service):
        def create_region(self, board_code, payload, current_user):
            raise ValidationError("首批字段别名不能重复", fields={"fields": "首批字段别名不能重复"})

    response = _dispatch(_router(DuplicateInitialField()), "POST", "/boards/report_submission/regions", body={"fields": []})
    assert response.status == 400
    assert response.body["error"]["fields"] == {"fields": "首批字段别名不能重复"}

    class Unauthorized(DomainError):
        status = 401
        code = "authentication_required"
        message = "请先登录"

    class LoginRequired(Service):
        def catalog(self, board_code, current_user):
            raise Unauthorized()

    assert _dispatch(_router(LoginRequired()), "GET", "/boards/report_submission/catalog").status == 401

    class Conflict(Service):
        def update_region(self, region_id, payload, current_user):
            raise ConflictError()

    assert _dispatch(_router(Conflict()), "PUT", "/regions/1", body={}).status == 409

    class Broken(Service):
        def list_datasources(self):
            raise RuntimeError("postgresql://secret@host:5432/db DROP TABLE C:/secret")

    response = _dispatch(_router(Broken()), "GET", "/datasources")
    assert response.status == 500
    assert "secret" not in str(response.body)
    assert response.body["meta"]["error_id"]


def test_datasource_response_only_contains_safe_summary_fields():
    response = _dispatch(_router(), "GET", "/datasources")

    assert response.status == 200
    assert response.body["data"] == [{"id": "safe", "name": "安全数据源", "db_type": "postgresql"}]
    rendered = str(response.body)
    assert "host" not in rendered and "password" not in rendered


class _FakeMonitoring:
    def __init__(self):
        self.calls = []
        self.begin_error = None
        self.finish_error = None

    def begin_call(self, board_code, caller_ip, request_id):
        self.calls.append(("begin", board_code, caller_ip, request_id))
        if self.begin_error:
            raise self.begin_error
        return object()

    def finish_call(self, trace, response):
        self.calls.append(("finish", response.status))
        if self.finish_error:
            raise self.finish_error

    def monitor_summary(self, credential_status=None, access_status=None):
        return {
            "enabled": True,
            "token_configured": True,
            "token_source": "none",
            "ip_whitelist_enabled": bool((access_status or {}).get("enabled", False)),
            "ip_whitelist_count": int((access_status or {}).get("count", 0) or 0),
        }

    def list_calls(self, query):
        return {"items": [], "page": 1, "page_size": 10, "total": 0, "total_pages": 1}


def test_external_preview_records_call_with_client_ip_and_request_id():
    monitoring = _FakeMonitoring()
    router = _router_with_monitoring(monitoring)

    response = router.dispatch_external(
        ModuleRequest(
            "GET",
            "/api/external/v1/dashboard-management/boards/report_submission/preview",
            {},
            {},
            None,
            {},
            client_ip="198.51.100.4",
        )
    )

    assert response.status == 200
    assert len(monitoring.calls) == 2
    assert monitoring.calls[0] == ("begin", "report_submission", "198.51.100.4", response.body["meta"]["request_id"])
    assert monitoring.calls[1][0] == "finish"
    assert monitoring.calls[1][1] == 200


def test_internal_preview_does_not_record_call():
    monitoring = _FakeMonitoring()
    router = _router_with_monitoring(monitoring)

    response = _dispatch(router, "GET", "/boards/report_submission/preview")

    assert response.status == 200
    assert response.body["data"]["data_year"] == 2026
    assert monitoring.calls == []


def test_external_preview_records_404_and_500_exactly_once():
    monitoring = _FakeMonitoring()
    router = _router_with_monitoring(monitoring)

    not_found = router.dispatch_external(
        ModuleRequest("GET", "/api/external/v1/dashboard-management/boards/unknown/preview", {}, {}, None, {})
    )
    # Unknown board codes no longer match any external route.
    assert not_found is None
    # No monitoring calls are recorded for unmatched external paths.
    assert monitoring.calls == []


def test_external_preview_finish_call_error_does_not_change_response():
    monitoring = _FakeMonitoring()
    monitoring.finish_error = RuntimeError("database unavailable")
    router = _router_with_monitoring(monitoring)

    response = router.dispatch_external(
        ModuleRequest(
            "GET",
            "/api/external/v1/dashboard-management/boards/report_submission/preview",
            {},
            {},
            None,
            {},
            client_ip="198.51.100.4",
        )
    )

    assert response.status == 200
    assert response.body["status"] == "partial"
    assert len(monitoring.calls) == 2


def test_external_preview_begin_call_error_does_not_change_response():
    monitoring = _FakeMonitoring()
    monitoring.begin_error = RuntimeError("database unavailable")
    router = _router_with_monitoring(monitoring)

    response = router.dispatch_external(
        ModuleRequest(
            "GET",
            "/api/external/v1/dashboard-management/boards/report_submission/preview",
            {},
            {},
            None,
            {},
            client_ip="unknown",
        )
    )

    assert response.status == 200
    assert response.body["status"] == "partial"
    assert monitoring.calls[0][0] == "begin"


def test_monitor_apis_require_permission_and_return_403_for_unauthorized():
    from auto_check.modules.dashboard_management.api import register_routes

    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(
        router,
        lambda: Service(),
        lambda: _FakeMonitoring(),
        lambda: None,
        lambda: _real_access_service(),
    )

    authorized = {"role": "user", "capabilities": ["sys.dashboard_management.external_api_monitor"]}
    unauthorized = {"role": "user", "capabilities": []}

    assert _dispatch(router, "GET", "/external-api/monitor/summary", user=authorized).status == 200
    assert _dispatch(router, "GET", "/external-api/monitor/calls", user=authorized).status == 200
    assert _dispatch(router, "GET", "/external-api/monitor/summary", user=unauthorized).status == 403
    assert _dispatch(router, "GET", "/external-api/monitor/calls", user=unauthorized).status == 403


def test_token_generation_requires_mapped_capability_and_strict_empty_object():
    from auto_check.modules.dashboard_management.api import register_routes

    class Credentials:
        calls = 0

        def generate(self, operator):
            self.calls += 1
            return type(
                "Generated",
                (),
                {
                    "token": "generated-test-token",
                    "generated_at": "2026-09-16T12:00:00",
                    "rotated": False,
                },
            )()

    credentials = Credentials()
    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(
        router,
        lambda: Service(),
        lambda: _FakeMonitoring(),
        lambda: credentials,
        lambda: _real_access_service(),
    )
    authorized = {
        "role": "user",
        "username": "token-manager",
        "capabilities": ["sys.dashboard_management.external_api_token_manage"],
    }

    denied = _dispatch(
        router,
        "POST",
        "/external-api/token/generate",
        body={},
        user={"role": "user", "capabilities": []},
    )
    invalid_mapping = _dispatch(
        router,
        "POST",
        "/external-api/token/generate",
        body={"unexpected": True},
        user=authorized,
    )
    invalid_scalar = _dispatch(
        router,
        "POST",
        "/external-api/token/generate",
        body=[],
        user=authorized,
    )
    generated = _dispatch(
        router,
        "POST",
        "/external-api/token/generate",
        body={},
        user=authorized,
    )

    assert denied.status == 403
    assert invalid_mapping.status == invalid_scalar.status == 400
    assert credentials.calls == 1
    assert generated.status == 200
    assert generated.body["token"] == "generated-test-token"


def test_token_generation_failure_log_does_not_include_exception_details(caplog):
    from auto_check.modules.dashboard_management.api import register_routes

    class FailingCredentials:
        @staticmethod
        def generate(operator):
            raise RuntimeError("private-token-digest-material")

    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(
        router,
        lambda: Service(),
        lambda: _FakeMonitoring(),
        lambda: FailingCredentials(),
        lambda: _real_access_service(),
    )

    with caplog.at_level("WARNING"):
        response = _dispatch(
            router,
            "POST",
            "/external-api/token/generate",
            body={},
        )

    assert response.status == 500
    assert "private-token-digest-material" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_monitor_apis_validate_query_parameters():
    import logging
    from auto_check.modules.dashboard_management.api import register_routes
    from auto_check.modules.dashboard_management.external_api_monitoring import ExternalApiMonitoringService

    class _FakeStatusFacade:
        def get_status(self):
            from auto_check.app.external_api import ExternalApiStatusSnapshot
            return ExternalApiStatusSnapshot(token_configured=True)

    class _FakeStore:
        def record_and_cleanup(self, record, cutoff):
            pass
        def summary(self, since, cutoff):
            return {"total": 0, "success": 0, "partial": 0, "failed": 0, "average_duration_ms": 0, "last_called_at": None, "last_success_at": None}
        def list_calls(self, query, cutoff):
            return {"items": [], "page": 1, "page_size": 10, "total": 0, "total_pages": 1}

    router = ModuleRouter(_manifest(), default_permission_evaluator)
    service = ExternalApiMonitoringService(
        _FakeStore(),
        status_facade=_FakeStatusFacade(),
        logger=logging.getLogger("test"),
    )
    register_routes(router, lambda: Service(), lambda: service, lambda: None, lambda: _real_access_service())
    admin = {"role": "admin"}

    assert _dispatch(router, "GET", "/external-api/monitor/calls", query={"page": "0"}, user=admin).status == 400
    assert _dispatch(router, "GET", "/external-api/monitor/calls", query={"page_size": "0"}, user=admin).status == 400
    assert _dispatch(router, "GET", "/external-api/monitor/calls", query={"page_size": "101"}, user=admin).status == 400
    assert _dispatch(router, "GET", "/external-api/monitor/calls", query={"board_code": "unknown"}, user=admin).status == 400
    assert _dispatch(router, "GET", "/external-api/monitor/calls", query={"result_status": "unknown"}, user=admin).status == 400
    assert _dispatch(router, "GET", "/external-api/monitor/calls", query={"caller_ip": "not-an-ip"}, user=admin).status == 400
    assert _dispatch(router, "GET", "/external-api/monitor/calls", query={"started_at": "not-a-date"}, user=admin).status == 400
    assert _dispatch(router, "GET", "/external-api/monitor/calls", query={"ended_at": "not-a-date"}, user=admin).status == 400


def test_monitor_apis_wrap_real_service_results_in_internal_response_envelope():
    import logging
    from auto_check.modules.dashboard_management.api import register_routes
    from auto_check.modules.dashboard_management.external_api_monitoring import ExternalApiMonitoringService

    class _FakeStatusFacade:
        def get_status(self):
            from auto_check.app.external_api import ExternalApiStatusSnapshot
            return ExternalApiStatusSnapshot(token_configured=True)

    class _FakeStore:
        def summary(self, since, cutoff):
            return {"total": 1, "success": 1, "partial": 0, "failed": 0, "average_duration_ms": 7, "last_called_at": None, "last_success_at": None}

        def list_calls(self, query, cutoff):
            return {"items": [], "page": 1, "page_size": 10, "total": 0, "total_pages": 1}

    service = ExternalApiMonitoringService(
        _FakeStore(),
        status_facade=_FakeStatusFacade(),
        logger=logging.getLogger("test"),
    )
    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(router, lambda: Service(), lambda: service, lambda: None, lambda: _real_access_service())

    summary = _dispatch(router, "GET", "/external-api/monitor/summary")
    calls = _dispatch(router, "GET", "/external-api/monitor/calls")

    assert summary.status == 200
    assert summary.body["data"]["last_24_hours"]["total"] == 1
    assert summary.body["meta"]["request_id"].startswith("req-")
    assert calls.status == 200
    assert calls.body["data"]["items"] == []
    assert calls.body["meta"]["request_id"].startswith("req-")


def test_monitor_summary_returns_safe_503_when_status_service_is_unavailable():
    class _UnavailableMonitoring(_FakeMonitoring):
        def monitor_summary(self):
            raise RuntimeError("secret backend details")

    response = _dispatch(
        _router_with_monitoring(_UnavailableMonitoring()),
        "GET",
        "/external-api/monitor/summary",
    )

    assert response.status == 503
    assert response.body["error"]["code"] == "service_unavailable"
    assert "secret" not in str(response.body)
    assert response.body["meta"]["request_id"].startswith("req-")
