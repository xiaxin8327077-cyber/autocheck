import { formatDateTime, TASK_STATUS_LABELS } from "../state.js";
import { button, element, emptyState, statusBadge } from "./dom.js";

function tone(status) {
  if (status === "completed") return "success";
  if (["failed", "partial_failed", "cancelled"].includes(status)) return "danger";
  if (["queued", "running"].includes(status)) return "warning";
  return "neutral";
}

export function createTaskList({ listen, onSelect }) {
  const body = element("tbody");
  const feedback = element("div", { className: "dv-task-feedback" });
  const table = element("table", { className: "dv-table dv-task-table" },
    element("thead", {}, element("tr", {}, ...["任务 / 批次", "报送期", "数据源", "任务状态", "创建时间", "结果截断", "操作"].map((label) => element("th", { text: label })))), body);
  const tableWrap = element("div", { className: "dv-task-table-wrap dv-scroll" }, table);
  const root = element("div", { className: "dv-task-list" }, feedback, tableWrap);
  let tasks = [];
  listen(root, "click", (event) => {
    const target = event.target.closest("[data-task-select]");
    if (target) onSelect(Number(target.dataset.taskSelect));
  });
  return {
    element: root,
    update(items, selectedId, { status = "success", error = "" } = {}) {
      tasks = Array.isArray(items) ? items : [];
      body.replaceChildren();
      feedback.replaceChildren();
      if (status === "loading" && !tasks.length) feedback.append(emptyState("正在加载任务…"));
      else if (status === "error") feedback.append(emptyState("任务加载失败", error));
      else if (!tasks.length) feedback.append(emptyState("暂无数据", "当前报送期尚无校验任务"));
      // 提示与表格只显示其一，避免空表头下再留一片空白。
      const hasFeedback = Boolean(feedback.children.length);
      feedback.hidden = !hasFeedback;
      tableWrap.hidden = hasFeedback;
      tasks.forEach((task) => {
        const row = element("tr", { className: Number(task.id) === Number(selectedId) ? "is-selected" : "" },
          element("td", {}, element("strong", { text: `任务 #${task.id}` }), element("span", { text: `第 ${task.run_no ?? "—"} 次执行` })),
          element("td", { text: task.report_period || "—" }),
          element("td", { text: task.source_id || "按规则快照" }),
          element("td", {}, statusBadge(TASK_STATUS_LABELS[task.status] || task.status || "未知", tone(task.status))),
          element("td", { className: "dv-date", text: formatDateTime(task.created_at) }),
          element("td", { text: task.truncated ? "是（结果不完整）" : "否" }),
          element("td", {}, button("查看异常", { className: "dv-table-action", dataset: { taskSelect: task.id } })));
        body.append(row);
      });
    },
  };
}
