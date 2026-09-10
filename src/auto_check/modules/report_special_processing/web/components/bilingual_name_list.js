/* 双语名称多项录入组件：每行“中文名｜英文名”，多项用全角分号序列化。
 * root 上挂 value（getter/setter），getter 返回规范串，兼容既有 draftPayload/validateForm 读取。 */

import { element } from "./dom.js";

export const BILINGUAL_PART_SEPARATOR = "｜";
export const BILINGUAL_ITEM_SEPARATOR = "；";
export const BILINGUAL_GROUP_SEPARATOR = "；；";
export const BILINGUAL_MAX_ITEMS = 5;

export function parseBilingualItems(value) {
  const text = String(value || "").trim();
  if (!text) return [];
  const items = [];
  for (const chunk of text.split(BILINGUAL_ITEM_SEPARATOR)) {
    const piece = chunk.trim();
    if (!piece) return null;
    const parts = piece.split(BILINGUAL_PART_SEPARATOR);
    if (parts.length !== 2) return null;
    const zh = parts[0].trim();
    const en = parts[1].trim();
    if (!zh || !en) return null;
    items.push({ zh, en });
  }
  return items;
}

export function serializeBilingualItems(items) {
  return items
    .filter((item) => String(item.zh || "").trim() || String(item.en || "").trim())
    .map((item) => `${String(item.zh || "").trim()}${BILINGUAL_PART_SEPARATOR}${String(item.en || "").trim()}`)
    .join(BILINGUAL_ITEM_SEPARATOR);
}

/* 解析分组字段串：组间用“；；”分隔，第 N 组对应第 N 张处理表。
 * 返回组数组（每组为 {zh,en} 数组，可为空组）；无分隔符的规范串按单组返回；
 * 非法/历史值返回 null，由调用方按旧值兼容处理。 */
export function parseBilingualGroups(value) {
  const text = String(value || "").trim();
  if (!text) return [];
  if (!text.includes(BILINGUAL_GROUP_SEPARATOR)) {
    const items = parseBilingualItems(text);
    return items ? [items] : null;
  }
  const groups = [];
  for (const chunk of text.split(BILINGUAL_GROUP_SEPARATOR)) {
    const piece = chunk.trim();
    if (!piece) {
      groups.push([]);
      continue;
    }
    const items = parseBilingualItems(piece);
    if (!items) return null;
    groups.push(items);
  }
  return groups;
}

export function serializeBilingualGroups(groups) {
  return groups.map((items) => serializeBilingualItems(items)).join(BILINGUAL_GROUP_SEPARATOR);
}

export function createBilingualNameList(documentRef, options = {}) {
  const {
    ariaLabel = "",
    zhPlaceholder = "中文名",
    enPlaceholder = "英文名",
    addLabel = "添加",
    maxItems = BILINGUAL_MAX_ITEMS,
    value = "",
    disabled = false,
  } = options;

  const rows = [];
  const rowsBox = element(documentRef, "div", { className: "rsp-bilingual-rows" });
  const addButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-bilingual-add",
    text: `+ ${addLabel}`,
    disabled: disabled || null,
  });
  const legacyHint = element(documentRef, "div", { className: "rsp-bilingual-helper", hidden: true });
  const root = element(documentRef, "div", { className: "rsp-bilingual-list", "aria-label": ariaLabel }, [
    rowsBox,
    element(documentRef, "div", { className: "rsp-bilingual-foot" }, [legacyHint]),
  ]);

  let legacyValue = "";
  let legacyDirty = false;

  function updateAddButton() {
    addButton.disabled = disabled || rows.length >= maxItems;
    addButton.textContent = rows.length >= maxItems ? `最多 ${maxItems} 项` : `+ ${addLabel}`;
  }

  function updateRowActions() {
    rows.forEach((row) => {
      if (row.removeButton) row.removeButton.hidden = rows.length <= 1;
    });
    if (disabled || !rows.length) return;
    addButton.remove();
    const lastRow = rows[rows.length - 1];
    lastRow.actions.append(addButton);
  }

  function resetLegacy() {
    legacyValue = "";
    legacyDirty = false;
    legacyHint.hidden = true;
    legacyHint.textContent = "";
  }

  function markLegacyDirty() {
    if (!legacyValue || legacyDirty) return;
    legacyDirty = true;
    legacyHint.hidden = true;
    legacyHint.textContent = "";
  }

  function removeRow(row) {
    if (rows.length <= 1) return;
    markLegacyDirty();
    const index = rows.indexOf(row);
    if (index >= 0) rows.splice(index, 1);
    row.root.remove();
    updateAddButton();
    updateRowActions();
  }

  function addRow(zh = "", en = "") {
    if (rows.length >= maxItems) return null;
    const zhInput = element(documentRef, "input", {
      className: "rsp-bilingual-zh",
      value: zh,
      maxlength: "100",
      placeholder: zhPlaceholder,
      "aria-label": `${ariaLabel}中文`,
      disabled: disabled || null,
    });
    const enInput = element(documentRef, "input", {
      className: "rsp-bilingual-en",
      value: en,
      maxlength: "100",
      placeholder: enPlaceholder,
      "aria-label": `${ariaLabel}英文`,
      disabled: disabled || null,
    });
    const removeButton = element(documentRef, "button", {
      type: "button",
      className: "rsp-bilingual-remove",
      text: "删除",
      disabled: disabled || null,
      onClick: () => removeRow(row),
    });
    const actions = disabled ? null : element(documentRef, "div", { className: "rsp-bilingual-actions" }, [removeButton]);
    const row = { zh: zhInput, en: enInput, removeButton, actions, root: null };
    row.root = element(documentRef, "div", { className: "rsp-bilingual-row" }, [
      zhInput,
      element(documentRef, "span", { className: "rsp-bilingual-sep", text: BILINGUAL_PART_SEPARATOR, "aria-hidden": "true" }),
      enInput,
      actions,
    ]);
    rows.push(row);
    rowsBox.append(row.root);
    zhInput.addEventListener("input", markLegacyDirty);
    enInput.addEventListener("input", markLegacyDirty);
    updateAddButton();
    updateRowActions();
    return row;
  }

  function showLegacyHelper() {
    if (disabled) return;
    legacyHint.hidden = false;
    legacyHint.textContent = "请补充英文名称后保存；未修改时将保留原有历史值。";
  }

  function renderValue(rawValue) {
    rows.forEach((item) => item.root.remove());
    rows.length = 0;
    resetLegacy();
    const text = String(rawValue || "").trim();
    if (!text) {
      addRow();
      return;
    }
    const items = parseBilingualItems(text);
    if (items && items.length) {
      items.forEach((item) => addRow(item.zh, item.en));
      updateAddButton();
      return;
    }
    // 旧格式以普通输入行展示；未编辑时仍提交原值，避免历史记录被无意改写。
    legacyValue = text;
    addRow(text, "");
    showLegacyHelper();
  }

  addButton.addEventListener("click", () => {
    markLegacyDirty();
    addRow();
  });

  Object.defineProperty(root, "value", {
    configurable: true,
    enumerable: false,
    get() {
      if (legacyValue && !legacyDirty) return legacyValue;
      return serializeBilingualItems(rows.map((row) => ({ zh: row.zh.value, en: row.en.value })));
    },
    set(next) {
      renderValue(next);
    },
  });

  renderValue(value);
  return root;
}
