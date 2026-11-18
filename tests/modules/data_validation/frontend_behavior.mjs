import assert from "node:assert/strict";
import {
  clearRuleFilters, confirmationReadiness, createState, createTestEvidence, hasCapability,
  loadConvergedPage, newEnabledRuleQuery, ownsResource, pageConvergence, paginationView,
  previousMonthEnd, setRulePageSize, taskIssueNotice, updateBoundedSelection, updateRuleFilter,
} from "./state.mjs";
import { createRuntime, errorMessage } from "./runtime.mjs";
import { createApi } from "./api.mjs";
import { createAiCandidatePanel } from "./components/ai_candidate.mjs";
import { createPagination } from "./components/pagination.mjs";
import { createRuleTable } from "./components/rule_table.mjs";
import { createDialog } from "./components/dialog.mjs";
import { bindSearch } from "./components/search.mjs";
import { createRuleForm } from "./components/rule_form.mjs";
import { openTaskDialog } from "./components/task_dialog.mjs";
import { formatHistoryValue, openHistoryDialog } from "./components/history_dialog.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { createResultsPage } from "./pages/results.mjs";
import { activate, deactivate, mount, unmount } from "./index.mjs";

class FakeText {
  constructor(text) { this.textContent = String(text); this.parentNode = null; }
}

class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.dataset = {};
    this.listeners = new Map();
    this._className = "";
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.indeterminate = false;
    this.value = "";
    this.type = "";
    this.files = null;
    this.classList = {
      add: (...names) => {
        const values = new Set(this._className.split(/\s+/).filter(Boolean));
        names.forEach((name) => values.add(name));
        this._className = [...values].join(" ");
      },
      remove: (...names) => {
        const removed = new Set(names);
        this._className = this._className.split(/\s+/).filter((name) => name && !removed.has(name)).join(" ");
      },
      toggle: (name, force) => {
        const values = new Set(this._className.split(/\s+/).filter(Boolean));
        const enabled = force === undefined ? !values.has(name) : Boolean(force);
        if (enabled) values.add(name); else values.delete(name);
        this._className = [...values].join(" ");
        return enabled;
      },
      contains: (name) => this._className.split(/\s+/).includes(name),
    };
  }
  get className() { return this._className; }
  set className(value) { this._className = String(value || ""); }
  get options() { return this.children.filter((child) => child.tagName === "OPTION"); }
  get isConnected() { return true; }
  setAttribute(name, value) { this.attributes.set(String(name), String(value)); }
  getAttribute(name) { return this.attributes.get(String(name)); }
  append(...nodes) {
    nodes.flat(Infinity).forEach((child) => {
      if (child === null || child === undefined || child === false) return;
      const value = typeof child === "string" ? new FakeText(child) : child;
      value.parentNode = this;
      this.children.push(value);
    });
  }
  appendChild(child) { this.append(child); return child; }
  replaceChildren(...nodes) {
    this.children.forEach((child) => { child.parentNode = null; });
    this.children = [];
    this.append(...nodes);
  }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    this.parentNode = null;
  }
  contains(target) {
    if (target === this) return true;
    return this.children.some((child) => child.contains?.(target));
  }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }
  removeEventListener(type, handler) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter((item) => item !== handler));
  }
  async dispatch(type, event = {}) {
    const payload = { target: this, currentTarget: this, preventDefault() {}, ...event };
    let result;
    for (const handler of [...(this.listeners.get(type) || [])]) result = await handler(payload);
    return result;
  }
  closest(selector) {
    const match = selector.match(/^\[data-([a-z0-9-]+)\]$/i);
    let node = this;
    while (node) {
      if (match) {
        const key = match[1].replace(/-([a-z])/g, (_all, letter) => letter.toUpperCase());
        if (node.dataset?.[key] !== undefined) return node;
      } else if (selector.startsWith(".") && node.classList?.contains(selector.slice(1))) return node;
      node = node.parentNode;
    }
    return null;
  }
  focus() { document.activeElement = this; }
  click() { return this.disabled ? undefined : this.dispatch("click"); }
}

globalThis.document = {
  activeElement: null,
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_namespace, tag) => new FakeElement(tag),
  createTextNode: (text) => new FakeText(text),
};
const flush = () => new Promise((resolve) => setImmediate(resolve));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function findByClass(root, className) {
  if (root.classList?.contains(className)) return root;
  for (const child of root.children || []) {
    const found = findByClass(child, className);
    if (found) return found;
  }
  return null;
}
function collectByClass(root, className, found = []) {
  if (root.classList?.contains(className)) found.push(root);
  for (const child of root.children || []) collectByClass(child, className, found);
  return found;
}
function findButton(root, label, prefix = false) {
  if (root.tagName === "BUTTON" && (
    root.getAttribute?.("aria-label") === label
    || (prefix ? root.textContent.startsWith(label) : root.textContent === label)
  )) return root;
  for (const child of root.children || []) {
    const found = findButton(child, label, prefix);
    if (found) return found;
  }
  return null;
}
function controlByLabel(root, label) {
  if (root.tagName === "LABEL" && root.children?.[0]?.textContent === label) return root.children[1];
  for (const child of root.children || []) {
    const found = controlByLabel(child, label);
    if (found) return found;
  }
  return null;
}

// 筛选、页容量、越界收敛及独立启用规则查询。
const state = createState();
state.ruleQuery.page = 7;
updateRuleFilter(state, { keyword: "期限", status: "draft" });
assert.equal(state.ruleQuery.page, 1);
state.ruleQuery.page = 3;
setRulePageSize(state, 100);
assert.equal(state.ruleQuery.page, 1);
assert.equal(state.ruleQuery.page_size, 100);
state.ruleQuery.page = 4;
clearRuleFilters(state);
assert.deepEqual(state.ruleQuery, { keyword: "", status: "", report_category: "", source_id: "", rule_type: "", page: 1, page_size: 100 });
const enabledQuery = newEnabledRuleQuery();
assert.deepEqual(enabledQuery, { keyword: "", status: "enabled", page: 1, page_size: 20 });
assert.notEqual(enabledQuery.status, state.ruleQuery.status);
assert.deepEqual(paginationView({ total: 0, page: 1, page_size: 50 }), {
  total: 0, pages: 1, page: 1, info: "暂无数据", current: "-", previousDisabled: true, nextDisabled: true,
});
assert.equal(paginationView({ total: 20, page: 1, page_size: 20 }).info, "共 20 条，第 1 / 1 页");
assert.equal(pageConvergence({ total: 12, page_size: 5 }, 9), 3);
assert.equal(pageConvergence({ total: 0, page_size: 50 }, 2), 1);
const requests = [];
const converged = await loadConvergedPage({
  query: { page: 9, page_size: 5 },
  onConverge: (page) => requests.push(`converge:${page}`),
  request: async (query) => {
    requests.push(query.page);
    return { items: [], total: 12, page: query.page, page_size: 5, marker: query.page };
  },
});
assert.deepEqual(requests, [9, "converge:3", 3]);
assert.equal(converged.marker, 3);
let staleConvergeWrites = 0;
const staleConverged = await loadConvergedPage({
  query: { page: 9, page_size: 5 },
  request: async () => ({ items: [], total: 12, page: 9, page_size: 5 }),
  onConverge: () => { staleConvergeWrites += 1; },
  isCurrent: () => false,
});
assert.equal(staleConverged.page, 9);
assert.equal(staleConvergeWrites, 0, "旧请求不得执行越界页回写或再次请求");

// 跨页选择上限与确认门槛均执行真实纯逻辑。
const selected = new Map();
assert.equal(updateBoundedSelection(selected, { id: 1, name: "第一页" }, true, 2).ok, true);
assert.equal(updateBoundedSelection(selected, { id: 2, name: "第二页" }, true, 2).ok, true);
assert.equal(selected.size, 2);
assert.equal(updateBoundedSelection(selected, { id: 3 }, true, 2).ok, false);
assert.match(updateBoundedSelection(selected, { id: 3 }, true, 2).reason, /最多选择 2/);
updateBoundedSelection(selected, { id: 1 }, false, 2);
assert.equal(updateBoundedSelection(selected, { id: 3 }, true, 2).ok, true);
const detail = {
  id: 8, version_no: 2, content_sha256: "abc",
  definition: { null_policy: "skip", equality_policy: "allow_equal" },
};
const evidence = createTestEvidence(detail, { passed_count: 2, failed_count: 0, not_run_count: 0, cases: [{ status: "passed" }, { status: "passed" }] });
assert.equal(confirmationReadiness(detail, evidence).ready, true);
assert.equal(confirmationReadiness(detail, null).ready, false);
assert.equal(confirmationReadiness(detail, { ...evidence, passed_count: 0 }).ready, false);
assert.equal(confirmationReadiness(detail, { ...evidence, failed_count: 1 }).ready, false);
assert.equal(confirmationReadiness(detail, evidence, true).ready, false);
assert.equal(confirmationReadiness({ ...detail, version_no: 3 }, evidence).ready, false);
assert.equal(confirmationReadiness({ ...detail, definition: { ...detail.definition, null_policy: "unresolved" } }, evidence).ready, false);

// 管理员具有全部能力，但资源归属不能被管理员身份绕过。
const ordinary = { id: "1", role: "user", capabilities: ["dv.view", "dv.run"] };
assert.equal(hasCapability(ordinary, "dv.run"), true);
assert.equal(hasCapability(ordinary, "dv.confirm"), false);
assert.equal(hasCapability({ id: "9", role: "admin", capabilities: [] }, "dv.confirm"), true);
assert.equal(ownsResource({ id: "9", role: "admin" }, { creator_user_id: "1" }), false);
assert.equal(ownsResource(ordinary, { creator_user_id: "1" }), true);
assert.match(taskIssueNotice({ status: "failed" }, 0), /不代表校验通过/);
assert.match(taskIssueNotice({ status: "running" }, 0), /不能据此判定通过/);
assert.equal(taskIssueNotice({ status: "completed" }, 0), "任务已完成，接口已登记异常 0 条。");
assert.equal(previousMonthEnd(new Date("2026-11-16T01:00:00Z")), "2026-10-31");
assert.equal(previousMonthEnd(new Date("2026-01-01T01:00:00Z")), "2025-12-31");

// 分通道请求序号与 AbortController 共同阻止旧响应，停用清理异步资源。
const notifications = [];
const runtime = createRuntime({ notify: (message, type) => notifications.push({ message, type }) });
runtime.activate();
let resolveStale;
let staleSignal;
const staleToken = runtime.next("slow");
const staleRequest = runtime.request(staleToken, (signal) => {
  staleSignal = signal;
  return new Promise((resolve) => { resolveStale = resolve; });
});
const currentToken = runtime.next("slow");
assert.equal(staleSignal.aborted, true);
assert.equal(runtime.current(staleToken), false);
assert.equal(runtime.current(currentToken), true);
resolveStale({ items: [{ name: "迟到数据" }] });
await staleRequest;
assert.equal(runtime.current(staleToken), false);

const search = new FakeElement("input");
const searchCalls = [];
bindSearch({ input: search, listen: runtime.listen, runtime, onSearch: (value) => searchCalls.push(value) });
search.value = "贷";
await search.dispatch("input");
search.value = "贷款";
await search.dispatch("input");
await sleep(340);
assert.deepEqual(searchCalls, ["贷款"]);
search.value = "贷款期限";
await search.dispatch("input");
await search.dispatch("keydown", { key: "Enter" });
assert.deepEqual(searchCalls, ["贷款", "贷款期限"]);
await sleep(340);
assert.deepEqual(searchCalls, ["贷款", "贷款期限"], "回车后不得再执行防抖旧请求");
runtime.deactivate();
assert.equal(runtime.snapshot().timers, 0);
assert.equal(runtime.snapshot().controllers, 0);
assert.equal(runtime.snapshot().active, false);
assert.equal(runtime.setTimer(() => { throw new Error("停用后不应安排定时器"); }, 10), null);
assert.equal(runtime.snapshot().timers, 0);
runtime.activate();

// 公共分页在空数据、单页、多页下可见；本模块自有「条/页」下拉、前后翻页与跳页均触发真实回调。
const pageCalls = [];
const sizeCalls = [];
const pager = createPagination({
  listen: runtime.listen,
  onPage: (page) => pageCalls.push(page),
  onPageSize: (size) => sizeCalls.push(size),
});
pager.update({ total: 0, page: 1, page_size: 50 });
const pagerInfo = pager.element.children[0].children[1];
const pagerControls = pager.element.children[1];
const pagerSize = pagerControls.children[0];
const sizeTrigger = pagerSize.children[0];
const sizePanel = pagerSize.children[1];
const prevButton = pagerControls.children[1];
const pagesWrap = pagerControls.children[2];
const nextButton = pagerControls.children[3];
assert.equal(pagerInfo.textContent, "暂无数据");
assert.equal(pagesWrap.children.length, 0, "空数据不渲染页码");
assert.equal(prevButton.disabled, true);
assert.equal(nextButton.disabled, true);
assert.equal(prevButton.textContent, "上一页");
assert.equal(nextButton.textContent, "下一页");
assert.equal(sizeTrigger.getAttribute("aria-label"), "每页条数");
assert.equal(sizePanel.hidden, true);
await sizeTrigger.dispatch("click");
assert.equal(sizePanel.hidden, false, "点击后展开模块自有条/页下拉");
const sizeOption = sizePanel.children.find((item) => item.dataset.pageSize === "100");
await sizeOption.dispatch("click");
assert.equal(sizePanel.hidden, true);
assert.equal(sizeTrigger.children[0].textContent, "100 条/页");
assert.deepEqual(sizeCalls, [100]);
pager.update({ total: 20, page: 1, page_size: 20 });
assert.equal(pagerInfo.textContent, "共 20 条，第 1 / 1 页");
assert.equal(pagesWrap.children.length, 1);
assert.equal(nextButton.disabled, true);
pager.update({ total: 120, page: 2, page_size: 20 });
assert.ok(pagesWrap.children.length >= 3, "多页时渲染页码按钮");
const pageFour = pagesWrap.children.find((item) => item.textContent === "4");
await pageFour.dispatch("click");
await prevButton.dispatch("click");
const jump = pagerControls.children[4].children[1];
jump.value = "4";
await jump.dispatch("change");
assert.deepEqual(pageCalls, [4, 1, 4]);

// 列表空态与表格只显示其一：空数据时不得再露出空表头和大片空白表格区。
const listRuntime = createRuntime({ notify: () => {} });
listRuntime.activate();
const ruleList = createRuleTable({
  listen: listRuntime.listen, user: ordinary, onAction: () => {}, onSelect: () => {},
});
ruleList.update({ items: [], total: 0, page: 1, page_size: 50 }, new Map(), { status: "success" });
const listFeedback = ruleList.element.children[0];
const listTable = ruleList.element.children[1];
assert.equal(listFeedback.hidden, false);
assert.equal(listTable.hidden, true, "空数据时不得同时露出空表头与空表体");
assert.equal(findByClass(listFeedback, "dv-empty").children[0].textContent, "暂无数据");
ruleList.update({
  items: [{ id: 1, rule_code: "DV000001", name: "期限规则", status: "draft" }],
  total: 1, page: 1, page_size: 50,
}, new Map(), { status: "success" });
assert.equal(listFeedback.hidden, true);
assert.equal(listTable.hidden, false, "有数据时必须显示表格");
listRuntime.destroy();

// 刚读取的服务端映射版本与表结构一致时不得误判为未保存修改。
const editorState = createState();
editorState.sourcesStatus = "success";
editorState.sources = [{ id: "src", name: "测试数据源", dialect: "mysql" }];
editorState.categoriesStatus = "success";
editorState.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
const editor = createRuleForm({
  state: editorState, listen: runtime.listen, user: ordinary,
  onChange: () => {}, onDescribe: () => {}, onParse: () => {},
  onRetrySources: () => {}, onRetryModels: () => {}, onMode: () => {},
});
editor.setSources();
editor.setCategories();
editor.reset({
  id: 8, name: "期限规则", mapping_version: "map-1", report_category: "pbc_central",
  definition: {
    name: "期限规则", description: "期限", source_id: "src", report_category: "pbc_central", table_name: "loan", dialect: "mysql",
    business_key: "project_code", expression: { left: "maturity_date", op: "lt", right: "issue_date" },
    violation_message: "期限异常", null_policy: "skip", equality_policy: "allow_equal",
    generation_mode: "manual", mapping_version: "map-1", rule_type: "field_compare",
  },
});
assert.equal(controlByLabel(editor.element, "监管报送分类 *").value, "pbc_central");
editor.setSources();
editor.setMetadata({ mapping_version: "map-1", columns: [
  { column_name: "project_code" }, { column_name: "maturity_date" },
  { column_name: "issue_date" }, { column_name: "report_date" },
] });
assert.equal(editor.isDirty(), false, "保存后真实 detail 与 mapping_version 一致时必须可直接测试");
assert.equal(editor.validateForSave().mapping_version, "map-1");
assert.equal(editor.metadataColumns().length, 4);
runtime.destroy();
assert.equal(runtime.snapshot().listeners, 0);
assert.equal(runtime.snapshot().timers, 0);

// 数值常量比较：字段模式保持旧签名；常量模式保存/重载 0、切换与非法校验贯通。
const constantRuntime = createRuntime({ notify: () => {} });
constantRuntime.activate();
const constantState = createState();
constantState.sourcesStatus = "success";
constantState.sources = [{ id: "src", name: "测试数据源", dialect: "mysql" }];
constantState.categoriesStatus = "success";
constantState.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
const constantForm = createRuleForm({
  state: constantState, listen: constantRuntime.listen, user: ordinary,
  onChange: () => {}, onDescribe: () => {}, onParse: () => {},
  onRetrySources: () => {}, onRetryModels: () => {},
});
constantForm.setSources();
constantForm.setCategories();
const constantColumns = [
  { column_name: "project_code" }, { column_name: "amount" },
  { column_name: "other_amount" }, { column_name: "report_date" },
];
const constantDefinition = (expression) => ({
  id: 8, name: "金额规则", report_category: "pbc_central", mapping_version: "map-constant",
  definition: {
    name: "金额规则", description: "金额不得为零", source_id: "src", dialect: "mysql",
    table_name: "loan", report_category: "pbc_central", business_key: "project_code",
    expression, violation_message: "金额异常", null_policy: "skip", equality_policy: "allow_equal",
    generation_mode: "manual", mapping_version: "map-constant", rule_type: "field_compare",
  },
});
constantForm.reset(constantDefinition({ left: "amount", op: "eq", right: "other_amount" }));
constantForm.setMetadata({ mapping_version: "map-constant", columns: constantColumns });
const targetType = controlByLabel(constantForm.element, "比较目标类型 *");
const rightFieldControl = controlByLabel(constantForm.element, "右字段 *");
const rightConstantControl = controlByLabel(constantForm.element, "数值常量 *");
const equalityControl = controlByLabel(constantForm.element, "相等处理口径");
const equalityField = equalityControl.parentNode;
const constantHint = collectByClass(constantForm.element, "dv-inline-status")
  .find((node) => node.textContent === "数值常量按异常触发关系判断相等");
assert.equal(targetType.value, "field");
assert.equal(rightFieldControl.hidden, false);
assert.equal(rightConstantControl.parentNode.hidden, true);
assert.equal(constantForm.isDirty(), false);
assert.deepEqual(constantForm.read().expression, { left: "amount", op: "eq", right: "other_amount" });
assert.equal(Object.prototype.hasOwnProperty.call(constantForm.read().expression, "right_type"), false);
assert.equal(constantForm.validateForSave().expression.right, "other_amount");

// 字段模式下先选择非默认相等口径，切到常量后必须保留该策略供切回使用。
equalityControl.value = "reject_equal";
await equalityControl.dispatch("change");
targetType.value = "value";
await targetType.dispatch("change");
assert.equal(rightFieldControl.parentNode.hidden, true);
assert.equal(rightConstantControl.parentNode.hidden, false);
assert.equal(equalityField.hidden, true);
assert.equal(equalityControl.disabled, true);
assert.equal(constantHint.hidden, false, "常量模式必须说明相等由异常触发关系判断");
assert.equal(constantForm.read().equality_policy, "allow_equal", "常量模式必须输出非未确认策略且不采用字段口径");
rightConstantControl.value = "0";
await rightConstantControl.dispatch("input");
const zeroPayload = constantForm.validateForSave();
assert.deepEqual(zeroPayload.expression, { left: "amount", op: "eq", right_type: "value", right: 0 });
assert.equal(typeof zeroPayload.expression.right, "number");
assert.equal(zeroPayload.expression.right, 0, "0 必须作为数值常量保存，不能当成空值或字段名");
assert.equal(zeroPayload.equality_policy, "allow_equal");
constantForm.markSaved();
assert.equal(constantForm.isDirty(), false, "数值 0 保存签名必须稳定");

// 非法常量：只报数值常量错误，不进入字段存在性校验。
for (const invalid of ["", "abc", "Infinity", "NaN"]) {
  rightConstantControl.value = invalid;
  await rightConstantControl.dispatch("input");
  let reason = "";
  try {
    constantForm.validateForSave();
  } catch (error) {
    reason = error.message;
  }
  assert.match(reason, /非空有限数值常量/);
  assert.doesNotMatch(reason, /不在当前真实表结构/);
}

// 重新放回 0 后可再次通过保存校验。
rightConstantControl.value = "0";
await rightConstantControl.dispatch("input");
assert.equal(constantForm.validateForSave().expression.right, 0);

// 切回字段模式：恢复进入常量前的字段相等口径，表达式回到旧的三键签名。
targetType.value = "field";
await targetType.dispatch("change");
assert.equal(rightFieldControl.parentNode.hidden, false);
assert.equal(rightConstantControl.parentNode.hidden, true);
assert.equal(equalityField.hidden, false);
assert.equal(equalityControl.disabled, false);
assert.equal(equalityControl.value, "reject_equal", "切回字段模式必须恢复原字段相等口径");
rightFieldControl.value = "other_amount";
await rightFieldControl.dispatch("change");
const fieldPayload = constantForm.validateForSave();
assert.deepEqual(fieldPayload.expression, { left: "amount", op: "eq", right: "other_amount" });
assert.equal(fieldPayload.equality_policy, "reject_equal");
assert.equal(Object.prototype.hasOwnProperty.call(fieldPayload.expression, "right_type"), false);

// 保存后按服务端详情重载：仍为数值常量 0，且不误判未保存修改。
constantForm.reset(constantDefinition({ left: "amount", op: "eq", right_type: "value", right: 0 }));
constantForm.setMetadata({ mapping_version: "map-constant", columns: constantColumns });
assert.equal(targetType.value, "value");
assert.equal(rightConstantControl.value, "0");
assert.deepEqual(constantForm.read().expression, { left: "amount", op: "eq", right_type: "value", right: 0 });
assert.equal(constantForm.read().equality_policy, "allow_equal");
assert.equal(constantForm.isDirty(), false, "常量 0 重载后必须与服务端签名一致");
constantForm.markSaved();

// AI 候选常量 0：表单回填 0，候选面板显示 0 且字段列表不列常量。
constantForm.applyCandidate({
  rule_type: "field_compare", rule_name: "零值规则",
  expression: { left: "amount", op: "eq", right_type: "value", right: 0 },
  violation_message: "金额不得为零", null_policy: "skip", equality_policy: "unresolved",
});
assert.equal(targetType.value, "value");
assert.equal(rightConstantControl.value, "0");
assert.deepEqual(constantForm.read().expression, { left: "amount", op: "eq", right_type: "value", right: 0 });
assert.equal(constantForm.read().equality_policy, "allow_equal", "候选的字段相等口径不得覆盖常量模式固定策略");
const candidatePanel = createAiCandidatePanel();
candidatePanel.update({
  rule_type: "field_compare", rule_name: "零值规则",
  expression: { left: "amount", op: "eq", right_type: "value", right: 0 },
  violation_message: "金额不得为零",
}, { source_id: "src", table_name: "loan" });
const conditionHeadline = findByClass(candidatePanel.element, "dv-ai-conclusion");
assert.ok(conditionHeadline, "候选条件必须转为业务结论");
assert.equal(conditionHeadline.textContent, "amount为 0时，提示人工核实", "数值 0 不得显示为—");
assert.equal(collectByClass(candidatePanel.element, "dv-parse-metric").length, 0, "不再呈现技术指标墙");
constantRuntime.destroy();

// 未决口径必须随规则保存/重载，处理说明不能放行不支持的要求。
const reviewRuntime = createRuntime({ notify: () => {} });
reviewRuntime.activate();
const reviewForm = createRuleForm({
  state: constantState, listen: reviewRuntime.listen, user: ordinary,
  onChange: () => {}, onDescribe: () => {}, onParse: () => {},
});
reviewForm.setSources();
reviewForm.setCategories();
const reviewedDefinition = {
  ...constantDefinition({ left: "amount", op: "eq", right_type: "value", right: 0 }).definition,
  uncertainties: ["确认存续范围"], uncertainty_resolutions: [], unsupported_requirements: [],
};
reviewForm.reset({ definition: reviewedDefinition });
reviewForm.setMetadata({ columns: constantColumns, mapping_version: "map-constant" });
assert.deepEqual(reviewForm.validateForSave().uncertainties, ["确认存续范围"]);
let reviewInput = controlByLabel(reviewForm.element, "处理说明 1：确认存续范围");
assert.ok(reviewInput);
assert.equal(controlByLabel(reviewForm.groups.config, "处理说明 1：确认存续范围"), reviewInput,
  "工作台移动分组后，复核控件仍必须挂载在配置分组中");
reviewInput.value = "文档证明该表仅存续项目，无额外筛选";
await reviewInput.dispatch("input");
assert.equal(reviewForm.isDirty(), true);
let reviewPayload = reviewForm.validateForSave();
assert.deepEqual(reviewPayload.uncertainty_resolutions, ["文档证明该表仅存续项目，无额外筛选"]);
reviewForm.reset({ definition: reviewPayload });
assert.equal(controlByLabel(reviewForm.element, "处理说明 1：确认存续范围").value, reviewPayload.uncertainty_resolutions[0]);
assert.equal(confirmationReadiness({ ...detail, definition: { ...detail.definition, ...reviewPayload } }, evidence).ready, true);
assert.equal(confirmationReadiness({ ...detail, definition: { ...detail.definition, ...reviewPayload, uncertainty_resolutions: [] } }, evidence).ready, false);
assert.equal(confirmationReadiness({ ...detail, definition: { ...detail.definition, ...reviewPayload, unsupported_requirements: ["需要状态筛选"] } }, evidence).ready, false);
reviewForm.applyCandidate({ rule_type: "field_compare", uncertainties: ["新问题"], expression: { left: "amount", op: "eq", right_type: "value", right: 0 } });
assert.deepEqual(reviewForm.read().uncertainty_resolutions, [""]);
assert.ok(controlByLabel(reviewForm.element, "处理说明 1：新问题"));
reviewForm.applyCandidate({ status: "needs_clarification", uncertainties: ["选表不唯一"], unsupported_requirements: ["需要跨表"] });
assert.throws(() => reviewForm.validateForSave(), /澄清/);
reviewForm.reset(constantDefinition({ left: "amount", op: "eq", right: "other_amount" }));
assert.equal(Object.hasOwn(reviewForm.read(), "uncertainties"), false, "旧手动规则不应被附加空口径字段");
reviewForm.reset(null, { ...reviewPayload, unsupported_requirements: ["额外状态筛选"] });
assert.deepEqual(reviewForm.read().uncertainties, reviewPayload.uncertainties, "转手工 seed 必须保留复核口径");
assert.deepEqual(reviewForm.read().unsupported_requirements, ["额外状态筛选"]);
const aiReviewForm = createRuleForm({ state: constantState, mode: "ai", listen: reviewRuntime.listen, user: { ...ordinary, capabilities: [...(ordinary.capabilities || []), "dv.ai_use"] }, onChange: () => {} });
aiReviewForm.applyCandidate({ rule_type: "field_compare", uncertainties: ["AI口径"], expression: { left: "amount", op: "eq", right_type: "value", right: 0 } });
assert.ok(controlByLabel(aiReviewForm.groups.aiConfig, "处理说明 1：AI口径"), "AI 工作台配置分组也必须实际挂载复核控件");
reviewRuntime.destroy();
assert.equal(constantRuntime.snapshot().listeners, 0);

// 模型探针错误码必须展示阶段与错误编号；成功文案不得暗示正式生成保证。
const modelErrorCases = [
  ["MODEL_TIMEOUT", "generate_rule", "a1b2c3d4e5f6", /^规则生成阶段：模型生成超时.*（错误编号 a1b2c3d4e5f6）$/],
  ["MODEL_REQUEST_FAILED", "select_table", "", /^选表阶段：模型服务拒绝或未能完成请求/],
  ["MODEL_RESPONSE_INVALID", "generate_rule", "0123456789ab", /^规则生成阶段：模型返回内容不符合规则格式.*（错误编号 0123456789ab）$/],
];
for (const [code, stage, reference, pattern] of modelErrorCases) {
  assert.match(errorMessage({ payload: { error: { code, stage, reference } } }), pattern);
}

// 弹窗只能由按钮或 Esc 关闭，遮罩点击保持打开。
let closed = 0;
const dialogHost = new FakeElement("div");
const dialog = createDialog({ host: dialogHost, title: "测试弹窗", onClose: () => { closed += 1; }, onError: (message) => { throw new Error(message); } });
await dialog.element.dispatch("click", { target: dialog.element });
assert.equal(dialogHost.children.length, 1);
assert.equal(closed, 0);
await dialog.closeButton.dispatch("click");
assert.equal(dialogHost.children.length, 0);
assert.equal(closed, 1);
const escDialog = createDialog({ host: dialogHost, title: "Esc 弹窗" });
await escDialog.element.dispatch("keydown", { key: "Escape" });
assert.equal(dialogHost.children.length, 1, "Esc 也不能替代显式按钮关闭");
escDialog.close();

// API 仅封装既有路由，并透传 AbortSignal。
const apiCalls = [];
const api = createApi({ api: async (path, options) => { apiCalls.push({ path, options }); return { data: { ok: true } }; } });
await api.rules({ page: 2, page_size: 20, keyword: "贷款", status: "enabled" }, { signal: "signal-1" });
assert.match(apiCalls[0].path, /^\/api\/modules\/data-validation\/rules\?/);
const ruleParams = new URLSearchParams(apiCalls[0].path.split("?")[1]);
assert.equal(ruleParams.get("status"), "enabled");
assert.equal(ruleParams.get("page"), "2");
assert.equal(ruleParams.get("page_size"), "20");
assert.equal(ruleParams.get("keyword"), "贷款");
assert.equal(apiCalls[0].options.signal, "signal-1");
await api.cancelTask(7);
await api.retryTask(7);
await api.exportRulePack([1, 2]);
await api.importRulePack('{"rules":[]}');
assert.equal(apiCalls[1].path, "/api/modules/data-validation/tasks/7/cancel");
assert.equal(apiCalls[2].path, "/api/modules/data-validation/tasks/7/retry");
assert.equal(apiCalls[3].path, "/api/modules/data-validation/rule-packs/export");
assert.deepEqual(JSON.parse(apiCalls[3].options.body), { rule_ids: [1, 2] });
assert.equal(apiCalls[4].path, "/api/modules/data-validation/rule-packs/import");
await api.ruleHistory(8, { page: 2, page_size: 20 });
assert.equal(apiCalls[5].path, "/api/modules/data-validation/rules/8/history?page=2&page_size=20");

// 实际打开任务弹窗：主规则筛选为 draft/page 4，弹窗仍独立请求 enabled/page 1。
const dialogRuntime = createRuntime({ notify: () => {} });
dialogRuntime.activate();
const dialogRequests = [];
const dialogApi = createApi({ api: async (path, options) => {
  dialogRequests.push({ path, options });
  if (path.includes("/rules?")) return { data: { items: [], total: 0, page: 1, page_size: 20 } };
  return { data: {} };
} });
const taskState = createState();
taskState.ruleQuery = { keyword: "其他筛选", status: "draft", page: 4, page_size: 100 };
const taskDialog = openTaskDialog({
  state: taskState, runtime: dialogRuntime, api: dialogApi, listen: dialogRuntime.listen,
  host: new FakeElement("div"), user: ordinary, notify: () => {}, initialRules: [], onStarted: () => {},
});
await flush();
await flush();
assert.ok(dialogRequests.length >= 1);
const dialogParams = new URLSearchParams(dialogRequests[0].path.split("?")[1]);
assert.equal(dialogParams.get("status"), "enabled");
assert.equal(dialogParams.get("page"), "1");
assert.equal(dialogParams.get("page_size"), "20");
assert.equal(dialogParams.get("keyword"), null);
taskDialog.close();
dialogRuntime.destroy();

// 手动创建：单页分区，②配置区与③测试区初始隐藏，读取表结构 / 保存草稿后逐步出现。
const manualRuntime = createRuntime({ notify: () => {} });
manualRuntime.activate();
const manualState = createState();
manualState.sourcesStatus = "success";
manualState.sources = [{ id: "src", name: "真实数据源", dialect: "mysql" }];
manualState.categoriesStatus = "success";
manualState.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
const manualDialogHost = new FakeElement("div");
let manualSaved = null;
let manualConfirmed = null;
const manualApi = {
  describe: async () => ({
    mapping_version: "map-manual",
    columns: [
      { column_name: "project_code", data_type: "varchar", comment: "项目编号" },
      { column_name: "maturity_date", data_type: "date", comment: "到期日" },
      { column_name: "issue_date", data_type: "date", comment: "发放日" },
      { column_name: "report_date", data_type: "date" },
    ],
  }),
  save: async (payload) => { manualSaved = { ...payload }; return { id: 51 }; },
  rule: async (id) => ({
    id, rule_code: "DV000051", name: manualSaved.name, creator_user_id: "1", status: "draft",
    version_no: 1, content_sha256: "manual-hash", sql_text: "SELECT manual_sql", definition: manualSaved,
  }),
  test: async () => ({
    passed_count: 1, failed_count: 0, not_run_count: 0,
    cases: [{ name: "正常", row: {}, expected_count: 0, actual_count: 0, status: "passed" }],
  }),
  confirm: async (id, payload) => { manualConfirmed = { id, ...payload }; return { id, status: "enabled" }; },
};
const manualWorkbench = createWorkbench({
  state: manualState, runtime: manualRuntime, api: manualApi, listen: manualRuntime.listen,
  user: { id: "1", role: "user", capabilities: ["dv.manage", "dv.test", "dv.confirm"] },
  notify: () => {}, host: manualDialogHost,
  onClose: () => {}, onChanged: async () => {},
  confirmAction: async () => true,
  onRetrySources: () => {}, onRetryModels: () => {},
});
await manualWorkbench.open({ mode: "manual" });
assert.equal(manualDialogHost.children.length, 1, "手动创建打开独立弹窗");
assert.equal(findButton(manualWorkbench.element, "✦ AI 分析"), null, "手动弹窗不得渲染 AI 分析控件");
assert.equal(findButton(manualWorkbench.element, "转手工继续"), null, "手动弹窗不得渲染转手工入口");
const manualConfig = findByClass(manualWorkbench.element, "dv-config-section");
const manualTesting = findByClass(manualWorkbench.element, "dv-testing-section");
assert.equal(manualConfig.hidden, true, "初始不显示配置区");
assert.equal(manualTesting.hidden, true, "初始不显示测试区");
// 基本信息 + 读取表结构 → 配置区出现。
assert.equal(controlByLabel(manualWorkbench.element, "数据源 *").value, "src", "手动创建数据源也应默认选中");
controlByLabel(manualWorkbench.element, "规则名称 *").value = "手工期限规则";
await controlByLabel(manualWorkbench.element, "规则名称 *").dispatch("input");
controlByLabel(manualWorkbench.element, "数据源 *").value = "src";
await controlByLabel(manualWorkbench.element, "数据源 *").dispatch("change");
controlByLabel(manualWorkbench.element, "监管报送分类 *").value = "pbc_central";
await controlByLabel(manualWorkbench.element, "监管报送分类 *").dispatch("change");
controlByLabel(manualWorkbench.element, "目标表 / 业务对象 *").children[0].value = "loan";
await controlByLabel(manualWorkbench.element, "目标表 / 业务对象 *").children[0].dispatch("input");
await findButton(manualWorkbench.element, "读取表结构").dispatch("click");
await flush();
assert.equal(manualConfig.hidden, false, "读取表结构后配置区出现");
// 补齐映射与口径后保存 → 测试区出现。
controlByLabel(manualWorkbench.element, "业务主键 *").value = "project_code";
await controlByLabel(manualWorkbench.element, "业务主键 *").dispatch("change");
controlByLabel(manualWorkbench.element, "异常触发关系").value = "lt";
await controlByLabel(manualWorkbench.element, "异常触发关系").dispatch("change");
controlByLabel(manualWorkbench.element, "左字段 *").value = "maturity_date";
await controlByLabel(manualWorkbench.element, "左字段 *").dispatch("change");
controlByLabel(manualWorkbench.element, "右字段 *").value = "issue_date";
await controlByLabel(manualWorkbench.element, "右字段 *").dispatch("change");
controlByLabel(manualWorkbench.element, "异常说明 *").value = "期限异常";
await controlByLabel(manualWorkbench.element, "异常说明 *").dispatch("input");
controlByLabel(manualWorkbench.element, "空值处理口径").value = "skip";
await controlByLabel(manualWorkbench.element, "空值处理口径").dispatch("change");
controlByLabel(manualWorkbench.element, "相等处理口径").value = "allow_equal";
await controlByLabel(manualWorkbench.element, "相等处理口径").dispatch("change");
await findButton(manualWorkbench.element, "保存草稿").dispatch("click");
await flush();
assert.equal(manualSaved.generation_mode, "manual");
assert.equal(manualSaved.mapping_version, "map-manual");
assert.equal(manualTesting.hidden, false, "保存草稿后测试区出现");
assert.match(findByClass(manualWorkbench.element, "dv-sql-preview").textContent, /manual_sql/);
await findButton(manualWorkbench.element, "运行测试").dispatch("click");
await flush();
await findButton(manualWorkbench.element, "确认启用").dispatch("click");
await flush();
assert.deepEqual(manualConfirmed, { id: 51, version_no: 1, expected_hash: "manual-hash" });
manualRuntime.destroy();

// AI 创建：单页分区，初始仅输入区；分析成功后描述折叠、配置区出现；保存后测试区出现。
const workRuntime = createRuntime({ notify: () => {} });
workRuntime.activate();
const workState = createState();
workState.sourcesStatus = "success";
workState.sources = [{ id: "src", name: "真实数据源", dialect: "mysql" }];
workState.categoriesStatus = "success";
workState.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
workState.modelsStatus = "success";
workState.models = [{ id: "model-1", name: "内网模型", model_name: "validation-model", is_default: true }];
const realColumns = [
  { column_name: "project_code", comment: "项目编号" },
  { column_name: "maturity_date", comment: "到期日" },
  { column_name: "issue_date", comment: "发放日" },
  { column_name: "report_date", comment: "报送日期" },
];
let createCalls = 0;
let getCalls = 0;
let modelTestCalls = 0;
let saveCalls = 0;
let testCalls = 0;
let confirmCalls = 0;
let savedDefinition = null;
let confirmPayload = null;
let changedCount = 0;
let workClosed = 0;
let resolveCreate = null;
let firstResult = null;
const workDialogHost = new FakeElement("div");
let previewTestCalls = 0;
let previewCalls = 0;
function makeWorkPreview(definition, hash) {
  const greater = definition.expression.op === "gt";
  const dates = (maturity, issue) => ({ maturity_date: maturity, issue_date: issue });
  const cases = [
    { name: "正常", row: greater ? dates("2026-01-01", "2027-01-01") : dates("2027-01-01", "2026-01-01"), expected_count: 0 },
    { name: "明显异常", row: greater ? dates("2027-01-01", "2026-01-01") : dates("2026-01-01", "2027-01-01"), expected_count: 1 },
    { name: "边界", row: dates("2026-01-01", "2026-01-01"), expected_count: 0 },
    { name: "空值", row: dates(null, "2026-01-01"), expected_count: 0 },
  ].map((item) => ({ ...item, actual_count: null, status: "not_run" }));
  return { definition, content_sha256: hash, sql_preview: "SELECT compiled_preview_sql", sql_params: { report_date: null }, cases, persisted: false };
}
const workApi = {
  describe: async (source, table) => {
    assert.equal(source, "src");
    assert.equal(table, "loan");
    return { mapping_version: "map-real", columns: realColumns };
  },
  testModel: async (modelId) => {
    modelTestCalls += 1;
    assert.equal(modelId, "model-1");
    return { available: true };
  },
  createAnalysis: async (payload) => {
    createCalls += 1;
    assert.equal(payload.model_id, "model-1");
    assert.equal(payload.source_id, "src");
    assert.equal(payload.table, undefined, "分析请求不得携带表结构，表清单与分类由后端读取或选定");
    const result = {
      rule_name: "贷款期限合理性校验", rule_type: "field_compare",
      table_name: "loan", source_id: "src", dialect: "mysql",
      report_category: "pbc_central", report_category_name: "人行大集中报送",
      columns: realColumns, mapping_version: "map-real",
      expression: { left: "maturity_date", op: createCalls === 1 ? "lt" : "gt", right: "issue_date" },
      business_key: "project_code", scope_description: "贷款记录",
      violation_message: "贷款期限异常", null_policy: "skip", equality_policy: "allow_equal",
      uncertainties: [], duplicate: { kind: "none" }, sql_status: "candidate", verification_status: "not_run",
    };
    result.preview = makeWorkPreview({ ...result, name: result.rule_name, generation_mode: "ai", description: payload.request_text }, `preview-${createCalls}`);
    const analysis_id = `analysis-${createCalls}`;
    if (createCalls === 1) {
      firstResult = result;
      return await new Promise((resolve) => { resolveCreate = () => resolve({
        analysis_id, status: "running", elapsed_ms: 0,
        steps: [{ id: "semantics", status: "running", detail: "理解需求" }],
      }); });
    }
    return {
      analysis_id, status: "completed", elapsed_ms: 0,
      steps: [
        { id: "semantics", status: "completed", table_name: "loan", field_count: 4 },
        { id: "metadata", status: "completed" },
        { id: "generation", status: "completed" },
      ],
      result,
    };
  },
  getAnalysis: async (id) => {
    getCalls += 1;
    return {
      analysis_id: id, status: "completed", elapsed_ms: 1200,
      steps: [
        { id: "semantics", status: "completed", table_name: "loan", field_count: 4 },
        { id: "metadata", status: "completed" },
        { id: "generation", status: "completed" },
      ],
      result: firstResult,
    };
  },
  cancelAnalysis: async () => {},
  preview: async (payload) => makeWorkPreview(payload.definition, `decision-${++previewCalls}`),
  testCandidate: async (payload) => {
    previewTestCalls += 1;
    const cases = payload.cases.map((item) => {
      const { maturity_date: left, issue_date: right } = item.row;
      const actual = left === null ? 0 : Number(payload.definition.expression.op === "gt" ? left > right : left < right);
      return { ...item, actual_count: actual, status: actual === item.expected_count ? "passed" : "failed" };
    });
    return { content_sha256: payload.expected_hash, cases, passed_count: cases.filter((item) => item.status === "passed").length,
      failed_count: cases.filter((item) => item.status === "failed").length, not_run_count: 0, persisted: false };
  },
  save: async (payload) => {
    saveCalls += 1;
    savedDefinition = { ...payload };
    return { id: 41 };
  },
  rule: async (id) => ({
    id, rule_code: "DV000041", name: savedDefinition.name, creator_user_id: "1", status: "draft",
    version_no: 1, content_sha256: "real-hash", sql_text: "SELECT real_detail_sql", definition: savedDefinition,
  }),
  test: async (id, payload) => {
    testCalls += 1;
    assert.equal(id, 41);
    assert.equal(payload.version_no, 1);
    return {
      passed_count: 1, failed_count: 0, not_run_count: 0,
      cases: [{ name: "真实案例", row: { maturity_date: "2026-12-31", issue_date: "2026-01-01" }, expected_count: 0, actual_count: 0, status: "passed" }],
    };
  },
  confirm: async (id, payload) => {
    confirmCalls += 1;
    confirmPayload = { id, ...payload };
    return { id, status: "enabled" };
  },
};
const workbench = createWorkbench({
  state: workState, runtime: workRuntime, api: workApi, listen: workRuntime.listen,
  user: { id: "1", role: "user", capabilities: ["dv.manage", "dv.ai_use", "dv.test", "dv.confirm"] },
  notify: () => {}, host: workDialogHost,
  onClose: () => { workClosed += 1; }, onChanged: async () => { changedCount += 1; },
  confirmAction: async () => true,
  onRetrySources: () => {}, onRetryModels: () => {},
});
await workbench.open({ mode: "ai" });
assert.equal(workDialogHost.children.length, 1, "AI 创建打开独立弹窗");
assert.ok(findButton(workbench.element, "✦ AI 分析"), "AI 输入区包含分析控件");
// 初始仅输入区：配置区与测试区隐藏，AI 配置字段不在输入区出现。
const aiInput = findByClass(workbench.element, "dv-form-ai-input");
const aiConfig = findByClass(workbench.element, "dv-form-ai-config");
const aiCollapsed = findByClass(workbench.element, "dv-description-collapsed");
const workConfig = findByClass(workbench.element, "dv-config-section");
const workTesting = findByClass(workbench.element, "dv-testing-section");
assert.ok(aiInput);
assert.equal(aiConfig, null, "AI technical config must not be mounted");
assert.ok(findByClass(workbench.element, "dv-ai-mark"), "保留原星光图标");
assert.equal(workConfig.hidden, true, "初始不显示结果/配置区");
assert.equal(workTesting.hidden, true, "初始不显示测试/操作区");
assert.equal(controlByLabel(workbench.element, "规则名称 *"), null, "AI 模式不展示内部配置字段");
assert.equal(aiCollapsed.hidden, true, "未分析时描述不折叠");
assert.equal(findButton(workbench.element, "下一步"), null, "单页不再有下一步按钮");
// 数据源默认选中当前唯一可用数据源（监管报送集市白名单）。
assert.equal(controlByLabel(workbench.element, "数据源 *").value, "src", "数据源应默认选中");
// 模型置于需求卡片顶栏，只有名称，不再出现底层型号拼接或独立可用性测试。
const aiMeta = findByClass(workbench.element, "dv-ai-request-meta");
assert.equal(controlByLabel(aiMeta, "启用模型").options.find(option => option.value === "model-1").textContent, "内网模型");
assert.ok(controlByLabel(aiMeta, "数据源 *"));
assert.equal(findButton(workbench.element, "测试可用性"), null);
assert.equal(modelTestCalls, 0);
controlByLabel(workbench.element, "数据源 *").value = "src";
await controlByLabel(workbench.element, "数据源 *").dispatch("change");
controlByLabel(workbench.element, "需求描述 *").value = "到期日不得早于发放日";
await controlByLabel(workbench.element, "需求描述 *").dispatch("input");
const analyzing = findButton(workbench.element, "✦ AI 分析").dispatch("click");
await flush();
assert.equal(createCalls, 1);
assert.equal(saveCalls, 0);
// 分析中必须有明显反馈：按钮变为「AI 分析中…」、输入禁用、进度条可见。
const aiProgress = findByClass(workbench.element, "dv-ai-progress");
assert.equal(aiProgress.hidden, false, "分析中必须显示进度提示");
assert.match(findByClass(aiProgress, "dv-ai-wait-title").textContent, /正在分析/, "状态标题说明 AI 正在工作");
assert.equal(aiInput.hidden, true, "分析期间收起编辑框，保留需求摘要");
assert.equal(findByClass(aiInput, "dv-ai-progress"), null, "分析状态独立于需求卡片，不挤在卡片底边");
assert.match(findByClass(aiProgress, "dv-ai-wait-value").textContent, /^\d+\.\d$/, "显示真实已等待时间而非虚假百分比");
assert.equal(findButton(workbench.element, "AI 分析中…").disabled, true, "分析中不得重复提交");
assert.equal(controlByLabel(workbench.element, "需求描述 *").disabled, true, "分析中输入应禁用");
resolveCreate();
await analyzing;
await sleep(1800);
await flush();
assert.equal(getCalls, 1, "分析任务必须通过真实 poll 取回结果");
assert.equal(aiProgress.hidden, true, "分析完成后进度提示收起");
// 分析成功后：描述折叠、配置区出现、AI 结果回填。
assert.equal(aiInput.hidden, true, "分析成功后需求描述折叠");
assert.equal(aiCollapsed.hidden, false, "折叠摘要出现");
assert.equal(workConfig.hidden, false, "分析成功后配置区出现");
assert.equal(workTesting.hidden, false, "分析完成后直接显示测试用例，无需保存");
assert.equal(controlByLabel(workbench.element, "业务主键 *"), null);
assert.match(findByClass(workbench.element, "dv-ai-conclusion").textContent, /到期日小于/);
assert.match(findByClass(workbench.element, "dv-ai-sql-code").children[0].textContent, /compiled_preview_sql/);
assert.equal(saveCalls, 0);
await findButton(workbench.element, "运行测试").dispatch("click");
assert.equal(previewTestCalls, 1); assert.equal(saveCalls, 0); assert.equal(testCalls, 0);
assert.equal(findButton(workbench.element, "保存并启用").disabled, false);
const expectedSelect = findByClass(workbench.element, "dv-case-expected");
expectedSelect.value = "1"; await expectedSelect.dispatch("change");
assert.equal(findButton(workbench.element, "保存并启用").disabled, true, "修改用例预期使旧结果失效");
await findButton(workbench.element, "运行测试").dispatch("click");
assert.equal(findButton(workbench.element, "保存并启用").disabled, true, "有失败用例不能启用");
// 点「修改」展开描述，改完后重新分析。
await findButton(workbench.element, "修改需求").dispatch("click");
assert.equal(aiInput.hidden, false, "点修改后描述重新展开");
controlByLabel(workbench.element, "需求描述 *").value = "到期日不得晚于发放日";
await controlByLabel(workbench.element, "需求描述 *").dispatch("input");
await findButton(workbench.element, "重新分析 →").dispatch("click");
await flush();
assert.equal(createCalls, 2, "修改描述后可重新使用 AI 分析");
assert.equal(aiInput.hidden, true, "重新分析成功后再次折叠");
// 不保存草稿即可检查、运行新需求的用例；最终保存启用才持久化并重验真实版本。
assert.equal(findButton(workbench.element, "保存并启用").disabled, true, "新需求不能沿用旧测试结果");
assert.equal(saveCalls, 0);
await findButton(workbench.element, "运行测试").dispatch("click");
assert.equal(findButton(workbench.element, "保存并启用").disabled, false);
assert.equal(saveCalls, 0); assert.equal(testCalls, 0);
await findButton(workbench.element, "保存并启用").dispatch("click");
await flush();
assert.equal(saveCalls, 1);
assert.equal(savedDefinition.generation_mode, "ai");
assert.equal(savedDefinition.name, "贷款期限合理性校验", "规则名称由 AI 自动生成");
assert.equal(savedDefinition.table_name, "loan", "目标表由 AI 自动选定");
assert.equal(savedDefinition.report_category, "pbc_central", "监管报送分类由 AI 自动选定");
assert.equal(savedDefinition.source_id, "src");
assert.equal(savedDefinition.mapping_version, "map-real");
assert.equal(previewTestCalls, 3, "所有预览测试都在保存前完成");
assert.equal(confirmCalls, 1);
assert.equal(testCalls, 1, "保存并启用时必须对真实保存版本重新验证，而非信任预览结果");
assert.deepEqual(confirmPayload, { id: 41, version_no: 1, expected_hash: "real-hash" });
assert.equal(workClosed, 1);
assert.equal(workDialogHost.children.length, 0);
assert.ok(changedCount >= 1);
workRuntime.destroy();

// AI 分析失败时提供转手工入口，保留用户有效输入（单页流程）。
const switchRuntime = createRuntime({ notify: () => {} });
switchRuntime.activate();
const switchState = createState();
switchState.sourcesStatus = "success";
switchState.sources = [{ id: "src", name: "真实数据源", dialect: "mysql" }];
switchState.categoriesStatus = "success";
switchState.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
switchState.modelsStatus = "success";
switchState.models = [{ id: "model-1", name: "内网模型", model_name: "validation-model", is_default: true }];
const switchDialogHost = new FakeElement("div");
const switchApi = {
  describe: async () => ({ mapping_version: "map-switch", columns: realColumns }),
  createAnalysis: async () => { throw new Error("模型不可用"); },
};
const switchWorkbench = createWorkbench({
  state: switchState, runtime: switchRuntime, api: switchApi, listen: switchRuntime.listen,
  user: { id: "1", role: "user", capabilities: ["dv.manage", "dv.ai_use"] },
  notify: () => {}, host: switchDialogHost,
  onClose: () => {}, onChanged: async () => {},
  confirmAction: async () => true,
  onRetrySources: () => {}, onRetryModels: () => {},
});
await switchWorkbench.open({ mode: "ai" });
controlByLabel(switchWorkbench.element, "数据源 *").value = "src";
await controlByLabel(switchWorkbench.element, "数据源 *").dispatch("change");
controlByLabel(switchWorkbench.element, "需求描述 *").value = "到期日不得早于发放日";
await controlByLabel(switchWorkbench.element, "需求描述 *").dispatch("input");
assert.equal(findButton(switchWorkbench.element, "转手工继续").hidden, true, "分析未失败时不显示转手工入口");
await findButton(switchWorkbench.element, "✦ AI 分析").dispatch("click").catch(() => {});
await flush();
assert.equal(findButton(switchWorkbench.element, "转手工继续").hidden, false, "分析失败后必须提供转手工入口");
// 失败提示必须出现在输入区，而不是藏在隐藏的配置区里。
const switchProgress = findByClass(switchWorkbench.element, "dv-ai-progress");
assert.equal(switchProgress.hidden, false, "分析失败时输入区必须显示错误提示");
assert.match(findByClass(switchProgress, "dv-ai-progress-text").textContent, /模型不可用/, "失败原因必须可见");
await findButton(switchWorkbench.element, "转手工继续").dispatch("click");
await flush();
assert.equal(findButton(switchWorkbench.element, "✦ AI 分析"), null, "转手工后不得再渲染 AI 分析控件");
assert.equal(controlByLabel(switchWorkbench.element, "规则说明").value, "到期日不得早于发放日", "转手工保留已填需求描述");
assert.equal(controlByLabel(switchWorkbench.element, "数据源 *").value, "src", "转手工保留已选数据源");
switchRuntime.destroy();

// 修改记录真实分页、展开三列对照及返回原页不丢失展开状态。
const historyRuntime = createRuntime({ notify: () => {} });
historyRuntime.activate();
const historyRequests = [];
const historyApi = {
  ruleHistory: async (ruleId, query) => {
    historyRequests.push({ ruleId, ...query });
    if (query.page === 2) return {
      items: [{ id: 2, action_code: "confirm", version_no: 2, operator_user_id: "1", operator_name: "校验员", created_at: "2026-11-02T01:00:00", summary: "确认启用记录", changes: [], before_status: "draft", after_status: "enabled" }],
      total: 25, page: 2, page_size: 20,
    };
    return {
      items: [{
        id: 1, action_code: "update", version_no: 2, operator_user_id: "1", operator_name: "校验员",
        created_at: "2026-11-01T01:00:00", summary: "修改期限口径",
        changes: [{ field: "expression", label: "比较条件", before: { text: "<旧口径>" }, after: { text: "新口径" } }],
        before_status: "draft", after_status: "draft",
      }],
      total: 25, page: 1, page_size: 20,
    };
  },
};
const historyDialog = openHistoryDialog({
  runtime: historyRuntime, api: historyApi, host: new FakeElement("div"),
  rule: { id: 8, rule_code: "DV000008", name: "期限规则" }, notify: () => {}, onClose: () => {},
});
await flush();
await flush();
assert.equal(historyRequests[0].page, 1);
assert.equal(historyRequests[0].page_size, 20);
const historyToggle = findButton(historyDialog.element, "展开 ▼");
await findByClass(historyDialog.element, "dv-history-table-wrap").dispatch("click", { target: historyToggle });
const diff = findByClass(historyDialog.element, "dv-audit-diff-grid");
assert.deepEqual(diff.children.slice(0, 3).map((cell) => cell.textContent), ["变更项", "修改前", "修改后"]);
assert.match(diff.children[4].textContent, /<旧口径>/);
assert.equal(formatHistoryValue({ a: 1 }), '{\n  "a": 1\n}');
await findButton(historyDialog.element, "下一页").dispatch("click");
assert.equal(historyRequests.at(-1).page, 2);
assert.equal(findByClass(historyDialog.element, "dv-audit-summary").textContent, "确认启用记录");
await findButton(historyDialog.element, "上一页").dispatch("click");
assert.equal(historyRequests.at(-1).page, 1);
assert.ok(findButton(historyDialog.element, "收起 ▲"), "返回原页后保留真实记录展开状态");
assert.ok(findByClass(historyDialog.element, "dv-audit-diff-grid"));
historyDialog.close();
historyApi.ruleHistory = async () => ({ items: [], total: 0, page: 1, page_size: 20 });
const emptyHistory = openHistoryDialog({
  runtime: historyRuntime, api: historyApi, host: new FakeElement("div"),
  rule: { id: 9, rule_code: "DV000009", name: "空记录" }, notify: () => {}, onClose: () => {},
});
await flush();
assert.equal(findByClass(emptyHistory.element, "dv-empty").children[0].textContent, "暂无数据");
emptyHistory.close();
historyApi.ruleHistory = async () => { throw new Error("历史服务不可用"); };
const failedHistory = openHistoryDialog({
  runtime: historyRuntime, api: historyApi, host: new FakeElement("div"),
  rule: { id: 10, rule_code: "DV000010", name: "失败记录" }, notify: () => {}, onClose: () => {},
});
await flush();
assert.equal(findByClass(failedHistory.element, "dv-empty").children[0].textContent, "修改记录加载失败");
failedHistory.close();
historyRuntime.destroy();

// 运行任务轮询可停止，任务切换时慢异常响应不得覆盖新任务。
const resultRuntime = createRuntime({ notify: () => {} });
resultRuntime.activate();
const resultState = createState();
resultState.activeTab = "results";
let resolveFirstIssue;
const resultApi = {
  tasks: async () => [
    { id: 1, run_no: 1, creator_user_id: "1", report_period: resultState.reportPeriod, status: "completed", created_at: "2026-11-01T01:00:00", truncated: 0 },
    { id: 2, run_no: 2, creator_user_id: "1", report_period: resultState.reportPeriod, status: "completed", created_at: "2026-11-01T02:00:00", truncated: 0 },
  ],
  issues: async (taskId) => {
    if (taskId === 1) return new Promise((resolve) => { resolveFirstIssue = resolve; });
    return { task_id: 2, items: [{ id: 22, rule_id: 2, version_no: 1, business_key: "second", message: "新任务", created_at: "2026-11-01" }], total: 1, page: 1, page_size: 50 };
  },
};
const resultPage = createResultsPage({
  state: resultState, runtime: resultRuntime, api: resultApi, listen: resultRuntime.listen,
  user: ordinary, notify: () => {}, confirmAction: async () => true, host: new FakeElement("div"),
  onNewTask: () => {}, onPeriodChange: () => {}, onRender: () => {},
});
resultState.tasks = await resultApi.tasks();
const firstSelection = resultPage.selectTask(1);
await flush();
const secondSelection = resultPage.selectTask(2);
await secondSelection;
resolveFirstIssue({ task_id: 1, items: [{ id: 11, business_key: "stale" }], total: 1, page: 1, page_size: 50 });
await firstSelection;
assert.equal(resultState.activeTaskId, 2);
assert.equal(resultState.issues.task_id, 2);
assert.equal(resultState.issues.items[0].business_key, "second");
resultApi.tasks = async () => [{ id: 3, run_no: 1, creator_user_id: "1", report_period: resultState.reportPeriod, status: "running", created_at: "2026-11-01", truncated: 0 }];
resultApi.issues = async () => ({ task_id: 3, items: [], total: 0, page: 1, page_size: 50 });
await resultPage.loadTasks();
assert.equal(resultRuntime.snapshot().timers, 1, "运行任务在结果页应安排轮询");
resultState.activeTab = "rules";
resultPage.stopPolling();
assert.equal(resultRuntime.snapshot().timers, 0);
assert.equal(resultRuntime.snapshot().controllers, 0);
resultRuntime.destroy();

// 完整挂载/激活/停用/卸载；迟到的列表响应在 page=null 后不得回写。
function lifecycleContext(root, rulesHandler) {
  const messages = [];
  const context = {
    root,
    user: () => ({ id: "1", role: "admin", capabilities: [] }),
    notify: (message, type) => messages.push({ message, type }),
    confirm: async () => true,
    api: async (path, options) => {
      if (path === "/api/modules/data-validation/rules/stats") return { data: { total: 0, enabled: 0, disabled: 0, draft: 0 } };
      if (path.startsWith("/api/modules/data-validation/rules?")) return rulesHandler(path, options);
      if (path === "/api/modules/data-validation/sources") return { data: [] };
      if (path === "/api/modules/data-validation/report-categories") return { data: [] };
      if (path === "/api/modules/data-validation/models") return { data: [] };
      if (path.startsWith("/api/modules/data-validation/tasks")) return { data: [] };
      throw new Error(`未预期的测试请求：${path}`);
    },
  };
  return { context, messages };
}
const root = new FakeElement("section");
const first = lifecycleContext(root, async (_path, _options) => ({ data: { items: [], total: 0, page: 1, page_size: 50 } }));
mount(first.context);
await activate();
assert.equal(root.children.length, 1);
deactivate();
unmount();
assert.equal(root.children.length, 0);

let resolveLateRules;
let lateSignal;
const lateRoot = new FakeElement("section");
const late = lifecycleContext(lateRoot, (_path, options) => {
  lateSignal = options.signal;
  return new Promise((resolve) => { resolveLateRules = resolve; });
});
mount(late.context);
const activation = activate();
await flush();
unmount();
assert.equal(lateSignal.aborted, true);
resolveLateRules({ data: { items: [{ id: 99, name: "不应回写" }], total: 1, page: 1, page_size: 50 } });
await activation;
assert.equal(lateRoot.children.length, 0);
assert.equal(late.messages.some((item) => item.type === "error"), false);

console.log(JSON.stringify({ ok: true, assertions: "state/runtime/dom/api/lifecycle" }));
