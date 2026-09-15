import { button, labeledControl, node } from "./dom.js";

function input(value = "", { disabled = false, placeholder = "" } = {}) { const control = node("input", { attrs: { value, placeholder } }); control.disabled = disabled; return control; }
function select(options, value, { disabled = false } = {}) { const control = node("select"); control.disabled = disabled; options.forEach(([optionValue, label]) => { const option = node("option", { text: label, attrs: { value: optionValue } }); option.selected = optionValue === value; control.append(option); }); return control; }
function checkbox(checked = false, disabled = false) { const control = node("input", { attrs: { type: "checkbox" } }); control.checked = checked; control.disabled = disabled; return control; }
function focusable(dialog) { return [...dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')]; }

function dialogShell(root, title, trigger) {
  const titleId = `dm-dialog-title-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const overlay = node("div", { className: "dm-dialog-overlay", attrs: { role: "presentation" } });
  const dialog = node("section", { className: "dm-dialog", attrs: { role: "dialog", "aria-modal": "true", "aria-labelledby": titleId, tabindex: "-1" } });
  const heading = node("div", { className: "dm-dialog-heading" });
  heading.append(node("h2", { text: title, attrs: { id: titleId } }));
  const close = () => { dialog.removeEventListener("keydown", onKeydown); overlay.remove(); trigger?.focus?.(); };
  const closeButton = button("关闭", "dm-button dm-button-plain", close);
  heading.append(closeButton); dialog.append(heading); overlay.append(dialog);
  const onKeydown = (event) => {
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (event.key !== "Tab") return;
    const controls = focusable(dialog); if (!controls.length) return;
    const first = controls[0]; const last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  dialog.addEventListener("keydown", onKeydown); root.append(overlay);
  return { dialog, close, focus: () => focusable(dialog).find((element) => element !== closeButton)?.focus?.() || dialog.focus() };
}

function appendActions(dialog, close, primaryText, onSubmit) {
  const actions = node("div", { className: "dm-dialog-actions" });
  const primary = button(primaryText, "dm-button dm-button-primary", async () => {
    if (primary.disabled) return;
    primary.disabled = true;
    try { await onSubmit(); } catch (_error) {} finally { primary.disabled = false; }
  });
  actions.append(button("取消", "dm-button dm-button-secondary", close), primary);
  dialog.append(actions);
  return actions;
}

export function openRegionDialog(root, { onCreate, notify, trigger = document.activeElement }) {
  const shell = dialogShell(root, "新增数据区域", trigger); const { dialog, close } = shell; dialog.classList.add("dm-dialog-create-region");
  const name = input("", { placeholder: "例如：月度监管统计" }); const shape = select([["scalar", "单值"], ["list", "列表"]], "list"); const description = node("textarea", { attrs: { placeholder: "说明该区域的数据口径" } });
  const fieldName = input("", { placeholder: "字段显示名" }); const alias = input("", { placeholder: "stable_field_alias" }); const fieldType = select([["string", "字符串"], ["integer", "整数"], ["decimal", "小数"], ["boolean", "布尔"], ["date", "日期"], ["datetime", "日期时间"]], "string"); const nullable = checkbox();
  const form = node("form", { className: "dm-dialog-form" });
  const descriptionControl = labeledControl("区域说明", description); descriptionControl.classList.add("dm-control-wide");
  form.append(labeledControl("区域名称", name), labeledControl("数据形态", shape), descriptionControl, node("h3", { text: "首批字段" }), labeledControl("显示名", fieldName), labeledControl("稳定别名", alias), labeledControl("字段类型", fieldType), labeledControl("允许空值", nullable));
  const formError = node("p", { className: "dm-field-lock-note", attrs: { role: "alert", hidden: "hidden" } });
  dialog.append(form, formError);
  appendActions(dialog, close, "创建区域", async () => {
    const fields = [{ field_alias: alias.value.trim(), name: fieldName.value.trim(), value_type: fieldType.value, nullable: nullable.checked, enabled: true, description: "", display_order: 10 }];
    const errors = [];
    if (!name.value.trim()) errors.push("请输入区域名称");
    if (!fieldName.value.trim()) errors.push("请输入字段显示名");
    if (!/^[a-z][a-z0-9_]{0,63}$/.test(alias.value.trim())) errors.push("字段别名必须为小写字母开头的 snake_case");
    if (!fields.some((field) => field.enabled)) errors.push("至少需要一个启用字段");
    if (new Set(fields.map((field) => field.field_alias)).size !== fields.length) errors.push("首批字段别名不能重复");
    if (errors.length) { formError.textContent = errors.join("；"); formError.hidden = false; throw new Error("invalid form"); }
    try { await onCreate({ name: name.value.trim(), shape: shape.value, description: description.value.trim(), fields }); close(); } catch (error) { if (error?.message !== "invalid form") { formError.textContent = error?.message || "新增数据区域失败"; formError.hidden = false; } throw error; }
  }); shell.focus();
}

export function openManageRegionDialog(root, { region, onSave, onDelete, notify, trigger = document.activeElement }) {
  const shell = dialogShell(root, "编辑区域", trigger); const { dialog, close } = shell; dialog.classList.add("dm-dialog-region"); const builtIn = Boolean(region.built_in);
  const name = input(region.name || ""); const description = node("textarea"); description.value = region.description || ""; const shape = select([["scalar", "单值"], ["list", "列表"]], region.shape || "list", { disabled: builtIn });
  const nameControl = labeledControl("区域名称", name);
  const descriptionControl = labeledControl("区域说明", description); descriptionControl.classList.add("dm-control-wide");
  const form = node("form", { className: "dm-dialog-form" }); form.append(nameControl, labeledControl(builtIn ? "数据形态（系统固定）" : "数据形态", shape), descriptionControl); dialog.append(form);
  const actions = appendActions(dialog, close, "保存区域", async () => { try { await onSave({ name: name.value.trim(), description: description.value.trim(), row_version: region.row_version, ...(!builtIn ? { shape: shape.value } : {}) }); close(); } catch (_error) {} });
  if (!builtIn && onDelete) actions.prepend(button("删除区域", "dm-button dm-button-danger dm-region-delete", async () => { if (await onDelete(region)) close(); }));
  shell.focus();
}

export function openFieldDialog(root, { field = null, onSave, notify, trigger = document.activeElement }) {
  const shell = dialogShell(root, field ? "管理字段" : "新增字段", trigger); const { dialog, close } = shell; const builtIn = Boolean(field?.built_in);
  const name = input(field?.name || "", { placeholder: "字段显示名" }); const alias = input(field?.alias || field?.field_alias || "", { disabled: Boolean(field), placeholder: "stable_field_alias" }); const type = select([["string", "字符串"], ["integer", "整数"], ["decimal", "小数"], ["boolean", "布尔"], ["date", "日期"], ["datetime", "日期时间"]], field?.value_type || "string", { disabled: builtIn }); const nullable = checkbox(Boolean(field?.nullable), builtIn); const description = node("textarea", { attrs: { placeholder: "字段说明" } }); description.value = field?.description || ""; const enabled = checkbox(field?.enabled !== false); const displayOrder = field?.display_order || 9999;
  const form = node("form", { className: "dm-dialog-form" }); if (builtIn) form.append(node("p", { className: "dm-field-lock-note", text: "内置字段的别名、类型和可空性由系统固定，不能修改。" })); form.append(labeledControl("显示名", name), labeledControl("稳定别名", alias), labeledControl("字段类型", type), labeledControl("允许空值", nullable), labeledControl("字段说明", description), labeledControl("启用字段", enabled)); dialog.append(form);
  appendActions(dialog, close, field ? "保存字段" : "新增字段", async () => { try { await onSave({ name: name.value.trim(), alias: alias.value.trim(), value_type: type.value, nullable: nullable.checked, description: description.value.trim(), display_order: displayOrder, enabled: enabled.checked, ...(field ? { row_version: field.row_version } : {}) }); close(); } catch (_error) {} }); shell.focus();
}

export function renderFieldPanel({ fields, canManage, onCreate, onManage }) {
  const section = node("section", { className: "dm-field-panel dm-config-section" }); const header = node("div", { className: "dm-section-heading" }); header.append(node("div", { className: "dm-section-title", text: "01" }), node("h3", { text: "输出字段" }), button("新增字段", "dm-button dm-button-secondary", onCreate, { disabled: !canManage })); section.append(header);
  const list = node("div", { className: "dm-field-tags" }); fields.forEach((field) => { const status = field.enabled === false ? "（已停用）" : ""; const tag = button(`${field.name} · ${field.alias || field.field_alias}${status}`, "dm-field-tag", () => onManage(field), { disabled: !canManage }); if (field.enabled === false) tag.classList.add("is-disabled"); list.append(tag); }); section.append(list); return section;
}
