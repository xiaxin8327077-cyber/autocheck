import { element } from "./dom.js";

const STATUS_LABELS = {
  draft: "草稿",
  pending: "待确认",
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

function displayWidth(text) {
  let width = 0;
  for (const char of String(text || "")) {
    const code = char.codePointAt(0) || 0;
    // 半角/ASCII 按 1，全角汉字等按 2，贴近视觉宽度
    width += code <= 0x00ff ? 1 : 2;
  }
  return width;
}

function compareByDisplayWidth(left, right) {
  const widthDiff = displayWidth(left) - displayWidth(right);
  if (widthDiff !== 0) return widthDiff;
  return String(left).localeCompare(String(right), "zh-CN");
}

function processNameList(record) {
  const items = Array.isArray(record?.report_processes) ? record.report_processes : [];
  const ordered = items
    .map((item) => ({
      code: String(item?.code || "").trim(),
      name: String(item?.name || "").trim(),
    }))
    .filter((item) => item.name);
  if (ordered.length) {
    ordered.sort((left, right) => compareByDisplayWidth(left.name, right.name));
    return ordered.map((item) => item.name);
  }
  const snapshot = String(record?.report_process_name_snapshot || record?.report_process_name || "").trim();
  if (!snapshot) return [];
  if (snapshot.includes("；")) {
    return snapshot
      .split("；")
      .map((part) => part.trim())
      .filter(Boolean)
      .sort(compareByDisplayWidth);
  }
  return [snapshot];
}

function processNamesCell(documentRef, record) {
  const names = processNameList(record);
  const fullText = names.join("；");
  if (!names.length) {
    return element(documentRef, "td", { className: "rsp-process-names", text: "—", title: "" });
  }
  const visible = names.map((name) => element(documentRef, "div", {
    className: "rsp-process-name-line",
    text: name,
  }));
  const block = element(documentRef, "div", {
    className: names.length > 3 ? "rsp-process-names-block is-compact" : "rsp-process-names-block",
  }, visible);
  return element(documentRef, "td", { className: "rsp-process-names", title: fullText }, [block]);
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
  if (record.can_confirm && ["pending", "processing"].includes(record.status)) {
    actions.push(actionLink(documentRef, "确认", () => onAction?.(record, "confirm"), "rsp-text-action rsp-text-action-success"));
  }
  if (record.can_void && ["draft", "pending", "processing"].includes(record.status)) {
    actions.push(actionLink(documentRef, "作废", () => onAction?.(record, "void"), "rsp-text-action rsp-text-action-danger"));
  }
  if (record.can_reopen && ["completed", "voided"].includes(record.status)) {
    actions.push(actionLink(documentRef, "重开", () => onAction?.(record, "reopen"), "rsp-text-action"));
  }
  if (record.can_delete) {
    actions.push(actionLink(documentRef, "删除", () => onAction?.(record, "delete"), "rsp-text-action rsp-text-action-danger"));
  }
  return element(documentRef, "td", { className: "rsp-row-actions" }, [
    element(documentRef, "div", { className: "rsp-row-actions-inner" }, actions),
  ]);
}

export function createRecordTable(documentRef, records, { selectedId, highlightId, onOpen, onAction }) {
  const head = element(documentRef, "thead", {}, [
    element(documentRef, "tr", {}, ["修改字段名", "修改前", "修改后", "关联报送", "状态", "处理人", "处理时间", "操作"].map((label) => element(documentRef, "th", { text: label, scope: "col" }))),
  ]);
  const body = element(documentRef, "tbody");
  records.forEach((record) => {
    const handledAt = formatDisplayDateTime(record.special_handling_at);
    const selected = String(record.id) === String(selectedId);
    const highlighted = String(record.id) === String(highlightId);
    const rowClass = [
      selected ? "is-selected" : "",
      highlighted ? "is-highlighted" : "",
    ].filter(Boolean).join(" ");
    const row = element(documentRef, "tr", {
      className: rowClass,
      dataset: { recordId: String(record.id) },
      "aria-label": `${record.record_no || "记录"}，${record.field_name || record.summary || "未填写字段"}`,
    }, [
      cell(documentRef, record.field_name),
      cell(documentRef, record.value_before),
      cell(documentRef, record.value_after),
      processNamesCell(documentRef, record),
      element(documentRef, "td", {}, [element(documentRef, "span", { className: `rsp-status rsp-status-${record.status}`, text: STATUS_LABELS[record.status] || record.status })]),
      cell(documentRef, record.handler_display_name_snapshot || record.handler_username_snapshot),
      cell(documentRef, handledAt),
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
          colspan: "8",
          text: "没有符合条件的特殊处理记录",
        }),
      ]),
    );
  }
  const wrap = element(documentRef, "div", { className: "rsp-table-wrap" }, [table]);
  return wrap;
}
