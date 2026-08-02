import { element, labeledField, option } from "./dom.js";

export function createFilters(documentRef, { catalog, filters, onApply, onReset }) {
  const status = element(documentRef, "select", { "aria-label": "处理状态" }, [option(documentRef, "", "全部状态")]);
  (catalog?.statuses || []).forEach((item) => status.append(option(documentRef, item.code, item.label)));
  status.value = filters.status;

  const keyword = element(documentRef, "input", {
    type: "search",
    value: filters.keyword,
    placeholder: "报表名称、处理摘要或记录编号",
    "aria-label": "涉及报表或摘要关键词",
    maxlength: "100",
  });

  const handler = element(documentRef, "select", { "aria-label": "处理人" }, [option(documentRef, "", "全部处理人")]);
  const users = catalog?.users || [];
  users.map((user) => handler.append(option(documentRef, user.id, user.display_name || user.username)));
  handler.value = filters.handler_user_id;

  const apply = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-primary",
    text: "查询",
    onClick: () => onApply({ status: status.value, keyword: keyword.value.trim(), handler_user_id: handler.value }),
  });
  const reset = element(documentRef, "button", {
    type: "button",
    className: "rsp-button rsp-button-secondary",
    text: "重置",
    onClick: onReset,
  });
  keyword.addEventListener("keydown", (event) => {
    if (event.key === "Enter") apply.click();
  });

  return element(documentRef, "section", { className: "rsp-filters", "aria-label": "筛选条件" }, [
    labeledField(documentRef, "处理状态", status),
    labeledField(documentRef, "涉及报表", keyword),
    labeledField(documentRef, "处理人", handler),
    element(documentRef, "div", { className: "rsp-filter-actions" }, [reset, apply]),
  ]);
}

