import { errorMessage } from "../runtime.js";
import { labelFor } from "../constants.js";
import { RULE_STATUS_LABELS, loadConvergedPage, MAX_TASK_RULES, newEnabledRuleQuery, updateBoundedSelection } from "../state.js";
import { createDialog } from "./dialog.js";
import { button, element, field, input } from "./dom.js";
import { createPagination } from "./pagination.js";
import { bindSearch } from "./search.js";

export function openTaskDialog({
  state, runtime, api, listen, host, user, notify, initialRules = [], onStarted, onClose,
}) {
  const query = newEnabledRuleQuery();
  let rules = { items: [], total: 0, page: 1, page_size: query.page_size };
  let loading = false;
  let starting = false;
  const selection = new Map();
  const enabledInitialRules = initialRules.filter((rule) => rule.status === "enabled");
  enabledInitialRules.slice(0, MAX_TASK_RULES).forEach((rule) => selection.set(Number(rule.id), rule));
  if (enabledInitialRules.length > MAX_TASK_RULES) {
    notify(`已选规则超过 ${MAX_TASK_RULES} 条，本次仅保留前 ${MAX_TASK_RULES} 条；请分批创建任务`, "warning");
  }
  const error = element("p", { className: "dv-feedback is-error", hidden: true });
  const dialog = createDialog({
    host, title: "新建只读校验执行任务", className: "dv-task-dialog",
    onClose: () => {
      runtime.invalidate("task-enabled-rules");
      runtime.invalidate("task-start");
      runtime.clearDebounce("task-rule-search");
      onClose?.();
    },
    onError: (message) => showError(message),
  });
  const period = input({ type: "date", value: state.reportPeriod });
  period.required = true;
  const search = input({ placeholder: "在当前已启用规则中搜索", className: "dv-input dv-search" });
  const selectedText = element("span", { className: "dv-selected-count" });
  const clear = button("清空跨页选择", { className: "dv-button dv-button-plain" });
  const body = element("tbody");
  const feedback = element("div", { className: "dv-task-choice-feedback" });
  const table = element("table", { className: "dv-table" },
    element("thead", {}, element("tr", {}, ...["选择", "规则编号", "规则名称", "数据源 / 表", "状态"].map((label) => element("th", { text: label })))), body);
  const listWrap = element("div", { className: "dv-enabled-rule-wrap dv-scroll" }, feedback, table);
  const pagination = createPagination({
    listen: dialog.bind,
    onPage: (page) => { query.page = Math.max(1, page); load(); },
    onPageSize: (size) => { query.page_size = size; query.page = 1; load(); },
  });
  const cancel = button("取消");
  const start = button("启动后台任务", { className: "dv-button dv-button-primary", capability: "dv.run" });
  dialog.body.append(
    element("div", { className: "dv-task-dialog-grid" },
      field("业务报送期 *", period),
      element("div", { className: "dv-readonly-note" }, element("span", { text: "执行数据源" }), element("strong", { text: "按每条已启用规则快照的数据源执行" }))),
    element("div", { className: "dv-notice", text: `仅通过独立服务端分页查询 status=enabled 规则；支持跨页选择，单任务最多 ${MAX_TASK_RULES} 条。不会复用规则列表的筛选或当前页。` }),
    element("div", { className: "dv-task-choice-toolbar" }, search, selectedText, clear),
    listWrap, pagination.element, error,
  );
  dialog.footer.append(cancel, start);
  dialog.bind(cancel, "click", () => dialog.close());
  dialog.bind(clear, "click", () => { selection.clear(); showError(""); render(); });
  dialog.bind(start, "click", startTask);
  dialog.bind(period, "change", () => showError(""));
  dialog.bind(listWrap, "change", (event) => {
    const id = event.target.dataset.enabledRule;
    if (!id) return;
    const rule = rules.items.find((item) => String(item.id) === String(id));
    const result = updateBoundedSelection(selection, rule, event.target.checked);
    if (!result.ok) {
      event.target.checked = false;
      showError(result.reason);
    } else showError("");
    render();
  });
  bindSearch({
    input: search, listen: dialog.bind, runtime, channel: "task-rule-search",
    onSearch: (keyword) => { query.keyword = keyword; query.page = 1; load(); },
  });

  function showError(message) {
    error.hidden = !message;
    error.textContent = message || "";
    if (message) notify(message, "error");
  }

  async function load() {
    const token = runtime.next("task-enabled-rules");
    loading = true;
    render();
    try {
      const result = await loadConvergedPage({
        query: { ...query, status: "enabled" },
        onConverge: (page) => { query.page = page; },
        isCurrent: () => runtime.current(token),
        request: (requestQuery) => runtime.request(token, (signal) => api.rules({ ...requestQuery, status: "enabled" }, { signal })),
      });
      if (!runtime.current(token)) return;
      rules = { ...result, page: query.page, page_size: query.page_size, items: Array.isArray(result.items) ? result.items : [] };
      loading = false;
      showError("");
      render();
    } catch (cause) {
      if (!runtime.current(token)) return;
      loading = false;
      showError(errorMessage(cause, "已启用规则加载失败"));
      render();
    }
  }

  function render() {
    body.replaceChildren();
    feedback.replaceChildren();
    if (loading) feedback.append(element("p", { className: "dv-loading", text: "正在独立加载已启用规则…" }));
    else if (!rules.items.length) feedback.append(element("p", { className: "dv-muted", text: "暂无数据" }));
    rules.items.forEach((rule) => {
      const checkbox = element("input", { dataset: { enabledRule: rule.id }, attrs: { "aria-label": `选择 ${rule.rule_code}` } });
      checkbox.type = "checkbox";
      checkbox.checked = selection.has(Number(rule.id));
      checkbox.disabled = starting || (!checkbox.checked && selection.size >= MAX_TASK_RULES);
      body.append(element("tr", {},
        element("td", {}, checkbox),
        element("td", { className: "dv-code", text: rule.rule_code }),
        element("td", { text: rule.name }),
        element("td", { text: `${rule.source_id || "—"} / ${rule.table_name || "—"}` }),
        element("td", { text: labelFor(rule.status, RULE_STATUS_LABELS) })));
    });
    selectedText.textContent = `跨页已选 ${selection.size} / ${MAX_TASK_RULES} 条`;
    clear.disabled = starting || !selection.size;
    start.disabled = starting || loading || !selection.size;
    start.textContent = starting ? "正在提交…" : `启动后台任务（${selection.size} 条）`;
    cancel.disabled = starting;
    dialog.closeButton.disabled = starting;
    period.disabled = starting;
    search.disabled = starting;
    pagination.update(rules, { loading });
  }

  async function startTask() {
    if (!period.value) return showError("请选择业务报送期");
    if (!selection.size) return showError("请至少选择一条已启用规则");
    if (selection.size > MAX_TASK_RULES) return showError(`单任务最多 ${MAX_TASK_RULES} 条规则`);
    const token = runtime.next("task-start");
    starting = true;
    render();
    try {
      const task = await runtime.request(token, (signal) => api.startTask({
        rule_ids: [...selection.keys()], source_id: "", report_period: period.value,
      }, { signal }));
      if (!runtime.current(token)) return;
      starting = false;
      dialog.close();
      onStarted(task, [...selection.values()]);
    } catch (cause) {
      if (!runtime.current(token)) return;
      starting = false;
      showError(errorMessage(cause, "任务创建失败"));
      render();
    }
  }

  render();
  load();
  return dialog;
}
