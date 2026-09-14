import { button, labeledControl, node } from "./dom.js";

function statusText(status, sourceMode) {
  if (sourceMode === "system") {
    if (status === "passed") return "系统数据预览已更新";
    if (status === "running") return "正在读取系统数据…";
    if (status === "failed") return "系统数据读取失败，请稍后重试";
    return "点击按钮读取当前系统数据";
  }
  if (status === "passed") return "测试通过，可保存配置";
  if (status === "running") return "测试执行中…";
  if (status === "failed") return "测试未通过，请修正后重试";
  return "SQL 或数据源修改后需要重新测试";
}

export function renderSourceEditor({ region, draft, datasources, canManage, canTest, pending, onMode, onDatasource, onSql, onTest }) {
  const section = node("section", { className: "dm-source-editor dm-config-section" });
  const heading = node("div", { className: "dm-section-heading" });
  heading.append(node("div", { className: "dm-section-title", text: "02" }), node("h3", { text: "数据来源" }));
  section.append(heading);
  const choices = node("div", { className: "dm-source-choices" });
  if (region.system_supported) {
    const system = button("系统数据", "dm-source-choice", () => onMode("system"), { disabled: !canManage || pending });
    if (draft.source_mode === "system") system.classList.add("is-active");
    system.append(node("small", { text: "使用系统内置口径" }));
    choices.append(system);
  }
  const sql = button("自定义 SQL", "dm-source-choice", () => onMode("sql"), { disabled: !canManage || pending });
  if (draft.source_mode === "sql") sql.classList.add("is-active");
  sql.append(node("small", { text: "通过编写 SQL 从指定数据源获取数据" }));
  choices.append(sql);
  section.append(choices);
  if (draft.source_mode === "system") {
    const source = region.system_source || {};
    const sourceInfo = node("div", { className: "dm-system-source" });
    const details = [
      ["来源功能", source.feature || "AutoCheck 系统数据"],
      ["系统数据库", source.database || "AutoCheck 系统库"],
    ];
    details.forEach(([label, value]) => {
      const item = node("div", { className: "dm-system-source-item" });
      item.append(node("span", { text: label }), node("strong", { text: value }));
      sourceInfo.append(item);
    });
    sourceInfo.append(node("p", { text: source.description || "使用系统内置只读查询获取数据。" }));
    section.append(sourceInfo);
    const generatedSql = node("textarea", { className: "dm-sql-text dm-system-sql", attrs: { readonly: "readonly", spellcheck: "false", "aria-label": "系统生成 SQL" } });
    generatedSql.value = source.sql || "";
    const generatedSqlControl = labeledControl("系统生成 SQL", generatedSql);
    generatedSqlControl.classList.add("dm-sql-control");
    section.append(generatedSqlControl);
    const actions = node("div", { className: "dm-source-actions" });
    const previewButton = button("预览系统数据", "dm-button dm-button-secondary", onTest, { disabled: !canTest || pending || draft.testStatus === "running" });
    actions.append(previewButton, node("p", { className: `dm-test-status is-${draft.testStatus}`, text: statusText(draft.testStatus, "system") }));
    section.append(actions);
    return section;
  }
  const datasource = node("select", { className: "dm-datasource" });
  datasource.disabled = !canManage || pending;
  datasource.append(node("option", { text: "请选择数据源", attrs: { value: "" } }));
  datasources.forEach((source) => datasource.append(node("option", { text: `${source.name}（${source.db_type}）`, attrs: { value: source.id } })));
  datasource.value = draft.datasource_id;
  const datasourceControl = labeledControl("数据源", datasource);
  datasourceControl.classList.add("dm-datasource-control");
  section.append(datasourceControl);
  const sqlText = node("textarea", { className: "dm-sql-text", attrs: { spellcheck: "false", "aria-label": "查询 SQL" } });
  sqlText.value = draft.sql_text;
  sqlText.disabled = !canManage || pending;
  const sqlControl = labeledControl("查询 SQL", sqlText);
  sqlControl.classList.add("dm-sql-control");
  section.append(sqlControl);
  const actions = node("div", { className: "dm-source-actions" });
  const testButton = button("测试执行", "dm-button dm-button-secondary", onTest, { disabled: !canTest || pending || draft.testStatus === "running" });
  const testStatus = node("p", { className: `dm-test-status is-${draft.testStatus}`, text: statusText(draft.testStatus, "sql") });
  const syncTestState = (nextDraft) => {
    testButton.disabled = !canTest || pending || nextDraft.testStatus === "running";
    testStatus.className = `dm-test-status is-${nextDraft.testStatus}`;
    testStatus.textContent = statusText(nextDraft.testStatus, "sql");
  };
  datasource.addEventListener("change", () => syncTestState(onDatasource(datasource.value) || draft));
  sqlText.addEventListener("input", () => {
    const nextDraft = onSql(sqlText.value);
    syncTestState(nextDraft || draft);
  });
  actions.append(testButton, testStatus);
  section.append(actions);
  return section;
}
