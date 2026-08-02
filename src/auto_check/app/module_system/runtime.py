"""Lifecycle orchestration for trusted, built-in Auto Check modules."""

from __future__ import annotations

import logging
from pathlib import Path
from concurrent.futures import Future, TimeoutError as FutureTimeoutError, wait
from dataclasses import dataclass
from threading import BoundedSemaphore, Condition, Lock, RLock, Thread, get_ident
from time import monotonic
from typing import Any, Callable, Mapping

from .contracts import (
    AutoCheckModule,
    ModuleBootstrapContext,
    ModuleContext,
    ModuleHealth,
    ModuleHttpResponse,
    ModuleRequest,
    ModuleStatus,
)
from .discovery import (
    DiscoveredModule,
    ModuleDiscoveryIssue,
    declaration_conflicts,
    discover_module_report,
    load_module_factory,
    plan_module_runtime,
)
from .events import EventBus
from .permissions import default_permission_evaluator
from .resources import ModuleAsset, ModuleAssetNotFound, read_module_asset
from .routing import ModuleRoutePreflight, ModuleRouter
from .schema import ModuleMigrationError, ModuleMigrationRunner, ModuleSchemaRegistry
from .services import PlatformServiceSpec, ServiceRegistry
from .storage import ModuleStateStore


class ModuleStartupError(RuntimeError):
    """Raised when a required module prevents the host from starting."""


class ModuleTaskLimitError(RuntimeError):
    """Raised when a module already owns its maximum number of tasks."""


class ModuleRuntimeError(RuntimeError):
    """Raised when a lifecycle transition cannot safely be performed."""


class ModuleDependencyError(ModuleRuntimeError):
    """Raised when a module's declared provider is not enabled."""


class ModuleLifecycleTimeout(ModuleRuntimeError):
    """Raised with a fixed safe message when trusted in-process module code hangs."""


def _daemon_call(
    callable: Callable[..., Any], /, *args: Any, name: str, **kwargs: Any
) -> Future:
    """Invoke trusted module code without letting an unkillable call own host shutdown.

    CPython cannot safely terminate an arbitrary running thread. Timed-out calls therefore
    remain daemon-isolated until they cooperate and return; callers must retain their Future
    to prevent duplicate lifecycle calls while that isolation is active.
    """
    future: Future = Future()

    def run() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            result = callable(*args, **kwargs)
        except BaseException as error:
            future.set_exception(error)
        else:
            future.set_result(result)

    Thread(target=run, name=name, daemon=True).start()
    return future


class _DaemonTaskPool:
    """Run bounded module work on daemon threads so abandoned work cannot hold process exit."""

    def __init__(self, maximum_workers: int, maximum_tasks: int) -> None:
        self._slots = BoundedSemaphore(maximum_workers)
        self._maximum_tasks = maximum_tasks
        self._futures: set[Future] = set()
        self._running: set[Future] = set()
        self._lock = Lock()
        self._closed = False

    def submit(self, callable: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future:
        with self._lock:
            if self._closed:
                raise RuntimeError("module task pool is stopped")
            if len(self._futures) >= self._maximum_tasks:
                raise ModuleTaskLimitError("global module background task limit reached")
            future: Future = Future()
            self._futures.add(future)

        def run() -> None:
            while not future.cancelled():
                if self._slots.acquire(timeout=0.05):
                    break
            else:
                return
            with self._lock:
                if future.cancelled():
                    self._slots.release()
                    return
                self._running.add(future)
            try:
                if not future.set_running_or_notify_cancel():
                    return
                try:
                    result = callable(*args, **kwargs)
                except BaseException as error:
                    future.set_exception(error)
                else:
                    future.set_result(result)
            finally:
                self._release_running(future)

        def discard(completed: Future) -> None:
            with self._lock:
                self._futures.discard(completed)

        future.add_done_callback(discard)
        thread = Thread(target=run, name="module-task", daemon=True)
        try:
            thread.start()
        except Exception:
            future.cancel()
            with self._lock:
                self._futures.discard(future)
            raise
        return future

    def _release_running(self, future: Future) -> None:
        """Release a physical worker slot only after its callable actually returns."""
        with self._lock:
            if future not in self._running:
                return
            self._running.remove(future)
        self._slots.release()

    def reopen(self) -> None:
        with self._lock:
            self._closed = False

    def shutdown(self, *, cancel_futures: bool) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            futures = tuple(self._futures)
        if cancel_futures:
            for future in futures:
                future.cancel()


class _ModuleTaskExecutor:
    """A module-owned, bounded view over the host's shared worker pool."""

    def __init__(self, executor: _DaemonTaskPool, maximum_tasks: int = 2) -> None:
        self._executor = executor
        self._maximum_tasks = maximum_tasks
        self._futures: set[Future] = set()
        self._lock = Lock()
        self._closed = False

    def submit(self, callable: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future:
        with self._lock:
            if self._closed:
                raise RuntimeError("module task executor is stopped")
            if len(self._futures) >= self._maximum_tasks:
                raise ModuleTaskLimitError("module background task limit reached")
            future = self._executor.submit(callable, *args, **kwargs)
            self._futures.add(future)

        def discard(completed: Future) -> None:
            with self._lock:
                self._futures.discard(completed)

        future.add_done_callback(discard)
        return future

    def shutdown(self, cancel_pending: bool) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            futures = tuple(self._futures)
        if cancel_pending:
            for future in futures:
                future.cancel()

    def wait_for_completion(self, timeout: float) -> tuple[Future, ...]:
        """Wait briefly, then detach daemon work that Python cannot safely terminate."""
        with self._lock:
            futures = tuple(self._futures)
        if not futures:
            return ()
        _, outstanding = wait(futures, timeout=timeout)
        return tuple(outstanding)


@dataclass
class LoadedModule:
    discovered: DiscoveredModule
    instance: AutoCheckModule | None = None
    router: ModuleRouter | None = None
    status: ModuleStatus = ModuleStatus.DISCOVERED
    error: str = ""
    isolated_futures: tuple[Future, ...] = ()
    health_future: Future | None = None


@dataclass(frozen=True)
class _ModuleBootstrapResult:
    instance: AutoCheckModule
    router: ModuleRouter


class _ModuleBootstrapProgress:
    def __init__(self) -> None:
        self._stage = "load_module_factory"
        self._lock = Lock()

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self._stage = stage

    def current_stage(self) -> str:
        with self._lock:
            return self._stage


class ModuleRuntime:
    """Own discovery, loading, visibility and cleanup of built-in modules."""

    def __init__(
        self,
        context: ModuleBootstrapContext,
        discovered: list[DiscoveredModule],
        *,
        discovery_issues: tuple[ModuleDiscoveryIssue, ...] = (),
        preflight_incompatibilities: Mapping[str, str] | None = None,
        platform_services: tuple[PlatformServiceSpec, ...] = (),
        lifecycle_timeout_seconds: float = 1.0,
        health_timeout_seconds: float = 0.5,
        task_shutdown_timeout_seconds: float = 1.0,
    ) -> None:
        if (
            lifecycle_timeout_seconds <= 0
            or health_timeout_seconds <= 0
            or task_shutdown_timeout_seconds <= 0
        ):
            raise ValueError("module timeouts must be positive")
        self._context = context
        self._loaded = [LoadedModule(item) for item in discovered]
        self._discovery_issues = tuple(discovery_issues)
        preflight_conflicts = dict(preflight_incompatibilities or {})
        declaration_candidates = [
            module
            for module in discovered
            if module.manifest.id not in preflight_conflicts
        ]
        self._declaration_conflicts = declaration_conflicts(declaration_candidates)
        self._declaration_conflicts.update(preflight_conflicts)
        self._propagate_declaration_conflicts()
        self._state_store = ModuleStateStore(context.application_database)
        self._services = ServiceRegistry()
        for platform_service in platform_services:
            self._services.register_platform(platform_service)
        self._events = EventBus()
        self._shared_executor = _DaemonTaskPool(maximum_workers=4, maximum_tasks=8)
        self._shared_executor_shutdown = False
        self._lifecycle_timeout_seconds = lifecycle_timeout_seconds
        self._health_timeout_seconds = health_timeout_seconds
        self._task_shutdown_timeout_seconds = task_shutdown_timeout_seconds
        self._contexts: dict[str, ModuleContext] = {}
        self._lifecycle_lock = RLock()
        self._transition_condition = Condition(self._lifecycle_lock)
        self._transition_owner: int | None = None
        self._transitioning_modules: set[str] = set()
        self._lifecycle_callback_threads: set[int] = set()

    @classmethod
    def build(
        cls,
        context: ModuleBootstrapContext,
        package_name: str = "auto_check.modules",
        **runtime_options: Any,
    ) -> ModuleRuntime:
        plan = plan_module_runtime(discover_module_report(package_name))
        return cls(
            context,
            list(plan.modules),
            discovery_issues=plan.issues,
            preflight_incompatibilities=plan.incompatibilities,
            **runtime_options,
        )

    @classmethod
    def empty(cls, context: ModuleBootstrapContext, **runtime_options: Any) -> ModuleRuntime:
        """Create a runtime that deliberately performs no package discovery."""
        return cls(context, [], **runtime_options)

    def start(self) -> None:
        self._run_transition(
            (
                *(loaded.discovered.manifest.id for loaded in self._loaded),
                *(issue.module_id for issue in self._discovery_issues),
            ),
            self._start,
        )

    def _start(self) -> None:
        self._ensure_shared_executor()
        required_issue = next(
            (issue for issue in self._discovery_issues if issue.required),
            None,
        )
        if required_issue is not None:
            self._shutdown_shared_executor()
            raise ModuleStartupError(
                f"required module {required_issue.module_id} is incompatible"
            )
        started_this_time: list[LoadedModule] = []
        for loaded in self._loaded:
            with self._lifecycle_lock:
                status = loaded.status
            if status == ModuleStatus.ENABLED:
                continue
            self._state_store.save_discovered(loaded.discovered.manifest)
            if loaded.discovered.manifest.id in self._declaration_conflicts:
                self._mark_incompatible(loaded)
                if loaded.discovered.manifest.required:
                    self._stop_loaded_reverse(started_this_time)
                    self._shutdown_shared_executor()
                    raise ModuleStartupError(
                        f"required module {loaded.discovered.manifest.id} is incompatible"
                    )
                continue
            enabled = self._state_store.load_enabled(loaded.discovered.manifest.id)
            if enabled is False:
                self._set_status(loaded, ModuleStatus.DISABLED)
                continue
            try:
                self._require_not_isolated(loaded)
                self._require_dependencies_enabled(loaded)
                self._start_loaded(loaded)
            except ModuleMigrationError as error:
                self._fail_loaded(loaded, ModuleStatus.MIGRATION_FAILED, error)
                if loaded.discovered.manifest.required:
                    self._stop_loaded_reverse(started_this_time)
                    self._shutdown_shared_executor()
                    raise ModuleStartupError(
                        f"required module {loaded.discovered.manifest.id} failed during migration"
                    ) from None
            except Exception as error:
                self._fail_loaded(loaded, ModuleStatus.STARTUP_FAILED, error)
                if loaded.discovered.manifest.required:
                    self._stop_loaded_reverse(started_this_time)
                    self._shutdown_shared_executor()
                    raise ModuleStartupError(
                        f"required module {loaded.discovered.manifest.id} failed to start"
                    ) from None
            else:
                started_this_time.append(loaded)

    def stop(self) -> None:
        self._run_transition(
            tuple(loaded.discovered.manifest.id for loaded in self._loaded), self._stop
        )

    def _stop(self) -> None:
        self._stop_loaded_reverse(self._loaded)
        self._shutdown_shared_executor()

    def status(self, module_id: str) -> ModuleStatus:
        with self._lifecycle_lock:
            try:
                return self._find(module_id).status
            except KeyError:
                if any(issue.module_id == module_id for issue in self._discovery_issues):
                    return ModuleStatus.INCOMPATIBLE
                raise

    def context_for(self, module_id: str) -> ModuleContext:
        with self._lifecycle_lock:
            return self._contexts[module_id]

    def dispatch(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str],
        body: Mapping[str, Any] | None,
        current_user: Mapping[str, Any] | None,
        body_size: int = 0,
    ) -> ModuleHttpResponse:
        with self._lifecycle_lock:
            routers = tuple(
                loaded.router
                for loaded in self._loaded
                if (
                    loaded.status == ModuleStatus.ENABLED
                    and loaded.router is not None
                    and loaded.discovered.manifest.id not in self._transitioning_modules
                )
            )
        request = ModuleRequest(method, path, {}, query, body, current_user or {})
        for router in routers:
            response = router.dispatch(request, body_size=body_size)
            if response is not None:
                return response
        return ModuleHttpResponse.json(404, {"error": "module route not found"})

    def preflight(self, *, method: str, path: str) -> ModuleRoutePreflight:
        """Resolve a module route before its request body is read or decoded."""
        with self._lifecycle_lock:
            routers = tuple(
                loaded.router
                for loaded in self._loaded
                if (
                    loaded.status == ModuleStatus.ENABLED
                    and loaded.router is not None
                    and loaded.discovered.manifest.id not in self._transitioning_modules
                )
            )
        for router in routers:
            preflight = router.preflight(method, path)
            if preflight is not None and preflight.status != 404:
                return preflight
        return ModuleRoutePreflight(status=404)

    def read_asset(self, module_id: str, relative_path: str) -> ModuleAsset:
        with self._lifecycle_lock:
            try:
                loaded = self._find(module_id)
            except KeyError:
                raise ModuleAssetNotFound("module asset not found") from None
            if (
                loaded.status != ModuleStatus.ENABLED
                or module_id in self._transitioning_modules
            ):
                raise ModuleAssetNotFound("module asset not found")
            discovered = loaded.discovered
        return read_module_asset(discovered, relative_path)

    def public_modules(self, current_user: Mapping[str, Any] | None) -> list[dict[str, object]]:
        with self._lifecycle_lock:
            manifests = tuple(
                loaded.discovered.manifest
                for loaded in self._loaded
                if (
                    loaded.status == ModuleStatus.ENABLED
                    and loaded.discovered.manifest.id not in self._transitioning_modules
                )
            )
        result: list[dict[str, object]] = []
        for manifest in manifests:
            navigation = []
            for item in manifest.navigation:
                if not default_permission_evaluator(current_user, item.permission):
                    continue
                navigation_item: dict[str, object] = {
                    "id": item.id,
                    "label": item.label,
                    "route": item.route,
                    "order": item.order,
                    "permission": item.permission,
                }
                if item.group_id is not None:
                    navigation_item.update(
                        {
                            "group_id": item.group_id,
                            "group_label": item.group_label,
                            "group_order": item.group_order,
                        }
                    )
                navigation.append(navigation_item)
            if not navigation:
                continue
            result.append(
                {
                    "id": manifest.id,
                    "name": manifest.name,
                    "version": manifest.version,
                    "frontend_entry": manifest.frontend_entry,
                    "frontend_style": manifest.frontend_style,
                    "navigation": navigation,
                }
            )
        return result

    def public_release_notes(self) -> list[dict[str, object]]:
        with self._lifecycle_lock:
            manifests = tuple(
                loaded.discovered.manifest
                for loaded in self._loaded
                if (
                    loaded.status == ModuleStatus.ENABLED
                    and loaded.discovered.manifest.id not in self._transitioning_modules
                    and loaded.discovered.manifest.release_notes is not None
                )
            )
        return [
            {
                "module_id": manifest.id,
                "module_name": manifest.name,
                "version": manifest.release_notes.version,
                "items": list(manifest.release_notes.items),
            }
            for manifest in sorted(manifests, key=lambda item: item.id)
            if manifest.release_notes is not None
        ]

    def admin_statuses(self, current_user: Mapping[str, Any] | None) -> list[dict[str, object]]:
        self._require_admin(current_user)
        with self._lifecycle_lock:
            snapshots = tuple(
                (
                    loaded.discovered.manifest,
                    loaded.status,
                    loaded.error,
                    loaded.instance,
                    loaded.discovered.manifest.id in self._transitioning_modules,
                    loaded,
                )
                for loaded in self._loaded
            )
        result: list[dict[str, object]] = []
        for manifest, status, error, instance, transitioning, loaded in snapshots:
            health = (
                ModuleHealth(healthy=False, message="module transition in progress")
                if transitioning
                else self._health_for(loaded, status, instance, manifest.id)
            )
            result.append(
                {
                    "id": manifest.id,
                    "name": manifest.name,
                    "version": manifest.version,
                    "required": manifest.required,
                    "enabled": status != ModuleStatus.DISABLED,
                    "status": status.value,
                    "health": {"healthy": health.healthy, "message": health.message[:500]},
                    "error": error[:500],
                }
            )
        for issue in self._discovery_issues:
            result.append(
                {
                    "id": issue.module_id,
                    "name": issue.name,
                    "version": issue.version,
                    "required": issue.required,
                    "enabled": True,
                    "status": ModuleStatus.INCOMPATIBLE.value,
                    "health": {
                        "healthy": False,
                        "message": "module is not running",
                    },
                    "error": issue.error,
                }
            )
        return result

    def set_enabled(
        self, module_id: str, enabled: bool, current_user: Mapping[str, Any] | None
    ) -> None:
        self._require_admin(current_user)
        self._run_transition((module_id,), lambda: self._set_enabled(module_id, enabled))

    def _set_enabled(self, module_id: str, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        with self._lifecycle_lock:
            loaded = self._find(module_id)
            required = loaded.discovered.manifest.required
            status = loaded.status
        if not enabled and required:
            raise ValueError("required module cannot be disabled")
        if not enabled:
            dependents = self._enabled_dependents(module_id)
            if dependents:
                raise ValueError(f"enabled dependent modules prevent disabling: {', '.join(dependents)}")
        if enabled and module_id in self._declaration_conflicts:
            raise ValueError("module declarations are incompatible")
        if enabled and status != ModuleStatus.ENABLED:
            self._require_not_isolated(loaded)
            self._require_dependencies_enabled(loaded)
        self._state_store.save_discovered(loaded.discovered.manifest)
        self._state_store.set_enabled(module_id, enabled)
        if not enabled:
            self._teardown_loaded(loaded, status=ModuleStatus.DISABLED)
            return
        if status == ModuleStatus.ENABLED:
            return
        try:
            self._ensure_shared_executor()
            self._start_loaded(loaded)
        except ModuleMigrationError as error:
            self._fail_loaded(loaded, ModuleStatus.MIGRATION_FAILED, error)
            if loaded.discovered.manifest.required:
                raise ModuleStartupError(f"required module {module_id} failed during migration") from None
        except Exception as error:
            self._fail_loaded(loaded, ModuleStatus.STARTUP_FAILED, error)
            if loaded.discovered.manifest.required:
                raise ModuleStartupError(f"required module {module_id} failed to start") from None

    def _start_loaded(self, loaded: LoadedModule) -> None:
        manifest = loaded.discovered.manifest
        self._set_status(loaded, ModuleStatus.LOADING)
        bootstrap_progress = _ModuleBootstrapProgress()
        bootstrap_future = self._module_call(
            self._bootstrap_module,
            loaded.discovered,
            bootstrap_progress,
            name=f"module-{manifest.id}-bootstrap",
        )
        try:
            bootstrap = bootstrap_future.result(timeout=self._lifecycle_timeout_seconds)
        except FutureTimeoutError:
            self._record_isolation_until_complete(loaded, bootstrap_future)
            if bootstrap_progress.current_stage() == "migration":
                raise ModuleMigrationError("module migration timed out") from None
            raise ModuleLifecycleTimeout("module bootstrap timed out") from None
        except ModuleMigrationError:
            raise
        except BaseException:
            raise ModuleRuntimeError("module bootstrap failed") from None
        instance = bootstrap.instance
        router = bootstrap.router
        events = self._events.for_module(manifest.id)
        executor = _ModuleTaskExecutor(self._shared_executor)
        module_context = ModuleContext(
            application_database=self._context.application_database,
            config_path=self._context.config_path,
            temp_root=_module_temp_root(self._context.temp_root, manifest.id),
            now=self._context.now,
            services=self._services.for_module(
                manifest.id,
                declared_services={service.name: service.version for service in manifest.services},
                dependencies=manifest.dependencies,
                service_dependencies={
                    requirement.name: requirement.minimum_version
                    for requirement in manifest.service_dependencies
                },
            ),
            events=events,
            logger=logging.LoggerAdapter(logging.getLogger(__name__), {"module_id": manifest.id}),
            background_executor=executor,
        )
        with self._lifecycle_lock:
            loaded.instance = instance
            loaded.router = router
            self._contexts[manifest.id] = module_context
        start_future = self._module_call(
            instance.start,
            module_context,
            name=f"module-{manifest.id}-start",
        )
        try:
            start_future.result(timeout=self._lifecycle_timeout_seconds)
        except FutureTimeoutError:
            self._schedule_stop_after_start(loaded, instance, start_future)
            module_context.background_executor.shutdown(cancel_pending=True)
            outstanding = self._cleanup_resources(manifest.id, module_context)
            self._record_isolation(loaded, outstanding)
            with self._lifecycle_lock:
                loaded.instance = None
                loaded.router = None
                self._contexts.pop(manifest.id, None)
            raise ModuleLifecycleTimeout("module start timed out") from None
        except BaseException:
            module_context.background_executor.shutdown(cancel_pending=True)
            try:
                self._best_effort_stop(loaded, instance)
            except Exception as error:
                self._log_lifecycle_error(manifest.id, error)
            finally:
                outstanding = self._cleanup_resources(manifest.id, module_context)
                self._record_isolation(loaded, outstanding)
                with self._lifecycle_lock:
                    loaded.instance = None
                    loaded.router = None
                    self._contexts.pop(manifest.id, None)
            raise ModuleRuntimeError("module start failed") from None
        self._set_status(loaded, ModuleStatus.ENABLED)

    def _bootstrap_module(
        self,
        discovered: DiscoveredModule,
        progress: _ModuleBootstrapProgress,
    ) -> _ModuleBootstrapResult:
        manifest = discovered.manifest
        factory = load_module_factory(manifest.backend_entry)
        progress.set_stage("factory")
        instance = factory()
        if instance.manifest.id != manifest.id:
            raise ValueError("module instance manifest does not match discovered manifest")
        progress.set_stage("register_routes")
        router = ModuleRouter(manifest, default_permission_evaluator)
        instance.register_routes(router)
        progress.set_stage("register_schema")
        schema_registry = ModuleSchemaRegistry(
            manifest.id, table_prefix=manifest.table_prefix
        )
        instance.register_schema(schema_registry)
        progress.set_stage("migration")
        ModuleMigrationRunner(self._context.application_database, schema_registry).run(
            manifest, discovered.package_name
        )
        return _ModuleBootstrapResult(instance=instance, router=router)

    def _stop_loaded_reverse(self, loaded_modules: list[LoadedModule]) -> None:
        for loaded in reversed(loaded_modules):
            with self._lifecycle_lock:
                status = loaded.status
            if status == ModuleStatus.ENABLED:
                self._teardown_loaded(loaded, status=ModuleStatus.DISCOVERED)

    def _teardown_loaded(self, loaded: LoadedModule, *, status: ModuleStatus) -> None:
        module_id = loaded.discovered.manifest.id
        with self._lifecycle_lock:
            context = self._contexts.get(module_id)
            instance = loaded.instance
            health_future = loaded.health_future
            loaded.health_future = None
        if health_future is not None and not health_future.done():
            self._record_isolation(loaded, (health_future,))
        if context is not None:
            context.background_executor.shutdown(cancel_pending=True)
        stop_timed_out = False
        if instance is not None:
            try:
                self._best_effort_stop(loaded, instance)
            except ModuleLifecycleTimeout:
                stop_timed_out = True
            except BaseException as error:
                self._log_lifecycle_error(module_id, error)
        with self._lifecycle_lock:
            context = self._contexts.pop(module_id, None)
        if context is not None:
            outstanding = self._cleanup_resources(module_id, context)
            self._record_isolation(loaded, outstanding)
        with self._lifecycle_lock:
            loaded.instance = None
            loaded.router = None
            if stop_timed_out:
                loaded.error = "ModuleLifecycleTimeout: module stop timed out"
        self._set_status(loaded, status, preserve_error=stop_timed_out)

    def _cleanup_resources(
        self, module_id: str, context: ModuleContext
    ) -> tuple[Future, ...]:
        context.background_executor.shutdown(cancel_pending=True)
        events_close_future = _daemon_call(
            context.events.close,
            name=f"module-{module_id}-events-close",
        )
        event_outstanding: tuple[Future, ...] = ()
        try:
            events_close_future.result(timeout=self._task_shutdown_timeout_seconds)
        except FutureTimeoutError:
            event_outstanding = (events_close_future,)
        except BaseException as error:
            self._log_lifecycle_error(module_id, error)
        context.services.close()
        self._services.unregister_owner(module_id)
        if isinstance(context.background_executor, _ModuleTaskExecutor):
            return (
                *event_outstanding,
                *context.background_executor.wait_for_completion(
                    self._task_shutdown_timeout_seconds
                ),
            )
        return event_outstanding

    def _record_isolation(
        self, loaded: LoadedModule, futures: tuple[Future, ...]
    ) -> None:
        if not futures:
            return
        with self._lifecycle_lock:
            loaded.isolated_futures = tuple(
                future
                for future in (*loaded.isolated_futures, *futures)
                if not future.done()
            )

    def _record_isolation_until_complete(
        self, loaded: LoadedModule, future: Future
    ) -> None:
        self._record_isolation(loaded, (future,))

        def discard(completed: Future) -> None:
            with self._lifecycle_lock:
                loaded.isolated_futures = tuple(
                    item
                    for item in loaded.isolated_futures
                    if item is not completed and not item.done()
                )

        future.add_done_callback(discard)

    def _require_not_isolated(self, loaded: LoadedModule) -> None:
        with self._lifecycle_lock:
            loaded.isolated_futures = tuple(
                future for future in loaded.isolated_futures if not future.done()
            )
            isolated = bool(loaded.isolated_futures)
        if isolated:
            raise ModuleRuntimeError("module remains isolated while abandoned work is running")

    def _best_effort_stop(self, loaded: LoadedModule, instance: AutoCheckModule) -> None:
        module_id = loaded.discovered.manifest.id
        stop_future = self._module_call(instance.stop, name=f"module-{module_id}-stop")
        try:
            stop_future.result(timeout=self._lifecycle_timeout_seconds)
        except FutureTimeoutError:
            self._record_isolation(loaded, (stop_future,))
            raise ModuleLifecycleTimeout("module stop timed out") from None
        except BaseException:
            raise ModuleRuntimeError("module stop failed") from None

    def _schedule_stop_after_start(
        self,
        loaded: LoadedModule,
        instance: AutoCheckModule,
        start_future: Future,
    ) -> None:
        """Stop once a timed-out start eventually returns, never concurrently with start."""
        cleanup_finished: Future = Future()
        self._record_isolation(loaded, (cleanup_finished,))

        def stop_after_completion(completed: Future) -> None:
            try:
                try:
                    completed.result()
                except BaseException:
                    pass
                try:
                    self._best_effort_stop(loaded, instance)
                except ModuleLifecycleTimeout:
                    pass
                except BaseException as error:
                    self._log_lifecycle_error(loaded.discovered.manifest.id, error)
            finally:
                cleanup_finished.set_result(None)

        start_future.add_done_callback(stop_after_completion)

    def _fail_loaded(self, loaded: LoadedModule, status: ModuleStatus, error: Exception) -> None:
        self._log_lifecycle_error(loaded.discovered.manifest.id, error)
        with self._lifecycle_lock:
            loaded.error = f"{type(error).__name__}: module lifecycle operation failed"
        self._set_status(loaded, status)

    def _set_status(
        self,
        loaded: LoadedModule,
        status: ModuleStatus,
        *,
        preserve_error: bool = False,
    ) -> None:
        with self._lifecycle_lock:
            loaded.status = status
            if not preserve_error and status not in {
                ModuleStatus.INCOMPATIBLE,
                ModuleStatus.MIGRATION_FAILED,
                ModuleStatus.STARTUP_FAILED,
            }:
                loaded.error = ""
            module_id = loaded.discovered.manifest.id
            error = loaded.error
        self._state_store.set_status(module_id, status, error)

    def _mark_incompatible(self, loaded: LoadedModule) -> None:
        module_id = loaded.discovered.manifest.id
        with self._lifecycle_lock:
            loaded.error = self._declaration_conflicts[module_id]
        self._set_status(loaded, ModuleStatus.INCOMPATIBLE)

    def _require_dependencies_enabled(self, loaded: LoadedModule) -> None:
        unavailable = [
            dependency
            for dependency in loaded.discovered.manifest.dependencies
            if self._find(dependency).status != ModuleStatus.ENABLED
        ]
        if unavailable:
            raise ModuleDependencyError(f"module dependencies are unavailable: {', '.join(unavailable)}")

    def _enabled_dependents(self, module_id: str) -> list[str]:
        dependents: set[str] = set()
        pending = [module_id]
        while pending:
            provider = pending.pop()
            for loaded in self._loaded:
                dependent_id = loaded.discovered.manifest.id
                if (
                    provider in loaded.discovered.manifest.dependencies
                    and dependent_id not in dependents
                ):
                    dependents.add(dependent_id)
                    pending.append(dependent_id)
        return sorted(
            module_id
            for module_id in dependents
            if self._find(module_id).status == ModuleStatus.ENABLED
        )

    def _health_for(
        self,
        loaded: LoadedModule,
        status: ModuleStatus,
        instance: AutoCheckModule | None,
        module_id: str,
    ) -> ModuleHealth:
        if status != ModuleStatus.ENABLED or instance is None:
            return ModuleHealth(healthy=False, message="module is not running")
        with self._lifecycle_lock:
            health_future = loaded.health_future
            if health_future is not None and not health_future.done():
                return ModuleHealth(
                    healthy=False,
                    message="module health check timed out",
                )
            health_future = self._module_call(
                instance.health,
                name=f"module-{module_id}-health",
            )
            loaded.health_future = health_future
        try:
            health = health_future.result(timeout=self._health_timeout_seconds)
        except FutureTimeoutError:
            return ModuleHealth(
                healthy=False,
                message="module health check timed out",
            )
        except BaseException as error:
            self._log_lifecycle_error(module_id, error)
            return ModuleHealth(healthy=False, message="health check unavailable")
        finally:
            if health_future.done():
                with self._lifecycle_lock:
                    if loaded.health_future is health_future:
                        loaded.health_future = None
        if not isinstance(health, ModuleHealth):
            return ModuleHealth(healthy=False, message="health check unavailable")
        return ModuleHealth(
            healthy=bool(health.healthy),
            message="healthy" if health.healthy else "unhealthy",
        )

    def _run_transition(
        self, module_ids: tuple[str, ...], operation: Callable[[], None]
    ) -> None:
        self._begin_transition(module_ids)
        try:
            operation()
        finally:
            self._finish_transition()

    def _module_call(
        self,
        callable: Callable[..., Any],
        /,
        *args: Any,
        name: str,
        **kwargs: Any,
    ) -> Future:
        def guarded_call() -> Any:
            owner = get_ident()
            with self._lifecycle_lock:
                self._lifecycle_callback_threads.add(owner)
            try:
                return callable(*args, **kwargs)
            finally:
                with self._lifecycle_lock:
                    self._lifecycle_callback_threads.discard(owner)

        return _daemon_call(guarded_call, name=name)

    def _begin_transition(self, module_ids: tuple[str, ...]) -> None:
        owner = get_ident()
        deadline = monotonic() + 5.0
        with self._transition_condition:
            if self._transition_owner == owner or owner in self._lifecycle_callback_threads:
                raise ModuleRuntimeError("module lifecycle callbacks cannot re-enter the runtime")
            while self._transition_owner is not None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise ModuleRuntimeError("timed out waiting for a module lifecycle transition")
                self._transition_condition.wait(remaining)
            self._transition_owner = owner
            self._transitioning_modules.update(module_ids)

    def _finish_transition(self) -> None:
        owner = get_ident()
        with self._transition_condition:
            if self._transition_owner != owner:
                raise ModuleRuntimeError("module lifecycle transition owner changed unexpectedly")
            self._transition_owner = None
            self._transitioning_modules.clear()
            self._transition_condition.notify_all()

    def _find(self, module_id: str) -> LoadedModule:
        for loaded in self._loaded:
            if loaded.discovered.manifest.id == module_id:
                return loaded
        raise KeyError(module_id)

    def _propagate_declaration_conflicts(self) -> None:
        changed = True
        while changed:
            changed = False
            for loaded in self._loaded:
                manifest = loaded.discovered.manifest
                if manifest.id in self._declaration_conflicts:
                    continue
                if any(
                    dependency in self._declaration_conflicts
                    for dependency in manifest.dependencies
                ):
                    self._declaration_conflicts[manifest.id] = (
                        "module dependency is incompatible"
                    )
                    changed = True

    def _ensure_shared_executor(self) -> None:
        if self._shared_executor_shutdown:
            self._shared_executor.reopen()
            self._shared_executor_shutdown = False

    def _shutdown_shared_executor(self) -> None:
        if not self._shared_executor_shutdown:
            self._shared_executor.shutdown(cancel_futures=True)
            self._shared_executor_shutdown = True

    @staticmethod
    def _require_admin(current_user: Mapping[str, Any] | None) -> None:
        if not current_user or current_user.get("role") != "admin":
            raise PermissionError("administrator permission required")

    @staticmethod
    def _log_lifecycle_error(module_id: str, error: BaseException) -> None:
        logging.getLogger(__name__).warning(
            "module lifecycle operation failed", extra={"module_id": module_id, "error_type": type(error).__name__}
        )


def _module_temp_root(platform_temp_root: Path, module_id: str) -> Path:
    root = Path(platform_temp_root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ModuleRuntimeError("module temporary root is unsafe")
    resolved_root = root.resolve(strict=True)
    child = root / module_id
    child.mkdir(exist_ok=True)
    if child.is_symlink():
        raise ModuleRuntimeError("module temporary root is unsafe")
    resolved_child = child.resolve(strict=True)
    if resolved_child.parent != resolved_root:
        raise ModuleRuntimeError("module temporary root escapes platform root")
    return resolved_child
