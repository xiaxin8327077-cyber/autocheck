/* 表-字段关联分组录入组件（特殊处理内容区域）。
 *
 * 序列化格式与既有 draftPayload 兼容，仍产出 table_name / field_name 两个字符串：
 * - 表名：规范串「中文｜英文；中文｜英文」，每项一张表；
 * - 字段名：按表分组，组间用双全角分号「；；」分隔，第 N 组对应第 N 张表，
 *   组内仍为「中文｜英文；…」，允许空组（该表暂无关联字段）。
 *
 * 历史（非规范/扁平）值按旧组件同款兼容策略：未修改时原样提交原值，
 * 一旦编辑则整体升级为分组格式。 */

import { element } from "./dom.js";
import {
  BILINGUAL_PART_SEPARATOR,
  BILINGUAL_MAX_ITEMS,
  parseBilingualItems,
  parseBilingualGroups,
  serializeBilingualItems,
  serializeBilingualGroups,
} from "./bilingual_name_list.js";

export const MAX_TABLE_GROUPS = BILINGUAL_MAX_ITEMS;
export const MAX_FIELDS_PER_TABLE = BILINGUAL_MAX_ITEMS;
// 字段数达到该阈值的表分组默认折叠，标题显示字段数量。
const COLLAPSE_FIELD_THRESHOLD = 4;

export function createTableFieldGroups(documentRef, options = {}) {
  const {
    ariaLabel = "处理表与关联字段",
    tableValue = "",
    fieldValue = "",
    disabled = false,
    confirm = null,
  } = options;

  const rawTable = String(tableValue || "").trim();
  const rawField = String(fieldValue || "").trim();
  let dirty = false;

  const tables = [];

  const cardsBox = element(documentRef, "div", { className: "rsp-tf-cards" });
  const addTableButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-bilingual-add rsp-tf-add-table",
    text: "+ 添加表",
    disabled: disabled || null,
  });
  const emptyHint = element(documentRef, "div", {
    className: "rsp-bilingual-helper rsp-tf-empty",
    text: "暂无处理表，点击「+ 添加表」新建。",
    hidden: true,
  });
  const root = element(documentRef, "div", { className: "rsp-tf-groups", "aria-label": ariaLabel }, [
    element(documentRef, "div", { className: "rsp-tf-head" }, [
      element(documentRef, "span", { className: "rsp-field-label rsp-tf-head-title", text: "处理表" }),
      disabled ? null : addTableButton,
    ]),
    // 固定列标题：始终可见，不依赖 placeholder 区分中英文列
    element(documentRef, "div", { className: "rsp-tf-cols-head", "aria-hidden": "true" }, [
      element(documentRef, "span", { className: "rsp-tf-col-label rsp-tf-col-zh", text: "中文表名" }),
      element(documentRef, "span", { className: "rsp-tf-col-label rsp-tf-col-en", text: "英文表名" }),
    ]),
    cardsBox,
    emptyHint,
  ]);

  function markDirty() {
    dirty = true;
    tables.forEach((table) => {
      if (table.legacyHint) {
        table.legacyHint.hidden = true;
      }
      table.fieldRows.forEach((row) => {
        if (row.legacyHint) row.legacyHint.hidden = true;
      });
    });
  }

  function updateTitles() {
    tables.forEach((table, index) => {
      const count = table.fieldRows.length;
      table.titleEl.textContent = `表${index + 1}（${count}个字段）`;
    });
    emptyHint.hidden = tables.length > 0;
    updateAddTableButton();
  }

  function updateAddTableButton() {
    if (disabled) return;
    addTableButton.disabled = tables.length >= MAX_TABLE_GROUPS;
    addTableButton.textContent = tables.length >= MAX_TABLE_GROUPS
      ? `最多 ${MAX_TABLE_GROUPS} 张表`
      : "+ 添加表";
  }

  function setCollapsed(table, collapsed) {
    table.collapsed = collapsed;
    table.body.hidden = collapsed;
    table.toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    table.toggle.textContent = collapsed ? "▸" : "▾";
  }

  function updateFieldRowActions(table) {
    table.fieldEmptyHint.hidden = table.fieldRows.length > 0;
    if (disabled) return;
    table.addFieldButton.disabled = table.fieldRows.length >= MAX_FIELDS_PER_TABLE;
    table.addFieldButton.textContent = table.fieldRows.length >= MAX_FIELDS_PER_TABLE
      ? `最多 ${MAX_FIELDS_PER_TABLE} 个字段`
      : "+ 添加字段";
    table.fieldRows.forEach((row) => {
      row.removeButton.hidden = false;
    });
    updateTitles();
  }

  function removeFieldRow(table, row) {
    markDirty();
    const index = table.fieldRows.indexOf(row);
    if (index >= 0) table.fieldRows.splice(index, 1);
    row.root.remove();
    updateFieldRowActions(table);
  }

  function addFieldRow(table, zh = "", en = "", { legacy = false } = {}) {
    if (table.fieldRows.length >= MAX_FIELDS_PER_TABLE) return null;
    const zhInput = element(documentRef, "input", {
      className: "rsp-bilingual-zh",
      value: zh,
      maxlength: "100",
      placeholder: "中文字段名",
      "aria-label": `表${tables.indexOf(table) + 1}字段中文`,
      disabled: disabled || null,
    });
    const enInput = element(documentRef, "input", {
      className: "rsp-bilingual-en",
      value: en,
      maxlength: "100",
      placeholder: "英文字段名",
      "aria-label": `表${tables.indexOf(table) + 1}字段英文`,
      disabled: disabled || null,
    });
    const removeButton = element(documentRef, "button", {
      type: "button",
      className: "rsp-bilingual-remove",
      text: "删除",
      disabled: disabled || null,
      onClick: () => removeFieldRow(table, row),
    });
    const row = { zhInput, enInput, removeButton, legacyHint: null, root: null };
    if (legacy && !disabled) {
      row.legacyHint = element(documentRef, "div", {
        className: "rsp-bilingual-helper",
        text: "历史字段名为旧格式，请补充规范格式后保存；未修改时将保留原有历史值。",
      });
    }
    row.root = element(documentRef, "div", { className: "rsp-bilingual-row rsp-tf-field-row" }, [
      zhInput,
      element(documentRef, "span", { className: "rsp-bilingual-sep", text: BILINGUAL_PART_SEPARATOR, "aria-hidden": "true" }),
      enInput,
      disabled ? null : removeButton,
    ]);
    table.fieldRows.push(row);
    table.fieldRowsBox.append(row.root);
    if (row.legacyHint) table.fieldRowsBox.append(row.legacyHint);
    zhInput.addEventListener("input", markDirty);
    enInput.addEventListener("input", markDirty);
    updateFieldRowActions(table);
    return row;
  }

  async function removeTable(table) {
    const fieldCount = table.fieldRows.length;
    if (fieldCount > 0 && typeof confirm === "function") {
      const ok = await confirm(
        "确认删除表",
        `删除该表将同时删除其下 ${fieldCount} 个关联字段，确认删除吗？`,
        { tone: "danger" },
      );
      if (!ok) return;
    }
    markDirty();
    const index = tables.indexOf(table);
    if (index >= 0) tables.splice(index, 1);
    table.root.remove();
    updateTitles();
  }

  function addTable({ zh = "", en = "", fields = [], legacyTable = false, legacyField = "" } = {}) {
    if (tables.length >= MAX_TABLE_GROUPS) return null;
    const toggle = element(documentRef, "button", {
      type: "button",
      className: "rsp-tf-toggle",
      text: "▾",
      "aria-expanded": "true",
      "aria-label": "折叠/展开表分组",
    });
    const titleEl = element(documentRef, "span", { className: "rsp-tf-card-title", text: "表1（0个字段）" });
    const zhInput = element(documentRef, "input", {
      className: "rsp-bilingual-zh",
      value: zh,
      maxlength: "100",
      placeholder: "中文表名",
      "aria-label": "处理表中文名",
      disabled: disabled || null,
    });
    const enInput = element(documentRef, "input", {
      className: "rsp-bilingual-en",
      value: en,
      maxlength: "100",
      placeholder: "英文表名",
      "aria-label": "处理表英文名",
      disabled: disabled || null,
    });
    const removeTableButton = element(documentRef, "button", {
      type: "button",
      className: "rsp-bilingual-remove rsp-tf-remove-table",
      text: "删除表",
      disabled: disabled || null,
      onClick: () => removeTable(table),
    });
    const addFieldButton = element(documentRef, "button", {
      type: "button",
      className: "rsp-bilingual-add",
      text: "+ 添加字段",
      disabled: disabled || null,
      onClick: () => {
        markDirty();
        addFieldRow(table);
      },
    });
    const fieldRowsBox = element(documentRef, "div", { className: "rsp-tf-field-rows" });
    const fieldEmptyHint = element(documentRef, "div", {
      className: "rsp-bilingual-helper rsp-tf-field-empty",
      text: "暂无关联字段。",
      hidden: true,
    });
    const body = element(documentRef, "div", { className: "rsp-tf-card-body" }, [
      element(documentRef, "div", { className: "rsp-tf-fields-head" }, [
        element(documentRef, "span", { className: "rsp-tf-fields-title", text: "关联字段" }),
        disabled ? null : addFieldButton,
      ]),
      // 字段区固定列标题，与字段行同栅格对齐
      element(documentRef, "div", { className: "rsp-tf-cols-head rsp-tf-field-cols-head", "aria-hidden": "true" }, [
        element(documentRef, "span", { className: "rsp-tf-col-label rsp-tf-col-zh", text: "中文字段名" }),
        element(documentRef, "span", { className: "rsp-tf-col-label rsp-tf-col-en", text: "英文字段名" }),
      ]),
      fieldRowsBox,
      fieldEmptyHint,
    ]);
    const head = element(documentRef, "div", { className: "rsp-tf-card-head" }, [
      toggle,
      titleEl,
      zhInput,
      element(documentRef, "span", { className: "rsp-bilingual-sep", text: BILINGUAL_PART_SEPARATOR, "aria-hidden": "true" }),
      enInput,
      disabled ? null : removeTableButton,
    ]);
    const cardChildren = [head];
    const table = {
      root: null,
      body,
      toggle,
      titleEl,
      zhInput,
      enInput,
      addFieldButton,
      fieldRowsBox,
      fieldEmptyHint,
      fieldRows: [],
      legacyHint: null,
      collapsed: false,
    };
    if (!disabled && (legacyTable || legacyField)) {
      table.legacyHint = element(documentRef, "div", {
        className: "rsp-bilingual-helper",
        text: "历史值为旧格式，请补充规范格式后保存；未修改时将保留原有历史值。",
      });
      cardChildren.push(table.legacyHint);
    }
    cardChildren.push(body);
    table.root = element(documentRef, "div", { className: "rsp-tf-card" }, cardChildren);
    toggle.addEventListener("click", () => setCollapsed(table, !table.collapsed));
    titleEl.addEventListener("click", () => setCollapsed(table, !table.collapsed));
    zhInput.addEventListener("input", markDirty);
    enInput.addEventListener("input", markDirty);
    tables.push(table);
    cardsBox.append(table.root);
    fields.forEach((item) => addFieldRow(table, item.zh, item.en));
    if (legacyField && !fields.length) {
      addFieldRow(table, legacyField, "", { legacy: true });
    }
    if (table.fieldRows.length >= COLLAPSE_FIELD_THRESHOLD) setCollapsed(table, true);
    updateFieldRowActions(table);
    updateTitles();
    return table;
  }

  function serializeTableValue() {
    return serializeBilingualItems(tables.map((table) => ({
      zh: table.zhInput.value,
      en: table.enInput.value,
    })));
  }

  function serializeFieldValue() {
    const groups = tables.map((table) => table.fieldRows.map((row) => ({
      zh: row.zhInput.value,
      en: row.enInput.value,
    })));
    const hasAnyField = groups.some((items) => serializeBilingualItems(items));
    if (!hasAnyField) return "";
    return serializeBilingualGroups(groups);
  }

  function renderInitial() {
    // 表：规范串逐项建卡；旧格式单卡承载原值；新建默认一张空表。
    const tableItems = parseBilingualItems(rawTable);
    let fieldGroups = rawField ? parseBilingualGroups(rawField) : [];
    if (fieldGroups === null) fieldGroups = [];
    let legacyFieldText = "";
    if (rawField && parseBilingualGroups(rawField) === null) legacyFieldText = rawField;

    if (tableItems && tableItems.length) {
      tableItems.forEach((item, index) => {
        addTable({
          zh: item.zh,
          en: item.en,
          fields: fieldGroups[index] || [],
          legacyField: index === 0 ? legacyFieldText : "",
        });
      });
      // 分组数多于表数（异常数据）时，多余字段并入最后一张表，避免丢数据。
      if (fieldGroups.length > tableItems.length && tables.length) {
        const last = tables[tables.length - 1];
        fieldGroups.slice(tableItems.length).forEach((items) => {
          items.forEach((item) => addFieldRow(last, item.zh, item.en));
        });
      }
      return;
    }
    // 表名为空或旧格式：单卡承载；历史字段/旧格式字段挂到该卡。
    const only = addTable({
      zh: tableItems ? "" : rawTable,
      en: "",
      fields: fieldGroups[0] || [],
      legacyTable: Boolean(rawTable) && !tableItems,
      legacyField: legacyFieldText,
    });
    // 纯新建：默认给首表准备一个空字段行，方便直接录入。
    if (!rawTable && !rawField && only && !only.fieldRows.length) addFieldRow(only);
  }

  addTableButton.addEventListener("click", () => {
    markDirty();
    const table = addTable({});
    table?.zhInput.focus();
  });

  Object.defineProperty(root, "tableValue", {
    configurable: true,
    enumerable: false,
    get() {
      if (!dirty) return rawTable;
      return serializeTableValue();
    },
    set(next) {
      // 冲突重载等场景整体重建由抽屉负责，这里仅保留接口对齐。
      void next;
    },
  });
  Object.defineProperty(root, "fieldValue", {
    configurable: true,
    enumerable: false,
    get() {
      if (!dirty) return rawField;
      return serializeFieldValue();
    },
    set(next) {
      void next;
    },
  });
  root.focusFirstInput = function focusFirstInput() {
    const first = tables[0];
    (first?.zhInput || addTableButton).focus?.();
  };

  renderInitial();
  return root;
}
