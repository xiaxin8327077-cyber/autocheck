export function element(tag, options = {}, ...children) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined && options.text !== null) node.textContent = String(options.text);
  Object.entries(options.attrs || {}).forEach(([name, value]) => {
    if (value !== false && value !== null && value !== undefined) node.setAttribute(name, String(value));
  });
  Object.entries(options.dataset || {}).forEach(([name, value]) => { node.dataset[name] = String(value); });
  if (options.hidden) node.hidden = true;
  if (options.disabled) node.disabled = true;
  append(node, ...children);
  return node;
}

export function append(node, ...children) {
  children.flat(Infinity).forEach((child) => {
    if (child === null || child === undefined || child === false) return;
    const isText = typeof child === "string" || typeof child === "number" || typeof child === "boolean";
    node.append(isText ? document.createTextNode(String(child)) : child);
  });
  return node;
}

export function button(label, {
  listen, onClick, className = "dv-button", title = "", disabled = false,
  hidden = false, capability = "", dataset = {}, ariaLabel = "",
} = {}) {
  const node = element("button", {
    className,
    text: label,
    hidden,
    disabled,
    dataset: { ...dataset, ...(capability ? { capability } : {}) },
    attrs: { type: "button", title: title || undefined, "aria-label": ariaLabel || undefined },
  });
  node.type = "button";
  if (title) node.title = title;
  if (disabled) node.disabled = true;
  if (onClick) listen(node, "click", onClick);
  return node;
}

export function input({ type = "text", value = "", placeholder = "", className = "dv-input", dataset = {} } = {}) {
  const node = element("input", { className, dataset, attrs: { type, placeholder } });
  node.type = type;
  node.value = value ?? "";
  node.placeholder = placeholder;
  return node;
}

export function textarea({ value = "", placeholder = "", rows = 4, className = "dv-textarea" } = {}) {
  const node = element("textarea", { className, attrs: { rows, placeholder } });
  node.rows = rows;
  node.value = value ?? "";
  node.placeholder = placeholder;
  return node;
}

export function select(options = [], { className = "dv-select", value = "" } = {}) {
  const node = element("select", { className });
  options.forEach(([optionValue, label, disabled = false]) => {
    const item = element("option", { text: label, disabled });
    item.value = String(optionValue);
    item.disabled = Boolean(disabled);
    node.append(item);
  });
  node.value = String(value);
  return node;
}

export function field(label, control, hint = "") {
  const wrapper = element("label", { className: "dv-field" },
    element("span", { className: "dv-field-label", text: label }), control);
  if (hint) wrapper.append(element("span", { className: "dv-field-hint", text: hint }));
  return wrapper;
}

export function statusBadge(label, tone = "neutral") {
  return element("span", { className: `dv-status is-${tone}`, text: label });
}

export function emptyState(title = "暂无数据", detail = "") {
  return element("div", { className: "dv-empty" },
    element("strong", { text: title }),
    detail ? element("p", { text: detail }) : null);
}

export function errorState(message, retryButton = null) {
  return element("div", { className: "dv-feedback is-error", attrs: { role: "alert" } },
    element("span", { text: message }), retryButton);
}

export function downloadText({ host, runtime, filename, content, type = "application/json;charset=utf-8" }) {
  const blob = new Blob([String(content ?? "")], { type });
  const url = URL.createObjectURL(blob);
  const link = element("a", { attrs: { href: url, download: filename }, hidden: true });
  link.href = url;
  link.download = filename;
  host.append(link);
  link.click();
  link.remove();
  const revokeTimer = runtime.setTimer(() => URL.revokeObjectURL(url), 0);
  if (revokeTimer === null) URL.revokeObjectURL(url);
}

export function setText(node, value) {
  node.textContent = value ?? "";
}
