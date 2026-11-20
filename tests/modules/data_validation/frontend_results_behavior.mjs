import assert from "node:assert/strict";
import { FakeElement, collectByClass, collectText, findButton } from "./frontend_workbench_dom.mjs";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createResultsPage } from "./pages/results.mjs";

const runtime = createRuntime({ notify() {} }); runtime.activate();
const state = createState(); state.activeTab = "results";
const batch = { id: 1, creator_user_id: "1", report_period: state.reportPeriod, status: "completed" };
const xss = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>项目';
const columns = ["project_code", "项目名称", "校验值", "异常说明"].map(name => ({ name, label: "文档旧名称" }));
const issues = [
  { id: 101, rule_id: 7, query_result: { columns, values: { project_code: "0", "项目名称": "项目信息表", "校验值": 0, "异常说明": "金额为0" } } },
  { id: 102, rule_id: 7, query_result: { columns, values: { project_code: "C-9", "项目名称": null, "校验值": "", "异常说明": xss } } },
  { id: 103, rule_id: 7, query_result: null },
];
const contract = { id: 104, rule_id: 8, query_result: {
  columns: ["合同编号", "本金余额", "数据日期"].map(name => ({ name })),
  values: { "合同编号": "000008", "本金余额": "-123456789012345.67", "数据日期": "2026-10-30" },
} };
let issueCalls = 0;
const api = {
  tasks: async () => [batch],
  taskDetails: async () => ({ ...batch, rules: [
    { rule_id: 7, name: "项目校验", rule_code: "DV7", version_no: 2, status: "VIOLATION", violation_count: 3 },
    { rule_id: 8, name: "合同校验", rule_code: "DV8", version_no: 1, status: "VIOLATION", violation_count: 1 },
  ] }),
  issues: async (_id, query) => {
    issueCalls++;
    assert.ok(query.rule_id, "只允许读取某一规则的明细");
    return { items: query.rule_id === 7 ? [...issues, contract] : [contract], total: query.rule_id === 7 ? 3 : 1, page: 1, page_size: 50 };
  },
};
const page = createResultsPage({ state, runtime, api, listen: runtime.listen,
  user: { id: "1", role: "user", capabilities: ["dv.view", "dv.view_results"] },
  notify() {}, confirmAction: async () => true, host: new FakeElement("div"), onNewTask() {}, onPeriodChange() {} });
await page.loadTasks();
assert.equal(issueCalls, 0);
assert.equal(collectByClass(page.panel, "dv-result-tab").length, 1);
await findButton(page.panel, "查看异常").dispatch("click");
const table = collectByClass(page.panel, "dv-issue-table")[0];
const headers = () => table.children[0].children[0].children.map(th => th.textContent);
const rows = () => table.children[1].children;
const cells = row => row.children.map(collectText);
assert.deepEqual(headers(), ["序号", "project_code", "项目名称", "校验值", "异常说明"]);
assert.equal(rows().length, 3, "接口混入其他规则时不展示其行或字段");
assert.deepEqual(cells(rows()[0]), ["1", "0", "项目信息表", "0", "金额为0"]);
assert.deepEqual(cells(rows()[1]), ["2", "C-9", "NULL", "空字符串", xss]);
assert.deepEqual(cells(rows()[2]), ["3", "未采集", "未采集", "未采集", "未采集"]);
assert.ok(!headers().includes("合同编号"));
assert.ok(!headers().includes("文档旧名称"));
assert.equal(globalThis.__xss, undefined);
assert.equal(table.children[1].children.flatMap(row => row.children).some(cell => cell.children?.some(child => child.tagName === "IMG")), false);
await findButton(page.panel, "返回规则列表").dispatch("click");
const drills = collectByClass(page.panel, "dv-table-action");
await drills[1].dispatch("click");
assert.deepEqual(headers(), ["序号", "合同编号", "本金余额", "数据日期"]);
assert.deepEqual(cells(rows()[0]), ["1", "000008", "-123456789012345.67", "2026-10-30"]);
assert.equal(rows().length, 1);
assert.ok(!headers().includes("项目名称"));
assert.doesNotMatch(collectText(table), /未返回此列/);
assert.equal(collectByClass(page.panel, "dv-result-toolbar")[0].hidden, false, "明细抽屉打开时保留规则列表与筛选栏");
assert.equal(collectByClass(page.panel, "dv-return-rules")[0].hidden, false);
contract.query_result = { columns: [], values: {}, status: "unsupported_projection" };
await page.loadIssues();
assert.match(collectText(collectByClass(page.panel, "dv-issue-feedback")[0]), /此查询尚不支持明细采集/);
assert.equal(collectByClass(page.panel, "dv-issue-table-wrap")[0].hidden, true);
assert.doesNotMatch(collectText(page.panel), /重新执行后查看/);
issues.forEach(issue => { issue.query_result = null; });
await findButton(page.panel, "返回规则列表").dispatch("click");
await findButton(page.panel, "查看异常").dispatch("click");
assert.match(collectText(collectByClass(page.panel, "dv-issue-feedback")[0]), /历史记录未采集查询明细/);
runtime.destroy();
console.log(JSON.stringify({ ok: true, assertions: "single-rule/SQL aliases/columns/null/XSS/precise values" }));
