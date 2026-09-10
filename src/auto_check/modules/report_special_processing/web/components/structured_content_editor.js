/* 特殊处理内容结构化编辑器（行内表单版）：处理表 → 数据源/英文表名/中文表名 → 处理范围 → 字段行。
 *
 * 交互方式：所有操作都在当前弹窗内完成，不再打开二级弹窗。
 * - 数据源归属每张表（不同表可来自不同数据源），只允许选择系统已配置数据源。
 * - 英文表名/英文字段名/条件字段均为“可搜索输入 + 候选面板”，物理名只能来自候选项。
 * - 中文表名/中文字段名：选择英文名后自动带出 comment，始终允许用户修改，不反写数据库。
 * - 处理范围：通用“条件字段 + 条件值”（不再固定项目/合同）：条件字段从当前表真实字段
 *   搜索选择，条件值支持单值/多值（“、”“；”分隔，去空去重），单值生成 `=`、多值生成 `IN`，
 *   条件行之间 AND；每张表至少一条有效条件。
 * - 指定数据日期：每张表独立开关（默认是）。为“是”时基于已缓存的表字段元数据按
  *   系统字典下发的匹配词优先级自动识别数据日期字段：唯一识别直接使用（不显示选择器）；
 *   无匹配或多候选时在标题行显示当前表真实字段的可搜索选择器，保存并使用真实物理字段名。
 * - 表区固定四列（数据源/英文表名/中文表名/操作），处理范围与字段区各自固定栅格，
 *   多张表之间同列严格对齐。
 * - 对外接口：getStructured()（新结构 payload）、getStrings()（兼容派生串）、
 *   getFieldTypes()（{datasource_id: {table_name: {column: data_type}}}）、
 *   validate({formal})（错误定位消息）。 */

import { element } from "./dom.js";

export const MAX_SC_TABLES = 5;
export const MAX_SC_FIELDS = 5;
const MAX_VALUE_LEN = 128;
const MAX_NAME_LEN = 100;
const MAX_SCOPE_CHARS = 1000;
const MAX_CONDITIONS = 20;
const SEARCH_DEBOUNCE_MS = 300;
const FIELD_META_PAGE_SIZE = 100;

function parseScopeText(text) {
  const seen = [];
  String(text || "")
    .split(/[、；,;，]/)
    .forEach((item) => {
      const value = String(item || "").trim();
      if (value && !seen.includes(value)) seen.push(value);
    });
  return seen;
}

function scopeText(values) {
  return (values || []).join("、");
}

function columnDisplayLabel(item) {
  const englishName = String(item?.primary || item?.column_name || "");
  const chineseName = String(item?.secondary || item?.column_comment || "");
  return chineseName ? `${chineseName}（${englishName}）` : englishName;
}

export function createStructuredContentEditor(documentRef, options = {}) {
  const {
    api,
    initial = null,
    disabled = false,
    notify = () => {},
    confirm = null,
    getHost = null,
    datasourceNameSnapshot = "",
    reportPeriodFieldMatchers = [],
  } = options;

  const state = {
    tables: [],
    loadedDatasources: [],
  };

  const addTableButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-bilingual-add rsp-sc-add-action rsp-sc-add-table",
    text: "＋ 添加处理表",
    disabled: disabled || null,
    onClick: () => addTable(),
  });
  const cardsBox = element(documentRef, "div", { className: "rsp-tf-cards rsp-sc-cards" });
  const root = element(documentRef, "div", {
    className: "rsp-sc-editor",
    "aria-label": "数据源与处理表字段",
  }, [
    element(documentRef, "div", { className: "rsp-tf-head rsp-sc-tables-head" }, [
      disabled ? null : element(documentRef, "div", { className: "rsp-sc-header-action" }, [addTableButton]),
    ]),
    cardsBox,
  ]);

  // ===== 数据源（每张表独立下拉） =====

  function fillDatasourceSelect(select, selectedId) {
    select.replaceChildren(
      element(documentRef, "option", { value: "", text: "请选择数据源" }),
      ...state.loadedDatasources.map((item) => element(documentRef, "option", {
        value: item.id,
        text: item.name,
      })),
    );
    select.value = selectedId || "";
  }

  async function loadDatasources() {
    if (disabled) return;
    if (typeof api?.listDatasources !== "function") return;
    try {
      const response = await api.listDatasources();
      const payload = response?.data || response || {};
      state.loadedDatasources = Array.isArray(payload.items) ? payload.items : [];
      state.tables.forEach((table) => {
        if (!table.datasourceId) return;
        const matched = state.loadedDatasources.some((item) => item.id === table.datasourceId);
        if (!matched) {
          state.loadedDatasources.push({
            id: table.datasourceId,
            name: table.datasourceName || table.datasourceId,
            db_type: table.datasourceType || "",
          });
        }
      });
      state.tables.forEach((table) => {
        if (table.dsSelect) fillDatasourceSelect(table.dsSelect, table.datasourceId);
      });
    } catch (error) {
      notify(error?.message || "数据源列表加载失败", "error");
    }
  }

  function setTableDatasource(table, datasourceId, datasourceName, datasourceType) {
    table.datasourceId = datasourceId || "";
    table.datasourceName = datasourceName || "";
    table.datasourceType = datasourceType || "";
    // 数据源变化后物理表/字段必须重新选择：清空并保留一行空字段与一条空条件；
    // 报送期识别结果属于旧表，一并清空。
    table.schema = "";
    table.physical = "";
    table.chinese = "";
    table.fieldMeta = null;
    table.fieldTypes = {};
    table.conditions = [emptyCondition()];
    table.reportPeriodField = "";
    table.reportPeriodFieldSource = "";
    if (table.comboInput) table.comboInput.value = "";
    if (table.cnInput) table.cnInput.value = "";
    if (table.periodFieldInput) table.periodFieldInput.value = "";
    table.fields = [emptyField()];
    renderConditions(table);
    renderFields(table);
    if (table.renderReportPeriodRow) table.renderReportPeriodRow();
  }

  // ===== 可搜索输入 + 候选面板（表/字段/条件共用） =====

  function makeCombo({ placeholder, pageSize, fetchPage, onPick }) {
    const input = element(documentRef, "input", {
      type: "text",
      className: "rsp-sc-combo-input",
      placeholder,
      autocomplete: "off",
      spellcheck: "false",
      "aria-label": placeholder,
      disabled: disabled || null,
    });
    const listBox = element(documentRef, "div", { className: "rsp-sc-combo-list", role: "listbox" });
    const status = element(documentRef, "div", { className: "rsp-sc-combo-status", hidden: true });
    const panel = element(documentRef, "div", { className: "rsp-sc-combo-panel", hidden: true }, [listBox, status]);
    const shell = element(documentRef, "div", { className: "rsp-sc-combo" }, [input, panel]);

    let page = 1;
    let totalPages = 1;
    let items = [];
    let timer = null;
    let scrollListenerAttached = false;
    let requestId = 0;

    function anchorPanel() {
      if (typeof input.getBoundingClientRect !== "function") return;
      const rect = input.getBoundingClientRect();
      if (!rect || typeof rect.top !== "number") return;
      panel.style.top = String(rect.bottom + 4) + "px";
      panel.style.left = String(rect.left) + "px";
      panel.style.width = String(rect.width) + "px";
    }

    function close() {
      panel.hidden = true;
    }

    async function load(requestedPage = 1) {
      const activeRequestId = ++requestId;
      const previousScrollTop = listBox.scrollTop;
      page = requestedPage;
      status.hidden = false;
      status.className = "rsp-sc-combo-status";
      status.textContent = "加载中…";
      panel.hidden = false;
      try {
        const response = await fetchPage({
          keyword: String(input.value || "").trim(),
          page,
          page_size: pageSize,
        });
        if (activeRequestId !== requestId) return;
        const payload = response?.data || response || {};
        const nextItems = Array.isArray(payload.items) ? payload.items : [];
        items = requestedPage === 1 ? nextItems : items.concat(nextItems);
        totalPages = Math.max(1, Number(payload.total_pages) || 1);
        renderItems();
        if (requestedPage > 1) listBox.scrollTop = previousScrollTop;
        else listBox.scrollTop = 0;
      } catch (error) {
        if (activeRequestId !== requestId) return;
        items = [];
        listBox.replaceChildren();
        status.hidden = false;
        status.className = "rsp-sc-combo-status is-error";
        status.textContent = error?.message || "读取失败，请稍后重试";
        panel.hidden = false;
      }
    }

    function renderItems() {
      listBox.replaceChildren();
      if (!items.length) {
        status.hidden = false;
        status.className = "rsp-sc-combo-status";
        status.textContent = "未找到匹配的数据";
        return;
      }
      status.hidden = true;
      items.forEach((item) => {
        const primaryText = String(item.primary || item.table_name || item.column_name || "");
        const secondaryText = String(item.secondary || item.table_comment || item.column_comment || "");
        listBox.append(element(documentRef, "button", {
          type: "button",
          className: "rsp-sc-combo-option",
          role: "option",
          onClick: () => {
            input.value = primaryText;
            onPick(item);
            close();
          },
        }, [
          element(documentRef, "span", { className: "rsp-sc-combo-primary", text: primaryText }),
          secondaryText ? element(documentRef, "span", { className: "rsp-sc-combo-secondary", text: secondaryText }) : null,
        ]));
      });
      if (page < totalPages) {
        listBox.append(element(documentRef, "button", {
          type: "button",
          className: "rsp-sc-combo-more",
          text: "加载更多",
          onClick: () => load(page + 1),
        }));
      }
    }

    function open() {
      attachScrollClose();
      anchorPanel();
      panel.hidden = false;
      load(1);
    }

    function scheduleSearch() {
      clearTimeout(timer);
      timer = setTimeout(() => {
        attachScrollClose();
        anchorPanel();
        load(1);
      }, SEARCH_DEBOUNCE_MS);
    }

    function attachScrollClose() {
      if (scrollListenerAttached) return;
      scrollListenerAttached = true;
      try {
        getHost?.()?.addEventListener?.("scroll", closeOnHostScroll, true);
      } catch (_) {
        // 宿主容器尚未就绪时忽略；滚动关闭为渐进增强。
      }
    }

    function closeOnHostScroll(event) {
      if (event?.target && shell.contains(event.target)) return;
      close();
    }

    input.addEventListener("input", scheduleSearch);
    input.addEventListener("focus", open);
    input.addEventListener("click", () => {
      if (panel.hidden) open();
    });
    root.addEventListener("click", (event) => {
      if (event.target === shell || shell.contains(event.target)) return;
      close();
    });

    return { shell, input, panel, close };
  }

  // ===== 字段元数据缓存（整表一次加载，复用） =====

  async function loadFieldMeta(table) {
    if (!table.datasourceId || !table.physical) {
      table.fieldMeta = null;
      table.fieldTypes = {};
      return;
    }
    let items = [];
    let page = 1;
    for (let guard = 0; guard < 10; guard += 1) {
      const response = await api.listColumns(table.datasourceId, table.physical, {
        keyword: "",
        page,
        page_size: FIELD_META_PAGE_SIZE,
      });
      const payload = response?.data || response || {};
      const batch = Array.isArray(payload.items) ? payload.items : [];
      items = items.concat(batch);
      const total = Number(payload.total) || batch.length;
      if (items.length >= total || !batch.length) break;
      page += 1;
    }
    table.fieldMeta = items;
    const types = {};
    items.forEach((item) => {
      if (item?.column_name) types[item.column_name] = String(item.data_type || "");
    });
    table.fieldTypes = types;
  }

  function filterFieldMeta(table, keyword) {
    const kw = String(keyword || "").trim().toLowerCase();
    if (!kw) return table.fieldMeta || [];
    return (table.fieldMeta || []).filter((item) => {
      const name = String(item.column_name || "").toLowerCase();
      const comment = String(item.column_comment || "").toLowerCase();
      return name.includes(kw) || comment.includes(kw);
    });
  }

  // ===== 报送期字段识别（基于已缓存元数据，不额外访问数据库） =====

  function detectReportPeriodField(table) {
    const matcherCodes = reportPeriodFieldMatchers
      .map((item) => String(item?.code || "").trim().toLowerCase())
      .filter((code, index, values) => code && values.indexOf(code) === index);
    const candidates = table.fieldMeta || [];
    let picked = "";
    const matchModes = [
      (name, code) => name === code,
      (name, code) => name.endsWith(`_${code}`),
      (name, code) => name.includes(code),
    ];
    search:
    for (const matchesMode of matchModes) {
      for (const code of matcherCodes) {
        const matches = candidates.filter((item) =>
          matchesMode(String(item.column_name || "").toLowerCase(), code));
        if (matches.length === 1) {
          picked = matches[0].column_name;
          break search;
        }
        if (matches.length > 1) break search;
      }
    }
    table.reportPeriodField = picked;
    table.reportPeriodFieldSource = picked ? "AUTO" : "MANUAL";
    return Boolean(picked);
  }

  // ===== 表/条件/字段模型 =====

  function emptyField() {
    return { physical: "", chinese: "", before: "", after: "", comboInput: null, cnInput: null };
  }

  function emptyCondition() {
    return { column: "", values: [], comboInput: null, valueInput: null };
  }

  function emptyTable() {
    return {
      datasourceId: "",
      datasourceType: "",
      datasourceName: "",
      schema: "",
      physical: "",
      chinese: "",
      fieldMeta: null,
      fieldTypes: {},
      conditions: [emptyCondition()],
      limitReportPeriod: true,
      reportPeriodField: "",
      reportPeriodFieldSource: "",
      fields: [emptyField()],
      dsSelect: null,
      comboInput: null,
      cnInput: null,
      periodFieldInput: null,
      conditionRowsBox: null,
      fieldsBox: null,
      removeButton: null,
      card: null,
      renderReportPeriodRow: null,
    };
  }

  function tableDisplay(table) {
    return table.chinese || table.physical;
  }

  function addTable() {
    if (state.tables.length >= MAX_SC_TABLES) {
      notify(`最多选择 ${MAX_SC_TABLES} 张处理表`, "warning");
      return;
    }
    const table = emptyTable();
    state.tables.push(table);
    const card = renderTableCard(table);
    cardsBox.append(card);
    updateTableRemoveButtons();
  }

  function updateTableRemoveButtons() {
    state.tables.forEach((table) => {
      if (!table.removeButton) return;
      table.removeButton.disabled = disabled || state.tables.length <= 1;
      table.removeButton.title = state.tables.length <= 1 ? "至少保留一张处理表" : "";
    });
  }

  async function removeTable(table) {
    if (state.tables.length <= 1) {
      notify("至少保留一张处理表", "warning");
      updateTableRemoveButtons();
      return;
    }
    const doRemove = () => {
      const index = state.tables.indexOf(table);
      if (index >= 0) state.tables.splice(index, 1);
      if (table.card) table.card.remove();
      updateTableRemoveButtons();
    };
    if (table.fields.some((field) => field.physical) && typeof confirm === "function") {
      const confirmModal = documentRef.getElementById?.("confirmModal");
      confirmModal?.classList.add("rsp-confirm-above-record");
      try {
        const ok = await confirm(
          "确认删除表",
          "删除该表将同时删除其关联字段及修改前/修改后信息，是否确认删除？",
          { tone: "danger" },
        );
        if (ok) doRemove();
      } finally {
        setTimeout(() => {
          confirmModal?.classList.remove("rsp-confirm-above-record");
        }, 220);
      }
      return;
    }
    doRemove();
  }

  function removeCondition(table, condition) {
    const filled = table.conditions.filter(
      (item) => item.column || (item.valueInput && String(item.valueInput.value || "").trim()),
    );
    if (filled.length <= 1) {
      const index = table.conditions.indexOf(condition);
      if (index >= 0) table.conditions[index] = emptyCondition();
      renderConditions(table);
      return;
    }
    const index = table.conditions.indexOf(condition);
    if (index >= 0) table.conditions.splice(index, 1);
    renderConditions(table);
  }

  function removeField(table, field) {
    const filled = table.fields.filter((item) => item.physical);
    if (filled.length <= 1) {
      const index = table.fields.indexOf(field);
      if (index >= 0) table.fields[index] = emptyField();
      renderFields(table);
      return;
    }
    const index = table.fields.indexOf(field);
    if (index >= 0) table.fields.splice(index, 1);
    renderFields(table);
  }

  function addConditionRow(table) {
    if (table.conditions.length >= MAX_CONDITIONS) {
      notify(`最多配置 ${MAX_CONDITIONS} 条处理范围条件`, "warning");
      return;
    }
    const empty = table.conditions.find((item) => !item.column);
    if (empty) {
      notify("请先在空条件行选择条件字段", "warning");
      return;
    }
    table.conditions.push(emptyCondition());
    renderConditions(table);
  }

  function addFieldRow(table) {
    if (table.fields.length >= MAX_SC_FIELDS) {
      notify(`每张表最多选择 ${MAX_SC_FIELDS} 个字段`, "warning");
      return;
    }
    if (!table.datasourceId) {
      notify("请先选择数据源", "warning");
      return;
    }
    if (!table.physical) {
      notify("请先选择处理表", "warning");
      return;
    }
    const empty = table.fields.find((field) => !field.physical && !field.chinese);
    if (empty) {
      notify("请先在空字段行选择字段", "warning");
      return;
    }
    table.fields.push(emptyField());
    renderFields(table);
  }

  // ===== 渲染 =====

  function renderTableCard(table) {
    const dsSelect = element(documentRef, "select", {
      className: "rsp-compact-select rsp-sc-ds-select",
      "aria-label": "数据源",
      disabled: disabled || null,
    });
    fillDatasourceSelect(dsSelect, table.datasourceId);
    table.dsSelect = dsSelect;
    dsSelect.addEventListener("change", () => {
      const matched = state.loadedDatasources.find((item) => item.id === dsSelect.value);
      setTableDatasource(table, dsSelect.value, matched?.name || "", matched?.db_type || "");
    });

    const combo = makeCombo({
      placeholder: "请选择表（支持中文/英文模糊搜索）",
      pageSize: 10,
      fetchPage: async (params) => {
        if (!table.datasourceId) throw new Error("请先选择数据源");
        return api.listTables(table.datasourceId, params);
      },
      onPick: (item) => {
        table.schema = String(item.schema || "");
        table.physical = String(item.primary || item.table_name || "");
        table.chinese = String(item.secondary || item.table_comment || "");
        if (table.cnInput) table.cnInput.value = table.chinese;
        // 表变化：重新加载整表字段元数据（一次），随后识别报送期字段
        loadFieldMeta(table)
          .then(() => {
            if (table.periodFieldInput) table.periodFieldInput.value = "";
            if (table.limitReportPeriod) {
              detectReportPeriodField(table);
            } else {
              table.reportPeriodField = "";
              table.reportPeriodFieldSource = "";
            }
            renderConditions(table);
            if (table.renderReportPeriodRow) table.renderReportPeriodRow();
          })
          .catch((error) => {
            notify(error?.message || "字段信息获取失败，请稍后重试", "error");
          });
      },
    });
    table.comboInput = combo.input;
    combo.input.value = table.physical;
    const cnInput = element(documentRef, "input", {
      className: "rsp-sc-cn-input",
      value: table.chinese,
      maxlength: String(MAX_NAME_LEN),
      placeholder: "请输入中文表名",
      "aria-label": "中文表名",
      disabled: disabled || null,
    });
    table.cnInput = cnInput;
    cnInput.addEventListener("input", () => { table.chinese = cnInput.value.trim(); });

    const removeButton = element(documentRef, "button", {
      type: "button",
      className: "rsp-bilingual-remove rsp-sc-remove-table",
      text: "删除表",
      disabled: disabled || null,
      onClick: () => removeTable(table),
    });
    table.removeButton = removeButton;

    // ===== 处理范围区 =====
    const radioName = `rsp-rp-${Math.random().toString(36).slice(2, 10)}`;
    const periodYes = element(documentRef, "input", {
      type: "radio",
      name: radioName,
      value: "yes",
      "aria-label": "限制报送期是",
      disabled: disabled || null,
    });
    const periodNo = element(documentRef, "input", {
      type: "radio",
      name: radioName,
      value: "no",
      "aria-label": "限制报送期否",
      disabled: disabled || null,
    });
    const periodFieldCombo = makeCombo({
      placeholder: "请选择数据日期字段",
      pageSize: 10,
      fetchPage: async (params) => {
        if (!table.datasourceId) throw new Error("请先选择数据源");
        if (!table.physical) throw new Error("请先选择处理表");
        const selectedLabel = reportPeriodDisplayLabel(table);
        const requestParams = selectedLabel && params.keyword === selectedLabel
          ? { ...params, keyword: "" }
          : params;
        if (table.fieldMeta) return columnFetch(table, requestParams);
        return api.listColumns(table.datasourceId, table.physical, requestParams);
      },
      onPick: (item) => {
        table.reportPeriodField = String(item.primary || item.column_name || "");
        table.reportPeriodFieldSource = "MANUAL";
        periodFieldCombo.input.value = columnDisplayLabel(item);
        if (table.renderReportPeriodRow) table.renderReportPeriodRow();
      },
    });
    periodFieldCombo.shell.classList.add("rsp-sc-date-field-picker");
    const periodFieldInput = periodFieldCombo.input;
    periodFieldInput.value = table.reportPeriodFieldSource === "MANUAL" ? table.reportPeriodField : "";
    table.periodFieldInput = periodFieldInput;
    periodFieldInput.addEventListener("input", () => {
      if (String(periodFieldInput.value || "").trim() !== table.reportPeriodField) {
        table.reportPeriodField = "";
        table.reportPeriodFieldSource = "";
      }
    });
    periodYes.addEventListener("change", () => {
      table.limitReportPeriod = true;
      // 否 → 是：基于已缓存元数据重新识别（不访问数据库）
      detectReportPeriodField(table);
      if (table.periodFieldInput) table.periodFieldInput.value = "";
      if (table.renderReportPeriodRow) table.renderReportPeriodRow();
      if (!table.reportPeriodField) table.periodFieldInput?.focus?.();
    });
    periodNo.addEventListener("change", () => {
      table.limitReportPeriod = false;
      table.reportPeriodField = "";
      table.reportPeriodFieldSource = "";
      if (table.periodFieldInput) table.periodFieldInput.value = "";
      if (table.renderReportPeriodRow) table.renderReportPeriodRow();
    });
    function renderReportPeriodRow() {
      periodYes.checked = table.limitReportPeriod;
      periodNo.checked = !table.limitReportPeriod;
      const show = table.limitReportPeriod
        && Boolean(table.physical)
        && table.reportPeriodFieldSource !== "AUTO";
      if (show && table.reportPeriodField) {
        periodFieldInput.value = reportPeriodDisplayLabel(table);
      }
      periodFieldCombo.shell.hidden = !show;
    }
    table.renderReportPeriodRow = renderReportPeriodRow;

    const conditionRowsBox = element(documentRef, "div", { className: "rsp-sc-condition-rows" });
    table.conditionRowsBox = conditionRowsBox;

    const scopeZone = element(documentRef, "div", { className: "rsp-sc-scope" }, [
      element(documentRef, "div", { className: "rsp-sc-section-head rsp-sc-scope-title-row" }, [
        element(documentRef, "div", { className: "rsp-sc-section-head-main" }, [
          element(documentRef, "div", { className: "rsp-sc-scope-controls" }, [
            element(documentRef, "span", { className: "rsp-tf-fields-title", text: "处理范围" }),
            element(documentRef, "span", { className: "rsp-sc-rp-label rsp-sc-date-label", text: "指定数据日期" }),
            element(documentRef, "div", { className: "rsp-sc-rp-options" }, [
              element(documentRef, "label", { className: "rsp-sc-radio" }, [
                periodYes,
                element(documentRef, "span", { text: "是" }),
              ]),
              element(documentRef, "label", { className: "rsp-sc-radio" }, [
                periodNo,
                element(documentRef, "span", { text: "否" }),
              ]),
            ]),
          ]),
          periodFieldCombo.shell,
        ]),
        disabled ? null : element(documentRef, "div", { className: "rsp-sc-header-action" }, [
          element(documentRef, "button", {
            type: "button",
            className: "rsp-bilingual-add rsp-sc-add-action",
            text: "＋ 添加条件",
            disabled: disabled || table.conditions.length >= MAX_CONDITIONS || null,
            onClick: () => addConditionRow(table),
          }),
        ]),
      ]),
      element(documentRef, "div", { className: "rsp-sc-row rsp-sc-cond-head" }, [
        element(documentRef, "span", { text: "条件字段" }),
        element(documentRef, "span", { text: "条件值" }),
        element(documentRef, "span", { text: "操作" }),
      ]),
      conditionRowsBox,
    ]);

    // ===== 关联字段区 =====
    const fieldsBox = element(documentRef, "div", { className: "rsp-sc-field-rows" });
    table.fieldsBox = fieldsBox;

    const cardBody = element(documentRef, "div", { className: "rsp-sc-card-body" }, [
      element(documentRef, "div", { className: "rsp-sc-row rsp-sc-tbl-head" }, [
        element(documentRef, "span", { text: "数据源" }),
        element(documentRef, "span", { text: "英文表名" }),
        element(documentRef, "span", { text: "中文表名" }),
        element(documentRef, "span", { text: "操作" }),
      ]),
      element(documentRef, "div", { className: "rsp-sc-row rsp-sc-tbl-row" }, [
        dsSelect,
        combo.shell,
        cnInput,
        removeButton,
      ]),
      scopeZone,
      element(documentRef, "div", { className: "rsp-sc-fields-area" }, [
        element(documentRef, "div", { className: "rsp-sc-section-head rsp-sc-fields-head" }, [
          element(documentRef, "div", { className: "rsp-sc-section-head-main" }, [
            element(documentRef, "span", { className: "rsp-tf-fields-title", text: "修改字段" }),
          ]),
          disabled ? null : element(documentRef, "div", { className: "rsp-sc-header-action" }, [
            element(documentRef, "button", {
              type: "button",
              className: "rsp-bilingual-add rsp-sc-add-action",
              text: "＋ 添加字段",
              disabled: disabled || table.fields.length >= MAX_SC_FIELDS || null,
              onClick: () => addFieldRow(table),
            }),
          ]),
        ]),
        element(documentRef, "div", { className: "rsp-sc-row rsp-sc-field-head" }, [
          element(documentRef, "span", { text: "英文字段名" }),
          element(documentRef, "span", { text: "中文字段名" }),
          element(documentRef, "span", { text: "修改前" }),
          element(documentRef, "span", { text: "修改后" }),
          element(documentRef, "span", { text: "操作" }),
        ]),
        fieldsBox,
      ]),
    ]);

    const card = element(documentRef, "div", { className: "rsp-tf-card rsp-sc-card" }, [cardBody]);
    table.card = card;
    renderConditions(table);
    renderFields(table);
    renderReportPeriodRow();
    return card;
  }

  // 字段/条件搜索：已缓存整表字段元数据时内存过滤 + 本地分页
  function columnFetch(table, params) {
    const keyword = String(params.keyword || "").trim();
    const filtered = filterFieldMeta(table, keyword);
    const pageSize = Number(params.page_size) || 20;
    const page = Number(params.page) || 1;
    const start = (page - 1) * pageSize;
    const items = filtered.slice(start, start + pageSize).map((item) => ({
      primary: item.column_name,
      secondary: item.column_comment || "",
    }));
    return {
      items,
      total: filtered.length,
      page,
      page_size: pageSize,
      total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)),
    };
  }

  function reportPeriodDisplayLabel(table) {
    return tableColumnDisplayLabel(table, table.reportPeriodField);
  }

  function tableColumnDisplayLabel(table, columnName) {
    const field = (table.fieldMeta || []).find(
      (item) => String(item?.column_name || "") === columnName,
    );
    return columnDisplayLabel({ column_name: columnName, column_comment: field?.column_comment || "" });
  }

  function renderConditions(table) {
    if (!table.conditionRowsBox) return;
    table.conditionRowsBox.replaceChildren(
      ...table.conditions.map((condition) => renderConditionRow(table, condition)),
    );
  }

  function renderConditionRow(table, condition) {
    const combo = makeCombo({
      placeholder: "请选择字段",
      pageSize: 10,
      fetchPage: async (params) => {
        if (!table.datasourceId) throw new Error("请先选择数据源");
        if (!table.physical) throw new Error("请先选择处理表");
        const selectedLabel = tableColumnDisplayLabel(table, condition.column);
        const requestParams = selectedLabel && params.keyword === selectedLabel
          ? { ...params, keyword: "" }
          : params;
        if (table.fieldMeta) return columnFetch(table, requestParams);
        return api.listColumns(table.datasourceId, table.physical, requestParams);
      },
      onPick: (item) => {
        condition.column = String(item.primary || item.column_name || "");
        combo.input.value = columnDisplayLabel(item);
        if (condition.valueInput) condition.valueInput.focus?.();
      },
    });
    condition.comboInput = combo.input;
    combo.input.value = tableColumnDisplayLabel(table, condition.column);
    const valueInput = element(documentRef, "input", {
      className: "rsp-sc-cn-input",
      value: scopeText(condition.values),
      maxlength: String(MAX_SCOPE_CHARS),
      placeholder: "请输入条件值",
      "aria-label": "条件值",
      disabled: disabled || null,
    });
    condition.valueInput = valueInput;
    valueInput.addEventListener("input", () => {
      condition.values = parseScopeText(valueInput.value);
    });
    return element(documentRef, "div", { className: "rsp-sc-row rsp-sc-cond-row" }, [
      combo.shell,
      valueInput,
      disabled ? element(documentRef, "span") : element(documentRef, "button", {
        type: "button",
        className: "rsp-bilingual-remove rsp-sc-remove-condition",
        text: "删除",
        disabled: disabled || null,
        onClick: () => removeCondition(table, condition),
      }),
    ]);
  }

  function renderFields(table) {
    if (!table.fieldsBox) return;
    table.fieldsBox.replaceChildren(
      ...table.fields.map((field) => renderFieldRow(table, field)),
    );
  }

  function renderFieldRow(table, field) {
    const combo = makeCombo({
      placeholder: "请选择字段",
      pageSize: 10,
      fetchPage: async (params) => {
        if (!table.datasourceId) throw new Error("请先选择数据源");
        if (!table.physical) throw new Error("请先选择处理表");
        if (table.fieldMeta) return columnFetch(table, params);
        return api.listColumns(table.datasourceId, table.physical, params);
      },
      onPick: (item) => {
        field.physical = String(item.primary || item.column_name || "");
        field.chinese = String(item.secondary || item.column_comment || "");
        if (field.cnInput) field.cnInput.value = field.chinese;
      },
    });
    field.comboInput = combo.input;
    combo.input.value = field.physical;
    const cnInput = element(documentRef, "input", {
      className: "rsp-sc-cn-input",
      value: field.chinese,
      maxlength: String(MAX_NAME_LEN),
      placeholder: "请输入中文字段名",
      "aria-label": "中文字段名",
      disabled: disabled || null,
    });
    field.cnInput = cnInput;
    cnInput.addEventListener("input", () => { field.chinese = cnInput.value.trim(); });

    const beforeInput = element(documentRef, "input", {
      className: "rsp-sc-value-input",
      value: field.before,
      maxlength: String(MAX_VALUE_LEN),
      placeholder: "修改前",
      "aria-label": "修改前",
      disabled: disabled || null,
    });
    const afterInput = element(documentRef, "input", {
      className: "rsp-sc-value-input",
      value: field.after,
      maxlength: String(MAX_VALUE_LEN),
      placeholder: "修改后",
      "aria-label": "修改后",
      disabled: disabled || null,
    });
    field.beforeInput = beforeInput;
    field.afterInput = afterInput;
    beforeInput.addEventListener("input", () => { field.before = beforeInput.value; });
    afterInput.addEventListener("input", () => { field.after = afterInput.value; });

    return element(documentRef, "div", { className: "rsp-sc-row rsp-sc-field-row" }, [
      combo.shell,
      cnInput,
      element(documentRef, "div", { className: "rsp-sc-value-cell" }, [beforeInput]),
      element(documentRef, "div", { className: "rsp-sc-value-cell" }, [afterInput]),
      disabled ? element(documentRef, "span") : element(documentRef, "button", {
        type: "button",
        className: "rsp-bilingual-remove rsp-sc-remove-field",
        text: "删除",
        disabled: disabled || null,
        onClick: () => removeField(table, field),
      }),
    ]);
  }

  // ===== 对外接口 =====

  function syncFromDom() {
    state.tables.forEach((table) => {
      if (table.cnInput) table.chinese = table.cnInput.value.trim();
      table.fields.forEach((field) => {
        if (field.cnInput) field.chinese = field.cnInput.value.trim();
      });
      table.conditions.forEach((condition) => {
        if (condition.valueInput) condition.values = parseScopeText(condition.valueInput.value);
      });
    });
  }

  function getStructured() {
    syncFromDom();
    const tables = state.tables
      .filter((table) => table.datasourceId && table.physical)
      .map((table) => ({
        schema: table.schema,
        table_name: table.physical,
        chinese_table_name: table.chinese,
        table_name_source: "MANUAL",
        datasource_id: table.datasourceId,
        datasource_type: table.datasourceType,
        conditions: table.conditions
          .filter((condition) => condition.column && condition.values.length)
          .map((condition) => ({
            column_name: condition.column,
            values: condition.values,
          })),
        limit_report_period: table.limitReportPeriod,
        report_period_field: table.limitReportPeriod ? table.reportPeriodField : "",
        report_period_field_source: table.limitReportPeriod ? table.reportPeriodFieldSource : "",
        fields: table.fields
          .filter((field) => field.physical)
          .map((field) => ({
            column_name: field.physical,
            chinese_column_name: field.chinese,
            column_name_source: "MANUAL",
            value_before: field.before,
            value_after: field.after,
          })),
      }));
    const first = state.tables.find((table) => table.datasourceId) || state.tables[0] || {};
    return {
      datasource_id: first.datasourceId || "",
      datasource_type: first.datasourceType || "",
      tables,
    };
  }

  function getFieldTypes() {
    const result = {};
    state.tables.forEach((table) => {
      if (!table.datasourceId || !table.physical || !table.fieldTypes) return;
      if (!result[table.datasourceId]) result[table.datasourceId] = {};
      result[table.datasourceId][table.physical] = { ...table.fieldTypes };
    });
    return result;
  }

  function getStrings() {
    const content = getStructured();
    if (!content.tables.length) return { table_name: "", field_name: "", value_before: "", value_after: "" };
    const tableName = content.tables
      .map((table) => `${table.chinese_table_name || table.table_name}｜${table.table_name}`)
      .join("；");
    const fieldName = content.tables
      .map((table) => table.fields
        .map((field) => `${field.chinese_column_name || field.column_name}｜${field.column_name}`)
        .join("；"))
      .join("；；");
    const before = [];
    const after = [];
    content.tables.forEach((table) => table.fields.forEach((field) => {
      before.push(field.value_before);
      after.push(field.value_after);
    }));
    return {
      table_name: tableName,
      field_name: fieldName,
      value_before: before.join("\n"),
      value_after: after.join("\n"),
    };
  }

  function validate({ formal = false } = {}) {
    syncFromDom();
    for (const table of state.tables) {
      if (!table.datasourceId) {
        return { message: "请选择数据源", control: table.dsSelect || null };
      }
      if (!table.physical) {
        return { message: "请选择处理表", control: table.comboInput || null };
      }
      if (!table.chinese) {
        return { message: "请输入中文表名", control: table.cnInput || null };
      }
      // 处理范围条件：逐行定位（空行忽略）
      const effectiveConditions = table.conditions.filter(
        (condition) => condition.column || (condition.valueInput && String(condition.valueInput.value || "").trim()),
      );
      if (formal && !effectiveConditions.length) {
        return {
          message: `请至少为“${tableDisplay(table)}”配置一条处理范围`,
          control: table.conditions[0]?.comboInput || null,
        };
      }
      for (const condition of effectiveConditions) {
        if (!condition.column) {
          return { message: "请选择处理范围字段", control: condition.comboInput || null };
        }
        if (!condition.values.length) {
          return { message: "请输入处理范围条件值", control: condition.valueInput || null };
        }
      }
      // 限制报送期：为“是”时必须有已确定（自动识别或人工校验通过）的报送期字段
      if (table.limitReportPeriod) {
        if (!table.reportPeriodField) {
          return {
            message: "请选择数据日期字段",
            control: table.periodFieldInput,
          };
        }
      }
      const fields = table.fields.filter((field) => field.physical);
      if (!fields.length) {
        return { message: `请至少为“${tableDisplay(table)}”选择一个关联字段`, control: null };
      }
      for (const field of fields) {
        const label = field.chinese || field.physical;
        if (!field.chinese) {
          return { message: "请输入中文字段名", control: field.cnInput || null };
        }
        if (formal && !String(field.before || "").trim()) {
          return { message: `${label}：请输入修改前内容`, control: field.beforeInput || null };
        }
        if (formal && !String(field.after || "").trim()) {
          return { message: `${label}：请输入修改后内容`, control: field.afterInput || null };
        }
      }
    }
    return null;
  }

  function applyInitial() {
    if (!initial || typeof initial !== "object") return;
    const initialTables = Array.isArray(initial.tables) ? initial.tables : [];
    initialTables.forEach((rawTable) => {
      const table = emptyTable();
      table.datasourceId = String(rawTable?.datasource_id || initial.datasource_id || "");
      table.datasourceType = String(rawTable?.datasource_type || initial.datasource_type || "");
      table.datasourceName = datasourceNameSnapshot || "";
      table.schema = String(rawTable?.schema || "");
      table.physical = String(rawTable?.table_name || "");
      table.chinese = String(rawTable?.chinese_table_name || "");
      table.limitReportPeriod = rawTable?.limit_report_period !== false;
      table.reportPeriodField = String(rawTable?.report_period_field || "");
      table.reportPeriodFieldSource = String(rawTable?.report_period_field_source || "");
      table.conditions = (Array.isArray(rawTable?.conditions) ? rawTable.conditions : []).map((item) => {
        const condition = emptyCondition();
        condition.column = String(item?.column_name || "");
        condition.values = Array.isArray(item?.values)
          ? item.values.map((value) => String(value || "").trim()).filter(Boolean)
          : [];
        return condition;
      });
      if (!table.conditions.length) table.conditions.push(emptyCondition());
      table.fields = (Array.isArray(rawTable?.fields) ? rawTable.fields : []).map((field) => {
        const item = emptyField();
        item.physical = String(field?.column_name || "");
        item.chinese = String(field?.chinese_column_name || "");
        item.before = String(field?.value_before || "");
        item.after = String(field?.value_after || "");
        return item;
      });
      if (!table.fields.length) table.fields.push(emptyField());
      state.tables.push(table);
      cardsBox.append(renderTableCard(table));
      // 回显后异步加载字段元数据并重新识别报送期（不阻塞渲染）
      if (table.datasourceId && table.physical && !disabled) {
        loadFieldMeta(table)
          .then(() => {
            if (table.limitReportPeriod) {
              const manual = table.reportPeriodFieldSource === "MANUAL";
              if (!manual || !table.reportPeriodField) {
                detectReportPeriodField(table);
              }
            } else {
              table.reportPeriodField = "";
              table.reportPeriodFieldSource = "";
            }
            renderConditions(table);
            if (table.renderReportPeriodRow) table.renderReportPeriodRow();
          })
          .catch(() => {});
      }
    });
  }

  applyInitial();
  if (!state.tables.length && !disabled) addTable();
  updateTableRemoveButtons();
  loadDatasources();

  root.getStructured = getStructured;
  root.getStrings = getStrings;
  root.getFieldTypes = getFieldTypes;
  root.validate = validate;
  root.focusFirst = () => {
    const first = state.tables[0];
    (first?.dsSelect || addTableButton).focus?.();
  };
  return root;
}
