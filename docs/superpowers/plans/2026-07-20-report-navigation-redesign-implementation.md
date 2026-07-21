# Report Navigation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** Rebuild the report-navigation page as the approved restrained 1+3 statistics layout, read-only seven-process panorama, selectable step details, and flat attention list without changing any existing snapshot, dependency, refresh, schedule, or statistics judgment logic.

**Architecture:** Keep `/api/report-navigation/dashboard` and its `period` query unchanged. Render `report_month` as a read-only scope next to the page title, visually separate the monthly report card from the three period-driven support cards, and derive the panorama/detail views entirely from the existing `processes[]` and `steps[]` snapshot. The horizontal spine is a batch-completion indicator: it receives the theme-colored completed state only when every applicable process is completed.

**Tech Stack:** Existing static HTML, vanilla JavaScript, scoped CSS, pytest static-structure tests.

**Implementation status:** Completed. The final reference is `C:\Users\jsitc\Desktop\监管智核-报送导航设计稿.html`; the approved refinements rename the right group to `任务统计`, rename the `data_governance` display label to `数据治理`, retain the four original icon colors, and place specific steps on the right at widths of `1400px` and above.

## Global Constraints

- Preserve backend judgment rules, process dependencies, quarterly `five_articles` filtering, refresh/cooldown behavior, card-maintenance APIs, and statistics-period query values.
- The report month is display-only and comes from `payload.report_month`; do not add a new month-selection API or historical-query behavior.
- The flow panorama exposes only `已完成` and `进行中`; no workflow action or manual-completion control appears in the panorama or detail area.
- Reuse `--ui-radius`, `--theme-accent`, `--theme-accent-readable`, current surface tokens, and semantic success/error colors without adding or restoring an appearance-mode selector.
- Preserve unrelated workspace changes and untracked files.

---

### Task 1: Lock the approved structure and behavior in static tests — completed

**Files:**
- Modify: `tests/test_web_static.py`

**Step 1: Replace obsolete fishbone/action assertions with failing structure assertions**

Assert that the report-navigation section contains:

```python
assert body.index('class="report-nav-page-title"') < body.index('id="reportNavMonth"')
assert 'id="reportNavMonthlyStat"' in body
assert 'id="reportNavPeriodStats"' in body
assert 'id="reportNavProcessDetails"' in body
assert 'class="report-nav-flow-legend"' in body
assert "立即处理" not in body and "查看</button>" not in body
```

Assert that JavaScript:

```python
assert 'function renderReportNavigationProcessDetails(process)' in app_js
assert 'data-report-nav-process=' in app_js
assert 'aria-pressed=' in app_js
assert 'data-manual-action' not in flow_renderer.group("body")
assert 'reportNavFishbone?.classList.toggle("all-done", allProcessesCompleted)' in app_js
assert '--report-nav-spine-progress' not in app_js
```

Keep assertions for the existing dashboard endpoint, `period` values, refresh/cooldown behavior, governance-card maintenance, and quarterly-process filtering.

**Step 2: Add failing theme/radius and responsive assertions**

Require the new groups, process cards, detail list, gray incomplete spine, `all-done` theme spine, `var(--ui-radius)`, and narrow-screen vertical timeline selectors.

**Step 3: Run focused tests and confirm RED**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "report_navigation"
```

Expected: failures for the new IDs, read-only renderer, all-or-nothing spine, and redesigned CSS.

---

### Task 2: Rebuild page markup and read-only rendering — completed

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Test: `tests/test_web_static.py`

**Step 1: Implement the title/month and 1+3 statistics structure**

- Place `报送月份` and `<span id="reportNavMonth">--</span>` immediately after the page title.
- Keep last update and manual refresh at the right edge.
- Render `report_forms` into `#reportNavMonthlyStat`.
- Render `supplement_tasks`, `data_governance`, and `special_governance` into `#reportNavPeriodStats` under the unchanged `#reportNavPeriodSelect`.
- Keep admin maintenance interactions on the two maintainable statistics cards by delegating from a shared stats wrapper.

**Step 2: Implement all-or-nothing panorama rendering**

- Keep the current applicable-process filter.
- Render seven alternating process cards from the existing snapshot with exactly: status icon/name/count, deadline, and completed time or `进行中`.
- Use a retained selected process code, defaulting to the first process containing an error, then the first in-progress process, then the first process.
- Toggle `.all-done` only when all applicable processes have `status === "completed"`; do not compute or set partial spine progress.

**Step 3: Implement selectable read-only details**

- Render existing `steps[]` as ordered read-only rows with semantic completed/current/error/pending state and snapshot messages/timestamps.
- Handle mouse click and Enter/Space on `[data-report-nav-process]` to update selection and details only.
- Remove the visible schedule editor and manual step-completion listeners from this page while leaving backend endpoints and judgment code untouched.

**Step 4: Run focused tests and confirm the behavior assertions pass**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "report_navigation"
```

---

### Task 3: Apply the approved visual system and responsive layout — completed

**Files:**
- Modify: `src/auto_check/web/styles.css`
- Test: `tests/test_web_static.py`

**Step 1: Add the restrained 1+3 statistics styling**

- Use two visual groups without heavy nested chrome: a monthly card column and a three-card period grid.
- Keep surfaces quiet, use minimal elevation, and keep semantic card icons distinct without neon or glow.

**Step 2: Restyle panorama and details**

- Use a neutral horizontal spine by default.
- Apply `var(--theme-accent)`/theme gradient to the entire spine, nodes, and end pill only under `.all-done`.
- Style completed card indicators green and selected cards with theme-colored border/focus.
- Use a compact ordered step list below the timeline on regular desktops and to the right of the timeline at widths of `1400px` and above; remove operation affordances.

**Step 3: Restyle attention rows and responsive states**

- Keep only the three existing records and chips, remove action-button spacing, and use flat bordered rows.
- At narrow widths, switch the flow to a vertical ordered timeline without changing selection semantics.
- Use only the current unified interface tokens and the saved user radius.

**Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "report_navigation or interface_radius"
```

---

### Task 4: Synchronize documentation and verify the repository — completed

**Files:**
- Modify: `docs/superpowers/specs/2026-07-20-report-navigation-readonly-progress-design.md`
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Step 1: Update approved design documentation**

- Document that `报送月份` sits after the page title and scopes the first card plus the seven-process flow.
- Document that `统计周期` scopes only the last three cards.
- Remove prototype-only wording from the formal implementation acceptance section where no longer applicable.

**Step 2: Update visible-change records**

- Add a detailed README note for the new read-only navigation, time-scope split, all-complete spine, and step-detail interaction.
- Keep the current in-app changelog wording at the required concise entry: `系统优化及BUG修复。`

**Step 3: Run full verification**

Run:

```powershell
python -m pytest -q
git diff --check
git status --short
```

Expected: all tests pass; no real whitespace errors; only intended tracked files plus the user's pre-existing untracked files are present.
