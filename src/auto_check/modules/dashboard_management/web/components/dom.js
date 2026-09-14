export function node(tag, { className = "", text = "", attrs = {} } = {}) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  Object.entries(attrs).forEach(([name, value]) => {
    if (value !== undefined && value !== null) element.setAttribute(name, String(value));
  });
  return element;
}

export function button(text, className, onClick, { disabled = false } = {}) {
  const element = node("button", { className, text, attrs: { type: "button" } });
  element.disabled = disabled;
  if (onClick) element.addEventListener("click", onClick);
  return element;
}

export function labeledControl(label, control) {
  const isCheckbox = control.type === "checkbox";
  const wrap = node("div", { className: isCheckbox ? "dm-control dm-control-checkbox" : "dm-control" });
  if (!control.id) control.id = `dm-control-${crypto.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  const labelNode = node("label", { className: "dm-control-label", text: label, attrs: { for: control.id } });
  if (isCheckbox) wrap.append(control, labelNode);
  else wrap.append(labelNode, control);
  return wrap;
}

export function clear(element) {
  element.replaceChildren();
  return element;
}
