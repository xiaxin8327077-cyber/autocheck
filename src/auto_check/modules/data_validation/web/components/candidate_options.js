import { button, element } from "./dom.js";

function newRequestKey() {
  const cryptoRef = globalThis.crypto;
  if (cryptoRef?.randomUUID) return cryptoRef.randomUUID();
  if (cryptoRef?.getRandomValues) {
    const bytes = cryptoRef.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((item) => item.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  throw new Error("当前环境不支持安全随机数");
}

export function createRequestKeyRegistry() {
  let current = newRequestKey();
  let currentFingerprint = null;
  let savedFingerprint = null;
  return {
    get() { return current; },
    fingerprint(next) {
      if (currentFingerprint === next) return current;
      current = newRequestKey();
      currentFingerprint = next;
      return current;
    },
    markSaved() { savedFingerprint = currentFingerprint; },
    isSaved() { return savedFingerprint !== null && savedFingerprint === currentFingerprint; },
    refresh() { current = newRequestKey(); currentFingerprint = null; return current; },
  };
}

function shortObjectLabel(label) {
  return String(label || "")
    .replace(/\.ktr\b/gi, "")
    .replace(/（[^）]*ktr[^）]*）/gi, "")
    .replace(/\([^)]*ktr[^)]*\)/gi, "")
    .trim() || "—";
}

function labelledIdentifier(label, identifier) {
  const text = String(label || "").trim();
  const id = String(identifier || "").trim();
  const mentioned = (text.match(/[A-Za-z_][A-Za-z0-9_$]*/g) || []).some((item) => item === id);
  return !id || mentioned ? (text || id || "—") : `${text || "—"}（${id}）`;
}

export function createCandidateOptionsPanel({
  listen, onToggle, onActive, onSaveOption, onSaveSelected,
} = {}) {
  const root = element("section", { className: "dv-ai-options", hidden: true });
  const title = element("h2", { className: "dv-ai-options-title", text: "发现多个有依据的校验方案" });
  const list = element("div", { className: "dv-ai-option-list" });
  const saveButton = button("保存所选 0 条草稿", {
    listen, className: "dv-button dv-button-plain dv-ai-options-save", onClick: () => onSaveSelected?.(),
  });
  const saved = element("div", { className: "dv-ai-saved-results" });
  const suggestions = element("section", { className: "dv-ai-suggestions", hidden: true });
  root.append(title, list, saveButton, saved, suggestions);
  const cardElements = new Map();
  const slotElements = new Map();
  let selectedIds = [];
  return {
    element: root,
    get selectedIds() { return [...selectedIds]; },
    getCardEl(id) { return cardElements.get(String(id)) || null; },
    getSlotEl(id) { return slotElements.get(String(id)) || null; },
    update(payload, { selected = [], activeId = "", savedRules = [], saving = false, locked = false, gates = {}, savedDuplicate = false, hideSave = false } = {}) {
      const options = Array.isArray(payload?.candidate_options) ? payload.candidate_options : [];
      const parallel = payload?.parallel_checks === true;
      title.textContent = parallel ? "已拆分为独立检查项" : "发现多个有依据的校验方案";
      selectedIds = [...new Set(selected)].filter((id) => options.some((item) => item.id === id));
      root.hidden = !options.length;
      list.replaceChildren();
      const selectedSet = new Set(selectedIds);
      options.forEach((option) => {
        const gate = gates[option.id] || { enabled: false, reasons: [] };
        const card = element("div", {
          className: `dv-ai-option-card${option.id === activeId ? " is-active" : ""}${selectedSet.has(option.id) ? " is-selected" : ""}`,
          attrs: {
            role: "button", tabindex: "0", "aria-pressed": option.id === activeId ? "true" : "false",
            "data-option-id": String(option.id),
          },
        });
        const check = element("input");
        check.type = "checkbox";
        check.className = "dv-ai-option-check";
        check.checked = selectedSet.has(option.id);
        check.disabled = locked;
        check.setAttribute("aria-label", `选择方案 ${option.label || option.id}`);
        check.dataset.optionId = String(option.id);
        listen(check, "click", (event) => { event?.stopPropagation?.(); });
        listen(check, "change", () => { if (!check.disabled) onToggle?.(option.id, check.checked); });
        const candidate = option.candidate || {};
        const tableId = candidate.table_name || option.table_id || "";
        const fieldId = candidate.expression?.left || option.field_id || "";
        const title = element("div", { className: "dv-ai-option-title" },
          element("strong", { text: option.label || option.id }),
          !parallel && option.recommended ? element("span", { className: "dv-ai-option-recommended", text: "推荐" }) : null,
          option.id === activeId ? element("span", { className: "dv-ai-option-current", text: "当前查看" }) : null);
        const body = element("div", { className: "dv-ai-option-body" }, title,
          element("div", { className: "dv-ai-option-grain", text: `检查粒度：${option.grain || "待核实"}` }),
          element("div", { className: "dv-ai-option-table", text: `真实表：${labelledIdentifier(shortObjectLabel(option.table_label), tableId)}` }),
          element("div", { className: "dv-ai-option-field", text: `真实字段：${labelledIdentifier(option.field_label, fieldId)}` }),
          element("div", { className: "dv-ai-option-reason", text: `${parallel ? "依据" : "推荐理由"}：${option.match_reason || "—"}` }));
        if (Array.isArray(option.differences) && option.differences.length) {
          body.append(element("div", { className: "dv-ai-option-diff", text: `差异：${option.differences.join("；")}` }));
        }
        const evidence = element("details", { className: "dv-ai-option-evidence" },
          element("summary", { text: "原始文档证据" }));
        evidence.append(element("div", { className: "dv-ai-option-evidence-row", text: `对象：${option.table_label || "—"}` }));
        evidence.append(element("div", { className: "dv-ai-option-evidence-row", text: `字段：${option.field_label || "—"}` }));
        if (candidate.logic) evidence.append(element("div", { className: "dv-ai-option-evidence-row", text: `取数逻辑：${candidate.logic}` }));
        if (candidate.dictionary) evidence.append(element("div", { className: "dv-ai-option-evidence-row", text: `字典：${candidate.dictionary}` }));
        body.append(evidence);
        const actions = element("div", { className: "dv-ai-option-actions" },
          button("查看/完善此方案", { listen, className: "dv-button dv-button-plain", onClick: () => { if (!locked) onActive?.(option.id); } }),
          button(option.id === activeId ? "保存当前方案并启用" : "完善并启用此方案", { listen, className: "dv-button", onClick: () => { if (!locked && gate.enabled) onSaveOption?.(option.id); } }));
        const expanded = option.id === activeId;
        actions.children[1].disabled = locked || !expanded || !gate.enabled;
        actions.children[1].title = !expanded
          ? "展开方案后可启用"
          : (gate.enabled ? "保存该方案为草稿并在测试通过后启用" : (gate.reasons.join("；") || "需先完成测试并通过"));
        Array.from(actions.children).forEach((control) => listen(control, "click", (event) => { event?.stopPropagation?.(); }));
        const slot = element("div", { className: "dv-ai-option-detail-slot", hidden: true });
        card.append(check, body, actions, slot);
        cardElements.set(String(option.id), card);
        slotElements.set(String(option.id), slot);
        listen(card, "click", (event) => {
          const tag = event?.target?.tagName;
          if (tag === "INPUT" || tag === "BUTTON" || tag === "A" || tag === "SELECT" || tag === "TEXTAREA") return;
          if (locked) return;
          onActive?.(option.id);
        });
        listen(card, "keydown", (event) => {
          if (locked) return;
          if (event?.key === "Enter" || event?.key === " ") {
            event?.preventDefault?.();
            onActive?.(option.id);
          }
        });
        list.append(card);
      });
      saveButton.textContent = saving ? "保存中…" : `保存所选 ${selectedSet.size} 条草稿`;
      saveButton.disabled = saving || locked || !selectedSet.size || savedDuplicate;
      saveButton.hidden = hideSave;
      saved.replaceChildren();
      (savedRules || []).forEach((rule) => {
        saved.append(element("div", { className: "dv-ai-saved-item", attrs: { role: "status" } },
          element("span", { text: rule.rule_code || "" }), element("strong", { text: rule.name || "未命名" })));
      });
      const comparison = Array.isArray(payload?.comparison_suggestions) ? payload.comparison_suggestions : [];
      suggestions.replaceChildren();
      suggestions.hidden = !comparison.length;
      if (comparison.length) {
        suggestions.append(element("h3", { className: "dv-ai-suggestion-title", text: "可进一步检查的一致性" }));
        comparison.forEach((item) => suggestions.append(element("div", { className: "dv-ai-suggestion" },
          element("strong", { text: item.title || "" }),
          element("p", { text: item.description || "" }),
          Array.isArray(item.limitations) && item.limitations.length
            ? element("ul", {}, item.limitations.map((text) => element("li", { text })))
            : null)));
      }
    },
  };
}
