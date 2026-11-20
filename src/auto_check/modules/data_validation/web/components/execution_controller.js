import { createExecutionTasks } from "./execution_tasks.js";

export function createExecutionController({ state, results, context, showResults, notify, ...options }) {
  function focus(task) {
    state.reportPeriod = task.report_period || state.reportPeriod;
    state.activeTaskId = Number(task.id);
    results.focusTask(task);
    state.issuesStatus = "idle";
  }
  const tracker = createExecutionTasks({ ...options, notify,
    onViewResults: async task => {
      focus(task);
      if (!await context.navigate?.("data-validation-results")) showResults();
    },
  });
  return { ...tracker,
    async started(task) {
      focus(task); tracker.track(task); await tracker.open(task.id);
      notify(`任务 #${task.id} 已提交，状态 ${task.status}`, "success");
      if (task.skipped?.length) notify(task.skipped.map(item => `规则 ${item.rule_id}：${item.reason}`).join("；"), "warning");
    },
  };
}
