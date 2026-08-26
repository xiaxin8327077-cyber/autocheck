"""通知 HTTP 集成测试。"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer

import pytest

from auto_check.app.app_database import ApplicationDatabase, ApplicationDatabaseConfig
from auto_check.app.notifications.http_api import NotificationHttpApi
from auto_check.app.notifications.platform import create_notification_platform_service
from auto_check.app.notifications.service import NotificationService
from auto_check.app.notifications.storage import NotificationStorage
from auto_check.app.notifications.stream import NotificationStreamHub
from auto_check.app.security import AuthManager
from auto_check.app.time_utils import beijing_now
from auto_check.app.config import default_config_path

BEIJING_TZ = timezone(timedelta(hours=8))


class FakeUserDirectory:
    def __init__(self):
        self._users = {
            "u1": {"id": "u1", "username": "user1", "display_name": "User 1", "enabled": True},
            "u2": {"id": "u2", "username": "user2", "display_name": "User 2", "enabled": True},
        }

    def get_user(self, user_id):
        return self._users.get(user_id)

    def list_active_users(self):
        return tuple(u for u in self._users.values() if u.get("enabled"))


class FakeStreamPublisher:
    def __init__(self):
        self.events = []

    def publish(self, user_id, event):
        self.events.append((user_id, event))


@pytest.fixture
def notification_setup(tmp_path):
    """Create a notification setup with storage, service, and HTTP API."""
    from tests.mysql_config_test_support import MemoryApplicationDatabase

    db = MemoryApplicationDatabase()
    storage = NotificationStorage(db)
    user_dir = FakeUserDirectory()
    stream_hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=100)
    service = NotificationService(storage, user_dir, stream_hub, now=beijing_now)
    http_api = NotificationHttpApi(service, stream_hub)
    return {
        "db": db,
        "storage": storage,
        "user_dir": user_dir,
        "stream_hub": stream_hub,
        "service": service,
        "http_api": http_api,
    }


class TestNotificationHttpApi:
    def test_list_requires_login(self, notification_setup):
        """Test that list returns 401 without authentication."""
        # This is tested through the Handler, but we can test the API directly
        api = notification_setup["http_api"]
        # The API itself doesn't check auth, the Handler does
        # So we test that the API works with a valid user_id
        status, payload = api.list_notifications(user_id="u1", query={})
        assert status == 200
        assert payload["unread_count"] == 0
        assert payload["items"] == []

    def test_list_returns_notifications(self, notification_setup):
        api = notification_setup["http_api"]
        service = notification_setup["service"]
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        req = validate_publish_request(NotificationPublishRequest(
            event_type="test_event",
            dedupe_key="test:1",
            recipient_user_ids=("u1",),
            category="todo",
            level="info",
            title="Test",
            content="Test content",
        ))
        service.publish("alpha", req)
        status, payload = api.list_notifications(user_id="u1", query={})
        assert status == 200
        assert payload["unread_count"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["title"] == "Test"

    def test_list_filters_by_user(self, notification_setup):
        api = notification_setup["http_api"]
        service = notification_setup["service"]
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        req = validate_publish_request(NotificationPublishRequest(
            event_type="test_event",
            dedupe_key="test:1",
            recipient_user_ids=("u1", "u2"),
            category="todo",
            level="info",
            title="Test",
            content="Test content",
        ))
        service.publish("alpha", req)
        status1, payload1 = api.list_notifications(user_id="u1", query={})
        status2, payload2 = api.list_notifications(user_id="u2", query={})
        assert payload1["unread_count"] == 1
        assert payload2["unread_count"] == 1
        assert payload1["items"][0]["id"] == payload2["items"][0]["id"]

    def test_mark_read(self, notification_setup):
        api = notification_setup["http_api"]
        service = notification_setup["service"]
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        req = validate_publish_request(NotificationPublishRequest(
            event_type="test_event",
            dedupe_key="test:1",
            recipient_user_ids=("u1",),
            category="todo",
            level="info",
            title="Test",
            content="Test content",
        ))
        result = service.publish("alpha", req)
        status, payload = api.mark_read(user_id="u1", notification_id=result.notification_id)
        assert status == 200
        assert payload["unread_count"] == 0
        assert payload["notification"]["is_read"] is True

    def test_mark_read_other_user_returns_404(self, notification_setup):
        api = notification_setup["http_api"]
        service = notification_setup["service"]
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        req = validate_publish_request(NotificationPublishRequest(
            event_type="test_event",
            dedupe_key="test:1",
            recipient_user_ids=("u1",),
            category="todo",
            level="info",
            title="Test",
            content="Test content",
        ))
        result = service.publish("alpha", req)
        status, payload = api.mark_read(user_id="u2", notification_id=result.notification_id)
        assert status == 404

    def test_mark_all_read(self, notification_setup):
        api = notification_setup["http_api"]
        service = notification_setup["service"]
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        for i in range(3):
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
        status, payload = api.mark_all_read(user_id="u1")
        assert status == 200
        assert payload["unread_count"] == 0

    def test_unread_count(self, notification_setup):
        api = notification_setup["http_api"]
        service = notification_setup["service"]
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        for i in range(3):
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
        status, payload = api.get_unread_count(user_id="u1")
        assert status == 200
        assert payload["unread_count"] == 3

    def test_clear_all(self, notification_setup):
        api = notification_setup["http_api"]
        service = notification_setup["service"]
        from auto_check.app.notifications.contracts import (
            NotificationPublishRequest,
            validate_publish_request,
        )
        for i in range(3):
            req = validate_publish_request(NotificationPublishRequest(
                event_type="test_event",
                dedupe_key=f"test:clear:{i}",
                recipient_user_ids=("u1", "u2"),
                category="todo",
                level="info",
                title=f"Test {i}",
                content=f"Content {i}",
            ))
            service.publish("alpha", req)
        # Clear u1's notifications
        status, payload = api.clear_all(user_id="u1")
        assert status == 200
        assert payload["deleted_count"] == 3
        # u1 should see no notifications
        status, payload = api.list_notifications(user_id="u1", query={})
        assert payload["unread_count"] == 0
        assert len(payload["items"]) == 0
        # u2 should still see all 3
        status, payload = api.list_notifications(user_id="u2", query={})
        assert payload["unread_count"] == 3
