from __future__ import annotations

from pathlib import Path
from concurrent.futures import CancelledError
from threading import Event, Thread, Timer

import pytest

from auto_check.app.module_system.contracts import (
    ModuleBootstrapContext,
    ModuleHealth,
    ModuleHttpResponse,
    ModuleManifest,
)
from auto_check.app.module_system.discovery import DiscoveredModule
from auto_check.app.module_system.runtime import (
    ModuleRuntime,
    ModuleRuntimeError,
    ModuleStartupError,
    ModuleTaskLimitError,
)


FIXTURE_PARENT = Path(__file__).resolve().parents[1] / "fixtures"


class _StateStore:
    def __init__(self, database):
        self.enabled: dict[str, bool] = {}
        self.discovered: set[str] = set()
        self.statuses = []

    def save_discovered(self, manifest):
        self.discovered.add(manifest.id)
        self.enabled.setdefault(manifest.id, True)

    def load_enabled(self, module_id):
        return self.enabled.get(module_id)

    def set_enabled(self, module_id, enabled):
        if module_id in self.discovered:
            self.enabled[module_id] = enabled

    def set_status(self, module_id, status, error=""):
        self.statuses.append((module_id, status, error))


class _MigrationRunner:
    def __init__(self, database, schema_registry=None):
        self.schema_registry = schema_registry

    def run(self, manifest, package_name):
        return manifest.schema_version


@pytest.fixture
def runtime_factory(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    import auto_check.app.module_system.runtime as runtime_module
    import module_packages.alpha.module as alpha_module
    import module_packages.beta.module as beta_module

    monkeypatch.setattr(runtime_module, "ModuleStateStore", _StateStore)
    monkeypatch.setattr(runtime_module, "ModuleMigrationRunner", _MigrationRunner)

    def create(module_ids):
        alpha_module.CALLS.clear()
        beta_module.CALLS = alpha_module.CALLS
        context = ModuleBootstrapContext(
            application_database=object(),
            config_path=Path("config.json"),
            temp_root=Path("temp"),
            now=lambda: None,
        )
        runtime = ModuleRuntime.build(context, package_name="module_packages")
        selected = {module_id for module_id in module_ids}
        runtime._loaded = [
            item for item in runtime._loaded if item.discovered.manifest.id in selected
        ]
        return runtime, alpha_module.CALLS

    return create


def _manifest(module_id: str, *, required: bool = False) -> ModuleManifest:
    return ModuleManifest.from_mapping(
        {
            "id": module_id,
            "name": module_id.title(),
            "version": "1.0.0",
            "platform_api": 1,
            "required": required,
            "backend_entry": f"fixture.{module_id}.module:create_module",
            "api_prefix": f"/api/modules/{module_id}",
            "frontend_entry": f"/module-assets/{module_id}/index.js",
            "frontend_style": f"/module-assets/{module_id}/styles.css",
            "navigation": [],
            "permissions": [f"{module_id}.view"],
            "dependencies": [],
            "schema_version": 0,
        }
    )


class _LifecycleModule:
    def __init__(self, manifest, calls, *, start_action=None, health_message=""):
        self.manifest = manifest
        self.calls = calls
        self.start_action = start_action
        self.health_message = health_message
        self.context = None

    def register_routes(self, router):
        return None

    def register_schema(self, registry):
        return None

    def start(self, context):
        self.context = context
        self.calls.append(f"{self.manifest.id}:start")
        if self.start_action:
            self.start_action(context)

    def stop(self):
        self.calls.append(f"{self.manifest.id}:stop")

    def health(self):
        return ModuleHealth(healthy=True, message=self.health_message)


@pytest.fixture
def isolated_runtime_factory(monkeypatch):
    import auto_check.app.module_system.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "ModuleStateStore", _StateStore)
    monkeypatch.setattr(runtime_module, "ModuleMigrationRunner", _MigrationRunner)

    def create(modules):
        factories = {}
        discovered = []
        for module in modules:
            manifest = module.manifest
            discovered.append(DiscoveredModule(f"fixture.{manifest.id}", None, manifest))
            factories[manifest.backend_entry] = lambda module=module: module
        monkeypatch.setattr(
            runtime_module, "load_module_factory", lambda entry: factories[entry]
        )
        context = ModuleBootstrapContext(
            application_database=object(),
            config_path=Path("config.json"),
            temp_root=Path("temp"),
            now=lambda: None,
        )
        return ModuleRuntime(context, discovered)

    return create


def test_runtime_starts_modules_in_dependency_order(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "beta"])

    runtime.start()

    assert calls == ["alpha:start", "beta:start"]
    assert [item["id"] for item in runtime.public_modules({"role": "admin"})] == ["alpha", "beta"]


def test_optional_module_failure_does_not_block_healthy_modules(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "broken_optional"])

    runtime.start()

    assert runtime.status("alpha").value == "enabled"
    assert runtime.status("broken_optional").value == "startup_failed"
    assert [item["id"] for item in runtime.public_modules({"role": "admin"})] == ["alpha"]


def test_required_module_failure_aborts_startup(runtime_factory):
    runtime, calls = runtime_factory(["broken_required"])

    with pytest.raises(ModuleStartupError, match="broken_required"):
        runtime.start()


def test_runtime_stops_enabled_modules_in_reverse_order(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "beta"])
    runtime.start()
    calls.clear()

    runtime.stop()

    assert calls == ["beta:stop", "alpha:stop"]
    runtime.stop()
    assert calls == ["beta:stop", "alpha:stop"]


def test_regular_user_only_receives_view_navigation(runtime_factory):
    runtime, calls = runtime_factory(["alpha"])
    runtime.start()

    modules = runtime.public_modules({"role": "user"})

    assert modules[0]["navigation"] == [
        {
            "id": "alpha",
            "label": "Alpha",
            "route": "alpha",
            "order": 10,
            "permission": "alpha.view",
        }
    ]


def test_admin_statuses_include_disabled_and_failed_modules(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "broken_optional"])
    runtime.start()
    runtime.set_enabled("alpha", False, {"role": "admin"})

    statuses = runtime.admin_statuses({"role": "admin"})

    assert [(item["id"], item["status"]) for item in statuses] == [
        ("alpha", "disabled"),
        ("broken_optional", "startup_failed"),
    ]


def test_runtime_returns_404_for_disabled_module_routes(runtime_factory):
    runtime, calls = runtime_factory(["alpha"])
    runtime.start()
    runtime.set_enabled("alpha", False, {"role": "admin"})

    response = runtime.dispatch(
        method="GET",
        path="/api/modules/alpha/unknown",
        query={},
        body=None,
        current_user={"role": "admin"},
    )

    assert response == ModuleHttpResponse.json(404, {"error": "module route not found"})


def test_runtime_reads_assets_only_for_enabled_modules(runtime_factory):
    runtime, calls = runtime_factory(["alpha"])
    runtime.start()

    assert b"export function mount" in runtime.read_asset("alpha", "index.js").content
    runtime.set_enabled("alpha", False, {"role": "admin"})
    with pytest.raises(LookupError):
        runtime.read_asset("alpha", "index.js")


def test_module_task_executor_limits_module_to_two_outstanding_tasks(runtime_factory):
    runtime, calls = runtime_factory(["alpha"])
    runtime.start()
    executor = runtime.context_for("alpha").background_executor
    release = Event()
    first = executor.submit(release.wait)
    second = executor.submit(release.wait)

    with pytest.raises(ModuleTaskLimitError):
        executor.submit(release.wait)

    release.set()
    first.result(timeout=2)
    second.result(timeout=2)
    runtime.stop()


def test_admin_operations_require_an_administrator(runtime_factory):
    runtime, calls = runtime_factory(["alpha"])

    with pytest.raises(PermissionError):
        runtime.admin_statuses({"role": "user"})
    with pytest.raises(PermissionError):
        runtime.set_enabled("alpha", False, {"role": "user"})


def test_start_failure_stops_partially_started_module_before_resource_cleanup(
    isolated_runtime_factory,
):
    calls = []

    def fail_after_creating_resources(context):
        context.services.register("alpha.worker", 1, object())
        context.events.subscribe("system:ready", lambda payload: None)
        raise RuntimeError("password=not-for-admin")

    module = _LifecycleModule(_manifest("alpha"), calls, start_action=fail_after_creating_resources)
    runtime = isolated_runtime_factory([module])

    runtime.start()

    assert calls == ["alpha:start", "alpha:stop"]
    assert runtime.status("alpha").value == "startup_failed"
    assert runtime._contexts == {}
    with pytest.raises(KeyError):
        runtime._services.resolve("alpha.worker", 1)


def test_teardown_closes_executor_before_module_stop_and_cancels_pending_tasks(
    isolated_runtime_factory,
):
    calls = []
    blockers = [Event() for _ in range(4)]
    pending = []

    def start_with_pending_task(context):
        pending.append(context.background_executor.submit(lambda: None))

    module = _LifecycleModule(_manifest("alpha"), calls, start_action=start_with_pending_task)
    runtime = isolated_runtime_factory([module])
    for blocker in blockers:
        runtime._shared_executor.submit(blocker.wait, 1)
    runtime.start()

    original_stop = module.stop

    def stop_after_executor_is_closed():
        with pytest.raises(RuntimeError, match="stopped"):
            module.context.background_executor.submit(lambda: None)
        original_stop()

    module.stop = stop_after_executor_is_closed
    runtime.set_enabled("alpha", False, {"role": "admin"})
    for blocker in blockers:
        blocker.set()

    assert pending[0].cancelled()
    assert calls == ["alpha:start", "alpha:stop"]
    runtime.stop()


def test_required_failure_rolls_back_started_modules_and_shuts_down_workers(
    isolated_runtime_factory,
):
    calls = []
    task_started = Event()
    task_release = Event()
    futures = []

    def start_task(context):
        def task():
            task_started.set()
            task_release.wait(1)

        futures.append(context.background_executor.submit(task))

    alpha = _LifecycleModule(_manifest("alpha"), calls, start_action=start_task)

    def fail_start(context):
        raise RuntimeError("fixture failure")

    required = _LifecycleModule(
        _manifest("required", required=True), calls, start_action=fail_start
    )
    runtime = isolated_runtime_factory([alpha, required])

    errors = []

    def start_runtime():
        with pytest.raises(ModuleStartupError, match="required") as error:
            runtime.start()
        errors.append(error.value)

    starter = Thread(target=start_runtime)
    starter.start()
    assert task_started.wait(0.2)
    assert starter.is_alive()
    task_release.set()
    starter.join(1)

    assert calls == ["alpha:start", "required:start", "required:stop", "alpha:stop"]
    assert runtime._contexts == {}
    assert runtime._shared_executor_shutdown is True
    assert not starter.is_alive()
    assert len(errors) == 1
    assert futures[0].done()


def test_disabling_before_start_persists_and_start_skips_the_module(isolated_runtime_factory):
    calls = []
    runtime = isolated_runtime_factory([_LifecycleModule(_manifest("alpha"), calls)])

    runtime.set_enabled("alpha", False, {"role": "admin"})
    runtime.start()

    assert calls == []
    assert runtime.status("alpha").value == "disabled"


def test_admin_health_message_is_sanitized_at_the_runtime_boundary(isolated_runtime_factory):
    calls = []
    module = _LifecycleModule(
        _manifest("alpha"),
        calls,
        health_message="postgres://user:password@db.internal/app token=abc C:\\private\\file",
    )
    runtime = isolated_runtime_factory([module])
    runtime.start()

    message = runtime.admin_statuses({"role": "admin"})[0]["health"]["message"]

    assert message
    assert "postgres" not in message
    assert "password" not in message
    assert "token" not in message
    assert "private" not in message


def test_stop_waits_for_running_module_task_before_returning(isolated_runtime_factory):
    calls = []
    started = Event()
    release = Event()
    futures = []

    def start_task(context):
        def task():
            started.set()
            release.wait(1)

        futures.append(context.background_executor.submit(task))

    runtime = isolated_runtime_factory(
        [_LifecycleModule(_manifest("alpha"), calls, start_action=start_task)]
    )
    runtime.start()
    assert started.wait(0.2)

    stopping = Thread(target=runtime.stop)
    stopping.start()
    assert stopping.is_alive()
    release.set()
    stopping.join(1)

    assert not stopping.is_alive()
    assert futures[0].done()


def test_partial_start_cancels_queued_task_before_module_stop(isolated_runtime_factory):
    calls = []
    blockers = [Event() for _ in range(4)]
    queued = []

    def fail_with_queued_task(context):
        queued.append(context.background_executor.submit(lambda: calls.append("alpha:task")))
        raise RuntimeError("fixture failure")

    module = _LifecycleModule(_manifest("alpha"), calls, start_action=fail_with_queued_task)
    runtime = isolated_runtime_factory([module])
    for blocker in blockers:
        runtime._shared_executor.submit(blocker.wait, 1)

    def stop_waiting_for_task():
        assert queued[0].cancelled()
        with pytest.raises(CancelledError):
            queued[0].result(timeout=0.2)
        calls.append("alpha:stop")

    module.stop = stop_waiting_for_task
    runtime.start()
    for blocker in blockers:
        blocker.set()

    assert calls == ["alpha:start", "alpha:stop"]


def test_restart_creates_a_new_pool_only_after_the_old_pool_is_closed(
    isolated_runtime_factory,
):
    calls = []
    runtime = isolated_runtime_factory([_LifecycleModule(_manifest("alpha"), calls)])
    runtime.start()
    old_pool = runtime._shared_executor

    runtime.stop()
    runtime.start()

    with pytest.raises(RuntimeError):
        old_pool.submit(lambda: None)
    assert runtime._shared_executor is not old_pool
    runtime.stop()


def test_disabling_waits_for_old_module_task_before_reenabling(isolated_runtime_factory):
    calls = []
    started = Event()
    release = Event()
    futures = []

    def start_task(context):
        def task():
            started.set()
            release.wait(1)

        futures.append(context.background_executor.submit(task))

    module = _LifecycleModule(_manifest("alpha"), calls, start_action=start_task)
    runtime = isolated_runtime_factory([module])
    runtime.start()
    old_executor = module.context.background_executor
    assert started.wait(0.2)

    disabling = Thread(
        target=lambda: runtime.set_enabled("alpha", False, {"role": "admin"})
    )
    disabling.start()
    assert disabling.is_alive()
    release.set()
    disabling.join(1)

    assert not disabling.is_alive()
    assert futures[0].done()
    runtime.set_enabled("alpha", True, {"role": "admin"})
    assert module.context.background_executor is not old_executor
    runtime.stop()


def test_concurrent_disable_then_enable_finishes_with_a_consistent_enabled_module(
    isolated_runtime_factory,
):
    calls = []
    stop_entered = Event()
    release_stop = Event()
    module = _LifecycleModule(_manifest("alpha"), calls)
    runtime = isolated_runtime_factory([module])
    runtime.start()
    original_stop = module.stop

    def blocking_stop():
        stop_entered.set()
        release_stop.wait(1)
        original_stop()

    module.stop = blocking_stop
    disabling = Thread(
        target=lambda: runtime.set_enabled("alpha", False, {"role": "admin"})
    )
    enabling = Thread(
        target=lambda: runtime.set_enabled("alpha", True, {"role": "admin"})
    )
    disabling.start()
    assert stop_entered.wait(0.2)
    enabling.start()
    release = Timer(0.1, release_stop.set)
    release.start()
    disabling.join(1)
    enabling.join(1)
    release.join(1)

    loaded = runtime._find("alpha")
    assert not disabling.is_alive()
    assert not enabling.is_alive()
    assert runtime._state_store.enabled["alpha"] is True
    assert loaded.status.value == "enabled"
    assert loaded.instance is not None
    assert loaded.router is not None
    runtime.stop()


def test_concurrent_start_and_stop_never_leaves_enabled_module_on_closed_executor(
    isolated_runtime_factory,
):
    calls = []
    start_entered = Event()
    release_start = Event()

    def blocking_start(context):
        start_entered.set()
        release_start.wait(1)

    module = _LifecycleModule(_manifest("alpha"), calls, start_action=blocking_start)
    runtime = isolated_runtime_factory([module])
    starting = Thread(target=runtime.start)
    stopping = Thread(target=runtime.stop)
    starting.start()
    assert start_entered.wait(0.2)
    stopping.start()
    release = Timer(0.1, release_start.set)
    release.start()
    starting.join(1)
    stopping.join(1)
    release.join(1)

    assert not starting.is_alive()
    assert not stopping.is_alive()
    assert runtime.status("alpha").value != "enabled"
    runtime.start()
    executor = runtime.context_for("alpha").background_executor
    assert executor.submit(lambda: "ok").result(timeout=0.2) == "ok"
    runtime.stop()


def test_module_lifecycle_callback_cannot_reenter_start_or_stop(isolated_runtime_factory):
    calls = []
    runtime_ref = {}
    reentry_errors = []

    def start_reentering(context):
        with pytest.raises(ModuleRuntimeError) as error:
            runtime_ref["runtime"].start()
        reentry_errors.append(error.value)

    module = _LifecycleModule(_manifest("alpha"), calls, start_action=start_reentering)
    runtime = isolated_runtime_factory([module])
    runtime_ref["runtime"] = runtime
    runtime.start()

    def stop_reentering():
        with pytest.raises(ModuleRuntimeError) as error:
            runtime.stop()
        reentry_errors.append(error.value)
        calls.append("alpha:stop")

    module.stop = stop_reentering
    runtime.stop()

    assert len(reentry_errors) == 2
    assert calls == ["alpha:start", "alpha:stop"]


def test_background_read_calls_do_not_deadlock_during_stop(isolated_runtime_factory):
    calls = []
    runtime_ref = {}
    worker_started = Event()
    allow_reads = Event()
    worker_finished = Event()
    observed = []

    def start_background_reader(context):
        def read_runtime_state():
            worker_started.set()
            allow_reads.wait(1)
            runtime = runtime_ref["runtime"]
            observed.append(runtime.public_modules({"role": "admin"}))
            observed.append(runtime.status("alpha").value)
            observed.append(
                runtime.dispatch(
                    method="GET",
                    path="/api/modules/alpha/unknown",
                    query={},
                    body=None,
                    current_user={"role": "admin"},
                ).status
            )
            worker_finished.set()

        context.background_executor.submit(read_runtime_state)

    module = _LifecycleModule(
        _manifest("alpha"), calls, start_action=start_background_reader
    )
    runtime = isolated_runtime_factory([module])
    runtime_ref["runtime"] = runtime
    runtime.start()
    assert worker_started.wait(0.2)

    def stop_and_release_reader():
        allow_reads.set()
        calls.append("alpha:stop")

    module.stop = stop_and_release_reader
    stopping = Thread(target=runtime.stop)
    stopping.start()
    stopping.join(1)

    assert not stopping.is_alive()
    assert worker_finished.is_set()
    assert observed[0] == []
    assert observed[1] == "enabled"
    assert observed[2] == 404
