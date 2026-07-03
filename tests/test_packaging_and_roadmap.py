from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "business-schema-config-roadmap.zh-CN.md"
PACKAGE_SCRIPT = ROOT / "scripts" / "package-windows.ps1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_business_schema_config_roadmap_is_saved_for_future_iterations():
    assert ROADMAP.exists()
    text = _read(ROADMAP)

    for expected in [
        "当前版本已完成后端查询层配置化",
        "reconcile-schema.yaml",
        "配置文件驱动",
        "元数据校验",
        "不要完全依赖动态识别业务含义",
        "字段配置版本",
        "历史记录",
    ]:
        assert expected in text


def test_windows_packaging_script_and_docs_are_present():
    assert PACKAGE_SCRIPT.exists()
    script = _read(PACKAGE_SCRIPT)
    readme = _read(README)

    assert "PyInstaller" in script
    assert "pytest" in script
    assert "$LASTEXITCODE -ne 0" in script
    assert "dist\\auto-check.exe" in script
    assert "scripts\\package-windows.ps1" in readme
    assert "每次调整完需要先测试并打包" in readme
