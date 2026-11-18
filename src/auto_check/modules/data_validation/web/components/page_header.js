import { element } from "./dom.js";

export function createPageHeader({ section, title, description, actions = [] }) {
  return element("header", { className: "dv-page-header" },
    element("div", { className: "dv-page-heading" },
      element("h1", { text: title }),
      element("p", { text: description })),
    element("div", { className: "dv-page-actions" }, actions));
}
