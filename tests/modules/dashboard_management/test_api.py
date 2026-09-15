from __future__ import annotations

import json
from importlib import resources

from auto_check.app.module_system.contracts import ModuleManifest, ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter


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
        return {"board": {"code": board_code, "name": "报送"}, "regions": []}

    def preview_external_board_data(self, board_code):
        from auto_check.modules.dashboard_management.validator import NotFoundError

        if board_code not in {"report_submission", "reporting_process"}:
            raise NotFoundError("外部看板接口不存在")
        return {
            "status": "partial",
            "generated_at": "2026-09-15T09:30:00",
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


def _router(service=None):
    from auto_check.modules.dashboard_management.api import register_routes

    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(router, lambda: service or Service())
    return router


def _dispatch(router, method, suffix, *, body=None, user=None, body_size=0):
    user = dict(user or {"role": "admin"})
    return router.dispatch(
        request=ModuleRequest(method, _manifest().api_prefix + suffix, {}, {}, body, user),
        body_size=body_size,
    )


def _dispatch_external(router, method, suffix):
    return router.dispatch_external(
        request=ModuleRequest(
            method,
            "/api/external/v1/dashboard-management" + suffix,
            {},
            {},
            None,
            {},
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
    assert response.body["data"]["board"]["code"] == "report_submission"
    assert response.body["data"]["regions"][0]["status"] == "error"
    assert response.body["meta"]["request_id"].startswith("req-")
    assert _dispatch_external(router, "GET", "/boards") is None
    assert _dispatch_external(router, "GET", "/datasources") is None


def test_external_board_preview_returns_404_for_unknown_board_code():
    response = _dispatch_external(
        _router(), "GET", "/boards/unknown_board/preview"
    )

    assert response.status == 404
    assert response.body["error"]["code"] == "resource_not_found"
    assert response.body["meta"]["request_id"].startswith("req-")


def test_internal_board_preview_response_contract_is_unchanged():
    response = _dispatch(
        _router(), "GET", "/boards/report_submission/preview"
    )

    assert set(response.body) == {"data", "meta"}
    assert response.body["data"] == {
        "board": {"code": "report_submission", "name": "报送"},
        "regions": [],
    }


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
