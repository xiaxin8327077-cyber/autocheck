from pathlib import Path
import shutil
import subprocess

import pytest

from tests.modules.data_validation.test_frontend_preview_questions_behavior import copy_web_modules


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_rule_form_preserves_semantic_definition_across_candidates_and_saved_edits(tmp_path: Path):
    copy_web_modules(tmp_path)
    script = Path(__file__).with_name("frontend_semantic_definition.mjs")
    shutil.copyfile(script, tmp_path / script.name)
    result = subprocess.run(["node", script.name], cwd=tmp_path, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
