# Report Navigation and Multilevel Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a default “报送导航” page and group the existing reconciliation overview, execution, and history pages under a responsive “智能核数” multilevel menu.

**Architecture:** Keep the existing hash-driven page model and preserve the existing `home`, `auto-check`, and `history` page identifiers. Add one new `report-navigation` page, shared menu-state helpers in `app.js`, and theme-scoped CSS for sidebar/top-nav hierarchy plus design-draft content.

**Tech Stack:** Static HTML, CSS, vanilla JavaScript, pytest static-structure tests, existing PowerShell packaging script.

---

### Task 1: Specify the navigation hierarchy and default route

**Files:**
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: Write failing static tests**

Add assertions that `index.html` contains a “报送导航” top-level entry, two “智能核数” group triggers, three child entries using existing page IDs, renamed visible labels, and `page-report-navigation`. Assert that the initialization fallback calls `switchPage("report-navigation")`, while `#home` remains valid.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_web_static.py -q -k "report_navigation or multilevel_navigation"`

Expected: failures because the new page, hierarchy, and default route do not exist.

### Task 2: Implement multilevel navigation behavior

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`

- [ ] **Step 1: Add semantic grouped navigation markup**

Add a sidebar group and a top-nav dropdown group. Use buttons with `data-nav-group="smart-reconcile"`, `aria-expanded`, and child links retaining `data-page="home"`, `data-page="auto-check"`, and `data-page="history"`.

- [ ] **Step 2: Add minimal group-state logic**

Extend `syncNavState(name)` so the group is active for the three child routes. Add click handlers for group toggles, outside-click closing for the top dropdown, and Escape closing. Change unauthorized users and initial fallback routing to `report-navigation`.

- [ ] **Step 3: Add theme-compatible hierarchy styles**

Style sidebar child indentation/expand state and the top-nav dropdown, including hover, focus-visible, active, space-tech light/dark, and the existing sidebar dark theme.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_web_static.py -q -k "report_navigation or multilevel_navigation or top_navigation"`

Expected: navigation tests pass.

### Task 3: Specify and implement the report navigation page

**Files:**
- Modify: `tests/test_web_static.py`
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/styles.css`

- [ ] **Step 1: Write failing page-structure and style tests**

Assert that `page-report-navigation` includes the period selector, four summary cards, report-flow fishbone, seven report branches, batch deadlines, three attention items, scoped CSS selectors, responsive rules, and dark-mode selectors.

- [ ] **Step 2: Run the page tests and verify RED**

Run: `python -m pytest tests/test_web_static.py -q -k "report_navigation_page"`

Expected: failures because the design-draft content is absent.

- [ ] **Step 3: Transplant the design-draft body into the app shell**

Copy the design content into `page-report-navigation`, excluding the standalone header, brand, theme toggle, script, and footer. Rename generic design classes with a `report-nav-` prefix where they overlap project-wide classes.

- [ ] **Step 4: Transplant and scope the design CSS**

Move the relevant period, stat card, fishbone, branch, batch, and attention-list styles into `styles.css` under `#page-report-navigation`. Preserve the draft’s light/dark palette and add responsive overflow handling so the seven-branch fishbone stays usable on narrower layouts.

- [ ] **Step 5: Run the page tests and verify GREEN**

Run: `python -m pytest tests/test_web_static.py -q -k "report_navigation_page"`

Expected: page structure and style tests pass.

### Task 4: Update visible text, help, release notes, and README

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `README.md`
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: Add failing documentation and changelog assertions**

Assert README documents the new default page and hierarchy, and the current in-app changelog includes the concrete new functions “报送导航” and “智能核数多级菜单”.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_web_static.py -q -k "report_navigation_docs"`

Expected: failures because documentation has not been updated.

- [ ] **Step 3: Update user-facing copy**

Rename page headings/help text to “对数总览”“对数执行”“对数历史”. Add detailed README release notes and concise feature entries to the existing current-version application changelog. Do not change `DEFAULT_VERSION`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_web_static.py -q -k "report_navigation_docs"`

Expected: documentation tests pass.

### Task 5: Full verification and application packaging

**Files:**
- Verify: all modified files
- Generate: `dist/auto-check.exe`

- [ ] **Step 1: Run the complete test suite**

Run: `python -m pytest -q`

Expected: exit code 0 with no failed tests.

- [ ] **Step 2: Check the diff and whitespace**

Run: `git diff --check`

Expected: no actual whitespace errors.

- [ ] **Step 3: Confirm the executable is not running**

Run: `Get-Process auto-check -ErrorAction SilentlyContinue`

Expected: no process holding `dist/auto-check.exe`; if found, stop and report the packaging blocker instead of terminating it without approval.

- [ ] **Step 4: Refresh the Windows package**

Run: `powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1`

Expected: exit code 0 and refreshed `dist/auto-check.exe`.

- [ ] **Step 5: Re-run targeted static tests after packaging**

Run: `python -m pytest tests/test_web_static.py -q`

Expected: exit code 0.
