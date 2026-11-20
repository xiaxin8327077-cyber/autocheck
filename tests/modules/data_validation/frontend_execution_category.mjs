import assert from "node:assert/strict";
import { FakeElement, collectByClass, collectText, controlByLabel, findButton } from "./frontend_workbench_dom.mjs";
import { createState, MAX_TASK_RULES } from "./state.mjs";
import { createRuntime, errorMessage } from "./runtime.mjs";
import { createApi } from "./api.mjs";
import { openTaskDialog } from "./components/task_dialog.mjs";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const xss = '<img src=x onerror="globalThis.__xss=1">';
const allRules = Array.from({ length: 25 }, (_, index) => {
  const id = index + 1;
  const category = id === 1 ? "pbc_central" : id === 2 ? "east" : id === 3 ? "pbc_template" : id === 4 ? "" : "east";
  return {
    id, rule_code: `DV${id}`, name: id === 2 ? xss : `校验${id}`,
    source_id: id === 3 ? "s2" : "s1", source_name: id === 3 ? "报送集市" : "监管报表",
    table_name: "proj_info", table_name_cn: "项目信息", report_category: category, status: "enabled",
  };
});
const normalize = (value) => ["pbc_central", "pbc_template"].includes(String(value || "")) ? "group:pbc" : String(value || "");
const scenario = process.argv[2] || "category";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function pageFor(selected, query) {
  const page = Math.max(1, Number(query.page) || 1);
  const pageSize = Math.max(1, Number(query.page_size) || 20);
  return { items: selected.slice((page - 1) * pageSize, page * pageSize), total: selected.length, page, page_size: pageSize };
}

function filteredRules(query) {
  const category = String(query.report_category || "");
  let selected = allRules.filter((rule) => {
    const code = normalize(rule.report_category);
    if (category === "__uncategorized__") return !code;
    return !category || code === category;
  });
  if (query.source_id) selected = selected.filter((rule) => rule.source_id === query.source_id);
  if (query.keyword) selected = selected.filter((rule) => rule.name.includes(query.keyword) || rule.rule_code.includes(query.keyword));
  return selected;
}

function dialogState() {
  const state = createState();
  state.reportPeriod = "2026-10-31";
  state.sources = [{ id: "s1", name: "监管报表" }, { id: "s2", name: "报送集市" }];
  state.categories = [
    { code: "pbc_central", name: "人行大集中报送" },
    { code: "pbc_template", name: "资管产品模板、逐笔" },
    { code: "east", name: xss },
  ];
  state.categoriesStatus = "success";
  return state;
}

function selectedRulesBoxes(dialog) {
  return collectByClass(dialog.body, "dv-rule-checkbox").filter((box) => box.dataset.enabledRule);
}

function selectedTextNode(dialog) {
  return collectByClass(dialog.body, "dv-selected-count")[0];
}

function footerNoteNode(dialog) {
  return collectByClass(dialog.footer, "dv-execution-footer-note")[0];
}

async function categoryScenario() {
  const requests = [];
  const notices = [];
  let saved;
  let startedTask;
  let startedIds;
  let closedAtStarted;
  const runtime = createRuntime({ notify() {} });
  runtime.activate();
  const state = createState();
  state.reportPeriod = "2026-10-31";
  state.sources = [{ id: "s1", name: "监管报表" }, { id: "s2", name: "报送集市" }];
  state.categories = [
    { code: "pbc_central", name: "人行大集中报送" },
    { code: "pbc_template", name: "资管产品模板、逐笔" },
    { code: "east", name: xss },
  ];
  state.categoriesStatus = "success";
  const api = {
    rules: async (query) => {
      requests.push({ ...query });
      return pageFor(filteredRules(query), query);
    },
    startTask: async (payload) => { saved = payload; return { id: 99, status: "queued", report_period: payload.report_period }; },
  };
  let dialog;
  dialog = openTaskDialog({
    state, runtime, api, host: new FakeElement("div"),
    notify(message, type) { notices.push([message, type]); },
    initialRules: [allRules[0]],
    onStarted(task, selectedRules) {
      startedTask = task;
      startedIds = selectedRules.map((rule) => Number(rule.id));
      closedAtStarted = dialog.isClosed();
    },
  });
  await settle();

  assert.match(collectText(dialog.dialog), /执行校验/);
  assert.equal(collectByClass(dialog.dialog, "dv-dialog-subtitle")[0].textContent, "准备执行");
  assert.ok(collectByClass(dialog.dialog, "dv-ai-icon").length, "header 使用图标");
  assert.equal(
    collectByClass(dialog.body, "dv-execution-description")[0].textContent,
    "按所选报送期执行勾选的已启用规则。",
  );
  const grid = collectByClass(dialog.body, "dv-task-dialog-grid")[0];
  assert.ok(grid, "报送期、数据源、报送分类横排");
  assert.equal(collectByClass(grid, "dv-field").length, 3);
  assert.ok(controlByLabel(grid, "报送期 *"));
  assert.ok(controlByLabel(grid, "数据源"));
  const category = controlByLabel(grid, "报送分类");
  assert.ok(category);
  assert.ok(category.classList.contains("dv-execution-category"));
  assert.equal(category.disabled, false);
  assert.equal(category.options[0].value, "");
  assert.equal(category.options[0].textContent, "全部分类");
  assert.ok(!category.options.some(option => option.value === "__uncategorized__"));
  const initialCategoryValues = category.options.map((option) => option.value);
  assert.deepEqual(initialCategoryValues, ["", "group:pbc", "east"], "人行旧分类归一且去重，分类仅来自导航目录");
  assert.match(collectText(category), /<img src=x/);
  assert.equal(globalThis.__xss, undefined, "分类名称按文本渲染");
  const selectionWrap = collectByClass(dialog.body, "dv-execution-selection")[0];
  assert.ok(selectionWrap, "列表与分页有独立满高容器");
  assert.equal(collectByClass(selectionWrap, "dv-enabled-rule-wrap").length, 1);
  const pagination = collectByClass(selectionWrap, "pagination")[0];
  assert.ok(pagination);

  // 遮罩与 Esc 都不应关闭准备弹窗。
  await dialog.element.dispatch("click");
  await dialog.element.dispatch("keydown", { key: "Escape" });
  assert.equal(dialog.isClosed(), false);

  const checkbox = (id) => collectByClass(dialog.body, "dv-rule-checkbox").find((box) => box.dataset.enabledRule === String(id));
  assert.equal(checkbox(1).checked, true);
  const third = checkbox(3);
  third.checked = true;
  await third.dispatch("change");
  assert.match(collectText(dialog.footer), /已选 2 条规则/);
  assert.equal(selectedTextNode(dialog).textContent, "已选 2 条");
  assert.doesNotMatch(selectedTextNode(dialog).textContent, /\/\s*100(?:\s|$)/);

  // 翻到第 2 页后，任一筛选变化都必须回到第 1 页，并保留跨页勾选。
  await findButton(pagination, "第 2 页").dispatch("click");
  await settle();
  assert.equal(requests.at(-1).page, 2);
  assert.match(collectText(dialog.footer), /已选 2 条规则/);
  assert.equal(selectedTextNode(dialog).textContent, "跨页已选 2 条");
  category.value = "group:pbc";
  await category.dispatch("change");
  await settle();
  assert.equal(requests.at(-1).report_category, "group:pbc", "旧人行分类查询使用规范 code");
  assert.equal(requests.at(-1).page, 1);
  assert.equal(requests.at(-1).status, "enabled");
  assert.equal(category.value, "group:pbc");
  assert.match(collectText(dialog.footer), /已选 2 条规则/);
  assert.equal(selectedTextNode(dialog).textContent, "已选 2 条");

  category.value = "east";
  await category.dispatch("change");
  await settle();
  assert.equal(requests.at(-1).report_category, "east");
  assert.equal(requests.at(-1).page, 1);
  assert.match(collectText(dialog.footer), /跨筛选保留 2 条已选规则/);
  const second = checkbox(2);
  second.checked = true;
  await second.dispatch("change");
  assert.match(collectText(dialog.footer), /已选 3 条规则/);

  const source = controlByLabel(dialog.body, "数据源");
  source.value = "s2";
  await source.dispatch("change");
  await settle();
  assert.equal(requests.at(-1).source_id, "s2");
  assert.equal(requests.at(-1).report_category, "east");
  assert.equal(requests.at(-1).page, 1);
  assert.match(collectText(dialog.body), /当前筛选下暂无已启用规则/);
  assert.equal(pagination.hidden, false, "空页分页仍可见");
  assert.equal(pagination.dataset.empty, "true");
  assert.equal(selectedRulesBoxes(dialog).length, 0);
  assert.match(collectText(dialog.footer), /已选 3 条规则/);
  assert.match(collectText(dialog.footer), /跨筛选保留 3 条已选规则/);

  // 动态目录完成加载后刷新选项，保留当前选择；错误/加载中不能被当成“没有分类”。
  state.categories = [
    { code: "group:pbc", name: "人行报送" },
    { code: "east", name: "East5报送" },
    { code: "1104", name: "1104报送" },
  ];
  state.categoriesStatus = "success";
  state.categoriesError = "";
  dialog.refreshCategories();
  assert.equal(category.value, "east");
  assert.deepEqual(category.options.map((option) => option.value), ["", "group:pbc", "east", "1104"]);
  assert.equal(category.parentNode.children.at(-1).hidden, true);

  state.categories = [];
  state.categoriesStatus = "error";
  state.categoriesError = "报送分类加载失败：网络中断";
  dialog.refreshCategories();
  assert.equal(category.value, "east", "目录失败时保留当前选值");
  assert.equal(category.disabled, false);
  assert.ok(category.options.some((option) => option.value === ""));
  assert.ok(!category.options.some((option) => option.value === "__uncategorized__"));
  assert.match(collectText(category.parentNode), /网络中断/);
  assert.doesNotMatch(collectText(category.parentNode), /暂无分类/);

  state.categoriesStatus = "loading";
  state.categoriesError = "";
  dialog.refreshCategories();
  assert.equal(category.value, "east", "目录未完成时保留当前选值");
  assert.equal(category.disabled, false);
  assert.match(collectText(category.parentNode), /加载中/);

  state.categories = [{ code: "east", name: "East5报送" }, { code: "1104", name: "1104报送" }];
  state.categoriesStatus = "success";
  dialog.refreshCategories();
  assert.equal(category.value, "east");
  assert.equal(category.parentNode.children.at(-1).hidden, true);

  const start = findButton(dialog.footer, "开始执行（3条）");
  assert.ok(start);
  assert.equal(start.disabled, false);
  await start.dispatch("click");
  await settle();
  assert.deepEqual(saved, { rule_ids: [1, 3, 2], source_id: "", report_period: "2026-10-31" });
  assert.equal(startedTask.id, 99);
  assert.deepEqual(startedIds, [1, 3, 2], "成功回调收到显式已选规则");
  assert.equal(closedAtStarted, true, "先关闭准备弹窗再回调");
  assert.equal(dialog.isClosed(), true);
  assert.equal(notices.filter(([, type]) => type === "error").length, 0);
  runtime.destroy();

  // 分类目录加载失败时仍允许用“全部分类”查询已有规则，并给出具体提示。
  const failedRequests = [];
  const failedRuntime = createRuntime({ notify() {} });
  failedRuntime.activate();
  const failedState = createState();
  failedState.reportPeriod = "2026-10-31";
  failedState.sources = [];
  failedState.categories = [];
  failedState.categoriesStatus = "error";
  failedState.categoriesError = "报送分类加载失败：网络中断";
  const failedDialog = openTaskDialog({
    state: failedState, runtime: failedRuntime, host: new FakeElement("div"), notify() {}, initialRules: [],
    api: {
      rules: async (query) => {
        failedRequests.push({ ...query });
        return { items: [], total: 0, page: query.page, page_size: query.page_size };
      },
      startTask: async () => { throw new Error("不应提交"); },
    },
  });
  await settle();
  const failedCategory = controlByLabel(failedDialog.body, "报送分类");
  assert.ok(failedCategory);
  assert.equal(failedCategory.disabled, false);
  assert.match(collectText(failedCategory.parentNode), /网络中断/);
  assert.ok(failedCategory.options.some((option) => option.value === ""));
  failedCategory.value = "";
  await failedCategory.dispatch("change");
  await settle();
  assert.equal(failedRequests.at(-1).report_category, "");
  assert.equal(failedRequests.at(-1).page, 1);
  failedState.categoriesStatus = "loading";
  failedState.categoriesError = "";
  failedDialog.refreshCategories();
  assert.equal(failedCategory.disabled, false);
  assert.match(collectText(failedCategory.parentNode), /加载中/);
  failedDialog.close();
  failedRuntime.destroy();
}

async function bulkSelectionScenario() {
  const pageRules = allRules.slice(0, 20);
  const ids = Array.from({ length: 10000 }, (_, index) => index + 1);
  const executionCalls = [];
  const pendingBatch = deferred();
  const pendingStart = deferred();
  let rulesCalls = 0;
  let startCalls = 0;
  let saved;
  let startedRules;
  let closedAtStarted;
  const runtime = createRuntime({ notify() {} });
  runtime.activate();
  const state = dialogState();
  const api = {
    rules: async (query) => {
      rulesCalls += 1;
      return { items: pageRules, total: 10000, page: query.page, page_size: query.page_size };
    },
    executionRuleIds: async (filters, options) => {
      executionCalls.push({ filters, options });
      return pendingBatch.promise;
    },
    startTask: async (payload) => {
      startCalls += 1;
      saved = payload;
      return pendingStart.promise;
    },
  };
  let dialog;
  dialog = openTaskDialog({
    state, runtime, api, host: new FakeElement("div"), notify() {}, initialRules: [pageRules[0]],
    onStarted(_task, selectedRules) {
      startedRules = selectedRules;
      closedAtStarted = dialog.isClosed();
    },
  });
  await settle();

  const selectFiltered = collectByClass(dialog.body, "dv-execution-select-filtered")[0];
  assert.ok(selectFiltered, "新增“选择当前筛选全部规则”按钮");
  assert.equal(selectFiltered.textContent, "选择当前筛选全部规则");
  assert.equal(selectedRulesBoxes(dialog).length, 20, "列表仍只渲染当前页");
  const rulesCallsBeforeSelection = rulesCalls;

  const pendingClick = selectFiltered.dispatch("click");
  await settle();
  assert.equal(executionCalls.length, 1);
  assert.equal(selectFiltered.textContent, "正在选择…");
  assert.equal(selectFiltered.disabled, true);
  await selectFiltered.dispatch("click");
  assert.equal(executionCalls.length, 1, "选择中禁止重复触发");
  assert.deepEqual(executionCalls[0].filters, { keyword: "", source_id: "", report_category: "" });
  assert.equal(typeof executionCalls[0].options.signal.aborted, "boolean");
  assert.equal(selectedRulesBoxes(dialog).length, 20, "等待响应期间仍只有当前页 DOM");

  pendingBatch.resolve({ rule_ids: ids, count: ids.length });
  await pendingClick;
  await settle();

  assert.equal(selectedRulesBoxes(dialog).length, 20, "一万条 ID 不创建额外表格行");
  assert.equal(rulesCalls, rulesCallsBeforeSelection, "批量选 ID 不重新拉取完整规则列表");
  assert.equal(selectedTextNode(dialog).textContent, "跨页已选 10000 条");
  assert.doesNotMatch(selectedTextNode(dialog).textContent, /100000|\/\s*100(?:\s|$)/);
  assert.equal(footerNoteNode(dialog).textContent, "已选 10000 条规则 · 将生成 1 个执行批次");
  assert.equal(findButton(dialog.body, "清空选择").disabled, false);

  const start = findButton(dialog.footer, "开始执行（10000条）");
  assert.ok(start);
  assert.equal(start.disabled, false);
  const firstStart = start.dispatch("click");
  await settle();
  assert.equal(startCalls, 1);
  await start.dispatch("click");
  await settle();
  assert.equal(startCalls, 1, "提交中禁止重复 startTask");
  pendingStart.resolve({ id: 100, status: "queued", report_period: "2026-10-31" });
  await firstStart;
  await settle();

  assert.ok(saved);
  assert.equal(saved.rule_ids.length, 10000);
  assert.equal(new Set(saved.rule_ids).size, 10000);
  assert.equal(saved.rule_ids[0], 1);
  assert.equal(saved.rule_ids.at(-1), 10000);
  assert.deepEqual(saved, { rule_ids: ids, source_id: "", report_period: "2026-10-31" });
  assert.equal(startedRules.length, 10000);
  assert.deepEqual(startedRules.at(-1), { id: 10000, status: "enabled" });
  assert.equal(closedAtStarted, true, "批量选择不影响 close 后回调契约");
  assert.equal(dialog.isClosed(), true);
  runtime.destroy();
}

async function selectionParamsScenario() {
  const executionCalls = [];
  const rulesRequests = [];
  const runtime = createRuntime({ notify() {} });
  runtime.activate();
  const state = dialogState();
  const api = {
    rules: async (query) => {
      rulesRequests.push({ ...query });
      return { items: [allRules[1]], total: 1, page: 1, page_size: query.page_size };
    },
    executionRuleIds: async (filters, options) => {
      executionCalls.push({ filters, options });
      return { rule_ids: [allRules[1].id], count: 1 };
    },
    startTask: async () => { throw new Error("不应提交"); },
  };
  const dialog = openTaskDialog({
    state, runtime, api, host: new FakeElement("div"), notify() {}, initialRules: [],
  });
  await settle();

  const category = controlByLabel(dialog.body, "报送分类");
  assert.ok(!category.options.some(option => option.value === "__uncategorized__"), "执行分类只显示报送导航目录，不人为追加未分类");
  category.value = "east";
  await category.dispatch("change");
  await settle();
  const source = controlByLabel(dialog.body, "数据源");
  source.value = "s2";
  await source.dispatch("change");
  await settle();
  const search = collectByClass(dialog.body, "dv-search")[0];
  search.value = "校验";
  await search.dispatch("input");
  await search.dispatch("keydown", { key: "Enter" });
  await settle();

  assert.deepEqual(
    { keyword: rulesRequests.at(-1).keyword, source_id: rulesRequests.at(-1).source_id, report_category: rulesRequests.at(-1).report_category, page: rulesRequests.at(-1).page },
    { keyword: "校验", source_id: "s2", report_category: "east", page: 1 },
  );
  const selectFiltered = collectByClass(dialog.body, "dv-execution-select-filtered")[0];
  await selectFiltered.dispatch("click");
  await settle();

  assert.equal(executionCalls.length, 1);
  assert.deepEqual(executionCalls[0].filters, { keyword: "校验", source_id: "s2", report_category: "east" });
  assert.equal(typeof executionCalls[0].options.signal.aborted, "boolean");
  assert.equal(selectedTextNode(dialog).textContent, "已选 1 条");
  dialog.close();
  runtime.destroy();
}

async function selectionFailureScenario() {
  const runtime = createRuntime({ notify() {} });
  runtime.activate();
  const state = dialogState();
  let queryFails = false;
  const api = {
    rules: async (query) => {
      if (queryFails) throw new Error("列表查询失败");
      return pageFor(filteredRules(query), query);
    },
    executionRuleIds: async () => { throw new Error("批量选择失败"); },
    startTask: async () => { throw new Error("不应提交"); },
  };
  const dialog = openTaskDialog({
    state, runtime, api, host: new FakeElement("div"), notify() {}, initialRules: [allRules[0]],
  });
  await settle();

  const selectFiltered = collectByClass(dialog.body, "dv-execution-select-filtered")[0];
  await selectFiltered.dispatch("click");
  await settle();
  assert.equal(selectedTextNode(dialog).textContent, "已选 1 条", "批量选择失败保留原选择");
  assert.equal(footerNoteNode(dialog).textContent, "已选 1 条规则 · 将生成 1 个执行批次");
  assert.equal(selectFiltered.textContent, "选择当前筛选全部规则");
  assert.equal(selectFiltered.disabled, false);
  assert.match(collectText(dialog.body), /批量选择失败/);

  queryFails = true;
  const category = controlByLabel(dialog.body, "报送分类");
  category.value = "group:pbc";
  await category.dispatch("change");
  await settle();
  assert.equal(selectedTextNode(dialog).textContent, "已选 1 条", "列表查询失败也保留原选择");
  assert.equal(footerNoteNode(dialog).textContent, "已选 1 条规则 · 将生成 1 个执行批次");
  assert.match(collectText(dialog.body), /列表查询失败/);
  dialog.close();
  runtime.destroy();
}

async function staleCloseScenario() {
  const pendingBatch = deferred();
  const executionCalls = [];
  const runtime = createRuntime({ notify() {} });
  runtime.activate();
  const state = dialogState();
  const pageRules = allRules.slice(0, 20);
  const api = {
    rules: async (query) => ({ items: pageRules, total: 20, page: query.page, page_size: query.page_size }),
    executionRuleIds: async (filters, options) => {
      executionCalls.push({ filters, options });
      return pendingBatch.promise;
    },
    startTask: async () => { throw new Error("不应提交"); },
  };
  const dialog = openTaskDialog({
    state, runtime, api, host: new FakeElement("div"), notify() {}, initialRules: [allRules[0]],
  });
  await settle();

  const selectFiltered = collectByClass(dialog.body, "dv-execution-select-filtered")[0];
  const pendingClick = selectFiltered.dispatch("click");
  await settle();
  assert.equal(executionCalls.length, 1);
  const selectedBeforeClose = selectedTextNode(dialog).textContent;
  const footerBeforeClose = footerNoteNode(dialog).textContent;

  dialog.close();
  assert.equal(dialog.isClosed(), true);
  assert.equal(executionCalls[0].options.signal.aborted, true, "关闭弹窗立即无效化批量选择通道");

  pendingBatch.resolve({ rule_ids: [21, 22], count: 2 });
  await pendingClick;
  await settle();
  assert.equal(selectedTextNode(dialog).textContent, selectedBeforeClose, "关闭后的迟到响应不写选择");
  assert.equal(footerNoteNode(dialog).textContent, footerBeforeClose);
  runtime.destroy();
}

async function staleFilterScenario() {
  const pendingBatch = deferred();
  const executionCalls = [];
  const requests = [];
  const runtime = createRuntime({ notify() {} });
  runtime.activate();
  const state = dialogState();
  const api = {
    rules: async (query) => {
      requests.push({ ...query });
      return pageFor(filteredRules(query), query);
    },
    executionRuleIds: async (filters, options) => {
      executionCalls.push({ filters, options });
      return pendingBatch.promise;
    },
    startTask: async () => { throw new Error("不应提交"); },
  };
  const dialog = openTaskDialog({
    state, runtime, api, host: new FakeElement("div"), notify() {}, initialRules: [allRules[0]],
  });
  await settle();

  const selectFiltered = collectByClass(dialog.body, "dv-execution-select-filtered")[0];
  const pendingClick = selectFiltered.dispatch("click");
  await settle();
  assert.equal(selectFiltered.textContent, "正在选择…");

  const category = controlByLabel(dialog.body, "报送分类");
  category.value = "group:pbc";
  await category.dispatch("change");
  await settle();
  assert.equal(requests.at(-1).report_category, "group:pbc");
  assert.equal(requests.at(-1).page, 1);
  assert.equal(executionCalls[0].options.signal.aborted, true, "筛选变化取消正在进行的批量选择");

  pendingBatch.resolve({ rule_ids: [21, 22], count: 2 });
  await pendingClick;
  await settle();
  assert.equal(selectedTextNode(dialog).textContent, "已选 1 条", "旧筛选迟到响应不并入新筛选");
  assert.equal(footerNoteNode(dialog).textContent, "已选 1 条规则 · 将生成 1 个执行批次");
  assert.deepEqual(
    selectedRulesBoxes(dialog).map((box) => [box.dataset.enabledRule, box.checked]),
    [["1", true], ["3", false]],
    "旧筛选迟到响应不新增选中行",
  );
  assert.equal(selectFiltered.textContent, "选择当前筛选全部规则");
  assert.equal(selectFiltered.disabled, false);
  dialog.close();
  runtime.destroy();
}

async function fullSelectionScenario() {
  assert.equal(MAX_TASK_RULES, 25, "本场景使用小上限验证选满边界");
  const pageRules = allRules.slice(0, 20);
  const ids = Array.from({ length: 30 }, (_, index) => index + 1);
  const runtime = createRuntime({ notify() {} });
  runtime.activate();
  const state = dialogState();
  const api = {
    rules: async (query) => ({ items: pageRules, total: 30, page: query.page, page_size: query.page_size }),
    executionRuleIds: async () => ({ rule_ids: ids, count: ids.length }),
    startTask: async () => { throw new Error("不应提交"); },
  };
  const dialog = openTaskDialog({
    state, runtime, api, host: new FakeElement("div"), notify() {}, initialRules: [allRules[0]],
  });
  await settle();

  const selectFiltered = collectByClass(dialog.body, "dv-execution-select-filtered")[0];
  await selectFiltered.dispatch("click");
  await settle();
  assert.equal(selectedTextNode(dialog).textContent, "跨页已选 25 条");
  assert.equal(footerNoteNode(dialog).textContent, "已选 25 条规则 · 将生成 1 个执行批次");
  assert.equal(selectedRulesBoxes(dialog).length, 20, "选满上限也不渲染额外行");
  assert.equal(selectFiltered.disabled, true, "选满后不再触发批量选择");
  const clear = findButton(dialog.body, "清空选择");
  assert.equal(clear.disabled, false, "选满仍可清除");

  await clear.dispatch("click");
  await settle();
  assert.equal(selectedTextNode(dialog).textContent, "已选 0 条");
  assert.equal(footerNoteNode(dialog).textContent, "已选 0 条规则 · 将生成 1 个执行批次");
  assert.equal(clear.disabled, true);
  assert.equal(selectFiltered.disabled, false, "清除后可重新选择");
  assert.equal(findButton(dialog.footer, "开始执行（0条）").disabled, true);
  dialog.close();
  runtime.destroy();
}

async function immediateSearchScenario() {
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const requests = [];
  const dialog = openTaskDialog({ state: dialogState(), runtime, host: new FakeElement("div"), notify() {},
    api: { rules: async query => pageFor(filteredRules(query), query),
      executionRuleIds: async query => { requests.push(query); return { rule_ids: filteredRules(query).map(rule => rule.id) }; } } });
  await settle();
  const search = collectByClass(dialog.body, "dv-search")[0]; search.value = "DV25";
  await search.dispatch("input");
  await collectByClass(dialog.body, "dv-execution-select-filtered")[0].dispatch("click");
  assert.equal(requests[0].keyword, "DV25", "输入后立即全选必须使用已显示的关键词");
  assert.match(footerNoteNode(dialog).textContent, /已选 1 条规则/);
  dialog.close(); runtime.destroy();
}

async function scopeRefreshScenario() {
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const state = dialogState(); state.sources = [];
  const visible = [allRules[1], allRules[4]];
  const dialog = openTaskDialog({ state, runtime, host: new FakeElement("div"), notify() {},
    api: { rules: async query => pageFor(visible, query),
      executionRuleIds: async () => ({ rule_ids: [2, 5, 25] }) } });
  await settle();
  await collectByClass(dialog.body, "dv-execution-select-filtered")[0].dispatch("click");
  const category = controlByLabel(dialog.body, "报送分类"); category.value = "east";
  await category.dispatch("change"); await settle();
  assert.doesNotMatch(collectText(dialog.footer), /跨筛选保留 [23] 条/,
    "未知归属的ID不能按选择动作的筛选条件冒充规则真实归属");
  assert.match(collectText(dialog.footer), /以已选总数为准/);
  state.sources = [{ id: "s1", name: "监管报表" }]; dialog.refreshSources();
  const source = controlByLabel(dialog.body, "数据源");
  assert.ok(source.options.some(option => option.value === "s1"), "慢加载的数据源要进入已打开弹窗");
  source.value = "s1"; dialog.refreshSources(); assert.equal(source.value, "s1");
  dialog.close(); runtime.destroy();
}

async function oldServiceScenario() {
  for (const [status, message] of [[400, "invalid request"], [404, "module route not found"]]) {
    const api = createApi({ api: async () => { throw Object.assign(new Error(message), { status, payload: { error: message } }); } });
    for (const invoke of [() => api.executionRuleIds(), () => api.taskProgress()]) {
      await assert.rejects(invoke, error => {
        assert.equal(error.code, "TASK_API_VERSION_MISMATCH");
        assert.match(errorMessage(error), /后端.*重启.*刷新/);
        return true;
      });
    }
  }
  const denied = Object.assign(new Error("permission denied"), { status: 403, payload: { error: "permission denied" } });
  const api = createApi({ api: async () => { throw denied; } });
  await assert.rejects(() => api.executionRuleIds(), error => error === denied && !error.code);
}

const scenarios = {
  category: categoryScenario,
  bulk: bulkSelectionScenario,
  params: selectionParamsScenario,
  failure: selectionFailureScenario,
  "stale-close": staleCloseScenario,
  "stale-filter": staleFilterScenario,
  full: fullSelectionScenario,
  immediate: immediateSearchScenario,
  scope: scopeRefreshScenario,
  legacy: oldServiceScenario,
};
assert.ok(scenarios[scenario], `未知测试场景：${scenario}`);
await scenarios[scenario]();
console.log(JSON.stringify({ ok: true, scenario }));
