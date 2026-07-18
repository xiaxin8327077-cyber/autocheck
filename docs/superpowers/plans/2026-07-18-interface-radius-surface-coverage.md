# Interface Radius Surface Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户截图指定的业务矩形表面、通知、结果详情和登录页全部读取现有全局圆角值，同时保持数据库为登录后唯一权威并且不改变任何业务功能。

**Architecture:** 主应用继续使用 `styles.css` 末尾现有的集中式 `--ui-radius` 覆盖层，只增加逐项核对过的精确选择器，并保持覆盖层唯一声明为 `border-radius`。登录页使用固定键 `autoCheckLastInterfaceRadius` 读取本机最后一次认证后成功获取或保存的圆角显示缓存，默认 4px；主应用成功 GET/POST 后才刷新缓存，MySQL 仍是登录后唯一权威。静态测试锁定精确选择器、显示缓存边界和 README 说明，应用内更新日志沿用已有“系统优化及BUG修复”精简口径。

**Tech Stack:** 原生 HTML/CSS/JavaScript、Python 3.12、pytest、PowerShell、PyInstaller、Windows WebView/浏览器验收。

## Global Constraints

- 仅修改界面显示，不修改 HTML 结构、JavaScript 事件、API、数据库、权限、表单值、焦点顺序或点击区域。
- 全部目标使用同一个 `--ui-radius`；范围仍为 1–15px、默认 4px、步长 1px。
- 默认太空主题、沉稳主题和暗色模式均需兼容。
- 圆形图标、头像、状态点、图表节点、普通胶囊、普通标签、进度条、复选框、单选框、滑块和 SVG 内部形状保持原样；用户明确指定的结果页 `.status-badge`、注意事项筛选标签和报送导航刷新按钮外壳除外。
- 覆盖层禁止使用全局 `button`、`table`、`[class*=item]`、`[class*=card]` 或通配后代选择器。
- `src/auto_check/web/app.js` 的 v2.1 日志保持“新增界面圆角个性化设置。”和“系统优化及BUG修复。”的精简口径，不展开本次界面细节。
- 登录页缓存只保存一个 1–15 的整数，不保存用户 ID、用户名或按用户映射；缓存读取/写入失败不得阻断登录和主应用。
- 弹窗专项检查与弹窗内部新增覆盖暂缓，等待后续弹窗改造；本计划只保留已经确认的既有弹窗基础覆盖。
- 所有编辑在 `D:\trae\autocheck\.worktrees\user-interface-radius-preferences` 独立 worktree 内完成。

---

### Task 1: 用静态测试锁定截图指定覆盖范围

**Files:**
- Modify: `tests/test_web_static.py:2874-2990`

**Interfaces:**
- Consumes: `styles.css` 中 `/* User interface radius preference: start/end */` 标记区，以及 `README_MD` 测试常量。
- Produces: 27 个新增必需选择器、特殊形状排除契约和 README 详细覆盖契约。

- [ ] **Step 1: 扩展圆角选择器契约测试**

在 `test_user_radius_override_is_semantic_and_border_radius_only()` 的必需选择器元组中加入：

```python
        "#page-report-navigation .report-nav-branch-panel",
        "#page-report-navigation .report-nav-batch",
        "#page-report-navigation .report-nav-todo",
        "#page-report-navigation .report-nav-load-state",
        ".toast",
        ".flow-toast",
        ".top-nav-status",
        ".dark-mode-toggle",
        ".history-summary-item",
        ".history-count-item",
        ".history-section",
        ".detail-block",
        ".detail-item",
        ".status-badge",
        ".flow-chain-list",
        ".flow-chain-selection-summary",
        ".flow-run-panel:last-child #flowLog",
        ".flow-history-table-wrap",
        ".db-validation-history-table-wrap",
        ".pbc-upload-area",
        "#page-settings .metric-item",
        "#page-settings .db-validation-source-row",
        ".flow-chain-config",
        ".config-item",
        "#page-settings .about-description",
        "#page-settings .about-features",
        "#page-settings .about-tech",
```

从同一测试的 `forbidden_selector` 元组中仅删除：

```python
        ".dark-mode-toggle",
```

保留 `.checkbox`、`.radio`、`.range-track`、`.range-thumb`、`svg`、`overlay` 和 `[class*=card]` 等现有禁止项。

- [ ] **Step 2: 增加 README 详细覆盖测试**

在圆角静态测试附近新增：

```python
def test_readme_documents_expanded_interface_radius_surface_coverage():
    readme = _read(README_MD)

    for text in (
        "鱼骨详情卡",
        "报送日期分组卡",
        "注意事项卡",
        "统计失败提示条",
        "右上角通知",
        "顶部版本标签",
        "暗色切换按钮外壳",
        "历史详情与执行历史表格外框",
        "结果详情分区",
        "结果状态标签",
        "一键导入上传区",
        "系统信息指标卡",
        "数据源与流程链配置行",
        "关于系统内容卡",
    ):
        assert text in readme
```

- [ ] **Step 3: 运行测试并确认先失败**

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_user_radius_override_is_semantic_and_border_radius_only tests/test_web_static.py::test_readme_documents_expanded_interface_radius_surface_coverage
```

Expected: FAIL；第一个测试报告新增选择器尚不在覆盖层，第二个测试报告 README 尚缺详细覆盖用语。

---

#### Task 1 implementation: 实现精确 CSS 覆盖并同步 README

**Files:**
- Modify: `src/auto_check/web/styles.css:12073-12142`
- Modify: `README.md:26`
- Modify: `README.md:318`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: 现有根变量 `--ui-radius` 和本任务前半段新增的失败测试契约。
- Produces: 所有截图指定矩形表面统一读取 `var(--ui-radius)`，且 README 当前功能与 v2.1 说明同步。

- [ ] **Step 1: 把精确选择器加入集中式覆盖层**

在 `/* User interface radius preference: start */` 与 `end` 之间的现有选择器列表中加入以下内容，继续共用原规则体：

```css
#page-report-navigation .report-nav-branch-panel,
#page-report-navigation .report-nav-batch,
#page-report-navigation .report-nav-todo,
#page-report-navigation .report-nav-load-state,
.toast,
.flow-toast,
.top-nav-status,
.dark-mode-toggle,
.history-summary-item,
.history-count-item,
.history-section,
.detail-block,
.detail-item,
.status-badge,
.flow-chain-list,
.flow-chain-selection-summary,
.flow-run-panel:last-child #flowLog,
.flow-history-table-wrap,
.db-validation-history-table-wrap,
.pbc-upload-area,
#page-settings .metric-item,
#page-settings .db-validation-source-row,
.flow-chain-config,
.config-item,
#page-settings .about-description,
#page-settings .about-features,
#page-settings .about-tech,
```

规则体保持完全不变：

```css
{
  border-radius: var(--ui-radius) !important;
}
```

- [ ] **Step 2: 更新 README 当前功能说明**

在 `README.md` 的“系统设置”条目中，把覆盖说明扩展为包含以下完整句子：

```markdown
截图指定的子表面也统一跟随该值，包括鱼骨详情卡、报送日期分组卡、注意事项卡、统计失败提示条、右上角通知、流程浮动通知、顶部版本标签、暗色切换按钮外壳、历史详情与执行历史表格外框、结果详情分区、结果状态标签、一键导入上传区、系统信息指标卡、数据源与流程链配置行、关于系统内容卡，以及使用本机上一次成功用户圆角的登录页卡片、输入框和登录按钮。
```

保持紧随其后的特殊形状排除说明不变。

- [ ] **Step 3: 更新 README v2.1 详细变更**

在 v2.1 的“新增用户级界面圆角个性化设置”条目末尾加入：

```markdown
；截图指定的子表面进一步覆盖报送导航提示、通知、版本标签、结果详情与状态、历史与流程、上传区、系统设置内容卡和登录页
```

不要修改应用界面版本号，也不要展开 `src/auto_check/web/app.js` 的精简更新日志。

- [ ] **Step 4: 运行聚焦测试并确认通过**

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_user_radius_override_is_semantic_and_border_radius_only tests/test_web_static.py::test_readme_documents_expanded_interface_radius_surface_coverage tests/test_web_static.py::test_v21_changelog_documents_interface_radius_concisely
```

Expected: 3 passed；更新日志仍保持精简，CSS 覆盖层只包含 `border-radius`。

- [ ] **Step 5: 运行前端静态测试**

Run:

```powershell
python -m pytest -q tests/test_web_static.py
```

Expected: PASS，无失败或错误。

- [ ] **Step 6: 检查本任务差异**

Run:

```powershell
git diff -- src/auto_check/web/styles.css tests/test_web_static.py README.md
git diff --check
```

Expected: CSS 只在集中式覆盖层增加精确选择器；测试只扩展圆角契约；README 只补充覆盖说明；无 whitespace error。

- [ ] **Step 7: 提交实现**

```powershell
git add src/auto_check/web/styles.css tests/test_web_static.py README.md
git commit -m "fix: extend unified radius to highlighted surfaces"
```

---

### Task 2: 登录页使用最后一次认证成功的圆角显示缓存

**Files:**
- Modify: `src/auto_check/web/login.html:8-24`
- Modify: `src/auto_check/web/login.html:606-616`
- Modify: `src/auto_check/web/app.js:551-790`
- Modify: `tests/test_web_static.py:3180-3390`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: 主应用 `normalizeInterfaceRadius()`、成功的 `GET/POST /api/settings/interface` 返回值和登录页 `document.documentElement`。
- Produces: 固定显示缓存键 `autoCheckLastInterfaceRadius`、登录页首屏根变量和浅色/暗色登录矩形表面圆角。

- [ ] **Step 1: 先写登录页缓存与样式失败测试**

在 `tests/test_web_static.py` 的圆角测试区新增：

```python
def test_login_uses_last_authenticated_interface_radius_display_cache():
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")

    assert "--ui-radius: 4px;" in login_html
    assert 'const LAST_INTERFACE_RADIUS_CACHE_KEY = "autoCheckLastInterfaceRadius";' in login_html
    assert "function normalizeLoginInterfaceRadius(value)" in login_html
    assert "Number.isInteger(parsed)" in login_html
    assert "parsed >= 1 && parsed <= 15" in login_html
    assert "localStorage.getItem(LAST_INTERFACE_RADIUS_CACHE_KEY)" in login_html
    assert 'document.documentElement.style.setProperty("--ui-radius", `${radiusPx}px`);' in login_html
    assert login_html.index('id="initialInterfaceRadiusScript"') < login_html.index("<style>")

    for selector in (
        ".right-panel",
        ':root[data-login-theme="dark"] .login-container',
        ".form-input",
        ':root[data-login-theme="dark"] .form-input',
        ".login-btn",
        ':root[data-login-theme="dark"] .login-btn',
    ):
        assert selector in login_html
```

- [ ] **Step 2: 把主应用本地存储断言改为单一非权威显示缓存契约**

将 `test_interface_radius_settings_refresh_on_each_entry_without_local_storage()` 重命名为 `test_interface_radius_settings_use_server_authority_with_login_display_cache()`，保留设置页每次进入重新 GET 的断言，并把原来禁止所有 radius localStorage 的断言替换为：

```python
    block = re.search(
        r"// Interface radius start(?P<body>.*?)// Interface radius end",
        app_js,
        re.S,
    )
    assert block is not None
    body = block.group("body")

    assert 'const LAST_INTERFACE_RADIUS_CACHE_KEY = "autoCheckLastInterfaceRadius";' in body
    assert "function cacheAuthenticatedInterfaceRadius(radiusPx)" in body
    assert "localStorage.setItem(LAST_INTERFACE_RADIUS_CACHE_KEY, String(normalizedRadiusPx));" in body
    assert "localStorage.getItem(LAST_INTERFACE_RADIUS_CACHE_KEY)" not in app_js
    assert "localStorage.removeItem(LAST_INTERFACE_RADIUS_CACHE_KEY)" not in app_js
    assert app_js.count("localStorage.setItem(LAST_INTERFACE_RADIUS_CACHE_KEY") == 1
    assert "autoCheckRadius" not in app_js
```

在现有 `test_interface_radius_preview_reset_save_and_discard_are_draft_safe()` 中增加：

```python
    assert "cacheAuthenticatedInterfaceRadius(" not in slider_body
    assert "cacheAuthenticatedInterfaceRadius(" not in reset_body
    assert "cacheAuthenticatedInterfaceRadius(savedRadiusPx);" in save_body
    assert "cacheAuthenticatedInterfaceRadius(" not in catch_body
```

并在 `test_interface_radius_state_normalization_rendering_and_api_boundary()` 中取得 `loadInterfaceRadiusPreference` 函数体，断言成功路径包含 `cacheAuthenticatedInterfaceRadius(radiusPx);`，catch 路径不包含该调用。

- [ ] **Step 3: 运行新测试并确认先失败**

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_login_uses_last_authenticated_interface_radius_display_cache tests/test_web_static.py::test_interface_radius_settings_use_server_authority_with_login_display_cache tests/test_web_static.py::test_interface_radius_preview_reset_save_and_discard_are_draft_safe tests/test_web_static.py::test_interface_radius_state_normalization_rendering_and_api_boundary
```

Expected: FAIL；登录页尚无显示缓存，主应用尚未在成功 GET/POST 后同步缓存。

- [ ] **Step 4: 在登录页首屏读取并规范化显示缓存**

在 `login.html` 的 `<style>` 之前加入：

```html
    <script id="initialInterfaceRadiusScript">
      (() => {
        const LAST_INTERFACE_RADIUS_CACHE_KEY = "autoCheckLastInterfaceRadius";
        const DEFAULT_LOGIN_INTERFACE_RADIUS_PX = 4;

        function normalizeLoginInterfaceRadius(value) {
          const parsed = Number(value);
          return Number.isInteger(parsed) && parsed >= 1 && parsed <= 15
            ? parsed
            : DEFAULT_LOGIN_INTERFACE_RADIUS_PX;
        }

        let radiusPx = DEFAULT_LOGIN_INTERFACE_RADIUS_PX;
        try {
          radiusPx = normalizeLoginInterfaceRadius(localStorage.getItem(LAST_INTERFACE_RADIUS_CACHE_KEY));
        } catch (_) {}
        document.documentElement.style.setProperty("--ui-radius", `${radiusPx}px`);
      })();
    </script>
```

并在登录页 `:root` 变量中增加：

```css
        --ui-radius: 4px;
```

- [ ] **Step 5: 让登录页指定矩形表面读取根变量**

在 `login.html` 内联样式末尾、`</style>` 前增加：

```css
      .right-panel,
      .form-input,
      .login-btn,
      :root[data-login-theme="dark"] .login-container,
      :root[data-login-theme="dark"] .form-input,
      :root[data-login-theme="dark"] .login-btn {
        border-radius: var(--ui-radius);
      }
```

不要加入 `.theme-toggle`、`.password-toggle`、`.remember-me input`、`.deco`、`.shape`、`.feature-card` 或 `.social-btn`。

- [ ] **Step 6: 主应用只在成功 GET/POST 后写显示缓存**

在 `app.js` 的 `// Interface radius start/end` 区域中，常量和 `normalizeInterfaceRadius()` 后加入：

```javascript
const LAST_INTERFACE_RADIUS_CACHE_KEY = "autoCheckLastInterfaceRadius";

function cacheAuthenticatedInterfaceRadius(radiusPx) {
  const normalizedRadiusPx = normalizeInterfaceRadius(radiusPx);
  try {
    localStorage.setItem(LAST_INTERFACE_RADIUS_CACHE_KEY, String(normalizedRadiusPx));
  } catch (_) {}
  return normalizedRadiusPx;
}
```

在 `loadInterfaceRadiusPreference()` 成功解析 `radiusPx` 并更新成功状态后加入：

```javascript
    cacheAuthenticatedInterfaceRadius(radiusPx);
```

在 `saveInterfaceRadiusPreference()` 成功应用服务端返回值后加入：

```javascript
    cacheAuthenticatedInterfaceRadius(savedRadiusPx);
```

不得在 slider `input`、恢复默认、catch、登录提交或偏好失败回退路径调用缓存函数。

- [ ] **Step 7: 运行聚焦测试和前端全量静态测试**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "interface_radius or login_uses_last_authenticated_interface_radius"
python -m pytest -q tests/test_web_static.py
```

Expected: 全部通过；登录、主题、密码显示、记住我和原圆角状态机测试无回归。

- [ ] **Step 8: 检查登录缓存边界并提交**

Run:

```powershell
git diff -- src/auto_check/web/login.html src/auto_check/web/app.js tests/test_web_static.py
git diff --check
```

Expected: 缓存只含一个整数键；主应用只写不读；登录页只读；无用户映射、API、数据库或认证流程变化。

```powershell
git add src/auto_check/web/login.html src/auto_check/web/app.js tests/test_web_static.py
git commit -m "feat: apply last user radius to login surfaces"
```

---

### Task 3: 补齐统计周期外壳与注意事项筛选标签

**Files:**
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: 现有集中式 `--ui-radius` 覆盖层，以及已覆盖的 `.trend-quick-btn`。
- Produces: 统计周期分段选择器外壳和注意事项筛选标签统一读取同一圆角值，不改变筛选、选中态或图表逻辑。

- [ ] **Step 1: 先增加失败测试**

在 `test_user_radius_override_is_semantic_and_border_radius_only()` 的必需选择器元组中加入：

```python
        ".trend-quick-btns",
        "#page-report-navigation .report-nav-filter-chips span",
```

在 `test_readme_documents_expanded_interface_radius_surface_coverage()` 的详细术语中加入：

```python
        "统计周期分段选择器",
        "注意事项筛选标签",
```

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_user_radius_override_is_semantic_and_border_radius_only tests/test_web_static.py::test_readme_documents_expanded_interface_radius_surface_coverage
```

Expected: FAIL；CSS 尚缺两个精确选择器，README 尚缺两处覆盖说明。

- [ ] **Step 2: 实现最小显示覆盖**

在 `/* User interface radius preference: start/end */` 集中式覆盖层加入：

```css
.trend-quick-btns,
#page-report-navigation .report-nav-filter-chips span,
```

继续共用唯一规则体：

```css
{
  border-radius: var(--ui-radius) !important;
}
```

不得修改 `.trend-quick-btn` 的筛选事件、选中态颜色、图表刷新逻辑，或注意事项标签的文字、数量与交互。

- [ ] **Step 3: 同步 README 详细说明**

在当前功能和 v2.1 详细变更中补充“统计周期分段选择器”和“注意事项筛选标签”；不修改应用内 `app.js` 的精简更新日志。

- [ ] **Step 4: 验证并提交**

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_user_radius_override_is_semantic_and_border_radius_only tests/test_web_static.py::test_readme_documents_expanded_interface_radius_surface_coverage tests/test_web_static.py::test_v21_changelog_documents_interface_radius_concisely
python -m pytest -q tests/test_web_static.py
git diff --check
```

Expected: 聚焦与前端静态测试全部通过；CSS 覆盖层仍只有 `border-radius`；无业务代码变化。

```powershell
git add src/auto_check/web/styles.css tests/test_web_static.py README.md
git commit -m "fix: include remaining filter controls in unified radius"
```

---

### Task 4: 补齐侧栏状态框与报送导航刷新按钮

**Files:**
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: 既有 `.top-nav-status`、`.dark-mode-toggle` 覆盖和报送导航刷新按钮原交互样式。
- Produces: 侧栏运行时状态框与刷新按钮外壳读取统一圆角，不改变主题消息、动画、冷却或刷新请求。

- [ ] **Step 1: 先增加失败测试**

在必需选择器元组中加入：

```python
        ".sidebar-footer .status",
        "#page-report-navigation .report-nav-refresh-button",
```

从 `forbidden_selector` 元组中仅删除：

```python
        ".report-nav-refresh-button",
```

在 README 详细覆盖术语测试中加入“侧栏状态消息框”和“报送导航刷新按钮”。运行两个聚焦测试并确认先失败。

- [ ] **Step 2: 实现最小显示覆盖**

在集中式圆角覆盖层加入：

```css
.sidebar-footer .status,
#page-report-navigation .report-nav-refresh-button,
```

继续共用唯一 `border-radius: var(--ui-radius) !important;` 规则体。不得修改 `.report-nav-refresh-icon`、`refreshing` 动画、倒计时、POST 请求、状态文字或状态恢复定时器。

- [ ] **Step 3: 同步 README 并验证**

在当前功能和 v2.1 详细变更中补充侧栏状态消息框与报送导航刷新按钮；应用内 `app.js` 日志保持精简且不改动。

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_user_radius_override_is_semantic_and_border_radius_only tests/test_web_static.py::test_readme_documents_expanded_interface_radius_surface_coverage tests/test_web_static.py::test_report_navigation_manual_refresh_has_icon_cooldown_and_error_feedback
python -m pytest -q tests/test_web_static.py
git diff --check
```

Expected: 全部通过；只改 CSS 精确选择器、静态契约和 README，无业务逻辑变化。

```powershell
git add src/auto_check/web/styles.css tests/test_web_static.py README.md
git commit -m "fix: apply unified radius to status and refresh controls"
```

---

### Task 5: 补齐对账业务设置页面内矩形分区

**Files:**
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: 对账业务设置页面现有字段配置、说明条和业务字段分组结构。
- Produces: 三类页面内矩形分区读取统一圆角，不修改表单、展开、表格行或保存逻辑。

- [ ] **Step 1: 先增加失败测试**

在 `test_user_radius_override_is_semantic_and_border_radius_only()` 的必需选择器中加入：

```python
        "#page-settings .reconcile-schema-table",
        "#page-settings .business-settings-note",
        "#page-settings .business-field-group",
```

在 README 详细覆盖术语测试中加入“对账表字段配置卡”“对账业务维护说明条”“对账业务字段表格分组”。运行聚焦测试并确认先失败。

- [ ] **Step 2: 实现最小显示覆盖**

在集中式圆角覆盖层加入：

```css
#page-settings .reconcile-schema-table,
#page-settings .business-settings-note,
#page-settings .business-field-group,
```

继续共用唯一 `border-radius: var(--ui-radius) !important;` 规则体。不得修改 HTML、`app.js`、表单值、字段展开、业务表格行、保存行为或任何弹窗选择器。

- [ ] **Step 3: 同步 README 并验证**

在当前功能和 v2.1 详细变更中补充三类对账业务设置页面矩形分区；应用内 `app.js` 更新日志保持精简且不改动。

Run:

```powershell
python -m pytest -q tests/test_web_static.py::test_user_radius_override_is_semantic_and_border_radius_only tests/test_web_static.py::test_readme_documents_expanded_interface_radius_surface_coverage
python -m pytest -q tests/test_web_static.py
git diff --check
```

Expected: 聚焦和静态测试通过；只修改 CSS 精确选择器、静态契约和 README。

```powershell
git add src/auto_check/web/styles.css tests/test_web_static.py README.md
git commit -m "fix: apply unified radius to business settings panels"
```

---

### Task 6: 全量验证、重新打包与浏览器验收

**Files:**
- Verify: `src/auto_check/web/styles.css`
- Verify: `src/auto_check/web/login.html`
- Verify: `src/auto_check/web/app.js`
- Verify: `tests/test_web_static.py`
- Verify: `README.md`
- Modify: `dist/auto-check.exe`

**Interfaces:**
- Consumes: Task 1 已提交的主应用 CSS/测试/README、Task 2 已提交的登录显示缓存、Task 3 已提交的筛选控件补充覆盖、Task 4 已提交的状态与刷新控件补充覆盖，以及 Task 5 已提交的对账业务设置页面分区覆盖。
- Produces: 通过全量回归的新 Windows 可执行文件，以及 1px、4px、15px 下的可视验收结果。

- [ ] **Step 1: 运行全量测试**

Run:

```powershell
python -m pytest -q
```

Expected: 全部测试通过，无 error、failure 或异常 skip 增长。

- [ ] **Step 2: 运行显示-only 审计**

Run:

```powershell
git show --stat --oneline HEAD
git diff HEAD^ --check
rg -n "User interface radius preference|report-nav-branch-panel|dark-mode-toggle|history-summary-item|flow-chain-list|pbc-upload-area|db-validation-source-row|about-tech" src/auto_check/web/styles.css tests/test_web_static.py README.md
```

Expected: 当前实现提交只涉及 `styles.css`、`test_web_static.py`、`README.md`；集中式覆盖层仍只有 `border-radius`，无业务代码变化。

- [ ] **Step 3: 只停止当前 worktree 的旧可执行文件**

Run:

```powershell
$exePath = (Resolve-Path "dist\auto-check.exe").Path
Get-CimInstance Win32_Process -Filter "Name = 'auto-check.exe'" |
  Where-Object { $_.ExecutablePath -eq $exePath } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Expected: 仅停止可执行路径等于当前 worktree `dist\auto-check.exe` 的进程；不处理其他目录的同名进程。

- [ ] **Step 4: 刷新 Windows 可执行文件**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1 -SkipTests
```

Expected: PyInstaller 退出码 0，`dist\auto-check.exe` 更新时间刷新且文件非空。

- [ ] **Step 5: 打包后复跑关键测试与完整性检查**

Run:

```powershell
python -m pytest -q tests/test_web_static.py tests/test_server.py tests/test_security.py
git diff --check
Get-FileHash dist\auto-check.exe -Algorithm SHA256
Get-Item dist\auto-check.exe | Select-Object FullName, Length, LastWriteTime
```

Expected: 测试全部通过；无 whitespace error；exe 有 SHA256、非零长度和新的修改时间。

- [ ] **Step 6: 提交打包产物**

```powershell
git add dist/auto-check.exe
git commit -m "build: refresh Windows executable"
```

- [ ] **Step 7: 隐藏启动新可执行文件并检查 HTTP**

Run:

```powershell
$exePath = (Resolve-Path "dist\auto-check.exe").Path
$process = Start-Process -FilePath $exePath -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
$process.Id
$response = $null
for ($attempt = 0; $attempt -lt 20; $attempt++) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing http://localhost:8765/ -TimeoutSec 2
    break
  } catch {
    Start-Sleep -Milliseconds 500
  }
}
if (-not $response) { throw "auto-check did not become ready on port 8765" }
$response | Select-Object StatusCode
```

Expected: 返回新进程 ID，首页 HTTP 状态为 200。

- [ ] **Step 8: 使用浏览器验证 1px、4px、15px 预览**

在已登录页面进入“系统设置→界面设置”；如果会话失效，使用现有管理员账号重新登录。分别把滑块拖到 1px、4px、15px，但不点击保存，逐类抽查：

- 报送导航：鱼骨详情卡、报送日期分组卡、注意事项卡、注意事项筛选标签和手工刷新按钮。
- 提示与导航：统计失败提示条、右上角通用通知、流程浮动通知、顶部版本标签、侧栏状态消息框和暗色切换按钮外壳。
- 结果/历史：结果详情分区、键值信息框、匹配状态标签、历史详情卡和两类执行历史表格外框。
- 流程/逐笔：流程链列表与摘要、执行日志和逐笔校验数据源配置行。
- 工具/设置：统计周期分段选择器、上传区、系统信息指标卡、逐笔数据源配置行、流程链与数据源配置行、对账表字段配置卡、对账业务维护说明条、对账业务字段表格分组，以及关于系统三类内容卡。

Expected: 所有已确认矩形目标的计算样式 `border-radius` 与滑块值一致；复选框、圆形图标、状态点、进度条和表格行保持原样；暗色切换、流程选择、历史查看和文件选择入口仍可操作。弹窗专项验收暂缓，不新增或评估弹窗内部覆盖。

随后把 `autoCheckLastInterfaceRadius` 依次设为 1、4、15 并重新打开登录页，分别检查浅色与暗色：浅色登录卡片、暗色登录外框、输入框和登录按钮使用缓存值；主题按钮、密码眼睛按钮、复选框和装饰圆形保持原样。最后恢复缓存为已保存的 4。

- [ ] **Step 9: 恢复已保存值并记录最终状态**

离开系统设置页触发未保存预览撤销，再返回界面设置确认显示已保存的 4px；不要把 1px 或 15px 写入数据库。

Run:

```powershell
git status --short
git log -5 --oneline
```

Expected: 工作区干净；最近提交包含设计补充、主应用 CSS/测试/README 实现、登录显示缓存实现和 exe 刷新。
