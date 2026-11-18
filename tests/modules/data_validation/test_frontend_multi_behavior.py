from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "data_validation" / "web"
SCENARIO = Path(__file__).with_name("frontend_multi_behavior.mjs")


def copy_web_modules(tmp_path: Path) -> None:
    for source in WEB.rglob("*.js"):
        target = tmp_path / source.relative_to(WEB)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = target.with_suffix(".mjs")
        content = source.read_text(encoding="utf-8").replace('.js"', '.mjs"').replace(".js'", ".mjs'")
        target.write_text(content, encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用，跳过前端行为测试；静态测试仍执行")
def test_frontend_multi_candidate_selection_and_batch_save(tmp_path: Path) -> None:
    copy_web_modules(tmp_path)
    scenario = tmp_path / "frontend_multi_behavior.mjs"
    scenario.write_text(SCENARIO.read_text(encoding="utf-8"), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(scenario)], cwd=tmp_path, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert json.loads(completed.stdout.strip())["ok"] is True
    payload = json.loads(completed.stdout.strip())
    batch = payload["batch_payload"]
    assert isinstance(batch["request_key"], str) and batch["request_key"]
    assert len(batch["definitions"]) == 2
    for definition in batch["definitions"]:
        assert definition["rule_type"] == "field_compare"
        assert definition["expression"]["right_type"] in ("value", "field")
        if definition["expression"]["right_type"] == "value":
            assert definition["expression"]["right"] == 0
        else:
            assert definition["expression"]["right"] == "f_balan_endp_amt"
        assert "preview" not in definition and "columns" not in definition
        assert definition["project_context"]["mode"] == "base"
        assert definition["project_context"]["code_field"] == "project_code"
        assert definition["project_context"]["confirmed"] is True
        assert definition["null_policy"] in ("zero", "skip")
    assert batch["definitions"][0]["null_policy"] == "zero"
    assert batch["definitions"][0]["expression"]["right"] == "f_balan_endp_amt"
    assert batch["definitions"][1]["null_policy"] == "zero"
    assert batch["definitions"][1]["expression"]["right"] == 0
