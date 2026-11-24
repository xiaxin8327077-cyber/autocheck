import { button, element, textarea } from "./dom.js";

export function createKeywordEditor(listen, onEdit) {
  const root = element("fieldset", { className: "dv-condition-group" });
  let words = [];
  let removers = [];
  function render() {
    removers.forEach((remove) => remove?.());
    removers = [];
    root.replaceChildren(element("legend", { text: "字面关键词" }));
    words.forEach((word, index) => {
      const control = textarea({ value: word, rows: 1, placeholder: "输入关键词" });
      control.setAttribute("aria-label", `关键词 ${index + 1}`);
      const remove = button("移除关键词", { disabled: words.length === 1 });
      removers.push(listen(control, "input", () => { words[index] = control.value; onEdit(); }));
      removers.push(listen(remove, "click", () => { words.splice(index, 1); render(); onEdit(); }));
      root.append(element("div", { className: "dv-form-grid" }, control, remove));
    });
    const add = button("添加关键词", { disabled: words.length >= 50 });
    removers.push(listen(add, "click", () => { if (words.length < 50) { words.push(""); render(); onEdit(); } }));
    root.append(add);
  }
  return {
    element: root, read: () => [...words],
    set(value) { words = Array.isArray(value) && value.length ? [...value] : [""]; render(); },
    dispose() { removers.forEach((remove) => remove?.()); },
  };
}
