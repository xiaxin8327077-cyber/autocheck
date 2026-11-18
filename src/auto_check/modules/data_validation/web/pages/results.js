import { errorMessage } from "../runtime.js";
import {
  canCancelTask, canRetryTask, emptyPage, formatDateTime, hasCapability, isTaskActive,
  loadConvergedPage, ownsResource, taskIssueNotice, TASK_STATUS_LABELS,
} from "../state.js";
import { button, downloadText, element, emptyState, field, input, statusBadge } from "../components/dom.js";
import { createPageHeader } from "../components/page_header.js";
import { createPagination } from "../components/pagination.js";
import { createTaskList } from "../components/task_list.js";

const PROJECT_NAME_STATUS_LABELS = {
  ok: "已定位", missing_code: "项目编号缺失", missing_null: "项目名称缺失",
  missing_reference: "未找到对应项目", duplicate: "项目关联重复", unmapped: "项目名称未映射",
  not_required: "非项目校验", legacy_unavailable: "历史记录未采集",
};

function projectStatus(issue) {
  const code = issue.project_name_status || "legacy_unavailable";
  if (code === "ok" && (issue.project_code == null || !String(issue.project_code).trim()
      || issue.project_name == null || !String(issue.project_name).trim())) {
    return statusBadge("项目定位信息不完整", "warning");
  }
  return statusBadge(PROJECT_NAME_STATUS_LABELS[code] || "项目定位待核实",
    code === "ok" ? "success" : code === "not_required" ? "neutral" : "warning");
}

function issueKind(issue) {
  const kind = issue.issue_kind || "legacy";
  const labels = { missing_value: "缺值待核实", numeric: "数值不符", comparison: "条件命中", legacy: "历史未采集" };
  return statusBadge(labels[kind] || "类型待核实", ["missing_value", "numeric"].includes(kind) ? "warning" : "neutral");
}

export function createResultsPage({
  state, runtime, api, listen, user, notify, confirmAction, host,
  onNewTask, onPeriodChange, onNewTaskStarted, onRender,
}) {
  const header = createPageHeader({
    section: "校验执行与结果",
    title: "校验任务与异常结果",
    description: "查看真实批次状态和已登记异常；失败、超时或取消不会被写成零异常通过",
    actions: [button("▶ 新建校验任务", {
      listen, className: "dv-button dv-button-primary", hidden: !hasCapability(user, "dv.run"),
      capability: "dv.run", onClick: () => onNewTask(),
    })],
  });
  const period = input({ type: "date", value: state.reportPeriod, dataset: { reportPeriod: "results" } });
  listen(period, "change", () => onPeriodChange(period.value));
  const tasks = createTaskList({ listen, onSelect: (id) => selectTask(id) });
  const detail = element("div", { className: "dv-task-detail" });
  const cancel = button("取消任务", { listen, className: "dv-button dv-button-danger", onClick: cancelTask });
  const retry = button("重试失败项", { listen, onClick: retryTask });
  const exportButton = button("导出已登记异常 CSV", { listen, capability: "dv.export", onClick: exportIssues });
  const actions = element("div", { className: "dv-card-actions" }, cancel, retry, exportButton);
  const notice = element("p", { className: "dv-result-notice" });
  const issueBody = element("tbody");
  const issueTable = element("table", { className: "dv-table dv-issue-table" },
    element("thead", {}, element("tr", {}, ...["异常编号", "规则 ID / 版本", "项目编号", "项目名称", "明细业务键", "项目定位", "核查类型", "异常说明", "登记时间"].map((label) => element("th", { text: label })))), issueBody);
  const issueWrap = element("div", { className: "dv-issue-table-wrap dv-scroll" }, issueTable);
  const issueFeedback = element("div", { className: "dv-issue-feedback" });
  const pagination = createPagination({
    listen,
    onPage: (page) => { state.issueQuery.page = Math.max(1, page); loadIssues(); },
    onPageSize: (size) => { state.issueQuery = { page: 1, page_size: size }; loadIssues(); },
  });
  const issuesCard = element("section", { className: "dv-card dv-issues-card" },
    element("div", { className: "dv-card-heading" }, element("h2", { text: "异常明细" }), actions),
    detail, notice, issueFeedback, issueWrap, pagination.element);
  const panel = element("section", { className: "dv-tab-panel dv-results-panel dv-panel-content", dataset: { panel: "results" }, attrs: { role: "tabpanel" } },
    element("div", { className: "dv-filters" }, field("报送期", period)),
    element("div", { className: "dv-results-grid" },
      element("section", { className: "dv-card dv-batches-card" },
        element("div", { className: "dv-card-heading" }, element("h2", { text: "执行批次" })), tasks.element),
      issuesCard));
  let pollTimer = null;

  function currentTask() {
    return state.tasks.find((task) => Number(task.id) === Number(state.activeTaskId)) || null;
  }

  function stopPolling() {
    runtime.clearTimer(pollTimer);
    pollTimer = null;
    runtime.invalidate("task-list");
    runtime.invalidate("task-issues");
  }

  function schedulePoll() {
    runtime.clearTimer(pollTimer);
    pollTimer = null;
    if (!runtime.isActive() || state.activeTab !== "results" || !state.tasks.some(isTaskActive)) return;
    pollTimer = runtime.setTimer(() => loadTasks({ poll: true }), 2500);
  }

  async function loadTasks({ poll = false } = {}) {
    const token = runtime.next("task-list");
    const reportPeriod = state.reportPeriod;
    if (!poll) state.tasksStatus = "loading";
    state.tasksError = "";
    renderAll();
    try {
      const result = await runtime.request(token, (signal) => api.tasks({ report_period: reportPeriod }, { signal }));
      if (!runtime.current(token) || state.reportPeriod !== reportPeriod) return;
      state.tasks = Array.isArray(result) ? result : [];
      state.tasksStatus = "success";
      let selectionChanged = false;
      if (!state.tasks.some((task) => Number(task.id) === Number(state.activeTaskId))) {
        state.activeTaskId = state.tasks[0]?.id ?? null;
        state.issueQuery.page = 1;
        selectionChanged = true;
      }
      if (!state.activeTaskId) state.issues = emptyPage(state.issueQuery.page_size);
      renderAll();
      if (state.activeTab === "results" && state.activeTaskId
          && (selectionChanged || !poll || (poll && isTaskActive(currentTask())))) {
        await loadIssues({ silent: poll });
      }
      if (!runtime.current(token)) return;
      schedulePoll();
    } catch (error) {
      if (!runtime.current(token)) return;
      state.tasksStatus = "error";
      state.tasksError = errorMessage(error, "任务加载失败");
      renderAll();
      if (!poll) notify(state.tasksError, "error");
      schedulePoll();
    }
  }

  async function selectTask(id) {
    if (!state.tasks.some((task) => Number(task.id) === Number(id))) return;
    runtime.clearTimer(pollTimer);
    pollTimer = null;
    state.activeTaskId = id;
    state.issueQuery.page = 1;
    state.issues = emptyPage(state.issueQuery.page_size);
    renderAll();
    await loadIssues();
    schedulePoll();
  }

  async function loadIssues({ silent = false } = {}) {
    const taskId = state.activeTaskId;
    if (!taskId) { renderAll(); return; }
    const token = runtime.next("task-issues");
    if (!silent) state.issuesStatus = "loading";
    state.issuesError = "";
    renderAll();
    try {
      const result = await loadConvergedPage({
        query: { ...state.issueQuery },
        onConverge: (page) => { state.issueQuery.page = page; },
        isCurrent: () => runtime.current(token),
        request: (query) => runtime.request(token, (signal) => api.issues(taskId, query, { signal })),
      });
      if (!runtime.current(token) || Number(state.activeTaskId) !== Number(taskId)) return;
      state.issues = {
        ...result,
        page: state.issueQuery.page,
        page_size: state.issueQuery.page_size,
        items: Array.isArray(result.items) ? result.items : [],
      };
      state.issuesStatus = "success";
    } catch (error) {
      if (!runtime.current(token)) return;
      state.issuesStatus = "error";
      state.issuesError = errorMessage(error, "异常明细加载失败");
      if (!silent) notify(state.issuesError, "error");
    } finally {
      if (runtime.current(token)) renderAll();
    }
  }

  async function cancelTask() {
    const task = currentTask();
    if (!task) return;
    if (!await confirmAction(`确定取消任务 #${task.id} 吗？已完成的规则结果会保留。`)) return;
    if (!runtime.isActive()) return;
    const token = runtime.next("task-cancel");
    await runtime.request(token, (signal) => api.cancelTask(task.id, { signal }));
    if (!runtime.current(token)) return;
    notify("任务已取消，未完成项不会显示为通过", "success");
    await loadTasks();
  }

  async function retryTask() {
    const task = currentTask();
    if (!task) return;
    const token = runtime.next("task-retry");
    await runtime.request(token, (signal) => api.retryTask(task.id, { signal }));
    if (!runtime.current(token)) return;
    notify("已调用既有重试接口，仅重试失败、超时或取消项", "success");
    await loadTasks();
  }

  async function exportIssues() {
    const task = currentTask();
    if (!task) return;
    const token = runtime.next("task-export");
    const result = await runtime.request(token, (signal) => api.exportIssues(task.id, { signal }));
    if (!runtime.current(token)) return;
    downloadText({
      host, runtime, filename: `validation-${task.report_period}-task-${task.id}.csv`,
      content: result.content, type: "text/csv;charset=utf-8",
    });
    notify(result.truncated ? "CSV 已导出；任务结果被标记为截断，不代表完整异常全集" : "已导出当前任务异常 CSV", result.truncated ? "warning" : "success");
  }

  function render() {
    period.value = state.reportPeriod;
    const task = currentTask();
    tasks.update(state.tasks, state.activeTaskId, { status: state.tasksStatus, error: state.tasksError });
    detail.replaceChildren();
    if (task) {
      detail.append(
        element("div", { className: "dv-task-facts" },
          element("span", { text: `任务 #${task.id} · 第 ${task.run_no ?? "—"} 次` }),
          element("span", { text: `报送期 ${task.report_period || "—"}` }),
          element("span", { text: `创建时间 ${formatDateTime(task.created_at)}` }),
          statusBadge(TASK_STATUS_LABELS[task.status] || task.status, task.status === "completed" ? "success" : isTaskActive(task) ? "warning" : "danger"),
          task.truncated ? element("span", { className: "dv-truncated", text: "结果已截断，不能视为完整异常全集" }) : null));
    } else detail.append(element("p", { className: "dv-muted", text: "请选择左侧批次查看异常明细" }));
    const owner = ownsResource(user, task);
    cancel.hidden = !task || !owner || !hasCapability(user, "dv.run") || !canCancelTask(task);
    retry.hidden = !task || !owner || !hasCapability(user, "dv.run") || !canRetryTask(task);
    exportButton.hidden = !task || !owner || !hasCapability(user, "dv.export");
    notice.textContent = task ? taskIssueNotice(task, state.issues.total) : "";
    notice.className = `dv-result-notice${task && task.status !== "completed" ? " is-warning" : ""}`;
    issueBody.replaceChildren();
    issueFeedback.replaceChildren();
    if (state.issuesStatus === "loading") issueFeedback.append(emptyState("正在加载异常明细…"));
    else if (state.issuesStatus === "error") issueFeedback.append(emptyState("异常明细加载失败", state.issuesError));
    else if (task && !state.issues.items.length) issueFeedback.append(emptyState("暂无数据", taskIssueNotice(task, 0)));
    // 提示与明细表只显示其一，避免空表头下再留一片空白。
    const hasIssueFeedback = Boolean(issueFeedback.children.length);
    issueFeedback.hidden = !hasIssueFeedback;
    issueWrap.hidden = hasIssueFeedback;
    (state.issues.items || []).forEach((issue) => issueBody.append(element("tr", {},
      element("td", { className: "dv-code", text: issue.id }),
      element("td", { text: `${issue.rule_id ?? "—"} / v${issue.version_no ?? "—"}` }),
      element("td", { className: "dv-code", text: issue.project_code ?? "—" }),
      element("td", { className: "dv-project-name", text: issue.project_name ?? "—", attrs: { title: issue.project_name ?? "" } }),
      element("td", { className: "dv-code", text: issue.business_key ?? "—" }),
      element("td", {}, projectStatus(issue)),
      element("td", {}, issueKind(issue)),
      element("td", { text: issue.message || "—" }),
      element("td", { className: "dv-date", text: formatDateTime(issue.created_at) }))));
    pagination.update(state.issues, { loading: state.issuesStatus === "loading" || !task });
  }

  function renderAll() {
    render();
    onRender?.();
  }

  renderAll();
  return { header, panel, render: renderAll, loadTasks, loadIssues, selectTask, stopPolling };
}
