# Table Header Visual Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every real table header match the current user-management header background while preserving existing table layout and theme behavior.

**Architecture:** Keep the existing global `th`, history-detail, and shared-modal selectors as the single visual layer. Use `var(--surface-container-low)` as the opaque light-theme background, use a clear surface-variant text color with a moderate shared weight, and remove duplicate user-table visual declarations so the same token reaches every table. Keep dark-mode selectors and all layout-specific selectors intact.

**Tech Stack:** Static HTML, CSS custom properties, Python `pytest` static-contract tests.

## Global Constraints

- Data-source configuration section headings are not tables and must not change.
- The three primary tool modal layouts must not change; only their list-header visual declarations may change.
- History-detail table title and cell alignment remains centered.
- Default, space-tech, and dark themes must remain supported.
- Scrollbars remain hidden while scrolling behavior remains available.

---

### Task 1: Unify table-header visual tokens

**Files:**
- Modify: `tests/test_web_static.py`
- Modify: `src/auto_check/web/styles.css`

**Interfaces:**
- Consumes: CSS custom properties `--surface-container-low` and `--on-surface-variant`.
- Produces: one shared light-theme header visual contract for global, history-detail, modal, and user-management tables.

- [ ] **Step 1: Write the failing static-contract test**

Update `test_modal_table_headers_match_history_tokens_without_layout_overrides` and `test_history_detail_modal_layout_keeps_tables_readable` so the global, modal, and history-detail header blocks require:

```python
for visual_declaration in (
    "color: var(--on-surface-variant)",
    "font-weight: 600",
    "background: var(--surface-container-low)",
    "border-bottom: 1px solid color-mix(in srgb, var(--outline-variant) 32%, var(--surface-container-lowest))",
):
    assert visual_declaration in global_body
```

Add a focused assertion for `.user-table th` that preserves its `font-size: 12px` layout declaration but removes the three duplicate visual declarations:

```python
user_header = re.search(r"(?m)^\.user-table th\s*\{(?P<body>.*?)\}", css, re.S)
assert user_header is not None
assert "font-size: 12px" in user_header.group("body")
for duplicate_visual in ("background:", "color:", "font-weight:"):
    assert duplicate_visual not in user_header.group("body")
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "modal_table_headers_match_history_tokens or history_detail_modal_layout"
```

Expected: FAIL because the shared selectors still use the mixed light background, mixed text color, and `font-weight: 500`, while `.user-table th` still contains its own visual override.

- [ ] **Step 3: Implement the shared visual contract**

In `src/auto_check/web/styles.css`, update all three light-theme header visual blocks (`th`, `.history-result-table th`, and the shared `.app-modal-shell` header selector) to use:

```css
color: var(--on-surface-variant);
font-weight: 600;
background: var(--surface-container-low);
border-bottom: 1px solid color-mix(in srgb, var(--outline-variant) 32%, var(--surface-container-lowest));
```

Keep the current dark-theme blocks unchanged. Reduce the user-management-specific block to layout-only styling:

```css
.user-table th {
  font-size: 12px;
}
```

Do not add declarations to `.modal-section-header` or change table alignment, positioning, padding, widths, or heights.

- [ ] **Step 4: Run focused and full static tests**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "modal_table_headers_match_history_tokens or history_detail_modal_layout"
python -m pytest -q tests/test_web_static.py
git diff --check
```

Expected: focused tests PASS, all static tests PASS, and `git diff --check` reports no whitespace errors.

- [ ] **Step 5: Commit the implementation**

```powershell
git add -- src/auto_check/web/styles.css tests/test_web_static.py
git commit -m "fix: unify table header contrast"
```

### Task 2: Match main-list header height to user management

**Files:**
- Modify: `tests/test_web_static.py`
- Modify: `src/auto_check/web/styles.css`

**Interfaces:**
- Consumes: the existing `.result-card > .table-wrap > .result-table` structure used by the reconciliation-result and reconciliation-history pages.
- Produces: `14px` vertical table-header padding for those two main lists only.

- [ ] **Step 1: Write the failing scope and height test**

Add a static test that requires a narrowly scoped rule:

```python
def test_main_result_and_history_headers_match_user_table_height_only():
    css = _read(STYLES_CSS)
    main_headers = re.search(
        r"(?m)^\.result-card > \.table-wrap > \.result-table > thead > tr > th\s*"
        r"\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert main_headers is not None
    assert "padding-top: 14px" in main_headers.group("body")
    assert "padding-bottom: 14px" in main_headers.group("body")
    assert "height:" not in main_headers.group("body")
    assert ".app-modal-shell" not in main_headers.group(0)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "main_result_and_history_headers_match_user_table_height_only"
```

Expected: FAIL because the scoped main-list header rule does not yet exist.

- [ ] **Step 3: Implement the scoped vertical padding**

Add the following rule after the existing history-table cell sizing rule, so it wins over `.history-table th, .history-table td` without changing horizontal padding:

```css
.result-card > .table-wrap > .result-table > thead > tr > th {
  padding-top: 14px;
  padding-bottom: 14px;
}
```

Do not modify global `th`, `.history-result-table th`, modal selectors, or user-management padding.

- [ ] **Step 4: Verify focused and full static tests**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "main_result_and_history_headers_match_user_table_height_only or modal_table_headers_match_history_tokens or history_detail_modal_layout"
python -m pytest -q tests/test_web_static.py
git diff --check
```

Expected: focused tests PASS, all static tests PASS, and `git diff --check` reports no whitespace errors.

- [ ] **Step 5: Commit the height adjustment**

```powershell
git add -- src/auto_check/web/styles.css tests/test_web_static.py
git commit -m "fix: align main table header height"
```
