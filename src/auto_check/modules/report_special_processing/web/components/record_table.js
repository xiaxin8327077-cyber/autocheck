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

function normalizeProcessNames(text) {
  return String(text || "").replace(/\//g, "、");
}

function processNamesCell(documentRef, text) {
  const value = normalizeProcessNames(text);
  const display = value || "—";
  return element(documentRef, "td", { className: "rsp-process-names", title: value }, [
    element(documentRef, "span", { className: "rsp-cell-fit", text: display }),
  ]);
}

function fitProcessNameNodes(root) {
  const nodes = root.querySelectorAll?.(".rsp-process-names .rsp-cell-fit") || [];
  const maxSize = 13;
  const minSize = 7;
  const lineHeight = 1.4;
  const lines = 3;
  const boxHeight = maxSize * lineHeight * lines;
  nodes.forEach((node) => {
    node.style.lineHeight = String(lineHeight);
    node.style.maxHeight = `${boxHeight}px`;
    node.style.fontSize = `${maxSize}px`;
    if (node.scrollHeight <= boxHeight + 1) return;
    let low = minSize;
    let high = maxSize;
    while (high - low > 0.25) {
      const mid = (low + high) / 2;
      node.style.fontSize = `${mid}px`;
      if (node.scrollHeight <= boxHeight + 1) low = mid;
      else high = mid;
    }
    let size = low;
    node.style.fontSize = `${size}px`;
    while (size > 5.5 && node.scrollHeight > boxHeight + 1) {
      size -= 0.25;
      node.style.fontSize = `${size}px`;
    }
  });
}

function scheduleProcessNameFit(wrap) {
  const run = () => fitProcessNameNodes(wrap);
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
  else setTimeout(run, 0);
  if (typeof ResizeObserver === "function") {
    if (wrap._rspFitObserver) wrap._rspFitObserver.disconnect();
    const observer = new ResizeObserver(() => run());
    wrap._rspFitObserver = observer;
    observer.observe(wrap);
  }
}

function summaryCell(documentRef, text) {
  const value = text || "—";
  return element(documentRef, "td", { className: "rsp-summary", title: text || "" }, [
    element(documentRef, "span", { className: "rsp-summary-text", text: value }),
  ]);
}

function reportNameList(reports) {
  return (reports || [])
    .map((item) => (typeof item === "string" ? item : item?.report_name || item?.name || ""))
    .map((name) => String(name || "").trim())
    .filter(Boolean);
}

function reportNamesCell(documentRef, reports) {
  const names = reportNameList(reports);
  const fullText = names.join("、");
  if (!names.length) {
    return element(documentRef, "td", { className: "rsp-report-names", text: "—", title: "" });
  }
  const visible = names.slice(0, 3).map((name, index) => {
    const text = index === 2 && names.length > 3 ? `${name}等` : name;
    return element(documentRef, "div", { className: "rsp-report-name-line", text });
  });
  return element(documentRef, "td", { className: "rsp-report-names", title: fullText }, visible);
}

function actionLink(documentRef, text, onClick, className = "rsp-text-action") {
  const button = element(documentRef, "button", {
    type: "button",
    className,
    text,
    "aria-label": text,
  });
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    onClick(event);
  });
  return button;
}

function buildRowActions(documentRef, record, { onOpen, onAction }) {
  const actions = [];
  actions.push(actionLink(
    documentRef,
    record.can_edit ? "编辑" : "查看",
    () => onOpen(record),
  ));
  if (record.can_edit && ["pending", "processing"].includes(record.status)) {
    actions.push(actionLink(documentRef, "完成", () => onAction?.(record, "complete"), "rsp-text-action rsp-text-action-success"));
  }
  if (record.can_admin && ["draft", "pending", "processing"].includes(record.status)) {
    actions.push(actionLink(documentRef, "作废", () => onAction?.(record, "void"), "rsp-text-action rsp-text-action-danger"));
  }
  return element(documentRef, "td", { className: "rsp-row-actions" }, [
    element(documentRef, "div", { className: "rsp-row-actions-inner" }, actions),
  ]);
}

export function createRecordTable(documentRef, records, { selectedId, onOpen, onAction }) {
  const head = element(documentRef, "thead", {}, [
    element(documentRef, "tr", {}, ["关联报送", "涉及报表", "处理摘要", "特殊处理时间", "处理人", "状态", "操作"].map((label) => element(documentRef, "th", { text: label, scope: "col" }))),
  ]);
  const body = element(documentRef, "tbody");
  records.forEach((record) => {
    const handledAt = formatDisplayDateTime(record.special_handling_at);
    const row = element(documentRef, "tr", {
      className: String(record.id) === String(selectedId) ? "is-selected" : "",
      dataset: { recordId: String(record.id) },
      "aria-label": `${record.record_no || "记录"}，${record.summary || "未填写摘要"}`,
    }, [
      processNamesCell(documentRef, record.report_process_name_snapshot || record.report_process_name),
      reportNamesCell(documentRef, record.reports),
      summaryCell(documentRef, record.summary),
      cell(documentRef, handledAt),
      cell(documentRef, record.handler_display_name_snapshot || record.handler_username_snapshot),
      element(documentRef, "td", {}, [element(documentRef, "span", { className: `rsp-status rsp-status-${record.status}`, text: STATUS_LABELS[record.status] || record.status })]),
      buildRowActions(documentRef, record, { onOpen: (item) => onOpen(item), onAction }),
    ]);
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
  const wrap = element(documentRef, "div", { className: "rsp-table-wrap" }, [table]);
  scheduleProcessNameFit(wrap);
  return wrap;
}
