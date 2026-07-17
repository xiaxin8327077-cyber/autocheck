from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MYSQL_STORAGE_DOC = ROOT / "docs" / "mysql-application-storage.zh-CN.md"
DEPLOYMENT_DOC = ROOT / "docs" / "deployment.zh-CN.md"
INTRANET_DEPLOYMENT_DOC = ROOT / "docs" / "intranet-production-deployment.zh-CN.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_readme_documents_user_interface_radius_behavior_and_scope() -> None:
    readme = _read(README)

    for expected in [
        "每个用户独立",
        "系统设置→界面设置",
        "1–15px",
        "默认 4px",
        "拖动即可预览",
        "显式保存",
        "仅影响显示，不改变系统功能",
        "导航",
        "卡片",
        "按钮",
        "输入框",
        "选择控件",
        "弹窗及弹窗内控件",
        "特殊形状",
    ]:
        assert expected in readme


def test_readme_distinguishes_migrated_rows_from_complete_mysql_schema() -> None:
    verification_line = next(
        line for line in _read(README).splitlines() if "上线核验" in line
    )

    assert "原 20 张迁移目标表的数据行数" in verification_line
    assert "当前完整 36 张应用存储表结构" in verification_line
    assert "004_user_interface_preferences.sql" in verification_line
    assert "MySQL 20 张表和迁移行数齐全" not in verification_line


def test_mysql_rollout_docs_require_004_and_36_table_sequence() -> None:
    for path in [README, MYSQL_STORAGE_DOC, DEPLOYMENT_DOC, INTRANET_DEPLOYMENT_DOC]:
        text = _read(path)
        scripts = [
            "001_init_schema.sql",
            "002_report_navigation.sql",
            "003_report_navigation_seed.sql",
            "004_user_interface_preferences.sql",
        ]
        assert "36 张" in text
        assert all(script in text for script in scripts)
        assert [text.index(script) for script in scripts] == sorted(
            text.index(script) for script in scripts
        )

    mysql_doc = _read(MYSQL_STORAGE_DOC)
    assert "user_interface_preferences" in mysql_doc
    assert "每个用户" in mysql_doc
    assert "不设置外键" in mysql_doc
    assert "孤儿偏好" in mysql_doc


def test_deployment_upgrade_docs_define_safe_manual_004_boundary() -> None:
    for path in [DEPLOYMENT_DOC, INTRANET_DEPLOYMENT_DOC]:
        text = _read(path)
        assert "升级应用前" in text
        assert "CREATE TABLE IF NOT EXISTS" in text
        assert "可重复执行" in text
        assert "不代表已在任何线上环境执行" in text
        assert "每个用户" in text
        assert "不设置外键" in text
        assert "孤儿偏好" in text
