import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .test_frontend_results_behavior import copy_web_modules

TARGET_MAX_TASK_RULES = 100000


def _prepare(tmp_path: Path, max_task_rules: int | None = None) -> None:
    copy_web_modules(tmp_path)
    # 父会话负责把生产 state.js 的 MAX_TASK_RULES 扩大到 100000。临时测试副本
    # 对齐同一资源上限，使本任务的 10000 条批量选择测试不依赖尚未合并的父改动；
    # 不修改仓库中的生产文件。full 场景单独使用小上限验证选满边界。
    state_path = tmp_path / "state.mjs"
    state_text = state_path.read_text(encoding="utf-8")
    match = re.search(r"export const MAX_TASK_RULES = (\d+);", state_text)
    assert match, "state.mjs 缺少 MAX_TASK_RULES"
    target = max_task_rules if max_task_rules is not None else TARGET_MAX_TASK_RULES
    if max_task_rules is not None or int(match.group(1)) < 10000:
        state_text = state_text.replace(
            match.group(0), f"export const MAX_TASK_RULES = {target};",
        )
        state_path.write_text(state_text, encoding="utf-8")
    for name in ("frontend_execution_category.mjs", "frontend_workbench_dom.mjs"):
        shutil.copyfile(Path(__file__).with_name(name), tmp_path / name)


def _run(tmp_path: Path, scenario: str, max_task_rules: int | None = None) -> None:
    _prepare(tmp_path, max_task_rules)
    result = subprocess.run(
        ["node", str(tmp_path / "frontend_execution_category.mjs"), scenario],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["scenario"] == scenario


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_report_category_filter_and_dynamic_refresh(tmp_path: Path) -> None:
    _run(tmp_path, "category")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_select_filtered_large_batch_keeps_page_dom_and_submits_ids(tmp_path: Path) -> None:
    _run(tmp_path, "bulk")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_select_filtered_passes_search_category_and_source_snapshot(tmp_path: Path) -> None:
    _run(tmp_path, "params")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_select_filtered_failure_keeps_existing_selection(tmp_path: Path) -> None:
    _run(tmp_path, "failure")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_select_filtered_ignores_late_response_after_close(tmp_path: Path) -> None:
    _run(tmp_path, "stale-close")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_select_filtered_ignores_late_response_after_filter_change(tmp_path: Path) -> None:
    _run(tmp_path, "stale-filter")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_full_selection_can_be_cleared_without_extra_rows(tmp_path: Path) -> None:
    _run(tmp_path, "full", max_task_rules=25)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_immediate_select_uses_pending_search(tmp_path: Path) -> None:
    _run(tmp_path, "immediate")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_dialog_bulk_scope_and_late_sources(tmp_path: Path) -> None:
    _run(tmp_path, "scope")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 不可用")
def test_execution_new_api_identifies_old_service_without_masking_permissions(tmp_path: Path) -> None:
    _run(tmp_path, "legacy")
