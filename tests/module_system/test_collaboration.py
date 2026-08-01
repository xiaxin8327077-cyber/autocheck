from __future__ import annotations

from concurrent.futures import Future
from typing import get_type_hints

import pytest

from auto_check.app.module_system.contracts import ModuleContext, ModuleTaskExecutor
from auto_check.app.module_system.events import EventBus
from auto_check.app.module_system.services import ServiceRegistry, ServiceVersionError


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
    services = ServiceRegistry().for_module("alpha")

    with pytest.raises(ValueError, match="namespace"):
        services.register("beta.lookup", 1, object())

    assert not hasattr(services, "_registry")


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
