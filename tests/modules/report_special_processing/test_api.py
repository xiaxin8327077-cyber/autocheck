from auto_check.app.module_system.contracts import ModuleManifest, ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter


def _manifest():
    import json
    from importlib import resources
    return ModuleManifest.from_mapping(json.loads(resources.files("auto_check.modules.report_special_processing").joinpath("manifest.json").read_text(encoding="utf-8")))


class Service:
    def catalog(self, user=None): return {"report_processes": [], "users": [], "statuses": [], "limits": {}, "workflow": {}, "capabilities": {}}
    def list_records(self, query, user): return {"items": [], "page": 1, "page_size": 20, "total": 0, "total_pages": 0}
    def create(self, body, user, request_id): return {"id": 1, "row_version": 1}
    def get(self, record_id, user): return {"id": record_id}
    def update(self, record_id, body, user, request_id): return {"id": record_id, "row_version": 2}
    def change_status(self, record_id, body, user, request_id): return {"id": record_id}
    def void(self, record_id, body, user, request_id): return {"id": record_id}
    def delete(self, record_id, body, user, request_id): return {"id": record_id, "deleted": True}
    def reopen(self, record_id, body, user, request_id): return {"id": record_id}
    def audit(self, record_id, query): return {"items": [], "page": 1, "page_size": 20, "total": 0, "total_pages": 0}
    def summary(self, query): return {"total": 0}


def _router(service=None):
    from auto_check.modules.report_special_processing.api import register_routes
    router = ModuleRouter(_manifest(), default_permission_evaluator)
    register_routes(router, lambda: service or Service())
    return router


def _dispatch(router, method, suffix, *, body=None, user=None, body_size=0):
    return router.dispatch(request=ModuleRequest(method, _manifest().api_prefix + suffix, {}, {}, body, user or {}), body_size=body_size)


def test_api_registers_contract_routes_and_enforces_body_limit():
    router = _router()
    assert _dispatch(router, "GET", "/catalog", user={"role": "user"}).status == 200
    assert _dispatch(router, "POST", "/records", body={}, user={"role": "user"}).status == 201
    assert _dispatch(router, "POST", "/records", body={}, user={"role": "user"}, body_size=1048577).status == 413
    assert _dispatch(router, "DELETE", "/records/1", body={"row_version": 1}, user={"role": "admin"}).status == 200


def test_api_void_delete_reopen_use_view_permission_service_enforces():
    """作废/删除/重开路由走 view 权限，细粒度由模块 service 按 rsp.* 判定。"""
    router = _router()
    assert _dispatch(router, "POST", "/records/1/void", body={}, user={"role": "user"}).status == 200
    assert _dispatch(router, "DELETE", "/records/1", body={"row_version": 1}, user={"role": "user"}).status == 200
    assert _dispatch(router, "POST", "/records/1/reopen", body={}, user={"role": "admin"}).status == 200
    assert _dispatch(router, "DELETE", "/records/1", body={"row_version": 1}, user={"role": "admin"}).status == 200


def test_api_maps_domain_and_unknown_errors_without_leaking_details():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    class Invalid(Service):
        def create(self, body, user, request_id): raise ValidationError("invalid_request", "无效请求")
    response = _dispatch(_router(Invalid()), "POST", "/records", body={}, user={"role": "user"})
    assert response.status == 400 and response.body["error"]["code"] == "invalid_request"
    class Broken(Service):
        def catalog(self, user=None): raise RuntimeError("mysql://secret script DROP TABLE path C:/secret")
    response = _dispatch(_router(Broken()), "GET", "/catalog", user={"role": "user"})
    assert response.status == 500
    rendered = str(response.body)
    assert "secret" not in rendered and "DROP TABLE" not in rendered
    assert response.body["meta"]["error_id"]
