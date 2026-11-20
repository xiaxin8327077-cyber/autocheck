import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import Metadata, loan_definition, service, user


def snapshot(detail):
    return {key: detail[key] for key in ("version_no", "content_sha256", "status", "current_version_id")}


def test_edit_rejects_stale_content_without_overwriting_hidden_definition():
    _db, rules = service(metadata=Metadata())
    created = rules.save_draft(user(), loan_definition())
    before = rules.get_rule(user(), created["id"])
    rules.save_draft(user(), loan_definition(name="其他窗口", violation_message="其他窗口更新的异常说明"), created["id"])
    with pytest.raises(AppError, match="CONFLICT_VERSION"):
        rules.save_draft(user(), {**before["definition"], "name": "旧窗口", "expected_rule": snapshot(before)}, created["id"])
    assert rules.get_rule(user(), created["id"])["definition"]["violation_message"] == "其他窗口更新的异常说明"


def test_edit_context_is_not_saved_as_business_definition():
    _db, rules = service(metadata=Metadata())
    created = rules.save_draft(user(), loan_definition())
    before = rules.get_rule(user(), created["id"])
    rules.save_draft(user(), {**before["definition"], "name": "新名称", "expected_rule": snapshot(before)}, created["id"])
    after = rules.get_rule(user(), created["id"])
    assert "expected_rule" not in after["definition"]
    assert after["version_no"] == 2


def test_edit_context_rejects_status_change_even_with_same_content_hash():
    _db, rules = service(metadata=Metadata())
    created = rules.save_draft(user(), loan_definition())
    before = rules.get_rule(user(), created["id"])
    rules.disable_rule(user(), created["id"])
    with pytest.raises(AppError, match="CONFLICT_VERSION"):
        rules.save_draft(user(), {**before["definition"], "expected_rule": snapshot(before)}, created["id"])


def test_storage_checks_editor_context_inside_write_lock():
    _db, rules = service(metadata=Metadata())
    created = rules.save_draft(user(), loan_definition())
    before = rules.get_rule(user(), created["id"])
    rules.disable_rule(user(), created["id"])
    with pytest.raises(AppError, match="CONFLICT_VERSION"):
        rules.storage.add_version(created["id"], before["definition"], before["sql_text"], "", before["content_sha256"], expected_rule=snapshot(before))


def test_stale_disable_does_not_change_newer_rule_state():
    _db, rules = service(metadata=Metadata())
    created = rules.save_draft(user(), loan_definition())
    before = rules.get_rule(user(), created["id"])
    rules.storage.set_status(created["id"], "enabled", before["version_id"])
    with pytest.raises(AppError, match="CONFLICT_VERSION"):
        rules.disable_rule(user(), created["id"], expected_rule=snapshot(before))
    assert rules.get_rule(user(), created["id"])["status"] == "enabled"


def test_stale_confirm_cannot_reverse_a_concurrent_disable():
    _db, rules = service(metadata=Metadata())
    created = rules.save_draft(user(), loan_definition())
    before = rules.get_rule(user(), created["id"])
    rules.run_tests(user(), created["id"], before["version_no"])
    rules.disable_rule(user(), created["id"])
    with pytest.raises(AppError, match="CONFLICT_VERSION"):
        rules.confirm_rule(user(), created["id"], before["version_no"], before["content_sha256"], expected_rule=snapshot(before))
    assert rules.get_rule(user(), created["id"])["status"] == "disabled"


def test_legacy_calls_without_editor_context_remain_compatible():
    _db, rules = service(metadata=Metadata())
    created = rules.save_draft(user(), loan_definition())
    before = rules.get_rule(user(), created["id"])
    rules.run_tests(user(), created["id"], before["version_no"])
    rules.confirm_rule(user(), created["id"], before["version_no"], before["content_sha256"])
    assert rules.get_rule(user(), created["id"])["status"] == "enabled"
