import { TEST_CASE_STATUS_LABELS, TEST_CASE_STATUS_TONES, labelFor, toneFor } from "../constants.js";
import { confirmationReadiness, previewReadiness, visibleSql } from "../state.js";
import { button, element, emptyState, select, statusBadge } from "./dom.js";
import { aiIcon } from "./ai_visuals.js";

function formatSampleValue(value) {
  if (value === null || value === undefined) return "空值";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function isNestedSample(row) {
  return row && typeof row === "object" && ((row.base && typeof row.base === "object" && !Array.isArray(row.base)) || Array.isArray(row.related));
}

function projectSections(row, columns, relatedColumns, driver) {
  if (!row?.project || typeof row.project !== "object" || Array.isArray(row.project) || !Array.isArray(row.details)) return null;
  const reversed = driver?.table_role === "related";
  return [{ label: "项目", values: row.project, metadata: reversed ? relatedColumns : columns },
    ...row.details.map((values, index) => ({ label: `明细 ${index + 1}`, values,
      metadata: reversed ? columns : relatedColumns }))];
}

function formatSample(row, columns, relatedColumns = [], driver = null) {
  if (!row || typeof row !== "object") return "—";
  const sections = projectSections(row, columns, relatedColumns, driver);
  if (sections) {
    const parts = sections.map(({ label, values, metadata }) => `${label}：${Object.entries(values || {}).map(([key, value]) =>
      `${metadata.find((column) => column.column_name === key)?.comment || key}：${formatSampleValue(value)}`).join("；")}`);
    if (!row.details.length) parts.push("没有对应明细记录");
    parts.push(`报送日期：${formatSampleValue(row.report_date)}`);
    return parts.join("；");
  }
  if (isNestedSample(row)) {
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

function sampleDetails(row, columns, relatedColumns, driver) {
  const fields = element("dl", { className: "dv-test-sample-fields" });
  const add = (label, value) => fields.append(element("div", {}, element("dt", { text: label }), element("dd", { text: formatSampleValue(value) })));
  const addRow = (values, metadata, prefix = "") => Object.entries(values || {}).forEach(([key, value]) => {
    add(prefix + (metadata.find((column) => column.column_name === key)?.comment || key), value);
  });
  if (row && typeof row === "object") {
    const sections = projectSections(row, columns, relatedColumns, driver);
    if (sections) {
      sections.forEach(({ label, values, metadata }) => addRow(values, metadata, `${label} · `));
      if (!row.details.length) add("明细", "没有对应明细记录");
      add("报送日期", row.report_date);
    } else if (isNestedSample(row)) {
      addRow(row.base, columns);
      const related = Array.isArray(row.related) ? row.related : [];
      related.forEach((record, i) => addRow(record, relatedColumns, `关联表${related.length > 1 ? ` ${i + 1}` : ""} · `));
      if (Array.isArray(row.related) && !related.length) add("关联记录", "无");
      Object.entries(row).filter(([key]) => !["base", "related"].includes(key)).forEach(([key, value]) => {
        add(key === "report_date" ? "报送日期" : key, value);
      });
    } else addRow(row, columns);
  } else add("样本", "—");
  return element("details", { className: "dv-test-sample" }, element("summary", { text: "查看样本" }), fields);
}

export function createTestPanel({ listen, onTest, onCaseChange, showSql = true }) {
  const sql = element("pre", { className: "dv-sql-preview" });
  const totals = [0, 1, 2].map(() => element("strong", { className: "dv-test-metric-value", text: "—" }));
  const metrics = element("div", { className: "dv-test-metrics" },
    element("div", {}, element("span", { text: "测试用例" }), totals[0]),
    element("div", {}, element("span", { text: "通过" }), totals[1]),
    element("div", {}, element("span", { text: "失败 / 未运行" }), totals[2]));
  const body = element("tbody");
  const headings = showSql ? ["测试场景", "样本输入", "预期判断", "实际判断", "测试结果"] : ["测试场景", "预期判断", "实际判断", "测试结果"];
  const table = element("table", { className: "dv-table dv-test-table" },
    element("thead", {}, element("tr", {}, ...headings.map((label) => element("th", { text: label })))), body);
  const tableWrap = element("div", { className: "dv-test-table-wrap dv-scroll" }, table);
  const feedback = element("div", { className: "dv-test-feedback" });
  const readinessText = element("p", { className: "dv-readiness" });
  const test = button("运行测试", { className: "dv-button dv-button-primary", capability: "dv.test" });
  const removeTest = listen(test, "click", onTest);
  const summaryStatus = element("span", { className: "dv-test-summary-status", attrs: { role: "status" } });
  const summaryCounts = element("span", { className: "dv-test-summary-counts" });
  const filter = button("只看未通过", { className: "dv-test-filter" });
  filter.setAttribute("aria-pressed", "false");
  const summary = element("div", { className: "dv-test-summary", hidden: showSql }, summaryStatus, summaryCounts, filter);
  const filterEmpty = element("div", { className: "dv-test-filter-empty", hidden: true, text: "没有未通过的测试用例" });
  metrics.hidden = !showSql;
  const root = element("section", { className: `dv-test-panel${showSql ? "" : " dv-test-panel-ai"}` },
    element("div", { className: "dv-test-toolbar", hidden: !showSql }, test), metrics, summary,
    showSql ? element("div", { className: "dv-sql-section" }, element("h3", { text: "规则 SQL" }), sql) : null,
    feedback, tableWrap, filterEmpty, readinessText,
    showSql ? element("p", { className: "dv-muted", text: "样本由字段类型合成，不读取业务数据；通过不代表已在业务库执行 SQL。运行测试、保存草稿和启用是独立操作。" }) : null);
  let caseRemovers = [];
  let failedOnly = false;
  let lastModel = null;
  let disposed = false;
  const removeFilter = listen(filter, "click", () => {
    if (disposed || filter.disabled || !lastModel) return;
    failedOnly = !failedOnly;
    panel.update(lastModel);
  });
  const panel = {
    element: root,
    dispose() {
      disposed = true;
      lastModel = null;
      removeTest?.();
      removeFilter?.();
      caseRemovers.forEach((remove) => remove?.());
      caseRemovers = [];
    },
    update(model) {
      lastModel = model;
      const { detail, evidence, dirty, canTest, readOnly, busy = false, testing = false, preview = null, previewCases = null, columns = [], relatedColumns = [], stale = false, caseItems = null } = model;
      caseRemovers.forEach((remove) => remove?.()); caseRemovers = [];
      const readiness = preview ? previewReadiness(preview, evidence, stale) : confirmationReadiness(detail, evidence, dirty);
      const related = relatedColumns.length ? relatedColumns : (preview?.definition?.related_columns || []);
      sql.textContent = detail ? visibleSql(detail) || "尚无可展示的规则 SQL。" : "保存草稿后显示已保存版本的 SQL。";
      const rows = caseItems || (evidence?.cases || previewCases || preview?.cases || []).map((item, index) => ({ item, index, columns, relatedColumns: related }));
      const cases = rows.map(({ item }) => item);
      const count = (status) => cases.filter((item) => (item.status || "not_run") === status).length;
      const passed = count("passed"), failed = count("failed"), notRun = count("not_run");
      if (!showSql) {
        summary.hidden = !cases.length;
        const allPassed = cases.length > 0 && passed === cases.length && !testing;
        summaryStatus.classList.toggle("is-success", allPassed);
        summaryStatus.classList.toggle("is-error", failed > 0 && !testing);
        summaryStatus.replaceChildren(aiIcon(allPassed ? "check" : "info"), element("span", { text: testing ? "正在运行样本测试…"
          : allPassed ? "全部测试通过" : failed ? `${failed} 项未通过，请核对预期与实际判断` : "尚有未运行的测试用例" }));
        summaryCounts.textContent = `通过 ${passed} · 失败 ${failed} · 未运行 ${notRun}`;
        filter.setAttribute("aria-pressed", String(failedOnly));
        filter.disabled = busy || testing;
      }
      totals[0].textContent = cases.length ? String(cases.length) : "—";
      totals[1].textContent = caseItems && cases.length ? String(count("passed")) : evidence ? String(Number(evidence.passed_count) || 0) : "—";
      totals[2].textContent = caseItems && cases.length ? `${count("failed")} / ${count("not_run")}`
        : evidence ? `${Number(evidence.failed_count) || 0} / ${Number(evidence.not_run_count) || 0}` : cases.length ? `0 / ${cases.length}` : "—";
      body.replaceChildren();
      const visibleRows = !showSql && failedOnly ? rows.filter(({ item }) => item.status !== "passed") : rows;
      visibleRows.forEach(({ item, index, target, columns: rowColumns, relatedColumns: rowRelated }) => {
        const row = element("tr");
        const driver = target?.preview?.definition?.project_driver || target?.candidate?.project_driver
          || preview?.definition?.project_driver || detail?.definition?.project_driver || detail?.version?.definition?.project_driver;
        const expectedLabel = (count) => count === 0 ? "不提醒" : count === 1 ? "提醒核实" : `提醒核实（${count}条）`;
        let expected = element("span", { text: Number.isInteger(item.expected_count) && item.expected_count >= 0 ? expectedLabel(item.expected_count) : "待确认" });
        if ((preview || caseItems) && onCaseChange && !readOnly) {
          const maximum = projectSections(item.row, rowColumns, rowRelated, driver) ? Math.max(1, item.row.details.length) : 1;
          expected = select(Array.from({ length: maximum + 1 }, (_, count) => [count, expectedLabel(count)]),
            { value: String(item.expected_count), className: "dv-select dv-case-expected" });
          expected.disabled = busy || testing || stale;
          expected.setAttribute("aria-label", `${item.name || "样本"}的预期判断`);
          caseRemovers.push(listen(expected, "change", () => onCaseChange(index, Number(expected.value), target)));
        }
        const name = item.name === "正常" ? "正常（本条不提醒）" : item.name || "未命名案例";
        if (showSql) row.append(element("td", { text: name }), element("td", { text: formatSample(item.row, rowColumns, rowRelated, driver) }));
        else {
          const ruleName = target?.preview?.definition?.name || target?.candidate?.rule_name || "";
          row.append(element("td", {}, element("span", { className: "dv-test-case-name", text: name }),
            ruleName ? element("span", { className: "dv-test-case-rule", text: ruleName }) : null,
            sampleDetails(item.row, rowColumns, rowRelated, driver)));
        }
        row.append(
          element("td", {}, expected), element("td", { text: item.actual_count === null || item.actual_count === undefined ? "—" : item.actual_count ? "提醒核实" : "不提醒" }),
          element("td", {}, statusBadge(labelFor(item.status || "not_run", TEST_CASE_STATUS_LABELS) || "未运行", toneFor(item.status || "not_run", TEST_CASE_STATUS_TONES))));
        body.append(row);
      });
      tableWrap.hidden = !visibleRows.length;
      filterEmpty.hidden = showSql || !failedOnly || !cases.length || visibleRows.length > 0;
      feedback.replaceChildren();
      if (testing) feedback.append(emptyState("正在运行样本测试…", "结果由后端计算返回，不执行真实业务查询"));
      else if (!caseItems) {
        if (preview && !evidence) feedback.append(element("p", { className: "dv-muted", text: "已按字段类型准备测试用例，可先检查预期判断并直接运行，无需保存草稿。" }));
        else if (!detail && !preview) feedback.append(emptyState("请先完成分析", "生成 SQL 后即可直接检查并运行测试用例"));
        else if (!evidence) feedback.append(emptyState("当前版本尚未在本页运行测试", "请核对用例并运行，确认前需要当前版本的通过结果"));
        else if (!cases.length) feedback.append(emptyState("没有测试证据", "不能确认启用"));
      }
      test.hidden = Boolean(caseItems) || !canTest || readOnly;
      test.disabled = busy || stale || readOnly || (preview ? !preview.sql_preview : !detail || dirty);
      test.textContent = testing ? "测试执行中…" : evidence ? "重新运行测试" : "运行测试";
      test.title = preview ? "直接运行当前未保存定义的文档合成样本" : dirty ? "规则已修改，请先保存新版本" : "运行已保存版本的样本测试";
      readinessText.textContent = caseItems ? "" : readiness.ready ? `测试已通过 ${evidence.passed_count} 项，可决定保存草稿或启用。` : readiness.reasons.join("；");
      readinessText.hidden = !showSql;
      readinessText.classList.toggle("is-ready", readiness.ready);
      return readiness;
    },
  };
  return panel;
}
