import { createApi } from "./api.js";
import { createRuntime, errorMessage } from "./runtime.js";
import { createState, hasCapability } from "./state.js";
import { button, element } from "./components/dom.js";
import { openTaskDialog } from "./components/task_dialog.js";
import { openHistoryDialog } from "./components/history_dialog.js";
import { createResultsPage } from "./pages/results.js";
import { createRulesPage } from "./pages/rules.js";
import { createSettingsPage } from "./pages/settings.js";
import { createWorkbench } from "./pages/workbench.js";

let instance = null;

export function mount(context) {
  if (!context?.root || typeof context.api !== "function" || typeof context.user !== "function"
      || typeof context.notify !== "function" || typeof context.confirm !== "function") {
    throw new Error("数据校验模块缺少宿主能力");
  }
  if (instance) unmount();
  const user = context.user() || {};
  const notify = (message, type = "info") => context.notify(message, type);
  const confirmAction = (message) => context.confirm(message);
  const runtime = createRuntime({ notify });
  const listen = runtime.listen;
  const state = createState();
  const api = createApi(context);
  const browser = element("div", { className: "dv-browser" });
  const headerHost = element("div", { className: "dv-header-host" });
  const panelsHost = element("div", { className: "dv-panels-host" });
  const dialogHost = element("div", { className: "dv-dialog-host" });
  const shell = element("section", { className: "dv-page" }, browser, dialogHost);
  context.root.replaceChildren(shell);

  let activeTaskDialog = null;
  let activeHistoryDialog = null;
  let results = null;
  let settings = null;
  let workbench = null;
  let rules = null;

  // 页面由顶部导航路由决定：数据校验（规则管理）与校验结果各自独立菜单入口，页内不再有 Tab。
  const mainCard = element("section", { className: "dv-main-card" }, panelsHost);
  browser.append(headerHost, mainCard);

  function routePage(route) {
    const name = typeof route === "object" && route ? route.name : route;
    if (name === "data-validation-results") return "results";
    if (name === "data-validation-settings") return "settings";
    return "rules";
  }

  function showPage(name, { load = true } = {}) {
    const target = name === "results" ? "results" : name === "settings" ? "settings" : "rules";
    if (target === "results" && !hasCapability(user, "dv.view_results") && !hasCapability(user, "dv.run")) {
      notify("当前用户没有此页面权限", "error");
      return false;
    }
    if (target === "settings" && !hasCapability(user, "dv.admin")) {
      notify("当前用户没有校验设置权限", "error");
      return false;
    }
    if (state.activeTab === "results" && target !== "results") results?.stopPolling();
    state.activeTab = target;
    const page = target === "rules" ? rules : target === "results" ? results : settings;
    headerHost.replaceChildren(page.header);
    [rules.panel, results.panel, settings.panel].forEach((panel) => { panel.hidden = panel !== page.panel; });
    if (!panelsHost.contains(page.panel)) panelsHost.append(rules.panel, results.panel, settings.panel);
    page.render?.();
    if (load && target === "results") results.loadTasks();
    if (load && target === "rules") rules.refresh();
    if (load && target === "settings") settings.refresh();
    return true;
  }

  function openWorkbench(options) {
    activeTaskDialog?.close();
    return workbench.open(options);
  }

  function openRuleHistory(rule) {
    activeHistoryDialog?.close();
    activeHistoryDialog = openHistoryDialog({
      runtime, api, host: dialogHost, rule, notify,
      onClose: () => { activeHistoryDialog = null; },
    });
  }

  function openRulesTask(initialRules = []) {
    if (!hasCapability(user, "dv.run")) return;
    activeTaskDialog?.close();
    activeTaskDialog = openTaskDialog({
      state, runtime, api, listen, host: dialogHost, user, notify, initialRules,
      onClose: () => { activeTaskDialog = null; },
      onStarted: async (task) => {
        state.reportPeriod = task.report_period || state.reportPeriod;
        state.activeTaskId = Number(task.id);
        state.issuesStatus = "idle";
        const navigated = await context.navigate?.("data-validation-results");
        if (!navigated) notify("任务已提交，可从顶部「数据质量 → 校验结果」查看", "info");
        notify(`任务 #${task.id} 已提交，状态 ${task.status}`, "success");
        if (Array.isArray(task.skipped) && task.skipped.length) {
          notify(task.skipped.map((item) => `规则 ${item.rule_id}：${item.reason}`).join("；"), "warning");
        }
      },
    });
  }

  function onPeriodChange(value) {
    results.stopPolling();
    state.reportPeriod = value;
    state.activeTaskId = null;
    state.issueQuery.page = 1;
    state.tasks = [];
    state.issuesStatus = "idle";
    results.render();
    if (state.activeTab === "results") results.loadTasks();
  }

  async function loadSources() {
    const token = runtime.next("sources");
    state.sourcesStatus = "loading";
    state.sourcesError = "";
    workbench?.refreshSources();
    try {
      const sources = await runtime.request(token, (signal) => api.sources({ signal }));
      if (!runtime.current(token)) return;
      state.sources = Array.isArray(sources) ? sources : [];
      state.sourcesStatus = "success";
    } catch (error) {
      if (!runtime.current(token)) return;
      state.sourcesStatus = "error";
      state.sourcesError = `数据源加载失败：${errorMessage(error)}。请重试；不会将其显示为“未配置”。`;
      notify(state.sourcesError, "error");
    } finally {
      if (runtime.current(token)) workbench?.refreshSources();
    }
  }

  async function loadCategories() {
    const token = runtime.next("categories");
    state.categoriesStatus = "loading";
    state.categoriesError = "";
    workbench?.refreshSources();
    try {
      const categories = await runtime.request(token, (signal) => api.reportCategories({ signal }));
      if (!runtime.current(token)) return;
      state.categories = Array.isArray(categories) ? categories : [];
      state.categoriesStatus = "success";
    } catch (error) {
      if (!runtime.current(token)) return;
      state.categoriesStatus = "error";
      state.categoriesError = `报送分类加载失败：${errorMessage(error)}`;
      notify(state.categoriesError, "error");
    } finally {
      if (runtime.current(token)) {
        workbench?.refreshSources();
        rules?.render();
      }
    }
  }

  async function loadModels() {
    if (!hasCapability(user, "dv.ai_use")) {
      state.modelsStatus = "disabled";
      return;
    }
    const token = runtime.next("models");
    state.modelsStatus = "loading";
    state.modelsError = "";
    workbench?.refreshSources();
    try {
      const models = await runtime.request(token, (signal) => api.models({ signal }));
      if (!runtime.current(token)) return;
      state.models = Array.isArray(models) ? models : [];
      state.modelsStatus = "success";
    } catch (error) {
      if (!runtime.current(token)) return;
      state.modelsStatus = "error";
      state.modelsError = `模型加载失败：${errorMessage(error)}。手工规则路径仍可使用。`;
      notify(state.modelsError, "error");
    } finally {
      if (runtime.current(token)) workbench?.refreshSources();
    }
  }

  rules = createRulesPage({
    state, runtime, api, listen, user, notify, confirmAction, host: shell,
    onOpenWorkbench: openWorkbench,
    onOpenTask: openRulesTask,
    onOpenHistory: openRuleHistory,
  });
  results = createResultsPage({
    state, runtime, api, listen, user, notify, confirmAction, host: shell,
    onNewTask: () => openRulesTask(),
    onPeriodChange,
  });
  settings = createSettingsPage({ state, runtime, api, listen, user, notify, host: shell });
  workbench = createWorkbench({
    state, runtime, api, listen, user, notify, host: dialogHost, confirmAction,
    onClose: () => {},
    onChanged: () => rules.refresh(),
    onRetrySources: loadSources,
    onRetryModels: loadModels,
  });
  panelsHost.append(rules.panel, results.panel, settings.panel);
  showPage("rules", { load: false });

  instance = {
    context,
    runtime,
    async activate(route) {
      runtime.activate();
      const pageName = routePage(route);
      showPage(pageName, { load: false });
      const loads = [loadSources(), loadModels(), loadCategories()];
      if (pageName === "rules") loads.push(rules.refresh());
      else if (pageName === "results") loads.push(results.loadTasks());
      else loads.push(settings.refresh());
      await Promise.all(loads);
    },
    deactivate() {
      activeTaskDialog?.close();
      activeTaskDialog = null;
      activeHistoryDialog?.close();
      activeHistoryDialog = null;
      results.stopPolling();
      workbench.cancel();
      runtime.deactivate();
    },
    unmount() {
      activeTaskDialog?.close();
      activeTaskDialog = null;
      activeHistoryDialog?.close();
      activeHistoryDialog = null;
      results.stopPolling();
      workbench.cancel();
      runtime.destroy();
      context.root.replaceChildren();
      instance = null;
    },
    showPage,
    runtimeSnapshot: () => runtime.snapshot(),
  };
}

export async function activate(route) {
  if (!instance) throw new Error("数据校验模块尚未挂载");
  return instance.activate(route);
}

export function deactivate() {
  instance?.deactivate();
}

export function unmount() {
  instance?.unmount();
}
