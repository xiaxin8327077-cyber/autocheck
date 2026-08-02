from datetime import date

from auto_check.app.server import ApiRouter
from mysql_config_test_support import MemoryApplicationDatabase


class FakeReportNavigationService:
    def __init__(self):
        self.calls = []
        self.refresh_result = {
            "status": "completed",
            "cooldown_seconds": 300,
            "retry_after_seconds": 300,
            "error_message": "",
        }

    def dashboard(self, *, period, current_user):
        self.calls.append(("dashboard", period, current_user))
        return {"period": period, "report_month": "2026-07", "cards": [], "processes": []}

    def set_manual_state(self, step_code, action, report_month, current_user):
        self.calls.append(("manual", step_code, action, report_month, current_user))
        return {"ok": True, "step_code": step_code, "action": action}

    def update_schedule(self, process_code, report_month, report_date, current_user):
        self.calls.append(("schedule", process_code, report_month, report_date, current_user))
        return {"ok": True, "report_date": report_date}

    def update_schedule_owner(self, process_code, report_month, owner_name, current_user):
        self.calls.append(("schedule-owner", process_code, report_month, owner_name, current_user))
        return {"ok": True, "owner_name": owner_name}

    def update_card_manual_values(self, card_code, values, current_user):
        self.calls.append(("card-values", card_code, values, current_user))
        return {"ok": True, "card_code": card_code}

    def manual_refresh(self, *, current_user):
        self.calls.append(("refresh", current_user))
        return dict(self.refresh_result)


def _admin():
    return {"id": "u1", "username": "admin", "display_name": "管理员", "role": "admin"}


def _user():
    return {"id": "u2", "username": "user", "display_name": "用户", "role": "user"}


def _router(tmp_path):
    service = FakeReportNavigationService()
    router = ApiRouter(
        config_path=tmp_path / "config.json",
        application_database=MemoryApplicationDatabase(),
        report_navigation_service=service,
    )
    return router, service


def test_dashboard_route_passes_selected_period_and_current_user(tmp_path):
    router, service = _router(tmp_path)
    router._query_string = "period=quarter"

    status, payload = router.handle(
        "GET",
        "/api/report-navigation/dashboard",
        None,
        current_user=_user(),
    )

    assert status == 200
    assert payload["period"] == "quarter"
    assert service.calls == [("dashboard", "quarter", _user())]


def test_manual_complete_and_cancel_require_admin_and_delegate_exact_action(tmp_path):
    router, service = _router(tmp_path)
    body = {"report_month": "2026-07"}

    denied, denied_payload = router.handle(
        "POST",
        "/api/report-navigation/steps/pbc_template_7/manual-complete",
        body,
        current_user=_user(),
    )
    completed, _ = router.handle(
        "POST",
        "/api/report-navigation/steps/pbc_template_7/manual-complete",
        body,
        current_user=_admin(),
    )
    cancelled, _ = router.handle(
        "POST",
        "/api/report-navigation/steps/pbc_template_7/manual-cancel",
        body,
        current_user=_admin(),
    )

    assert (denied, denied_payload["error"]) == (403, "admin role required")
    assert completed == 200
    assert cancelled == 200
    assert [call[2] for call in service.calls] == ["manual-complete", "manual-cancel"]


def test_schedule_update_requires_admin_and_passes_month_and_date(tmp_path):
    router, service = _router(tmp_path)
    body = {"report_month": "2026-07", "report_date": "2026-07-20"}

    denied, _ = router.handle(
        "POST",
        "/api/report-navigation/schedules/east5",
        body,
        current_user=_user(),
    )
    allowed, payload = router.handle(
        "POST",
        "/api/report-navigation/schedules/east5",
        body,
        current_user=_admin(),
    )

    assert denied == 403
    assert allowed == 200
    assert payload["report_date"] == "2026-07-20"
    assert service.calls == [("schedule", "east5", "2026-07", "2026-07-20", _admin())]


def test_schedule_owner_update_requires_admin_and_passes_month_and_name(tmp_path):
    router, service = _router(tmp_path)
    body = {"report_month": "2026-07", "owner_name": "张智核"}

    denied, _ = router.handle(
        "POST",
        "/api/report-navigation/schedule-owners/east5",
        body,
        current_user=_user(),
    )
    allowed, payload = router.handle(
        "POST",
        "/api/report-navigation/schedule-owners/east5",
        body,
        current_user=_admin(),
    )

    assert denied == 403
    assert allowed == 200
    assert payload["owner_name"] == "张智核"
    assert service.calls == [
        ("schedule-owner", "east5", "2026-07", "张智核", _admin())
    ]


def test_governance_card_values_require_admin_and_pass_all_four_periods(tmp_path):
    router, service = _router(tmp_path)
    values = {
        period: {"completed_count": index, "incomplete_count": index + 1}
        for index, period in enumerate(("week", "month", "quarter", "year"), start=1)
    }
    body = {"values": values}

    denied, _ = router.handle(
        "POST", "/api/report-navigation/cards/data_governance", body, current_user=_user()
    )
    allowed, payload = router.handle(
        "POST", "/api/report-navigation/cards/data_governance", body, current_user=_admin()
    )

    assert denied == 403
    assert allowed == 200
    assert payload == {"ok": True, "card_code": "data_governance"}
    assert service.calls == [("card-values", "data_governance", values, _admin())]


def test_provider_managed_governance_card_values_return_conflict(tmp_path):
    from auto_check.app.report_navigation_platform import ProviderManagedCardError

    router, service = _router(tmp_path)
    service.update_card_manual_values = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        ProviderManagedCardError("card statistics are managed by a provider")
    )
    values = {
        period: {"completed_count": 1, "incomplete_count": 2}
        for period in ("week", "month", "quarter", "year")
    }

    status, payload = router.handle(
        "POST",
        "/api/report-navigation/cards/special_governance",
        {"values": values},
        current_user=_admin(),
    )

    assert status == 409
    assert payload == {"error": "card statistics are managed by a provider"}


def test_manual_refresh_route_maps_success_cooldown_busy_and_failure_statuses(tmp_path):
    router, service = _router(tmp_path)

    success, success_payload = router.handle(
        "POST", "/api/report-navigation/refresh", {}, current_user=_user()
    )
    service.refresh_result = {
        "status": "cooldown",
        "retry_after_seconds": 120,
        "error_message": "请等待 2 分钟后再刷新",
    }
    cooldown, cooldown_payload = router.handle(
        "POST", "/api/report-navigation/refresh", {}, current_user=_user()
    )
    service.refresh_result = {
        "status": "skipped",
        "retry_after_seconds": 0,
        "error_message": "统计任务正在执行",
    }
    busy, busy_payload = router.handle(
        "POST", "/api/report-navigation/refresh", {}, current_user=_user()
    )
    service.refresh_result = {
        "status": "failed",
        "cooldown_seconds": 300,
        "retry_after_seconds": 300,
        "error_message": "业务数据源连接失败",
    }
    failed, failed_payload = router.handle(
        "POST", "/api/report-navigation/refresh", {}, current_user=_user()
    )

    assert (success, success_payload["status"]) == (200, "completed")
    assert (cooldown, cooldown_payload["retry_after_seconds"]) == (429, 120)
    assert cooldown_payload["error"] == "请等待 2 分钟后再刷新"
    assert (busy, busy_payload["error"]) == (409, "统计任务正在执行")
    assert (failed, failed_payload["error"]) == (500, "业务数据源连接失败")
    assert service.calls == [("refresh", _user())] * 4
