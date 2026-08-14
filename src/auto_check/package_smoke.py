from __future__ import annotations

import importlib
from importlib import resources
from typing import Any

from auto_check.app.module_system.discovery import discover_modules
from auto_check.app.module_system.schema import load_module_migrations


MODULE_ID = "report_special_processing"
MODULE_PACKAGE = "auto_check.modules.report_special_processing"
RESOURCE_PACKAGE = "auto_check.resources.data"
RESOURCE_FILES = ("FileName.xlsx", "RefInfo.xlsx")
SQLALCHEMY_DIALECTS = (
    "sqlalchemy.dialects.mysql",
    "sqlalchemy.dialects.mysql.pymysql",
)


def run_package_smoke() -> dict[str, Any]:
    """Load dynamic packages and data that PyInstaller can otherwise omit."""
    for module_name in SQLALCHEMY_DIALECTS:
        importlib.import_module(module_name)

    discovered = {item.manifest.id: item for item in discover_modules()}
    module = discovered.get(MODULE_ID)
    if module is None:
        raise RuntimeError(f"packaged module is missing: {MODULE_ID}")

    frontend_entry = "web/index.js"
    frontend_asset = resources.files(MODULE_PACKAGE).joinpath(frontend_entry)
    if not frontend_asset.is_file() or not frontend_asset.read_bytes():
        raise RuntimeError(f"packaged module frontend is missing: {frontend_entry}")

    migrations = load_module_migrations(MODULE_PACKAGE)
    migration_versions = [item.version for item in migrations]
    expected_versions = list(range(1, module.manifest.schema_version + 1))
    if migration_versions != expected_versions:
        raise RuntimeError(
            "packaged module migrations do not match schema version: "
            f"expected {expected_versions}, got {migration_versions}"
        )

    resource_root = resources.files(RESOURCE_PACKAGE)
    for name in RESOURCE_FILES:
        resource = resource_root.joinpath(name)
        if not resource.is_file() or not resource.read_bytes():
            raise RuntimeError(f"packaged resource is missing: {name}")

    return {
        "status": "ok",
        "module_id": module.manifest.id,
        "schema_version": module.manifest.schema_version,
        "migration_versions": migration_versions,
        "frontend_entry": frontend_entry,
        "resource_files": list(RESOURCE_FILES),
    }
