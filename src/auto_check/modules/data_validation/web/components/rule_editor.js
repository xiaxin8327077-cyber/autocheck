import { errorMessage, isAbortError } from "../runtime.js";
import { confirmationReadiness, createTestEvidence, hasCapability, ownsResource, reportCategoryCode, targetTableLabel, visibleSql } from "../state.js";
import { button, element, field, input, select, textarea } from "./dom.js";
import { createDialog } from "./dialog.js";

const CHANNEL = "rule-editor";

function context(detail) {
  return { version_no: detail.version_no, content_sha256: detail.content_sha256,
    status: detail.status, current_version_id: detail.current_version_id ?? null };
}

function sameContext(detail, expected) {
  return JSON.stringify(context(detail)) === JSON.stringify(expected);
}

function physicalTable(value, validate = true) {
  const text = String(value || "").trim();
  const name = /[（(]([^（）()]+)[）)]$/.exec(text)?.[1] || text;
  if (validate && !/^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$/.test(name)) throw new Error("请输入有效的表英文名");
  return name;
}

// 只对引号外、最外层 SQL 子句换行；显示格式不进入保存或执行请求。
function displaySql(sql) {
  let depth = 0, last = 0, result = "";
  const tokens = /'(?:[^']|'')*'|"(?:[^"]|"")*"|`[^`]*`|[()]|\b(?:FROM|WHERE|AND|GROUP BY|ORDER BY)\b/gi;
  for (const token of String(sql || "").matchAll(tokens)) {
    if (token[0] === "(") depth++;
    else if (token[0] === ")") depth--;
    else if (!depth && /^[A-Z]/i.test(token[0]) && token.index > 0) {
      result += String(sql).slice(last, token.index).trimEnd() + "\n";
      last = token.index;
    }
  }
  return result + String(sql || "").slice(last);
}

function showSql(v, sql) {
  v.sql.replaceChildren(...displaySql(sql).split("\n").map(line => {
    const row = element("span", { className: "dv-editor-sql-line" });
    let start = 0;
    const tokens = /'(?:[^']|'')*'|"(?:[^"]|"")*"|:[A-Za-z_][A-Za-z0-9_]*|\b(?:SELECT|FROM|WHERE|AND|OR|AS|IN|IS|NOT|NULL|JOIN|ON|CASE|WHEN|THEN|ELSE|END|GROUP|BY|ORDER|SUM|COUNT)\b/gi;
    for (const token of line.matchAll(tokens)) {
      row.append(document.createTextNode(line.slice(start, token.index)));
      const kind = token[0].startsWith("'") ? "string" : token[0].startsWith(":") ? "parameter" : token[0].startsWith('"') ? "identifier" : "keyword";
      row.append(element("span", { className: `dv-sql-${kind}`, text: token[0] }));
      start = token.index + token[0].length;
    }
    row.append(document.createTextNode(line.slice(start) || (line ? "" : " ")));
    return row;
  }));
}

export function createRuleEditor({ state, runtime, api, user, notify, host, onChanged }) {
  let view = null;

  function close() {
    runtime.invalidate(CHANNEL);
    const previous = view;
    view = null;
    previous?.dialog.close();
  }

  function editable(v) {
    return Boolean(v.detail && ownsResource(user, v.detail) && hasCapability(user, "dv.manage"));
  }

  function refreshSources() {
    if (!view?.detail) return;
    const v = view;
    for (const [control, options, fallback] of [
      [v.source, state.sources.map(item => [String(item.id), item.name]), v.detail.source_name],
      [v.category, state.categories.map(item => [String(item.code), item.name]), v.category.value],
    ]) {
      const value = control.value;
      const choices = [...options];
      if (!choices.some(([id]) => id === value)) choices.unshift([value, fallback || value || "未选择"]);
      control.replaceChildren(...choices.map(([id, label]) => {
        const option = element("option", { text: label }); option.value = id; return option;
      }));
      control.value = value;
    }
  }

  function render(v) {
    if (view !== v) return;
    const readOnly = !editable(v);
    const locked = v.busy || readOnly;
    [...v.controls, v.toggle].forEach(control => { control.disabled = locked; });
    v.toggle.classList.toggle("on", v.enabled);
    v.toggle.setAttribute("aria-checked", String(v.enabled));
    v.statusText.textContent = v.enabled ? "已开启" : "已停用";
    v.save.hidden = readOnly;
    v.save.disabled = locked || !v.detail;
    v.save.textContent = v.busy ? "保存中…" : "保存";
    v.cancel.disabled = v.busy;
    v.dialog.closeButton.disabled = v.busy;
    v.form.hidden = !v.detail;
    v.loading.hidden = Boolean(v.detail) || Boolean(v.error);
    v.feedback.hidden = !v.error;
    v.feedback.textContent = v.error || "";
    v.dialog.setTitle(v.detail && readOnly ? "查看校验规则" : "编辑校验规则");
  }

  function read(v, validate = true) {
    const name = v.name.value.trim();
    if (validate && !name) throw new Error("请输入规则名称");
    if (validate && (!v.source.value || !v.category.value)) throw new Error("请选择数据源和报送分类");
    return { name, description: v.description.value.trim(), source_id: v.source.value,
      report_category: v.category.value, tables: v.tables.map(item => physicalTable(item.control.value, validate)) };
  }

  function currentVersion(v) {
    return v.detail.status === "enabled" && v.detail.version_id != null
      && Number(v.detail.version_id) === Number(v.detail.current_version_id);
  }

  async function save(v) {
    if (view !== v || v.busy || !editable(v)) return;
    let values;
    values = read(v, false);
    let changed = JSON.stringify(values) !== v.baseline;
    const needsActivation = v.enabled && (changed || !currentVersion(v) || v.pending);
    try { if (changed || needsActivation) read(v); } catch (error) { v.error = errorMessage(error); render(v); return; }
    if (needsActivation && (!hasCapability(user, "dv.test") || !hasCapability(user, "dv.confirm"))) {
      v.error = "保存并开启需要校验测试和确认启用权限，请联系管理员分配权限。"; render(v); return;
    }
    v.busy = true; v.error = ""; render(v);
    const token = runtime.next(CHANNEL);
    const valid = () => view === v && runtime.current(token);
    const request = invoke => runtime.request(token, invoke);
    let wrote = false;
    try {
      const latest = await request(signal => api.rule(v.id, { signal }));
      if (!valid()) return;
      const expected = v.pending ? { ...context(v.detail),
        version_no: v.pending.receipt.version_no, content_sha256: v.pending.receipt.content_sha256 } : context(v.detail);
      if (!sameContext(latest, expected)) {
        throw new Error("规则版本或状态已变化，请关闭后重新打开编辑界面。");
      }
      v.detail = latest;
      if (v.pending) {
        v.baseline = JSON.stringify(v.pending.values);
        v.pending = null;
        showSql(v, visibleSql(latest) || "SQL 参数暂无法完整还原。");
        wrote = true;
        changed = JSON.stringify(values) !== v.baseline;
      }
      if (changed) {
        const definition = structuredClone(latest.definition);
        Object.assign(definition, { name: values.name, description: values.description,
          source_id: values.source_id, report_category: values.report_category });
        const sourceChanged = String(latest.definition.source_id) !== values.source_id;
        for (const [index, item] of v.tables.entries()) {
          const table = values.tables[index];
          const before = item.kind === "base" ? definition : definition[item.kind];
          if (sourceChanged || table !== before.table_name) {
            const metadata = await request(signal => api.describe(values.source_id, table, { signal }));
            if (!valid()) return;
            // 文档绑定规则保存时由服务端核验 doc-v…；物理列哈希不能替换文档版本。
            if (item.kind === "base" && !String(definition.mapping_version || "").startsWith("doc-v")) {
              definition.mapping_version = metadata.mapping_version || "";
            }
            else if (item.kind === "join") definition.related_columns = metadata.columns || [];
          }
          before.table_name = table;
        }
        const source = state.sources.find(item => String(item.id) === values.source_id);
        if (source) definition.dialect = source.dialect;
        const saved = await request(signal => api.save({ ...definition, expected_rule: context(latest) }, v.id, { signal }));
        if (!valid()) return;
        wrote = true;
        v.pending = { receipt: saved, values };
        const detail = await request(signal => api.rule(v.id, { signal }));
        if (!valid()) return;
        if ((saved.content_sha256 && saved.content_sha256 !== detail.content_sha256)
            || (saved.version_no && Number(saved.version_no) !== Number(detail.version_no))) {
          throw new Error("保存后的规则版本已变化，请重新打开编辑界面核对。");
        }
        v.detail = detail;
        v.baseline = JSON.stringify(values);
        v.pending = null;
        showSql(v, visibleSql(detail) || "SQL 参数暂无法完整还原。");
      }
      if (v.enabled && !currentVersion(v)) {
        const detail = v.detail;
        if (!detail.sql_text) throw new Error("规则尚无可用 SQL，请核对相关表及规则说明。");
        const result = await request(signal => api.test(v.id, { version_no: detail.version_no }, { signal }));
        if (!valid()) return;
        // 新协议回传版本证据时必须匹配，不能把不同版本的结果重新贴上当前哈希。
        if ((result.content_sha256 && result.content_sha256 !== detail.content_sha256)
            || (result.version_no && Number(result.version_no) !== Number(detail.version_no))) {
          throw new Error("校验结果对应的版本已变化，请重新保存。");
        }
        const readiness = confirmationReadiness(detail, createTestEvidence(detail, result));
        if (!readiness.ready) throw new Error(readiness.reasons.join("；"));
        await request(signal => api.confirm(v.id, { version_no: detail.version_no, expected_hash: detail.content_sha256,
          expected_rule: context(detail) }, { signal }));
        if (!valid()) return;
        wrote = true;
      } else if (!v.enabled && v.detail.status === "enabled") {
        await request(signal => api.disable(v.id, { signal, expected_rule: context(v.detail) }));
        if (!valid()) return;
        wrote = true;
      }
      if (wrote) {
        try { await onChanged?.(); } catch { if (valid()) notify("规则已保存，请刷新列表查看最新状态。", "warning"); }
      }
      if (!valid()) return;
      notify(v.enabled ? "规则已保存并开启" : v.detail.status === "draft" ? "修改已保存，规则保持关闭" : "规则已保存并停用", "success");
      close();
    } catch (error) {
      if (!valid() || isAbortError(error)) return;
      v.error = `${wrote ? "修改已保存，状态更新未完成；请重试保存。" : ""}${errorMessage(error)}`;
      if (wrote) await onChanged?.();
    } finally {
      if (valid()) { v.busy = false; render(v); }
    }
  }

  async function open(ruleId) {
    close();
    const v = { id: Number(ruleId), detail: null, busy: false, enabled: false, error: "", tables: [] };
    view = v;
    v.dialog = createDialog({ host, title: "编辑校验规则", className: "dv-rule-editor", onClose: () => {
      if (view === v) { runtime.invalidate(CHANNEL); view = null; }
    }, onError: message => { v.error = message; render(v); } });
    const bind = v.dialog.bind;
    v.name = input(); v.source = select(); v.category = select(); v.description = textarea({ rows: 2 });
    const tables = element("div", { className: "dv-editor-tables" });
    v.sql = element("pre", { className: "dv-editor-sql", attrs: { role: "textbox", "aria-label": "SQL", "aria-readonly": "true", tabindex: "0" } });
    v.toggle = button("", { className: "user-enable-switch dv-editor-switch", ariaLabel: "开启校验规则" });
    v.toggle.setAttribute("role", "switch");
    v.toggle.setAttribute("aria-checked", "false");
    bind(v.toggle, "click", () => { if (!v.busy && editable(v)) { v.enabled = !v.enabled; render(v); } });
    v.statusText = element("span", { text: "已停用" });
    v.controls = [v.name, v.source, v.category, v.description];
    v.form = element("div", { className: "dv-editor-form", hidden: true }, field("规则名称", v.name),
      element("div", { className: "dv-editor-source-row" }, field("数据源", v.source), field("报送分类", v.category)),
      field("相关表", tables), field("规则说明", v.description), field("SQL", v.sql),
      field("状态", element("span", { className: "dv-editor-status" }, v.toggle, v.statusText)));
    v.loading = element("p", { className: "dv-muted", text: "正在读取规则…" });
    v.feedback = element("div", { className: "dv-feedback is-error", hidden: true, attrs: { role: "alert" } });
    v.save = button("保存", { className: "dv-button dv-button-primary", capability: "dv.manage" });
    v.cancel = button("取消");
    bind(v.save, "click", () => save(v));
    bind(v.cancel, "click", () => { if (!v.busy) close(); });
    v.dialog.body.append(v.loading, v.form, v.feedback);
    v.dialog.footer.append(v.cancel, v.save);
    render(v);
    const token = runtime.next(CHANNEL);
    try {
      const detail = await runtime.request(token, signal => api.rule(v.id, { signal }));
      if (view !== v || !runtime.current(token)) return;
      v.detail = detail;
      const definition = detail.definition;
      v.name.value = definition.name || detail.name || "";
      v.description.value = definition.description || "";
      for (const [control, value] of [[v.source, String(definition.source_id || "")], [v.category, reportCategoryCode(definition.report_category)]]) {
        const option = element("option", { text: value }); option.value = value;
        control.append(option); control.value = value;
      }
      v.enabled = detail.status === "enabled";
      const summary = state.rules.items.find(item => Number(item.id) === v.id) || {};
      const addTable = (kind, table, label = "") => {
        if (!table?.table_name) return;
        const control = input({ value: targetTableLabel({ ...table, table_name_cn: table.table_name_cn || label }) });
        control.setAttribute("aria-label", v.tables.length ? `相关表 ${v.tables.length + 1}` : "相关表");
        tables.append(control); v.tables.push({ kind, control }); v.controls.push(control);
      };
      addTable("base", definition, summary.table_name_cn);
      addTable("join", definition.join);
      if (definition.project_context?.mode === "lookup") addTable("project_context", definition.project_context);
      showSql(v, visibleSql(detail) || "尚无可用 SQL");
      refreshSources();
      v.baseline = JSON.stringify(read(v, false));
      render(v);
    } catch (error) {
      if (view === v && runtime.current(token) && !isAbortError(error)) {
        v.error = `读取规则失败：${errorMessage(error)}`; render(v);
      }
    }
  }

  return { open, close, refreshSources };
}
