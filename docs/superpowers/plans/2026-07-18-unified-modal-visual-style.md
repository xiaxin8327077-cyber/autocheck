# Unified Modal Visual Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将监管智核全部系统弹窗统一为轻量平衡风格，并把对数历史详情调整为参考稿的信息层级，同时保留现有尺寸、业务交互、表格居中规则和用户圆角设置联动。

**Architecture:** 在现有 `.modal` 与 `.pbc-modal` 结构上增加 `app-modal-*` 共享语义类，由一组集中 CSS 规则统一遮罩、外壳、标题栏、内容区、关闭按钮和底部操作区；原 ID、业务类和事件绑定保持不变。历史详情只重排前端渲染结构并增加展示类，不改变 API、历史数据或恢复行为。

**Tech Stack:** 原生 HTML/CSS/JavaScript、Python 3.12、pytest 静态结构测试、PowerShell、PyInstaller

## Global Constraints

- 工作目录固定为 `D:\trae\autocheck\.worktrees\user-interface-radius-preferences`，继续使用分支 `codex/user-interface-radius-preferences`。
- 不重复实现圆角设置；全部新增矩形弹窗元素读取现有 `--ui-radius`。
- 弹窗尺寸保留现有专用规则，历史详情继续使用 `min(1240px, 94vw)` 和 `92vh`。
- 历史详情表头、普通单元格和金额单元格全部保持居中。
- 人行全量产品导入保持“上传文件、字段映射、开始导入、完成”四步。
- 不修改 API、权限、焦点、遮罩关闭、后台执行、历史口径、差异类型或恢复结果行为。
- 默认太空主题、沉稳主题和暗色模式均需覆盖。
- 应用内更新日志只保留“系统优化及BUG修复。”，不得展开视觉改动细节；README 记录详细变化。
- 不修改应用版本号。

---

### Task 1: 建立全部弹窗共用的平衡外壳

**Files:**
- Modify: `src/auto_check/web/index.html:608-1038, 1490-1660`
- Modify: `src/auto_check/web/styles.css:5348-5757, 5906-5997, 7857-7886, 10068-10285, 12080-12175`
- Test: `tests/test_web_static.py:3083-3108, 5191-5230`

**Interfaces:**
- Consumes: 现有 `--ui-radius`、主题变量、弹窗 ID、`.modal`、`.pbc-modal` 和现有事件绑定。
- Produces: `app-modal-overlay`、`app-modal-shell`、`app-modal-header`、`app-modal-body`、`app-modal-footer`、`app-modal-close` 六个共享视觉类。

- [ ] **Step 1: 写入共享外壳失败测试**

在 `tests/test_web_static.py` 增加：

```python
def test_all_system_modals_use_balanced_shared_shell():
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)

    overlay_ids = (
        "pbcModalOverlay",
        "dbValidationModalOverlay",
        "dbValidationHistoryOverlay",
        "flowModalOverlay",
        "flowHistoryOverlay",
        "flowChainEditorOverlay",
        "confirmModal",
        "promptModal",
        "infoModal",
        "reportNavCardMaintenanceModal",
        "userModal",
        "configModal",
    )
    for overlay_id in overlay_ids:
        opening = re.search(
            rf'<div class="(?P<classes>[^"]+)" id="{overlay_id}"',
            html,
        )
        assert opening is not None
        assert "app-modal-overlay" in opening.group("classes").split()

    assert html.count("app-modal-shell") == len(overlay_ids)
    assert html.count("app-modal-header") == len(overlay_ids)
    assert "pbc-modal-icon" not in html
    assert "user-modal-icon" not in html

    for selector in (
        ".app-modal-overlay",
        ".app-modal-shell",
        ".app-modal-header",
        ".app-modal-body",
        ".app-modal-footer",
        ".app-modal-close",
    ):
        assert selector in css
    assert '[data-color-mode="dark"] .app-modal-overlay' in css
    assert '[data-color-mode="dark"] .app-modal-shell' in css
```

把现有 `test_radius_surfaces_drop_fixed_polygon_clipping_but_pbc_close_stays_diamond` 改为：

```python
def test_pbc_close_uses_shared_radius_instead_of_diamond():
    css = _read(STYLES_CSS)
    close_rule = re.search(
        r"(?m)^\.pbc-modal-close\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert close_rule is not None
    close_body = close_rule.group("body")
    assert "clip-path" not in close_body
    assert "rotate(90deg)" not in css

    override = css.split("/* User interface radius preference: start */", 1)[1].split(
        "/* User interface radius preference: end */",
        1,
    )[0]
    assert ".pbc-modal-close" in override
```

在用户弹窗测试的结构 token 列表中删除 `"user-modal-icon"`，并新增：

```python
assert "app-modal-shell" in modal.group("body")
assert "user-modal-icon" not in modal.group("body")
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "balanced_shared_shell or shared_radius_instead_of_diamond or user_edit_modal"
```

Expected: FAIL，原因包括 `app-modal-overlay`/`app-modal-shell` 尚不存在、标题图标仍存在、PBC 关闭按钮仍使用菱形裁剪。

- [ ] **Step 3: 为 12 个弹窗增加共享语义类**

在 `index.html` 对 12 个遮罩开标签执行以下精确类名替换，同时保留 ID、`hidden` 和专用类：

```text
class="modal-overlay" -> class="app-modal-overlay modal-overlay"
class="pbc-modal-overlay" -> class="app-modal-overlay pbc-modal-overlay"
class="pbc-modal-overlay db-validation-modal-overlay" -> class="app-modal-overlay pbc-modal-overlay db-validation-modal-overlay"
class="pbc-modal-overlay db-validation-history-overlay" -> class="app-modal-overlay pbc-modal-overlay db-validation-history-overlay"
class="pbc-modal-overlay flow-modal-overlay" -> class="app-modal-overlay pbc-modal-overlay flow-modal-overlay"
class="pbc-modal-overlay flow-history-overlay" -> class="app-modal-overlay pbc-modal-overlay flow-history-overlay"
class="pbc-modal-overlay flow-chain-editor-overlay" -> class="app-modal-overlay pbc-modal-overlay flow-chain-editor-overlay"
```

对 12 个外壳开标签执行以下精确类名替换：

```text
class="modal modal-confirm" -> class="app-modal-shell modal modal-confirm"
class="modal modal-confirm modal-prompt" -> class="app-modal-shell modal modal-confirm modal-prompt"
class="modal modal-info" -> class="app-modal-shell modal modal-info"
class="modal modal-confirm report-nav-card-maintenance-modal" -> class="app-modal-shell modal modal-confirm report-nav-card-maintenance-modal"
class="modal user-modal" -> class="app-modal-shell modal user-modal"
class="modal" -> class="app-modal-shell modal"
class="pbc-modal" -> class="app-modal-shell pbc-modal"
class="pbc-modal db-validation-modal" -> class="app-modal-shell pbc-modal db-validation-modal"
class="pbc-modal db-validation-history-modal" -> class="app-modal-shell pbc-modal db-validation-history-modal"
class="pbc-modal flow-modal" -> class="app-modal-shell pbc-modal flow-modal"
class="pbc-modal flow-history-modal" -> class="app-modal-shell pbc-modal flow-history-modal"
class="pbc-modal flow-chain-editor-modal" -> class="app-modal-shell pbc-modal flow-chain-editor-modal"
```

对标题、正文、底栏和关闭按钮执行以下精确类名替换：

```text
class="modal-header" -> class="app-modal-header modal-header"
class="modal-header user-modal-header" -> class="app-modal-header modal-header user-modal-header"
class="pbc-modal-header" -> class="app-modal-header pbc-modal-header"
class="modal-body" -> class="app-modal-body modal-body"
class="modal-body user-modal-body" -> class="app-modal-body modal-body user-modal-body"
class="modal-footer" -> class="app-modal-footer modal-footer"
class="modal-footer user-modal-footer" -> class="app-modal-footer modal-footer user-modal-footer"
class="pbc-modal-footer" -> class="app-modal-footer pbc-modal-footer"
class="btn-close" -> class="app-modal-close btn-close"
class="btn-close user-modal-close" -> class="app-modal-close btn-close user-modal-close"
class="pbc-modal-close" -> class="app-modal-close pbc-modal-close"
```

为六个工具弹窗补齐正文边界：

```text
pbcModal: 在 <!-- Steps indicator --> 前插入 <div class="app-modal-body pbc-modal-body">，在 <!-- Footer buttons --> 前闭合该 div。
dbValidationModal: 将 class="db-validation-grid" 改为 class="app-modal-body pbc-modal-body db-validation-grid"。
dbValidationHistoryOverlay: 将 class="db-validation-history-table-wrap" 改为 class="app-modal-body pbc-modal-body db-validation-history-table-wrap"。
flowModal: 将 class="flow-run-grid" 改为 class="app-modal-body pbc-modal-body flow-run-grid"。
flowHistoryOverlay: 将 class="flow-history-table-wrap" 改为 class="app-modal-body pbc-modal-body flow-history-table-wrap"。
flowChainEditorOverlay: 将 class="flow-chain-editor-body" 改为 class="app-modal-body pbc-modal-body flow-chain-editor-body"。
```

删除六个 `.pbc-modal-icon` 元素和 `userModalIcon` 元素；保留标题、副标题、工具入口按钮以及用户角色卡内部的小图标。

- [ ] **Step 4: 写入集中式平衡弹窗 CSS**

在专用弹窗规则之后、用户圆角覆盖层之前加入：

```css
/* ===== Shared balanced modal visual system ===== */
.app-modal-overlay {
  background: color-mix(in srgb, #0f172a 34%, transparent);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.app-modal-shell {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--outline-variant);
  background: var(--surface-container-lowest);
  box-shadow: 0 12px 36px rgba(15, 23, 42, 0.16);
}

.app-modal-header {
  flex: 0 0 auto;
  min-height: 58px;
  margin: 0;
  padding: 17px 24px;
  border-bottom: 1px solid var(--outline-variant);
  background: var(--surface-container-lowest);
}

.app-modal-header h2,
.app-modal-header h3 {
  margin: 0;
  color: var(--on-surface);
  font-size: 16px;
  font-weight: 500;
}

.app-modal-header p {
  margin: 4px 0 0;
  color: var(--on-surface-variant);
  font-size: 12px;
}

.app-modal-body {
  flex: 1 1 auto;
  min-height: 0;
  padding: 22px 24px;
  overflow: auto;
}

.pbc-modal-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.app-modal-footer {
  flex: 0 0 auto;
  margin: 0;
  padding: 14px 24px;
  border-top: 1px solid var(--outline-variant);
  background: var(--surface-container-lowest);
}

.app-modal-close {
  top: 15px;
  right: 20px;
  width: 28px;
  height: 28px;
  clip-path: none;
  border: 0;
  background: transparent;
  color: var(--outline);
  box-shadow: none;
  transform: none;
}

.app-modal-close:hover {
  color: var(--on-surface);
  background: var(--surface-container-low);
  transform: none;
}

.app-modal-shell :is(.btn-primary, .btn-confirm-primary, .pbc-btn--primary) {
  color: #ffffff;
  background: var(--secondary);
  box-shadow: none;
}

.app-modal-shell .pbc-btn--success {
  color: #ffffff;
  background: var(--success, #16a34a);
  box-shadow: none;
}

[data-color-mode="dark"] .app-modal-overlay {
  background: rgba(2, 6, 23, 0.66);
}

[data-color-mode="dark"] .app-modal-shell,
[data-color-mode="dark"] .app-modal-header,
[data-color-mode="dark"] .app-modal-footer {
  border-color: rgba(148, 163, 184, 0.24);
  background: #0f172a;
}
```

从原 `.pbc-modal-close` 删除 `clip-path`，从 hover 删除旋转；删除不再使用的 `.pbc-modal-icon`、`.db-validation-modal-icon`、`.flow-modal-icon` 和 `.user-modal-icon` 规则。把 `.pbc-modal-close` 加入文件末尾“User interface radius preference”矩形选择器清单。

- [ ] **Step 5: 运行共享外壳与相关回归测试**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "balanced_shared_shell or shared_radius_instead_of_diamond or user_edit_modal or pbc_import_modal_flow or flow_chain_editor_blank_overlay"
```

Expected: PASS；四步导入和禁止空白遮罩关闭的断言保持通过。

- [ ] **Step 6: 提交共享外壳**

```powershell
git add src/auto_check/web/index.html src/auto_check/web/styles.css tests/test_web_static.py
git commit -m "feat: unify system modal shells"
```

---

### Task 2: 重排并轻量化对数历史详情

**Files:**
- Modify: `src/auto_check/web/app.js:3878-3955`
- Modify: `src/auto_check/web/styles.css:3940-4118, 5068-5090`
- Modify: `tests/test_history_ui_static.py`
- Test: `tests/test_web_static.py:5380-5540`

**Interfaces:**
- Consumes: Task 1 的 `app-modal-footer`、现有 `showInfo()`、`historyDiffItems()`、`historyResultTable()` 和 `--ui-radius`。
- Produces: `history-section--complete`、`history-section--added`、`history-section--removed`、`history-section-bar`、`history-status`、`history-status--done`、`history-status--pending`。

- [ ] **Step 1: 把历史详情测试改成新结构契约**

在 `tests/test_web_static.py` 的历史详情测试中加入或替换为：

```python
def test_history_detail_uses_inline_metadata_and_colored_sections():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    start = app_js.index("function renderHistoryDetailContent(run)")
    end = app_js.index("function renderHistoryDetailLoading", start)
    detail = app_js[start:end]

    complete = 'historySection("本次完整核对结果", run.results || [], "complete")'
    added = 'historySection("本次新增差异", historyDiffItems(run, "added_results"), "added")'
    removed = 'historySection("本次减少差异", historyDiffItems(run, "removed_results"), "removed")'
    assert detail.index(complete) < detail.index(added) < detail.index(removed)
    assert "${historyDetailCounts(run)}" not in detail
    assert "function historyDetailCounts" not in app_js
    assert "function historyCountItem" not in app_js

    summary = re.search(r"(?m)^\.history-summary-grid\s*\{(?P<body>.*?)\}", css, re.S)
    assert summary is not None
    assert "display: flex" in summary.group("body")
    assert "flex-wrap: wrap" in summary.group("body")

    for tone in ("complete", "added", "removed"):
        assert f".history-section--{tone} .history-section-bar" in css
    assert ".history-status--done" in css
    assert ".history-status--pending" in css

    cells = re.search(
        r"(?m)^\.history-result-table th,\s*\n\.history-result-table td\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert cells is not None
    assert "text-align: center" in cells.group("body")
    assert ".history-result-table td.money-cell" in css
```

删除旧 `test_history_detail_counts_are_one_row` 对三张计数卡的断言；`tests/test_history_ui_static.py` 继续校验共享 info modal、关闭按钮和恢复按钮事件不变，并新增完整/新增/减少顺序断言。

- [ ] **Step 2: 运行历史详情测试并确认失败**

Run:

```powershell
python -m pytest tests/test_history_ui_static.py tests/test_web_static.py -q -k "history_detail"
```

Expected: FAIL，旧代码仍按新增/减少/完整顺序渲染，仍包含计数卡，且尚无色条与状态胶囊规则。

- [ ] **Step 3: 重排历史详情渲染器**

把 `renderHistoryDetailContent()` 的主体调整为：

```javascript
function renderHistoryDetailContent(run) {
  return `
    <div class="history-detail-card">
      <div class="history-detail">
        <div class="history-summary-grid">
          ${historySummaryItem("报告期", run.run_date)}
          ${historySummaryItem("执行人", historyExecutorName(run))}
          ${historySummaryItem("执行时间", run.run_at)}
          ${historySummaryItem("基准记录", historyBaselineText(run))}
        </div>
        ${historySection("本次完整核对结果", run.results || [], "complete")}
        ${historySection("本次新增差异", historyDiffItems(run, "added_results"), "added")}
        ${historySection("本次减少差异", historyDiffItems(run, "removed_results"), "removed")}
      </div>
      <div class="app-modal-footer history-detail-footer">
        <button type="button" class="btn-primary btn-sm restore-history-detail" data-id="${escapeHtml(run.id || "")}">恢复到结果页</button>
      </div>
    </div>
  `;
}
```

删除 `historyDetailCounts()` 与 `historyCountItem()`，把 `historySection()` 改为：

```javascript
function historySection(title, items, tone) {
  if (!items.length) return "";
  const scrollClass = items.length > 10 ? " history-section--scroll" : "";
  return `<section class="history-section history-section--${tone}${scrollClass}">
    <div class="history-section-title">
      <span class="history-section-bar" aria-hidden="true"></span>
      <strong>${escapeHtml(title)}</strong>
      <span>${formatMoney(items.length)} 条</span>
    </div>
    <div class="history-section-table">${historyResultTable(items)}</div>
  </section>`;
}
```

在 `historyResultTable()` 中生成状态胶囊：

```javascript
const status = String(item.match_status || "");
const statusClass = status === "已解释" ? "history-status--done" : "history-status--pending";
```

```html
<td><span class="history-status ${statusClass}">${escapeHtml(status)}</span></td>
```

保持五个表头、数据字段和金额格式化函数不变。

- [ ] **Step 4: 用轻量元数据、色条和中性胶囊替换旧卡片样式**

把历史详情相关 CSS 调整为：

```css
.history-summary-grid {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 10px 30px;
  margin-bottom: 10px;
}

.history-summary-item {
  display: inline-flex;
  align-items: baseline;
  gap: 7px;
  min-height: 0;
  border: 0;
  background: transparent;
}

.history-summary-item span,
.history-summary-item strong {
  padding: 0;
  font-size: 13px;
}

.history-summary-item span {
  color: var(--on-surface-variant);
  background: transparent;
}

.history-summary-item strong {
  color: var(--on-surface);
  font-weight: 500;
  overflow-wrap: break-word;
}

.history-section {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
}

.history-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 0 10px;
  border: 0;
  color: var(--on-surface);
  background: transparent;
  font-size: 13px;
  font-weight: 500;
}

.history-section-bar {
  width: 3px;
  height: 14px;
  flex: 0 0 auto;
}

.history-section--complete .history-section-bar { background: #22c55e; }
.history-section--added .history-section-bar { background: #ef4444; }
.history-section--removed .history-section-bar { background: #3b82f6; }

.history-result-table th,
.history-result-table td {
  text-align: center;
  border-bottom: 1px solid var(--surface-variant);
}

.history-result-table td.money-cell { text-align: center; }

.history-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 20px;
  padding: 2px 10px;
  border-radius: 999px;
  color: var(--on-surface-variant);
  font-size: 11px;
  white-space: nowrap;
}

.history-status--done { background: var(--surface-container-high); }
.history-status--pending {
  border: 1px solid var(--outline-variant);
  background: transparent;
}
```

删除 `.history-detail-counts`、`.history-count-item` 及相应暗色规则；暗色模式使用主题变量，不重新引入厚重卡片背景。保留 `.modal-info--history-detail` 宽高、主体 overflow、超过 10 行的 360px 分组滚动和五列表格 `min-width: 780px`。

- [ ] **Step 5: 运行历史详情和圆角回归测试**

Run:

```powershell
python -m pytest tests/test_history_ui_static.py tests/test_web_static.py -q -k "history_detail or interface_radius"
```

Expected: PASS；历史详情新层级、居中、宽屏尺寸和圆角联动均满足断言。

- [ ] **Step 6: 提交历史详情改造**

```powershell
git add src/auto_check/web/app.js src/auto_check/web/styles.css tests/test_history_ui_static.py tests/test_web_static.py
git commit -m "feat: restyle reconciliation history detail"
```

---

### Task 3: 同步 README 与应用内发布口径

**Files:**
- Modify: `README.md:15-31, 315-330`
- Verify: `src/auto_check/web/app.js:10280-10300`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: Task 1 与 Task 2 的最终可见行为。
- Produces: README 详细说明；v2.1 应用内日志继续只使用统一优化文案。

- [ ] **Step 1: 写入文档同步失败测试**

在 `tests/test_web_static.py` 增加：

```python
def test_balanced_modal_refresh_is_documented_with_concise_in_app_changelog():
    readme = _read(ROOT / "README.md")
    app_js = _read(APP_JS)

    assert "系统弹窗统一为轻量平衡风格" in readme
    assert "历史详情按完整结果、新增差异、减少差异分组" in readme
    assert "表头和内容继续保持居中" in readme
    assert "弹窗圆角继续跟随当前用户的界面设置" in readme

    current = re.search(
        r'<span class="changelog-version">v2\.1</span>(?P<body>.*?)<div class="changelog-item">',
        app_js,
        re.S,
    )
    assert current is not None
    assert "系统优化及BUG修复。" in current.group("body")
    assert "弹窗" not in current.group("body")
    assert "历史详情" not in current.group("body")
```

- [ ] **Step 2: 运行文档测试并确认失败**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "balanced_modal_refresh_is_documented"
```

Expected: FAIL，README 尚未包含本次详细说明。

- [ ] **Step 3: 更新 README，保持应用内日志精简**

在“当前功能”的对数历史或主题说明中加入：

```markdown
- 弹窗视觉：系统弹窗统一为轻量平衡风格，使用纯色表面、细分隔线、克制阴影、统一标题栏、独立滚动内容区和固定操作区；确认、输入、信息、用户、数据源、人行导入与校验、流程工具弹窗保留各自适配业务内容的尺寸。历史详情按完整结果、新增差异、减少差异分组，使用绿、红、蓝色条区分，表头和内容继续保持居中。弹窗圆角继续跟随当前用户的界面设置，并兼容太空、沉稳和暗色模式。
```

在 `v2.1` 最新变化中增加同口径的详细条目。`app.js` 当前 v2.1 已包含 `<li>系统优化及BUG修复。</li>`，保持该条且不新增第二条、不展开弹窗细节。

- [ ] **Step 4: 运行文档和更新日志测试**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "balanced_modal_refresh_is_documented or changelog or version"
```

Expected: PASS；README 详细、应用内日志精简、版本仍为 v2.1。

- [ ] **Step 5: 提交文档同步**

```powershell
git add README.md tests/test_web_static.py
git commit -m "docs: document balanced modal visual style"
```

---

### Task 4: 全量验证、视觉检查与 Windows 打包

**Files:**
- Verify: `src/auto_check/web/index.html`
- Verify: `src/auto_check/web/styles.css`
- Verify: `src/auto_check/web/app.js`
- Verify: `README.md`
- Modify after successful packaging: `dist/auto-check.exe`

**Interfaces:**
- Consumes: Task 1 至 Task 3 的实现和测试。
- Produces: 通过全量测试、三主题视觉检查和刷新后的 Windows 可执行文件。

- [ ] **Step 1: 运行全部自动化测试**

Run:

```powershell
python -m pytest -q
```

Expected: PASS，0 failed。

- [ ] **Step 2: 检查差异与空白字符**

Run:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` 无真实 whitespace error；状态只包含本任务预期文件或已提交后为空。

- [ ] **Step 3: 在本地应用检查代表性弹窗**

先确认 `8765` 未被参考页或其他临时服务占用，再启动当前 worktree 的应用。至少检查：

1. 默认太空浅色：历史详情、用户编辑、人行导入。
2. 沉稳浅色：确认、输入、数据源配置。
3. 暗色模式：历史详情、逐笔校验、流程执行和流程链编辑。
4. 圆角值 1px、4px、15px：外壳、关闭按钮、主次按钮和输入框同步；胶囊、进度圆环和开关保持原形。

Expected: 无尺寸回退、底栏滚出、表格错位、遮罩穿透、文字低对比度或按钮渐变残留；历史表格全部居中。

- [ ] **Step 4: 确认可执行文件未运行并打包**

Run:

```powershell
Get-Process -Name "auto-check" -ErrorAction SilentlyContinue
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
```

Expected: 打包前无运行中的 `auto-check` 进程；脚本成功完成并刷新 `dist\auto-check.exe`。

- [ ] **Step 5: 再次运行全量测试和差异检查**

Run:

```powershell
python -m pytest -q
git diff --check
```

Expected: PASS，0 failed；无真实 whitespace error。

- [ ] **Step 6: 提交打包产物**

```powershell
git add dist/auto-check.exe
git commit -m "build: refresh Windows executable"
```

- [ ] **Step 7: 汇总最终状态**

Run:

```powershell
git status --short
git log -5 --oneline --decorate
```

Expected: 工作区干净；最近提交依次包含共享弹窗外壳、历史详情、README 和打包产物。
