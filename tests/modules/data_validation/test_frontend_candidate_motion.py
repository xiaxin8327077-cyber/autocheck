from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from .test_frontend_multi_behavior import copy_web_modules


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用，跳过前端行为测试")
def test_candidate_detail_motion_tracks_expansion_not_render(tmp_path: Path) -> None:
    copy_web_modules(tmp_path)
    directory = Path(__file__).parent
    for name in ("frontend_workbench_dom.mjs", "frontend_candidate_motion.mjs"):
        shutil.copyfile(directory / name, tmp_path / name)
    result = subprocess.run(
        ["node", str(tmp_path / "frontend_candidate_motion.mjs")], cwd=tmp_path,
        text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=60, check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert json.loads(result.stdout.strip())["ok"] is True
