import assert from "node:assert/strict";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { createKnowledgeSettings } from "./components/knowledge_settings.mjs";

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
    if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
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

const columns = [
  { column_name: "c_projcode", comment: "项目编号", data_type: "varchar" },
  { column_name: "f_endp_amt", comment: "实收信托", data_type: "numeric" },
  { column_name: "report_date", comment: "报送日期", data_type: "date" },
];
const candidate = {
  rule_name: "项目校验", rule_type: "field_compare", table_name: "reg_pub_project_info",
  source_id: "src", dialect: "mysql", report_category: "pbc_central",
  columns, related_columns: [], project_columns: [{ column_name: "c_projname", comment: "项目名称", data_type: "varchar" }],
  project_table: "reg_pub_project_info", mapping_version: "map-q",
  business_key: "c_projcode", report_date_field: "report_date",
  expression: { left: "f_endp_amt", op: "eq", right_type: "value", right: 0 },
  violation_message: "金额为0", null_policy: "skip", equality_policy: "allow_equal",
  uncertainties: [], unsupported_requirements: [],
  ai_suggestions: [{ title: "检查实收对应字段一致性", support_level: "supported",
    references: [{ table_name: "reg_pub_project_info", field_name: "f_endp_amt" }] }],
  questions: [
    { id: "project_context.code_field", text: "本表用哪个项目编号？", options: [{ value: "c_projcode", label: "项目编号" }] },
    { id: "project_context.name_field", text: "本表用哪个项目名称？", options: [{ value: "c_projname", label: "项目名称" }] },
  ],
  preview: {
    definition: { name: "项目校验", rule_type: "field_compare", business_key: "c_projcode", report_date_field: "report_date",
      expression: { left: "f_endp_amt", op: "eq", right_type: "value", right: 0 }, null_policy: "skip", equality_policy: "allow_equal" },
    content_sha256: "h0", sql_preview: "SELECT 1", sql_params: {},
    cases: [{ name: "正常", row: { f_endp_amt: 1 }, expected_count: 0, actual_count: null, status: "not_run" }],
    questions: [],
    columns, project_columns: [{ column_name: "c_projname", comment: "项目名称", data_type: "varchar" }],
    project_table: "reg_pub_project_info", mapping_version: "map-q", persisted: false,
  },
};
const state = createState();
state.sourcesStatus = "success";
state.sources = [{ id: "src", name: "监管报表", dialect: "mysql" }];
state.categoriesStatus = "success";
state.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
state.modelsStatus = "success";
state.models = [{ id: "model-1", name: "内网模型", model_name: "validation-model", is_default: true }];
const previewCalls = [];
const api = {
  createAnalysis: async () => ({ analysis_id: "a1", status: "completed", elapsed_ms: 0, steps: [], result: candidate }),
  getAnalysis: async () => ({ analysis_id: "a1", status: "completed", steps: [], result: candidate }),
  cancelAnalysis: async () => {},
  preview: async (payload) => {
    previewCalls.push(payload);
    const staged = previewCalls.length === 1
      ? { content_sha256: "h1", questions: [{ id: "project_context.confirmed", text: "确认项目关联？", options: [{ value: "true", label: "确认" }] }] }
      : { content_sha256: `h${previewCalls.length}`, questions: [] };
    return {
      definition: { ...candidate, name: "项目校验", project_context: { mode: "base", code_field: "c_projcode", name_field: "c_projname", confirmed: true } },
      sql_preview: "SELECT 1", sql_params: {},
      cases: [{ name: "正常", row: { f_endp_amt: 1 }, expected_count: 0, actual_count: null, status: "not_run" }],
      columns, project_columns: [{ column_name: "c_projname", comment: "项目名称", data_type: "varchar" }],
      project_table: "reg_pub_project_info", mapping_version: "map-q", persisted: false,
      ...staged,
    };
  },
  testCandidate: async () => ({ cases: [], passed_count: 0, failed_count: 0, not_run_count: 0, content_sha256: "h" }),
  describe: async () => ({ mapping_version: "map", columns }),
};
const runtime = createRuntime({ notify: () => {} });
runtime.activate();
const wb = createWorkbench({
  state, runtime, api, listen: runtime.listen,
  user: { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] },
  notify: () => {}, host: new FakeElement("div"), onClose: () => {}, onChanged: async () => {},
  confirmAction: async () => true, onRetrySources: () => {}, onRetryModels: () => {},
});
await wb.open({ mode: "ai" });
const req = controlByLabel(wb.element, "需求描述 *");
req.value = "项目需求";
await req.dispatch("input");
await controlByLabel(wb.element, "数据源 *").dispatch("change");
await controlByLabel(wb.element, "启用模型").dispatch("change");
await findButton(wb.element, "✦ AI 分析").dispatch("click");
await sleep(30);
const panelQuestions = () => collectByClass(wb.element, "dv-ai-choices")[0]?.children || [];
assert.equal(panelQuestions().length, 1, "候选面板一次展示一个分阶段问题");
const suggestions = () => findByClass(wb.element, "dv-ai-supplements");
assert.ok(suggestions().hidden, "确认口径中不显示已有合格建议");
const answerCurrent = async () => {
  const radios = collectByClass(wb.element, "dv-ai-choices").flatMap((group) => group.children.map((label) => label.children.find((child) => child.tagName === "INPUT")));
  assert.equal(radios.length, 1, "一次只渲染一个分阶段问题");
  radios[0].checked = true;
  await radios[0].dispatch("change");
  await findButton(wb.element, "按此口径继续分析").dispatch("click");
  await sleep(30);
};
await answerCurrent();
assert.equal(previewCalls.length, 0, "仍有已知待解决问题时不得调用 preview");
assert.ok(collectText(wb.element).includes("本表用哪个项目名称"), "未选完的已知问题必须保留");
await answerCurrent();
assert.equal(previewCalls.length, 1, "已知问题选完后才请求 preview");
assert.ok(collectText(wb.element).includes("确认项目关联"), "preview 返回的新问题必须合入并显示");
assert.ok(suggestions().hidden, "预览返回后仍有独立口径，继续隐藏建议");
await answerCurrent();
assert.equal(previewCalls.length, 2, "新问题选完后再请求终态 preview");
assert.equal(collectByClass(wb.element, "dv-ai-choices").length, 0, "全部问题解决后面板不再显示问题");
assert.equal(suggestions().hidden, false, "口径全部确认且已有 SQL 预览时显示合格建议");
assert.match(collectText(suggestions()), /检查实收对应字段一致性/);
assert.ok(findButton(wb.element, "运行测试"), "预览生成后测试区必须可用");
// 状态选择：编号分行；仅继续时保存本地偏好；新分析预勾选但不自动请求预览。
const lastValues = new Map();
globalThis.localStorage = { getItem: (key) => lastValues.get(key) ?? null, setItem: (key, value) => lastValues.set(key, value) };
const status = (field, value) => ({ table: "base", field, op: "eq", value, confirmed: true });
const statuses = [status("c_projstatus", "1"), status("pro_status", "2"), status("pro_isclose", "1")];
const steps = ["1.判定范围：期末余额 0.5。", "2、按同日报送日。", "3．其他情况：留空。"];
const scopeQuestion = { id: "filters.0", remember_scope: "active_status", text: "采用哪个筛选口径？",
  options: statuses.map((selection, index) => ({ value: String(index), label: `${selection.field} = ${selection.value}`,
    description: index === 1 ? steps.join(" ") : "文档字典", selection })) };
const scopeCandidate = { ...candidate, preview: null, filters: [{ ...statuses[0], confirmed: false }],
  columns: [...columns, ...statuses.map((item) => ({ column_name: item.field, data_type: "varchar" }))], questions: [scopeQuestion] };
api.createAnalysis = async () => ({ status: "completed", result: scopeCandidate });
api.preview = async (payload) => {
  previewCalls.push(payload);
  return { ...candidate.preview, definition: payload.definition, questions: [], content_sha256: "scope-hash" };
};
const runScopeAnalysis = async () => {
  await wb.open({ mode: "ai" });
  const input = controlByLabel(wb.element, "需求描述 *");
  input.value = "存续的项目，实收信托一般不为0";
  await input.dispatch("input");
  await findButton(wb.element, "✦ AI 分析").dispatch("click");
  await sleep(30);
};
const choiceRows = () => collectByClass(wb.element, "dv-ai-choice");
const chooseStatus = async (index) => {
  const radio = choiceRows()[index].children.find((child) => child.tagName === "INPUT");
  radio.checked = true;
  await radio.dispatch("change");
};
await runScopeAnalysis();
assert.equal(choiceRows().length, 3);
assert.deepEqual(collectByClass(choiceRows()[1], "dv-ai-choice-note-line").map(collectText), steps);
assert.equal(choiceRows().some((row) => row.classList.contains("is-selected")), false);
await chooseStatus(1);
assert.equal(lastValues.size, 0, "仅勾选还不能记忆");
await findButton(wb.element, "按此口径继续分析").dispatch("click");
assert.equal(previewCalls.at(-1).definition.filters[0].field, "pro_status");
assert.equal(lastValues.size, 1);
const priorPreviewCount = previewCalls.length;
await runScopeAnalysis();
assert.equal(previewCalls.length, priorPreviewCount, "预勾选不能自动生成预览");
assert.ok(choiceRows()[1].classList.contains("is-selected"));
assert.equal(collectText(collectByClass(choiceRows()[1], "dv-ai-choice-tail")[0]), "上次");
await chooseStatus(2);
assert.ok(choiceRows()[2].classList.contains("is-selected"));
assert.equal(collectText(collectByClass(choiceRows()[1], "dv-ai-choice-tail")[0]), "上次");
await findButton(wb.element, "按此口径继续分析").dispatch("click");
assert.equal(previewCalls.at(-1).definition.filters[0].field, "pro_isclose");
await runScopeAnalysis();
assert.ok(choiceRows()[2].classList.contains("is-selected"));
assert.equal(collectText(collectByClass(choiceRows()[2], "dv-ai-choice-tail")[0]), "上次");
scopeQuestion.options.pop();
await runScopeAnalysis();
assert.equal(choiceRows().some((row) => row.classList.contains("is-selected")), false);
assert.equal(collectByClass(wb.element, "dv-ai-choice-tail").length, 0, "文档已无上次选项，不能强行预选");
const shared = { ...scopeQuestion, uncertainty: "请确认存续范围", options: scopeQuestion.options };
const parallelBase = { ...scopeCandidate, parallel_check: true, uncertainties: [shared.uncertainty],
  uncertainty_resolutions: [], columns: [...scopeCandidate.columns, { column_name: "f_balan_fatotal", data_type: "numeric" }] };
const paid = { ...parallelBase, questions: [shared] };
const asset = { ...parallelBase, rule_name: "项目资产检查", expression: { ...parallelBase.expression, left: "" },
  questions: [shared, { id: "expression.left", text: "这里的资产指哪个字段？",
    options: [{ value: "f_balan_fatotal", label: "资产大类科目余额" }] }] };
api.createAnalysis = async () => ({status: "completed", result: { ...paid, candidate_options: [
  {id: "paid", label: "项目实收检查", recommended: true, candidate: paid},
  {id: "asset", label: "项目资产检查", candidate: asset},
] }});
api.batchSaveCandidates = async () => assert.fail("预览不能保存规则");
const beforeParallel = previewCalls.length;
await runScopeAnalysis();
assert.match(collectText(wb.element), /已拆分为独立检查项/);
assert.equal(choiceRows().length, 2);
await chooseStatus(0);
await findButton(wb.element, "按此口径继续分析").dispatch("click");
assert.equal(previewCalls.length, beforeParallel + 1);
assert.equal(previewCalls.at(-1).definition.expression.left, "f_endp_amt");
const assetCard = collectByClass(wb.element, "dv-ai-option-card")[1];
await findButton(assetCard, "查看/完善此方案").dispatch("click");
assert.match(collectText(wb.element), /这里的资产指哪个字段/);
assert.equal(choiceRows().length, 1, "只问资产字段，不重复问存续");
await chooseStatus(0);
await findButton(wb.element, "按此口径继续分析").dispatch("click");
assert.equal(previewCalls.length, beforeParallel + 2);
assert.equal(previewCalls.at(-1).definition.expression.left, "f_balan_fatotal");
assert.deepEqual(previewCalls.at(-1).definition.filters, previewCalls.at(-2).definition.filters);
assert.deepEqual(previewCalls.at(-1).definition.uncertainty_resolutions, previewCalls.at(-2).definition.uncertainty_resolutions);
const configured = { kind: "public", topic: "产品分类", summary: "公开摘要", reference: "https://example.org/guide",
  source_name: "", valid_from: "", valid_to: "", keywords: ["项目"] };
let knowledgeSnapshot = { revision: 0, active_revision: 0, draft: [configured], active: [] };
const knowledgeApi = {
  knowledge: async () => knowledgeSnapshot,
  previewKnowledge: async ({ entries }) => ({ entries }),
  saveKnowledge: async ({ entries, expected_revision }) => {
    assert.equal(expected_revision, knowledgeSnapshot.revision);
    return knowledgeSnapshot = { ...knowledgeSnapshot, revision: expected_revision + 1, draft: entries };
  },
  activateKnowledge: async ({ expected_revision, enabled }) => {
    assert.equal(expected_revision, knowledgeSnapshot.revision);
    assert.equal(enabled, true);
    return knowledgeSnapshot = { ...knowledgeSnapshot, revision: expected_revision + 1,
      active_revision: expected_revision + 1, active: knowledgeSnapshot.draft };
  },
};
const settings = createKnowledgeSettings({ runtime, api: knowledgeApi, listen: runtime.listen, canAdmin: true });
await settings.refresh();
const knowledgeButton = (text) => findButton(settings.section, text);
assert.ok(knowledgeButton("启用已保存草稿").disabled);
await knowledgeButton("预览草稿").dispatch("click");
assert.match(collectText(settings.section), /草稿预览.*未保存、未启用/);
assert.equal(knowledgeSnapshot.revision, 0);
await knowledgeButton("保存知识草稿").dispatch("click");
assert.equal(knowledgeSnapshot.active_revision, 0);
assert.equal(knowledgeButton("启用已保存草稿").disabled, false);
const topic = controlByLabel(settings.section, "主题");
topic.value = "未保存的主题";
await topic.dispatch("input");
assert.ok(knowledgeButton("启用已保存草稿").disabled);
await knowledgeButton("保存知识草稿").dispatch("click");
await knowledgeButton("启用已保存草稿").dispatch("click");
assert.equal(knowledgeSnapshot.active[0].topic, "未保存的主题");
assert.match(collectText(settings.section), /启用 v3/);
assert.ok(createKnowledgeSettings({ runtime, api: knowledgeApi, listen: runtime.listen, canAdmin: false }).section.hidden);
runtime.destroy();
console.log(JSON.stringify({ ok: true, assertions: "preview/questions-merge/staged/backend-metadata/scope-memory/numbered-steps/knowledge-settings" }));
