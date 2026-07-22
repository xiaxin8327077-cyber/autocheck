# Report Navigation Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive read-only reporting schedule below the fishbone progress card, with timeline status, expandable details, fishbone step linking, administrator deadline editing, and monthly owner maintenance.

**Architecture:** Reuse the current report-navigation dashboard payload and process snapshots. Store the only missing datum, `owner_name`, on each monthly schedule row; expose it through one focused administrator endpoint. Render and calculate all schedule dates, progress, overdue state, and next-step text in the existing frontend without changing collection or evaluator logic.

**Tech Stack:** Python 3.11, SQLAlchemy Core, MySQL, vanilla JavaScript, HTML/CSS, pytest static and service tests.

## Global Constraints

- Place the schedule between “报送流程进度” and “注意事项”.
- Keep the page read-only except for administrator right-click editing of deadline and owner.
- Use existing theme/radius variables; schedule status colors keep completed green, current neutral, pending gray, and overdue/error red.
- Five-articles remains subject to the existing applicable-month filter.
- Expansion and collapse use the same 180ms outer-card height animation and do not depend on the system animation preference.
- Do not add workflow execution or “继续处理”; “查看步骤” only selects and scrolls to the existing fishbone details.
- Run only schedule/report-navigation focused tests and do not package the executable.

---

### Task 1: Monthly owner persistence and API

**Files:**
- Modify: `src/auto_check/app/app_database.py`
- Modify: `src/auto_check/app/storage_report_navigation.py`
- Modify: `src/auto_check/app/report_navigation.py`
- Modify: `src/auto_check/app/server.py`
- Modify: `sql/app_storage/mysql/002_report_navigation.sql`
- Create: `sql/app_storage/mysql/007_report_navigation_schedule_owner.sql`
- Modify: `tests/mysql_config_test_support.py`
- Modify: `tests/test_report_navigation.py`
- Modify: `tests/test_report_navigation_api.py`
- Modify: `tests/test_report_navigation_schema.py`

**Interfaces:**
- Produces: `ScheduleConfig.owner_name: str`.
- Produces: `ReportNavigationStore.update_schedule_owner(report_month, process_code, owner_name, updated_by, now)`.
- Produces: `ReportNavigationService.update_schedule_owner(process_code, report_month, owner_name, current_user)`.
- Produces: `POST /api/report-navigation/schedule-owners/{process_code}` with `{report_month, owner_name}`.
- Extends dashboard process items with `owner_name` and `owner_editable`.

- [ ] **Step 1: Write failing schema, store, service, and route tests**

```python
def test_schedule_owner_is_saved_and_returned_in_dashboard():
    service.update_schedule_owner("east5", "2026-07", "张智核", admin, now=current)
    process = next(item for item in service.dashboard(period="month", current_user=admin, now=current)["processes"] if item["process_code"] == "east5")
    assert process["owner_name"] == "张智核"
    assert process["owner_editable"] is True
```

- [ ] **Step 2: Run focused tests and confirm missing owner behavior fails**

Run: `python -m pytest -q tests/test_report_navigation_schema.py tests/test_report_navigation.py tests/test_report_navigation_api.py -k "schedule_owner"`

Expected: FAIL because the schedule schema, service method, and route do not exist.

- [ ] **Step 3: Add the nullable owner column and preservation rules**

Add `owner_name VARCHAR(128) NULL` to the schedule table definition and an idempotent migration. Date updates preserve the current owner; owner updates preserve the current date and validate administrator role, current/future report month, existing process, maximum 128 characters, and trimmed text.

- [ ] **Step 4: Expose owner data through dashboard and API**

Dashboard payload:

```python
"owner_name": schedule.owner_name if schedule else "",
"owner_editable": is_admin,
```

- [ ] **Step 5: Run the owner-focused tests**

Run: `python -m pytest -q tests/test_report_navigation_schema.py tests/test_report_navigation.py tests/test_report_navigation_api.py -k "schedule_owner"`

Expected: PASS.

### Task 2: Schedule timeline and expandable detail interaction

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: dashboard process fields `report_date`, `owner_name`, `completed_steps`, `total_steps`, `completed_at`, `status`, and `steps`.
- Produces: `renderReportNavigationSchedule(payload)` and schedule row state helpers.
- Produces: schedule owner context-menu editor calling the Task 1 endpoint.

- [ ] **Step 1: Write a failing static structure and behavior test**

The test requires a card between flow and attention cards, sticky process column, generated calendar dates/weekdays/today marker, state classes, deadline and owner context menus, the “查看步骤” link, 180ms outer-card animation, and horizontal overflow.

- [ ] **Step 2: Run the new static test and confirm it fails**

Run: `python -m pytest -q tests/test_web_static.py -k "report_navigation_schedule_timeline"`

Expected: FAIL because the card and renderer do not exist.

- [ ] **Step 3: Add schedule markup and pure calculation helpers**

State precedence:

```text
completed after deadline -> overdue-completed
completed on/before deadline -> completed
error -> risk
unfinished after deadline -> overdue
completed_steps > 0 -> running
otherwise -> pending
```

The timeline starts on the first day of the current report month and ends on the latest visible process deadline. Date columns always share the available width evenly; the schedule does not use horizontal scrolling or leave unused space on the right. Header dates, row dots, deadline markers, labels, and line endpoints all use the same date-column center coordinates; the neutral baseline runs exactly from the first-date center to the latest-deadline center. Regular weekends and database-configured statutory holidays use red date text; adjusted weekend workdays keep the normal date color and display a workday marker. The database stores only annual holiday/workday exceptions and is updated once per year. Each row shows a dotted baseline, solid progress from the first calendar day toward its deadline, and an endpoint marker.

- [ ] **Step 4: Add expansion, collapse, and fishbone linking**

Expanded content contains status, monthly owner, percentage progress bar, the first non-completed step, overdue text when applicable, and a “查看步骤” button. One row may be open; row/blank clicks toggle it. The button calls the existing fishbone selection function and scrolls the flow card into view.

- [ ] **Step 5: Add responsive CSS**

Align the schedule frame with fishbone start/end capsules, keep names sticky during horizontal scroll, use 56px date columns, and stack the expanded metadata on narrow screens.

- [ ] **Step 6: Run the schedule static test**

Run: `python -m pytest -q tests/test_web_static.py -k "report_navigation_schedule_timeline"`

Expected: PASS.

### Task 3: Documentation, migration, and focused verification

**Files:**
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js` system changelog entry
- Verify: `sql/app_storage/mysql/007_report_navigation_schedule_owner.sql`

**Interfaces:**
- Documents the schedule timeline, monthly owner maintenance, read-only step linking, and migration order.

- [ ] **Step 1: Update README and the compact application changelog**

README lists concrete schedule behavior. The application changelog retains the required compact phrase “系统优化及BUG修复” for UI/detail work.

- [ ] **Step 2: Apply the additive owner migration to the configured local application database**

Run `007_report_navigation_schedule_owner.sql` against the application database, then restart only the source Python service on port 8765.

- [ ] **Step 3: Run one focused verification set**

Run: `python -m pytest -q tests/test_report_navigation_schema.py tests/test_report_navigation.py tests/test_report_navigation_api.py tests/test_web_static.py -k "schedule_owner or report_navigation_schedule_timeline"`

Expected: PASS with no failures.

- [ ] **Step 4: Inspect the final diff**

Run: `git diff --check` and `git status --short`.

Expected: no whitespace errors; unrelated untracked files remain untouched.
