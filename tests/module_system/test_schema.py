from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[2]
MODULE_SQL = ROOT / "sql" / "app_storage" / "mysql" / "012_module_system.sql"


def test_module_system_core_tables_are_part_of_expected_schema():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["app_modules"] >= {
        "module_id",
        "module_version",
        "enabled",
        "status",
        "last_error",
        "installed_at",
        "updated_at",
    }
    assert EXPECTED_APP_SCHEMA["app_module_schema_versions"] >= {
        "module_id",
        "schema_version",
        "applied_at",
        "checksum",
    }
    assert EXPECTED_APP_SCHEMA["app_module_migration_history"] >= {
        "id",
        "module_id",
        "from_version",
        "to_version",
        "status",
        "checksum",
        "started_at",
        "finished_at",
        "error_message",
    }
    assert len(EXPECTED_APP_SCHEMA) == 42


def test_module_system_sql_is_repeatable_and_does_not_change_core_version():
    sql = MODULE_SQL.read_text(encoding="utf-8")

    assert sql.count("CREATE TABLE IF NOT EXISTS") == 3
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "INSERT INTO `app_schema_version`" not in sql
