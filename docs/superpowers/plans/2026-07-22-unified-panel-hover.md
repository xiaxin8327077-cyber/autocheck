# Unified Panel Hover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make outer content panels on the report-navigation, reconciliation, history, settings, and user-management pages use one hover border and shadow treatment matching the reconciliation overview.

**Architecture:** Add one final, high-priority grouped CSS rule that includes the overview baseline selectors and every target outer panel selector. Verify the grouped rule structurally so older page-specific glow and border rules cannot become the effective result.

**Tech Stack:** Static HTML/CSS, Python pytest static source assertions.

## Global Constraints

- Hover border is `1px` and uses a light theme-color mix.
- Hover raises the panel by `2px` and uses only a subtle inset highlight.
- Default and hover shadows must not contain any outer drop shadow or `0 0` spreading theme-colored glow.
- Internal buttons, table rows, flow cards, dialogs, and other nested components remain unchanged.
- Do not run the full test suite again; run the focused static test and `git diff --check`.

---

### Task 1: Unify outer panel hover feedback

**Files:**
- Modify: `tests/test_web_static.py`
- Modify: `src/auto_check/web/styles.css`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing page-specific card class names and global theme variables.
- Produces: one grouped CSS hover rule covering all outer content panels.

- [ ] **Step 1: Write the failing static test**

Add a test that extracts the final rule containing these selectors:

```python
selectors = [
    "#page-home .glass-card:hover",
    "#page-home .glass-stat-card:hover",
    "#page-report-navigation .report-nav-stats-layout:hover",
    "#page-report-navigation .report-nav-flow-card:hover",
    "#page-report-navigation .report-nav-schedule-card:hover",
    "#page-report-navigation .report-nav-attention-card:hover",
    "#page-auto-check > .card:hover",
    "#page-history > .card:hover",
    "#page-settings .settings-dashboard-card:hover",
    "#page-users .user-stat-card:hover",
    "#page-users .user-filter-bar:hover",
    "#page-users .user-table-card:hover",
]
for selector in selectors:
    assert selector in css
assert "border-color: color-mix(in srgb, var(--theme-accent) 36%, var(--outline-variant)) !important;" in css
assert "0 4px 24px rgba(15, 23, 42, 0.08)" in css
assert "transform: translateY(-2px) !important;" in css
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "unified_panel_hover"
```

Expected: failure because the shared grouped rule does not exist.

- [ ] **Step 3: Add the final shared CSS rule**

Append a scoped rule after existing page-specific overrides:

```css
#page-home .glass-card:hover,
#page-home .glass-stat-card:hover,
#page-report-navigation .report-nav-stats-layout:hover,
#page-report-navigation .report-nav-flow-card:hover,
#page-report-navigation .report-nav-schedule-card:hover,
#page-report-navigation .report-nav-attention-card:hover,
#page-auto-check > .card:hover,
#page-history > .card:hover,
#page-settings .settings-dashboard-card:hover,
#page-users .user-stat-card:hover,
#page-users .user-filter-bar:hover,
#page-users .user-table-card:hover {
  border-width: 1px !important;
  border-color: color-mix(in srgb, var(--theme-accent) 36%, var(--outline-variant)) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.56) !important;
  transform: translateY(-2px) !important;
}
```

- [ ] **Step 4: Update visible-change documentation**

Update `README.md` to state that all listed pages share the reconciliation-overview outer-panel hover standard and do not use a theme glow.

- [ ] **Step 5: Run focused verification**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "unified_panel_hover or report_navigation_matches_the_selected_desktop_design_proportions"
git diff --check
```

Expected: selected tests pass and `git diff --check` reports no whitespace errors.
