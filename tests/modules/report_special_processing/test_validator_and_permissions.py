from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


def _payload(**overrides):
    payload = {
        "save_mode": "record",
        "report_process_code": "pbc",
        "report_period": "2026-07-31",
        "reports": ["  1104-01   资产负债表  "],
        "summary": "摘要",
        "processing_content": "特殊处理内容",
        "processing_script": "DROP TABLE never_executed;",
        "special_handling_at": "2026-08-01T15:32:18+08:00",
        "handler_user_id": "12",
    }
    payload.update(overrides)
    return payload


def test_validator_normalizes_complete_input_without_executing_script():
    from auto_check.modules.report_special_processing.validator import validate_record_input

    value = validate_record_input(_payload())
    assert value.reports == ("1104-01 资产负债表",)
    assert value.processing_script == "DROP TABLE never_executed;"
    assert value.special_handling_at.tzinfo == ZoneInfo("Asia/Shanghai")


def test_draft_allows_business_fields_to_be_missing_except_process():
    from auto_check.modules.report_special_processing.validator import validate_record_input

    value = validate_record_input({"save_mode": "draft", "report_process_code": "pbc"})
    assert value.report_process_codes == ("pbc",)
    assert value.reports == ()
    assert value.report_period is None
    assert value.handler_user_id is None


def test_validator_accepts_multi_report_process_codes():
    from auto_check.modules.report_special_processing.validator import validate_record_input

    payload = _payload()
    payload.pop("report_process_code", None)
    payload["report_process_codes"] = ["pbc", "east5"]
    value = validate_record_input(payload)
    assert value.report_process_codes == ("pbc", "east5")
    assert value.report_process_code == "pbc"


@pytest.mark.parametrize(
    "payload",
    [
        _payload(reports=[]),
        _payload(reports=[str(i) for i in range(51)]),
        _payload(reports=["same", " same "]),
        _payload(processing_script="汉" * 174763),
        _payload(report_period="2026-02-30"),
        _payload(special_handling_at="2026-08-01T15:32:18"),
        _payload(summary="x" * 26),
        {**_payload(), "creator_user_id": "forged"},
    ],
)
def test_validator_rejects_contract_violations(payload):
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import validate_record_input

    with pytest.raises(ValidationError):
        validate_record_input(payload)


def test_script_accepts_exact_512_kib_utf8_boundary():
    from auto_check.modules.report_special_processing.validator import validate_record_input

    value = validate_record_input(_payload(processing_script="x" * 524288))
    assert len(value.processing_script.encode("utf-8")) == 524288


def test_void_reason_accepts_up_to_20_characters_and_rejects_longer():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import validate_action

    version, reason = validate_action(
        {"row_version": 1, "reason": "一二三四五六七八九十十一十二十三十四十五"},
        require_reason=True,
        reason_max_length=20,
    )
    assert version == 1
    assert len(reason) == 20

    with pytest.raises(ValidationError) as error:
        validate_action(
            {"row_version": 1, "reason": "一二三四五六七八九十十一十二十三十四十五十"},
            require_reason=True,
            reason_max_length=20,
        )
    assert "最多 20 个字符" in str(error.value.fields["reason"])


def test_permissions_bind_to_rsp_capabilities_and_creator_scope():
    from auto_check.modules.report_special_processing.permissions import (
        can_confirm,
        can_create,
        can_delete,
        can_edit,
        can_reopen,
        can_void,
    )

    record = {"creator_user_id": "1", "handler_user_id": "2", "status": "pending"}
    creator = {"id": "1", "role": "user"}
    handler = {"id": "2", "role": "user"}
    other = {"id": "3", "role": "user"}
    admin = {"id": "9", "role": "admin"}
    confirmer = {"id": "8", "role": "user", "capabilities": ["rsp.view", "rsp.confirm"]}

    assert can_edit(creator, record)
    assert not can_edit(handler, record)  # 谁创建谁处理：处理人不可单独编辑
    assert not can_edit(other, record)
    assert can_edit(admin, record)
    assert not can_edit(creator, {**record, "status": "completed"})

    assert can_void(creator, record)
    assert not can_void(other, record)
    assert can_void(admin, record)

    assert can_reopen(admin, {**record, "status": "completed"})
    assert can_reopen(creator, {**record, "status": "completed"})
    assert not can_reopen(other, {**record, "status": "completed"})

    assert can_delete(admin) and not can_delete(creator)
    assert can_create(creator) and not can_create(confirmer)
    assert can_confirm(confirmer) and not can_confirm(creator)
    assert can_confirm(admin)


@pytest.mark.parametrize(
    ("source", "target", "allowed"),
    [
        ("draft", "pending", True),
        ("pending", "processing", True),
        ("pending", "completed", True),
        ("processing", "pending", True),
        ("processing", "completed", True),
        ("completed", "processing", False),
        ("voided", "pending", False),
    ],
)
def test_normal_status_transitions_are_strict(source, target, allowed):
    from auto_check.modules.report_special_processing.permissions import can_transition
    assert can_transition(source, target) is allowed
