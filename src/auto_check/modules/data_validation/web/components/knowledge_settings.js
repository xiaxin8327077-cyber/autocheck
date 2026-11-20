import { errorMessage } from "../runtime.js";
import { button, element, field, input, select, textarea } from "./dom.js";

const SOURCE_OPTIONS = [["", "所有授权数据源（仅公开知识）"], ["监管报送集市", "监管报送集市"], ["监管报表", "监管报表"]];
const SOURCE_GROUPS = [["监管报送集市", "监管报送集市"], ["监管报表", "监管报表"], ["", "公开知识"]];
const KIND_OPTIONS = [["public", "公开监管知识"], ["local", "本地确认口径"]];
const MAX_ENTRIES = 24;
const CHANNEL = "settings-knowledge";

export function createKnowledgeSettings({ runtime, api, listen, canAdmin }) {
  let snapshot = null;
  let saved = "";
  let busy = false;
  const rows = [];
  const draftGroups = sourceGroups();
  const editor = element("div", { className: "dv-knowledge-editor" }, ...[...draftGroups.values()].map((group) => group.node));
  const status = element("p", { className: "dv-inline-status", attrs: { role: "status" } });
  const feedback = element("p", { className: "dv-inline-status", attrs: { role: "status" } });
  const previewPanel = element("div", { className: "dv-knowledge-preview", hidden: true });
  const activePanel = element("details", { className: "dv-knowledge-preview", hidden: true });
  const controls = { capability: "dv.admin", listen };
  const add = button("新增条目", { ...controls, onClick: () => {
    const row = addEntry({}, true);
    row?.fields.topic.focus?.();
    changed();
  } });
  const preview = button("预览草稿", { ...controls, onClick: showPreview });
  const save = button("保存知识草稿", { ...controls, className: "dv-button dv-button-primary", onClick: saveDraft });
  const enable = button("启用已保存草稿", { ...controls, onClick: () => activate(true) });
  const disable = button("停用业务知识", { ...controls, onClick: () => activate(false) });
  const reload = button("重新读取并丢弃未保存编辑", { ...controls, onClick: () => refresh(true) });
  const section = element("section", { className: "dv-page-section dv-knowledge-settings", hidden: !canAdmin },
    element("div", { className: "dv-page-section-heading" }, element("h2", { text: "信托业务知识" })),
    element("p", { className: "dv-muted", text: "启用后，系统按术语、数据源和适用期间匹配条目，并把摘要自动加入选表和规则生成的提示词。请仅维护获准发送给所选模型的业务口径。" }),
    status, activePanel, editor,
    element("div", { className: "dv-filter-actions" }, add, preview, save, enable, disable, reload),
    feedback, previewPanel);

  function sourceGroups() {
    return new Map(SOURCE_GROUPS.map(([source, label]) => {
      const list = element("div", { className: "dv-knowledge-group-entries" });
      const node = element("section", { className: "dv-knowledge-group", dataset: { knowledgeSource: source }, hidden: true },
        element("h3", { className: "dv-knowledge-group-title", text: label }), list);
      return [source, { node, list }];
    }));
  }

  function placeEntry(groups, source, entry) {
    const group = groups.get(source) || groups.get("");
    if (entry.parentNode !== group.list) group.list.append(entry);
    group.node.hidden = false;
  }

  function entryHeading(topic, sourceName) {
    const title = element("strong", { text: topic || "新条目" });
    const source = element("span", { className: "dv-muted", text: sourceName || "所有授权数据源" });
    const heading = element("summary", { className: "dv-knowledge-heading" },
      element("span", { className: "dv-knowledge-heading-line" }, title, source));
    return { heading, title, source };
  }

  function addEntry(entry, open = false) {
    if (rows.length >= MAX_ENTRIES) return;
    const fields = {
      kind: select(KIND_OPTIONS, { value: entry.kind || "public" }),
      topic: input({ value: entry.topic }),
      source_name: select(SOURCE_OPTIONS, { value: entry.source_name || "" }),
      keywords: input({ value: (entry.keywords || []).join("、"), placeholder: "如：实收、合同汇总" }),
      valid_from: input({ type: "date", value: entry.valid_from }),
      valid_to: input({ type: "date", value: entry.valid_to }),
      reference: input({ value: entry.reference, placeholder: "公开资料 HTTPS 链接 / 本地口径依据" }),
      summary: textarea({ value: entry.summary, rows: 3 }),
    };
    fields.topic.maxLength = 80;
    fields.reference.maxLength = 240;
    fields.summary.maxLength = 500;
    fields.keywords.maxLength = 200;
    const remove = button("移除此条", { className: "dv-button dv-button-plain is-danger", capability: "dv.admin" });
    const { heading, title, source } = entryHeading(entry.topic, entry.source_name);
    const node = element("details", { className: "dv-knowledge-entry" }, heading,
      element("div", { className: "dv-knowledge-body" },
        element("div", { className: "dv-form-grid" }, field("知识类型", fields.kind), field("主题", fields.topic),
          field("适用数据源", fields.source_name), field("匹配词（最多 8 个）", fields.keywords),
          field("适用起日（可空）", fields.valid_from), field("适用止日（可空）", fields.valid_to)),
        field("来源或依据", fields.reference), field("摘要（最多 500 字）", fields.summary), remove));
    node.open = open;
    const row = { node, fields, remove, title, source, dispose: listen(remove, "click", () => {
      if (!canAdmin || busy) return;
      rows.splice(rows.indexOf(row), 1);
      row.dispose?.();
      node.remove();
      changed();
    }) };
    rows.push(row);
    placeEntry(draftGroups, fields.source_name.value, node);
    return row;
  }

  function entries() {
    return rows.map(({ fields }) => ({
      ...Object.fromEntries(Object.entries(fields).map(([name, item]) => [name, item.value.trim()])),
      keywords: fields.keywords.value.split(/[、，,;；\n]+/).map((item) => item.trim()).filter(Boolean),
    }));
  }

  function dirty() { return JSON.stringify(entries()) !== saved; }

  function sync() {
    const locked = !canAdmin || !snapshot || busy;
    rows.forEach((row) => {
      Object.values(row.fields).forEach((control) => { control.disabled = locked; });
      row.remove.disabled = locked;
    });
    add.disabled = locked || rows.length >= MAX_ENTRIES;
    preview.disabled = locked;
    save.disabled = locked || (snapshot.revision > 0 && !dirty());
    enable.disabled = locked || !snapshot.revision || dirty() || !rows.length || snapshot.active_revision === snapshot.revision;
    disable.disabled = locked || !snapshot.active_revision || dirty();
    reload.disabled = busy || !canAdmin;
    if (snapshot) {
      status.textContent = `草稿 ${snapshot.revision ? `v${snapshot.revision}` : "未保存"} · `
        + (snapshot.active_revision ? `启用 v${snapshot.active_revision}（${snapshot.active.length} 条）` : "未启用")
        + (dirty() ? " · 有未保存编辑" : "");
    }
  }

  function changed() {
    previewPanel.hidden = true;
    rows.forEach(({ fields, node, title, source }) => {
      title.textContent = fields.topic.value.trim() || "新条目";
      source.textContent = fields.source_name.value || "所有授权数据源";
      const focus = document.activeElement === fields.source_name && node.parentNode !== draftGroups.get(fields.source_name.value)?.list;
      placeEntry(draftGroups, fields.source_name.value, node);
      if (focus) fields.source_name.focus();
    });
    draftGroups.forEach(({ node, list }) => { node.hidden = list.children.length === 0; });
    sync();
  }
  listen(editor, "input", changed);
  listen(editor, "change", changed);

  function summaries(items) {
    const groups = sourceGroups();
    for (const item of items) {
      const entry = element("details", { className: "dv-knowledge-entry" }, entryHeading(item.topic, item.source_name).heading,
        element("div", { className: "dv-knowledge-body" },
          element("p", { text: item.summary }),
          element("p", { className: "dv-muted", text: `适用：${item.valid_from || "不限"} 至 ${item.valid_to || "不限"}` }),
          element("p", { className: "dv-muted", text: `来源：${item.reference}` })));
      placeEntry(groups, item.source_name, entry);
    }
    return [...groups.values()].filter(({ node }) => !node.hidden).map(({ node }) => node);
  }

  function render(result) {
    const entryKey = (entry) => [entry.kind, entry.source_name, entry.topic, entry.valid_from, entry.valid_to].join("\0");
    const expanded = new Set(entries().filter((_, index) => rows[index].node.open).map(entryKey));
    snapshot = result;
    rows.splice(0).forEach((row) => row.dispose?.());
    draftGroups.forEach(({ list }) => list.replaceChildren());
    result.draft.forEach((entry) => addEntry(entry, expanded.has(entryKey(entry))));
    saved = JSON.stringify(entries());
    activePanel.hidden = !result.active_revision;
    activePanel.replaceChildren(element("summary", { text: "查看当前启用版" }), ...summaries(result.active));
    changed();
  }

  async function request(operation, handle, label) {
    if (!canAdmin || busy) return;
    const token = runtime.next(CHANNEL);
    busy = true;
    feedback.textContent = "";
    sync();
    try {
      const result = await runtime.request(token, operation);
      if (runtime.current(token)) handle(result);
    } catch (error) {
      if (runtime.current(token)) feedback.textContent = errorMessage(error, `${label}失败`);
    } finally {
      busy = false;
      sync();
    }
  }

  function refresh(force = false) {
    if (!force && snapshot && dirty()) return;
    return request((signal) => api.knowledge({ signal }), render, "读取知识");
  }
  function showPreview() {
    if (preview.disabled) return;
    return request((signal) => api.previewKnowledge({ entries: entries() }, { signal }), (result) => {
      previewPanel.replaceChildren(element("strong", { text: `草稿预览 · ${result.entries.length} 条（未保存、未启用）` }),
        ...summaries(result.entries));
      previewPanel.hidden = false;
    }, "预览");
  }
  function saveDraft() {
    if (save.disabled) return;
    return request((signal) => api.saveKnowledge({ expected_revision: snapshot.revision, entries: entries() }, { signal }),
      (result) => { render(result); feedback.textContent = "草稿已保存，现有启用版本不变。"; }, "保存知识草稿");
  }
  function activate(enabled) {
    if ((enabled ? enable : disable).disabled) return;
    return request((signal) => api.activateKnowledge({ expected_revision: snapshot.revision, enabled }, { signal }),
      (result) => { render(result); feedback.textContent = enabled ? "知识已启用，仅供后续 AI 分析参考。" : "业务知识已停用。"; },
      enabled ? "启用知识" : "停用知识");
  }
  sync();
  return { section, refresh };
}
