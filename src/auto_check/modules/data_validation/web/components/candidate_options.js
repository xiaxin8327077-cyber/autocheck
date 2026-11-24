import { button, element } from "./dom.js";
import { hasComparison } from "../comparisons.js";
import { candidateRuleName, candidateFiltersText } from "./ai_candidate.js";
import { documentEvidence, tableLabel } from "./candidate_evidence.js";

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

export function createCandidateOptionsPanel({
  listen, onToggle, onActive, onSaveSelected,
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
  let expandedId = "";
  let expansionAnimation = null;
  return {
    element: root,
    get selectedIds() { return [...selectedIds]; },
    getCardEl(id) { return cardElements.get(String(id)) || null; },
    getSlotEl(id) { return slotElements.get(String(id)) || null; },
    animateExpanded(id) {
      const next = String(id || "");
      if (next === expandedId) return;
      expandedId = next;
      expansionAnimation?.cancel();
      expansionAnimation = null;
      const content = slotElements.get(next)?.children[0];
      if (content?.animate) {
        expansionAnimation = content.animate([
          { opacity: 0, transform: "translateY(4px)" },
          { opacity: 1, transform: "translateY(0)" },
        ], { duration: 160, easing: "ease-out" });
      }
    },
    update(payload, { selected = [], activeId = "", savedRules = [], saving = false, locked = false, savedDuplicate = false, hideSave = false } = {}) {
      const options = Array.isArray(payload?.candidate_options) ? payload.candidate_options : [];
      const parallel = payload?.parallel_checks === true;
      const bySelection = options.length > 0 && options.every((item) => item.fromSelection);
      const hasRecommendation = !parallel && !bySelection && options.filter((item) => item.recommended).length === 1;
      const showCategory = new Set(options.map(({ candidate }) => candidate?.report_category || "")).size > 1;
      title.textContent = bySelection ? "按已选口径生成的方案" : parallel ? "已拆分为独立检查项" : "可选校验方案";
      selectedIds = [...new Set(selected)].filter((id) => options.some((item) => item.id === id));
      root.hidden = !options.length;
      list.replaceChildren();
      const selectedSet = new Set(selectedIds);
      options.forEach((option) => {
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
        const candidate = option.candidate || {};
        const summary = hasComparison(candidate.expression) ? candidateRuleName(candidate) : option.label || option.field_label || "校验方案";
        check.setAttribute("aria-label", `选择方案 ${[tableLabel(candidate, option), summary].filter(Boolean).join(" · ")}`);
        check.dataset.optionId = String(option.id);
        listen(check, "click", (event) => { event?.stopPropagation?.(); });
        listen(check, "change", () => { if (!check.disabled) onToggle?.(option.id, check.checked); });
        const badges = [
          option.supplemental ? element("span", { className: "dv-ai-option-recommended", text: "补充规则" }) : null,
          hasRecommendation && option.recommended && !option.fromSelection ? element("span", { className: "dv-ai-option-recommended", text: "推荐" }) : null,
          option.id === activeId ? element("span", { className: "dv-ai-option-current", text: "当前查看" }) : null,
        ].filter(Boolean);
        const title = element("div", { className: "dv-ai-option-title" },
          element("strong", { text: summary }),
          badges.length ? element("span", { className: "dv-ai-option-badges" }, badges) : null);
        const name = tableLabel(candidate, option);
        const sameNameAcrossTables = name && name !== candidate.table_name && options.some((other) =>
          other.candidate?.table_name && other.candidate.table_name !== candidate.table_name && tableLabel(other.candidate, other) === name);
        const source = [sameNameAcrossTables ? `${name}（${candidate.table_name}）` : name, candidate.grain || option.grain,
          showCategory ? candidate.report_category_name || candidate.report_category || "未分类" : ""].filter(Boolean).join(" · ");
        const filters = candidateFiltersText(candidate);
        const body = element("div", { className: "dv-ai-option-body" }, title,
          source ? element("div", { className: "dv-ai-option-table", text: `检查对象：${source}` }) : null,
          filters ? element("div", { className: "dv-ai-option-field", text: `适用范围：${filters}` }) : null);
        const evidence = documentEvidence(candidate, option);
        body.append(evidence);
        if (!option.fromSelection && (option.match_reason || option.differences?.length)) {
          body.append(element("details", { className: "dv-ai-reasoning" },
            element("summary", { text: "方案说明" }), ...[option.match_reason, ...(option.differences || [])]
              .filter(Boolean).map((text) => element("div", { text }))));
        }
        const actions = element("div", { className: "dv-ai-option-actions" },
          button("查看此方案", { listen, className: "dv-button dv-button-plain", onClick: () => { if (!locked) onActive?.(option.id); } }));
        Array.from(actions.children).forEach((control) => listen(control, "click", (event) => { event?.stopPropagation?.(); }));
        const slot = element("div", { className: "dv-ai-option-detail-slot", hidden: true });
        card.append(check, body, actions, slot);
        cardElements.set(String(option.id), card);
        slotElements.set(String(option.id), slot);
        listen(card, "click", (event) => {
          if (locked) return;
          for (let target = event?.target; target && target !== card; target = target.parentNode) {
            if (target === slot || ["DETAILS", "SUMMARY", "INPUT", "BUTTON", "A", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
          }
          onActive?.(option.id);
        });
        listen(card, "keydown", (event) => {
          if (locked || event?.target !== card) return;
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
