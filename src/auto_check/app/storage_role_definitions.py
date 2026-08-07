"""角色定义的应用库存取（系统内建 + 自定义角色）。

系统内建角色由 ``capabilities.ROLE_DEFINITIONS`` 固定定义；自定义角色持久化
到 ``role_definitions`` 表，角色码由系统自动生成（``custom_<序号>``）。

自定义角色不可与系统内建角色同码；删除前需确认无用户引用该角色。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, Text, select
from sqlalchemy.dialects.mysql import BOOLEAN, DATETIME, TINYINT, insert as mysql_insert
from sqlalchemy.engine import Connection

from .capabilities import ROLE_DEFINITIONS, SYSTEM_ROLES

_ROLE_REMARK_MAX_LEN = 20
_ROLE_NAME_MAX_LEN = 10


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


_METADATA = MetaData()

ROLE_DEFINITIONS_TABLE = Table(
    "role_definitions",
    _METADATA,
    Column("role_code", String(32), primary_key=True),
    Column("display_name", String(64), nullable=False),
    Column("remark", String(200), nullable=False, default=""),
    Column("is_system", TINYINT(unsigned=True), nullable=False, default=0),
    Column("created_by", String(64), nullable=True),
    Column("created_at", DATETIME(fsp=6), nullable=False),
    Column("updated_by", String(64), nullable=True),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)


def _normalize_remark(remark: str) -> str:
    value = str(remark or "").strip()
    if len(value) > _ROLE_REMARK_MAX_LEN:
        raise ValueError(f"remark must be at most {_ROLE_REMARK_MAX_LEN} characters")
    return value


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "role_code": str(row.get("role_code") or ""),
        "display_name": str(row.get("display_name") or ""),
        "remark": str(row.get("remark") or ""),
        "is_system": bool(row.get("is_system", 0)),
        "created_by": row.get("created_by") if row.get("created_by") is not None else None,
        "created_at": str(row.get("created_at") or ""),
        "updated_by": row.get("updated_by") if row.get("updated_by") is not None else None,
        "updated_at": str(row.get("updated_at") or ""),
    }


def load_role_definitions(connection: Connection) -> list[dict[str, Any]]:
    """加载全部角色定义：系统内建 + 自定义，系统角色固定在前（admin、user）。"""
    rows = connection.execute(
        select(ROLE_DEFINITIONS_TABLE)
        .where(ROLE_DEFINITIONS_TABLE.c.is_system == 0)
        .order_by(
            ROLE_DEFINITIONS_TABLE.c.created_at,
            ROLE_DEFINITIONS_TABLE.c.role_code,
        )
    ).mappings().all()
    custom = [_row_to_dict(row) for row in rows]
    # 系统内建角色不存库，由代码常量提供
    system = [
        {
            "role_code": code,
            "display_name": name,
            "remark": "",
            "is_system": True,
            "created_by": None,
            "created_at": "",
            "updated_by": None,
            "updated_at": "",
        }
        for code, name in ROLE_DEFINITIONS.items()
    ]
    return system + custom


def purge_removed_builtin_role_definitions(connection: Connection) -> int:
    """删除已下线预留角色在 role_definitions 表中的残留行；返回删除行数。"""
    from auto_check.app.capabilities import REMOVED_BUILTIN_ROLES

    result = connection.execute(
        ROLE_DEFINITIONS_TABLE.delete().where(
            ROLE_DEFINITIONS_TABLE.c.role_code.in_(tuple(REMOVED_BUILTIN_ROLES))
        )
    )
    return int(result.rowcount or 0)


def load_custom_role_codes(connection: Connection) -> list[str]:
    """仅返回自定义角色码（按创建时间排序）。"""
    rows = connection.execute(
        select(ROLE_DEFINITIONS_TABLE.c.role_code)
        .where(ROLE_DEFINITIONS_TABLE.c.is_system == 0)
        .order_by(ROLE_DEFINITIONS_TABLE.c.created_at, ROLE_DEFINITIONS_TABLE.c.role_code)
    ).mappings().all()
    return [str(row["role_code"]) for row in rows]


def load_custom_role_remarks(connection: Connection) -> dict[str, str]:
    """自定义角色码 → 备注（空备注保持为空，不回退为角色名称）。"""
    rows = connection.execute(
        select(
            ROLE_DEFINITIONS_TABLE.c.role_code,
            ROLE_DEFINITIONS_TABLE.c.remark,
        ).where(ROLE_DEFINITIONS_TABLE.c.is_system == 0)
    ).mappings().all()
    return {str(row["role_code"]): str(row.get("remark") or "") for row in rows}


def _next_custom_code(connection: Connection) -> str:
    """生成下一个不冲突的自定义角色码 custom_<序号>。"""
    existing = set(load_custom_role_codes(connection))
    index = 1
    while True:
        code = f"custom_{index}"
        if code not in existing and code not in SYSTEM_ROLES:
            return code
        index += 1


def create_role_definition(
    connection: Connection,
    *,
    display_name: str,
    remark: str = "",
    updated_by: str | None = None,
) -> dict[str, Any]:
    """创建自定义角色；角色码自动生成。拒绝系统角色码/重复。"""
    name = str(display_name or "").strip()
    if not name:
        raise ValueError("display name is required")
    if len(name) > _ROLE_NAME_MAX_LEN:
        raise ValueError(f"display name must be at most {_ROLE_NAME_MAX_LEN} characters")
    code = _next_custom_code(connection)
    now = _utc_now()
    normalized_remark = _normalize_remark(remark)
    statement = mysql_insert(ROLE_DEFINITIONS_TABLE).values(
        role_code=code,
        display_name=name,
        remark=normalized_remark,
        is_system=0,
        created_by=updated_by,
        created_at=now,
        updated_by=updated_by,
        updated_at=now,
    )
    connection.execute(statement)
    return {
        "role_code": code,
        "display_name": name,
        "remark": normalized_remark,
        "is_system": False,
        "created_by": updated_by,
        "created_at": str(now),
        "updated_by": updated_by,
        "updated_at": str(now),
    }


def update_role_definition(
    connection: Connection,
    role_code: str,
    *,
    display_name: str | None = None,
    remark: str | None = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    """更新自定义角色的显示名/备注；系统内建角色仅可改备注。"""
    rows = connection.execute(
        select(ROLE_DEFINITIONS_TABLE).where(
            ROLE_DEFINITIONS_TABLE.c.role_code == str(role_code)
        )
    ).mappings().all()
    if not rows:
        if role_code in SYSTEM_ROLES:
            # 系统角色不持久化到本表，仅备注可改（备注存 role_capability_settings.remarks_json）
            raise ValueError("system role display name cannot be changed")
        raise ValueError("role definition not found")
    row = rows[0]
    values: dict[str, Any] = {"updated_by": updated_by, "updated_at": _utc_now()}
    if display_name is not None:
        name = str(display_name or "").strip()
        if not name:
            raise ValueError("display name is required")
        if len(name) > _ROLE_NAME_MAX_LEN:
            raise ValueError(f"display name must be at most {_ROLE_NAME_MAX_LEN} characters")
        values["display_name"] = name
    if remark is not None:
        values["remark"] = _normalize_remark(remark)
    connection.execute(
        ROLE_DEFINITIONS_TABLE.update()
        .where(ROLE_DEFINITIONS_TABLE.c.role_code == str(role_code))
        .values(**values)
    )
    updated = dict(row)
    updated.update(values)
    return _row_to_dict(updated)


def delete_role_definition(connection: Connection, role_code: str) -> None:
    """删除自定义角色；仅系统内建 admin/user 不可删。若仍有用户引用则抛 ValueError。"""
    if role_code in SYSTEM_ROLES:
        raise ValueError("system role cannot be deleted")
    from auto_check.app.capabilities import REMOVED_BUILTIN_ROLES

    rows = connection.execute(
        select(ROLE_DEFINITIONS_TABLE.c.role_code).where(
            ROLE_DEFINITIONS_TABLE.c.role_code == str(role_code)
        )
    ).mappings().all()
    if not rows:
        # 已下线预留角色若不在表中，视为已清理成功，避免前端反复报错
        if role_code in REMOVED_BUILTIN_ROLES:
            return
        raise ValueError("role definition not found")
    if count_users_by_role(connection, role_code) > 0:
        raise ValueError("role is in use by existing users and cannot be deleted")
    connection.execute(
        ROLE_DEFINITIONS_TABLE.delete().where(
            ROLE_DEFINITIONS_TABLE.c.role_code == str(role_code)
        )
    )


def count_users_by_role(connection: Connection, role_code: str) -> int:
    """统计使用某角色码的启用+停用用户数量。"""
    from .storage_users import USERS

    rows = connection.execute(
        select(USERS.c.id).where(USERS.c.role == str(role_code))
    ).mappings().all()
    return len(rows)