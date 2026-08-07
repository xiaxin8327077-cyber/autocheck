"""角色能力矩阵与角色备注的应用库存取。

配置以单行（``id=1``）JSON 快照持久化。矩阵读取时与代码默认矩阵按
角色/能力合并（参见 :func:`auto_check.app.capabilities.merge_matrix`），
只补缺失项，不覆盖已保存值。

自定义角色由独立的 ``role_definitions`` 表登记；本模块的 load/save 函数
传入 ``custom_roles``/``custom_role_remarks`` 参数，使矩阵与备注合并时保留
自定义角色的已存值。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, select
from sqlalchemy.dialects.mysql import DATETIME, TINYINT, insert as mysql_insert
from sqlalchemy.engine import Connection

from .capabilities import (
    assert_admin_column_unchanged,
    assert_admin_only_unchanged,
    assert_required_unchanged,
    merge_matrix,
    merge_remarks,
    sanitize_admin_only,
    sanitize_required,
)

_METADATA = MetaData()

ROLE_CAPABILITY_SETTINGS = Table(
    "role_capability_settings",
    _METADATA,
    Column("id", TINYINT(unsigned=True), primary_key=True),
    Column("matrix_json", Text, nullable=False),
    Column("remarks_json", Text, nullable=True),
    Column("version", Integer, nullable=False, default=1),
    Column("updated_by", String(64), nullable=True),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_matrix(raw: Any) -> dict[str, dict[str, bool]] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    decoded: dict[str, dict[str, bool]] = {}
    for role, caps in raw.items():
        if not isinstance(caps, dict):
            continue
        decoded[str(role)] = {str(code): bool(value) for code, value in caps.items()}
    return decoded


def _decode_remarks(raw: Any) -> dict[str, str] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    return {str(role): str(value or "") for role, value in raw.items()}


def load_role_capability_matrix(
    connection: Connection,
    *,
    custom_roles: list[str] | None = None,
) -> dict[str, dict[str, bool]]:
    """加载矩阵快照并与默认矩阵合并；历史违规值经 sanitize 清洗。"""
    row = connection.execute(
        select(ROLE_CAPABILITY_SETTINGS.c.matrix_json).where(
            ROLE_CAPABILITY_SETTINGS.c.id == 1
        )
    ).mappings().first()
    stored = _decode_matrix(row.get("matrix_json")) if row else None
    cleaned = sanitize_required(sanitize_admin_only(stored))
    return merge_matrix(cleaned, custom_roles=custom_roles)


def save_role_capability_matrix(
    connection: Connection,
    *,
    matrix: dict[str, dict[str, bool]],
    updated_by: str | None,
    custom_roles: list[str] | None = None,
) -> dict[str, dict[str, bool]]:
    """保存矩阵快照。

    保存前依次做 admin 列锁、必选、仅管理员能力校验（违反抛
    :class:`ValueError`），再合并后以 upsert 写入单行快照；返回合并后的矩阵。
    """
    previous = load_role_capability_matrix(connection, custom_roles=custom_roles)
    merged = merge_matrix(matrix, custom_roles=custom_roles)
    assert_admin_column_unchanged(previous, merged)
    assert_required_unchanged(merged)
    assert_admin_only_unchanged(merged)
    matrix_json = _stable_json(merged)
    normalized_updated_by = None if updated_by is None else str(updated_by)
    remarks_row = connection.execute(
        select(ROLE_CAPABILITY_SETTINGS.c.remarks_json).where(
            ROLE_CAPABILITY_SETTINGS.c.id == 1
        )
    ).mappings().first()
    remarks_json = remarks_row.get("remarks_json") if remarks_row else None
    statement = mysql_insert(ROLE_CAPABILITY_SETTINGS).values(
        id=1,
        matrix_json=matrix_json,
        remarks_json=remarks_json,
        version=1,
        updated_by=normalized_updated_by,
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    connection.execute(
        statement.on_duplicate_key_update(
            matrix_json=statement.inserted.matrix_json,
            updated_by=statement.inserted.updated_by,
            updated_at=statement.inserted.updated_at,
        )
    )
    return merged


def load_role_remarks(
    connection: Connection,
    *,
    custom_role_remarks: dict[str, str] | None = None,
) -> dict[str, str]:
    row = connection.execute(
        select(ROLE_CAPABILITY_SETTINGS.c.remarks_json).where(
            ROLE_CAPABILITY_SETTINGS.c.id == 1
        )
    ).mappings().first()
    stored = _decode_remarks(row.get("remarks_json")) if row else None
    return merge_remarks(stored, custom_role_remarks=custom_role_remarks)


def save_role_remarks(
    connection: Connection,
    *,
    remarks: dict[str, str],
    updated_by: str | None,
    custom_roles: list[str] | None = None,
    custom_role_remarks: dict[str, str] | None = None,
) -> dict[str, str]:
    from auto_check.app.storage_role_definitions import _ROLE_REMARK_MAX_LEN

    incoming: dict[str, str] = {}
    for role, remark in (remarks or {}).items():
        value = str(remark or "").strip()
        if len(value) > _ROLE_REMARK_MAX_LEN:
            raise ValueError(f"remark must be at most {_ROLE_REMARK_MAX_LEN} characters")
        incoming[str(role)] = value
    row = connection.execute(
        select(ROLE_CAPABILITY_SETTINGS.c.remarks_json).where(
            ROLE_CAPABILITY_SETTINGS.c.id == 1
        )
    ).mappings().first()
    existing = _decode_remarks(row.get("remarks_json")) if row else {}
    overlay = dict(existing or {})
    overlay.update(incoming)
    merged = merge_remarks(overlay, custom_role_remarks=custom_role_remarks)
    remarks_json = _stable_json(merged)
    normalized_updated_by = None if updated_by is None else str(updated_by)
    matrix = load_role_capability_matrix(connection, custom_roles=custom_roles)
    statement = mysql_insert(ROLE_CAPABILITY_SETTINGS).values(
        id=1,
        matrix_json=_stable_json(matrix),
        remarks_json=remarks_json,
        version=1,
        updated_by=normalized_updated_by,
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    connection.execute(
        statement.on_duplicate_key_update(
            remarks_json=statement.inserted.remarks_json,
            updated_by=statement.inserted.updated_by,
            updated_at=statement.inserted.updated_at,
        )
    )
    return merged
