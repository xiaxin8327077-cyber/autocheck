import { errorMessage } from "../runtime.js";
import { hasCapability } from "../state.js";
import { button, element, input, select, textarea } from "../components/dom.js";
import { createPageHeader } from "../components/page_header.js";
import { createKnowledgeSettings } from "../components/knowledge_settings.js";

const CHANNELS = ["settings-documents", "settings-prompts", "settings-rules", "settings-import"];

export function createSettingsPage({ state, runtime, api, listen, user, notify, host }) {
  const canAdmin = hasCapability(user, "dv.admin");
  const header = createPageHeader({
    section: "校验设置",
    title: "校验设置",
    description: "管理文档快照、信托业务知识、生成提示词与数据源映射",
    actions: [],
  });

  // ① 文档快照
  const fileInput = input({ type: "file", className: "dv-file-input" });
  fileInput.accept = ".xlsx";
  fileInput.hidden = true;
  const importButton = button("导入文档", { listen, className: "dv-button dv-button-primary", onClick: () => fileInput.click() });
  const docFeedback = element("p", { className: "dv-inline-status" });
  const docSummary = element("div", { className: "dv-settings-summary" });
  const docTable = element("tbody");
  const docList = element("table", { className: "dv-table" },
    element("thead", {}, element("tr", {}, ...["版本", "文件名", "表数", "字段数", "导入时间", "状态", "操作"]
      .map((label) => element("th", { text: label })))),
    docTable);
  const documentsSection = element("section", { className: "dv-page-section" },
    element("div", { className: "dv-page-section-heading" }, element("h2", { text: "文档快照" })),
    element("p", { className: "dv-muted", text: "字段类型为空时按字符串（varchar）处理，不再列为解析告警。" }),
    element("div", { className: "dv-filter-actions" }, fileInput, importButton),
    docSummary, docFeedback,
    element("div", { className: "dv-table-wrap dv-scroll" }, docList));

  // ② 提示词
  const promptInputs = new Map();
  const promptSections = [];
  const promptsSection = element("section", { className: "dv-page-section" },
    element("div", { className: "dv-page-section-heading" }, element("h2", { text: "生成提示词" })));

  // ③ 数据源映射规则
  const ruleBody = element("tbody");
  const ruleTable = element("table", { className: "dv-table" },
    element("thead", {}, element("tr", {}, ...["sheet 前缀", "归属数据源", "操作"].map((label) => element("th", { text: label })))),
    ruleBody);
  const addRule = button("添加规则", { listen, className: "dv-button dv-button-plain", onClick: () => addRuleRow("", "") });
  const saveRules = button("保存映射", { listen, className: "dv-button dv-button-primary", onClick: saveSourceRules });
  const rulesSection = element("section", { className: "dv-page-section" },
    element("div", { className: "dv-page-section-heading" }, element("h2", { text: "数据源映射规则" })),
    element("p", { className: "dv-muted", text: "数据源按 Sheet 前缀匹配。报表分类使用「校验页分类名称_表名」，例如「1104报送_贷款明细」；「人行_」对应人行大集中报送、资管产品模板、逐笔。" }),
    element("div", { className: "dv-table-wrap dv-scroll" }, ruleTable),
    element("div", { className: "dv-filter-actions" }, addRule, saveRules));

  const knowledge = createKnowledgeSettings({ runtime, api, listen, canAdmin });
  const panel = element("section", {
    className: "dv-tab-panel dv-settings-panel", dataset: { panel: "settings" }, attrs: { role: "tabpanel" },
  }, documentsSection, knowledge.section, promptsSection, rulesSection);

  if (!canAdmin) {
    notify("当前用户没有校验设置权限", "error");
    documentsSection.append(element("p", { className: "dv-feedback is-error", text: "当前用户没有校验设置权限（需要 dv.admin）" }));
  }

  listen(fileInput, "change", importDocument);
  listen(importButton, "click", () => {
    if (canAdmin) fileInput.click();
  });

  function setFeedback(message, tone = "") {
    docFeedback.textContent = message || "";
    docFeedback.classList.remove("is-error", "is-success", "is-warning");
    if (tone) docFeedback.classList.add(`is-${tone}`);
  }

  async function importDocument() {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (!canAdmin) return;
    const token = runtime.next("settings-import");
    setFeedback("正在解析文档并生成快照…", "");
    importButton.disabled = true;
    try {
      const buffer = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (let index = 0; index < buffer.length; index += 1) binary += String.fromCharCode(buffer[index]);
      const result = await runtime.request(token, (signal) => api.importDocument({
        file_name: file.name,
        name: file.name,
        content_base64: btoa(binary),
      }, { signal }));
      if (!runtime.current(token)) return;
      setFeedback(
        `已导入版本 v${result?.document?.version_no ?? "?"}：${result?.table_count ?? 0} 张表、${result?.field_count ?? 0} 个字段`
        + (Array.isArray(result?.warnings) && result.warnings.length ? `；${result.warnings.length} 条告警` : ""),
        "success",
      );
      fileInput.value = "";
      await loadDocuments();
    } catch (error) {
      if (runtime.current(token)) setFeedback(`导入失败：${errorMessage(error)}`, "error");
      throw error;
    } finally {
      if (runtime.current(token)) importButton.disabled = false;
    }
  }

  function renderDocuments(documents) {
    docTable.replaceChildren();
    docSummary.replaceChildren();
    const active = documents.find((item) => item.status === "active");
    if (!active) {
      docSummary.append(element("p", { className: "dv-muted", text: "尚未导入文档；AI 分析将无法生成规则。" }));
    } else {
      docSummary.append(
        element("p", { className: "dv-inline-status is-success", text:
          `当前启用版本 v${active.version_no}：${active.table_count} 张表 / ${active.field_count} 个字段，导入于 ${active.imported_at}` }),
      );
      if (Array.isArray(active.warnings) && active.warnings.length) {
        const list = element("ul", { className: "dv-uncertainty-list" });
        active.warnings.slice(0, 20).forEach((item) => list.append(element("li", { text: String(item) })));
        docSummary.append(element("div", { className: "dv-notice is-warning" }, element("strong", { text: "解析告警" }), list));
      }
    }
    documents.forEach((item) => {
      const toggle = button(item.status === "active" ? "已启用" : "启用", {
        listen, className: "dv-table-action", disabled: item.status === "active" || !canAdmin,
        onClick: () => activateDocument(item.id),
      });
      docTable.append(element("tr", {},
        element("td", { text: `v${item.version_no}` }),
        element("td", { text: item.file_name || item.name }),
        element("td", { text: String(item.table_count) }),
        element("td", { text: String(item.field_count) }),
        element("td", { className: "dv-date", text: item.imported_at || "" }),
        element("td", {}, element("span", { className: `dv-status is-${item.status === "active" ? "success" : "neutral"}`, text: item.status === "active" ? "启用中" : "历史" })),
        element("td", {}, toggle)));
    });
  }

  async function loadDocuments() {
    const token = runtime.next("settings-documents");
    try {
      const documents = await runtime.request(token, (signal) => api.documents({ signal }));
      if (!runtime.current(token)) return;
      renderDocuments(Array.isArray(documents) ? documents : []);
    } catch (error) {
      if (runtime.current(token)) setFeedback(`文档列表加载失败：${errorMessage(error)}`, "error");
    }
  }

  async function activateDocument(documentId) {
    const token = runtime.next("settings-documents");
    try {
      await runtime.request(token, (signal) => api.activateDocument(documentId, { signal }));
      if (!runtime.current(token)) return;
      notify("文档版本已切换", "success");
      await loadDocuments();
    } catch (error) {
      if (runtime.current(token)) notify(errorMessage(error, "启用文档失败"), "error");
    }
  }

  function renderPrompts(prompts) {
    promptsSection.replaceChildren(
      element("div", { className: "dv-page-section-heading" }, element("h2", { text: "生成提示词" })),
    );
    promptInputs.clear();
    (prompts || []).forEach((item) => {
      const area = textarea({ value: item.content, rows: 7, className: "dv-textarea dv-prompt-input" });
      promptInputs.set(item.stage, area);
      const save = button("保存提示词", { listen, className: "dv-button", onClick: () => savePrompt(item.stage) });
      const reset = button("恢复默认", { listen, className: "dv-button dv-button-plain", onClick: () => resetPrompt(item.stage) });
      promptsSection.append(element("div", { className: "dv-prompt-block" },
        element("div", { className: "dv-prompt-heading" },
          element("strong", { text: item.label }),
          element("span", { className: "dv-muted", text: item.is_default ? "使用内置默认" : `自定义 v${item.version_no}` })),
        area,
        element("p", { className: "dv-muted", text: item.stage === "generate_sql"
          ? "独立 SQL 模板：当前 AI 新增字段比较规则不调用此阶段，SQL 由后端编译。"
          : "保留已保存的模板正文；运行时自动追加当前输出约束。恢复默认会保存为新版本。" }),
        ...(item.output_contract ? [element("details", {},
          element("summary", { text: "查看运行时自动追加的输出约束" }),
          element("p", { className: "dv-muted", text: item.output_contract }))] : []),
        element("div", { className: "dv-filter-actions" }, save, reset)));
    });
  }

  async function loadPrompts() {
    const token = runtime.next("settings-prompts");
    try {
      const prompts = await runtime.request(token, (signal) => api.prompts({ signal }));
      if (!runtime.current(token)) return;
      renderPrompts(Array.isArray(prompts) ? prompts : []);
    } catch (error) {
      if (runtime.current(token)) notify(errorMessage(error, "提示词加载失败"), "error");
    }
  }

  async function savePrompt(stage) {
    const content = promptInputs.get(stage)?.value || "";
    const token = runtime.next("settings-prompts");
    try {
      await runtime.request(token, (signal) => api.savePrompt({ stage, content }, { signal }));
      if (!runtime.current(token)) return;
      notify("提示词已保存为新版本", "success");
      await loadPrompts();
    } catch (error) {
      if (runtime.current(token)) notify(errorMessage(error, "提示词保存失败"), "error");
    }
  }

  async function resetPrompt(stage) {
    const token = runtime.next("settings-prompts");
    try {
      await runtime.request(token, (signal) => api.resetPrompt(stage, { signal }));
      if (!runtime.current(token)) return;
      notify("已恢复默认提示词", "success");
      await loadPrompts();
    } catch (error) {
      if (runtime.current(token)) notify(errorMessage(error, "恢复默认失败"), "error");
    }
  }

  function addRuleRow(prefix, sourceName) {
    const prefixInput = input({ value: prefix, placeholder: "如：集市层_" });
    const sourceInput = input({ value: sourceName, placeholder: "如：监管报送集市" });
    const remove = button("删除", { listen, className: "dv-table-action is-danger", onClick: () => row.remove() });
    const row = element("tr", {},
      element("td", {}, prefixInput),
      element("td", {}, sourceInput),
      element("td", {}, remove));
    row.dataset.prefix = "1";
    ruleBody.append(row);
  }

  async function loadRules() {
    const token = runtime.next("settings-rules");
    try {
      const rules = await runtime.request(token, (signal) => api.sourceRules({ signal }));
      if (!runtime.current(token)) return;
      ruleBody.replaceChildren();
      (Array.isArray(rules) ? rules : []).forEach((item) => addRuleRow(item.sheet_prefix || "", item.data_source_name || ""));
    } catch (error) {
      if (runtime.current(token)) notify(errorMessage(error, "映射规则加载失败"), "error");
    }
  }

  async function saveSourceRules() {
    const rules = [...ruleBody.children].map((row) => ({
      sheet_prefix: row.children[0].children[0]?.value ?? "",
      data_source_name: row.children[1].children[0]?.value ?? "",
    }));
    const token = runtime.next("settings-rules");
    try {
      await runtime.request(token, (signal) => api.saveSourceRules(rules, { signal }));
      if (!runtime.current(token)) return;
      notify("映射规则已保存", "success");
      await loadRules();
    } catch (error) {
      if (runtime.current(token)) notify(errorMessage(error, "映射规则保存失败"), "error");
    }
  }

  function render() {
    if (!canAdmin) return;
  }

  async function refresh() {
    if (!canAdmin) return;
    await Promise.all([loadDocuments(), knowledge.refresh(), loadPrompts(), loadRules()]);
  }

  render();
  return { header, panel, refresh, render };
}