import { element } from "./dom.js";

function selectedLabel(options, selected) {
  const names = options
    .filter((item) => selected.has(String(item.code)))
    .map((item) => item.name || item.code);
  return names.length ? names.join("；") : "请选择关联报送";
}

export function createProcessMultiSelect(documentRef, {
  options = [],
  values = [],
  disabled = false,
  "aria-label": ariaLabel = "关联报送",
} = {}) {
  const selected = new Set((values || []).map((item) => String(item)).filter(Boolean));
  const optionNodes = new Map();
  const trigger = element(documentRef, "button", {
    type: "button",
    className: "rsp-multi-select-trigger",
    "aria-label": ariaLabel,
    "aria-haspopup": "listbox",
    "aria-expanded": "false",
    disabled,
  });
  const list = element(documentRef, "div", {
    className: "rsp-multi-select-panel",
    role: "listbox",
    "aria-multiselectable": "true",
    hidden: "",
  });
  const root = element(documentRef, "div", {
    className: disabled ? "rsp-multi-select is-disabled" : "rsp-multi-select",
  }, [trigger, list]);

  function syncOption(code) {
    const row = optionNodes.get(code);
    if (!row) return;
    const active = selected.has(code);
    row.classList.toggle("is-selected", active);
    row.setAttribute("aria-selected", String(active));
  }

  function syncTrigger() {
    trigger.textContent = selectedLabel(options, selected);
    trigger.title = trigger.textContent;
    trigger.setAttribute("aria-expanded", list.hidden ? "false" : "true");
    root.classList.toggle("is-open", !list.hidden);
  }

  function toggleCode(code) {
    if (selected.has(code)) selected.delete(code);
    else selected.add(code);
    syncOption(code);
    syncTrigger();
  }

  options.forEach((item) => {
    const code = String(item.code);
    const row = element(documentRef, "button", {
      type: "button",
      className: "rsp-multi-select-option",
      role: "option",
      "aria-selected": String(selected.has(code)),
      "data-code": code,
      disabled,
      text: item.name || code,
    });
    if (selected.has(code)) row.classList.add("is-selected");
    row.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (disabled) return;
      toggleCode(code);
    });
    optionNodes.set(code, row);
    list.append(row);
  });

  function close() {
    list.hidden = true;
    syncTrigger();
  }

  function open() {
    if (disabled) return;
    list.hidden = false;
    syncTrigger();
  }

  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (list.hidden) open();
    else close();
  });

  const onDocumentClick = (event) => {
    const target = event.target;
    if (target && typeof root.contains === "function" && root.contains(target)) return;
    close();
  };
  documentRef.addEventListener("click", onDocumentClick, true);

  syncTrigger();

  return {
    root,
    get value() {
      return options
        .map((item) => String(item.code))
        .filter((code) => selected.has(code));
    },
    setAttribute(name, value) {
      if (name === "aria-invalid") trigger.setAttribute(name, value);
      else root.setAttribute(name, value);
    },
    focus() {
      trigger.focus();
    },
    destroy() {
      documentRef.removeEventListener("click", onDocumentClick, true);
    },
  };
}
