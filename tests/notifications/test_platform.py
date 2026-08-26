import pytest

from auto_check.app.notifications.platform import (
    NOTIFICATION_SERVICE,
    NOTIFICATION_SERVICE_VERSION,
    create_notification_platform_service,
)
from auto_check.app.notifications.service import NotificationService
from auto_check.app.notifications.storage import NotificationStorage


class FakeUserDirectory:
    def get_user(self, user_id):
        return {"id": user_id, "enabled": True}

    def list_active_users(self):
        return ({"id": "u1", "enabled": True},)


class FakeStreamPublisher:
    def publish(self, user_id, event):
        pass


def make_request(**overrides):
    from auto_check.app.notifications.contracts import (
        NotificationPublishRequest,
        validate_publish_request,
    )
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
def notification_service():
    from tests.mysql_config_test_support import MemoryApplicationDatabase

    storage = NotificationStorage(MemoryApplicationDatabase())
    return NotificationService(storage, FakeUserDirectory(), FakeStreamPublisher(), now=lambda: __import__("datetime").datetime.now())


class TestPlatformService:
    def test_service_name_and_version(self):
        assert NOTIFICATION_SERVICE == "platform.notification"
        assert NOTIFICATION_SERVICE_VERSION == 1

    def test_facade_injects_bound_module_owner(self, notification_service):
        spec = create_notification_platform_service(notification_service)
        assert spec.name == "platform.notification"
        assert spec.version == 1
        bound = spec.binder("report_special_processing")
        bound.value.publish(make_request())
        assert notification_service.published_sources == ["report_special_processing"]

    def test_closed_facade_rejects_publish(self, notification_service):
        bound = create_notification_platform_service(notification_service).binder("alpha")
        bound.close()
        with pytest.raises(RuntimeError, match="closed"):
            bound.value.publish(make_request())

    def test_facade_injects_source_module_automatically(self, notification_service):
        bound = create_notification_platform_service(notification_service).binder("beta")
        result = bound.value.publish(make_request())
        assert result.created is True
        # Verify the source_module was set to the bound owner
        notif = notification_service._storage.database.connection.tables["system_notifications"][0]
        assert notif["source_module"] == "beta"
