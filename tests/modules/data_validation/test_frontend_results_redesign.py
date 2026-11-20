import json
import shutil
import subprocess
import re
from pathlib import Path

import pytest

from .test_frontend_results_behavior import WEB, copy_web_modules


def test_result_fonts_load_through_real_module_asset_whitelist():
    from auto_check.app.module_system.discovery import discover_modules
    from auto_check.app.module_system.resources import read_module_asset
    module = next(item for item in discover_modules() if item.manifest.id == "data_validation")
    pending = ["results-replica.css"]
    visited = set()
    faces = 0
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        asset = read_module_asset(module, name)
        assert asset.content_type.startswith("text/css")
        css = asset.content.decode("utf-8")
        assert "https://" not in css
        assert "url('./fonts/" not in css, "字体必须能通过既有静态资源白名单加载"
        pending.extend(re.findall(r'@import url\("\./([^\"]+)"\)', css))
        faces += css.count("data:font/woff2;base64,")
    assert faces == 6
    import base64
    for weight in ("400", "500", "600"):
        parts = []
        for part in ("a", "b"):
            asset = read_module_asset(module, f"fonts/Noto_Sans_SC-{weight}-{part}.json")
            parts.append(json.loads(asset.content)["data"])
        assert base64.b64decode("".join(parts)).startswith(b"wOF2")


def test_result_drawer_stays_above_execution_background():
    css = (WEB / "styles.css").read_text(encoding="utf-8") + (WEB / "results-replica.css").read_text(encoding="utf-8")
    drawer = re.search(r"\.dv-result-overlay\s*\{([^}]+)\}", css).group(1)
    assert int(re.search(r"z-index:\s*(\d+)", drawer).group(1)) >= 1000


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_result_modes_share_list_and_rule_drawer(tmp_path: Path) -> None:
    copy_web_modules(tmp_path)
    for name in ("frontend_results_modes.mjs", "frontend_workbench_dom.mjs"):
        (tmp_path / name).write_text(Path(__file__).with_name(name).read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(["node", str(tmp_path / "frontend_results_modes.mjs")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_classified_results_dynamic_query_data_and_final_poll(tmp_path: Path) -> None:
    copy_web_modules(tmp_path)
    for name in ("frontend_results_redesign.mjs", "frontend_workbench_dom.mjs"):
        (tmp_path / name).write_text(Path(__file__).with_name(name).read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(["node", str(tmp_path / "frontend_results_redesign.mjs")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_selection_sources_and_backdrop(tmp_path: Path) -> None:
    copy_web_modules(tmp_path)
    for name in ("frontend_execution_dialog.mjs", "frontend_workbench_dom.mjs"):
        (tmp_path / name).write_text(Path(__file__).with_name(name).read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(["node", str(tmp_path / "frontend_execution_dialog.mjs")], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"]
