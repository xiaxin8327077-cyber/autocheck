import json
import shutil
import subprocess
from pathlib import Path

import pytest

from .test_frontend_results_behavior import copy_web_modules


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_ten_thousand_rule_dom_pause_and_server_pagination(tmp_path: Path):
    copy_web_modules(tmp_path)
    for name in ("frontend_execution_scale.mjs", "frontend_workbench_dom.mjs"):
        shutil.copyfile(Path(__file__).with_name(name), tmp_path / name)
    result = subprocess.run(["node", "frontend_execution_scale.mjs"], cwd=tmp_path,
                            capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["bounded_rows"] == 20
