from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import MANIFEST
from auto_check.modules.data_validation.storage import AUDITS
from tests.modules.data_validation.support import Metadata, loan_definition, service, user


ITEM_FIELDS = {
    "id", "action_code", "version_no", "operator_user_id", "operator_name",
    "created_at", "summary", "changes", "before_status", "after_status",
}


def _owner(**overrides):
    value = {
        "id": "1", "role": "user", "username": "checker", "display_name": "校验员",
    }
    value.update(overrides)
    return value


def _change(item, field):
    return next(change for change in item["changes"] if change["field"] == field)


def test_create_and_two_edits_keep_real_recursive_diffs_and_versions():
    _database, rules = service()
    owner = _owner()
    created = rules.save_draft(owner, loan_definition(name="初版", violation_message="第一版提示"))
    first_version = rules.storage.get_version(created["id"], 1)

    second = loan_definition(name="第二版", violation_message="第一版提示")
    second["expression"] = {"left": "maturity_date", "op": "lte", "right": "issue_date"}
    rules.save_draft(_owner(display_name="第二位操作人"), second, created["id"])
    second_version = rules.storage.get_version(created["id"], 2)

    third = loan_definition(name="第二版", violation_message="最终提示")
    third["expression"] = {"left": "end_date", "op": "lte", "right": "issue_date"}
    rules.save_draft(owner, third, created["id"])

    page = rules.list_rule_history(owner, created["id"])
    assert page["total"] == 3
    assert page["page_size"] == 20
    assert [item["action_code"] for item in page["items"]] == ["update", "update", "create"]
    assert [item["version_no"] for item in page["items"]] == [3, 2, 1]
    assert all(set(item) == ITEM_FIELDS for item in page["items"])

    latest, middle, initial = page["items"]
    assert _change(latest, "expression.left") == {
        "field": "expression.left", "label": "比较左字段",
        "before": "maturity_date", "after": "end_date",
    }
    assert _change(latest, "violation_message")["before"] == "第一版提示"
    assert _change(latest, "violation_message")["after"] == "最终提示"
    assert _change(middle, "name")["before"] == "初版"
    assert _change(middle, "name")["after"] == "第二版"
    assert _change(middle, "expression.op")["before"] == "lt"
    assert _change(middle, "expression.op")["after"] == "lte"
    assert all(change["before"] is None for change in initial["changes"])
    assert initial["operator_name"] == "校验员"
    assert middle["operator_name"] == "第二位操作人"
    assert latest["operator_name"] == "校验员"

    assert rules.storage.get_version(created["id"], 1)["content_sha256"] == first_version["content_sha256"]
    assert rules.storage.get_version(created["id"], 1)["definition"] == first_version["definition"]
    assert rules.storage.get_version(created["id"], 2)["content_sha256"] == second_version["content_sha256"]
    assert rules.storage.get_version(created["id"], 2)["definition"] == second_version["definition"]


def test_confirm_and_disable_have_status_evidence_without_duplicate_confirmation():
    _database, rules = service(metadata=Metadata())
    owner = _owner()
    created = rules.save_draft(owner, loan_definition())
    version = rules.storage.latest_version(created["id"])
    tested = rules.run_tests(owner, created["id"], 1)
    rules.confirm_rule(owner, created["id"], 1, version["content_sha256"])
    rules.disable_rule(owner, created["id"])

    page = rules.list_rule_history(owner, created["id"])
    assert page["total"] == 3
    assert [item["action_code"] for item in page["items"]] == ["disable", "confirm", "create"]
    disabled, confirmed, _created = page["items"]
    assert disabled["before_status"] == "enabled"
    assert disabled["after_status"] == "disabled"
    assert confirmed["before_status"] == "draft"
    assert confirmed["after_status"] == "enabled"
    assert version["content_sha256"] in confirmed["summary"]
    assert f"测试通过 {tested['passed_count']}" in confirmed["summary"]
    assert confirmed["version_no"] == disabled["version_no"] == 1


def test_copy_records_source_only_on_the_new_rule():
    database, rules = service()
    owner = _owner()
    source = rules.save_draft(owner, loan_definition(name="来源规则"))
    rules.save_draft(owner, loan_definition(name="来源规则第二版"), source["id"])

    with pytest.raises(AppError) as denied:
        rules.copy_rule(_owner(id="2", username="stranger", display_name="路人"), source["id"])
    assert denied.value.code == "FORBIDDEN"
    assert [item["action_code"] for item in rules.list_rule_history(owner, source["id"])["items"]] == ["update", "create"]
    with database.connect() as connection:
        copy_rows = connection.execute(
            select(AUDITS).where(AUDITS.c.rule_id == source["id"]).where(AUDITS.c.action_code == "copy")
        ).all()
    assert not copy_rows

    copier = _owner(id="9", role="admin", username="copier", display_name="复制人")
    copied = rules.copy_rule(copier, source["id"])

    copied_history = rules.list_rule_history(copier, copied["id"])
    assert copied_history["total"] == 1
    event = copied_history["items"][0]
    assert event["action_code"] == "copy"
    assert event["version_no"] == 1
    assert event["operator_user_id"] == "9"
    assert event["operator_name"] == "复制人"
    assert source["rule_code"] in event["summary"]
    assert "版本 2" in event["summary"]
    assert event["before_status"] is None
    assert event["after_status"] == "draft"

    source_history = rules.list_rule_history(owner, source["id"])
    assert [item["action_code"] for item in source_history["items"]] == ["update", "create"]


def test_history_uses_rule_visibility_and_admin_cannot_edit_for_owner():
    _database, rules = service()
    owner = _owner()
    created = rules.save_draft(owner, loan_definition())

    with pytest.raises(AppError) as denied:
        rules.list_rule_history(user("2"), created["id"])
    assert denied.value.code == "FORBIDDEN"
    assert rules.storage.latest_audit(created["id"])["action_code"] == "access_denied"

    admin = user("9", "admin")
    admin_history = rules.list_rule_history(admin, created["id"])
    assert admin_history["total"] == 1
    with pytest.raises(AppError) as admin_denied:
        rules.save_draft(admin, loan_definition(name="管理员代改"), created["id"])
    assert admin_denied.value.code == "FORBIDDEN"
    assert [item["action_code"] for item in rules.list_rule_history(admin, created["id"])["items"]] == ["create"]


def test_legacy_versions_and_confirmation_are_synthesized_without_backfill_or_duplicates():
    database, rules = service()
    owner = _owner()
    created = rules.storage.create_rule(
        creator_user_id="1", name="旧版", description="旧数据",
        definition=loan_definition(name="旧版"), sql_text="SELECT 1", mapping_version="map-1",
        content_sha256="a" * 64, generation_mode="manual",
    )
    rules.storage.add_version(
        created["id"], loan_definition(name="旧版二", description="第二次保存"),
        "SELECT 2", "map-2", "b" * 64,
    )
    rules.storage.set_status(created["id"], "enabled", 2)
    rules.storage.add_confirmation(
        rule_id=created["id"], version_no=2, version_id=2,
        content_sha256="b" * 64, confirmer_user_id="1",
        passed_count=4, failed_count=0, not_run_count=0,
    )
    first_version = rules.storage.get_version(created["id"], 1)
    second_version = rules.storage.get_version(created["id"], 2)
    with database.connect() as connection:
        audit_count = len(connection.execute(select(AUDITS).where(AUDITS.c.rule_id == created["id"])).all())

    page = rules.list_rule_history(owner, created["id"], {"page_size": 50})
    assert audit_count == 0
    assert [item["action_code"] for item in page["items"]] == ["confirm", "update", "create"]
    confirm, update, create = page["items"]
    assert confirm["created_at"]
    assert "b" * 64 in confirm["summary"]
    assert update["created_at"] == second_version["created_at"]
    assert create["created_at"] == first_version["created_at"]
    assert update["operator_user_id"] == create["operator_user_id"] == "1"
    assert _change(update, "name")["before"] == "旧版"
    assert _change(update, "name")["after"] == "旧版二"
    assert "a" * 64 in create["summary"]

    rules.save_draft(owner, loan_definition(name="升级后的新版"), created["id"])
    upgraded = rules.list_rule_history(owner, created["id"], {"page_size": 50})
    assert [item["action_code"] for item in upgraded["items"]] == ["update", "confirm", "update", "create"]
    assert sum(item["action_code"] == "confirm" for item in upgraded["items"]) == 1
    assert rules.storage.get_version(created["id"], 1)["content_sha256"] == "a" * 64
    assert rules.storage.get_version(created["id"], 2)["content_sha256"] == "b" * 64


def test_history_pagination_is_stable_and_supports_all_page_sizes():
    _database, rules = service()
    owner = _owner()
    created = rules.save_draft(owner, loan_definition(name="版本 1"))
    for version_no in range(2, 26):
        rules.save_draft(owner, loan_definition(name=f"版本 {version_no}"), created["id"])

    first = rules.list_rule_history(owner, created["id"])
    first_again = rules.list_rule_history(owner, created["id"], {"page": 1, "page_size": 20})
    second = rules.list_rule_history(owner, created["id"], {"page": 2, "page_size": 20})
    assert first == first_again
    assert first["total"] == second["total"] == 25
    assert first["page_size"] == second["page_size"] == 20
    assert len(first["items"]) == 20
    assert len(second["items"]) == 5
    assert [item["version_no"] for item in first["items"]] == list(range(25, 5, -1))
    assert [item["version_no"] for item in second["items"]] == [5, 4, 3, 2, 1]
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})

    invalid = rules.list_rule_history(owner, created["id"], {"page_size": 7})
    assert invalid["page_size"] == 20
    assert len(rules.list_rule_history(owner, created["id"], {"page_size": 50})["items"]) == 25
    assert len(rules.list_rule_history(owner, created["id"], {"page_size": 100})["items"]) == 25


def test_history_persists_only_masked_diffs_not_request_envelope_or_secrets():
    database, rules = service()
    owner = _owner()
    definition = loan_definition(
        name="脱敏",
        api_key="create-secret",
        nested={"password": "nested-secret", "safe": "ok"},
        params={"access_token": "token-secret", "ordinary": 1},
    )
    created = rules.save_draft(owner, definition)
    changed = dict(definition)
    changed["api_key"] = "updated-secret"
    changed["nested"] = {"password": "new-nested-secret", "safe": "changed"}
    rules.save_draft(owner, changed, created["id"])

    with database.connect() as connection:
        rows = connection.execute(select(AUDITS).where(AUDITS.c.rule_id == created["id"])).mappings().all()
    assert len(rows) == 2
    raw_audits = "".join(str(row["detail_json"]) for row in rows)
    for secret in ("create-secret", "updated-secret", "nested-secret", "new-nested-secret", "token-secret"):
        assert secret not in raw_audits
    assert "request_payload" not in raw_audits
    assert "current_user" not in raw_audits

    history = rules.list_rule_history(owner, created["id"])
    visible = json.dumps(history, ensure_ascii=False)
    for secret in ("create-secret", "updated-secret", "nested-secret", "new-nested-secret", "token-secret"):
        assert secret not in visible
    latest = history["items"][0]
    assert _change(latest, "api_key")["before"] == "********"
    assert _change(latest, "api_key")["after"] == "********"
    assert _change(latest, "nested.safe")["before"] == "ok"


def test_history_route_returns_contract_with_view_permission():
    _database, rules = service()
    created = rules.save_draft(_owner(), loan_definition())
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    response = router.dispatch(ModuleRequest(
        method="GET",
        path=f"{MANIFEST.api_prefix}/rules/{created['id']}/history",
        path_params={},
        query={"page": "1", "page_size": "20"},
        body=None,
        current_user={
            "id": "1", "role": "user", "username": "checker", "display_name": "校验员",
            "capabilities": ["dv.view"],
        },
    ))
    assert response is not None
    assert response.status == 200
    assert response.body["data"]["total"] == 1
    assert response.body["data"]["items"][0]["action_code"] == "create"
