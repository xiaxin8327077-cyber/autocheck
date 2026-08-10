import { element, labeledField, option } from "./dom.js";

export function createFilters(documentRef, { catalog, filters, onApply, onReset, onExport }) {
  const status = element(documentRef, "select", { "aria-label": "处理状态" }, [option(documentRef, "", "全部状态")]);
  (catalog?.statuses || []).forEach((item) => status.append(option(documentRef, item.code, item.label)));
  status.value = filters.status;

  const keyword = element(documentRef, "input", {
    type: "search",
    value: filters.keyword,
    placeholder: "字段名、处理摘要或记录编号",
    "aria-label": "关键词",
    maxlength: "100",
  });

  const handler = element(documentRef, "select", { "aria-label": "处理人" }, [option(documentRef, "", "全部处理人")]);
  const users = catalog?.users || [];
  users.map((user) => handler.append(option(documentRef, user.id, user.display_name || user.username)));
  handler.value = filters.handler_user_id;

  const currentFilters = () => ({
    status: status.value,
    keyword: keyword.value.trim(),
    handler_user_id: handler.value,
  });
  const apply = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-primary",
    text: "查询",
    onClick: () => onApply(currentFilters()),
  });
  const reset = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-secondary",
    text: "重置",
    onClick: onReset,
  });
  const exportButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-primary",
    "aria-label": "导出",
    onClick: () => onExport?.(currentFilters()),
  }, [
    element(documentRef, "span", { className: "rsp-btn-icon", "aria-hidden": "true", text: "\u21E9" }),
    element(documentRef, "span", { "data-export-label": "", text: "导出" }),
  ]);
  keyword.addEventListener("keydown", (event) => {
    if (event.key === "Enter") apply.click();
  });

  return element(documentRef, "section", { className: "rsp-filters", "aria-label": "筛选条件" }, [
    labeledField(documentRef, "处理状态", status),
    labeledField(documentRef, "关键词", keyword),
    labeledField(documentRef, "处理人", handler),
    element(documentRef, "div", { className: "rsp-filter-actions" }, [reset, apply, exportButton]),
  ]);
}
