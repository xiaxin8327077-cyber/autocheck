import { errorMessage } from "../runtime.js";
import { hasCapability, isTaskActive, ownsResource } from "../state.js";
import { button, element } from "./dom.js";
import { aiIcon } from "./ai_visuals.js";
import { taskStatus } from "./task_list.js";
import { executionSummary, isExecutionPending, openExecutionProgress } from "./execution_progress.js";

const MAX_TRACKED = 20;
const idOf = value => Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;
const codeOf = error => error?.payload?.error?.code || error?.code;

export function createExecutionTasks({ runtime, api, user, host, notify, confirmAction, onViewResults, storage }) {
  if (storage === undefined) {
    try { storage = globalThis.localStorage; } catch { storage = null; }
  }
  const key = `data_validation:execution:${String(user?.id || "")}`;
  const tasks = new Map();
  const wanted = new Set();
  let active = false, destroyed = false, timer = null, dialog = null, selectedId = null;
  let detail = null, readError = "", detailError = "", cancelling = false;
  let detailPage = 1, detailPageSize = 20, actionBusy = "", refreshPromise = null;
  let removers = [];
  const root = element("aside", { className: "dv-execution-background dv-scroll", hidden: true,
    attrs: { "aria-label": "校验后台任务" } });
  const allowed = () => hasCapability(user, "dv.view_results");
  const owned = task => idOf(task?.id) && ownsResource(user, task);

  function persist() {
    try { storage?.setItem(key, JSON.stringify([...wanted].slice(-MAX_TRACKED))); } catch { /* 服务端任务仍可恢复。 */ }
  }
  function remember(task) {
    if (!owned(task)) return;
    const id = idOf(task.id);
    tasks.set(id, { ...tasks.get(id), ...task });
    wanted.add(id);
    // 不逐出活跃任务；历史完成提示按容量收敛。
    for (const known of wanted) {
      if (wanted.size <= MAX_TRACKED) break;
      if (!isExecutionPending(tasks.get(known)) && known !== selectedId) { wanted.delete(known); tasks.delete(known); }
    }
  }
  function schedule() {
    runtime.clearTimer(timer); timer = null;
    if (active && !destroyed && (readError || [...tasks.values()].some(isExecutionPending))) {
      const busy = [...tasks.values()].some(isTaskActive);
      const interval = globalThis.document?.hidden || !busy ? 15000 : readError ? 5000 : 2500;
      timer = runtime.setTimer(() => refresh(), interval);
    }
  }
  function render() {
    removers.forEach(remove => remove?.()); removers = [];
    root.replaceChildren();
    root.hidden = !active || !allowed() || (!tasks.size && !(readError && wanted.size)) || Boolean(dialog);
    const bind = (node, fn) => { removers.push(runtime.listen(node, "click", fn)); return node; };
    [...tasks.values()].sort((a, b) => Number(b.id) - Number(a.id)).forEach(task => {
      const summary = executionSummary(task), current = taskStatus(task);
      const activeTask = isExecutionPending(task);
      const line = element("div", { className: `dv-execution-background-task is-${current.tone}` },
        element("div", { className: "dv-execution-background-title" }, aiIcon(activeTask ? "database" : current.tone === "danger" ? "info" : "check"),
          element("strong", { text: `校验${current.label} · #${task.id}` }),
          element("span", { text: summary ? `${summary.finished} / ${summary.total} 条` : "进度待返回" })),
        element("div", { className: "dv-execution-background-meta", text: [
          (task.categories || []).map(item => item.name || item.code).join("、"), task.report_period,
        ].filter(Boolean).join(" · ") }));
      const action = bind(button(activeTask ? "查看进度" : "查看结果", {
        className: "dv-ai-text-button", capability: "dv.view_results",
      }), () => activeTask ? open(task.id) : viewResults(task));
      const controls = element("div", { className: "dv-execution-background-actions" },
        element("span", { className: "dv-execution-background-issues", text: summary ? `${summary.issues} 条异常${summary.truncated ? " · 结果截断" : ""}` : "异常数量待返回" }), action);
      if (!activeTask) controls.append(bind(button("关闭提示", { className: "dv-ai-text-button" }), () => {
        wanted.delete(idOf(task.id)); tasks.delete(idOf(task.id)); persist(); render();
      }));
      line.append(controls); root.append(line);
    });
    if (readError) root.append(element("div", { className: "dv-execution-background-error", attrs: { role: "status" } },
      element("span", { text: `进度刷新失败：${readError}` }), bind(button("重试", { className: "dv-ai-text-button" }), refresh)));
  }

  async function loadDetail() {
    const id = selectedId, currentDialog = dialog;
    if (!active || !id || !currentDialog) return;
    const token = runtime.next("execution-task-detail");
    currentDialog.update(detail || tasks.get(id), { loading: true, cancelling, action: actionBusy });
    try {
      const value = await runtime.request(token, signal => api.taskDetails(id, { page: detailPage, page_size: detailPageSize }, { signal }));
      if (!runtime.current(token) || dialog !== currentDialog || selectedId !== id) return;
      if (!owned(value) || idOf(value.id) !== id) throw Object.assign(new Error("无权查看该任务"), { code: "FORBIDDEN" });
      detail = value; detailError = ""; remember(value); persist();
      if (value.rule_page) { detailPage = value.rule_page.page; detailPageSize = value.rule_page.page_size; }
      currentDialog.update(detail, { cancelling, action: actionBusy }); render();
    } catch (error) {
      if (!runtime.current(token) || dialog !== currentDialog) return;
      detailError = errorMessage(error, "执行进度读取失败");
      currentDialog.update(detail || tasks.get(id), { error: detailError, cancelling, action: actionBusy });
    }
  }

  async function refresh() {
    if (refreshPromise) return refreshPromise;
    const promise = refreshOnce(); refreshPromise = promise;
    try { await promise; } finally { if (refreshPromise === promise) refreshPromise = null; }
  }
  async function refreshOnce() {
    if (!active || destroyed || !allowed()) return;
    runtime.clearTimer(timer); timer = null;
    const token = runtime.next("execution-tasks");
    const requestedIds = [...wanted];
    try {
      const summaryApi = typeof api.taskProgress === "function";
      let response;
      if (summaryApi) {
        const summaries = new Map();
        // 每次最多20个ID，仍覆盖所有已登记任务，避免较早批次停在运行状态。
        for (let offset = 0; offset < Math.max(1, requestedIds.length); offset += MAX_TRACKED) {
          const values = await runtime.request(token, signal => api.taskProgress(requestedIds.slice(offset, offset + MAX_TRACKED), { signal }));
          if (!runtime.current(token) || !active) return;
          if (Array.isArray(values)) values.forEach(task => summaries.set(idOf(task?.id), task));
        }
        response = [...summaries.values()];
      } else response = await runtime.request(token, signal => api.tasks({}, { signal }));
      if (!runtime.current(token) || !active) return;
      const ownedTasks = (Array.isArray(response) ? response : []).filter(owned);
      const returned = new Set(ownedTasks.map(task => idOf(task.id)));
      ownedTasks.filter(task => isExecutionPending(task) || wanted.has(idOf(task.id))).forEach(remember);
      // 恢复超出最近批次列表的已登记任务，仍由服务端校验归属。
      for (const id of requestedIds.filter(id => !returned.has(id))) {
        if (summaryApi) { wanted.delete(id); tasks.delete(id); continue; }
        try {
          const value = await runtime.request(token, signal => api.taskDetails(id, {}, { signal }));
          if (!runtime.current(token) || !active) return;
          if (owned(value)) remember(value);
          else { wanted.delete(id); tasks.delete(id); }
        } catch (error) {
          if (!runtime.current(token)) return;
          if (["FORBIDDEN", "TASK_NOT_FOUND"].includes(codeOf(error))) { wanted.delete(id); tasks.delete(id); }
          else throw error;
        }
      }
      readError = ""; persist(); render();
      if (dialog) await loadDetail();
    } catch (error) {
      if (!runtime.current(token) || !active) return;
      readError = errorMessage(error, "后台任务进度读取失败"); render();
      dialog?.update(detail || tasks.get(selectedId), { error: `进度刷新失败：${readError}`, cancelling });
    } finally { if (runtime.current(token) && active) schedule(); }
  }

  async function stop() {
    const id = selectedId;
    if (!id || cancelling || actionBusy || !hasCapability(user, "dv.run") || !owned(tasks.get(id)) || !isExecutionPending(tasks.get(id))) return;
    if (confirmAction && !await confirmAction("停止当前批次的剩余校验？已完成结果会保留。")) return;
    if (!active || id !== selectedId) return;
    cancelling = true;
    dialog?.update(detail || tasks.get(id), { cancelling: true, error: detailError });
    const token = runtime.next("execution-task-cancel");
    try {
      const value = await runtime.request(token, signal => api.cancelTask(id, { signal }));
      if (!runtime.current(token) || !active) return;
      if (owned(value)) remember(value);
      runtime.invalidate("execution-tasks"); refreshPromise = null;
      await refresh();
    } catch (error) {
      if (runtime.current(token)) {
        detailError = errorMessage(error, "停止请求失败，请重新读取任务状态");
        dialog?.update(detail || tasks.get(id), { error: detailError });
      }
    } finally {
      if (runtime.current(token)) {
        cancelling = false;
        dialog?.update(detail || tasks.get(selectedId), { error: detailError }); render(); schedule();
      }
    }
  }
  async function control(action) {
    const id = selectedId;
    if (!id || actionBusy || cancelling || !hasCapability(user, "dv.run") || !owned(tasks.get(id))) return;
    const task = tasks.get(id);
    if (action === "resume" ? task.status !== "paused" : !isTaskActive(task) || task.status === "pausing") return;
    const token = runtime.next("execution-task-control");
    actionBusy = action;
    dialog?.update(detail || task, { action: actionBusy });
    try {
      const value = await runtime.request(token, signal => action === "resume"
        ? api.resumeTask(id, { signal }) : api.pauseTask(id, { signal }));
      if (!runtime.current(token) || !active) return;
      if (owned(value)) { remember(value); if (selectedId === id && detail) detail = { ...detail, ...value }; }
      runtime.invalidate("execution-tasks"); refreshPromise = null;
      await refresh();
    } catch (error) {
      if (runtime.current(token)) detailError = errorMessage(error, action === "resume" ? "继续执行失败，请稍后重试" : "暂停请求失败，请重试");
    } finally {
      if (runtime.current(token)) {
        actionBusy = "";
        dialog?.update(detail || tasks.get(selectedId), { error: detailError }); render(); schedule();
      }
    }
  }
  async function viewResults(task) {
    if (!owned(task) || !allowed()) return;
    dialog?.close();
    await onViewResults?.(task);
  }
  async function open(value) {
    const id = idOf(value);
    if (!active || !allowed() || !owned(tasks.get(id))) return;
    dialog?.close(); selectedId = id; detail = null; detailError = ""; detailPage = 1; detailPageSize = 20;
    const opened = openExecutionProgress({ host, task: tasks.get(id), canStop: hasCapability(user, "dv.run"),
      onStop: stop, onPause: () => control("pause"), onResume: () => control("resume"),
      onResults: () => viewResults(tasks.get(id)), onRetry: loadDetail,
      onPage: page => { detailPage = page; return loadDetail(); },
      onPageSize: size => { detailPage = 1; detailPageSize = size; return loadDetail(); },
      onClose: () => {
        if (dialog !== opened) return;
        runtime.invalidate("execution-task-detail"); dialog = null; selectedId = null; detail = null; render();
      } });
    dialog = opened; render();
    await loadDetail(); schedule();
  }
  return {
    element: root, open, refresh,
    async activate() {
      if (destroyed || !allowed()) return;
      active = true;
      refreshPromise = null;
      try {
        const ids = JSON.parse(storage?.getItem(key) || "[]");
        if (Array.isArray(ids)) ids.slice(0, MAX_TRACKED).forEach(value => { const id = idOf(value); if (id) wanted.add(id); });
      } catch { /* 存储不可用时仍查询服务端活跃任务。 */ }
      render(); await refresh();
    },
    track(task) {
      if (!allowed()) { notify?.("任务已在后台提交，当前角色没有查看执行进度权限。", "info"); return; }
      remember(task); persist(); render(); schedule();
    },
    deactivate() {
      active = false;
      runtime.clearTimer(timer); timer = null;
      ["execution-tasks", "execution-task-detail", "execution-task-cancel", "execution-task-control"].forEach(runtime.invalidate);
      dialog?.close(); dialog = null; cancelling = false; actionBusy = ""; root.hidden = true;
    },
    destroy() {
      this.deactivate(); destroyed = true;
      removers.forEach(remove => remove?.()); removers = [];
      root.remove();
    },
  };
}
