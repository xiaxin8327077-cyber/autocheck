import assert from "node:assert/strict";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createWorkbench } from "./pages/workbench.mjs";

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
    this.value = "";
    this.type = "";
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
  setAttribute(name, value) { this.attributes.set(String(name), String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  append(...nodes) {
    nodes.flat(Infinity).forEach((child) => {
      if (child === null || child === undefined || child === false) return;
      const value = typeof child === "string" ? new FakeText(child) : child;
      value.parentNode = this;
      this.children.push(value);
    });
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    this.parentNode = null;
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
  focus() { globalThis.document.activeElement = this; }
  click() { return this.disabled ? undefined : this.dispatch("click"); }
}

globalThis.document = {
  activeElement: null,
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_namespace, tag) => new FakeElement(tag),
  createTextNode: (text) => new FakeText(text),
};

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

function collectText(node) {
  if (!node) return "";
  if (node.children && node.children.length) return node.children.map(collectText).join("");
  return node.textContent || "";
}

function findButton(root, label) {
  if (root.tagName === "BUTTON" && (root.getAttribute?.("aria-label") === label || root.textContent === label)) return root;
  for (const child of root.children || []) {
    const found = findButton(child, label);
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

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const realNow = performance.now.bind(performance);
let clockOffset = 0;
Object.defineProperty(performance, "now", { value: () => realNow() + clockOffset });

const baseColumns = [
  { column_name: "c_projcode", comment: "项目编号", data_type: "varchar" },
  { column_name: "f_endp_amt", comment: "实收信托", data_type: "numeric" },
  { column_name: "d_cldate", comment: "数据日期", data_type: "date" },
];
const candidate = {
  rule_name: "存续项目实收信托提醒",
  rule_type: "field_compare",
  table_name: "reg_pub_project_info",
  source_id: "src",
  dialect: "postgresql",
  report_category: "pbc_central",
  report_category_name: "人行大集中报送",
  columns: baseColumns,
  related_columns: [],
  mapping_version: "doc-v1-abc",
  business_key: "c_projcode",
  report_date_field: "d_cldate",
  expression: { left: "f_endp_amt", op: "eq", right_type: "value", right: 0 },
  violation_message: "存续项目实收信托异常，请人工核实",
  null_policy: "skip",
  equality_policy: "allow_equal",
  scope_description: "所选项目数据",
  uncertainties: [],
  unsupported_requirements: [],
  duplicate: { kind: "none", rule_code: "", evidence: "" },
  sql_status: "candidate",
  verification_status: "not_run",
  preview: {
    definition: {}, content_sha256: "hash", sql_preview: "SELECT 1", sql_params: {},
    cases: [{ name: "正常", row: { f_endp_amt: 1 }, expected_count: 0, actual_count: null, status: "not_run" }],
    persisted: false,
  },
};

const state = createState();
state.sourcesStatus = "success";
state.sources = [{ id: "src", name: "监管报表", dialect: "postgresql" }];
state.categoriesStatus = "success";
state.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
state.modelsStatus = "success";
state.models = [{ id: "model-1", name: "内网模型", model_name: "validation-model", is_default: true }];

const snapshots = [];
let createCalls = 0;
let getCalls = 0;
let cancelCalls = 0;
let expectedReasoning = false;
const api = {
  createAnalysis: async (payload) => {
    createCalls += 1;
    assert.equal(payload.source_id, "src");
    assert.equal(payload.model_id, "model-1");
    assert.equal(payload.reasoning_enabled, expectedReasoning, "推理开关必须随请求发送");
    assert.equal(payload.await_first_poll, true, "模型只能在页面拿到 ID 后启动");
    assert.equal(payload.table, undefined);
    return {
      analysis_id: "a1", status: "running", elapsed_ms: 0, timeout_ms: 180000,
      steps: [{ id: "semantics", status: "running", detail: "理解需求" }],
    };
  },
  getAnalysis: async (id) => {
    getCalls += 1;
    assert.equal(id, "a1");
    assert.ok(snapshots.length, "没有已排队的服务端 snapshot");
    return snapshots.shift();
  },
  cancelAnalysis: async (id) => {
    cancelCalls += 1;
    assert.equal(id, "a1");
    if (cancelCalls === 1) throw new Error("连接中断");
    return { status: "cancelling" };
  },
  describe: async () => ({ mapping_version: "map", columns: baseColumns }),
  preview: async (payload) => ({ definition: payload.definition, content_sha256: "hash", sql_preview: "SELECT 1", sql_params: {}, cases: [], persisted: false }),
  testCandidate: async () => ({ cases: [], passed_count: 0, failed_count: 0, not_run_count: 0, content_sha256: "hash", persisted: false }),
  save: async () => ({ id: 1 }),
  rule: async () => ({ id: 1, definition: candidate }),
};

const runtime = createRuntime({ notify: () => {} });
runtime.activate();
const host = new FakeElement("div");
const workbench = createWorkbench({
  state, runtime, api, listen: runtime.listen,
  user: { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] },
  notify: () => {}, host, onClose: () => {}, onChanged: async () => {},
  confirmAction: async () => true, onRetrySources: () => {}, onRetryModels: () => {},
});
await workbench.open({ mode: "ai" });

const request = controlByLabel(workbench.element, "需求描述 *");
request.value = "存续项目实收信托一般不为0";
await request.dispatch("input");
const source = controlByLabel(workbench.element, "数据源 *");
source.value = "src";
await source.dispatch("change");
const model = controlByLabel(workbench.element, "启用模型");
model.value = "model-1";
await model.dispatch("change");
const reasoningSwitch = findByClass(workbench.element, "dv-ai-reasoning-switch");
assert.equal(reasoningSwitch.getAttribute("role"), "switch");
assert.equal(reasoningSwitch.getAttribute("aria-checked"), "false", "新建默认关闭推理");
await findButton(workbench.element, "✦ AI 分析").dispatch("click");
await sleep(30);

assert.equal(createCalls, 1);
assert.equal(reasoningSwitch.disabled, true, "分析中不能切换推理模式");
await reasoningSwitch.dispatch("click");
assert.equal(reasoningSwitch.getAttribute("aria-checked"), "false");
const progress = findByClass(workbench.element, "dv-ai-progress");
assert.equal(progress.hidden, false, "等待区必须可见");
assert.equal(collectByClass(workbench.element, "dv-ai-step").length, 0, "方案 A 不再显示三步清单");
assert.ok(workbench.element.classList.contains("is-ai-waiting"));
const readonlyRequest = findByClass(workbench.element, "dv-ai-wait-request");
assert.equal(readonlyRequest.hidden, false);
assert.match(collectText(readonlyRequest), /监管报表.*内网模型.*READ-ONLY.*存续项目实收信托一般不为0/);
assert.doesNotMatch(collectText(readonlyRequest), /validation-model/);
assert.equal(findByClass(workbench.element, "dv-ai-request-meta").hidden, true, "等待中不显示下拉控件");
const liveStage = findByClass(progress, "dv-ai-wait-stage");
assert.match(liveStage.textContent, /解析业务语义与逻辑/);
assert.doesNotMatch(liveStage.textContent, /reg_pub_project_info|字段/, "未返回前不得展示表名/字段数");
const track = findByClass(progress, "dv-ai-wait-track");
assert.equal(track.getAttribute("role"), "progressbar");
assert.equal(track.getAttribute("aria-valuenow"), undefined, "不定进度不能报告百分比");
assert.doesNotMatch(collectText(progress), /%/, "不得出现百分比假进度");
const timer = findByClass(progress, "dv-ai-wait-timer");
const initialTime = collectText(timer);
assert.match(initialTime, /^已等待 \d+\.\d 秒$/);
await sleep(260);
assert.notEqual(collectText(timer), initialTime);
assert.equal(findByClass(progress, "dv-ai-wait-track"), track, "计时不重建进度线");
assert.match(liveStage.textContent, /解析业务语义与逻辑/, "时间流逝不推进后端阶段");
assert.equal(findButton(workbench.element, "结束会话").hidden, false, "固定 footer 结束会话必须可见");
const continueWaiting = findButton(workbench.element, "继续等待");
clockOffset = 59000;
await sleep(110);
assert.equal(continueWaiting.hidden, true);
clockOffset = 60000;
await sleep(110);
assert.equal(continueWaiting.hidden, false);
assert.match(collectText(progress), /耗时较长.*180 秒/);
await findByClass(host, "dv-overlay").dispatch("click");
assert.equal(workbench.isOpen(), true, "等待中点击遮罩也不能关闭弹窗");
assert.equal(cancelCalls, 0);
await continueWaiting.click();
assert.equal(continueWaiting.hidden, true);
assert.equal(createCalls, 1, "继续等待不得重新提交");
assert.equal(findByClass(progress, "dv-ai-wait-track"), track);
assert.match(collectText(progress), /耗时较长.*180 秒/);

// 真实 snapshot 推进：step1/2 完成，step3 running，展示真实表名/字段数。
snapshots.push({
  analysis_id: "a1", status: "running", elapsed_ms: 80000, timeout_ms: 180000,
  activity: { phase: "model_wait", detail: "等待模型返回（复核文档中的备选口径）", round_number: 2, elapsed_ms: 70000 },
  steps: [
    { id: "semantics", status: "completed", detail: "已匹配目标表" },
    { id: "metadata", status: "completed", detail: "已检索字典与字段说明" },
    { id: "generation", status: "running", detail: "正在生成规则", table_name: "reg_pub_project_info", field_count: 12 },
  ],
});
await sleep(1100);
assert.match(liveStage.textContent, /核对校验规则与待确认口径.*reg_pub_project_info.*字段 12/);
assert.match(liveStage.textContent, /第 2 轮.*等待模型返回.*70\.0 秒/);
assert.doesNotMatch(liveStage.textContent, /内网模型/);
assert.equal(findByClass(progress, "dv-ai-wait-track"), track, "阶段更新也不重建等待布局");

// 完成：结果进入既有候选流程，等待区隐藏。
snapshots.push({
  analysis_id: "a1", status: "completed", elapsed_ms: 1200,
  steps: [
    { id: "semantics", status: "completed", table_name: "reg_pub_project_info", field_count: 12 },
    { id: "metadata", status: "completed" },
    { id: "generation", status: "completed" },
  ],
  result: candidate,
});
await sleep(1100);
assert.equal(findByClass(workbench.element, "dv-ai-progress").hidden, true, "结果返回后等待区必须隐藏");
assert.equal(readonlyRequest.hidden, true);
assert.equal(findByClass(workbench.element, "dv-ai-request-meta").hidden, false);
assert.ok(!workbench.element.classList.contains("is-ai-waiting"));
assert.equal(findByClass(workbench.element, "dv-config-section").hidden, false, "结果必须进入既有候选流程");
assert.equal(createCalls, 1, "不得重调 parse/创建分析");

// 结束：失败可重试、后台退出才显示结束，旧 GET 返回的候选不能覆盖结束过程。
await findButton(workbench.element, "修改需求").dispatch("click");
assert.equal(reasoningSwitch.disabled, false);
await reasoningSwitch.dispatch("click");
assert.equal(reasoningSwitch.getAttribute("aria-checked"), "true");
expectedReasoning = true;
const request2 = controlByLabel(workbench.element, "需求描述 *");
request2.value = "另一个需求";
await request2.dispatch("input");
await findButton(workbench.element, "应用修改 →").dispatch("click");
await sleep(30);
assert.equal(createCalls, 2);
let finishOldGet;
snapshots.push(new Promise((resolve) => { finishOldGet = resolve; }));
await sleep(1000);
await findButton(workbench.element, "结束会话").click();
assert.equal(cancelCalls, 1);
assert.match(collectText(progress), /未能确认会话已结束/);
assert.equal(findButton(workbench.element, "重试结束会话").disabled, false);
await findButton(workbench.element, "重试结束会话").click();
assert.equal(cancelCalls, 2);
assert.equal(findButton(workbench.element, "正在结束…").disabled, true);
assert.match(collectText(progress), /正在结束会话/);
finishOldGet({ status: "completed", result: candidate });
await sleep(10);
assert.equal(findByClass(workbench.element, "dv-config-section").hidden, true);
assert.equal(readonlyRequest.hidden, false);
snapshots.push({ status: "cancelled" });
await sleep(1100);
assert.match(collectText(progress), /本次分析会话已结束/);
const getCallsAfterEnd = getCalls;
await sleep(950);
assert.equal(getCalls, getCallsAfterEnd, "确认终止后不得继续 poll");
assert.equal(findByClass(workbench.element, "dv-config-section").hidden, true, "迟到响应不得覆盖已取消状态");

// 二次分析必须恢复只读等待态且不残留上一轮的阶段详情。
await findButton(workbench.element, "修改需求").dispatch("click");
const request3 = controlByLabel(workbench.element, "需求描述 *");
request3.value = "第二次需求";
await request3.dispatch("input");
await findButton(workbench.element, "✦ AI 分析").dispatch("click");
await sleep(30);
assert.equal(readonlyRequest.hidden, false);
assert.match(collectText(readonlyRequest), /第二次需求/);
assert.match(liveStage.textContent, /解析业务语义与逻辑/);
assert.doesNotMatch(liveStage.textContent, /reg_pub_project_info|字段/, "不得残留上次快照");
snapshots.push({ status: "failed", elapsed_ms: 180000, timeout_ms: 180000,
  error: { code: "ANALYSIS_TIMEOUT", reference: "123456abcdef" } });
await sleep(1100);
assert.match(collectText(progress), /分析总时限.*180 秒/);
assert.match(collectText(progress), /错误编号 123456abcdef/);
assert.doesNotMatch(collectText(progress), /会话已结束/);

await findButton(workbench.element, "✦ AI 分析").dispatch("click");
await sleep(1100);
assert.match(collectText(progress), /进度连接中断.*上次收到的后台状态/);
clockOffset += 181000;
await sleep(1100);
assert.match(collectText(progress), /进度连接中断.*无法确认后台结果/);
const offlinePollCount = getCalls;
await sleep(950);
assert.equal(getCalls, offlinePollCount);

// POST 未返回时取消：迟到 create 返回的 id 必须尽力 DELETE，且不覆盖已取消状态。
let pendingCreate = null;
const api2Cancels = [];
const api2 = {
  createAnalysis: () => new Promise((resolve) => { pendingCreate = resolve; }),
  getAnalysis: async () => { throw new Error("取消后不得 poll"); },
  cancelAnalysis: async (id) => { api2Cancels.push(id); return { status: "cancelled" }; },
  describe: async () => ({ mapping_version: "map", columns: baseColumns }),
  preview: async () => ({}),
};
const runtime2 = createRuntime({ notify: () => {} });
runtime2.activate();
const wb2 = createWorkbench({
  state, runtime: runtime2, api: api2, listen: runtime2.listen,
  user: { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] },
  notify: () => {}, host: new FakeElement("div"), onClose: () => {}, onChanged: async () => {},
  confirmAction: async () => true, onRetrySources: () => {}, onRetryModels: () => {},
});
await wb2.open({ mode: "ai" });
const req2 = controlByLabel(wb2.element, "需求描述 *");
req2.value = "待取消需求";
await req2.dispatch("input");
await controlByLabel(wb2.element, "数据源 *").dispatch("change");
await controlByLabel(wb2.element, "启用模型").dispatch("change");
findButton(wb2.element, "✦ AI 分析").dispatch("click");
await sleep(20);
assert.ok(pendingCreate, "createAnalysis 应处于 pending");
await findButton(wb2.element, "结束会话").dispatch("click");
assert.match(collectText(findByClass(wb2.element, "dv-ai-progress")), /正在结束会话/);
assert.equal(findButton(wb2.element, "正在结束…").disabled, true);
pendingCreate({ analysis_id: "a2", status: "running", elapsed_ms: 0, steps: [{ id: "semantics", status: "running" }] });
await sleep(30);
assert.deepEqual(api2Cancels, ["a2"], "迟到 create 的 id 必须尽力 DELETE");
assert.match(collectText(findByClass(wb2.element, "dv-ai-progress")), /本次分析会话已结束/);
assert.equal(findByClass(wb2.element, "dv-config-section").hidden, true, "迟到 create 不得覆盖已取消状态");
runtime2.destroy();

// 关闭弹窗：有 id 时发送尽力 DELETE；之后 poll 不得应用结果。
const api3Cancels = [];
const api3 = {
  createAnalysis: async () => ({ analysis_id: "a3", status: "running", elapsed_ms: 0, steps: [{ id: "semantics", status: "running" }] }),
  getAnalysis: async () => { throw new Error("关闭后不得 poll"); },
  cancelAnalysis: async (id) => { api3Cancels.push(id); },
  describe: async () => ({ mapping_version: "map", columns: baseColumns }),
  preview: async () => ({}),
};
const runtime3 = createRuntime({ notify: () => {} });
runtime3.activate();
const wb3 = createWorkbench({
  state, runtime: runtime3, api: api3, listen: runtime3.listen,
  user: { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] },
  notify: () => {}, host: new FakeElement("div"), onClose: () => {}, onChanged: async () => {},
  confirmAction: async () => true, onRetrySources: () => {}, onRetryModels: () => {},
});
await wb3.open({ mode: "ai" });
const req3 = controlByLabel(wb3.element, "需求描述 *");
req3.value = "关闭取消需求";
await req3.dispatch("input");
await controlByLabel(wb3.element, "数据源 *").dispatch("change");
await controlByLabel(wb3.element, "启用模型").dispatch("change");
await findButton(wb3.element, "✦ AI 分析").dispatch("click");
await sleep(30);
wb3.close();
assert.deepEqual(api3Cancels, ["a3"], "关闭时有 id 必须尽力 DELETE");
await sleep(1000);
assert.equal(wb3.isOpen(), false, "关闭后不得再应用迟到响应");
runtime3.destroy();
runtime.destroy();

console.log(JSON.stringify({ ok: true, assertions: "waiting/steps/poll/cancel/late-response/reset/post-pending/close" }));
