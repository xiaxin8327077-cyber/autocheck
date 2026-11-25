import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { FakeElement, collectByClass, collectText, controlByLabel, findButton } from "./frontend_workbench_dom.mjs";

const fixture = JSON.parse(readFileSync(process.argv[2], "utf8"));
const state = createState();
state.sourcesStatus = state.categoriesStatus = state.modelsStatus = "success";
state.sources = [{ id: "src", name: "监管报表", dialect: "postgresql" }];
state.models = [{ id: "model-1", name: "模型", is_default: true }];
state.categories = [{ code: "group:pbc", name: "人行" }];
const host = new FakeElement("div");
const runtime = createRuntime({ notify: message => assert.fail(message) });
runtime.activate();
const schedule = runtime.setTimer;
runtime.setTimer = (callback, delay) => schedule(callback, delay === 3000 ? 0 : delay);
const requests = [];
const cancelled = [];
const samples = [];
let batch;
let resolveLate;
const api = {
  async createAnalysis(payload) {
    const results = fixture.pending ? [fixture.result, fixture.pending, fixture.child] : [fixture.result, fixture.child];
    const result = results[requests.length];
    requests.push(payload);
    if (fixture.late && requests.length === 2) return await new Promise(resolve => { resolveLate = resolve; });
    if (fixture.failure && requests.length === 2) {
      return { analysis_id: "analysis-2", status: "failed", error: { code: "MODEL_UNAVAILABLE" } };
    }
    return { analysis_id: requests.length === 1 ? (fixture.parentAnalysisId || "analysis-1") : "analysis-" + requests.length, status: result ? "completed" : "running", result };
  },
  async cancelAnalysis(id) {
    cancelled.push(id);
    return fixture.cancelSnapshot || { status: "cancelled" };
  },
  async testCandidate(payload) {
    samples.push(payload);
    const cases = payload.cases.map(c => ({ ...c, actual_count: c.expected_count, status: "passed" }));
    return { cases, content_sha256: payload.expected_hash, passed_count: cases.length, failed_count: 0, not_run_count: 0 };
  },
  save: () => assert.fail("采纳不能保存规则"),
  batchSaveCandidates: async payload => {
    batch = payload;
    // Python consumes this exact request at the real in-memory batch route.
    // Stop the UI simulation at the save boundary without confirming saved rules.
    throw Object.assign(new Error("已记录批量保存请求"), { status: 400, payload: { error: { code: "VALIDATION_ERROR" } } });
  },
  confirm: () => assert.fail("采纳不能启用规则"),
  run: () => assert.fail("采纳不能执行规则"),
};
const wb = createWorkbench({ state, runtime, api, listen: runtime.listen, host,
  user: { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] },
  notify: () => {}, onClose: () => {}, onChanged: async () => {}, confirmAction: () => assert.fail("不应请求启用"),
});
await wb.open({ mode: "ai" });
const original = wb.element;
const text = controlByLabel(original, "需求描述 *");
text.value = fixture.result.description;
await text.dispatch("input");
await controlByLabel(original, "数据源 *").dispatch("change");
await controlByLabel(original, "启用模型").dispatch("change");
assert.equal(collectByClass(original, "dv-ai-reasoning-switch").length, 0, "需求栏不得保留推理开关");
await findButton(original, "✦ AI 分析").dispatch("click");
if (fixture.confirmationOnly) {
  assert.equal(collectByClass(original, "dv-ai-supplement").length, 0, "口径确认阶段不显示补充建议");
  writeFileSync(process.argv[3], JSON.stringify({}));
  wb.close(); runtime.destroy(); process.exit(0);
}
if (fixture.child || fixture.cancelSnapshot) {
  for (const input of collectByClass(original, "dv-ai-option-check")) {
    if (input.checked) continue;
    const current = collectByClass(original, "dv-ai-option-check").find(el => el.dataset.optionId === input.dataset.optionId);
    current.checked = true;
    await current.dispatch("change");
  }
  await findButton(original, "生成并运行测试用例").dispatch("click");
  assert.equal(samples.length, 2);
  samples.length = 0;
}
if (fixture.scopeReview === "separate") {
  const check = collectByClass(original, "dv-ai-option-check").find(el => el.dataset.optionId === "alternate-filter");
  check.checked = true;
  await check.dispatch("change");
}
if (fixture.scopeReview === "none") {
  for (const input of collectByClass(original, "dv-ai-option-check").filter(el => el.checked)) {
    input.checked = false;
    await input.dispatch("change");
  }
  assert.ok(collectByClass(original, "dv-ai-option-check").every(el => !el.checked));
}
assert.ok(!findButton(original, "按原条件采纳"));
assert.ok(!findButton(original, "独立分析"));
const card = collectByClass(original, "dv-ai-supplement")[0];
const adopt = findButton(card, "采纳");
if (fixture.scopeReview === "none") {
  assert.ok(!adopt || adopt.disabled, "没有勾选已预览方案时不能采纳");
  writeFileSync(process.argv[3], JSON.stringify({}));
  wb.close(); runtime.destroy(); process.exit(0);
}
assert.ok(adopt && !adopt.disabled);
const cardText = collectText(card);
if (fixture.result.ai_suggestions[0].applicability_dictionary) assert.ok(cardText.includes("项目状态") && cardText.includes("存续"), cardText);
for (const note of fixture.result.ai_suggestions[0].preconditions) assert.ok(cardText.includes(note));
assert.ok(cardText.includes("系统已核对文档引用"));
if (fixture.late) {
  const pendingClick = adopt.dispatch("click");
  for (let i = 0; i < 20 && !resolveLate; i++) await Promise.resolve();
  assert.ok(resolveLate, "补充分析请求应进入在途状态");
  if (fixture.late.startsWith("changed")) {
    text.value += "（修改需求）";
    await text.dispatch("input");
  } else wb.close();
  resolveLate({ analysis_id: "analysis-2", status: fixture.late.endsWith("running") ? "running" : "completed", result: fixture.child });
  await pendingClick;
  assert.equal(collectByClass(original, "dv-ai-option-card").length, fixture.result.candidate_options.length, "关闭后迟到结果不能追加方案");
  assert.deepEqual(cancelled, fixture.late.endsWith("running") ? ["analysis-2"] : [], "迟到的在途任务必须取消");
  writeFileSync(process.argv[3], JSON.stringify({}));
  wb.close(); runtime.destroy(); process.exit(0);
}
await adopt.dispatch("click");
let child = collectByClass(card, "dv-ai-supplement-inline")[0];
if (!fixture.child || fixture.pending) {
  assert.ok(child, "采纳过程应显示在建议卡片内");
  assert.equal(collectByClass(host, "dv-workbench-dialog").length, 1, "采纳不得打开子弹窗");
  assert.equal(collectByClass(original, "dv-ai-option-card").length, fixture.result.candidate_options.length, "原方案始终可见");
  assert.equal(collectByClass(child, "dv-ai-request").length, 0, "补充分析不显示需求输入");
  assert.doesNotMatch(collectText(child), /adoption_context|parent_analysis_id|\{\s*definition/, "不展示机器请求");
}
const request = requests[1];
assert.ok(request && !request.revision_of);
assert.equal(request.analysis_protocol, 2);
assert.equal(request.include_suggestions, false);
assert.equal(request.reasoning_enabled, false, "补充分析请求必须始终关闭推理");
assert.equal(request.adoption_context.mode, "inherit_selected");
assert.equal(request.adoption_context.parent_analysis_id, fixture.parentAnalysisId || "analysis-1");
assert.deepEqual(request.adoption_context.parent_context, fixture.result.analysis_context);
assert.equal(request.adoption_context.suggestion_id, fixture.result.ai_suggestions[0].id);
assert.ok(request.adoption_context.parents.length >= 1);
assert.ok(request.adoption_context.parents.every(parent => parent.definition && parent.hash));
assert.doesNotMatch(request.request_text, /\{|\}|adoption_context|parent_analysis_id/);
assert.ok(request.request_text.includes(fixture.result.ai_suggestions[0].title));
if (fixture.scopeReview === "unselected") assert.ok(request.adoption_context.parents.every(parent => parent.definition.filters.every(filter => filter.value !== "2")));
if (fixture.scopeReview === "separate") {
  assert.ok(request.adoption_context.parents.some(parent => parent.definition.filters.some(filter => filter.value === "1")));
  assert.ok(request.adoption_context.parents.some(parent => parent.definition.filters.some(filter => filter.value === "2")));
}
if (fixture.failure) {
  const retry = findButton(child, "重试采纳");
  assert.ok(retry && !retry.disabled, "失败后允许在卡片内重试");
  await retry.dispatch("click");
  assert.equal(requests.length, 3, "重试必须创建新的分析任务");
  assert.equal(requests[2].adoption_context.mode, "inherit_selected");
  child = collectByClass(collectByClass(original, "dv-ai-supplement")[0], "dv-ai-supplement-inline")[0];
}
if (fixture.pending) {
  const input = collectByClass(child, "dv-business-question").flatMap(group => group.children)
    .find(node => node.tagName === "TEXTAREA");
  assert.match(input.getAttribute("aria-label"), /计量口径/);
  input.value = "募集份额与项目实收使用同一单位，可直接比较。";
  await input.dispatch("input");
  await findButton(child, "确认全部口径").dispatch("click");
  assert.equal(requests[2].request_text, request.request_text);
  assert.ok(requests[2].clarification_answers.some(item => item.answer === input.value));
}
if (fixture.child) {
  if (!fixture.pending) assert.equal(requests.length, 2, "已确认业务知识下只需独立分析一次");
  assert.equal(collectByClass(host, "dv-workbench-dialog").length, 1, "成功后补充方案回到父工作台");
  assert.equal(collectByClass(original, "dv-ai-option-card").length, 3);
  const adopted = findButton(original, "已采纳");
  assert.ok(adopted && adopted.disabled);
  const callsBeforeRepeat = requests.length;
  await adopted.dispatch("click");
  assert.equal(requests.length, callsBeforeRepeat);
  assert.ok(collectByClass(original, "dv-ai-sql-code").some(node => /SUM\(/i.test(collectText(node))));
  assert.equal(batch, undefined, "采纳后不能自动保存");
  let supplement = collectByClass(original, "dv-ai-option-check").at(-1);
  supplement.checked = false;
  await supplement.dispatch("change");
  assert.equal(findButton(original, "保存并启动以上2个方案").disabled, false, "原两张卡的测试证据仍有效");
  supplement = collectByClass(original, "dv-ai-option-check").at(-1);
  supplement.checked = true;
  await supplement.dispatch("change");
  assert.equal(findButton(original, "保存并启动以上3个方案").disabled, true);
  const run = findButton(original, "生成并运行测试用例") || findButton(original, "运行当前及所选方案测试");
  await run.dispatch("click");
  assert.equal(samples.length, 3);
  const save = findButton(original, "保存并启动以上3个方案");
  assert.equal(save.hidden, false);
  assert.equal(save.disabled, false);
  await save.dispatch("click");
  assert.equal(batch.definitions.length, 3);
} else if (fixture.endSession) await findButton(child, "结束会话").dispatch("click");
else await collectByClass(child, "dv-dialog-close")[0].dispatch("click");
assert.deepEqual(cancelled, fixture.child ? [] : ["analysis-" + requests.length]);
assert.equal(collectByClass(host, "dv-workbench-dialog").length, 1);
assert.equal(wb.element, original);
assert.equal(collectByClass(original, "dv-ai-option-card").length, fixture.result.candidate_options.length + (fixture.child ? 1 : 0));
assert.equal(controlByLabel(original, "需求描述 *").value, fixture.result.description);
if (fixture.cancelSnapshot) {
  assert.ok(collectByClass(original, "dv-ai-option-check").every(input => input.checked));
  assert.equal(findButton(original, "保存并启动以上2个方案").disabled, false);
  assert.equal(samples.length, 0);
  assert.equal(batch, undefined);
  assert.equal(findButton(original, "采纳").disabled, false);
}
const sample = samples.find(p => p.definition.join?.right_aggregate === "sum");
writeFileSync(process.argv[3], JSON.stringify({ request, clarification: requests[2], sample, batch, samples }));
wb.close();
runtime.destroy();
