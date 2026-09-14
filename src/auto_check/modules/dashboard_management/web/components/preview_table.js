import { node } from "./dom.js";

export function renderPreviewTable(preview, sourceMode = "sql", fields = []) {
  const section = node("section", { className: "dm-preview dm-config-section" });
  const heading = node("div", { className: "dm-section-heading" });
  heading.append(node("div", { className: "dm-section-title", text: "03" }), node("h3", { text: "执行与预览" }));
  section.append(heading, node("p", { className: "dm-section-help", text: sourceMode === "system" ? "读取 AutoCheck 系统库并显示结果预览（前 10 行）。" : "测试执行通过后显示结果预览（前 10 行）。" }));
  const rows = Array.isArray(preview?.rows) ? preview.rows.slice(0, 10) : [];
  const columns = preview?.columns?.length ? preview.columns : Object.keys(rows[0] || {});
  const fieldLabels = new Map(fields.map((field) => [String(field.alias || field.field_alias || "").toLowerCase(), field.name || field.alias || field.field_alias]));
  if (!columns.length) {
    section.append(node("p", { className: "dm-empty", text: sourceMode === "system" ? "点击“预览系统数据”后显示结果。" : "执行测试后显示前 10 行结果。" }));
    return section;
  }
  const table = node("table", { className: "dm-preview-table" });
  if (columns.length > 1) table.classList.add("is-multi-column");
  const head = node("thead");
  const row = node("tr");
  columns.forEach((column) => {
    const key = typeof column === "string" ? column : column.alias || column.name;
    row.append(node("th", { text: fieldLabels.get(String(key || "").toLowerCase()) || column.name || key || "字段" }));
  });
  head.append(row);
  const body = node("tbody");
  rows.forEach((entry) => {
    const tableRow = node("tr");
    columns.forEach((column) => {
      const key = typeof column === "string" ? column : column.alias || column.name;
      tableRow.append(node("td", { text: String(entry?.[key] ?? "") }));
    });
    body.append(tableRow);
  });
  table.append(head, body);
  section.append(table);
  if (preview?.has_more) section.append(node("p", { className: "dm-preview-more", text: "仅展示前 10 行，仍有更多结果。" }));
  return section;
}
