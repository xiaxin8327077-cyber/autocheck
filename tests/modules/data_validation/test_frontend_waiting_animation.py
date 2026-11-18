"""Scheme A: monotonic elapsed time and an indeterminate activity line."""
from pathlib import Path

WEB = Path(__file__).resolve().parents[3] / "src/auto_check/modules/data_validation/web"


def test_tenths_clock_is_monotonic_and_does_not_rebuild_waiting_ui():
    source = (WEB / "pages/workbench.js").read_text(encoding="utf-8")
    clock = source.split("function startElapsed()", 1)[1].split("function inputSignature()", 1)[0]
    assert "performance.now()" in clock
    assert "renderElapsed();" in clock and "render();" not in clock
    assert clock.count("runtime.setTimer(tick, 100)") == 2
    assert 'page.aiWaitTimer.textContent = work.aiElapsed.toFixed(1)' in source
    assert '"已等待 ", aiWaitTimer, " 秒"' in source


def test_running_line_moves_without_claiming_completion():
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    source = (WEB / "pages/workbench.js").read_text(encoding="utf-8")
    track = css.split(".dv-ai-wait-track::before {", 1)[1].split("}", 1)[0]
    assert "animation: dv-ai-wait-sweep 1.8s ease-in-out infinite !important" in track
    assert "@keyframes dv-ai-wait-sweep { from { transform: translateX(-100%); } to { transform: translateX(250%); } }" in css
    assert "aria-valuenow" not in source
    assert "page.aiWaitBody.hidden = !work.aiLoading" in source


def test_only_the_activity_line_overrides_optional_effects():
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    mark = css.split(".dv-ai-wait-mark {", 1)[1].split("}", 1)[0]
    assert "animation:" not in mark
    assert css.count("animation: dv-ai-wait-sweep") == 1
