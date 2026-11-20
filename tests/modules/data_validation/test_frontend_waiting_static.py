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
    for label in ("解析业务语义与逻辑", "检索数据字典与表结构说明", "核对校验规则与待确认口径"):
        assert label in workbench
    for step_id in ("semantics", "metadata", "generation"):
        assert step_id in workbench
    assert "ANALYSIS_POLL_MS = 900" in workbench
    assert "api.createAnalysis" in workbench and "api.getAnalysis" in workbench and "api.cancelAnalysis" in workbench
    assert "startAnalysisPolling" in workbench and "cancelWaiting" in workbench
    assert "stopAnalysisPolling" in workbench
    assert 'steps.find((step) => step.status === "running")' in workbench
    assert "current?.table_name" in workbench and "current?.field_count" in workbench
    assert "dv-ai-steps" not in workbench and "dv-ai-step-index" not in styles
    assert 'role: "progressbar"' in workbench and "aria-valuenow" not in workbench
    assert 'classList.toggle("is-ai-waiting", work.aiLoading)' in workbench
    assert "继续等待" in workbench and "结束会话" in workbench
    assert "本次分析会话已结束" in workbench
    assert 'footerButton.setAttribute("aria-label", footerButton.textContent)' in workbench
    assert 'aiIcon("star")' in workbench and 'text: "READ-ONLY"' in workbench
    assert "page.form.groups.aiContext.hidden = work.aiLoading" in workbench
    assert "page.waitRequest.hidden = !work.aiLoading" in workbench

    # 不引入百分比假进度、CDN 或字体。
    assert "progress" not in workbench.lower() or "%" not in workbench
    # 结果页可导入随包发布的专用样式，不依赖 CDN 或远程字体。
    local_styles = styles.replace('@import url("./results-replica.css");', "")
    assert "http://" not in local_styles and "https://" not in local_styles and "@import" not in local_styles
    for token in (
        "is-ai-waiting", "dv-ai-wait-body", "dv-ai-wait-mark", "dv-ai-wait-title", "dv-ai-wait-timer",
        "dv-ai-wait-request-meta", "dv-ai-wait-chip", "dv-ai-wait-readonly", "dv-ai-wait-track", "dv-ai-wait-stage",
    ):
        assert token in styles
    assert "dv-ai-wait-request-label" in styles and "dv-ai-wait-value" in styles
    for var in ("--ui-radius", "--ui-panel-surface", "--ui-subsection-surface", "--ui-content-border"):
        assert var in styles
