import assert from "node:assert/strict";
import { confirmationReadiness, createState } from "./state.mjs";
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
      if (value.parentNode) value.parentNode.children = value.parentNode.children.filter((item) => item !== value);
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
    payload.stopPropagation = () => { payload.__stopped = true; };
    let result;
    for (const handler of [...(this.listeners.get(type) || [])]) result = await handler(payload);
    if (!payload.__stopped && this.parentNode) result = await this.parentNode.dispatch(type, payload);
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
  if (root.tagName === "BUTTON" && root.textContent === label) return root;
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

function makeCandidate(name, table, field, comment, left, right, op, caseName) {
  const columns = [
    { column_name: "project_code", comment: "项目编号", data_type: "varchar" },
    { column_name: field, comment, data_type: "numeric" },
    { column_name: "f_balan_endp_amt", comment: "余额金额", data_type: "numeric" },
    { column_name: "report_date", comment: "报送日期", data_type: "date" },
  ];
  const candidate = {
    rule_name: name, rule_type: "field_compare", table_name: table, source_id: "src", dialect: "mysql",
    report_category: "pbc_central", columns, related_columns: [], mapping_version: "map-multi",
    business_key: "project_code", report_date_field: "report_date",
    expression: { left, op: "eq", right_type: "value", right: 0 }, violation_message: `${name}异常`, null_policy: "skip", equality_policy: "allow_equal",
    scope_description: "所选项目数据", uncertainties: [], unsupported_requirements: [],
    duplicate: { kind: "none", rule_code: "", evidence: "" }, sql_status: "candidate", verification_status: "not_run",
    preview: {
      definition: {}, content_sha256: `hash-${name}`, sql_preview: `SELECT ${field}`, sql_params: {},
      cases: [{ name: caseName, row: { [field]: 0 }, expected_count: 0, actual_count: null, status: "not_run" }],
      persisted: false,
    },
  };
  const { preview: _preview, columns: _columns, related_columns: _related, ...canonical } = candidate;
  candidate.preview.definition = {
    ...canonical, name: candidate.rule_name, generation_mode: "ai", description: "多候选测试",
    project_context: {
      mode: "base", code_field: "project_code", name_field: "project_name", table_name: table,
      key: "project_code", date_field: "report_date", unique_evidence: "主键", confirmed: true,
    },
  };
  return candidate;
}

const candidateA = makeCandidate("项目粒度方案", "reg_pub_project_info", "f_endp_amt", "实收信托", "f_endp_amt", "report_date", "lt", "项目样本");
candidateA.expression = { left: "f_endp_amt", op: "eq", right: "f_balan_endp_amt", right_type: "field" };
candidateA.null_policy = "zero";
candidateA.preview.definition.expression = candidateA.expression;
candidateA.preview.definition.null_policy = "zero";
candidateA.preview.cases.push({ name: "NULL按0", row: { f_endp_amt: null, f_balan_endp_amt: 0 }, expected_count: 0, actual_count: null, status: "not_run" });
const candidateB = makeCandidate("合同粒度方案", "reg_pub_contract", "f_contract_amt", "合同金额", "f_contract_amt", "report_date", "lt", "合同样本");
candidateB.null_policy = "zero";
candidateB.preview.definition.null_policy = "zero";
candidateB.preview.cases.push({ name: "NULL按0常量", row: { f_contract_amt: null }, expected_count: 0, actual_count: null, status: "not_run" });
const options = [
  {
    id: "opt-a", label: "项目粒度方案", recommended: true, grain: "项目", table_label: "reg_pub_project_info",
    field_label: "f_endp_amt", match_reason: "项目表有实收信托字段", differences: ["按项目粒度汇总", "与合同粒度不同"],
    candidate: candidateA,
  },
  {
    id: "opt-b", label: "合同粒度方案", recommended: false, grain: "合同", table_label: "reg_pub_contract",
    field_label: "f_contract_amt", match_reason: "合同表有合同金额字段", differences: ["按合同粒度"],
    candidate: candidateB,
  },
];
const candidateC = makeCandidate("期限方案", "reg_pub_term", "f_term_amt", "期限金额", "f_term_amt", "report_date", "lt", "期限样本");
options.push({
  id: "opt-c", label: "期限方案", recommended: false, grain: "项目", table_label: "reg_pub_term",
  field_label: "f_term_amt", match_reason: "期限表有期限金额字段", differences: ["按项目期限"],
  candidate: candidateC,
});
const result = {
  ...candidateA,
  candidate_options: options,
  ai_suggestions: [
    {
      id: "sug-1", category: "consistency", title: "日期口径一致性", reason: "两表日期字段含义需核实",
      references: [{ table_name: "reg_pub_project_info", field_name: "d_cldate" }],
      preconditions: ["确认两表按同一业务日期对齐"], support_level: "needs_confirmation",
      limitations: ["未读取业务行"], provenance: "model",
    },
    { id: "unrelated-key", kind: "unique", title: "不相关的项目编号唯一性", support_level: "supported",
      references: [{ table_name: "reg_pub_project_info", field_name: "project_code" }] },
    { id: "matching-amount", kind: "two_table_exists", title: "项目实收对应字段一致性", support_level: "supported",
      references: [{ table_name: "reg_pub_project_info", field_name: "f_endp_amt" }] },
    {
      id: "sug-2", category: "consistency", title: "金额单位一致性", reason: "合同金额对应字段可比",
      references: [{ table_name: "reg_pub_contract", field_name: "f_contract_amt" }],
      preconditions: [], support_level: "supported", limitations: [], provenance: "model",
    },
  ],
  comparison_suggestions: [{ title: "日期与粒度口径", description: "日期/币种/粒度口径仍待证实", limitations: ["不能据此自动启用"], supported: false }],
};

const state = createState();
state.sourcesStatus = "success";
state.sources = [{ id: "src", name: "监管报表", dialect: "mysql" }];
state.categoriesStatus = "success";
state.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
state.modelsStatus = "success";
state.models = [{ id: "model-1", name: "内网模型", model_name: "validation-model", is_default: true }];

const batchCalls = [];
const saveCalls = [];
const confirmCalls = [];
const testCalls = [];
const previewTestCalls = [];
let requestKeys = [];
let batchFailOnce = false;
const api = {
  createAnalysis: async () => ({ analysis_id: "a1", status: "completed", elapsed_ms: 0, steps: [], result }),
  getAnalysis: async (id) => ({ analysis_id: id, status: "completed", steps: [], result }),
  cancelAnalysis: async () => {},
  batchSaveCandidates: async (payload) => {
    const transported = JSON.parse(JSON.stringify(payload));
    batchCalls.push(transported);
    requestKeys.push(transported.request_key);
    if (batchFailOnce) {
      batchFailOnce = false;
      throw new Error("首次失败用于验证重试幂等");
    }
    return { count: transported.definitions.length, rules: transported.definitions.map((item, index) => ({ id: 100 + batchCalls.length * 10 + index, rule_code: `DV${batchCalls.length}-${index + 1}`, name: item.name })) };
  },
  save: async (definition) => { saveCalls.push(definition); return { id: 90 + saveCalls.length }; },
  rule: async (id) => ({ id, rule_code: `DV${id}`, name: "已保存方案", creator_user_id: "1", status: "draft", version_no: 1, content_sha256: `hash-${id}`, sql_text: "SELECT 1", definition: {} }),
  test: async (id, payload) => {
    testCalls.push({ id, payload });
    return { passed_count: 1, failed_count: 0, not_run_count: 0, cases: [{ name: "样本", row: {}, expected_count: 0, actual_count: 0, status: "passed" }] };
  },
  confirm: async (id, payload) => { confirmCalls.push({ id, payload }); return { id, status: "enabled" }; },
  preview: async () => candidateA.preview,
  testCandidate: async (payload) => {
    previewTestCalls.push(payload);
    const cases = (payload.cases || []).map((item) => ({ ...item, actual_count: item.expected_count, status: "passed" }));
    return {
      content_sha256: payload.expected_hash, cases,
      passed_count: cases.length, failed_count: 0, not_run_count: 0, persisted: false,
    };
  },
  describe: async () => ({ mapping_version: "map", columns: candidateA.columns }),
};

const runtime = createRuntime({ notify: () => {} });
runtime.activate();
const workbench = createWorkbench({
  state, runtime, api, listen: runtime.listen,
  user: { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] },
  notify: () => {}, host: new FakeElement("div"), onClose: () => {}, onChanged: async () => {},
  confirmAction: async () => true, onRetrySources: () => {}, onRetryModels: () => {},
});
await workbench.open({ mode: "ai" });
const request = controlByLabel(workbench.element, "需求描述 *");
request.value = "多候选需求";
await request.dispatch("input");
await controlByLabel(workbench.element, "数据源 *").dispatch("change");
await controlByLabel(workbench.element, "启用模型").dispatch("change");
await findButton(workbench.element, "✦ AI 分析").dispatch("click");
await sleep(30);

const panel = findByClass(workbench.element, "dv-ai-options");
assert.ok(panel && !panel.hidden, "多候选必须展示方案卡");
assert.match(collectText(panel), /发现多个有依据的校验方案/);
const cards = collectByClass(workbench.element, "dv-ai-option-card");
assert.equal(cards.length, 3);
const panelText = collectText(panel);
assert.match(panelText, /检查粒度：项目/);
assert.doesNotMatch(panelText, /reg_pub_project_info（reg_pub_project_info）/);
assert.doesNotMatch(panelText, /f_endp_amt（f_endp_amt）/);
assert.match(panelText, /真实表：reg_pub_project_info/);
assert.match(panelText, /真实字段：f_endp_amt/);
assert.match(panelText, /推荐理由：项目表有实收信托字段/);
assert.match(panelText, /按项目粒度汇总/);
assert.doesNotMatch(collectText(cards[0]).slice(0, 40), /^reg_pub_project_info$/);
const checks = collectByClass(workbench.element, "dv-ai-option-check");
assert.equal(checks.length, 3);
assert.equal(checks[0].checked, true, "推荐项初选");
assert.equal(checks[1].checked, false);
assert.match(collectText(findByClass(workbench.element, "dv-ai-options-save")), /保存所选 1 条草稿/);

// 建议区：只建议，无创建按钮。
assert.doesNotMatch(collectText(findByClass(workbench.element, "dv-ai-suggestions")), /可进一步检查的一致性/, "新建议存在时旧 comparison 不得重复显示");
const supplements = findByClass(workbench.element, "dv-ai-supplements");
assert.ok(supplements && !supplements.hidden, "AI补充建议区必须独立于手风琴显示");
const supplementText = collectText(supplements);
assert.match(supplementText, /AI补充建议/);
assert.match(supplementText, /项目实收对应字段一致性/);
assert.doesNotMatch(supplementText, /日期口径一致性|需人工确认|项目编号唯一性|金额单位一致性/);
assert.match(supplementText, /可进一步检查/);
assert.equal(findButton(supplements, "保存"), null, "建议区不得出现保存/启用按钮");
assert.equal(findButton(supplements, "创建"), null);
assert.match(collectText(findByClass(workbench.element, "dv-ai-business-facts")), /数值比较：NULL按0处理/);
const nullCase = candidateA.preview.cases.find((item) => item.name === "NULL按0");
assert.ok(nullCase && nullCase.row.f_endp_amt === null && nullCase.expected_count === 0, "数值 NULL 按 0 候选样本必须保留");

// 勾选第二项，计数与 request_key 变化。
const conclusion = () => collectByClass(workbench.element, "dv-ai-conclusion").at(-1).textContent;
checks[1].checked = true;
await checks[1].dispatch("change");
assert.match(collectText(findByClass(workbench.element, "dv-ai-options-save")), /保存所选 2 条草稿/);

// 切换活动卡：载入对应 candidate，保留各自 previewCases。
const actions = collectByClass(workbench.element, "dv-ai-option-actions");
const actionButtons = actions.map((group) => findButton(group, "查看/完善此方案"));
await actionButtons[1].dispatch("click");
const activeCards = collectByClass(workbench.element, "dv-ai-option-card").filter((card) => card.classList.contains("is-active"));
assert.equal(activeCards.length, 1);
assert.match(collectText(activeCards[0]), /合同粒度方案/);
assert.match(conclusion(), /合同金额/);
await actionButtons[0].dispatch("click");
assert.match(conclusion(), /实收信托/);

// 手风琴：展开卡内挂载既有 SQL/问题/测试 DOM，折叠后移回原位；勾选不展开、不触发启用。
const cardsNow = () => collectByClass(workbench.element, "dv-ai-option-card");
const optionIdOf = (card) => card.getAttribute("data-option-id");
const activeCard = () => cardsNow().find((card) => card.classList.contains("is-active"));
const detailSlot = (card) => card.children.find((child) => child.classList.contains("dv-ai-option-detail-slot"));
assert.equal(cardsNow().filter((card) => card.classList.contains("is-selected")).length, 2, "勾选蓝框为已选两项");
assert.ok(activeCard() && detailSlot(activeCard()) && !detailSlot(activeCard()).hidden, "默认展开当前方案");
assert.ok(collectByClass(detailSlot(activeCard()), "dv-ai-sql-code").length >= 1, "展开卡内必须显示该方案 SQL");
assert.ok(collectByClass(detailSlot(activeCard()), "dv-test-panel").length >= 1, "展开卡内必须显示该方案测试");
checks[1].dispatch("click");
assert.equal(cardsNow().filter((card) => card.classList.contains("is-active")).length, 1, "checkbox 不得触发展开/启用");
assert.equal(confirmCalls.length, 0, "整卡展开不得触发启用");
const cardB = cardsNow().find((card) => optionIdOf(card) === "opt-b");
await cardB.dispatch("keydown", { key: "Enter" });
assert.equal(optionIdOf(activeCard()), "opt-b", "键盘 Enter 必须展开方案");
assert.match(conclusion(), /合同金额/);
await activeCard().children[1].dispatch("click");
assert.equal(cardsNow().filter((card) => card.classList.contains("is-active")).length, 0, "再点同一卡必须收起");
assert.ok(collectByClass(findByClass(workbench.element, "dv-ai-result"), "dv-ai-sql-code").length >= 1, "收起后详情移回卡后原位");
assert.equal(confirmCalls.length, 0, "收起不得触发启用");

// 首次失败后，同选择未改口径重试复用 request_key；成功仅 draft。
batchFailOnce = true;
await findButton(workbench.element, "保存所选 2 条草稿").dispatch("click");
await sleep(30);
assert.equal(batchCalls.length, 1, "失败请求已按真实传输序列化记录");
assert.equal(batchCalls[0].definitions.length, 2);
await findButton(workbench.element, "保存所选 2 条草稿").dispatch("click");
await sleep(30);
assert.equal(batchCalls.length, 2);
assert.equal(batchCalls[1].request_key, batchCalls[0].request_key, "同选择未改口径重试必须复用 request_key");
assert.equal(typeof batchCalls[1].request_key, "string");
assert.match(collectText(findByClass(workbench.element, "dv-ai-saved-results")), /DV2-1/);
assert.match(collectText(findByClass(workbench.element, "dv-ai-saved-results")), /DV2-2/);
assert.equal(confirmCalls.length, 0, "批量保存不得自动启用");

// 已成功组合禁止重复创建。
await findButton(workbench.element, "保存所选 2 条草稿").dispatch("click");
await sleep(30);
assert.equal(batchCalls.length, 2, "已保存未改组合不得重复创建");

// 新增选择只创建未保存项并换 key。
checks[2].checked = true;
await checks[2].dispatch("change");
await findButton(workbench.element, "保存所选 3 条草稿").dispatch("click");
await sleep(30);
assert.equal(batchCalls.length, 3);
assert.notEqual(batchCalls[2].request_key, batchCalls[1].request_key, "改选择必须换 request_key");
assert.equal(batchCalls[2].definitions.length, 1, "只创建未保存的第三项");

// 单方案“保存此方案并启用”只处理该方案；未展开时不得模糊启用。
const cardA = cardsNow().find((card) => optionIdOf(card) === "opt-a");
await cardA.children[1].dispatch("click");
assert.equal(optionIdOf(activeCard()), "opt-a", "启用前必须展开当前方案");
const enableButtons = () => collectByClass(workbench.element, "dv-ai-option-actions")
  .map((group) => findButton(group, "保存当前方案并启用") || findButton(group, "完善并启用此方案"));
assert.equal(enableButtons()[0].disabled, true, "未测试通过不得启用");
await findButton(workbench.element, "运行测试").dispatch("click");
await sleep(30);
assert.equal(previewTestCalls.length, 1, "启用前必须先运行该方案测试");
assert.equal(enableButtons()[0].disabled, false, "测试通过后启用解锁");
const savesBefore = saveCalls.length;
await enableButtons()[0].dispatch("click");
await sleep(30);
assert.equal(saveCalls.length, savesBefore, "已保存未改方案启用复用 rule_id，不重复创建");
assert.equal(testCalls.length, 1);
assert.equal(confirmCalls.length, 1, "仅启用所选方案");

runtime.destroy();

// 单候选也显示独立 AI补充建议；为空显示中性说明，不伪造空泛建议。
async function openSingleAi(result) {
  const singleApi = {
    ...api,
    createAnalysis: async () => ({ analysis_id: `a-${Math.random().toString(16).slice(2)}`, status: "completed", elapsed_ms: 0, steps: [], result }),
  };
  const singleRuntime = createRuntime({ notify: () => {} });
  singleRuntime.activate();
  const wb = createWorkbench({
    state, runtime: singleRuntime, api: singleApi, listen: singleRuntime.listen,
    user: { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] },
    notify: () => {}, host: new FakeElement("div"), onClose: () => {}, onChanged: async () => {},
    confirmAction: async () => true, onRetrySources: () => {}, onRetryModels: () => {},
  });
  await wb.open({ mode: "ai" });
  const req = controlByLabel(wb.element, "需求描述 *");
  req.value = "单候选建议需求";
  await req.dispatch("input");
  await controlByLabel(wb.element, "数据源 *").dispatch("change");
  await controlByLabel(wb.element, "启用模型").dispatch("change");
  await findButton(wb.element, "✦ AI 分析").dispatch("click");
  await sleep(30);
  return { wb, runtime: singleRuntime };
}
const singleWithSuggestions = await openSingleAi({
  ...candidateA,
  ai_suggestions: [{ id: "s1", title: "单方案补充", reason: "需核实日期", references: [{ table_name: "reg_pub_project_info", field_name: "d_cldate" }], preconditions: ["确认日期"], support_level: "unsupported", limitations: ["未读取业务行"] }],
});
const singleSupp = findByClass(singleWithSuggestions.wb.element, "dv-ai-supplements");
assert.ok(singleSupp.hidden, "只有不支持建议时整个区域隐藏");
assert.doesNotMatch(collectText(singleSupp), /单方案补充/);
singleWithSuggestions.runtime.destroy();
const singleEmpty = await openSingleAi({ ...candidateA, ai_suggestions: [] });
const emptySupp = findByClass(singleEmpty.wb.element, "dv-ai-supplements");
assert.ok(emptySupp.hidden, "为空时不显示建议区或空占位");
singleEmpty.runtime.destroy();

// zero 门禁反例：字段-字段、字段-有限常量放行；字符串常量/一元/缺右类型拒绝；review 放行。
const readinessFor = (definition) => confirmationReadiness(
  { definition, version_no: 0, content_sha256: "h" },
  { version_no: 0, content_sha256: "h", cases: [{ status: "passed" }], passed_count: 1, failed_count: 0, not_run_count: 0 },
  false,
  true,
);
const zeroBase = { rule_type: "field_compare", null_policy: "zero", equality_policy: "allow_equal" };
assert.equal(readinessFor({ ...zeroBase, expression: { left: "amount", op: "eq", right_type: "field", right: "f_balan" } }).ready, true, "数值字段-字段 zero 放行");
assert.equal(readinessFor({ ...zeroBase, expression: { left: "amount", op: "eq", right_type: "value", right: 0 } }).ready, true, "数值字段-有限常量 zero 放行");
assert.equal(readinessFor({ ...zeroBase, expression: { left: "amount", op: "eq", right_type: "value", right: "0" } }).ready, false, "字符串常量 zero 拒绝");
assert.equal(readinessFor({ ...zeroBase, expression: { left: "amount", op: "eq", right_type: "value", right: null } }).ready, false, "非有限常量 zero 拒绝");
assert.equal(readinessFor({ ...zeroBase, expression: { left: "report_date", op: "is_null" } }).ready, false, "一元 zero 拒绝");
assert.equal(readinessFor({ ...zeroBase, null_policy: "review", expression: { left: "amount", op: "eq", right_type: "value", right: 0 } }).ready, true, "review 缺值单列核查放行");

console.log(JSON.stringify({
  ok: true,
  assertions: "multi/options/selection/switch/batch-save/request-key/enable/suggestions/gates/idempotent",
  batch_payload: batchCalls.filter((call) => call.definitions.length === 2).at(-1),
}));
