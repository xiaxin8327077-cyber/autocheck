import { element, labeledField, option } from "./dom.js";
import { formatDisplayDateTime } from "./record_table.js";
import { createProcessMultiSelect } from "./process_multi_select.js";

const SUMMARY_MAX_LENGTH = 25;

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
    reports: fields.reports.value.split("\n").map((value) => value.trim()).filter(Boolean),
    summary: fields.summary.value.trim(),
    processing_content: fields.content.value.trim(),
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

export function createRecordDrawer(documentRef, options) {
  const {
    catalog, record, mode, user, catalogAvailable, actions, onClose, onSaved, onConflict,
  } = options;
  const creating = mode === "create";
  const current = record || {};
  const canEdit = creating || Boolean(current.can_edit);
  const title = creating ? "新建报表特殊处理" : (canEdit ? "编辑" : "查看");

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

  const fields = {
    process,
    handler,
    period: element(documentRef, "input", { type: "date", value: current.report_period || options.reportPeriod || "", "aria-label": "所处报送期", disabled: !canEdit }),
    reports: element(documentRef, "textarea", { className: "rsp-reports-input", "aria-label": "涉及报表，每行一项", placeholder: "每行填写一个报表名称", disabled: !canEdit }),
    summary: element(documentRef, "input", {
      value: current.summary || "",
      maxlength: String(SUMMARY_MAX_LENGTH),
      "aria-label": "处理摘要",
      placeholder: `最多 ${SUMMARY_MAX_LENGTH} 个字符`,
      disabled: !canEdit,
    }),
    content: element(documentRef, "textarea", { "aria-label": "特殊处理内容", maxlength: "20000", disabled: !canEdit }),
    script: element(documentRef, "textarea", { className: "rsp-script", "aria-label": "处理脚本", spellcheck: "false", disabled: !canEdit }),
  };
  fields.reports.value = (current.reports || []).map((item) => typeof item === "string" ? item : item.report_name).join("\n");
  fields.content.value = current.processing_content || "";
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
    reports: "涉及报表",
    summary: "处理摘要",
    processing_content: "处理说明",
    processing_script: "处理脚本",
    special_handling_at: "特殊处理时间",
  };
  function resolveControl(fieldName) {
    if (fieldName === "report_process_codes" || fieldName === "report_process_code") return fields.process;
    if (fieldName === "handler_user_id") return fields.handler;
    if (fieldName === "report_period") return fields.period;
    if (fieldName === "processing_content") return fields.content;
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
  const auditBody = element(documentRef, "tbody");
  const auditStatus = element(documentRef, "span", { className: "rsp-audit-page", text: "第 1 / 1 页" });
  let auditPage = 1;
  let auditTotalPages = 1;
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
      auditBody.replaceChildren();
      const items = data.items || [];
      if (!items.length) {
        auditBody.append(element(documentRef, "tr", { className: "rsp-empty-row" }, [
          element(documentRef, "td", {
            className: "rsp-empty",
            colspan: "3",
            text: total ? "本页暂无操作记录" : "暂无操作记录",
          }),
        ]));
      } else {
        items.forEach((item) => {
          const summaryText = item.action_summary || item.action_code || "";
          const summaryLines = String(summaryText).split(/\n+/).map((line) => line.trim()).filter(Boolean);
          const summaryCell = summaryLines.length > 1
            ? element(documentRef, "td", { className: "rsp-audit-summary", title: summaryText }, summaryLines.map((line) => element(documentRef, "div", { className: "rsp-audit-summary-line", text: line })))
            : element(documentRef, "td", { className: "rsp-audit-summary", text: summaryText || "—", title: summaryText || "" });
          auditBody.append(element(documentRef, "tr", {}, [
            element(documentRef, "td", { text: formatDisplayDateTime(item.occurred_at) || item.occurred_at || "—" }),
            element(documentRef, "td", { text: item.operator_display_name_snapshot || item.operator_username_snapshot }),
            summaryCell,
          ]));
        });
      }
      auditPage = nextPage;
      auditTotalPages = totalPages;
      syncAuditPager();
    } catch (error) {
      if (error?.name !== "AbortError") options.notify("操作记录加载失败", "error");
    }
  }

  const copyScript = async () => {
    try {
      await documentRef.defaultView?.navigator?.clipboard?.writeText(fields.script.value || "");
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
      labeledField(documentRef, "涉及报表", fields.reports, "rsp-span-two"),
    ]),
  ]);
  const content = element(documentRef, "section", { className: "rsp-modal-section" }, [
    element(documentRef, "h3", { text: "特殊处理内容" }),
    labeledField(documentRef, "处理摘要", fields.summary, "rsp-stacked"),
    labeledField(documentRef, "处理说明", fields.content, "rsp-stacked"),
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
  if (canEdit && current.status !== "completed" && current.status !== "voided") {
    if (creating || current.status === "draft") {
      footerButtons.push(actionButton(documentRef, "保存草稿", "rsp-button-secondary", saveDraft, saveDisabled));
    }
    footerButtons.push(actionButton(documentRef, creating ? "保存记录" : "保存修改", "rsp-button-primary", saveRecord, saveDisabled));
  }
  const footer = element(documentRef, "footer", { className: "rsp-modal-actions" }, [
    formHint,
    element(documentRef, "div", { className: "rsp-modal-actions-right" }, footerButtons),
  ]);
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

  shell.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  });

  loadAudit(1);
  syncAuditPager();
  return overlay;
}
