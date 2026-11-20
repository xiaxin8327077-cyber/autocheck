import assert from "node:assert/strict";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { createKnowledgeSettings } from "./components/knowledge_settings.mjs";
import { createRuleForm } from "./components/rule_form.mjs";

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

const columns = [
  { column_name: "c_projcode", comment: "项目编号", data_type: "varchar" },
  { column_name: "f_endp_amt", comment: "实收信托", data_type: "numeric" },
  { column_name: "report_date", comment: "报送日期", data_type: "date" },
];
const candidate = {
  analysis_context: "current-doc-and-settings",
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
    if (previewCalls.length === 1) return {
      status: "needs_confirmation", definition: { ...payload.definition,
        project_context: { mode: "base", code_field: "c_projcode", name_field: "c_projname", confirmed: false } },
      questions: [{ id: "project_context.confirmed", text: "确认项目关联？", options: [{ value: "true", label: "确认" }] }],
      columns, persisted: false,
    };
    return {
      definition: { ...payload.definition, name: "项目校验", project_context: { mode: "base", code_field: "c_projcode", name_field: "c_projname", confirmed: true } },
      sql_preview: "SELECT 1", sql_params: {},
      cases: [{ name: "正常", row: { f_endp_amt: 1 }, expected_count: 0, actual_count: null, status: "not_run" }],
      columns, project_columns: [{ column_name: "c_projname", comment: "项目名称", data_type: "varchar" }],
      project_table: "reg_pub_project_info", mapping_version: "map-q", persisted: false,
      questions: [], content_sha256: `h${previewCalls.length}`,
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
const inputChoices = (root) => collectByClass(root, "dv-ai-choice").map((row) => row.children.find((child) => child.tagName === "INPUT"));
const choose = async (node) => { node.checked = true; await node.dispatch("change"); };
const allQuestions = () => findByClass(wb.element, "dv-business-questions");
assert.equal(collectByClass(allQuestions(), "dv-business-question").length, 2);
assert.match(collectText(wb.element), /本表用哪个项目名称/, "先列出所有已知待选项");
assert.ok(findByClass(wb.element, "dv-testing-section").hidden, "旧预览不应开放测试");
assert.ok(findButton(wb.element, "保存并启用").hidden);
const suggestions = () => findByClass(wb.element, "dv-ai-supplements");
assert.ok(!suggestions().hidden, "主规则待确认时也展示模型建议，不因此隐藏");
const answerCurrent = async () => {
  const radios = collectByClass(wb.element, "dv-ai-choices").flatMap((group) => group.children.map((label) => label.children.find((child) => child.tagName === "INPUT")));
  assert.equal(radios.length, 1, "一次只渲染一个分阶段问题");
  radios[0].checked = true;
  await radios[0].dispatch("change");
  await findButton(wb.element, "确认当前口径").dispatch("click");
  await sleep(30);
};
await choose(inputChoices(allQuestions())[0]);
assert.equal(previewCalls.length, 0, "仍有已知待解决问题时不得调用 preview");
assert.ok(collectText(wb.element).includes("本表用哪个项目名称"), "未选完的已知问题必须保留");
await choose(inputChoices(allQuestions())[1]);
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(previewCalls.length, 1, "已知问题选完后才请求 preview");
assert.equal(previewCalls[0].analysis_id, "a1");
assert.equal(previewCalls[0].analysis_context, "current-doc-and-settings");
assert.equal(previewCalls[0].analysis_request_text, "项目需求");
assert.ok(previewCalls[0].model_id);
assert.ok(collectText(wb.element).includes("确认项目关联"), "preview 返回的新问题必须合入并显示");
assert.ok(!suggestions().hidden, "预览仍有独立口径时建议继续展示，测试和启用仍受门禁控制");
assert.ok(findByClass(wb.element, "dv-testing-section").hidden, "预检仍需确认时不接受返回的旧 SQL");
await choose(inputChoices(allQuestions())[0]);
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(previewCalls.length, 2, "新问题选完后再请求终态 preview");
assert.equal(collectByClass(wb.element, "dv-ai-choices").length, 0, "全部问题解决后面板不再显示问题");
assert.equal(suggestions().hidden, false, "口径全部确认且已有 SQL 预览时显示合格建议");
assert.match(collectText(suggestions()), /检查实收对应字段一致性/);
assert.ok(findButton(wb.element, "生成并运行测试用例"), "预览生成后测试入口必须可用");
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
await findButton(wb.element, "确认当前口径").dispatch("click");
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
await findButton(wb.element, "确认当前口径").dispatch("click");
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
assert.match(collectText(allQuestions()), /有 2 个业务口径需要确认/);
assert.equal(collectByClass(wb.element, "dv-ai-option-card").length, 0);
assert.equal(inputChoices(allQuestions()).length, 3);
await choose(inputChoices(allQuestions())[0]);
assert.equal(previewCalls.length, beforeParallel);
assert.match(collectText(wb.element), /这里的资产指哪个字段/);
await choose(inputChoices(allQuestions())[2]);
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(previewCalls.length, beforeParallel + 2);
assert.equal(previewCalls.at(-2).definition.expression.left, "f_endp_amt");
assert.equal(previewCalls.at(-1).definition.expression.left, "f_balan_fatotal");
assert.deepEqual(previewCalls.at(-1).definition.filters, previewCalls.at(-2).definition.filters);
assert.deepEqual(previewCalls.at(-1).definition.uncertainty_resolutions, previewCalls.at(-2).definition.uncertainty_resolutions);
const documentGap = "文档中「资管产品明细」缺少项目名称字段。请在「校验设置 → 文档快照」补充字段说明后重新分析。";
api.createAnalysis = async () => ({ status: "completed", result: { ...scopeCandidate,
  questions: [], filters: [statuses[0]], uncertainties: [documentGap], preview_error: documentGap,
} });
await runScopeAnalysis();
assert.match(collectText(wb.element), /暂时无法预览/);
assert.equal(collectText(wb.element).split(documentGap).length, 2, "文档缺口只展示一次");
assert.equal(findButton(wb.element, "重试生成预览"), null);
assert.equal(findButton(wb.element, "生成 SQL 预览"), null);
assert.equal(choiceRows().length, 0, "已确定的存续条件不出现确认卡");
await wb.element.dispatch("click", { target: wb.element });
assert.ok(wb.isOpen(), "文档缺口提示弹窗点击遮罩保持打开");
const rawRefusal = "目标表缺少实收字段和终止状态字段，无法构造字段比较表达式。";
const modelJudgments = {
  select_table: { table: "raise_info_dtl_pboc", uncertainties: [], unsupported_requirements: [] },
  generate_rule: { expression: {}, uncertainties: [rawRefusal], unsupported_requirements: [] },
};
api.createAnalysis = async () => ({ status: "completed", result: {
  ...scopeCandidate, table_name: "proj_info_dtl_pboc", questions: [], filters: [statuses[0]],
  uncertainties: [], model_judgments: modelJudgments,
  knowledge_context: { revision: 8, topics: ["监管报表项目实收字段映射"] },
} });
await runScopeAnalysis();
const visibleTrace = collectText(wb.element);
assert.match(visibleTrace, /模型判断/);
assert.match(visibleTrace, /本次提供的业务知识（v8）：监管报表项目实收字段映射/);
assert.match(visibleTrace, /模型选表：raise_info_dtl_pboc/);
assert.match(visibleTrace, /模型生成的条件：未生成/);
assert.ok(visibleTrace.includes(rawRefusal));
assert.match(visibleTrace, /系统核对的目标表：proj_info_dtl_pboc/);
assert.equal(collectByClass(wb.element, "dv-ai-unresolved").length, 0, "模型原话不会成为额外的启用门禁");
await wb.element.dispatch("click", { target: wb.element });
assert.ok(wb.isOpen(), "模型判断展开项所在弹窗不受遮罩点击关闭");
const categoryQuestion = { id: "report_category", text: "确认报送类型", options: [{ value: "pbc_central", label: "人行大集中报送" }] };
api.createAnalysis = async () => ({ status: "completed", result: { ...scopeCandidate,
  questions: [categoryQuestion], filters: [statuses[0]], uncertainties: [documentGap], preview_error: documentGap,
} });
await runScopeAnalysis();
const beforeBlockedPreview = previewCalls.length;
await choose(inputChoices(allQuestions())[0]);
assert.ok(findButton(wb.element, "确认全部口径").disabled);
assert.equal(previewCalls.length, beforeBlockedPreview, "确定分类无法补齐文档字段");
assert.match(collectText(wb.element), /缺少项目名称字段/);
const pendingCandidate = { ...scopeCandidate, preview: candidate.preview, filters: [statuses[0]],
  uncertainties: ["需确定独立的截止日期"], unsupported_requirements: ["需说明特例如何处理"],
  questions: [categoryQuestion] };
api.createAnalysis = async () => ({ status: "completed", result: pendingCandidate });
await runScopeAnalysis();
assert.match(collectText(wb.element), /需确定独立的截止日期/);
assert.match(collectText(wb.element), /需说明特例如何处理/);
await choose(inputChoices(allQuestions())[0]);
assert.ok(findButton(wb.element, "确认全部口径").disabled);
assert.equal(previewCalls.length, beforeBlockedPreview, "类别回答完成不能提前编译仍有独立要求的 SQL");
assert.equal(findByClass(wb.element, "dv-ai-sql-preview"), null);
assert.ok(findByClass(wb.element, "dv-testing-section").hidden);
assert.equal(findButton(wb.element, "重试生成预览"), null);
const readyCandidate = { ...candidate, questions: [], preview: { ...candidate.preview,
  definition: { ...candidate.preview.definition, table_name: candidate.table_name },
} };
const blockedOption = { ...pendingCandidate, questions: [], parallel_check: true };
api.createAnalysis = async () => ({ status: "completed", result: { candidate_options: [
  { id: "ready", label: "可运行", recommended: true, candidate: readyCandidate },
  { id: "blocked", label: "需补充", candidate: blockedOption },
] } });
await runScopeAnalysis();
assert.equal(collectByClass(wb.element, "dv-ai-option-card").length, 0);
assert.ok(findByClass(wb.element, "dv-testing-section").hidden);
assert.equal(previewCalls.length, beforeBlockedPreview);
assert.equal(findByClass(wb.element, "dv-ai-sql-preview"), null);
assert.match(collectText(wb.element), /需确定独立的截止日期/);
const lookupChoices = ["dim_a", "dim_b"].map((table_name) => ({ value: table_name, label: table_name,
  selection: { mode: "lookup", table_name } }));
api.createAnalysis = async () => ({ status: "completed", result: { ...readyCandidate, preview: null,
  questions: [{ id: "project_context.table_name", text: "选择项目维表", options: lookupChoices }] } });
await runScopeAnalysis();
await chooseStatus(1);
assert.deepEqual(choiceRows().map((row) => row.classList.contains("is-selected")), [false, true], "两个不同项目维表不能同时标记已选");
await findButton(wb.element, "确认当前口径").dispatch("click");
assert.equal(previewCalls.at(-1).definition.project_context.table_name, "dim_b");
const nullChoice = { id: "null_policy", text: "缺值时如何处理？", uncertainty: "需确认空值口径",
  options: [{ value: "skip", label: "仅比较两侧都有值的记录" }] };
api.createAnalysis = async () => ({ status: "completed", result: { ...readyCandidate,
  preview: candidate.preview, null_policy: "unresolved", uncertainties: [nullChoice.uncertainty], questions: [nullChoice] } });
await runScopeAnalysis();
assert.ok(findByClass(wb.element, "dv-testing-section").hidden);
const beforeNull = previewCalls.length;
await answerCurrent();
assert.equal(previewCalls.length, beforeNull + 1);
assert.equal(previewCalls.at(-1).definition.null_policy, "skip");
assert.match(previewCalls.at(-1).definition.uncertainty_resolutions[0], /仅比较两侧都有值的记录/);
const configured = { kind: "public", topic: "产品分类", summary: "公开摘要", reference: "https://example.org/guide",
  source_name: "", valid_from: "", valid_to: "", keywords: ["项目"] };
const martMapping = { ...configured, kind: "local", source_name: "监管报送集市", topic: "集市项目映射" };
const reportMapping = { ...configured, kind: "local", source_name: "监管报表", topic: "报表项目映射" };
let knowledgeSnapshot = { revision: 0, active_revision: 0, draft: [configured, martMapping, reportMapping], active: [] };
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
const draftGroups = collectByClass(settings.section, "dv-knowledge-group");
assert.deepEqual(draftGroups.map((item) => item.dataset.knowledgeSource), ["监管报送集市", "监管报表", ""]);
assert.match(collectText(draftGroups[0]), /集市项目映射/);
assert.doesNotMatch(collectText(draftGroups[0]), /报表项目映射/);
assert.match(collectText(draftGroups[1]), /报表项目映射/);
assert.doesNotMatch(collectText(draftGroups[1]), /集市项目映射/);
const knowledgeEntry = () => collectByClass(settings.section, "dv-knowledge-entry")
  .find((node) => controlByLabel(node, "知识类型")?.value === "public");
assert.equal(knowledgeEntry().tagName, "DETAILS");
assert.equal(knowledgeEntry().open, false, "已保存条目默认收起");
assert.match(collectText(knowledgeEntry().children[0]), /产品分类/);
assert.ok(knowledgeButton("启用已保存草稿").disabled);
await knowledgeButton("预览草稿").dispatch("click");
assert.match(collectText(settings.section), /草稿预览.*未保存、未启用/);
assert.equal(knowledgeSnapshot.revision, 0);
await knowledgeButton("保存知识草稿").dispatch("click");
assert.equal(knowledgeSnapshot.active_revision, 0);
assert.equal(knowledgeButton("启用已保存草稿").disabled, false);
const topic = controlByLabel(knowledgeEntry(), "主题");
knowledgeEntry().open = true;
topic.value = "未保存的主题";
await topic.dispatch("input");
assert.match(collectText(knowledgeEntry().children[0]), /未保存的主题/);
assert.ok(knowledgeButton("启用已保存草稿").disabled);
await knowledgeButton("保存知识草稿").dispatch("click");
await knowledgeButton("启用已保存草稿").dispatch("click");
assert.equal(knowledgeSnapshot.active[0].topic, "未保存的主题");
assert.match(collectText(settings.section), /启用 v3/);
assert.ok(knowledgeEntry().open, "保存及启用保留当前编辑条目的展开状态");
assert.ok(createKnowledgeSettings({ runtime, api: knowledgeApi, listen: runtime.listen, canAdmin: false }).section.hidden);

const choices = { ...candidate, preview: null,
  columns: [...columns, { column_name: "f_endp_total", comment: "累计实收", data_type: "numeric" }],
  expression: { left: "f_endp_amt", op: "is_null" }, null_policy: "violate",
  questions: [{ id: "expression.left", text: "实收指哪个字段？", uncertainty: "确认实收字段",
    options: [{ value: "f_endp_amt", label: "实收信托" }, { value: "f_endp_total", label: "累计实收" }] }],
  uncertainties: ["确认实收字段"],
};
api.createAnalysis = async () => ({ status: "completed", result: choices });
const allPreviews = [];
api.preview = async ({ definition }) => {
  allPreviews.push(definition);
  return { ...candidate.preview, definition, questions: [], content_sha256: definition.expression.left };
};
await wb.open({ mode: "ai" });
const requestAll = controlByLabel(wb.element, "需求描述 *");
requestAll.value = "实收不得为空";
await requestAll.dispatch("input");
await findButton(wb.element, "✦ AI 分析").dispatch("click");
const allRadio = choiceRows().find((row) => collectText(row).includes("全部都要")).children[0];
allRadio.checked = true;
await allRadio.dispatch("change");
await findButton(wb.element, "确认当前口径").dispatch("click");
assert.deepEqual(allPreviews.map((item) => item.expression.left), ["f_endp_amt", "f_endp_total"]);
assert.ok(allPreviews.every((item) => item.uncertainty_resolutions[0].includes(item.expression.left)));
assert.equal(collectByClass(wb.element, "dv-ai-option-card").length, 2);
assert.equal(collectByClass(wb.element, "dv-ai-option-check").filter((item) => item.checked).length, 2);
assert.ok(findButton(wb.element, "生成并运行测试用例"));
const navFields = [
  { value: "unit_net_value", label: "单位净值", rule_name: "单位净值非空校验" },
  { value: "accum_net_value", label: "累计净值", rule_name: "累计净值非空校验" },
];
const requirement = { id: "check_requirement", text: "要对“净值”做哪项检查？", uncertainty: "请明确校验要求",
  options: [{ value: "not_empty", label: "不得为空" }] };
const navFieldQuestion = { id: "expression.left", text: "净值指哪个字段？", uncertainty: "请选择净值字段", options: navFields };
for (const inputText of ["净值", "净值不得为空"]) {
  const bare = inputText === "净值";
  const questions = bare ? [requirement, navFieldQuestion] : [navFieldQuestion];
  const nav = { ...choices, description: inputText, rule_name: "净值检查", preview: candidate.preview,
    columns: [...columns, ...navFields.map(({ value, label }) => ({ column_name: value, comment: label, data_type: "numeric" }))],
    expression: { left: "", op: "is_null" }, questions, uncertainties: questions.map((q) => q.uncertainty) };
  api.createAnalysis = async () => ({ status: "completed", result: nav });
  allPreviews.length = 0;
  await wb.open({ mode: "ai" });
  const input = controlByLabel(wb.element, "需求描述 *");
  input.value = inputText;
  await input.dispatch("input");
  await findButton(wb.element, "✦ AI 分析").dispatch("click");
  assert.equal(findByClass(wb.element, "dv-ai-sql-preview"), null);
  if (bare) {
    assert.match(collectText(wb.element), /要对“净值”做哪项检查/);
    assert.match(collectText(wb.element), /净值指哪个字段/);
    assert.match(collectText(allQuestions()), /有 2 个业务口径需要确认/);
    await choose(inputChoices(allQuestions())[0]);
    assert.equal(input.value, "净值", "选择口径时保留原需求");
  }
  const labels = choiceRows().map((row) => findByClass(row, "dv-ai-choice-title").textContent);
  assert.deepEqual(labels.slice(bare ? -2 : -3), bare ? ["单位净值", "累计净值"] : ["单位净值", "累计净值", "全部都要"]);
  assert.equal(allPreviews.length, 0, "检查要求已确定也要等字段选择");
  if (bare) await choose(findByClass(allQuestions(), "dv-business-select-all"));
  else await chooseStatus(2);
  await findButton(wb.element, bare ? "确认全部口径" : "确认当前口径").dispatch("click");
  assert.deepEqual(allPreviews.map((item) => item.expression.left), ["unit_net_value", "accum_net_value"]);
  for (const definition of allPreviews) {
    assert.equal(definition.description, "净值不得为空");
    assert.equal(definition.expression.op, "is_null");
    assert.equal(definition.null_policy, "violate");
    assert.equal(definition.equality_policy, "allow_equal");
    assert.ok(definition.uncertainty_resolutions.every(Boolean));
  }
}
// A common scope is answered before a metric selection can branch into multiple cards.
const methods = ["c_oper_mode", "c_oper_mode_orig"].map((field, i) => ({
  label: ["运行方式", "原始运行方式"][i], selection: { table: "base", field, op: "in", value: ["1", "3"], confirmed: true },
}));
const methodQuestion = { id: "filters.0", text: "采用哪个运行方式？", uncertainty: "确认运行方式", options: methods };
const navRequest = "项目为净值型时，净值不得为空";
const scopedNav = { ...choices, analysis_protocol: 2, semantic_intent: {
  metrics: [{ side: "left", term: "净值", fields: navFields.map((opt) => opt.value) }],
  scopes: [{ category: "净值型", fields: methods.map((opt) => opt.selection.field) }], open_questions: [],
}, rule_name: "净值空值核查", description: navRequest, preview: null,
  columns: [...columns, ...navFields.map(({ value, label }) => ({ column_name: value, comment: label, data_type: "numeric" })),
    ...methods.map(({ label, selection }) => ({ column_name: selection.field, comment: label, data_type: "varchar" }))],
  expression: { left: navFields[0].value, op: "is_null" }, questions: [navFieldQuestion, methodQuestion],
  filters: [{ ...methods[0].selection, confirmed: false }], uncertainties: [navFieldQuestion.uncertainty, methodQuestion.uncertainty] };
api.createAnalysis = async () => ({ status: "completed", result: scopedNav });
const requestOrder = [];
const previousPreview = api.preview;
api.preview = async (payload) => {
  requestOrder.push(payload.review_only ? "review" : "sql");
  if (payload.review_only) return { definition: payload.definition, ready: true, questions: [], uncertainties: [] };
  return previousPreview(payload);
};
allPreviews.length = 0;
await wb.open({ mode: "ai" });
const scopedInput = controlByLabel(wb.element, "需求描述 *");
scopedInput.value = navRequest;
await scopedInput.dispatch("input");
await findButton(wb.element, "✦ AI 分析").dispatch("click");
assert.match(collectText(wb.element), /有\s*2\s*个业务口径需要确认/);
const allChoices = findByClass(wb.element, "dv-business-questions");
const labeledChoice = (label) => collectByClass(allChoices, "dv-ai-choice").find((row) =>
  findByClass(row, "dv-ai-choice-title").textContent === label)?.children[0];
for (const label of ["运行方式", "原始运行方式", "单位净值", "累计净值"]) assert.ok(labeledChoice(label), label);
const commitChoices = findButton(wb.element, "确认全部口径");
assert.ok(commitChoices.disabled);
const originalMethod = labeledChoice("原始运行方式");
originalMethod.checked = true;
await originalMethod.dispatch("change");
assert.ok(commitChoices.disabled, "only one question has been answered");
assert.equal(collectByClass(wb.element, "dv-ai-option-card").length, 0);
assert.equal(requestOrder.length, 0);
const metricGroup = collectByClass(allChoices, "dv-business-question").find((group) =>
  collectByClass(group, "dv-ai-choice-title").some((title) => title.textContent === "单位净值"));
const allMetrics = findByClass(metricGroup, "dv-business-select-all");
allMetrics.checked = true;
await allMetrics.dispatch("change");
assert.deepEqual([labeledChoice("单位净值").checked, labeledChoice("累计净值").checked, originalMethod.checked], [true, true, true]);
assert.equal(commitChoices.disabled, false);
allMetrics.checked = false;
await allMetrics.dispatch("change");
assert.equal(commitChoices.disabled, true, "清空其中一组后立即禁止提交");
await commitChoices.dispatch("click");
assert.equal(requestOrder.length, 0);
allMetrics.checked = true;
await allMetrics.dispatch("change");
assert.equal(requestOrder.length, 0, "choosing fields never submits one question ahead of the rest");
await commitChoices.dispatch("click");
await sleep(30);
assert.deepEqual(requestOrder, ["review", "review", "sql", "sql"]);
assert.equal(collectByClass(wb.element, "dv-ai-option-card").length, 2);
assert.deepEqual(allPreviews.map((item) => item.expression.left), navFields.map((o) => o.value));
assert.deepEqual(allPreviews.map((item) => item.name), ["单位净值非空校验", "累计净值非空校验"], "每条方案预览与后续保存使用该字段的模型名称");
assert.ok(allPreviews.every((item) => item.filters.length === 1 && item.filters[0].field === "c_oper_mode_orig"
  && item.filters[0].confirmed && item.filters[0].value.join(",") === "1,3" && item.uncertainty_resolutions.every(Boolean)));
api.preview = previousPreview;
// 一个指标绑定到上下界两个位置。仅为勾选的指标各生成一条完整规则。
const fieldOptions = [
  { ...navFields[0], rule_name: "单位净值低于0.8或高于1.2校验" },
  { ...navFields[1], rule_name: "累计净值低于0.8或高于1.2校验" },
  { value: "estimated_nav", label: "估算净值", rule_name: "估算净值低于0.8或高于1.2校验" },
];
const navColumns = [...columns, ...fieldOptions.map(({ value, label }) => ({ column_name: value, comment: label, data_type: "numeric" }))];
const range = { logic: "any", conditions: [
  { left: "", op: "lt", right_type: "value", right: 0.8 },
  { left: "", op: "gt", right_type: "value", right: 1.2 },
] };
const rangeQuestion = { ...navFieldQuestion, id: "expression.conditions.0.left",
  targets: ["expression.conditions.0.left", "expression.conditions.1.left"], options: fieldOptions };
const grouped = { ...candidate, rule_name: "净值越界", expression: range, preview: null, columns: navColumns,
  questions: [rangeQuestion], uncertainties: [rangeQuestion.uncertainty], null_handling: { left: "review", right: "review" },
  null_policy: "review", include_result_fields: true };
api.createAnalysis = async () => ({ status: "completed", result: grouped });
api.preview = async ({ definition }) => {
  allPreviews.push(definition);
  return { ...candidate.preview, definition, columns: navColumns, questions: [], content_sha256: "range-" + allPreviews.length };
};
allPreviews.length = 0;
await wb.open({ mode: "ai" });
const groupedRequest = controlByLabel(wb.element, "需求描述 *");
groupedRequest.value = "净值低于 0.8 或高于 1.2";
await groupedRequest.dispatch("input");
await findButton(wb.element, "✦ AI 分析").dispatch("click");
assert.ok(choiceRows().every((row) => row.children[0].type === "checkbox"));
await chooseStatus(0);
await chooseStatus(2);
await findButton(wb.element, "确认当前口径").dispatch("click");
assert.equal(allPreviews.length, 2);
for (const [i, chosen] of [fieldOptions[0], fieldOptions[2]].entries()) {
  assert.deepEqual(allPreviews[i].expression, { logic: "any", conditions: range.conditions.map((item) => ({ ...item, left: chosen.value })) });
  assert.deepEqual(allPreviews[i].null_handling, grouped.null_handling);
  assert.ok(allPreviews[i].uncertainty_resolutions[0].includes(chosen.value));
}
assert.match(collectText(wb.element), /单位净值低于0.8或高于1.2校验/);

// 单规则的 AI 编辑会清掉旧 SQL / 测试证据，重新预览和测试收到用户修改后的整组。
const savedRange = allPreviews[0];
api.createAnalysis = async () => ({ status: "completed", result: { ...grouped, ...savedRange, questions: [], preview: null } });
await wb.open({ mode: "ai" });
const editRequest = controlByLabel(wb.element, "需求描述 *");
editRequest.value = "检查单位净值范围";
await editRequest.dispatch("input");
await findButton(wb.element, "✦ AI 分析").dispatch("click");
await findButton(wb.element, "生成 SQL 预览").dispatch("click");
const editGroup = findByClass(wb.element, "dv-condition-group");
const logic = controlByLabel(editGroup, "异常触发方式");
logic.value = "all";
await logic.dispatch("change");
const upper = controlByLabel(collectByClass(editGroup, "dv-condition-row")[1], "数值常量");
upper.value = "1.5";
await upper.dispatch("input");
assert.equal(findByClass(wb.element, "dv-ai-sql-preview"), null);
await findButton(wb.element, "生成 SQL 预览").dispatch("click");
const editedRange = allPreviews.at(-1);
assert.equal(editedRange.expression.logic, "all");
assert.deepEqual(editedRange.expression.conditions.map((item) => item.right), [0.8, 1.5]);
let tested;
api.testCandidate = async (payload) => {
  tested = payload.definition;
  return { content_sha256: payload.expected_hash, cases: [], passed_count: 0, failed_count: 0, not_run_count: 0 };
};
await findButton(wb.element, "生成并运行测试用例").dispatch("click");
assert.deepEqual(tested.expression, editedRange.expression);

// 已保存组在手工表单的初次加载、元数据刷新、修改与保存校验中均完整保留。
const manual = createRuleForm({ state, mode: "manual", listen: runtime.listen, user: { capabilities: ["dv.manage"] } });
manual.reset({ name: "净值越界", definition: savedRange });
manual.setMetadata({ mapping_version: "map-q", columns: navColumns });
assert.deepEqual(manual.validateForSave().expression, savedRange.expression);
assert.deepEqual(manual.read().null_handling, savedRange.null_handling);
const manualUpper = controlByLabel(collectByClass(manual.element, "dv-condition-row")[1], "数值常量");
manualUpper.value = "1.8";
await manualUpper.dispatch("input");
assert.deepEqual(manual.validateForSave().expression.conditions.map((item) => item.right), [0.8, 1.8]);
manual.setMetadata(null);
assert.deepEqual(manual.read().expression.conditions.map((item) => item.right), [0.8, 1.8]);
assert.throws(() => manual.validateForSave(), /真实表结构/);

// 旧候选同时携带已选指标/范围与模型留下的原话：后端在最后一次选择后重新核对。
const oldNotes = [
  "f_curr_performance为非净值型产品本期业绩表现是否即为净值；c_oper_mode取值2或4但需确认是否排除其他运行方式",
  "已采用单位净值f_netvalue但f_curr_performance也可能理解为净值",
  "非净值型筛选依据c_oper_mode取值为2或4，已按此范围执行，但需确认是否还需排除其他特殊状态",
];
const metric = { ...rangeQuestion, options: [{ value: "f_netvalue", label: "单位净值" }] };
const selectedScope = { field: "c_oper_mode", table: "base", op: "in", value: ["2", "4"], confirmed: true };
const scope = { id: "filters.0", text: "采用哪个运行方式？", uncertainty: "确认非净值型分类范围",
  options: [{ value: "group", label: "运行方式 2 或 4", selection: selectedScope }] };
const oldColumns = [...columns, { column_name: "f_netvalue", data_type: "numeric", comment: "单位净值" },
  { column_name: "c_oper_mode", data_type: "varchar", comment: "运行方式" }];
const emptyReason = "空值按 0 参与本次数值比较，0 不会命中校验条件。";
const separateReason = "字典另有独立的空值说明。";
let oldResult = { ...grouped, expression: range, columns: oldColumns, filters: [{ ...selectedScope, confirmed: false }],
  questions: [metric, scope], uncertainties: [metric.uncertainty, scope.uncertainty, ...oldNotes],
  null_evidence: [{ source: emptyReason }, { source: separateReason }, { source: emptyReason }],
  notices: [emptyReason, "独立提示"] };
let oldAnalysisCalls = 0;
api.createAnalysis = async () => { oldAnalysisCalls++; return { status: "completed", result: oldResult }; };
const rechecks = [];
const independent = "尚需确认合同截止日期采用到期日还是终止日";
api.preview = async ({ definition }) => {
  rechecks.push(definition);
  return { status: "needs_confirmation", definition: { ...definition, uncertainties: [independent], uncertainty_resolutions: [""] },
    questions: [], uncertainties: [independent], columns: oldColumns };
};
await runScopeAnalysis();
await answerCurrent();
assert.equal(rechecks.length, 0, "尚有已知的范围选择时继续展示它");
await answerCurrent();
assert.equal(rechecks.length, 1, "最后一个结构化答案完成后，旧自由文本不能挡住后端核对");
assert.deepEqual(rechecks[0].expression.conditions.map((item) => item.left), ["f_netvalue", "f_netvalue"]);
assert.deepEqual(rechecks[0].filters, [selectedScope]);
assert.deepEqual(rechecks[0].uncertainties.slice(2), oldNotes);
assert.ok(rechecks[0].uncertainty_resolutions.slice(0, 2).every(Boolean));
assert.ok(rechecks[0].uncertainty_resolutions.slice(2).every((item) => item === ""));
assert.match(collectText(wb.element), /尚需确认合同截止日期/);
assert.ok(!collectText(wb.element).includes(oldNotes[0]));
assert.equal(findByClass(wb.element, "dv-ai-sql-preview"), null);
await sleep(50);
assert.equal(rechecks.length, 1, "后端仍有独立问题时不得自动重复核对");

// 加载只有残留文本的旧候选：手动重新核对沿用原定义，没有额外的分析调用。
const dictionaryQuestion = { table: "project_report", field: "c_oper_mode", category: "非净值型" };
oldResult = { ...oldResult, ...rechecks[0], questions: [], null_evidence: oldResult.null_evidence,
  pending_dictionary_questions: [dictionaryQuestion] };
api.preview = async ({ definition, pending_dictionary_questions }) => {
  assert.deepEqual(pending_dictionary_questions, [dictionaryQuestion]);
  rechecks.push(definition);
  return { ...candidate.preview, definition: { ...definition, uncertainties: [], uncertainty_resolutions: [] },
    questions: [], columns: oldColumns };
};
await runScopeAnalysis();
const countBeforeRetry = oldAnalysisCalls;
await findButton(wb.element, "重新核对已选口径").dispatch("click");
assert.equal(oldAnalysisCalls, countBeforeRetry);
assert.equal(rechecks.length, 2);
assert.ok(findByClass(wb.element, "dv-ai-sql-preview"));
assert.equal(collectText(wb.element).split(emptyReason).length, 2, "同一空值解释仅展示一次");
assert.ok(collectText(wb.element).includes(separateReason));
assert.ok(collectText(wb.element).includes("独立提示"));
runtime.destroy();
console.log(JSON.stringify({ ok: true, assertions: "preview/questions-merge/staged/backend-metadata/scope-memory/numbered-steps/knowledge-settings" }));
