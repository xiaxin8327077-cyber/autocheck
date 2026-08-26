from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA

ROOT = Path(__file__).resolve().parents[2]


def test_notification_tables_are_core_application_schema():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["system_notifications"] == frozenset(
        {
            "id",
            "source_module",
            "event_type",
            "category",
            "level",
            "title",
            "content",
            "action_json",
            "dedupe_key",
            "dedupe_hash",
            "created_at",
            "expires_at",
        }
    )
    assert EXPECTED_APP_SCHEMA["system_notification_recipients"] == frozenset(
        {
            "notification_id",
            "user_id",
            "received_at",
            "read_at",
            "cleared_at",
        }
    )


def test_notification_migration_has_required_keys_and_does_not_bump_global_version():
    sql = (ROOT / "sql/app_storage/mysql/018_system_notifications.sql").read_text("utf-8")
    assert "CREATE TABLE IF NOT EXISTS `system_notifications`" in sql
    assert "UNIQUE KEY `uk_system_notifications_source_event`" in sql
    assert "KEY `ix_system_notifications_expires`" in sql
    assert "CREATE TABLE IF NOT EXISTS `system_notification_recipients`" in sql
    assert "PRIMARY KEY (`notification_id`, `user_id`)" in sql
    assert "ON DELETE CASCADE" in sql
    assert "INSERT INTO `app_schema_version`" not in sql
    assert "UPDATE `app_schema_version`" not in sql
