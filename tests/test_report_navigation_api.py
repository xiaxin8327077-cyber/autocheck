from datetime import date

from auto_check.app.server import ApiRouter
from mysql_config_test_support import MemoryApplicationDatabase


class FakeReportNavigationService:
    def __init__(self):
        self.calls = []

    def dashboard(self, *, period, current_user):
        self.calls.append(("dashboard", period, current_user))
        return {"period": period, "report_month": "2026-07", "cards": [], "processes": []}

    def set_manual_state(self, step_code, action, report_month, current_user):
        self.calls.append(("manual", step_code, action, report_month, current_user))
        return {"ok": True, "step_code": step_code, "action": action}

    def update_schedule(self, process_code, report_month, report_date, current_user):
        self.calls.append(("schedule", process_code, report_month, report_date, current_user))
        return {"ok": True, "report_date": report_date}


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

