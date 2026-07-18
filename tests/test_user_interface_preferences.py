import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA
from auto_check.app.storage_user_interface_preferences import (
    UserInterfacePreferences,
    load_user_interface_preferences,
    prune_user_interface_preferences,
    save_user_interface_preferences,
)
from mysql_config_test_support import MySqlContractConnection


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "004_user_interface_preferences.sql"
PREFERENCE_UPDATES_SQL = (
    ROOT / "sql" / "app_storage" / "mysql" / "005_user_appearance_preferences.sql"
)


def _assert_preferences(
    preferences,
    radius_px,
    line_chart_style,
    vitality_theme_color,
    calm_theme_color,
):
    assert preferences.__class__.__name__ == "UserInterfacePreferences"
    assert preferences.radius_px == radius_px
    assert preferences.line_chart_style == line_chart_style
    assert preferences.vitality_theme_color == vitality_theme_color
    assert preferences.calm_theme_color == calm_theme_color


def test_user_interface_preferences_schema_is_safe_incremental_ddl():
    assert SCHEMA_SQL.exists(), "user interface preferences schema SQL is required"

    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    upper = sql.upper()
    sql_without_comments = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql_without_comments = re.sub(r"(?m)(?:--|#)[^\r\n]*$", "", sql_without_comments)
    normalized_sql = " ".join(sql_without_comments.split())

    create_table = "CREATE TABLE IF NOT EXISTS `user_interface_preferences`"
    assert upper.count("CREATE TABLE IF NOT EXISTS") == 1
    assert sql.count(create_table) == 1
    assert normalized_sql.count(";") == 1
    assert len([statement for statement in normalized_sql.split(";") if statement.strip()]) == 1
    assert "`user_id` VARCHAR(64) NOT NULL COMMENT '用户 ID'" in sql
    assert "`radius_px` TINYINT UNSIGNED NOT NULL DEFAULT 4 COMMENT '界面圆角像素值，范围 1 至 15'" in sql
    assert "`updated_at` DATETIME(6) NOT NULL COMMENT '更新时间'" in sql
    assert "PRIMARY KEY (`user_id`)" in sql
    assert "CHECK (`radius_px` BETWEEN 1 AND 15)" in sql
    assert "COMMENT='用户界面偏好表：保存每个用户的界面圆角设置。'" in sql
    for forbidden_keyword in (
        "CREATE DATABASE",
        "USE",
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "DROP",
        "TRUNCATE",
        "ALTER",
        "FOREIGN KEY",
        "APP_SCHEMA_VERSION",
    ):
        pattern = r"\b" + re.escape(forbidden_keyword).replace(r"\ ", r"\s+") + r"\b"
        assert re.search(pattern, upper) is None, forbidden_keyword


def test_user_interface_preference_updates_are_guarded_incremental_ddl():
    assert PREFERENCE_UPDATES_SQL.exists(), "appearance preference update SQL is required"

    sql = PREFERENCE_UPDATES_SQL.read_text(encoding="utf-8")
    sql_without_comments = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql_without_comments = re.sub(r"(?m)(?:--|#)[^\r\n]*$", "", sql_without_comments)
    upper = sql_without_comments.upper()

    assert "DATABASE()" in upper
    assert "INFORMATION_SCHEMA.COLUMNS" in upper
    assert "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in upper
    assert "PREPARE" in upper
    assert "EXECUTE" in upper
    assert "DEALLOCATE PREPARE" in upper
    assert "THEME_GRADIENT_ENABLED" not in upper
    assert "`line_chart_style` VARCHAR(16) NOT NULL DEFAULT ''straight''" in sql
    assert "`vitality_theme_color` CHAR(7) NULL" in sql
    assert "`calm_theme_color` CHAR(7) NULL" in sql
    assert "CHECK (`line_chart_style` IN (''straight'', ''smooth''))" in sql
    assert "CHECK (`vitality_theme_color` IS NULL OR REGEXP_LIKE(`vitality_theme_color`, ''^#[0-9A-F]{6}$'', ''c''))" in sql
    assert "CHECK (`calm_theme_color` IS NULL OR REGEXP_LIKE(`calm_theme_color`, ''^#[0-9A-F]{6}$'', ''c''))" in sql
    assert "BINARY `vitality_theme_color` REGEXP" not in sql
    assert "BINARY `calm_theme_color` REGEXP" not in sql
    assert "ALTER TABLE `user_interface_preferences`" in sql
    assert set(re.findall(r"ALTER\s+TABLE\s+`([^`]+)`", upper)) == {
        "USER_INTERFACE_PREFERENCES"
    }
    for forbidden_keyword in (
        "CREATE TABLE",
        "CREATE DATABASE",
        "USE",
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "DROP",
        "TRUNCATE",
        "FOREIGN KEY",
        "APP_SCHEMA_VERSION",
    ):
        pattern = r"\b" + re.escape(forbidden_keyword).replace(r"\ ", r"\s+") + r"\b"
        assert re.search(pattern, upper) is None, forbidden_keyword


def test_application_schema_keeps_version_one_and_adds_user_interface_preferences():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["user_interface_preferences"] == frozenset(
        {
            "user_id",
            "radius_px",
            "line_chart_style",
            "vitality_theme_color",
            "calm_theme_color",
            "updated_at",
        }
    )
    assert "theme_gradient_enabled" not in EXPECTED_APP_SCHEMA["user_interface_preferences"]
    assert len(EXPECTED_APP_SCHEMA) == 37


def test_missing_interface_preferences_use_complete_defaults():
    connection = MySqlContractConnection()

    assert UserInterfacePreferences() == UserInterfacePreferences(4, "straight", None, None)
    _assert_preferences(
        load_user_interface_preferences(connection, "user-a"),
        radius_px=4,
        line_chart_style="straight",
        vitality_theme_color=None,
        calm_theme_color=None,
    )


def test_loaded_interface_preferences_are_immutable():
    connection = MySqlContractConnection()
    preferences = load_user_interface_preferences(connection, "user-a")

    with pytest.raises(FrozenInstanceError):
        preferences.radius_px = 8


@pytest.mark.parametrize(
    ("stored_preferences", "expected_preferences"),
    [
        (
            {
                "radius_px": 99,
                "line_chart_style": "smooth",
                "vitality_theme_color": "#3f6faf",
                "calm_theme_color": "#112233",
            },
            (4, "smooth", "#3F6FAF", "#112233"),
        ),
        (
            {
                "radius_px": 8,
                "line_chart_style": "curved",
                "vitality_theme_color": "#AABBCC",
                "calm_theme_color": "invalid",
            },
            (8, "straight", "#AABBCC", None),
        ),
    ],
)
def test_malformed_interface_preference_fields_fall_back_independently(
    stored_preferences, expected_preferences
):
    connection = MySqlContractConnection()
    connection.tables["user_interface_preferences"].append(
        {"user_id": "user-a", **stored_preferences, "updated_at": None}
    )

    _assert_preferences(load_user_interface_preferences(connection, "user-a"), *expected_preferences)


def test_interface_preferences_upsert_preserves_reserved_personal_colors():
    connection = MySqlContractConnection()
    connection.tables["user_interface_preferences"].append(
        {
            "user_id": "user-a",
            "radius_px": 2,
            "line_chart_style": "straight",
            "vitality_theme_color": "#ABCDEF",
            "calm_theme_color": "#123456",
            "updated_at": None,
        }
    )

    _assert_preferences(
        save_user_interface_preferences(
            connection,
            "user-a",
            radius_px=15,
            line_chart_style="smooth",
        ),
        15,
        "smooth",
        "#ABCDEF",
        "#123456",
    )

    assert any("ON DUPLICATE KEY UPDATE" in sql.upper() for sql in connection.executed_sql)
    assert connection.tables["user_interface_preferences"] == [
        {
            "user_id": "user-a",
            "radius_px": 15,
            "line_chart_style": "smooth",
            "vitality_theme_color": "#ABCDEF",
            "calm_theme_color": "#123456",
            "updated_at": connection.tables["user_interface_preferences"][0]["updated_at"],
        }
    ]


def test_new_interface_preference_row_reserves_null_personal_colors():
    connection = MySqlContractConnection()

    saved = save_user_interface_preferences(
        connection, "user-a", radius_px=3, line_chart_style="straight"
    )

    _assert_preferences(saved, 3, "straight", None, None)
    assert connection.tables["user_interface_preferences"][0]["vitality_theme_color"] is None
    assert connection.tables["user_interface_preferences"][0]["calm_theme_color"] is None


def test_interface_preferences_isolate_users():
    connection = MySqlContractConnection()
    save_user_interface_preferences(connection, "user-a", radius_px=3, line_chart_style="straight")
    save_user_interface_preferences(connection, "user-b", radius_px=12, line_chart_style="smooth")

    _assert_preferences(load_user_interface_preferences(connection, "user-a"), 3, "straight", None, None)
    _assert_preferences(load_user_interface_preferences(connection, "user-b"), 12, "smooth", None, None)
    assert len(connection.tables["user_interface_preferences"]) == 2


def test_prune_interface_preferences_keeps_only_active_users():
    connection = MySqlContractConnection()
    save_user_interface_preferences(connection, "active", radius_px=6, line_chart_style="smooth")
    save_user_interface_preferences(connection, "deleted", radius_px=12, line_chart_style="straight")

    prune_user_interface_preferences(connection, ["active", "", "active"])

    assert [row["user_id"] for row in connection.tables["user_interface_preferences"]] == ["active"]
    _assert_preferences(load_user_interface_preferences(connection, "active"), 6, "smooth", None, None)
    _assert_preferences(load_user_interface_preferences(connection, "deleted"), 4, "straight", None, None)


def test_prune_interface_preferences_with_no_active_users_clears_all():
    connection = MySqlContractConnection()
    save_user_interface_preferences(connection, "user-a", radius_px=2, line_chart_style="straight")
    save_user_interface_preferences(connection, "user-b", radius_px=14, line_chart_style="smooth")

    prune_user_interface_preferences(connection, [])

    assert connection.tables["user_interface_preferences"] == []


@pytest.mark.parametrize("invalid_value", [0, 16, True, 1.5])
def test_save_interface_preferences_rejects_invalid_radius(invalid_value):
    connection = MySqlContractConnection()

    with pytest.raises(ValueError) as exc_info:
        save_user_interface_preferences(
            connection,
            "user-a",
            radius_px=invalid_value,
            line_chart_style="straight",
        )

    assert str(exc_info.value) == "radius_px must be an integer between 1 and 15"


@pytest.mark.parametrize("invalid_value", ["", "curved", True, None])
def test_save_interface_preferences_rejects_unknown_line_chart_style(invalid_value):
    connection = MySqlContractConnection()

    with pytest.raises(ValueError) as exc_info:
        save_user_interface_preferences(
            connection,
            "user-a",
            radius_px=4,
            line_chart_style=invalid_value,
        )

    assert str(exc_info.value) == "line_chart_style must be one of: smooth, straight"
