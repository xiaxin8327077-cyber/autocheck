import { button, element, textarea } from "./dom.js";
import { fieldTarget } from "../comparisons.js";

let panelNumber = 0;

function displayChoice(question, option, dictionaries) {
  const filter = option.selection;
  const field = filter?.field || (fieldTarget(question.id) && !filter ? option.value : "");
  const marker = field ? `（${field}）` : "";
  const index = marker ? option.label.indexOf(marker) : -1;
  const title = index < 0 ? option.label : option.label.slice(0, index).trim() || field;
  const suffix = index < 0 ? "" : option.label.slice(index + marker.length).replace(/^[，,]\s*/, "").trim();
  const entries = dictionaries?.[filter?.table]?.[field];
  const selected = entries && [].concat(filter.value).map((value) => entries.find((entry) => entry.value === value));
  if (!selected?.length || !selected.every(Boolean)) return { title, field, detail: suffix };
  return { title, field, detail: selected.map(({ value, label }) => `${value}＝${label}`).join(" · "),
    dictionaryKey: JSON.stringify([filter.op, selected.map(({ value, label }) => JSON.stringify([value, label])).sort()]) };
}

function hasAnswer(value) {
  if (Array.isArray(value)) return value.length > 0;
  return value != null && (typeof value !== "string" || value.trim() !== "");
}

function isModelSuggestion(option) {
  return option.tag === "模型建议" || option.tag === "模型推荐";
}

export function createBusinessQuestionsPanel({ listen, onConfirm }) {
  const root = element("section", { className: "dv-ai-result dv-business-questions", hidden: true });
  const prefix = "dv-business-question-" + ++panelNumber;
  const progress = element("span", { className: "dv-ai-footer-note", hidden: true, attrs: { role: "status" } });
  const submit = button("确认全部口径", { className: "dv-button dv-button-primary", hidden: true, disabled: true });
  let answers = new Map();
  let groups = [];
  let removers = [];
  let signature, busy, submitting = false;
  let generation = 0;

  function bind(node, event, handler) {
    removers.push(listen(node, event, handler));
  }

  function setVisible(visible) {
    root.hidden = progress.hidden = submit.hidden = !visible;
  }

  function clear() {
    generation++;
    removers.splice(0).forEach((remove) => remove?.());
    root.replaceChildren();
    setVisible(false);
    groups = [];
    answers = new Map();
    submit.disabled = true;
    signature = undefined;
    submitting = busy = false;
  }

  function refresh() {
    const locked = busy || submitting;
    for (const { key, multiple, controls, selectAll } of groups) {
      const current = answers.get(key);
      const selected = (multiple && Array.isArray(current) ? current : [current]).map((value) => JSON.stringify(value));
      let checkedCount = 0;
      for (const { input, row, value } of controls) {
        input.disabled = locked;
        if (!row) continue;
        const checked = selected.includes(JSON.stringify(value));
        input.checked = checked;
        row.classList.toggle("is-selected", checked);
        if (checked) checkedCount++;
      }
      if (selectAll) {
        selectAll.disabled = locked;
        selectAll.checked = checkedCount === controls.length;
        selectAll.indeterminate = checkedCount > 0 && !selectAll.checked;
      }
    }
    const completed = groups.filter(({ key }) => hasAnswer(answers.get(key))).length;
    const status = `已完成 ${completed} / ${groups.length} 项口径`;
    if (progress.textContent !== status) progress.textContent = status;
    submit.disabled = locked || completed < groups.length;
  }

  function update(items, { busy: waiting = false } = {}) {
    if (!items?.length) { clear(); return; }
    const next = JSON.stringify(items);
    if (next === signature) { busy = waiting; refresh(); return; }
    const previous = new Map(groups.map((group) => [group.key, { question: group.question, value: answers.get(group.key) }]));
    clear();
    signature = next;
    busy = waiting;
    root.append(element("h2", { className: "dv-ai-conclusion", text: `有 ${items.length} 个业务口径需要确认` }));
    items.forEach(({ key, question, context, multiple, dictionaries, value: initial }, index) => {
      const options = question.options || [];
      const controls = [];
      const old = previous.get(key);
      let value = old && JSON.stringify(old.question) === JSON.stringify(question) ? old.value : initial;
      if (value === undefined) {
        const recommended = options.filter(isModelSuggestion).map((option) => option.selection ?? option.value);
        value = multiple ? recommended : recommended.length === 1 ? recommended[0] : undefined;
      }
      if (value !== undefined) answers.set(key, value);
      const groupState = { key, question, multiple, controls };
      groups.push(groupState);
      const title = multiple ? question.text.replace(/(采用|使用)哪个/, "$1哪些") : question.text;
      const headingId = `${prefix}-heading-${index}`;
      const header = element("div", { className: "dv-business-heading" },
        element("h3", { className: "dv-field-label", text: title, attrs: { id: headingId } }));
      const group = element("fieldset", { className: "dv-ai-choices dv-business-question", attrs: { "aria-labelledby": headingId } }, header);
      if (context) group.append(element("p", { className: "dv-muted", text: context }));
      if (!options.length) {
        const input = textarea({ rows: 2, value: answers.get(key) ?? "" });
        input.setAttribute("aria-label", question.text);
        bind(input, "input", () => { answers.set(key, input.value); refresh(); });
        controls.push({ input });
        group.append(input);
      } else {
        if (multiple) {
          const selectAll = element("input", { className: "dv-business-select-all" });
          selectAll.type = "checkbox";
          groupState.selectAll = selectAll;
          bind(selectAll, "change", () => {
            answers.set(key, selectAll.checked ? controls.map(({ value }) => value) : []);
            refresh();
          });
          header.append(element("div", { className: "dv-business-tools" },
            element("span", { text: "可多选，按字段分别生成方案" }), element("label", {}, selectAll, "全部都要")));
        }
        const list = element("div", { className: "dv-business-options" });
        const displays = options.map((option) => displayChoice(question, option, dictionaries));
        const common = displays[0].dictionaryKey;
        const shared = displays.length > 1 && common && displays.every(({ dictionaryKey }) => dictionaryKey === common);
        options.forEach((option, i) => {
          const { title: name, field, detail } = displays[i];
          const value = option.selection ?? option.value;
          const input = element("input");
          input.type = multiple ? "checkbox" : "radio";
          input.name = prefix + "-" + index;
          const row = element("label", { className: "dv-ai-choice" }, input,
            element("span", { className: "dv-ai-choice-body" }, element("span", { className: "dv-ai-choice-title", text: name }),
              field && field !== name ? element("code", { className: "dv-business-field-code", text: field }) : null,
              detail && !shared ? element("span", { className: "dv-business-dictionary", text: detail }) : null,
              option.description ? element("span", { className: "dv-ai-choice-note", text: option.description }) : null),
            option.tag ? element("span", { className: "dv-ai-choice-tail", text: isModelSuggestion(option) ? "模型建议" : option.tag }) : null);
          bind(input, "change", () => {
            if (multiple) {
              answers.set(key, controls.filter(({ input }) => input.checked).map(({ value }) => value));
            } else if (input.checked) answers.set(key, value);
            refresh();
          });
          controls.push({ input, row, value });
          list.append(row);
        });
        group.append(list);
        if (shared) group.append(element("p", { className: "dv-business-shared-dictionary", text: displays[0].detail }));
      }
      root.append(group);
    });
    bind(submit, "click", async () => {
      if (submit.disabled) return;
      const active = generation;
      submitting = true;
      refresh();
      try { await onConfirm(new Map(answers)); }
      finally { if (generation === active) { submitting = false; refresh(); } }
    });
    refresh();
  }

  return { element: root, progress, submit, setVisible, update, clear };
}
