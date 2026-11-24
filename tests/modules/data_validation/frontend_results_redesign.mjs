import assert from "node:assert/strict";
import { FakeElement, collectByClass, collectText, findButton } from "./frontend_workbench_dom.mjs";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createResultsPage } from "./pages/results.mjs";
import { createApi } from "./api.mjs";
import { queryColumns, queryValue, canonicalQueryValue } from "./components/result_fields.mjs";

const aliased = { project_name: null, query_result: { columns: [
  { name: "business_key", label: "合同编号", source_field: "contract_no" },
  { name: "project_name", label: "项目名称", source_field: "c_project" },
  { name: "message", label: "SQL 说明" },
], values: { business_key: "000001", project_name: "SQL项目", message: "查询原文" } } };
assert.ok(queryColumns([aliased]).some((column) => column.label === "合同编号"));
assert.ok(queryColumns([aliased]).some((column) => column.name === "message"));
assert.equal(canonicalQueryValue(aliased, "project_name", aliased.project_name), "SQL项目");
const constructorIssue = { query_result: { columns: [{ name: "constructor" }, { name: "note" }],
  values: { constructor: "工程公司" }, unavailable: { note: "oversized" } } };
const constructorColumns = queryColumns([constructorIssue]);
assert.equal(queryValue(constructorIssue, constructorColumns[0]), "工程公司");
assert.equal(queryValue(constructorIssue, constructorColumns[1]), "值过长，未保存");

const category = { code: "group:pbc", name: "人行报送", rule_count: 1 };
const other = { code: "1104", name: "1104报送", rule_count: 1 };
const summary = { rule_count: 2, completed_count: 2, failed_count: 0, pending_count: 0, issue_count: 3 };
const batch = { id: 1, run_no: 1, creator_user_id: "1", status: "completed", report_period: "2026-10-31", categories: [category, other], summary };
const rule = { rule_id: 7, rule_code: "DV7", name: "净值校验", version_no: 2, status: "completed", violation_count: 3, report_category: category.code, report_category_name: category.name, table_name: "proj_info", table_name_cn: "项目信息", source_name: "监管报表" };
const cleanRule = { ...rule, rule_id: 8, rule_code: "DV8", name: "无异常校验", status: "PASS", violation_count: 0 };
const xss = '<img src=x onerror="window.__xss=1">';
const cols = [
  { name: "合同编号", label: "旧文档名称不应展示", source_field: "c_contract" },
  { name: "checked_value", label: "单位净值", source_field: "f_netvalue" },
  { name: "data_date", label: "数据日期", source_field: "d_cldate" },
  { name: "异常说明", label: "旧说明" },
];
const items = [
  { id: 10, rule_id: 7, version_no: 2, rule_name: rule.name, report_category_name: category.name, project_code: "0001", project_name: "项目甲", business_key: "001", project_name_status: "ok", message: xss, issue_kind: "numeric", query_result: { columns: cols, values: { "合同编号": "000003", checked_value: 0, data_date: "2026-10-31", "异常说明": xss } } },
  { id: 11, rule_id: 7, version_no: 2, project_code: "0", project_name: null, project_name_status: "missing_null", issue_kind: "missing_value", query_result: { columns: cols, values: { "合同编号": "", checked_value: null, data_date: "2026-10-31" } } },
  { id: 12, rule_id: 7, version_no: 1, query_result: null },
  { id: 13, rule_id: 7, version_no: 2, issue_kind: "calculation_error", query_result: {
    columns: [{ name: "异常类型" }, { name: "原始文字", source_field: "note" }],
    values: { "异常类型": "calculation_error", "原始文字": "calculation_error" },
  } },
];
const calls = [];
const runtime = createRuntime({ notify() {} }); runtime.activate();
const state = createState(); state.activeTab = "results"; state.reportPeriod = batch.report_period;
state.categories = [category, other];
let currentBatch = batch;
let lateIssues;
let resolveExport;
const api = {
  tasks: async (query) => { calls.push(["tasks", query]); return [currentBatch]; },
  taskDetails: async (id, query) => { calls.push(["detail", id, query]); return { ...currentBatch, rules: [rule, cleanRule], total_rule_count: 2 }; },
  issues: async (id, query) => { calls.push(["issues", id, query]); if (lateIssues) return lateIssues; return { items, total: 3, page: query.page, page_size: query.page_size }; },
  exportIssues: async () => new Promise((resolve) => { resolveExport = resolve; }),
};
const page = createResultsPage({ state, runtime, api, listen: runtime.listen, user: { id: "1", role: "admin" }, notify() {}, confirmAction: async () => true, host: new FakeElement("div"), onNewTask() {}, onPeriodChange() {} });
const resultCard = collectByClass(page.panel, "dv-issues-card")[0];
assert.ok(resultCard.classList.contains("is-awaiting-task"), "尚未选定批次时使用对齐的空状态表头");
await page.loadTasks();
assert.ok(!resultCard.classList.contains("is-awaiting-task"), "选定批次后恢复批次摘要布局");
const onlyIssuesSwitch = collectByClass(page.panel, "dv-only-issues-switch")[0];
assert.ok(onlyIssuesSwitch, "正式结果页必须展示异常规则筛选开关");
assert.equal(onlyIssuesSwitch.getAttribute("role"), "switch");
assert.equal(onlyIssuesSwitch.getAttribute("aria-checked"), "true");
assert.doesNotMatch(collectText(page.panel), /无异常校验/);
const requestsBeforeFilter = calls.length;
await onlyIssuesSwitch.dispatch("click");
assert.equal(onlyIssuesSwitch.getAttribute("aria-checked"), "false");
assert.match(collectText(page.panel), /无异常校验/);
assert.equal(calls.length, requestsBeforeFilter, "切换仅筛选已加载的执行结果，不发起额外请求");
assert.equal(collectByClass(page.panel, "dv-result-tab").length, 1, "默认没有异常明细页签入口");
assert.equal(calls.filter(([name]) => name === "issues").length, 0, "进入批次不请求所有规则的混合异常");
assert.equal(page.header.hidden, true, "结果页不再展示重复的标题与说明");
const periodRow = collectByClass(page.panel, "dv-results-filters")[0];
assert.ok(findButton(periodRow, "立即执行"), "立即执行和报送期位于同一行并沿用原执行弹窗");
assert.match(collectText(page.panel), /人行报送/);
assert.match(collectText(page.panel), /1104报送/);
assert.match(collectText(page.panel), /监管报送分类/);
assert.equal(collectByClass(page.panel, "dv-batch-entry").length, 1);
const drill = findButton(page.panel, "查看异常"); assert.ok(drill); await drill.dispatch("click");
assert.equal(calls.filter(([name]) => name === "issues").at(-1)[2].rule_id, 7);
assert.match(collectText(page.panel), /合同编号/);
assert.match(collectText(page.panel), /checked_value/);
assert.doesNotMatch(collectText(page.panel), /旧文档名称不应展示|f_netvalue/);
const table = collectByClass(page.panel, "dv-issue-table")[0];
const rows = table.children[1].children;
assert.equal(rows.length, 4);
assert.match(collectText(rows[0]), /000003/); assert.match(collectText(rows[0]), /2026-10-31/);
assert.ok(rows[0].children.some((cell) => collectText(cell) === "0"), "0 必须原样保留");
assert.match(collectText(rows[1]), /NULL/); assert.match(collectText(rows[1]), /空字符串/);
assert.match(collectText(rows[2]), /未采集/);
assert.match(collectText(rows[3]), /公式无法计算：除数为 0/);
assert.ok(rows[3].children.some((cell) => collectText(cell) === "calculation_error"));
assert.match(collectText(rows[0]), /<img src=x/); assert.equal(globalThis.__xss, undefined);
assert.doesNotMatch(collectText(page.panel), /异常示例|示例项目/);
await findButton(page.panel, "返回规则列表").dispatch("click");
assert.equal(onlyIssuesSwitch.getAttribute("aria-checked"), "false", "返回后保留开关选择");
assert.equal(collectByClass(page.panel, "dv-result-toolbar")[0].hidden, false);
// 分类切换同步清除规则钻取和页码，所有请求带相同分类。
state.issueQuery.page = 4;
const issuesBeforeCategory = calls.filter(([name]) => name === "issues").length;
await findButton(page.panel, "1104报送").dispatch("click");
assert.equal(onlyIssuesSwitch.getAttribute("aria-checked"), "false", "切换分类保留用户选择");
assert.equal(state.issueQuery.page, 1);
assert.equal(calls.filter(([name]) => name === "tasks").at(-1)[1].report_category, "1104");
assert.equal(calls.filter(([name]) => name === "issues").length, issuesBeforeCategory, "切分类回到规则列表，不请求混合异常");
// 切分类后，旧分类的迟到异常不得覆盖当前结果。
await findButton(page.panel, "查看异常").dispatch("click");
let resolveLate; lateIssues = new Promise((resolve) => { resolveLate = resolve; });
const old = page.loadIssues(); await Promise.resolve(); lateIssues = null;
await findButton(page.panel, "全部分类").dispatch("click");
resolveLate({ items: [{ id: 99, message: "迟到旧结果" }], total: 1 }); await old;
assert.equal(state.issues.items.length, 0);
// running → completed 那次轮询必须刷新最终规则和异常。
currentBatch = { ...batch, status: "running" }; await page.loadTasks();
await findButton(page.panel, "查看异常").dispatch("click");
const before = calls.filter(([name]) => name === "issues").length;
currentBatch = batch; await page.loadTasks({ poll: true });
assert.equal(calls.filter(([name]) => name === "issues").length, before + 1);
assert.equal(runtime.snapshot().timers, 0);
// 钻取范围变化后，旧范围导出不能再下载。
let downloaded = 0; URL.createObjectURL = () => { downloaded += 1; return "blob:qa"; };
const exporting = findButton(page.panel, "导出此规则异常").dispatch("click"); await Promise.resolve();
await findButton(page.panel, "返回规则列表").dispatch("click"); resolveExport({ content: "old", truncated: false }); await exporting;
assert.equal(downloaded, 0);
await findButton(page.panel, "1104报送").dispatch("click");
page.focusTask(batch); await page.loadTasks();
assert.equal(calls.filter(([name]) => name === "tasks").at(-1)[1].report_category, "");
// 即使是管理员，他人任务详情/操作也不能请求或展示。
currentBatch = { ...batch, creator_user_id: "2" }; const detailCount = calls.filter(([name]) => name === "detail").length;
await page.loadTasks(); assert.equal(calls.filter(([name]) => name === "detail").length, detailCount);
assert.match(collectText(page.panel), /创建人/);
// 加载中和加载为空均沿用同一个空状态表头，避免分隔线跳动。
let resolveEmptyTasks;
api.tasks = () => new Promise((resolve) => { resolveEmptyTasks = resolve; });
state.tasks = []; state.activeTaskId = null;
const loadingEmptyTasks = page.loadTasks();
assert.ok(resultCard.classList.contains("is-awaiting-task"));
resolveEmptyTasks([]); await loadingEmptyTasks;
assert.ok(resultCard.classList.contains("is-awaiting-task"));
page.stopPolling(); runtime.destroy();
// API 分类/钻取/导出必须携带相同范围。
const requests = []; const client = createApi({ api: async (path, options) => { requests.push([path, options]); return { data: {} }; } });
await client.tasks({ report_category: "group:pbc" }); await client.taskDetails(1, { report_category: "1104" });
await client.issues(1, { report_category: "1104", rule_id: 7 }); await client.exportIssues(1, { report_category: "1104", rule_id: 7 });
assert.match(requests[0][0], /report_category=group%3Apbc/);
assert.match(requests[1][0], /tasks\/1\?report_category=1104/);
assert.match(requests[2][0], /rule_id=7/);
assert.equal(JSON.parse(requests[3][1].body).report_category, "1104");
assert.equal(JSON.parse(requests[3][1].body).rule_id, 7);
console.log(JSON.stringify({ ok: true }));
