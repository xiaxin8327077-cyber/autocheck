import { errorMessage } from "../runtime.js";
import {
  emptyPage, formatDateTime, loadConvergedPage, RULE_STATUS_LABELS,
} from "../state.js";
import { createDialog } from "./dialog.js";
import { button, element, emptyState, statusBadge } from "./dom.js";
import { createPagination } from "./pagination.js";

const ACTION_META = {
  create: ["创建", "neutral"],
  update: ["修改", "primary"],
  confirm: ["确认启用", "success"],
  disable: ["停用", "danger"],
  delete: ["删除", "danger"],
  copy: ["复制", "primary"],
};

export function formatHistoryValue(value) {
  if (value === null || value === undefined || value === "") return "（空）";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value, null, 2);
    } catch (_error) {
      return String(value);
    }
  }
  return String(value);
}

function actionBadge(actionCode) {
  const [label, tone] = ACTION_META[actionCode] || [actionCode || "未知操作", "neutral"];
  return statusBadge(label, tone === "primary" ? "neutral" : tone);
}

function detailRow(item, expanded) {
  if (!expanded) return null;
  const changes = Array.isArray(item.changes) ? item.changes : [];
  const grid = element("div", { className: "dv-audit-diff-grid" },
    element("div", { className: "dv-audit-diff-head", text: "变更项" }),
    element("div", { className: "dv-audit-diff-head", text: "修改前" }),
    element("div", { className: "dv-audit-diff-head", text: "修改后" }));
  changes.forEach((change) => {
    grid.append(
      element("div", { className: "dv-audit-field", text: change.label || change.field || "未命名变更" }),
      element("div", { className: "dv-audit-before", text: formatHistoryValue(change.before) }),
      element("div", { className: "dv-audit-after", text: formatHistoryValue(change.after) }),
    );
  });
  const statusFlow = item.before_status || item.after_status
    ? element("p", { className: "dv-audit-status-flow", text: `状态：${RULE_STATUS_LABELS[item.before_status] || item.before_status || "（空）"} → ${RULE_STATUS_LABELS[item.after_status] || item.after_status || "（空）"}` })
    : null;
  return element("tr", { className: "dv-audit-detail-row", dataset: { historyDetail: item.id } },
    element("td", { attrs: { colspan: "6" } },
      element("div", { className: "dv-audit-detail" },
        statusFlow,
        changes.length ? grid : emptyState("无字段级变更明细", "该操作仅记录摘要或状态变化"))));
}

export function openHistoryDialog({
  runtime, api, host, rule, notify, onClose,
}) {
  const channel = `rule-history-${rule.id}`;
  const query = { page: 1, page_size: 20 };
  let payload = emptyPage(20);
  let status = "idle";
  let loadError = "";
  const expanded = new Set();
  const dialog = createDialog({
    host,
    title: `修改记录 · ${rule.rule_code || `规则 ${rule.id}`} · ${rule.name || ""}`,
    className: "dv-history-dialog",
    onClose: () => {
      runtime.invalidate(channel);
      onClose?.();
    },
    onError: (message) => notify(message, "error"),
  });
  const body = element("tbody");
  const feedback = element("div", { className: "dv-history-feedback" });
  const table = element("table", { className: "dv-table dv-history-table" },
    element("thead", {}, element("tr", {},
      element("th", { className: "dv-audit-toggle-cell", text: "详情" }),
      ...["操作时间", "操作人", "动作", "版本", "变更摘要"].map((label) => element("th", { text: label })))), body);
  const wrap = element("div", { className: "dv-history-table-wrap dv-scroll" }, feedback, table);
  const pagination = createPagination({
    listen: dialog.bind,
    onPage: (page) => { query.page = Math.max(1, page); load(); },
    onPageSize: (size) => { query.page_size = size; query.page = 1; load(); },
  });
  const close = button("关闭");
  dialog.bind(close, "click", () => dialog.close());
  dialog.body.append(
    element("p", { className: "dv-notice", text: "记录由服务端按页返回。展开一行可查看变更项、修改前与修改后；对象值仅以安全文本展示。" }),
    wrap, pagination.element,
  );
  dialog.footer.append(close);
  dialog.bind(wrap, "click", (event) => {
    const target = event.target.closest("[data-history-toggle]");
    if (!target) return;
    const id = Number(target.dataset.historyToggle);
    if (expanded.has(id)) expanded.delete(id);
    else expanded.add(id);
    render();
  });

  async function load() {
    const token = runtime.next(channel);
    status = "loading";
    loadError = "";
    render();
    try {
      const result = await loadConvergedPage({
        query: { ...query },
        onConverge: (page) => { query.page = page; },
        isCurrent: () => runtime.current(token),
        request: (requestQuery) => runtime.request(token, (signal) => api.ruleHistory(rule.id, requestQuery, { signal })),
      });
      if (!runtime.current(token)) return;
      payload = {
        ...result,
        page: query.page,
        page_size: query.page_size,
        items: Array.isArray(result.items) ? result.items : [],
      };
      status = "success";
    } catch (error) {
      if (!runtime.current(token)) return;
      status = "error";
      loadError = errorMessage(error, "修改记录加载失败");
      payload = emptyPage(query.page_size);
      notify(loadError, "error");
    } finally {
      if (runtime.current(token)) render();
    }
  }

  function render() {
    body.replaceChildren();
    feedback.replaceChildren();
    if (status === "loading") feedback.append(emptyState("正在加载修改记录…"));
    else if (status === "error") feedback.append(emptyState("修改记录加载失败", loadError));
    else if (!payload.items.length) feedback.append(emptyState("暂无数据", "该规则尚无修改记录"));
    payload.items.forEach((item) => {
      const isExpanded = expanded.has(Number(item.id));
      const toggle = button(isExpanded ? "收起 ▲" : "展开 ▼", {
        className: "dv-audit-detail-toggle",
        dataset: { historyToggle: item.id },
        ariaLabel: isExpanded ? "收起变更详情" : "展开变更详情",
      });
      toggle.setAttribute("aria-expanded", String(isExpanded));
      body.append(element("tr", { className: isExpanded ? "is-expanded" : "" },
        element("td", { className: "dv-audit-toggle-cell" }, toggle),
        element("td", { className: "dv-date", text: formatDateTime(item.created_at) }),
        element("td", {}, element("strong", { text: item.operator_name || item.operator_user_id || "—" }),
          element("span", { text: item.operator_user_id || "" })),
        element("td", {}, actionBadge(item.action_code)),
        element("td", { className: "dv-code", text: item.version_no ? `v${item.version_no}` : "—" }),
        element("td", { className: "dv-audit-summary", text: item.summary || "—" })));
      const detail = detailRow(item, isExpanded);
      if (detail) body.append(detail);
    });
    pagination.update(payload, { loading: status === "loading" });
  }

  render();
  load();
  return dialog;
}
