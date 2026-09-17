from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    select,
)

from .validator import ValidationError


METADATA = MetaData()

#: 两个固定监管看板外部接口共用的唯一白名单作用域。
BOARD_PREVIEW_SCOPE = "dashboard_management.board_preview"

#: 单个作用域允许管理员配置的最大地址数量。
MAX_ALLOWED_IPS = 100

EXTERNAL_API_ACCESS_POLICIES = Table(
    "dashboard_management_external_api_access_policies",
    METADATA,
    Column("scope_key", String(128), primary_key=True),
    Column("whitelist_enabled", Boolean, nullable=False),
    Column("allowed_ips_json", Text, nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_by", String(128), nullable=False),
    Column("updated_at", DateTime, nullable=False),
)


class AccessPolicyError(RuntimeError):
    """Raised when a stored access policy cannot be trusted."""

    message = "外部接口访问策略暂时不可用"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message


@dataclass(frozen=True)
class ExternalApiAccessPolicy:
    enabled: bool
    allowed_ips: tuple[str, ...]
    updated_at: datetime | None


def _allowed_ips_error(message: str) -> ValidationError:
    return ValidationError(message, fields={"allowed_ips": message})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _collapse(address: ipaddress.IPv4Address | ipaddress.IPv6Address):
    """Collapse IPv4-mapped IPv6 addresses to plain IPv4."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def parse_client_address(value: object):
    """Parse one already-normalized address; return ``None`` when unusable."""
    if not isinstance(value, str):
        return None
    text = value.strip().split("%", 1)[0]
    if not text or text == "unknown":
        return None
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    return _collapse(address)


def normalize_allowed_ips(value: object) -> tuple[str, ...]:
    """Validate administrator input and return normalized, de-duplicated addresses."""
    if not isinstance(value, list):
        raise _allowed_ips_error("allowed_ips 必须为 IP 地址列表")
    if len(value) > MAX_ALLOWED_IPS:
        raise _allowed_ips_error(f"最多允许 {MAX_ALLOWED_IPS} 个 IP 地址")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str):
            raise _allowed_ips_error(f"第 {index} 项不是合法的 IP 地址")
        candidate = item.strip()
        if not candidate:
            continue
        if "%" in candidate:
            raise _allowed_ips_error(f"第 {index} 项不支持 IPv6 zone id")
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            raise _allowed_ips_error(f"第 {index} 项不是合法的 IP 地址") from None
        text = _collapse(address).compressed
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)

    if len(normalized) > MAX_ALLOWED_IPS:
        raise _allowed_ips_error(f"最多允许 {MAX_ALLOWED_IPS} 个 IP 地址")
    return tuple(normalized)


def _decode_allowed_ips(payload: object) -> tuple[str, ...]:
    """Decode persisted JSON; corrupted content must never be trusted."""
    try:
        decoded = json.loads(payload) if isinstance(payload, str) else None
    except (TypeError, ValueError):
        raise AccessPolicyError() from None
    if not isinstance(decoded, list) or len(decoded) > MAX_ALLOWED_IPS:
        raise AccessPolicyError()
    normalized: list[str] = []
    for item in decoded:
        if not isinstance(item, str):
            raise AccessPolicyError()
        try:
            address = ipaddress.ip_address(item)
        except ValueError:
            raise AccessPolicyError() from None
        normalized.append(_collapse(address).compressed)
    return tuple(normalized)


class _AccessPolicyRepository:
    """Persistence for the dashboard external API IP whitelist policy."""

    def __init__(self, database: Any) -> None:
        self._database = database

    def read(self) -> tuple[bool, str, datetime | None] | None:
        with self._database.connect() as connection:
            row = connection.execute(
                select(
                    EXTERNAL_API_ACCESS_POLICIES.c.whitelist_enabled,
                    EXTERNAL_API_ACCESS_POLICIES.c.allowed_ips_json,
                    EXTERNAL_API_ACCESS_POLICIES.c.updated_at,
                ).where(EXTERNAL_API_ACCESS_POLICIES.c.scope_key == BOARD_PREVIEW_SCOPE)
            ).first()
        if row is None:
            return None
        return bool(row[0]), str(row[1]), row[2]

    def write(
        self,
        *,
        enabled: bool,
        allowed_ips: tuple[str, ...],
        operator: str,
        timestamp: datetime,
    ) -> None:
        payload = json.dumps(list(allowed_ips), ensure_ascii=False, separators=(",", ":"))
        with self._database.transaction() as connection:
            existing = connection.execute(
                select(EXTERNAL_API_ACCESS_POLICIES.c.scope_key).where(
                    EXTERNAL_API_ACCESS_POLICIES.c.scope_key == BOARD_PREVIEW_SCOPE
                )
            ).first()
            if existing is None:
                connection.execute(
                    EXTERNAL_API_ACCESS_POLICIES.insert().values(
                        scope_key=BOARD_PREVIEW_SCOPE,
                        whitelist_enabled=enabled,
                        allowed_ips_json=payload,
                        created_by=operator,
                        created_at=timestamp,
                        updated_by=operator,
                        updated_at=timestamp,
                    )
                )
            else:
                connection.execute(
                    EXTERNAL_API_ACCESS_POLICIES.update()
                    .where(EXTERNAL_API_ACCESS_POLICIES.c.scope_key == BOARD_PREVIEW_SCOPE)
                    .values(
                        whitelist_enabled=enabled,
                        allowed_ips_json=payload,
                        updated_by=operator,
                        updated_at=timestamp,
                    )
                )


class DashboardExternalApiAccessService:
    """IP whitelist policy for the two fixed external dashboard preview routes.

    The policy lives in the module-owned database table; environment variables and
    in-memory state are never treated as the source of truth.
    """

    def __init__(self, database: Any, *, utc_now: Any = _utc_now) -> None:
        self._repository = _AccessPolicyRepository(database)
        self._utc_now = utc_now

    def status(self) -> ExternalApiAccessPolicy:
        record = self._repository.read()
        if record is None:
            return ExternalApiAccessPolicy(enabled=False, allowed_ips=(), updated_at=None)
        enabled, payload, updated_at = record
        return ExternalApiAccessPolicy(
            enabled=enabled,
            allowed_ips=_decode_allowed_ips(payload),
            updated_at=updated_at,
        )

    def update(
        self,
        *,
        enabled: bool,
        allowed_ips: list[str],
        operator: str,
    ) -> ExternalApiAccessPolicy:
        if type(enabled) is not bool:
            raise ValidationError("enabled 必须为布尔值", fields={"enabled": "enabled 必须为布尔值"})
        normalized = normalize_allowed_ips(allowed_ips)
        if not isinstance(operator, str) or not operator.strip():
            raise ValidationError("操作人无效", fields={"operator": "操作人无效"})
        self._repository.write(
            enabled=enabled,
            allowed_ips=normalized,
            operator=operator.strip()[:128],
            timestamp=self._utc_now(),
        )
        return self.status()

    def is_allowed(self, client_ip: str, server_ip: str) -> bool:
        policy = self.status()
        if not policy.enabled:
            return True
        client = parse_client_address(client_ip)
        if client is None:
            return False
        if client.is_loopback:
            return True
        server = parse_client_address(server_ip)
        if server is not None and server == client:
            return True
        return client.compressed in policy.allowed_ips
