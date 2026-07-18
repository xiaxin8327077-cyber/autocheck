import copy
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from sqlalchemy.dialects.mysql import CHAR, TINYINT

from auto_check.app.storage_system_interface_preferences import (
    EffectiveThemeColors,
    SYSTEM_INTERFACE_PREFERENCES,
    SystemInterfacePreferences,
    load_system_interface_preferences,
    normalize_theme_color,
    resolve_effective_theme_colors,
    save_system_interface_preferences,
)
from auto_check.app.storage_user_interface_preferences import UserInterfacePreferences
from mysql_config_test_support import MySqlContractConnection


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "006_system_interface_preferences.sql"


def test_system_interface_preferences_schema_is_guarded_and_contains_no_seed_dml():
    assert SCHEMA_SQL.exists(), "system interface preferences schema SQL is required"

    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    upper = sql.upper()
    sql_without_comments = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql_without_comments = re.sub(r"(?m)(?:--|#)[^\r\n]*$", "", sql_without_comments)
    normalized_sql = " ".join(sql_without_comments.split())

    assert upper.count("CREATE TABLE IF NOT EXISTS") == 1
    assert normalized_sql.count(";") == 1
    assert "CREATE TABLE IF NOT EXISTS `system_interface_preferences`" in sql
    assert "`id` TINYINT UNSIGNED NOT NULL" in sql
    assert "`vitality_theme_color` CHAR(7) NOT NULL DEFAULT '#3F6FAF'" in sql
    assert "`calm_theme_color` CHAR(7) NOT NULL DEFAULT '#355F63'" in sql
    assert "`updated_by` VARCHAR(64) NULL" in sql
    assert "`updated_at` DATETIME(6) NOT NULL" in sql
    assert "PRIMARY KEY (`id`)" in sql
    assert "CHECK (`id` = 1)" in sql
    assert "CHECK (REGEXP_LIKE(`vitality_theme_color`, '^#[0-9A-F]{6}$', 'c'))" in sql
    assert "CHECK (REGEXP_LIKE(`calm_theme_color`, '^#[0-9A-F]{6}$', 'c'))" in sql
    assert "BINARY `vitality_theme_color` REGEXP" not in sql
    assert "BINARY `calm_theme_color` REGEXP" not in sql
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


def test_system_interface_preferences_sqlalchemy_table_matches_unsigned_singleton_id():
    id_type = SYSTEM_INTERFACE_PREFERENCES.c.id.type

    assert isinstance(id_type, TINYINT)
    assert id_type.unsigned is True
    assert isinstance(SYSTEM_INTERFACE_PREFERENCES.c.vitality_theme_color.type, CHAR)
    assert isinstance(SYSTEM_INTERFACE_PREFERENCES.c.calm_theme_color.type, CHAR)


def test_system_theme_models_and_normalization_are_strict_and_immutable():
    assert SystemInterfacePreferences() == SystemInterfacePreferences("#3F6FAF", "#355F63", None)
    assert EffectiveThemeColors() == EffectiveThemeColors("#3F6FAF", "#355F63")
    assert normalize_theme_color("#3f6faf") == "#3F6FAF"
    assert normalize_theme_color(None, allow_none=True) is None

    with pytest.raises(ValueError, match=r"#RRGGBB"):
        normalize_theme_color("#fff")
    with pytest.raises(ValueError, match=r"#RRGGBB"):
        normalize_theme_color(None)
    with pytest.raises(ValueError, match=r"#RRGGBB"):
        normalize_theme_color(123456)
    with pytest.raises(FrozenInstanceError):
        SystemInterfacePreferences().vitality_theme_color = "#000000"


def test_missing_system_interface_preferences_use_code_defaults():
    connection = MySqlContractConnection()

    assert load_system_interface_preferences(connection) == SystemInterfacePreferences()


def test_malformed_system_fields_fall_back_independently():
    connection = MySqlContractConnection()
    connection.tables["system_interface_preferences"].append(
        {
            "id": 1,
            "vitality_theme_color": "#3f6faf",
            "calm_theme_color": "#112233",
            "updated_by": "admin-id",
            "updated_at": None,
        }
    )

    assert load_system_interface_preferences(connection) == SystemInterfacePreferences(
        "#3F6FAF", "#112233", "admin-id"
    )


def test_system_theme_save_updates_both_colors_and_audit_identity_atomically():
    connection = MySqlContractConnection()

    saved = save_system_interface_preferences(
        connection,
        vitality_theme_color="#abcdef",
        calm_theme_color="#123456",
        updated_by="admin-id",
    )

    assert saved == SystemInterfacePreferences("#ABCDEF", "#123456", "admin-id")
    assert load_system_interface_preferences(connection) == saved
    assert len(connection.tables["system_interface_preferences"]) == 1
    assert any("ON DUPLICATE KEY UPDATE" in sql.upper() for sql in connection.executed_sql)

    before_rows = copy.deepcopy(connection.tables["system_interface_preferences"])
    before_sql_count = len(connection.executed_sql)
    with pytest.raises(ValueError, match=r"#RRGGBB"):
        save_system_interface_preferences(
            connection,
            vitality_theme_color="#654321",
            calm_theme_color="invalid",
            updated_by="other-admin",
        )

    assert connection.tables["system_interface_preferences"] == before_rows
    assert len(connection.executed_sql) == before_sql_count


def test_effective_theme_colors_resolve_personal_overrides_per_field():
    system = SystemInterfacePreferences("#111111", "#222222", "admin-id")

    assert resolve_effective_theme_colors(
        UserInterfacePreferences(vitality_theme_color="#ABCDEF"), system
    ) == EffectiveThemeColors("#ABCDEF", "#222222")
    assert resolve_effective_theme_colors(
        UserInterfacePreferences(calm_theme_color="#123456"), system
    ) == EffectiveThemeColors("#111111", "#123456")
