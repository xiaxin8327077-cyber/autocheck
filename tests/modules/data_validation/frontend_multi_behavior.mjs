import assert from "node:assert/strict";
import { confirmationReadiness, createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { createCandidateOptionsPanel } from "./components/candidate_options.mjs";

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
const persistedRules = new Map();
function persistRule(id, definition, ruleCode = `DV${id}`) {
  const preview = options.find((option) => option.candidate.rule_name === definition.name)?.candidate.preview;
  const rule = { id, rule_code: ruleCode, name: definition.name, creator_user_id: "1", status: "draft", version_no: 1,
    content_sha256: preview?.content_sha256, sql_text: "SELECT 1", definition };
  persistedRules.set(id, rule);
  return rule;
}
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
    return { count: transported.definitions.length, rules: transported.definitions.map((item, index) =>
      persistRule(100 + batchCalls.length * 10 + index, item, `DV${batchCalls.length}-${index + 1}`)) };
  },
  save: async (definition) => { saveCalls.push(definition); return persistRule(90 + saveCalls.length, definition); },
  rule: async (id) => persistedRules.get(id),
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
assert.match(collectText(panel), /可选校验方案/);
const cards = collectByClass(workbench.element, "dv-ai-option-card");
assert.equal(cards.length, 3);
const panelText = collectText(panel);
const documentScope = "每次清空本表再写入快照。取数配置与 SQL 布尔条件只供查阅。";
const splitPanel = createCandidateOptionsPanel({ listen: runtime.listen });
const splitOptions = ["单位净值", "累计净值"].map((label, i) => {
  const name = ["f_netvalue", "f_totalnetvalue"][i];
  return { id: String(i), fromSelection: true, recommended: true, candidate: {
    table_name: "proj_info_dtl_pboc", table_name_cn: "项目信息（proj_info_dtl_pboc.ktr）", grain: "项目级",
    document_scope: documentScope, columns: [{ column_name: name, comment: label },
      { column_name: "mode", comment: "原始运行方式" }], expression: { left: name, op: "is_null" },
    filters: [{ field: "mode", table: "base", op: "in", value: ["1", "3"] }],
    semantic_intent: { dictionary_snapshots: { base: { mode: [{ value: "1", label: "开放式净值型" }, { value: "3", label: "封闭式净值型" }] } } },
  } };
});
splitPanel.update({ candidate_options: splitOptions });
assert.match(collectText(splitPanel.element), /按已选口径生成的方案/);
for (const [index, card] of collectByClass(splitPanel.element, "dv-ai-option-card").entries()) {
  assert.match(collectText(findByClass(card, "dv-ai-option-title")), index ? /累计净值为空/ : /单位净值为空/);
  assert.equal(collectText(findByClass(card, "dv-ai-option-table")), "检查对象：项目信息 · 项目级");
  assert.equal(collectText(findByClass(card, "dv-ai-option-field")), "适用范围：原始运行方式属于开放式净值型、封闭式净值型");
  assert.equal(findByClass(card, "dv-ai-option-recommended"), null);
  const evidence = findByClass(card, "dv-ai-option-evidence");
  assert.ok(!evidence.open && collectText(evidence).includes(documentScope));
  assert.match(collectText(evidence), /1＝开放式净值型、3＝封闭式净值型/);
}
// Old split candidates sometimes put the entire scope in table_label; only the physical identifier is reliable then.
const oldSplit = { ...splitOptions[0], table_label: documentScope, candidate: {
  ...splitOptions[0].candidate, table_name_cn: "", grain: "", scope_description: documentScope,
} };
splitPanel.update({ candidate_options: [oldSplit] });
assert.equal(collectText(findByClass(splitPanel.element, "dv-ai-option-table")), "检查对象：proj_info_dtl_pboc");
splitPanel.update({ candidate_options: splitOptions.map((option, i) => ({ ...option, candidate: { ...option.candidate,
  table_name: i ? "other_project_table" : option.candidate.table_name, report_category: i ? "other" : "group:pbc",
  report_category_name: i ? "其他报送" : "人行报送",
} })) });
const sources = collectByClass(splitPanel.element, "dv-ai-option-table").map(collectText);
assert.match(sources[0], /项目信息（proj_info_dtl_pboc） · 项目级 · 人行报送/);
assert.match(sources[1], /项目信息（other_project_table） · 项目级 · 其他报送/);
assert.match(panelText, /检查对象：reg_pub_project_info · 项目/);
assert.doesNotMatch(panelText, /reg_pub_project_info（reg_pub_project_info）/);
assert.doesNotMatch(panelText, /f_endp_amt（f_endp_amt）/);
assert.match(collectText(findByClass(cards[0], "dv-ai-option-title")), /项目粒度方案/);
assert.match(collectText(findByClass(cards[0], "dv-ai-option-evidence")), /检查字段：实收信托（f_endp_amt）/);
assert.match(collectText(findByClass(cards[0], "dv-ai-reasoning")), /项目表有实收信托字段/);
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
assert.match(supplementText, /日期口径一致性/);
assert.match(supplementText, /项目编号唯一性/);
assert.match(supplementText, /金额单位一致性/);
assert.match(supplementText, /需先确认口径/);
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

// 卡片只提供查看入口；切换活动卡不能保存、重验或启用。
const actions = collectByClass(workbench.element, "dv-ai-option-actions");
for (const group of actions) {
  assert.deepEqual(group.children.filter((child) => child.tagName === "BUTTON").map(collectText), ["查看此方案"],
    "方案卡右侧只保留查看/完善入口，不得再有单条保存并启用按钮");
  assert.equal(findButton(group, "保存当前方案并启用"), null);
  assert.equal(findButton(group, "完善并启用此方案"), null);
}
const actionButtons = actions.map((group) => findButton(group, "查看此方案"));
assert.ok(actionButtons.every(Boolean), "每张方案卡都保留查看/完善入口");
await actionButtons[1].dispatch("click");
const activeCards = collectByClass(workbench.element, "dv-ai-option-card").filter((card) => card.classList.contains("is-active"));
assert.equal(activeCards.length, 1);
assert.match(collectText(activeCards[0]), /合同粒度方案/);
assert.equal(conclusion(), "合同粒度方案");
await actionButtons[0].dispatch("click");
assert.equal(conclusion(), "项目粒度方案");
assert.equal(batchCalls.length, 0, "查看方案不能创建草稿");
assert.equal(saveCalls.length, 0, "查看方案不能走单条保存接口");
assert.equal(testCalls.length, 0, "查看方案不能重验保存版本");
assert.equal(confirmCalls.length, 0, "查看方案不能启用规则");

// 手风琴展示 SQL 与问题，测试用例统一显示在独立区域。
const cardsNow = () => collectByClass(workbench.element, "dv-ai-option-card");
const optionIdOf = (card) => card.getAttribute("data-option-id");
const activeCard = () => cardsNow().find((card) => card.classList.contains("is-active"));
const detailSlot = (card) => card.children.find((child) => child.classList.contains("dv-ai-option-detail-slot"));
assert.equal(cardsNow().filter((card) => card.classList.contains("is-selected")).length, 2, "勾选蓝框为已选两项");
assert.ok(activeCard() && detailSlot(activeCard()) && !detailSlot(activeCard()).hidden, "默认展开当前方案");
assert.ok(collectByClass(detailSlot(activeCard()), "dv-ai-sql-code").length >= 1, "展开卡内必须显示该方案 SQL");
const testingSection = findByClass(workbench.element, "dv-testing-section");
assert.equal(collectByClass(detailSlot(activeCard()), "dv-test-panel").length, 0, "方案卡不能包含测试用例");
assert.ok(findButton(testingSection, "生成并运行测试用例"));
assert.equal(previewTestCalls.length, 0);
const originalEvidence = findByClass(activeCard(), "dv-ai-option-evidence").children[0];
await originalEvidence.dispatch("click");
assert.equal(optionIdOf(activeCard()), "opt-a", "点击原始证据不能收起方案");
const modelReason = findByClass(detailSlot(activeCard()), "dv-ai-reasoning").children[0];
await modelReason.dispatch("keydown", { key: "Enter" });
assert.equal(optionIdOf(activeCard()), "opt-a", "用 Enter 展开方案内说明不能收起外层");
checks[1].dispatch("click");
assert.equal(cardsNow().filter((card) => card.classList.contains("is-active")).length, 1, "checkbox 不得触发展开/启用");
assert.equal(confirmCalls.length, 0, "整卡展开不得触发启用");
const cardB = cardsNow().find((card) => optionIdOf(card) === "opt-b");
await cardB.dispatch("keydown", { key: "Enter" });
assert.equal(optionIdOf(activeCard()), "opt-b", "键盘 Enter 必须展开方案");
assert.equal(conclusion(), "合同粒度方案");
await activeCard().children[1].dispatch("click");
assert.equal(cardsNow().filter((card) => card.classList.contains("is-active")).length, 0, "再点同一卡必须收起");
const collapsedDetails = findByClass(workbench.element, "dv-ai-single-detail");
assert.ok(collapsedDetails?.hidden, "收起后卡外的详情也必须隐藏");
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

// 多张已保存方案也只能从底部统一重验并启用，未勾选项不在启用范围内。
const cardA = cardsNow().find((card) => optionIdOf(card) === "opt-a");
await cardA.children[1].dispatch("click");
assert.equal(optionIdOf(activeCard()), "opt-a");
assert.equal(findButton(workbench.element, "保存并启动以上3个方案").disabled, true, "未测试通过不得启用");
const generating = findButton(testingSection, "生成并运行测试用例").dispatch("click");
await sleep(10);
assert.equal(findByClass(testingSection, "dv-ai-test-preparing").hidden, false);
assert.equal(previewTestCalls.length, 0);
await generating;
assert.equal(previewTestCalls.length, 3, "一次执行全部已勾选方案的样本测试");
assert.equal(collectByClass(testingSection, "dv-test-table").length, 1, "所选方案的测试用例使用一张表");
const selectedCaseCount = () => findByClass(testingSection, "dv-test-table").children[1].children.length;
assert.equal(selectedCaseCount(), options.reduce((total, option) => total + option.candidate.preview.cases.length, 0));
const optionChecks = () => collectByClass(workbench.element, "dv-ai-option-check");
optionChecks()[2].checked = false;
await optionChecks()[2].dispatch("change");
assert.equal(selectedCaseCount(), options[0].candidate.preview.cases.length + options[1].candidate.preview.cases.length);
assert.equal(collectByClass(detailSlot(activeCard()), "dv-test-panel").length, 0);
const selectedFooterEnable = findButton(workbench.element, "保存并启动以上2个方案");
assert.ok(selectedFooterEnable, "底部统一入口随勾选数量更新");
assert.equal(selectedFooterEnable.disabled, false, "测试通过后统一启用解锁");
const savesBefore = saveCalls.length;
const batchesBeforeEnable = batchCalls.length;
const testsBeforeEnable = testCalls.length;
const confirmationsBeforeEnable = confirmCalls.length;
await selectedFooterEnable.dispatch("click");
await sleep(30);
assert.equal(saveCalls.length, savesBefore, "统一启用不得回退到单条保存接口");
assert.equal(batchCalls.length, batchesBeforeEnable, "已保存未改方案复用 rule_id，不重复创建");
assert.equal(testCalls.length, testsBeforeEnable + 2, "两个勾选方案都必须重验保存版本");
assert.equal(confirmCalls.length, confirmationsBeforeEnable + 2, "仅启用两个勾选方案");
assert.equal(new Set(testCalls.slice(-2).map((entry) => entry.id)).size, 2, "重验不能重复处理同一方案");
assert.deepEqual(confirmCalls.slice(-2).map((entry) => entry.id), testCalls.slice(-2).map((entry) => entry.id),
  "启用的是刚刚重验通过的保存版本");

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

// 主按钮只保存并启动勾选方案，展开另一个方案不改变保存范围。
const footerOptions = structuredClone(options);
for (const option of footerOptions.slice(0, 2)) {
  option.recommended = true;
  const cases = option.candidate.preview.cases;
  cases.push(...cases.map((item) => ({ ...item, name: `${item.name}（补充）` })));
}
const footerScenario = await openSingleAi({ ...result, candidate_options: footerOptions });
const footerRoot = footerScenario.wb.element;
const currentCard = collectByClass(footerRoot, "dv-ai-option-card")[2];
await findButton(currentCard, "查看此方案").dispatch("click");
const footerEnable = findButton(footerRoot, "保存并启动以上2个方案");
assert.ok(footerEnable, "主按钮明确显示已勾选方案数量");
assert.equal(footerEnable.disabled, true, "勾选方案未测试时禁止启动");
assert.equal(findButton(footerRoot, "保存所选 2 条草稿").hidden, true, "AI新建不显示保存草稿入口");
await footerRoot.dispatch("click", { target: footerRoot });
assert.ok(footerScenario.wb.isOpen(), "点击遮罩保持分析结果弹窗打开");
const footerTesting = findByClass(footerRoot, "dv-testing-section");
await findButton(footerTesting, "运行当前及所选方案测试").click();
assert.equal(footerEnable.disabled, false, "完成所选方案的测试后可统一启动");
assert.deepEqual(previewTestCalls.slice(-3).map(({ definition }) => definition.name),
  [candidateA.rule_name, candidateB.rule_name, candidateC.rule_name]);
assert.equal(findButton(footerRoot, "保存所选 2 条草稿").disabled, false, "测试当前方案不改变草稿勾选");
const toggleCurrentCard = () => findButton(collectByClass(footerRoot, "dv-ai-option-card")[2], "查看此方案").click();
await toggleCurrentCard();
assert.equal(footerEnable.disabled, false, "没有展开方案也能启动已勾选方案");
await toggleCurrentCard();
assert.equal(footerEnable.disabled, false, "重新展开时恢复本方案的通过证据");

const currentCase = collectByClass(footerTesting, "dv-case-expected").at(-1);
currentCase.value = "1";
await currentCase.dispatch("change");
assert.equal(footerEnable.disabled, false, "修改未勾选方案的预期不影响已勾选方案");
await findButton(footerTesting, "运行当前及所选方案测试").click();
assert.equal(footerEnable.disabled, false);
const confirmationsBefore = confirmCalls.length;
const batchBeforeFooter = batchCalls.length;
const testsBeforeFooter = testCalls.length;
const savesBeforeFooter = saveCalls.length;
await footerEnable.click();
assert.equal(batchCalls.length, batchBeforeFooter + 1, "多选统一入口必须先走真实批量保存");
assert.deepEqual(batchCalls.at(-1).definitions.map((d) => d.name), [candidateA.rule_name, candidateB.rule_name], "保存全部勾选方案，不保存未勾选的当前方案");
assert.equal(saveCalls.length, savesBeforeFooter, "多选统一入口不得逐条调用保存接口");
assert.equal(testCalls.length, testsBeforeFooter + 2, "多选统一入口必须逐条重验保存版本");
assert.equal(confirmCalls.length, confirmationsBefore + 2);
assert.equal(testCalls.slice(-2).every((entry) => entry.payload.cases[0].expected_count === 0), true, "每个保存版本沿用对应方案自己的用例");
assert.deepEqual(confirmCalls.slice(-2).map((entry) => entry.id), testCalls.slice(-2).map((entry) => entry.id),
  "多选只启用刚重验通过的保存版本");
footerScenario.runtime.destroy();

// 只勾选一条时也从底部走批量保存、保存版本重验和启用，不能依赖卡片单条入口。
const singleFooterOptions = structuredClone(options.slice(0, 2));
singleFooterOptions.forEach((option, index) => { option.recommended = index === 0; });
const singleFooterScenario = await openSingleAi({ ...result, candidate_options: singleFooterOptions });
const singleFooterRoot = singleFooterScenario.wb.element;
assert.deepEqual(collectByClass(singleFooterRoot, "dv-ai-option-check").map((input) => input.checked), [true, false]);
const singleFooterEnable = findButton(singleFooterRoot, "保存并启动以上1个方案");
assert.ok(singleFooterEnable, "单选也保留底部统一保存并启用入口");
assert.equal(singleFooterEnable.disabled, true, "单选未测试时同样禁止启用");
await findButton(singleFooterRoot, "生成并运行测试用例").click();
assert.equal(singleFooterEnable.disabled, false);
const batchBeforeSingle = batchCalls.length;
const testsBeforeSingle = testCalls.length;
const confirmationsBeforeSingle = confirmCalls.length;
const savesBeforeSingle = saveCalls.length;
await singleFooterEnable.click();
assert.equal(batchCalls.length, batchBeforeSingle + 1, "单选统一入口必须走批量保存");
assert.deepEqual(batchCalls.at(-1).definitions.map((definition) => definition.name), [candidateA.rule_name],
  "单选只保存勾选方案，不带入同页未勾选方案");
assert.equal(saveCalls.length, savesBeforeSingle, "单选统一入口同样不得调用旧单条保存接口");
assert.equal(testCalls.length, testsBeforeSingle + 1, "单选保存后必须重验服务端保存版本");
assert.equal(confirmCalls.length, confirmationsBeforeSingle + 1, "单选只启用一个勾选方案");
assert.equal(confirmCalls.at(-1).id, testCalls.at(-1).id, "单选启用的是刚重验通过的保存版本");
assert.equal(confirmCalls.at(-1).payload.expected_hash, persistedRules.get(confirmCalls.at(-1).id).content_sha256,
  "启用确认必须携带刚回读保存版本的哈希");
assert.equal(singleFooterScenario.wb.isOpen(), false, "单选完整保存重验启用后正常关闭");
singleFooterScenario.runtime.destroy();

const singleWithSuggestions = await openSingleAi({
  ...candidateA,
  ai_suggestions: [{ id: "s1", title: "单方案补充", reason: "需核实日期", references: [{ table_name: "reg_pub_project_info", field_name: "d_cldate" }], preconditions: ["确认日期"], support_level: "unsupported", limitations: ["未读取业务行"] }],
});
const singleSupp = findByClass(singleWithSuggestions.wb.element, "dv-ai-supplements");
assert.ok(!singleSupp.hidden, "模型不支持的建议也完整展示，并说明限制");
assert.match(collectText(singleSupp), /单方案补充/);
assert.match(collectText(singleSupp), /暂不支持直接生成/);
assert.equal(findButton(singleSupp, "采纳"), null);
singleWithSuggestions.runtime.destroy();
const singleEmpty = await openSingleAi({ ...candidateA, ai_suggestions: [] });
const emptySupp = findByClass(singleEmpty.wb.element, "dv-ai-supplements");
assert.ok(emptySupp.hidden, "为空时不显示建议区或空占位");
singleEmpty.runtime.destroy();

// 真实多维度发现后的只读建议，在口径尚未确认时也应可见；不能由建议直接采纳或启用。
const pendingOptions = structuredClone(options.slice(0, 2));
for (const option of pendingOptions) {
  option.candidate.preview = null;
  option.candidate.can_enable = false;
  option.candidate.questions = [{ id: "business_key", text: "请确认记录定位编号", options: [
    { value: "project_code", label: "项目编号" },
  ] }];
}
const comparisonNotice = {
  id: "model-sum", category: "consistency", kind: "aggregate_consistency", provenance: "model",
  title: "核对项目实收与资金端份额合计是否一致",
  reason: "按同一项目、同一报送期汇总后核对；口径还需确认。",
  references: [{ table_name: "reg_pub_project_info", field_name: "f_endp_amt" },
    { table_name: "reg_pub_contract", field_name: "f_contract_amt" }],
  limitations: ["需确认单位与允许差额，不自动执行"], support_level: "needs_confirmation",
};
const pendingComparison = await openSingleAi({ ...pendingOptions[0].candidate,
  candidate_options: pendingOptions, ai_suggestions: [comparisonNotice], comparison_suggestions: [],
});
const pendingNotice = findByClass(pendingComparison.wb.element, "dv-ai-supplements");
assert.ok(pendingNotice && !pendingNotice.hidden, "多维度一致性建议不能因为口径待确认或缺少 SQL 而消失");
assert.match(collectText(pendingNotice), /核对项目实收与资金端份额合计是否一致/);
assert.match(collectText(pendingNotice), /需确认单位与允许差额/);
assert.equal(findButton(pendingNotice, "采纳"), null, "只读建议不能绕过确认生成规则");
assert.equal(findButton(pendingNotice, "保存并启用"), null);
const pendingRequest = controlByLabel(pendingComparison.wb.element, "需求描述 *");
pendingRequest.value += "（修改范围）";
await pendingRequest.dispatch("input");
assert.ok(findByClass(pendingComparison.wb.element, "dv-ai-supplements").hidden, "需求过期后不能显示旧建议");
pendingComparison.runtime.destroy();

const readyComparison = await openSingleAi({ ...candidateA, candidate_options: options.slice(0, 2),
  ai_suggestions: [comparisonNotice], comparison_suggestions: [],
});
assert.ok(!findByClass(readyComparison.wb.element, "dv-ai-supplements").hidden,
  "只有待人工确认的一致性建议时也应保留，不要求另有可采纳建议");
readyComparison.runtime.destroy();

const supplement = { ...candidateA.preview.definition, name: "实收合计一致性", null_policy: "review",
  expression: { left: "f_endp_amt", op: "neq", right_type: "field", right: "f_contract_amt", right_table: "related" },
  join: { table_name: "reg_pub_contract", relationship_confirmed: true, unmatched_policy: "review", right_aggregate: "sum",
    report_date_field: "report_date", on: [{ left: "project_code", right: "project_code" }] },
};
const defaultPreview = api.preview;
api.preview = async ({ definition }) => ({ ...candidateA.preview, definition, content_sha256: "sum-hash", sql_preview: "SELECT SUM(amount)" });
const adopted = await openSingleAi({ ...candidateA, ai_suggestions: [{ id: "aggregate", title: supplement.name,
  definition: supplement, support_level: "supported", references: [{ table_name: "reg_pub_project_info", field_name: "f_endp_amt" }],
}] });
await findButton(adopted.wb.element, "采纳").dispatch("click");
assert.match(collectText(findByClass(adopted.wb.element, "dv-ai-options")), /补充规则/);
assert.ok(collectByClass(adopted.wb.element, "dv-ai-sql-code").some((node) => /SELECT SUM/.test(collectText(node))));
const oldTests = previewTestCalls.length;
await findButton(adopted.wb.element, "生成并运行测试用例").dispatch("click");
assert.equal(previewTestCalls.length, oldTests + 2);
assert.equal(previewTestCalls.at(-1).definition.join.right_aggregate, "sum");
await findButton(adopted.wb.element, "保存所选 2 条草稿").dispatch("click");
assert.equal(batchCalls.at(-1).definitions.at(-1).join.right_aggregate, "sum");
adopted.runtime.destroy();
api.preview = defaultPreview;

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
  batch_payload: batchCalls.filter((call) => call.definitions.length === 2 && !call.definitions.some((definition) => definition.join?.right_aggregate)).at(-1),
}));
