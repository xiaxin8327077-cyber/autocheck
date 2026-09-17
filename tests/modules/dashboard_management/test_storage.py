from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.exc import IntegrityError

from auto_check.modules.dashboard_management.contracts import VersionConflictError


class _Database:
    def __init__(self) -> None:
        self._engine = create_engine("sqlite+pysqlite:///:memory:")
        event.listen(
            self._engine,
            "connect",
            lambda dbapi_connection, _: dbapi_connection.execute("PRAGMA foreign_keys=ON"),
        )

    @contextmanager
    def connect(self):
        with self._engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self):
        with self._engine.begin() as connection:
            yield connection


@pytest.fixture
def storage():
    from auto_check.modules.dashboard_management.storage import (
        METADATA,
        DashboardManagementStorage,
    )

    database = _Database()
    METADATA.create_all(database._engine)
    instance = DashboardManagementStorage(database)
    instance.seed_builtin_catalog()
    return instance


def test_seed_builtin_catalog_is_idempotent_and_preserves_admin_enabled_and_order(storage) -> None:
    regions = storage.list_regions("report_submission")
    trust = next(item for item in regions if item["region_code"] == "monthly_trust_projects")
    storage.update_region(trust["id"], {"enabled": False, "display_order": 999}, trust["row_version"])

    storage.seed_builtin_catalog()

    seeded = storage.list_regions("report_submission")
    preserved = next(item for item in seeded if item["id"] == trust["id"])
    assert len(storage.list_regions("report_submission")) == 7
    assert len(storage.list_regions("reporting_process")) == 3
    assert len(storage.list_fields(trust["id"])) == 4
    assert preserved["enabled"] is False
    assert preserved["display_order"] == 999
    assert storage.get_source_config(trust["id"])["source_mode"] == "sql"


def test_initial_year_snapshots_use_confirmed_month_and_quarter_cutoffs(storage) -> None:
    report_regions = {
        row["region_code"]: row
        for row in storage.list_regions("report_submission")
    }

    trust_rows = storage.list_year_snapshots(
        report_regions["monthly_trust_projects"]["id"], 2026
    )
    completion_rows = storage.list_year_snapshots(
        report_regions["report_reconciliation_completion_time"]["id"], 2026
    )
    validation_rows = storage.list_year_snapshots(
        report_regions["report_validation_issue_handling"]["id"], 2026
    )
    quarter_rows = storage.list_year_snapshots(
        report_regions["quarterly_special_processing"]["id"], 2026
    )

    assert [row["period_value"] for row in trust_rows] == [1, 2, 3, 4, 5, 6]
    assert trust_rows[-1]["row"] == {
        "month": "6月",
        "single_trust_count": 4,
        "collective_trust_count": 52,
        "property_trust_count": 77,
    }
    assert [row["row"]["reconciliation_completed_time"] for row in completion_rows] == [
        "21:00", "20:00", "19:00", "01:00", "23:00", "20:00",
    ]
    assert [row["row"]["reconciliation_completed_at"] for row in completion_rows] == [
        None, None, None, None, None, None,
    ]
    assert [row["period_value"] for row in validation_rows] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert [row["row"]["validation_issue_count"] for row in validation_rows] == [
        75, 52, 42, 60, 16, 23, 25, 20,
    ]
    assert [row["period_value"] for row in quarter_rows] == [1, 2]
    assert [row["row"]["special_processing_count"] for row in quarter_rows] == [31, 34]

    before = (trust_rows, completion_rows, validation_rows, quarter_rows)
    storage.seed_initial_year_snapshots()
    after = tuple(
        storage.list_year_snapshots(report_regions[code]["id"], 2026)
        for code in (
            "monthly_trust_projects",
            "report_reconciliation_completion_time",
            "report_validation_issue_handling",
            "quarterly_special_processing",
        )
    )
    assert after == before


def test_year_snapshot_upsert_overwrites_returned_period_and_preserves_missing_period(storage) -> None:
    from auto_check.modules.dashboard_management.year_snapshots import SnapshotRow

    trust = next(
        row
        for row in storage.list_regions("report_submission")
        if row["region_code"] == "monthly_trust_projects"
    )
    refreshed_at = datetime(2026, 7, 15, 9, 30)
    storage.upsert_year_snapshots(
        trust["id"],
        (
            SnapshotRow(2026, "month", 6, {
                "month": "6月",
                "single_trust_count": 400,
                "collective_trust_count": 500,
                "property_trust_count": 600,
            }),
            SnapshotRow(2026, "month", 7, {
                "month": "7月",
                "single_trust_count": 1,
                "collective_trust_count": 2,
                "property_trust_count": 3,
            }),
        ),
        refreshed_at,
    )

    rows = storage.list_year_snapshots(trust["id"], 2026)
    assert [row["period_value"] for row in rows] == [1, 2, 3, 4, 5, 6, 7]
    assert rows[0]["row"]["single_trust_count"] == 7
    assert rows[5]["row"]["single_trust_count"] == 400
    assert rows[5]["source_refreshed_at"] == refreshed_at
    assert rows[6]["source_refreshed_at"] == refreshed_at
    assert storage.list_year_snapshots(trust["id"], 2025) == []


def test_year_snapshot_refresh_is_atomic_and_older_refresh_cannot_replace_newer_data(storage) -> None:
    from auto_check.modules.dashboard_management.year_snapshots import SnapshotRow

    trust = next(
        row
        for row in storage.list_regions("report_submission")
        if row["region_code"] == "monthly_trust_projects"
    )
    newer_at = datetime(2026, 8, 15, 10, 0)
    older_at = datetime(2026, 8, 15, 9, 0)

    refreshed = storage.refresh_year_snapshots(
        trust["id"],
        (SnapshotRow(2026, "month", 8, {
            "month": "8月",
            "single_trust_count": 800,
            "collective_trust_count": 801,
            "property_trust_count": 802,
        }),),
        period_year=2026,
        refreshed_at=newer_at,
    )
    assert refreshed[-1]["row"]["single_trust_count"] == 800

    refreshed = storage.refresh_year_snapshots(
        trust["id"],
        (SnapshotRow(2026, "month", 8, {
            "month": "8月",
            "single_trust_count": 8,
            "collective_trust_count": 9,
            "property_trust_count": 10,
        }),),
        period_year=2026,
        refreshed_at=older_at,
    )

    august = refreshed[-1]
    assert august["row"]["single_trust_count"] == 800
    assert august["source_refreshed_at"] == newer_at


def test_region_and_field_updates_use_row_version_optimistic_locks(storage) -> None:
    region = storage.create_region({
        "board_code": "report_submission",
        "region_code": "custom_region_0123456789ab",
        "name": "自定义区域",
        "shape": "list",
        "description": "测试区域",
        "display_order": 80,
    })
    updated_region = storage.update_region(region["id"], {"name": "已更新区域"}, region["row_version"])
    assert updated_region["name"] == "已更新区域"
    assert updated_region["row_version"] == 2
    with pytest.raises(VersionConflictError):
        storage.update_region(region["id"], {"name": "过期更新"}, region["row_version"])

    field = storage.create_field(region["id"], {
        "field_alias": "custom_value",
        "name": "自定义值",
        "value_type": "string",
        "nullable": True,
        "description": "测试字段",
        "display_order": 10,
    })
    updated_field = storage.update_field(field["id"], {"enabled": False}, field["row_version"])
    assert updated_field["enabled"] is False
    assert updated_field["row_version"] == 2
    with pytest.raises(VersionConflictError):
        storage.update_field(field["id"], {"name": "过期字段"}, field["row_version"])


def test_delete_custom_region_removes_region_fields_and_source_atomically(storage) -> None:
    region = storage.create_region_with_fields_and_default_sql({
        "board_code": "report_submission",
        "region_code": "custom_region_delete_me",
        "name": "待删除区域",
        "shape": "list",
        "description": "测试删除",
        "display_order": 9999,
    }, [{
        "field_alias": "custom_value",
        "name": "自定义值",
        "value_type": "string",
        "nullable": True,
        "description": "",
        "display_order": 10,
    }])

    storage.delete_custom_region(region["id"], region["row_version"])

    assert storage.get_region(region["id"]) is None
    assert storage.list_fields(region["id"]) == []
    assert storage.get_source_config(region["id"]) is None


def test_delete_custom_region_rejects_builtin_and_stale_versions(storage) -> None:
    builtin = storage.list_regions("report_submission")[0]
    with pytest.raises(ValueError, match="内置数据区域不能删除"):
        storage.delete_custom_region(builtin["id"], builtin["row_version"])

    custom = storage.create_region({
        "board_code": "report_submission",
        "region_code": "custom_region_stale_delete",
        "name": "并发删除区域",
        "shape": "scalar",
        "description": "",
        "display_order": 9999,
    })
    storage.update_region(custom["id"], {"name": "已被更新"}, custom["row_version"])
    with pytest.raises(VersionConflictError):
        storage.delete_custom_region(custom["id"], custom["row_version"])


def test_create_region_rejects_board_codes_outside_fixed_catalog(storage) -> None:
    with pytest.raises(ValueError, match="看板"):
        storage.create_region({
            "board_code": "third_dashboard",
            "region_code": "custom_region_fedcba987654",
            "name": "无效看板区域",
            "shape": "scalar",
            "description": "不应创建",
            "display_order": 90,
        })


def test_storage_schema_uses_bigint_identifiers_and_foreign_keys(storage) -> None:
    from sqlalchemy import BigInteger, Integer
    from auto_check.modules.dashboard_management.storage import FIELDS, REGIONS, SOURCE_CONFIGS

    assert isinstance(REGIONS.c.id.type, BigInteger)
    assert isinstance(REGIONS.c.id.type.dialect_impl(sqlite_dialect()), Integer)
    assert {foreign_key.target_fullname for foreign_key in FIELDS.c.region_id.foreign_keys} == {
        "dashboard_management_regions.id"
    }
    assert {foreign_key.target_fullname for foreign_key in SOURCE_CONFIGS.c.region_id.foreign_keys} == {
        "dashboard_management_regions.id"
    }

    with pytest.raises(IntegrityError):
        storage.create_field(999999, {
            "field_alias": "orphan_field",
            "name": "孤儿字段",
            "value_type": "string",
            "nullable": True,
            "description": "外键验证",
            "display_order": 10,
        })


def test_first_source_config_insert_conflict_becomes_version_conflict(storage, monkeypatch) -> None:
    region = storage.create_region({
        "board_code": "reporting_process",
        "region_code": "custom_region_123456abcdef",
        "name": "并发来源区域",
        "shape": "scalar",
        "description": "插入竞态测试",
        "display_order": 90,
    })
    storage.save_source_config(region["id"], {"source_mode": "sql"}, expected_version=None)
    monkeypatch.setattr(
        storage,
        "_get_source_config_with_connection",
        lambda connection, region_id: None,
    )

    with pytest.raises(VersionConflictError):
        storage.save_source_config(region["id"], {"source_mode": "sql"}, expected_version=None)


def test_source_config_is_one_per_region_and_uses_optimistic_lock(storage) -> None:
    region = storage.create_region({
        "board_code": "reporting_process",
        "region_code": "custom_region_abcdef012345",
        "name": "来源测试区域",
        "shape": "scalar",
        "description": "测试来源配置",
        "display_order": 80,
    })
    assert storage.get_source_config(region["id"]) is None

    created = storage.save_source_config(region["id"], {
        "source_mode": "sql",
        "datasource_id": "reporting",
        "sql_text": "SELECT 1 AS custom_value",
        "tested_signature": "a" * 64,
    }, expected_version=None)
    updated = storage.save_source_config(region["id"], {
        "source_mode": "system",
        "datasource_id": None,
        "sql_text": None,
    }, expected_version=created["row_version"])

    assert updated["region_id"] == region["id"]
    assert updated["source_mode"] == "system"
    assert updated["row_version"] == 2
    with pytest.raises(VersionConflictError):
        storage.save_source_config(region["id"], {"source_mode": "sql"}, created["row_version"])


def test_get_field_returns_field_with_its_region_identity(storage) -> None:
    region = storage.list_regions("report_submission")[0]
    field = storage.list_fields(region["id"])[0]

    assert storage.get_field(field["id"]) == field
    assert storage.get_field(999999) is None


def test_invalidate_source_test_clears_signature_and_advances_version(storage) -> None:
    region = storage.list_regions("report_submission")[0]
    current = storage.get_source_config(region["id"])
    configured = storage.save_source_config(region["id"], {
        "tested_signature": "a" * 64,
        "tested_at": current["created_at"],
        "tested_by": "admin",
    }, current["row_version"])

    storage.invalidate_source_test(region["id"])

    invalidated = storage.get_source_config(region["id"])
    assert invalidated["tested_signature"] is None
    assert invalidated["tested_at"] is None
    assert invalidated["tested_by"] is None
    assert invalidated["row_version"] == configured["row_version"] + 1


def test_record_successful_sql_test_locks_region_and_updates_only_test_marker(storage) -> None:
    region = storage.list_regions("report_submission")[0]
    before = storage.get_source_config(region["id"])

    recorded = storage.record_successful_sql_test(
        region["id"], "b" * 64, "admin", region["row_version"],
    )

    assert recorded["tested_signature"] == "b" * 64
    assert recorded["tested_by"] == "admin"
    assert recorded["row_version"] == before["row_version"] + 1
    assert recorded["datasource_id"] == before["datasource_id"]
    assert recorded["sql_text"] == before["sql_text"]


def test_field_change_invalidates_captured_schema_version_before_old_sql_test_records(storage) -> None:
    from auto_check.modules.dashboard_management.contracts import VersionConflictError

    region = storage.list_regions("report_submission")[0]
    old_schema_version = region["row_version"]
    source_before = storage.get_source_config(region["id"])

    storage.create_field_and_invalidate_source(region["id"], {
        "field_alias": "changed_during_test",
        "name": "测试期间变更字段",
        "value_type": "integer",
        "nullable": False,
        "enabled": True,
        "description": "",
        "display_order": 998,
    })

    with pytest.raises(VersionConflictError):
        storage.record_successful_sql_test(region["id"], "c" * 64, "admin", old_schema_version)
    source_after = storage.get_source_config(region["id"])
    assert storage.get_region(region["id"])["row_version"] == old_schema_version + 1
    assert source_after["tested_signature"] is None
    assert source_after["row_version"] == source_before["row_version"] + 1


def test_save_source_config_rejects_stale_region_schema_snapshot(storage) -> None:
    from auto_check.modules.dashboard_management.storage import SchemaVersionConflictError

    region = storage.create_region({
        "board_code": "report_submission",
        "region_code": "custom_region_snapshot0001",
        "name": "保存快照区域",
        "shape": "list",
        "description": "",
        "display_order": 997,
    })
    source = storage.save_source_config(region["id"], {
        "source_mode": "sql", "datasource_id": "safe", "sql_text": "SELECT value",
        "tested_signature": "d" * 64,
    }, expected_version=None)
    captured_region_version = region["row_version"]
    changed_region = storage.update_region(
        region["id"], {"shape": "scalar"}, captured_region_version,
    )

    with pytest.raises(SchemaVersionConflictError):
        storage.save_source_config(region["id"], {
            "source_mode": "sql", "datasource_id": "safe", "sql_text": "SELECT value",
            "tested_signature": "d" * 64,
        }, source["row_version"], expected_region_version=captured_region_version)
    assert storage.get_region(region["id"])["row_version"] == changed_region["row_version"]
    assert storage.get_source_config(region["id"]) == source


def test_public_field_writes_bump_region_schema_version_and_clear_test_marker(storage) -> None:
    region = storage.list_regions("report_submission")[0]
    source = storage.get_source_config(region["id"])
    configured = storage.save_source_config(region["id"], {
        "tested_signature": "e" * 64,
    }, source["row_version"])
    field = storage.create_field(region["id"], {
        "field_alias": "public_write_field",
        "name": "公开写入字段",
        "value_type": "string",
        "nullable": True,
        "description": "",
        "display_order": 996,
    })
    after_create_region = storage.get_region(region["id"])
    after_create_source = storage.get_source_config(region["id"])
    assert after_create_region["row_version"] == region["row_version"] + 1
    assert after_create_source["tested_signature"] is None

    storage.update_field(field["id"], {"name": "公开写入字段已更新"}, field["row_version"])
    assert storage.get_region(region["id"])["row_version"] == after_create_region["row_version"] + 1
    assert storage.get_source_config(region["id"])["row_version"] == after_create_source["row_version"] + 1
    assert configured["row_version"] < after_create_source["row_version"]


def test_create_region_with_default_sql_rolls_back_when_source_insert_fails(storage, monkeypatch) -> None:
    def fail_source_insert(connection, region_id):
        raise RuntimeError("source insert failed")

    monkeypatch.setattr(
        storage,
        "_create_default_source_config_with_connection",
        fail_source_insert,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="source insert failed"):
        storage.create_region_with_fields_and_default_sql({
            "board_code": "report_submission",
            "region_code": "custom_region_aaaaaa111111",
            "name": "不应残留的区域",
            "shape": "list",
            "description": "失败回滚",
            "display_order": 999,
        }, [{
            "field_alias": "rollback_initial", "name": "回滚字段", "value_type": "string",
            "nullable": False, "enabled": True, "description": "", "display_order": 10,
        }])

    assert all(
        item["region_code"] != "custom_region_aaaaaa111111"
        for item in storage.list_regions("report_submission")
    )


def test_atomic_region_create_rolls_back_region_and_fields_when_later_field_fails(storage, monkeypatch) -> None:
    def fail_second_field(connection, region_id, values):
        if values["field_alias"] == "second_initial":
            raise RuntimeError("second field failed")
        return original(connection, region_id, values)

    original = storage._create_field_with_connection
    monkeypatch.setattr(storage, "_create_field_with_connection", fail_second_field)
    with pytest.raises(RuntimeError, match="second field failed"):
        storage.create_region_with_fields_and_default_sql({
            "board_code": "report_submission", "region_code": "custom_region_atomic0001", "name": "原子区域",
            "shape": "list", "description": "", "display_order": 999,
        }, [
            {"field_alias": "first_initial", "name": "首字段", "value_type": "string", "nullable": False, "enabled": True, "description": "", "display_order": 10},
            {"field_alias": "second_initial", "name": "次字段", "value_type": "string", "nullable": False, "enabled": True, "description": "", "display_order": 20},
        ])
    assert all(item["region_code"] != "custom_region_atomic0001" for item in storage.list_regions("report_submission"))


def test_fields_metadata_rejects_duplicate_alias_within_one_region(storage) -> None:
    from sqlalchemy.exc import IntegrityError

    region = storage.create_region({
        "board_code": "report_submission", "region_code": "custom_region_unique0001", "name": "唯一字段区域",
        "shape": "list", "description": "", "display_order": 997,
    })
    field = {"field_alias": "same_alias", "name": "同别名", "value_type": "string", "nullable": False, "enabled": True, "description": "", "display_order": 10}
    storage.create_field(region["id"], field)
    with pytest.raises(IntegrityError):
        storage.create_field(region["id"], {**field, "name": "重复别名", "display_order": 20})


def test_atomic_region_create_leaves_no_region_when_database_rejects_duplicate_initial_alias(storage) -> None:
    from sqlalchemy.exc import IntegrityError

    fields = [
        {"field_alias": "duplicate_alias", "name": "字段一", "value_type": "string", "nullable": False, "enabled": True, "description": "", "display_order": 10},
        {"field_alias": "duplicate_alias", "name": "字段二", "value_type": "string", "nullable": False, "enabled": True, "description": "", "display_order": 20},
    ]
    with pytest.raises(IntegrityError):
        storage.create_region_with_fields_and_default_sql({
            "board_code": "report_submission", "region_code": "custom_region_duplicate01", "name": "不应保留",
            "shape": "list", "description": "", "display_order": 996,
        }, fields)
    assert all(item["region_code"] != "custom_region_duplicate01" for item in storage.list_regions("report_submission"))


def test_field_change_switches_system_source_and_invalidates_in_one_version(storage) -> None:
    region = storage.list_regions("report_submission")[0]
    source = storage.get_source_config(region["id"])
    configured = storage.save_source_config(region["id"], {
        "tested_signature": "a" * 64,
        "tested_at": source["created_at"],
        "tested_by": "admin",
    }, source["row_version"])

    field = storage.create_field_and_invalidate_source(region["id"], {
        "field_alias": "transactional_value",
        "name": "事务字段",
        "value_type": "string",
        "nullable": False,
        "enabled": True,
        "description": "事务测试",
        "display_order": 999,
    })

    source = storage.get_source_config(region["id"])
    assert field["field_alias"] == "transactional_value"
    assert source["source_mode"] == "sql"
    assert source["tested_signature"] is None
    assert source["tested_at"] is None
    assert source["tested_by"] is None
    assert source["row_version"] == configured["row_version"] + 1


def test_field_change_rolls_back_when_source_invalidation_fails(storage, monkeypatch) -> None:
    region = storage.list_regions("report_submission")[0]
    before_fields = storage.list_fields(region["id"])
    before_source = storage.get_source_config(region["id"])

    def fail_invalidation(connection, region_id, **kwargs):
        raise RuntimeError("source invalidation failed")

    monkeypatch.setattr(
        storage,
        "_invalidate_source_test_with_connection",
        fail_invalidation,
        raising=False,
    )
    with pytest.raises(RuntimeError, match="source invalidation failed"):
        storage.create_field_and_invalidate_source(region["id"], {
            "field_alias": "rolled_back_value",
            "name": "回滚字段",
            "value_type": "string",
            "nullable": False,
            "enabled": True,
            "description": "回滚测试",
            "display_order": 999,
        })

    assert storage.list_fields(region["id"]) == before_fields
    assert storage.get_source_config(region["id"]) == before_source


def test_second_field_disable_cannot_leave_region_without_enabled_fields(storage) -> None:
    region = storage.create_region({
        "board_code": "report_submission",
        "region_code": "custom_region_bbbbbb222222",
        "name": "并发禁用保护",
        "shape": "list",
        "description": "两个字段",
        "display_order": 998,
    })
    storage.save_source_config(region["id"], {"source_mode": "sql"}, expected_version=None)
    first = storage.create_field(region["id"], {
        "field_alias": "first_value",
        "name": "第一字段",
        "value_type": "string",
        "nullable": False,
        "enabled": True,
        "description": "",
        "display_order": 10,
    })
    second = storage.create_field(region["id"], {
        "field_alias": "second_value",
        "name": "第二字段",
        "value_type": "string",
        "nullable": False,
        "enabled": True,
        "description": "",
        "display_order": 20,
    })

    source_before = storage.get_source_config(region["id"])
    storage.update_field_and_invalidate_source(first["id"], {"enabled": False}, first["row_version"])
    source_after_first_disable = storage.get_source_config(region["id"])
    assert source_after_first_disable["row_version"] == source_before["row_version"] + 1
    assert source_after_first_disable["tested_signature"] is None
    with pytest.raises(ValueError, match="至少保留一个启用字段"):
        storage.update_field_and_invalidate_source(second["id"], {"enabled": False}, second["row_version"])

    assert [item["field_alias"] for item in storage.list_fields(region["id"], include_disabled=False)] == [
        "second_value",
    ]
    assert storage.get_source_config(region["id"])["row_version"] == source_after_first_disable["row_version"]


def test_field_update_rolls_back_when_source_invalidation_fails(storage, monkeypatch) -> None:
    region = storage.list_regions("report_submission")[0]
    field = storage.list_fields(region["id"])[0]
    before_source = storage.get_source_config(region["id"])

    def fail_invalidation(connection, region_id, **kwargs):
        raise RuntimeError("source invalidation failed")

    monkeypatch.setattr(storage, "_invalidate_source_test_with_connection", fail_invalidation)
    with pytest.raises(RuntimeError, match="source invalidation failed"):
        storage.update_field_and_invalidate_source(
            field["id"], {"name": "不应写入"}, field["row_version"]
        )

    assert storage.get_field(field["id"]) == field
    assert storage.get_source_config(region["id"]) == before_source
