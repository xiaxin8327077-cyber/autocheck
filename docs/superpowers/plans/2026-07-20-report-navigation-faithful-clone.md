# Report Navigation Faithful Clone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faithfully reproduce `C:\Users\jsitc\Desktop\监管智核-报送导航设计稿.html` in the existing report-navigation page while preserving the current API and business judgment logic.

**Architecture:** Keep the existing HTML/JavaScript data flow and add a page-scoped visual layer matching the reference. Process details stay read-only and collapsed initially; card selection toggles the details panel, which becomes a right column at wide breakpoints and a lower panel at narrow breakpoints.

**Tech Stack:** Static HTML, CSS, vanilla JavaScript, pytest static-contract tests, in-app browser visual QA.

## Global Constraints

- The desktop HTML and the supplied screenshot are the only visual source of truth.
- All visible radii use `var(--ui-radius)` and continue to follow the system setting.
- Keep the existing fixed Logo blue gradient and semantic status colors.
- Preserve all API calls, report-month/stat-period scope, completion calculations, process filtering, and all-done spine logic.
- Do not restore dark mode, calm mode, or appearance switches.
- Process details are read-only and appear only after a process-card click.
- At `min-width: 1400px`, expanded details appear on the right; below that breakpoint they appear below the timeline.
- Do not package `dist\auto-check.exe` unless explicitly requested.

---

### Task 1: Lock the interaction contract

**Files:**
- Modify: `tests/test_web_static.py`
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`

**Interfaces:**
- Consumes: existing `reportNavigationVisibleProcesses` and process-card event delegation.
- Produces: `has-selection` state on `.report-nav-flow-card` and the `hidden` state on `#reportNavProcessDetails`.

- [ ] Add failing assertions for default hidden details, no automatic first-card selection, click-to-toggle selection, and responsive expansion state.
- [ ] Run the focused static test and confirm it fails for the current automatic-selection behavior.
- [ ] Implement the minimal selection toggle without changing dashboard payload handling.
- [ ] Re-run the focused test and confirm it passes.

### Task 2: Reproduce the visual hierarchy

**Files:**
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: the current report-navigation DOM and existing theme/radius tokens.
- Produces: reference-matched title row, 1+3 statistics grouping, timeline geometry, process cards, detail panel, and attention rows.

- [ ] Add failing CSS contract assertions for the measured reference proportions and `var(--ui-radius)` usage.
- [ ] Run the focused static test and confirm the visual contract fails.
- [ ] Replace the current wide-screen overrides with page-scoped reference values.
- [ ] Add `.has-selection`-scoped right-column rules at `min-width: 1400px` and keep the base detail flow below the timeline.
- [ ] Re-run the focused static test and confirm it passes.

### Task 3: Visual comparison and regression verification

**Files:**
- Modify: `design-qa.md`
- Create: `docs/design-qa/report-navigation-faithful-clone.png`
- Modify: `README.md`

**Interfaces:**
- Consumes: the reference HTML/screenshot and the local app with realistic dashboard data.
- Produces: accepted browser screenshot and a `design-qa.md` result.

- [ ] Capture the reference and implementation at the same desktop viewport and state.
- [ ] Compare full-page and focused process-region evidence together; fix every P0/P1/P2 mismatch.
- [ ] Verify default collapsed state, wide right expansion, narrow lower expansion, card switching, card collapse, period switching, and console cleanliness.
- [ ] Update README with the final visible behavior; keep the in-app changelog at its existing concise optimization entry.
- [ ] Run `python -m pytest -q tests/test_web_static.py`, then the full `python -m pytest -q`, and finally `git diff --check`.
- [ ] Record the final evidence and set `final result: passed` only when no P0/P1/P2 mismatch remains.

