"""Lifecycle orchestration for trusted, built-in Auto Check modules."""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Condition, Lock, RLock, get_ident
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
from .discovery import DiscoveredModule, discover_modules, load_module_factory, sort_modules
from .events import EventBus
from .permissions import default_permission_evaluator
from .resources import ModuleAsset, ModuleAssetNotFound, read_module_asset
from .routing import ModuleRouter
from .schema import ModuleMigrationError, ModuleMigrationRunner, ModuleSchemaRegistry
from .services import ServiceRegistry
from .storage import ModuleStateStore


class ModuleStartupError(RuntimeError):
    """Raised when a required module prevents the host from starting."""


class ModuleTaskLimitError(RuntimeError):
    """Raised when a module already owns its maximum number of tasks."""


class ModuleRuntimeError(RuntimeError):
    """Raised when a lifecycle transition cannot safely be performed."""


class _ModuleTaskExecutor:
    """A module-owned, bounded view over the host's shared worker pool."""

    def __init__(self, executor: ThreadPoolExecutor, maximum_tasks: int = 2) -> None:
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

    def wait_for_completion(self) -> None:
        """Wait for the module's already-running tasks after queued work is cancelled."""
        with self._lock:
            futures = tuple(self._futures)
        for future in futures:
            try:
                future.result()
            except Exception:
                pass


@dataclass
class LoadedModule:
    discovered: DiscoveredModule
    instance: AutoCheckModule | None = None
    router: ModuleRouter | None = None
    status: ModuleStatus = ModuleStatus.DISCOVERED
    error: str = ""


class ModuleRuntime:
    """Own discovery, loading, visibility and cleanup of built-in modules."""

    def __init__(
        self,
        context: ModuleBootstrapContext,
        discovered: list[DiscoveredModule],
    ) -> None:
        self._context = context
        self._loaded = [LoadedModule(item) for item in discovered]
        self._state_store = ModuleStateStore(context.application_database)
        self._services = ServiceRegistry()
        self._events = EventBus()
        self._shared_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="module")
        self._shared_executor_shutdown = False
        self._contexts: dict[str, ModuleContext] = {}
        self._lifecycle_lock = RLock()
        self._transition_condition = Condition(self._lifecycle_lock)
        self._transition_owner: int | None = None
        self._transitioning_modules: set[str] = set()

    @classmethod
    def build(
        cls,
        context: ModuleBootstrapContext,
        package_name: str = "auto_check.modules",
    ) -> ModuleRuntime:
        return cls(context, sort_modules(discover_modules(package_name)))

    @classmethod
    def empty(cls, context: ModuleBootstrapContext) -> ModuleRuntime:
        """Create a runtime that deliberately performs no package discovery."""
        return cls(context, [])

    def start(self) -> None:
        self._run_transition(
            tuple(loaded.discovered.manifest.id for loaded in self._loaded), self._start
        )

    def _start(self) -> None:
        self._ensure_shared_executor()
        started_this_time: list[LoadedModule] = []
        for loaded in self._loaded:
            with self._lifecycle_lock:
                status = loaded.status
            if status == ModuleStatus.ENABLED:
                continue
            self._state_store.save_discovered(loaded.discovered.manifest)
            enabled = self._state_store.load_enabled(loaded.discovered.manifest.id)
            if enabled is False:
                self._set_status(loaded, ModuleStatus.DISABLED)
                continue
            try:
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
            return self._find(module_id).status

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
            navigation = [
                {
                    "id": item.id,
                    "label": item.label,
                    "route": item.route,
                    "order": item.order,
                    "permission": item.permission,
                }
                for item in manifest.navigation
                if default_permission_evaluator(current_user, item.permission)
            ]
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
                )
                for loaded in self._loaded
            )
        result: list[dict[str, object]] = []
        for manifest, status, error, instance, transitioning in snapshots:
            health = (
                ModuleHealth(healthy=False, message="module transition in progress")
                if transitioning
                else self._health_for(status, instance, manifest.id)
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
        factory = load_module_factory(manifest.backend_entry)
        instance = factory()
        if instance.manifest.id != manifest.id:
            raise ValueError("module instance manifest does not match discovered manifest")
        router = ModuleRouter(manifest, default_permission_evaluator)
        instance.register_routes(router)
        schema_registry = ModuleSchemaRegistry()
        instance.register_schema(schema_registry)
        ModuleMigrationRunner(self._context.application_database, schema_registry).run(
            manifest, loaded.discovered.package_name
        )
        events = self._events.for_module(manifest.id)
        executor = _ModuleTaskExecutor(self._shared_executor)
        module_context = ModuleContext(
            application_database=self._context.application_database,
            config_path=self._context.config_path,
            temp_root=self._context.temp_root,
            now=self._context.now,
            services=self._services.for_module(manifest.id),
            events=events,
            logger=logging.LoggerAdapter(logging.getLogger(__name__), {"module_id": manifest.id}),
            background_executor=executor,
        )
        with self._lifecycle_lock:
            loaded.instance = instance
            loaded.router = router
            self._contexts[manifest.id] = module_context
        try:
            instance.start(module_context)
        except Exception:
            module_context.background_executor.shutdown(cancel_pending=True)
            try:
                instance.stop()
            except Exception as error:
                self._log_lifecycle_error(manifest.id, error)
            self._cleanup_resources(manifest.id, module_context)
            with self._lifecycle_lock:
                loaded.instance = None
                loaded.router = None
                self._contexts.pop(manifest.id, None)
            raise
        self._set_status(loaded, ModuleStatus.ENABLED)

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
        if context is not None:
            context.background_executor.shutdown(cancel_pending=True)
        if instance is not None:
            try:
                instance.stop()
            except Exception as error:
                self._log_lifecycle_error(module_id, error)
        with self._lifecycle_lock:
            context = self._contexts.pop(module_id, None)
        if context is not None:
            self._cleanup_resources(module_id, context)
        with self._lifecycle_lock:
            loaded.instance = None
            loaded.router = None
        self._set_status(loaded, status)

    def _cleanup_resources(self, module_id: str, context: ModuleContext) -> None:
        context.background_executor.shutdown(cancel_pending=True)
        context.events.close()
        self._services.unregister_owner(module_id)
        if isinstance(context.background_executor, _ModuleTaskExecutor):
            context.background_executor.wait_for_completion()

    def _fail_loaded(self, loaded: LoadedModule, status: ModuleStatus, error: Exception) -> None:
        self._log_lifecycle_error(loaded.discovered.manifest.id, error)
        with self._lifecycle_lock:
            loaded.error = f"{type(error).__name__}: module lifecycle operation failed"
        self._set_status(loaded, status)

    def _set_status(self, loaded: LoadedModule, status: ModuleStatus) -> None:
        with self._lifecycle_lock:
            loaded.status = status
            if status not in {ModuleStatus.MIGRATION_FAILED, ModuleStatus.STARTUP_FAILED}:
                loaded.error = ""
            module_id = loaded.discovered.manifest.id
            error = loaded.error
        self._state_store.set_status(module_id, status, error)

    def _health_for(
        self,
        status: ModuleStatus,
        instance: AutoCheckModule | None,
        module_id: str,
    ) -> ModuleHealth:
        if status != ModuleStatus.ENABLED or instance is None:
            return ModuleHealth(healthy=False, message="module is not running")
        try:
            health = instance.health()
        except Exception as error:
            self._log_lifecycle_error(module_id, error)
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

    def _begin_transition(self, module_ids: tuple[str, ...]) -> None:
        owner = get_ident()
        deadline = monotonic() + 5.0
        with self._transition_condition:
            if self._transition_owner == owner:
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

    def _ensure_shared_executor(self) -> None:
        if self._shared_executor_shutdown:
            self._shared_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="module")
            self._shared_executor_shutdown = False

    def _shutdown_shared_executor(self) -> None:
        if not self._shared_executor_shutdown:
            self._shared_executor.shutdown(wait=True, cancel_futures=True)
            self._shared_executor_shutdown = True

    @staticmethod
    def _require_admin(current_user: Mapping[str, Any] | None) -> None:
        if not current_user or current_user.get("role") != "admin":
            raise PermissionError("administrator permission required")

    @staticmethod
    def _log_lifecycle_error(module_id: str, error: Exception) -> None:
        logging.getLogger(__name__).warning(
            "module lifecycle operation failed", extra={"module_id": module_id, "error_type": type(error).__name__}
        )
