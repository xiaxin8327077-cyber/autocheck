# Report Navigation Period and Schedule Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the report-navigation period selector and reporting schedule cards to the approved design-draft styling, with the schedule card group centered across the flow header.

**Architecture:** Keep the existing page DOM and scoped `report-nav-*` component system. Replace only the period chevron markup and the CSS for the two approved surfaces; use a flow-card-specific three-column grid so the schedule group is centered relative to the whole card without changing the notice-card header. Preserve the existing dark-mode and responsive conventions.

**Approved extension:** The calm (`data-theme="light"`) theme shows a standard 20px “报送导航” page title at the left of the period row. The vitality (`data-theme="space-tech"`) theme hides that title and retains the right-aligned period controls.

**Tech Stack:** Static HTML, scoped CSS, Python `pytest` static-structure tests, PyInstaller Windows packaging script.

---

## File map

- `tests/test_web_static.py`: locks the reference-derived HTML/CSS contracts before implementation.
- `src/auto_check/web/index.html`: replaces the period text glyph with the design draft's chevron SVG; reporting dates and labels remain unchanged.
- `src/auto_check/web/styles.css`: restores period styling, warm schedule-card styling, exact centering, dark mode, and narrow-screen fallback.
- `README.md`: records the visible behavior in the current-feature and v2.1 change sections.
- `src/auto_check/web/app.js`: keeps the existing concise v2.1 entry `系统优化及BUG修复。`; no duplicate UI-fix bullet is added.
- `dist/auto-check.exe`: refreshed delivery artifact after tests pass and running instances are stopped.

### Task 0: Add the theme-specific report-navigation title

**Files:**
- Modify: `tests/test_web_static.py`
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/styles.css`

- [x] **Step 1: Add and run a failing static test requiring the title in the period row, 20px/700 typography, vitality-theme hiding, and dark-mode color compatibility.**
- [x] **Step 2: Add `<h2 class="report-nav-page-title">报送导航</h2>` as the first child of `.report-nav-period-bar`.**
- [x] **Step 3: Style the title with `margin: 0 auto 0 0`, `font-size: 20px`, and `font-weight: 700`; hide it only under `[data-theme="space-tech"]`.**
- [x] **Step 4: Run the focused test and confirm it passes.**

### Task 1: Add failing visual-contract tests

**Files:**
- Modify: `tests/test_web_static.py:735`

- [ ] **Step 1: Add a focused failing test after `test_report_navigation_page_styles_are_scoped_responsive_and_dark_compatible`**

```python
def test_report_navigation_period_and_schedule_match_design_draft():
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)

    assert '<svg class="report-nav-period-chevron"' in html
    assert '<span aria-hidden="true">&#9662;</span>' not in html

    period_bar = re.search(
        r"#page-report-navigation \.report-nav-period-bar\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert period_bar is not None
    period_body = period_bar.group("body")
    assert "gap: 12px;" in period_body
    assert "padding: 4px 2px 0;" in period_body
    for obsolete in ["min-height:", "border:", "background:", "box-shadow:", "backdrop-filter:"]:
        assert obsolete not in period_body

    assert "#page-report-navigation .report-nav-period-label::before" in css
    assert "background: rgba(59, 130, 246, 0.10);" in css
    assert "padding: 8px 34px 8px 14px;" in css

    flow_head = re.search(
        r"#page-report-navigation \.report-nav-flow-card > \.report-nav-card-head\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert flow_head is not None
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);" in flow_head.group("body")

    batches = re.search(
        r"#page-report-navigation \.report-nav-batches\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert batches is not None
    assert "grid-column: 2;" in batches.group("body")
    assert "justify-self: center;" in batches.group("body")
    assert "gap: 12px;" in batches.group("body")

    batch = re.search(
        r"#page-report-navigation \.report-nav-batch\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert batch is not None
    batch_body = batch.group("body")
    assert "align-items: flex-start;" in batch_body
    assert "padding: 10px 14px;" in batch_body
    assert "min-width: 250px;" in batch_body
    assert "rgba(255, 165, 0, 0.32)" in batch_body
    assert "rgba(255, 215, 0, 0.10)" in batch_body

    assert "linear-gradient(135deg, #FFD700 0%, #FFA500 100%)" in css
    assert '[data-color-mode="dark"] #page-report-navigation .report-nav-period-select select' in css
    assert '[data-color-mode="dark"] #page-report-navigation .report-nav-batch' in css
```

- [ ] **Step 2: Run the focused test and confirm it fails for the current simplified styles**

Run:

```powershell
python -m pytest tests/test_web_static.py::test_report_navigation_period_and_schedule_match_design_draft -q
```

Expected: FAIL because the current HTML uses the text glyph and the current CSS still contains the full-width period card and blue-gray compact schedule cards.

- [ ] **Step 3: Commit the red test when repository index permissions allow it**

```powershell
git add tests/test_web_static.py
git commit -m "test: lock report navigation timing styles"
```

Expected: one test-only commit. If the worktree index remains read-only, leave the focused change uncommitted and continue without staging unrelated files.

### Task 2: Restore the period selector and centered schedule cards

**Files:**
- Modify: `src/auto_check/web/index.html:131-142`
- Modify: `src/auto_check/web/styles.css:1438-1484`
- Modify: `src/auto_check/web/styles.css:1643-1697`
- Modify: `src/auto_check/web/styles.css:2017-2056`

- [ ] **Step 1: Replace the period text chevron with the design-draft SVG**

Replace the existing `span` in `.report-nav-period-select` with:

```html
<svg class="report-nav-period-chevron" aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
  <polyline points="6 9 12 15 18 9"></polyline>
</svg>
```

- [ ] **Step 2: Replace the period rules with the scoped design-draft values**

```css
#page-report-navigation .report-nav-period-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 4px 2px 0;
}

#page-report-navigation .report-nav-period-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--report-nav-blue);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

#page-report-navigation .report-nav-period-label::before {
  width: 20px;
  height: 2px;
  border-radius: 2px;
  background: var(--space-gradient-primary, linear-gradient(135deg, #3b82f6, #06b6d4, #8b5cf6));
  content: "";
}

#page-report-navigation .report-nav-period-select {
  position: relative;
  display: inline-flex;
  align-items: center;
}

#page-report-navigation .report-nav-period-select select {
  padding: 8px 34px 8px 14px;
  border: 1px solid rgba(59, 130, 246, 0.28);
  border-radius: 10px;
  outline: none;
  color: var(--report-nav-blue);
  background: rgba(59, 130, 246, 0.10);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  appearance: none;
  transition: all 0.2s ease;
}

#page-report-navigation .report-nav-period-select select:hover {
  border-color: rgba(59, 130, 246, 0.42);
  background: rgba(59, 130, 246, 0.16);
}

#page-report-navigation .report-nav-period-select select:focus {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.18);
}

#page-report-navigation .report-nav-period-chevron {
  position: absolute;
  right: 12px;
  color: var(--report-nav-blue);
  pointer-events: none;
}
```

- [ ] **Step 3: Add a flow-card-only centered header grid and restore the schedule-card geometry**

```css
#page-report-navigation .report-nav-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 20px;
}

#page-report-navigation .report-nav-flow-card > .report-nav-card-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
}

#page-report-navigation .report-nav-flow-card > .report-nav-card-head h2 {
  grid-column: 1;
  justify-self: start;
}

#page-report-navigation .report-nav-batches {
  display: flex;
  grid-column: 2;
  justify-self: center;
  justify-content: center;
  gap: 12px;
}

#page-report-navigation .report-nav-batch {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 250px;
  padding: 10px 14px;
  border: 1px solid rgba(255, 165, 0, 0.32);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(255, 215, 0, 0.10), rgba(255, 165, 0, 0.06));
  text-align: left;
}

#page-report-navigation .report-nav-batch > strong {
  flex: 0 0 auto;
  padding: 7px 11px;
  border-radius: 10px;
  color: #7c2d12;
  background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
  box-shadow: 0 4px 10px rgba(245, 158, 11, 0.35);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.06em;
}

#page-report-navigation .report-nav-batch p {
  margin: 0;
  color: var(--on-surface-variant);
  font-size: 12.5px;
  line-height: 1.65;
  text-align: left;
}

#page-report-navigation .report-nav-batch p b {
  color: var(--on-surface);
  font-weight: 600;
}

#page-report-navigation .report-nav-batch time {
  color: var(--report-nav-blue);
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  font-weight: 400;
}
```

- [ ] **Step 4: Split the dark-mode rules so the period bar stays transparent and schedule cards stay warm**

Remove `.report-nav-period-bar` from the shared dark card selector. Remove `.report-nav-batch` from the shared dark todo selector, then add:

```css
[data-color-mode="dark"] #page-report-navigation .report-nav-period-select select {
  border-color: rgba(56, 189, 248, 0.34);
  color: #93c5fd;
  background: rgba(56, 189, 248, 0.14);
}

[data-color-mode="dark"] #page-report-navigation .report-nav-period-chevron {
  color: #93c5fd;
}

[data-color-mode="dark"] #page-report-navigation .report-nav-batch {
  border-color: rgba(255, 165, 0, 0.28);
  background: linear-gradient(135deg, rgba(255, 215, 0, 0.06), rgba(255, 165, 0, 0.04));
}
```

- [ ] **Step 5: Add the narrow-screen grid fallback without affecting the notice-card header**

Inside `@media (max-width: 1100px)`, replace the flow-header behavior with:

```css
#page-report-navigation .report-nav-card-head { flex-direction: column; }
#page-report-navigation .report-nav-flow-card > .report-nav-card-head {
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
}
#page-report-navigation .report-nav-flow-card > .report-nav-card-head h2,
#page-report-navigation .report-nav-batches { grid-column: 1; }
#page-report-navigation .report-nav-batches {
  width: 100%;
  justify-self: start;
  justify-content: flex-start;
  flex-wrap: wrap;
}
```

- [ ] **Step 6: Run the focused test and the surrounding report-navigation tests**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "report_navigation"
```

Expected: all selected report-navigation tests PASS.

- [ ] **Step 7: Commit the implementation when repository index permissions allow it**

```powershell
git add src/auto_check/web/index.html src/auto_check/web/styles.css tests/test_web_static.py
git commit -m "fix: match report navigation timing design"
```

Expected: one focused implementation commit, or an unchanged working tree index if repository permissions still block commits.

### Task 3: Update documentation and verify the delivery

**Files:**
- Modify: `README.md:17`
- Modify: `README.md:317`
- Verify: `src/auto_check/web/app.js:9524-9535`
- Verify: `tests/test_web_static.py`
- Refresh: `dist/auto-check.exe`

- [ ] **Step 1: Update the current-feature description**

Change the report-navigation bullet to:

```markdown
- 报送导航：作为系统默认页面，按设计稿展示统计周期、报送报表、补录任务、数据治理流程、报表特殊治理、报送流程进度和注意事项；统计周期采用精简选择条，报送时间使用暖黄色卡片并在流程标题栏中整体居中，同时兼容浅色与暗色模式。
```

- [ ] **Step 2: Add a detailed v2.1 change bullet after the existing report-navigation bullet**

```markdown
- 还原报送导航顶部统计周期选择条和报送流程时间卡片的设计稿样式，人行、金监报送时间卡片组改为相对流程卡片整体居中，卡片内部文字保持左对齐，并补充暗色与窄屏适配。
```

- [ ] **Step 3: Verify the concise in-app changelog remains compliant**

Run:

```powershell
rg -n -A 12 'changelog-version">v2\.1' src\auto_check\web\app.js
```

Expected: the v2.1 block contains exactly one generic UI-fix entry `系统优化及BUG修复。`; do not add detailed visual-fix text to `app.js`.

- [ ] **Step 4: Run the complete test suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests PASS with zero failures.

- [ ] **Step 5: Check whitespace and the focused diff**

Run:

```powershell
git diff --check
git diff -- src/auto_check/web/index.html src/auto_check/web/styles.css tests/test_web_static.py README.md
```

Expected: no actual whitespace errors; diff contains only the approved period/schedule styling, tests, and documentation plus the previously approved report-navigation work already present in the dirty branch.

- [ ] **Step 6: Visually compare both themes**

At a desktop viewport close to the supplied screenshots, verify:

- the period row has no full-width white card;
- the period label has the blue gradient dash and the selector has the blue translucent treatment;
- the two warm schedule cards are centered as one group relative to the full flow card;
- schedule-card text remains left aligned;
- dark mode retains readable blue dates and warm card borders;
- at widths below 1100 px the schedule cards wrap beneath the title without horizontal overflow.

Expected: no visible mismatch remains in the two approved surfaces. If authenticated browser access is unavailable, compare against a fresh screenshot from the running application before declaring visual QA complete.

- [ ] **Step 7: Stop running packaged instances before rebuilding**

Run:

```powershell
Get-Process -Name auto-check -ErrorAction SilentlyContinue | Stop-Process -Force
```

Expected: no `auto-check.exe` process remains and `dist\auto-check.exe` is no longer locked.

- [ ] **Step 8: Rebuild the Windows executable without rerunning the already-passing suite**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1 -SkipTests
```

Expected: successful package completion and a refreshed `dist\auto-check.exe`.

- [ ] **Step 9: Verify the packaged artifact**

Run:

```powershell
Get-Item dist\auto-check.exe | Select-Object FullName,Length,LastWriteTime
Get-FileHash dist\auto-check.exe -Algorithm SHA256
Get-Process -Name auto-check -ErrorAction SilentlyContinue
```

Expected: the executable has a new modification time and SHA256 hash, and no packaged instance is left running.

- [ ] **Step 10: Commit documentation when repository index permissions allow it**

```powershell
git add README.md
git commit -m "docs: describe report navigation timing layout"
```

Expected: one documentation commit, or no staging changes if the worktree index remains read-only.
