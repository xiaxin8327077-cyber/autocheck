"""系统字典的应用库存取（字典分类 + 字典项）。

平台层能力：字典分类与字典项持久化到 ``system_dictionaries`` /
``system_dictionary_items`` 两张表；分类通过 ``enabled`` 启停，字典项支持维护与删除。
业务记录使用编码与名称快照保存历史展示。业务模块不得直接访问本模块，
只能通过 ``platform.dictionary`` 只读服务消费启用项。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, TINYINT, insert as mysql_insert
from sqlalchemy.engine import Connection

_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
_ITEM_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{0,63}$")
_NAME_MAX_LEN = 100
_DESCRIPTION_MAX_LEN = 255
_SORT_MIN = 0
_SORT_MAX = 9999


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


_METADATA = MetaData()

DICTIONARIES = Table(
    "system_dictionaries",
    _METADATA,
    Column("dictionary_code", String(64), primary_key=True),
    Column("dictionary_name", String(100), nullable=False),
    Column("description", String(255), nullable=False, default=""),
    Column("enabled", TINYINT(1), nullable=False, default=1),
    Column("system_locked", TINYINT(1), nullable=False, default=0),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("created_by", String(64), nullable=True),
    Column("created_at", DATETIME(fsp=6), nullable=False),
    Column("updated_by", String(64), nullable=True),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)

DICTIONARY_ITEMS = Table(
    "system_dictionary_items",
    _METADATA,
    Column("id", BIGINT(unsigned=True), primary_key=True, autoincrement=True),
    Column("dictionary_code", String(64), nullable=False),
    Column("item_code", String(64), nullable=False),
    Column("item_name", String(100), nullable=False),
    Column("description", String(255), nullable=False, default=""),
    Column("enabled", TINYINT(1), nullable=False, default=1),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("created_by", String(64), nullable=True),
    Column("created_at", DATETIME(fsp=6), nullable=False),
    Column("updated_by", String(64), nullable=True),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)


# ---------------------------------------------------------------- 校验辅助


def _normalize_code(value: Any, label: str) -> str:
    code = str(value or "").strip()
    if not code:
        raise ValueError(f"{label}必填")
    if not _CODE_PATTERN.fullmatch(code):
        raise ValueError(f"{label}格式不正确：仅允许小写字母、数字和下划线，最长 64 位，可使用纯数字")
    return code


def _normalize_item_code(value: Any) -> str:
    code = str(value or "").strip()
    if not code:
        raise ValueError("字典项编码必填")
    if not _ITEM_CODE_PATTERN.fullmatch(code):
        raise ValueError("字典项编码格式不正确：仅允许大小写字母、数字和下划线，最长 64 位，可使用纯数字")
    return code


def _normalize_name(value: Any, label: str) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError(f"{label}必填")
    if len(name) > _NAME_MAX_LEN:
        raise ValueError(f"{label}最长 {_NAME_MAX_LEN} 个字符")
    return name


def _normalize_description(value: Any) -> str:
    description = str(value or "").strip()
    if len(description) > _DESCRIPTION_MAX_LEN:
        raise ValueError(f"说明最长 {_DESCRIPTION_MAX_LEN} 个字符")
    return description


def _normalize_sort_order(value: Any) -> int:
    try:
        order = int(value if value is not None else 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("排序必须是整数") from exc
    if order < _SORT_MIN or order > _SORT_MAX:
        raise ValueError(f"排序必须在 {_SORT_MIN} 到 {_SORT_MAX} 之间")
    return order


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _dictionary_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": str(row.get("dictionary_code") or ""),
        "name": str(row.get("dictionary_name") or ""),
        "description": str(row.get("description") or ""),
        "enabled": _as_bool(row.get("enabled", 1)),
        "system_locked": _as_bool(row.get("system_locked", 0)),
        "sort_order": int(row.get("sort_order") or 0),
        "created_by": row.get("created_by"),
        "created_at": str(row.get("created_at") or ""),
        "updated_by": row.get("updated_by"),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _item_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "dictionary_code": str(row.get("dictionary_code") or ""),
        "code": str(row.get("item_code") or ""),
        "name": str(row.get("item_name") or ""),
        "description": str(row.get("description") or ""),
        "enabled": _as_bool(row.get("enabled", 1)),
        "sort_order": int(row.get("sort_order") or 0),
        "created_by": row.get("created_by"),
        "created_at": str(row.get("created_at") or ""),
        "updated_by": row.get("updated_by"),
        "updated_at": str(row.get("updated_at") or ""),
    }


# ---------------------------------------------------------------- 查询


def list_dictionaries(connection: Connection) -> list[dict[str, Any]]:
    """加载全部分类与字典项：分类一次查询、字典项一次查询，内存组装。"""
    dictionary_rows = connection.execute(select(DICTIONARIES)).mappings().all()
    item_rows = connection.execute(select(DICTIONARY_ITEMS)).mappings().all()
    items_by_code: dict[str, list[dict[str, Any]]] = {}
    for row in item_rows:
        item = _item_row_to_dict(dict(row))
        items_by_code.setdefault(item["dictionary_code"], []).append(item)
    entries = []
    for row in dictionary_rows:
        entry = _dictionary_row_to_dict(dict(row))
        entry["items"] = sorted(
            items_by_code.get(entry["code"], []),
            key=lambda item: (item["sort_order"], item["id"]),
        )
        entries.append(entry)
    entries.sort(key=lambda entry: (entry["sort_order"], entry["code"]))
    return entries


def list_active_dictionary_items(connection: Connection, dictionary_code: str) -> list[dict[str, Any]]:
    """返回启用分类下的启用字典项，按 ``sort_order,id`` 排序；未知分类返回空。"""
    code = str(dictionary_code or "").strip()
    dictionary_rows = connection.execute(
        select(DICTIONARIES).where(DICTIONARIES.c.dictionary_code == code)
    ).mappings().all()
    if not dictionary_rows or not _as_bool(dictionary_rows[0].get("enabled", 1)):
        return []
    item_rows = connection.execute(
        select(DICTIONARY_ITEMS).where(DICTIONARY_ITEMS.c.dictionary_code == code)
    ).mappings().all()
    items = [_item_row_to_dict(dict(row)) for row in item_rows if _as_bool(row.get("enabled", 1))]
    items.sort(key=lambda item: (item["sort_order"], item["id"]))
    return items


def get_active_dictionary_item(connection: Connection, dictionary_code: str, item_code: str) -> dict[str, Any] | None:
    """按编码取启用字典项；不存在、已停用或分类停用返回 ``None``。"""
    code = str(item_code or "").strip()
    for item in list_active_dictionary_items(connection, dictionary_code):
        if item["code"] == code:
            return item
    return None


# ---------------------------------------------------------------- 分类写入


def create_dictionary(
    connection: Connection,
    *,
    code: Any,
    name: Any,
    description: Any = "",
    enabled: Any = True,
    sort_order: Any = 0,
    system_locked: Any = False,
    updated_by: str | None = None,
) -> dict[str, Any]:
    """新增字典分类；编码重复抛 ``ValueError``。"""
    dictionary_code = _normalize_code(code, "字典编码")
    dictionary_name = _normalize_name(name, "字典名称")
    normalized_description = _normalize_description(description)
    normalized_sort = _normalize_sort_order(sort_order)
    existing = connection.execute(
        select(DICTIONARIES).where(DICTIONARIES.c.dictionary_code == dictionary_code)
    ).mappings().all()
    if existing:
        raise ValueError(f"字典编码已存在：{dictionary_code}")
    now = _utc_now()
    connection.execute(
        mysql_insert(DICTIONARIES).values(
            dictionary_code=dictionary_code,
            dictionary_name=dictionary_name,
            description=normalized_description,
            enabled=1 if _as_bool(enabled) else 0,
            system_locked=1 if _as_bool(system_locked) else 0,
            sort_order=normalized_sort,
            created_by=updated_by,
            created_at=now,
            updated_by=updated_by,
            updated_at=now,
        )
    )
    return {
        "code": dictionary_code,
        "name": dictionary_name,
        "description": normalized_description,
        "enabled": _as_bool(enabled),
        "system_locked": _as_bool(system_locked),
        "sort_order": normalized_sort,
        "created_by": updated_by,
        "created_at": str(now),
        "updated_by": updated_by,
        "updated_at": str(now),
        "items": [],
    }


def update_dictionary(
    connection: Connection,
    code: Any,
    *,
    name: Any = None,
    description: Any = None,
    enabled: Any = None,
    sort_order: Any = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    """更新字典分类的名称/说明/启停/排序；编码固定不可修改。"""
    dictionary_code = _normalize_code(code, "字典编码")
    rows = connection.execute(
        select(DICTIONARIES).where(DICTIONARIES.c.dictionary_code == dictionary_code)
    ).mappings().all()
    if not rows:
        raise ValueError(f"字典分类不存在：{dictionary_code}")
    row = dict(rows[0])
    values: dict[str, Any] = {"updated_by": updated_by, "updated_at": _utc_now()}
    if name is not None:
        values["dictionary_name"] = _normalize_name(name, "字典名称")
    if description is not None:
        values["description"] = _normalize_description(description)
    if enabled is not None:
        values["enabled"] = 1 if _as_bool(enabled) else 0
    if sort_order is not None:
        values["sort_order"] = _normalize_sort_order(sort_order)
    connection.execute(
        DICTIONARIES.update().where(DICTIONARIES.c.dictionary_code == dictionary_code).values(**values)
    )
    row.update(values)
    entry = _dictionary_row_to_dict(row)
    entry["items"] = []
    return entry


def delete_dictionary(connection: Connection, code: Any) -> None:
    """删除自定义字典及其键值；系统预置字典不可删除。"""
    dictionary_code = _normalize_code(code, "字典编码")
    rows = connection.execute(
        select(DICTIONARIES).where(DICTIONARIES.c.dictionary_code == dictionary_code)
    ).mappings().all()
    if not rows:
        raise ValueError(f"字典分类不存在：{dictionary_code}")
    if _as_bool(dict(rows[0]).get("system_locked")):
        raise ValueError("系统预置字典不可删除")
    connection.execute(
        DICTIONARY_ITEMS.delete().where(DICTIONARY_ITEMS.c.dictionary_code == dictionary_code)
    )
    connection.execute(
        DICTIONARIES.delete().where(DICTIONARIES.c.dictionary_code == dictionary_code)
    )


# ---------------------------------------------------------------- 字典项写入


def create_dictionary_item(
    connection: Connection,
    *,
    dictionary_code: Any,
    item_code: Any,
    item_name: Any,
    description: Any = "",
    enabled: Any = True,
    sort_order: Any = 0,
    updated_by: str | None = None,
) -> dict[str, Any]:
    """在指定分类下新增字典项；分类不存在或编码重复抛 ``ValueError``。"""
    parent_code = _normalize_code(dictionary_code, "字典编码")
    code = _normalize_item_code(item_code)
    name = _normalize_name(item_name, "字典项名称")
    normalized_description = _normalize_description(description)
    normalized_sort = _normalize_sort_order(sort_order)
    dictionary_rows = connection.execute(
        select(DICTIONARIES).where(DICTIONARIES.c.dictionary_code == parent_code)
    ).mappings().all()
    if not dictionary_rows:
        raise ValueError(f"字典分类不存在：{parent_code}")
    item_rows = connection.execute(
        select(DICTIONARY_ITEMS).where(DICTIONARY_ITEMS.c.dictionary_code == parent_code)
    ).mappings().all()
    if any(str(dict(row).get("item_code") or "") == code for row in item_rows):
        raise ValueError(f"字典项编码已存在：{code}")
    now = _utc_now()
    inserted = connection.execute(
        mysql_insert(DICTIONARY_ITEMS).values(
            dictionary_code=parent_code,
            item_code=code,
            item_name=name,
            description=normalized_description,
            enabled=1 if _as_bool(enabled) else 0,
            sort_order=normalized_sort,
            created_by=updated_by,
            created_at=now,
            updated_by=updated_by,
            updated_at=now,
        )
    )
    inserted_id = 0
    raw_key = inserted.inserted_primary_key[0] if inserted.inserted_primary_key else None
    if isinstance(raw_key, int):
        inserted_id = raw_key
    if not inserted_id:
        rows_after = connection.execute(
            select(DICTIONARY_ITEMS).where(DICTIONARY_ITEMS.c.dictionary_code == parent_code)
        ).mappings().all()
        inserted_id = max(
            (
                int(dict(row).get("id") or 0)
                for row in rows_after
                if str(dict(row).get("item_code") or "") == code
            ),
            default=0,
        )
    return {
        "id": inserted_id,
        "dictionary_code": parent_code,
        "code": code,
        "name": name,
        "description": normalized_description,
        "enabled": _as_bool(enabled),
        "sort_order": normalized_sort,
        "created_by": updated_by,
        "created_at": str(now),
        "updated_by": updated_by,
        "updated_at": str(now),
    }


def update_dictionary_item(
    connection: Connection,
    dictionary_code: Any,
    item_id: Any,
    *,
    item_code: Any = None,
    item_name: Any = None,
    description: Any = None,
    enabled: Any = None,
    sort_order: Any = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    """更新字典项编码、名称、说明、启停与排序；所属分类固定不可修改。"""
    parent_code = _normalize_code(dictionary_code, "字典编码")
    try:
        target_id = int(item_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("字典项标识无效") from exc
    rows = connection.execute(
        select(DICTIONARY_ITEMS).where(DICTIONARY_ITEMS.c.dictionary_code == parent_code)
    ).mappings().all()
    row = next((dict(item) for item in rows if int(dict(item).get("id") or 0) == target_id), None)
    if row is None:
        raise ValueError(f"字典项不存在：{target_id}")
    values: dict[str, Any] = {"updated_by": updated_by, "updated_at": _utc_now()}
    if item_code is not None:
        normalized_code = _normalize_item_code(item_code)
        if any(
            int(dict(item).get("id") or 0) != target_id
            and str(dict(item).get("item_code") or "") == normalized_code
            for item in rows
        ):
            raise ValueError(f"字典项编码已存在：{normalized_code}")
        values["item_code"] = normalized_code
    if item_name is not None:
        values["item_name"] = _normalize_name(item_name, "字典项名称")
    if description is not None:
        values["description"] = _normalize_description(description)
    if enabled is not None:
        values["enabled"] = 1 if _as_bool(enabled) else 0
    if sort_order is not None:
        values["sort_order"] = _normalize_sort_order(sort_order)
    connection.execute(
        DICTIONARY_ITEMS.update()
        .where(DICTIONARY_ITEMS.c.id == target_id)
        .where(DICTIONARY_ITEMS.c.dictionary_code == parent_code)
        .values(**values)
    )
    row.update(values)
    return _item_row_to_dict(row)


def delete_dictionary_item(
    connection: Connection,
    dictionary_code: Any,
    item_id: Any,
) -> None:
    """删除指定字典中的字典项；业务历史展示由记录快照保证。"""
    parent_code = _normalize_code(dictionary_code, "字典编码")
    try:
        target_id = int(item_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("字典项标识无效") from exc
    result = connection.execute(
        DICTIONARY_ITEMS.delete()
        .where(DICTIONARY_ITEMS.c.id == target_id)
        .where(DICTIONARY_ITEMS.c.dictionary_code == parent_code)
    )
    if not result.rowcount:
        raise ValueError(f"字典项不存在：{target_id}")
