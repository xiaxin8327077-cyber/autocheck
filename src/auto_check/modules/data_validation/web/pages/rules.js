import { errorMessage } from "../runtime.js";
import {
  clearRuleFilters, hasCapability, loadConvergedPage, ownsResource,
  RULE_TYPE_LABELS, setRulePageSize, updateRuleFilter,
} from "../state.js";
import { button, downloadText, element, input, select } from "../components/dom.js";
import { createCategoryTabs } from "../components/category_tabs.js";
import { createPagination } from "../components/pagination.js";
import { createRuleTable } from "../components/rule_table.js";
import { bindSearch } from "../components/search.js";
import { createStatsCards } from "../components/stats_cards.js";

export function createRulesPage({
  state, runtime, api, listen, user, notify, confirmAction, host,
  onOpenWorkbench, onOpenTask, onOpenHistory,
}) {
  const canManage = hasCapability(user, "dv.manage");
  const canExport = hasCapability(user, "dv.export");
  const canRun = hasCapability(user, "dv.run");
  let deleting = false;
  const manualButton = button("新建", {
    listen, hidden: !canManage, capability: "dv.manage", onClick: () => onOpenWorkbench({ mode: "manual" }),
  });
  const aiButton = button("✦ AI 新建规则", {
    listen, className: "dv-button dv-button-primary", hidden: !hasCapability(user, "dv.ai_use"),
    capability: "dv.ai_use", onClick: () => onOpenWorkbench({ mode: "ai" }),
  });
  // 上部卡片：状态胶囊 + 监管报送分类胶囊，统计均来自后端。
  const stats = createStatsCards({ listen, onFilter: (value) => {
    updateRuleFilter(state, { status: value });
    stats.update(state.stats, value, state.statsStatus);
    loadRules();
  } });
  const categoryTabs = createCategoryTabs({ listen, onFilter: (value) => {
    const next = state.ruleQuery.report_category === value ? "" : value;
    updateRuleFilter(state, { report_category: next });
    categoryTabs.update(state.stats, next, state.statsStatus);
    loadRules();
  } });
  // 顶部卡片：第一行标题 + 状态胶囊 + 操作按钮，第二行监管报送分类胶囊。
  const header = element("section", { className: "dv-rules-header" },
    element("div", { className: "dv-rules-header-top" },
      element("h1", { className: "dv-rules-title", text: "校验规则管理" }),
      stats.element,
      element("div", { className: "dv-page-actions" }, manualButton, aiButton)),
    categoryTabs.element);

  // 内容卡片：筛选 + 表格 + 分页。
  const search = input({ placeholder: "搜索编号 / 规则名称 / 描述", className: "dv-input dv-search" });
  search.value = state.ruleQuery.keyword;
  const sourceFilter = select([["", "数据源：全部"]], { value: state.ruleQuery.source_id });
  let sourceSignature = "";
  function syncSourceOptions() {
    const nextSignature = state.sources.map((item) => `${item.id}:${item.name}`).join("|");
    if (nextSignature !== sourceSignature) {
      sourceSignature = nextSignature;
      sourceFilter.replaceChildren();
      [["", "数据源：全部"], ...state.sources.map((item) => [item.id, item.name])].forEach(([value, label]) => {
        const option = element("option", { text: label });
        option.value = value;
        sourceFilter.append(option);
      });
    }
    sourceFilter.value = state.ruleQuery.source_id;
  }
  const typeFilter = select([
    ["", "校验类型：全部"],
    ...Object.entries(RULE_TYPE_LABELS),
  ], { value: state.ruleQuery.rule_type });
  const reset = button("重置", { listen, className: "dv-reset-link", onClick: () => {
    clearRuleFilters(state);
    search.value = "";
    sourceFilter.value = "";
    typeFilter.value = "";
    render();
    loadRules();
  } });
  const disableSelectedButton = button("批量停用", {
    listen, hidden: !canManage, capability: "dv.manage", onClick: disableSelected,
  });
  const deleteSelectedButton = button("批量删除", {
    listen, className: "dv-button dv-button-danger", hidden: !canManage, capability: "dv.manage",
    onClick: () => deleteRules([...state.selectedRules.values()]),
  });
  const executeButton = button("批量新建任务", {
    listen, hidden: !canRun, capability: "dv.run", onClick: () => {
      const rules = [...state.selectedRules.values()].filter((rule) => rule.status === "enabled");
      if (rules.length) onOpenTask(rules);
    },
  });
  const exportButton = button("导出规则包", {
    listen, hidden: !canExport, capability: "dv.export", onClick: exportSelected,
  });
  const actions = element("div", { className: "dv-filter-actions" }, disableSelectedButton, deleteSelectedButton, executeButton, exportButton);
  const filters = element("div", { className: "dv-filters" }, search, sourceFilter, typeFilter, reset, actions);

  const table = createRuleTable({ listen, user, onAction: handleAction, onSelect: selectRule, onSelectPage: selectPage });
  const pagination = createPagination({
    listen,
    onPage: (page) => {
      state.ruleQuery.page = Math.max(1, page);
      loadRules();
    },
    onPageSize: (size) => {
      setRulePageSize(state, size);
      loadRules();
    },
  });
  const contentCard = element("section", { className: "dv-panel-content" },
    filters, table.element, pagination.element);
  const panel = element("section", {
    className: "dv-tab-panel dv-rules-panel", dataset: { panel: "rules" }, attrs: { role: "tabpanel" },
  }, contentCard);

  listen(host || panel, "click", (event) => {
    if (!event.target.closest("[data-more-toggle]") && !event.target.closest("[data-action]")) table.closeMenus();
  });
  listen(host || panel, "keydown", (event) => {
    if (event.key === "Escape") table.closeMenus();
  });

  bindSearch({
    input: search, listen, runtime,
    onSearch: (keyword) => {
      updateRuleFilter(state, { keyword });
      loadRules();
    },
  });
  listen(sourceFilter, "change", () => {
    updateRuleFilter(state, { source_id: sourceFilter.value });
    loadRules();
  });
  listen(typeFilter, "change", () => {
    updateRuleFilter(state, { rule_type: typeFilter.value });
    loadRules();
  });

  function selectRule(rule, checked) {
    if (!rule || deleting) return;
    if (checked) state.selectedRules.set(Number(rule.id), rule);
    else state.selectedRules.delete(Number(rule.id));
    render();
  }

  function selectPage(rules, checked) {
    if (deleting) return;
    for (const rule of rules) {
      if (checked) state.selectedRules.set(Number(rule.id), rule);
      else state.selectedRules.delete(Number(rule.id));
    }
    render();
  }

  async function handleAction(name, rule) {
    if (deleting) return;
    if (name === "retry") return loadRules();
    if (!rule) return;
    if (name === "edit") return onOpenWorkbench({ mode: "manual", ruleId: rule.id });
    if (name === "history") return onOpenHistory(rule);
    if (name === "execute") return onOpenTask([rule]);
    if (name === "delete") return deleteRules([rule]);
    if (name === "copy") {
      const token = runtime.next(`rule-copy-${rule.id}`);
      await runtime.request(token, (signal) => api.copy(rule.id, { signal }));
      if (!runtime.current(token)) return;
      notify(`已复制 ${rule.rule_code} 为新草稿`, "success");
      await refresh();
      return;
    }
    if (name === "disable") {
      const accepted = await confirmAction(`确定停用规则“${rule.name}”吗？历史版本和任务快照会保留。`);
      if (!accepted || !runtime.isActive()) return;
      const token = runtime.next(`rule-disable-${rule.id}`);
      await runtime.request(token, (signal) => api.disable(rule.id, { signal }));
      if (!runtime.current(token)) return;
      state.selectedRules.delete(Number(rule.id));
      notify("规则已停用", "success");
      await refresh();
    }
  }

  async function disableSelected() {
    if (deleting) return;
    const selected = [...state.selectedRules.values()]
      .filter((rule) => rule.status === "enabled" && ownsResource(user, rule));
    if (!selected.length) {
      notify("请先选择本人创建的已启用规则", "warning");
      return;
    }
    const accepted = await confirmAction(`确定批量停用选中的 ${selected.length} 条规则吗？历史版本和任务快照会保留。`);
    if (!accepted || !runtime.isActive()) return;
    const token = runtime.next("rules-batch-disable");
    for (const rule of selected) {
      await runtime.request(token, (signal) => api.disable(rule.id, { signal }));
      if (!runtime.current(token)) return;
      state.selectedRules.delete(Number(rule.id));
    }
    notify(`已停用 ${selected.length} 条规则`, "success");
    await refresh();
  }

  async function deleteRules(rules) {
    if (deleting || !rules.length) return;
    if (!canManage || !rules.every(rule => ownsResource(user, rule))) {
      notify("只能删除本人创建的规则，请调整勾选范围", "warning");
      return;
    }
    const selected = [...rules];
    const token = runtime.next("rules-delete");
    let attempted = false, deleted = 0;
    deleting = true;
    render();
    try {
      const subject = selected.length === 1 ? `规则“${selected[0].name}”` : `选中的 ${selected.length} 条规则`;
      const accepted = await confirmAction(`确定删除${subject}吗？删除后将从校验列表移除，历史版本和校验结果会保留。`);
      if (!accepted || !runtime.current(token)) return;
      attempted = true;
      for (const rule of selected) {
        await runtime.request(token, signal => api.deleteRule(rule.id, { signal }));
        if (!runtime.current(token)) return;
        state.selectedRules.delete(Number(rule.id));
        deleted += 1;
      }
      notify(`已删除 ${deleted} 条校验规则`, "success");
    } catch (error) {
      if (runtime.current(token)) notify(deleted
        ? `已删除 ${deleted} 条，其余未完成：${errorMessage(error)}` : errorMessage(error, "删除失败，请重试"), "error");
    } finally {
      deleting = false;
      if (runtime.current(token)) {
        render();
        if (attempted) await refresh();
      }
    }
  }

  async function exportSelected() {
    if (deleting) return;
    const selected = [...state.selectedRules.values()];
    if (!selected.length) throw new Error("请先选择需要导出的规则");
    if (!selected.every((rule) => ownsResource(user, rule))) throw new Error("只能导出本人创建的规则包");
    const token = runtime.next("rule-pack-export");
    const result = await runtime.request(token, (signal) => api.exportRulePack(selected.map((rule) => rule.id), { signal }));
    if (!runtime.current(token)) return;
    downloadText({
      host, runtime, filename: `data-validation-rules-${Date.now()}.json`,
      content: result.content, type: "application/json;charset=utf-8",
    });
    notify(`已导出 ${selected.length} 条真实规则定义`, "success");
  }

  async function loadRules() {
    const token = runtime.next("rules-list");
    state.rulesStatus = "loading";
    state.rulesError = "";
    render();
    try {
      const result = await loadConvergedPage({
        query: { ...state.ruleQuery },
        onConverge: (page) => { state.ruleQuery.page = page; },
        isCurrent: () => runtime.current(token),
        request: (query) => runtime.request(token, (signal) => api.rules(query, { signal })),
      });
      if (!runtime.current(token)) return;
      state.rules = {
        ...result,
        page: state.ruleQuery.page,
        page_size: state.ruleQuery.page_size,
        items: Array.isArray(result.items) ? result.items : [],
      };
      state.rulesStatus = "success";
    } catch (error) {
      if (!runtime.current(token)) return;
      state.rulesStatus = "error";
      state.rulesError = errorMessage(error, "规则加载失败");
      notify(state.rulesError, "error");
    } finally {
      if (runtime.current(token)) render();
    }
  }

  async function loadStats() {
    const token = runtime.next("rules-stats");
    state.statsStatus = "loading";
    stats.update(state.stats, state.ruleQuery.status, state.statsStatus);
    categoryTabs.update(state.stats, state.ruleQuery.report_category, state.statsStatus);
    try {
      const result = await runtime.request(token, (signal) => api.stats({ signal }));
      if (!runtime.current(token)) return;
      state.stats = result || {};
      state.statsStatus = "success";
    } catch (error) {
      if (!runtime.current(token)) return;
      state.statsStatus = "error";
      notify(errorMessage(error, "统计信息加载失败"), "error");
    } finally {
      if (runtime.current(token)) {
        stats.update(state.stats, state.ruleQuery.status, state.statsStatus);
        categoryTabs.update(state.stats, state.ruleQuery.report_category, state.statsStatus);
      }
    }
  }

  function render() {
    syncSourceOptions();
    const categories = Array.isArray(state.stats.categories) && state.stats.categories.length
      ? state.stats.categories
      : state.categories;
    const categoryNames = Object.fromEntries(categories.map((item) => [item.code, item.name]));
    const categoryTones = Object.fromEntries(categories.map((item, index) => [item.code, index % 5]));
    table.update(state.rules, state.selectedRules, {
      status: state.rulesStatus, error: state.rulesError, categoryNames, categoryTones, busy: deleting,
    });
    const selected = [...state.selectedRules.values()];
    pagination.update(state.rules, {
      loading: state.rulesStatus === "loading", selectedCount: selected.length,
    });
    disableSelectedButton.disabled = deleting || !selected.some(
      (rule) => rule.status === "enabled" && ownsResource(user, rule),
    );
    deleteSelectedButton.disabled = deleting || !selected.length || !selected.every(rule => ownsResource(user, rule));
    deleteSelectedButton.title = selected.length && selected.every(rule => ownsResource(user, rule))
      ? `删除所选 ${selected.length} 条规则，保留历史校验结果` : "请勾选本人创建的规则";
    exportButton.disabled = deleting || !selected.length || !selected.every((rule) => ownsResource(user, rule));
    exportButton.title = selected.length && selected.every((rule) => ownsResource(user, rule))
      ? "导出真实 JSON 规则包" : "只能导出本人创建的规则";
    executeButton.disabled = deleting || !selected.some((rule) => rule.status === "enabled");
    stats.update(state.stats, state.ruleQuery.status, state.statsStatus);
    categoryTabs.update(state.stats, state.ruleQuery.report_category, state.statsStatus);
  }

  async function refresh() {
    await Promise.all([loadRules(), loadStats()]);
  }

  render();
  return { header, panel, refresh, loadRules, render };
}
