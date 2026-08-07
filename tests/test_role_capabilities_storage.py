"""角色能力矩阵存储层（单行 JSON 快照）测试。"""

import json
from datetime import UTC, datetime

from mysql_config_test_support import MemoryApplicationDatabase

from auto_check.app.capabilities import has_capability, merge_matrix
from auto_check.app.storage_role_capabilities import (
    ROLE_CAPABILITY_SETTINGS,
    load_role_capability_matrix,
    save_role_capability_matrix,
)


def _db():
    return MemoryApplicationDatabase()


def test_load_empty_returns_default_matrix():
    db = _db()
    with db.connect() as connection:
        matrix = load_role_capability_matrix(connection)
    assert matrix == merge_matrix(None)
    assert has_capability("admin", "history.delete", matrix) is True
    assert has_capability("user", "sys.users", matrix) is False
    assert has_capability("user", "rsp.view", matrix) is True
    assert has_capability("user", "rsp.confirm", matrix) is False


def test_load_sanitizes_historical_admin_only_grant():
    # 旧版本无 admin-only 约束，历史矩阵可能把管理员专属能力授给非 admin 角色；
    # 读取时必须清洗为 False，否则后续任何保存都会被校验拒绝
    db = _db()
    with db.transaction() as connection:
        connection.execute(
            ROLE_CAPABILITY_SETTINGS.insert().values(
                id=1,
                matrix_json=json.dumps(
                    {
                        "custom_auditor": {
                            "sys.users": True,
                            "history.delete": True,
                            "sys.settings": False,
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                version=1,
                updated_by="legacy",
                updated_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
    with db.connect() as connection:
        matrix = load_role_capability_matrix(connection, custom_roles=["custom_auditor"])
    assert matrix["custom_auditor"]["sys.users"] is False
    assert matrix["custom_auditor"]["sys.role_permissions"] is False
    assert matrix["custom_auditor"]["sys.settings"] is False
    # admin 列不受清洗影响
    assert matrix["admin"]["sys.users"] is True
    assert matrix["admin"]["sys.role_permissions"] is True


def test_save_and_load_roundtrip_non_admin_change():
    db = _db()
    with db.transaction() as connection:
        saved = save_role_capability_matrix(
            connection,
            matrix={"user": {"menu.tools": False}},
            updated_by="admin",
        )
    assert has_capability("user", "menu.tools", saved) is False
    with db.connect() as connection:
        matrix = load_role_capability_matrix(connection)
    assert has_capability("user", "menu.tools", matrix) is False
    # admin 列保持默认（锁定）
    assert has_capability("admin", "menu.tools", matrix) is True


def test_save_rejects_admin_only_capability_for_non_admin():
    import pytest
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="admin-only"):
            save_role_capability_matrix(
                connection,
                matrix={"user": {"sys.users": True}},
                updated_by="admin",
            )


def test_save_rejects_disabling_required_capability():
    import pytest
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="required"):
            save_role_capability_matrix(
                connection,
                matrix={"user": {"menu.report_navigation": False}},
                updated_by="admin",
            )


def test_save_preserves_custom_role_when_passed():
    db = _db()
    with db.transaction() as connection:
        save_role_capability_matrix(
            connection,
            matrix={"custom_auditor": {"menu.tools": False}},
            updated_by="admin",
            custom_roles=["custom_auditor"],
        )
    with db.connect() as connection:
        matrix = load_role_capability_matrix(connection, custom_roles=["custom_auditor"])
    assert "custom_auditor" in matrix
    assert has_capability("custom_auditor", "menu.tools", matrix) is False
    # 自定义角色默认等同 user 档
    assert has_capability("custom_auditor", "menu.home", matrix) is True


def test_save_rejects_admin_only_for_custom_role():
    import pytest
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="admin-only"):
            save_role_capability_matrix(
                connection,
                matrix={"custom_auditor": {"sys.users": True}},
                updated_by="admin",
                custom_roles=["custom_auditor"],
            )


def test_save_rejects_required_disable_for_custom_role():
    import pytest
    db = _db()
    with db.transaction() as connection:
        with pytest.raises(ValueError, match="required"):
            save_role_capability_matrix(
                connection,
                matrix={"custom_auditor": {"menu.report_navigation": False}},
                updated_by="admin",
                custom_roles=["custom_auditor"],
            )


def test_save_rejects_admin_column_change():
    db = _db()
    incoming = merge_matrix(None)
    incoming["admin"]["history.delete"] = False
    with db.transaction() as connection:
        try:
            save_role_capability_matrix(connection, matrix=incoming, updated_by="admin")
            assert False, "expected ValueError"  # noqa: B011
        except ValueError as exc:
            assert "admin" in str(exc).lower()
    # 失败后库仍为空（回滚/未写入）
    with db.connect() as connection:
        matrix = load_role_capability_matrix(connection)
    assert matrix == merge_matrix(None)


def test_save_merges_missing_capabilities():
    db = _db()
    with db.transaction() as connection:
        save_role_capability_matrix(
            connection,
            matrix={"user": {"sys.settings": False}},
            updated_by="admin",
        )
    with db.connect() as connection:
        matrix = load_role_capability_matrix(connection)
    # 已存值保留
    assert matrix["user"]["sys.settings"] is False
    # 缺失项补默认
    assert "history.delete" in matrix["user"]
    assert matrix["user"]["history.delete"] is False
    assert matrix["user"]["rsp.view"] is True


def test_save_drops_unknown_roles_and_capabilities():
    db = _db()
    with db.transaction() as connection:
        save_role_capability_matrix(
            connection,
            matrix={"ghost_role": {"sys.settings": True}, "user": {"ghost.capability": True}},
            updated_by="admin",
        )
    with db.connect() as connection:
        matrix = load_role_capability_matrix(connection)
    assert "ghost_role" not in matrix
    assert "ghost.capability" not in matrix["user"]


def test_save_persists_across_new_connection():
    db = _db()
    with db.transaction() as connection:
        save_role_capability_matrix(
            connection,
            matrix={"custom_auditor": {"rsp.confirm": True}},
            updated_by="admin",
            custom_roles=["custom_auditor"],
        )
    with db.connect() as connection:
        matrix = load_role_capability_matrix(connection, custom_roles=["custom_auditor"])
    assert has_capability("custom_auditor", "rsp.confirm", matrix) is True
    # 自定义角色其它能力保持标准档默认
    assert has_capability("custom_auditor", "rsp.create", matrix) is True


def test_load_role_remarks_empty_returns_defaults():
    from auto_check.app.capabilities import DEFAULT_ROLE_REMARKS
    from auto_check.app.storage_role_capabilities import load_role_remarks
    db = _db()
    with db.connect() as connection:
        remarks = load_role_remarks(connection)
    assert remarks == DEFAULT_ROLE_REMARKS


def test_save_and_load_role_remarks_roundtrip():
    from auto_check.app.storage_role_capabilities import load_role_remarks, save_role_remarks
    db = _db()
    with db.transaction() as connection:
        saved = save_role_remarks(connection, remarks={"user": "测试备注"}, updated_by="admin")
    assert saved["user"] == "测试备注"
    with db.connect() as connection:
        remarks = load_role_remarks(connection)
    assert remarks["user"] == "测试备注"
    assert "admin" in remarks
