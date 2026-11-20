import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRuntime } from "./runtime.mjs";
import { createState } from "./state.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { FakeElement, collectByClass, controlByLabel, findButton } from "./frontend_workbench_dom.mjs";

const result = JSON.parse(readFileSync(process.argv[2], "utf8"));
const state = createState();
state.sourcesStatus = state.modelsStatus = state.categoriesStatus = "success";
state.sources = [{ id: "src", name: "设备", dialect: "postgresql" }];
state.models = [{ id: "model-1", name: "模型", is_default: true }];
state.categories = [{ code: "group:pbc", name: "报送" }];
const runtime = createRuntime({ notify: () => {} });
runtime.activate();
const schedule = runtime.setTimer;
runtime.setTimer = (callback, delay) => schedule(callback, delay === 3000 ? 0 : delay);
const samples = [];
let batch;
const api = {
  async createAnalysis() { return { status: "completed", analysis_id: "devices", result }; },
  async testCandidate(payload) {
    samples.push(payload);
    const cases = payload.cases.map(c => ({ ...c, status: "passed", actual_count: c.expected_count }));
    return { cases, content_sha256: payload.expected_hash, passed_count: cases.length, failed_count: 0, not_run_count: 0 };
  },
  async batchSaveCandidates(payload) {
    batch = payload;
    // The Python test runs this exact payload against the in-memory service.
    throw Object.assign(new Error("已送达批量保存边界"), { status: 400, payload: { error: { code: "VALIDATION_ERROR" } } });
  },
};
const wb = createWorkbench({ state, runtime, api, listen: runtime.listen, host: new FakeElement("div"),
  user: { id: "1", role: "user", capabilities: ["dv.ai_use", "dv.manage", "dv.test", "dv.confirm"] },
  notify: () => {}, onChanged: async () => {} });
await wb.open({ mode: "ai" });
const root = wb.element;
const request = controlByLabel(root, "需求描述 *");
request.value = result.description;
await request.dispatch("input");
await controlByLabel(root, "数据源 *").dispatch("change");
await controlByLabel(root, "启用模型").dispatch("change");
await findButton(root, "✦ AI 分析").dispatch("click");
const count = result.candidate_options.length;
assert.equal(collectByClass(root, "dv-ai-option-card").length, count);
for (let i = 0; i < count; i++) {
  const checkbox = collectByClass(root, "dv-ai-option-check")[i];
  if (checkbox.checked) continue;
  checkbox.checked = true;
  await checkbox.dispatch("change");
}
await findButton(root, "生成并运行测试用例").dispatch("click");
assert.equal(samples.length, count);
const save = findButton(root, `保存并启动以上${count}个方案`);
assert.ok(!save.hidden && !save.disabled);
await save.dispatch("click");
assert.equal(batch.definitions.length, count);
console.log(JSON.stringify({ samples, batch }));
wb.close();
runtime.destroy();
