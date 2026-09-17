/* 数据源元数据选择弹窗（选择处理表 / 选择字段共用）。
 *
 * 表与字段均来自后端元数据接口（后端搜索 + 后端分页），不支持手工输入物理名。
 * selectMode=single：单击行选中，确定回填一条（处理表）。
 * selectMode=multi：勾选多选（字段）；已添加项置灰不可选。 */

import { element } from "./dom.js";

const PAGE_SIZE_SINGLE = 20;
const PAGE_SIZE_MULTI = 50;

export function openMetadataPicker(documentRef, options) {
  const {
    host,
    title,
    subtitle = "",
    searchPlaceholder = "输入中文名称或英文名称",
    columns,
    fetchPage,
    selectMode = "single",
    isAdded = () => false,
    itemKey = (item) => String(item.table_name || item.column_name || ""),
    onConfirm,
    onCancel,
    notify,
  } = options;

  const selected = new Map();
  let activeRow = null;
  let page = 1;
  let totalPages = 1;
  let keyword = "";
  let loading = false;
  let destroyed = false;

  const searchInput = element(documentRef, "input", {
    type: "search",
    className: "rsp-picker-search",
    placeholder: searchPlaceholder,
    "aria-label": `${title}搜索`,
  });
  const listBox = element(documentRef, "div", { className: "rsp-picker-list", role: "listbox" });
  const statusText = element(documentRef, "div", { className: "rsp-picker-status", text: "加载中…", hidden: true });
  const pageInfo = element(documentRef, "span", { className: "rsp-picker-page-info", text: "第 1 / 1 页" });
  const prevButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-secondary rsp-picker-page",
    text: "上一页",
    disabled: true,
  });
  const nextButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-secondary rsp-picker-page",
    text: "下一页",
    disabled: true,
  });
  const confirmButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-primary",
    text: "确定",
    disabled: true,
  });
  const cancelButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-secondary",
    text: "取消",
  });

  function close() {
    documentRef.removeEventListener?.("keydown", onKeydown, true);
    shell.remove?.();
    destroyed = true;
  }
  function onKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
      onCancel?.();
    }
  }

  prevButton.addEventListener("click", () => {
    if (page > 1) load(page - 1);
  });
  nextButton.addEventListener("click", () => {
    if (page < totalPages) load(page + 1);
  });
  cancelButton.addEventListener("click", () => {
    close();
    onCancel?.();
  });
  confirmButton.addEventListener("click", () => {
    const items = selectMode === "single"
      ? (activeRow ? [activeRow.item] : [])
      : Array.from(selected.values());
    if (!items.length) return;
    close();
    onConfirm?.(items);
  });
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      load(1);
    }
  });
  const searchButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-secondary",
    text: "搜索",
    onClick: () => load(1),
  });

  function updatePager() {
    pageInfo.textContent = `第 ${page} / ${totalPages} 页`;
    prevButton.disabled = page <= 1;
    nextButton.disabled = page >= totalPages;
  }

  function updateConfirmState() {
    confirmButton.disabled = selectMode === "single" ? !activeRow : selected.size === 0;
  }

  function rowCell(item, column) {
    const value = String(item[column.key] || "");
    if (column.key === columns[0]?.key && !value) {
      return element(documentRef, "span", { className: "rsp-picker-cell rsp-picker-cell-empty", text: "--" });
    }
    return element(documentRef, "span", {
      className: `rsp-picker-cell${column.mono ? " rsp-picker-cell-mono" : ""}`,
      text: value,
      title: value,
    });
  }

  function renderRows(items) {
    const rows = [];
    if (columns.length) {
      rows.push(element(documentRef, "div", {
        className: `rsp-picker-row rsp-picker-row-head${selectMode === "multi" ? " rsp-picker-row-multi" : ""}`,
      }, [
        selectMode === "multi" ? element(documentRef, "span", { className: "rsp-picker-cell", text: "" }) : null,
        ...columns.map((column) => element(documentRef, "span", { className: "rsp-picker-cell", text: column.label })),
      ]));
    }
    items.forEach((item) => {
      const key = itemKey(item);
      const added = isAdded(item);
      const isChecked = selected.has(key);
      const children = [];
      if (selectMode === "multi") {
        children.push(element(documentRef, "span", {
          className: `rsp-picker-check${isChecked ? " is-checked" : ""}`,
          text: isChecked ? "✓" : "",
          "aria-hidden": "true",
        }));
      }
      columns.forEach((column) => children.push(rowCell(item, column)));
      if (added) children.push(element(documentRef, "span", { className: "rsp-picker-added", text: "已添加" }));
      const row = element(documentRef, "div", {
        className: "rsp-picker-row"
          + (selectMode === "multi" ? " rsp-picker-row-multi" : "")
          + (added ? " is-added" : "")
          + (activeRow && activeRow.key === key ? " is-active" : "")
          + (isChecked ? " is-selected" : ""),
        role: "option",
        "aria-selected": isChecked || (activeRow && activeRow.key === key) ? "true" : "false",
        onClick: () => {
          if (added) {
            notify?.(`${key} 已添加，不能重复选择`, "warning");
            return;
          }
          if (selectMode === "single") {
            activeRow = { key, item };
            renderRows(lastItems);
            updateConfirmState();
            return;
          }
          if (selected.has(key)) selected.delete(key);
          else selected.set(key, item);
          renderRows(lastItems);
          updateConfirmState();
        },
      }, children);
      rows.push(row);
    });
    listBox.replaceChildren(...rows);
  }

  let lastItems = [];

  async function load(requestedPage) {
    if (loading || destroyed) return;
    loading = true;
    page = requestedPage;
    keyword = searchInput.value.trim();
    statusText.hidden = false;
    statusText.textContent = "加载中…";
    statusText.className = "rsp-picker-status";
    updatePager();
    try {
      const response = await fetchPage({
        keyword,
        page,
        page_size: selectMode === "single" ? PAGE_SIZE_SINGLE : PAGE_SIZE_MULTI,
      });
      const payload = response?.data || response || {};
      lastItems = Array.isArray(payload.items) ? payload.items : [];
      totalPages = Math.max(1, Number(payload.total_pages) || 1);
      statusText.hidden = lastItems.length > 0;
      statusText.textContent = payload.total === 0 || !lastItems.length
        ? (options.emptyText || "未找到匹配的数据")
        : "";
      renderRows(lastItems);
    } catch (error) {
      lastItems = [];
      totalPages = 1;
      listBox.replaceChildren();
      statusText.hidden = false;
      statusText.className = "rsp-picker-status is-error";
      statusText.textContent = error?.message || "读取失败，请稍后重试";
    } finally {
      loading = false;
      updatePager();
      updateConfirmState();
    }
  }

  const shell = element(documentRef, "div", {
    className: "rsp-picker-overlay",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": title,
  }, [
    element(documentRef, "div", { className: "rsp-picker" }, [
      element(documentRef, "header", { className: "rsp-picker-head" }, [
        element(documentRef, "h3", { text: title }),
        subtitle ? element(documentRef, "span", { className: "rsp-picker-subtitle", text: subtitle }) : null,
        element(documentRef, "button", {
          type: "button",
          className: "rsp-modal-close",
          text: "×",
          "aria-label": "关闭",
          onClick: () => { close(); onCancel?.(); },
        }),
      ]),
      element(documentRef, "div", { className: "rsp-picker-search-row" }, [searchInput, searchButton]),
      element(documentRef, "div", { className: "rsp-picker-body" }, [listBox, statusText]),
      element(documentRef, "footer", { className: "rsp-picker-foot" }, [
        element(documentRef, "div", { className: "rsp-picker-pager" }, [prevButton, pageInfo, nextButton]),
        element(documentRef, "div", { className: "rsp-picker-actions" }, [cancelButton, confirmButton]),
      ]),
    ]),
  ]);

  (host || documentRef.body).append(shell);
  documentRef.addEventListener?.("keydown", onKeydown, true);
  searchInput.focus?.();
  load(1);
  return { close };
}
