from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine

from auto_check.app.notifications.contracts import (
    NotificationAction,
    NotificationPublishRequest,
    validate_publish_request,
)
from auto_check.app.notifications.storage import METADATA, NotificationStorage

BEIJING_TZ = timezone(timedelta(hours=8))


def aware_beijing_datetime(
    year=2026, month=8, day=25, hour=10, minute=0, second=0, microsecond=0
):
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=BEIJING_TZ)


def sample_request(
    *,
    event_type="test_event",
    dedupe_key="test:1",
    recipients=("u1",),
    category="todo",
    level="info",
    title="Test Notification",
    content="Test content",
    action=None,
):
    return validate_publish_request(
        NotificationPublishRequest(
            event_type=event_type,
            dedupe_key=dedupe_key,
            recipient_user_ids=recipients,
            category=category,
            level=level,
            title=title,
            content=content,
            action=action,
        )
    )


@pytest.fixture
def storage():
    from tests.mysql_config_test_support import MemoryApplicationDatabase

    db = MemoryApplicationDatabase()
    return NotificationStorage(db)


class TestStorageUserIsolation:
    def test_isolates_unread_state_by_user(self, storage):
        created = storage.create_or_get(
            source_module="alpha",
            request=sample_request(recipients=("u1", "u2")),
            now=aware_beijing_datetime(),
        )
        storage.mark_read("u1", created.notification_id, aware_beijing_datetime())
        assert storage.unread_count("u1", aware_beijing_datetime()) == 0
        assert storage.unread_count("u2", aware_beijing_datetime()) == 1


class TestStorageDeduplication:
    def test_returns_existing_notification_for_same_dedupe_key(self, storage):
        first = storage.create_or_get(
            source_module="alpha",
            request=sample_request(),
            now=aware_beijing_datetime(),
        )
        second = storage.create_or_get(
            source_module="alpha",
            request=sample_request(),
            now=aware_beijing_datetime(),
        )
        assert second.notification_id == first.notification_id
        assert second.created is False


class TestStorageListAndRead:
    def test_list_returns_only_current_user_items(self, storage):
        storage.create_or_get(
            source_module="alpha",
            request=sample_request(dedupe_key="n1", recipients=("u1",)),
            now=aware_beijing_datetime(),
        )
        storage.create_or_get(
            source_module="alpha",
            request=sample_request(dedupe_key="n2", recipients=("u2",)),
            now=aware_beijing_datetime(),
        )
        page = storage.list_for_user("u1", unread_only=False, limit=20, cursor=None, now=aware_beijing_datetime())
        assert len(page.items) == 1
        assert page.items[0].is_read is False

    def test_mark_read_returns_updated_item(self, storage):
        created = storage.create_or_get(
            source_module="alpha",
            request=sample_request(recipients=("u1",)),
            now=aware_beijing_datetime(),
        )
        updated = storage.mark_read("u1", created.notification_id, aware_beijing_datetime())
        assert updated is not None
        assert updated.is_read is True
        assert updated.read_at is not None

    def test_mark_all_read_updates_only_current_user(self, storage):
        storage.create_or_get(
            source_module="alpha",
            request=sample_request(dedupe_key="n1", recipients=("u1", "u2")),
            now=aware_beijing_datetime(),
        )
        storage.create_or_get(
            source_module="alpha",
            request=sample_request(dedupe_key="n2", recipients=("u1",)),
            now=aware_beijing_datetime(),
        )
        updated = storage.mark_all_read("u1", aware_beijing_datetime())
        assert updated == 2
        assert storage.unread_count("u1", aware_beijing_datetime()) == 0
        assert storage.unread_count("u2", aware_beijing_datetime()) == 1

    def test_delete_expired_batch_removes_expired_notifications(self, storage):
        created = storage.create_or_get(
            source_module="alpha",
            request=sample_request(recipients=("u1",)),
            now=aware_beijing_datetime(),
        )
        # Manually expire the notification
        storage.database.connection.tables["system_notifications"][0]["expires_at"] = aware_beijing_datetime(
            2020, 1, 1
        )
        deleted = storage.delete_expired_batch(aware_beijing_datetime(), limit=1000)
        assert deleted == 1
        assert len(storage.database.connection.tables["system_notifications"]) == 0
        assert len(storage.database.connection.tables["system_notification_recipients"]) == 0

    def test_get_for_user_returns_none_for_other_user(self, storage):
        created = storage.create_or_get(
            source_module="alpha",
            request=sample_request(recipients=("u1",)),
            now=aware_beijing_datetime(),
        )
        assert storage.get_for_user("u2", created.notification_id, aware_beijing_datetime()) is None

    def test_cleanup_after_all_recipients_cleared(self, storage):
        """Expired notifications should be cleaned even if all recipients cleared them."""
        created = storage.create_or_get(
            source_module="alpha",
            request=sample_request(recipients=("u1", "u2")),
            now=aware_beijing_datetime(),
        )
        # Expire the notification
        storage.database.connection.tables["system_notifications"][0]["expires_at"] = (
            aware_beijing_datetime() - timedelta(days=1)
        )
        # Both recipients clear it
        storage.delete_all_for_user("u1", aware_beijing_datetime())
        storage.delete_all_for_user("u2", aware_beijing_datetime())
        # Cleanup should still remove the expired notification
        deleted = storage.delete_expired_batch(aware_beijing_datetime(), limit=1000)
        assert deleted >= 1
        assert len(storage.database.connection.tables["system_notifications"]) == 0

    def test_clear_all_works_with_real_sqlalchemy_connection(self):
        class SqlAlchemyApplicationDatabase:
            def __init__(self):
                self.engine = create_engine("sqlite+pysqlite:///:memory:")
                METADATA.create_all(self.engine)

            @contextmanager
            def connect(self):
                with self.engine.connect() as connection:
                    yield connection

            @contextmanager
            def transaction(self):
                with self.engine.begin() as connection:
                    yield connection

        now = datetime(2026, 8, 25, 10, 0, 0)
        storage = NotificationStorage(SqlAlchemyApplicationDatabase())
        storage.create_or_get(
            source_module="alpha",
            request=sample_request(recipients=("u1", "u2")),
            now=now,
        )

        assert storage.delete_all_for_user("u1", now + timedelta(hours=1)) == 1
        assert storage.unread_count("u1", now) == 0
        assert storage.unread_count("u2", now) == 1
