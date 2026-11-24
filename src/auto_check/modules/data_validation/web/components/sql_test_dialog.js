import { errorMessage, isAbortError } from "../runtime.js";
import { createDialog } from "./dialog.js";
import { button, element, field, input } from "./dom.js";
import { aiIcon } from "./ai_visuals.js";
import { displayIssueKind } from "./result_fields.js";

export function previousMonthEnd(now = new Date()) {
  const day = new Date(now.getFullYear(), now.getMonth(), 0);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}

function cellValue(row, name) {
  const unavailable = row.unavailable?.[name];
  if (unavailable) return unavailable === "oversized" ? "内容超出显示上限" : "暂不支持显示";
  if (!Object.prototype.hasOwnProperty.call(row.values || {}, name)) return "未返回";
  const value = row.values[name];
  if (value === null) return "NULL";
  return value === "" ? "空字符串" : String(value);
}

export function openSqlTestDialog({ host, api, preview, parent = null, now = new Date() }) {
  let controller = null;
  let busy = false;
  const snapshot = structuredClone(preview);
  const parentWasInert = parent?.inert;
  if (parent) parent.inert = true;
  const dialog = createDialog({ host, title: "测试运行结果", icon: aiIcon("database"), subtitle: "只读试运行", className: "dv-sql-test-dialog",
    onClose: () => { controller?.abort(); if (parent) parent.inert = parentWasInert; } });
  const date = input({ type: "date", value: previousMonthEnd(now), className: "dv-input dv-sql-test-date" });
  date.setAttribute("aria-label", "报送日期");
  const runButton = button("重新运行", { className: "dv-button dv-button-primary", capability: "dv.test" });
  const feedback = element("div", { className: "dv-sql-test-feedback", attrs: { role: "status", "aria-live": "polite" } });
  const status = element("span", { className: "dv-status" });
  const state = element("div", { className: "dv-empty dv-sql-test-state" });
  const head = element("thead"), body = element("tbody");
  const table = element("table", { className: "dv-table dv-sql-test-table" }, head, body);
  const wrap = element("div", { className: "dv-sql-test-table-wrap dv-scroll", hidden: true }, table);
  const result = element("section", { className: "dv-sql-test-results", attrs: { "aria-label": "查询结果" } },
    element("div", { className: "dv-sql-test-result-heading" },
      element("div", { className: "dv-sql-test-result-title" }, element("h3", { text: "查询结果" }), status), feedback), state, wrap);
  dialog.body.append(element("div", { className: "dv-sql-test-toolbar" },
    element("div", { className: "dv-sql-test-controls" }, field("报送日期", date), runButton),
    element("span", { className: "dv-sql-test-limit" }, aiIcon("info"), "最多返回 10 条数据")), result);
  const done = button("关闭", { className: "dv-button" });
  dialog.footer.append(done);
  dialog.bind(done, "click", dialog.close);
  dialog.bind(runButton, "click", run);
  dialog.bind(date, "change", () => {
    if (busy) return;
    head.replaceChildren(); body.replaceChildren();
    status.className = "dv-status"; status.textContent = "待运行";
    feedback.textContent = "日期已修改";
    showState("idle", "报送日期已修改", "点击重新运行，查看所选日期的查询结果。");
  });

  function showState(tone, title, detail) {
    wrap.hidden = true;
    state.hidden = false;
    state.className = `dv-empty dv-sql-test-state is-${tone}`;
    state.replaceChildren(element("span", { className: "dv-sql-test-state-icon" }, aiIcon(
      tone === "empty" ? "check" : tone === "error" ? "info" : "database")),
    element("strong", { text: title }), element("p", { text: detail }));
  }
  dialog.bind(dialog.dialog, "keydown", event => {
    if (event.key !== "Tab") return;
    event.preventDefault();
    const controls = [dialog.closeButton, date, runButton, done].filter(control => !control.disabled);
    const index = controls.indexOf(document.activeElement);
    controls[index < 0 ? (event.shiftKey ? controls.length - 1 : 0)
      : (index + (event.shiftKey ? -1 : 1) + controls.length) % controls.length].focus();
  });

  async function run() {
    if (busy || dialog.isClosed()) return;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date.value)) {
      status.className = "dv-status is-warning"; status.textContent = "待运行";
      feedback.textContent = "日期未填写";
      showState("idle", "请选择报送日期", "选择报送日期后，点击重新运行。");
      return;
    }
    busy = true;
    dialog.body.setAttribute("aria-busy", "true");
    date.disabled = runButton.disabled = true;
    runButton.textContent = "运行中…";
    status.className = "dv-status"; status.textContent = "运行中";
    feedback.textContent = "请稍候";
    showState("loading", "正在查询数据", `正在查询 ${date.value} 的数据，请稍候。`);
    head.replaceChildren(); body.replaceChildren();
    controller?.abort(); controller = new AbortController();
    try {
      const result = await api.runCandidateSql({ definition: snapshot.definition,
        expected_hash: snapshot.content_sha256, report_date: date.value }, { signal: controller.signal });
      if (dialog.isClosed()) return;
      const columns = result.columns || [];
      const rows = (result.rows || []).slice(0, 10);
      head.append(element("tr", {}, element("th", { text: "序号" }),
        ...columns.map(column => element("th", { text: column.name }))));
      rows.forEach((row, index) => body.append(element("tr", {}, element("td", { text: index + 1 }),
        ...columns.map(column => element("td", { text: displayIssueKind(cellValue(row, column.name),
          column.name === (snapshot.definition.result_aliases?.issue_kind || "issue_kind")) })))));
      status.className = `dv-status${result.truncated ? " is-warning" : " is-success"}`;
      status.textContent = "运行完成";
      feedback.textContent = result.truncated ? "仅展示前 10 条数据，其余数据未展示。" : `返回 ${rows.length} 条`;
      if (rows.some(row => row.status || Object.keys(row.unavailable || {}).length)) {
        feedback.textContent += " 部分内容无法完整显示，请查看单元格提示。";
      }
      state.hidden = true;
      wrap.hidden = !rows.length || !columns.length;
      if (!rows.length) showState("empty", "未查询到异常数据",
        `${result.report_date || date.value} 的数据中，没有满足当前校验条件的记录。`);
    } catch (error) {
      if (dialog.isClosed() || isAbortError(error)) return;
      status.className = "dv-status is-danger"; status.textContent = "运行失败";
      feedback.textContent = "未返回结果";
      const code = error?.payload?.error?.code || error?.code;
      const message = code === "TIMEOUT" ? "测试运行超时，请重试或缩小查询范围。"
        : code === "SQL_TEST_LIMIT_REACHED" ? "测试运行较多，请稍后重试。" : errorMessage(error);
      showState("error", "暂时无法获取结果", message);
    } finally {
      busy = false;
      dialog.body.setAttribute("aria-busy", "false");
      if (!dialog.isClosed()) {
        date.disabled = runButton.disabled = false;
        runButton.textContent = "重新运行";
      }
    }
  }
  dialog.ready = run();
  return dialog;
}
