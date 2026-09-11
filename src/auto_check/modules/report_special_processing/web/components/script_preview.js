/* 报表特殊处理脚本的前端渐进式预览。
 *
 * 这里只拼接用户当前已选择的表和字段，不参与记录保存与正式校验：
 * - 选表即输出 UPDATE；
 * - 选修改字段即输出 SET，空修改后按空字符串展示；
 * - 选条件字段即输出 WHERE，空条件值按空字符串展示；
 * - 未选条件字段时允许不输出 WHERE。
 */

const NUMERIC_TYPES = ["int", "decimal", "numeric", "float", "double", "real", "number", "money"];
const NO_VALUE_OPERATORS = new Set(["IS NULL", "IS NOT NULL"]);
const VALID_OPERATORS = new Set(["=", "<>", ">", ">=", "<", "<=", "LIKE", "IN", "IS NULL", "IS NOT NULL"]);

function literal(value) {
  return `'${String(value ?? "").replaceAll("'", "''")}'`;
}

function typedLiteral(value, dataType) {
  const text = String(value ?? "").trim();
  const kind = String(dataType || "").trim().toLowerCase();
  if (text && NUMERIC_TYPES.some((token) => kind.includes(token)) && Number.isFinite(Number(text))) {
    return text;
  }
  return literal(text);
}

function reportPeriodValue(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4})-?(\d{2})-?(\d{2})/);
  return match ? `${match[1]}-${match[2]}-${match[3]}` : text.slice(0, 10);
}

function conditionClause(condition, tableTypes) {
  const column = String(condition?.column_name || "").trim();
  if (!column) return "";
  const rawOperator = String(condition?.operator || "=").trim().toUpperCase();
  const operator = VALID_OPERATORS.has(rawOperator) ? rawOperator : "=";
  if (NO_VALUE_OPERATORS.has(operator)) return `${column} ${operator}`;

  const values = Array.isArray(condition?.values)
    ? condition.values.map((value) => String(value ?? "").trim()).filter(Boolean)
    : [];
  const dataType = tableTypes[column] || "";
  if (operator === "IN") {
    const effectiveValues = values.length ? values : [""];
    return `${column} IN (${effectiveValues.map((value) => typedLiteral(value, dataType)).join(", ")})`;
  }
  if (operator === "LIKE") {
    const value = values[0] || "";
    const pattern = value && !value.startsWith("%") && !value.endsWith("%") ? `%${value}%` : value;
    return `${column} LIKE ${literal(pattern)}`;
  }
  return `${column} ${operator} ${typedLiteral(values[0] || "", dataType)}`;
}

function tablePreview(table, fieldTypes, reportPeriod) {
  const tableName = String(table?.table_name || "").trim();
  if (!tableName) return "";
  const datasourceId = String(table?.datasource_id || "");
  const datasourceName = String(table?.datasource_name || datasourceId);
  const chineseName = String(table?.chinese_table_name || "未命名");
  const tableTypes = fieldTypes?.[datasourceId]?.[tableName] || {};
  const lines = [
    `-- 数据源：${datasourceName}`,
    `-- 表：${tableName}（${chineseName}）`,
    `UPDATE ${tableName}`,
  ];

  const assignments = (Array.isArray(table?.fields) ? table.fields : [])
    .filter((field) => String(field?.column_name || "").trim())
    .map((field) => `${String(field.column_name).trim()} = ${literal(field.value_after)}`);
  if (assignments.length) lines.push(`SET ${assignments.join(", ")}`);

  const where = [];
  const periodField = String(table?.report_period_field || "").trim();
  if (table?.limit_report_period && periodField) {
    where.push(`${periodField} = ${literal(reportPeriodValue(reportPeriod))}`);
  }
  (Array.isArray(table?.conditions) ? table.conditions : []).forEach((condition) => {
    const clause = conditionClause(condition, tableTypes);
    if (clause) where.push(clause);
  });
  if (where.length) lines.push(`WHERE ${where.join(" AND ")}`);

  if (assignments.length || where.length) lines[lines.length - 1] += ";";
  return lines.join("\n");
}

export function buildScriptPreview(structuredContent, fieldTypes = {}, reportPeriod = "") {
  const tables = Array.isArray(structuredContent?.tables) ? structuredContent.tables : [];
  return tables
    .map((table) => tablePreview(table, fieldTypes, reportPeriod))
    .filter(Boolean)
    .join("\n\n");
}
