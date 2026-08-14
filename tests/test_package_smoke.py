from auto_check.package_smoke import run_package_smoke


def test_package_smoke_loads_dynamic_module_assets_migrations_and_resources() -> None:
    result = run_package_smoke()

    assert result["module_id"] == "report_special_processing"
    assert result["schema_version"] == 3
    assert result["migration_versions"] == [1, 2, 3]
    assert result["frontend_entry"] == "web/index.js"
    assert result["resource_files"] == ["FileName.xlsx", "RefInfo.xlsx"]
    assert result["status"] == "ok"
