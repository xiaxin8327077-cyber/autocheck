import assert from "node:assert/strict";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { createBusinessQuestionsPanel } from "./components/business_questions.mjs";
import { FakeElement, collectByClass, collectText, controlByLabel, findButton } from "./frontend_workbench_dom.mjs";

const state = createState();
state.sources = [{ id: "src", name: "项目", dialect: "mysql" }];
state.models = [{ id: "model", name: "模型", is_default: true }];
state.categories = [{ code: "group:pbc", name: "人行" }];
state.sourcesStatus = state.modelsStatus = state.categoriesStatus = "success";
const runtime = createRuntime({ notify() {} });
runtime.activate();
const fields = ["kind", "kind2"];
const scope = { category: "净值型", fields };
const dictionary = [{ value: "1", label: "开放式净值型" }, { value: "3", label: "封闭式净值型" }];
const choices = fields.map((field, index) => ({ value: String(index), label: `运行方式${index + 1}（${field}）`,
  selection: { table: "base", field, op: "in", value: ["1","3"], confirmed: true } }));
const question = { id: "filters.0", text: "采用哪个运行方式？", uncertainty: "范围", options: choices };
const cols = ["id","period","nav","total",...fields].map((column_name) => ({ column_name, data_type: "numeric",
  comment: ({ kind: "运行方式", kind2: "运行方式_原始" })[column_name] || "" }));
function option(name, patch) {
  const candidate = { rule_type: "field_compare", rule_name: name, source_id: "src", dialect: "mysql",
    report_category: "group:pbc", table_name: "products", mapping_version: "doc-v2", analysis_protocol: 2,
    semantic_intent: { scopes: [scope], dictionary_snapshots: { base: { kind: dictionary, kind2: dictionary } } },
    questions: [question], uncertainties: ["范围"],
    filters: [{ ...choices[0].selection, confirmed: false }], columns: cols,
    expression: { left: name, op: "is_null" }, business_key: "id", report_date_field: "period",
    null_policy: "violate", equality_policy: "allow_equal", violation_message: "缺值", ...patch };
  return { id: name, label: name, recommended: true, candidate };
}
const next = { id: "report_category", text: "再次确认报送分类", options: [{ value: "group:pbc", label: "人行" }] };
let result, discover, failOnce, extraQuestion;
let inspectSaving;
let rejectStoredTest = false;
const requests = [];
const calls = [];
const savedBatches = [];
const singleSaves = [];
const activations = [];
const savedRules = new Map();
const sample = { name: "样本", row: { nav: null }, expected_count: 1, actual_count: 1, status: "passed" };
const definitionHash = (definition) => JSON.stringify([definition.name, definition.expression, definition.filters]);
function storeRule(definition) {
  const rule = { id: savedRules.size + 1, rule_code: `R${savedRules.size + 1}`, name: definition.name,
    version_no: 1, definition, generation_mode: "ai", content_sha256: definitionHash(definition) };
  savedRules.set(rule.id, rule);
  return rule;
}
const api = {
  createAnalysis: async (payload) => { requests.push(payload); return { status: "completed", analysis_id: "a", result }; },
  preview: async ({ definition, review_only }) => {
    calls.push([review_only ? "review" : "sql", definition]);
    if (failOnce) { failOnce = false; throw new Error("文档读取失败"); }
    if (review_only && extraQuestion) {
      return { status: "needs_confirmation", ready: false, questions: [extraQuestion], definition, columns: cols };
    }
    if (review_only && discover && definition.expression.left === "total") {
      discover = false;
      return { status: "needs_confirmation", ready: false, questions: [next], definition, columns: cols };
    }
    if (review_only) return { status: "ready", ready: true, definition, questions: [], columns: cols };
    return { sql_preview: "SELECT 1", content_sha256: definitionHash(definition), definition, questions: [], columns: cols, cases: [sample] };
  },
  testCandidate: async ({ expected_hash }) => ({ content_sha256: expected_hash, cases: [sample],
    passed_count: 1, failed_count: 0, not_run_count: 0 }),
  batchSaveCandidates: async (payload) => {
    await inspectSaving?.();
    savedBatches.push(payload);
    return { rules: payload.definitions.map(storeRule) };
  },
  save: async (definition, id) => {
    singleSaves.push(id);
    if (!id) return storeRule(definition);
    const old = savedRules.get(id);
    const rule = { ...old, definition, version_no: old.version_no + 1 };
    savedRules.set(id, rule);
    return rule;
  },
  rule: async (id) => savedRules.get(id),
  test: async (id, { version_no }) => {
    if (rejectStoredTest) throw new Error("测试服务暂不可用");
    return { content_sha256: savedRules.get(id).content_sha256, version_no,
      cases: [sample], passed_count: 1, failed_count: 0, not_run_count: 0 };
  },
  confirm: async (id) => { activations.push(id); },
};
const host = new FakeElement("div");
const notices = [];
const wb = createWorkbench({ state, runtime, api, listen: runtime.listen, user: { role: "admin" },
  notify(message) { notices.push(message); }, host, confirmAction: async () => true });
const rows = () => collectByClass(wb.element, "dv-ai-choice");
const cards = () => collectByClass(wb.element, "dv-ai-option-card").length;
async function select(i) {
  const input = rows()[i].children[0]; input.checked = true; await input.dispatch("change");
}
async function unselect(i) {
  const input = rows()[i].children[0]; input.checked = false; await input.dispatch("change");
}
async function start(patch, firstPatch, single = false) {
  calls.length = 0;
  result = { candidate_options: single ? [option("nav", firstPatch)] : [option("nav", firstPatch), option("total", patch)] };
  await wb.open({ mode: "ai" });
  const input = controlByLabel(wb.element, "需求描述 *"); input.value = "净值型项目的净值不得为空";
  await input.dispatch("input");
  await findButton(wb.element, "✦ AI 分析").dispatch("click");
  assert.equal(cards(), 0, "所有疑问答完前不显示方案");
  assert.deepEqual(calls, []);
}
await start();
assert.equal(rows().length, 2, "完全相同的分类范围只问一次");
assert.match(collectText(wb.element), /nav、total/);
assert.ok(rows().every((row) => row.children[0].type === "checkbox"));
assert.deepEqual(collectByClass(wb.element, "dv-business-field-code").map(collectText), fields);
assert.deepEqual(collectByClass(wb.element, "dv-business-shared-dictionary").map(collectText), ["1＝开放式净值型 · 3＝封闭式净值型"]);
const footer = collectByClass(host, "dv-dialog-footer")[0];
assert.ok(findButton(footer, "确认全部口径"), "确认操作固定在弹窗底栏");
assert.match(collectText(footer), /已完成 0 \/ 1 项口径/);
await collectByClass(host, "dv-overlay")[0].dispatch("click");
assert.ok(wb.isOpen(), "口径选择期间点击遮罩不关闭弹窗");
await select(1);
discover = true;
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.ok(calls.every(([action]) => action === "review"));
assert.equal(cards(), 0);
assert.match(collectText(wb.element), /再次确认报送分类/);
assert.equal(rows()[0].children[0].type, "radio", "报送分类等其他口径沿用当前选择方式");
await select(0);
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(cards(), 2);
const compiled = calls.filter(([action]) => action === "sql");
assert.equal(compiled.length, 2);
assert.ok(compiled.every(([, definition]) => definition.filters[0].field === "kind2"));

const analysesBeforeReselect = requests.length;
const previewsBeforeReselect = calls.length;
const reselect = findButton(wb.element, "重新选择口径");
assert.ok(reselect && !reselect.hidden, "生成方案后可返回选择业务口径");
await findButton(wb.element, "生成并运行测试用例").dispatch("click");
assert.equal(findButton(wb.element, "保存并启动以上2个方案").disabled, false, "旧方案测试已通过");
await reselect.dispatch("click");
assert.equal(cards(), 0, "返回时移除旧方案");
assert.equal(calls.length, previewsBeforeReselect, "返回选择不请求预览");
assert.equal(requests.length, analysesBeforeReselect, "返回不调用模型");
assert.deepEqual(rows().map((row) => row.children[0].checked), [false, true], "恢复原始候选及上次勾选");
assert.ok(findButton(wb.element, "保存并启用").hidden);
await select(0);
await unselect(1);
discover = true;
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(cards(), 0, "新口径仍须逐步复核后续问题");
assert.equal(rows()[0].children[0].checked, true, "相同的后续问题保留上次选择");
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(cards(), 2);
assert.ok(calls.filter(([action]) => action === "sql").slice(-2)
  .every(([, definition]) => definition.filters[0].field === "kind"), "按新选择重新编译");
assert.equal(requests.length, analysesBeforeReselect, "重新确认只复核文档和生成 SQL");
assert.ok(findButton(wb.element, "保存并启动以上2个方案").disabled, "新方案不能沿用旧测试结果启用");
await reselect.dispatch("click");
assert.deepEqual(rows().map((row) => row.children[0].checked), [true, false], "多次返回保留最近一次已确认选择");
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(cards(), 2);

const requestInput = controlByLabel(wb.element, "需求描述 *");
requestInput.value = "修改后的需求";
await requestInput.dispatch("input");
assert.ok(reselect.hidden || reselect.disabled, "需求变化后不能返回旧分析的口径");
await reselect.dispatch("click");
assert.equal(cards(), 2, "过期入口不应改动当前结果");

await start();
await select(0);
await findButton(wb.element, "确认全部口径").dispatch("click");
const batchReturn = findButton(wb.element, "重新选择口径");
inspectSaving = async () => {
  assert.equal(batchReturn.disabled, true, "保存期间禁止返回");
  await batchReturn.dispatch("click");
  assert.equal(cards(), 2, "禁用入口也由处理函数防护，不中断保存");
};
await findButton(wb.element, "保存所选 2 条草稿").dispatch("click");
inspectSaving = null;
const savedCount = savedBatches.length;
const originalSaved = JSON.stringify([...savedRules]);
await batchReturn.dispatch("click");
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(findButton(wb.element, "保存所选 2 条草稿").disabled, true, "相同口径重选后仍识别已保存草稿");
await findButton(wb.element, "保存所选 2 条草稿").dispatch("click");
assert.equal(savedBatches.length, savedCount, "相同方案不重复创建");
await findButton(wb.element, "生成并运行测试用例").dispatch("click");
const changedStored = [...savedRules.values()].find((rule) => rule.definition.expression.left === "nav");
const storedHash = changedStored.content_sha256;
changedStored.content_sha256 = "other-window-version";
await findButton(collectByClass(wb.element, "dv-ai-option-card")[0], "保存当前方案并启用").dispatch("click");
assert.equal(activations.length, 0, "其他窗口修改已保存规则后，不能按本页旧预览启用新版本");
assert.match(notices.at(-1), /已保存规则版本已变化/);
changedStored.content_sha256 = storedHash;
await batchReturn.dispatch("click");
await select(1);
await unselect(0);
await findButton(wb.element, "确认全部口径").dispatch("click");
await findButton(wb.element, "保存所选 2 条草稿").dispatch("click");
assert.equal(savedBatches.length, savedCount + 1, "新口径可保存新草稿");
assert.equal(JSON.stringify([...savedRules].slice(0, JSON.parse(originalSaved).length)), originalSaved, "重选不修改原草稿或已启用规则");

await start();
await select(0);
await findButton(wb.element, "确认全部口径").dispatch("click");
await findButton(wb.element, "生成并运行测试用例").dispatch("click");
rejectStoredTest = true;
await findButton(collectByClass(wb.element, "dv-ai-option-card")[0], "保存当前方案并启用").dispatch("click");
rejectStoredTest = false;
const afterFailedEnable = singleSaves.length;
const onlySavedId = [...savedRules.keys()].at(-1);
await findButton(wb.element, "重新选择口径").dispatch("click");
await findButton(wb.element, "确认全部口径").dispatch("click");
await findButton(wb.element, "保存所选 2 条草稿").dispatch("click");
assert.equal(singleSaves.length, afterFailedEnable);
assert.equal(savedBatches.at(-1).definitions.length, 1, "保存成功而启用失败的草稿仍复用，不重复创建");
assert.ok(savedRules.has(onlySavedId));

await start(null, { description: "模型组织的完整规则摘要" }, true);
await select(1);
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(cards(), 0, "单方案使用独立详情界面");
const singleReturn = findButton(wb.element, "重新选择口径");
assert.equal(singleReturn.hidden, false);
await findButton(wb.element, "保存草稿").dispatch("click");
assert.equal(singleSaves.at(-1), null);
assert.equal(singleReturn.hidden, false, "保存规则摘要后仍保留原需求和返回入口");
const originalSingle = JSON.stringify([...savedRules]);
const originalSingleSaveCount = singleSaves.length;
await singleReturn.dispatch("click");
await findButton(wb.element, "确认全部口径").dispatch("click");
await findButton(wb.element, "保存草稿").dispatch("click");
assert.equal(singleSaves.length, originalSingleSaveCount, "单方案重选同定义后保存复用现有规则，不追加版本");
assert.equal(JSON.stringify([...savedRules]), originalSingle);
await findButton(wb.element, "生成并运行测试用例").dispatch("click");
await findButton(wb.element, "保存并启用").dispatch("click");
assert.equal(singleSaves.length, originalSingleSaveCount, "同口径启用重新读取和测试已有版本，不写入新版本");
assert.equal(activations.length, 1);
assert.equal(wb.isOpen(), false);

await start(null, null, true);
await select(1);
await findButton(wb.element, "确认全部口径").dispatch("click");
await findButton(wb.element, "保存草稿").dispatch("click");
await findButton(wb.element, "重新选择口径").dispatch("click");
assert.deepEqual(rows().map((row) => row.children[0].checked), [false, true]);
await select(0);
await unselect(1);
await findButton(wb.element, "确认全部口径").dispatch("click");
await findButton(wb.element, "保存草稿").dispatch("click");
assert.equal(singleSaves.at(-1), null, "单方案改变口径后保存新草稿，不更新原规则");

await findButton(wb.element, "重新选择口径").dispatch("click");
extraQuestion = { id: "supplement.0", text: "需要补充文档依据", options: [] };
const beforeExtra = requests.length;
await findButton(wb.element, "确认全部口径").dispatch("click");
const extra = collectByClass(wb.element, "dv-business-question").flatMap((group) => group.children)
  .find((node) => node.tagName === "TEXTAREA");
extra.value = "其他说明";
await extra.dispatch("input");
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(requests.length, beforeExtra, "重选复核遇到缺少依据时不自动重新调用模型");
assert.match(notices.at(-1), /修改需求后重新分析/);
extraQuestion = null;

await start(null, { expression: { logic: "any", conditions: [
  { left: "nav", op: "lt", right_type: "value", right: 0 },
  { left: "nav", op: "gt", right_type: "value", right: 1 },
] } }, true);
await select(0);
await findButton(wb.element, "确认全部口径").dispatch("click");
await findButton(wb.element, "保存草稿").dispatch("click");
const beforeGroupEdits = singleSaves.length;
const groupSavedBefore = JSON.stringify([...savedRules]);
await findButton(wb.element, "重新选择口径").dispatch("click");
await findButton(wb.element, "确认全部口径").dispatch("click");
async function editUpper(value) {
  const row = collectByClass(wb.element, "dv-condition-row")[1];
  const upper = controlByLabel(row, "数值常量");
  upper.value = String(value);
  await upper.dispatch("input");
  await findButton(wb.element, "生成 SQL 预览").dispatch("click");
}
await editUpper(2);
await findButton(wb.element, "保存草稿").dispatch("click");
assert.equal(singleSaves.at(-1), null, "同口径重选后编辑组合条件，保存新定义不得覆盖原规则");
assert.equal(JSON.stringify([...savedRules].slice(0, JSON.parse(groupSavedBefore).length)), groupSavedBefore);
const afterGroupSave = singleSaves.length;
await findButton(wb.element, "保存草稿").dispatch("click");
assert.equal(singleSaves.length, afterGroupSave, "重选后新保存的定义仍可复用，不重复创建");
await editUpper(3);
await findButton(wb.element, "生成并运行测试用例").dispatch("click");
await findButton(wb.element, "保存并启用").dispatch("click");
assert.deepEqual(singleSaves.slice(beforeGroupEdits), [null, null], "编辑组合条件的保存及启用都创建独立草稿");

const otherDictionary = [{ value: "A", label: "开放式净值型" }, { value: "C", label: "封闭式净值型" }];
await start();
await select(0);
await select(1);
await findButton(wb.element, "确认全部口径").dispatch("click");
const namedDefinitions = calls.filter(([action]) => action === "sql").map(([, definition]) => definition);
assert.equal(cards(), 4);
assert.deepEqual(namedDefinitions.map(({ name }) => name), [
  "nav · 运行方式", "nav · 运行方式_原始", "total · 运行方式", "total · 运行方式_原始",
], "筛选字段展开使用文档中文名，四种组合名称清晰区分");
await findButton(wb.element, "保存所选 4 条草稿").dispatch("click");
assert.deepEqual([...savedRules.values()].slice(-4).map(({ name }) => name), namedDefinitions.map(({ name }) => name),
  "保存回读保留生成的中文范围名称");

const differingChoices = [choices[0], { ...choices[1], selection: { ...choices[1].selection, value: ["A", "C"] } }];
await start({ questions: [{ ...question, options: differingChoices }], semantic_intent: { scopes: [scope],
  dictionary_snapshots: { base: { kind: dictionary, kind2: otherDictionary } } } });
assert.deepEqual(collectByClass(rows()[2], "dv-business-dictionary").map(collectText), ["1＝开放式净值型 · 3＝封闭式净值型"]);
assert.deepEqual(collectByClass(rows()[3], "dv-business-dictionary").map(collectText), ["A＝开放式净值型 · C＝封闭式净值型"]);
await select(0);
await select(2);
await select(3);
assert.deepEqual(rows().map((row) => row.children[0].checked), [true, false, true, true]);
assert.match(collectText(wb.element), /已完成 2 \/ 2 项口径/);
assert.deepEqual(calls, [], "全部确认前不调用复核或 SQL 预览");
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.deepEqual(calls.map(([action]) => action), ["review", "review", "review", "sql", "sql", "sql"]);
assert.equal(cards(), 3);
assert.deepEqual(calls.filter(([action]) => action === "sql").map(([, definition]) => ({
  metric: definition.expression.left,
  filters: definition.filters.map(({ field, value }) => [field, value]),
})), [
  { metric: "nav", filters: [["kind", ["1", "3"]]] },
  { metric: "total", filters: [["kind", ["1", "3"]]] },
  { metric: "total", filters: [["kind2", ["A", "C"]]] },
]);

for (const patch of [{ table_name: "other" }, { source_id: "other" }, { report_category: "other" },
  { mapping_version: "other" }, { semantic_intent: { scopes: [{ ...scope, category: "另一分类" }] } },
  { questions: [{ ...question, options: choices.map((o) => ({ ...o, selection: { ...o.selection, value: ["2","3"] } })) }] }]) {
  await start(patch);
  assert.equal(rows().length, 4, "不同依据的分类分别确认");
  await select(0);
  assert.ok(findButton(wb.element, "确认全部口径").disabled);
}
await start();
await select(1);
failOnce = true;
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(cards(), 0);
await findButton(wb.element, "重试生成预览").dispatch("click");
assert.equal(cards(), 2);

await start({ uncertainties: ["范围","是否另需合同截止日？"] }, undefined, false);
await select(1);
const free = collectByClass(wb.element, "dv-business-question").flatMap((group) => group.children)
  .find((node) => node.tagName === "TEXTAREA");
free.value = "没有";
await free.dispatch("input");
await findButton(wb.element, "确认全部口径").dispatch("click");
const supplement = requests.at(-1);
assert.equal(supplement.request_text, "净值型项目的净值不得为空");
assert.equal(controlByLabel(wb.element, "需求描述 *").value, supplement.request_text);
assert.equal(supplement.reasoning_enabled, false, "补充分析也不得重新开启推理");
assert.ok(supplement.clarification_answers.some(item => item.question === "是否另需合同截止日？" && item.answer === "没有"));
assert.ok(supplement.clarification_answers.some(item => item.question_id === "filters.0" && item.answer.includes("kind2")));
assert.equal(calls.length, 0);
await select(0);
const followup = collectByClass(wb.element, "dv-business-question").flatMap((group) => group.children)
  .find((node) => node.tagName === "TEXTAREA");
followup.value = "单独核对合同记录";
await followup.dispatch("input");
await findButton(wb.element, "确认全部口径").dispatch("click");
const repeated = requests.at(-1);
assert.equal(repeated.request_text, supplement.request_text);
assert.equal(repeated.clarification_answers.length, supplement.clarification_answers.length);
assert.deepEqual(repeated.clarification_answers.filter(item => item.question === "是否另需合同截止日？").map(item => item.answer),
  ["单独核对合同记录"]);
await findButton(wb.element, "修改需求").dispatch("click");
const editedText = controlByLabel(wb.element, "需求描述 *");
editedText.value += "，同时核对日期";
await editedText.dispatch("input");
await findButton(wb.element, "应用修改 →").dispatch("click");
assert.deepEqual(requests.at(-1).clarification_answers || [], []);

const manyFields = Array.from({ length: 14 }, (_, i) => `kind${i + 1}`);
const manyChoices = manyFields.map((field, i) => ({ value: String(i), label: field,
  selection: { table: "base", field, op: "in", value: ["1", "3"], confirmed: true } }));
const many = { semantic_intent: { scopes: [{ ...scope, fields: manyFields }] },
  questions: [{ ...question, options: manyChoices }],
  columns: [...cols, ...manyFields.map((column_name) => ({ column_name, data_type: "numeric" }))] };
await start(many, many);
const allScopes = collectByClass(wb.element, "dv-business-select-all")[0];
allScopes.checked = true;
await allScopes.dispatch("change");
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.match(notices.at(-1), /超过 26 个方案/);
assert.equal(calls.length, 0, "组合超限时尚未发送复核或预览请求");
assert.equal(cards(), 0);

const defaultAnswers = [];
const defaults = createBusinessQuestionsPanel({ listen: runtime.listen, onConfirm: async (answers) => defaultAnswers.push(answers) });
const recommendedItems = [
  { key: "scope", multiple: true, question: { ...question, options: [
    { ...choices[0], tag: "模型建议" }, choices[1],
  ] } },
  { key: "metric", multiple: true, question: { id: "expression.left", text: "选择净值字段", options: [
    { value: "nav", label: "单位净值", tag: "模型推荐" }, { value: "total", label: "累计净值" },
  ] } },
];
defaults.update(recommendedItems);
const defaultInputs = () => collectByClass(defaults.element, "dv-ai-choice").map((row) => row.children[0]);
assert.deepEqual(defaultInputs().map((input) => input.checked), [true, false, true, false], "首次展示默认勾选模型建议");
assert.deepEqual(collectByClass(defaults.element, "dv-ai-choice-tail").map(collectText), ["模型建议", "模型建议"]);
assert.equal(defaults.submit.disabled, false);
assert.equal(defaultAnswers.length, 0, "默认勾选仍等待用户点击确认");
await defaults.submit.dispatch("click");
assert.deepEqual(defaultAnswers[0].get("scope"), [choices[0].selection]);
assert.deepEqual(defaultAnswers[0].get("metric"), ["nav"]);
defaultInputs()[0].checked = false;
await defaultInputs()[0].dispatch("change");
defaults.update(recommendedItems, { busy: true });
defaults.update([...recommendedItems, { key: "extra", question: next }]);
assert.equal(defaultInputs()[0].checked, false, "重绘及新增问题保留用户取消勾选");
assert.equal(defaultInputs()[2].checked, true);
assert.equal(defaults.submit.disabled, true);
defaults.clear();
defaults.update(recommendedItems);
assert.equal(defaultInputs()[0].checked, true, "重新分析后按新建议初始化");
defaults.clear();
defaults.update(recommendedItems.map((item) => ({ ...item, value: [] })));
assert.deepEqual(defaultInputs().map((input) => input.checked), [false, false, false, false], "显式传入空选择优先于默认建议");
defaults.clear();
const metricQuestion = { ...recommendedItems[1].question, uncertainty: "选择净值字段" };
for (const confirmSelection of [false, true]) {
  await start(null, { questions: [metricQuestion], uncertainties: [metricQuestion.text], filters: [],
    semantic_intent: { metrics: [{ term: "净值", side: "left", fields: ["nav", "total"] }], scopes: [] } }, true);
  assert.equal(rows()[0].children[0].checked, true, "模型建议在确认前已预填");
  if (confirmSelection) {
    await unselect(0);
    await select(1);
    await findButton(wb.element, "确认全部口径").dispatch("click");
    assert.equal(calls.at(-1)?.[0], "sql", "已选指标完成文档复核并生成预览");
  }
  await findButton(wb.element, "修改需求").dispatch("click");
  const input = controlByLabel(wb.element, "需求描述 *");
  input.value += "，同时不得小于0";
  await input.dispatch("input");
  await findButton(wb.element, "应用修改 →").dispatch("click");
  const revision = requests.at(-1);
  assert.equal(revision.revision_of, "a");
  if (confirmSelection) assert.equal(revision.revised_definition.expression.left, "total");
  else assert.equal(revision.revised_definition, undefined, "确认前修改需求不得提交预填指标为个人选择");
}
const evidenceQuestion = { id: "evidence/1/scopes/base/-/0/kind",
  text: "是否按项目分类筛选净值型项目？", requires_analysis: true,
  options: [{ label: "采用项目分类", value: "products.kind" }] };
await start(null, { rule_type: null, expression: {}, questions: [evidenceQuestion],
  uncertainties: [evidenceQuestion.text], filters: [] }, true);
const priorRequests = requests.length;
await select(0);
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.equal(requests.length, priorRequests + 1, "尚无可预览规则的字段选择提交给语义分析");
assert.equal(calls.length, 0);
assert.equal(requests.at(-1).clarification_answers[0].answer, "采用项目分类（products.kind）");
const formulaChoices = [{ value: "nav", label: "当期值" }, { value: "total", label: "累计值" }];
const makeSlot = (path, text) => ({ id: "expression.right." + path + ".field", text, uncertainty: text, options: formulaChoices });
const slots = [makeSlot("left", "分子取哪项数值？"), makeSlot("right.left", "分母取哪项数值？")];
const equation = { left: "total", op: "neq", right_type: "formula",
  right: { op: "/", left: { field: "total" }, right: { op: "-", left: { field: "nav" }, right: { value: 2 } } } };
await start(null, { expression: equation, questions: slots, uncertainties: slots.map((slot) => slot.text),
  filters: [], null_policy: "skip", semantic_intent: { metrics: [], scopes: [] } }, true);
assert.equal(rows().length, 4, "公式内各个位置的字段候选分别确认");
await select(0); await select(3);
await findButton(wb.element, "确认全部口径").dispatch("click");
const bound = structuredClone(equation);
bound.right.left.field = "nav"; bound.right.right.left.field = "total";
assert.deepEqual(calls.at(-1)[1].expression, bound);
let testedFormula;
const runFormulaSample = api.testCandidate;
api.testCandidate = (payload) => { testedFormula = payload.definition.expression; return runFormulaSample(payload); };
await findButton(wb.element, "生成并运行测试用例").dispatch("click");
assert.deepEqual(testedFormula, bound);
await findButton(wb.element, "保存草稿").dispatch("click");
assert.deepEqual([...savedRules.values()].at(-1).definition.expression, bound);

const relatedChoices = choices.map((choice) => ({ ...choice, selection: { ...choice.selection, table: "related" } }));
await start(null, { semantic_intent: { scopes: [{ ...scope, table: "related" }] },
  questions: [{ ...question, options: relatedChoices }],
  filters: [{ ...relatedChoices[0].selection, confirmed: false }],
  join: { table_name: "contracts", on: [{ left: "id", right: "id" }], report_date_field: "period",
    relationship_confirmed: true, unmatched_policy: "exclude" },
  related_columns: cols.map((column) => ({ ...column, comment: fields.includes(column.column_name)
    ? `明细${column.comment}` : column.comment })) }, true);
await select(0); await select(1);
await findButton(wb.element, "确认全部口径").dispatch("click");
assert.deepEqual(calls.filter(([action]) => action === "sql").map(([, definition]) => definition.name),
  ["nav · 明细运行方式", "nav · 明细运行方式_原始"], "同名物理字段按所选表的元数据取中文名");
runtime.destroy();
