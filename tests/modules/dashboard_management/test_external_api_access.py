from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


class _Database:
    """Minimal application-database double with a switchable write failure."""

    def __init__(self) -> None:
        self._engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.fail_transactions = False

    @contextmanager
    def connect(self):
        with self._engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self):
        if self.fail_transactions:
            raise RuntimeError("database unavailable")
        with self._engine.begin() as connection:
            yield connection


def _service(database=None, *, utc_now=None):
    from auto_check.modules.dashboard_management.external_api_access import (
        METADATA,
        DashboardExternalApiAccessService,
    )

    database = database or _Database()
    METADATA.create_all(database._engine)
    return database, DashboardExternalApiAccessService(
        database,
        utc_now=utc_now or (lambda: datetime(2026, 9, 17, 10, 20, 30)),
    )


def test_scope_and_limit_are_fixed_constants():
    from auto_check.modules.dashboard_management.external_api_access import (
        BOARD_PREVIEW_SCOPE,
        MAX_ALLOWED_IPS,
    )

    assert BOARD_PREVIEW_SCOPE == "dashboard_management.board_preview"
    assert MAX_ALLOWED_IPS == 100


def test_table_declares_all_fixed_columns():
    from auto_check.modules.dashboard_management.external_api_access import (
        EXTERNAL_API_ACCESS_POLICIES,
    )

    assert EXTERNAL_API_ACCESS_POLICIES.name == "dashboard_management_external_api_access_policies"
    assert set(EXTERNAL_API_ACCESS_POLICIES.c.keys()) == {
        "scope_key",
        "whitelist_enabled",
        "allowed_ips_json",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    }


def test_status_defaults_to_disabled_without_a_database_record():
    _, service = _service()

    policy = service.status()

    assert policy.enabled is False
    assert policy.allowed_ips == ()
    assert policy.updated_at is None


def test_disabled_whitelist_allows_any_source_ip():
    _, service = _service()

    assert service.is_allowed("203.0.113.9", "192.168.1.1") is True
    assert service.is_allowed("unknown", "unknown") is True
    assert service.is_allowed("", "") is True


def test_enabled_whitelist_allows_configured_ipv4_and_ipv6():
    _, service = _service()
    service.update(
        enabled=True,
        allowed_ips=["192.168.1.10", "2001:db8::10"],
        operator="admin",
    )

    assert service.is_allowed("192.168.1.10", "10.0.0.1") is True
    assert service.is_allowed("2001:db8::10", "10.0.0.1") is True
    assert service.is_allowed("203.0.113.9", "10.0.0.1") is False


def test_enabled_whitelist_allows_loopback_sources_without_configuration():
    _, service = _service()
    service.update(enabled=True, allowed_ips=[], operator="admin")

    assert service.is_allowed("127.0.0.1", "127.0.0.1") is True
    assert service.is_allowed("::1", "::1") is True
    assert service.is_allowed("127.0.0.5", "10.0.0.1") is True


def test_enabled_whitelist_allows_source_equal_to_connected_server_address():
    _, service = _service()
    service.update(enabled=True, allowed_ips=[], operator="admin")

    # 本机通过自己的局域网 IP 调用：对端地址等于本次连接的服务端本地地址。
    assert service.is_allowed("192.168.1.8", "192.168.1.8") is True
    assert service.is_allowed("192.168.1.8", "192.168.1.9") is False
    assert service.is_allowed("192.168.1.8", "unknown") is False


def test_enabled_whitelist_rejects_unknown_and_unparsable_sources():
    _, service = _service()
    service.update(enabled=True, allowed_ips=["192.168.1.10"], operator="admin")

    assert service.is_allowed("unknown", "192.168.1.8") is False
    assert service.is_allowed("", "192.168.1.8") is False
    assert service.is_allowed("not-an-ip", "192.168.1.8") is False
    assert service.is_allowed("192.168.1.10/32", "192.168.1.8") is False


def test_enabled_whitelist_normalizes_ipv4_mapped_ipv6():
    _, service = _service()
    policy = service.update(
        enabled=True,
        allowed_ips=["::ffff:192.168.1.8", "::ffff:10.0.0.1"],
        operator="admin",
    )

    assert policy.allowed_ips == ("192.168.1.8", "10.0.0.1")
    assert service.is_allowed("192.168.1.8", "10.0.0.9") is True
    # 请求侧同样规范化：mapped 形式的回环地址按 IPv4 回环自动放行。
    assert service.is_allowed("::ffff:127.0.0.1", "10.0.0.9") is True


def test_allowed_ips_are_deduplicated_keeping_first_position():
    _, service = _service()
    policy = service.update(
        enabled=True,
        allowed_ips=["2001:db8::10", "192.168.1.10", "2001:db8:0:0::10", "192.168.1.10"],
        operator="admin",
    )

    assert policy.allowed_ips == ("2001:db8::10", "192.168.1.10")


def test_ipv6_addresses_are_stored_in_compressed_form():
    _, service = _service()
    policy = service.update(
        enabled=True,
        allowed_ips=["2001:0db8:0000:0000:0000:0000:0000:0010"],
        operator="admin",
    )

    assert policy.allowed_ips == ("2001:db8::10",)
    assert service.is_allowed("2001:db8::10", "10.0.0.1") is True


def test_blank_entries_are_ignored_and_whitespace_trimmed():
    _, service = _service()
    policy = service.update(
        enabled=True,
        allowed_ips=["", "  ", "  192.168.1.10  ", "\t", "2001:db8::10"],
        operator="admin",
    )

    assert policy.allowed_ips == ("192.168.1.10", "2001:db8::10")


@pytest.mark.parametrize(
    "value",
    ["not-an-ip", "192.168.1.256", "192.168.1.10/24", "10.0.0.0/8", "example.com", "::ffff:1.2.3.4%eth0", "2001:db8::10%1"],
)
def test_invalid_address_entries_are_rejected(value):
    from auto_check.modules.dashboard_management.validator import ValidationError

    _, service = _service()

    with pytest.raises(ValidationError) as error:
        service.update(enabled=True, allowed_ips=[value], operator="admin")

    assert error.value.status == 400
    assert set(error.value.fields) == {"allowed_ips"}


def test_more_than_one_hundred_addresses_are_rejected():
    from auto_check.modules.dashboard_management.external_api_access import MAX_ALLOWED_IPS
    from auto_check.modules.dashboard_management.validator import ValidationError

    _, service = _service()
    too_many = [f"10.0.{index // 256}.{index % 256}" for index in range(MAX_ALLOWED_IPS + 1)]

    with pytest.raises(ValidationError):
        service.update(enabled=True, allowed_ips=too_many, operator="admin")

    accepted = service.update(enabled=True, allowed_ips=too_many[:MAX_ALLOWED_IPS], operator="admin")
    assert len(accepted.allowed_ips) == MAX_ALLOWED_IPS


def test_enabled_whitelist_with_empty_list_only_allows_local_machine():
    _, service = _service()
    policy = service.update(enabled=True, allowed_ips=[], operator="admin")

    assert policy.enabled is True
    assert policy.allowed_ips == ()
    assert service.is_allowed("127.0.0.1", "10.0.0.1") is True
    assert service.is_allowed("192.168.1.8", "192.168.1.8") is True
    assert service.is_allowed("203.0.113.9", "10.0.0.1") is False


def test_update_requires_strict_boolean_and_list_payload():
    from auto_check.modules.dashboard_management.validator import ValidationError

    _, service = _service()

    for invalid in (0, 1, "true", None):
        with pytest.raises(ValidationError) as error:
            service.update(enabled=invalid, allowed_ips=[], operator="admin")
        assert set(error.value.fields) == {"enabled"}

    for invalid in ("192.168.1.10", {"192.168.1.10"}, None):
        with pytest.raises(ValidationError) as error:
            service.update(enabled=True, allowed_ips=invalid, operator="admin")
        assert set(error.value.fields) == {"allowed_ips"}

    with pytest.raises(ValidationError):
        service.update(enabled=True, allowed_ips=[True], operator="admin")


def test_update_persists_normalized_json_and_utc_timestamp():
    from auto_check.modules.dashboard_management.external_api_access import (
        EXTERNAL_API_ACCESS_POLICIES,
    )

    database, service = _service()
    policy = service.update(
        enabled=True,
        allowed_ips=["192.168.1.10", "2001:db8::10"],
        operator="admin",
    )

    assert policy.updated_at == datetime(2026, 9, 17, 10, 20, 30)
    with database.connect() as connection:
        row = connection.execute(EXTERNAL_API_ACCESS_POLICIES.select()).mappings().one()
    assert row["scope_key"] == "dashboard_management.board_preview"
    assert row["whitelist_enabled"] is True
    assert row["allowed_ips_json"] == '["192.168.1.10","2001:db8::10"]'
    assert row["created_by"] == "admin"
    assert row["updated_by"] == "admin"
    assert row["created_at"] == row["updated_at"] == datetime(2026, 9, 17, 10, 20, 30)

    # 第二次写入走 UPDATE 分支并保留创建信息。
    updated = service.update(enabled=False, allowed_ips=[], operator="operator-2")
    assert updated.enabled is False
    with database.connect() as connection:
        row = connection.execute(EXTERNAL_API_ACCESS_POLICIES.select()).mappings().one()
    assert row["created_by"] == "admin"
    assert row["updated_by"] == "operator-2"
    assert row["allowed_ips_json"] == "[]"


def test_update_failure_keeps_the_previous_configuration():
    database, service = _service()
    service.update(enabled=True, allowed_ips=["192.168.1.10"], operator="admin")

    database.fail_transactions = True
    with pytest.raises(RuntimeError):
        service.update(enabled=True, allowed_ips=["10.0.0.1"], operator="admin")
    database.fail_transactions = False

    policy = service.status()
    assert policy.enabled is True
    assert policy.allowed_ips == ("192.168.1.10",)
    assert service.is_allowed("192.168.1.10", "10.0.0.1") is True
    assert service.is_allowed("10.0.0.1", "10.0.0.9") is False


@pytest.mark.parametrize(
    "payload",
    ["{not-json", "null", '{"enabled": true}', '"192.168.1.10"', '[1, 2]', '["not-an-ip"]'],
)
def test_corrupted_stored_policy_never_allows_access(payload):
    from auto_check.modules.dashboard_management.external_api_access import (
        EXTERNAL_API_ACCESS_POLICIES,
        AccessPolicyError,
    )

    database, service = _service()
    with database.transaction() as connection:
        connection.execute(
            EXTERNAL_API_ACCESS_POLICIES.insert().values(
                scope_key="dashboard_management.board_preview",
                whitelist_enabled=True,
                allowed_ips_json=payload,
                created_by="admin",
                created_at=datetime(2026, 9, 17, 10, 0, 0),
                updated_by="admin",
                updated_at=datetime(2026, 9, 17, 10, 0, 0),
            )
        )

    # 读取失败必须向上抛出，由接口层转换为 503，绝不能退化为“放行”。
    with pytest.raises(AccessPolicyError):
        service.status()
    with pytest.raises(AccessPolicyError):
        service.is_allowed("192.168.1.10", "10.0.0.1")


def test_corrupted_policy_read_failure_is_not_treated_as_disabled():
    from auto_check.modules.dashboard_management.external_api_access import (
        EXTERNAL_API_ACCESS_POLICIES,
        AccessPolicyError,
    )

    database, service = _service()
    with database.transaction() as connection:
        connection.execute(
            EXTERNAL_API_ACCESS_POLICIES.insert().values(
                scope_key="dashboard_management.board_preview",
                whitelist_enabled=False,
                allowed_ips_json="{broken",
                created_by="admin",
                created_at=datetime(2026, 9, 17, 10, 0, 0),
                updated_by="admin",
                updated_at=datetime(2026, 9, 17, 10, 0, 0),
            )
        )

    with pytest.raises(AccessPolicyError):
        service.status()
