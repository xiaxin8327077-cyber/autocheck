from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Barrier, Thread
from typing import get_type_hints

import pytest

from auto_check.app.module_system.contracts import ModuleContext, ModuleTaskExecutor
from auto_check.app.module_system.events import EventBus
from auto_check.app.module_system.services import (
    ServiceAccessError,
    ServiceRegistry,
    ServiceUnavailableError,
    ServiceVersionError,
)


def test_service_registry_resolves_compatible_public_service():
    provider = object()
    registry = ServiceRegistry()
    registry.register("alpha.lookup", 2, provider, owner="alpha")

    assert registry.resolve("alpha.lookup", minimum_version=1) is provider


def test_service_registry_rejects_cross_namespace_registration():
    registry = ServiceRegistry()

    with pytest.raises(ValueError, match="namespace"):
        registry.register("beta.lookup", 1, object(), owner="alpha")


@pytest.mark.parametrize(
    ("name", "version"),
    [
        ("alpha", 1),
        ("Alpha.lookup", 1),
        ("alpha.lookup.extra", 1),
        ("alpha.lookup", 0),
        ("alpha.lookup", True),
    ],
)
def test_service_registry_rejects_invalid_name_or_version(name, version):
    with pytest.raises(ValueError):
        ServiceRegistry().register(name, version, object(), owner="alpha")


def test_service_registry_rejects_duplicate_registration():
    registry = ServiceRegistry()
    registry.register("alpha.lookup", 1, object(), owner="alpha")

    with pytest.raises(ValueError, match="already registered"):
        registry.register("alpha.lookup", 2, object(), owner="alpha")


def test_service_registry_rejects_incompatible_version():
    registry = ServiceRegistry()
    registry.register("alpha.lookup", 1, object(), owner="alpha")

    with pytest.raises(ServiceVersionError, match="version"):
        registry.resolve("alpha.lookup", minimum_version=2)


def test_module_service_view_only_registers_its_own_namespace():
    services = ServiceRegistry().for_module(
        "alpha", declared_services={"alpha.lookup": 1}, dependencies=()
    )

    with pytest.raises(ServiceAccessError):
        services.register("beta.lookup", 1, object())

    assert not hasattr(services, "_registry")


def test_module_service_view_requires_a_declared_service_with_the_declared_version():
    services = ServiceRegistry().for_module(
        "alpha", declared_services={"alpha.lookup": 2}, dependencies=()
    )

    with pytest.raises(ServiceAccessError):
        services.register("alpha.other", 1, object())
    with pytest.raises(ServiceVersionError):
        services.register("alpha.lookup", 1, object())


def test_module_service_view_only_resolves_own_or_declared_dependency_services():
    registry = ServiceRegistry()
    registry.register("beta.lookup", 1, object(), owner="beta")
    view = registry.for_module("alpha", declared_services={}, dependencies=("beta",))

    assert view.resolve("beta.lookup", 1)
    with pytest.raises(ServiceAccessError):
        view.resolve("gamma.lookup", 1)
    with pytest.raises(ServiceUnavailableError):
        view.resolve("beta.missing", 1)


def test_service_registry_operations_are_safe_under_concurrent_registration_and_resolution():
    registry = ServiceRegistry()
    barrier = Barrier(3)
    errors = []

    def register():
        barrier.wait()
        try:
            registry.register("alpha.lookup", 1, object(), owner="alpha")
        except ValueError:
            pass
        except Exception as error:
            errors.append(error)

    def resolve():
        barrier.wait()
        for _ in range(100):
            try:
                registry.resolve("alpha.lookup", 1)
            except ServiceUnavailableError:
                pass
            except Exception as error:
                errors.append(error)

    threads = [Thread(target=register), Thread(target=register), Thread(target=resolve)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_service_registry_removes_services_owned_by_a_stopped_module():
    registry = ServiceRegistry()
    registry.register("alpha.lookup", 1, object(), owner="alpha")
    registry.register("beta.lookup", 1, object(), owner="beta")

    registry.unregister_owner("alpha")

    with pytest.raises(KeyError):
        registry.resolve("alpha.lookup", 1)
    assert registry.resolve("beta.lookup", 1)


def test_event_bus_isolates_failing_subscriber():
    calls = []
    bus = EventBus()
    bus.subscribe("alpha:published", lambda payload: calls.append(("first", payload)), owner="alpha")
    bus.subscribe(
        "alpha:published",
        lambda payload: (_ for _ in ()).throw(RuntimeError("fixture failure")),
        owner="beta",
    )
    bus.subscribe("alpha:published", lambda payload: calls.append(("third", payload)), owner="gamma")

    report = bus.publish("alpha:published", {"id": "1"})

    assert calls == [("first", {"id": "1"}), ("third", {"id": "1"})]
    assert report.delivered == 2
    assert report.failed == 1
    assert len(report.errors) == 1
    assert report.errors[0].owner == "beta"


def test_event_bus_rejects_invalid_name_and_non_serializable_payload():
    bus = EventBus()

    with pytest.raises(ValueError, match="event"):
        bus.subscribe("alpha.published", lambda payload: None, owner="alpha")
    with pytest.raises(ValueError, match="serializable"):
        bus.publish("alpha:published", {"not_json": object()})


def test_event_subscription_close_removes_handler():
    calls = []
    bus = EventBus()
    subscription = bus.subscribe("alpha:published", calls.append, owner="alpha")

    subscription.close()
    report = bus.publish("alpha:published", {"id": "1"})

    assert calls == []
    assert report.delivered == 0
    assert report.failed == 0


def test_module_event_view_only_publishes_own_namespace_and_closes_subscriptions():
    bus = EventBus()
    events = bus.for_module("alpha")
    calls = []
    events.subscribe("beta:changed", calls.append)

    with pytest.raises(ValueError, match="namespace"):
        events.publish("beta:changed", {})

    events.close()
    bus.publish("beta:changed", {"id": "1"})

    assert calls == []
    assert not hasattr(events, "_bus")


def test_platform_event_bus_can_publish_system_events():
    bus = EventBus()
    calls = []
    bus.subscribe("system:ready", calls.append, owner="alpha")

    bus.publish("system:ready", {"status": "ok"})

    assert calls == [{"status": "ok"}]


def test_module_event_view_cannot_claim_the_system_namespace():
    with pytest.raises(ValueError, match="system"):
        EventBus().for_module("system")


def test_module_context_uses_collaboration_types_and_task_executor_protocol():
    context_hints = get_type_hints(ModuleContext)
    executor_hints = get_type_hints(ModuleTaskExecutor.submit)

    assert context_hints["services"].__name__ == "ModuleServices"
    assert context_hints["events"].__name__ == "ModuleEvents"
    assert executor_hints["return"] is Future


def test_event_subscription_close_is_idempotent_under_concurrency():
    bus = EventBus()
    calls = []
    subscription = bus.subscribe("alpha:published", calls.append, owner="alpha")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(subscription.close) for _ in range(20)]
        for future in futures:
            future.result(timeout=1)

    assert bus.publish("alpha:published", {"id": "1"}).delivered == 0
    assert calls == []


def test_closed_module_event_view_rejects_new_work():
    events = EventBus().for_module("alpha")
    events.close()

    with pytest.raises(RuntimeError, match="closed"):
        events.subscribe("system:ready", lambda payload: None)
    with pytest.raises(RuntimeError, match="closed"):
        events.publish("alpha:published", {})
