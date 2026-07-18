# Theme Gradient and Line Chart Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to execute this plan one task at a time, with a fresh implementation agent and review checkpoint for each task.

**Goal:** 在不改变业务功能和数据结果的前提下，为两套固定主题增加一个按用户保存的全局渐变开关，并为全系统折线图增加“直线折线 / 平滑曲线”偏好；折线图默认使用直线折线。

**Architecture:** 扩展现有 MySQL `user_interface_preferences`、当前用户界面偏好 API 和前端异步状态机，一次性保存圆角、渐变和折线图风格。主题强调面通过集中 CSS 令牌切换纯色/渐变；Canvas 折线图通过共享路径与颜色函数切换几何、数据点可见性和主题色。服务端是跨设备权威来源，前端缓存只用于减少初始闪变。

**Tech Stack:** Python 3.12、SQLAlchemy Core、MySQL 8、原生 HTML/CSS/JavaScript、Canvas 2D、pytest、PyInstaller。

**Approved design:** [`docs/superpowers/specs/2026-07-18-theme-color-gradient-preference-design.md`](../specs/2026-07-18-theme-color-gradient-preference-design.md)

## Global constraints

- 开始实施前先确认其他会话已结束或已提交其工作；保留所有无关修改，不重置、不覆盖。
- 活力主题固定纯色 `#3B82F6`，沉稳主题固定纯色 `#25676E`，不提供颜色选择器。
- 渐变开关同时作用于两套主题和折线图颜色。
- 折线图风格只有 `straight` 和 `smooth`；默认、旧记录补值、接口失败回退和恢复默认均为 `straight`。
- 直线折线隐藏空心数据点圆圈；平滑曲线保留现有圆圈。数值标签和 tooltip 命中区域始终保留。
- 两种风格均跟随当前主题：渐变开启时使用主题渐变，关闭时使用主题纯色。多系列折线只从当前主题色派生固定深浅层级。
- 渐变开关同时控制应用内容区底层和登录页背景；两者共用同一背景配方。关闭时活力内容区/登录页均使用 `#EDF3FC`，沉稳均使用 `#EBF1F3`。
- 登录页暗色与亮色使用完全相同的居中单卡片布局，暗色不得保留双栏或左侧功能介绍。
- 登录页交互链接、焦点和勾选框跟随主题色；按钮/勾选框填充响应渐变开关，普通文字与语义反馈色保持独立。
- 登录输入框聚焦边框与光晕跟随主题色，错误态优先使用语义红，浏览器原生密码管理弹层不在改造范围。
- 除连接几何、圆圈可见性和主题驱动的折线颜色外，不改变图表数据、线宽、阴影、面积填充、标签、网格、图例、坐标轴、tooltip、动画或请求流程。
- 成功绿、警告橙/黄、错误红及饼图、柱图等业务分类色保持独立。
- 每个任务按 TDD 顺序执行：先补失败测试，确认失败原因正确，再写最小实现，再运行聚焦测试。
- 每个任务只提交本任务文件；最终任务再运行全量测试和打包。

---

## Task 1: Model and persist the complete preference record

**Files:**

- Modify: `src/auto_check/app/storage_user_interface_preferences.py`
- Modify: `tests/test_user_interface_preferences.py`
- Modify if required: `tests/mysql_config_test_support.py`
- Modify: `tests/test_security.py`

### Step 1: Write failing storage tests

Replace integer-only expectations with an immutable value object and add cases for missing rows, malformed fields, complete upsert, user isolation, strict validation and unchanged pruning.

```python
@dataclass(frozen=True, slots=True)
class UserInterfacePreferences:
    radius_px: int = 4
    theme_gradient_enabled: bool = True
    line_chart_style: str = "straight"
```

Malformed stored values fall back per field, so one bad field does not discard two valid fields. Save validation must reject non-`bool` gradients and styles outside `straight/smooth`.

Run `python -m pytest -q tests/test_user_interface_preferences.py tests/test_security.py`.

Expected: FAIL because storage still returns and saves only an integer.

### Step 2: Extend the table and constants

Add:

```python
DEFAULT_THEME_GRADIENT_ENABLED = True
DEFAULT_LINE_CHART_STYLE = "straight"
LINE_CHART_STYLES = frozenset({"straight", "smooth"})
```

Add both new columns to the SQLAlchemy `USER_INTERFACE_PREFERENCES` table.

### Step 3: Implement the new storage contract

```python
def load_user_interface_preferences(
    connection: Connection,
    user_id: str,
) -> UserInterfacePreferences: ...

def save_user_interface_preferences(
    connection: Connection,
    user_id: str,
    *,
    radius_px: int,
    theme_gradient_enabled: bool,
    line_chart_style: str,
) -> UserInterfacePreferences: ...
```

On load, accept only integer `0/1` from MySQL for the gradient and convert to Python `bool`; do not use generic truthiness. On save, require `type(theme_gradient_enabled) is bool`, validate the style whitelist, and upsert all three fields plus `updated_at` atomically.

If the in-memory fixture needs changes, keep them generic to row shape; retain the existing `user_id` primary-key behavior.

### Step 4: Verify and commit

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_security.py
git diff --check
```

Stage only changed files from this task and commit as `feat: persist complete user appearance preferences`.

---

## Task 2: Expand the authenticated interface-settings API

**Files:**

- Modify: `src/auto_check/app/server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_security.py`

### Step 1: Write failing API tests

Update GET/POST expectations to:

```json
{
  "settings": {
    "radius_px": 4,
    "theme_gradient_enabled": true,
    "line_chart_style": "straight"
  }
}
```

Add parameterized rejection tests for missing fields, gradient values `0`, `1`, `"true"`, `null`, line styles `"curve"`, `"STRAIGHT"`, `1`, `null`, and all existing invalid radius values. Keep tests proving a submitted `user_id` cannot modify another user and admin/operator settings remain isolated.

Run `python -m pytest -q tests/test_server.py tests/test_security.py`.

Expected: FAIL because the endpoint handles only `radius_px`.

### Step 2: Return and save the complete record

Serialize all three fields on GET and POST, require all three in POST, use `type(value) is bool`, validate the shared style whitelist, derive `user_id` only from the authenticated session, and keep one transaction for the upsert.

Use a small serializer to avoid response drift:

```python
def _serialize_interface_preferences(value: UserInterfacePreferences) -> dict[str, object]:
    return {
        "radius_px": value.radius_px,
        "theme_gradient_enabled": value.theme_gradient_enabled,
        "line_chart_style": value.line_chart_style,
    }
```

Do not add a new endpoint or partial-update semantics.

### Step 3: Verify and commit

Run:

```powershell
python -m pytest -q tests/test_server.py tests/test_security.py tests/test_user_interface_preferences.py
git diff --check
```

Commit the three task files as `feat: expose appearance preferences through settings api`.

---

## Task 3: Add the incremental MySQL appearance-preference schema

**Files:**

- Create: `sql/app_storage/mysql/005_user_appearance_preferences.sql`
- Modify: `src/auto_check/app/app_database.py`
- Modify: `scripts/export_sqlite_to_mysql.py`
- Modify: `tests/test_user_interface_preferences.py`
- Modify: `tests/test_app_database.py`
- Modify: `tests/test_sqlite_to_mysql_export.py`

### Step 1: Write failing schema-contract tests

Extend the schema tests to require a guarded `005_user_appearance_preferences.sql` that:

- only alters `user_interface_preferences`;
- adds `theme_gradient_enabled TINYINT(1) NOT NULL DEFAULT 1`;
- adds `line_chart_style VARCHAR(16) NOT NULL DEFAULT 'straight'`;
- constrains the values to `0/1` and `straight/smooth`;
- contains no DML, table recreation, foreign key, database creation or schema-version mutation;
- safely skips columns/constraints already present by checking `information_schema`.

Update the expected schema:

```python
assert EXPECTED_APP_SCHEMA["user_interface_preferences"] == frozenset(
    {
        "user_id",
        "radius_px",
        "theme_gradient_enabled",
        "line_chart_style",
        "updated_at",
    }
)
assert len(EXPECTED_APP_SCHEMA) == 36
```

Update the exporter test to require post-migration order `002`, `003`, `004`, `005`.

Run `python -m pytest -q tests/test_user_interface_preferences.py tests/test_app_database.py tests/test_sqlite_to_mysql_export.py`.

Expected: FAIL because script `005` and the new expected columns are absent.

### Step 2: Add guarded incremental DDL

Use `DATABASE()` plus `information_schema.COLUMNS` / `information_schema.TABLE_CONSTRAINTS` guards and prepared `ALTER TABLE` statements. The resulting schema must be equivalent to:

```sql
ALTER TABLE `user_interface_preferences`
  ADD COLUMN `theme_gradient_enabled` TINYINT(1) NOT NULL DEFAULT 1
    COMMENT '是否启用主题渐变：1启用，0关闭' AFTER `radius_px`,
  ADD COLUMN `line_chart_style` VARCHAR(16) NOT NULL DEFAULT 'straight'
    COMMENT '折线图风格：straight直线折线，smooth平滑曲线' AFTER `theme_gradient_enabled`,
  ADD CONSTRAINT `chk_user_interface_theme_gradient_enabled`
    CHECK (`theme_gradient_enabled` IN (0, 1)),
  ADD CONSTRAINT `chk_user_interface_line_chart_style`
    CHECK (`line_chart_style` IN ('straight', 'smooth'));
```

Do not modify `004_user_interface_preferences.sql`; it is already deployed.

### Step 3: Update validation and export ordering

Add the two columns to `EXPECTED_APP_SCHEMA["user_interface_preferences"]`, keep schema version `1` and table count `36`, and append `005` to `POST_MIGRATION_SCHEMA_SCRIPTS` after `004`.

### Step 4: Verify and commit

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_app_database.py tests/test_sqlite_to_mysql_export.py
git diff --check
```

Stage only the six listed files and commit as `feat: extend user appearance preference schema`.

---

## Task 4: Add WYSIWYG controls and extend the frontend state machine

**Files:**

- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

### Step 1: Write failing DOM and state tests

Require:

- one native checkbox/switch for `使用主题渐变`;
- a radiogroup with exactly `straight` and `smooth`, with `straight` first and selected by default;
- no color input, HEX input or chart tension control;
- strict GET/POST parsing of all three preference fields;
- one POST payload containing all three fields;
- dirty state when any field differs from the saved snapshot;
- reset defaults `{ radius_px: 4, theme_gradient_enabled: true, line_chart_style: "straight" }`;
- stale GET/POST results remain invalidated across edits, saves, logout and user switch;
- failed save keeps the visible draft but not the saved snapshot;
- leaving the page restores all three saved values.
- the last successful gradient display cache is available to `login.html`; failed loads, saves or logins do not update it.

Run `python -m pytest -q tests/test_web_static.py -k "interface or preference"`.

Expected: FAIL because only the radius control/state exists.

### Step 2: Add accessible controls to the existing card

Keep the current card and save/reset buttons. Add an accessible native switch and a two-option segmented radiogroup:

```html
<input id="interfaceThemeGradientToggle" type="checkbox" role="switch" checked>
<div id="interfaceLineChartStyle" role="radiogroup" aria-label="折线图风格">
  <label><input type="radio" name="interfaceLineChartStyle" value="straight" checked>直线折线</label>
  <label><input type="radio" name="interfaceLineChartStyle" value="smooth">平滑曲线</label>
</div>
```

Use scoped styles, preserve keyboard/focus accessibility, consume `--ui-radius`, and verify both themes and dark mode.

### Step 3: Extend the existing race-safe state machine

Preserve request IDs, auth revision, edit revision, server mutation revision and abort behavior. Track saved/draft values for:

```javascript
const DEFAULT_INTERFACE_PREFERENCES = Object.freeze({
  radiusPx: 4,
  themeGradientEnabled: true,
  lineChartStyle: "straight",
});
```

Strictly parse the response. On input, update the draft, apply the visual preview, increment `editRevision`, and render the saved/unsaved status. Update display caches only after successful authenticated GET/POST; invalidate them on user change. Do not move theme selection or dark-mode preference into this API.

### Step 4: Verify and commit

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "interface or preference"
git diff --check
```

Commit the four task files as `feat: add appearance controls to interface settings`.

---

## Task 5: Consolidate fixed theme colors, the gradient switch, and app background

**Files:**

- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

### Step 1: Write failing token and scope tests

Assert the exact fixed solid/gradient values, `data-theme-gradient="true/false"`, absence of user color controls, and scoped high-emphasis selectors. Assert semantic status colors and non-line categorical chart colors remain independent. Require the application shell/content backdrop to consume the approved low-emphasis page-background token and switch through the same root attribute.

Run `python -m pytest -q tests/test_web_static.py -k "theme or gradient or semantic"`.

Expected: FAIL until the new tokens and state exist.

### Step 2: Separate solid-color and background-fill tokens

Use a solid token for text/borders/focus and a fill token for backgrounds:

```css
:root {
  --theme-accent-solid: #3b82f6;
  --theme-accent-gradient: linear-gradient(135deg, #3b82f6 0%, #06b6d4 52%, #8b5cf6 100%);
  --theme-accent-fill: var(--theme-accent-gradient);
}

:root[data-theme-gradient="false"] {
  --theme-accent-fill: var(--theme-accent-solid);
}
```

Override the solid/gradient tokens for the calm theme with `#25676E` and the approved teal gradient.

Add separate page-background tokens instead of reusing the full button fill:

```css
--theme-page-background-solid: #edf3fc;
--theme-page-background-gradient: /* vitality blue/cyan/purple layers at 4%–7% */;
```

The login page must reuse the exact same theme-stop strength and solid background as the application content area: vitality `4%–7%` with solid `#EDF3FC`, calm `5%–8%` with solid `#EBF1F3`. The vitality purple stop stays at the lower end of its range. Dark content/login backgrounds also share one recipe: vitality solid `#121D36`, calm solid `#101C2E`, with the same reduced theme-stop strength when gradient mode is enabled.

### Step 3: Migrate only approved high-emphasis surfaces

Apply the fill token to active primary navigation, primary/confirm buttons, active tabs/segments, non-semantic selected filters, non-semantic module icons and existing decorative accents. Do not touch semantic badges, report-process category colors, categorical chart series, error banners or destructive buttons. Preserve dimensions, radius, pointer behavior and disabled behavior.

Apply the page-background token once at the root/application-shell layer behind `.main-content`; do not duplicate it per business page. Keep cards, tables and modal surfaces unchanged.

### Step 4: Apply preview state independently

```javascript
function applyThemeGradient(enabled) {
  document.documentElement.dataset.themeGradient = enabled ? "true" : "false";
}
```

Call it for load, live draft, reset, discard and auth reset. Theme or dark-mode switching must not overwrite the attribute. Updating the attribute must immediately change accent surfaces, application background and chart redraw behavior.

### Step 5: Verify and commit

Run `python -m pytest -q tests/test_web_static.py -k "theme or gradient or semantic or interface"` and `git diff --check`.

Commit the three task files as `feat: add fixed theme gradient preference`.

---

## Task 6: Route line charts through selected geometry and theme color

**Files:**

- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

### Step 1: Write failing chart tests

Add harness/static tests proving:

- default style is `straight`, and only `straight/smooth` normalize successfully;
- straight paths use `moveTo/lineTo`, smooth paths delegate to the existing `smoothCurveThrough(..., 0.35, bounds)`;
- the single-series area fill and stroke share the same selected geometry;
- the multi-series chart uses the shared tracer for every series;
- straight mode skips visible point circles, while smooth mode draws them;
- point coordinates remain available for value labels and tooltip hit testing in straight mode;
- empty and single-point series remain valid;
- theme/gradient/style changes redraw current charts without refetching data;
- line, legend, label and smooth-point colors come from the current theme palette.

Run `python -m pytest -q tests/test_web_static.py -k "chart or curve or line_style"`.

Expected: FAIL because current charts call `smoothCurveThrough` and hard-coded series colors directly.

### Step 2: Add one shared path tracer

```javascript
const DEFAULT_LINE_CHART_STYLE = "straight";
const LINE_CHART_STYLES = new Set(["straight", "smooth"]);

function normalizeLineChartStyle(value) {
  return LINE_CHART_STYLES.has(value) ? value : DEFAULT_LINE_CHART_STYLE;
}

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

Do not change the existing smoothing algorithm.

### Step 3: Add a shared Canvas theme palette

Read the current theme and `data-theme-gradient`. For gradient mode create a `CanvasGradient` across the plot bounds with the exact three approved color stops; for solid mode return the fixed theme color. For multi-series charts derive deterministic deep/light or opacity variants from the same theme family. Keep legend swatches and numeric labels aligned with the corresponding series.

Do not use CSS gradient strings as Canvas stroke values. Build the `CanvasGradient` with `ctx.createLinearGradient(...)` and `addColorStop(...)`.

### Step 4: Replace direct chart drawing branches

In `drawGlassChart`, use the tracer for both area-fill and visible stroke. In `drawGlassMultiMetricChart`, use it for each series. Draw point circles only when the normalized style is `smooth`; keep the existing point arrays and hit radii for labels/tooltips in both styles.

Keep stroke widths, caps/joins, shadows, fill opacity, axes, tooltip content and animation timing unchanged.

### Step 5: Wire WYSIWYG redraw and verify

Both the line-style control and gradient control call `refreshHomeChartsForTheme()`, which already redraws `renderChart()` and `renderTrendChart()`. Do not save until the user clicks “保存界面设置”.

Run `python -m pytest -q tests/test_web_static.py -k "chart or curve or line_style or theme or interface"` and `git diff --check`.

Commit the two task files as `feat: add themed selectable line chart geometry`.

---

## Task 7: Apply the login background and unify light/dark layout

**Files:**

- Modify: `src/auto_check/web/login.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

### Step 1: Write failing login visual-state tests

Require:

- the pre-style bootstrap reads the most recent successful gradient cache, normalizes exact boolean values, and defaults to enabled;
- the login root receives `data-theme-gradient="true/false"` before CSS renders;
- vitality and calm login backgrounds reuse the application-content background recipe and strength; light solid values are `#EDF3FC` and `#EBF1F3`;
- decorative `.deco` colors derive from the current theme and are hidden when gradient is disabled;
- failed login never updates interface-preference caches;
- dark mode contains no `grid-template-columns: 1fr 1fr`, `max-width: 860px`, dark-only `min-height`, dark-only panel padding, or `.left-panel { display: flex; }` override;
- both modes share the same container/card geometry and form order;
- the dark logo, if used, occupies the same brand slot and dimensions as the light logo.
- login links, input caret/focus, password-toggle focus and checked checkbox consume login accent tokens; normal labels and semantic feedback do not.
- username/password/confirm-password focus rings use the current theme at roughly `14%` outer-ring and `10%` soft-shadow opacity; invalid and disabled states keep semantic/neutral precedence.

Run `python -m pytest -q tests/test_web_static.py -k "login and (theme or gradient or layout)"`.

Expected: FAIL because the current dark login uses a two-column layout and the login background does not read the gradient preference.

### Step 2: Bootstrap the last successful visual preference

Extend the existing pre-style radius bootstrap in `login.html` to also read the last successful gradient display cache and the most recently active user's local theme selection. Set root data attributes before `<style>` to avoid a flash. Do not call the protected interface-settings API before authentication.

Only successful authenticated GET/POST in `app.js` may update the gradient display cache. Preserve the current rule that login failure cannot contaminate it.

### Step 3: Add login background tokens

Declare login equivalents for the main app tokens, but reuse the exact application-content recipes rather than separate login values. Gradient mode uses vitality `4%–7%` and calm `5%–8%`; light solid mode uses vitality `#EDF3FC` and calm `#EBF1F3`; dark solid mode uses vitality `#121D36` and calm `#101C2E`. Dark gradient mode uses the same strength and theme family as the corresponding application backdrop. When gradient is disabled, hide the decorative background blobs so no unrelated pink/green gradient remains.

Add `--login-accent-text` for links/caret/focus and `--login-accent-fill` for the login button and checked checkbox. Accent fill follows the gradient switch; accent text always uses a readable solid theme color. In dark mode derive a lighter same-hue foreground when required for contrast. Do not apply accent text to headings, field labels, helper text, or semantic status messages.

Use the solid accent text token for input border/caret and low-alpha derived values for the focus ring/shadow. Apply the rule consistently to username, password and setup confirmation fields, including autofill focus. Error selectors must override the theme ring with semantic red; disabled fields must not show the accent glow. Do not attempt to style the browser-owned saved-password popup.

### Step 4: Remove dark-only geometry

Keep the light single-card geometry as the shared layout. Remove dark selectors that change display, grid, size, padding, margin, positioning or content visibility. Keep `.left-panel` out of layout in both modes. Render light/dark logo resources in the same `.light-brand` slot and switch only their visibility/resource without changing geometry.

Dark selectors may change only color, background, border color, shadow color, logo resource visibility and browser autofill paint.

### Step 5: Verify and commit

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "login or interface or theme or gradient"
git diff --check
```

Commit the three task files as `feat: unify login theme layout and background`.

---

## Task 8: Close the remaining user-management and data-source radius gaps

**Files:**

- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

### Step 1: Write failing selector tests

Assert these five selectors consume `var(--ui-radius)` in the existing final radius-override block:

```css
#page-users .user-filter-pill,
.user-modal .user-role-card,
.user-modal .user-role-card-icon,
.user-modal .user-enable-row,
#configModal .modal-section
```

Also assert the override does not include `.user-enable-switch` or its thumb, because the switch track/circle retain their dedicated shape. Assert the data-source `.modal-section` keeps `overflow: hidden` and `.modal-section-header` remains nested inside it, so the “数据库连接” title bar is clipped by the outer radius instead of receiving an independent radius.

Run `python -m pytest -q tests/test_web_static.py -k "radius and user"`.

Expected: FAIL because the filter pill is fixed at `999px`, the role/enable surfaces are fixed at `12px`/`10px`, and the data-source connection group is fixed at `8px`.

### Step 2: Add the selectors to the established radius override

Use the existing rule:

```css
border-radius: var(--ui-radius) !important;
```

Do not alter DOM, spacing, color, role selection, enabled-switch state, disabled state, filter data attributes, data-source form behavior or event listeners. The user selector scope must cover both new-user and edit-user modes because they share the same modal; `#configModal .modal-section` must cover both new-data-source and edit-data-source modes. Keep the section header square on its lower edge and let the outer container perform corner clipping.

### Step 3: Verify and commit

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "radius or user or modal"
git diff --check
```

Commit the two task files as `fix: apply radius to omitted interface controls`.

---

## Task 9: Update release documentation, verify, and package

**Files:**

- Modify: `README.md`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `docs/intranet-production-deployment.zh-CN.md`
- Modify: `docs/mysql-application-storage.zh-CN.md`
- Modify: `src/auto_check/web/app.js` only for the concise in-app update log
- Modify: affected documentation/static tests as required
- Refresh: `dist/auto-check.exe`

### Step 1: Update release-facing documentation

Document fixed theme colors, one global gradient switch, application/login backgrounds, unified light/dark login layout, straight/smooth chart style with straight as default, theme-driven line colors, straight-mode hidden point circles, the two user-management radius gaps, per-user cross-device persistence, and `005` deployment order.

Keep the in-app changelog concise:

```text
新增用户级主题渐变与折线图风格设置。
系统优化及BUG修复。
```

Document that the schema still has 36 tables and schema version `1`; upgrade order is stop app → back up database → run `005` → deploy application → verify two users independently.

### Step 2: Run the full test suite

Run `python -m pytest -q`.

Expected: PASS with no feature-specific failures.

### Step 3: Review the final diff

Run:

```powershell
git status --short
git diff --check
git diff --stat
```

Exclude unrelated files, credentials, database data and generated `build/` content.

### Step 4: Package the application

Confirm `dist\auto-check.exe` is not running, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
Get-Item dist\auto-check.exe | Select-Object FullName,Length,LastWriteTime
Get-FileHash dist\auto-check.exe -Algorithm SHA256
```

Expected: packaging exits `0`, the timestamp is current, and the final handoff records size and SHA-256.

### Step 5: Commit only release-facing changes

Stage the listed docs, concise changelog/tests, and tracked executable if repository policy requires it. Inspect the staged list before committing. Commit as `docs: document appearance preference rollout`.

---

## Final acceptance checklist

- New and upgraded users default to gradient enabled and straight line charts.
- Radius, gradient and chart style save atomically for the authenticated user only.
- Two users see independent settings across login and device changes.
- Gradient switching immediately previews both themes and all line charts; no user color picker exists.
- Gradient switching also changes the application backdrop and login background; solid mode contains no residual decorative gradient blobs.
- Before authentication, login uses the last successfully cached gradient preference and defaults safely when absent/invalid.
- Login light/dark modes share one centered single-card geometry; switching mode changes colors/resources only and does not move any content.
- Login interactive links, focus states and checked checkbox follow the current theme; normal copy and semantic feedback retain their own colors.
- Login input focus borders and soft glows follow the current theme without introducing a multicolor gradient ring.
- Straight mode uses direct line segments and hides visible point circles; labels and tooltip hits remain.
- Smooth mode keeps the current curve tension and point circles.
- Single-series fill follows the selected geometry exactly.
- Line colors follow current theme/gradient; multi-series charts remain distinguishable with same-theme derived levels.
- Semantic colors and non-line categorical chart colors remain unchanged.
- User filter pills, role cards/icons, enable-row container and the data-source “数据库连接” group follow `--ui-radius`; the group header is clipped by its outer container, while the switch track/thumb retain their dedicated shape.
- Theme, dark mode, radius, gradient and chart-style drafts do not overwrite each other.
- Full pytest passes, `git diff --check` is clean, and the executable is rebuilt only after source verification.
