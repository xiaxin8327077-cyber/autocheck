from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "data_validation" / "web"
SCENARIO = Path(__file__).with_name("frontend_grounding_behavior.mjs")


def copy_web_modules(tmp_path: Path) -> None:
    for source in WEB.rglob("*.js"):
        target = tmp_path / source.relative_to(WEB)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = target.with_suffix(".mjs")
        content = source.read_text(encoding="utf-8").replace('.js"', '.mjs"').replace(".js'", ".mjs'")
        target.write_text(content, encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用，跳过前端行为测试；静态测试仍执行")
def test_frontend_grounding_filters_join_and_samples(tmp_path: Path) -> None:
    copy_web_modules(tmp_path)
    scenario = tmp_path / "frontend_grounding_behavior.mjs"
    scenario.write_text(SCENARIO.read_text(encoding="utf-8"), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(scenario)], cwd=tmp_path, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=30, check=False,
    )
    assert completed.returncode == 0, f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    payload = json.loads(completed.stdout.strip())
    assert payload["ok"] is True
    # 真实 form.read() JSON 交给 Python 消费者验证嵌套契约（不是前端自测 shape）。
    snapshot = payload["snapshot"]
    assert set(snapshot) >= {"filters", "join", "expression", "related_columns", "report_date_field", "null_policy", "equality_policy"}
    assert "relationship_confirmed" not in snapshot and "unmatched_policy" not in snapshot, "不得输出顶层关系字段"
    join = snapshot["join"]
    assert join["table_name"] == "reg_pub_accountbalance_sum"
    assert join["on"] == [{"left": "c_projcode", "right": "c_projcode"}]
    assert join["report_date_field"] == "d_balancedate"
    assert join["relationship_confirmed"] is True
    assert join["unmatched_policy"] == "exclude"
    assert snapshot["expression"]["right_table"] == "related"
    from auto_check.modules.data_validation.query_spec import query_ready, validate_query_spec
    assert validate_query_spec(snapshot)["join"]["relationship_confirmed"] is True
    assert query_ready(snapshot) is True
    assert snapshot["filters"][0]["confirmed"] is True
    assert snapshot["related_columns"] == [
        {"column_name": "c_projcode", "comment": "项目编号", "data_type": "varchar"},
        {"column_name": "d_balancedate", "comment": "报送日期", "data_type": "date"},
        {"column_name": "f_balan_endp_amt", "comment": "实收信托余额", "data_type": "numeric"},
    ]
    unary = payload["unary"]
    assert unary["expression"] == {"left": "d_startdate", "op": "is_null"}
    assert unary["null_policy"] == "violate"
    assert unary["equality_policy"] == "allow_equal"
