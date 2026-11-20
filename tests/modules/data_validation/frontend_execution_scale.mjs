import assert from "node:assert/strict";
import { FakeElement, collectByClass, collectText, findButton } from "./frontend_workbench_dom.mjs";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { openExecutionProgress } from "./components/execution_progress.mjs";
import { createExecutionTasks } from "./components/execution_tasks.mjs";
import { createResultsPage } from "./pages/results.mjs";

const user = { id: "1", role: "user", capabilities: ["dv.view_results", "dv.run"] };
const row = id => ({ rule_id: id, id, name: `规则 ${id}`, rule_code: `DV${id}`, version_no: 1,
  status: "VIOLATION", violation_count: 3, source_name: "监管报表", table_name: "products", report_category: "group:pbc" });
const batch = { id: 81, creator_user_id: "1", report_period: "2026-10-31", status: "running",
  categories: [{ code: "group:pbc", name: "人行报送" }],
  summary: { rule_count: 10000, completed_count: 2000, failed_count: 0, issue_count: 3 } };
const host = new FakeElement("div");
const started = performance.now();
const bounded = openExecutionProgress({ host, task: { ...batch, rules: Array(10000).fill(row(1)) } });
assert.equal(collectByClass(bounded.body, "dv-execution-progress-table")[0].children[1].children.length, 20,
  "旧后端意外返回整批时前端也不能渲染一万行");
const renderMs = performance.now() - started;
bounded.close();

const runtime = createRuntime({ notify() {} }); runtime.activate();
const timers = new Map(); let timerId = 0; const delays = [];
runtime.setTimer = (fn, delay) => { delays.push(delay); const id = ++timerId; timers.set(id, fn); return id; };
runtime.clearTimer = id => timers.delete(id);
let task = structuredClone(batch), pauses = 0, resumes = 0, heavyReads = 0;
const detailRequests = [];
const api = {
  tasks: async () => { heavyReads++; throw new Error("不可轮询完整历史"); },
  taskProgress: async () => [structuredClone(task)],
  taskDetails: async (_id, query) => { detailRequests.push({ ...query }); const page = query.page || 1, size = query.page_size || 20;
    return { ...task, rule_page: { total: 10000, page, page_size: size },
      rules: Array.from({ length: size }, (_, i) => row((page - 1) * size + i + 1)) }; },
  pauseTask: async () => { pauses++; task = { ...task, status: "paused" }; return task; },
  resumeTask: async () => { resumes++; task = { ...task, status: "running" }; return task; },
};
const tracker = createExecutionTasks({ runtime, api, user, host, notify() {}, confirmAction: async () => true });
host.append(tracker.element); await tracker.activate(); await tracker.open(81);
let overlay = host.children.find(node => node.classList?.contains("dv-overlay"));
await findButton(overlay, "暂停执行").dispatch("click");
assert.equal(pauses, 1); assert.ok(collectText(overlay).includes("已暂停"));
assert.ok(delays.at(-1) >= 10000, "暂停后应降低后台轮询频率");
assert.equal(findButton(overlay, "查看结果").hidden, true, "暂停不是执行完成");
await findButton(overlay, "继续执行").dispatch("click"); assert.equal(resumes, 1);
await findButton(overlay, "下一页").dispatch("click");
assert.equal(detailRequests.at(-1).page, 2);
assert.equal(collectByClass(overlay, "dv-execution-progress-table")[0].children[1].children.length, 20);
assert.equal(heavyReads, 0);
tracker.destroy(); runtime.destroy();

let releaseSummary;
const pendingRuntime = createRuntime({ notify() {} }); pendingRuntime.activate();
const pendingTracker = createExecutionTasks({ runtime: pendingRuntime, user, host,
  api: { taskProgress: () => new Promise(resolve => { releaseSummary = resolve; }) } });
const activating = pendingTracker.activate();
pendingTracker.track({ ...batch, id: 82 });
releaseSummary([]); await activating;
assert.ok(collectText(pendingTracker.element).includes("#82"), "旧请求不能删除请求后新登记的任务");
pendingTracker.destroy(); pendingRuntime.destroy();

const manyRuntime = createRuntime({ notify() {} }); manyRuntime.activate();
manyRuntime.setTimer = () => 1; manyRuntime.clearTimer = () => {};
const progressRequests = [];
const manyTracker = createExecutionTasks({ runtime: manyRuntime, user, host, api: {
  taskProgress: async ids => {
    progressRequests.push(ids);
    return ids.map(id => ({ ...batch, id, status: "completed" }));
  },
} });
await manyTracker.activate();
for (let id = 101; id <= 125; id++) manyTracker.track({ ...batch, id });
await manyTracker.refresh();
assert.ok(progressRequests.some(ids => ids.includes(101)), "超过20个活跃任务时也要更新较早的任务终态");
assert.ok(progressRequests.every(ids => ids.length <= 20), "进度请求应遵守服务端20批限制");
assert.doesNotMatch(collectText(manyTracker.element), /校验运行中/, "全部已完成后不能遗留运行提示");
manyTracker.destroy(); manyRuntime.destroy();

const state = createState(); state.activeTab = "results"; state.reportPeriod = batch.report_period;
const resultsRuntime = createRuntime({ notify() {} }); resultsRuntime.activate();
resultsRuntime.setTimer = () => 1; resultsRuntime.clearTimer = () => {};
const requests = [];
const resultsApi = { tasks: async () => [batch], taskProgress: async () => [batch],
  taskDetails: async (_id, query) => { requests.push(query); return { ...batch,
    rule_page: { total: query.only_issues ? 97 : 10000, page: query.page || 1, page_size: 50 },
    rules: Array.from({ length: 50 }, (_, i) => row(((query.page || 1) - 1) * 50 + i + 1)) }; } };
const page = createResultsPage({ state, runtime: resultsRuntime, api: resultsApi, listen: resultsRuntime.listen, user,
  notify() {}, host: new FakeElement("div"), confirmAction: async () => true, onPeriodChange() {} });
await page.loadTasks();
assert.equal(requests.at(-1).only_issues, true, "异常筛选应在服务端分页前完成");
await findButton(page.panel, "只查看异常规则").dispatch("click");
assert.equal(requests.at(-1).only_issues, false);
await findButton(page.panel, "下一页").dispatch("click");
assert.equal(requests.at(-1).page, 2);
assert.equal(collectByClass(page.panel, "dv-rule-result-table")[0].children[1].children.length, 50);
const history = Array.from({ length: 100 }, (_, i) => ({ ...batch, id: 200 - i, status: "completed" }));
history[0].status = "running";
resultsApi.tasks = async () => history;
resultsApi.taskDetails = async id => ({ ...batch, id, status: id === 1 ? "completed" : "running",
  rules: [row(1)], rule_page: { total: 10000, page: 1, page_size: 50 } });
resultsApi.taskProgress = async () => [{ ...batch, id: 201 }];
page.focusTask({ ...batch, id: 1, status: "completed" }); await page.loadTasks();
assert.equal(state.activeTaskId, 1, "从后台提示打开早期批次时应保留指定批次");
await page.loadTasks({ poll: true });
assert.equal(state.activeTaskId, 1, "轮询新批次不能挤掉当前指定的早期批次");
assert.ok(state.tasks.some(task => task.id === 201), "指定批次保留时也应接收新增进度");
const listenersBeforePoll = resultsRuntime.snapshot().listeners;
for (let i = 0; i < 20; i++) await page.loadTasks({ poll: true });
assert.equal(resultsRuntime.snapshot().listeners, listenersBeforePoll, "长期轮询不能保留脱离DOM的分页监听器");
resultsRuntime.destroy();
console.log(JSON.stringify({ ok: true, bounded_rows: 20, render_ms: Math.round(renderMs * 100) / 100 }));
