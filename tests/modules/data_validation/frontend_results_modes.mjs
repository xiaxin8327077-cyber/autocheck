import assert from "node:assert/strict";
import { FakeElement, collectByClass, collectText, findButton } from "./frontend_workbench_dom.mjs";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createResultsPage } from "./pages/results.mjs";

const runtime = createRuntime({ notify() {} }); runtime.activate();
const state = createState(); state.activeTab = "results";
const batch = { id: 3, creator_user_id: "1", report_period: state.reportPeriod, status: "completed",
  created_at: "2026-11-20 12:30:00", is_full: true,
  categories: [{ code: "pbc", name: "人行报送" }, { code: "1104", name: "1104报送" }, { code: "east5", name: "East5报送" }],
  summary: { rule_count: 2, completed_count: 2, failed_count: 0, issue_count: 5 } };
const rules = [{ rule_id: 7, rule_code: "DV000007", name: "余额核查", version_no: 1, status: "VIOLATION", violation_count: 5,
  description: "按执行版本的范围核查", sql_text: "SELECT amount AS 余额 FROM loan", table_name: "loan" },
{ rule_id: 8, rule_code: "DV000008", name: "日期核查", version_no: 2, status: "PASS", violation_count: 0, description: "日期须有效", sql_text: "SELECT d FROM loan" }];
const calls = [];
const page = createResultsPage({ state, runtime, listen: runtime.listen,
  api: { tasks: async () => [batch, { ...batch, id: 2, status: "running" }, { ...batch, id: 1, summary: { ...batch.summary, issue_count: 7 } }],
    taskDetails: async (id, query) => { calls.push(["detail", id, query]); return { ...batch, id, rules }; },
    issues: async (id, query) => { calls.push(["issues", id, query]); return { items: [{ rule_id: 7, query_result: { columns: [{ name: "余额" }], values: { "余额": 0 } } }], total: 1, ...query }; } },
  user: { id: "1", role: "admin" }, host: new FakeElement("div"), notify() {}, confirmAction: async () => true,
  onNewTask() { calls.push(["execute"]); }, onPeriodChange() {} });
await page.loadTasks();
const batchTable = collectByClass(page.panel, "dv-batch-table")[0];
assert.ok(batchTable, "批次富下拉必须保留原稿五列表格");
assert.deepEqual(batchTable.children[0].children[0].children.map(collectText), ["批次号", "执行时间", "覆盖条线", "异常数", "较前批变化"]);
assert.match(collectText(collectByClass(page.panel, "dv-batch-trigger")[0]), /2026-11-20 12:30:00/);
assert.match(collectText(batchTable), /2026-11-20 12:30:00/);
assert.match(collectText(batchTable), /全量/);
assert.match(collectText(batchTable), /-2/);
const batchTrigger = collectByClass(page.panel, "dv-batch-trigger")[0];
await batchTrigger.dispatch("click"); assert.equal(batchTrigger.getAttribute("aria-expanded"), "true");
await page.panel.dispatch("click"); assert.equal(batchTrigger.getAttribute("aria-expanded"), "false", "批次下拉点击外部空白收起");
const trendButton = findButton(page.panel, "趋势审阅");
assert.ok(trendButton, "结果页提供趋势审阅切换");
const table = collectByClass(page.panel, "dv-rule-result-table")[0];
const wrap = collectByClass(page.panel, "dv-result-rule-wrap")[0];
wrap.scrollTop = 135;
const toggle = collectByClass(page.panel, "dv-only-issues-switch")[0];
await toggle.dispatch("click");
const search = collectByClass(page.panel, "dv-result-search")[0];
assert.ok(search); search.value = "余额"; await search.dispatch("change");
await findButton(page.panel, "查看异常").dispatch("click");
const drawer = collectByClass(page.panel, "dv-result-drawer")[0];
assert.ok(drawer); assert.match(collectText(drawer), /按执行版本的范围核查/);
assert.match(collectText(drawer), /SELECT amount AS 余额 FROM loan/);
for (const label of ["数据源 / 目标表", "执行批次与检出", "2026-11-20 12:30:00", "发现 5 条异常记录", "业务校验口径", "异常校验 SQL", "复制 SQL", "共 5 条"]) assert.ok(collectText(drawer).includes(label), `保留完整明细要素：${label}`);
const overlay = collectByClass(page.panel, "dv-result-overlay")[0];
assert.equal(overlay.hidden, false);
document.activeElement = new FakeElement("body");
await overlay.dispatch("click");
assert.equal(overlay.hidden, true, "按用户要求点击遮罩收起结果明细");
await findButton(page.panel, "查看异常").dispatch("click");
const issueTable = collectByClass(page.panel, "dv-issue-table")[0];
const issueWrap = collectByClass(page.panel, "dv-issue-table-wrap")[0]; issueWrap.scrollLeft = 47;
const before = calls.length;
await trendButton.dispatch("click");
assert.equal(calls.length, before, "切换模式不请求数据或清空当前明细");
assert.equal(overlay.hidden, false); assert.equal(state.activeTaskId, 3);
assert.equal(toggle.getAttribute("aria-checked"), "false"); assert.equal(search.value, "余额");
assert.equal(collectByClass(page.panel, "dv-rule-result-table")[0], table);
assert.equal(collectByClass(page.panel, "dv-issue-table")[0], issueTable);
assert.equal(wrap.scrollTop, 135); assert.equal(issueWrap.scrollLeft, 47);
assert.equal(collectByClass(page.panel, "dv-result-trend")[0].hidden, false);
const trendSummary = collectByClass(page.panel, "dv-trend-summary")[0];
assert.ok(collectByClass(page.panel, "dv-trend-heading")[0].children.includes(trendSummary), "批次摘要位于趋势标题栏上方");
assert.equal(collectByClass(page.panel, "dv-trend-filter").length, 0, "按用户要求移除全部/已完成筛选");
assert.match(collectText(collectByClass(page.panel, "dv-trend-axis")[0]), /2026-11-20 12:30:00/, "趋势图轴显示完整时间");
for (const label of ["当前批次", "2026-11-20 12:30:00", "规则执行", "异常总数", "覆盖条线", "-2"]) assert.ok(collectText(trendSummary).includes(label), `紧凑趋势摘要保留：${label}`);
assert.equal(collectByClass(page.panel, "dv-result-toolbar")[0].hidden, false, "抽屉不替换下方规则列表");
await findButton(page.panel, "精简快切").dispatch("click");
assert.equal(collectByClass(page.panel, "dv-result-trend")[0].hidden, true);
assert.equal(overlay.hidden, false);
await findButton(page.panel, "返回规则列表").dispatch("click");
assert.equal(overlay.hidden, true);
assert.ok(document.activeElement === collectByClass(page.panel, "dv-table-action")[0], "关闭后焦点返回重绘后的当前规则按钮");
search.value = ""; await search.dispatch("change");
assert.equal(findButton(page.panel, "查看口径"), null, "无异常规则不再提供查看口径");
const cleanRow = table.children[1].children.find(row=>collectText(row).includes("日期核查"));
assert.equal(collectText(cleanRow.children[5]), "-");
const issueCount = calls.filter(c => c[0] === "issues").length;
await cleanRow.dispatch("click"); assert.equal(overlay.hidden, true, "无异常行点击也不打开明细");
assert.equal(calls.filter(c => c[0] === "issues").length, issueCount);
await findButton(page.panel, "上一批次").dispatch("click");
assert.equal(state.activeTaskId, 2); assert.equal(overlay.hidden, true);
await findButton(page.panel, "立即执行").dispatch("click");
assert.equal(calls.at(-1)[0], "execute", "保留原执行弹窗入口回调");
await findButton(page.panel, "查看全部批次").dispatch("click");
const batchOverlay = collectByClass(page.panel, "dv-overlay")[0]; assert.ok(batchOverlay);
await batchOverlay.dispatch("click"); assert.equal(batchOverlay.parentNode, null, "全部批次侧栏点击外部空白收起");
page.stopPolling(); runtime.destroy();

// 已运行的旧后端可能返回分页数据却忽略 keyword，不能将其冒充筛选结果。
{
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const state = createState(); state.activeTab = "results";
  let total = 1;
  const page = createResultsPage({ state, runtime, listen: runtime.listen,
    api: { tasks: async () => [batch], taskDetails: async () => ({ ...batch,
      rules: [rules[0]], rule_page: { total, page: 1, page_size: 50 } }) },
    user: { id: "1", role: "admin" }, host: new FakeElement("div"), notify() {}, confirmAction: async () => true,
    onNewTask() {}, onPeriodChange() {} });
  await page.loadTasks();
  const search = collectByClass(page.panel, "dv-result-search")[0];
  search.value = "读到"; await search.dispatch("change");
  const table = collectByClass(page.panel, "dv-rule-result-table")[0];
  assert.equal(table.children[1].children.length, 0, "不匹配的关键词不能保留旧后端返回的规则");
  assert.match(collectText(page.panel), /没有匹配的规则/);
  assert.match(collectText(page.panel), /规则执行（0）/);
  search.value = "余额"; await search.dispatch("change");
  assert.equal(table.children[1].children.length, 1);
  total = 51;
  search.value = "其他页"; await search.dispatch("change");
  assert.match(collectText(page.panel), /当前服务尚未加载规则搜索/,
    "旧后端多页数据不能把仅当前页无匹配冒充全批次无匹配");
  runtime.destroy();
}

// 在首个详情响应前搜索，必须重新请求当前关键字，不能卡在加载中。
{
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const state = createState(); state.activeTab = "results";
  let finishFirst, count = 0; const queries = [];
  const page = createResultsPage({ state, runtime, listen: runtime.listen, user: { id: "1", role: "admin" },
    api: { tasks: async () => [batch], taskDetails: async (_id, query) => {
      count++; queries.push({ ...query });
      if (count === 1) return new Promise(resolve => { finishFirst = resolve; });
      return { ...batch, rules: query.keyword === "不存在" ? [] : [rules[0]], rule_page: { total: query.keyword === "不存在" ? 0 : 1, page: 1, page_size: 50 } };
    } }, host: new FakeElement("div"), notify() {}, onNewTask() {}, onPeriodChange() {} });
  const loading = page.loadTasks();
  for (let i = 0; i < 30 && !finishFirst; i++) await Promise.resolve();
  assert.ok(finishFirst);
  const search = collectByClass(page.panel, "dv-result-search")[0]; search.value = "余额";
  await search.dispatch("input"); await search.dispatch("change");
  finishFirst({ ...batch, rules: [], rule_page: { total: 0, page: 1, page_size: 50 } }); await loading;
  assert.equal(queries.length, 2); assert.equal(queries.at(-1).keyword, "余额");
  assert.match(collectText(collectByClass(page.panel, "dv-rule-result-table")[0]), /余额核查/);
  search.value = "不存在"; await search.dispatch("change");
  assert.match(collectText(collectByClass(page.panel, "dv-table-feedback")[0]), /没有匹配的规则/);
  page.stopPolling(); runtime.destroy();
}

// 运行中的规则产生异常后，最后轮询刷新列表并提供明细入口。
{
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const state = createState(); state.activeTab = "results";
  let finished = false, issues = 0;
  const task = () => ({ ...batch, status: finished ? "completed" : "running" });
  const page = createResultsPage({ state, runtime, listen: runtime.listen, user: { id: "1", role: "admin" },
    api: { tasks: async () => [task()], taskDetails: async () => ({ ...task(), rules: [{ ...rules[0], status: finished ? "VIOLATION" : "running", violation_count: finished ? 5 : 0 }] }),
      issues: async () => { issues++; return { items: [{ rule_id: 7, query_result: { columns: [{ name: "余额" }], values: { "余额": 5 } } }], total: 1, page: 1, page_size: 50 }; } },
    host: new FakeElement("div"), notify() {}, onNewTask() {}, onPeriodChange() {} });
  await page.loadTasks(); await collectByClass(page.panel, "dv-only-issues-switch")[0].dispatch("click");
  assert.equal(findButton(page.panel, "查看异常"), null); assert.equal(issues, 0);
  finished = true; await page.loadTasks({ poll: true });
  await findButton(page.panel, "查看异常").dispatch("click");
  assert.equal(issues, 1); assert.match(collectText(collectByClass(page.panel, "dv-issue-table")[0]), /余额/);
  page.stopPolling(); runtime.destroy();
}

// 轮询失败仍展示上次结果，但必须明确提示刷新失败，成功后清除。
{
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const state = createState(); state.activeTab = "results"; let fail = false;
  const page = createResultsPage({ state, runtime, listen: runtime.listen, user: { id: "1", role: "admin" },
    api: { tasks: async () => { if (fail) throw new Error("网络暂不可用"); return [batch]; },
      taskDetails: async () => ({ ...batch, rules }) }, host: new FakeElement("div"), notify() {}, onNewTask() {}, onPeriodChange() {} });
  await page.loadTasks(); fail = true; await page.loadTasks({ poll: true });
  assert.match(collectText(page.panel), /批次刷新失败/);
  const feedback = collectByClass(page.panel, "dv-batch-feedback")[0]; assert.equal(feedback.hidden, false);
  fail = false; await page.loadTasks({ poll: true }); assert.equal(feedback.hidden, true);
  page.stopPolling(); runtime.destroy();
}
// 旧详情接口遗漏审阅字段时，只有与执行快照完全相同的版本才能补齐。
for (const { mismatch = false, legacyIdentity = false, patch = {}, fail = false } of [
  {}, { legacyIdentity: true },
  { mismatch: true, patch: { version_no: 2 } },
  { mismatch: true, legacyIdentity: true, patch: { version_no: 2 } },
  { mismatch: true, patch: { version_id: 71 } },
  { mismatch: true, patch: { content_sha256: "b".repeat(64) } },
  { mismatch: true, patch: { id: 8 } },
  { mismatch: true, fail: true },
]) {
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const state = createState(); state.activeTab = "results";
  const hash = "a".repeat(64);
  const legacy = { ...rules[0], version_id: 70, content_sha256: hash };
  delete legacy.description; delete legacy.sql_text;
  if (legacyIdentity) { delete legacy.version_id; delete legacy.content_sha256; }
  let reviewCalls = 0;
  const page = createResultsPage({ state, runtime, listen: runtime.listen,
    api: { tasks: async () => [batch], taskDetails: async () => ({ ...batch, rules: [legacy] }),
      rule: async () => { reviewCalls++; if (fail) throw new Error("读取被拒绝");
        return { id: 7, version_id: 70, version_no: 1, content_sha256: hash,
          definition: { description: "执行版本口径", violation_message: "本次提醒" }, sql_text: "SELECT frozen_amount FROM loan", ...patch }; },
      issues: async () => ({ items: [], total: 0, page: 1, page_size: 50 }) },
    user: { id: "1", role: "admin" }, host: new FakeElement("div"), notify() {}, confirmAction: async () => true,
    onNewTask() {}, onPeriodChange() {} });
  await page.loadTasks(); await findButton(page.panel, "查看异常").dispatch("click");
  assert.equal(reviewCalls, 1);
  const drawer = collectByClass(page.panel, "dv-result-drawer")[0];
  if (mismatch) {
    assert.ok(!collectText(drawer).includes("SELECT frozen_amount"), "新版 SQL 不得冒充历史执行口径");
    assert.match(collectText(drawer), /当前服务未提供本次执行版本/);
  } else {
    assert.match(collectText(drawer), /执行版本口径/);
    assert.match(collectText(drawer), /SELECT frozen_amount FROM loan/);
    await page.loadTasks({ poll: true });
    assert.match(collectText(drawer), /SELECT frozen_amount FROM loan/, "旧详情刷新不会抹掉已核对的执行版本 SQL");
  }
  runtime.destroy();
}

// 抽屉关闭后的迟到口径响应不能重新打开或污染明细。
{
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const state = createState(); state.activeTab = "results";
  let finishReview;
  const legacy = { ...rules[0], version_id: 70, content_sha256: "a".repeat(64) };
  delete legacy.description; delete legacy.sql_text;
  const page = createResultsPage({ state, runtime, listen: runtime.listen,
    api: { tasks: async () => [batch], taskDetails: async () => ({ ...batch, rules: [legacy] }),
      rule: async () => new Promise(resolve => { finishReview = resolve; }),
      issues: async () => ({ items: [], total: 0, page: 1, page_size: 50 }) },
    user: { id: "1", role: "admin" }, host: new FakeElement("div"), notify() {}, confirmAction: async () => true,
    onNewTask() {}, onPeriodChange() {} });
  await page.loadTasks(); const opening = findButton(page.panel, "查看异常").dispatch("click");
  for (let i = 0; i < 20 && !finishReview; i++) await Promise.resolve();
  assert.ok(finishReview);
  await findButton(page.panel, "关闭规则明细").dispatch("click");
  finishReview({ id: 7, version_id: 70, version_no: 1, content_sha256: legacy.content_sha256,
    definition: { description: "迟到说明" }, sql_text: "SELECT late_sql FROM loan" });
  await opening;
  assert.equal(collectByClass(page.panel, "dv-result-overlay")[0].hidden, true);
  assert.ok(!collectText(collectByClass(page.panel, "dv-result-drawer")[0]).includes("late_sql"));
  runtime.destroy();
}
// 展示和复制都使用已替换变量的 SQL，保留模板但不复制模板。
{
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const state = createState(); state.activeTab = "results";
  const display = "SELECT amount FROM loan WHERE report_date = '2026-11-20' AND kind IN ('1', '3')";
  const page = createResultsPage({ state, runtime, listen: runtime.listen,
    api: { tasks: async () => [batch], taskDetails: async () => ({ ...batch, rules: [{ ...rules[0],
      sql_text: "SELECT amount FROM loan WHERE report_date = :report_date AND kind IN (:filter_1_0, :filter_1_1)", sql_display: display }] }),
      issues: async () => ({ items: [], total: 0, page: 1, page_size: 50 }) },
    user: { id: "1", role: "admin" }, host: new FakeElement("div"), notify() {}, confirmAction: async () => true,
    onNewTask() {}, onPeriodChange() {} });
  await page.loadTasks(); await findButton(page.panel, "查看异常").dispatch("click");
  assert.equal(collectText(collectByClass(page.panel, "dv-review-sql")[0]), display);
  let copied;
  const prior = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: { writeText: async sql => { copied = sql; } } } });
  try { await findButton(page.panel, "复制 SQL").dispatch("click"); assert.equal(copied, display); }
  finally { if (prior) Object.defineProperty(globalThis, "navigator", prior); else delete globalThis.navigator; runtime.destroy(); }
}
console.log(JSON.stringify({ ok: true }));
