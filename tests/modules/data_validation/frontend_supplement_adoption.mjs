import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { FakeElement, collectByClass, collectText, controlByLabel, findButton } from "./frontend_workbench_dom.mjs";

const fixture = JSON.parse(readFileSync(process.argv[2], "utf8"));
if (fixture.scopeReview) {
  const alternate = structuredClone(fixture.result.candidate_options[0]);
  alternate.id = "alternate-filter";
  alternate.recommended = false;
  alternate.candidate.filters[0].value = "2";
  alternate.candidate.preview.definition.filters[0].value = "2";
  fixture.result.candidate_options.push(alternate);
}
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
const api = {
  async createAnalysis(payload) {
    const results = fixture.pending ? [fixture.result, fixture.pending, fixture.child] : [fixture.result, fixture.child];
    const result = results[requests.length];
    requests.push(payload);
    if (fixture.failure && requests.length === 2) {
      return { analysis_id: "analysis-2", status: "failed", error: { code: "MODEL_UNAVAILABLE" } };
    }
    return { analysis_id: "analysis-" + requests.length, status: result ? "completed" : "running", result };
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
if (fixture.reasoning) await collectByClass(original, "dv-ai-reasoning-switch")[0].dispatch("click");
await findButton(original, "✦ AI 分析").dispatch("click");
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
const adopt = findButton(original, "采纳");
assert.ok(adopt && !adopt.disabled);
const cardText = collectText(collectByClass(original, "dv-ai-supplement")[0]);
for (const note of fixture.result.ai_suggestions[0].preconditions) assert.ok(cardText.includes(note));
assert.ok(cardText.includes("系统已核对文档引用"));
await adopt.dispatch("click");
let child = collectByClass(host, "dv-workbench-dialog").at(-1);
if (!fixture.child || fixture.pending) assert.notEqual(child, original);
const request = requests[1];
assert.ok(request && !request.revision_of);
assert.equal(request.reasoning_enabled, Boolean(fixture.reasoning));
if (fixture.scopeReview === "unselected") assert.doesNotMatch(request.request_text, /"value":"2"/);
if (fixture.scopeReview === "separate") {
  const groups = JSON.parse(request.request_text.split("\n").find(line => line.startsWith("各原方案的适用范围：")).split("：")[1]);
  assert.ok(groups.some(group => group.filters.some(f => f.value === "1")));
  assert.ok(groups.some(group => group.filters.some(f => f.value === "2")));
  assert.ok(groups.every(group => new Set(group.filters.map(filter => filter.value)).size === 1));
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
assert.deepEqual(cancelled, fixture.child || fixture.failure ? [] : ["analysis-" + requests.length]);
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
