# Global Solid Theme Colors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the canceled gradient preference with administrator-managed global solid theme colors, future-ready per-user overrides, accessible light/dark rendering, and the already-approved personal line-chart/radius, semantic-button, login, and radius coverage work.

**Architecture:** Store global defaults in a dedicated one-row `system_interface_preferences` table and reserve nullable per-user overrides in `user_interface_preferences`; never use `app_settings`. Resolve effective colors server-side, expose anonymous read plus administrator-only atomic write, and render all target surfaces from pure-color CSS variables with JavaScript contrast derivation. Preserve the existing modal and table-header visual work, and finish with the authorized MySQL migration, full verification, packaging, and one whole-branch review.

**Tech Stack:** Python 3.12, SQLAlchemy Core, MySQL 8 DDL, native HTML/CSS/JavaScript, Canvas 2D, pytest, PyInstaller/PowerShell.

## Global Constraints

- Default vitality color is exactly `#3F6FAF`; default calm color is exactly `#355F63`.
- There is no theme gradient setting, database column, API field, DOM control, cache field, root attribute or target-component gradient branch.
- `app_settings` is explicitly excluded from theme-color storage.
- Current global color editing is capability-gated to administrators; future personal colors are nullable reserved fields and are not writable in this release.
- Effective color precedence is field-by-field: valid personal override, then valid system color, then code default.
- Color input accepts only six-digit HEX with `#`; lowercase input is normalized to uppercase before persistence.
- Every solid accent computes readable text/icon colors independently for light and dark surfaces. Semantic danger/warning/success/disabled colors override theme colors.
- Existing unified modal white surfaces, local gray selection/log regions, layout, scrolling and spacing must not regress.
- Existing unified table-header background, text, border and height must not be changed or matched by new theme selectors.
- Visual changes must not change business behavior, event IDs, request payloads outside the named settings APIs, data calculations, flow execution, imports, exports or validation.
- Default radius remains `4px`; accepted range remains `1`–`15px`; default line style remains `straight`.
- Straight charts hide visible point circles but retain values and tooltip hit targets; smooth charts retain circles.
- Per user instruction, do not dispatch per-task reviewers. Dispatch one whole-branch reviewer after all implementation, migration verification, tests and packaging.
- The controller applies the user-authorized remote MySQL migration; subagents never receive credentials or mutate the database.

## Controller Preparation Before Task 1

The interrupted Task 5 draft contains only canceled gradient work in these three tracked files:

```text
src/auto_check/web/app.js
src/auto_check/web/styles.css
tests/test_web_static.py
```

Verify `git diff --name-only` lists only these uncommitted tracked files, then restore exactly these files to `HEAD`. Do not restore documentation, committed Tasks 1–4, user files, modal work or table-header work. Confirm `git status --short` is clean before dispatching Task 1.

---

## Task 1: Replace gradient persistence with global and personal solid-color schema

**Files:**

- Modify: `src/auto_check/app/storage_user_interface_preferences.py`
- Create: `src/auto_check/app/storage_system_interface_preferences.py`
- Modify: `src/auto_check/app/app_database.py`
- Modify: `sql/app_storage/mysql/005_user_appearance_preferences.sql`
- Create: `sql/app_storage/mysql/006_system_interface_preferences.sql`
- Modify: `scripts/export_sqlite_to_mysql.py`
- Modify: `tests/test_user_interface_preferences.py`
- Create: `tests/test_system_interface_preferences.py`
- Modify: `tests/test_app_database.py`
- Modify: `tests/test_sqlite_to_mysql_export.py`
- Modify: `tests/mysql_config_test_support.py`

**Interfaces:**

- Produces `UserInterfacePreferences(radius_px: int, line_chart_style: str, vitality_theme_color: str | None, calm_theme_color: str | None)`.
- Produces `SystemInterfacePreferences(vitality_theme_color: str, calm_theme_color: str, updated_by: str | None = None)`.
- Produces `EffectiveThemeColors(vitality_theme_color: str, calm_theme_color: str)`.
- Produces `normalize_theme_color(value: object, *, allow_none: bool = False) -> str | None`, `load_system_interface_preferences`, `save_system_interface_preferences`, and `resolve_effective_theme_colors`.

- [ ] **Step 1: Write failing storage and schema tests**

Require all of the following:

```python
assert UserInterfacePreferences() == UserInterfacePreferences(4, "straight", None, None)
assert SystemInterfacePreferences() == SystemInterfacePreferences("#3F6FAF", "#355F63", None)
assert normalize_theme_color("#3f6faf") == "#3F6FAF"
assert normalize_theme_color(None, allow_none=True) is None
with pytest.raises(ValueError):
    normalize_theme_color("#fff")
```

Add load/save tests proving user radius/line saves preserve existing nullable personal colors, system saves atomically update both colors and `updated_by`, malformed fields fall back independently, and personal overrides win independently over system defaults.

Schema tests must require 37 tables, user columns `line_chart_style`, `vitality_theme_color`, `calm_theme_color`, no `theme_gradient_enabled`, guarded `005`, guarded `006`, and exporter order through `006`.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_system_interface_preferences.py tests/test_app_database.py tests/test_sqlite_to_mysql_export.py
```

Expected: FAIL because the current model contains `theme_gradient_enabled`, there is no system storage/table, `005` adds the canceled field, and the expected/export schema stops at 36 tables/`005`.

- [ ] **Step 3: Implement strict shared color normalization**

In the new system storage module define:

```python
DEFAULT_VITALITY_THEME_COLOR = "#3F6FAF"
DEFAULT_CALM_THEME_COLOR = "#355F63"
THEME_COLOR_PATTERN = re.compile(r"^#[0-9A-F]{6}$")

def normalize_theme_color(value: object, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if type(value) is not str:
        raise ValueError("theme color must be a #RRGGBB string")
    normalized = value.upper()
    if not THEME_COLOR_PATTERN.fullmatch(normalized):
        raise ValueError("theme color must be a #RRGGBB string")
    return normalized
```

Use field-isolated fallback helpers for database reads; validation errors on writes must be strict and atomic.

- [ ] **Step 4: Rework user storage without overwriting future personal colors**

Remove all gradient constants, columns, validation and SQL values. Insert new rows with personal colors `NULL`; on duplicate key update only `radius_px`, `line_chart_style`, and `updated_at`, then reload the row so existing personal colors remain in the returned object.

The SQLAlchemy table must declare both personal colors as nullable `String(7)` columns.

- [ ] **Step 5: Add one-row system storage**

Define a SQLAlchemy table matching `006`. `load_system_interface_preferences()` selects `id=1` and returns code defaults if absent. `save_system_interface_preferences()` validates both values before executing one MySQL upsert with `id=1`, both colors, `updated_by`, and one timestamp.

Resolve each effective field separately:

```python
return EffectiveThemeColors(
    vitality_theme_color=user.vitality_theme_color or system.vitality_theme_color,
    calm_theme_color=user.calm_theme_color or system.calm_theme_color,
)
```

- [ ] **Step 6: Rewrite `005` and add `006`**

`005` uses `information_schema.COLUMNS` and `TABLE_CONSTRAINTS` guards to add:

```sql
`line_chart_style` VARCHAR(16) NOT NULL DEFAULT 'straight',
`vitality_theme_color` CHAR(7) NULL,
`calm_theme_color` CHAR(7) NULL
```

with `straight/smooth` and nullable uppercase HEX checks. It must contain no `theme_gradient_enabled`, DML, table recreation, foreign key, database creation or schema-version mutation.

`006` uses `CREATE TABLE IF NOT EXISTS system_interface_preferences` with `id TINYINT UNSIGNED`, both default colors, nullable `updated_by`, `updated_at DATETIME(6)`, primary key, `id=1` check and uppercase HEX checks. It contains no seed insert.

- [ ] **Step 7: Update expected schema/export support**

Add the 37th table and exact columns to `EXPECTED_APP_SCHEMA`, append `006` after `005` in `MYSQL_POST_EXPORT_UPGRADE_SCRIPTS`, and update in-memory test connections for the new table and changed user columns.

- [ ] **Step 8: Verify and commit**

Run the Step 2 tests plus `git diff --check`. Expected: all pass and `004` is unchanged. Commit only Task 1 files:

```text
feat: persist global solid theme colors
```

---

## Task 2: Expose effective theme colors and administrator-only global writes

**Files:**

- Modify: `src/auto_check/app/server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_security.py`

**Interfaces:**

- Consumes Task 1 user/system/effective value objects and normalization.
- Produces anonymous/authenticated `GET /api/settings/interface/theme-colors`.
- Produces administrator-only `POST /api/settings/interface/theme-colors`.
- Keeps `GET/POST /api/settings/interface` for only radius and line-chart style.

- [ ] **Step 1: Write failing router and HTTP security tests**

Require anonymous GET response:

```json
{
  "colors": {
    "system": {"vitality": "#3F6FAF", "calm": "#355F63"},
    "personal": {"vitality": null, "calm": null},
    "effective": {"vitality": "#3F6FAF", "calm": "#355F63"}
  },
  "capabilities": {"can_manage_system_theme_colors": false}
}
```

Authenticated tests cover per-field personal overrides and admin capability. POST tests cover lowercase normalization, atomic invalid rejection, login, admin role, CSRF, user isolation and `updated_by`.

Update interface preference expectations to only `radius_px` and `line_chart_style`; assert the gradient key is absent and personal colors cannot be written through that route.

- [ ] **Step 2: Run RED tests**

```powershell
python -m pytest -q tests/test_server.py -k "interface_settings or theme_colors"
python -m pytest -q tests/test_security.py -k "interface_settings or theme_colors"
```

Expected: FAIL because current interface API still requires `theme_gradient_enabled` and no color route exists.

- [ ] **Step 3: Simplify personal interface serialization**

Serialize and validate exactly:

```python
{"radius_px": preferences.radius_px, "line_chart_style": preferences.line_chart_style}
```

One POST atomically saves those two fields only; storage preserves reserved personal colors.

- [ ] **Step 4: Add color response and capability helpers**

Use one helper to load system colors, optional current-user preferences, and effective colors in a single connection scope. Capability is true only when `current_user.role == "admin"` in this release. Keep the capability calculation in one server helper so future permission policy changes do not require frontend role checks.

- [ ] **Step 5: Add anonymous GET and protected POST**

GET does not require a user ID. POST checks the capability before validation, validates both raw values, then performs one transaction/upsert. Return the same structured response after save. The HTTP layer's existing unsafe-method CSRF protection remains authoritative; do not add query-string secrets or bypasses.

- [ ] **Step 6: Verify and commit**

Run both focused commands, all three storage test files, and `git diff --check`. Commit:

```text
feat: expose global theme color settings
```

---

## Task 3: Remove gradient state and add an accessible pure-color runtime

**Files:**

- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes Task 2 response shapes.
- Produces `normalizeThemeHex`, `deriveThemePalette`, `applyEffectiveThemeColors`, and a personal interface state containing only `radiusPx` and `lineChartStyle`.

- [ ] **Step 1: Write failing removal and palette tests**

Assert the gradient toggle/control, `themeGradientEnabled`, `theme_gradient_enabled`, `data-theme-gradient`, gradient cache keys and gradient tokens are absent. Assert personal GET/POST carries only radius and line style.

Use the JavaScript harness to require:

```javascript
normalizeThemeHex("#3f6faf") === "#3F6FAF"
normalizeThemeHex("#fff") === null
deriveThemePalette("#3F6FAF", "light").accent === "#3F6FAF"
```

Require `onAccent` to choose black or white with the higher WCAG contrast and `readableAccent` to meet at least 4.5:1 against the supplied light/dark surface.

- [ ] **Step 2: Run RED tests**

```powershell
python -m pytest -q tests/test_web_static.py -k "interface or gradient or palette or contrast"
```

Expected: FAIL because Task 4 currently exposes/stores gradient state and no pure-color contrast runtime exists.

- [ ] **Step 3: Remove canceled state and control**

Delete the gradient row from `index.html`. Reduce `DEFAULT_INTERFACE_PREFERENCES`, draft/saved cloning, parsing, equality, payload, reset, cache and control synchronization to radius and line style. Preserve request ID, auth revision, edit revision, server mutation revision, failed-save behavior and visible radio focus/disabled states.

- [ ] **Step 4: Implement pure-color parsing and contrast**

Implement deterministic sRGB conversion, relative luminance and contrast. `deriveThemePalette(hex, mode)` returns:

```javascript
{
  accent: "#RRGGBB",
  onAccent: "#000000" | "#FFFFFF",
  readableAccent: "#RRGGBB",
  focusRing: "rgba(...)"
}
```

Adjust only `readableAccent` toward black on light surfaces or white on dark surfaces until contrast is at least 4.5; never mutate `accent`.

- [ ] **Step 5: Apply variables without gradient attributes**

`applyEffectiveThemeColors({vitality, calm})` selects the current theme's color, derives the current light/dark palette and sets:

```text
--theme-accent
--theme-on-accent
--theme-accent-readable
--theme-focus-ring
```

Theme or dark-mode switching reapplies the same saved effective colors. There is no gradient root dataset.

- [ ] **Step 6: Verify and commit**

Run the focused command, complete `tests/test_web_static.py`, and `git diff --check`. Commit:

```text
refactor: replace theme gradients with solid color runtime
```

---

## Task 4: Add administrator global-color controls and WYSIWYG state

**Files:**

- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes Task 2 color endpoint and Task 3 runtime.
- Produces `systemThemeColorState`, `loadSystemThemeColors`, `saveSystemThemeColors`, `resetSystemThemeColorDraft`, and a successful-login/effective-color display cache.

- [ ] **Step 1: Write failing markup, state and race tests**

Require two `type="text"` inputs with IDs `systemVitalityThemeColor` and `systemCalmThemeColor`, readonly swatches, inline errors, separate save/reset buttons and a capability-controlled container. Assert there is no `type="color"`.

Harness tests must cover valid live preview, incomplete/invalid text preserving the last valid preview, lowercase normalization, save disablement, reset-as-draft, failed save, leave-page discard, logout/user switch, stale GET, stale POST and server mutation revision.

- [ ] **Step 2: Run RED tests**

```powershell
python -m pytest -q tests/test_web_static.py -k "system_theme or theme_color or interface"
```

Expected: FAIL because there are no global color controls or state.

- [ ] **Step 3: Add capability-driven markup**

Place the global color group inside the existing interface card. Keep it hidden until the server capability is true; do not add an `admin-only` class or direct role check. Each row contains label, text input, swatch and error region. Personal and global save buttons remain independent.

- [ ] **Step 4: Add an atomic draft/saved state machine**

Track saved colors, raw input strings, last valid draft, loading/saving/dirty, request ID, auth revision, edit revision and server mutation revision. Valid input calls `applyEffectiveThemeColors` immediately; invalid input changes only its raw/error state. Leaving the page restores saved effective colors.

- [ ] **Step 5: Implement load/save/reset**

GET the color route after authentication and for the anonymous login bootstrap consumer. POST both colors with CSRF. On success replace saved/draft, update swatches and cache; on failure retain preview and dirty state. Reset uses exact defaults but does not POST.

- [ ] **Step 6: Verify and commit**

Run the focused command, full static tests and `git diff --check`. Commit:

```text
feat: add global theme color controls
```

---

## Task 5: Route application surfaces, forms, dates and backgrounds through solid tokens

**Files:**

- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes Task 3 root variables and Task 4 live application.
- Produces scoped solid styling for emphasis, forms, calendar and page background.

- [ ] **Step 1: Write failing scope and no-gradient tests**

Require target primary navigation, primary actions, active segments/tabs, non-semantic selected filters and module icons to consume `--theme-accent`/`--theme-on-accent`. Require inputs, textareas, searches, selects and date controls to consume readable focus/caret/icon variables while surfaces remain neutral.

Require the custom calendar selected date, month, navigation, clear and today actions to be pure color. Require application backgrounds to be one computed solid CSS variable. Assert target rules contain no `linear-gradient` or `radial-gradient`, and assert form/theme selectors do not include `th` or table-header containers.

- [ ] **Step 2: Run RED tests**

```powershell
python -m pytest -q tests/test_web_static.py -k "theme or form or calendar or background or header"
```

Expected: FAIL while current surfaces use scattered fixed/gradient colors.

- [ ] **Step 3: Derive one solid page background**

Use JavaScript hex mixing to set `--theme-page-background` from the active accent and the current neutral page base: low accent proportion in light mode and a slightly higher proportion in dark mode. Set it once on the application shell behind `.main-content`; cards, tables and modals retain their existing surfaces.

- [ ] **Step 4: Migrate high-emphasis and form selectors**

Use solid accent/on-accent for eligible primary surfaces. Use readable accent/focus-ring for text, icons, borders, carets and focus. Error, success, readonly and disabled selectors have higher priority. Do not use broad unscoped `button`, `input` or table selectors.

- [ ] **Step 5: Remove component-local calendar gradients**

Selected day uses `background: var(--theme-accent)` and `color: var(--theme-on-accent)`. Month title, previous/next, clear and today use `--theme-accent-readable`. Preserve date values, navigation, keyboard behavior, outside-month styling, positioning and `--ui-radius`.

- [ ] **Step 6: Verify protected surfaces and commit**

Run the focused command, full static tests, `git diff --check`, and inspect the diff around all `.table-*`, `th`, modal and overlay rules. Commit:

```text
feat: apply solid themes to interface surfaces
```

---

## Task 6: Normalize semantic button colors without overriding theme or status meaning

**Files:**

- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes `--theme-accent`, `--theme-on-accent`, readable/focus variables and dark mode.
- Produces `--action-danger`, `--action-warning`, `--action-success`, neutral variants, explicit `data-action-tone`/`data-action-variant`, and `showConfirm(title, message, options)`.

- [ ] **Step 1: Write failing button inventory tests**

Audit every literal/template button: it must have a recognized action base/tone or explicit state-control role. Require exact light semantic colors `#BA1A1A`, `#B45309`, `#137333` and dark colors `#FFB4AB`, `#FBBF24`, `#6DDB9C`. Require disabled rules to override all colors and feedback.

- [ ] **Step 2: Run RED tests**

```powershell
python -m pytest -q tests/test_web_static.py -k "button or action_tone or semantic or confirm"
```

Expected: FAIL because action meanings are inconsistent and confirmation tone is implicit.

- [ ] **Step 3: Add centralized action tokens and variants**

Theme-primary solid buttons use `--theme-accent` and `--theme-on-accent`. Danger, warning and success use stable semantic tokens; weak variants use semantic text/icon/border plus at most an 8% same-color background. Neutral secondary actions retain neutral surfaces and readable theme focus only.

- [ ] **Step 4: Classify static and dynamic controls by meaning**

Apply deterministic mappings:

- new/add/save/confirm/start/next/retry/import/login: primary solid;
- delete/irreversible clear: danger, weak for row actions;
- disable/stop/cancel execution/restore defaults/schema overwrite: warning;
- enable/re-enable/complete: success;
- view/edit/refresh/export/download/test connection/back/close: neutral weak;
- navigation toggles, theme/dark toggles, filters, pagination, disclosures and switches: state-control roles.

Do not change IDs, event datasets, handler selectors, labels or business requests.

- [ ] **Step 5: Make confirmation tone explicit**

Add strict `primary/danger/warning/success` normalization to the optional third `showConfirm` argument. Set/reset the confirmation button dataset on every lifecycle. Update destructive, warning and success call sites by operation semantics, never by matching Chinese rendered text.

- [ ] **Step 6: Verify and commit**

Run the focused command, full static tests and `git diff --check`. Commit:

```text
feat: standardize semantic button colors
```

---

## Task 7: Add selectable straight/smooth chart geometry using effective solid theme colors

**Files:**

- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes personal `lineChartStyle` and Task 3 effective colors.
- Produces `normalizeLineChartStyle`, `traceChartLine`, and one solid Canvas theme palette helper.

- [ ] **Step 1: Write failing chart tests**

Require straight default, strict style normalization, `moveTo/lineTo` straight paths, existing `smoothCurveThrough(ctx, points, 0.35, bounds)` smooth paths, common area/stroke geometry, no visible circles in straight mode, retained labels/hit targets, circles in smooth mode, no data refetch on style/theme change and colors sourced from effective theme colors.

- [ ] **Step 2: Run RED tests**

```powershell
python -m pytest -q tests/test_web_static.py -k "chart or curve or line_style"
```

Expected: FAIL because current renderers directly call the smooth helper and use hard-coded colors.

- [ ] **Step 3: Implement shared path tracing**

```javascript
function traceChartLine(ctx, points, style, bounds = null) {
  if (points.length < 2) return;
  if (normalizeLineChartStyle(style) === "straight") {
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    points.slice(1).forEach((point) => ctx.lineTo(point.x, point.y));
    return;
  }
  smoothCurveThrough(ctx, points, 0.35, bounds);
}
```

Route both homepage line renderers and the area-fill boundary through this helper.

- [ ] **Step 4: Use one solid Canvas palette**

Read the currently applied CSS accent/readable variables and return solid strings for stroke, labels, legends and smooth points. Multi-series layers may derive same-hue lightness levels, but must not create `CanvasGradient`.

- [ ] **Step 5: Redraw without refetching and commit**

Theme, dark-mode and line-style changes call existing redraw functions with cached data. Run focused/full static tests and `git diff --check`. Commit:

```text
feat: add themed selectable line chart geometry
```

---

## Task 8: Unify login light/dark layout and bootstrap effective solid colors

**Files:**

- Modify: `src/auto_check/web/login.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_login_page.py`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes Task 2 anonymous read, Task 3 color parser/palette semantics, Task 4 successful-effective-color cache, and Task 5 solid background formula.
- Produces pre-style login color bootstrap and one identical light/dark centered-card layout.

- [ ] **Step 1: Write failing login tests**

Require strict last-successful effective-color cache parsing, default colors on missing/invalid cache, no gradient cache/attribute/style, anonymous service refresh, login failure cache isolation, successful login cache update, identical light/dark geometry and theme-aware links/focus/check/button/icon colors.

- [ ] **Step 2: Run RED tests**

```powershell
python -m pytest -q tests/test_login_page.py tests/test_web_static.py -k "login or theme_color or cache"
```

Expected: FAIL because login still has gradient/special dark-layout behavior or lacks effective-color bootstrap.

- [ ] **Step 3: Add pre-style pure-color bootstrap**

Before the login CSS, parse only exact `#RRGGBB` cached values. Set accent/on-accent/readable/focus/page-background variables synchronously. Missing/invalid cache uses `#3F6FAF` / `#355F63`; asynchronously fetch the anonymous color endpoint and reapply valid system colors.

- [ ] **Step 4: Unify layout and theme interactions**

Remove dark-only two-column/grid/width/padding/left-panel rules. Light and dark share one centered card, field positions and Logo geometry. Links, cursor, focus border/ring, password-eye focus, checkbox and login button consume pure theme variables; error and disabled states override them.

- [ ] **Step 5: Verify and commit**

Run login/static tests, `git diff --check`, and inspect for dark selectors changing display/grid/geometry. Commit:

```text
feat: apply effective solid themes to login
```

---

## Task 9: Apply the remaining scoped radius overrides

**Files:**

- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes existing `--ui-radius`.
- Produces exactly sixteen additional scoped selectors; no DOM or event changes.

- [ ] **Step 1: Write failing selector tests**

Require `border-radius: var(--ui-radius) !important` for:

```css
#page-users .user-filter-pill,
#page-users .user-avatar,
#page-users .role-badge,
#page-users .user-status-badge,
.user-modal .user-role-card,
.user-modal .user-role-card-icon,
.user-modal .user-enable-row,
#configModal .modal-section,
#infoModal .home-stat-modal-table-wrap,
#dbValidationModal .db-validation-table-item,
#dbValidationModal #dbValidationLog,
.flow-chain-editor-overlay .flow-definition-table,
.flow-chain-editor-overlay .flow-selected-step,
.flow-chain-editor-overlay .flow-selected-step-actions .btn-icon,
#page-report-navigation .report-nav-done-meta,
#page-report-navigation .report-nav-no-panel-done-meta
```

Explicitly exclude `.user-avatar-status`, `.current-user-badge`, switch track/thumb, inner table, layout-only flow list and unscoped icon buttons.

- [ ] **Step 2: Run RED tests**

```powershell
python -m pytest -q tests/test_web_static.py -k "radius and (user or modal or home_stat or validation or flow or report)"
```

Expected: FAIL for fixed `999/12/10/8/7/4px` component values.

- [ ] **Step 3: Add only the final scoped override**

Change only `border-radius`. Preserve user avatar size/color/online point/“我” marker, badge colors, switch geometry, data-source form behavior, table data/sticky headers/scrolling, validation selection/logging, flow loading/search/order/move/remove, and fishbone colors/borders/shadows/transforms/positioning.

- [ ] **Step 4: Verify and commit**

Run focused/full static tests and `git diff --check`. Commit:

```text
fix: apply radius to omitted interface controls
```

---

## Task 10: Update release docs, fully verify, migrate MySQL and package

**Files:**

- Modify: `README.md`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `docs/intranet-production-deployment.zh-CN.md`
- Modify: `docs/mysql-application-storage.zh-CN.md`
- Modify: `src/auto_check/web/app.js` only for concise in-app changelog
- Modify: affected documentation/static tests
- Refresh: `dist/auto-check.exe`

**Interfaces:**

- Consumes Tasks 1–9.
- Produces canonical DDL docs, verified remote schema and refreshed Windows executable.

- [ ] **Step 1: Update documentation and concise changelog**

Document global defaults, admin-only current editing, future personal override precedence, strict HEX, pure-color/no-gradient rendering, automatic light/dark contrast, semantic buttons, line styles, login layout, radius coverage and `005`/`006` order.

`docs/mysql-application-storage.zh-CN.md` must contain complete canonical DDL for both final tables, 37-table count and exact defaults/checks—not only an upgrade note. Explicitly state theme colors do not use `app_settings`.

Keep the application changelog line exactly concise:

```text
系统优化及BUG修复
```

- [ ] **Step 2: Run documentation/static tests**

```powershell
python -m pytest -q tests/test_deployment_docs.py tests/test_web_static.py tests/test_login_page.py
```

Expected: PASS.

- [ ] **Step 3: Run the full suite and diff validation**

```powershell
python -m pytest -q
git diff --check
git status --short
```

If the known flow-chain active-job timing test fails once because the job completes before polling, rerun that exact test once and record both outputs; do not modify unrelated flow code unless the failure reproduces consistently.

- [ ] **Step 4: Apply the authorized remote MySQL migration**

The controller uses the connection supplied in this session without writing credentials to source, docs, scripts, logs or commits.

Before mutation query current `user_interface_preferences` columns/constraints/row count and whether `system_interface_preferences` exists. Execute the finalized `005` then `006`. Afterward verify:

- `user_interface_preferences` has radius, line style and both nullable personal colors, no gradient column, all checks and unchanged row count;
- `system_interface_preferences` exists with exact defaults/checks/audit columns and no unexpected rows;
- the application database has 37 expected tables.

- [ ] **Step 5: Package Windows executable**

Confirm no running `dist\auto-check.exe` owns the file, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
Get-Item dist\auto-check.exe | Select-Object Length, LastWriteTime
Get-FileHash dist\auto-check.exe -Algorithm SHA256
```

Expected: package exit `0`, current timestamp, nonzero size and recorded SHA-256.

- [ ] **Step 6: Commit release-facing changes**

Stage only Task 10 docs, changelog/tests and the tracked executable. Inspect staged names and commit:

```text
docs: document solid theme preference rollout
```

---

## Task 11: One whole-branch review and correction pass

**Files:** All changes from base commit recorded immediately before Task 1 through Task 10 head.

- [ ] **Step 1: Dispatch one fresh whole-branch reviewer**

Provide the design, this plan, base SHA, head SHA, test/package evidence and explicit protected modal/table-header constraints. Reviewer reports only actionable Critical/Important/Minor findings with file/line evidence.

- [ ] **Step 2: Fix verified findings**

Use systematic debugging for any real defect. Add a failing regression test before each behavior fix. Do not implement speculative style preferences or unrelated refactors.

- [ ] **Step 3: Re-run final evidence**

Run focused affected tests, `python -m pytest -q`, `git diff --check`, rebuild if source changed after packaging, and reverify MySQL only if DDL/storage changed during review.

- [ ] **Step 4: Record final branch state**

Update the SDD ledger with task commits, full-suite result, migration verification, executable size/hash and review disposition. The worktree must contain no uncommitted tracked changes.

## Final Acceptance Checklist

- System colors default to `#3F6FAF` and `#355F63`, are stored only in `system_interface_preferences`, and can be changed only through the current admin capability.
- Reserved nullable personal colors resolve before system defaults but have no current write UI/API for regular users.
- No canceled gradient field/control/cache/root attribute or target-component gradient remains.
- All theme text/icons and solid fills remain readable in light and dark mode; semantic actions retain meaning.
- Personal radius and line style remain isolated per user and save atomically without overwriting reserved colors.
- Login, application backgrounds, forms, dates and charts use effective pure colors.
- Straight/smooth behavior, semantic buttons and sixteen radius gaps match the design.
- Unified table headers and modal surfaces/layout remain unchanged.
- Canonical DDL, remote MySQL, full tests and packaged executable are current.
- One final whole-branch review has no unresolved Critical or Important findings.
