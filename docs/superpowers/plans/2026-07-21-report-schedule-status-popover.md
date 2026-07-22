# Report Schedule Status Popover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ineffective schedule “查看步骤” tooltip with the local prototype’s 04 status-panel hover behavior.

**Architecture:** Keep the trigger and panel inside one wrapper. JavaScript controls a single `.open` state with a 120ms show delay and 140ms hide grace period; CSS supplies a transparent bridge, left-opening panel, status dots, and the subtle running pulse.

**Tech Stack:** Vanilla JavaScript, HTML template strings, CSS, pytest static assertions.

## Global Constraints

- Keep “查看步骤” hover-only; do not add click navigation.
- Preserve the existing theme variables and system radius.
- Run only the focused static test plus lightweight syntax/diff checks; do not package.

---

### Task 1: Lock the hover contract

**Files:**
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: existing report schedule static test.
- Produces: assertions for `openReportNavigationScheduleStepsPreview`, `closeReportNavigationScheduleStepsPreview`, status classes, four delegated events, transparent bridge, and `.open` CSS state.

- [ ] **Step 1: Replace the old fixed-position and CSS-only hover assertions.**
- [ ] **Step 2: Run `python -m pytest -q tests/test_web_static.py::test_report_navigation_schedule_timeline_expands_with_hover_step_preview` and confirm it fails against the old implementation.**

### Task 2: Implement the 04 status panel

**Files:**
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`

**Interfaces:**
- Consumes: process step status and the schedule table’s delegated events.
- Produces: numbered rows classified as `completed`, `running`, or `waiting`; delayed open/close helpers; a left-opening interactive panel.

- [ ] **Step 1: Classify the first incomplete step as running and remaining incomplete steps as waiting.**
- [ ] **Step 2: Replace viewport positioning with 120ms open and 140ms close helpers.**
- [ ] **Step 3: Add pointer-out and focus-out handling so the panel closes smoothly without breaking movement into the panel.**
- [ ] **Step 4: Replace fixed tooltip CSS with the prototype-style open state, bridge, arrow, status dots, and running pulse.**

### Task 3: Document and verify

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the implemented behavior.
- Produces: current user-facing behavior documentation.

- [ ] **Step 1: Document the delayed, move-into-panel 04 status preview.**
- [ ] **Step 2: Run the focused pytest, `node --check src/auto_check/web/app.js`, and `git diff --check`.**
