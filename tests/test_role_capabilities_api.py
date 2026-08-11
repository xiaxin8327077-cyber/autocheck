"""角色能力矩阵 API + 会话能力下发测试。

直接调用 ``ApiRouter.handle`` 注入 ``current_user``，避免 HTTP/RSA 开销。
"""

import time

from auto_check.app.capabilities import (
    CAPABILITY_DEFINITIONS,
    LOCKED_ROLE,
    ROLE_DEFINITIONS,
    has_capability,
    merge_matrix,
)
from auto_check.app.security import AuthSession
from auto_check.app.server import ApiRouter, _session_user
from mysql_config_test_support import MemoryApplicationDatabase


class _FakeReportNavigationService:
    def dashboard(self, *, period, current_user):
        return {"period": period, "report_month": "2026-07", "cards": [], "processes": []}

    def manual_refresh(self, *, current_user):
        return {
            "status": "completed",
            "cooldown_seconds": 300,
            "retry_after_seconds": 300,
            "error_message": "",
        }


class _FakeHistoryStore:
    def __init__(self):
        self.deleted = []

    def delete_run(self, history_id):
        self.deleted.append(history_id)
        return True


def _admin():
    return {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}


def _user():
    return {"id": "u2", "username": "user", "display_name": "用户", "role": "user"}


def _router(tmp_path):
    service = _FakeReportNavigationService()
    router = ApiRouter(
        config_path=tmp_path / "config.json",
        application_database=MemoryApplicationDatabase(),
        report_navigation_service=service,
        start_field_mapping_auto_refresh=False,
    )
    router.history_store = _FakeHistoryStore()
    return router, service


def _session(role="user", username="user", user_id="u2", display_name="用户"):
    return AuthSession(
        session_id="s1",
        csrf_token="csrf",
        expires_at=time.time() + 3600,
        last_activity_at=time.time(),
        user_id=user_id,
        username=username,
        display_name=display_name,
        role=role,
    )


# --- GET /api/role-capabilities ---


def test_admin_can_get_role_capabilities(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("GET", "/api/role-capabilities", None, current_user=_admin())
    assert status == 200
    assert payload["matrix"] == merge_matrix(None)
    assert payload["roles"] == ROLE_DEFINITIONS
    assert payload["capabilities"] == CAPABILITY_DEFINITIONS
    assert payload["locked_roles"] == [LOCKED_ROLE]


def test_standard_user_get_role_capabilities_returns_403(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("GET", "/api/role-capabilities", None, current_user=_user())
    assert (status, payload["error"]) == (403, "admin role required")


# --- PUT /api/role-capabilities ---


def test_admin_put_role_capabilities_updates_matrix(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle(
        "PUT",
        "/api/role-capabilities",
        {"matrix": {"user": {"menu.tools": False}}},
        current_user=_admin(),
    )
    assert status == 200
    assert has_capability("user", "menu.tools", payload["matrix"]) is False
    # 再次 GET 验证持久化
    status, payload = router.handle("GET", "/api/role-capabilities", None, current_user=_admin())
    assert status == 200
    assert has_capability("user", "menu.tools", payload["matrix"]) is False


def test_put_role_capabilities_rejects_granting_admin_only_to_user(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle(
        "PUT",
        "/api/role-capabilities",
        {"matrix": {"user": {"sys.users": True}}},
        current_user=_admin(),
    )
    assert status == 400
    assert "admin-only" in payload["error"]


def test_put_role_capabilities_rejects_admin_column_change(tmp_path):
    router, _ = _router(tmp_path)
    incoming = merge_matrix(None)
    incoming["admin"]["history.delete"] = False
    status, payload = router.handle(
        "PUT",
        "/api/role-capabilities",
        {"matrix": incoming},
        current_user=_admin(),
    )
    assert status == 400
    assert "admin" in payload["error"].lower()


def test_standard_user_put_role_capabilities_returns_403(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle(
        "PUT",
        "/api/role-capabilities",
        {"matrix": {"user": {"sys.users": True}}},
        current_user=_user(),
    )
    assert (status, payload["error"]) == (403, "admin role required")


def test_put_role_capabilities_requires_matrix_body(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("PUT", "/api/role-capabilities", {}, current_user=_admin())
    assert (status, payload["error"]) == (400, "matrix or remarks is required")


# --- DELETE /api/history capability ---


def test_history_delete_requires_capability_default_user_denied(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("DELETE", "/api/history", {"id": "r1"}, current_user=_user())
    assert (status, payload["error"]) == (403, "admin role required")
    assert router.history_store.deleted == []


def test_admin_can_delete_history(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("DELETE", "/api/history", {"id": "r1"}, current_user=_admin())
    assert status == 200
    assert payload["ok"] is True
    assert router.history_store.deleted == ["r1"]


def test_history_delete_grantable_to_user_then_allows_delete(tmp_path):
    # history.delete 不再是管理员专属，可授予其他角色
    router, _ = _router(tmp_path)
    status, _ = router.handle(
        "PUT",
        "/api/role-capabilities",
        {"matrix": {"user": {"history.delete": True}}},
        current_user=_admin(),
    )
    assert status == 200
    status, payload = router.handle("DELETE", "/api/history", {"id": "r2"}, current_user=_user())
    assert status == 200
    assert payload["ok"] is True
    assert router.history_store.deleted == ["r2"]


def test_history_delete_missing_id_returns_400(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("DELETE", "/api/history", {}, current_user=_admin())
    assert (status, payload["error"]) == (400, "id is required")


# --- 会话能力下发 ---


def test_session_user_function_includes_capabilities():
    payload = _session_user(_session(), capabilities=["rsp.confirm", "rsp.view"])
    assert payload["capabilities"] == ["rsp.confirm", "rsp.view"]


def test_session_user_function_backward_compatible_without_capabilities():
    payload = _session_user(_session())
    assert "capabilities" not in payload


def test_router_session_payload_reads_matrix_for_custom_role(tmp_path):
    router, _ = _router(tmp_path)
    status, created = router.handle(
        "POST",
        "/api/role-definitions",
        {"display_name": "审计员"},
        current_user=_admin(),
    )
    assert status == 201
    code = created["role_definition"]["role_code"]
    payload = router.session_user_payload(
        _session(role=code, username="auditor", display_name="审计员")
    )
    assert payload["role"] == code
    # 自定义角色默认等同 user 标准档
    assert "rsp.create" in payload["capabilities"]
    assert "rsp.confirm" not in payload["capabilities"]


def test_router_session_payload_reads_matrix_for_admin(tmp_path):
    router, _ = _router(tmp_path)
    payload = router.session_user_payload(_session(role="admin", username="admin", display_name="管理员"))
    assert set(payload["capabilities"]) == set(CAPABILITY_DEFINITIONS)


def test_router_session_payload_reflects_matrix_change(tmp_path):
    router, _ = _router(tmp_path)
    status, created = router.handle(
        "POST",
        "/api/role-definitions",
        {"display_name": "审计员"},
        current_user=_admin(),
    )
    assert status == 201
    code = created["role_definition"]["role_code"]
    router.handle(
        "PUT",
        "/api/role-capabilities",
        {"matrix": {code: {"rsp.confirm": True}}},
        current_user=_admin(),
    )
    payload = router.session_user_payload(
        _session(role=code, username="auditor", display_name="审计员")
    )
    assert "rsp.confirm" in payload["capabilities"]


def test_get_role_capabilities_returns_remarks(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("GET", "/api/role-capabilities", None, current_user=_admin())
    assert status == 200
    assert "remarks" in payload
    assert payload["remarks"]["admin"]


def test_put_role_remarks_persists(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("PUT", "/api/role-capabilities", {"remarks": {"user": "持久备注"}}, current_user=_admin())
    assert status == 200
    assert payload["remarks"]["user"] == "持久备注"
    status, payload = router.handle("GET", "/api/role-capabilities", None, current_user=_admin())
    assert payload["remarks"]["user"] == "持久备注"


# --- role-definitions CRUD ---


def test_admin_create_role_definition(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("POST", "/api/role-definitions", {"display_name": "审计员", "remark": "自定义审计"}, current_user=_admin())
    assert status == 201
    rd = payload["role_definition"]
    assert rd["role_code"].startswith("custom_")
    assert rd["display_name"] == "审计员"
    # 新建角色默认矩阵等同 user 档
    assert has_capability(rd["role_code"], "menu.home", payload["matrix"]) is True
    assert has_capability(rd["role_code"], "sys.users", payload["matrix"]) is False


def test_create_role_definition_rejects_non_admin(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("POST", "/api/role-definitions", {"display_name": "x"}, current_user=_user())
    assert (status, payload["error"]) == (403, "admin role required")


def test_create_role_definition_requires_display_name(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("POST", "/api/role-definitions", {"display_name": "  "}, current_user=_admin())
    assert status == 400


def test_admin_update_role_definition(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("POST", "/api/role-definitions", {"display_name": "原名"}, current_user=_admin())
    code = payload["role_definition"]["role_code"]
    status, payload = router.handle("PUT", f"/api/role-definitions/{code}", {"display_name": "新名", "remark": "改备注"}, current_user=_admin())
    assert status == 200
    assert payload["role_definition"]["display_name"] == "新名"


def test_admin_update_custom_role_name_and_remark_persist_over_stale_snapshot(tmp_path):
    from auto_check.app.storage_role_capabilities import save_role_remarks

    router, _ = _router(tmp_path)
    status, payload = router.handle(
        "POST",
        "/api/role-definitions",
        {"display_name": "wwww", "remark": "111"},
        current_user=_admin(),
    )
    assert status == 201
    code = payload["role_definition"]["role_code"]
    with router.application_database.transaction() as connection:
        save_role_remarks(
            connection,
            remarks={code: "111"},
            updated_by="u1",
            custom_roles=[code],
            custom_role_remarks={code: "111"},
        )
    status, payload = router.handle(
        "PUT",
        f"/api/role-definitions/{code}",
        {"display_name": "vvvvvv", "remark": "111111111"},
        current_user=_admin(),
    )
    assert status == 200, payload
    assert payload["role_definition"]["display_name"] == "vvvvvv"
    assert payload["role_definition"]["remark"] == "111111111"
    status, payload = router.handle("GET", "/api/role-capabilities", None, current_user=_admin())
    assert status == 200
    assert payload["roles"][code] == "vvvvvv"
    assert payload["remarks"][code] == "111111111"


def test_admin_delete_role_definition_no_users(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("POST", "/api/role-definitions", {"display_name": "临时"}, current_user=_admin())
    code = payload["role_definition"]["role_code"]
    status, payload = router.handle("DELETE", f"/api/role-definitions/{code}", None, current_user=_admin())
    assert status == 200


def test_delete_role_definition_rejects_system_role(tmp_path):
    router, _ = _router(tmp_path)
    status, payload = router.handle("DELETE", "/api/role-definitions/admin", None, current_user=_admin())
    assert status == 400


def test_admin_can_delete_removed_builtin_role_leftover(tmp_path):
    from auto_check.app.storage_role_definitions import ROLE_DEFINITIONS_TABLE

    router, _ = _router(tmp_path)
    with router.application_database.transaction() as connection:
        connection.execute(
            ROLE_DEFINITIONS_TABLE.insert().values(
                role_code="regulatory_report",
                display_name="监管报表",
                remark="预留角色",
                is_system=0,
                created_by="admin",
                created_at="2026-08-07 00:00:00",
                updated_by="admin",
                updated_at="2026-08-07 00:00:00",
            )
        )
    status, payload = router.handle(
        "DELETE", "/api/role-definitions/regulatory_report", None, current_user=_admin()
    )
    assert status == 200, payload
    status, payload = router.handle("GET", "/api/role-capabilities", None, current_user=_admin())
    assert status == 200
    assert "regulatory_report" not in payload["roles"]
    assert all(d["role_code"] != "regulatory_report" for d in payload["role_definitions"])


def test_get_role_capabilities_returns_role_definitions_and_locks(tmp_path):
    router, _ = _router(tmp_path)
    router.handle("POST", "/api/role-definitions", {"display_name": "审计"}, current_user=_admin())
    status, payload = router.handle("GET", "/api/role-capabilities", None, current_user=_admin())
    assert status == 200
    assert "required_capabilities" in payload
    assert "admin_only_capabilities" in payload
    assert "role_definitions" in payload
    assert "menu.report_navigation" in payload["required_capabilities"]
    assert "sys.users" in payload["admin_only_capabilities"]
    assert "history.delete" not in payload["admin_only_capabilities"]
    custom_defs = [d for d in payload["role_definitions"] if not d["is_system"]]
    assert any(d["display_name"] == "审计" for d in custom_defs)


def test_report_navigation_admin_capability_denied_for_user(tmp_path):
    router, _ = _router(tmp_path)
    body = {"report_month": "2026-07"}
    status, payload = router.handle("POST", "/api/report-navigation/steps/pbc_template_7/manual-complete", body, current_user=_user())
    assert (status, payload["error"]) == (403, "admin role required")
