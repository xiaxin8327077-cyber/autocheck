import assert from "node:assert/strict";
import { createTestPanel } from "./components/test_panel.mjs";
import { createRuntime } from "./runtime.mjs";
import { collectByClass, collectText, findButton } from "./frontend_workbench_dom.mjs";

const runtime = createRuntime({ notify(message) { throw new Error(message); } });
runtime.activate();
const changes = [];
const columns = [
  { column_name: "code", comment: "项目编号" },
  { column_name: "amount", comment: "金额" },
  { column_name: "nullable", comment: "可空字段" },
  { column_name: "base", comment: "基础值" },
  { column_name: "related", comment: "关联标志" },
];
const relatedColumns = [{ column_name: "right_code", comment: "关联编号" }, { column_name: "value", comment: "关联金额" }];
const targetA = { candidate: { rule_name: "规则甲" } };
const targetB = { candidate: { rule_name: "规则乙" } };
const samples = [
  { name: "正常", row: { code: "001", amount: 0, base: 0, related: "0007" }, expected_count: 0, actual_count: 0, status: "passed" },
  { name: "缺值", row: { base: { code: "002", amount: 0, nullable: null },
    related: [{ right_code: "0007", value: 0 }, { right_code: "0008", value: 2 }], report_date: "2026-11-19" },
    expected_count: 1, actual_count: 0, status: "failed" },
  { name: "范围外", row: { code: "003", amount: 2 }, expected_count: 0, actual_count: null, status: "not_run" },
];
const preview = { content_sha256: "h", sql_preview: "SELECT 1", definition: { rule_type: "field_compare", source_id: "src",
  table_name: "base", business_key: "code", report_date_field: "day", report_category: "group:pbc",
  expression: { left: "amount", op: "is_null" }, null_policy: "violate", equality_policy: "allow_equal" } };
const evidence = { content_sha256: "h", cases: samples, passed_count: 1, failed_count: 1, not_run_count: 1 };
const caseItems = samples.map((item, i) => ({ item, index: [9, 2, 4][i], target: i ? targetB : targetA, columns, relatedColumns }));
const panel = createTestPanel({ listen: runtime.listen, showSql: false, onTest() { assert.fail("过滤不能运行测试"); },
  onCaseChange(...args) { changes.push(args); } });
const model = { preview, evidence, previewCases: samples, columns, relatedColumns, caseItems,
  dirty: false, canTest: true, readOnly: false, busy: false, testing: false, stale: false };
const readiness = panel.update(model);
assert.equal(readiness.ready, false);
assert.ok(panel.element.classList.contains("dv-test-panel-ai"));
const table = collectByClass(panel.element, "dv-test-table")[0];
assert.equal(table.children[0].children[0].children.length, 4, "AI表格只保留场景、预期、实际、结果四列");
assert.equal(table.children[1].children.length, 3);
const details = collectByClass(panel.element, "dv-test-sample");
assert.equal(details.length, 3);
assert.ok(details.every((node) => node.tagName === "DETAILS"));
assert.match(collectText(details[0]), /基础值0/);
assert.match(collectText(details[0]), /关联标志0007/);
const sampleText = collectText(details[1]);
for (const value of ["查看样本", "项目编号", "002", "金额", "0", "空值", "关联编号", "0007", "0008", "2026-11-19"]) {
  assert.ok(sampleText.includes(value), `样本详情必须保留 ${value}`);
}
assert.match(collectText(table), /规则甲/);
assert.match(collectText(table), /规则乙/);
const counts = collectByClass(panel.element, "dv-test-summary-counts")[0];
const allCounts = collectText(counts);
assert.match(allCounts, /通过.*1/);
assert.match(allCounts, /失败.*1/);
assert.match(allCounts, /未运行.*1/);
const filter = findButton(panel.element, "只看未通过");
await filter.dispatch("click");
assert.equal(filter.getAttribute("aria-pressed"), "true");
assert.equal(table.children[1].children.length, 2, "过滤同时保留失败与未运行案例");
assert.equal(collectText(counts), allCounts, "过滤不改变全部用例的统计");
const expected = collectByClass(panel.element, "dv-case-expected")[0];
expected.value = "0";
await expected.dispatch("change");
assert.equal(changes.length, 1);
assert.deepEqual(changes[0], [2, 0, targetB], "过滤后修改预期仍使用原方案和原用例下标");
assert.deepEqual(panel.update(model), readiness, "过滤不改变启用门槛");
const passedItems = caseItems.map((entry) => ({ ...entry, item: { ...entry.item, status: "passed", actual_count: entry.item.expected_count } }));
panel.update({ ...model, caseItems: passedItems });
const empty = collectByClass(panel.element, "dv-test-filter-empty")[0];
assert.ok(empty && !empty.hidden);
assert.match(collectText(empty), /没有未通过的测试用例/);
assert.equal(collectText(collectByClass(panel.element, "dv-test-summary-counts")[0]).includes("3"), true);

const manual = createTestPanel({ listen: runtime.listen, onTest() {}, showSql: true });
manual.update({ ...model, caseItems: null });
const manualTable = collectByClass(manual.element, "dv-test-table")[0];
assert.equal(manualTable.children[0].children[0].children.length, 5, "手工与既有规则测试保持原表格");
assert.match(collectText(manualTable.children[0]), /样本输入/);
assert.equal(collectByClass(manual.element, "dv-test-sample").length, 0);
const projectColumns = [{ column_name: "code", comment: "项目编号" }, { column_name: "shared", comment: "项目金额" }];
const detailColumns = [{ column_name: "contract", comment: "合同编号" }, { column_name: "shared", comment: "合同金额" }];
const driverPanel = createTestPanel({ listen: runtime.listen, showSql: false, onTest() {}, onCaseChange() {} });
const driverItems = ["base", "related"].map((role, i) => ({
  index: i, item: { name: `项目驱动${i}`, row: { report_date: "2026-11-01", project: { code: "P", shared: 0 },
    details: i ? [{ contract: "C1", shared: 1 }, { contract: "C2", shared: 2 }] : [] },
  expected_count: i ? 2 : 1, actual_count: null, status: "not_run" },
  columns: role === "base" ? projectColumns : detailColumns,
  relatedColumns: role === "base" ? detailColumns : projectColumns,
  target: { preview: { definition: { project_driver: { version: 1, table_role: role } } } },
}));
driverPanel.update({ ...model, caseItems: driverItems });
const driverDetails = collectByClass(driverPanel.element, "dv-test-sample");
assert.match(collectText(driverDetails[0]), /项目.*项目金额.*0/);
assert.match(collectText(driverDetails[0]), /没有对应明细记录/);
assert.match(collectText(driverDetails[1]), /明细 1.*合同金额.*1/);
assert.match(collectText(driverDetails[1]), /明细 2.*合同金额.*2/);
assert.doesNotMatch(collectText(driverDetails[1]), /\{"|\[object Object\]/);
assert.ok(collectByClass(driverPanel.element, "dv-case-expected")[1].options.some((option) => option.value === "2"),
  "项目包含多条违规明细时，预期数量2不能丢失");
driverPanel.dispose();
panel.dispose();
const pressed = filter.getAttribute("aria-pressed");
await filter.dispatch("click");
assert.equal(filter.getAttribute("aria-pressed"), pressed, "关闭后清理过滤事件");
manual.dispose();
runtime.destroy();
