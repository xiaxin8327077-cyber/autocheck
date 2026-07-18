import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA
from auto_check.app.storage_user_interface_preferences import (
    load_user_interface_preferences,
    prune_user_interface_preferences,
    save_user_interface_preferences,
)
from mysql_config_test_support import MySqlContractConnection


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "004_user_interface_preferences.sql"


def _assert_preferences(preferences, radius_px, theme_gradient_enabled, line_chart_style):
    assert preferences.__class__.__name__ == "UserInterfacePreferences"
    assert preferences.radius_px == radius_px
    assert preferences.theme_gradient_enabled is theme_gradient_enabled
    assert preferences.line_chart_style == line_chart_style


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


def test_application_schema_keeps_version_one_and_adds_user_interface_preferences():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["user_interface_preferences"] == frozenset(
        {"user_id", "radius_px", "updated_at"}
    )
    assert len(EXPECTED_APP_SCHEMA) == 36


def test_missing_interface_preferences_use_complete_defaults():
    connection = MySqlContractConnection()

    _assert_preferences(
        load_user_interface_preferences(connection, "user-a"),
        radius_px=4,
        theme_gradient_enabled=False,
        line_chart_style="straight",
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
            {"radius_px": 99, "theme_gradient_enabled": 1, "line_chart_style": "smooth"},
            (4, True, "smooth"),
        ),
        (
            {"radius_px": 8, "theme_gradient_enabled": True, "line_chart_style": "smooth"},
            (8, False, "smooth"),
        ),
        (
            {"radius_px": 8, "theme_gradient_enabled": 0, "line_chart_style": "curved"},
            (8, False, "straight"),
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


def test_interface_preferences_upsert_keeps_one_latest_row():
    connection = MySqlContractConnection()

    _assert_preferences(
        save_user_interface_preferences(
            connection,
            "user-a",
            radius_px=1,
            theme_gradient_enabled=True,
            line_chart_style="smooth",
        ),
        1,
        True,
        "smooth",
    )
    _assert_preferences(
        save_user_interface_preferences(
            connection,
            "user-a",
            radius_px=15,
            theme_gradient_enabled=False,
            line_chart_style="straight",
        ),
        15,
        False,
        "straight",
    )

    _assert_preferences(load_user_interface_preferences(connection, "user-a"), 15, False, "straight")
    assert any(
        "ON DUPLICATE KEY UPDATE" in sql.upper() for sql in connection.executed_sql
    )
    assert connection.tables["user_interface_preferences"] == [
        {
            "user_id": "user-a",
            "radius_px": 15,
            "theme_gradient_enabled": 0,
            "line_chart_style": "straight",
            "updated_at": connection.tables["user_interface_preferences"][0]["updated_at"],
        }
    ]
    assert type(connection.tables["user_interface_preferences"][0]["theme_gradient_enabled"]) is int


def test_interface_preferences_isolate_users():
    connection = MySqlContractConnection()

    save_user_interface_preferences(
        connection, "user-a", radius_px=3, theme_gradient_enabled=False, line_chart_style="straight"
    )
    save_user_interface_preferences(
        connection, "user-b", radius_px=12, theme_gradient_enabled=True, line_chart_style="smooth"
    )

    _assert_preferences(load_user_interface_preferences(connection, "user-a"), 3, False, "straight")
    _assert_preferences(load_user_interface_preferences(connection, "user-b"), 12, True, "smooth")
    assert len(connection.tables["user_interface_preferences"]) == 2


def test_prune_interface_preferences_keeps_only_active_users():
    connection = MySqlContractConnection()
    save_user_interface_preferences(
        connection, "active", radius_px=6, theme_gradient_enabled=True, line_chart_style="smooth"
    )
    save_user_interface_preferences(
        connection, "deleted", radius_px=12, theme_gradient_enabled=False, line_chart_style="straight"
    )

    prune_user_interface_preferences(connection, ["active", "", "active"])

    assert [row["user_id"] for row in connection.tables["user_interface_preferences"]] == [
        "active"
    ]
    _assert_preferences(load_user_interface_preferences(connection, "active"), 6, True, "smooth")
    _assert_preferences(load_user_interface_preferences(connection, "deleted"), 4, False, "straight")


def test_prune_interface_preferences_with_no_active_users_clears_all():
    connection = MySqlContractConnection()
    save_user_interface_preferences(
        connection, "user-a", radius_px=2, theme_gradient_enabled=False, line_chart_style="straight"
    )
    save_user_interface_preferences(
        connection, "user-b", radius_px=14, theme_gradient_enabled=True, line_chart_style="smooth"
    )

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
            theme_gradient_enabled=False,
            line_chart_style="straight",
        )

    assert str(exc_info.value) == "radius_px must be an integer between 1 and 15"


@pytest.mark.parametrize("invalid_value", [0, 1, "false", None])
def test_save_interface_preferences_rejects_non_boolean_theme_gradient(invalid_value):
    connection = MySqlContractConnection()

    with pytest.raises(ValueError) as exc_info:
        save_user_interface_preferences(
            connection,
            "user-a",
            radius_px=4,
            theme_gradient_enabled=invalid_value,
            line_chart_style="straight",
        )

    assert str(exc_info.value) == "theme_gradient_enabled must be a boolean"


@pytest.mark.parametrize("invalid_value", ["", "curved", True, None])
def test_save_interface_preferences_rejects_unknown_line_chart_style(invalid_value):
    connection = MySqlContractConnection()

    with pytest.raises(ValueError) as exc_info:
        save_user_interface_preferences(
            connection,
            "user-a",
            radius_px=4,
            theme_gradient_enabled=False,
            line_chart_style=invalid_value,
        )

    assert str(exc_info.value) == "line_chart_style must be one of: smooth, straight"
