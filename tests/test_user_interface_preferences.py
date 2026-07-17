import re
from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "004_user_interface_preferences.sql"


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
