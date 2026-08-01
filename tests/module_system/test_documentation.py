import json
import re
from pathlib import Path

from auto_check.app.module_system.contracts import ModuleManifest


ROOT = Path(__file__).resolve().parents[2]


def test_deployment_docs_include_module_schema_upgrade():
    for relative in [
        "README.md",
        "docs/mysql-application-storage.zh-CN.md",
        "docs/mysql-application-storage-progress.zh-CN.md",
        "docs/deployment.zh-CN.md",
        "docs/intranet-production-deployment.zh-CN.md",
        "docs/production-baseline-diff-audit-2026-07-24.zh-CN.md",
        "docs/production-release-file-checklist-2026-07-25.zh-CN.md",
    ]:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "012_module_system.sql" in content


def test_module_development_guide_defines_required_contracts():
    content = (ROOT / "docs/module-development-guide.zh-CN.md").read_text(encoding="utf-8")

    for fragment in [
        "manifest.json",
        "backend_entry",
        "api_prefix",
        "platform_api",
        "schema_version",
        "register_routes",
        "register_schema",
        "mount",
        "activate",
        "deactivate",
        "unmount",
        "-- module-statement-break",
        "python -m pytest tests/modules",
    ]:
        assert fragment in content


def test_module_development_guide_manifest_example_is_a_real_module_manifest():
    content = (ROOT / "docs/module-development-guide.zh-CN.md").read_text(encoding="utf-8")
    manifest_text = re.search(
        r"## 1\. 清单与命名空间.*?```json\n(.*?)\n```",
        content,
        flags=re.DOTALL,
    )

    assert manifest_text is not None
    manifest = ModuleManifest.from_mapping(json.loads(manifest_text.group(1)))

    assert manifest.navigation[0].id == "example_module"
    assert manifest.navigation[0].label == "示例模块"
    assert manifest.navigation[0].route == "example-module"
    assert manifest.navigation[0].order == 100
    assert manifest.navigation[0].permission == "example_module.view"


def test_module_development_guide_uses_actual_backend_and_frontend_context_contracts():
    content = (ROOT / "docs/module-development-guide.zh-CN.md").read_text(encoding="utf-8")

    assert "ModuleRequest.current_user" in content
    for field in [
        "application_database",
        "config_path",
        "temp_root",
        "now",
        "services",
        "events",
        "logger",
        "background_executor",
    ]:
        assert f"`{field}`" in content

    assert "FrontendModuleContext" not in content
    assert "`root`、`api`、`user`、`notify`、`confirm`、`navigate`、`events`" in content
    assert "Object.freeze" in content
