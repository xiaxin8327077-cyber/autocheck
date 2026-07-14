from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DEPLOY_SCRIPT = ROOT / "scripts" / "run-deployed-windows.ps1"
LINUX_DEPLOY_SCRIPT = ROOT / "scripts" / "run-deployed-linux.sh"
DEPLOYMENT_DOC = ROOT / "docs" / "deployment.zh-CN.md"
INTRANET_DEPLOYMENT_DOC = ROOT / "docs" / "intranet-production-deployment.zh-CN.md"
CHECK_HISTORY_DOC = ROOT / "docs" / "check-history-design.zh-CN.md"
LOCAL_SQLITE_DOC = ROOT / "docs" / "local-sqlite-database-design.zh-CN.md"
PRODUCTION_SQLITE_MIGRATION_DOC = ROOT / "docs" / "production-sqlite-storage-migration.zh-CN.md"
MYSQL_STORAGE_DOC = ROOT / "docs" / "mysql-application-storage.zh-CN.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fixed_port_deployment_scripts_and_docs_are_present() -> None:
    windows_script = _read(WINDOWS_DEPLOY_SCRIPT)
    linux_script = _read(LINUX_DEPLOY_SCRIPT)
    deployment_doc = _read(DEPLOYMENT_DOC)

    for text in [windows_script, linux_script, deployment_doc]:
        assert "8765" in text
        assert "AUTO_CHECK_HOST" in text
        assert "AUTO_CHECK_PORT" in text

    assert "--host" in windows_script
    assert "--port" in windows_script
    assert "--no-browser" in windows_script
    assert "--host" in linux_script
    assert "--port" in linux_script
    assert "--no-browser" in linux_script
    assert "0.0.0.0" in deployment_doc


def test_linux_deployment_doc_covers_operational_steps() -> None:
    deployment_doc = _read(DEPLOYMENT_DOC)

    for expected in [
        "python3.12",
        "python3.12-venv",
        "python -m pip install -e .",
        "AUTO_CHECK_CONFIG=/var/lib/auto-check/config.json",
        "systemctl daemon-reload",
        "systemctl enable --now auto-check",
        "journalctl -u auto-check -f",
        "ufw allow",
        "firewall-cmd",
        "curl -I http://127.0.0.1:",
        "tar -czf",
    ]:
        assert expected in deployment_doc


def test_mysql_application_storage_docs_cover_production_cutover() -> None:
    readme = _read(ROOT / "README.md")
    deployment_doc = _read(DEPLOYMENT_DOC)
    intranet_doc = _read(INTRANET_DEPLOYMENT_DOC)
    mysql_doc = _read(MYSQL_STORAGE_DOC)
    check_history_doc = _read(CHECK_HISTORY_DOC)
    local_sqlite_doc = _read(LOCAL_SQLITE_DOC)
    production_sqlite_doc = _read(PRODUCTION_SQLITE_MIGRATION_DOC)

    for text in [readme, deployment_doc, intranet_doc, mysql_doc]:
        assert "MySQL 应用库" in text
        assert "app_database" in text
        assert "auto_check" in text
        assert "sql/app_storage/mysql/001_init_schema.sql" in text
        assert "scripts/export_sqlite_to_mysql.py" in text
        assert "AUTO_CHECK_SECRET_KEY" in text
        assert "本地数据查询页面及入口已隐藏" in text
        assert "删除旧 SQLite `auto-check.db` 后应用仍应只依赖 MySQL 应用库运行" in text

    assert "DatabaseHistoryStore" in check_history_doc
    assert "SqliteHistoryStore" not in check_history_doc
    assert "运行时不再自动迁移旧 SQLite 或旧 JSON 历史" in check_history_doc
    assert "历史迁移与回滚参考" in local_sqlite_doc
    assert "当前运行版本不再使用 SQLite 作为应用存储" in local_sqlite_doc
    assert "历史迁移与回滚参考" in production_sqlite_doc
    assert "不要通过本地数据查询页面迁移旧历史" in production_sqlite_doc
