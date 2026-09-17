from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from auto_check.app.module_system.contracts import ModuleHttpResponse


class _Database:
    def __init__(self) -> None:
        self._engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        event.listen(
            self._engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
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
def store():
    from auto_check.modules.dashboard_management.external_api_monitoring import (
        METADATA,
        ExternalApiMonitoringStore,
    )

    database = _Database()
    METADATA.create_all(database._engine)
    return ExternalApiMonitoringStore(database)


def _record(**overrides):
    from auto_check.modules.dashboard_management.external_api_monitoring import ExternalApiCallRecord

    values = {
        "called_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "board_code": "report_submission",
        "http_status": 200,
        "result_status": "success",
        "failed_region_count": 0,
        "duration_ms": 12,
        "request_id": "req-test",
        "caller_ip": "198.51.100.4",
    }
    values.update(overrides)
    return ExternalApiCallRecord(**values)


def test_store_cleans_records_older_than_30_days_and_keeps_recent(store):
    from auto_check.modules.dashboard_management.external_api_monitoring import EXTERNAL_API_CALLS

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now - timedelta(days=31)
    with store._database.transaction() as connection:
        connection.execute(EXTERNAL_API_CALLS.insert(), {
            "called_at": old,
            "board_code": "report_submission",
            "http_status": 200,
            "result_status": "success",
            "failed_region_count": 0,
            "duration_ms": 5,
            "request_id": "req-old",
            "caller_ip": "198.51.100.4",
        })

    cutoff = now - timedelta(days=30)
    store.record_and_cleanup(_record(request_id="req-new"), cutoff)

    with store._database.connect() as connection:
        rows = connection.execute(EXTERNAL_API_CALLS.select()).mappings().all()
    assert [row["request_id"] for row in rows] == ["req-new"]


def test_store_summary_counts_results_and_average_duration(store):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    store.record_and_cleanup(_record(
        called_at=now - timedelta(hours=1),
        request_id="req-1",
        result_status="success",
        duration_ms=10,
    ), now - timedelta(days=30))
    store.record_and_cleanup(_record(
        called_at=now - timedelta(hours=2),
        request_id="req-2",
        result_status="partial",
        failed_region_count=2,
        duration_ms=20,
    ), now - timedelta(days=30))
    store.record_and_cleanup(_record(
        called_at=now - timedelta(hours=3),
        request_id="req-3",
        result_status="error",
        http_status=500,
        duration_ms=30,
    ), now - timedelta(days=30))
    store.record_and_cleanup(_record(
        called_at=now - timedelta(hours=25),
        request_id="req-outside-summary-window",
        result_status="error",
        http_status=500,
        duration_ms=999,
    ), now - timedelta(days=30))

    summary = store.summary(now - timedelta(hours=24), now - timedelta(days=30))

    assert summary["total"] == 3
    assert summary["success"] == 1
    assert summary["partial"] == 1
    assert summary["failed"] == 1
    assert summary["average_duration_ms"] == 20
    assert summary["last_called_at"] == now - timedelta(hours=1)
    assert summary["last_success_at"] == now - timedelta(hours=1)


def test_store_summary_returns_zero_values_when_no_calls_exist(store):
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    summary = store.summary(now - timedelta(hours=24), now - timedelta(days=30))

    assert summary == {
        "total": 0,
        "success": 0,
        "partial": 0,
        "failed": 0,
        "average_duration_ms": 0,
        "last_called_at": None,
        "last_success_at": None,
    }


def test_store_list_calls_filters_by_ip_and_orders_descending(store):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for index in range(3):
        store.record_and_cleanup(_record(
            called_at=now - timedelta(minutes=index),
            request_id=f"req-{index}",
            caller_ip="203.0.113.9" if index == 1 else "198.51.100.4",
        ), now - timedelta(days=30))

    result = store.list_calls({"caller_ip": "203.0.113.9"}, now - timedelta(days=30))

    assert result["total"] == 1
    assert result["items"][0]["request_id"] == "req-1"
    assert result["items"][0]["caller_ip"] == "203.0.113.9"


def test_store_list_calls_paginates_with_stable_order(store):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for index in range(5):
        store.record_and_cleanup(_record(
            called_at=now - timedelta(minutes=index),
            request_id=f"req-{index}",
        ), now - timedelta(days=30))

    first_page = store.list_calls({"page": 1, "page_size": 2}, now - timedelta(days=30))
    assert first_page["total"] == 5
    assert first_page["total_pages"] == 3
    assert [item["request_id"] for item in first_page["items"]] == ["req-0", "req-1"]

    last_page = store.list_calls({"page": 3, "page_size": 2}, now - timedelta(days=30))
    assert [item["request_id"] for item in last_page["items"]] == ["req-4"]

    out_of_range = store.list_calls({"page": 99, "page_size": 2}, now - timedelta(days=30))
    assert out_of_range["page"] == 3
    assert [item["request_id"] for item in out_of_range["items"]] == ["req-4"]


def test_store_list_calls_empty_result_returns_page_one(store):
    result = store.list_calls({}, datetime.now(timezone.utc) - timedelta(days=30))

    assert result["items"] == []
    assert result["page"] == 1
    assert result["total_pages"] == 1
    assert result["total"] == 0


class _FakeStore:
    def __init__(self) -> None:
        self.records = []
        self.fail_on_record = False

    def record_and_cleanup(self, record, cutoff):
        if self.fail_on_record:
            raise RuntimeError("database unavailable")
        self.records.append(record)

    def summary(self, since, cutoff):
        return {
            "total": len(self.records),
            "success": sum(1 for r in self.records if r.result_status == "success"),
            "partial": sum(1 for r in self.records if r.result_status == "partial"),
            "failed": sum(1 for r in self.records if r.result_status == "error"),
            "average_duration_ms": 0,
            "last_called_at": None,
            "last_success_at": None,
        }

    def list_calls(self, query, cutoff):
        return {"items": [], "page": 1, "page_size": 10, "total": 0, "total_pages": 1}


class _FakeStatusFacade:
    def __init__(self, token_configured=True):
        self._token_configured = token_configured

    def get_status(self):
        from auto_check.app.external_api import ExternalApiStatusSnapshot
        return ExternalApiStatusSnapshot(token_configured=self._token_configured)


def _service(store=None, token_configured=True, utc_now=None, monotonic_now=None):
    from auto_check.modules.dashboard_management.external_api_monitoring import ExternalApiMonitoringService
    return ExternalApiMonitoringService(
        store or _FakeStore(),
        status_facade=_FakeStatusFacade(token_configured),
        logger=__import__("logging").getLogger("test"),
        utc_now=utc_now or (lambda: datetime.now(timezone.utc)),
        monotonic_now=monotonic_now or (lambda: 0.0),
    )


def test_service_classifies_partial_response_with_failed_region_count():
    service = _service()
    trace = service.begin_call("report_submission", "203.0.113.8", "req-1")
    service.finish_call(trace, ModuleHttpResponse.json(200, {
        "status": "partial",
        "data": {"regions": [{"status": "success"}, {"status": "error"}]},
        "meta": {"request_id": "req-1"},
    }))
    record = service._store.records[0]
    assert record.result_status == "partial"
    assert record.failed_region_count == 1
    assert record.caller_ip == "203.0.113.8"
    assert record.duration_ms >= 0


def test_service_classifies_404_and_500_as_error_with_safe_summary():
    service = _service()
    trace = service.begin_call("report_submission", "203.0.113.8", "req-404")
    service.finish_call(trace, ModuleHttpResponse.json(404, {
        "error": {"code": "resource_not_found", "message": "看板不存在"},
        "meta": {"request_id": "req-404"},
    }))
    record = service._store.records[0]
    assert record.result_status == "error"
    assert record.http_status == 404
    assert record.error_code == "resource_not_found"
    assert record.error_message == "看板不存在"
    assert record.failed_region_count == 0

    trace = service.begin_call("report_submission", "203.0.113.8", "req-500")
    service.finish_call(trace, ModuleHttpResponse.json(500, {
        "error": {"code": "internal_error", "message": "系统暂时无法处理该请求"},
        "meta": {"request_id": "req-500"},
    }))
    record = service._store.records[1]
    assert record.result_status == "error"
    assert record.http_status == 500
    assert record.error_code == "internal_error"


def test_service_finish_call_swallows_store_errors():
    store = _FakeStore()
    store.fail_on_record = True
    service = _service(store)
    trace = service.begin_call("report_submission", "203.0.113.8", "req-1")
    service.finish_call(trace, ModuleHttpResponse.json(200, {"status": "success", "meta": {"request_id": "req-1"}}))
    assert store.records == []


def test_service_rounds_positive_duration_up_and_stores_naive_utc_time():
    now = datetime(2026, 9, 16, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    ticks = iter((10.0, 10.0001))
    service = _service(utc_now=lambda: now, monotonic_now=lambda: next(ticks))

    trace = service.begin_call("report_submission", "203.0.113.8", "req-duration")
    service.finish_call(trace, ModuleHttpResponse.json(200, {
        "status": "success",
        "data": {"regions": []},
        "meta": {"request_id": "req-duration"},
    }))

    record = service._store.records[0]
    assert record.duration_ms == 1
    assert record.called_at == datetime(2026, 9, 16, 0, 0)
    assert record.called_at.tzinfo is None


def test_service_accepts_unknown_peer_ip_as_safe_fallback():
    service = _service()

    trace = service.begin_call("report_submission", "unknown", "req-unknown-ip")

    assert trace.caller_ip == "unknown"


def test_service_monitor_summary_reports_token_configured_and_endpoints():
    service = _service(token_configured=True)
    summary = service.monitor_summary()
    assert summary["enabled"] is True
    assert summary["token_configured"] is True
    assert summary["retention_days"] == 30
    assert len(summary["endpoints"]) == 2
    assert summary["last_24_hours"]["total"] == 0


def test_service_monitor_summary_reports_token_not_configured():
    service = _service(token_configured=False)
    summary = service.monitor_summary()
    assert summary["enabled"] is False
    assert summary["token_configured"] is False


def test_service_monitor_summary_uses_module_credential_status_as_authority():
    service = _service(token_configured=True)

    unavailable = service.monitor_summary(
        credential_status={"configured": False, "source": "none", "generated_at": None}
    )
    managed = service.monitor_summary(
        credential_status={
            "configured": True,
            "source": "managed",
            "generated_at": datetime(2026, 9, 17, 1, 2, 3),
        }
    )

    assert unavailable["token_configured"] is False
    assert unavailable["token_source"] == "none"
    assert unavailable["token_generated_at"] is None
    assert managed["token_configured"] is True
    assert managed["token_source"] == "managed"
    assert managed["token_generated_at"] == "2026-09-17T01:02:03+00:00"


def test_service_outputs_database_timestamps_as_explicit_utc_iso_strings():
    called_at = datetime(2026, 9, 16, 1, 2, 3)

    class _TimestampStore(_FakeStore):
        def summary(self, since, cutoff):
            result = dict(super().summary(since, cutoff))
            result["last_called_at"] = called_at
            result["last_success_at"] = called_at
            return result

        def list_calls(self, query, cutoff):
            return {
                "items": [{"called_at": called_at, "request_id": "req-time"}],
                "page": 1,
                "page_size": 10,
                "total": 1,
                "total_pages": 1,
            }

    service = _service(_TimestampStore())

    summary = service.monitor_summary()
    calls = service.list_calls({})

    assert summary["last_called_at"] == "2026-09-16T01:02:03+00:00"
    assert summary["last_success_at"] == "2026-09-16T01:02:03+00:00"
    assert calls["items"][0]["called_at"] == "2026-09-16T01:02:03+00:00"


def test_service_list_calls_validates_query_parameters():
    from auto_check.modules.dashboard_management.validator import ValidationError
    service = _service()
    for bad_query in [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"board_code": "unknown_board"},
        {"result_status": "unknown"},
        {"caller_ip": "not-an-ip"},
        {"started_at": "not-a-date"},
        {"ended_at": "not-a-date"},
        {"started_at": "2026-09-16T10:00:00+08:00", "ended_at": "2026-09-16T09:00:00+08:00"},
    ]:
        try:
            service.list_calls(bad_query)
            raise AssertionError(f"expected ValidationError for {bad_query}")
        except ValidationError:
            pass


def test_service_list_calls_normalizes_timezone_filters_to_naive_utc():
    store = _FakeStore()
    captured = {}

    def capture(query, cutoff):
        captured["query"] = query
        return {"items": [], "page": 1, "page_size": 10, "total": 0, "total_pages": 1}

    store.list_calls = capture
    service = _service(store)

    service.list_calls({
        "started_at": "2026-09-16T08:00:00+08:00",
        "ended_at": "2026-09-16T09:30:00+08:00",
    })

    assert captured["query"].started_at == datetime(2026, 9, 16, 0, 0)
    assert captured["query"].ended_at == datetime(2026, 9, 16, 1, 30)
