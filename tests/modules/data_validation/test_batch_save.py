"""多候选批量草稿：规范化、原子事务、跨请求幂等回执。"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from sqlalchemy import insert, select

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import MANIFEST
from auto_check.modules.data_validation.storage import AUDITS, DOCUMENTS
from tests.modules.data_validation.support import doc_xlsx_bytes, service, user
from tests.modules.data_validation.test_ai_service import _generate_payload, _rules_with_doc, _select_payload


def _rules():
    rules, _model = _rules_with_doc([_select_payload(), _generate_payload()])
    return rules


def _definition(name: str = "期限提醒", **overrides):
    definition = {
        "name": name,
        "description": "到期日不得早于发放日",
        "rule_type": "field_compare",
        "source_id": "src",
        "dialect": "mysql",
        "table_name": "test_table",
        "business_key": "row_id",
        "report_date_field": "issue_date",
        "violation_message": "期限异常",
        "null_policy": "skip",
        "equality_policy": "allow_equal",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
    }
    definition.update(overrides)
    return definition


def _call(router, method, path, current_user, body=None):
    response = router.dispatch(ModuleRequest(
        method=method, path=f"{MANIFEST.api_prefix}{path}", path_params={}, query={},
        body=body, current_user=current_user,
    ))
    assert response is not None
    return response


def test_batch_saves_independent_drafts_with_real_grain_and_unique_codes() -> None:
    rules = _rules()
    single = rules.save_draft(user(), _definition(name="单条"))
    result = rules.batch_save_candidates(user(), {
        "request_key": str(uuid.uuid4()),
        "definitions": [_definition(name="批量一"), _definition(name="批量二")],
    })
    assert result["count"] == 2 and result["reused"] is False
    assert [item["status"] for item in result["rules"]] == ["draft", "draft"]
    assert all(item["version_no"] == 1 and item["current_version_id"] is None for item in result["rules"])
    # 批量保存必须与 preview/单条一致，不额外注入描述造成哈希漂移。
    assert all(item["description"] == "到期日不得早于发放日" for item in result["rules"])

    codes = [single["rule_code"], *[item["rule_code"] for item in result["rules"]]]
    assert len(set(codes)) == 3 and all(code.startswith("DV") for code in codes)


@pytest.fixture
def rules_with_description_limit():
    rules = _rules()
    # SQLite ignores VARCHAR length. Enforce the MySQL rule-table limit on both writes.
    with rules.storage.database.begin() as conn:
        for operation in ("insert", "update"):
            conn.exec_driver_sql(
                f"CREATE TRIGGER enforce_description_{operation} BEFORE {operation} "
                "ON data_validation_rules WHEN length(NEW.description) > 1000 "
                "BEGIN SELECT RAISE(ABORT, 'rule description exceeds 1000 characters'); END"
            )
    return rules


def test_batch_saves_seven_plans_with_a_long_supplement_description(rules_with_description_limit):
    rules = rules_with_description_limit
    owner = {**user(), "capabilities": ["dv.manage"]}
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    description = "补充方案的适用范围与已确认检查条件。" * 90
    supplement = _definition(name="补充方案", description=description, generation_mode="ai")
    preview = rules.preview_candidate(owner, {"definition": supplement})
    payload = {
        "request_key": str(uuid.uuid4()),
        "definitions": [_definition(name=f"主方案{index}") for index in range(1, 7)] + [supplement],
    }

    saved = _call(router, "POST", "/ai/candidates/batch-save", owner, body=payload)
    assert saved.status == 200
    batch = saved.body["data"]
    assert batch["count"] == 7
    supplement_row = batch["rules"][-1]
    assert supplement_row["description"] == description[:1000]
    detail = rules.get_rule(owner, supplement_row["id"])
    assert detail["definition"]["description"] == description
    assert detail["content_sha256"] == preview["content_sha256"]

    retried = _call(router, "POST", "/ai/candidates/batch-save", owner, body=payload)
    assert retried.status == 200
    assert retried.body["data"]["reused"] is True
    assert retried.body["data"]["rules"] == batch["rules"]
    assert len(rules.storage.visible_rules(owner["id"])) == 7


def test_edit_keeps_the_full_description_in_the_new_version(rules_with_description_limit):
    rules = rules_with_description_limit
    owner = user()
    created = rules.save_draft(owner, _definition())
    description = "保存后的完整规则说明。" * 100

    rules.save_draft(owner, _definition(description=description), rule_id=created["id"])

    detail = rules.get_rule(owner, created["id"])
    assert detail["description"] == description[:1000]
    assert detail["definition"]["description"] == description
    assert detail["version_no"] == 2


def test_batch_is_idempotent_by_request_key_and_payload_hash() -> None:
    rules = _rules()
    key = str(uuid.uuid4())
    definitions = [_definition(name="幂等一"), _definition(name="幂等二")]
    first = rules.batch_save_candidates(user(), {"request_key": key, "definitions": definitions})
    second = rules.batch_save_candidates(user(), {"request_key": str(uuid.UUID(key)).upper(), "definitions": definitions})
    assert second["reused"] is True
    assert [item["id"] for item in second["rules"]] == [item["id"] for item in first["rules"]]
    assert len(rules.storage.visible_rules(str(user()["id"]))) == 2

    with pytest.raises(AppError) as conflict:
        rules.batch_save_candidates(user(), {
            "request_key": key, "definitions": [_definition(name="不同载荷")],
        })
    assert conflict.value.code == "CONFLICT_VERSION"
    assert len(rules.storage.visible_rules(str(user()["id"]))) == 2


def test_batch_is_atomic_and_leaves_no_partial_receipt(monkeypatch) -> None:
    rules = _rules()
    original = rules.storage._insert_rule_tx
    calls = {"count": 0}

    def flaky(connection, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("第二份草稿写入失败")
        return original(connection, **kwargs)

    monkeypatch.setattr(rules.storage, "_insert_rule_tx", flaky)
    with pytest.raises(RuntimeError):
        rules.batch_save_candidates(user(), {
            "request_key": str(uuid.uuid4()),
            "definitions": [_definition(name="回滚一"), _definition(name="回滚二")],
        })
    assert rules.storage.visible_rules(str(user()["id"])) == []
    with rules.storage.database.connect() as connection:
        actions = [row[0] for row in connection.execute(select(AUDITS.c.action_code)).all()]
    assert not any(str(action).startswith("ai_batch:") for action in actions)


def test_batch_rejects_bad_requests_and_stale_or_forged_definitions() -> None:
    rules = _rules()
    owner = user()
    with pytest.raises(AppError) as bad_uuid:
        rules.batch_save_candidates(owner, {"request_key": "not-uuid", "definitions": [_definition()]})
    assert bad_uuid.value.code == "VALIDATION_ERROR"
    with pytest.raises(AppError) as too_many:
        rules.batch_save_candidates(owner, {"request_key": str(uuid.uuid4()), "definitions": [_definition()] * 4})
    assert too_many.value.code == "VALIDATION_ERROR"
    with pytest.raises(AppError) as stale:
        rules.batch_save_candidates(owner, {
            "request_key": str(uuid.uuid4()),
            "definitions": [_definition(mapping_version="doc-v-old")],
        })
    assert stale.value.code == "CONFLICT_VERSION"
    with pytest.raises(AppError) as forged_source:
        rules.batch_save_candidates(owner, {
            "request_key": str(uuid.uuid4()), "definitions": [_definition(source_id="other")],
        })
    assert forged_source.value.code == "SOURCE_UNAVAILABLE"
    with pytest.raises(AppError) as missing_table:
        rules.batch_save_candidates(owner, {
            "request_key": str(uuid.uuid4()), "definitions": [_definition(table_name="not_in_document")],
        })
    assert missing_table.value.code == "VALIDATION_ERROR"


def test_batch_owner_isolation_for_reused_request_key() -> None:
    rules = _rules()
    key = str(uuid.uuid4())
    first = rules.batch_save_candidates(user("1"), {"request_key": key, "definitions": [_definition(name="甲")]})
    second = rules.batch_save_candidates(user("2"), {"request_key": key, "definitions": [_definition(name="甲")]})
    assert second["reused"] is False
    assert {item["id"] for item in second["rules"]}.isdisjoint({item["id"] for item in first["rules"]})


def test_batch_route_requires_manage_and_returns_saved_rules() -> None:
    rules = _rules()
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    manager = {**user(), "capabilities": ["dv.manage"]}
    viewer = {**user("2"), "capabilities": []}

    denied = _call(router, "POST", "/ai/candidates/batch-save", viewer, body={
        "request_key": str(uuid.uuid4()), "definitions": [_definition()]})
    assert denied.status == 403

    created = _call(router, "POST", "/ai/candidates/batch-save", manager, body={
        "request_key": str(uuid.uuid4()), "definitions": [_definition(name="路由批量")]})
    assert created.status == 200
    assert created.body["data"]["count"] == 1
    assert created.body["data"]["rules"][0]["status"] == "draft"


def test_batch_rejects_multiple_active_documents_instead_of_split_locks() -> None:
    rules = _rules()
    active = rules.storage.active_document()
    columns = {column.name for column in DOCUMENTS.c}
    row = {key: value for key, value in active.items() if key in columns and key != "id"}
    row["warnings_json"] = "[]"
    with rules.storage.database.begin() as connection:
        connection.execute(insert(DOCUMENTS).values(**row))
    with pytest.raises(AppError) as ambiguous:
        rules.batch_save_candidates(user(), {
            "request_key": str(uuid.uuid4()), "definitions": [_definition()]})
    assert ambiguous.value.code == "VALIDATION_ERROR"
    assert rules.storage.visible_rules(str(user()["id"])) == []


def test_batch_receipt_is_bound_to_document_version() -> None:
    rules = _rules()
    key = str(uuid.uuid4())
    definitions = [_definition(name="文档版本")]
    first = rules.batch_save_candidates(user(), {"request_key": key, "definitions": definitions})
    assert first["count"] == 1
    rules.import_document(user(), "doc-v2.xlsx", doc_xlsx_bytes(fields=[
        ("row_id", "编号", "varchar", "Y"),
        ("maturity_date", "到期日期", "date", ""),
        ("issue_date", "发放日期", "date", ""),
    ]))
    with pytest.raises(AppError) as conflict:
        rules.batch_save_candidates(user(), {"request_key": key, "definitions": definitions})
    assert conflict.value.code == "CONFLICT_VERSION"
    assert len(rules.storage.visible_rules(str(user()["id"]))) == 1
