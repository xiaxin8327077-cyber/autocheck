import { comparisons, operandFields } from "../comparisons.js";
import { element } from "./dom.js";

function businessLabel(label, identifier) {
  const text = String(label || "").trim()
    .replace(/\s*[（(][^()（）]*\.ktr[)）]\s*$/i, "")
    .replace(/\.ktr$/i, "").trim();
  if (!text || text === "—") return identifier || "";
  const suffix = text.match(/\s*[（(]([^()（）]+)[)）]$/);
  return suffix && suffix[1] === identifier ? text.slice(0, suffix.index).trim() || identifier : text;
}

export function tableLabel(candidate, option = {}, related = false) {
  if (related) return businessLabel(candidate.related_table_name_cn, candidate.join?.table_name);
  // Older split options sometimes assigned the complete scope document to table_label.
  const optionLabel = String(option.table_label || "").trim();
  const copiedScope = optionLabel === candidate.scope_description && (option.fromSelection || optionLabel.length > 120 || /[\r\n]/.test(optionLabel));
  const label = candidate.table_name_cn || (copiedScope ? "" : optionLabel);
  return businessLabel(label, candidate.table_name || option.table_id);
}

export function columnLabel(candidate, name, role = "base") {
  const columns = role === "related" ? candidate.related_columns : candidate.columns;
  const column = columns?.find((item) => item.column_name === name);
  return businessLabel(column?.comment || column?.field_cn, name);
}

function metricRefs(candidate) {
  const refs = new Map();
  for (const part of comparisons(candidate.expression)) {
    for (const side of ["left", "right"]) {
      const role = side === "right" && part.right_table === "related" ? "related" : "base";
      for (const name of operandFields(part, side)) refs.set(role + "." + name, [role, name]);
    }
  }
  return [...refs.values()];
}

export function objectLabel(candidate, option) {
  const table = tableLabel(candidate, option);
  const metrics = metricRefs(candidate).filter(([role]) => role === "base").map(([, name]) => columnLabel(candidate, name));
  return [table, metrics.join("、") || option?.field_label].filter(Boolean).join(" · ");
}

export function filterValues(candidate, filter) {
  const values = Array.isArray(filter.value) ? filter.value : [filter.value];
  const dictionary = candidate.semantic_intent?.dictionary_snapshots?.[filter.table || "base"]?.[filter.field] || [];
  return values.map((value) => ({
    value, label: dictionary.find((item) => String(item.value) === String(value))?.label || "",
  }));
}

export function documentEvidence(candidate, option = {}) {
  const details = element("details", { className: "dv-ai-option-evidence" }, element("summary", { text: "原始证据" }));
  const rows = new Set();
  function row(label, value) {
    if (value) rows.add(label + "：" + value);
  }
  const qualified = (label, name) => label && name && label !== name ? `${label}（${name}）` : label || name;
  row("数据表", qualified(tableLabel(candidate, option), candidate.table_name || option.table_id));
  if (candidate.join?.table_name) row("关联表", qualified(tableLabel(candidate, option, true), candidate.join.table_name));
  for (const [role, name] of metricRefs(candidate)) {
    const column = (role === "related" ? candidate.related_columns : candidate.columns)?.find((item) => item.column_name === name);
    row(role === "related" ? "关联字段" : "检查字段", qualified(columnLabel(candidate, name, role), name));
    row("取数逻辑", column?.logic);
  }
  for (const filter of candidate.filters || []) {
    const name = qualified(columnLabel(candidate, filter.field, filter.table), filter.field);
    const values = filterValues(candidate, filter).filter((v) => v.value != null)
      .map(({ value, label }) => label ? `${value}＝${label}` : value);
    row("筛选字段", [name, values.join("、")].filter(Boolean).join(" · "));
  }
  row("日期字段", candidate.report_date_field);
  const scope = candidate.document_scope ?? candidate.scope_description;
  if (scope !== candidate.table_name && scope !== tableLabel(candidate, option)) row("取数说明", scope);
  row("取数逻辑", candidate.logic);
  row("字典", candidate.dictionary);
  for (const note of candidate.null_evidence || []) row("空值依据", note?.source?.trim());
  for (const line of rows) details.append(element("div", { className: "dv-ai-option-evidence-row", text: line }));
  if (!rows.size) details.hidden = true;
  return details;
}
