# Smart Reconcile Theme-Specific Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the calm sidebar a click-to-toggle parent menu while keeping the vitality top menu hover-driven, with parent click opening “对数总览” and mouse leave closing the dropdown.

**Architecture:** Keep the shared markup and route IDs. CSS limits hover/focus reveal to `.top-nav-group`; JavaScript branches on the parent group class so sidebar clicks toggle `.open`, while top-nav clicks switch to `home` and blur only pointer-triggered clicks.

**Tech Stack:** CSS, vanilla JavaScript, pytest static tests, PowerShell/PyInstaller packaging.

---

### Task 1: Replace the old shared-behavior test

**Files:**
- Modify: `tests/test_web_static.py`

- [x] **Step 1: Write failing assertions**

```python
assert ".nav-group:hover .nav-submenu" not in css
assert ".nav-group:focus-within .nav-submenu" not in css
assert ".top-nav-group:hover .top-nav-submenu" in css
assert 'group.classList.contains("nav-group")' in toggle_handler
assert "setNavGroupOpen(group, !group.classList.contains(\"open\"));" in toggle_handler
assert 'group.classList.contains("top-nav-group")' in toggle_handler
assert 'switchPage("home");' in toggle_handler
assert "event.detail > 0" in toggle_handler
assert "toggle.blur();" in toggle_handler
```

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/test_web_static.py -q -k "smart_reconcile_parent"`

Expected: fail because the sidebar still opens on hover and both parent buttons navigate to `home`.

### Task 2: Implement theme-specific behavior

**Files:**
- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/app.js`

- [x] **Step 1: Restore click-only sidebar CSS**

```css
.nav-group.open .nav-submenu {
  max-height: 140px;
  opacity: 1;
}
```

Remove sidebar `:hover` and `:focus-within` reveal/chevron selectors. Keep top-nav hover/focus selectors unchanged.

- [x] **Step 2: Stop route state from forcing the sidebar open**

Remove the `setNavGroupOpen(group, active)` call from `syncNavGroupState`; retain only active class synchronization.

- [x] **Step 3: Split parent click behavior**

```javascript
const group = toggle.closest("[data-nav-group]");
if (!group) return;
if (group.classList.contains("nav-group")) {
  setNavGroupOpen(group, !group.classList.contains("open"));
  return;
}
if (group.classList.contains("top-nav-group")) {
  switchPage("home");
  if (event.detail > 0) toggle.blur();
}
```

- [x] **Step 4: Release pointer focus after selecting a top submenu item**

```javascript
if (item.classList.contains("top-nav-subitem") && e.detail > 0) item.blur();
```

- [x] **Step 5: Verify GREEN**

Run: `python -m pytest tests/test_web_static.py -q -k "smart_reconcile_parent"`

Expected: pass.

### Task 3: Document and deliver

**Files:**
- Modify: `README.md`
- Verify: `src/auto_check/web/app.js` v2.1 changelog
- Verify: `dist/auto-check.exe`

- [x] **Step 1: Update README**

Describe calm click-to-toggle and vitality hover/click-to-overview behavior; keep the in-app changelog at “系统优化及BUG修复”.

- [x] **Step 2: Run regressions**

Run `python -m pytest tests/test_web_static.py -q`, then `python -m pytest -q`.

Expected: all tests pass.

- [x] **Step 3: Run diff check and package once**

Run `git diff --check`, stop only processes using the worktree EXE, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1 -PythonPath 'C:\Users\jsitc\AppData\Local\Programs\Python\Python311\python.exe'
```

Expected: the package script passes its tests and rebuilds `dist/auto-check.exe`.
