from __future__ import annotations

from threading import Thread

import pytest

def test_dropin_module_needs_no_central_registration(dropin_runtime):
    runtime = dropin_runtime()

    runtime.start()

    modules = runtime.public_modules({"id": "1", "role": "admin"})
    assert [module["id"] for module in modules] == ["report_demo"]
    assert modules[0]["navigation"] == [
        {
            "id": "report-demo",
            "label": "Report demo",
            "route": "report-demo",
            "order": 90,
            "permission": "report_demo.view",
        }
    ]

    response = runtime.dispatch(
        method="GET",
        path="/api/modules/report-demo/health",
        query={},
        body=None,
        current_user={"id": "1", "username": "admin", "role": "admin"},
    )
    assert response.status == 200
    assert response.body == {"module": "report_demo", "status": "ok"}

    asset = runtime.read_asset("report_demo", "index.js")
    assert b"export function mount" in asset.content
    assert dropin_runtime.database.tables == {"report_demo_items": {"id", "name"}}
    assert dropin_runtime.database.schema_versions == {"report_demo": 1}
    assert dropin_runtime.database.completed_migrations == {"report_demo": [1]}
    assert dropin_runtime.lifecycle_calls == ["report_demo:start"]

    runtime.stop()

    assert dropin_runtime.lifecycle_calls == ["report_demo:start", "report_demo:stop"]


def test_disabling_dropin_module_removes_api_navigation_and_tasks(dropin_runtime):
    runtime = dropin_runtime()
    runtime.start()
    executor = runtime.context_for("report_demo").background_executor
    assert dropin_runtime.task_started.wait(0.5)

    errors = []
    disabling = Thread(
        target=lambda: _disable_module(runtime, errors),
        daemon=True,
    )
    disabling.start()
    assert dropin_runtime.stop_entered.wait(0.5)
    assert disabling.is_alive()
    dropin_runtime.task_release.set()
    disabling.join(1)

    assert not disabling.is_alive()
    assert errors == []
    assert dropin_runtime.task_state.future is not None
    assert dropin_runtime.task_state.future.done()
    with pytest.raises(RuntimeError, match="stopped"):
        executor.submit(lambda: None)

    assert runtime.public_modules({"role": "admin"}) == []
    assert runtime.dispatch(
        method="GET",
        path="/api/modules/report-demo/health",
        query={},
        body=None,
        current_user={"role": "admin"},
    ).status == 404
    with pytest.raises(LookupError):
        runtime.read_asset("report_demo", "index.js")
    assert dropin_runtime.lifecycle_calls == ["report_demo:start", "report_demo:stop"]


def _disable_module(runtime, errors):
    try:
        runtime.set_enabled("report_demo", False, {"role": "admin"})
    except Exception as error:
        errors.append(error)
