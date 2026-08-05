import { element, labeledField, option } from "./dom.js";
import { formatDisplayDateTime } from "./record_table.js";

function nowHandlingAt() {
  const date = new Date();
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return `${local.toISOString().slice(0, 19)}+08:00`;
}

function draftPayload(fields, saveMode, rowVersion, specialHandlingAt) {
  const payload = {
    save_mode: saveMode,
    report_process_code: fields.process.value,
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
  const canAdmin = Boolean(current.can_admin || user?.role === "admin" || user?.is_admin);
  const title = creating ? "新建报表特殊处理" : (current.summary || "报表特殊处理详情");
  const eyebrow = creating ? "数据录入" : (current.record_no || "记录详情");

  const process = element(documentRef, "select", { "aria-label": "关联报送", disabled: !canEdit });
  process.append(option(documentRef, "", "请选择关联报送"));
  const report_processes = catalog?.report_processes || [];
  report_processes.map((item) => process.append(option(documentRef, item.code, item.name)));
  process.value = current.report_process_code || options.activeProcessCode || "";

  const users = catalog?.users || [];
  const handler = element(documentRef, "select", { "aria-label": "处理人", disabled: !canEdit }, [option(documentRef, "", "请选择处理人")]);
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
    summary: element(documentRef, "input", { value: current.summary || "", maxlength: "200", "aria-label": "处理摘要", disabled: !canEdit }),
    content: element(documentRef, "textarea", { "aria-label": "特殊处理内容", maxlength: "20000", disabled: !canEdit }),
    script: element(documentRef, "textarea", { className: "rsp-script", "aria-label": "处理脚本", spellcheck: "false", disabled: !canEdit }),
    reason: element(documentRef, "input", { maxlength: "500", "aria-label": "管理员操作原因", placeholder: "作废或重开时必填" }),
  };
  fields.reports.value = (current.reports || []).map((item) => typeof item === "string" ? item : item.report_name).join("\n");
  fields.content.value = current.processing_content || "";
  fields.script.value = current.processing_script || "";

  function resolveHandlingAt() {
    if (creating) return nowHandlingAt();
    return current.special_handling_at || nowHandlingAt();
  }

  const errorBox = element(documentRef, "div", { className: "rsp-form-error", role: "alert", hidden: "" });
  function showError(error) {
    errorBox.hidden = false;
    errorBox.textContent = error.message || "保存失败，请重试";
    options.notify(errorBox.textContent, "error");
    Object.entries(error.fields || {}).forEach(([fieldName, message]) => {
      const control = fields[fieldName];
      if (control) {
        control.setAttribute("aria-invalid", "true");
        control.setAttribute("title", Array.isArray(message) ? message.join("；") : String(message));
      }
    });
    if (error.refreshRequired) onConflict();
  }
  async function run(operation, successMessage) {
    errorBox.hidden = true;
    try {
      const response = await operation();
      options.notify(successMessage, "success");
      await onSaved(response?.data || response);
    } catch (error) {
      if (error?.name !== "AbortError") showError(error);
    }
  }
  const saveDraft = () => run(
    () => creating
      ? actions.createRecord(draftPayload(fields, "draft", null, resolveHandlingAt()))
      : actions.updateRecord(current.id, draftPayload(fields, "draft", current.row_version, resolveHandlingAt())),
    "草稿已保存",
  );
  const saveRecord = () => run(
    () => creating
      ? actions.createRecord(draftPayload(fields, "record", null, resolveHandlingAt()))
      : actions.updateRecord(current.id, draftPayload(fields, "record", current.row_version, resolveHandlingAt())),
    creating ? "特殊处理记录已创建" : "修改已保存",
  );
  const completeRecord = async () => {
    if (!await options.confirm("确认将该记录标记为已完成吗？")) return;
    await run(() => actions.changeStatus(current.id, { target_status: "completed", row_version: current.row_version, reason: "处理完成" }), "记录已完成");
  };
  const voidRecord = async () => {
    const reason = fields.reason.value.trim();
    if (!reason) { showError(new Error("请输入作废原因")); fields.reason.focus(); return; }
    if (!await options.confirm("确认作废该记录吗？作废后仍保留完整留痕。")) return;
    await run(() => actions.voidRecord(current.id, { row_version: current.row_version, reason }), "记录已作废");
  };
  const reopenRecord = async () => {
    const reason = fields.reason.value.trim();
    if (!reason) { showError(new Error("请输入重开原因")); fields.reason.focus(); return; }
    if (!await options.confirm("确认重开该记录并恢复为待处理吗？")) return;
    await run(() => actions.reopenRecord(current.id, { row_version: current.row_version, reason }), "记录已重开");
  };

  const auditBody = element(documentRef, "tbody");
  const auditStatus = element(documentRef, "span", { className: "rsp-audit-page", text: "第 1 页" });
  let auditPage = 1;
  async function loadAudit(page = 1) {
    if (creating) return;
    try {
      const response = await actions.audit(current.id, { page, page_size: 10 });
      const data = response?.data || response || {};
      auditBody.replaceChildren();
      (data.items || []).forEach((item) => auditBody.append(element(documentRef, "tr", {}, [
        element(documentRef, "td", { text: formatDisplayDateTime(item.occurred_at) || item.occurred_at || "—" }),
        element(documentRef, "td", { text: item.operator_display_name_snapshot || item.operator_username_snapshot }),
        element(documentRef, "td", { text: item.action_summary || item.action_code }),
      ])));
      auditPage = data.page || page;
      auditStatus.textContent = `第 ${auditPage} / ${data.total_pages || 1} 页`;
    } catch (error) {
      if (error?.name !== "AbortError") options.notify("操作留痕加载失败", "error");
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
    element(documentRef, "div", {}, [
      element(documentRef, "span", { className: "rsp-eyebrow", text: eyebrow }),
      element(documentRef, "h2", { text: title }),
    ]),
  ]);
  const basic = element(documentRef, "section", { className: "rsp-modal-section" }, [
    element(documentRef, "h3", { text: "基本信息" }),
    element(documentRef, "div", { className: "rsp-form-grid rsp-form-grid-basic" }, [
      labeledField(documentRef, "关联报送", fields.process),
      labeledField(documentRef, "所处报送期", fields.period),
      labeledField(documentRef, "处理人", fields.handler),
      labeledField(documentRef, "涉及报表", fields.reports, "rsp-span-two"),
      !creating
        ? element(documentRef, "div", { className: "rsp-workflow-state rsp-span-two" }, [
          element(documentRef, "span", { text: "流程状态" }),
          element(documentRef, "strong", { text: "未启用" }),
          element(documentRef, "small", { text: "审批流程将在后续阶段启用" }),
        ])
        : null,
      !creating && canAdmin ? labeledField(documentRef, "操作原因", fields.reason, "rsp-span-two") : null,
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
    element(documentRef, "h3", { text: "操作留痕" }),
    element(documentRef, "div", { className: "rsp-audit-table-wrap" }, [element(documentRef, "table", {}, [
      element(documentRef, "thead", {}, [element(documentRef, "tr", {}, ["操作时间", "操作人", "操作内容"].map((label) => element(documentRef, "th", { text: label })))]),
      auditBody,
    ])]),
    element(documentRef, "div", { className: "rsp-audit-pagination" }, [
      actionButton(documentRef, "上一页", "rsp-button-secondary", () => loadAudit(Math.max(1, auditPage - 1))),
      auditStatus,
      actionButton(documentRef, "下一页", "rsp-button-secondary", () => loadAudit(auditPage + 1)),
    ]),
  ]);

  const saveDisabled = !catalogAvailable || !canEdit;
  const footerButtons = [];
  if (canEdit && current.status !== "completed" && current.status !== "voided") {
    footerButtons.push(actionButton(documentRef, "保存草稿", "rsp-button-secondary", saveDraft, saveDisabled));
    footerButtons.push(actionButton(documentRef, creating ? "保存记录" : "保存修改", "rsp-button-primary", saveRecord, saveDisabled));
  }
  if (!creating && canEdit && ["pending", "processing"].includes(current.status)) {
    footerButtons.push(actionButton(
      documentRef,
      current.status === "pending" ? "开始处理" : "转为待处理",
      "rsp-button-secondary",
      () => run(
        () => actions.changeStatus(current.id, {
          target_status: current.status === "pending" ? "processing" : "pending",
          row_version: current.row_version,
          reason: current.status === "pending" ? "开始处理" : "转回待处理",
        }),
        current.status === "pending" ? "记录已转为处理中" : "记录已转为待处理",
      ),
    ));
    footerButtons.push(actionButton(documentRef, "完成", "rsp-button-success", completeRecord));
  }
  if (!creating && canAdmin && ["draft", "pending", "processing"].includes(current.status)) {
    footerButtons.push(actionButton(documentRef, "作废", "rsp-button-danger", voidRecord));
  }
  if (!creating && canAdmin && ["completed", "voided"].includes(current.status)) {
    footerButtons.push(actionButton(documentRef, "重开", "rsp-button-warning", reopenRecord));
  }
  const footer = element(documentRef, "footer", { className: "rsp-modal-actions" }, footerButtons);
  const body = element(documentRef, "div", { className: "rsp-modal-body" }, [
    errorBox, basic, content, script, audit,
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

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) onClose();
  });
  shell.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  });
  shell.addEventListener("click", (event) => event.stopPropagation());

  loadAudit(1);
  return overlay;
}
