from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


def _payload(**overrides):
    payload = {
        "save_mode": "record",
        "report_process_code": "pbc",
        "report_period": "2026-07-31",
        "summary": "摘要",
        "processing_script": "DROP TABLE never_executed;",
        "special_handling_at": "2026-08-01T15:32:18+08:00",
        "handler_user_id": "12",
        "dimension": "project",
        "governance_owner_user_id": "owner-1",
        "table_name": "t_asset",
        "field_name": "amount",
        "value_before": "1",
        "value_after": "2",
    }
    payload.update(overrides)
    return payload


def test_validator_normalizes_complete_input_without_executing_script():
    from auto_check.modules.report_special_processing.validator import validate_record_input

    value = validate_record_input(
        _payload(
            reports=["  1104-01   资产负债表  "],
            processing_content="特殊处理内容",
        )
    )
    assert value.reports == ()
    assert value.processing_content == ""
    assert value.dimension == "project"
    assert value.governance_owner_user_id == "owner-1"
    assert value.table_name == "t_asset"
    assert value.field_name == "amount"
    assert value.value_before == "1"
    assert value.value_after == "2"
    assert value.processing_script == "DROP TABLE never_executed;"
    assert value.special_handling_at.tzinfo == ZoneInfo("Asia/Shanghai")


def test_draft_allows_optional_business_fields_but_requires_table_and_field():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import validate_record_input

    value = validate_record_input({
        "save_mode": "draft",
        "report_process_code": "pbc",
        "table_name": "t_draft",
        "field_name": "col_a",
    })
    assert value.report_process_codes == ("pbc",)
    assert value.reports == ()
    assert value.report_period is None
    assert value.handler_user_id is None
    assert value.dimension is None
    assert value.governance_owner_user_id is None
    assert value.table_name == "t_draft"
    assert value.field_name == "col_a"

    with pytest.raises(ValidationError) as missing_table:
        validate_record_input({"save_mode": "draft", "report_process_code": "pbc", "field_name": "col_a"})
    assert "table_name" in missing_table.value.fields

    with pytest.raises(ValidationError) as missing_field:
        validate_record_input({"save_mode": "draft", "report_process_code": "pbc", "table_name": "t_draft"})
    assert "field_name" in missing_field.value.fields


def test_validator_accepts_multi_report_process_codes():
    from auto_check.modules.report_special_processing.validator import validate_record_input

    payload = _payload()
    payload.pop("report_process_code", None)
    payload["report_process_codes"] = ["pbc", "east5"]
    value = validate_record_input(payload)
    assert value.report_process_codes == ("pbc", "east5")
    assert value.report_process_code == "pbc"


def test_validate_record_input_requires_dimension_fields_for_formal_save():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import validate_record_input

    with pytest.raises(ValidationError) as exc:
        validate_record_input({
            "save_mode": "record",
            "report_process_codes": ["p1"],
            "report_period": "2026-07-31",
            "summary": "s" * 10,
            "handler_user_id": "u1",
            "special_handling_at": "2026-07-31T10:00:00+08:00",
        })
    assert "dimension" in exc.value.fields


def test_summary_allows_128_chars_rejects_129():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import validate_record_input

    payload = _payload(summary="字" * 128)
    assert validate_record_input(payload).summary == "字" * 128
    with pytest.raises(ValidationError):
        validate_record_input({**payload, "summary": "字" * 129})


@pytest.mark.parametrize(
    "payload",
    [
        _payload(processing_script="汉" * 174763),
        _payload(report_period="2026-02-30"),
        _payload(special_handling_at="2026-08-01T15:32:18"),
        _payload(summary="x" * 129),
        _payload(dimension="unknown"),
        _payload(table_name="t" * 129),
        _payload(field_name="f" * 129),
        _payload(value_before="b" * 129),
        _payload(value_after="a" * 129),
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
    owned = {**record, "governance_owner_user_id": "8"}
    assert can_confirm(confirmer, owned) and not can_confirm(creator, owned)
    assert can_confirm(admin, owned)
    assert not can_confirm(confirmer)


def test_can_confirm_requires_capability_and_governance_owner():
    from auto_check.modules.report_special_processing.permissions import can_confirm

    record = {"governance_owner_user_id": "owner-1", "status": "pending"}
    assert can_confirm({"id": "owner-1", "role": "user", "capabilities": ["rsp.confirm"]}, record)
    assert not can_confirm({"id": "other", "role": "user", "capabilities": ["rsp.confirm"]}, record)
    assert can_confirm({"id": "admin", "role": "admin", "capabilities": ["rsp.confirm"]}, record)


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


# ---------------------------------------------------------------------------
# 记录附件输入契约与文件校验（图片 / Excel / Word / ZIP）
# ---------------------------------------------------------------------------

import base64 as _b64
import io as _io
import zipfile as _zipfile


def _valid_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _valid_jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 24


def _valid_webp() -> bytes:
    return b"RIFF\x10\x00\x00\x00WEBP" + b"\x00" * 16


def _valid_ole() -> bytes:
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 24


def _ooxml_bytes(marker_dir: str, extra=None) -> bytes:
    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
        archive.writestr(marker_dir + "entry.xml", "<x/>")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _valid_xlsx() -> bytes:
    return _ooxml_bytes("xl/")


def _valid_docx() -> bytes:
    return _ooxml_bytes("word/")


def _valid_zip() -> bytes:
    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.txt", "hello")
    return buffer.getvalue()


def _file(file_name: str, content: bytes, client_id: str = "local-1", content_type: str = "application/octet-stream") -> dict:
    return {
        "client_id": client_id,
        "file_name": file_name,
        "content_type": content_type,
        "data_base64": _b64.b64encode(content).decode("ascii"),
    }


def _attachments_payload(retained=None, files=None) -> dict:
    return {"record_attachments": {"retained_ids": retained or [], "new_files": files or []}}


def test_record_attachment_change_accepts_supported_files():
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    payload = _attachments_payload(files=[_file("证据.png", _valid_png())])
    change = validate_record_attachment_change(payload, creating=True)
    assert change.retained_ids == ()
    assert change.new_files[0].file_name == "证据.png"
    assert change.new_files[0].content_type == "image/png"
    assert change.new_files[0].content == _valid_png()
    assert len(change.new_files[0].content_sha256) == 64
    assert change.new_files[0].byte_size == len(_valid_png())


@pytest.mark.parametrize(
    "file_name,content,content_type",
    [
        ("a.png", _valid_png(), "image/png"),
        ("a.jpg", _valid_jpeg(), "image/jpeg"),
        ("a.jpeg", _valid_jpeg(), "image/jpeg"),
        ("a.webp", _valid_webp(), "image/webp"),
        ("a.xls", _valid_ole(), "application/x-ole-storage"),
        ("a.doc", _valid_ole(), "application/x-ole-storage"),
        ("a.xlsx", _valid_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("a.docx", _valid_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("a.zip", _valid_zip(), "application/zip"),
    ],
)
def test_record_attachment_accepts_each_allowed_type(file_name, content, content_type):
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    change = validate_record_attachment_change(
        _attachments_payload(files=[_file(file_name, content)]), creating=True
    )
    assert change.new_files[0].content_type == content_type
    assert change.new_files[0].file_extension == file_name[file_name.rfind(".") :].lower()


def test_record_attachment_omitted_field_returns_none():
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    assert validate_record_attachment_change({}, creating=True) is None
    assert validate_record_attachment_change({"save_mode": "record"}, creating=False) is None


def test_record_attachment_creating_empty_set_is_allowed():
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    change = validate_record_attachment_change(_attachments_payload(), creating=True)
    assert change.retained_ids == ()
    assert change.new_files == ()


def test_record_attachment_requires_both_arrays_explicitly():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    for bad in (
        {"record_attachments": {}},
        {"record_attachments": {"retained_ids": []}},
        {"record_attachments": {"new_files": []}},
        {"record_attachments": {"retained_ids": [], "new_files": [], "extra": 1}},
        {"record_attachments": "not-a-mapping"},
        {"record_attachments": []},
    ):
        with pytest.raises(ValidationError):
            validate_record_attachment_change(bad, creating=False)


def test_record_attachment_rejects_duplicate_or_invalid_retained_ids():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(retained=[1, 1]), creating=False)
    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(retained=[0]), creating=False)
    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(retained=["1"]), creating=False)


def test_record_attachment_creating_cannot_retain_existing():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(retained=[1]), creating=True)


def test_record_attachment_sanitizes_path_file_name():
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    change = validate_record_attachment_change(
        _attachments_payload(files=[_file("../../etc/passwd.png", _valid_png())]), creating=True
    )
    assert change.new_files[0].file_name == "passwd.png"


def test_record_attachment_rejects_invalid_base64_and_empty():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    bad = _file("a.png", _valid_png())
    bad["data_base64"] = "!!!not-base64!!!"
    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(files=[bad]), creating=True)
    empty = _file("a.png", b"")
    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(files=[empty]), creating=True)


@pytest.mark.parametrize(
    "file_name,content",
    [
        ("a.png", _valid_jpeg()),  # 扩展名与魔数不匹配
        ("a.svg", b"<svg></svg>"),
        ("a.xlsm", _ooxml_bytes("xl/", {"xl/vbaProject.bin": "x"})),
        ("a.docm", _ooxml_bytes("word/", {"word/vbaProject.bin": "x"})),
        ("a.rar", b"Rar!\x1a\x07"),
        ("a.7z", b"7z\xbc\xaf\x27\x1c"),
        ("a.exe", b"MZ\x90\x00"),
    ],
)
def test_record_attachment_rejects_disallowed_types(file_name, content):
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(files=[_file(file_name, content)]), creating=True)


def test_record_attachment_rejects_corrupt_zip_and_wrong_ooxml_dir():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    with pytest.raises(ValidationError):
        validate_record_attachment_change(
            _attachments_payload(files=[_file("a.zip", b"not a zip")]), creating=True
        )
    # xlsx 扩展名但容器内没有 xl/ 目录。
    with pytest.raises(ValidationError):
        validate_record_attachment_change(
            _attachments_payload(files=[_file("a.xlsx", _valid_docx())]), creating=True
        )


def test_record_attachment_rejects_macro_content_type():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types><Override ContentType="application/vnd.ms-excel.sheet.macroEnabled.12"/></Types>',
        )
        archive.writestr("xl/entry.xml", "<x/>")
    macro = buffer.getvalue()
    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(files=[_file("a.xlsx", macro)]), creating=True)


def test_record_attachment_rejects_same_batch_duplicate_hash():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    dup = [
        _file("a.png", _valid_png(), client_id="c1"),
        _file("b.png", _valid_png(), client_id="c2"),
    ]
    with pytest.raises(ValidationError):
        validate_record_attachment_change(_attachments_payload(files=dup), creating=True)
    # 同名不同内容允许（相同类型、不同字节、不同哈希）。
    ok = [
        _file("a.png", _valid_png(), client_id="c1"),
        _file("a.png", _valid_png() + b"more-bytes", client_id="c2"),
    ]
    change = validate_record_attachment_change(_attachments_payload(files=ok), creating=True)
    assert len(change.new_files) == 2


def test_record_attachment_single_file_size_boundary():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        MAX_RECORD_ATTACHMENT_BYTES,
        validate_record_attachment_change,
    )

    # ZIP 容器包裹大内容，构造恰好 10 MiB 的合法文件较复杂，这里用 ole 二进制直接验证边界。
    at_limit = _valid_ole() + b"\x01" * (MAX_RECORD_ATTACHMENT_BYTES - len(_valid_ole()))
    change = validate_record_attachment_change(
        _attachments_payload(files=[_file("big.xls", at_limit)]), creating=True
    )
    assert change.new_files[0].byte_size == MAX_RECORD_ATTACHMENT_BYTES
    over = at_limit + b"\x01"
    with pytest.raises(ValidationError):
        validate_record_attachment_change(
            _attachments_payload(files=[_file("big.xls", over)]), creating=True
        )


def test_record_attachment_count_limit_includes_retained():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    files = [
        _file(f"f{i}.png", _valid_png() + bytes([i]), client_id=f"c{i}") for i in range(9)
    ]
    # 9 新 + 1 保留 = 10，允许。
    change = validate_record_attachment_change(
        _attachments_payload(retained=[100], files=files), creating=False
    )
    assert len(change.new_files) == 9
    # 9 新 + 2 保留 = 11，拒绝。
    with pytest.raises(ValidationError):
        validate_record_attachment_change(
            _attachments_payload(retained=[100, 101], files=files), creating=False
        )


def _corrupt_crc_xlsx() -> bytes:
    """构造中央目录完好、但成员压缩数据 CRC 损坏的 xlsx。"""
    import os as _os

    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w", compression=_zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", _os.urandom(300).hex())
        archive.writestr("xl/workbook.xml", "<x/>")
    raw = bytearray(buffer.getvalue())
    # 第一个成员的本地头约 49 字节，其后为存储数据；在数据区中部翻转一位破坏 CRC。
    raw[120] ^= 0xFF
    return bytes(raw)


def test_record_attachment_rejects_crc_corrupted_ooxml_member():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    with pytest.raises(ValidationError):
        validate_record_attachment_change(
            _attachments_payload(files=[_file("broken.xlsx", _corrupt_crc_xlsx())]),
            creating=True,
        )


def test_record_attachment_converts_encrypted_member_error_to_validation_error(monkeypatch):
    import zipfile as zipfile_module

    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing import validator
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    class _EncryptedArchive:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def namelist(self):
            return ["[Content_Types].xml", "xl/workbook.xml"]

        def getinfo(self, name):
            class _Info:
                file_size = 10
            return _Info()

        def read(self, name):
            raise RuntimeError(f"File {name} is encrypted")

    content = _valid_xlsx()  # 必须在 monkeypatch 之前构造真实 zip
    monkeypatch.setattr(zipfile_module, "ZipFile", lambda *a, **k: _EncryptedArchive())
    monkeypatch.setattr(validator, "zipfile", zipfile_module)
    with pytest.raises(ValidationError):
        validate_record_attachment_change(
            _attachments_payload(files=[_file("secret.xlsx", content)]),
            creating=True,
        )


def test_record_attachment_does_not_mask_unexpected_program_errors(monkeypatch):
    import zipfile as zipfile_module

    from auto_check.modules.report_special_processing import validator
    from auto_check.modules.report_special_processing.validator import (
        validate_record_attachment_change,
    )

    class _BrokenArchive:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def namelist(self):
            raise TypeError("programmer error")

    content = _valid_xlsx()  # 必须在 monkeypatch 之前构造真实 zip
    monkeypatch.setattr(zipfile_module, "ZipFile", lambda *a, **k: _BrokenArchive())
    monkeypatch.setattr(validator, "zipfile", zipfile_module)
    with pytest.raises(TypeError):
        validate_record_attachment_change(
            _attachments_payload(files=[_file("weird.xlsx", content)]),
            creating=True,
        )


def test_attachment_base64_decoding_is_strict():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    from auto_check.modules.report_special_processing.validator import (
        _decode_attachment_base64,
    )

    assert _decode_attachment_base64("YQ==", "k") == b"a"
    for bad in ("Y Q", "YQ==\n", "YQ", "!!!!"):
        with pytest.raises(ValidationError):
            _decode_attachment_base64(bad, "k")
