from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "data_validation" / "web"


def read(*parts: str) -> str:
    return WEB.joinpath(*parts).read_text(encoding="utf-8")


def test_analysis_waiting_contract_is_real_not_fake_steps() -> None:
    api = read("api.js")
    workbench = read("pages", "workbench.js")
    styles = read("styles.css")

    # 真实 API 合同，保留 parse 仅作兼容。
    assert "createAnalysis" in api and "/ai/analyses" in api
    assert "getAnalysis" in api and "cancelAnalysis" in api
    assert 'request(`/ai/analyses/${encodeURIComponent(analysisId)}`' in api
    assert 'body("DELETE", {}, options)' in api
    assert "parse:" in api, "旧 parse 仅保留兼容，不得静默 fallback 假步骤"

    # 步骤合同与固定三步文案。
    for label in ("解析业务语义与逻辑", "检索数据字典与表结构说明", "生成校验规则与 SQL 预览"):
        assert label in workbench
    for step_id in ("semantics", "metadata", "generation"):
        assert step_id in workbench
    assert "ANALYSIS_POLL_MS = 900" in workbench
    assert "api.createAnalysis" in workbench and "api.getAnalysis" in workbench and "api.cancelAnalysis" in workbench
    assert "startAnalysisPolling" in workbench and "cancelWaiting" in workbench
    assert "stopAnalysisPolling" in workbench
    assert 'steps.find((step) => step.status === "running")' in workbench
    assert "current.table_name" in workbench and "current.field_count" in workbench
    assert "dv-ai-steps" not in workbench and "dv-ai-step-index" not in styles
    assert 'role: "progressbar"' in workbench and "aria-valuenow" not in workbench
    assert 'classList.toggle("is-ai-waiting", work.aiLoading)' in workbench
    assert "取消等待" in workbench
    assert "已取消等待" in workbench
    assert 'footerButton.textContent = work.detail ? "关闭" : "取消"' in workbench
    assert 'footerButton.setAttribute("aria-label", work.aiLoading ? "取消等待"' in workbench
    assert 'aiIcon("star")' in workbench and 'text: "READ-ONLY"' in workbench
    assert "page.form.groups.aiContext.hidden = work.aiLoading" in workbench
    assert "page.waitRequest.hidden = !work.aiLoading" in workbench

    # 不引入百分比假进度、CDN 或字体。
    assert "progress" not in workbench.lower() or "%" not in workbench
    assert "http://" not in styles and "https://" not in styles and "@import" not in styles
    for token in (
        "is-ai-waiting", "dv-ai-wait-body", "dv-ai-wait-mark", "dv-ai-wait-title", "dv-ai-wait-timer",
        "dv-ai-wait-request-meta", "dv-ai-wait-chip", "dv-ai-wait-readonly", "dv-ai-wait-track", "dv-ai-wait-stage",
    ):
        assert token in styles
    assert "dv-ai-wait-request-label" in styles and "dv-ai-wait-value" in styles
    for var in ("--ui-radius", "--ui-panel-surface", "--ui-subsection-surface", "--ui-content-border"):
        assert var in styles
