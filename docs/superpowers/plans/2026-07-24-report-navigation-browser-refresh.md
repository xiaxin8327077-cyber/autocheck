# Report Navigation Browser Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 浏览器刷新报送导航时立即恢复当前用户、当前统计周期的最近成功画面，后台加载最新数据，并在无缓存时显示友好的首次加载骨架。

**Architecture:** 使用 `sessionStorage` 保存按用户与统计周期隔离的 dashboard payload。`loadReportNavigation()` 在网络请求前尝试恢复有效缓存，网络成功后原子替换页面并更新缓存；缓存不可用时通过独立页面状态显示骨架，网络失败时保留已恢复内容。

**Tech Stack:** 原生 JavaScript、HTML、CSS、pytest 静态结构测试。

## Global Constraints

- 不修改后端报送导航统计、刷新冷却、权限或接口结构。
- 缓存仅使用 `sessionStorage`，不得跨浏览器标签页或浏览器会话长期保存。
- 缓存必须按用户 ID 和统计周期隔离，业务报告期跨月时失效。
- 页面样式沿用现有亮色主题、Logo 蓝主题变量和全局圆角变量。
- 先写失败测试并确认失败，再修改生产代码。
- 可见界面优化同步更新 `README.md`；应用内更新日志仅保留“系统优化及BUG修复”口径。
- 不自动打包 `dist\auto-check.exe`。

---

### Task 1: Dashboard session cache and stale-while-revalidate loading

**Files:**
- Modify: `tests/test_web_static.py`
- Modify: `src/auto_check/web/app.js:384-401`
- Modify: `src/auto_check/web/app.js:2422-2465`
- Modify: `src/auto_check/web/app.js:2632-2650`

**Interfaces:**
- Consumes: `authState.user.id`, `reportNavPeriodSelect.value`, `renderReportNavigation(payload, options)`, `api(path)`.
- Produces:
  - `reportNavigationCacheKey(period: string): string`
  - `readReportNavigationCache(period: string, now?: Date): object | null`
  - `writeReportNavigationCache(period: string, payload: object, now?: Date): void`
  - `clearReportNavigationCache(): void`
  - `expectedReportNavigationBusinessDate(now?: Date): string`

- [ ] **Step 1: Write failing static contract tests**

Add a focused test to `tests/test_web_static.py`:

```python
def test_report_navigation_browser_refresh_restores_scoped_session_cache():
    app_js = _read(APP_JS)

    assert 'const REPORT_NAV_CACHE_PREFIX = "autoCheckReportNavigationDashboard:v1";' in app_js
    assert "function reportNavigationCacheKey(period)" in app_js
    assert "authState.user?.id" in app_js
    assert "sessionStorage.getItem(reportNavigationCacheKey(period))" in app_js
    assert "sessionStorage.setItem(reportNavigationCacheKey(period), JSON.stringify(entry))" in app_js
    assert "expectedReportNavigationBusinessDate" in app_js
    assert "cached.businessReportDate !== expectedReportNavigationBusinessDate()" in app_js
    assert "renderReportNavigation(cached.payload" in app_js
    assert "writeReportNavigationCache(period, payload);" in app_js
    assert "clearReportNavigationCache();" in app_js
```

Add a second test for failure behavior:

```python
def test_report_navigation_browser_refresh_keeps_cached_content_on_request_failure():
    app_js = _read(APP_JS)
    start = app_js.index("async function loadReportNavigation")
    end = app_js.index("function syncReportNavigationPeriodTabs", start)
    body = app_js[start:end]

    assert "const cached = readReportNavigationCache(period);" in body
    assert "let restoredFromCache = false;" in body
    assert "restoredFromCache = true;" in body
    assert "if (!restoredFromCache)" in body
    assert "renderReportNavigation({})" not in body
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "report_navigation_browser_refresh"
```

Expected: both tests fail because cache constants and helper functions do not exist.

- [ ] **Step 3: Implement scoped cache helpers**

Add near the existing report-navigation state:

```javascript
const REPORT_NAV_CACHE_PREFIX = "autoCheckReportNavigationDashboard:v1";

function expectedReportNavigationBusinessDate(now = new Date()) {
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
  const previousMonthEnd = new Date(firstDay.getTime() - 86400000);
  return [
    previousMonthEnd.getFullYear(),
    String(previousMonthEnd.getMonth() + 1).padStart(2, "0"),
    String(previousMonthEnd.getDate()).padStart(2, "0"),
  ].join("-");
}

function reportNavigationCacheKey(period) {
  const userId = String(authState.user?.id || "");
  return `${REPORT_NAV_CACHE_PREFIX}:${userId}:${period}`;
}

function readReportNavigationCache(period, now = new Date()) {
  if (!authState.user?.id) return null;
  try {
    const cached = JSON.parse(sessionStorage.getItem(reportNavigationCacheKey(period)) || "null");
    if (!cached || cached.userId !== String(authState.user.id) || cached.period !== period) return null;
    if (cached.businessReportDate !== expectedReportNavigationBusinessDate(now)) return null;
    if (!cached.payload || typeof cached.payload !== "object") return null;
    return cached;
  } catch (_) {
    return null;
  }
}

function writeReportNavigationCache(period, payload, now = new Date()) {
  if (!authState.user?.id || !payload || typeof payload !== "object") return;
  const businessReportDate = String(payload.business_report_date || "");
  if (businessReportDate !== expectedReportNavigationBusinessDate(now)) return;
  const entry = {
    userId: String(authState.user.id),
    period,
    businessReportDate,
    savedAt: new Date().toISOString(),
    payload,
  };
  try {
    sessionStorage.setItem(reportNavigationCacheKey(period), JSON.stringify(entry));
  } catch (_) {}
}

function clearReportNavigationCache() {
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(`${REPORT_NAV_CACHE_PREFIX}:`)) sessionStorage.removeItem(key);
    }
  } catch (_) {}
}
```

- [ ] **Step 4: Implement cache-first dashboard loading**

Update `loadReportNavigation()` so it restores a matching cache only when the currently rendered payload does not match the selected period, then fetches and replaces it:

```javascript
async function loadReportNavigation({ preserveSchedule = false } = {}) {
  if (reportNavigationLoading) return;
  reportNavigationLoading = true;
  const period = reportNavPeriodSelect?.value || "month";
  const cached = readReportNavigationCache(period);
  let restoredFromCache = false;
  if (String(reportNavigationPayload?.period || "") !== period && cached?.payload) {
    renderReportNavigation(cached.payload, { preserveSchedule: false });
    restoredFromCache = true;
  }
  setReportNavigationLoadingState(restoredFromCache ? "refreshing-with-cache" : "initial-loading");
  setStatus(restoredFromCache ? "正在更新报送导航…" : "正在读取最新统计结果…");
  try {
    const payload = await api(`/api/report-navigation/dashboard?period=${encodeURIComponent(period)}`);
    renderReportNavigation(payload, { preserveSchedule });
    writeReportNavigationCache(period, payload);
    setReportNavigationLoadingState("ready");
    return payload;
  } catch (error) {
    setStatus(`统计结果读取失败：${error.message}`);
    setReportNavigationLoadingState(restoredFromCache ? "error-with-cache" : "error-empty");
    if (!restoredFromCache) showReportNavigationEmptyLoadError();
    return null;
  } finally {
    reportNavigationLoading = false;
  }
}
```

Call `clearReportNavigationCache()` after successful logout before navigation to `/login.html`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "report_navigation_browser_refresh"
```

Expected: cache contract tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add tests/test_web_static.py src/auto_check/web/app.js
git commit -m "feat: preserve report navigation during browser refresh"
```

---

### Task 2: First-load skeleton and page loading states

**Files:**
- Modify: `tests/test_web_static.py`
- Modify: `src/auto_check/web/index.html:121-210`
- Modify: `src/auto_check/web/styles.css:1410-1788`
- Modify: `src/auto_check/web/app.js:16-40`

**Interfaces:**
- Consumes: `reportNavPage`, `reportNavInitialLoading`.
- Produces:
  - `setReportNavigationLoadingState(state: string): void`
  - `showReportNavigationEmptyLoadError(): void`

- [ ] **Step 1: Write failing skeleton structure and state tests**

Add:

```python
def test_report_navigation_has_first_load_skeleton_and_accessible_loading_state():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'id="reportNavInitialLoading"' in html
    assert 'class="report-nav-initial-loading"' in html
    assert 'role="status"' in html
    assert "function setReportNavigationLoadingState(state)" in app_js
    assert 'reportNavPage.dataset.loadingState = state;' in app_js
    assert 'reportNavPage.setAttribute("aria-busy"' in app_js
    assert "#page-report-navigation[data-loading-state=\"initial-loading\"] .report-nav-initial-loading" in css
    assert "@keyframes report-nav-skeleton-shimmer" in css
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m pytest tests/test_web_static.py::test_report_navigation_has_first_load_skeleton_and_accessible_loading_state -q
```

Expected: FAIL because the skeleton container and loading-state function do not exist.

- [ ] **Step 3: Add the skeleton container**

Add `data-loading-state="initial-loading" aria-busy="true"` to `#page-report-navigation`, then place this container directly inside it:

```html
<div class="report-nav-initial-loading" id="reportNavInitialLoading" role="status" aria-live="polite">
  <span class="report-nav-loading-spinner" aria-hidden="true"></span>
  <strong>正在加载报送导航</strong>
  <small>正在读取最新统计结果…</small>
</div>
```

- [ ] **Step 4: Add loading state helpers**

Add DOM references and helpers:

```javascript
const reportNavPage = document.getElementById("page-report-navigation");
const reportNavInitialLoading = document.getElementById("reportNavInitialLoading");

function setReportNavigationLoadingState(state) {
  if (!reportNavPage) return;
  reportNavPage.dataset.loadingState = state;
  reportNavPage.setAttribute("aria-busy", state === "initial-loading" ? "true" : "false");
  if (reportNavInitialLoading) reportNavInitialLoading.hidden = state !== "initial-loading";
  reportNavRefreshButton?.classList.toggle("refreshing", state === "refreshing-with-cache");
}

function showReportNavigationEmptyLoadError() {
  if (!reportNavInitialLoading) return;
  reportNavInitialLoading.hidden = false;
  reportNavInitialLoading.querySelector("strong").textContent = "报送导航加载失败";
  reportNavInitialLoading.querySelector("small").textContent = "请稍后刷新页面重试";
}
```

- [ ] **Step 5: Add scoped skeleton styles**

Add page-scoped CSS:

```css
#page-report-navigation .report-nav-initial-loading {
  min-height: 420px;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 8px;
  color: var(--on-surface-variant);
}

#page-report-navigation .report-nav-initial-loading[hidden] {
  display: none;
}

#page-report-navigation[data-loading-state="initial-loading"] > :not(.report-nav-initial-loading) {
  display: none;
}

#page-report-navigation .report-nav-loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(52, 102, 217, 0.16);
  border-top-color: #3466d9;
  border-radius: 50%;
  animation: report-nav-skeleton-shimmer .8s linear infinite;
}

@keyframes report-nav-skeleton-shimmer {
  to { transform: rotate(360deg); }
}
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "report_navigation_browser_refresh or report_navigation_has_first_load_skeleton"
```

Expected: all new refresh and skeleton tests pass.

- [ ] **Step 7: Commit Task 2**

```powershell
git add tests/test_web_static.py src/auto_check/web/index.html src/auto_check/web/styles.css src/auto_check/web/app.js
git commit -m "fix: smooth report navigation first load"
```

---

### Task 3: Documentation and regression verification

**Files:**
- Modify: `README.md:327`
- Modify: `src/auto_check/web/app.js:11424-11440`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: completed browser-refresh behavior.
- Produces: user-facing release notes and final verification evidence.

- [ ] **Step 1: Add a failing release-note assertion**

Add:

```python
def test_report_navigation_refresh_optimization_is_documented():
    readme = _read(ROOT / "README.md")
    app_js = _read(APP_JS)

    assert "浏览器刷新时优先恢复当前用户和统计周期的最近成功画面" in readme
    assert "<li>系统优化及BUG修复。</li>" in app_js
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests/test_web_static.py::test_report_navigation_refresh_optimization_is_documented -q
```

Expected: FAIL because README does not yet describe the optimization.

- [ ] **Step 3: Update release notes**

Add a detailed `v2.1` README bullet:

```markdown
- 报送导航优化浏览器刷新体验：同一标签页刷新时优先恢复当前用户和统计周期的最近成功画面，后台读取最新数据后整体替换；首次无缓存时显示加载状态，读取失败时保留已有画面。
```

Keep the application changelog entry at the required concise wording:

```html
<li>系统优化及BUG修复。</li>
```

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_web_static.py -q -k "report_navigation"
```

Expected: all report-navigation frontend tests pass.

- [ ] **Step 5: Run full verification**

Run:

```powershell
python -m pytest -q
git diff --check
```

Expected: 0 failed, 0 errors; no whitespace errors.

- [ ] **Step 6: Commit Task 3**

```powershell
git add README.md src/auto_check/web/app.js tests/test_web_static.py
git commit -m "docs: record report navigation refresh optimization"
```
