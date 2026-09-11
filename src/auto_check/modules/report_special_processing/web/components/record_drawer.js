import { element, labeledField, option } from "./dom.js";
import { formatDisplayDateTime } from "./record_table.js";
import { createProcessMultiSelect } from "./process_multi_select.js";
import { createTableFieldGroups } from "./table_field_groups.js";
import { createStructuredContentEditor } from "./structured_content_editor.js";
import { buildScriptPreview } from "./script_preview.js";
import { createRecordAttachmentSection, renderRecordAttachmentSnapshot } from "./record_attachments.js";
import { confirmAttachmentUrl } from "../api.js";
import { buildSemanticAuditViewModel, renderSemanticAuditDetail } from "./audit_detail.js";
import { createLegacyContentPreview, createStructuredContentPreview, readonlyField, readonlyTextBlock } from "./record_preview.js";

const SUMMARY_MAX_LENGTH = 128;
const FIELD_TEXT_MAX_LENGTH = 128;
const DIMENSION_LABELS = {
  project: "项目端",
  fund: "资金端",
  asset: "资产端",
  finance: "财务端",
};

const AUDIT_ACTION_META = {
  create: { label: "创建", tone: "neutral", className: "rsp-audit-action-neutral" },
  update: { label: "修改", tone: "update", className: "rsp-audit-action-update" },
  status_change: { label: "状态变更", tone: "update", className: "rsp-audit-action-update" },
  reopen: { label: "重开", tone: "reopen", className: "rsp-audit-action-reopen" },
  void: { label: "作废", tone: "void", className: "rsp-audit-action-void" },
};

const AUDIT_FIELD_LABELS = {
  report_process_name_snapshot: "关联报送",
  report_period: "所处报送期",
  dimension: "所属维度",
  business_system_name_snapshot: "所属业务系统",
  datasource_name_snapshot: "数据源",
  summary: "处理摘要",
  table_name: "处理表名",
  field_name: "处理字段名",
  value_before: "修改前",
  value_after: "修改后",
  processing_script: "处理脚本",
  special_handling_at: "特殊处理时间",
  handler_display_name_snapshot: "处理人",
  governance_owner_display_name_snapshot: "数据治理负责人",
  status: "状态",
};

const AUDIT_STATUS_LABELS = {
  draft: "草稿",
  pending: "待确认",
  processing: "处理中",
  completed: "已完成",
  voided: "已作废",
};

const SCRIPT_AUDIT_PREVIEW_LINES = 8;
const SCRIPT_AUDIT_PREVIEW_CHARS = 400;
const MAX_CONFIRM_IMAGES = 3;
const MAX_CONFIRM_IMAGE_BYTES = 2 * 1024 * 1024;
const MAX_CONFIRM_NOTE_CHARS = 500;
const CONFIRM_IMAGE_TYPES = {
  "image/png": "image/png",
  "image/jpeg": "image/jpeg",
  "image/jpg": "image/jpeg",
  "image/pjpeg": "image/jpeg",
  "image/webp": "image/webp",
};

function formatAuditValue(value, field = "") {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length)) {
    return "（空）";
  }
  if (field === "status") return AUDIT_STATUS_LABELS[value] || String(value);
  if (Array.isArray(value)) return value.map((item) => formatAuditValue(item)).join("；");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function clampScriptAuditPreview(text) {
  const normalized = String(text ?? "").replace(/\r\n|\r/g, "\n");
  const lines = normalized.split("\n");
  let preview = lines.slice(0, SCRIPT_AUDIT_PREVIEW_LINES).join("\n");
  if (preview.length > SCRIPT_AUDIT_PREVIEW_CHARS) preview = preview.slice(0, SCRIPT_AUDIT_PREVIEW_CHARS);
  return preview;
}

async function copyTextToClipboard(documentRef, text) {
  const value = String(text ?? "");
  const clipboard = documentRef.defaultView?.navigator?.clipboard;
  if (clipboard && typeof clipboard.writeText === "function") {
    try {
      await clipboard.writeText(value);
      return;
    } catch (_) {
      // HTTP 局域网等非安全上下文会拒绝 clipboard API，改走选区复制。
    }
  }
  const textarea = documentRef.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  documentRef.body.append(textarea);
  textarea.focus();
  textarea.select();
  let copied = false;
  try {
    copied = Boolean(documentRef.execCommand("copy"));
  } finally {
    textarea.remove();
  }
  if (!copied) throw new Error("copy failed");
}

function formatScriptAuditPreviewValue(meta, side) {
  const hasFull = hasAuditValue(meta, side);
  const full = hasFull ? String(meta[side] ?? "") : "";
  const raw = hasAuditValue(meta, `${side}_preview`)
    ? String(meta[`${side}_preview`] ?? "")
    : full;
  const preview = clampScriptAuditPreview(raw);
  const chars = Number(meta[`${side}_chars`] || full.length || raw.length || 0);
  const truncated = Boolean(meta[`${side}_truncated`]) || raw !== preview || (hasFull && full !== preview);
  if (!preview && !full) return { text: "（空）", title: "", copy: "", copyIsPreview: false, truncated: false };
  return {
    text: truncated ? `${preview}...` : preview,
    title: truncated ? `${preview}\n（共 ${chars} 字）` : preview,
    copy: hasFull ? full : preview,
    copyIsPreview: !hasFull,
    truncated,
  };
}

function formatScriptAuditPair(meta) {
  const hasFull = hasAuditValue(meta, "old") || hasAuditValue(meta, "new");
  const hasPreview = hasAuditValue(meta, "old_preview") || hasAuditValue(meta, "new_preview");
  const hasChars = hasAuditValue(meta, "old_chars") || hasAuditValue(meta, "new_chars");
  if (!hasPreview && !hasFull && !hasChars) return null;
  if (!hasPreview && !hasFull) {
    return {
      key: "processing_script",
      label: AUDIT_FIELD_LABELS.processing_script,
      old: `${Number(meta.old_chars || 0)} 字`,
      new: `${Number(meta.new_chars || 0)} 字`,
    };
  }
  const oldCell = formatScriptAuditPreviewValue(meta, "old");
  const newCell = formatScriptAuditPreviewValue(meta, "new");
  return {
    key: "processing_script",
    label: AUDIT_FIELD_LABELS.processing_script,
    old: oldCell.text,
    new: newCell.text,
    oldTitle: oldCell.title,
    newTitle: newCell.title,
    oldCopy: oldCell.copy,
    newCopy: newCell.copy,
    oldCopyIsPreview: oldCell.copyIsPreview,
    newCopyIsPreview: newCell.copyIsPreview,
    scriptPreview: true,
  };
}

function hasAuditValue(meta, key) {
  return Object.prototype.hasOwnProperty.call(meta, key);
}

function auditNoteLabel(key, actionCode) {
  if (key === "reopen_reason" || actionCode === "reopen") return "重开原因";
  if (key === "void_reason" || actionCode === "void") return "作废理由";
  if (actionCode === "status_change") return "确认说明";
  return "操作说明";
}

function describeAuditEntry(item, recordId) {
  let action = AUDIT_ACTION_META[item?.action_code] || {
    label: "操作记录", tone: "neutral", className: "rsp-audit-action-neutral",
  };
  if (item?.action_code === "status_change" && item?.to_status === "completed") {
    action = { label: "完成", tone: "completed", className: "rsp-audit-action-completed" };
  } else if ((item?.action_code === "create" || item?.action_code === "update") && item?.to_status === "draft") {
    action = { label: "保存草稿", tone: "neutral", className: "rsp-audit-action-neutral" };
  }

  const paired = [];
  const notes = [];
  const attachments = [];
  let attachmentDiff = null;
  let structuredDiff = null;
  const changedFields = item?.changed_fields;
  const hasStructuredAuditData = Boolean(
    changedFields && typeof changedFields === "object" && !Array.isArray(changedFields) && Object.keys(changedFields).length,
  );
  Object.entries(changedFields || {}).forEach(([key, meta]) => {
    if (!meta || typeof meta !== "object") return;
    if (key === "structured_content") {
      structuredDiff = meta;
      return;
    }
    if (["reason", "reopen_reason", "void_reason"].includes(key)) {
      if (hasAuditValue(meta, "new")) {
        notes.push({ label: auditNoteLabel(key, item?.action_code), value: formatAuditValue(meta.new) });
      }
      return;
    }
    if (key === "confirm_attachments") {
      const ids = Array.isArray(meta.ids) ? meta.ids.map(Number).filter((id) => id > 0) : [];
      attachments.push(...ids);
      return;
    }
    if (key === "record_attachments") {
      // 记录附件走专用双栏快照，不进入普通字符串对照，也不 JSON.stringify 到单元格。
      if (Array.isArray(meta.old) || Array.isArray(meta.new)) {
        attachmentDiff = {
          old: Array.isArray(meta.old) ? meta.old : [],
          new: Array.isArray(meta.new) ? meta.new : [],
        };
      }
      return;
    }
    if (key === "processing_script") {
      const scriptPair = formatScriptAuditPair(meta);
      if (scriptPair) paired.push(scriptPair);
      return;
    }
    if (AUDIT_FIELD_LABELS[key] && hasAuditValue(meta, "old") && hasAuditValue(meta, "new")) {
      paired.push({
        key,
        label: AUDIT_FIELD_LABELS[key],
        old: formatAuditValue(meta.old, key),
        new: formatAuditValue(meta.new, key),
      });
    }
  });

  if (
    !paired.some((item) => item.key === "status")
    && item?.from_status
    && item?.to_status
    && item.from_status !== item.to_status
  ) {
    paired.unshift({
      key: "status",
      label: AUDIT_FIELD_LABELS.status,
      old: formatAuditValue(item.from_status, "status"),
      new: formatAuditValue(item.to_status, "status"),
    });
  }

  const hasLegacyContentDiff = [
    "datasource_name_snapshot", "table_name", "field_name", "value_before", "value_after",
  ].some((key) => Object.prototype.hasOwnProperty.call(changedFields || {}, key));
  const hasBasicSemanticDiff = [
    "report_process_name_snapshot", "report_period", "dimension", "business_system_name_snapshot",
    "summary", "special_handling_at", "handler_display_name_snapshot",
    "governance_owner_display_name_snapshot",
  ].some((key) => Object.prototype.hasOwnProperty.call(changedFields || {}, key));
  const hasScriptSemanticDiff = Boolean(
    changedFields?.processing_script
    && typeof changedFields.processing_script === "object"
    && changedFields.processing_script.mode,
  );
  const semanticCandidate = structuredDiff || hasBasicSemanticDiff || hasScriptSemanticDiff
    ? buildSemanticAuditViewModel(item) : null;
  const semanticModel = !hasLegacyContentDiff && semanticCandidate
    ? semanticCandidate : null;
  const visiblePairs = semanticModel
    ? paired.filter((pair) => pair.key !== "processing_script")
    : paired;

  return {
    ...action,
    paired: visiblePairs,
    notes,
    attachments,
    attachmentDiff,
    structuredDiff,
    semanticModel,
    recordId: Number(recordId || item?.record_id || 0),
    hasStructuredAuditData,
    status: visiblePairs.find((pair) => pair.key === "status") || null,
    summary: String(item?.action_summary || item?.action_code || "—"),
  };
}

function renderAuditScriptValue(documentRef, pair, side, onCopyScript) {
  const isBefore = side === "old";
  const label = isBefore ? "修改前" : "修改后";
  const text = isBefore ? pair.old : pair.new;
  const title = isBefore ? pair.oldTitle : pair.newTitle;
  const copyText = isBefore ? pair.oldCopy : pair.newCopy;
  const copyIsPreview = isBefore ? pair.oldCopyIsPreview : pair.newCopyIsPreview;
  const children = [
    element(documentRef, "div", { className: "rsp-audit-script-text", title: title || undefined, text }),
  ];
  if (copyText) {
    children.unshift(element(documentRef, "button", {
      type: "button",
      className: "rsp-button rsp-button-secondary rsp-audit-script-copy",
      text: "复制",
      "aria-label": `复制${label}脚本`,
      onClick: (event) => {
        event.preventDefault();
        event.stopPropagation();
        onCopyScript?.(copyText, copyIsPreview);
      },
    }));
  }
  return element(documentRef, "div", {
    className: `rsp-audit-value ${isBefore ? "rsp-audit-value-before" : "rsp-audit-value-after"} rsp-audit-value--script`,
    "data-audit-label": label,
  }, children);
}

function renderAuditDetail(documentRef, entry, onCopyScript, onOpenImage, attachmentOptions = null) {
  const cells = [];
  if (!entry.semanticModel && entry.paired.length) {
    ["字段", "修改前", "修改后"].forEach((label) => {
      cells.push(element(documentRef, "div", { className: "rsp-audit-diff-header", text: label }));
    });
    entry.paired.forEach((pair) => {
      cells.push(element(documentRef, "div", { className: "rsp-audit-field", text: pair.label }));
      if (pair.scriptPreview) {
        cells.push(renderAuditScriptValue(documentRef, pair, "old", onCopyScript));
        cells.push(renderAuditScriptValue(documentRef, pair, "new", onCopyScript));
        return;
      }
      cells.push(element(documentRef, "div", {
        className: "rsp-audit-value rsp-audit-value-before",
        "data-audit-label": "修改前",
        text: pair.old,
      }));
      cells.push(element(documentRef, "div", {
        className: "rsp-audit-value rsp-audit-value-after",
        "data-audit-label": "修改后",
        text: pair.new,
      }));
    });
  }
  entry.notes.forEach((note) => {
    cells.push(element(documentRef, "div", { className: "rsp-audit-detail-note" }, [
      element(documentRef, "strong", { text: `${note.label}：` }),
      element(documentRef, "span", { text: note.value }),
    ]));
  });
  if (entry.attachments?.length && entry.recordId) {
    cells.push(element(documentRef, "div", { className: "rsp-audit-detail-attachments" }, [
      element(documentRef, "strong", { text: "确认图片：" }),
      element(documentRef, "div", { className: "rsp-confirm-thumbs" }, entry.attachments.map((id) => {
        const src = confirmAttachmentUrl(entry.recordId, id);
        return element(documentRef, "button", {
          type: "button",
          className: "rsp-confirm-thumb",
          "aria-label": "查看确认图片",
          onClick: (event) => {
            event.preventDefault();
            onOpenImage?.(src);
          },
        }, [
          element(documentRef, "img", { src, alt: "确认图片" }),
        ]);
      })),
    ]));
  }
  const hasExtras = Boolean(entry.notes.length || entry.attachments?.length);
  const semanticBlock = entry.semanticModel
    ? renderSemanticAuditDetail(documentRef, entry.semanticModel, { onCopyScript })
    : null;
  // 记录附件“修改前 / 修改后”双栏：标签只按该条审计的 old/new 集合渲染。
  let attachmentBlock = null;
  if (entry.attachmentDiff && attachmentOptions) {
    const snapshotOptions = { ...attachmentOptions, recordId: entry.recordId || attachmentOptions.recordId };
    attachmentBlock = element(documentRef, "div", { className: "rsp-audit-record-attachments" }, [
      element(documentRef, "strong", { className: "rsp-audit-record-attachments-title", text: "附件：" }),
      element(documentRef, "div", { className: "rsp-audit-record-attachments-columns" }, [
        element(documentRef, "div", { className: "rsp-audit-record-attachments-column" }, [
          element(documentRef, "h4", { text: "修改前" }),
          renderRecordAttachmentSnapshot(documentRef, { ...snapshotOptions, attachments: entry.attachmentDiff.old }),
        ]),
        element(documentRef, "div", { className: "rsp-audit-record-attachments-column" }, [
          element(documentRef, "h4", { text: "修改后" }),
          renderRecordAttachmentSnapshot(documentRef, { ...snapshotOptions, attachments: entry.attachmentDiff.new }),
        ]),
      ]),
    ]);
  }
  return element(documentRef, "div", { className: "rsp-audit-detail" }, [
    semanticBlock,
    cells.length ? element(documentRef, "div", {
      className: "rsp-audit-detail-scroll",
      "aria-label": "完整变更对照",
    }, [
      element(documentRef, "div", {
        className: `rsp-audit-diff-grid${hasExtras ? " has-notes" : ""}`,
      }, cells),
    ]) : null,
    attachmentBlock,
  ]);
}

function nowHandlingAt() {
  const date = new Date();
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return `${local.toISOString().slice(0, 19)}+08:00`;
}

function draftPayload(fields, saveMode, rowVersion, specialHandlingAt, structuredContent, processingScriptMode = "AUTO") {
  const payload = {
    save_mode: saveMode,
    report_process_codes: fields.process.value,
    report_period: fields.period.value,
    dimension: fields.dimension.value || null,
    business_system_code: fields.businessSystem?.value || null,
    governance_owner_user_id: fields.governanceOwner.value || null,
    summary: fields.summary.value.trim(),
    table_name: fields.tableName.value.trim(),
    field_name: fields.fieldName.value.trim(),
    value_before: fields.valueBefore.value.trim(),
    value_after: fields.valueAfter.value.trim(),
    processing_script: fields.script.value,
    processing_script_mode: processingScriptMode,
    special_handling_at: specialHandlingAt,
    handler_user_id: fields.handler.value,
  };
  // 结构化模式：提交完整数据源→表→字段→修改前/后，后端以此为准重新派生兼容串。
  if (structuredContent) payload.structured_content = structuredContent;
  if (rowVersion !== null && rowVersion !== undefined) payload.row_version = rowVersion;
  return payload;
}

function actionButton(documentRef, text, className, onClick, disabled = false) {
  return element(documentRef, "button", { type: "button", className: `rsp-button ${className}`, text, onClick, disabled });
}

function fillSelect(select, items, emptyLabel) {
  select.replaceChildren(option(select.ownerDocument, "", emptyLabel));
  (items || []).forEach((item) => {
    select.append(option(select.ownerDocument, item.id, item.display_name || item.username));
  });
}

function pickRandomId(items) {
  if (!items?.length) return "";
  return String(items[Math.floor(Math.random() * items.length)].id);
}

export function createRecordDrawer(documentRef, options) {
  const {
    catalog, record, mode, user, catalogAvailable, actions, onClose, onSaved, onConflict,
  } = options;
  const creating = mode === "create";
  const confirming = mode === "confirm";
  const current = record || {};
  const canEdit = !confirming && (creating || Boolean(current.can_edit));
  const readOnly = !canEdit;
  const title = creating
    ? "新建报表特殊处理"
    : (confirming ? "确认特殊处理" : (canEdit ? "编辑" : "查看"));

  const report_processes = catalog?.report_processes || [];
  const initialProcessCodes = Array.isArray(current.report_process_codes) && current.report_process_codes.length
    ? current.report_process_codes
    : (current.report_process_code
      ? [current.report_process_code]
      : (options.activeProcessCode ? [options.activeProcessCode] : []));
  const process = createProcessMultiSelect(documentRef, {
    options: report_processes,
    values: initialProcessCodes,
    disabled: !canEdit,
    "aria-label": "关联报送",
  });

  const users = catalog?.users || [];
  const handler = element(documentRef, "select", { className: "rsp-compact-select", "aria-label": "处理人", disabled: !canEdit }, [option(documentRef, "", "请选择处理人")]);
  users.map((item) => handler.append(option(documentRef, item.id, item.display_name || item.username)));
  const defaultHandlerId = current.handler_user_id != null && current.handler_user_id !== ""
    ? String(current.handler_user_id)
    : (user?.id != null && user?.id !== "" ? String(user.id) : "");
  handler.value = defaultHandlerId;
  if (defaultHandlerId && handler.value !== defaultHandlerId) {
    handler.append(option(
      documentRef,
      defaultHandlerId,
      user?.display_name || user?.username || "当前用户",
    ));
    handler.value = defaultHandlerId;
  }

  const dimensions = catalog?.dimensions || [];
  const dimension = element(documentRef, "select", {
    className: "rsp-compact-select",
    "aria-label": "所属维度",
    disabled: !canEdit,
  }, [option(documentRef, "", "请选择所属维度")]);
  dimensions.forEach((item) => dimension.append(option(documentRef, item.code, item.label || item.code)));

  const businessSystems = catalog?.business_systems || [];
  const businessSystem = element(documentRef, "select", {
    className: "rsp-compact-select",
    "aria-label": "所属业务系统",
    disabled: !canEdit,
  }, [option(documentRef, "", businessSystems.length ? "请选择所属业务系统" : "请先在系统管理—字典管理中维护业务系统")]);
  businessSystems.forEach((item) => businessSystem.append(option(documentRef, item.code, item.name || item.code)));
  if (current.business_system_code) {
    const savedCode = String(current.business_system_code);
    if (!businessSystems.some((item) => item.code === savedCode)) {
      // 历史选择项已停用：保持原样可继续编辑其他字段，改选时只能选启用项。
      businessSystem.append(option(
        documentRef,
        savedCode,
        `${current.business_system_name_snapshot || savedCode}（已停用）`,
      ));
    }
    businessSystem.value = savedCode;
  }

  const governanceOwner = element(documentRef, "select", {
    className: "rsp-compact-select",
    "aria-label": "数据治理负责人",
    disabled: !canEdit,
  }, [option(documentRef, "", "请选择数据治理负责人")]);

  const candidatesByDimension = catalog?.governance_owner_candidates_by_dimension || {};

  function syncGovernanceOwnerOptions({ preferExisting = false, autoPick = true } = {}) {
    const code = dimension.value || "";
    const candidates = code ? (candidatesByDimension[code] || []) : [];
    fillSelect(governanceOwner, users, "请选择数据治理负责人");

    let next = "";
    if (preferExisting) {
      const existingId = current.governance_owner_user_id != null && current.governance_owner_user_id !== ""
        ? String(current.governance_owner_user_id)
        : "";
      if (existingId && users.some((item) => String(item.id) === existingId)) {
        next = existingId;
      } else if (existingId) {
        governanceOwner.append(option(
          documentRef,
          existingId,
          current.governance_owner_display_name_snapshot
            || current.governance_owner_username_snapshot
            || existingId,
        ));
        next = existingId;
      }
    }

    if (!next && autoPick && candidates.length) {
      next = pickRandomId(candidates);
    }
    governanceOwner.value = next;
  }

  if (current.dimension) dimension.value = String(current.dimension);
  syncGovernanceOwnerOptions({ preferExisting: true, autoPick: creating && !current.governance_owner_user_id });

  dimension.addEventListener("change", () => {
    syncGovernanceOwnerOptions({ preferExisting: false, autoPick: true });
  });

  // 特殊处理内容：新建或已带结构化内容的记录走“数据源→表→字段→修改前/后”编辑器；
  // 历史手工录入记录继续用表-字段分组组件（方案 A 兼容）。
  const recordStructured = current.structured_content && typeof current.structured_content === "object"
    ? current.structured_content
    : null;
  const useStructured = creating || Boolean(recordStructured);
  let structuredEditor = null;
  let tableFieldGroups = null;
  let contentPreview = null;
  if (useStructured) {
    if (canEdit) {
      structuredEditor = createStructuredContentEditor(documentRef, {
        api: actions,
        initial: recordStructured,
        disabled: false,
        notify: options.notify,
        confirm: options.confirm,
        getHost: () => overlayNode,
        datasourceNameSnapshot: current.datasource_name_snapshot || "",
        reportPeriodFieldMatchers: catalog?.report_period_fields || [],
        onChange: () => {
          if (typeof autoGenerateRef === "function") autoGenerateRef();
        },
      });
    } else {
      contentPreview = createStructuredContentPreview(documentRef, {
        initial: recordStructured,
        datasourceNameSnapshot: current.datasource_name_snapshot || "",
      });
    }
  } else {
    if (canEdit) {
      tableFieldGroups = createTableFieldGroups(documentRef, {
        tableValue: current.table_name || "",
        fieldValue: current.field_name || "",
        disabled: false,
        confirm: options.confirm,
      });
    } else {
      contentPreview = createLegacyContentPreview(documentRef, current);
    }
  }
  const DERIVED_KEYS = { table: "table_name", field: "field_name", before: "value_before", after: "value_after" };
  function groupControl(kind) {
    if (readOnly) {
      return {
        get value() {
          return current[DERIVED_KEYS[kind]] || "";
        },
        setAttribute: () => {},
        removeAttribute: () => {},
        focus: () => {},
      };
    }
    if (structuredEditor) {
      return {
        get value() {
          return structuredEditor.getStrings()[DERIVED_KEYS[kind]] || "";
        },
        setAttribute: (name, value) => structuredEditor.setAttribute(name, value),
        removeAttribute: (name) => structuredEditor.removeAttribute(name),
        focus: () => structuredEditor.focusFirst?.(),
      };
    }
    return {
      get value() {
        return kind === "table" ? tableFieldGroups.tableValue : tableFieldGroups.fieldValue;
      },
      setAttribute: (name, value) => tableFieldGroups.setAttribute(name, value),
      removeAttribute: (name) => tableFieldGroups.removeAttribute(name),
      focus: () => tableFieldGroups.focusFirstInput?.(),
    };
  }

  const fields = {
    process,
    handler,
    dimension,
    businessSystem,
    governanceOwner,
    period: element(documentRef, "input", { type: "date", value: current.report_period || options.reportPeriod || "", "aria-label": "所处报送期", disabled: !canEdit }),
    summary: element(documentRef, "textarea", {
      className: "rsp-summary",
      rows: "3",
      value: current.summary || "",
      maxlength: String(SUMMARY_MAX_LENGTH),
      "aria-label": "处理摘要",
      placeholder: `最多 ${SUMMARY_MAX_LENGTH} 个字符`,
      disabled: !canEdit,
    }),
    tableName: groupControl("table"),
    fieldName: groupControl("field"),
    valueBefore: useStructured ? groupControl("before") : element(documentRef, "input", {
      value: current.value_before || "",
      "aria-label": "修改前",
      maxlength: String(FIELD_TEXT_MAX_LENGTH),
      disabled: !canEdit,
    }),
    valueAfter: useStructured ? groupControl("after") : element(documentRef, "input", {
      value: current.value_after || "",
      "aria-label": "修改后",
      maxlength: String(FIELD_TEXT_MAX_LENGTH),
      disabled: !canEdit,
    }),
    script: element(documentRef, "textarea", { className: "rsp-script", "aria-label": "处理脚本", spellcheck: "false", disabled: !canEdit }),
  };
  fields.script.value = current.processing_script || "";

  function resolveHandlingAt() {
    if (creating) return nowHandlingAt();
    return current.special_handling_at || nowHandlingAt();
  }

  const formHint = element(documentRef, "div", {
    className: "rsp-field-hint",
    role: "alert",
    hidden: "",
  });
  // 版本冲突提示条：只提示并提供显式“加载最新记录”动作，
  // 刷新/放弃必须由用户明确触发，错误回调不得自动重建抽屉。
  const conflictText = element(documentRef, "span", { className: "rsp-conflict-bar-text" });
  const conflictBar = element(documentRef, "div", {
    className: "rsp-conflict-bar",
    role: "alert",
    hidden: "",
  }, [
    conflictText,
    actionButton(documentRef, "加载最新记录", "rsp-button-secondary", () => {
      onConflict();
    }),
  ]);
  function showConflictBar() {
    conflictText.textContent =
      "记录已被其他人修改，未保存内容已保留；点击“加载最新记录”将覆盖当前未保存内容。";
    conflictBar.hidden = false;
  }
  const FIELD_LABELS = {
    report_process_codes: "关联报送",
    report_process_code: "关联报送",
    report_period: "所处报送期",
    handler_user_id: "处理人",
    dimension: "所属维度",
    business_system_code: "所属业务系统",
    governance_owner_user_id: "数据治理负责人",
    summary: "处理摘要",
    table_name: "处理表名",
    field_name: "处理字段名",
    value_before: "修改前",
    value_after: "修改后",
    processing_script: "处理脚本",
    special_handling_at: "特殊处理时间",
  };
  function resolveControl(fieldName) {
    if (fieldName === "report_process_codes" || fieldName === "report_process_code") return fields.process;
    if (fieldName === "handler_user_id") return fields.handler;
    if (fieldName === "governance_owner_user_id") return fields.governanceOwner;
    if (fieldName === "report_period") return fields.period;
    if (fieldName === "table_name") return fields.tableName;
    if (fieldName === "field_name") return fields.fieldName;
    if (fieldName === "business_system_code") return fields.businessSystem;
    if (fieldName === "value_before") return fields.valueBefore;
    if (fieldName === "value_after") return fields.valueAfter;
    if (fieldName === "processing_script") return fields.script;
    return fields[fieldName] || null;
  }
  function formatFieldMessage(fieldName, message) {
    const label = FIELD_LABELS[fieldName] || "";
    const text = Array.isArray(message) ? message.filter(Boolean).join("；") : String(message || "").trim();
    if (!label) return text || "字段无效";
    if (!text) return `${label}无效`;
    if (text.startsWith(label)) return text;
    return `${label}${text}`;
  }
  function clearFormHint() {
    formHint.hidden = true;
    formHint.textContent = "";
    Object.values(fields).forEach((control) => {
      control?.removeAttribute?.("aria-invalid");
      control?.removeAttribute?.("title");
    });
  }
  function showFormHint(message, focusControl = null, { focus = true } = {}) {
    formHint.hidden = false;
    formHint.textContent = message;
    if (focusControl?.setAttribute) focusControl.setAttribute("aria-invalid", "true");
    // 自动生成脚本等非用户主动提交场景传 focus=false：只提示错误、不夺焦，
    // 避免 combo 输入框因 focus 触发候选面板自动展开。
    if (focus) focusControl?.focus?.();
  }
  function showError(error) {
    const fieldEntries = Object.entries(error.fields || {});
    clearFormHint();
    const fieldMessages = fieldEntries
      .map(([fieldName, message]) => formatFieldMessage(fieldName, message))
      .filter(Boolean);
    const text = fieldMessages.length
      ? fieldMessages.join("；")
      : (error.message || "保存失败，请重试");
    const firstField = fieldEntries[0]?.[0] || "";
    showFormHint(text, resolveControl(firstField));
    // 字段校验只在底部提示，不弹右上角 toast
    if (!fieldMessages.length) options.notify(text, "error");
    fieldEntries.forEach(([fieldName]) => {
      const control = resolveControl(fieldName);
      control?.setAttribute?.("aria-invalid", "true");
    });
    // 版本冲突：仅显示提示条保留编辑状态；是否加载最新记录由用户显式决定。
    if (error.refreshRequired) showConflictBar();
  }
  // 提交互斥锁：保存/确认请求在途期间忽略重复点击并禁用底部操作按钮，
  // 防止多次点击创建重复记录；成功后保持锁定直到抽屉关闭。
  let submitting = false;
  const footerActionButtons = [];
  function setFooterActionsDisabled(disabled) {
    footerActionButtons.forEach((button) => {
      button.disabled = Boolean(disabled);
    });
  }
  async function run(operation, successMessage) {
    if (submitting) return;
    submitting = true;
    setFooterActionsDisabled(true);
    clearFormHint();
    try {
      const response = await operation();
      options.notify(successMessage, "success");
      await onSaved(response?.data || response);
      // 保存成功后抽屉关闭，释放附件组件的 Blob URL 与监听器。
      attachmentSection?.destroy();
    } catch (error) {
      // 保存失败（含普通业务 409、400 与网络错误）不销毁附件组件，
      // 表单与未保存附件保留在当前标签页内，允许修正后重试。
      submitting = false;
      setFooterActionsDisabled(false);
      if (error?.name !== "AbortError") showError(error);
    }
  }
  function validateForm({ formal = false, focus = true } = {}) {
    clearFormHint();
    if (structuredEditor) {
      // 结构化模式：数据源/表/字段/中文名逐条定位校验；正式保存另验字段级修改前/后。
      const problem = structuredEditor.validate({ formal });
      if (problem) {
        showFormHint(problem.message, problem.control || structuredEditor, { focus });
        return false;
      }
    } else {
      const tableName = fields.tableName.value.trim();
      if (!tableName) {
        showFormHint("请填写处理表名", fields.tableName);
        return false;
      }
      const fieldName = fields.fieldName.value.trim();
      if (!fieldName) {
        showFormHint("请填写处理字段名", fields.fieldName);
        return false;
      }
      if (formal && !fields.valueBefore.value.trim()) {
        showFormHint("请填写修改前内容", fields.valueBefore);
        return false;
      }
      if (formal && !fields.valueAfter.value.trim()) {
        showFormHint("请填写修改后内容", fields.valueAfter);
        return false;
      }
    }
    const summary = fields.summary.value.trim();
    if (summary.length > SUMMARY_MAX_LENGTH) {
      showFormHint(`处理摘要最多支持${SUMMARY_MAX_LENGTH}个字符`, fields.summary);
      return false;
    }
    return true;
  }
  fields.summary.addEventListener("input", () => {
    if (!formHint.hidden) clearFormHint();
  });
  async function buildSavePayload(saveMode) {
    const payload = draftPayload(
      fields,
      saveMode,
      creating ? null : current.row_version,
      resolveHandlingAt(),
      structuredEditor ? structuredEditor.getStructured() : null,
      scriptMode,
    );
    if (attachmentSection) {
      // 等待附件 Base64 构建完成后一次性提交；无变化时省略字段。
      const attachmentChange = await attachmentSection.buildChangePayload();
      if (attachmentChange) payload.record_attachments = attachmentChange;
    }
    return payload;
  }
  const saveDraft = () => {
    if (!validateForm({ formal: false })) return;
    return run(async () => {
      const payload = await buildSavePayload("draft");
      return creating
        ? actions.createRecord(payload)
        : actions.updateRecord(current.id, payload);
    }, "草稿已保存");
  };
  const saveRecord = () => {
    if (!validateForm({ formal: true })) return;
    return run(async () => {
      const payload = await buildSavePayload("record");
      return creating
        ? actions.createRecord(payload)
        : actions.updateRecord(current.id, payload);
    }, creating ? "特殊处理记录已创建" : "修改已保存");
  };
  const confirmImages = [];
  const confirmNoteInput = confirming ? element(documentRef, "textarea", {
    className: "rsp-confirm-note-input",
    rows: "3",
    maxlength: String(MAX_CONFIRM_NOTE_CHARS),
    placeholder: "可填写说明，也可直接粘贴最多 3 张图片；不填也能确认",
    "aria-label": "确认说明",
  }) : null;
  const confirmNoteCount = confirming ? element(documentRef, "span", {
    className: "rsp-confirm-note-count",
    text: `0 / ${MAX_CONFIRM_NOTE_CHARS}`,
  }) : null;
  const confirmThumbs = confirming ? element(documentRef, "div", { className: "rsp-confirm-thumbs" }) : null;
  let overlayNode = null;
  let lightboxNode = null;
  let attachmentPreviewUrl = "";
  function revokeAttachmentPreview() {
    if (!attachmentPreviewUrl) return;
    const url = attachmentPreviewUrl;
    attachmentPreviewUrl = "";
    try {
      (documentRef.defaultView || globalThis).URL?.revokeObjectURL?.(url);
    } catch (_) {}
  }
  function closeImageLightbox() {
    lightboxNode?.remove();
    lightboxNode = null;
    revokeAttachmentPreview();
  }
  function openAttachmentPreview(blobUrl) {
    if (!blobUrl || !overlayNode) return;
    // openImageLightbox 内部先关闭旧灯箱并撤销旧的附件预览 URL。
    openImageLightbox(blobUrl);
    attachmentPreviewUrl = blobUrl;
  }
  function openImageLightbox(src) {
    if (!overlayNode || !src) return;
    closeImageLightbox();
    const img = element(documentRef, "img", {
      className: "rsp-image-lightbox-img",
      src,
      alt: "图片预览",
    });
    lightboxNode = element(documentRef, "div", {
      className: "rsp-image-lightbox",
      role: "dialog",
      tabIndex: "-1",
      "aria-modal": "true",
      "aria-label": "图片预览",
      onClick: (event) => {
        if (event.target === lightboxNode) closeImageLightbox();
      },
    }, [img]);
    overlayNode.append(lightboxNode);
    lightboxNode.focus();
  }
  function normalizeConfirmImageType(type) {
    return CONFIRM_IMAGE_TYPES[String(type || "").toLowerCase()] || "";
  }
  function renderConfirmThumbs() {
    if (!confirmThumbs) return;
    confirmThumbs.replaceChildren();
    confirmImages.forEach((image, index) => {
      confirmThumbs.append(element(documentRef, "div", { className: "rsp-confirm-thumb-wrap" }, [
        element(documentRef, "button", {
          type: "button",
          className: "rsp-confirm-thumb",
          "aria-label": "预览图片",
          onClick: () => openImageLightbox(image.previewUrl),
        }, [element(documentRef, "img", { src: image.previewUrl, alt: "待确认图片" })]),
        element(documentRef, "button", {
          type: "button",
          className: "rsp-confirm-thumb-remove",
          text: "×",
          "aria-label": "删除图片",
          onClick: (event) => {
            event.preventDefault();
            event.stopPropagation();
            confirmImages.splice(index, 1);
            renderConfirmThumbs();
          },
        }),
      ]));
    });
  }
  function addConfirmFiles(files) {
    const accepted = [];
    for (const file of files) {
      const contentType = normalizeConfirmImageType(file.type);
      if (!contentType) {
        options.notify("仅支持 PNG、JPEG、WebP 图片", "error");
        continue;
      }
      if (file.size > MAX_CONFIRM_IMAGE_BYTES) {
        options.notify("单张图片最大 2 MiB", "error");
        continue;
      }
      accepted.push(file);
    }
    if (!accepted.length) return;
    const remaining = MAX_CONFIRM_IMAGES - confirmImages.length;
    if (remaining <= 0) {
      options.notify("最多粘贴 3 张图片", "error");
      return;
    }
    if (accepted.length > remaining) options.notify("最多粘贴 3 张图片", "error");
    accepted.slice(0, remaining).forEach((file) => {
      const reader = new FileReader();
      reader.onload = () => {
        const url = String(reader.result || "");
        const comma = url.indexOf(",");
        confirmImages.push({
          contentType: normalizeConfirmImageType(file.type),
          dataBase64: comma >= 0 ? url.slice(comma + 1) : "",
          previewUrl: url,
        });
        renderConfirmThumbs();
      };
      reader.readAsDataURL(file);
    });
  }
  function handleConfirmPaste(event) {
    const clipboard = event.clipboardData;
    if (!clipboard) return;
    const files = [];
    if (clipboard.files?.length) {
      Array.from(clipboard.files).forEach((file) => files.push(file));
    }
    if (!files.length && clipboard.items) {
      Array.from(clipboard.items).forEach((item) => {
        if (item.kind === "file" && String(item.type || "").startsWith("image/")) {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      });
    }
    const imageFiles = files.filter((file) => String(file.type || "").startsWith("image/"));
    if (!imageFiles.length) return;
    event.preventDefault();
    addConfirmFiles(imageFiles);
  }
  const confirmSourceSystem = () => {
    const payload = {
      target_status: "completed",
      row_version: current.row_version,
    };
    const note = confirmNoteInput?.value.trim() || "";
    if (note) payload.reason = note;
    if (confirmImages.length) {
      payload.confirm_images = confirmImages.map((item) => ({
        content_type: item.contentType,
        data_base64: item.dataBase64,
      }));
    }
    return run(() => actions.changeStatus(current.id, payload), "记录已确认完成");
  };
  const auditBody = element(documentRef, "tbody");
  const auditStatus = element(documentRef, "span", { className: "rsp-audit-page", text: "第 1 / 1 页" });
  let auditPage = 1;
  let auditTotalPages = 1;
  const expandedAuditIds = new Set();
  const auditPrev = actionButton(documentRef, "上一页", "rsp-button-secondary", () => {
    if (auditPage <= 1) return;
    loadAudit(auditPage - 1);
  });
  const auditNext = actionButton(documentRef, "下一页", "rsp-button-secondary", () => {
    if (auditPage >= auditTotalPages) return;
    loadAudit(auditPage + 1);
  });
  function syncAuditPager() {
    auditPrev.disabled = auditPage <= 1;
    auditNext.disabled = auditPage >= auditTotalPages;
    auditStatus.textContent = `第 ${auditPage} / ${auditTotalPages} 页`;
  }
  const copyAuditScript = async (text, copyIsPreview) => {
    try {
      await copyTextToClipboard(documentRef, text);
      options.notify(
        copyIsPreview ? "已复制脚本开头预览；系统不会执行该脚本" : "脚本已复制；系统不会执行该脚本",
        "success",
      );
    } catch (_) {
      options.notify("复制失败，请手动选择脚本文本", "error");
    }
  };
  function renderAuditBody(items, total) {
    auditBody.replaceChildren();
    if (!items.length) {
      auditBody.append(element(documentRef, "tr", { className: "rsp-empty-row" }, [
        element(documentRef, "td", {
          className: "rsp-empty",
          colspan: "3",
          text: total ? "本页暂无操作记录" : "暂无操作记录",
        }),
      ]));
      return;
    }
    items.forEach((item, index) => {
      const auditId = String(item?.id ?? `${auditPage}-${index}`);
      const entry = describeAuditEntry(item, current.id);
      const hasDetails = entry.paired.length > 0 || entry.notes.length > 0
        || entry.attachments.length > 0 || Boolean(entry.attachmentDiff) || Boolean(entry.semanticModel);
      const expanded = hasDetails && expandedAuditIds.has(auditId);
      const summaryParts = [
        element(documentRef, "span", {
          className: `rsp-audit-action ${entry.className}`,
          text: entry.label,
        }),
      ];
      if (entry.status) {
        summaryParts.push(element(documentRef, "span", { className: "rsp-audit-summary-separator", text: "·" }));
        summaryParts.push(element(documentRef, "span", {
          className: "rsp-audit-status-flow",
          text: `状态：${entry.status.old} → ${entry.status.new}`,
        }));
      }
      entry.notes.forEach((note) => {
        summaryParts.push(element(documentRef, "span", { className: "rsp-audit-summary-separator", text: "·" }));
        summaryParts.push(element(documentRef, "span", {
          className: "rsp-audit-summary-note",
          text: `${note.label}：${note.value}`,
        }));
      });
      if (entry.semanticModel) {
        if (entry.semanticModel.business_change_count) {
          summaryParts.push(element(documentRef, "span", { className: "rsp-audit-summary-separator", text: "·" }));
          summaryParts.push(element(documentRef, "span", {
            className: "rsp-audit-change-count",
            text: `共 ${entry.semanticModel.business_change_count} 项业务变更`,
          }));
        }
        if (entry.semanticModel.summary_parts.length) {
          summaryParts.push(element(documentRef, "span", { className: "rsp-audit-summary-separator", text: "·" }));
          summaryParts.push(element(documentRef, "span", {
            className: "rsp-audit-semantic-summary",
            text: entry.semanticModel.summary_parts.join(" · "),
          }));
        }
      } else if (entry.paired.length) {
        summaryParts.push(element(documentRef, "span", { className: "rsp-audit-summary-separator", text: "·" }));
        summaryParts.push(element(documentRef, "span", {
          className: "rsp-audit-change-count",
          text: `共 ${entry.paired.length} 项变更`,
        }));
      }
      if (entry.attachmentDiff) {
        const addedCount = entry.attachmentDiff.new.filter((meta) => meta?.change === "added").length;
        const removedCount = entry.attachmentDiff.old.filter((meta) => meta?.change === "removed").length;
        summaryParts.push(element(documentRef, "span", { className: "rsp-audit-summary-separator", text: "·" }));
        summaryParts.push(element(documentRef, "span", {
          className: "rsp-audit-change-count",
          text: entry.paired.length || entry.notes.length
            ? `附件新增 ${addedCount} 个、移除 ${removedCount} 个`
            : (entry.summary || `附件新增 ${addedCount} 个、移除 ${removedCount} 个`),
        }));
      }
      if (hasDetails) {
        summaryParts.push(element(documentRef, "button", {
          type: "button",
          className: "rsp-audit-detail-toggle",
          text: expanded ? "收起详情" : "查看变更详情",
          "aria-expanded": expanded ? "true" : "false",
          onClick: () => {
            if (expandedAuditIds.has(auditId)) expandedAuditIds.delete(auditId);
            else expandedAuditIds.add(auditId);
            renderAuditBody(items, total);
          },
        }));
      } else if (!hasDetails && !entry.hasStructuredAuditData) {
        summaryParts.push(element(documentRef, "div", {
          className: "rsp-audit-summary-line rsp-audit-summary-legacy",
          text: entry.summary,
        }));
      }
      const row = element(documentRef, "tr", { className: expanded ? "is-expanded" : "" }, [
        element(documentRef, "td", { text: formatDisplayDateTime(item?.occurred_at) || item?.occurred_at || "—" }),
        element(documentRef, "td", { text: item?.operator_display_name_snapshot || item?.operator_username_snapshot || "—" }),
        element(documentRef, "td", { className: "rsp-audit-summary" }, [
          element(documentRef, "div", { className: "rsp-audit-summary-content" }, summaryParts),
        ]),
      ]);
      auditBody.append(row);
      if (expanded) {
        auditBody.append(element(documentRef, "tr", { className: "rsp-audit-detail-row" }, [
          element(documentRef, "td", { colspan: "3" }, [
            renderAuditDetail(documentRef, entry, copyAuditScript, openImageLightbox, auditAttachmentOptions),
          ]),
        ]));
      }
    });
  }
  async function loadAudit(requestedPage = 1) {
    if (creating) return;
    const page = Math.max(1, Number(requestedPage) || 1);
    try {
      const response = await actions.audit(current.id, { page, page_size: 10 });
      const data = response?.data || response || {};
      const total = Number(data.total) || 0;
      const totalPages = Math.max(1, Number(data.total_pages) || 0);
      let nextPage = Math.max(1, Number(data.page) || page);
      if (nextPage > totalPages) {
        if (page !== totalPages) {
          await loadAudit(totalPages);
          return;
        }
        nextPage = totalPages;
      }
      const items = data.items || [];
      auditPage = nextPage;
      auditTotalPages = totalPages;
      expandedAuditIds.clear();
      renderAuditBody(items, total);
      syncAuditPager();
    } catch (error) {
      if (error?.name !== "AbortError") options.notify("操作记录加载失败", "error");
    }
  }

  const copyScript = async () => {
    try {
      await copyTextToClipboard(documentRef, fields.script.value);
      options.notify("脚本已复制；系统不会执行该脚本", "success");
    } catch (_) {
      options.notify("复制失败，请手动选择脚本文本", "error");
      fields.script.focus();
      fields.script.select();
    }
  };

  // 处理脚本：随上方配置实时自动生成（debounce），仅保存留痕，绝不执行。
  // AUTO：脚本只读，配置有效变化后自动刷新；MANUAL：允许手工编辑并暂停自动覆盖。
  let scriptMode = "AUTO";
  let generatedScriptText = fields.script.value || "";
  let autoGenerateTimer = null;
  let autoGenerateRef = null;
  const SCRIPT_DEBOUNCE_MS = 400;
  const copyScriptButton = actionButton(documentRef, "复制脚本", "rsp-button-secondary", copyScript, true);
  // 模式切换只在下方注册一个 click 监听，避免一次点击先进入 MANUAL 又立即恢复 AUTO。
  const manualEditButton = actionButton(
    documentRef, "手动编辑", "rsp-button-secondary", null,
    !canEdit || !catalogAvailable || !structuredEditor,
  );
  const scriptHint = element(documentRef, "div", {
    className: "rsp-script-hint",
    role: "status",
    text: "选择处理表后将自动生成脚本",
    hidden: true,
  });
  const scriptModeHint = element(documentRef, "div", {
    className: "rsp-script-mode-hint",
    role: "status",
    text: "手动编辑模式，自动生成已暂停",
    hidden: true,
  });
  function syncScriptActions() {
    const hasText = Boolean(String(fields.script.value || "").trim());
    copyScriptButton.disabled = !hasText;
    manualEditButton.textContent = scriptMode === "MANUAL" ? "恢复自动生成" : "手动编辑";
    manualEditButton.disabled = !canEdit || !catalogAvailable || !structuredEditor;
    scriptHint.hidden = scriptMode !== "AUTO" || hasText;
    scriptModeHint.hidden = scriptMode !== "MANUAL";
    fields.script.readOnly = scriptMode === "AUTO";
  }
  function enterManualScriptMode() {
    clearTimeout(autoGenerateTimer);
    autoGenerateTimer = null;
    scriptMode = "MANUAL";
    syncScriptActions();
    options.notify("手动编辑模式，自动生成已暂停", "info");
  }
  function enterAutoScriptMode() {
    scriptMode = "AUTO";
    autoGenerateScript();
  }
  function scheduleAutoGenerate() {
    if (scriptMode !== "AUTO") return;
    clearTimeout(autoGenerateTimer);
    autoGenerateTimer = setTimeout(() => {
      autoGenerateTimer = null;
      autoGenerateScript();
    }, SCRIPT_DEBOUNCE_MS);
  }
  autoGenerateRef = scheduleAutoGenerate;
  fields.period.addEventListener("change", scheduleAutoGenerate);
  fields.period.addEventListener("input", scheduleAutoGenerate);
  function autoGenerateScript() {
    if (!structuredEditor || scriptMode !== "AUTO") return;
    // 脚本预览与正式保存校验解耦：表/字段刚选中便生成对应片段，
    // 修改内容区域的 validate() 与后端 create/update 校验保持原样。
    const script = buildScriptPreview(
      structuredEditor.getStructured(),
      structuredEditor.getFieldTypes ? structuredEditor.getFieldTypes() : {},
      fields.period?.value || "",
    ).trim();
    generatedScriptText = script;
    fields.script.value = script;
    syncScriptActions();
  }
  async function confirmScriptModeRestore() {
    const confirmModal = documentRef.getElementById?.("confirmModal");
    confirmModal?.classList.add("rsp-confirm-above-record");
    try {
      return await options.confirm(
        "恢复自动生成",
        "恢复自动生成后，当前手工修改的脚本将被覆盖，是否继续？",
        { tone: "warning" },
      );
    } finally {
      // 平台确认框关闭有过渡动画，延后清理可避免退场时重新落到编辑弹窗下层。
      setTimeout(() => {
        confirmModal?.classList.remove("rsp-confirm-above-record");
      }, 220);
    }
  }
  manualEditButton.addEventListener("click", async () => {
    if (scriptMode === "AUTO") {
      enterManualScriptMode();
      return;
    }
    // MANUAL → 恢复自动生成：若脚本被手工修改过，先确认覆盖
    const changed = String(fields.script.value) !== generatedScriptText;
    if (changed && typeof options.confirm === "function") {
      const ok = await confirmScriptModeRestore();
      if (!ok) return;
    }
    enterAutoScriptMode();
  });
  syncScriptActions();

  // 附件区域：新建/可编辑记录使用编辑组件；查看与确认模式使用只读快照。
  const currentAttachments = Array.isArray(current.record_attachments) ? current.record_attachments : [];
  // 抽屉级缩略图 object URL 缓存：编辑区、详情快照与审计双栏共享，关闭时统一释放。
  const thumbCache = new Map();
  const attachmentSection = !confirming && (creating || canEdit)
    ? createRecordAttachmentSection(documentRef, {
      recordId: current.id || null,
      initialAttachments: currentAttachments,
      editable: true,
      limits: catalog?.limits?.record_attachments,
      notify: options.notify,
      fetchAttachment: actions.fetchRecordAttachment,
      previewImage: openAttachmentPreview,
      thumbCache,
    })
    : null;
  const attachmentSnapshot = !attachmentSection && currentAttachments.length
    ? renderRecordAttachmentSnapshot(documentRef, {
      recordId: current.id || null,
      attachments: currentAttachments,
      fetchAttachment: actions.fetchRecordAttachment,
      previewImage: openAttachmentPreview,
      notify: options.notify,
      thumbCache,
    })
    : null;
  const attachmentsSectionNode = attachmentSection
    ? element(documentRef, "section", { className: "rsp-modal-section" }, [attachmentSection.element])
    : (attachmentSnapshot
      ? element(documentRef, "section", { className: "rsp-modal-section" }, [
        element(documentRef, "h3", { text: "附件" }),
        attachmentSnapshot,
      ])
      : null);
  const auditAttachmentOptions = {
    recordId: current.id,
    fetchAttachment: actions.fetchRecordAttachment,
    previewImage: openAttachmentPreview,
    notify: options.notify,
    thumbCache,
  };
  function closeWithCleanup() {
    attachmentSection?.destroy();
    const view = documentRef?.defaultView || globalThis;
    thumbCache.forEach((url) => {
      try {
        view.URL?.revokeObjectURL?.(url);
      } catch (_) {}
    });
    thumbCache.clear();
    onClose();
  }

  const closeButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-modal-close",
    text: "×",
    "aria-label": "关闭",
    onClick: closeWithCleanup,
  });
  const header = element(documentRef, "header", { className: "rsp-modal-head" }, [
    element(documentRef, "h2", { text: title }),
  ]);
  // 处理编号为系统生成的只读元信息：仅在已有编号时展示在“基本信息”标题行右侧，
  // 新建/编号为空时整个区域不渲染，不保留空白占位。
  const recordNoText = String(current.record_no || "").trim();
  const copyRecordNo = async () => {
    try {
      await copyTextToClipboard(documentRef, recordNoText);
      options.notify("处理编号已复制", "success");
    } catch (_) {
      options.notify("复制失败，请手动选择编号", "error");
    }
  };
  const basicTitle = element(documentRef, "div", { className: "rsp-section-title" }, [
    element(documentRef, "h3", { text: "基本信息" }),
    recordNoText
      ? element(documentRef, "div", { className: "rsp-record-no-meta" }, [
        element(documentRef, "span", { className: "rsp-record-no-label", text: "处理编号：" }),
        element(documentRef, "span", { className: "rsp-record-no-value", text: recordNoText }),
        element(documentRef, "button", {
          type: "button",
          className: "rsp-record-no-copy",
          text: "复制",
          "aria-label": "复制处理编号",
          onClick: copyRecordNo,
        }),
      ])
      : null,
  ]);
  const basic = element(documentRef, "section", { className: "rsp-modal-section" }, [
    basicTitle,
    readOnly ? element(documentRef, "div", { className: "rsp-readonly-basic-preview" }, [
      element(documentRef, "div", { className: "rsp-readonly-basic-grid" }, [
        readonlyField(documentRef, "所处报送期", current.report_period),
        readonlyField(documentRef, "处理人", current.handler_display_name_snapshot || current.handler_username_snapshot),
        readonlyField(documentRef, "所属维度", (
          dimensions.find((item) => String(item.code) === String(current.dimension || ""))?.label
            || DIMENSION_LABELS[String(current.dimension || "")]
            || current.dimension
        )),
        readonlyField(documentRef, "所属业务系统", current.business_system_name_snapshot || current.business_system_code),
        readonlyField(documentRef, "数据治理负责人", (
          current.governance_owner_display_name_snapshot
            || current.governance_owner_username_snapshot
        )),
      ]),
      readonlyField(documentRef, "关联报送", (
        Array.isArray(current.report_processes) && current.report_processes.length
          ? current.report_processes.map((item) => item?.name).filter(Boolean).join("；")
          : current.report_process_name_snapshot
      ), "rsp-readonly-related-reports"),
      element(documentRef, "div", { className: "rsp-readonly-summary" }, [
        element(documentRef, "span", { className: "rsp-readonly-info-label", text: "处理摘要" }),
        readonlyTextBlock(documentRef, "处理摘要", current.summary),
      ]),
    ]) : element(documentRef, "div", { className: "rsp-form-grid rsp-form-grid-basic" }, [
      labeledField(documentRef, "关联报送", fields.process.root || fields.process, "rsp-process-field"),
      labeledField(documentRef, "所处报送期", fields.period),
      labeledField(documentRef, "处理人", fields.handler),
      labeledField(documentRef, "所属维度", fields.dimension),
      labeledField(documentRef, "所属业务系统", fields.businessSystem),
      labeledField(documentRef, "数据治理负责人", fields.governanceOwner),
      labeledField(documentRef, "处理摘要", fields.summary, "rsp-span-all rsp-summary-field"),
    ]),
  ]);
  const content = element(documentRef, "section", { className: "rsp-modal-section rsp-special-content-section" }, [
    element(documentRef, "h3", { text: "特殊处理内容" }),
    readOnly ? contentPreview : element(documentRef, "div", { className: "rsp-form-grid rsp-form-grid-basic" }, useStructured ? [
      // 数据源→表→字段→修改前/后均在编辑器内；处理摘要位于基本信息区。
      element(documentRef, "div", { className: "rsp-span-two rsp-sc-field" }, [structuredEditor]),
    ] : [
      element(documentRef, "div", { className: "rsp-span-two rsp-tf-field" }, [tableFieldGroups]),
      element(documentRef, "div", { className: "rsp-span-two rsp-value-pair" }, [
        labeledField(documentRef, "修改前", fields.valueBefore),
        labeledField(documentRef, "修改后", fields.valueAfter),
      ]),
    ]),
  ]);
  const script = element(documentRef, "section", { className: "rsp-modal-section" }, [
    element(documentRef, "div", { className: "rsp-section-title" }, [
      element(documentRef, "h3", { text: "处理脚本" }),
      element(documentRef, "strong", { className: "rsp-script-warning", text: "脚本仅保存留痕，不在系统内执行。" }),
      structuredEditor ? manualEditButton : null,
      copyScriptButton,
    ]),
    scriptHint,
    scriptModeHint,
    readOnly
      ? readonlyTextBlock(documentRef, "处理脚本", fields.script.value, "rsp-readonly-script")
      : fields.script,
  ]);
  fields.script.addEventListener("input", syncScriptActions);
  const audit = element(documentRef, "section", { className: "rsp-modal-section rsp-audit", hidden: creating ? "" : null }, [
    element(documentRef, "h3", { text: "操作记录" }),
    element(documentRef, "div", { className: "rsp-audit-table-wrap" }, [element(documentRef, "table", {}, [
      element(documentRef, "thead", {}, [element(documentRef, "tr", {}, ["操作时间", "操作人", "操作内容"].map((label) => element(documentRef, "th", { text: label })))]),
      auditBody,
    ])]),
    element(documentRef, "div", { className: "rsp-audit-pagination" }, [
      auditPrev,
      auditStatus,
      auditNext,
    ]),
  ]);

  const saveDisabled = !catalogAvailable || !canEdit;
  const footerButtons = [];
  if (confirming) {
    footerButtons.push(actionButton(documentRef, "取消", "rsp-button-secondary", onClose));
    footerButtons.push(actionButton(
      documentRef,
      "源系统已确认",
      "rsp-button-primary",
      confirmSourceSystem,
      !catalogAvailable || !current.can_confirm,
    ));
  } else if (canEdit && current.status !== "completed" && current.status !== "voided") {
    if (creating || current.status === "draft") {
      footerButtons.push(actionButton(documentRef, "保存草稿", "rsp-button-secondary", saveDraft, saveDisabled));
    }
    footerButtons.push(actionButton(documentRef, creating ? "保存记录" : "保存修改", "rsp-button-primary", saveRecord, saveDisabled));
  }
  footerActionButtons.push(...footerButtons);
  const actionBar = element(documentRef, "div", { className: "rsp-modal-actions-bar" }, [
    formHint,
    element(documentRef, "div", { className: "rsp-modal-actions-right" }, footerButtons),
  ]);
  const footerChildren = [];
  if (confirming) {
    confirmNoteInput.addEventListener("input", () => {
      confirmNoteCount.textContent = `${confirmNoteInput.value.length} / ${MAX_CONFIRM_NOTE_CHARS}`;
    });
    footerChildren.push(element(documentRef, "div", {
      className: "rsp-confirm-note",
      onPaste: handleConfirmPaste,
    }, [
      element(documentRef, "div", { className: "rsp-confirm-note-head" }, [
        element(documentRef, "span", { className: "rsp-field-label", text: "确认说明（选填）" }),
        confirmNoteCount,
      ]),
      confirmNoteInput,
      confirmThumbs,
      element(documentRef, "p", {
        className: "rsp-confirm-note-hint",
        text: "可直接粘贴图片，最多 3 张；系统只保存展示，不会解析或执行图片内容。",
      }),
    ]));
  }
  footerChildren.push(conflictBar, actionBar);
  const footer = element(documentRef, "footer", {
    className: confirming ? "rsp-modal-actions rsp-modal-actions--confirm" : "rsp-modal-actions",
  }, footerChildren);
  const body = element(documentRef, "div", { className: "rsp-modal-body" }, [
    basic, content, script, attachmentsSectionNode, audit,
  ]);
  const shell = element(documentRef, "div", {
    className: "rsp-record-modal",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": title,
  }, [closeButton, header, body, footer]);
  const overlay = element(documentRef, "div", {
    className: "rsp-record-modal-overlay",
  }, [shell]);
  overlayNode = overlay;

  overlay.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    if (lightboxNode) {
      closeImageLightbox();
      return;
    }
    closeWithCleanup();
  });
  if (attachmentSection) {
    // 抽屉级粘贴监听：只有剪贴板包含文件时才拦截，纯文字粘贴不受影响。
    overlay.addEventListener("paste", (event) => {
      attachmentSection.handlePaste(event);
    });
  }

  loadAudit(1);
  syncAuditPager();
  return overlay;
}
