// 列来源只采用已保存的 SELECT 输出描述，不按字段名猜业务含义。
const identity = (column) => JSON.stringify([column.name, column.source_field || ""]);

export function queryColumns(issues) {
  const columns = new Map();
  (issues || []).forEach((issue) => (issue.query_result?.columns || []).forEach((column) => {
    if (!column?.name) return;
    const key = identity(column);
    if (!columns.has(key)) columns.set(key, { ...column, key });
  }));
  return [...columns.values()];
}

export function queryValue(issue, column) {
  const result = issue.query_result;
  if (!result) return "未采集";
  if (result.status === "unsupported_projection") return "未支持采集";
  if (!(result.columns || []).some((item) => identity(item) === column.key)) return "未返回此列";
  const unavailable = Object.prototype.hasOwnProperty.call(result.unavailable || {}, column.name)
    ? result.unavailable[column.name] : null;
  if (unavailable) return unavailable === "oversized" ? "值过长，未保存" : "类型不支持，未保存";
  if (!Object.prototype.hasOwnProperty.call(result.values || {}, column.name)) return "未返回此列";
  const value = result.values[column.name];
  if (value === null) return "NULL";
  if (value === "") return "空字符串";
  if (["string", "number", "boolean"].includes(typeof value)) return String(value);
  return "类型不支持，未保存";
}

export function canonicalQueryValue(issue, name, fallback) {
  const column = issue.query_result?.columns?.find((item) => item.name === name);
  return column ? queryValue(issue, { ...column, key: identity(column) }) : fallback ?? "—";
}

export function queryCaptureNotice(issue) {
  if (!issue.query_result) return "历史记录未采集查询明细";
  if (issue.query_result.status === "unsupported_projection") return "此查询尚不支持明细采集";
  if (issue.query_result.status === "partial_projection" || Object.keys(issue.query_result.unavailable || {}).length) return "查询明细未完整保存";
  return "";
}
