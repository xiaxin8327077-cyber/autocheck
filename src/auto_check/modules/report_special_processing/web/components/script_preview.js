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

// Keep these reserved-word snapshots aligned with SQLAlchemy's dialect sets;
// test_qualified_scripts.py checks both lists against the installed source.
const PG_RESERVED_WORDS = new Set([
  'all', 'analyse', 'analyze', 'and', 'any', 'array', 'as', 'asc',
  'asymmetric', 'authorization', 'between', 'binary', 'both', 'case', 'cast', 'check',
  'collate', 'column', 'constraint', 'create', 'cross', 'current_catalog', 'current_date', 'current_role',
  'current_schema', 'current_time', 'current_timestamp', 'current_user', 'default', 'deferrable', 'desc', 'distinct',
  'do', 'else', 'end', 'except', 'false', 'fetch', 'for', 'foreign',
  'freeze', 'from', 'full', 'grant', 'group', 'having', 'ilike', 'in',
  'initially', 'inner', 'intersect', 'into', 'is', 'isnull', 'join', 'leading',
  'left', 'like', 'limit', 'localtime', 'localtimestamp', 'natural', 'new', 'not',
  'notnull', 'null', 'of', 'off', 'offset', 'old', 'on', 'only',
  'or', 'order', 'outer', 'over', 'overlaps', 'placing', 'primary', 'references',
  'returning', 'right', 'select', 'session_user', 'similar', 'some', 'symmetric', 'table',
  'then', 'to', 'trailing', 'true', 'union', 'unique', 'user', 'using',
  'variadic', 'verbose', 'when', 'where', 'window', 'with',
]);

const MYSQL_RESERVED_WORDS = new Set([
  'accessible', 'add', 'admin', 'all', 'alter', 'analyze', 'and', 'array',
  'as', 'asc', 'asensitive', 'before', 'between', 'bigint', 'binary', 'blob',
  'both', 'by', 'call', 'cascade', 'case', 'change', 'char', 'character',
  'check', 'collate', 'column', 'condition', 'constraint', 'continue', 'convert', 'create',
  'cross', 'cube', 'cume_dist', 'current_date', 'current_time', 'current_timestamp', 'current_user', 'cursor',
  'database', 'databases', 'day_hour', 'day_microsecond', 'day_minute', 'day_second', 'dec', 'decimal',
  'declare', 'default', 'delayed', 'delete', 'dense_rank', 'desc', 'describe', 'deterministic',
  'distinct', 'distinctrow', 'div', 'double', 'drop', 'dual', 'each', 'else',
  'elseif', 'empty', 'enclosed', 'escaped', 'except', 'exists', 'exit', 'explain',
  'false', 'fetch', 'first_value', 'float', 'float4', 'float8', 'for', 'force',
  'foreign', 'from', 'fulltext', 'function', 'general', 'generated', 'get', 'get_master_public_key',
  'grant', 'group', 'grouping', 'groups', 'having', 'high_priority', 'hour_microsecond', 'hour_minute',
  'hour_second', 'if', 'ignore', 'ignore_server_ids', 'in', 'index', 'infile', 'inner',
  'inout', 'insensitive', 'insert', 'int', 'int1', 'int2', 'int3', 'int4',
  'int8', 'integer', 'intersect', 'interval', 'into', 'io_after_gtids', 'io_before_gtids', 'is',
  'iterate', 'join', 'json_table', 'key', 'keys', 'kill', 'lag', 'last_value',
  'lateral', 'lead', 'leading', 'leave', 'left', 'like', 'limit', 'linear',
  'lines', 'load', 'localtime', 'localtimestamp', 'lock', 'long', 'longblob', 'longtext',
  'loop', 'low_priority', 'master_bind', 'master_heartbeat_period', 'master_ssl_verify_server_cert', 'match', 'maxvalue', 'mediumblob',
  'mediumint', 'mediumtext', 'member', 'middleint', 'minute_microsecond', 'minute_second', 'mod', 'modifies',
  'natural', 'no_write_to_binlog', 'not', 'nth_value', 'ntile', 'null', 'numeric', 'of',
  'on', 'optimize', 'optimizer_costs', 'option', 'optionally', 'or', 'order', 'out',
  'outer', 'outfile', 'over', 'parallel', 'parse_gcol_expr', 'partition', 'percent_rank', 'persist',
  'persist_only', 'precision', 'primary', 'procedure', 'purge', 'qualify', 'range', 'rank',
  'read', 'read_write', 'reads', 'real', 'recursive', 'references', 'regexp', 'release',
  'rename', 'repeat', 'replace', 'require', 'resignal', 'restrict', 'return', 'revoke',
  'right', 'rlike', 'role', 'row', 'row_number', 'rows', 'schema', 'schemas',
  'second_microsecond', 'select', 'sensitive', 'separator', 'set', 'show', 'signal', 'slow',
  'smallint', 'spatial', 'specific', 'sql', 'sql_after_gtids', 'sql_before_gtids', 'sql_big_result', 'sql_calc_found_rows',
  'sql_small_result', 'sqlexception', 'sqlstate', 'sqlwarning', 'ssl', 'starting', 'stored', 'straight_join',
  'system', 'table', 'terminated', 'then', 'tinyblob', 'tinyint', 'tinytext', 'to',
  'trailing', 'trigger', 'true', 'undo', 'union', 'unique', 'unlock', 'unsigned',
  'update', 'usage', 'use', 'using', 'utc_date', 'utc_time', 'utc_timestamp', 'values',
  'varbinary', 'varchar', 'varcharacter', 'varying', 'virtual', 'when', 'where', 'while',
  'window', 'with', 'write', 'xor', 'year_month', 'zerofill',
]);

function identifier(name, dbType) {
  const text = String(name);
  const dialect = String(dbType || "").trim().toLowerCase();
  const quote = dialect === "mysql" ? "`" : '"';
  const isSimpleAscii = /^[A-Za-z_][A-Za-z0-9_$]*$/.test(text);
  const hasAsciiUppercase = /[A-Z]/.test(text);
  const reserved = dialect === "mysql"
    ? MYSQL_RESERVED_WORDS.has(text.toLowerCase())
    : PG_RESERVED_WORDS.has(text.toLowerCase());
  const needsQuote = !isSimpleAscii || reserved || (dialect !== "mysql" && hasAsciiUppercase);
  return needsQuote ? quote + text.replaceAll(quote, quote + quote) + quote : text;
}

function tableIdentifier(table, datasource, dbType) {
  const name = String(table.table_name);
  let scope = String(table.schema || "");
  let parts;
  if (scope) {
    if (dbType === "mysql" && datasource.database) scope = String(datasource.database);
    parts = [scope, name];
  } else {
    // 仅无 schema 快照的历史名称兼容两段限定；元数据的原始点号表名不拆分。
    const token = '(?:"(?:[^"]|"")+"|`(?:[^`]|``)+`|[A-Za-z_][A-Za-z0-9_$#]*)';
    const match = name.match(new RegExp(`^(${token})\\.(${token})$`));
    if (match) {
      parts = match.slice(1).map((part) => {
        const quote = part[0];
        return quote === '"' || quote === "`" ? part.slice(1, -1).replaceAll(quote + quote, quote) : part;
      });
    } else {
      scope = String((dbType === "mysql" ? datasource.database : datasource.schema) || "");
      parts = scope ? [scope, name] : [name];
    }
  }
  return parts.map((part) => identifier(part, dbType)).join(".");
}

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

function conditionClause(condition, tableTypes, dbType) {
  const column = String(condition?.column_name || "");
  if (!column.trim()) return "";
  const quotedColumn = identifier(column, dbType);
  const rawOperator = String(condition?.operator || "=").trim().toUpperCase();
  const operator = VALID_OPERATORS.has(rawOperator) ? rawOperator : "=";
  if (NO_VALUE_OPERATORS.has(operator)) return `${quotedColumn} ${operator}`;

  const values = Array.isArray(condition?.values)
    ? condition.values.map((value) => String(value ?? "").trim()).filter(Boolean)
    : [];
  const dataType = tableTypes[column] || "";
  if (operator === "IN") {
    const effectiveValues = values.length ? values : [""];
    return `${quotedColumn} IN (${effectiveValues.map((value) => typedLiteral(value, dataType)).join(", ")})`;
  }
  if (operator === "LIKE") {
    const value = values[0] || "";
    const pattern = value && !value.startsWith("%") && !value.endsWith("%") ? `%${value}%` : value;
    return `${quotedColumn} LIKE ${literal(pattern)}`;
  }
  return `${quotedColumn} ${operator} ${typedLiteral(values[0] || "", dataType)}`;
}

function tablePreview(table, fieldTypes, reportPeriod, structuredContent, datasources) {
  const tableName = String(table?.table_name || "");
  if (!tableName.trim()) return "";
  const datasourceId = String(table?.datasource_id || "");
  const datasourceName = String(table?.datasource_name || datasourceId);
  const datasource = datasources[datasourceId] || {};
  const dbType = datasource.db_type || table.datasource_type || structuredContent.datasource_type;
  const chineseName = String(table?.chinese_table_name || "未命名");
  const tableTypes = fieldTypes?.[datasourceId]?.[tableName] || {};
  const lines = [
    `-- 数据源：${datasourceName}`,
    `-- 表：${tableName}（${chineseName}）`,
    `UPDATE ${tableIdentifier(table, datasource, dbType)}`,
  ];

  const assignments = (Array.isArray(table?.fields) ? table.fields : [])
    .filter((field) => String(field?.column_name || "").trim())
    .map((field) => `${identifier(String(field.column_name), dbType)} = ${literal(field.value_after)}`);
  if (assignments.length) lines.push(`SET ${assignments.join(", ")}`);

  const where = [];
  const periodField = String(table?.report_period_field || "");
  if (table?.limit_report_period && periodField) {
    where.push(`${identifier(periodField, dbType)} = ${literal(reportPeriodValue(reportPeriod))}`);
  }
  (Array.isArray(table?.conditions) ? table.conditions : []).forEach((condition) => {
    const clause = conditionClause(condition, tableTypes, dbType);
    if (clause) where.push(clause);
  });
  if (where.length) lines.push(`WHERE ${where.join(" AND ")}`);

  if (assignments.length || where.length) lines[lines.length - 1] += ";";
  return lines.join("\n");
}

export function buildScriptPreview(structuredContent, fieldTypes = {}, reportPeriod = "", datasources = {}) {
  const tables = Array.isArray(structuredContent?.tables) ? structuredContent.tables : [];
  return tables
    .map((table) => tablePreview(table, fieldTypes, reportPeriod, structuredContent, datasources))
    .filter(Boolean)
    .join("\n\n");
}
