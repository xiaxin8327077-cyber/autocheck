from datetime import datetime
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from auto_check.app.report_check_config import (
    DEFAULT_REPORT_CHECK_DATA_SOURCE,
    DEFAULT_REPORT_CHECK_REMAINING_SQL,
    DEFAULT_REPORT_CHECK_TOTAL_SQL,
    default_report_check_config,
    normalize_report_check_config,
    validate_report_check_sql,
)
from auto_check.app import report_check_statistics
from auto_check.app.report_check_statistics import ReportCheckStatistics
from auto_check.app.report_navigation_platform import CardStatisticsRequest
from mysql_config_test_support import MemoryApplicationDatabase

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_server_registers_report_check_for_collection_without_dashboard_refresh():
    source = Path("src/auto_check/app/server.py").read_text(encoding="utf-8")
    registration = (
        "semantics_version=REPORT_CHECK_SEMANTICS_VERSION,\n"
        "            include_in_collect=True,\n"
        "            refresh_on_dashboard=False,"
    )
    assert registration in source


class FakeClient:
    def __init__(self, rows):
        self._rows = list(rows)
        self.calls = []

    def fetch_one(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        if not self._rows:
            return None
        return self._rows.pop(0)


def _request(previous_end=datetime(2026, 7, 1, 0, 0)):
    return CardStatisticsRequest(
        card_code="report_check",
        period_kind="month",
        period_start=datetime(2026, 7, 1, 0, 0, tzinfo=SHANGHAI),
        period_end_exclusive=datetime(2026, 8, 1, 0, 0, tzinfo=SHANGHAI),
        previous_period_start=datetime(2026, 6, 1, 0, 0, tzinfo=SHANGHAI),
        previous_period_end_exclusive=previous_end.replace(tzinfo=SHANGHAI),
        as_of=datetime(2026, 7, 16, 9, 30, tzinfo=SHANGHAI),
    )


def test_validate_report_check_sql_rejects_unsafe_or_empty_values():
    for bad in ["", "   ", "delete from ck_rule", "update ck_rule set x=1", "select 1; select 2", "x" * 8001]:
        with pytest.raises(ValueError):
            validate_report_check_sql(bad)
    assert validate_report_check_sql("  select 1;  ") == "select 1"
    assert validate_report_check_sql("WITH a AS (select 1) select * from a")


def test_normalize_report_check_config_requires_all_fields():
    with pytest.raises(ValueError):
        normalize_report_check_config({})
    with pytest.raises(ValueError):
        normalize_report_check_config(
            {"data_source": "reg-report-analysis", "total_sql": DEFAULT_REPORT_CHECK_TOTAL_SQL}
        )
    config = normalize_report_check_config(default_report_check_config())
    assert config["data_source"] == DEFAULT_REPORT_CHECK_DATA_SOURCE
    assert config["description"] == "仅统计不可提交的报文错误"
    assert normalize_report_check_config(
        {
            "data_source": "reg-report-analysis",
            "total_sql": "select 1",
            "remaining_sql": "select ${report_period}",
            "description": "  仅统计测试错误  ",
        }
    )["description"] == "仅统计测试错误"
    with pytest.raises(ValueError, match="描述文字不能超过"):
        normalize_report_check_config(
            {
                "data_source": "reg-report-analysis",
                "total_sql": "select 1",
                "remaining_sql": "select ${report_period}",
                "description": "说" * 101,
            }
        )
    with pytest.raises(ValueError, match="remaining_sql 必须包含报送期占位符"):
        normalize_report_check_config(
            {
                "data_source": "reg-report-analysis",
                "total_sql": "select 1",
                "remaining_sql": "select 2",
            }
        )


def test_config_roundtrip_through_app_settings_and_bad_value_fallback():
    from auto_check.app.report_check_config import (
        REPORT_CHECK_SETTING_KEY,
        load_report_check_config,
        save_report_check_config,
    )
    from auto_check.app.storage_config import save_setting

    database = MemoryApplicationDatabase()
    with database.connect() as connection:
        assert load_report_check_config(connection) == default_report_check_config()
        save_report_check_config(
            connection,
            {
                "data_source": "other-source",
                "total_sql": "select * from ck_rule",
                "remaining_sql": "select ${report_period}",
            },
        )
        assert load_report_check_config(connection) == {
            "data_source": "other-source",
            "total_sql": "select * from ck_rule",
            "remaining_sql": "select ${report_period}",
            "description": "仅统计不可提交的报文错误",
        }
        save_setting(connection, REPORT_CHECK_SETTING_KEY, {"data_source": "", "total_sql": "", "remaining_sql": ""})
        assert load_report_check_config(connection) == default_report_check_config()


def _provider(rows, config=None):
    client = FakeClient(rows)
    return (
        ReportCheckStatistics(
            MemoryApplicationDatabase(),
            config_loader=lambda connection: config or default_report_check_config(),
            data_source_loader=lambda: [
                type("Entry", (), {"name": DEFAULT_REPORT_CHECK_DATA_SOURCE, "config": object()})()
            ],
            client_factory=lambda cfg: client,
            now=lambda: datetime(2026, 7, 16, 9, 30),
        ),
        client,
    )


def test_provider_maps_total_and_remaining_for_current_reporting_period():
    provider, client = _provider([{"c": 26}, {"c": 4}])
    result = provider(_request())
    assert (result.total, result.completed, result.incomplete, result.previous_completed) == (26, 22, 4, 22)
    assert result.semantics_version == 2
    total_sql, total_params = client.calls[0]
    assert total_sql == f"select count(1) from ({DEFAULT_REPORT_CHECK_TOTAL_SQL}) t"
    assert total_params == ()
    assert client.calls[1] == (
        report_check_statistics.REPORT_PERIOD_PLACEHOLDER.sub("%s", DEFAULT_REPORT_CHECK_REMAINING_SQL),
        ("2026_06_30",),
    )
    assert len(client.calls) == 2


def test_provider_rejects_remaining_sql_without_report_period_placeholder():
    config = dict(default_report_check_config())
    config["remaining_sql"] = "select 4"
    provider, _ = _provider([{"c": 10}, {"c": 4}], config=config)
    with pytest.raises(ValueError, match="报送期占位符"):
        provider(_request())


def test_provider_clamps_completed_when_remaining_exceeds_total():
    provider, _ = _provider([{"c": 3}, {"c": 9}])
    result = provider(_request())
    assert (result.total, result.completed, result.incomplete) == (3, 0, 9)


def test_provider_compares_completed_count_with_previous_calendar_day():
    database = MemoryApplicationDatabase()
    entry = type("Entry", (), {"name": DEFAULT_REPORT_CHECK_DATA_SOURCE, "config": object()})()

    def build(rows, current):
        client = FakeClient(rows)
        return ReportCheckStatistics(
            database,
            config_loader=lambda connection: default_report_check_config(),
            data_source_loader=lambda: [entry],
            client_factory=lambda cfg: client,
            now=lambda: current,
        )

    first = build([{"c": 10}, {"c": 4}], datetime(2026, 7, 15, 9, 0))(
        replace(_request(), as_of=datetime(2026, 7, 15, 9, 0, tzinfo=SHANGHAI))
    )
    second = build([{"c": 10}, {"c": 2}], datetime(2026, 7, 16, 9, 0))(
        replace(_request(), as_of=datetime(2026, 7, 16, 9, 0, tzinfo=SHANGHAI))
    )

    assert first.previous_completed == first.completed == 6
    assert (second.completed, second.previous_completed) == (8, 6)


def test_provider_rejects_missing_data_source_and_bad_scalar():
    missing = ReportCheckStatistics(
        MemoryApplicationDatabase(),
        config_loader=lambda connection: default_report_check_config(),
        data_source_loader=lambda: [],
        client_factory=lambda cfg: FakeClient([]),
    )
    with pytest.raises(ValueError):
        missing(_request())

    for rows in [[None], [{"c": "abc"}], [{"c": -1}], []]:
        provider, _ = _provider(rows)
        with pytest.raises(ValueError):
            provider(_request())


def test_report_check_config_api_requires_admin_and_tests_sql(tmp_path):
    from auto_check.app.server import ApiRouter

    database = MemoryApplicationDatabase()
    database.connection.tables["data_sources"].append(
        {
            "id": "1",
            "name": "reg-report-analysis",
            "db_type": "mysql",
            "host": "127.0.0.1",
            "port": 3306,
            "database_name": "analysis",
            "schema_name": "",
            "username": "reader",
            "password_encrypted": "",
            "is_default": True,
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }
    )
    seen = []
    calls = []
    expected_report_date = "2026_06_30"

    class FakeClientFactory:
        def __init__(self, config):
            seen.append(config)

        def fetch_one(self, sql, params=()):
            calls.append((sql, tuple(params)))
            if sql == f"select count(1) from ({DEFAULT_REPORT_CHECK_TOTAL_SQL}) t":
                return {"c": 26}
            return {"c": 4}

    import auto_check.app.server as server_module

    original = server_module.DatabaseClient
    original_now = server_module.beijing_now
    server_module.DatabaseClient = FakeClientFactory
    server_module.beijing_now = lambda: datetime(2026, 7, 16, 9, 30, tzinfo=SHANGHAI)
    try:
        router = ApiRouter(
            config_path=tmp_path / "config.json",
            application_database=database,
        )
        user = {"id": "u2", "username": "user", "role": "user"}
        admin = {"id": "u1", "username": "admin", "role": "admin"}
        for method in ("GET", "POST"):
            status, _ = router.handle(
                method, "/api/report-navigation/report-check-config", {}, current_user=user
            )
            assert status == 403
        status, _ = router.handle(
            "POST", "/api/report-navigation/report-check-config/test", {}, current_user=user
        )
        assert status == 403

        status, payload = router.handle(
            "GET", "/api/report-navigation/report-check-config", None, current_user=admin
        )
        assert status == 200
        assert payload["data_source"] == DEFAULT_REPORT_CHECK_DATA_SOURCE
        assert payload["is_default"] is True
        assert payload["total_sql"] == DEFAULT_REPORT_CHECK_TOTAL_SQL
        assert payload["description"] == "仅统计不可提交的报文错误"

        status, payload = router.handle(
            "POST",
            "/api/report-navigation/report-check-config",
            {"data_source": "", "total_sql": "select 1", "remaining_sql": "select 1"},
            current_user=admin,
        )
        assert status == 400

        status, payload = router.handle(
            "POST",
            "/api/report-navigation/report-check-config/test",
            default_report_check_config(),
            current_user=admin,
        )
        assert status == 200
        assert payload == {"ok": True, "total": 26, "remaining": 4}
        assert calls[-1] == (
            report_check_statistics.REPORT_PERIOD_PLACEHOLDER.sub("%s", DEFAULT_REPORT_CHECK_REMAINING_SQL),
            (expected_report_date,),
        )

        status, payload = router.handle(
            "POST",
            "/api/report-navigation/report-check-config",
            {
                "data_source": "reg-report-analysis",
                "total_sql": "select * from ck_rule",
                "remaining_sql": "select ${report_period}",
                "description": "仅统计自定义错误",
            },
            current_user=admin,
        )
        assert status == 200
        assert payload["is_default"] is False
        status, payload = router.handle(
            "GET", "/api/report-navigation/report-check-config", None, current_user=admin
        )
        assert payload["total_sql"] == "select * from ck_rule"
        assert payload["description"] == "仅统计自定义错误"
    finally:
        server_module.DatabaseClient = original
        server_module.beijing_now = original_now


def test_report_check_provider_registered_on_real_service_dashboard(tmp_path):
    from auto_check.app.report_navigation import ReportNavigationService

    database = MemoryApplicationDatabase()
    service = ReportNavigationService(database)
    handle = service.register_card_provider(
        owner="builtin.report_check",
        card_code="report_check",
        provider=ReportCheckStatistics(
            database,
            config_loader=lambda connection: default_report_check_config(),
            data_source_loader=lambda: [],
            client_factory=lambda cfg: FakeClient([]),
        ),
        semantics_version=1,
        include_in_collect=False,
        refresh_on_dashboard=True,
    )
    try:
        payload = service.dashboard(
            period="month",
            current_user={"username": "admin", "role": "admin"},
            now=datetime(2026, 7, 16, 9, 30),
        )
        card = next(item for item in payload["cards"] if item["card_code"] == "report_check")
        assert card["source"] == "provider"
        assert card["available"] is False
        assert card["total_count"] is None
        assert card["description"] == "仅统计不可提交的报文错误"
        assert payload["card_maintenance"] == {} or "report_check" not in payload["card_maintenance"]
    finally:
        handle.close()
