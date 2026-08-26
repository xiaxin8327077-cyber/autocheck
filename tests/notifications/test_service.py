from datetime import datetime, timezone, timedelta

import pytest

from auto_check.app.notifications.contracts import (
    NotificationPublishRequest,
    NotificationStreamEvent,
    NotificationStreamPublisher,
    validate_publish_request,
)
from auto_check.app.notifications.service import NotificationService
from auto_check.app.notifications.storage import NotificationStorage

BEIJING_TZ = timezone(timedelta(hours=8))


def now_dt():
    return datetime(2026, 8, 25, 10, 0, 0, tzinfo=BEIJING_TZ)


class FakeUserDirectory:
    def __init__(self, users):
        self._users = {u: {"id": u, "enabled": True} for u in users}

    def get_user(self, user_id):
        return self._users.get(user_id)

    def list_active_users(self):
        return tuple(user for user in self._users.values() if user.get("enabled"))


class FakeStreamPublisher:
    def __init__(self):
        self.events = []

    def publish(self, user_id, event):
        self.events.append((user_id, event))


def make_request(**overrides):
    base = dict(
        event_type="test_event",
        dedupe_key="test:1",
        recipient_user_ids=("u1",),
        category="todo",
        level="info",
        title="Test",
        content="Test content",
    )
    base.update(overrides)
    return validate_publish_request(NotificationPublishRequest(**base))


@pytest.fixture
def storage():
    from tests.mysql_config_test_support import MemoryApplicationDatabase

    return NotificationStorage(MemoryApplicationDatabase())


@pytest.fixture
def user_dir():
    return FakeUserDirectory({"u1", "u2"})


@pytest.fixture
def stream():
    return FakeStreamPublisher()


@pytest.fixture
def service(storage, user_dir, stream):
    return NotificationService(
        storage,
        user_dir,
        stream,
        now=now_dt,
    )


class TestServicePublish:
    def test_publish_persists_and_emits_event(self, service, stream):
        result = service.publish("alpha", make_request())
        assert result.created is True
        assert result.recipient_count == 1
        assert len(stream.events) == 1
        user_id, event = stream.events[0]
        assert user_id == "u1"
        assert event.type == "notification"

    def test_duplicate_publish_does_not_emit_second_event(self, service, stream):
        first = service.publish("alpha", make_request())
        second = service.publish("alpha", make_request())
        assert first.created is True
        assert second.created is False
        assert len(stream.events) == 1

    def test_publish_validates_recipients_exist(self, service):
        with pytest.raises(Exception):
            service.publish("alpha", make_request(recipient_user_ids=("nonexistent",)))

    def test_publish_uses_beijing_time_for_expiry(self, service, storage):
        result = service.publish("alpha", make_request())
        notif = storage.database.connection.tables["system_notifications"][0]
        assert notif["expires_at"] == notif["created_at"] + __import__("datetime").timedelta(days=30)


class TestServiceCleanup:
    def test_cleanup_deletes_expired(self, service, storage):
        result = service.publish("alpha", make_request())
        storage.database.connection.tables["system_notifications"][0]["expires_at"] = now_dt() - __import__("datetime").timedelta(days=1)
        deleted = service.cleanup_expired()
        assert deleted == 1
        assert len(storage.database.connection.tables["system_notifications"]) == 0

    def test_cleanup_deletes_expired_in_batches(self, service, storage):
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        # Create 5 notifications
        for i in range(5):
            req = validate_publish_request(NotificationPublishRequest(
                event_type="test_event",
                dedupe_key=f"test:{i}",
                recipient_user_ids=("u1",),
                category="todo",
                level="info",
                title=f"Test {i}",
                content=f"Content {i}",
            ))
            service.publish("alpha", req)
        # Expire all notifications
        for notif in storage.database.connection.tables["system_notifications"]:
            notif["expires_at"] = now_dt() - __import__("datetime").timedelta(days=1)
        # Cleanup should delete all
        deleted = service.cleanup_expired()
        assert deleted == 5

    def test_notification_visible_until_expiry_boundary(self, service, storage):
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        req = validate_publish_request(NotificationPublishRequest(
            event_type="test_event",
            dedupe_key="test:boundary",
            recipient_user_ids=("u1",),
            category="todo",
            level="info",
            title="Boundary Test",
            content="Boundary content",
        ))
        service.publish("alpha", req)
        notif = storage.database.connection.tables["system_notifications"][0]
        # Set expires_at to exactly now
        notif["expires_at"] = now_dt()
        # Should not be visible (expires_at <= now means expired)
        page = storage.list_for_user("u1", unread_only=False, limit=20, cursor=None, now=now_dt())
        assert len(page.items) == 0

    def test_business_success_preserved_when_notification_fails(self, service, storage):
        def failing_publish(request):
            raise RuntimeError("notification service unavailable")
        service._stream = failing_publish
        # Should not raise
        result = service.publish("alpha", make_request())
        assert result.created is True

    def test_same_dedupe_key_is_idempotent(self, service, storage):
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        req = validate_publish_request(NotificationPublishRequest(
            event_type="test_event",
            dedupe_key="test:idempotent",
            recipient_user_ids=("u1",),
            category="todo",
            level="info",
            title="Idempotent Test",
            content="Idempotent content",
        ))
        first = service._storage.create_or_get("alpha", req, now_dt())
        second = service._storage.create_or_get("alpha", req, now_dt())
        assert first.notification_id == second.notification_id
        assert second.created is False
        # Only one notification and one recipient
        assert len(storage.database.connection.tables["system_notifications"]) == 1
        assert len(storage.database.connection.tables["system_notification_recipients"]) == 1
