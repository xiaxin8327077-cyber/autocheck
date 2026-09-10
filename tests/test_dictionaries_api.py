"""字典管理 API 测试：能力鉴权、分类/字典项 CRUD 与错误映射。

直接调用 ``ApiRouter.handle`` 注入 ``current_user``，避免 HTTP/RSA 开销；
登录与 CSRF 由 ``_handle_api`` 全局前置校验，路由位于其后天然受保护。
"""

import pytest

from auto_check.app.server import ApiRouter
from mysql_config_test_support import MemoryApplicationDatabase


def _admin():
    return {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}


def _user():
    return {"id": "u2", "username": "user", "display_name": "用户", "role": "user"}


def _custom():
    return {"id": "u3", "username": "auditor", "display_name": "审计", "role": "custom_1"}


@pytest.fixture()
def router(tmp_path):
    return ApiRouter(
        config_path=tmp_path / "config.json",
        application_database=MemoryApplicationDatabase(),
        report_navigation_service=None,
        start_field_mapping_auto_refresh=False,
    )


def _create_dictionary(router, *, code="business_system", name="业务系统", **kwargs):
    return router.handle(
        "POST",
        "/api/system/dictionaries",
        {"code": code, "name": name, **kwargs},
        current_user=_admin(),
    )


# ---------------------------------------------------------------- 鉴权


def test_dictionary_routes_require_capability(router):
    status, payload = router.handle("GET", "/api/system/dictionaries", None, current_user=_user())
    assert status == 403
    assert "error" in payload
    status, _ = router.handle(
        "POST", "/api/system/dictionaries", {"code": "x1", "name": "n"}, current_user=_user()
    )
    assert status == 403
    status, _ = router.handle(
        "POST", "/api/system/dictionaries", {"code": "x1", "name": "n"}, current_user=_custom()
    )
    assert status == 403
    status, _ = router.handle("GET", "/api/system/dictionaries", None, current_user=None)
    assert status == 403


def test_admin_default_matrix_allows_dictionaries():
    from auto_check.app.capabilities import ADMIN_ONLY_CAPABILITIES, DEFAULT_MATRIX, has_capability

    assert "sys.dictionaries" in ADMIN_ONLY_CAPABILITIES
    assert has_capability("admin", "sys.dictionaries", DEFAULT_MATRIX)
    assert not has_capability("user", "sys.dictionaries", DEFAULT_MATRIX)


# ---------------------------------------------------------------- 分类


def test_get_dictionaries_returns_empty_list(router):
    status, payload = router.handle("GET", "/api/system/dictionaries", None, current_user=_admin())
    assert status == 200
    assert payload == {"dictionaries": []}


def test_create_dictionary_and_list_nested(router):
    status, payload = _create_dictionary(router, description="说明", sort_order=10)
    assert status == 201
    assert payload["dictionary"]["code"] == "business_system"
    assert payload["dictionary"]["system_locked"] is False
    status, listed = router.handle("GET", "/api/system/dictionaries", None, current_user=_admin())
    assert status == 200
    entry = listed["dictionaries"][0]
    assert entry["name"] == "业务系统"
    assert entry["description"] == "说明"
    assert entry["enabled"] is True
    assert entry["items"] == []


def test_create_dictionary_validation_and_conflict(router):
    status, _ = _create_dictionary(router, code="Bad Code")
    assert status == 400
    status, payload = _create_dictionary(router, name="  ")
    assert status == 400
    status, _ = _create_dictionary(router, code="ok", name="x")
    assert status == 201
    status, payload = _create_dictionary(router, code="ok", name="重复")
    assert status == 409
    assert "已存在" in payload["error"]


def test_create_dictionary_accepts_numeric_code(router):
    status, payload = _create_dictionary(router, code="100", name="数字字典")
    assert status == 201
    assert payload["dictionary"]["code"] == "100"


def test_update_dictionary(router):
    _create_dictionary(router)
    status, payload = router.handle(
        "PUT",
        "/api/system/dictionaries/business_system",
        {"name": "业务系统改名", "enabled": False, "sort_order": 3},
        current_user=_admin(),
    )
    assert status == 200
    assert payload["dictionary"]["name"] == "业务系统改名"
    assert payload["dictionary"]["enabled"] is False
    status, _ = router.handle("PUT", "/api/system/dictionaries/ghost", {"name": "x"}, current_user=_admin())
    assert status == 404


def test_delete_custom_dictionary_and_reject_locked(router):
    _create_dictionary(router, code="custom", name="自定义")
    status, payload = router.handle(
        "DELETE", "/api/system/dictionaries/custom", None, current_user=_admin()
    )
    assert status == 200
    assert payload["deleted"] is True

    from auto_check.app.storage_dictionaries import create_dictionary
    with router.application_database.transaction() as connection:
        create_dictionary(
            connection, code="locked", name="预置", system_locked=True, updated_by="admin"
        )
    status, payload = router.handle(
        "DELETE", "/api/system/dictionaries/locked", None, current_user=_admin()
    )
    assert status == 400
    assert "系统预置字典不可删除" in payload["error"]


# ---------------------------------------------------------------- 字典项


def test_create_item_requires_existing_dictionary(router):
    status, payload = router.handle(
        "POST",
        "/api/system/dictionaries/ghost/items",
        {"code": "ta", "name": "TA估值"},
        current_user=_admin(),
    )
    assert status == 404


def test_create_list_and_update_items(router):
    _create_dictionary(router)
    status, payload = router.handle(
        "POST",
        "/api/system/dictionaries/business_system/items",
        {"code": "valuation", "name": "估值系统", "sort_order": 20},
        current_user=_admin(),
    )
    assert status == 201
    item = payload["item"]
    assert item["code"] == "valuation"
    status, payload = router.handle(
        "POST",
        "/api/system/dictionaries/business_system/items",
        {"code": "ta", "name": "TA估值", "sort_order": 10},
        current_user=_admin(),
    )
    assert status == 201
    status, payload = router.handle(
        "POST",
        "/api/system/dictionaries/business_system/items",
        {"code": "ta", "name": "重复"},
        current_user=_admin(),
    )
    assert status == 409
    status, listed = router.handle("GET", "/api/system/dictionaries", None, current_user=_admin())
    codes = [entry["code"] for entry in listed["dictionaries"][0]["items"]]
    assert codes == ["ta", "valuation"]
    status, payload = router.handle(
        "PUT",
        f"/api/system/dictionaries/business_system/items/{item['id']}",
        {"code": "valuation_new", "name": "新估值系统", "enabled": False},
        current_user=_admin(),
    )
    assert status == 200
    assert payload["item"]["code"] == "valuation_new"
    assert payload["item"]["name"] == "新估值系统"
    assert payload["item"]["enabled"] is False


def test_create_numeric_item_code_and_reject_duplicate_in_same_dictionary(router):
    _create_dictionary(router)
    status, payload = router.handle(
        "POST",
        "/api/system/dictionaries/business_system/items",
        {"code": "1001", "name": "数字编码"},
        current_user=_admin(),
    )
    assert status == 201
    assert payload["item"]["code"] == "1001"
    status, payload = router.handle(
        "POST",
        "/api/system/dictionaries/business_system/items",
        {"code": "1001", "name": "重复编码"},
        current_user=_admin(),
    )
    assert status == 409
    assert "已存在" in payload["error"]


def test_create_uppercase_item_code(router):
    _create_dictionary(router)
    status, payload = router.handle(
        "POST",
        "/api/system/dictionaries/business_system/items",
        {"code": "TA_SYSTEM", "name": "大写编码"},
        current_user=_admin(),
    )
    assert status == 201
    assert payload["item"]["code"] == "TA_SYSTEM"


def test_update_item_invalid_routes(router):
    _create_dictionary(router)
    status, _ = router.handle(
        "PUT", "/api/system/dictionaries/business_system/items/not-a-number", {"name": "x"}, current_user=_admin()
    )
    assert status == 400
    status, _ = router.handle(
        "PUT", "/api/system/dictionaries/business_system/items/999", {"name": "x"}, current_user=_admin()
    )
    assert status == 404


def test_delete_item(router):
    _create_dictionary(router)
    status, payload = router.handle(
        "POST",
        "/api/system/dictionaries/business_system/items",
        {"code": "delete_me", "name": "待删除"},
        current_user=_admin(),
    )
    assert status == 201
    item_id = payload["item"]["id"]
    status, payload = router.handle(
        "DELETE",
        f"/api/system/dictionaries/business_system/items/{item_id}",
        None,
        current_user=_admin(),
    )
    assert status == 200
    assert payload["deleted"] is True
    status, listed = router.handle("GET", "/api/system/dictionaries", None, current_user=_admin())
    assert listed["dictionaries"][0]["items"] == []


def test_unknown_dictionary_method_routes_404(router):
    status, _ = router.handle("DELETE", "/api/system/dictionaries/business_system", None, current_user=_admin())
    assert status == 404
