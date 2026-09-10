from __future__ import annotations

import base64
import binascii
import hashlib
import io
import zipfile
from datetime import date, datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .contracts import (
    DIMENSIONS,
    PageQuery,
    RecordAttachmentChange,
    RecordAttachmentFile,
    RecordInput,
    RecordStatus,
    ValidationError,
)
from .structured_content import (
    StructuredContentError,
    derive_field_name,
    derive_table_name,
    derive_value_after,
    derive_value_before,
    parse_structured_content,
    validate_formal_values,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_REPORTS = 50
MAX_PROCESSES = 20
MAX_SCRIPT_BYTES = 512 * 1024
MAX_REQUEST_BYTES = 1024 * 1024
MAX_CONFIRM_IMAGES = 3
MAX_CONFIRM_IMAGE_BYTES = 2 * 1024 * 1024
MAX_CONFIRM_STATUS_BYTES = 10 * 1024 * 1024
ALLOWED_CONFIRM_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_WEBP_RIFF = b"RIFF"
_WEBP_TYPE = b"WEBP"

# ===== 记录附件（图片 / Excel / Word / ZIP）校验常量 =====
MAX_RECORD_ATTACHMENTS = 10
MAX_RECORD_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_RECORD_ATTACHMENTS_TOTAL_BYTES = 30 * 1024 * 1024
MAX_RECORD_ATTACHMENT_REQUEST_BYTES = 45 * 1024 * 1024
MAX_RECORD_ATTACHMENT_FILE_NAME_CHARS = 255
MAX_OOXML_ENTRIES = 5000
MAX_OOXML_CONTENT_TYPES_BYTES = 1024 * 1024
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# 扩展名 -> 分类；服务端按魔数/容器校验后写回规范化 MIME，不信任客户端声明。
ATTACHMENT_EXTENSION_KINDS = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".xls": "ole",
    ".doc": "ole",
    ".xlsx": "ooxml",
    ".docx": "ooxml",
    ".zip": "zip",
}
ALLOWED_ATTACHMENT_EXTENSIONS = tuple(sorted(ATTACHMENT_EXTENSION_KINDS))
_EXPECTED_IMAGE_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_OOXML_CONTENT_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_OOXML_MARKER_DIRS = {".xlsx": "xl/", ".docx": "word/"}
SORTS = frozenset(
    {"special_handling_at_desc", "updated_at_desc", "created_at_desc"}
)
_RECORD_FIELDS = frozenset(
    {
        "save_mode",
        "report_process_code",
        "report_process_codes",
        "report_period",
        "reports",
        "summary",
        "processing_content",
        "processing_script",
        "special_handling_at",
        "handler_user_id",
        "row_version",
        "dimension",
        "business_system_code",
        "governance_owner_user_id",
        "table_name",
        "field_name",
        "value_before",
        "value_after",
        "structured_content",
        "datasource_name_snapshot",
        "record_attachments",
    }
)


def _error(field: str, message: str = "字段无效") -> ValidationError:
    return ValidationError(fields={field: message})


def _text(value: Any, field: str, maximum: int, *, required: bool) -> str:
    if value is None:
        if required:
            raise _error(field, "不能为空")
        return ""
    if not isinstance(value, str):
        raise _error(field)
    normalized = value.strip()
    if required and not normalized:
        raise _error(field, "不能为空")
    if len(normalized) > maximum:
        raise _error(field, f"最多 {maximum} 个字符")
    return normalized


def _optional_date(value: Any, field: str, *, required: bool) -> date | None:
    if value is None or value == "":
        if required:
            raise _error(field, "不能为空")
        return None
    if not isinstance(value, str):
        raise _error(field)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _error(field, "日期格式无效") from None


def _optional_datetime(value: Any, field: str, *, required: bool) -> datetime | None:
    if value is None or value == "":
        if required:
            raise _error(field, "不能为空")
        return None
    if not isinstance(value, str):
        raise _error(field)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _error(field, "时间格式无效") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(field, "时间必须包含时区")
    return parsed.astimezone(SHANGHAI)


def _process_codes(payload: Mapping[str, Any]) -> tuple[str, ...]:
    raw = payload.get("report_process_codes", None)
    if raw is None and "report_process_code" in payload:
        single = payload.get("report_process_code")
        raw = [single] if single not in {None, ""} else []
    if raw is None:
        raw = []
    if not isinstance(raw, list) or len(raw) > MAX_PROCESSES:
        raise _error("report_process_codes")
    codes: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise _error("report_process_codes")
        code = item.strip()
        if not code or len(code) > 64:
            raise _error("report_process_codes")
        codes.append(code)
    if not codes:
        raise _error("report_process_codes", "至少选择一项")
    if len(set(codes)) != len(codes):
        raise _error("report_process_codes", "关联报送不能重复")
    return tuple(codes)


def _optional_dimension(value: Any, *, required: bool) -> str | None:
    if value is None or value == "":
        if required:
            raise _error("dimension", "不能为空")
        return None
    if not isinstance(value, str) or value not in DIMENSIONS:
        raise _error("dimension")
    return value


def _optional_text_field(
    value: Any, field: str, maximum: int, *, required: bool
) -> str | None:
    text = _text(value, field, maximum, required=required)
    return text or None


def validate_record_input(payload: Mapping[str, Any]) -> RecordInput:
    if not isinstance(payload, Mapping) or any(key not in _RECORD_FIELDS for key in payload):
        raise ValidationError()
    save_mode = payload.get("save_mode")
    if save_mode not in {"draft", "record"}:
        raise _error("save_mode")
    formal = save_mode == "record"
    process_codes = _process_codes(payload)
    script = payload.get("processing_script")
    if script is None or script == "":
        script = None
    elif not isinstance(script, str) or len(script.encode("utf-8")) > MAX_SCRIPT_BYTES:
        raise _error("processing_script", "脚本最大 512 KiB")
    handler = _text(payload.get("handler_user_id"), "handler_user_id", 64, required=formal) or None
    row_version = payload.get("row_version")
    if row_version is not None and (type(row_version) is not int or row_version < 1):
        raise _error("row_version")
    # 结构化内容（数据源→表→字段→修改前/后）：存在时以它为准派生兼容字符串，
    # 客户端自报的 table_name/field_name/value_before/value_after 不再生效；
    # 不存在时保持历史手工录入路径的全部既有校验。
    structured = None
    structured_raw = payload.get("structured_content")
    if structured_raw is not None:
        try:
            structured = parse_structured_content(structured_raw)
            if formal:
                # 正式保存：每个字段的修改前/修改后必填，错误定位到具体字段。
                validate_formal_values(structured)
        except StructuredContentError as exc:
            raise ValidationError(fields=exc.fields) from None
    datasource_name_snapshot = _optional_text_field(
        payload.get("datasource_name_snapshot"), "datasource_name_snapshot", 200, required=False
    )
    if structured is not None:
        table_name = derive_table_name(structured)
        field_name = derive_field_name(structured)
        value_before = derive_value_before(structured)
        value_after = derive_value_after(structured)
    else:
        table_name = _optional_text_field(payload.get("table_name"), "table_name", 4096, required=True)
        field_name = _optional_text_field(payload.get("field_name"), "field_name", 4096, required=True)
        value_before = _optional_text_field(
            payload.get("value_before"), "value_before", 128, required=formal
        )
        value_after = _optional_text_field(
            payload.get("value_after"), "value_after", 128, required=formal
        )
    return RecordInput(
        save_mode=save_mode,
        report_process_codes=process_codes,
        reports=(),
        summary=_text(payload.get("summary"), "summary", 128, required=formal),
        processing_content="",
        processing_script=script,
        report_period=_optional_date(payload.get("report_period"), "report_period", required=formal),
        special_handling_at=_optional_datetime(
            payload.get("special_handling_at"), "special_handling_at", required=formal
        ),
        handler_user_id=handler,
        row_version=row_version,
        dimension=_optional_dimension(payload.get("dimension"), required=formal),
        business_system_code=_optional_text_field(
            payload.get("business_system_code"), "business_system_code", 64, required=formal
        ),
        governance_owner_user_id=_optional_text_field(
            payload.get("governance_owner_user_id"),
            "governance_owner_user_id",
            64,
            required=formal,
        ),
        table_name=table_name,
        field_name=field_name,
        value_before=value_before,
        value_after=value_after,
        structured_content=structured,
        datasource_name_snapshot=datasource_name_snapshot,
    )


def validate_page_query(query: Mapping[str, str]) -> PageQuery:
    try:
        page = int(query.get("page", "1"))
        page_size = int(query.get("page_size", "10"))
    except (TypeError, ValueError):
        raise ValidationError() from None
    sort = str(query.get("sort", "special_handling_at_desc"))
    if page < 1 or not 1 <= page_size <= 100 or sort not in SORTS:
        raise ValidationError()
    keyword = str(query.get("keyword", "")).strip()
    if len(keyword) > 100:
        raise _error("keyword")
    filters = {
        key: value
        for key in (
            "report_process_code",
            "report_period",
            "status",
            "handler_user_id",
            "keyword",
            "special_handling_from",
            "special_handling_to",
        )
        if (value := query.get(key)) not in {None, ""}
    }
    if "status" in filters and filters["status"] not in {item.value for item in RecordStatus}:
        raise _error("status")
    return PageQuery(page=page, page_size=page_size, sort=sort, filters=filters)


def validate_action(
    payload: Mapping[str, Any],
    *,
    require_reason: bool = False,
    reason_max_length: int = 500,
) -> tuple[int, str]:
    if not isinstance(payload, Mapping):
        raise ValidationError()
    version = payload.get("row_version")
    if type(version) is not int or version < 1:
        raise _error("row_version")
    maximum = max(1, int(reason_max_length))
    reason = _text(payload.get("reason"), "reason", maximum, required=require_reason)
    return version, reason


def _detect_confirm_image_type(content: bytes) -> str | None:
    if content.startswith(_PNG_MAGIC):
        return "image/png"
    if content.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == _WEBP_RIFF and content[8:12] == _WEBP_TYPE:
        return "image/webp"
    return None


def _decode_confirm_image_base64(raw: Any) -> bytes:
    if not isinstance(raw, str) or not raw.strip():
        raise _error("confirm_images", "图片内容无效")
    payload = raw.strip()
    if payload.lower().startswith("data:"):
        comma = payload.find(",")
        if comma < 0:
            raise _error("confirm_images", "图片内容无效")
        payload = payload[comma + 1 :]
    payload = "".join(payload.split())
    padding = (-len(payload)) % 4
    if padding:
        payload += "=" * padding
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise _error("confirm_images", "图片内容无效") from None


def validate_confirm_images(raw: Any) -> tuple[dict[str, Any], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise _error("confirm_images")
    if len(raw) > MAX_CONFIRM_IMAGES:
        raise _error("confirm_images", "最多粘贴 3 张图片")
    images: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise _error("confirm_images")
        content = _decode_confirm_image_base64(item.get("data_base64"))
        if len(content) > MAX_CONFIRM_IMAGE_BYTES:
            raise _error("confirm_images", "单张图片最大 2 MiB")
        detected = _detect_confirm_image_type(content)
        if detected is None or detected not in ALLOWED_CONFIRM_IMAGE_TYPES:
            raise _error("confirm_images", "仅支持 PNG、JPEG、WebP 图片")
        images.append({"content_type": detected, "content": content})
    return tuple(images)


# ===== 记录附件校验 =====
# 省略语义：省略整个字段返回 None；一旦提供，必须显式给出 retained_ids 与
# new_files 两个数组；``([], [])`` 表示清空当前附件。


def validate_record_attachment_change(
    payload: Mapping[str, Any], *, creating: bool
) -> RecordAttachmentChange | None:
    if "record_attachments" not in payload:
        return None
    raw = payload["record_attachments"]
    if not isinstance(raw, Mapping) or set(raw) != {"retained_ids", "new_files"}:
        raise _error("record_attachments", "附件参数不完整")
    retained_ids = _validate_retained_attachment_ids(raw["retained_ids"])
    if creating and retained_ids:
        raise _error("record_attachments", "新建记录不能引用已有附件")
    raw_files = raw["new_files"]
    if not isinstance(raw_files, list):
        raise _error("record_attachments", "附件参数不完整")
    new_files = tuple(_validate_record_attachment_file(item) for item in raw_files)
    seen_hashes: set[str] = set()
    for item in new_files:
        if item.content_sha256 in seen_hashes:
            raise _error(f"record_attachments.{item.client_id}", "该附件已添加")
        seen_hashes.add(item.content_sha256)
    if len(retained_ids) + len(new_files) > MAX_RECORD_ATTACHMENTS:
        raise _error("record_attachments", f"每条记录最多 {MAX_RECORD_ATTACHMENTS} 个附件")
    return RecordAttachmentChange(retained_ids, new_files)


def _validate_retained_attachment_ids(raw: Any) -> tuple[int, ...]:
    if not isinstance(raw, list):
        raise _error("record_attachments", "附件参数不完整")
    ids: list[int] = []
    seen: set[int] = set()
    for item in raw:
        if type(item) is not int or item < 1:
            raise _error("record_attachments", "附件引用无效")
        if item in seen:
            raise _error("record_attachments", "附件引用重复")
        seen.add(item)
        ids.append(item)
    return tuple(ids)


def _validate_record_attachment_file(item: Any) -> RecordAttachmentFile:
    if not isinstance(item, Mapping) or set(item) != {
        "client_id",
        "file_name",
        "content_type",
        "data_base64",
    }:
        raise _error("record_attachments", "附件内容无效")
    client_id = item.get("client_id")
    if not isinstance(client_id, str) or not client_id.strip() or len(client_id.strip()) > 64:
        raise _error("record_attachments", "附件内容无效")
    client_id = client_id.strip()
    field_key = f"record_attachments.{client_id}"
    file_name = _sanitize_attachment_file_name(item.get("file_name"), field_key)
    extension = _attachment_extension(file_name, field_key)
    content = _decode_attachment_base64(item.get("data_base64"), field_key)
    if len(content) > MAX_RECORD_ATTACHMENT_BYTES:
        raise _error(field_key, "单个附件最大 10 MiB")
    content_type = _validate_attachment_content(extension, content, field_key)
    content_sha256 = hashlib.sha256(content).hexdigest()
    return RecordAttachmentFile(
        client_id=client_id,
        file_name=file_name,
        file_extension=extension,
        content_type=content_type,
        content=content,
        content_sha256=content_sha256,
    )


def _sanitize_attachment_file_name(raw: Any, field_key: str) -> str:
    if not isinstance(raw, str):
        raise _error(field_key, "文件名无效")
    # basename 语义：去除路径分隔符之前的部分。
    name = raw.replace("\\", "/").split("/")[-1]
    # 去除 NUL、控制字符与删除符。
    name = "".join(ch for ch in name if ord(ch) >= 32 and ord(ch) != 127)
    name = name.strip()
    if not name or len(name) > MAX_RECORD_ATTACHMENT_FILE_NAME_CHARS:
        raise _error(field_key, "文件名无效")
    return name


def _attachment_extension(file_name: str, field_key: str) -> str:
    dot = file_name.rfind(".")
    if dot <= 0 or dot == len(file_name) - 1:
        raise _error(field_key, "不支持的附件类型")
    extension = file_name[dot:].lower()
    if extension not in ATTACHMENT_EXTENSION_KINDS:
        raise _error(field_key, "不支持的附件类型")
    return extension


def _decode_attachment_base64(raw: Any, field_key: str) -> bytes:
    # 严格解码：不剥离空白、不自动补 padding，非规范编码一律拒绝。
    if not isinstance(raw, str) or not raw:
        raise _error(field_key, "附件内容无效")
    try:
        content = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise _error(field_key, "附件内容无效") from None
    if not content:
        raise _error(field_key, "附件内容无效")
    return content


def _validate_attachment_content(extension: str, content: bytes, field_key: str) -> str:
    kind = ATTACHMENT_EXTENSION_KINDS[extension]
    if kind == "image":
        detected = _detect_confirm_image_type(content)
        if detected is None or detected != _EXPECTED_IMAGE_TYPE[extension]:
            raise _error(field_key, "图片内容与类型不匹配")
        return detected
    if kind == "ole":
        if not content.startswith(_OLE_MAGIC):
            raise _error(field_key, "文件内容无效")
        return "application/x-ole-storage"
    if kind == "ooxml":
        return _validate_ooxml_content(extension, content, field_key)
    # zip：仅校验容器结构，不解压成员正文、不执行任何内容。
    _validate_zip_container(content, field_key)
    return "application/zip"


def _validate_zip_container(content: bytes, field_key: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            archive.namelist()
    except zipfile.BadZipFile:
        raise _error(field_key, "文件内容无效") from None


def _validate_ooxml_content(extension: str, content: bytes, field_key: str) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise _error(field_key, "文件内容无效") from None
    # 成员读取阶段（目录/CRC/加密/压缩方式）的预期输入错误统一转为字段校验错误；
    # 其他异常（程序/数据库错误）不捕获、不伪装。
    try:
        with archive:
            entries = archive.namelist()
            if len(entries) > MAX_OOXML_ENTRIES:
                raise _error(field_key, "文件内容无效")
            lowered = [name.lower() for name in entries]
            if any("vbaproject.bin" in name for name in lowered):
                raise _error(field_key, "不支持宏启用文件")
            if "[content_types].xml" not in lowered:
                raise _error(field_key, "文件内容无效")
            content_types_name = next(
                name for name in entries if name.lower() == "[content_types].xml"
            )
            info = archive.getinfo(content_types_name)
            if info.file_size > MAX_OOXML_CONTENT_TYPES_BYTES:
                raise _error(field_key, "文件内容无效")
            content_types = archive.read(content_types_name).decode("utf-8", "ignore").lower()
            if "macroenabled" in content_types:
                raise _error(field_key, "不支持宏启用文件")
            marker = _OOXML_MARKER_DIRS[extension]
            if not any(name.lower().startswith(marker) for name in entries):
                raise _error(field_key, "文件内容无效")
    except zipfile.BadZipFile:
        raise _error(field_key, "文件内容无效或已损坏") from None
    except (zipfile.LargeZipFile, RuntimeError, NotImplementedError):
        raise _error(field_key, "不支持加密或该压缩方式的容器") from None
    return _OOXML_CONTENT_TYPES[extension]
