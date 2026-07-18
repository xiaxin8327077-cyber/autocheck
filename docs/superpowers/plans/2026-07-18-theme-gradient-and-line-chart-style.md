# Theme Gradient, Semantic Buttons, and Line Chart Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变业务功能和数据结果的前提下，为两套固定主题增加按用户保存的全局渐变开关，统一全系统按钮语义颜色，并为全系统折线图增加默认“直线折线”的“直线折线 / 平滑曲线”偏好。

**Architecture:** 扩展现有 MySQL `user_interface_preferences`、当前用户界面偏好 API 和前端异步状态机，一次性保存圆角、渐变和折线图风格。主题强调面与按钮语义通过集中 CSS 令牌管理：渐变只控制主题主要操作，危险/警示/成功保持稳定单色，通用确认弹窗显式接收操作语义。Canvas 折线图通过共享路径与颜色函数切换几何、数据点可见性和主题色；服务端是跨设备权威来源，前端缓存只用于减少初始闪变。

**Tech Stack:** Python 3.12、SQLAlchemy Core、MySQL 8、原生 HTML/CSS/JavaScript、Canvas 2D、pytest、PyInstaller。

**Approved design:** [`docs/superpowers/specs/2026-07-18-theme-color-gradient-preference-design.md`](../specs/2026-07-18-theme-color-gradient-preference-design.md)

## Global Constraints

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
- 全部按钮、图标按钮和按钮式链接必须被归入主题主要、危险、警示、成功或中性次要五类；状态型导航、筛选、分页和开关必须显式标记为状态控件，不得偶然继承操作按钮颜色。
- 普通主要操作使用当前主题色；删除/不可逆清空使用 `#BA1A1A`，停用/停止/恢复默认使用 `#B45309`，启用/完成使用 `#137333`；暗色对应值为 `#FFB4AB`、`#FBBF24`、`#6DDB9C`。
- 按钮语义决定色相，操作层级决定使用实心背景还是文字/图标/描边；禁用态统一使用中性灰且优先级最高。
- 渐变开关只影响主题主要按钮；危险、警示、成功按钮不生成渐变，悬浮、按下和焦点不得改变语义色相。
- 除连接几何、圆圈可见性和主题驱动的折线颜色外，不改变图表数据、线宽、阴影、面积填充、标签、网格、图例、坐标轴、tooltip、动画或请求流程。
- 成功绿、警告橙/黄、错误红及饼图、柱图等业务分类色保持独立。
- 每个任务按 TDD 顺序执行：先补失败测试，确认失败原因正确，再写最小实现，再运行聚焦测试。
- 每个任务只提交本任务文件；最终任务再运行全量测试和打包。

## File responsibility map

- `src/auto_check/app/storage_user_interface_preferences.py`：界面偏好值对象、校验和按用户持久化。
- `src/auto_check/app/server.py`：当前认证用户界面偏好 GET/POST 契约。
- `sql/app_storage/mysql/005_user_appearance_preferences.sql`：现有 MySQL 表的增量字段与约束。
- `src/auto_check/web/index.html`：界面设置控件、静态按钮语义标记和弹窗结构。
- `src/auto_check/web/styles.css`：主题、背景、按钮语义、圆角和暗色模式令牌与选择器。
- `src/auto_check/web/app.js`：偏好状态机、确认弹窗语义、动态按钮标记和图表绘制。
- `src/auto_check/web/login.html`：认证前偏好启动、统一登录布局和登录主题交互。
- `tests/test_user_interface_preferences.py`、`tests/test_server.py`、`tests/test_security.py`：存储/API/用户隔离契约。
- `tests/test_web_static.py`：前端状态、按钮语义清单、主题、登录、图表和圆角静态契约。
- `README.md` 与部署文档：用户说明、升级顺序和上线验收。

---

## Task 1: Model and persist the complete preference record

**Files:**

- Modify: `src/auto_check/app/storage_user_interface_preferences.py`
- Modify: `tests/test_user_interface_preferences.py`
- Modify if required: `tests/mysql_config_test_support.py`
- Modify: `tests/test_security.py`

**Interfaces:**

- Consumes: SQLAlchemy `Connection`, the existing `USER_INTERFACE_PREFERENCES` table and authenticated user IDs supplied by callers.
- Produces: immutable `UserInterfacePreferences`; `load_user_interface_preferences(connection, user_id)` and keyword-only `save_user_interface_preferences(connection, user_id, radius_px, theme_gradient_enabled, line_chart_style)` used by Task 2.

- [ ] **Step 1: Write failing storage tests**

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

- [ ] **Step 2: Extend the table and constants**

Add:

```python
DEFAULT_THEME_GRADIENT_ENABLED = True
DEFAULT_LINE_CHART_STYLE = "straight"
LINE_CHART_STYLES = frozenset({"straight", "smooth"})
```

Add both new columns to the SQLAlchemy `USER_INTERFACE_PREFERENCES` table.

- [ ] **Step 3: Implement the new storage contract**

Implement `load_user_interface_preferences(connection: Connection, user_id: str) -> UserInterfacePreferences` and `save_user_interface_preferences(connection: Connection, user_id: str, *, radius_px: int, theme_gradient_enabled: bool, line_chart_style: str) -> UserInterfacePreferences` with the existing SQLAlchemy select/upsert pattern.

On load, accept only integer `0/1` from MySQL for the gradient and convert to Python `bool`; do not use generic truthiness. On save, require `type(theme_gradient_enabled) is bool`, validate the style whitelist, and upsert all three fields plus `updated_at` atomically.

If the in-memory fixture needs changes, keep them generic to row shape; retain the existing `user_id` primary-key behavior.

- [ ] **Step 4: Verify and commit**

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

**Interfaces:**

- Consumes: the Task 1 value object and load/save functions plus the existing authenticated session.
- Produces: `/api/settings/interface` GET/POST response `{radius_px, theme_gradient_enabled, line_chart_style}` consumed by Task 4.

- [ ] **Step 1: Write failing API tests**

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

- [ ] **Step 2: Return and save the complete record**

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

- [ ] **Step 3: Verify and commit**

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

**Interfaces:**

- Consumes: Task 1 column definitions and the existing post-migration script runner.
- Produces: idempotent `005_user_appearance_preferences.sql` and updated expected-schema/export order required before deploying Tasks 1–2.

- [ ] **Step 1: Write failing schema-contract tests**

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

- [ ] **Step 2: Add guarded incremental DDL**

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

- [ ] **Step 3: Update validation and export ordering**

Add the two columns to `EXPECTED_APP_SCHEMA["user_interface_preferences"]`, keep schema version `1` and table count `36`, and append `005` to `POST_MIGRATION_SCHEMA_SCRIPTS` after `004`.

- [ ] **Step 4: Verify and commit**

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

**Interfaces:**

- Consumes: the Task 2 API response and existing radius preference state machine.
- Produces: `DEFAULT_INTERFACE_PREFERENCES`, saved/draft state for all three fields, WYSIWYG controls and successful-display cache consumed by Tasks 5, 7 and 8.

- [ ] **Step 1: Write failing DOM and state tests**

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

- [ ] **Step 2: Add accessible controls to the existing card**

Keep the current card and save/reset buttons. Add an accessible native switch and a two-option segmented radiogroup:

```html
<input id="interfaceThemeGradientToggle" type="checkbox" role="switch" checked>
<div id="interfaceLineChartStyle" role="radiogroup" aria-label="折线图风格">
  <label><input type="radio" name="interfaceLineChartStyle" value="straight" checked>直线折线</label>
  <label><input type="radio" name="interfaceLineChartStyle" value="smooth">平滑曲线</label>
</div>
```

Use scoped styles, preserve keyboard/focus accessibility, consume `--ui-radius`, and verify both themes and dark mode.

- [ ] **Step 3: Extend the existing race-safe state machine**

Preserve request IDs, auth revision, edit revision, server mutation revision and abort behavior. Track saved/draft values for:

```javascript
const DEFAULT_INTERFACE_PREFERENCES = Object.freeze({
  radiusPx: 4,
  themeGradientEnabled: true,
  lineChartStyle: "straight",
});
```

Strictly parse the response. On input, update the draft, apply the visual preview, increment `editRevision`, and render the saved/unsaved status. Update display caches only after successful authenticated GET/POST; invalidate them on user change. Do not move theme selection or dark-mode preference into this API.

- [ ] **Step 4: Verify and commit**

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

**Interfaces:**

- Consumes: `themeGradientEnabled` draft/saved state from Task 4 and the existing theme/dark attributes.
- Produces: `--theme-accent-solid`, `--theme-accent-gradient`, `--theme-accent-fill`, shared page-background tokens and `applyThemeGradient(enabled)` consumed by Tasks 6–8.

- [ ] **Step 1: Write failing token and scope tests**

Assert the exact fixed solid/gradient values, `data-theme-gradient="true/false"`, absence of user color controls, and scoped high-emphasis selectors. Assert semantic status colors and non-line categorical chart colors remain independent. Require the application shell/content backdrop to consume the approved low-emphasis page-background token and switch through the same root attribute.

Run `python -m pytest -q tests/test_web_static.py -k "theme or gradient or semantic"`.

Expected: FAIL until the new tokens and state exist.

- [ ] **Step 2: Separate solid-color and background-fill tokens**

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

- [ ] **Step 3: Migrate only approved high-emphasis surfaces**

Apply the fill token to active primary navigation, ordinary primary/confirm buttons, active tabs/segments, non-semantic selected filters, non-semantic module icons and existing decorative accents. Defer dangerous, warning, success and mixed-use button mapping to Task 6. Do not touch semantic badges, report-process category colors, categorical chart series or error banners. Preserve dimensions, radius, pointer behavior and disabled behavior.

Apply the page-background token once at the root/application-shell layer behind `.main-content`; do not duplicate it per business page. Keep cards, tables and modal surfaces unchanged.

- [ ] **Step 4: Apply preview state independently**

```javascript
function applyThemeGradient(enabled) {
  document.documentElement.dataset.themeGradient = enabled ? "true" : "false";
}
```

Call it for load, live draft, reset, discard and auth reset. Theme or dark-mode switching must not overwrite the attribute. Updating the attribute must immediately change accent surfaces, application background and chart redraw behavior.

- [ ] **Step 5: Verify and commit**

Run `python -m pytest -q tests/test_web_static.py -k "theme or gradient or semantic or interface"` and `git diff --check`.

Commit the three task files as `feat: add fixed theme gradient preference`.

---

## Task 6: Normalize semantic button colors across static and dynamic UI

**Files:**

- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes: `--theme-accent-solid`, `--theme-accent-fill`, `data-theme-gradient` and dark-mode tokens from Task 5.
- Produces: button tokens `--action-danger`, `--action-warning`, `--action-success` and matching `--on-*`/soft variants; explicit `data-action-tone` / `data-action-variant` mappings; backward-compatible `showConfirm(title, message, options)` with `options.tone`.

- [ ] **Step 1: Write the failing button-inventory and token tests**

Add a small tag auditor to `tests/test_web_static.py` so every literal `<button>` in `index.html` and every button template in `app.js` is either an action button or an explicitly identified state control:

```python
import re

ACTION_TONES = {"primary", "danger", "warning", "success", "neutral"}
ACTION_BASE_CLASSES = {
    "btn-primary",
    "btn-confirm-primary",
    "btn-danger",
    "btn-stop",
    "btn-outline",
    "pbc-btn--primary",
    "pbc-btn--success",
    "pbc-btn--secondary",
    "pbc-btn--outline",
    "pbc-btn--ghost",
}

def _attr(tag: str, name: str) -> str:
    match = re.search(rf'\b{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else ""

def assert_button_is_classified(tag: str) -> None:
    tone_match = re.search(r'\bdata-action-tone="([^"]+)"', tag)
    if tone_match:
        assert tone_match.group(1) in ACTION_TONES
        return
    classes = set(re.findall(r'[A-Za-z0-9_-]+', _attr(tag, "class")))
    assert classes & ACTION_BASE_CLASSES or 'data-control-role=' in tag, tag
```

Require exact light tokens `#BA1A1A`, `#B45309`, `#137333`, dark tokens `#FFB4AB`, `#FBBF24`, `#6DDB9C`, and the following priority behaviors:

- `.btn-primary`, normal `.btn-confirm-primary` and `.pbc-btn--primary` use the theme fill.
- `.btn-danger` and `data-action-tone="danger"` use danger tokens.
- `.btn-stop` and `data-action-tone="warning"` use warning tokens, not `--error`.
- `.pbc-btn--success` and `data-action-tone="success"` use success tokens.
- `.btn-outline` and neutral tool actions use neutral tokens unless an explicit semantic tone overrides them.
- gradient-off selectors do not replace danger/warning/success colors.
- disabled selectors remove gradients, semantic shadows and pointer feedback and use neutral disabled colors.

Run `python -m pytest -q tests/test_web_static.py -k "button or action_tone or semantic"`.

Expected: FAIL because button colors are inconsistent, `btn-stop` is red, mixed-use button classes lack explicit tones, and `showConfirm` cannot receive an operation tone.

- [ ] **Step 2: Add centralized semantic-action tokens and variants**

Add the exact light tokens at `:root`:

```css
--action-danger: #ba1a1a;
--on-action-danger: #ffffff;
--action-warning: #b45309;
--on-action-warning: #ffffff;
--action-success: #137333;
--on-action-success: #ffffff;
--action-neutral: var(--on-surface-variant);
--action-neutral-border: var(--outline-variant);
--action-danger-soft: color-mix(in srgb, var(--action-danger) 8%, transparent);
--action-warning-soft: color-mix(in srgb, var(--action-warning) 8%, transparent);
--action-success-soft: color-mix(in srgb, var(--action-success) 8%, transparent);
```

Override dark mode with:

```css
--action-danger: #ffb4ab;
--on-action-danger: #690005;
--action-warning: #fbbf24;
--on-action-warning: #422006;
--action-success: #6ddb9c;
--on-action-success: #003919;
```

Use explicit tone/variant custom-property mappings; do not add a broad unscoped `button` color rule:

```css
[data-action-tone="danger"] {
  --button-action: var(--action-danger);
  --button-on-action: var(--on-action-danger);
  --button-action-soft: var(--action-danger-soft);
}

[data-action-tone][data-action-variant="solid"] {
  color: var(--button-on-action);
  background: var(--button-action);
  border-color: var(--button-action);
}

[data-action-tone][data-action-variant="weak"] {
  color: var(--button-action);
  background: transparent;
  border-color: var(--button-action);
}

[data-action-tone][data-action-variant="weak"]:hover {
  background: var(--button-action-soft);
}
```

Provide equivalent mappings for warning, success and neutral. Keep theme primary solid buttons on `--theme-accent-fill`; their gradient-off state switches to `--theme-accent-solid`. Focus rings derive from the current `--button-action` or theme solid token. Hover/active may change brightness, opacity, shadow or transform but never hue. Disabled styling wins over tone selectors and uses neutral gray.

- [ ] **Step 3: Classify static controls and mixed-use button families**

Audit all 97 literal buttons in `index.html`. Existing base classes can supply the default role, but mixed-use families must receive explicit attributes. Apply these deterministic mappings:

- `report-nav-action-button`: “立即处理” is `primary/solid`; “查看” is `neutral/weak`.
- `exportBtn`, user exports, downloads, rules documents, history/record entry, refresh, edit, test connection, cancel, back and close actions are `neutral/weak`; change `exportBtn` away from `.btn-primary`.
- new/add, login, ordinary save/confirm, start, next, retry and import actions are `primary/solid`; update currently outlined “新增链路”“添加”“保存表字段配置” buttons accordingly.
- `stopRunBtn` and `flowCancelBtn` are `warning`; reset-interface, reset-default-settings and schema-overwrite initialization actions are `warning/weak`.
- `pbcClearFilesBtn` and irreversible clear/delete actions are `danger`; list-row delete remains `danger/weak`.
- `pbcFinishBtn`, enable/re-enable and explicit complete actions are `success`; `dbValidationDownloadBtn` is a neutral download, not a success action.
- navigation group toggles, theme/dark toggles, active filters, pagination, accordion headers and the user enable switch use `data-control-role="navigation|toggle|filter|pagination|disclosure|switch"`; active selection continues to use theme tokens. The user enable switch remains success-colored when on and neutral when off, and retains its dedicated track/thumb shape.

Perform the same audit for HTML templates in `app.js`, including history/config/user row actions. An explicit `data-action-tone` overrides a neutral base class; do not change element IDs, datasets used by business code, click handlers, labels or event delegation selectors.

- [ ] **Step 4: Make confirmation tone explicit and backward compatible**

Add a strict normalizer and optional third parameter without breaking existing two-argument calls:

```javascript
const CONFIRM_ACTION_TONES = new Set(["primary", "danger", "warning", "success"]);

function normalizeConfirmActionTone(value) {
  return CONFIRM_ACTION_TONES.has(value) ? value : "primary";
}

function showConfirm(title, message, options = {}) {
  return new Promise((resolve) => {
    const tone = normalizeConfirmActionTone(options.tone);
    const modal = document.getElementById("confirmModal");
    const titleEl = document.getElementById("confirmTitle");
    const messageEl = document.getElementById("confirmMessage");
    const okBtn = document.getElementById("confirmOk");
    const cancelBtn = document.getElementById("confirmCancel");

    titleEl.textContent = title;
    messageEl.textContent = message;
    okBtn.dataset.actionTone = tone;
    okBtn.dataset.actionVariant = "solid";
    modal.hidden = false;

    const cleanup = () => {
      modal.classList.add("closing");
      setTimeout(() => {
        modal.hidden = true;
        modal.classList.remove("closing");
        okBtn.dataset.actionTone = "primary";
        okBtn.dataset.actionVariant = "solid";
      }, 200);
    };

    okBtn.onclick = () => {
      cleanup();
      resolve(true);
    };

    cancelBtn.onclick = () => {
      cleanup();
      resolve(false);
    };
  });
}
```

Update call sites by meaning, not by Chinese text matching:

- delete user/history/data source and clear-all history: `{ tone: "danger" }`;
- disable user, stop/cancel execution, overwrite initialization and restore defaults: `{ tone: "warning" }`;
- enable user and mark-complete confirmation: `{ tone: "success" }`;
- report-date change, logout, ordinary import/save and other confirmations without a semantic risk: explicit or default `{ tone: "primary" }`.

For the manual-action branch, compute the tone directly from `isCancel`; do not infer it from the rendered title. Reset the confirm button to primary during cleanup so stale tone cannot leak into the next dialog. Do not change confirmation wording, Promise resolution, timing, API requests or error handling.

- [ ] **Step 5: Verify interaction, contrast and no functional drift**

Extend tests to cover:

- solid variants use semantic backgrounds with the matching high-contrast `on-color`; weak variants use semantic text/icon/border and at most the approved `8%` soft background;
- danger/warning/success colors remain unchanged when `data-theme-gradient` switches;
- vitality/calm and light/dark combinations keep the same semantic role;
- disabled and loading buttons cannot show hover lift or duplicate-click affordance;
- `showConfirm` defaults to primary, rejects unknown tone to primary, applies each valid tone, and clears stale tone;
- destructive, warning and success call sites pass the correct explicit option;
- button IDs, click handlers, request methods and payload code are unchanged.

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "button or action_tone or semantic or confirm"
git diff --check
```

Expected: PASS with no button-inventory omissions.

- [ ] **Step 6: Commit**

Stage only the four task files, inspect `git diff --cached --name-only`, and commit as `feat: standardize semantic button colors`.

---

## Task 7: Route line charts through selected geometry and theme color

**Files:**

- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes: Task 4 `lineChartStyle` draft/saved state, Task 5 theme/gradient tokens and existing chart point arrays.
- Produces: `normalizeLineChartStyle`, `traceChartLine` and the Canvas theme-palette helper used by both homepage line-chart renderers.

- [ ] **Step 1: Write failing chart tests**

Add harness/static tests proving:

- default style is `straight`, and only `straight/smooth` normalize successfully;
- straight paths use `moveTo/lineTo`, smooth paths delegate to the existing `smoothCurveThrough(ctx, points, 0.35, bounds)`;
- the single-series area fill and stroke share the same selected geometry;
- the multi-series chart uses the shared tracer for every series;
- straight mode skips visible point circles, while smooth mode draws them;
- point coordinates remain available for value labels and tooltip hit testing in straight mode;
- empty and single-point series remain valid;
- theme/gradient/style changes redraw current charts without refetching data;
- line, legend, label and smooth-point colors come from the current theme palette.

Run `python -m pytest -q tests/test_web_static.py -k "chart or curve or line_style"`.

Expected: FAIL because current charts call `smoothCurveThrough` and hard-coded series colors directly.

- [ ] **Step 2: Add one shared path tracer**

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

- [ ] **Step 3: Add a shared Canvas theme palette**

Read the current theme and `data-theme-gradient`. For gradient mode create a `CanvasGradient` across the plot bounds with the exact three approved color stops; for solid mode return the fixed theme color. For multi-series charts derive deterministic deep/light or opacity variants from the same theme family. Keep legend swatches and numeric labels aligned with the corresponding series.

Do not use CSS gradient strings as Canvas stroke values. Build the `CanvasGradient` with `ctx.createLinearGradient(bounds.left, 0, bounds.right, 0)` and `gradient.addColorStop(offset, color)`.

- [ ] **Step 4: Replace direct chart drawing branches**

In `drawGlassChart`, use the tracer for both area-fill and visible stroke. In `drawGlassMultiMetricChart`, use it for each series. Draw point circles only when the normalized style is `smooth`; keep the existing point arrays and hit radii for labels/tooltips in both styles.

Keep stroke widths, caps/joins, shadows, fill opacity, axes, tooltip content and animation timing unchanged.

- [ ] **Step 5: Wire WYSIWYG redraw and verify**

Both the line-style control and gradient control call `refreshHomeChartsForTheme()`, which already redraws `renderChart()` and `renderTrendChart()`. Do not save until the user clicks “保存界面设置”.

Run `python -m pytest -q tests/test_web_static.py -k "chart or curve or line_style or theme or interface"` and `git diff --check`.

Commit the two task files as `feat: add themed selectable line chart geometry`.

---

## Task 8: Apply the login background and unify light/dark layout

**Files:**

- Modify: `src/auto_check/web/login.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes: Task 4 last-successful display cache and Task 5 theme/background values; Task 6 supplies the same theme-primary login-button behavior.
- Produces: pre-auth `data-theme-gradient`, shared light/dark single-card geometry and login accent/background tokens.

- [ ] **Step 1: Write failing login visual-state tests**

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

- [ ] **Step 2: Bootstrap the last successful visual preference**

Extend the existing pre-style radius bootstrap in `login.html` to also read the last successful gradient display cache and the most recently active user's local theme selection. Set root data attributes before `<style>` to avoid a flash. Do not call the protected interface-settings API before authentication.

Only successful authenticated GET/POST in `app.js` may update the gradient display cache. Preserve the current rule that login failure cannot contaminate it.

- [ ] **Step 3: Add login background tokens**

Declare login equivalents for the main app tokens, but reuse the exact application-content recipes rather than separate login values. Gradient mode uses vitality `4%–7%` and calm `5%–8%`; light solid mode uses vitality `#EDF3FC` and calm `#EBF1F3`; dark solid mode uses vitality `#121D36` and calm `#101C2E`. Dark gradient mode uses the same strength and theme family as the corresponding application backdrop. When gradient is disabled, hide the decorative background blobs so no unrelated pink/green gradient remains.

Add `--login-accent-text` for links/caret/focus and `--login-accent-fill` for the login button and checked checkbox. Accent fill follows the gradient switch; accent text always uses a readable solid theme color. In dark mode derive a lighter same-hue foreground when required for contrast. Do not apply accent text to headings, field labels, helper text, or semantic status messages.

Use the solid accent text token for input border/caret and low-alpha derived values for the focus ring/shadow. Apply the rule consistently to username, password and setup confirmation fields, including autofill focus. Error selectors must override the theme ring with semantic red; disabled fields must not show the accent glow. Do not attempt to style the browser-owned saved-password popup.

- [ ] **Step 4: Remove dark-only geometry**

Keep the light single-card geometry as the shared layout. Remove dark selectors that change display, grid, size, padding, margin, positioning or content visibility. Keep `.left-panel` out of layout in both modes. Render light/dark logo resources in the same `.light-brand` slot and switch only their visibility/resource without changing geometry.

Dark selectors may change only color, background, border color, shadow color, logo resource visibility and browser autofill paint.

- [ ] **Step 5: Verify and commit**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "login or interface or theme or gradient"
git diff --check
```

Commit the three task files as `feat: unify login theme layout and background`.

---

## Task 9: Close the remaining user-management, data-source and home-stat radius gaps

**Files:**

- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

**Interfaces:**

- Consumes: the existing root `--ui-radius` maintained by Task 4.
- Produces: six additional scoped radius selectors with no DOM or event changes.

- [ ] **Step 1: Write failing selector tests**

Assert these six selectors consume `var(--ui-radius)` in the existing final radius-override block:

```css
#page-users .user-filter-pill,
.user-modal .user-role-card,
.user-modal .user-role-card-icon,
.user-modal .user-enable-row,
#configModal .modal-section,
#infoModal .home-stat-modal-table-wrap
```

Also assert the override does not include `.user-enable-switch` or its thumb, because the switch track/circle retain their dedicated shape. Assert the data-source `.modal-section` keeps `overflow: hidden` and `.modal-section-header` remains nested inside it, so the “数据库连接” title bar is clipped by the outer radius instead of receiving an independent radius. Assert `.home-stat-modal-table-wrap` keeps `overflow: auto`, the nested `.home-stat-modal-table` receives no separate radius override, and the shared wrapper remains used by both `renderHomeReportPeriodTable()` and `renderHomeResultTable()` so “报送期差异数详情” and the other home-stat detail tables are covered together.

Run `python -m pytest -q tests/test_web_static.py -k "radius and (user or modal or home_stat)"`.

Expected: FAIL because the filter pill is fixed at `999px`, the role/enable surfaces are fixed at `12px`/`10px`, the data-source connection group is fixed at `8px`, and the home-stat table wrapper is fixed at `10px`.

- [ ] **Step 2: Add the selectors to the established radius override**

Use the existing rule:

```css
border-radius: var(--ui-radius) !important;
```

Do not alter DOM, spacing, color, role selection, enabled-switch state, disabled state, filter data attributes, data-source form behavior, table data, sorting, sticky headers, scrolling or event listeners. The user selector scope must cover both new-user and edit-user modes because they share the same modal; `#configModal .modal-section` must cover both new-data-source and edit-data-source modes. Keep the section header square on its lower edge and let the outer container perform corner clipping. Keep `.home-stat-modal-table-wrap` as the sole rounded/clipping surface with `overflow: auto`; do not add a second radius to `.home-stat-modal-table`.

- [ ] **Step 3: Verify and commit**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "radius or user or modal or home_stat"
git diff --check
```

Commit the two task files as `fix: apply radius to omitted interface controls`.

---

## Task 10: Update release documentation, verify, and package

**Files:**

- Modify: `README.md`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `docs/intranet-production-deployment.zh-CN.md`
- Modify: `docs/mysql-application-storage.zh-CN.md`
- Modify: `src/auto_check/web/app.js` only for the concise in-app update log
- Modify: affected documentation/static tests as required
- Refresh: `dist/auto-check.exe`

**Interfaces:**

- Consumes: completed and reviewed outputs from Tasks 1–9.
- Produces: release-facing documentation, concise in-app changelog, full verification evidence and refreshed Windows executable.

- [ ] **Step 1: Update release-facing documentation**

Document fixed theme colors, one global gradient switch, the five-role semantic button system, application/login backgrounds, unified light/dark login layout, straight/smooth chart style with straight as default, theme-driven line colors, straight-mode hidden point circles, the remaining radius gaps including home-stat detail table wrappers, per-user cross-device persistence, and `005` deployment order. README must explain that the gradient switch affects only theme-primary buttons, while danger/warning/success buttons retain stable semantic colors.

Keep the in-app changelog concise:

```text
新增用户级主题渐变与折线图风格设置。
系统优化及BUG修复。
```

Document that the schema still has 36 tables and schema version `1`; upgrade order is stop app → back up database → run `005` → deploy application → verify two users independently.

- [ ] **Step 2: Run the full test suite**

Run `python -m pytest -q`.

Expected: PASS with no feature-specific failures.

- [ ] **Step 3: Review the final diff**

Run:

```powershell
git status --short
git diff --check
git diff --stat
```

Exclude unrelated files, credentials, database data and generated `build/` content.

- [ ] **Step 4: Package the application**

Confirm `dist\auto-check.exe` is not running, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
Get-Item dist\auto-check.exe | Select-Object FullName,Length,LastWriteTime
Get-FileHash dist\auto-check.exe -Algorithm SHA256
```

Expected: packaging exits `0`, the timestamp is current, and the final handoff records size and SHA-256.

- [ ] **Step 5: Commit only release-facing changes**

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
- Every action button, icon button and button-style link is classified as theme-primary, danger, warning, success or neutral-secondary; state controls are explicitly identified and keep their selected-state behavior.
- Delete/irreversible clear is red, disable/stop/restore-default is orange, enable/complete is green, ordinary primary actions follow the current theme, and view/edit/refresh/export/cancel/back remains neutral.
- Strong semantic actions use a solid background and contrast foreground; weak row/tool actions use the same semantic hue for text/icon/border. Disabled state is neutral gray and overrides all tones.
- The gradient switch affects only theme-primary buttons. Danger, warning and success remain stable single colors in both themes; dark mode adjusts contrast without changing meaning.
- Confirmation dialogs receive an explicit action tone from the caller, default safely to primary, and never infer risk from localized button text.
- Straight mode uses direct line segments and hides visible point circles; labels and tooltip hits remain.
- Smooth mode keeps the current curve tension and point circles.
- Single-series fill follows the selected geometry exactly.
- Line colors follow current theme/gradient; multi-series charts remain distinguishable with same-theme derived levels.
- Semantic status/badge colors and non-line categorical chart colors remain independently meaningful; action buttons use the standardized semantic-action tokens from Task 6.
- User filter pills, role cards/icons, enable-row container, the data-source “数据库连接” group and home-stat detail table wrappers follow `--ui-radius`; group/table headers are clipped by their outer containers, while the switch track/thumb retain their dedicated shape and table scrolling/sticky headers remain intact.
- Theme, dark mode, radius, gradient and chart-style drafts do not overwrite each other.
- Full pytest passes, `git diff --check` is clean, and the executable is rebuilt only after source verification.
