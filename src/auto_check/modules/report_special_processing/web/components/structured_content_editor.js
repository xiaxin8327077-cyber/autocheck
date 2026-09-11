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
let itemIdSequence = 0;

function createItemId(prefix) {
  itemIdSequence += 1;
  const randomUuid = globalThis.crypto?.randomUUID?.();
  const suffix = randomUuid || `${Date.now().toString(36)}-${itemIdSequence.toString(36)}`;
  return `${prefix}-${suffix}`.slice(0, 64);
}

/* 行尾操作图标（与项目现有 SVG 图标风格一致：24×24 viewBox、stroke-based） */
const ICON_PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';
const ICON_MINUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/></svg>';
/* 表级删除图标（与行级减号区分） */
const ICON_TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>';

/* 条件运算符：页面展示中文名，内部保存 SQL 运算符。 */
const CONDITION_OPERATORS = [
  { value: "=", label: "等于" },
  { value: "<>", label: "不等于" },
  { value: ">", label: "大于" },
  { value: ">=", label: "大于等于" },
  { value: "<", label: "小于" },
  { value: "<=", label: "小于等于" },
  { value: "LIKE", label: "模糊匹配" },
  { value: "IN", label: "属于多个值（IN）" },
  { value: "IS NULL", label: "为空" },
  { value: "IS NOT NULL", label: "不为空" },
];
const CONDITION_OPERATORS_REQUIRING_VALUE = new Set(["=", "<>", ">", ">=", "<", "<=", "LIKE", "IN"]);
const CONDITION_OPERATOR_NO_VALUE = new Set(["IS NULL", "IS NOT NULL"]);

/* 条件运算符智能匹配：AUTO 模式下 1 个有效值 → 等于，多个有效值 → 属于多个值；
 * 用户主动选择运算符后进入 MANUAL，不再被自动覆盖。 */
function autoOperator(values) {
  return (values || []).length > 1 ? "IN" : "=";
}

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

/* 弹窗滚动时，平台增强的定制下拉（数据源/条件类型等）直接关闭，
 * 避免 fixed 下拉停留在原坐标造成漂移/覆盖（需求允许“关闭或重定位”二选一）。 */
let platformSelectCloseRaf = 0;
function schedulePlatformSelectClose(documentRef) {
  if (platformSelectCloseRaf) return;
  const view = documentRef?.defaultView;
  const run = () => {
    platformSelectCloseRaf = 0;
    const closeFn = typeof view?.closeCustomSelect === "function" ? view.closeCustomSelect : null;
    const opens = documentRef.querySelectorAll(".custom-select-open .custom-select-native");
    for (let i = 0; i < opens.length; i += 1) {
      try {
        if (closeFn) closeFn(opens[i]);
        else opens[i].closest?.(".custom-select-shell")?.classList.remove("custom-select-open");
      } catch (_) {
        // 平台下拉状态异常时忽略。
      }
    }
  };
  platformSelectCloseRaf = view?.requestAnimationFrame
    ? view.requestAnimationFrame(run)
    : setTimeout(run, 16);
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
    onChange = null,
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

  // 配置变更通知：输入、选择、增删等任意交互变化都触发 onChange
  // （由抽屉侧做 debounce 后实时重新生成处理脚本）。
  if (!disabled && typeof onChange === "function") {
    ["input", "change", "click"].forEach((type) => {
      root.addEventListener(type, onChange, true);
    });
  }

  // 编辑器级滚动守护：弹窗滚动时关闭平台定制下拉（数据源/条件类型等），
  // 与 combo 面板解耦，确保未打开过组合框时同样生效，避免下拉漂移。
  (function attachEditorScrollGuard() {
    const attach = () => {
      try {
        getHost?.()?.addEventListener?.("scroll", (event) => {
          if (event?.target && root.contains(event.target)) return;
          schedulePlatformSelectClose(documentRef);
        }, true);
      } catch (_) {
        // 宿主容器尚未就绪时忽略。
      }
    };
    attach();
  })();

  // 平台定制下拉打开后的贴紧校正：平台按可用空间预留高度可能导致
  // 向上展开时面板底部悬空（数据源项少时尤其明显），统一校正为
  // 向下贴选择框底部、向上贴选择框顶部。
  root.addEventListener("click", (event) => {
    const shellEl = event.target?.closest?.(".custom-select-shell");
    if (!shellEl) return;
    if (!(shellEl.classList.contains("rsp-sc-ds-select") || shellEl.classList.contains("rsp-sc-cond-op"))) return;
    const view = documentRef?.defaultView;
    const run = () => {
      const select = shellEl.querySelector("select.custom-select-native");
      if (!select) return;
      const dropdowns = documentRef.querySelectorAll(".custom-select-dropdown");
      let dropdown = null;
      for (let i = 0; i < dropdowns.length; i += 1) {
        if (!dropdowns[i].hidden) { dropdown = dropdowns[i]; break; }
      }
      if (!dropdown) return;
      const s = shellEl.getBoundingClientRect();
      const d = dropdown.getBoundingClientRect();
      if (!s.width || !d.width) return;
      const gap = 8;
      const height = Math.min(320, Math.round(d.height));
      if (d.bottom <= s.top) {
        // 向上展开：底部贴选择框顶部
        dropdown.style.top = String(Math.round(Math.max(16, s.top - gap - height))) + "px";
        dropdown.style.maxHeight = height + "px";
      } else {
        // 向下展开：顶部贴选择框底部
        dropdown.style.top = String(Math.round(s.bottom + gap)) + "px";
      }
    };
    if (view?.requestAnimationFrame) view.requestAnimationFrame(run);
    else setTimeout(run, 16);
  });

  // ===== 数据源（每张表独立下拉） =====

  function fillDatasourceSelect(select, selectedId, selectedName = "", selectedType = "") {
    const items = [...state.loadedDatasources];
    if (selectedId && !items.some((item) => item.id === selectedId)) {
      items.push({
        id: selectedId,
        name: selectedName || selectedId,
        db_type: selectedType || "",
      });
    }
    select.replaceChildren(
      element(documentRef, "option", { value: "", text: "请选择数据源" }),
      ...items.map((item) => element(documentRef, "option", {
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
        if (table.dsSelect) {
          fillDatasourceSelect(
            table.dsSelect,
            table.datasourceId,
            table.datasourceName,
            table.datasourceType,
          );
        }
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
    if (table.updateCardTitle) table.updateCardTitle();
  }

  function updateCardTitles() {
    state.tables.forEach((table) => {
      if (table.updateCardTitle) table.updateCardTitle();
    });
  }

  // ===== 可搜索输入 + 候选面板（表/字段/条件共用） =====

  function makeCombo({ placeholder, pageSize, fetchPage, onPick }) {
    const input = element(documentRef, "input", {
      type: "search",
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
    let scrollRaf = 0;
    let requestId = 0;
    let loading = false;

    // 面板 fixed 定位（不被弹窗滚动容器/底部按钮裁切，层级最高）。
    // 展开方向在打开时锚定一次：下方空间不足且上方够时向上展开；
    // 弹窗滚动时 rAF 节流跟随输入框重定位，方向保持不变，避免漂移与跳动。
    let openUp = null; // null=未锚定 | true=向上 | false=向下

    function positionPanel() {
      if (typeof input.getBoundingClientRect !== "function") return;
      const rect = input.getBoundingClientRect();
      if (!rect || typeof rect.top !== "number") return;
      const viewportHeight = documentRef.defaultView?.innerHeight || 800;
      const gap = 6;
      const panelHeight = Math.min(260, panel.scrollHeight || 260);
      if (openUp === null) {
        // 仅当上方空间能完整容纳面板时才向上展开（底部贴输入框顶部）；
        // 否则保持向下展开并限制在视口内，避免面板漂移到上方覆盖表单区域。
        const spaceBelow = viewportHeight - rect.bottom - gap;
        const spaceAbove = rect.top - gap;
        openUp = spaceBelow < panelHeight && spaceAbove >= panelHeight;
      }
      panel.style.left = String(Math.max(8, Math.round(rect.left))) + "px";
      panel.style.width = String(Math.round(rect.width)) + "px";
      if (openUp) {
        panel.style.top = String(Math.round(rect.top - gap - panelHeight)) + "px";
      } else {
        const top = rect.bottom + gap;
        const maxTop = viewportHeight - panelHeight - 8;
        panel.style.top = String(Math.round(Math.min(top, Math.max(8, maxTop)))) + "px";
      }
    }

    function open() {
      attachScrollClose();
      openUp = null;
      positionPanel();
      panel.hidden = false;
      load(1);
    }

    function close() {
      panel.hidden = true;
    }

    async function load(requestedPage = 1) {
      if (loading) return; // 防连点：一次只允许一个在途请求
      loading = true;
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
      } finally {
        loading = false;
        // 内容高度可能变化（加载完成/错误态）：重新锚定，确保向上展开时
        // 面板底部始终贴输入框顶部，向下展开时顶部贴输入框底部。
        if (!panel.hidden) positionPanel();
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

    function scheduleSearch() {
      clearTimeout(timer);
      timer = setTimeout(() => {
        attachScrollClose();
        positionPanel();
        load(1);
      }, SEARCH_DEBOUNCE_MS);
    }

    function attachScrollClose() {
      if (scrollListenerAttached) return;
      scrollListenerAttached = true;
      const host = getHost?.();
      if (!host) return;
      try {
        host.addEventListener?.("scroll", closeOnHostScroll, true);
        // 点击弹窗任意非本下拉区域（基本信息/处理脚本/空白处等）时收起候选面板。
        host.addEventListener?.("click", onOverlayClick);
      } catch (_) {
        // 宿主容器尚未就绪时忽略；滚动跟随与失焦关闭为渐进增强。
      }
    }

    function onOverlayClick(event) {
      if (panel.hidden) return;
      if (event?.target === shell || shell.contains(event.target)) return;
      close();
    }

    // 弹窗内容区（.rsp-modal-body）滚动后，锚点输入框可能滚到表头之上或底部操作栏之后。
    // 此时面板是 fixed 定位，必须收起而不是继续跟随，否则会浮在表头之上、溢出弹窗边界。
    function anchorVisibleInScroller() {
      if (typeof input.getBoundingClientRect !== "function") return true;
      const rect = input.getBoundingClientRect();
      if (!rect || typeof rect.top !== "number") return true;
      const host = getHost?.();
      const scroller = host?.querySelector?.(".rsp-modal-body");
      if (!scroller || typeof scroller.getBoundingClientRect !== "function") return true;
      const box = scroller.getBoundingClientRect();
      if (!box || typeof box.top !== "number" || !(Number(box.height) > 0)) return true;
      // 完全滚出内容区可视范围（含被表头遮挡）时视为不可见。
      return rect.bottom > box.top && rect.top < box.bottom;
    }

    function closeOnHostScroll(event) {
      // 弹窗滚动时：锚点仍在可视区则跟随输入框重定位（方向锚定不翻转）；
      // 锚点滚出可视区（如滚到表头之后）则直接收起，避免面板溢出弹窗；
      // 平台定制下拉（数据源/条件类型等）直接关闭，避免漂移覆盖。
      if (event?.target && shell.contains(event.target)) return;
      if (scrollRaf) return;
      const raf = documentRef.defaultView?.requestAnimationFrame;
      const step = () => {
        scrollRaf = 0;
        if (!panel.hidden) {
          if (anchorVisibleInScroller()) positionPanel();
          else close();
        }
        schedulePlatformSelectClose(documentRef);
      };
      scrollRaf = raf ? raf(step) : setTimeout(step, 16);
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
    return {
      itemId: createItemId("field"),
      physical: "", chinese: "", before: "", after: "", comboInput: null, cnInput: null,
    };
  }

function emptyCondition() {
  return {
    itemId: createItemId("condition"),
    column: "",
    chinese: "",
    values: [],
    operator: "=",
    operatorMode: "AUTO",
    comboInput: null,
    operatorSelect: null,
    valueInput: null,
  };
}

  function emptyTable() {
    return {
      itemId: createItemId("table"),
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
    updateCardTitles();
  }

  function updateTableRemoveButtons() {
    // 单张处理表时不显示删除按钮（系统始终至少保留一张表）
    const visible = !disabled && state.tables.length > 1;
    state.tables.forEach((table) => {
      if (!table.removeButton) return;
      table.removeButton.hidden = !visible;
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
      updateCardTitles();
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
    // 删除按钮仅在行数>1时可用，直接移除即可
    const index = table.conditions.indexOf(condition);
    if (index >= 0) table.conditions.splice(index, 1);
    renderConditions(table);
  }

  function removeField(table, field) {
    // 删除按钮仅在行数>1时可用，直接移除即可
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
    fillDatasourceSelect(
      dsSelect,
      table.datasourceId,
      table.datasourceName,
      table.datasourceType,
    );
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
            if (table.updateCardTitle) table.updateCardTitle();
          })
          .catch((error) => {
            notify(error?.message || "字段信息获取失败，请稍后重试", "error");
          });
      },
    });
    table.comboInput = combo.input;
    combo.input.value = table.physical;
    const cnInput = element(documentRef, "input", {
      type: "search",
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
      className: "rsp-sc-icon-btn rsp-sc-remove-table",
      title: "删除处理表",
      "aria-label": "删除处理表",
      disabled: disabled || null,
      onClick: () => removeTable(table),
    });
    removeButton.innerHTML = ICON_TRASH;
    table.removeButton = removeButton;

    // ===== 处理表标题栏（表级操作与边界标识） =====
    const titleIndex = element(documentRef, "span", {
      className: "rsp-sc-card-title-index",
      text: "处理表",
    });
    const titleMeta = element(documentRef, "span", { className: "rsp-sc-card-title-meta" });
    function updateCardTitle() {
      const index = state.tables.indexOf(table) + 1;
      titleIndex.textContent = `处理表 ${index}`;
      const meta = table.datasourceName && table.physical
        ? `${table.datasourceName} / ${table.physical}`
        : "";
      titleMeta.textContent = meta;
      titleMeta.hidden = !meta;
    }
    table.updateCardTitle = updateCardTitle;
    // 表级删除按钮位于“处理表 N”标题之前，单表时隐藏（不占用布局）
    const titleBar = element(documentRef, "div", { className: "rsp-sc-card-title" }, [
      disabled ? null : removeButton,
      titleIndex,
      titleMeta,
    ]);

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
      ]),
      element(documentRef, "div", { className: "rsp-sc-row rsp-sc-cond-head" }, [
        element(documentRef, "span", { text: "条件字段" }),
        element(documentRef, "span", { text: "条件类型" }),
        element(documentRef, "span", { text: "条件值" }),
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
        element(documentRef, "span"),
      ]),
      element(documentRef, "div", { className: "rsp-sc-row rsp-sc-tbl-row" }, [
        dsSelect,
        combo.shell,
        cnInput,
        element(documentRef, "span"),
      ]),
      scopeZone,
      element(documentRef, "div", { className: "rsp-sc-fields-area" }, [
        element(documentRef, "div", { className: "rsp-sc-section-head rsp-sc-fields-head" }, [
          element(documentRef, "div", { className: "rsp-sc-section-head-main" }, [
            element(documentRef, "span", { className: "rsp-tf-fields-title", text: "修改字段" }),
          ]),
        ]),
        element(documentRef, "div", { className: "rsp-sc-row rsp-sc-field-head" }, [
          element(documentRef, "span", { text: "英文字段名" }),
          element(documentRef, "span", { text: "中文字段名" }),
          element(documentRef, "span", { text: "修改前" }),
          element(documentRef, "span", { text: "修改后" }),
        ]),
        fieldsBox,
      ]),
    ]);

    const card = element(documentRef, "div", { className: "rsp-tf-card rsp-sc-card" }, [titleBar, cardBody]);
    table.card = card;
    renderConditions(table);
    renderFields(table);
    renderReportPeriodRow();
    updateCardTitle();
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

  function tableColumnDisplayLabel(table, columnName, fallbackChinese = "") {
    const field = (table.fieldMeta || []).find(
      (item) => String(item?.column_name || "") === columnName,
    );
    return columnDisplayLabel({
      column_name: columnName,
      column_comment: field?.column_comment || fallbackChinese,
    });
  }

  function renderConditions(table) {
    if (!table.conditionRowsBox) return;
    const lastIndex = table.conditions.length - 1;
    table.conditionRowsBox.replaceChildren(
      ...table.conditions.map((condition, index) => renderConditionRow(table, condition, index === lastIndex)),
    );
  }

  function renderConditionRow(table, condition, isLast) {
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
        condition.chinese = String(item.column_comment || item.secondary || "");
        combo.input.value = columnDisplayLabel(item);
        if (condition.valueInput) condition.valueInput.focus?.();
      },
    });
    condition.comboInput = combo.input;
    combo.input.value = tableColumnDisplayLabel(table, condition.column, condition.chinese);

    // 条件类型：用户主动选择后进入 MANUAL，不再被单值/多值智能匹配覆盖。
    const operatorSelect = element(documentRef, "select", {
      className: "rsp-compact-select rsp-sc-cond-op",
      "aria-label": "条件类型",
      disabled: disabled || null,
    });
    CONDITION_OPERATORS.forEach((item) => {
      operatorSelect.append(element(documentRef, "option", { value: item.value, text: item.label }));
    });
    condition.operatorSelect = operatorSelect;

    const valueInput = element(documentRef, "input", {
      type: "search",
      className: "rsp-sc-cn-input",
      value: scopeText(condition.values),
      maxlength: String(MAX_SCOPE_CHARS),
      placeholder: "请输入条件值",
      "aria-label": "条件值",
      disabled: disabled || null,
    });
    condition.valueInput = valueInput;
    function syncOperatorState() {
      operatorSelect.value = condition.operator;
      const noValue = CONDITION_OPERATOR_NO_VALUE.has(condition.operator);
      valueInput.disabled = disabled || noValue;
      valueInput.placeholder = noValue ? "无需填写" : "请输入条件值";
      if (noValue) {
        condition.values = [];
        if (valueInput.value !== "") valueInput.value = "";
      }
    }
    // 程序化切换（智能匹配）也会派发 change 以刷新平台定制下拉的显示文本；
    // 用标志位区分，避免把程序切换误判为用户主动选择而进入 MANUAL。
    let suppressOperatorChange = false;
    operatorSelect.addEventListener("change", () => {
      if (suppressOperatorChange) {
        suppressOperatorChange = false;
        return;
      }
      condition.operatorMode = "MANUAL"; // 用户主动选择即锁定，后续不自动覆盖
      condition.operator = operatorSelect.value;
      syncOperatorState();
    });
    function applyOperatorProgrammatically(nextOperator) {
      condition.operator = nextOperator;
      suppressOperatorChange = true;
      operatorSelect.value = nextOperator;
      operatorSelect.dispatchEvent(new Event("change", { bubbles: true }));
    }
    valueInput.addEventListener("input", () => {
      // 实时智能切换：编辑条件值时即时解析并按有效值数量切换条件类型
      // （1 个值 → 等于，多个值 → 属于多个值（IN）），不受此前手动选择锁定影响；
      // 用户手动修改条件类型时仍允许覆盖（下一次输入重新智能切换）。
      condition.values = parseScopeText(valueInput.value);
      applyOperatorProgrammatically(autoOperator(condition.values));
    });
    syncOperatorState();

    const canRemove = !disabled && table.conditions.length > 1;
    return element(documentRef, "div", { className: "rsp-sc-row rsp-sc-cond-row" }, [
      combo.shell,
      operatorSelect,
      valueInput,
      disabled
        ? element(documentRef, "span")
        : rowActions({
            isLast,
            canRemove,
            onRemove: () => removeCondition(table, condition),
            onAdd: () => addConditionRow(table),
            addLabel: "添加条件",
            removeLabel: "删除条件",
          }),
    ]);
  }

  function renderFields(table) {
    if (!table.fieldsBox) return;
    const lastIndex = table.fields.length - 1;
    table.fieldsBox.replaceChildren(
      ...table.fields.map((field, index) => renderFieldRow(table, field, index === lastIndex)),
    );
  }

  function renderFieldRow(table, field, isLast) {
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
      type: "search",
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
      type: "search",
      className: "rsp-sc-value-input",
      value: field.before,
      maxlength: String(MAX_VALUE_LEN),
      placeholder: "修改前",
      "aria-label": "修改前",
      disabled: disabled || null,
    });
    const afterInput = element(documentRef, "input", {
      type: "search",
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

    const canRemove = !disabled && table.fields.length > 1;
    return element(documentRef, "div", { className: "rsp-sc-row rsp-sc-field-row" }, [
      combo.shell,
      cnInput,
      element(documentRef, "div", { className: "rsp-sc-value-cell" }, [beforeInput]),
      element(documentRef, "div", { className: "rsp-sc-value-cell" }, [afterInput]),
      disabled
        ? element(documentRef, "span")
        : rowActions({
            isLast,
            canRemove,
            onRemove: () => removeField(table, field),
            onAdd: () => addFieldRow(table),
            addLabel: "添加字段",
            removeLabel: "删除字段",
          }),
    ]);
  }

  // ===== 行级操作按钮：左对齐 [-]（始终），最后一行追加 [+]，无假占位 =====
  function rowActions({ isLast, canRemove, onRemove, onAdd, addLabel, removeLabel }) {
    const wrap = element(documentRef, "div", { className: "rsp-sc-row-actions" });
    // 删除（减号）：每一行都作为固定操作锚点，位于最左
    const removeBtn = element(documentRef, "button", {
      type: "button",
      className: "rsp-sc-icon-btn rsp-sc-icon-minus",
      title: removeLabel,
      "aria-label": removeLabel,
      disabled: !canRemove || null,
      onClick: onRemove,
    });
    removeBtn.innerHTML = ICON_MINUS;
    wrap.append(removeBtn);
    // 新增（加号）：仅最后一行，紧跟在减号右侧
    if (isLast && onAdd) {
      const addBtn = element(documentRef, "button", {
        type: "button",
        className: "rsp-sc-icon-btn rsp-sc-icon-add",
        title: addLabel,
        "aria-label": addLabel,
        onClick: onAdd,
      });
      addBtn.innerHTML = ICON_PLUS;
      wrap.append(addBtn);
    }
    return wrap;
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
        item_id: table.itemId,
        schema: table.schema,
        table_name: table.physical,
        chinese_table_name: table.chinese,
        table_name_source: "MANUAL",
        datasource_id: table.datasourceId,
        datasource_type: table.datasourceType,
        datasource_name: table.datasourceName,
        // 脚本预览需要在条件字段刚选中、条件值尚未输入时也看到 WHERE；
        // 保存前 validate() 仍按原规则拦截缺少必填值的条件，不放宽保存校验。
        conditions: table.conditions
          .filter((condition) => condition.column)
          .map((condition) => ({
            item_id: condition.itemId,
            column_name: condition.column,
            chinese_column_name: condition.chinese,
            operator: condition.operator,
            operator_mode: condition.operatorMode,
            values: condition.values,
          })),
        limit_report_period: table.limitReportPeriod,
        report_period_field: table.limitReportPeriod ? table.reportPeriodField : "",
        report_period_field_source: table.limitReportPeriod ? table.reportPeriodFieldSource : "",
        fields: table.fields
          .filter((field) => field.physical)
          .map((field) => ({
            item_id: field.itemId,
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
        (condition) => condition.column
          || (condition.valueInput && String(condition.valueInput.value || "").trim())
          || CONDITION_OPERATOR_NO_VALUE.has(condition.operator),
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
        if (CONDITION_OPERATORS_REQUIRING_VALUE.has(condition.operator) && !condition.values.length) {
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
      table.itemId = String(rawTable?.item_id || table.itemId);
      table.datasourceId = String(rawTable?.datasource_id || initial.datasource_id || "");
      table.datasourceType = String(rawTable?.datasource_type || initial.datasource_type || "");
      table.datasourceName = String(rawTable?.datasource_name || datasourceNameSnapshot || "");
      table.schema = String(rawTable?.schema || "");
      table.physical = String(rawTable?.table_name || "");
      table.chinese = String(rawTable?.chinese_table_name || "");
      table.limitReportPeriod = rawTable?.limit_report_period !== false;
      table.reportPeriodField = String(rawTable?.report_period_field || "");
      table.reportPeriodFieldSource = String(rawTable?.report_period_field_source || "");
      table.conditions = (Array.isArray(rawTable?.conditions) ? rawTable.conditions : []).map((item) => {
        const condition = emptyCondition();
        condition.itemId = String(item?.item_id || condition.itemId);
        condition.column = String(item?.column_name || "");
        condition.chinese = String(item?.chinese_column_name || "");
        condition.operator = String(item?.operator || "=").trim().toUpperCase() || "=";
        condition.operatorMode = String(item?.operator_mode || "AUTO").trim().toUpperCase() === "MANUAL" ? "MANUAL" : "AUTO";
        condition.values = Array.isArray(item?.values)
          ? item.values.map((value) => String(value || "").trim()).filter(Boolean)
          : [];
        return condition;
      });
      if (!table.conditions.length) table.conditions.push(emptyCondition());
      table.fields = (Array.isArray(rawTable?.fields) ? rawTable.fields : []).map((field) => {
        const item = emptyField();
        item.itemId = String(field?.item_id || item.itemId);
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
