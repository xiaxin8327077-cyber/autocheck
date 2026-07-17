from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "004_user_interface_preferences.sql"


def test_user_interface_preferences_schema_is_safe_incremental_ddl():
    assert SCHEMA_SQL.exists(), "user interface preferences schema SQL is required"

    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    upper = sql.upper()

    assert "CREATE TABLE IF NOT EXISTS `user_interface_preferences`" in sql
    assert "`user_id` VARCHAR(64) NOT NULL COMMENT '用户 ID'" in sql
    assert "`radius_px` TINYINT UNSIGNED NOT NULL DEFAULT 4" in sql
    assert "`updated_at` DATETIME(6) NOT NULL" in sql
    assert "PRIMARY KEY (`user_id`)" in sql
    assert "CHECK (`radius_px` BETWEEN 1 AND 15)" in sql
    assert "COMMENT='用户界面偏好表：保存每个用户的界面圆角设置。'" in sql
    assert "FOREIGN KEY" not in upper
    assert "DROP" not in upper
    assert "TRUNCATE" not in upper
    assert "ALTER" not in upper
    assert "APP_SCHEMA_VERSION" not in upper


def test_application_schema_keeps_version_one_and_adds_user_interface_preferences():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["user_interface_preferences"] == frozenset(
        {"user_id", "radius_px", "updated_at"}
    )
    assert len(EXPECTED_APP_SCHEMA) == 36
