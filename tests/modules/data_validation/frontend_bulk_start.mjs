import assert from "node:assert/strict";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createWorkbench } from "./pages/workbench.mjs";
import { FakeElement, collectByClass, controlByLabel, findButton } from "./frontend_workbench_dom.mjs";

const names = ["方案甲", "方案乙", "方案丙"];
async function scenario(flags = {}) {
  const state = createState();
  state.sources = [{ id: "src", name: "监管报表", dialect: "mysql" }];
  state.models = [{ id: "model", name: "模型", is_default: true }];
  state.categories = [{ code: "group:pbc", name: "人行" }];
  state.sourcesStatus = state.modelsStatus = state.categoriesStatus = "success";
  const runtime = createRuntime({ notify(message) { throw new Error(message); } });
  runtime.activate();
  // This suite exercises save/confirm recovery. Real generation timing is covered separately.
  const timer = runtime.setTimer;
  runtime.setTimer = (callback, delay, key) => timer(callback, Math.min(delay, 5), key);
  const columns = ["id", "day", "value0", "value1", "value2"].map(column_name => ({ column_name, data_type: "numeric" }));
  const options = names.map((name, i) => {
    const definition = { name, description: "指标不得为空", generation_mode: "ai", rule_type: "field_compare",
      source_id: "src", dialect: "mysql", table_name: "products", report_category: "group:pbc", mapping_version: "doc1",
      business_key: "id", report_date_field: "day", expression: { left: `value${i}`, op: "is_null" },
      null_policy: "violate", equality_policy: "allow_equal", violation_message: "请核实" };
    const cases = [0, null].map((value, k) => ({ name: k ? "空值" : "正常", row: { id: `00${k}`, [`value${i}`]: value },
      expected_count: k, actual_count: null, status: "not_run" }));
    return { id: String(i), label: name, recommended: i < 2, candidate: { ...definition, rule_name: name,
      columns, questions: [], uncertainties: [], unsupported_requirements: [],
      preview: { definition, sql_preview: "SELECT 1", content_sha256: name, cases } } };
  });
  const rows = new Map(), receipts = new Map(), batch = [], tested = [], confirmed = [], notices = [];
  let changed = 0;
  const resultFor = (definition, cases, fail) => {
    const values = cases.map((item, i) => ({ ...item,
      actual_count: fail && i === 0 ? 1 : Number(item.row[definition.expression.left] === null),
      status: (fail && i === 0 ? 1 : Number(item.row[definition.expression.left] === null)) === item.expected_count ? "passed" : "failed" }));
    return { cases: values, passed_count: values.filter(x => x.status === "passed").length,
      failed_count: values.filter(x => x.status === "failed").length, not_run_count: 0 };
  };
  const api = {
    createAnalysis: async () => ({ status: "completed", result: { candidate_options: options,
      ai_suggestions: flags.suggestions ? [{ id: "extra", title: "补充检查", support_level: "supported",
        references: [{ table_name: "products", field_name: "value0" }],
        questions: flags.suggestionQuestions ? [{ id: "expression.left", text: "确认补充字段", uncertainty: "选择补充指标",
          options: ["value0", "value1"].map(value => ({ value, label: value })) }] : [],
        definition: { ...options[0].candidate.preview.definition, name: "补充检查" } }] : [] } }),
    preview: async ({ definition }) => ({ definition, sql_preview: "SELECT 1", content_sha256: definition.name,
      cases: options[0].candidate.preview.cases, questions: [], columns }),
    testCandidate: async ({ definition, cases, expected_hash }) => ({ ...resultFor(definition, cases, flags.failPreview === definition.name), content_sha256: expected_hash }),
    batchSaveCandidates: async (payload) => {
      batch.push(structuredClone(payload));
      if (flags.rejectValidation) {
        throw Object.assign(new Error("规则校验拒绝"), { status: 400, payload: { error: { code: "VALIDATION_ERROR" } } });
      }
      let ids = receipts.get(payload.request_key);
      if (!ids) {
        ids = payload.definitions.map((definition) => {
          const id = rows.size + 1;
          rows.set(id, { id, name: definition.name, rule_code: `R${id}`, definition: structuredClone(definition),
            version_no: 1, version_id: id * 10, current_version_id: null, content_sha256: definition.name, status: "draft" });
          return id;
        });
        receipts.set(payload.request_key, ids);
      }
      if (flags.dropReply) { flags.dropReply = false; throw new Error("保存响应丢失"); }
      return { rules: ids.map(id => structuredClone(rows.get(id))) };
    },
    save: async () => assert.fail("主按钮应批量保存所选项"),
    rule: async (id) => {
      const value = structuredClone(rows.get(Number(id)));
      if (flags.drift === value.name) value.content_sha256 = "changed-by-another-window";
      return value;
    },
    test: async (id, payload) => {
      const stored = rows.get(Number(id));
      tested.push({ id, name: stored.name, ...structuredClone(payload) });
      return resultFor(stored.definition, payload.cases, flags.failStored === stored.name);
    },
    confirm: async (id) => {
      const stored = rows.get(Number(id));
      if (flags.failConfirm === stored.name) throw new Error("启动请求失败");
      stored.status = "enabled";
      stored.current_version_id = stored.version_id;
      confirmed.push(Number(id));
      if (flags.dropConfirmReply === stored.name) {
        flags.dropConfirmReply = "";
        throw new Error("启动响应丢失");
      }
      return structuredClone(stored);
    },
  };
  const wb = createWorkbench({ state, runtime, api, listen: runtime.listen, user: { role: "admin" }, host: new FakeElement("div"),
    notify(message) { notices.push(message); }, confirmAction: async () => true, onChanged: async () => { changed++; } });
  await wb.open({ mode: "ai" });
  const input = controlByLabel(wb.element, "需求描述 *");
  input.value = "指标不得为空";
  await input.dispatch("input");
  await findButton(wb.element, "✦ AI 分析").dispatch("click");
  const primary = () => collectByClass(wb.element, "dv-ai-footer-actions")[0].children
    .find(node => node.tagName === "BUTTON" && node.textContent.startsWith("保存并启动以上"));
  const generate = async () => {
    const heading = collectByClass(wb.element, "dv-ai-test-heading")[0];
    await heading.children.find(node => node.tagName === "BUTTON").dispatch("click");
  };
  const check = async (i, checked) => {
    const control = collectByClass(wb.element, "dv-ai-option-check")[i];
    control.checked = checked;
    await control.dispatch("change");
  };
  return { wb, runtime, flags, rows, batch, tested, confirmed, notices, primary, generate, check,
    changed: () => changed };
}

const all = await scenario({ failPreview: "方案丙" });
const third = collectByClass(all.wb.element, "dv-ai-option-card")[2];
await findButton(third, "查看此方案").dispatch("click");
await all.generate();
await findButton(collectByClass(all.wb.element, "dv-ai-option-card")[2], "查看此方案").dispatch("click");
assert.equal(all.primary().textContent, "保存并启动以上2个方案");
assert.equal(all.primary().disabled, false, "未展开或未勾选方案失败，不影响已勾选且通过的方案");
assert.equal(findButton(all.wb.element, "保存所选 2 条草稿").hidden, true);
assert.equal(findButton(all.wb.element, "保存草稿").hidden, true);
await all.primary().dispatch("click");
assert.equal(all.rows.size, 2);
assert.deepEqual([...all.rows.values()].map(x => x.name), names.slice(0, 2));
assert.ok([...all.rows.values()].every(x => x.status === "enabled"));
assert.deepEqual(all.tested.map(x => x.name), names.slice(0, 2));
assert.deepEqual(all.tested.map(x => Object.keys(x.cases[0].row)), [["id", "value0"], ["id", "value1"]]);
assert.deepEqual(all.confirmed, [1, 2]);
assert.equal(all.wb.isOpen(), false);
assert.equal(all.changed(), 1);
all.runtime.destroy();

const invalid = await scenario({ failPreview: "方案乙" });
await invalid.generate();
assert.equal(invalid.primary().disabled, true);
await invalid.primary().dispatch("click");
assert.equal(invalid.batch.length, 0, "一条所选规则未通过，不开始保存任何规则");
invalid.runtime.destroy();

const retest = await scenario({ failStored: "方案乙" });
await retest.generate();
await retest.primary().dispatch("click");
assert.equal(retest.rows.size, 2);
assert.equal(retest.confirmed.length, 0, "所有保存版本复测通过前不启动第一条");
assert.equal(retest.primary().disabled, true, "保存版本失败结果回显并阻止重试启动");
retest.flags.failStored = "";
await retest.generate();
await retest.primary().dispatch("click");
assert.equal(retest.batch.length, 1, "复测失败后重试复用已有ID");
assert.equal(retest.rows.size, 2);
assert.deepEqual(retest.confirmed, [1, 2]);
retest.runtime.destroy();

const lost = await scenario({ dropReply: true, suggestions: true });
await lost.generate();
assert.equal(findButton(lost.wb.element, "采纳").disabled, false);
await lost.primary().dispatch("click");
assert.equal(lost.rows.size, 2);
assert.equal(lost.confirmed.length, 0);
assert.ok(collectByClass(lost.wb.element, "dv-ai-option-check").every(x => x.disabled), "保存结果未知时锁定勾选范围");
assert.ok(collectByClass(lost.wb.element, "dv-case-expected").every(x => x.disabled));
assert.equal(findButton(lost.wb.element, "采纳").disabled, true);
await findButton(lost.wb.element, "采纳").dispatch("click");
assert.equal(collectByClass(lost.wb.element, "dv-ai-option-card").length, 3, "回执未知时采纳 handler 也不得加入新方案");
await lost.check(1, false);
await lost.check(1, true);
assert.equal(lost.primary().textContent, "保存并启动以上2个方案");
await lost.primary().dispatch("click");
assert.equal(lost.batch.length, 2);
assert.equal(lost.batch[0].request_key, lost.batch[1].request_key, "响应丢失后保留原批次UUID");
assert.equal(lost.rows.size, 2, "响应丢失后不重复新增");
assert.deepEqual(lost.confirmed, [1, 2]);
lost.runtime.destroy();

const rejected = await scenario({ rejectValidation: true });
await rejected.generate();
await rejected.primary().dispatch("click");
assert.equal(rejected.rows.size, 0);
assert.ok(collectByClass(rejected.wb.element, "dv-ai-option-check").every(x => !x.disabled), "明确未保存的校验拒绝不锁死编辑");
await rejected.check(1, false);
rejected.flags.rejectValidation = false;
assert.equal(rejected.primary().textContent, "保存并启动以上1个方案");
await rejected.primary().dispatch("click");
assert.equal(rejected.rows.size, 1);
assert.deepEqual(rejected.batch[1].definitions.map(x => x.name), ["方案甲"]);
rejected.runtime.destroy();

const unknownThenRejected = await scenario({ dropReply: true });
await unknownThenRejected.generate();
await unknownThenRejected.primary().dispatch("click");
unknownThenRejected.flags.rejectValidation = true;
await unknownThenRejected.primary().dispatch("click");
assert.equal(unknownThenRejected.rows.size, 2);
assert.ok(collectByClass(unknownThenRejected.wb.element, "dv-ai-option-check").every(x => x.disabled), "已有未知结果不能因后续业务拒绝丢失原回执");
unknownThenRejected.flags.rejectValidation = false;
await unknownThenRejected.primary().dispatch("click");
assert.equal(unknownThenRejected.rows.size, 2);
assert.equal(new Set(unknownThenRejected.batch.map(x => x.request_key)).size, 1);
unknownThenRejected.runtime.destroy();

const pendingChoice = await scenario({ dropReply: true, suggestions: true, suggestionQuestions: true });
await pendingChoice.generate();
await findButton(pendingChoice.wb.element, "采纳").dispatch("click");
await pendingChoice.check(3, false);
const chooseAll = collectByClass(pendingChoice.wb.element, "dv-ai-choices")[0].children.at(-1).children[0];
chooseAll.checked = true;
await chooseAll.dispatch("change");
assert.equal(findButton(pendingChoice.wb.element, "确认当前口径").disabled, false);
await pendingChoice.primary().dispatch("click");
assert.equal(pendingChoice.rows.size, 2);
assert.equal(findButton(pendingChoice.wb.element, "确认当前口径").disabled, true, "回执未知时禁止确认未勾选方案的口径");
assert.ok(collectByClass(pendingChoice.wb.element, "dv-ai-choices")[0].children.every(label => label.children[0].disabled));
await findButton(pendingChoice.wb.element, "确认当前口径").dispatch("click");
assert.equal(pendingChoice.primary().textContent, "保存并启动以上2个方案");
await pendingChoice.primary().dispatch("click");
assert.equal(pendingChoice.rows.size, 2);
assert.deepEqual(pendingChoice.confirmed, [1, 2]);
pendingChoice.runtime.destroy();

const partial = await scenario({ failConfirm: "方案乙" });
await partial.generate();
await partial.primary().dispatch("click");
assert.deepEqual(partial.confirmed, [1]);
assert.match(partial.notices.at(-1), /1\/2/);
partial.flags.failConfirm = "";
await partial.primary().dispatch("click");
assert.deepEqual(partial.confirmed, [1, 2], "部分启动后重试不重复确认已启用的同一版本");
assert.equal(partial.rows.size, 2);
partial.runtime.destroy();

const confirmLost = await scenario({ dropConfirmReply: "方案乙" });
await confirmLost.generate();
await confirmLost.primary().dispatch("click");
assert.deepEqual(confirmLost.confirmed, [1, 2]);
await confirmLost.primary().dispatch("click");
assert.deepEqual(confirmLost.confirmed, [1, 2], "启动成功但回包丢失后由fresh GET恢复状态");
assert.equal(confirmLost.rows.size, 2);
confirmLost.runtime.destroy();

const drift = await scenario({ drift: "方案乙" });
await drift.generate();
await drift.primary().dispatch("click");
assert.equal(drift.confirmed.length, 0, "保存版本漂移时不启动任何方案");
assert.match(drift.notices.at(-1), /版本已变化/);
drift.runtime.destroy();

const subset = await scenario();
await subset.check(0, false);
assert.equal(subset.primary().textContent, "保存并启动以上1个方案");
await subset.generate();
await subset.primary().dispatch("click");
assert.equal(subset.rows.size, 1);
assert.equal([...subset.rows.values()][0].name, "方案乙");
subset.runtime.destroy();

const empty = await scenario();
await empty.check(0, false); await empty.check(1, false);
assert.equal(empty.primary().textContent, "保存并启动以上0个方案");
assert.equal(empty.primary().disabled, true);
await empty.primary().dispatch("click");
assert.equal(empty.batch.length, 0);
empty.runtime.destroy();
