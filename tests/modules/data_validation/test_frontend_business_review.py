from pathlib import Path
import shutil
import subprocess

import pytest

from tests.modules.data_validation.test_frontend_preview_questions_behavior import copy_web_modules


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_workbench_confirms_all_candidate_scopes_before_compiling(tmp_path: Path):
    copy_web_modules(tmp_path)
    for name in ("frontend_workbench_dom.mjs", "frontend_business_review.mjs"):
        shutil.copyfile(Path(__file__).with_name(name), tmp_path / name)
    result = subprocess.run(["node", "frontend_business_review.mjs"], cwd=tmp_path,
                            capture_output=True, encoding="utf-8", errors="replace", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
