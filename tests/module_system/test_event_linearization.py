from threading import Event, Thread
from time import monotonic, sleep

from auto_check.app.module_system.events import EventBus, EventDeliveryReport, ModuleEvents


class _TrackedSubscription:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_close_waits_for_an_inflight_module_publish_before_returning():
    publish_entered = Event()
    release_publish = Event()
    close_returned = Event()
    deliveries = []

    def publish(event_name, payload):
        publish_entered.set()
        assert release_publish.wait(1)
        deliveries.append((event_name, payload))
        return EventDeliveryReport(delivered=1, failed=0, errors=())

    events = ModuleEvents(subscribe=lambda event_name, handler: None, publish=publish)
    publishing = Thread(target=lambda: events.publish("alpha:changed", {"id": "1"}))

    def close():
        events.close()
        close_returned.set()

    closing = Thread(target=close)

    publishing.start()
    assert publish_entered.wait(1)
    closing.start()
    try:
        deadline = monotonic() + 1
        while not events._closed and monotonic() < deadline:
            sleep(0.001)
        assert events._closed
        sleep(0.01)
        assert not close_returned.is_set()
    finally:
        release_publish.set()
        publishing.join(timeout=1)
        closing.join(timeout=1)

    assert close_returned.is_set()
    assert deliveries == [("alpha:changed", {"id": "1"})]


def test_close_waits_for_an_inflight_subscription_to_be_tracked_and_closed():
    subscribe_entered = Event()
    release_subscribe = Event()
    close_returned = Event()
    subscription = _TrackedSubscription()
    subscribed = []

    def subscribe(event_name, handler):
        subscribe_entered.set()
        assert release_subscribe.wait(1)
        return subscription

    events = ModuleEvents(
        subscribe=subscribe,
        publish=lambda event_name, payload: EventDeliveryReport(0, 0, ()),
    )
    subscribing = Thread(
        target=lambda: subscribed.append(events.subscribe("system:ready", lambda payload: None))
    )
    closing = Thread(target=lambda: (events.close(), close_returned.set()))

    subscribing.start()
    assert subscribe_entered.wait(1)
    closing.start()
    try:
        sleep(0.01)
        assert not close_returned.is_set()
    finally:
        release_subscribe.set()
        subscribing.join(timeout=1)
        closing.join(timeout=1)

    assert close_returned.is_set()
    assert subscribed == [subscription]
    assert subscription.closed is True


def test_close_waits_for_an_inflight_inbound_subscription_handler():
    handler_entered = Event()
    release_handler = Event()
    close_returned = Event()
    effects = []
    bus = EventBus()
    events = bus.for_module("beta")

    def handler(payload):
        handler_entered.set()
        assert release_handler.wait(1)
        effects.append(payload)

    events.subscribe("alpha:changed", handler)
    publishing = Thread(target=lambda: bus.publish("alpha:changed", {"id": "1"}))
    closing = Thread(target=lambda: (events.close(), close_returned.set()))

    publishing.start()
    assert handler_entered.wait(1)
    closing.start()
    try:
        sleep(0.01)
        assert not close_returned.is_set()
    finally:
        release_handler.set()
        publishing.join(timeout=1)
        closing.join(timeout=1)

    assert effects == [{"id": "1"}]
    assert close_returned.is_set()


def test_reentrant_module_close_waits_for_a_different_inflight_subscription():
    target_entered = Event()
    closing_handler_entered = Event()
    release_target = Event()
    close_returned = Event()
    effects = []
    bus = EventBus()
    events = bus.for_module("beta")

    def target_handler(payload):
        target_entered.set()
        assert release_target.wait(1)
        effects.append(payload)

    def closing_handler(payload):
        closing_handler_entered.set()
        events.close()
        close_returned.set()

    events.subscribe("alpha:target", target_handler)
    events.subscribe("alpha:close", closing_handler)
    target_publish = Thread(
        target=lambda: bus.publish("alpha:target", {"id": "target"})
    )
    closing_publish = Thread(target=lambda: bus.publish("alpha:close", {}))

    target_publish.start()
    assert target_entered.wait(1)
    closing_publish.start()
    try:
        assert closing_handler_entered.wait(1)
        sleep(0.01)
        assert not close_returned.is_set()
    finally:
        release_target.set()
        target_publish.join(timeout=1)
        closing_publish.join(timeout=1)

    assert effects == [{"id": "target"}]
    assert close_returned.is_set()
    assert not target_publish.is_alive()
    assert not closing_publish.is_alive()


def test_external_close_and_handler_self_close_do_not_deadlock():
    handler_entered = Event()
    attempt_self_close = Event()
    handler_returned = Event()
    external_close_returned = Event()
    bus = EventBus()
    subscription = None

    def handler(payload):
        handler_entered.set()
        assert attempt_self_close.wait(1)
        subscription.close()
        handler_returned.set()

    subscription = bus.subscribe("alpha:changed", handler, owner="beta")
    publishing = Thread(
        target=lambda: bus.publish("alpha:changed", {}),
        daemon=True,
    )
    closing = Thread(
        target=lambda: (subscription.close(), external_close_returned.set()),
        daemon=True,
    )

    publishing.start()
    assert handler_entered.wait(1)
    closing.start()
    deadline = monotonic() + 1
    while not subscription._closed and monotonic() < deadline:
        sleep(0.001)
    assert subscription._closed
    attempt_self_close.set()
    publishing.join(timeout=1)
    closing.join(timeout=1)

    assert handler_returned.is_set()
    assert external_close_returned.is_set()
    assert not publishing.is_alive()
    assert not closing.is_alive()


def test_external_module_close_and_handler_module_close_do_not_deadlock():
    handler_entered = Event()
    attempt_inner_close = Event()
    handler_returned = Event()
    external_close_returned = Event()
    bus = EventBus()
    events = bus.for_module("beta")

    def handler(payload):
        handler_entered.set()
        assert attempt_inner_close.wait(1)
        events.close()
        handler_returned.set()

    events.subscribe("alpha:changed", handler)
    publishing = Thread(
        target=lambda: bus.publish("alpha:changed", {}),
        daemon=True,
    )
    closing = Thread(
        target=lambda: (events.close(), external_close_returned.set()),
        daemon=True,
    )

    publishing.start()
    assert handler_entered.wait(1)
    closing.start()
    deadline = monotonic() + 1
    while not events._closed and monotonic() < deadline:
        sleep(0.001)
    assert events._closed
    attempt_inner_close.set()
    publishing.join(timeout=1)
    closing.join(timeout=1)

    assert handler_returned.is_set()
    assert external_close_returned.is_set()
    assert not publishing.is_alive()
    assert not closing.is_alive()


def test_external_module_close_waits_after_handler_self_close_returns():
    handler_entered = Event()
    self_close_returned = Event()
    release_handler = Event()
    handler_returned = Event()
    external_close_returned = Event()
    bus = EventBus()
    events = bus.for_module("beta")

    def handler(payload):
        handler_entered.set()
        events.close()
        self_close_returned.set()
        assert release_handler.wait(1)
        handler_returned.set()

    events.subscribe("alpha:changed", handler)
    publishing = Thread(
        target=lambda: bus.publish("alpha:changed", {}),
        daemon=True,
    )
    closing = Thread(
        target=lambda: (events.close(), external_close_returned.set()),
        daemon=True,
    )

    publishing.start()
    assert handler_entered.wait(1)
    assert self_close_returned.wait(1)
    closing.start()
    try:
        sleep(0.01)
        assert not external_close_returned.is_set()
    finally:
        release_handler.set()
        publishing.join(timeout=1)
        closing.join(timeout=1)

    assert handler_returned.is_set()
    assert external_close_returned.is_set()
    assert not publishing.is_alive()
    assert not closing.is_alive()
