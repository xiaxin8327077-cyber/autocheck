from threading import Event, Thread
from time import monotonic, sleep

from auto_check.app.module_system.events import EventDeliveryReport, ModuleEvents


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
