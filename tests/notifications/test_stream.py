import threading

import pytest

from auto_check.app.notifications.contracts import NotificationStreamEvent
from auto_check.app.notifications.stream import (
    NotificationStreamHub,
    NotificationStreamLimitError,
    NotificationSubscription,
)


def sample_event(notification_id="n1"):
    return NotificationStreamEvent(
        type="notification",
        unread_count=1,
    )


class TestHubDelivery:
    def test_delivers_only_to_target_user(self):
        hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=100)
        u1 = hub.subscribe("u1")
        u2 = hub.subscribe("u2")
        hub.publish("u1", sample_event("n1"))
        # u1 should have the event
        event = u1.next(1.0)
        assert event is not None
        assert event.type == "notification"
        # u2 should not have the event
        assert u2.next(0.01) is None

    def test_queue_overflow_emits_resync(self):
        hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=1)
        sub = hub.subscribe("u1")
        hub.publish("u1", sample_event("n1"))
        hub.publish("u1", sample_event("n2"))
        event = sub.next(1.0)
        assert event is not None
        assert event.type == "resync"

    def test_enforces_per_user_limit(self):
        hub = NotificationStreamHub(max_per_user=1, max_total=200, queue_size=100)
        hub.subscribe("u1")
        with pytest.raises(NotificationStreamLimitError):
            hub.subscribe("u1")

    def test_enforces_global_limit(self):
        hub = NotificationStreamHub(max_per_user=5, max_total=1, queue_size=100)
        hub.subscribe("u1")
        with pytest.raises(NotificationStreamLimitError):
            hub.subscribe("u2")

    def test_close_sends_close_sentinel_and_rejects_new_subscriptions(self):
        hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=100)
        sub = hub.subscribe("u1")
        hub.close()
        event = sub.next(1.0)
        assert event is not None
        assert event.type == "close"
        with pytest.raises(NotificationStreamLimitError):
            hub.subscribe("u2")

    def test_subscribe_after_close_raises(self):
        hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=100)
        hub.close()
        with pytest.raises(NotificationStreamLimitError):
            hub.subscribe("u1")

    def test_close_is_idempotent(self):
        hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=100)
        hub.close()
        hub.close()  # should not raise

    def test_subscription_close_is_idempotent(self):
        hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=100)
        sub = hub.subscribe("u1")
        sub.close()
        sub.close()  # should not raise
