import { errorMessage } from "../runtime.js";
import { labelFor } from "../constants.js";
import { RULE_STATUS_LABELS, loadConvergedPage, MAX_TASK_RULES, newEnabledRuleQuery, reportCategoryCode, targetTableLabel, updateBoundedSelection } from "../state.js";
import { aiIcon } from "./ai_visuals.js";
import { createDialog } from "./dialog.js";
import { button, element, field, input, select } from "./dom.js";
import { createPagination } from "./pagination.js";
import { bindSearch } from "./search.js";

export function openTaskDialog({
  state, runtime, api, listen, host, user, notify, initialRules = [], onStarted, onClose,
}) {
  const query = newEnabledRuleQuery();
  query.report_category = "";
  query.source_id = "";
  let rules = { items: [], total: 0, page: 1, page_size: query.page_size };
  let loading = false;
  let starting = false;
  let selectingFiltered = false;
  const selection = new Map();
  // 批量选择只保留最小占位对象；来源/分类仅用于跨筛选计数，不回填完整规则。
  const selectionOrigins = new Map();
  const enabledInitialRules = initialRules.filter((rule) => rule.status === "enabled");
  enabledInitialRules.slice(0, MAX_TASK_RULES).forEach((rule) => selection.set(Number(rule.id), rule));
  if (enabledInitialRules.length > MAX_TASK_RULES) {
    notify(`已选规则超过 ${MAX_TASK_RULES} 条，本次仅保留前 ${MAX_TASK_RULES} 条；请分批创建任务`, "warning");
  }
  const error = element("p", { className: "dv-feedback is-error", hidden: true });
  const dialog = createDialog({
    host, title: "执行校验", subtitle: "准备执行", icon: aiIcon("database"), className: "dv-task-dialog",
    onClose: () => {
      runtime.invalidate("task-enabled-rules");
      runtime.invalidate("task-start");
      runtime.invalidate("task-rule-selection");
      runtime.clearDebounce("task-rule-search");
      onClose?.();
    },
    onError: (message) => showError(message),
  });
  const period = input({ type: "date", value: state.reportPeriod });
  period.required = true;
  const source = select([["", "全部数据源"], ...(state.sources || []).map((item) => [item.id, item.name])]);
  const category = select([], { className: "dv-select dv-execution-category" });
  const categoryHint = element("span", { className: "dv-field-hint", hidden: true });
  const search = input({ placeholder: "搜索规则名称或编号", className: "dv-input dv-search" });
  const selectedText = element("span", { className: "dv-selected-count" });
  const selectFiltered = button("选择当前筛选全部规则", {
    className: "dv-button dv-button-plain dv-execution-select-filtered",
    title: "选择当前筛选下的全部已启用规则",
  });
  const clear = button("清空选择", { className: "dv-button dv-button-plain" });
  const selectAll = element("input", { className: "dv-rule-checkbox", attrs: { "aria-label": "选择当前页全部已启用规则" } });
  selectAll.type = "checkbox";
  const body = element("tbody");
  const feedback = element("div", { className: "dv-task-choice-feedback" });
  const table = element("table", { className: "dv-table dv-execution-rule-table" },
    element("thead", {}, element("tr", {}, element("th", { className: "dv-select-cell" }, element("label", { className: "dv-rule-select" }, selectAll)),
      ...["规则名称", "目标数据表", "数据源"].map((label) => element("th", { text: label })))), body);
  const listWrap = element("div", { className: "dv-enabled-rule-wrap dv-scroll" }, feedback, table);
  const pagination = createPagination({
    listen: dialog.bind,
    onPage: (page) => { query.page = Math.max(1, page); load(); },
    onPageSize: (size) => { query.page_size = size; query.page = 1; load(); },
  });
  const cancel = button("取消");
  const start = button("启动后台任务", { className: "dv-button dv-button-primary", capability: "dv.run" });
  const footerNote = element("span", { className: "dv-execution-footer-note" });
  const crossFilterNote = element("span", { className: "dv-execution-cross-filter-note", hidden: true });
  const categoryField = field("报送分类", category);
  categoryField.append(categoryHint);
  dialog.body.append(
    element("p", { className: "dv-execution-description", text: "按所选报送期执行勾选的已启用规则。" }),
    element("div", { className: "dv-task-dialog-grid" },
      field("报送期 *", period), categoryField, field("数据源", source)),
    element("div", { className: "dv-task-choice-toolbar" }, search, selectedText, selectFiltered, clear),
    element("div", { className: "dv-execution-selection" }, listWrap, pagination.element),
    error,
  );
  dialog.footer.append(element("div", { className: "dv-execution-footer-context" }, footerNote, crossFilterNote), cancel, start);
  dialog.bind(cancel, "click", () => dialog.close());
  dialog.bind(clear, "click", () => {
    if (starting || selectingFiltered) return;
    selection.clear();
    selectionOrigins.clear();
    showError("");
    render();
  });
  dialog.bind(start, "click", startTask);
  dialog.bind(selectFiltered, "click", selectFilteredRules);
  dialog.bind(period, "change", () => showError(""));
  dialog.bind(source, "change", () => {
    cancelFilteredSelection();
    query.source_id = source.value;
    query.page = 1;
    return load();
  });
  dialog.bind(category, "change", () => {
    cancelFilteredSelection();
    query.report_category = category.value;
    query.page = 1;
    showError("");
    return load();
  });
  dialog.bind(selectAll, "change", () => {
    if (starting || selectingFiltered) return;
    const enabled = rules.items.filter((rule) => rule.status === "enabled");
    const additional = enabled.filter((rule) => !selection.has(Number(rule.id)));
    if (selectAll.checked && selection.size + additional.length > MAX_TASK_RULES) {
      showError(`单个任务最多选择 ${MAX_TASK_RULES} 条规则，请减少选择后重试`);
    } else {
      enabled.forEach((rule) => applySelection(rule, selectAll.checked)); showError("");
    }
    render();
  });
  dialog.bind(listWrap, "change", (event) => {
    if (starting || selectingFiltered) return;
    const id = event.target.dataset.enabledRule;
    if (!id) return;
    const rule = rules.items.find((item) => String(item.id) === String(id));
    const result = applySelection(rule, event.target.checked);
    if (!result.ok) {
      event.target.checked = false;
      showError(result.reason);
    } else showError("");
    render();
  });
  // 搜索框输入变化后立即作废旧筛选下的批量选择，不等防抖查询完成。
  dialog.bind(search, "input", () => cancelFilteredSelection());
  bindSearch({
    input: search, listen: dialog.bind, runtime, channel: "task-rule-search",
    onSearch: (keyword) => {
      cancelFilteredSelection();
      query.keyword = keyword;
      query.page = 1;
      load();
    },
  });

  function applySelection(rule, checked) {
    const id = Number(rule?.id);
    const result = updateBoundedSelection(selection, rule, checked);
    if (result.ok && Number.isInteger(id)) selectionOrigins.delete(id);
    return result;
  }

  function cancelFilteredSelection() {
    runtime.invalidate("task-rule-selection");
    if (!selectingFiltered) return;
    selectingFiltered = false;
    render();
  }

  function showError(message) {
    error.hidden = !message;
    error.textContent = message || "";
    if (message) notify(message, "error");
  }

  function categoryEntries() {
    const entries = [["", "全部分类"]];
    const names = new Map();
    (Array.isArray(state.categories) ? state.categories : []).forEach((item) => {
      const raw = String(item?.code || "");
      if (!raw || raw === "__uncategorized__") return;
      const code = reportCategoryCode(raw);
      if (!code || code === "__uncategorized__") return;
      const name = String(item?.name || "");
      const fallback = code === "group:pbc" ? "人行报送" : code;
      if (!names.has(code) || (raw === code && name)) names.set(code, name || fallback);
    });
    names.forEach((name, code) => entries.push([code, name]));
    return entries;
  }

  function updateCategoryHint() {
    let message = "";
    if (state.categoriesStatus === "loading" || state.categoriesStatus === "idle") {
      message = "报送分类目录加载中；可先按“全部分类”查询已有规则。";
    } else if (state.categoriesStatus === "error") {
      message = `${state.categoriesError || "报送分类目录加载失败"}；仍可按“全部分类”查询已有规则。`;
    } else if (state.categoriesStatus === "success" && !(state.categories || []).length) {
      message = "报送分类目录为空；仍可按“全部分类”查询已有规则。";
    }
    categoryHint.textContent = message;
    categoryHint.hidden = !message;
  }

  function refreshCategories() {
    const previous = category.value;
    const entries = categoryEntries();
    if (previous && !entries.some(([value]) => value === previous) && state.categoriesStatus !== "success") {
      entries.splice(1, 0, [previous, previous === "group:pbc" ? "人行报送" : previous]);
    }
    category.replaceChildren(...entries.map(([value, label]) => {
      const option = element("option", { text: label });
      option.value = String(value);
      return option;
    }));
    category.value = entries.some(([value]) => value === previous) ? previous : "";
    updateCategoryHint();
  }

  function refreshSources() {
    const previous = source.value;
    const entries = [["", "全部数据源"], ...(state.sources || []).map(item => [String(item.id), item.name])];
    if (previous && !entries.some(([value]) => value === previous)) entries.push([previous, previous]);
    source.replaceChildren(...entries.map(([value, text]) => {
      const option = element("option", { text }); option.value = value; return option;
    }));
    source.value = previous;
  }

  function outsideCurrentFilters(rule) {
    const id = Number(rule?.id);
    const origin = Number.isInteger(id) ? selectionOrigins.get(id) : null;
    const known = origin || rule || {};
    let unknown = false;
    if (query.source_id) {
      if (!Object.hasOwn(known, "source_id")) unknown = true;
      else if (String(known.source_id ?? "") !== String(query.source_id)) return true;
    }
    if (query.report_category) {
      if (!Object.hasOwn(known, "report_category")) unknown = true;
      else {
        const code = reportCategoryCode(known.report_category);
        if (query.report_category === "__uncategorized__" ? Boolean(code) : code !== query.report_category) return true;
      }
    }
    return unknown ? null : false;
  }

  async function selectFilteredRules() {
    if (starting || selectingFiltered) return;
    // 批量选择使用用户当前看到的搜索词，不能等待防抖后才更新范围。
    const visibleKeyword = String(search.value || "").trim();
    if (visibleKeyword !== query.keyword) {
      runtime.clearDebounce("task-rule-search");
      query.keyword = visibleKeyword;
      query.page = 1;
      load();
    }
    if (typeof api.executionRuleIds !== "function") {
      showError("当前版本不支持批量选择，请刷新页面或手动勾选规则");
      return;
    }
    if (selection.size >= MAX_TASK_RULES) {
      showError(`单个任务最多选择 ${MAX_TASK_RULES} 条规则，请先清空或取消部分选择`);
      return;
    }
    const token = runtime.next("task-rule-selection");
    selectingFiltered = true;
    showError("");
    render();
    try {
      const result = await runtime.request(token, (signal) => api.executionRuleIds({
        keyword: query.keyword,
        source_id: query.source_id || "",
        report_category: query.report_category || "",
      }, { signal }));
      if (!runtime.current(token)) return;
      if (!Array.isArray(result?.rule_ids)) throw new Error("批量选择返回结果缺少规则编号");
      const sourceId = query.source_id || "";
      const reportCategory = query.report_category === "__uncategorized__" ? "" : (query.report_category || "");
      let truncated = false;
      for (const rawId of result.rule_ids) {
        const id = Number(rawId);
        if (!Number.isInteger(id) || id <= 0 || selection.has(id)) continue;
        if (selection.size >= MAX_TASK_RULES) {
          truncated = true;
          break;
        }
        // 只存最小占位对象，不把完整规则或上万行 DOM 带进弹窗。
        selection.set(id, { id, status: "enabled" });
        selectionOrigins.set(id, {
          ...(sourceId ? { source_id: sourceId } : {}),
          ...(query.report_category ? { report_category: reportCategory } : {}),
        });
      }
      selectingFiltered = false;
      if (truncated) {
        notify(`已达到单个任务 ${MAX_TASK_RULES} 条规则上限，本次仅保留前 ${MAX_TASK_RULES} 条；请分批创建任务`, "warning");
      }
      render();
    } catch (cause) {
      if (!runtime.current(token)) return;
      selectingFiltered = false;
      showError(errorMessage(cause, "批量选择规则失败"));
      render();
    }
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
    updateCategoryHint();
    if (loading) feedback.append(element("p", { className: "dv-loading", text: "正在加载已启用规则…" }));
    else if (!rules.items.length) {
      const filtered = Boolean(query.report_category || query.source_id || query.keyword);
      feedback.append(element("p", { className: "dv-muted", text: filtered ? "当前筛选下暂无已启用规则" : "暂无已启用规则" }));
    }
    table.hidden = loading || !rules.items.length;
    rules.items.forEach((rule) => {
      if (selection.has(Number(rule.id))) selectionOrigins.delete(Number(rule.id));
      if (selection.has(Number(rule.id))) selection.set(Number(rule.id), {
        ...selection.get(Number(rule.id)), source_id: rule.source_id, report_category: rule.report_category,
      });
      const checkbox = element("input", { className: "dv-rule-checkbox", dataset: { enabledRule: rule.id }, attrs: { "aria-label": `选择 ${rule.rule_code}` } });
      checkbox.type = "checkbox";
      checkbox.checked = selection.has(Number(rule.id));
      checkbox.disabled = starting || selectingFiltered || (!checkbox.checked && selection.size >= MAX_TASK_RULES);
      body.append(element("tr", { className: checkbox.checked ? "is-selected" : "" },
        element("td", { className: "dv-select-cell" }, element("label", { className: "dv-rule-select" }, checkbox)),
        element("td", { className: "dv-execution-rule-name" }, element("strong", { text: rule.name }),
          element("span", { className: "dv-muted", text: `${rule.rule_code} · ${labelFor(rule.status, RULE_STATUS_LABELS)}` })),
        element("td", { className: "dv-execution-target", text: targetTableLabel(rule) }),
        element("td", { text: rule.source_name || state.sources?.find((item) => String(item.id) === String(rule.source_id))?.name || "数据源名称未采集" })));
    });
    const selectedPage = rules.items.filter((rule) => selection.has(Number(rule.id))).length;
    selectedText.textContent = selection.size > selectedPage
      ? `跨页已选 ${selection.size} 条`
      : `已选 ${selection.size} 条`;
    footerNote.textContent = `已选 ${selection.size} 条规则 · 将生成 1 个执行批次`;
    const ranges = [...selection.values()].map(outsideCurrentFilters);
    const crossFilterCount = ranges.filter(value => value === true).length;
    const unknownRange = ranges.includes(null);
    crossFilterNote.textContent = unknownRange ? "已保留之前筛选中勾选的规则，以已选总数为准"
      : crossFilterCount ? `跨筛选保留 ${crossFilterCount} 条已选规则，仍将一并执行` : "";
    crossFilterNote.hidden = !crossFilterCount && !unknownRange;
    selectAll.checked = Boolean(rules.items.length) && selectedPage === rules.items.length;
    selectAll.indeterminate = selectedPage > 0 && selectedPage < rules.items.length;
    selectAll.disabled = starting || selectingFiltered || loading || !rules.items.length;
    selectFiltered.textContent = selectingFiltered ? "正在选择…" : "选择当前筛选全部规则";
    selectFiltered.disabled = starting || selectingFiltered || selection.size >= MAX_TASK_RULES;
    clear.disabled = starting || selectingFiltered || !selection.size;
    start.disabled = starting || selectingFiltered || loading || !selection.size;
    start.textContent = starting ? "正在提交…" : `开始执行（${selection.size}条）`;
    cancel.disabled = starting;
    dialog.closeButton.disabled = starting;
    period.disabled = starting;
    search.disabled = starting;
    source.disabled = starting;
    category.disabled = starting;
    pagination.update(rules, { loading });
  }

  async function startTask() {
    if (starting || selectingFiltered) return;
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

  refreshCategories();
  render();
  load();
  return { ...dialog, refreshCategories, refreshSources };
}
