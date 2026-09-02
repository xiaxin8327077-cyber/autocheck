import { element, labeledField, option } from "./dom.js";
import { formatDisplayDateTime } from "./record_table.js";
import { createProcessMultiSelect } from "./process_multi_select.js";
import { confirmAttachmentUrl } from "../api.js";

const SUMMARY_MAX_LENGTH = 128;
const FIELD_TEXT_MAX_LENGTH = 128;

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
  const changedFields = item?.changed_fields;
  const hasStructuredAuditData = Boolean(
    changedFields && typeof changedFields === "object" && !Array.isArray(changedFields) && Object.keys(changedFields).length,
  );
  Object.entries(changedFields || {}).forEach(([key, meta]) => {
    if (!meta || typeof meta !== "object") return;
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

  return {
    ...action,
    paired,
    notes,
    attachments,
    recordId: Number(recordId || item?.record_id || 0),
    hasStructuredAuditData,
    status: paired.find((pair) => pair.key === "status") || null,
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

function renderAuditDetail(documentRef, entry, onCopyScript, onOpenImage) {
  const cells = [];
  if (entry.paired.length) {
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
  return element(documentRef, "div", { className: "rsp-audit-detail" }, [
    element(documentRef, "div", {
      className: "rsp-audit-detail-scroll",
      "aria-label": "完整变更对照",
    }, [
      element(documentRef, "div", {
        className: `rsp-audit-diff-grid${hasExtras ? " has-notes" : ""}`,
      }, cells),
    ]),
  ]);
}

function nowHandlingAt() {
  const date = new Date();
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return `${local.toISOString().slice(0, 19)}+08:00`;
}

function draftPayload(fields, saveMode, rowVersion, specialHandlingAt) {
  const payload = {
    save_mode: saveMode,
    report_process_codes: fields.process.value,
    report_period: fields.period.value,
    dimension: fields.dimension.value || null,
    governance_owner_user_id: fields.governanceOwner.value || null,
    summary: fields.summary.value.trim(),
    table_name: fields.tableName.value.trim(),
    field_name: fields.fieldName.value.trim(),
    value_before: fields.valueBefore.value.trim(),
    value_after: fields.valueAfter.value.trim(),
    processing_script: fields.script.value,
    special_handling_at: specialHandlingAt,
    handler_user_id: fields.handler.value,
  };
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

  const fields = {
    process,
    handler,
    dimension,
    governanceOwner,
    period: element(documentRef, "input", { type: "date", value: current.report_period || options.reportPeriod || "", "aria-label": "所处报送期", disabled: !canEdit }),
    summary: element(documentRef, "input", {
      value: current.summary || "",
      maxlength: String(SUMMARY_MAX_LENGTH),
      "aria-label": "处理摘要",
      placeholder: `最多 ${SUMMARY_MAX_LENGTH} 个字符`,
      disabled: !canEdit,
    }),
    tableName: element(documentRef, "input", {
      value: current.table_name || "",
      "aria-label": "处理表名",
      maxlength: String(FIELD_TEXT_MAX_LENGTH),
      disabled: !canEdit,
    }),
    fieldName: element(documentRef, "input", {
      value: current.field_name || "",
      "aria-label": "处理字段名",
      maxlength: String(FIELD_TEXT_MAX_LENGTH),
      disabled: !canEdit,
    }),
    valueBefore: element(documentRef, "input", {
      value: current.value_before || "",
      "aria-label": "修改前",
      maxlength: String(FIELD_TEXT_MAX_LENGTH),
      disabled: !canEdit,
    }),
    valueAfter: element(documentRef, "input", {
      value: current.value_after || "",
      "aria-label": "修改后",
      maxlength: String(FIELD_TEXT_MAX_LENGTH),
      disabled: !canEdit,
    }),
    recordNo: element(documentRef, "input", {
      className: "rsp-readonly-input",
      value: current.record_no || "",
      "aria-label": "处理编号",
      placeholder: creating ? "保存后自动生成" : "",
      disabled: true,
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
  const FIELD_LABELS = {
    report_process_codes: "关联报送",
    report_process_code: "关联报送",
    report_period: "所处报送期",
    handler_user_id: "处理人",
    dimension: "所属维度",
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
  function showFormHint(message, focusControl = null) {
    formHint.hidden = false;
    formHint.textContent = message;
    if (focusControl?.setAttribute) focusControl.setAttribute("aria-invalid", "true");
    focusControl?.focus?.();
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
    if (error.refreshRequired) onConflict();
  }
  async function run(operation, successMessage) {
    clearFormHint();
    try {
      const response = await operation();
      options.notify(successMessage, "success");
      await onSaved(response?.data || response);
    } catch (error) {
      if (error?.name !== "AbortError") showError(error);
    }
  }
  function validateForm() {
    clearFormHint();
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
  const saveDraft = () => {
    if (!validateForm()) return;
    return run(
      () => creating
        ? actions.createRecord(draftPayload(fields, "draft", null, resolveHandlingAt()))
        : actions.updateRecord(current.id, draftPayload(fields, "draft", current.row_version, resolveHandlingAt())),
      "草稿已保存",
    );
  };
  const saveRecord = () => {
    if (!validateForm()) return;
    return run(
      () => creating
        ? actions.createRecord(draftPayload(fields, "record", null, resolveHandlingAt()))
        : actions.updateRecord(current.id, draftPayload(fields, "record", current.row_version, resolveHandlingAt())),
      creating ? "特殊处理记录已创建" : "修改已保存",
    );
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
  function closeImageLightbox() {
    lightboxNode?.remove();
    lightboxNode = null;
  }
  function openImageLightbox(src) {
    if (!overlayNode || !src) return;
    closeImageLightbox();
    const img = element(documentRef, "img", {
      className: "rsp-image-lightbox-img",
      src,
      alt: "确认图片预览",
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
      const hasDetails = entry.paired.length > 0 || entry.notes.length > 0 || entry.attachments.length > 0;
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
      if (entry.paired.length) {
        summaryParts.push(element(documentRef, "span", { className: "rsp-audit-summary-separator", text: "·" }));
        summaryParts.push(element(documentRef, "span", {
          className: "rsp-audit-change-count",
          text: `共 ${entry.paired.length} 项变更`,
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
          element(documentRef, "td", { colspan: "3" }, [renderAuditDetail(documentRef, entry, copyAuditScript, openImageLightbox)]),
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

  const closeButton = element(documentRef, "button", {
    type: "button",
    className: "rsp-modal-close",
    text: "×",
    "aria-label": "关闭",
    onClick: onClose,
  });
  const header = element(documentRef, "header", { className: "rsp-modal-head" }, [
    element(documentRef, "h2", { text: title }),
  ]);
  const basic = element(documentRef, "section", { className: "rsp-modal-section" }, [
    element(documentRef, "h3", { text: "基本信息" }),
    element(documentRef, "div", { className: "rsp-form-grid rsp-form-grid-basic" }, [
      labeledField(documentRef, "关联报送", fields.process.root || fields.process, "rsp-process-field"),
      labeledField(documentRef, "所处报送期", fields.period),
      labeledField(documentRef, "处理人", fields.handler),
      labeledField(documentRef, "所属维度", fields.dimension),
      labeledField(documentRef, "数据治理负责人", fields.governanceOwner),
      labeledField(documentRef, "处理编号", fields.recordNo, "rsp-readonly-field"),
    ]),
  ]);
  const content = element(documentRef, "section", { className: "rsp-modal-section" }, [
    element(documentRef, "h3", { text: "特殊处理内容" }),
    element(documentRef, "div", { className: "rsp-form-grid rsp-form-grid-basic" }, [
      labeledField(documentRef, "处理表名", fields.tableName),
      labeledField(documentRef, "处理字段名", fields.fieldName),
      labeledField(documentRef, "修改前", fields.valueBefore),
      labeledField(documentRef, "修改后", fields.valueAfter),
      labeledField(documentRef, "处理摘要", fields.summary, "rsp-span-cols-2"),
    ]),
  ]);
  const script = element(documentRef, "section", { className: "rsp-modal-section" }, [
    element(documentRef, "div", { className: "rsp-section-title" }, [
      element(documentRef, "h3", { text: "处理脚本" }),
      element(documentRef, "strong", { className: "rsp-script-warning", text: "脚本仅保存留痕，不在系统内执行。" }),
      actionButton(documentRef, "复制脚本", "rsp-button-secondary", copyScript),
    ]),
    fields.script,
  ]);
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
  footerChildren.push(actionBar);
  const footer = element(documentRef, "footer", {
    className: confirming ? "rsp-modal-actions rsp-modal-actions--confirm" : "rsp-modal-actions",
  }, footerChildren);
  const body = element(documentRef, "div", { className: "rsp-modal-body" }, [
    basic, content, script, audit,
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
    onClose();
  });

  loadAudit(1);
  syncAuditPager();
  return overlay;
}
