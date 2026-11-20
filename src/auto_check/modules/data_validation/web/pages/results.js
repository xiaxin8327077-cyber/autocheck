import { errorMessage } from "../runtime.js";
import {
  canCancelTask, canRetryTask, emptyPage, formatDateTime, hasCapability, isTaskActive,
  loadConvergedPage, ownsResource, reportCategoryCode, targetTableLabel, taskIssueNotice, visibleSql,
} from "../state.js";
import { button, downloadText, element, emptyState, field, input, statusBadge } from "../components/dom.js";
import { createPagination } from "../components/pagination.js";
import { categoryBadge, taskStatus } from "../components/task_list.js";
import { queryCaptureNotice, queryColumns, queryValue } from "../components/result_fields.js";
import { createResultBatches } from "../components/result_batches.js";
import { resultIcon } from "../components/result_icons.js";
import { loadResultFonts } from "../components/result_fonts.js";

function ruleStatus(rule) {
  const code = rule.status;
  if (code === "PASS") return statusBadge(rule.truncated ? "结果截断" : "未发现异常", rule.truncated ? "warning" : "success");
  if (code === "VIOLATION") return statusBadge("发现异常", "warning");
  return statusBadge({ ERROR: "执行失败", TIMEOUT: "执行超时", CANCELLED: "已取消", RUNNING: "执行中", PENDING: "等待执行", running: "执行中", queued: "等待执行" }[code] || code || "状态未知",
    ["ERROR", "TIMEOUT", "CANCELLED"].includes(code) ? "danger" : "neutral");
}

export function createResultsPage({
  state, runtime, api, listen, user, notify, confirmAction, host, onNewTask, onPeriodChange, onRender,
}) {
  let reportCategory = "";
  let issueRuleId = null;
  let selectedTab = "rules";
  let onlyIssues = true;
  let detailData = null;
  let detailStatus = "idle";
  let detailError = "";
  let pollTimer = null;
  let pinnedTaskId = null;
  let selectedRule = null;
  let reviewStatus = "idle";
  let drawerOpener = null;
  let searchTimer = null;
  const ruleQuery = { page: 1, page_size: 50, keyword: "" };
  const knownCategories = new Map();
  const header = element("div", { hidden: true });
  const newTaskButton = button("批量执行", { listen, className: "dv-button dv-button-primary", hidden: !hasCapability(user, "dv.run"), capability: "dv.run", onClick: () => onNewTask() });
  newTaskButton.replaceChildren(resultIcon("play"), element("span", { text: "立即执行" }));
  newTaskButton.setAttribute("aria-label", "立即执行");
  const period = input({ type: "date", value: state.reportPeriod, dataset: { reportPeriod: "results" } });
  const periodText = element("span", { className: "dv-result-period-text dv-code", text: state.reportPeriod });
  const periodPicker = element("div", { className: "dv-result-period-picker" }, periodText, resultIcon("chevron"), period);
  listen(period, "change", () => { resetDetail(); onPeriodChange(period.value); });
  const categories = element("div", { className: "dv-results-category-options", attrs: { role: "group", "aria-label": "监管报送分类" } });
  listen(categories, "click", (event) => {
    const target = event.target.closest("[data-result-category]");
    if (target) return changeCategory(target.dataset.resultCategory);
  });
  const detail = element("div", { className: "dv-task-detail" });
  const summary = element("div", { className: "dv-result-summary" });
  const cancel = button("取消执行", { listen, className: "dv-button dv-button-danger", onClick: cancelTask });
  const retry = button("重试失败项", { listen, onClick: retryTask });
  const exportButton = button("导出异常", { listen, capability: "dv.export", onClick: exportIssues });
  exportButton.setAttribute("aria-label", "导出此规则异常");
  const notice = element("p", { className: "dv-result-notice" });
  const rulesTab = button("规则执行", { listen, className: "dv-result-tab", onClick: () => showTab("rules") });
  rulesTab.setAttribute("role", "tab");
  rulesTab.setAttribute("id", "dv-result-rules-tab");
  rulesTab.setAttribute("aria-controls", "dv-result-rules");
  const tabs = element("div", { className: "dv-result-tabs", attrs: { role: "tablist", "aria-label": "批次结果" } }, rulesTab);
  const onlyIssuesSwitch = button("", { listen, className: "user-enable-switch dv-only-issues-switch on", ariaLabel: "只查看异常规则",
    onClick: () => { const paged = Boolean(detailData?.rule_page); onlyIssues = !onlyIssues; ruleQuery.page = 1;
      renderAll(); if (paged) return loadDetail(); } });
  onlyIssuesSwitch.setAttribute("role", "switch");
  const rulesFilter = element("div", { className: "dv-only-issues-filter" }, element("span", { text: "只查看异常规则" }), onlyIssuesSwitch);
  const search = input({ placeholder: "搜索规则名称、编码或表名…", className: "dv-input dv-result-search" });
  search.setAttribute("aria-label", "搜索规则执行结果");
  function applySearch() {
    runtime.clearTimer(searchTimer); searchTimer = null;
    ruleQuery.keyword = search.value.trim().slice(0, 200); ruleQuery.page = 1;
    if ((!detailData || detailData.rule_page) && ownsResource(user, currentTask())) return loadDetail();
    renderAll();
  }
  listen(search, "change", applySearch);
  listen(search, "input", () => {
    runtime.clearTimer(searchTimer); runtime.invalidate("task-detail");
    searchTimer = runtime.setTimer(applySearch, 200);
  });
  const toolbar = element("div", { className: "dv-result-toolbar" }, tabs,
    element("div", { className: "dv-result-search-wrap" }, resultIcon("search"), search), rulesFilter);
  listen(tabs, "keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    rulesTab.focus();
  });
  const ruleBody = element("tbody");
  const ruleFeedback = element("div", { className: "dv-table-feedback" });
  const ruleTable = element("table", { className: "dv-table dv-rule-result-table" },
    element("thead", {}, element("tr", {}, ...["规则名称 / 执行版本", "监管分类", "数据源 / 目标表", "执行结果", "异常数量", "操作"].map((text) => element("th", { text })))), ruleBody);
  const ruleWrap = element("div", { className: "dv-result-rule-wrap dv-scroll" }, ruleTable);
  listen(ruleWrap, "click", (event) => {
    const target = event.target.closest("[data-rule-issues]");
    if (!target) return;
    const rule = (detailData?.rules || []).find(rule => Number(rule.rule_id) === Number(target.dataset.ruleIssues));
    if (!rule || Number(rule.violation_count) <= 0 || !ownsResource(user, currentTask())) return;
    runtime.invalidate("task-issues"); runtime.invalidate("task-export"); runtime.invalidate("task-review"); selectedRule = rule;
    reviewStatus = "idle";
    drawerOpener = target; issueRuleId = Number(rule.rule_id); state.issueQuery.page = 1;
    state.issues = emptyPage(state.issueQuery.page_size); state.issuesStatus = "idle";
    selectedTab = "issues"; renderAll(); drawer.focus?.();
    if (Number(rule.violation_count) > 0) return Promise.all([loadIssues(), loadRuleReview()]);
  });
  const rulePagination = createPagination({ listen,
    onPage: page => { ruleQuery.page = page; return loadDetail(); },
    onPageSize: size => { ruleQuery.page = 1; ruleQuery.page_size = size; return loadDetail(); },
  });
  const rulesPanel = element("div", { className: "dv-result-content", attrs: { role: "tabpanel", id: "dv-result-rules", "aria-labelledby": "dv-result-rules-tab" } }, ruleFeedback, ruleWrap, rulePagination.element);
  function closeRule() {
    const previousId = issueRuleId;
    runtime.invalidate("task-issues"); runtime.invalidate("task-export"); runtime.invalidate("task-review"); issueRuleId = null; selectedTab = "rules";
    selectedRule = null; reviewStatus = "idle";
    state.issueQuery.page = 1; state.issues = emptyPage(state.issueQuery.page_size); state.issuesStatus = "idle"; renderAll();
    const row = [...ruleBody.children].find(item => Number(item.dataset.ruleIssues) === previousId);
    const action = row?.children[5]?.children[0];
    if (action) action.focus?.();
    else if (drawerOpener?.isConnected) drawerOpener.focus?.();
    else search.focus?.();
  }
  const clearRule = button("返回规则列表", { listen, className: "dv-button dv-button-plain dv-return-rules", onClick: closeRule });
  const ruleScope = element("div", { className: "dv-issue-scope" }, element("div", { className: "dv-issue-context" }), clearRule);
  const issueHead = element("thead"); const issueBody = element("tbody");
  const issueTable = element("table", { className: "dv-table dv-issue-table" }, issueHead, issueBody);
  const issueWrap = element("div", { className: "dv-issue-table-wrap dv-scroll" }, issueTable);
  const issueFeedback = element("div", { className: "dv-issue-feedback" });
  const captureNotice = element("p", { className: "dv-query-capture-notice" });
  const pagination = createPagination({ listen,
    onPage: (page) => { state.issueQuery.page = Math.max(1, page); return loadIssues(); },
    onPageSize: (size) => { state.issueQuery = { page: 1, page_size: size }; return loadIssues(); },
  });
  const issuesPanel = element("div", { className: "dv-result-content", attrs: { role: "region", id: "dv-result-issues", "aria-label": "当前规则异常明细" } }, ruleScope, issueFeedback, issueWrap, captureNotice, pagination.element);
  const reviewName = element("h2", { attrs: { id: "dv-result-review-title" } });
  const reviewFacts = element("div", { className: "dv-review-facts" });
  const reviewSource = element("div", { className: "dv-review-source" });
  const reviewBatch = element("div", { className: "dv-review-batch" });
  const reviewDescription = element("p", { className: "dv-review-description" });
  const reviewTotal = element("span", { className: "dv-review-total dv-code" });
  const sqlPreview = element("pre", { className: "dv-review-sql dv-scroll" });
  const copySql = button("复制 SQL", { listen, className: "dv-button dv-button-plain", onClick: async () => {
    const sql = reviewSql(selectedRule);
    if (!sql) return;
    try { await navigator.clipboard.writeText(sql); notify("SQL 已复制", "success"); }
    catch { notify("无法自动复制，请在 SQL 区域选中后复制", "warning"); }
  } });
  copySql.replaceChildren(resultIcon("copy"), element("span", { text: "复制 SQL" }));
  const reviewClose = button("", { listen, className: "dv-review-close", ariaLabel: "关闭规则明细", onClick: closeRule });
  reviewClose.append(resultIcon("close"));
  const reviewSqlSection = element("section", { className: "dv-review-sql-section" },
    element("div", { className: "dv-review-sql-heading" }, element("strong", { text: "异常校验 SQL" }), copySql), sqlPreview);
  const drawer = element("section", { className: "dv-result-drawer", attrs: { role: "dialog", "aria-modal": "true", "aria-labelledby": "dv-result-review-title", tabindex: "-1" } },
    element("header", { className: "dv-review-heading" }, element("div", {}, reviewFacts, reviewName), reviewClose),
    element("div", { className: "dv-review-body dv-scroll" },
      element("section", { className: "dv-review-definition" },
        element("div", { className: "dv-review-metadata" }, reviewSource, reviewBatch),
        element("div", { className: "dv-review-business" }, element("div", { className: "dv-muted", text: "业务校验口径" }), reviewDescription)),
      reviewSqlSection, element("div", { className: "dv-review-issues-heading" }, element("h3", { className: "dv-review-issues-title", text: "异常数据明细" }), reviewTotal), issuesPanel),
    element("footer", { className: "dv-review-footer" }, element("span", { className: "dv-muted", text: "仅展示当前规则的本次执行结果" }), exportButton,
      button("关闭", { listen, onClick: closeRule })));
  const overlay = element("div", { className: "dv-result-overlay", hidden: true }, drawer);
  listen(overlay, "click", event => { if (event.target === overlay) { event.preventDefault(); closeRule(); } });
  listen(drawer, "keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); closeRule(); }
    if (event.key !== "Tab") return;
    const controls = [...(drawer.querySelectorAll?.('button:not([disabled]), input:not([disabled]), [tabindex="0"]') || [])].filter(node => !node.hidden && node.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (!first) { event.preventDefault(); return; }
    if (event.shiftKey && (document.activeElement === first || document.activeElement === drawer)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === drawer)) { event.preventDefault(); first.focus(); }
  });
  const resultCard = element("section", { className: "dv-card dv-issues-card" },
    notice, toolbar, rulesPanel);
  const workspace = element("div", { className: "dv-results-workspace" });
  const panel = element("section", { className: "dv-tab-panel dv-results-panel dv-results-replica dv-panel-content", dataset: { panel: "results" }, attrs: { role: "tabpanel" } },
    element("div", { className: "dv-results-filters" }, field("报送期", periodPicker), element("span", { className: "dv-result-filter-divider" }),
      element("div", { className: "dv-results-categories" }, element("strong", { text: "监管报送分类" }), categories), newTaskButton),
    workspace, overlay);
  const batches = createResultBatches({ listen, host: panel, onSelect: selectTask, onModeChange: mode => { workspace.dataset.resultView = mode; } });
  panel.dataset.resultFonts = "loading";
  loadResultFonts().then(() => { panel.dataset.resultFonts = "ready"; }).catch(() => { panel.dataset.resultFonts = "fallback"; });
  workspace.append(batches.heading, batches.trend,
    element("div", { className: "dv-results-batch-bar" }, batches.navigator, summary, element("div", { className: "dv-batch-actions" }, cancel, retry)), resultCard);

  function currentTask() { return state.tasks.find((task) => Number(task.id) === Number(state.activeTaskId)) || null; }
  function scope() { return { report_category: reportCategory, ...(issueRuleId ? { rule_id: issueRuleId } : {}) }; }
  function resetDetail() {
    runtime.invalidate("task-detail"); runtime.invalidate("task-issues"); runtime.invalidate("task-export"); runtime.invalidate("task-review");
    detailData = null; detailStatus = "idle"; detailError = ""; issueRuleId = null; selectedTab = "rules"; selectedRule = null; reviewStatus = "idle";
    pinnedTaskId = null;
    ruleQuery.page = 1;
    state.issueQuery.page = 1; state.issues = emptyPage(state.issueQuery.page_size); state.issuesStatus = "idle";
  }
  function stopPolling() {
    runtime.clearTimer(pollTimer); pollTimer = null;
    runtime.clearTimer(searchTimer); searchTimer = null; batches.close();
    ["task-list", "task-detail", "task-issues", "task-review", "task-export", "task-cancel", "task-retry"].forEach((channel) => runtime.invalidate(channel));
  }
  function focusTask(task) {
    stopPolling(); reportCategory = ""; resetDetail(); state.activeTaskId = Number(task.id); pinnedTaskId = Number(task.id);
    state.tasks = [task, ...state.tasks.filter(item => Number(item.id) !== Number(task.id))].slice(0, 100);
    renderAll();
    if (runtime.isActive() && state.activeTab === "results") loadTasks();
  }
  function schedulePoll() {
    runtime.clearTimer(pollTimer); pollTimer = null;
    const pending = state.tasks.some(task => ownsResource(user, task) && (isTaskActive(task) || task.status === "paused"));
    if (runtime.isActive() && state.activeTab === "results" && pending) pollTimer = runtime.setTimer(() => loadTasks({ poll: true }),
      globalThis.document?.hidden || !state.tasks.some(task => ownsResource(user, task) && isTaskActive(task)) ? 15000 : 2500);
  }
  async function changeCategory(code) {
    if (code === reportCategory) return;
    stopPolling(); reportCategory = code; resetDetail(); state.tasks = [];
    return loadTasks();
  }
  function showTab(tab) { selectedTab = tab; renderAll(); }
  async function loadTasks({ poll = false } = {}) {
    const token = runtime.next("task-list"); const reportPeriod = state.reportPeriod; const category = reportCategory;
    if (!poll) state.tasksStatus = "loading";
    state.tasksError = ""; renderAll();
    try {
      const progressIds = [...new Set(state.tasks.filter(task => ownsResource(user, task)
        && (isTaskActive(task) || task.status === "paused" || Number(task.id) === Number(state.activeTaskId))).map(task => task.id))];
      const lightweight = poll && typeof api.taskProgress === "function" && progressIds.length <= 20;
      const result = await runtime.request(token, signal => lightweight
        ? api.taskProgress(progressIds, { signal, report_category: category })
        : api.tasks({ report_period: reportPeriod, report_category: category }, { signal }));
      if (!runtime.current(token) || state.reportPeriod !== reportPeriod || category !== reportCategory) return;
      if (lightweight) {
        const updates = (Array.isArray(result) ? result : []).filter(task => task.report_period === reportPeriod
          && (!category || task.categories?.some(item => reportCategoryCode(item.code) === category)));
        const merged = new Map(state.tasks.map(task => [Number(task.id), task]));
        updates.forEach(task => merged.set(Number(task.id), task));
        const ordered = [...merged.values()].sort((a, b) => Number(b.id) - Number(a.id));
        const pinned = merged.get(pinnedTaskId);
        state.tasks = pinned && ownsResource(user, pinned)
          ? [pinned, ...ordered.filter(task => Number(task.id) !== pinnedTaskId)].slice(0, 100)
          : ordered.slice(0, 100);
      } else {
        const listed = Array.isArray(result) ? result : [];
        if (pinnedTaskId && !listed.some(task => Number(task.id) === pinnedTaskId)) {
          const selected = await runtime.request(token, signal => api.taskDetails(pinnedTaskId,
            { report_category: category, ...ruleQuery, only_issues: onlyIssues }, { signal }));
          if (!runtime.current(token)) return;
          state.tasks = ownsResource(user, selected) ? [selected, ...listed].slice(0, 100) : listed;
        } else state.tasks = listed;
      }
      state.tasksStatus = "success";
      if (!state.tasks.some((task) => Number(task.id) === Number(state.activeTaskId))) {
        state.activeTaskId = state.tasks[0]?.id ?? null; resetDetail();
      }
      if (detailData && Number(detailData.id) !== Number(state.activeTaskId)) resetDetail();
      renderAll();
      // 包括运行→结束的最后一次轮询，最终规则与异常均刷新后再停止。
      if (state.activeTab === "results" && ownsResource(user, currentTask())) {
        await loadDetail({ silent: poll });
        if (runtime.current(token) && selectedTab === "issues" && issueRuleId
            && (Number(selectedRule?.violation_count) > 0 || state.issuesStatus === "success")) await loadIssues({ silent: poll });
      }
      else { detailData = null; state.issues = emptyPage(state.issueQuery.page_size); renderAll(); }
      if (runtime.current(token)) schedulePoll();
    } catch (error) {
      if (!runtime.current(token)) return;
      state.tasksStatus = "error"; state.tasksError = errorMessage(error, "批次加载失败"); renderAll();
      if (!poll) notify(state.tasksError, "error"); schedulePoll();
    }
  }
  async function selectTask(id) {
    if (!state.tasks.some((task) => Number(task.id) === Number(id))) return;
    runtime.clearTimer(pollTimer); pollTimer = null; state.activeTaskId = id; resetDetail(); renderAll();
    pinnedTaskId = Number(id);
    if (ownsResource(user, currentTask())) await loadDetail();
    schedulePoll();
  }
  async function loadDetail({ silent = false } = {}) {
    const id = state.activeTaskId; const category = reportCategory;
    if (!id || !ownsResource(user, currentTask())) return;
    const token = runtime.next("task-detail");
    if (!silent || !detailData) detailStatus = "loading";
    detailError = ""; renderAll();
    try {
      const result = await runtime.request(token, signal => api.taskDetails(id, { report_category: category,
        ...ruleQuery, only_issues: onlyIssues }, { signal }));
      if (!runtime.current(token) || Number(id) !== Number(state.activeTaskId) || category !== reportCategory) return;
      detailData = result; detailStatus = "success";
      if (selectedRule) {
        const refreshed = result.rules?.find(rule => Number(rule.rule_id) === issueRuleId);
        if (refreshed) selectedRule = sameReviewVersion(selectedRule, refreshed) ? { ...selectedRule, ...refreshed } : refreshed;
      }
      if (result.rule_page) { ruleQuery.page = result.rule_page.page; ruleQuery.page_size = result.rule_page.page_size; }
    } catch (error) {
      if (!runtime.current(token)) return;
      detailStatus = "error"; detailError = errorMessage(error, "规则执行结果加载失败");
    } finally { if (runtime.current(token)) renderAll(); }
  }
  function sameReviewVersion(snapshot, version) {
    return Number(snapshot.rule_id) === Number(version.rule_id ?? version.id)
      && Number(snapshot.version_no) > 0 && Number(snapshot.version_no) === Number(version.version_no)
      && (!snapshot.version_id || Number(snapshot.version_id) === Number(version.version_id))
      && (!snapshot.content_sha256 || snapshot.content_sha256 === version.content_sha256);
  }
  function missingReviewFields(rule) {
    return rule?.sql_text === undefined || (rule?.description === undefined && rule?.violation_message === undefined);
  }
  function reviewSql(rule) { return visibleSql(rule); }
  async function loadRuleReview() {
    const snapshot = selectedRule, taskId = state.activeTaskId, category = reportCategory;
    if (!snapshot || !missingReviewFields(snapshot) || typeof api.rule !== "function"
        || !snapshot.rule_id || !snapshot.version_no || !ownsResource(user, currentTask())) return;
    const token = runtime.next("task-review"); reviewStatus = "loading"; renderAll();
    try {
      const version = await runtime.request(token, signal => api.rule(snapshot.rule_id, { signal }));
      if (!runtime.current(token) || Number(taskId) !== Number(state.activeTaskId) || category !== reportCategory
          || selectedTab !== "issues" || !selectedRule || !sameReviewVersion(snapshot, selectedRule)) return;
      // 同一规则的版本号创建后不复用；若快照提供 ID/哈希，也必须一致，才补充字段。
      if (!sameReviewVersion(snapshot, version)) { reviewStatus = "unavailable"; return; }
      selectedRule = { ...selectedRule,
        description: selectedRule.description ?? version.definition?.description ?? "",
        violation_message: selectedRule.violation_message ?? version.definition?.violation_message ?? "",
        sql_text: selectedRule.sql_text ?? version.sql_text ?? "",
        sql_display: selectedRule.sql_display ?? version.sql_display,
        sql_display_error: selectedRule.sql_display_error ?? version.sql_display_error };
      reviewStatus = "ready";
    } catch {
      if (runtime.current(token)) reviewStatus = "unavailable";
    } finally { if (runtime.current(token)) renderAll(); }
  }
  async function loadIssues({ silent = false } = {}) {
    const taskId = state.activeTaskId; const selection = scope();
    if (!taskId || !issueRuleId || selectedTab !== "issues" || !ownsResource(user, currentTask())) { renderAll(); return; }
    const token = runtime.next("task-issues");
    if (!silent) state.issuesStatus = "loading";
    state.issuesError = ""; renderAll();
    try {
      const result = await loadConvergedPage({ query: { ...state.issueQuery, ...selection },
        onConverge: (page) => { state.issueQuery.page = page; }, isCurrent: () => runtime.current(token),
        request: (query) => runtime.request(token, (signal) => api.issues(taskId, query, { signal })),
      });
      if (!runtime.current(token) || Number(taskId) !== Number(state.activeTaskId) || selection.report_category !== reportCategory || (selection.rule_id || null) !== issueRuleId) return;
      state.issues = { ...result, page: state.issueQuery.page, page_size: state.issueQuery.page_size, items: Array.isArray(result.items) ? result.items : [] };
      state.issuesStatus = "success";
    } catch (error) {
      if (!runtime.current(token)) return;
      state.issuesStatus = "error"; state.issuesError = errorMessage(error, "异常明细加载失败");
      if (!silent) notify(state.issuesError, "error");
    } finally { if (runtime.current(token)) renderAll(); }
  }
  async function cancelTask() {
    const task = currentTask();
    if (!ownsResource(user, task) || !hasCapability(user, "dv.run") || !canCancelTask(task)) return;
    if (!await confirmAction(`确定取消批次 #${task.id} 的执行吗？已完成的规则结果会保留。`)) return;
    if (!runtime.isActive()) return;
    const token = runtime.next("task-cancel"); await runtime.request(token, (signal) => api.cancelTask(task.id, { signal }));
    if (!runtime.current(token)) return;
    notify("执行已取消，已完成的结果已保留", "success"); await loadTasks();
  }
  async function retryTask() {
    const task = currentTask();
    if (!ownsResource(user, task) || !hasCapability(user, "dv.run") || !canRetryTask(task)) return;
    const token = runtime.next("task-retry"); await runtime.request(token, (signal) => api.retryTask(task.id, { signal }));
    if (!runtime.current(token)) return;
    notify("已在原批次重试未完成项", "success"); await loadTasks();
  }
  async function exportIssues() {
    const task = currentTask();
    if (!ownsResource(user, task) || !hasCapability(user, "dv.export") || !issueRuleId || selectedTab !== "issues") return;
    const selection = scope(); const token = runtime.next("task-export");
    const result = await runtime.request(token, (signal) => api.exportIssues(task.id, { ...selection, signal }));
    if (!runtime.current(token) || Number(state.activeTaskId) !== Number(task.id)
        || selection.report_category !== reportCategory || (selection.rule_id || null) !== issueRuleId) return;
    downloadText({ host, runtime, filename: `validation-${task.report_period}-task-${task.id}-rule-${issueRuleId}.csv`, content: result.content, type: "text/csv;charset=utf-8" });
    notify(result.truncated ? "已导出当前范围；结果有截断，异常数据不完整" : "已导出当前筛选范围的异常", result.truncated ? "warning" : "success");
  }
  function renderCategories() {
    [...(state.categories || []), ...state.tasks.flatMap((task) => task.categories || [])].forEach((category) => {
      const code = reportCategoryCode(category.code) || "__uncategorized__";
      knownCategories.set(code, { code, name: category.name || code });
    });
    categories.replaceChildren(...[{ code: "", name: "全部分类" }, ...knownCategories.values()].map((category) => button(category.name, {
      className: `dv-category-pill${category.code === reportCategory ? " is-active" : ""}`, dataset: { resultCategory: category.code },
    })));
    [...categories.children].forEach((pill) => pill.setAttribute("aria-pressed", String(pill.dataset.resultCategory === reportCategory)));
  }
  function serverSearchedRules() { return detailData?.rule_page?.keyword === ruleQuery.keyword; }
  function searchUnavailable() {
    const page = detailData?.rule_page;
    return Boolean(ruleQuery.keyword && page && !serverSearchedRules()
      && (Number(page.page) !== 1 || Number(page.total) > (detailData.rules || []).length));
  }
  function matchingRules() {
    if (searchUnavailable()) return [];
    const keyword = ruleQuery.keyword.toLowerCase();
    return (detailData?.rules || []).filter(rule => (!onlyIssues || Number(rule.violation_count) > 0)
      && (serverSearchedRules() || !keyword || [rule.name, rule.rule_code, rule.table_name, rule.table_name_cn, rule.source_name].some(value => String(value || "").toLowerCase().includes(keyword))));
  }
  function rulePage() {
    const page = detailData?.rule_page;
    if (page && ruleQuery.keyword && !serverSearchedRules()) return { ...page, page: 1, total: matchingRules().length };
    return page || { total: matchingRules().length, ...ruleQuery };
  }
  function visibleRules() {
    const values = matchingRules();
    const start = detailData?.rule_page ? 0 : (ruleQuery.page - 1) * ruleQuery.page_size;
    return values.slice(start, start + Math.min(100, ruleQuery.page_size));
  }
  function renderRules(task, owner) {
    ruleBody.replaceChildren(); ruleFeedback.replaceChildren();
    if (!task) ruleFeedback.append(emptyState("请选择执行批次", "从上方批次选择查看规则结果及异常明细"));
    else if (!owner) ruleFeedback.append(emptyState("仅批次创建人可查看明细", "此处可查看批次摘要"));
    else if (detailStatus === "loading") ruleFeedback.append(emptyState("正在加载规则结果…"));
    else if (detailStatus === "error") ruleFeedback.append(emptyState("规则结果加载失败", detailError));
    else if (searchUnavailable()) ruleFeedback.append(emptyState("规则搜索暂不可用", "当前服务尚未加载规则搜索，请统一重载后重试"));
    else if (ruleQuery.keyword && !visibleRules().length) ruleFeedback.append(emptyState("没有匹配的规则", "试试其他规则名称、编码或表名"));
    else if (!detailData?.rules?.length) ruleFeedback.append(emptyState(onlyIssues && detailData?.summary?.rule_count
      ? "当前暂无异常规则" : "暂无规则结果", onlyIssues ? "关闭“只查看异常规则”可查看全部执行结果" : "当前分类范围内没有规则"));
    else if (!visibleRules().length) ruleFeedback.append(emptyState(ruleQuery.keyword ? "没有匹配的规则" : "当前暂无异常规则", ruleQuery.keyword ? "试试其他规则名称、编码或表名" : "关闭“只查看异常规则”可查看全部执行结果"));
    ruleWrap.hidden = Boolean(ruleFeedback.children.length);
    rulePagination.element.hidden = !task || !owner;
    rulePagination.update(rulePage(), { loading: detailStatus === "loading" });
    visibleRules().forEach((rule) => ruleBody.append(element("tr", { dataset: Number(rule.violation_count) > 0 ? { ruleIssues: rule.rule_id } : {} },
      element("td", { className: "dv-result-rule-name" }, element("strong", { text: rule.name }), element("span", { className: "dv-muted dv-code", text: `${rule.rule_code} · V${rule.version_no}` }), rule.error_code ? element("span", { className: "dv-result-error", text: rule.error_code }) : null),
      element("td", {}, categoryBadge({ code: rule.report_category, name: rule.report_category_name })),
      element("td", { className: "dv-result-target" }, element("span", { text: `${rule.source_name || "数据源名称未采集"} / ${rule.table_name_cn || rule.table_name || "目标表未采集"}` }), element("span", { className: "dv-muted dv-code", text: rule.table_name || "" })),
      element("td", {}, ruleStatus(rule)),
      element("td", { className: `dv-result-count${Number(rule.violation_count) > 0 ? " is-warning" : " is-zero"}`, text: `${rule.violation_count ?? 0}${rule.truncated ? "+（截断）" : ""}` }),
      element("td", {}, Number(rule.violation_count) > 0 ? button("查看异常", { className: "dv-table-action", dataset: { ruleIssues: rule.rule_id } }) : element("span", { className: "dv-muted", text: "-" })))));
  }
  function renderIssues(task, owner) {
    issueBody.replaceChildren(); issueFeedback.replaceChildren();
    const items = (state.issues.items || []).filter((item) => Number(item.rule_id) === issueRuleId);
    const columns = queryColumns(items);
    const captureMessage = [...new Set(items.map(queryCaptureNotice).filter(Boolean))].join("；");
    if (!task) issueFeedback.append(emptyState("请选择执行批次"));
    else if (!owner) issueFeedback.append(emptyState("仅批次创建人可查看明细"));
    else if (state.issuesStatus === "loading") issueFeedback.append(emptyState("正在加载异常明细…"));
    else if (state.issuesStatus === "error") issueFeedback.append(emptyState("异常明细加载失败", state.issuesError));
    else if (!items.length) issueFeedback.append(emptyState("暂无异常记录", selectedRule?.status === "PASS" ? "本次执行未发现异常" : taskIssueNotice(task, 0)));
    else if (!columns.length) issueFeedback.append(emptyState("没有可展示的 SQL 查询明细", captureMessage || "本次记录未保存可展示的 SQL 字段"));
    const hasIssueFeedback = Boolean(issueFeedback.children.length);
    issueFeedback.hidden = !hasIssueFeedback;
    issueWrap.hidden = hasIssueFeedback;
    issueHead.replaceChildren(element("tr", {}, element("th", { text: "序号" }), ...columns.map((column) => element("th", { text: column.name }))));
    items.forEach((issue, index) => issueBody.append(element("tr", {},
      element("td", { className: "dv-result-row-number", text: (state.issueQuery.page - 1) * state.issueQuery.page_size + index + 1 }),
      ...columns.map((column) => {
        const value = queryValue(issue, column);
        return element("td", { className: `dv-query-value dv-code${value.length < 80 && !value.includes("\n") ? " is-short" : ""}`, text: value });
      }))));
    captureNotice.textContent = captureMessage;
    captureNotice.hidden = hasIssueFeedback || !captureNotice.textContent;
    ruleScope.hidden = !issueRuleId;
    ruleScope.children[0].replaceChildren(element("strong", { text: selectedRule?.name || "当前规则" }),
      element("span", { className: "dv-muted", text: `${selectedRule?.rule_code || "—"} · v${selectedRule?.version_no ?? "—"} · ${selectedRule?.report_category_name || "未分类"} · ${selectedRule?.violation_count ?? state.issues.total} 条异常` }));
    pagination.element.hidden = !task || !owner;
    pagination.update(state.issues, { loading: state.issuesStatus === "loading" || !task });
  }
  function render() {
    period.value = state.reportPeriod; periodText.textContent = state.reportPeriod; renderCategories();
    const task = currentTask(); const owner = ownsResource(user, task);
    resultCard.classList.toggle("is-awaiting-task", !task);
    batches.update(state.tasks, state.activeTaskId, { status: state.tasksStatus, error: state.tasksError, reportPeriod: state.reportPeriod });
    detail.replaceChildren(); summary.replaceChildren();
    if (task) {
      const info = taskStatus(task);
      detail.append(element("div", { className: "dv-result-title" }, element("h2", { text: `批次 #${task.id}` }), statusBadge(info.label, info.tone)),
        element("div", { className: "dv-task-facts" }, element("span", { text: `报送期 ${task.report_period || "—"}` }), element("span", { text: `创建于 ${formatDateTime(task.created_at)}` })),
        element("div", { className: "dv-batch-categories" }, ...(task.categories || []).map(categoryBadge)));
      const data = detailData?.summary || task.summary;
      if (data) summary.append(element("span", { text: `${reportCategory ? "当前分类 · " : ""}已完成 ${data.completed_count + data.failed_count} / ${data.rule_count} 条规则` }),
        element("strong", { className: data.issue_count ? "is-warning" : "", text: `异常 ${data.issue_count} 条` }),
        element("span", { className: data.failed_count ? "is-danger" : "", text: `未成功 ${data.failed_count} 条规则` }));
      if (data?.truncated ?? task.truncated) summary.append(element("strong", { className: "dv-truncated", text: "当前范围结果已截断，异常数据不完整" }));
    }
    cancel.hidden = !owner || !hasCapability(user, "dv.run") || !canCancelTask(task);
    retry.hidden = !owner || !hasCapability(user, "dv.run") || !canRetryTask(task);
    exportButton.hidden = !owner || !hasCapability(user, "dv.export") || selectedTab !== "issues" || !issueRuleId;
    exportButton.textContent = "导出明细";
    notice.textContent = task && task.status !== "completed" ? taskIssueNotice(task, state.issues.total) : "";
    notice.className = "dv-result-notice is-warning";
    rulesTab.textContent = `规则执行（${detailData ? rulePage().total : "—"}）`;
    rulesTab.setAttribute("aria-selected", String(selectedTab === "rules")); rulesTab.classList.toggle("is-active", selectedTab === "rules");
    onlyIssuesSwitch.classList.toggle("on", onlyIssues); onlyIssuesSwitch.setAttribute("aria-checked", String(onlyIssues));
    onlyIssuesSwitch.disabled = !task || !owner || detailStatus === "loading";
    toolbar.hidden = false; rulesPanel.hidden = false;
    overlay.hidden = selectedTab !== "issues" || !owner || !selectedRule;
    issuesPanel.hidden = selectedTab !== "issues";
    if (selectedRule) {
      reviewName.textContent = selectedRule.name || "规则明细";
      reviewTotal.textContent = `共 ${selectedRule.violation_count ?? 0} 条${selectedRule.truncated ? "（已截断）" : ""}`;
      reviewFacts.replaceChildren(element("span", { className: "dv-review-rule-code dv-code", text: `${selectedRule.rule_code || "—"} · V${selectedRule.version_no ?? "—"}` }),
        categoryBadge({ code: selectedRule.report_category, name: selectedRule.report_category_name }), ruleStatus(selectedRule));
      reviewSource.replaceChildren(element("div", { className: "dv-muted", text: "数据源 / 目标表" }),
        element("strong", { text: `${selectedRule.source_name || "数据源名称未采集"} / ${selectedRule.table_name_cn || selectedRule.table_name || "目标表未采集"}` }),
        element("div", { className: "dv-muted dv-code", text: selectedRule.table_name || "" }));
      reviewBatch.replaceChildren(element("div", { className: "dv-muted", text: "执行批次与检出" }),
        element("strong", { className: "dv-code", text: `#${task?.id} · ${formatDateTime(task?.created_at)}` }),
        element("div", { className: "dv-review-found dv-code", text: `发现 ${selectedRule.violation_count ?? 0} 条异常记录` }));
      const reviewPending = reviewStatus === "loading";
      const reviewUnavailable = missingReviewFields(selectedRule);
      reviewDescription.textContent = selectedRule.description || selectedRule.violation_message
        || (reviewPending ? "正在加载本次执行口径…" : reviewUnavailable
          ? "当前服务未提供本次执行版本的口径说明，请统一重载后重试。" : "此执行版本未采集口径说明。");
      const sql = reviewSql(selectedRule);
      sqlPreview.textContent = sql || (selectedRule.sql_display_error ? "本次执行参数暂无法完整还原。" : reviewPending ? "正在加载本次执行 SQL…" : reviewUnavailable
        ? "当前服务未提供本次执行版本的 SQL 全文，请统一重载后重试。" : "此执行版本未采集 SQL 全文。");
      copySql.hidden = !sql;
    }
    renderRules(task, owner); renderIssues(task, owner);
  }
  function renderAll() { render(); onRender?.(); }
  renderAll();
  return { header, panel, render: renderAll, loadTasks, loadIssues, selectTask, stopPolling, focusTask };
}
