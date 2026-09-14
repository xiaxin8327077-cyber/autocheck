# Dashboard Screen Preview and Region Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full-screen previews for the two copied dashboards, fix stale region edit versions, and allow custom region deletion.

**Architecture:** Copy the two dependency-free HTML dashboards into module-owned static assets and adapt only those copies to consume the existing board preview JSON endpoint. Add a guarded transactional delete endpoint and refresh region metadata before opening the edit dialog so optimistic locking remains intact.

**Tech Stack:** Python, SQLAlchemy Core, ES modules, standalone HTML/CSS/SVG, pytest.

## Global Constraints

- Never modify, start, or write files under `D:\xiaxin\kanban`.
- Do not weaken optimistic locking or allow built-in region deletion.
- Dashboard preview closes by explicit close action or Escape, never by clicking the backdrop.
- Do not package the Windows executable and do not perform browser visual QA.

---

### Task 1: Region lifecycle API

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/storage.py`
- Modify: `src/auto_check/modules/dashboard_management/service.py`
- Modify: `src/auto_check/modules/dashboard_management/api.py`
- Test: `tests/modules/dashboard_management/test_storage.py`
- Test: `tests/modules/dashboard_management/test_service.py`
- Test: `tests/modules/dashboard_management/test_api.py`

**Interfaces:**
- Produces: `DashboardManagementService.delete_region(region_id, payload, current_user)` and `DELETE /regions/{region_id}`.

- [ ] Add failing tests proving custom region deletion removes child rows and built-in deletion is rejected.
- [ ] Run focused tests and confirm the missing delete behavior fails.
- [ ] Implement transactional source/field/region deletion guarded by `row_version`.
- [ ] Run focused backend tests and confirm they pass.

### Task 2: Region edit freshness and delete controls

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/web/index.js`
- Modify: `src/auto_check/modules/dashboard_management/web/api.js`
- Modify: `src/auto_check/modules/dashboard_management/web/components/catalog_dialog.js`
- Modify: `src/auto_check/modules/dashboard_management/web/styles.css`
- Test: `tests/modules/dashboard_management/test_frontend_static.py`
- Test: `tests/modules/dashboard_management/test_frontend_behavior.py`

**Interfaces:**
- Consumes: `DELETE /regions/{region_id}`.
- Produces: edit dialog opened from freshly loaded catalog data and a destructive action shown only for custom regions.

- [ ] Add failing frontend tests for fresh catalog loading, delete confirmation and custom-only delete visibility.
- [ ] Run focused frontend tests and confirm failure.
- [ ] Add `deleteRegion`, fresh-load-before-edit, delete confirmation and danger styling.
- [ ] Run focused frontend tests and confirm they pass.

### Task 3: Copied dashboard preview pages

**Files:**
- Create: `src/auto_check/modules/dashboard_management/web/screens/financial-report.html`
- Create: `src/auto_check/modules/dashboard_management/web/screens/financial-report-flow.html`
- Modify: `src/auto_check/modules/dashboard_management/web/components/dashboard_tabs.js`
- Modify: `src/auto_check/modules/dashboard_management/web/components/board_preview_dialog.js`
- Modify: `src/auto_check/modules/dashboard_management/web/styles.css`
- Test: `tests/modules/dashboard_management/test_frontend_static.py`

**Interfaces:**
- Consumes: `GET /api/modules/dashboard-management/boards/{board_code}/preview`.
- Produces: near-full-screen iframe preview selected from the existing hover menu.

- [ ] Add failing tests for enabled “看板页面”, module-owned iframe paths, explicit close and current preview API URLs.
- [ ] Run the focused static test and confirm failure.
- [ ] Mechanically copy the two standalone HTML files into module assets without modifying the source project.
- [ ] Adapt the copied pages to map region codes and aliases from the board preview JSON.
- [ ] Add iframe modal rendering, loading behavior and close controls.
- [ ] Run focused frontend tests and confirm they pass.

### Task 4: Documentation and verification

**Files:**
- Modify: `README.md`
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`

- [ ] Document copied-page isolation, preview behavior, delete semantics and edit freshness.
- [ ] Run `python -m pytest -q tests/modules/dashboard_management` and confirm all tests pass.
- [ ] Run `git diff --check` and confirm no whitespace errors.
- [ ] Restart the local development service once and verify port 8765 is listening.
