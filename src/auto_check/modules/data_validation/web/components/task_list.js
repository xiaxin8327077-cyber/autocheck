import { formatDateTime, isTaskActive } from "../state.js";
import { element, emptyState, statusBadge } from "./dom.js";

export function taskStatus(task) {
  const status = task?.status;
  if (status === "completed") return { label: "执行完成", tone: "success" };
  if (status === "running") return { label: "执行中", tone: "info" };
  if (status === "queued") return { label: "排队中", tone: "neutral" };
  if (status === "pausing") return { label: "暂停中", tone: "info" };
  if (status === "paused") return { label: "已暂停", tone: "warning" };
  return { label: { failed: "执行失败", partial_failed: "部分失败", cancelled: "已取消" }[status] || "状态未知", tone: "danger" };
}

export function categoryBadge(category) {
  return element("span", { className: "dv-category-badge is-accent", text: category.name || category.code || "未分类" });
}

export function createTaskList({ listen, onSelect }) {
  const entries = element("div", { className: "dv-batch-entries" });
  const feedback = element("div", { className: "dv-task-feedback" });
  const tableWrap = element("div", { className: "dv-task-table-wrap dv-scroll" }, entries);
  const root = element("div", { className: "dv-task-list" }, feedback, tableWrap);
  let tasks = [];
  listen(root, "click", (event) => {
    const target = event.target.closest("[data-task-select]");
    if (target) return onSelect(Number(target.dataset.taskSelect));
  });
  return {
    element: root,
    update(items, selectedId, { status = "success", error = "" } = {}) {
      tasks = Array.isArray(items) ? items : [];
      entries.replaceChildren();
      feedback.replaceChildren();
      if (status === "loading" && !tasks.length) feedback.append(emptyState("正在加载批次…"));
      else if (status === "error") feedback.append(emptyState("批次加载失败", error));
      else if (!tasks.length) feedback.append(emptyState("暂无执行批次", "当前筛选范围内尚无校验记录"));
      // 提示与表格只显示其一，避免空表头下再留一片空白。
      const hasFeedback = Boolean(feedback.children.length);
      feedback.hidden = !hasFeedback;
      tableWrap.hidden = hasFeedback;
      tasks.forEach((task) => {
        const selected = Number(task.id) === Number(selectedId);
        const info = taskStatus(task);
        const summary = task.summary;
        const count = summary ? `${summary.rule_count} 条规则` : "规则数量未采集";
        const conclusion = task.status === "completed" && summary
          ? summary.truncated || task.truncated ? "执行完成 · 结果截断"
            : summary.issue_count ? `执行完成 · ${summary.issue_count} 条异常` : "执行完成 · 未发现异常"
          : info.label;
        entries.append(element("button", {
          className: `dv-batch-entry${selected ? " is-selected" : ""}`,
          dataset: { taskSelect: task.id }, attrs: { type: "button", "aria-pressed": String(selected), "aria-label": `查看批次 #${task.id}` },
        },
        element("div", { className: "dv-batch-entry-title" }, element("strong", { text: `批次 #${task.id}` }),
          task.truncated ? element("span", { className: "dv-truncated", text: "截断" }) : null),
        element("span", { className: "dv-batch-meta", text: `${formatDateTime(task.created_at)} · ${count}` }),
        element("div", { className: "dv-batch-categories" }, ...(task.categories || []).map(categoryBadge)),
        statusBadge(conclusion, task.status === "completed" && summary?.issue_count ? "warning" : info.tone),
        isTaskActive(task) && summary ? element("span", { className: "dv-batch-meta", text: `已完成 ${summary.completed_count + summary.failed_count} / ${summary.rule_count}` }) : null));
      });
    },
  };
}
