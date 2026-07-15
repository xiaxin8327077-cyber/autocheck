# 对数总览首次执行统计与质量卡片调整实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 恢复执行趋势日期框的主干自适应宽度，将对数质量和差异类型分布改为每期首次执行口径，并删除质量分展示。

**Architecture:** 保留现有单页应用和自定义下拉框结构，在进入对数总览后对隐藏初始化的日期框做组件级重新测量。新增独立的“每期首次执行”选择函数和通用汇总函数，仅供两块分布统计使用；高频差异项目继续消费全部近期执行记录。

**Tech Stack:** 原生 HTML/CSS/JavaScript、Python pytest 静态结构测试、PowerShell Windows 打包脚本。

---

## 文件结构

- `src/auto_check/web/app.js`：页面切换、下拉框测量、历史记录筛选和首页统计渲染。
- `src/auto_check/web/index.html`：删除质量分圆环与评价标签节点。
- `src/auto_check/web/styles.css`：让状态分布占满质量卡，并删除质量分专用样式。
- `tests/test_web_static.py`：覆盖宽度重测、每期首次执行口径、质量分移除和文档更新。
- `README.md`：详细记录首页统计口径和展示变化。

### Task 1: 恢复日期下拉框的主干自适应宽度

**Files:**
- Modify: `tests/test_web_static.py:1801`
- Modify: `src/auto_check/web/app.js:1588,729`

- [ ] **Step 1: 写入失败测试**

```python
def test_home_chart_date_select_remeasures_after_hidden_default_page_becomes_visible():
    app_js = _read(APP_JS)

    assert "function scheduleHomeChartDateSelectMeasure()" in app_js
    assert "const state = customSelectStates.get(chartDateSelect);" in app_js
    assert "customSelectMeasure(chartDateSelect, state.shell);" in app_js
    assert 'if (name === "home") scheduleHomeChartDateSelectMeasure();' in app_js
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_web_static.py::test_home_chart_date_select_remeasures_after_hidden_default_page_becomes_visible -q`

Expected: FAIL，提示 `scheduleHomeChartDateSelectMeasure` 不存在。

- [ ] **Step 3: 实现显示后重新测量**

在自定义下拉框测量函数附近增加：

```javascript
function scheduleHomeChartDateSelectMeasure() {
  window.requestAnimationFrame(() => {
    if (document.documentElement.getAttribute("data-page") !== "home" || !chartDateSelect) return;
    const state = customSelectStates.get(chartDateSelect);
    if (!state) return;
    customSelectMeasure(chartDateSelect, state.shell);
  });
}
```

在 `switchPage()` 设置 `data-page` 后增加：

```javascript
if (name === "home") scheduleHomeChartDateSelectMeasure();
```

不修改主干已有的 `.chart-date-select { width: auto; min-width: 150px; }`。

- [ ] **Step 4: 运行测试并确认通过**

Run: `python -m pytest tests/test_web_static.py::test_home_chart_date_select_remeasures_after_hidden_default_page_becomes_visible tests/test_web_static.py::test_home_chart_date_select_keeps_scrollable_wider_dropdown -q`

Expected: `2 passed`。

- [ ] **Step 5: 提交本任务**

```powershell
git add src/auto_check/web/app.js tests/test_web_static.py
git commit -m "fix: restore home chart date select width"
```

### Task 2: 两块分布统计改取每期第一次执行

**Files:**
- Modify: `tests/test_web_static.py:913`
- Modify: `src/auto_check/web/app.js:5071,5412,6012`

- [ ] **Step 1: 写入失败测试**

在首页静态测试中加入：

```python
assert "function firstHomeRunsForPeriodDates(runs = [], dates = [])" in app_js
assert "compareHomeRunTimeAsc(run, current) < 0" in app_js
assert "function aggregateHomeSummaryForRuns(runs = [], summaryBuilder = () => ({}))" in app_js
assert "aggregateHomeSummaryForRuns(recentFirstPeriodRuns, homeStatusCountsForRun)" in app_js
assert "aggregateHomeSummaryForRuns(recentFirstPeriodRuns, homeDifferenceTypeSummaryForRun)" in app_js
assert "averageHomeSummaryByPeriod" not in app_js
assert "buildHomeFrequencyItems(recentPeriodRuns, recentPeriodDates)" in app_js
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_web_static.py::test_home_dashboard_uses_clickable_reconcile_stats_and_keeps_line_charts -q`

Expected: FAIL，提示首次执行选择函数不存在或旧平均函数仍存在。

- [ ] **Step 3: 增加首次执行选择与汇总函数**

在 `homeRunsForPeriodDates()` 后增加：

```javascript
function firstHomeRunsForPeriodDates(runs = [], dates = []) {
  const firstByDate = new Map();
  homeRunsForPeriodDates(runs, dates).forEach((run) => {
    const current = firstByDate.get(run.run_date);
    if (!current || compareHomeRunTimeAsc(run, current) < 0) firstByDate.set(run.run_date, run);
  });
  return dates.map((date) => firstByDate.get(date)).filter(Boolean);
}
```

用通用求和替换旧的每期平均函数：

```javascript
function aggregateHomeSummaryForRuns(runs = [], summaryBuilder = () => ({})) {
  const summary = {};
  runs.forEach((run) => {
    Object.entries(summaryBuilder(run) || {}).forEach(([key, value]) => {
      summary[key] = (summary[key] || 0) + Number(value || 0);
    });
  });
  return summary;
}
```

在 `renderHomeStats()` 加入并替换两处统计：

```javascript
const recentFirstPeriodRuns = firstHomeRunsForPeriodDates(recentPeriodRuns, recentPeriodDates);
const periodStatusCounts = aggregateHomeSummaryForRuns(recentFirstPeriodRuns, homeStatusCountsForRun);
const periodTypeSummary = aggregateHomeSummaryForRuns(recentFirstPeriodRuns, homeDifferenceTypeSummaryForRun);
```

保留：

```javascript
const frequencyItems = buildHomeFrequencyItems(recentPeriodRuns, recentPeriodDates);
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python -m pytest tests/test_web_static.py::test_home_dashboard_uses_clickable_reconcile_stats_and_keeps_line_charts -q`

Expected: `1 passed`。

- [ ] **Step 5: 提交本任务**

```powershell
git add src/auto_check/web/app.js tests/test_web_static.py
git commit -m "feat: use first run for home quality statistics"
```

### Task 3: 删除质量分并扩展状态分布

**Files:**
- Modify: `tests/test_web_static.py:913`
- Modify: `src/auto_check/web/index.html:369`
- Modify: `src/auto_check/web/styles.css:4539`
- Modify: `src/auto_check/web/app.js:5476,6089`

- [ ] **Step 1: 写入失败测试**

```python
assert 'id="homeQualityScore"' not in html
assert 'id="homeQualityTag"' not in html
assert "质量分" not in html
assert "home-quality-ring" not in html
assert "home-quality-tag" not in html
assert 'class="home-quality-body">\n                <div class="home-quality-bars"' in html
assert '"homeQualityScore"' not in app_js
assert "periodExplainedPct" not in app_js
assert ".home-quality-ring" not in css
assert ".home-quality-tag" not in css
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_web_static.py::test_home_dashboard_uses_clickable_reconcile_stats_and_keeps_line_charts -q`

Expected: FAIL，显示质量分节点或计算仍存在。

- [ ] **Step 3: 精简 HTML 和 JavaScript**

将质量卡正文改为：

```html
<div class="home-quality-body">
  <div class="home-quality-bars" id="homeQualityRows">
    <p class="home-analysis-empty">暂无核对数据</p>
  </div>
</div>
```

从 `setHomeEmptyState()` 删除 `homeQualityScore`、圆环和标签重置；从 `renderHomeStats()` 删除 `periodExplained`、`periodExplainedPct`、质量分写入、圆环进度和评价标签计算。

- [ ] **Step 4: 精简 CSS 并让分布占满卡片**

删除 `.home-quality-ring`、`.home-quality-ring span`、`.home-quality-ring small`、`.home-quality-info` 和 `.home-quality-tag` 规则，将正文和条形区域调整为：

```css
.home-quality-body {
  display: flex;
  align-items: center;
  flex: 1;
  min-height: 0;
}

.home-quality-bars {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-height: 0;
  overflow: hidden;
}
```

移除窄屏媒体查询中不再需要的 `.home-quality-body` 纵向布局覆盖。

- [ ] **Step 5: 运行测试并确认通过**

Run: `python -m pytest tests/test_web_static.py::test_home_dashboard_uses_clickable_reconcile_stats_and_keeps_line_charts tests/test_web_static.py::test_home_analysis_cards_keep_height_in_short_scale_ratio_viewports -q`

Expected: `2 passed`。

- [ ] **Step 6: 提交本任务**

```powershell
git add src/auto_check/web/index.html src/auto_check/web/styles.css src/auto_check/web/app.js tests/test_web_static.py
git commit -m "refactor: simplify home quality card"
```

### Task 4: 文档、全量测试与 Windows 打包

**Files:**
- Modify: `README.md:359`
- Modify: `src/auto_check/web/app.js:9527`
- Modify: `tests/test_web_static.py:1150`

- [ ] **Step 1: 更新文档测试**

```python
assert "对数质量和差异类型分布按每期第一次执行汇总" in readme
assert "对数质量移除质量分" in readme
assert "每期全部执行次数先取平均后汇总" not in readme
assert "系统优化及BUG修复。" in app_js
```

- [ ] **Step 2: 运行文档测试并确认失败**

Run: `python -m pytest tests/test_web_static.py::test_home_dashboard_uses_clickable_reconcile_stats_and_keeps_line_charts -q`

Expected: FAIL，提示 README 仍为旧口径。

- [ ] **Step 3: 更新 README 与应用内日志**

将 README 首页说明中的“每期全部执行次数先取平均后汇总”改为“每期第一次执行汇总”，删除旧的平均值和同期前序执行纳入口径描述，并补充“对数质量移除质量分、圆环和评价标签”。应用内 `v2.1` 日志保持精简，仅保留或复用：

```html
<li>系统优化及BUG修复。</li>
```

- [ ] **Step 4: 运行首页相关测试**

Run: `python -m pytest tests/test_web_static.py -q`

Expected: 全部通过。

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest -q`

Expected: 全部通过，无失败。

- [ ] **Step 6: 检查差异和空白错误**

Run: `git diff --check`

Expected: 无实际 whitespace error；CRLF/LF 提示可忽略。

- [ ] **Step 7: 结束占用打包文件的进程并打包**

```powershell
Get-Process -Name auto-check -ErrorAction SilentlyContinue | Stop-Process -Force
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
```

Expected: `dist\auto-check.exe` 生成成功且退出码为 0。

- [ ] **Step 8: 校验产物**

```powershell
Get-Item dist\auto-check.exe | Select-Object FullName,Length,LastWriteTime
Get-FileHash dist\auto-check.exe -Algorithm SHA256
```

Expected: 文件存在、时间为本次打包时间，并输出 SHA256。

- [ ] **Step 9: 提交文档和测试更新**

```powershell
git add README.md src/auto_check/web/app.js tests/test_web_static.py
git commit -m "docs: update home dashboard statistics behavior"
```
