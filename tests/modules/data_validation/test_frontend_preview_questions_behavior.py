from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "data_validation" / "web"
SCENARIO = Path(__file__).with_name("frontend_preview_questions_behavior.mjs")


def copy_web_modules(tmp_path: Path) -> None:
    for source in WEB.rglob("*.js"):
        target = tmp_path / source.relative_to(WEB)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = target.with_suffix(".mjs")
        content = source.read_text(encoding="utf-8").replace('.js"', '.mjs"').replace(".js'", ".mjs'")
        target.write_text(content, encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用，跳过前端行为测试；静态测试仍执行")
def test_frontend_staged_preview_questions_merge(tmp_path: Path) -> None:
    copy_web_modules(tmp_path)
    scenario = tmp_path / "frontend_preview_questions_behavior.mjs"
    scenario.write_text(SCENARIO.read_text(encoding="utf-8"), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(scenario)], cwd=tmp_path, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert json.loads(completed.stdout.strip())["ok"] is True
