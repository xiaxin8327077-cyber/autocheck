import assert from "node:assert/strict";
import { createRuleEditor } from "./components/rule_editor.mjs";
import { createRuntime } from "./runtime.mjs";
import { createState } from "./state.mjs";
import { FakeElement, collectByClass, collectText, findButton, controlByLabel } from "./frontend_workbench_dom.mjs";

const owner = { id: "1", capabilities: ["dv.view", "dv.manage", "dv.test", "dv.confirm"] };
const initial = {
  id: 2, creator_user_id: "1", name: "净值非空校验", description: "检查单位净值", status: "enabled",
  version_no: 1, version_id: 10, current_version_id: 10, content_sha256: "hash1",
  sql_text: "SELECT :violation_message AS message FROM project WHERE data_date = :report_date",
  sql_display: "SELECT '原值' AS message FROM project WHERE data_date = :report_date",
  definition: {
    name: "净值非空校验", description: "检查单位净值", source_id: "source1", report_category: "group:pbc",
    table_name: "project", rule_type: "field_compare", dialect: "postgresql", generation_mode: "ai",
    business_key: "project_id", report_date_field: "report_date", mapping_version: "mapping1",
    expression: { left: "netvalue", op: "is_null", right: "", right_type: "field", right_table: "base" },
    null_policy: "violation", equality_policy: "allow", violation_message: "净值为空",
    filters: [{ table: "base", field: "mode", op: "in", value: ["1", "3"], confirmed: true }],
    join: { table_name: "related", report_date_field: "report_date", on: [{ left: "project_id", right: "project_id" }], relationship_confirmed: true, unmatched_policy: "exclude" },
    project_context: { mode: "base", key: "project_id", name: "project_name", confirmed: true },
    uncertainties: [], uncertainty_resolutions: [], unsupported_requirements: [],
  },
};
function passed(detail) { return { version_no: detail.version_no, content_sha256: detail.content_sha256,
  passed_count: 1, failed_count: 0, not_run_count: 0, cases: [{ status: "passed" }] }; }
async function setup({ user = owner, detail = initial, overrides = {} } = {}) {
  let stored = structuredClone(detail);
  const calls = [], notices = [];
  const host = new FakeElement("div");
  const runtime = createRuntime({ notify: (...args) => notices.push(args) }); runtime.activate();
  const state = createState();
  state.sources = [{ id: "source1", name: "监管报表", dialect: "postgresql" }, { id: "source2", name: "集市", dialect: "mysql" }];
  state.sourcesStatus = "success";
  state.categories = [{ code: "group:pbc", name: "人行报送" }, { code: "east", name: "East5报送" }];
  state.categoriesStatus = "success";
  state.rules.items = [{ id: 2, table_name: "project", table_name_cn: "项目信息（project.ktr）" }];
  const api = {
    async rule(id) { calls.push(["rule", id]); return structuredClone(stored); },
    async save(payload, id) { calls.push(["save", structuredClone(payload), id]); const { expected_rule, ...definition } = payload; stored = { ...stored, definition: structuredClone(definition),
      version_no: stored.version_no + 1, version_id: stored.version_id + 1, content_sha256: "hash2", name: payload.name, description: payload.description };
      return { id, version_no: stored.version_no, content_sha256: stored.content_sha256 }; },
    async describe(source, table) { calls.push(["describe", source, table]); return { mapping_version: "mapping2", columns: [] }; },
    async test(id, payload) { calls.push(["test", id, payload]); return passed(stored); },
    async confirm(id, payload) { calls.push(["confirm", id, payload]); stored.status = "enabled"; stored.current_version_id = stored.version_id; },
    async disable(id) { calls.push(["disable", id]); stored.status = "disabled"; },
    ...overrides,
  };
  const editor = createRuleEditor({ state, runtime, api, user, host, notify: (...args) => notices.push(args), onChanged: async () => calls.push(["changed"]) });
  await editor.open(2);
  const root = () => collectByClass(host, "dv-rule-editor")[0];
  const save = () => findButton(host, "保存");
  const toggle = () => collectByClass(host, "dv-editor-switch")[0];
  const change = async (label, value) => { const control = controlByLabel(host, label); control.value = value; await control.dispatch("input"); await control.dispatch("change"); };
  return { host, runtime, state, editor, api, calls, notices, root, save, toggle, change, stored: () => stored };
}

{
  const c = await setup();
  const text = collectText(c.host);
  for (const label of ["规则名称", "数据源", "报送分类", "相关表", "规则说明", "SQL", "状态"]) assert.ok(text.includes(label), label);
  for (const label of ["业务主键", "异常触发关系", "左字段", "右字段", "处理口径", "测试用例", "保存草稿", "映射版本"]) assert.ok(!text.includes(label), label);
  assert.equal(controlByLabel(c.host, "SQL").getAttribute("aria-readonly"), "true");
  assert.ok(text.includes("'原值'") && text.includes(":report_date") && !text.includes(":violation_message"));
  assert.equal(controlByLabel(c.host, "相关表").children[0].value, "项目信息（project）");
  assert.equal(c.toggle().getAttribute("role"), "switch");
  assert.equal(c.toggle().getAttribute("aria-checked"), "true");
  await c.toggle().dispatch("click");
  assert.equal(c.toggle().getAttribute("aria-checked"), "false");
  assert.ok(collectText(c.host).includes("已停用"));
  assert.equal(c.calls.some(([name]) => name === "disable"), false, "拨动开关只改变待保存状态");
  await c.host.children[0].dispatch("click");
  assert.ok(c.root(), "遮罩点击不关闭");
  await c.toggle().dispatch("click");
  await c.save().dispatch("click");
  assert.equal(c.calls.some(([name]) => ["save", "test", "confirm", "disable"].includes(name)), false, "未修改且已启用当前版本时不写入");
  c.runtime.destroy();
}
{
  const c = await setup();
  await c.change("规则名称", "修改后的名称"); await c.change("规则说明", "修改后的说明");
  await c.save().dispatch("click");
  const saved = c.calls.find(([name]) => name === "save")[1];
  const { expected_rule, ...savedDefinition } = saved;
  assert.deepEqual(savedDefinition, { ...initial.definition, name: "修改后的名称", description: "修改后的说明" }, "完整保留隐藏定义");
  assert.deepEqual(initial.definition.filters[0].value, ["1", "3"], "原始详情不被修改");
  assert.deepEqual(c.calls.filter(([name]) => ["save", "test", "confirm"].includes(name)).map(([name]) => name), ["save", "test", "confirm"]);
  assert.deepEqual(c.calls.find(([name]) => name === "confirm").slice(1), [2, { version_no: 2, expected_hash: "hash2",
    expected_rule: { version_no: 2, content_sha256: "hash2", status: "enabled", current_version_id: 10 } }]);
  assert.equal(c.host.children.length, 0);
  c.runtime.destroy();
}
{
  const c = await setup(); await c.toggle().dispatch("click"); await c.change("规则名称", "保存并停用");
  await c.save().dispatch("click");
  assert.ok(c.calls.some(([name]) => name === "disable"));
  assert.ok(!c.calls.some(([name]) => name === "test" || name === "confirm"));
  c.runtime.destroy();
}
{
  const c = await setup({ detail: { ...initial, version_id: 11, version_no: 2 } });
  await c.save().dispatch("click");
  assert.ok(!c.calls.some(([name]) => name === "save"));
  assert.ok(c.calls.some(([name]) => name === "test"), "最新版本尚未启用时不能把规则状态当作本版本已启用");
  assert.ok(c.calls.some(([name]) => name === "confirm")); c.runtime.destroy();
}
{
  let failures = 1;
  const c = await setup();
  c.api.confirm = async (id, payload) => { c.calls.push(["confirm", id, payload]); if (failures--) throw new Error("确认暂时失败"); };
  await c.change("规则名称", "重试名称"); await c.save().dispatch("click");
  assert.ok(c.root()); assert.ok(collectText(c.host).includes("修改已保存"));
  assert.equal(controlByLabel(c.host, "规则名称").value, "重试名称");
  await c.save().dispatch("click");
  assert.equal(c.calls.filter(([name]) => name === "save").length, 1, "启用失败后重试不重复建版本");
  assert.equal(c.calls.filter(([name]) => name === "confirm").length, 2); c.runtime.destroy();
}
{
  const c = await setup();
  c.api.test = async () => ({ passed_count: 0, failed_count: 1, cases: [{ status: "failed" }] });
  await c.change("规则名称", "失败用例"); await c.save().dispatch("click");
  assert.ok(!c.calls.some(([name]) => name === "confirm")); assert.ok(c.root()); c.runtime.destroy();
}
for (const user of [{ id: "other", role: "admin" }, { id: "1", capabilities: ["dv.view"] }]) {
  const c = await setup({ user }); assert.equal(c.save().hidden, true); assert.equal(c.toggle().disabled, true);
  await c.save().dispatch("click"); assert.ok(!c.calls.some(([name]) => name === "save")); c.runtime.destroy();
}
{
  const c = await setup({ user: { id: "1", capabilities: ["dv.view", "dv.manage"] } });
  await c.change("规则名称", "缺少启用权限"); await c.save().dispatch("click");
  assert.ok(!c.calls.some(([name]) => name === "save"), "启用权限不足时保存前提示");
  await c.toggle().dispatch("click"); await c.save().dispatch("click");
  assert.ok(c.calls.some(([name]) => name === "disable"), "管理者仍可保存并停用"); c.runtime.destroy();
}
{
  let resolveSave; const c = await setup();
  c.api.save = async () => { c.calls.push(["save"]); return new Promise(resolve => { resolveSave = resolve; }); };
  await c.change("规则名称", "等待保存"); const saving = c.save().dispatch("click");
  for (let i = 0; i < 12 && !resolveSave; i++) await Promise.resolve();
  assert.ok(resolveSave); assert.equal(findButton(c.host, "取消").disabled, true);
  await findButton(c.host, "取消").dispatch("click"); assert.ok(c.root(), "保存期间取消不关闭");
  assert.equal(findButton(c.host, "关闭弹窗").disabled, true, "保存期间原生关闭按钮禁用");
  await findButton(c.host, "保存中…").dispatch("click");
  assert.equal(c.calls.filter(([name]) => name === "save").length, 1);
  c.editor.close(); resolveSave({ id: 2 }); await saving;
  assert.ok(!c.calls.some(([name]) => name === "test" || name === "confirm"), "关闭使迟到保存结果无效"); c.runtime.destroy();
}
{
  const c = await setup(); await c.change("规则名称", "发生并发变更");
  c.api.rule = async () => ({ ...initial, version_no: 3, content_sha256: "other-hash" });
  await c.save().dispatch("click"); assert.ok(!c.calls.some(([name]) => name === "save"));
  assert.ok(collectText(c.host).includes("版本")); c.runtime.destroy();
}
{
  const c = await setup({ detail: { ...initial, status: "draft", current_version_id: null } });
  await c.save().dispatch("click"); assert.ok(!c.calls.some(([name]) => name === "disable"), "未修改草稿不自动转停用"); c.runtime.destroy();
}
{
  const c = await setup({ detail: { ...initial, definition: { ...initial.definition, report_category: "" } } });
  assert.ok(!collectText(c.host).includes("读取规则失败"), "未分类规则仍可正常查看");
  await c.toggle().dispatch("click"); await c.save().dispatch("click");
  assert.ok(c.calls.some(([name]) => name === "disable"), "单纯停用不强制补填历史分类"); c.runtime.destroy();
}
{
  const c = await setup(); c.api.rule = async () => ({ ...initial, status: "disabled" });
  await c.save().dispatch("click");
  assert.ok(!c.calls.some(([name]) => ["save", "test", "confirm", "disable"].includes(name)), "并发启停不能被覆盖");
  assert.ok(collectText(c.host).includes("状态")); c.runtime.destroy();
}
{
  const c = await setup({ detail: { ...initial, definition: { ...initial.definition, mapping_version: "doc-v4-123456789abc" } } });
  await c.change("数据源", "source2"); await c.save().dispatch("click");
  const payload = c.calls.find(([name]) => name === "save")[1];
  assert.equal(payload.mapping_version, "doc-v4-123456789abc", "保留文档绑定版本，不替换成物理列哈希");
  assert.deepEqual(payload.expected_rule, { version_no: 1, content_sha256: "hash1", status: "enabled", current_version_id: 10 }); c.runtime.destroy();
}
{
  const c = await setup(); const originalRule = c.api.rule; let saved = false, failed = false;
  const originalSave = c.api.save;
  c.api.save = async (...args) => { const receipt = await originalSave(...args); saved = true; return { ...receipt, version_no: 2, content_sha256: "hash2" }; };
  c.api.rule = async (...args) => { if (saved && !failed) { failed = true; throw new Error("暂时断网"); } return originalRule(...args); };
  await c.change("规则名称", "保存后断网"); await c.save().dispatch("click");
  assert.ok(c.root()); await c.save().dispatch("click");
  assert.equal(c.calls.filter(([name]) => name === "save").length, 1);
  assert.ok(c.calls.some(([name]) => name === "confirm"), "读取恢复后继续已保存版本的启用"); c.runtime.destroy();
}
console.log(JSON.stringify({ ok: true, assertions: "compact-rule-editor" }));
