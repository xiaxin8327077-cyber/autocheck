import { element } from "./dom.js";

const BASIC_LABELS = {
  report_process_name_snapshot: "关联报送",
  report_period: "所属报送期",
  dimension: "所属维度",
  business_system_name_snapshot: "所属业务系统",
  summary: "处理摘要",
  special_handling_at: "特殊处理时间",
  handler_display_name_snapshot: "处理人",
  governance_owner_display_name_snapshot: "数据治理负责人",
};

const TABLE_INFO_LABELS = {
  datasource_id: "数据源标识",
  datasource_name: "数据源",
  datasource_type: "数据源类型",
  schema: "Schema",
  table_name: "英文表名",
  chinese_table_name: "中文表名",
};

const SCOPE_INFO_LABELS = {
  limit_report_period: "指定数据日期",
  report_period_field: "数据日期字段",
};

const CONDITION_LABELS = {
  column_name: "条件字段",
  operator: "条件类型",
  values: "条件值",
};

const FIELD_LABELS = {
  column_name: "处理字段",
  chinese_column_name: "中文字段名",
  value_before: "修改前内容",
  value_after: "修改后内容",
};

const OPERATOR_LABELS = {
  "=": "等于",
  "<>": "不等于",
  ">": "大于",
  ">=": "大于等于",
  "<": "小于",
  "<=": "小于等于",
  LIKE: "模糊匹配",
  IN: "属于多个值（IN）",
  "IS NULL": "为空",
  "IS NOT NULL": "不为空",
};

function hasOwn(value, key) {
  return value && Object.prototype.hasOwnProperty.call(value, key);
}

function displayValue(value, key = "") {
  if (value === null || value === undefined || value === "") return "未设置";
  if (key === "limit_report_period") return value ? "是" : "否";
  if (key === "operator") return OPERATOR_LABELS[String(value).toUpperCase()] || String(value);
  if (Array.isArray(value)) return value.length ? value.join("、") : "未设置";
  return String(value);
}

function tableSnapshot(table) {
  return table && typeof table === "object" ? table : {};
}

function tableIdentity(table) {
  const snapshot = tableSnapshot(table);
  const datasource = String(snapshot.datasource_name || snapshot.datasource_id || "未设置数据源");
  const tableName = String(snapshot.table_name || "未设置表名");
  const chinese = String(snapshot.chinese_table_name || "");
  return {
    datasource,
    table_name: tableName,
    chinese_table_name: chinese,
    text: `${datasource} / ${tableName}${chinese ? `（${chinese}）` : ""}`,
  };
}

export function buildSemanticAuditViewModel(item) {
  const changedFields = item?.changed_fields && typeof item.changed_fields === "object"
    ? item.changed_fields : {};
  const structured = changedFields.structured_content;
  const basic = Object.entries(changedFields)
    .filter(([key, meta]) => BASIC_LABELS[key] && meta && typeof meta === "object"
      && hasOwn(meta, "old") && hasOwn(meta, "new"))
    .map(([key, meta]) => ({
      key,
      label: BASIC_LABELS[key],
      old: displayValue(meta.old, key),
      new: displayValue(meta.new, key),
    }));
  const tables = Array.isArray(structured?.tables) ? structured.tables : [];
  const specialCount = Number(structured?.change_count || 0);
  const businessCount = basic.length + specialCount;
  const affectedTables = Number(structured?.affected_tables || tables.length || 0);
  const modifiedTables = Number(structured?.modified_tables || 0);
  const addedTables = Number(structured?.added_tables || 0);
  const removedTables = Number(structured?.removed_tables || 0);
  const compact = affectedTables <= 2 && businessCount <= 8;
  let openedModified = false;
  const tableModels = tables.map((table) => {
    const change = String(table?.change || "modified");
    let defaultExpanded = false;
    if (change !== "removed" && compact) defaultExpanded = true;
    else if (change === "modified" && !openedModified) defaultExpanded = true;
    if (change === "modified" && defaultExpanded) openedModified = true;
    const snapshot = change === "removed" ? table?.before : table?.after;
    return {
      ...table,
      change,
      identity: tableIdentity(snapshot),
      default_expanded: defaultExpanded,
    };
  });
  const scriptMeta = changedFields.processing_script;
  const scriptChanged = Boolean(scriptMeta && typeof scriptMeta === "object");
  const scriptMode = String(scriptMeta?.mode || "AUTO").trim().toUpperCase() === "MANUAL"
    ? "MANUAL" : "AUTO";
  const summaryParts = [];
  if (basic.length) summaryParts.push(`基本信息${basic.length}项`);
  if (specialCount) summaryParts.push(`特殊处理内容${specialCount}项`);
  if (affectedTables > 1 || addedTables || removedTables) {
    if (modifiedTables) summaryParts.push(`修改${modifiedTables}张表`);
    if (addedTables) summaryParts.push(`新增${addedTables}张表`);
    if (removedTables) summaryParts.push(`删除${removedTables}张表`);
  }
  if (affectedTables) summaryParts.push(`涉及${affectedTables}张处理表`);
  if (scriptChanged) summaryParts.push(scriptMode === "MANUAL" ? "手动脚本已修改" : "脚本同步更新");
  return {
    basic,
    tables: tableModels,
    script: scriptChanged ? {
      old: String(scriptMeta.old ?? scriptMeta.old_preview ?? ""),
      new: String(scriptMeta.new ?? scriptMeta.new_preview ?? ""),
      mode: scriptMode,
    } : null,
    script_changed: scriptChanged,
    basic_change_count: basic.length,
    special_change_count: specialCount,
    business_change_count: businessCount,
    affected_tables: affectedTables,
    modified_tables: modifiedTables,
    added_tables: addedTables,
    removed_tables: removedTables,
    summary_parts: summaryParts,
  };
}

function diffTable(documentRef, rows) {
  return element(documentRef, "div", { className: "rsp-audit-semantic-diff" }, [
    ...["变更项", "修改前", "修改后"].map((text) => element(documentRef, "div", {
      className: "rsp-audit-semantic-diff-head", text,
    })),
    ...rows.flatMap((row) => [
      element(documentRef, "div", { className: "rsp-audit-semantic-field", text: row.label }),
      element(documentRef, "div", { className: "rsp-audit-semantic-before", text: displayValue(row.old, row.key) }),
      element(documentRef, "div", { className: "rsp-audit-semantic-after", text: displayValue(row.new, row.key) }),
    ]),
  ]);
}

function section(documentRef, title, content, count = 0) {
  if (!content) return null;
  return element(documentRef, "section", { className: "rsp-audit-semantic-section" }, [
    element(documentRef, "h5", { text: `${title}${count ? ` · ${count}项` : ""}` }),
    content,
  ]);
}

function objectName(snapshot, kind) {
  const value = tableSnapshot(snapshot);
  if (kind === "condition") {
    const english = String(value.column_name || "未设置条件字段");
    const chinese = String(value.chinese_column_name || "");
    return chinese ? `${chinese}（${english}）` : english;
  }
  const english = String(value.column_name || "未设置字段");
  const chinese = String(value.chinese_column_name || "");
  return chinese ? `${chinese}（${english}）` : english;
}

function conditionText(snapshot) {
  const value = tableSnapshot(snapshot);
  return `${objectName(value, "condition")} · ${displayValue(value.operator, "operator")} · ${displayValue(value.values, "values")}`;
}

function fieldText(snapshot) {
  const value = tableSnapshot(snapshot);
  return `${objectName(value, "field")}：${displayValue(value.value_before)} → ${displayValue(value.value_after)}`;
}

function semanticEvents(documentRef, events, kind) {
  if (!Array.isArray(events) || !events.length) return null;
  const labels = kind === "condition" ? CONDITION_LABELS : FIELD_LABELS;
  const addedTitle = kind === "condition" ? "新增条件" : "新增修改字段";
  const removedTitle = kind === "condition" ? "删除条件" : "删除修改字段";
  return element(documentRef, "div", { className: "rsp-audit-event-list" }, events.map((event) => {
    if (event.change === "added") {
      return element(documentRef, "div", { className: "rsp-audit-event rsp-audit-event-added" }, [
        element(documentRef, "strong", { text: `+ ${addedTitle}` }),
        element(documentRef, "span", { text: kind === "condition" ? conditionText(event.after) : fieldText(event.after) }),
      ]);
    }
    if (event.change === "removed") {
      return element(documentRef, "div", { className: "rsp-audit-event rsp-audit-event-removed" }, [
        element(documentRef, "strong", { text: `- ${removedTitle}` }),
        element(documentRef, "span", { text: kind === "condition" ? conditionText(event.before) : fieldText(event.before) }),
      ]);
    }
    const snapshot = event.after || event.before;
    const rows = (event.changes || []).map((change) => ({
      ...change,
      label: labels[change.key] || change.key,
    }));
    return element(documentRef, "div", { className: "rsp-audit-event rsp-audit-event-modified" }, [
      element(documentRef, "strong", {
        text: `${kind === "condition" ? "条件" : "字段"}：${objectName(snapshot, kind)}`,
      }),
      diffTable(documentRef, rows),
    ]);
  }));
}

function snapshotInfo(documentRef, rows) {
  return element(documentRef, "div", { className: "rsp-audit-snapshot-info" }, rows.map((row) =>
    element(documentRef, "div", { className: "rsp-audit-snapshot-info-row" }, [
      element(documentRef, "span", { className: "rsp-audit-snapshot-label", text: row.label }),
      element(documentRef, "span", { className: "rsp-audit-snapshot-value", text: displayValue(row.value, row.key) }),
    ])));
}

function snapshotList(documentRef, items, formatter) {
  if (!items.length) return null;
  return element(documentRef, "div", { className: "rsp-audit-snapshot-list" }, items.map((item) =>
    element(documentRef, "div", { className: "rsp-audit-snapshot-item", text: formatter(item) })));
}

function fullSnapshot(documentRef, snapshot, change) {
  const value = tableSnapshot(snapshot);
  const conditions = Array.isArray(value.conditions) ? value.conditions : [];
  const fields = Array.isArray(value.fields) ? value.fields : [];
  const prefix = change === "removed" ? "删除前包含" : "新增配置";
  const tableInfo = [
    { key: "datasource_name", label: "数据源", value: value.datasource_name || value.datasource_id },
    { key: "table_name", label: "英文表名", value: value.table_name },
    { key: "chinese_table_name", label: "中文表名", value: value.chinese_table_name },
  ];
  if (value.schema) tableInfo.push({ key: "schema", label: "Schema", value: value.schema });
  if (value.datasource_type) {
    tableInfo.push({ key: "datasource_type", label: "数据源类型", value: value.datasource_type });
  }
  const scopeInfo = [
    { key: "limit_report_period", label: "指定数据日期", value: Boolean(value.limit_report_period) },
  ];
  if (value.limit_report_period) {
    scopeInfo.push({ key: "report_period_field", label: "数据日期字段", value: value.report_period_field });
  }
  return element(documentRef, "div", { className: "rsp-audit-snapshot" }, [
    element(documentRef, "div", { className: "rsp-audit-snapshot-summary", text:
      `${prefix}：${value.limit_report_period ? "指定数据日期" : "不指定数据日期"} · ${conditions.length}条处理范围 · ${fields.length}个修改字段`,
    }),
    section(documentRef, "表信息", snapshotInfo(documentRef, tableInfo)),
    section(documentRef, "处理范围", element(documentRef, "div", { className: "rsp-audit-snapshot-section-body" }, [
      snapshotInfo(documentRef, scopeInfo),
      snapshotList(documentRef, conditions, conditionText),
    ]), conditions.length),
    section(documentRef, "修改字段", snapshotList(documentRef, fields, fieldText), fields.length),
  ].filter(Boolean));
}

function renderTable(documentRef, table, index) {
  const changeLabels = { modified: "修改", added: "新增", removed: "删除" };
  const body = [];
  if (table.change === "modified") {
    const tableInfo = (table.table_info || []).map((item) => ({
      ...item, label: TABLE_INFO_LABELS[item.key] || item.key,
    }));
    const scopeInfo = (table.scope_info || []).map((item) => ({
      ...item, label: SCOPE_INFO_LABELS[item.key] || item.key,
    }));
    body.push(section(documentRef, "表信息变更", tableInfo.length ? diffTable(documentRef, tableInfo) : null, tableInfo.length));
    const scopeChildren = [
      scopeInfo.length ? diffTable(documentRef, scopeInfo) : null,
      semanticEvents(documentRef, table.conditions, "condition"),
    ].filter(Boolean);
    body.push(section(documentRef, "处理范围变更", scopeChildren.length
      ? element(documentRef, "div", {}, scopeChildren) : null));
    body.push(section(documentRef, "修改字段变更", semanticEvents(documentRef, table.fields, "field")));
  } else {
    body.push(fullSnapshot(documentRef, table.change === "removed" ? table.before : table.after, table.change));
  }
  const disclosureText = table.change === "removed" ? "查看删除前配置" : `${table.change_count || 0}项变更`;
  return element(documentRef, "details", {
    className: `rsp-audit-table-card rsp-audit-table-card-${table.change}`,
    open: table.default_expanded ? "" : null,
  }, [
    element(documentRef, "summary", {}, [
      element(documentRef, "span", { className: `rsp-audit-table-badge rsp-audit-table-badge-${table.change}`, text: changeLabels[table.change] || "修改" }),
      element(documentRef, "span", { className: "rsp-audit-table-name", text: `处理表${index + 1} · ${table.identity.text}` }),
      element(documentRef, "span", { className: "rsp-audit-table-count", text: disclosureText }),
    ]),
    element(documentRef, "div", { className: "rsp-audit-table-body" }, body.filter(Boolean)),
  ]);
}

function scriptDisclosure(documentRef, script, onCopyScript) {
  if (!script) return null;
  const scriptColumn = (label, text) => element(documentRef, "div", { className: "rsp-audit-script-column" }, [
    element(documentRef, "div", { className: "rsp-audit-script-column-head" }, [
      element(documentRef, "strong", { text: label }),
      onCopyScript ? element(documentRef, "button", {
        type: "button", className: "rsp-button rsp-button-secondary", text: "复制",
        onClick: (event) => { event.preventDefault(); onCopyScript(text, false); },
      }) : null,
    ]),
    element(documentRef, "pre", { text: text || "（空）" }),
  ]);
  const sourceLabel = script.mode === "MANUAL" ? "手动编辑" : "自动生成";
  return element(documentRef, "details", { className: "rsp-audit-script-disclosure" }, [
    element(documentRef, "summary", { text: `脚本变更 · ${sourceLabel} · 查看 Diff` }),
    element(documentRef, "div", { className: "rsp-audit-script-columns" }, [
      scriptColumn("修改前脚本", script.old),
      scriptColumn("修改后脚本", script.new),
    ]),
  ]);
}

export function renderSemanticAuditDetail(documentRef, model, options = {}) {
  const children = [];
  if (model.basic.length) {
    children.push(section(documentRef, "基本信息", diffTable(documentRef, model.basic), model.basic_change_count));
  }
  if (model.tables.length) {
    children.push(element(documentRef, "section", { className: "rsp-audit-semantic-section rsp-audit-special-section" }, [
      element(documentRef, "h5", { text: `特殊处理内容 · ${model.special_change_count}项 · 涉及${model.affected_tables}张表` }),
      element(documentRef, "div", { className: "rsp-audit-table-list" }, model.tables.map((table, index) => renderTable(documentRef, table, index))),
    ]));
  }
  children.push(scriptDisclosure(documentRef, model.script, options.onCopyScript));
  return element(documentRef, "div", { className: "rsp-audit-semantic" }, children.filter(Boolean));
}
