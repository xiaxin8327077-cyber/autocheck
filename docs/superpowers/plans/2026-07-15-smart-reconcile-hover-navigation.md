# Smart Reconcile Hover Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make “智能核数” reveal its child menu on hover or keyboard focus in both themes and navigate directly to “对数总览” when clicked.

**Architecture:** Preserve the existing grouped navigation markup, route IDs, and `syncNavGroupState`. Extend the existing CSS open-state selectors with `:hover` and `:focus-within`, then simplify the parent-toggle click handler to close transient top menus and call `switchPage("home")`.

**Tech Stack:** Static HTML/CSS, vanilla JavaScript, pytest static-structure tests, existing PowerShell packaging script.

---

### Task 1: Specify hover, focus, and click behavior

**Files:**
- Modify: `tests/test_web_static.py`

- [x] **Step 1: Write the failing static test**

Add a test that checks for all four CSS selectors and the direct navigation call:

```python
assert ".nav-group:hover .nav-submenu" in css
assert ".nav-group:focus-within .nav-submenu" in css
assert ".top-nav-group:hover .top-nav-submenu" in css
assert ".top-nav-group:focus-within .top-nav-submenu" in css
assert 'switchPage("home")' in toggle_handler
assert "nextOpen" not in toggle_handler
```

- [x] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/test_web_static.py -q -k "smart_reconcile_parent_hover"`

Expected: fail because hover/focus selectors and direct parent navigation are absent.

### Task 2: Implement consistent parent-menu behavior

**Files:**
- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/app.js`

- [x] **Step 1: Extend sidebar reveal selectors**

Use one rule for active-open, pointer hover, and keyboard focus:

```css
.nav-group.open .nav-submenu,
.nav-group:hover .nav-submenu,
.nav-group:focus-within .nav-submenu {
  max-height: 140px;
  opacity: 1;
}
```

- [x] **Step 2: Extend top-menu reveal selectors**

```css
.top-nav-group.open .top-nav-submenu,
.top-nav-group:hover .top-nav-submenu,
.top-nav-group:focus-within .top-nav-submenu {
  display: grid;
  gap: 3px;
}
```

- [x] **Step 3: Replace parent click toggling with navigation**

```javascript
navGroupToggles.forEach((toggle) => {
  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    document.querySelectorAll(".top-nav-group.open").forEach((group) => setNavGroupOpen(group, false));
    switchPage("home");
  });
});
```

- [x] **Step 4: Run the focused test and verify GREEN**

Run: `python -m pytest tests/test_web_static.py -q -k "smart_reconcile_parent_hover"`

Expected: pass.

### Task 3: Document, regress, and package

**Files:**
- Modify: `README.md`
- Verify: `src/auto_check/web/app.js` current v2.1 changelog
- Verify: `dist/auto-check.exe`

- [x] **Step 1: Update visible behavior documentation**

Document that both theme variants reveal the child menu on hover/focus and that clicking the parent enters “对数总览”. Keep the in-app changelog wording as “系统优化及BUG修复”.

- [x] **Step 2: Run frontend and full regression tests**

Run: `python -m pytest tests/test_web_static.py -q`

Expected: all frontend static tests pass.

Run: `python -m pytest -q`

Expected: all project tests pass.

- [x] **Step 3: Check the diff**

Run: `git diff --check`

Expected: no whitespace errors; Windows LF/CRLF conversion warnings are acceptable under repository instructions.

- [x] **Step 4: Rebuild the Windows executable**

Confirm the exact worktree `dist/auto-check.exe` is not running, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1 -PythonPath 'C:\Users\jsitc\AppData\Local\Programs\Python\Python311\python.exe'
```

Expected: tests pass inside the packaging script and `dist/auto-check.exe` is rebuilt successfully.
