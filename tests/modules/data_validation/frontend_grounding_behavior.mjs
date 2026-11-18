import assert from "node:assert/strict";
import { confirmationReadiness, createState, createTestEvidence } from "./state.mjs";
import { createAiCandidatePanel } from "./components/ai_candidate.mjs";
import { createRuleForm } from "./components/rule_form.mjs";
import { createTestPanel } from "./components/test_panel.mjs";

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
  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
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

function findByText(root, text) {
  if (root.tagName === "BUTTON" && root.textContent === text) return root;
  for (const child of root.children || []) {
    const found = findByText(child, text);
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

const baseColumns = [
  { column_name: "c_projcode", comment: "项目编号", data_type: "varchar" },
  { column_name: "f_endp_amt", comment: "实收信托", data_type: "numeric" },
  { column_name: "c_projstatus", comment: "项目状态", data_type: "varchar" },
  { column_name: "pro_status", comment: "业务状态", data_type: "varchar" },
  { column_name: "d_startdate", comment: "项目开始日", data_type: "date" },
  { column_name: "d_cldate", comment: "数据日期", data_type: "date" },
];
const relatedColumns = [
  { column_name: "c_projcode", comment: "项目编号", data_type: "varchar" },
  { column_name: "d_balancedate", comment: "报送日期", data_type: "date" },
  { column_name: "f_balan_endp_amt", comment: "实收信托余额", data_type: "numeric" },
];

const statusSelection = { table: "base", field: "c_projstatus", op: "eq", value: "1" };
const candidate = {
  rule_type: "field_compare",
  rule_name: "存续项目实收信托提醒",
  table_name: "reg_pub_project_info",
  report_category: "pbc_central",
  business_key: "c_projcode",
  report_date_field: "d_cldate",
  expression: { left: "f_endp_amt", op: "lt", right: "f_balan_endp_amt", right_table: "related" },
  violation_message: "存续项目实收信托异常，请人工核实",
  null_policy: "skip",
  equality_policy: "allow_equal",
  filters: [{ ...statusSelection, confirmed: false }],
  join: {
    table_name: "reg_pub_accountbalance_sum",
    on: [{ left: "c_projcode", right: "c_projcode" }],
    report_date_field: "d_balancedate",
    relationship_confirmed: false,
    unmatched_policy: "unresolved",
  },
  related_columns: relatedColumns,
  columns: baseColumns,
  uncertainties: ["选择存续状态口径", "确认关联关系", "确认未匹配处理", "确认关联日期"],
  uncertainty_resolutions: ["", "", "", ""],
  unsupported_requirements: [],
};

const state = createState();
state.sourcesStatus = "success";
const martSource = { id: "mart", name: "监管报送集市", dialect: "postgresql" };
const reportSource = { id: "src", name: "监管报表", dialect: "postgresql" };
state.sources = [martSource, reportSource];
state.categoriesStatus = "success";
state.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
const user = { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] };

// 1) 确认门禁：filters 全部 confirmed、关联关系确认、未匹配口径非 unresolved。
const detail = { id: 8, version_no: 1, content_sha256: "hash", definition: { ...candidate } };
const evidence = createTestEvidence(detail, {
  passed_count: 1, failed_count: 0, not_run_count: 0, cases: [{ status: "passed" }],
});
assert.equal(confirmationReadiness(detail, evidence).ready, false);
assert.match(confirmationReadiness(detail, evidence).reasons.join("；"), /筛选条件未确认/);
assert.match(confirmationReadiness(detail, evidence).reasons.join("；"), /关联关系尚未确认/);
assert.match(confirmationReadiness(detail, evidence).reasons.join("；"), /未匹配/);
const confirmedDefinition = {
  ...candidate,
  filters: [{ ...statusSelection, confirmed: true }],
  join: {
    ...candidate.join,
    relationship_confirmed: true,
    unmatched_policy: "exclude",
  },
  uncertainty_resolutions: ["明确选择 项目状态 = 1（存续）", "已确认关联关系", "已确认未匹配处理", "已确认关联日期"],
};
assert.equal(confirmationReadiness({ ...detail, definition: confirmedDefinition }, evidence).ready, true);
// 旧规则没有 filters/join 时不得被新门禁误伤。
assert.equal(confirmationReadiness({ ...detail, definition: { null_policy: "skip", equality_policy: "allow_equal" } }, evidence).ready, true);

// 2) 表单必须完整保留 filters/join/right_table/related_columns，不能被白名单读丢。
const form = createRuleForm({
  state, mode: "ai", listen: () => {}, user,
  onChange: () => {}, onDescribe: () => {}, onParse: () => {},
});
form.setSources();
const aiSource = controlByLabel(form.element, "数据源 *");
assert.equal(aiSource.value, "src");
assert.ok(!aiSource.options.some((item) => item.value === "mart"));
const manualSourceForm = createRuleForm({ state, mode: "manual", listen: () => {}, user, onChange: () => {} });
manualSourceForm.setSources();
const manualSource = controlByLabel(manualSourceForm.element, "数据源 *");
assert.equal(manualSource.value, "mart");
assert.ok(manualSource.options.some((item) => item.value === "src"));
state.sources = [martSource];
form.setSources();
assert.equal(aiSource.value, "");
assert.throws(() => form.validateForParse());
state.sources = [martSource, reportSource];
form.setSources();
form.setCategories();
form.setMetadata({ columns: baseColumns, related_columns: relatedColumns, mapping_version: "doc-v1-abc" });
assert.equal(form.applyCandidate(candidate), true);
const first = form.read();
assert.deepEqual(first.filters, [{ ...statusSelection, confirmed: false }]);
assert.equal(first.expression.right_table, "related");
assert.equal(first.join.table_name, "reg_pub_accountbalance_sum");
assert.equal(first.join.report_date_field, "d_balancedate");
assert.equal(first.join.unmatched_policy, "unresolved");
assert.equal(first.join.relationship_confirmed, false);
assert.equal(Object.hasOwn(first, "unmatched_policy"), false, "不得把 unmatched_policy 输出到顶层");
assert.equal(Object.hasOwn(first, "relationship_confirmed"), false, "不得把 relationship_confirmed 输出到顶层");
assert.deepEqual(first.related_columns, relatedColumns);
assert.throws(() => form.validateForSave(), /筛选条件 1 尚未确认/);

form.applyDecision("filters.0", statusSelection, {
  uncertainty: "选择存续状态口径",
  options: [{ value: "0", label: "项目状态 = 1（存续）", selection: statusSelection }],
});
form.applyDecision("join.relationship_confirmed", "confirm", {
  uncertainty: "确认关联关系",
  options: [{
    value: "confirm",
    label: "确认关联",
    selection: { on: [{ left: "c_projcode", right: "c_projcode" }], relationship_confirmed: true },
  }],
});
form.applyDecision("join.unmatched_policy", "exclude", {
  uncertainty: "确认未匹配处理",
  options: [{ value: "exclude", label: "未匹配记录不提醒" }],
});
form.applyDecision("join.report_date_field", "d_balancedate", {
  uncertainty: "确认关联日期",
  options: [{ value: "d_balancedate", label: "报送日期" }],
});
const saved = form.validateForSave();
assert.equal(saved.filters[0].confirmed, true);
assert.equal(saved.join.relationship_confirmed, true);
assert.deepEqual(saved.join.on, [{ left: "c_projcode", right: "c_projcode" }]);
assert.equal(saved.join.unmatched_policy, "exclude");
assert.equal(saved.join.report_date_field, "d_balancedate");
assert.equal(saved.expression.right_table, "related");
assert.match(saved.uncertainty_resolutions[0], /明确选择/);
assert.throws(() => form.applyDecision("filters.0", { table: "base", field: "not_a_field" }, {}), /不在当前可用范围/);
assert.throws(() => form.applyDecision("join.report_date_field", "c_projcode", {}), /不在当前可用范围/);

// 后端精确 operator：in 保留原始值类型，is_not_null 值为 null；非法 op 必须阻塞而非静默改 eq。
form.reset({
  definition: {
    ...saved,
    filters: [
      { table: "base", field: "c_projcode", op: "in", value: ["P1", 2], confirmed: true },
      { table: "base", field: "c_projcode", op: "not_in", value: [3, "P2"], confirmed: true },
      { table: "base", field: "f_endp_amt", op: "is_not_null", value: null, confirmed: true },
    ],
  },
});
const typed = form.read();
assert.deepEqual(typed.filters[0].value, ["P1", 2]);
assert.equal(typed.filters[0].op, "in");
assert.deepEqual(typed.filters[1].value, [3, "P2"]);
assert.equal(typed.filters[1].op, "not_in");
assert.equal(typed.filters[2].op, "is_not_null");
assert.equal(typed.filters[2].value, null);
form.reset({
  definition: {
    ...saved,
    filters: [{ table: "base", field: "c_projcode", op: "like", value: ["P1"], confirmed: true }],
  },
});
form.setMetadata({ columns: baseColumns, related_columns: relatedColumns, mapping_version: "doc-v1-abc" });
assert.throws(() => form.validateForSave(), /筛选运算符 like 不受支持/);

// signature 必须包含全部新结构，才能正确判断未保存修改。
const signature = form.signature();
assert.match(signature, /"filters"/);
assert.match(signature, /"join"/);
assert.match(signature, /"unmatched_policy"/);
assert.match(signature, /"relationship_confirmed"/);
assert.match(signature, /"right_table":"related"/);

// 切换数据源 / 表（setMetadata(null)）必须清理旧 query spec，不能残留。
form.setMetadata(null);
const cleared = form.read();
assert.equal(Object.hasOwn(cleared, "filters"), false);
assert.equal(Object.hasOwn(cleared, "join"), false);
assert.equal(Object.hasOwn(cleared, "related_columns"), false);
assert.equal(Object.hasOwn(cleared.expression, "right_table"), false);

// reset 重载同样保留完整关系证据。
form.setMetadata({ columns: baseColumns, related_columns: relatedColumns, mapping_version: "doc-v1-abc" });
form.reset({ definition: saved, name: saved.name, report_category: saved.report_category });
const reloaded = form.read();
assert.deepEqual(reloaded.filters, saved.filters);
assert.deepEqual(reloaded.join, saved.join);
assert.equal(reloaded.expression.right_table, "related");
assert.equal(reloaded.join.unmatched_policy, "exclude");
assert.equal(reloaded.join.relationship_confirmed, true);
assert.deepEqual(reloaded.related_columns, relatedColumns);

// P1：detail.related_columns 是可信顶层元数据（不在 definition、不改哈希）；main-only setMetadata 不得清空。
const detailColumns = [{ column_name: "c_projcode", comment: "项目编号", data_type: "varchar" }];
form.reset({
  definition: { ...saved, related_columns: undefined },
  related_columns: detailColumns,
  name: saved.name,
  report_category: saved.report_category,
});
assert.deepEqual(form.read().related_columns, detailColumns, "reset(detail) 必须从 detail.related_columns 恢复");
form.setMetadata({ columns: baseColumns, mapping_version: "doc-v1-main-only" });
assert.deepEqual(form.read().related_columns, detailColumns, "main-only setMetadata 不得清空相关列");

// P1：兼容读取顶层老暂态，但只输出嵌套 join。
form.reset({
  definition: {
    ...saved,
    join: { table_name: "reg_pub_accountbalance_sum", on: [{ left: "c_projcode", right: "c_projcode" }], report_date_field: "d_balancedate" },
    relationship_confirmed: true,
    unmatched_policy: "exclude",
  },
});
form.setMetadata({ columns: baseColumns, related_columns: relatedColumns, mapping_version: "doc-v1-legacy" });
const legacy = form.read();
assert.equal(legacy.join.relationship_confirmed, true, "顶层老暂态必须归入 join");
assert.equal(legacy.join.unmatched_policy, "exclude", "顶层老暂态必须归入 join");
assert.equal(Object.hasOwn(legacy, "relationship_confirmed"), false);
assert.equal(Object.hasOwn(legacy, "unmatched_policy"), false);

// P2：expression.right 在 right_table=related 时必须查 relatedColumns，而不是 base columns。
form.applyDecision("expression.right", "f_balan_endp_amt", {
  options: [{ value: "f_balan_endp_amt", label: "实收信托余额" }],
});
assert.equal(form.read().expression.right, "f_balan_endp_amt");
assert.throws(() => form.applyDecision("expression.right", "d_cldate", {}), /不在当前可用范围/);

// 3) 候选面板：业务摘要展示筛选/关联/日期，选项 selection 原样回传，不显示 [object Object]。
const choices = [];
const panel = createAiCandidatePanel({
  listen: (node, type, handler) => node.addEventListener(type, handler),
  onChoice: (id, value) => choices.push({ id, value }),
  onEdit: () => {}, onRetry: () => {}, notify: () => {},
});
panel.update(candidate, { request_text: "存续项目实收信托一般不为0" });
const facts = collectText(findByClass(panel.element, "dv-ai-business-facts"));
assert.match(facts, /筛选条件：项目状态为1/);
assert.match(facts, /关联 reg_pub_accountbalance_sum/);
assert.match(facts, /关联日期 d_balancedate/);
assert.match(facts, /校验日期：d_cldate/);
assert.doesNotMatch(collectText(panel.element), /\[object Object\]/);
panel.update({
  ...candidate,
  filters: [{ table: "base", field: "c_projcode", op: "not_in", value: ["P1", 2], confirmed: true }],
}, {});
assert.match(collectText(findByClass(panel.element, "dv-ai-business-facts")), /筛选条件：项目编号不属于P1、2/);

const filterQuestion = {
  id: "filters.0",
  text: "存续按哪个状态口径？",
  uncertainty: "两个状态字段编码不同",
  options: [{ value: "0", label: "项目状态 = 1（存续）", selection: statusSelection }],
};
panel.update({ ...candidate, questions: [filterQuestion] }, {}, { selectedChoice: null });
const fieldset = collectByClass(panel.element, "dv-ai-choices")[0];
const radioInput = fieldset.children[0].children.find((child) => child.tagName === "INPUT" && child.type === "radio");
assert.ok(radioInput, "筛选问题必须渲染真实单选项");
radioInput.checked = true;
await radioInput.dispatch("change");
assert.equal(choices.length, 1);
assert.equal(choices[0].id, "filters.0");
assert.deepEqual(choices[0].value, statusSelection);

// 4) 测试面板：关系样本可读渲染，旧 flat 样本保留。
const testPanel = createTestPanel({ listen: () => {}, onTest: () => {}, onCaseChange: () => {}, onDecision: () => {} });
const relationCase = {
  name: "正常",
  row: { base: { f_endp_amt: 100, c_projstatus: "1" }, related: [{ f_balan_endp_amt: 100 }], report_date: "2026-10-31" },
  expected_count: 0,
  status: "not_run",
};
testPanel.update({
  detail: null, evidence: null, dirty: false, canTest: true, readOnly: false,
  preview: { definition: { ...candidate, related_columns: relatedColumns }, cases: [relationCase], sql_preview: "SELECT 1" },
  previewCases: [relationCase], columns: baseColumns, relatedColumns, stale: false,
});
const relationSample = collectText(collectByClass(testPanel.element, "dv-test-table")[0]);
assert.match(relationSample, /实收信托：100/);
assert.match(relationSample, /项目状态：1/);
assert.match(relationSample, /关联：实收信托余额：100/);
assert.match(relationSample, /报送日期：2026-10-31/);
assert.doesNotMatch(relationSample, /\[object Object\]/);
testPanel.update({
  detail: null, evidence: null, dirty: false, canTest: true, readOnly: false,
  preview: { definition: {}, cases: [{ name: "正常", row: { amount: 1 }, expected_count: 0 }], sql_preview: "SELECT 1" },
  previewCases: [{ name: "正常", row: { amount: 1 }, expected_count: 0 }], columns: [{ column_name: "amount", comment: "金额" }], stale: false,
});
assert.match(collectText(collectByClass(testPanel.element, "dv-test-table")[0]), /金额：1/);

// 5) 一元空值判断：canonical expression {left,op}，默认 violate/allow_equal，无 skip 按钮。
const unaryForm = createRuleForm({
  state, mode: "ai", listen: () => {}, user,
  onChange: () => {}, onDescribe: () => {}, onParse: () => {},
});
unaryForm.setSources();
unaryForm.setCategories();
unaryForm.setMetadata({ columns: baseColumns, mapping_version: "doc-v1-unary" });
const unaryCandidate = {
  rule_type: "field_compare",
  rule_name: "项目开始日不能为空",
  table_name: "reg_pub_project_info",
  report_category: "pbc_central",
  business_key: "c_projcode",
  report_date_field: "d_cldate",
  expression: { left: "d_startdate", op: "is_null" },
  violation_message: "项目开始日为空，请核实",
  columns: baseColumns,
  uncertainties: [],
  unsupported_requirements: [],
};
assert.equal(unaryForm.applyCandidate(unaryCandidate), true);
// 真实 <select> 必须在设置 value 前追加一元 option，否则真实浏览器会把 value 变空（fakeDOM 不会暴露）。
const unaryOpSelect = controlByLabel(unaryForm.element, "异常触发关系");
assert.ok([...unaryOpSelect.options].some((option) => option.value === "is_null"),
  "真实 select 必须存在 is_null option，不能只设置不存在的 value");
assert.equal(unaryOpSelect.value, "is_null", "真实 select 的 value 必须命中已存在 option");
const unaryPayload = unaryForm.validateForSave();
assert.deepEqual(unaryPayload.expression, { left: "d_startdate", op: "is_null" });
assert.equal(unaryPayload.null_policy, "violate");
assert.equal(unaryPayload.equality_policy, "allow_equal");
const unaryPanel = createAiCandidatePanel({ listen: () => {}, onEdit: () => {}, onRetry: () => {}, notify: () => {} });
unaryPanel.update(unaryCandidate, {});
assert.equal(findByClass(unaryPanel.element, "dv-ai-conclusion").textContent, "项目开始日为空时，提示人工核实");
const unaryTestPanel = createTestPanel({ listen: () => {}, onTest: () => {}, onCaseChange: () => {}, onDecision: () => {} });
unaryTestPanel.update({
  detail: null, evidence: null, dirty: false, canTest: true, readOnly: false,
  preview: {
    definition: { ...unaryCandidate, null_policy: "violate", equality_policy: "allow_equal" },
    cases: [{ name: "空值", row: { base: { d_startdate: null } }, expected_count: 1, status: "not_run" }],
    sql_preview: "SELECT 1",
  },
  previewCases: [{ name: "空值", row: { base: { d_startdate: null } }, expected_count: 1, status: "not_run" }],
  columns: baseColumns, stale: false,
});
assert.equal(findByText(unaryTestPanel.element, "空值由其他规则检查，本条跳过"), null, "一元空值判断不得提供 skip 按钮");
assert.match(collectText(collectByClass(unaryTestPanel.element, "dv-test-table")[0]), /项目开始日：空值/);

// 状态原始建议与用户选择不同：表单须替换实际筛选，只保留独立的补充提示。
const activeScopeQuestion = { ...filterQuestion, uncertainty: "请确认存续范围的状态字段与状态码" };
for (const pendingIssue of ["", "关联键无法确认", "截止日期尚未确认"]) {
  const issues = [activeScopeQuestion.uncertainty, ...(pendingIssue ? [pendingIssue] : [])];
  unaryForm.applyCandidate({
    ...unaryCandidate, uncertainties: issues,
    filters: [{ ...statusSelection, field: "pro_status", value: "2", confirmed: false }],
  });
  unaryForm.applyDecision(activeScopeQuestion.id, statusSelection, activeScopeQuestion);
  const definition = unaryForm.read();
  assert.deepEqual(definition.filters, [{ ...statusSelection, confirmed: true }]);
  assert.match(definition.uncertainty_resolutions[0], /项目状态 = 1/);
  const preview = { sql_preview: 'SELECT 1 WHERE "c_projstatus" = :filter_1', sql_params: { filter_1: "1" } };
  unaryPanel.update({ ...unaryCandidate, ...definition, questions: [], preview }, {});
  const unresolved = findByClass(unaryPanel.element, "dv-ai-unresolved");
  if (pendingIssue) {
    assert.ok(collectText(unresolved).includes(pendingIssue));
    assert.doesNotMatch(collectText(unresolved), /存续/);
  } else {
    assert.equal(unresolved, null);
  }
}

// 6) 转手工 seed 必须保留 expression/日期/两种 policy/filters/join/related_columns 与一元算子。
const manualSeedForm = createRuleForm({
  state, mode: "manual", listen: () => {}, user, onChange: () => {},
});
manualSeedForm.setSources();
manualSeedForm.setCategories();
const manualSeed = {
  name: "存续项目实收信托提醒",
  source_id: "src",
  table_name: "reg_pub_project_info",
  request_text: "存续项目实收信托一般不为0",
  report_category: "pbc_central",
  business_key: "c_projcode",
  report_date_field: "d_cldate",
  expression: { left: "f_endp_amt", op: "lt", right: "f_balan_endp_amt", right_table: "related" },
  null_policy: "skip",
  equality_policy: "allow_equal",
  violation_message: "存续项目实收信托异常，请人工核实",
  filters: [{ table: "base", field: "c_projstatus", op: "eq", value: "1", confirmed: true }],
  join: {
    table_name: "reg_pub_accountbalance_sum",
    on: [{ left: "c_projcode", right: "c_projcode" }],
    report_date_field: "d_balancedate",
    unmatched_policy: "exclude",
    relationship_confirmed: true,
  },
  related_columns: relatedColumns,
};
manualSeedForm.reset(null, manualSeed);
const seeded = manualSeedForm.read();
assert.deepEqual(seeded.expression, manualSeed.expression);
assert.equal(seeded.report_date_field, "d_cldate");
assert.equal(seeded.null_policy, "skip");
assert.equal(seeded.equality_policy, "allow_equal");
assert.deepEqual(seeded.filters, manualSeed.filters);
assert.deepEqual(seeded.join, manualSeed.join);
assert.equal(seeded.join.unmatched_policy, "exclude");
assert.equal(seeded.join.relationship_confirmed, true);
assert.equal(Object.hasOwn(seeded, "unmatched_policy"), false);
assert.equal(Object.hasOwn(seeded, "relationship_confirmed"), false);
assert.deepEqual(seeded.related_columns, relatedColumns);
assert.equal(seeded.generation_mode, "manual", "seed 不得改变手工生成方式");
manualSeedForm.reset(null, {
  ...manualSeed,
  expression: { left: "d_startdate", op: "is_null" },
  null_policy: "violate",
  equality_policy: "allow_equal",
  filters: [],
  join: null,
  related_columns: [],
});
const unarySeeded = manualSeedForm.read();
assert.deepEqual(unarySeeded.expression, { left: "d_startdate", op: "is_null" });
assert.equal(unarySeeded.null_policy, "violate");
assert.equal(unarySeeded.equality_policy, "allow_equal");
assert.equal(Object.hasOwn(unarySeeded, "join"), false);
manualSeedForm.setMetadata({ columns: baseColumns, mapping_version: "map-manual" });
manualSeedForm.reset(null, {
  ...manualSeed,
  filters: [{ table: "base", field: "c_projcode", op: "like", value: ["P1"], confirmed: true }],
});
manualSeedForm.setMetadata({ columns: baseColumns, mapping_version: "map-manual" });
assert.throws(() => manualSeedForm.validateForSave(), /筛选运算符 like 不受支持/);

console.log(JSON.stringify({
  ok: true,
  assertions: "grounding/state/form/candidate/test-panel/unary/seed/bridge",
  snapshot: seeded,
  unary: unaryPayload,
}));
