import { element } from "./dom.js";

const STATUS_LABELS = {
  draft: "草稿",
  pending: "待处理",
  processing: "处理中",
  completed: "已完成",
  voided: "已作废",
};

export function formatDisplayDateTime(value) {
  if (!value) return "";
  return String(value)
    .replace("T", " ")
    .replace(/\.\d+(?=(?:Z|[+-]\d{2}:?\d{2})?$)/, "")
    .replace(/(?:Z|[+-]\d{2}:?\d{2})$/, "")
    .trim();
}

function cell(documentRef, text, className = "") {
  return element(documentRef, "td", { className, text: text || "—", title: text || "" });
}

export function createRecordTable(documentRef, records, { selectedId, onOpen }) {
  const head = element(documentRef, "thead", {}, [
    element(documentRef, "tr", {}, ["关联报送", "涉及报表", "处理摘要", "特殊处理时间", "处理人", "状态", "操作"].map((label) => element(documentRef, "th", { text: label, scope: "col" }))),
  ]);
  const body = element(documentRef, "tbody");
  records.forEach((record) => {
    const handledAt = formatDisplayDateTime(record.special_handling_at);
    const trigger = element(documentRef, "button", {
      type: "button",
      className: "rsp-text-action",
      text: record.can_edit ? "编辑" : "查看",
      "aria-label": `${record.can_edit ? "编辑" : "查看"} ${record.record_no || "特殊处理记录"}`,
    });
    const row = element(documentRef, "tr", {
      className: String(record.id) === String(selectedId) ? "is-selected" : "",
      dataset: { recordId: String(record.id) },
      tabIndex: "0",
      "aria-label": `${record.record_no || "记录"}，${record.summary || "未填写摘要"}`,
      onClick: () => onOpen(record, row),
      onKeydown: (event) => {
        if (event.key === "Enter") onOpen(record, row);
      },
    }, [
      cell(documentRef, record.report_process_name_snapshot || record.report_process_name),
      cell(documentRef, (record.reports || []).join("、"), "rsp-report-names"),
      cell(documentRef, record.summary),
      cell(documentRef, handledAt),
      cell(documentRef, record.handler_display_name_snapshot || record.handler_username_snapshot),
      element(documentRef, "td", {}, [element(documentRef, "span", { className: `rsp-status rsp-status-${record.status}`, text: STATUS_LABELS[record.status] || record.status })]),
      element(documentRef, "td", {}, [trigger]),
    ]);
    trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      onOpen(record, trigger);
    });
    body.append(row);
  });

  const table = element(documentRef, "table", { className: "rsp-ledger-table", "aria-label": "报表特殊处理台账" }, [head, body]);
  if (!records.length) {
    body.append(
      element(documentRef, "tr", { className: "rsp-empty-row" }, [
        element(documentRef, "td", {
          className: "rsp-empty",
          colspan: "7",
          text: "没有符合条件的特殊处理记录",
        }),
      ]),
    );
  }
  return element(documentRef, "div", { className: "rsp-table-wrap" }, [table]);
}
