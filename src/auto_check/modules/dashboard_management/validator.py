from __future__ import annotations

import re
from typing import Any, Mapping

from .storage import BOARD_CODES


FIELD_VALUE_TYPES = frozenset({"string", "integer", "decimal", "boolean", "date", "datetime"})
FIELD_ALIAS_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
REGION_SHAPES = frozenset({"scalar", "list"})


class DomainError(RuntimeError):
    status = 400
    code = "invalid_request"
    message = "请求参数无效"

    def __init__(self, message: str | None = None, *, fields: Mapping[str, str] | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.fields = dict(fields or {})


class ValidationError(DomainError):
    pass


class NotFoundError(DomainError):
    status = 404
    code = "resource_not_found"
    message = "资源不存在"


class ConflictError(DomainError):
    status = 409
    code = "version_conflict"
    message = "数据已被其他操作更新，请刷新后重试"


def _error(field: str, message: str) -> ValidationError:
    return ValidationError(message, fields={field: message})


def _mapping(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValidationError()
    return payload


def _text(value: Any, field: str, maximum: int, *, required: bool) -> str:
    if value is None:
        if required:
            raise _error(field, f"{field}不能为空")
        return ""
    if not isinstance(value, str):
        raise _error(field, f"{field}无效")
    normalized = value.strip()
    if required and not normalized:
        raise _error(field, f"{field}不能为空")
    if len(normalized) > maximum:
        raise _error(field, f"{field}最多 {maximum} 个字符")
    return normalized


def _order(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 9999:
        raise _error("display_order", "显示顺序必须为 0 至 9999 的整数")
    return value


def _version(payload: Mapping[str, Any]) -> int:
    value = payload.get("row_version")
    if type(value) is not int or value < 1:
        raise _error("row_version", "版本号无效")
    return value


def _boolean(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise _error(field, f"{field}无效")
    return value


def validate_board_code(board_code: str) -> str:
    if not isinstance(board_code, str) or board_code not in BOARD_CODES:
        raise ValidationError("不支持的固定看板编码", fields={"board_code": "不支持的固定看板编码"})
    return board_code


def validate_create_region(payload: Mapping[str, Any]) -> dict[str, Any]:
    values = _mapping(payload)
    allowed = {"name", "shape", "enabled", "display_order", "description", "fields"}
    if any(key not in allowed for key in values):
        raise ValidationError()
    shape = values.get("shape")
    if shape not in REGION_SHAPES:
        raise _error("shape", "数据形态无效")
    raw_fields = values.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise _error("fields", "至少需要一个启用字段")
    fields = [validate_create_field(item) for item in raw_fields]
    if not any(field["enabled"] for field in fields):
        raise _error("fields", "至少需要一个启用字段")
    aliases = [field["field_alias"] for field in fields]
    if len(set(aliases)) != len(aliases):
        raise _error("fields", "首批字段别名不能重复")
    return {
        "name": _text(values.get("name"), "数据区域名称", 100, required=True),
        "shape": shape,
        "enabled": _boolean(values.get("enabled", True), "enabled"),
        "display_order": _order(values.get("display_order")),
        "description": _text(values.get("description", ""), "description", 500, required=False),
        "fields": fields,
    }


def validate_update_region(payload: Mapping[str, Any], existing: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    values = _mapping(payload)
    allowed = {"name", "region_code", "shape", "enabled", "display_order", "description", "row_version"}
    if any(key not in allowed for key in values):
        raise ValidationError()
    if "region_code" in values and values["region_code"] != existing["region_code"]:
        if existing["built_in"]:
            raise _error("region_code", "内置数据区域编码不可修改")
        raise _error("region_code", "数据区域编码创建后不可修改")
    if "shape" in values:
        if values["shape"] not in REGION_SHAPES:
            raise _error("shape", "数据形态无效")
        if existing["built_in"] and values["shape"] != existing["shape"]:
            raise _error("shape", "内置数据区域形态不可修改")
    changes: dict[str, Any] = {}
    if "name" in values:
        changes["name"] = _text(values["name"], "数据区域名称", 100, required=True)
    if "shape" in values:
        changes["shape"] = values["shape"]
    if "enabled" in values:
        changes["enabled"] = _boolean(values["enabled"], "enabled")
    if "display_order" in values:
        changes["display_order"] = _order(values["display_order"])
    if "description" in values:
        changes["description"] = _text(values["description"], "description", 500, required=False)
    return changes, _version(values)


def validate_create_field(payload: Mapping[str, Any]) -> dict[str, Any]:
    values = _mapping(payload)
    allowed = {"field_alias", "name", "value_type", "nullable", "enabled", "display_order", "description"}
    if any(key not in allowed for key in values):
        raise ValidationError()
    alias = values.get("field_alias")
    if not isinstance(alias, str) or FIELD_ALIAS_PATTERN.fullmatch(alias) is None:
        raise _error("field_alias", "字段别名必须为小写字母开头的 snake_case")
    value_type = values.get("value_type")
    if value_type not in FIELD_VALUE_TYPES:
        raise _error("value_type", "字段类型无效")
    return {
        "field_alias": alias,
        "name": _text(values.get("name"), "字段名称", 100, required=True),
        "value_type": value_type,
        "nullable": _boolean(values.get("nullable"), "nullable"),
        "enabled": _boolean(values.get("enabled", True), "enabled"),
        "display_order": _order(values.get("display_order")),
        "description": _text(values.get("description", ""), "description", 500, required=False),
    }


def validate_update_field(payload: Mapping[str, Any], existing: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    values = _mapping(payload)
    allowed = {"field_alias", "name", "value_type", "nullable", "enabled", "display_order", "description", "row_version"}
    if any(key not in allowed for key in values):
        raise ValidationError()
    if "field_alias" in values and values["field_alias"] != existing["field_alias"]:
        if existing["built_in"]:
            raise _error("field_alias", "内置字段别名不可修改")
        raise _error("field_alias", "字段别名创建后不可修改")
    if "value_type" in values:
        if values["value_type"] not in FIELD_VALUE_TYPES:
            raise _error("value_type", "字段类型无效")
        if existing["built_in"] and values["value_type"] != existing["value_type"]:
            raise _error("value_type", "内置字段类型不可修改")
    changes: dict[str, Any] = {}
    if "name" in values:
        changes["name"] = _text(values["name"], "字段名称", 100, required=True)
    if "value_type" in values:
        changes["value_type"] = values["value_type"]
    if "nullable" in values:
        changes["nullable"] = _boolean(values["nullable"], "nullable")
    if "enabled" in values:
        changes["enabled"] = _boolean(values["enabled"], "enabled")
    if "display_order" in values:
        changes["display_order"] = _order(values["display_order"])
    if "description" in values:
        changes["description"] = _text(values["description"], "description", 500, required=False)
    return changes, _version(values)
