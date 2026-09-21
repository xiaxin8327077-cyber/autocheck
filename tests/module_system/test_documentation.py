import json
import re
from pathlib import Path

from auto_check.app.module_system.contracts import ModuleManifest


ROOT = Path(__file__).resolve().parents[2]


def test_deployment_docs_include_module_schema_upgrade():
    for relative in [
        "docs/project-history.zh-CN.md",
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


def test_module_development_guide_defines_explicit_external_readonly_route_contract():
    content = (ROOT / "docs/module-development-guide.zh-CN.md").read_text(encoding="utf-8")

    for fragment in [
        "external=True",
        "/api/external/v1/",
        "只允许 `GET`",
        "platform.external_api_status",
        "get_status()",
        "verify_candidate()",
        "普通模块不得直接读取或记录环境 Token",
    ]:
        assert fragment in content


def test_dashboard_management_external_api_doc_covers_monitoring():
    content = (ROOT / "docs/dashboard-management-external-api.zh-CN.md").read_text(encoding="utf-8")

    for fragment in [
        "Token 缺失或错误 401",
        "限流 429",
        "Token 未配置或认证服务异常 503",
        "精确路径错误方法 405",
        "未命中精确接口的 404 和内部预览不记录",
        "TCP 对端 IP",
        "X-Forwarded-For",
        "30 天",
        "接口监控",
        "返回看板管理",
    ]:
        assert fragment in content
    assert "尚未包含在当前外部 v1 接口交付中" not in content
