import { TEST_CASE_STATUS_LABELS, TEST_CASE_STATUS_TONES, labelFor, toneFor } from "../constants.js";
import { confirmationReadiness, previewReadiness } from "../state.js";
import { button, element, emptyState, select, statusBadge } from "./dom.js";

function formatSampleValue(value) {
  if (value === null || value === undefined) return "空值";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatSample(row, columns, relatedColumns = []) {
  if (!row || typeof row !== "object") return "—";
  if (Object.prototype.hasOwnProperty.call(row, "base") || Object.prototype.hasOwnProperty.call(row, "related")) {
    const parts = [];
    for (const [key, value] of Object.entries(row.base || {})) {
      const name = columns.find((column) => column.column_name === key)?.comment || key;
      parts.push(`${name}：${formatSampleValue(value)}`);
    }
    const related = Array.isArray(row.related) ? row.related : [];
    related.forEach((item, index) => {
      const inner = Object.entries(item || {}).map(([key, value]) => {
        const name = relatedColumns.find((column) => column.column_name === key)?.comment || key;
        return `${name}：${formatSampleValue(value)}`;
      }).join("；");
      parts.push(`关联${related.length > 1 ? ` ${index + 1}` : ""}：${inner || "无字段"}`);
    });
    if (Object.prototype.hasOwnProperty.call(row, "report_date")) parts.push(`报送日期：${formatSampleValue(row.report_date)}`);
    return parts.join("；") || "—";
  }
  return Object.entries(row).map(([key, value]) => {
    const name = columns.find((column) => column.column_name === key)?.comment || key;
    return `${name}：${formatSampleValue(value)}`;
  }).join("；") || "—";
}

export function createTestPanel({ listen, onTest, onCaseChange, onDecision, showSql = true }) {
  const sql = element("pre", { className: "dv-sql-preview" });
  const totals = [0, 1, 2].map(() => element("strong", { className: "dv-test-metric-value", text: "—" }));
  const metrics = element("div", { className: "dv-test-metrics" },
    element("div", {}, element("span", { text: "测试用例" }), totals[0]),
    element("div", {}, element("span", { text: "通过" }), totals[1]),
    element("div", {}, element("span", { text: "失败 / 未运行" }), totals[2]));
  const body = element("tbody");
  const table = element("table", { className: "dv-table dv-test-table" },
    element("thead", {}, element("tr", {}, ...["测试场景", "样本输入", "预期判断", "实际判断", "测试结果"].map((label) => element("th", { text: label })))), body);
  const tableWrap = element("div", { className: "dv-test-table-wrap dv-scroll" }, table);
  const feedback = element("div", { className: "dv-test-feedback" });
  const decisions = element("div", { className: "dv-test-decisions" });
  const readinessText = element("p", { className: "dv-readiness" });
  const test = button("运行测试", { listen, className: "dv-button dv-button-primary", capability: "dv.test", onClick: onTest });
  const root = element("section", { className: "dv-test-panel" },
    element("div", { className: "dv-test-toolbar" }, test), metrics,
    showSql ? element("div", { className: "dv-sql-section" }, element("h3", { text: "服务端规则 SQL（detail.sql_text）" }), sql) : null,
    feedback, decisions, tableWrap, readinessText,
    element("p", { className: "dv-muted", text: "样本由字段类型合成，不读取业务数据；通过不代表已在业务库执行 SQL。运行测试、保存草稿和启用是独立操作。" }));
  let caseRemovers = [];
  return {
    element: root,
    update({ detail, evidence, dirty, canTest, readOnly, busy = false, testing = false, preview = null, previewCases = null, columns = [], relatedColumns = [], stale = false }) {
      caseRemovers.forEach((remove) => remove?.()); caseRemovers = [];
      const readiness = preview ? previewReadiness(preview, evidence, stale) : confirmationReadiness(detail, evidence, dirty);
      const related = relatedColumns.length ? relatedColumns : (preview?.definition?.related_columns || []);
      sql.textContent = detail ? detail.sql_text || "规则尚未成功编译 SQL。" : "保存草稿后显示已保存版本的 SQL。";
      const cases = evidence?.cases || previewCases || preview?.cases || [];
      totals[0].textContent = cases.length ? String(cases.length) : "—";
      totals[1].textContent = evidence ? String(Number(evidence.passed_count) || 0) : "—";
      totals[2].textContent = evidence ? `${Number(evidence.failed_count) || 0} / ${Number(evidence.not_run_count) || 0}` : cases.length ? `0 / ${cases.length}` : "—";
      body.replaceChildren();
      cases.forEach((item, index) => {
        const row = element("tr");
        let expected = element("span", { text: item.expected_count === 1 ? "提醒核实" : item.expected_count === 0 ? "不提醒" : "待确认" });
        if (preview && onCaseChange && !readOnly) {
          expected = select([[0, "不提醒"], [1, "提醒核实"]], { value: String(item.expected_count), className: "dv-select dv-case-expected" });
          expected.disabled = busy || testing || stale;
          expected.setAttribute("aria-label", `${item.name || "样本"}的预期判断`);
          caseRemovers.push(listen(expected, "change", () => onCaseChange(index, Number(expected.value))));
        }
        const sample = formatSample(item.row, columns, related);
        row.append(element("td", { text: item.name === "正常" ? "正常（本条不提醒）" : item.name || "未命名案例" }), element("td", { text: sample }),
          element("td", {}, expected), element("td", { text: item.actual_count === null || item.actual_count === undefined ? "—" : item.actual_count ? "提醒核实" : "不提醒" }),
          element("td", {}, statusBadge(labelFor(item.status || "not_run", TEST_CASE_STATUS_LABELS) || "未运行", toneFor(item.status || "not_run", TEST_CASE_STATUS_TONES))));
        body.append(row);
      });
      tableWrap.hidden = !cases.length;
      feedback.replaceChildren(); decisions.replaceChildren();
      if (testing) feedback.append(emptyState("正在运行样本测试…", "结果由后端计算返回，不执行真实业务查询"));
      else if (preview && !evidence) feedback.append(element("p", { className: "dv-muted", text: "已按字段类型准备测试用例，可先检查预期判断并直接运行，无需保存草稿。" }));
      else if (!detail && !preview) feedback.append(emptyState("请先完成分析", "生成 SQL 后即可直接检查并运行测试用例"));
      else if (!evidence) feedback.append(emptyState("当前版本尚未在本页运行测试", "请核对用例并运行，确认前需要当前版本的通过结果"));
      else if (!cases.length) feedback.append(emptyState("没有测试证据", "不能确认启用"));
      const unaryExpression = ["is_null", "is_not_null"].includes(preview?.definition?.expression?.op);
      if (preview?.definition.null_policy === "unresolved" && !unaryExpression) {
        const skip = button("空值由其他规则检查，本条跳过", { className: "dv-button dv-button-plain" });
        skip.disabled = busy || testing || stale;
        caseRemovers.push(listen(skip, "click", () => onDecision?.("null_policy", "skip")));
        decisions.append(element("p", { text: "遇到空值时怎么办？当前尚未确认，空值用例不会算作通过。" }), skip);
      }
      test.hidden = !canTest || readOnly;
      test.disabled = busy || stale || readOnly || (preview ? !preview.sql_preview : !detail || dirty);
      test.textContent = testing ? "测试执行中…" : evidence ? "重新运行测试" : "运行测试";
      test.title = preview ? "直接运行当前未保存定义的文档合成样本" : dirty ? "规则已修改，请先保存新版本" : "运行已保存版本的样本测试";
      readinessText.textContent = readiness.ready ? `测试已通过 ${evidence.passed_count} 项，可决定保存草稿或启用。` : readiness.reasons.join("；");
      readinessText.classList.toggle("is-ready", readiness.ready);
      return readiness;
    },
  };
}
