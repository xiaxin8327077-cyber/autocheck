# Report Navigation Popover Manual Step Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let administrators confirm configured report-navigation steps directly from the all-steps popover without widening it, while keeping future step permissions database-driven.

**Architecture:** Keep the existing manual-complete and manual-cancel endpoints, strengthen service validation with both process and step switches, and render the existing status text as the action only when the payload permits it. Normalize current database permissions with a repeatable SQL migration and seed defaults so only `pbc_template_7` is enabled now.

**Tech Stack:** Python 3.12, SQLAlchemy/MySQL, vanilla JavaScript/CSS, pytest.

## Global Constraints

- Only administrators may change manual step state.
- Only the current report month may be changed.
- Both `report_nav_processes.allow_manual_step_completion` and `report_nav_steps.manual_completion_allowed` must permit the operation.
- Current seed and migration enable only `pbc_template_7`; future steps are enabled through database switches without code changes.
- The popover width and step-name layout remain unchanged.
- The existing right-side status text becomes the control; no separate button is added.
- Automatic completion cannot be manually cancelled.

---

### Task 1: Normalize database permissions and enforce both switches

**Files:**
- Create: `sql/app_storage/mysql/009_report_navigation_manual_step_permissions.sql`
- Modify: `sql/app_storage/mysql/003_report_navigation_seed.sql`
- Modify: `src/auto_check/app/report_navigation.py`
- Test: `tests/test_report_navigation.py`
- Test: `tests/test_report_navigation_schema.py`

**Interfaces:**
- Consumes: `ReportNavigationStore.load_processes(report_month)` and `load_step_config(step_code)`.
- Produces: `ReportNavigationService.set_manual_state(...)` that rejects disabled process or step switches.

- [ ] **Step 1: Add failing permission tests**

Add service tests that set either the process switch or step switch to `0` and assert `set_manual_state()` raises `ValueError` containing `不允许手动完成`. Add SQL assertions that only the `pbc_template_7` seed row ends in `manual_completion_allowed=1` and that migration `009_report_navigation_manual_step_permissions.sql` exists.

- [ ] **Step 2: Run the focused tests and confirm failure**

```powershell
python -m pytest -q tests/test_report_navigation.py tests/test_report_navigation_schema.py -k "manual"
```

Expected: failure because process-level validation and migration `009` are absent.

- [ ] **Step 3: Implement permission normalization and validation**

Change all current seed step flags to `0` except:

```sql
('pbc_template_7', ..., 1, 0, 1)
```

Create migration `009_report_navigation_manual_step_permissions.sql`:

```sql
UPDATE `report_nav_steps`
SET `manual_completion_allowed` = CASE WHEN `step_code` = 'pbc_template_7' THEN 1 ELSE 0 END;
```

In `set_manual_state()`, load the active process for the report month and reject unless both switches are true:

```python
process = next(
    (item for item in self.store.load_processes(report_month) if item.process_code == step.process_code),
    None,
)
if process is None or not process.allow_manual_step_completion or not step.manual_completion_allowed:
    raise ValueError("步骤不存在或不允许手动完成")
```

- [ ] **Step 4: Run focused backend tests**

```powershell
python -m pytest -q tests/test_report_navigation.py tests/test_report_navigation_schema.py -k "manual"
```

Expected: all selected tests pass.

### Task 2: Make configured status text actionable inside the popover

**Files:**
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: step payload fields `status`, `manual_completed`, and `manual_completion_allowed`.
- Produces: `setReportNavigationManualStepState(stepCode, action, processCode)` and status controls with `data-report-nav-step-action`.

- [ ] **Step 1: Add a failing frontend static test**

Assert the renderer emits a clickable status only for `manual_completion_allowed`, uses `manual-complete` for incomplete steps and `manual-cancel` only for `manual_completed`, calls the existing API with `report_month`, reloads navigation, and reopens the same popover. Assert CSS uses theme-colored underlined text without changing the popover width.

- [ ] **Step 2: Run the frontend test and confirm failure**

```powershell
python -m pytest -q tests/test_web_static.py -k "manual_step_confirmation"
```

Expected: failure because no popover status action exists.

- [ ] **Step 3: Implement the status action**

Render actionable status as:

```js
const manualAction = step.manual_completion_allowed && (!completed || step.manual_completed)
  ? (step.manual_completed ? "manual-cancel" : "manual-complete")
  : "";
const statusMarkup = manualAction
  ? `<button type="button" class="report-nav-schedule-step-status-action" data-report-nav-step-action="${manualAction}" data-report-nav-step-code="${escapeHtml(step.step_code || "")}">${stepStatusText}</button>`
  : `<em>${stepStatusText}</em>`;
```

Handle clicks before row selection, disable during the request, call the endpoint, reload, and immediately reopen the same process popover. Style the control with transparent background, no extra padding, theme-readable text, underline, pointer cursor, darker hover color, and a keyboard focus ring.

- [ ] **Step 4: Run the focused frontend test**

```powershell
python -m pytest -q tests/test_web_static.py -k "manual_step_confirmation"
```

Expected: selected test passes.

### Task 3: Update deployment and visible documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `docs/intranet-production-deployment.zh-CN.md`
- Modify: `docs/mysql-application-storage.zh-CN.md`
- Modify: `src/auto_check/web/app.js`
- Test: `tests/test_deployment_docs.py`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: migration `009_report_navigation_manual_step_permissions.sql`.
- Produces: deployment sequence and user-facing documentation for popover confirmation.

- [ ] **Step 1: Update documentation assertions first**

Require deployment documents to include migration `009_report_navigation_manual_step_permissions.sql`. Require README and the v2.1 in-app changelog to describe administrator confirmation in the all-steps popover and database-driven expansion.

- [ ] **Step 2: Run documentation tests and confirm failure**

```powershell
python -m pytest -q tests/test_deployment_docs.py tests/test_web_static.py -k "deployment or manual_step_confirmation"
```

Expected: failure until documentation is updated.

- [ ] **Step 3: Update documentation and changelog**

Append migration `009` to application-database upgrade sequences. Replace the old README statement that manual completion is unavailable, and add this v2.1 changelog entry:

```html
<li>新增报送步骤浮窗人工确认和撤销确认。</li>
```

- [ ] **Step 4: Run final focused verification**

```powershell
python -m pytest -q tests/test_report_navigation.py tests/test_report_navigation_api.py tests/test_report_navigation_schema.py tests/test_deployment_docs.py tests/test_web_static.py
git diff --check
```

Expected: all selected tests pass with no warnings or whitespace errors. Do not package the executable.
