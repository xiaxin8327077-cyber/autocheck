export function element(documentRef, tag, options = {}, children = []) {
  const node = documentRef.createElement(tag);
  Object.entries(options).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "disabled") node.disabled = Boolean(value);
    else if (key === "value") node.value = value;
    else if (key === "checked") node.checked = Boolean(value);
    else if (key === "tabIndex") node.tabIndex = Number(value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, String(value));
  });
  const list = Array.isArray(children) ? children : [children];
  list.filter(Boolean).forEach((child) => node.append(child));
  return node;
}

export function option(documentRef, value, label) {
  return element(documentRef, "option", { value, text: label });
}

export function labeledField(documentRef, label, control, className = "") {
  return element(documentRef, "label", { className }, [
    element(documentRef, "span", { className: "rsp-field-label", text: label }),
    control,
  ]);
}

