import assert from "node:assert/strict";
import { FakeElement, collectByClass, collectText, findButton } from "./frontend_workbench_dom.mjs";
import { createRuntime } from "./runtime.mjs";
import { createExecutionTasks } from "./components/execution_tasks.mjs";
import { openExecutionProgress } from "./components/execution_progress.mjs";

const user = { id: "1", capabilities: ["dv.run", "dv.view_results"] };
const detail = (id = 4, status = "running") => ({ id, creator_user_id: "1", report_period: "2026-10-31", status,
  categories: [{ code: "group:pbc", name: "人行报送" }],
  summary: { rule_count: 4, completed_count: 2, failed_count: 0, issue_count: 3, truncated: false },
  rules: ["PASS", "VIOLATION", "RUNNING", "PENDING"].map((status, i) => ({ rule_id: i + 1,
    name: `校验规则${i + 1}`, rule_code: `DV00000${i + 1}`, version_no: 1, status, violation_count: i === 1 ? 3 : 0,
    table_name: "proj_info", table_name_cn: "项目信息", source_name: "监管报表" })) });

const viewHost = new FakeElement("div");
const view = openExecutionProgress({ host: viewHost, task: detail(), canStop: true });
assert.ok(collectText(view.body).includes("已完成 2 / 4 条"));
assert.ok(collectText(view.body).includes("50%"));
assert.ok(collectText(view.body).includes("3 条异常"));
assert.ok(collectText(view.body).includes("等待执行"));
assert.ok(collectText(view.body).includes("人行报送"));
assert.equal(collectByClass(view.body, "dv-execution-progress-track")[0].getAttribute("aria-valuenow"), "50");
await view.element.dispatch("click"); assert.equal(view.isClosed(), false);
await findButton(view.footer, "后台继续").dispatch("click"); assert.equal(view.isClosed(), true);

function environment(owner = user) {
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const timers = new Map(); let nextTimer = 0;
  runtime.setTimer = fn => { const id = ++nextTimer; timers.set(id, fn); return id; };
  runtime.clearTimer = id => timers.delete(id);
  const values = new Map();
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const host = new FakeElement("div");
  let current = detail(); let fail = false; let cancelled = 0; let reads = 0; let viewed = 0;
  const api = {
    tasks: async () => { reads++; if (fail) throw new Error("暂时断网"); return [current, { ...detail(9), creator_user_id: "2" }]; },
    taskDetails: async id => { reads++; return { ...current, id: Number(id) }; },
    cancelTask: async () => { cancelled++; current = { ...current, status: "cancelled" }; return current; },
  };
  const options = { runtime, api, user: owner, host, storage, notify() {}, confirmAction: async () => true,
    onViewResults: async () => { viewed++; } };
  const tracker = createExecutionTasks(options); host.append(tracker.element);
  return { tracker, options, runtime, host, values, timers, api, setTask: value => { current = value; },
    setFail: value => { fail = value; }, cancelled: () => cancelled, reads: () => reads, viewed: () => viewed };
}

const env = environment();
await env.tracker.activate();
assert.ok(collectText(env.tracker.element).includes("2 / 4"));
assert.ok(!collectText(env.tracker.element).includes("#9"), "管理员以外本人任务隔离");
assert.ok([...env.values.values()].some(value => value.includes("4")));
assert.ok([...env.values.values()].every(value => !value.includes("proj_info") && !value.includes("人行")), "仅持久化任务 ID");
await env.tracker.open(4);
let overlay = env.host.children.find(node => node.classList?.contains("dv-overlay"));
await overlay.dispatch("click");
assert.ok(env.host.children.includes(overlay));
await findButton(overlay, "后台继续").dispatch("click");
assert.equal(env.cancelled(), 0, "关闭进度不取消后台任务");
assert.ok(env.timers.size > 0, "关闭弹窗保留后台轮询");
env.setFail(true); await env.tracker.refresh();
assert.ok(collectText(env.tracker.element).includes("进度刷新失败"));
assert.ok(collectText(env.tracker.element).includes("2 / 4"), "失败保留已知进度而非伪造零异常");
env.setFail(false);
await env.tracker.open(4);
overlay = env.host.children.find(node => node.classList?.contains("dv-overlay"));
await findButton(overlay, "停止执行").dispatch("click");
assert.equal(env.cancelled(), 1);
assert.ok(collectText(overlay).includes("已取消"));
env.tracker.deactivate();
assert.equal(env.timers.size, 0);
assert.equal(env.cancelled(), 1, "离开模块仅清理前端资源");
env.setTask({ ...detail(4, "completed"), summary: { rule_count: 4, completed_count: 4, failed_count: 0, issue_count: 3 },
  rules: detail().rules.map(r => ({ ...r, status: r.rule_id === 2 ? "VIOLATION" : "PASS" })) });
env.tracker.destroy();
const restored = createExecutionTasks(env.options); env.host.append(restored.element);
await restored.activate();
assert.ok(collectText(restored.element).includes("执行完成"));
await findButton(restored.element, "查看结果").dispatch("click");
assert.equal(env.viewed(), 1);
restored.destroy(); env.runtime.destroy();

const restricted = environment({ id: "2", capabilities: ["dv.run"] });
await restricted.tracker.activate(); restricted.tracker.track({ ...detail(8), creator_user_id: "2" });
assert.equal(restricted.reads(), 0, "无查看权限不查询任务接口");
restricted.tracker.destroy(); restricted.runtime.destroy();

const failure = openExecutionProgress({ host: viewHost, task: { ...detail(6, "partial_failed"),
  summary: { rule_count: 4, completed_count: 2, failed_count: 2, issue_count: 0, truncated: true } }, canStop: false });
assert.ok(collectText(failure.body).includes("失败"));
assert.ok(collectText(failure.body).includes("截断"));
assert.equal(findButton(failure.footer, "停止执行").hidden, true);
failure.close();
console.log(JSON.stringify({ ok: true }));
