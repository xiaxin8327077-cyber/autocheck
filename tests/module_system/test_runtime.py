from __future__ import annotations

from pathlib import Path
from concurrent.futures import CancelledError
from threading import Event, Thread, Timer, current_thread
from time import monotonic, sleep

import pytest

from auto_check.app.module_system.contracts import (
    ModuleBootstrapContext,
    ModuleHealth,
    ModuleHttpResponse,
    ModuleManifest,
)
from auto_check.app.module_system.discovery import DiscoveredModule
from auto_check.app.module_system.runtime import (
    ModuleDependencyError,
    ModuleRuntime,
    ModuleRuntimeError,
    ModuleStartupError,
    ModuleTaskLimitError,
    _module_temp_root,
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


def _manifest(
    module_id: str,
    *,
    required: bool = False,
    api_prefix: str | None = None,
    dependencies: tuple[str, ...] = (),
    table_prefix: str | None = None,
    services: list[dict[str, object]] | None = None,
    backend_entry: str | None = None,
) -> ModuleManifest:
    return ModuleManifest.from_mapping(
        {
            "id": module_id,
            "name": module_id.title(),
            "version": "1.0.0",
            "platform_api": 1,
            "required": required,
            "backend_entry": backend_entry or f"fixture.{module_id}.module:create_module",
            "api_prefix": api_prefix or f"/api/modules/{module_id}",
            "frontend_entry": f"/module-assets/{module_id}/index.js",
            "frontend_style": f"/module-assets/{module_id}/styles.css",
            "navigation": [],
            "permissions": [f"{module_id}.view"],
            "dependencies": list(dependencies),
            "schema_version": 0,
            **({"table_prefix": table_prefix} if table_prefix is not None else {}),
            **({"services": services} if services is not None else {}),
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
def isolated_runtime_factory(monkeypatch, tmp_path):
    import auto_check.app.module_system.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "ModuleStateStore", _StateStore)
    monkeypatch.setattr(runtime_module, "ModuleMigrationRunner", _MigrationRunner)

    def create(modules, **runtime_options):
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
            temp_root=tmp_path / "module-data",
            now=lambda: None,
        )
        return ModuleRuntime(context, discovered, **runtime_options)

    return create


def test_runtime_starts_modules_in_dependency_order(runtime_factory):
    runtime, calls = runtime_factory(["alpha", "beta"])

    runtime.start()

    assert calls == ["alpha:start", "beta:start"]
    assert [item["id"] for item in runtime.public_modules({"role": "admin"})] == ["alpha", "beta"]


def test_runtime_marks_optional_api_prefix_conflicts_incompatible_without_loading_them(
    isolated_runtime_factory,
):
    class RouteModule(_LifecycleModule):
        def register_routes(self, router):
            if self.manifest.id == "second":
                router.add(
                    "POST",
                    "/target",
                    lambda request: ModuleHttpResponse.json(200, {}),
                    permission="second.view",
                    max_body_bytes=1,
                )

    runtime = isolated_runtime_factory(
        [
            RouteModule(_manifest("first", api_prefix="/api/modules/shared"), []),
            RouteModule(_manifest("second", api_prefix="/api/modules/shared"), []),
        ]
    )
    runtime.start()

    assert runtime.status("first").value == "incompatible"
    assert runtime.status("second").value == "incompatible"
    assert runtime.preflight(method="POST", path="/api/modules/shared/target").status == 404


@pytest.mark.parametrize(
    "left,right",
    [
        (
            _manifest("custom_report", table_prefix="custom_report_"),
            _manifest("custom_reports", table_prefix="custom_report_"),
        ),
        (_manifest("foo", table_prefix="foo_"), _manifest("foo_s", table_prefix="foo_s_")),
    ],
)
def test_runtime_rejects_exact_and_nested_table_prefix_conflicts_before_factories(
    isolated_runtime_factory, left, right
):
    calls = []
    runtime = isolated_runtime_factory([
        _LifecycleModule(left, calls),
        _LifecycleModule(right, calls),
    ])

    runtime.start()

    assert calls == []
    assert runtime.status(left.id).value == "incompatible"
    assert runtime.status(right.id).value == "incompatible"


def test_required_declaration_conflict_aborts_and_rolls_back_healthy_modules(isolated_runtime_factory):
    calls = []
    healthy = _LifecycleModule(_manifest("healthy"), calls)
    required = _LifecycleModule(
        _manifest("required", required=True, backend_entry="fixture.foreign.module:create_module"), calls
    )
    runtime = isolated_runtime_factory([healthy, required])

    with pytest.raises(ModuleStartupError, match="required"):
        runtime.start()

    assert calls == ["healthy:start", "healthy:stop"]


def test_optional_foreign_backend_entry_is_incompatible_without_calling_its_factory(
    isolated_runtime_factory,
):
    calls = []
    foreign = _LifecycleModule(
        _manifest("alpha", backend_entry="fixture.other.module:create_module"), calls
    )
    runtime = isolated_runtime_factory([foreign])

    runtime.start()

    assert calls == []
    assert foreign.context is None
    assert runtime.status("alpha").value == "incompatible"


def test_dependency_failure_prevents_dependent_factory_and_start(isolated_runtime_factory):
    calls = []
    provider = _LifecycleModule(_manifest("provider"), calls, start_action=lambda context: (_ for _ in ()).throw(RuntimeError()))
    dependent = _LifecycleModule(_manifest("dependent", dependencies=("provider",)), calls)
    runtime = isolated_runtime_factory([provider, dependent])

    runtime.start()

    assert calls == ["provider:start", "provider:stop"]
    assert runtime.status("dependent").value == "startup_failed"
    assert dependent.context is None


def test_required_dependent_aborts_when_provider_is_unavailable(isolated_runtime_factory):
    calls = []
    provider = _LifecycleModule(
        _manifest("provider"), calls, start_action=lambda context: (_ for _ in ()).throw(RuntimeError())
    )
    required = _LifecycleModule(
        _manifest("required", required=True, dependencies=("provider",)), calls
    )
    runtime = isolated_runtime_factory([provider, required])

    with pytest.raises(ModuleStartupError, match="required"):
        runtime.start()

    assert required.context is None


def test_enabling_dependent_requires_an_enabled_provider_before_persisting_state(
    isolated_runtime_factory,
):
    calls = []
    provider = _LifecycleModule(_manifest("provider"), calls)
    dependent = _LifecycleModule(_manifest("dependent", dependencies=("provider",)), calls)
    runtime = isolated_runtime_factory([provider, dependent])
    runtime.set_enabled("dependent", False, {"role": "admin"})
    runtime.start()
    runtime.set_enabled("provider", False, {"role": "admin"})

    with pytest.raises(ModuleDependencyError):
        runtime.set_enabled("dependent", True, {"role": "admin"})

    assert runtime._state_store.enabled["dependent"] is False


def test_disabling_provider_with_enabled_transitive_dependents_is_rejected_without_state_change(
    isolated_runtime_factory,
):
    calls = []
    provider = _LifecycleModule(_manifest("provider"), calls)
    direct = _LifecycleModule(_manifest("direct", dependencies=("provider",)), calls)
    transitive = _LifecycleModule(_manifest("transitive", dependencies=("direct",)), calls)
    runtime = isolated_runtime_factory([provider, direct, transitive])
    runtime.start()

    with pytest.raises(ValueError, match="dependent"):
        runtime.set_enabled("provider", False, {"role": "admin"})

    assert runtime._state_store.enabled["provider"] is True
    assert runtime.status("provider").value == "enabled"


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


def test_background_tasks_use_daemon_threads_and_keep_a_global_running_limit(
    isolated_runtime_factory,
):
    release = Event()
    started = [Event() for _ in range(4)]
    modules = [
        _LifecycleModule(_manifest(module_id), [])
        for module_id in ("alpha", "beta", "gamma", "delta", "epsilon")
    ]
    runtime = isolated_runtime_factory(modules)
    runtime.start()

    futures = []
    for index, module_id in enumerate(("alpha", "alpha", "beta", "beta")):
        def task(index=index):
            started[index].set()
            release.wait()
            return current_thread().daemon

        futures.append(runtime.context_for(module_id).background_executor.submit(task))
    assert all(event.wait(0.2) for event in started)

    pending = [
        runtime.context_for(module_id).background_executor.submit(lambda: True)
        for module_id in ("gamma", "gamma", "delta", "delta")
    ]
    sleep(0.05)
    assert all(not future.running() for future in pending)
    assert all(not future.done() for future in pending)
    with pytest.raises(ModuleTaskLimitError, match="global"):
        runtime.context_for("epsilon").background_executor.submit(lambda: True)

    release.set()
    assert all(future.result(timeout=1) is True for future in futures)
    assert all(future.result(timeout=1) is True for future in pending)
    runtime.stop()


def test_stuck_background_task_does_not_block_stop_and_prevents_duplicate_reenable(
    isolated_runtime_factory,
):
    release = Event()
    task_started = Event()
    calls = []
    futures = []

    def start_task(context):
        def stuck_task():
            task_started.set()
            release.wait()

        futures.append(context.background_executor.submit(stuck_task))

    module = _LifecycleModule(_manifest("alpha"), calls, start_action=start_task)
    runtime = isolated_runtime_factory(
        [module], task_shutdown_timeout_seconds=0.05, lifecycle_timeout_seconds=0.05
    )
    runtime.start()
    assert task_started.wait(0.2)

    started_at = monotonic()
    runtime.set_enabled("alpha", False, {"role": "admin"})
    assert monotonic() - started_at < 0.3
    assert runtime.status("alpha").value == "disabled"
    assert not futures[0].done()

    with pytest.raises(ModuleRuntimeError, match="isolated"):
        runtime.set_enabled("alpha", True, {"role": "admin"})

    release.set()
    futures[0].result(timeout=1)
    runtime.set_enabled("alpha", True, {"role": "admin"})
    assert runtime.status("alpha").value == "enabled"
    runtime.stop()


def test_isolated_running_tasks_keep_real_global_slots_until_they_finish(
    isolated_runtime_factory,
):
    alpha_release = Event()
    beta_release = Event()
    alpha_started = [Event(), Event()]
    beta_started = [Event(), Event()]
    gamma_started = [Event(), Event()]
    modules = [
        _LifecycleModule(_manifest(module_id), [])
        for module_id in ("alpha", "beta", "gamma")
    ]
    runtime = isolated_runtime_factory(
        modules, task_shutdown_timeout_seconds=0.05, lifecycle_timeout_seconds=0.05
    )
    runtime.start()

    def blocking_task(started, release):
        started.set()
        release.wait()

    alpha_futures = [
        runtime.context_for("alpha").background_executor.submit(
            blocking_task, started, alpha_release
        )
        for started in alpha_started
    ]
    beta_futures = [
        runtime.context_for("beta").background_executor.submit(
            blocking_task, started, beta_release
        )
        for started in beta_started
    ]
    assert all(event.wait(0.2) for event in (*alpha_started, *beta_started))

    runtime.set_enabled("alpha", False, {"role": "admin"})
    gamma_futures = [
        runtime.context_for("gamma").background_executor.submit(
            lambda started=started: started.set()
        )
        for started in gamma_started
    ]
    sleep(0.1)
    assert not any(event.is_set() for event in gamma_started)

    alpha_release.set()
    assert all(event.wait(0.5) for event in gamma_started)
    assert all(future.result(timeout=1) is None for future in alpha_futures)
    assert all(future.result(timeout=1) is None for future in gamma_futures)
    beta_release.set()
    assert all(future.result(timeout=1) is None for future in beta_futures)
    runtime.stop()


def test_stuck_event_publish_cannot_block_runtime_cleanup_or_duplicate_reenable(
    isolated_runtime_factory,
):
    publish_started = Event()
    release_publish = Event()
    publish_futures = []

    def start_publish(context):
        if publish_futures:
            return

        def stuck_handler(payload):
            publish_started.set()
            release_publish.wait()

        context.events.subscribe("alpha:changed", stuck_handler)
        publish_futures.append(
            context.background_executor.submit(
                context.events.publish, "alpha:changed", {"id": "1"}
            )
        )

    module = _LifecycleModule(_manifest("alpha"), [], start_action=start_publish)
    runtime = isolated_runtime_factory(
        [module], task_shutdown_timeout_seconds=0.05, lifecycle_timeout_seconds=0.05
    )
    runtime.start()
    assert publish_started.wait(0.2)

    watchdog = Timer(0.4, release_publish.set)
    watchdog.start()
    started_at = monotonic()
    runtime.set_enabled("alpha", False, {"role": "admin"})
    watchdog.cancel()
    watchdog.join(0.1)
    assert monotonic() - started_at < 0.3
    assert runtime.status("alpha").value == "disabled"
    assert runtime._contexts == {}
    with pytest.raises(ModuleRuntimeError, match="isolated"):
        runtime.set_enabled("alpha", True, {"role": "admin"})

    release_publish.set()
    publish_futures[0].result(timeout=1)
    deadline = monotonic() + 0.5
    while any(
        not future.done() for future in runtime._find("alpha").isolated_futures
    ) and monotonic() < deadline:
        sleep(0.01)
    runtime.set_enabled("alpha", True, {"role": "admin"})
    assert runtime.status("alpha").value == "enabled"
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
    resource_steps = []

    def fail_after_creating_resources(context):
        context.services.register("alpha.worker", 1, object())
        resource_steps.append("service")
        context.events.subscribe("system:ready", lambda payload: None)
        resource_steps.append("subscription")
        raise RuntimeError("password=not-for-admin")

    module = _LifecycleModule(
        _manifest("alpha", services=[{"name": "alpha.worker", "version": 1}]),
        calls,
        start_action=fail_after_creating_resources,
    )
    runtime = isolated_runtime_factory([module])

    runtime.start()

    assert calls == ["alpha:start", "alpha:stop"]
    assert resource_steps == ["service", "subscription"]
    assert runtime.status("alpha").value == "startup_failed"
    assert runtime._contexts == {}
    with pytest.raises(KeyError):
        runtime._services.resolve("alpha.worker", 1)


def test_stuck_start_is_isolated_without_concurrent_stop_and_other_modules_start(
    isolated_runtime_factory,
):
    release_start = Event()
    start_entered = Event()
    delayed_stop_called = Event()
    start_finished = Event()
    late_service_errors = []
    start_threads = []
    calls = []

    def block_first_start(context):
        start_threads.append(current_thread().daemon)
        if len(start_threads) != 1:
            return
        start_entered.set()
        release_start.wait()
        try:
            context.services.register("alpha.worker", 1, object())
        except Exception as error:
            late_service_errors.append(error)
        start_finished.set()

    alpha = _LifecycleModule(
        _manifest("alpha", services=[{"name": "alpha.worker", "version": 1}]),
        calls,
        start_action=block_first_start,
    )
    original_stop = alpha.stop

    def tracked_stop():
        delayed_stop_called.set()
        original_stop()

    alpha.stop = tracked_stop
    beta = _LifecycleModule(_manifest("beta"), calls)
    runtime = isolated_runtime_factory(
        [alpha, beta], lifecycle_timeout_seconds=0.05, task_shutdown_timeout_seconds=0.05
    )

    watchdog = Timer(0.4, release_start.set)
    watchdog.start()
    started_at = monotonic()
    runtime.start()
    watchdog.cancel()
    watchdog.join(0.1)
    assert monotonic() - started_at < 0.3
    assert start_entered.is_set()
    assert runtime.status("alpha").value == "startup_failed"
    assert runtime.status("beta").value == "enabled"
    assert not delayed_stop_called.is_set()
    assert runtime._contexts.get("alpha") is None

    with pytest.raises(ModuleRuntimeError, match="isolated"):
        runtime.set_enabled("alpha", True, {"role": "admin"})
    assert len(start_threads) == 1

    release_start.set()
    assert start_finished.wait(0.5)
    assert delayed_stop_called.wait(0.5)
    assert len(late_service_errors) == 1
    assert "closed" in str(late_service_errors[0])

    deadline = monotonic() + 0.5
    while any(
        not future.done() for future in runtime._find("alpha").isolated_futures
    ) and monotonic() < deadline:
        sleep(0.01)
    runtime.set_enabled("alpha", True, {"role": "admin"})
    assert runtime.status("alpha").value == "enabled"
    assert start_threads == [True, True]
    runtime.stop()


def test_stuck_stop_cannot_block_teardown_and_records_a_safe_disabled_error(
    isolated_runtime_factory,
):
    release_stop = Event()
    stop_entered = Event()
    calls = []
    module = _LifecycleModule(
        _manifest("alpha", services=[{"name": "alpha.worker", "version": 1}]), calls
    )
    original_start = module.start

    def start_with_service(context):
        original_start(context)
        context.services.register("alpha.worker", 1, object())

    module.start = start_with_service
    stop_calls = 0

    def block_first_stop():
        nonlocal stop_calls
        stop_calls += 1
        if stop_calls == 1:
            stop_entered.set()
            release_stop.wait()
            raise RuntimeError("password=must-not-leak")
        calls.append("alpha:stop")

    module.stop = block_first_stop
    runtime = isolated_runtime_factory(
        [module], lifecycle_timeout_seconds=0.05, task_shutdown_timeout_seconds=0.05
    )
    runtime.start()

    watchdog = Timer(0.4, release_stop.set)
    watchdog.start()
    started_at = monotonic()
    runtime.set_enabled("alpha", False, {"role": "admin"})
    watchdog.cancel()
    watchdog.join(0.1)
    assert monotonic() - started_at < 0.3
    assert stop_entered.is_set()
    assert runtime.status("alpha").value == "disabled"
    assert runtime._contexts == {}
    assert "timed out" in runtime._find("alpha").error
    assert "password" not in runtime._find("alpha").error
    with pytest.raises(KeyError):
        runtime._services.resolve("alpha.worker", 1)
    with pytest.raises(ModuleRuntimeError, match="isolated"):
        runtime.set_enabled("alpha", True, {"role": "admin"})

    release_stop.set()
    deadline = monotonic() + 0.5
    while any(
        not future.done() for future in runtime._find("alpha").isolated_futures
    ) and monotonic() < deadline:
        sleep(0.01)
    runtime.set_enabled("alpha", True, {"role": "admin"})
    assert runtime.status("alpha").value == "enabled"
    runtime.stop()


def test_stuck_health_is_bounded_deduplicated_and_does_not_hide_healthy_siblings(
    isolated_runtime_factory,
):
    release_health = Event()
    health_entered = Event()
    health_calls = 0
    health_threads = []
    alpha = _LifecycleModule(_manifest("alpha"), [])

    def block_first_health():
        nonlocal health_calls
        health_calls += 1
        health_threads.append(current_thread().daemon)
        if health_calls == 1:
            health_entered.set()
            release_health.wait()
        return ModuleHealth(healthy=True)

    alpha.health = block_first_health
    beta = _LifecycleModule(_manifest("beta"), [])
    runtime = isolated_runtime_factory(
        [alpha, beta],
        lifecycle_timeout_seconds=0.05,
        health_timeout_seconds=0.05,
        task_shutdown_timeout_seconds=0.05,
    )
    runtime.start()

    watchdog = Timer(0.4, release_health.set)
    watchdog.start()
    started_at = monotonic()
    statuses = runtime.admin_statuses({"role": "admin"})
    watchdog.cancel()
    watchdog.join(0.1)
    assert monotonic() - started_at < 0.3
    assert health_entered.is_set()
    assert statuses[0]["health"] == {
        "healthy": False,
        "message": "module health check timed out",
    }
    assert statuses[1]["health"]["healthy"] is True

    runtime.admin_statuses({"role": "admin"})
    assert health_calls == 1

    runtime.set_enabled("alpha", False, {"role": "admin"})
    with pytest.raises(ModuleRuntimeError, match="isolated"):
        runtime.set_enabled("alpha", True, {"role": "admin"})

    release_health.set()
    deadline = monotonic() + 0.5
    while any(
        not future.done() for future in runtime._find("alpha").isolated_futures
    ) and monotonic() < deadline:
        sleep(0.01)
    runtime.set_enabled("alpha", True, {"role": "admin"})
    runtime.admin_statuses({"role": "admin"})
    assert health_calls == 2
    assert health_threads == [True, True]
    runtime.stop()


def test_normal_lifecycle_callbacks_complete_on_daemon_isolation_threads(
    isolated_runtime_factory,
):
    callback_threads = []
    module = _LifecycleModule(
        _manifest("alpha"),
        [],
        start_action=lambda context: callback_threads.append(("start", current_thread().daemon)),
    )
    original_stop = module.stop

    def tracked_stop():
        callback_threads.append(("stop", current_thread().daemon))
        original_stop()

    def tracked_health():
        callback_threads.append(("health", current_thread().daemon))
        return ModuleHealth(healthy=True)

    module.stop = tracked_stop
    module.health = tracked_health
    runtime = isolated_runtime_factory([module])

    runtime.start()
    assert runtime.admin_statuses({"role": "admin"})[0]["health"]["healthy"] is True
    runtime.stop()

    assert callback_threads == [("start", True), ("health", True), ("stop", True)]


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


def test_restart_reopens_the_same_pool_without_bypassing_old_running_slots(
    isolated_runtime_factory,
):
    calls = []
    runtime = isolated_runtime_factory([_LifecycleModule(_manifest("alpha"), calls)])
    runtime.start()
    old_pool = runtime._shared_executor

    runtime.stop()
    runtime.start()

    assert runtime._shared_executor is old_pool
    assert old_pool.submit(lambda: "ok").result(timeout=1) == "ok"
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


def test_runtime_gives_each_module_a_distinct_temporary_directory(
    isolated_runtime_factory,
):
    runtime = isolated_runtime_factory(
        [
            _LifecycleModule(_manifest("alpha"), []),
            _LifecycleModule(_manifest("beta"), []),
        ]
    )

    runtime.start()

    alpha_root = runtime.context_for("alpha").temp_root
    beta_root = runtime.context_for("beta").temp_root
    assert alpha_root.name == "alpha"
    assert beta_root.name == "beta"
    assert alpha_root.parent == beta_root.parent
    assert alpha_root != beta_root
    runtime.stop()


def test_module_temporary_root_rejects_root_symlink(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "module-data"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(ModuleRuntimeError, match="unsafe"):
        _module_temp_root(link, "alpha")


def test_unsafe_module_temp_directory_does_not_block_a_sibling(
    isolated_runtime_factory, tmp_path
):
    runtime = isolated_runtime_factory(
        [
            _LifecycleModule(_manifest("alpha"), []),
            _LifecycleModule(_manifest("beta"), []),
        ]
    )
    root = runtime._context.temp_root
    root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "alpha").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    runtime.start()

    assert runtime.status("alpha").value == "startup_failed"
    assert runtime.status("beta").value == "enabled"
    assert runtime.context_for("beta").temp_root.parent == root.resolve()
    runtime.stop()
