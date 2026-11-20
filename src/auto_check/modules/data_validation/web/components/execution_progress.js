import { isTaskActive, targetTableLabel, taskIssueNotice } from "../state.js";
import { createDialog } from "./dialog.js";
import { button, element, emptyState, statusBadge } from "./dom.js";
import { aiIcon } from "./ai_visuals.js";
import { taskStatus } from "./task_list.js";
import { createPagination } from "./pagination.js";

export const isExecutionPending = task => isTaskActive(task) || task?.status === "paused";

export function executionSummary(task) {
  if (!task?.summary) return null;
  const count = value => Math.max(0, Number(value) || 0);
  const total = count(task.summary.rule_count);
  const finished = Math.min(total, count(task.summary.completed_count) + count(task.summary.failed_count));
  return { total, finished, failed: count(task.summary.failed_count), issues: count(task.summary.issue_count),
    percent: total ? Math.floor(finished * 100 / total) : 0,
    truncated: Boolean(task.truncated || task.summary.truncated) };
}

function rowStatus(rule) {
  if (rule.truncated && ["PASS", "VIOLATION"].includes(rule.status)) return ["结果截断", "warning", "info"];
  if (rule.status === "PASS") return ["已完成 · 无异常", "success", "check"];
  if (rule.status === "VIOLATION") return [`已完成 · ${Number(rule.violation_count) || 0} 条异常`, "warning", "info"];
  if (["RUNNING", "running"].includes(rule.status)) return ["执行中", "primary", "scope"];
  if (["PENDING", "queued"].includes(rule.status)) return ["等待执行", "neutral", "info"];
  return [{ ERROR: "执行失败", TIMEOUT: "执行超时", CANCELLED: "已取消" }[rule.status] || "状态未知", "danger", "info"];
}

export function openExecutionProgress({ host, task, canStop = false, onStop, onPause, onResume, onResults, onClose, onRetry, onPage, onPageSize }) {
  let currentTask = task;
  const dialog = createDialog({ host, title: "执行校验", icon: aiIcon("database"), subtitle: "执行进度",
    className: "dv-task-dialog dv-execution-progress-dialog", onClose });
  const context = element("div", { className: "dv-execution-context" });
  const count = element("strong", { className: "dv-execution-count" });
  const status = element("span");
  const issues = element("span", { className: "dv-execution-issue-count" });
  const bar = element("span", { className: "dv-execution-progress-fill" });
  const track = element("div", { className: "dv-execution-progress-track", attrs: { role: "progressbar",
    "aria-label": "校验执行进度", "aria-valuemin": "0", "aria-valuemax": "100" } }, bar);
  const percentage = element("span", { className: "dv-execution-percentage" });
  const progress = element("div", { className: "dv-execution-progress-line" }, track, percentage);
  const notice = element("p", { className: "dv-execution-notice", attrs: { role: "status" } });
  const feedback = element("div", { className: "dv-feedback is-error", hidden: true, attrs: { role: "alert" } });
  const retry = button("重试读取", { className: "dv-button dv-button-plain" });
  dialog.bind(retry, "click", () => onRetry?.());
  const rows = element("tbody");
  const table = element("table", { className: "dv-table dv-execution-progress-table" },
    element("thead", {}, element("tr", {}, ...["规则名称", "目标数据表", "执行结果"].map(text => element("th", { text })))), rows);
  const tableWrap = element("div", { className: "dv-execution-progress-table-wrap dv-scroll" }, table);
  const empty = element("div", { className: "dv-execution-progress-empty" });
  const pagination = createPagination({ listen: dialog.bind, onPage: page => onPage?.(page),
    onPageSize: size => onPageSize?.(size) });
  const list = element("section", { className: "dv-execution-progress-list" }, tableWrap, empty, pagination.element);
  dialog.body.append(context, element("div", { className: "dv-execution-summary" },
    element("div", { className: "dv-execution-summary-heading" }, count, status, issues), progress),
  feedback, notice, list);
  const footerNote = element("span", { className: "dv-execution-footer-note" });
  const background = button("后台继续", { className: "dv-button" });
  const stop = button("停止执行", { className: "dv-button dv-button-danger", capability: "dv.run" });
  const pause = button("暂停执行", { className: "dv-button", capability: "dv.run" });
  const results = button("查看结果", { className: "dv-button dv-button-primary", capability: "dv.view_results" });
  dialog.footer.append(footerNote, background, pause, stop, results);
  dialog.bind(background, "click", dialog.close);
  dialog.bind(stop, "click", () => onStop?.());
  dialog.bind(pause, "click", () => currentTask?.status === "paused" ? onResume?.() : onPause?.());
  dialog.bind(results, "click", () => onResults?.());
  dialog.update = (value, { loading = false, error = "", cancelling = false, action = "" } = {}) => {
    if (dialog.isClosed()) return;
    const current = value || {};
    currentTask = current;
    const summary = executionSummary(current);
    const active = isExecutionPending(current);
    const rowLimit = Math.min(100, Math.max(1, Number(current.rule_page?.page_size) || 20));
    const ruleRows = Array.isArray(current.rules) ? current.rules.slice(0, rowLimit) : [];
    const fullSources = Array.isArray(current.sources);
    const names = fullSources ? current.sources.map(source => source.name || source.id).filter(Boolean)
      : [...new Set(ruleRows.map(rule => rule.source_name).filter(Boolean))];
    context.replaceChildren(...[["报送期", current.report_period || "—"],
      ["报送分类", (current.categories || []).map(category => category.name || category.code).join("、") || "正在读取"],
      [fullSources ? "数据源" : "当前页数据源", names.join("、") || "正在读取"]].map(([label, text]) => element("span", {},
      element("span", { className: "dv-muted", text: `${label}：` }), element("strong", { text }))));
    count.textContent = summary ? `${summary.failed ? "已结束" : "已完成"} ${summary.finished} / ${summary.total} 条` : "正在读取执行进度";
    const tone = taskStatus(current);
    status.replaceChildren(statusBadge(tone.label, tone.tone));
    issues.textContent = summary ? `已发现 ${summary.issues} 条异常` : "异常数量待返回";
    issues.classList.toggle("has-issues", Boolean(summary?.issues));
    progress.hidden = !summary;
    track.setAttribute("aria-valuenow", String(summary?.percent || 0));
    bar.setAttribute("style", `width: ${summary?.percent || 0}%`);
    percentage.textContent = summary ? `${summary.percent}%` : "—";
    notice.textContent = [summary?.failed ? `${summary.failed} 条规则失败或已取消。` : "",
      summary?.truncated ? "部分结果已截断。" : "", taskIssueNotice(current, summary?.issues || 0)].filter(Boolean).join(" ");
    notice.hidden = !notice.textContent;
    feedback.hidden = !error;
    feedback.replaceChildren(...(error ? [element("span", { text: error }), retry] : []));
    tableWrap.hidden = !ruleRows.length;
    empty.hidden = Boolean(ruleRows.length);
    empty.replaceChildren(...(ruleRows.length ? [] : [emptyState(error ? "执行进度暂不可用" : loading ? "正在读取规则执行进度…" : "暂无规则执行记录")]));
    pagination.update(current.rule_page || { total: summary?.total || ruleRows.length, page: 1, page_size: 20 }, { loading });
    rows.replaceChildren(...ruleRows.map(rule => {
      const [label, color, icon] = rowStatus(rule);
      const running = ["RUNNING", "running"].includes(rule.status);
      return element("tr", { className: running ? "is-running" : "" },
        element("td", {}, element("strong", { text: rule.name || "未命名规则" }),
          element("span", { className: "dv-execution-rule-meta", text: `${rule.rule_code || ""}${rule.version_no ? ` · v${rule.version_no}` : ""}` })),
        element("td", {}, element("span", { text: targetTableLabel(rule) }),
          element("span", { className: "dv-execution-rule-meta", text: rule.source_name || "数据源名称未采集" })),
        element("td", {}, element("span", { className: `dv-execution-rule-status is-${color}` }, aiIcon(icon, running ? "is-running" : ""), label)));
    }));
    footerNote.textContent = current.status === "paused" ? "任务已暂停，可稍后继续执行。" : current.status === "pausing"
      ? "当前查询结束后暂停，已完成结果会保留。" : active ? "关闭窗口后仍会在后台继续执行。" : `批次 #${current.id || "—"} · ${tone.label}`;
    background.textContent = active && current.status !== "paused" ? "后台继续" : "关闭";
    stop.hidden = !canStop || !active;
    stop.disabled = cancelling || Boolean(action);
    stop.textContent = cancelling ? "正在停止…" : "停止执行";
    pause.hidden = !canStop || !active;
    pause.disabled = Boolean(action) || current.status === "pausing";
    pause.textContent = action === "resume" ? "正在继续…" : current.status === "pausing" || action === "pause"
      ? "正在暂停…" : current.status === "paused" ? "继续执行" : "暂停执行";
    results.hidden = active;
    results.disabled = Boolean(error && !summary);
    dialog.body.setAttribute("aria-busy", String(loading));
  };
  dialog.update(task, { loading: !task?.rules });
  return dialog;
}
