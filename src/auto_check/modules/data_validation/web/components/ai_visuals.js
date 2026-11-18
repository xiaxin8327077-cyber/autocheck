import { element } from "./dom.js";

const paths = {
  spark: ["m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3L12 3Z", "m20 2 .6 1.4L22 4l-1.4.6L20 6l-.6-1.4L18 4l1.4-.6L20 2Z"],
  star: ["M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09l2.847.814-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z"],
  check: ["M12 3a9 9 0 1 1-.01 0", "m8 12 2.6 2.6L16 9"],
  info: ["M12 3a9 9 0 1 1-.01 0", "M12 11v5m0-9h.01"],
  chevron: ["m9 5 7 7-7 7"],
  database: ["M4 5a8 3 0 1 0 16 0 8 3 0 1 0-16 0", "M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"],
  question: ["M12 3a9 9 0 1 1-.01 0", "M9.5 8.5a2.6 2.6 0 0 1 5 1c0 2-2.5 2-2.5 4m0 3h.01"],
  lock: ["M7 10h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z", "M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"],
  arrow: ["M4 12h15m-6-6 6 6-6 6"],
  scope: ["M8 3H4v4m12-4h4v4M8 21H4v-4m12 4h4v-4", "M12 8a4 4 0 1 1-.01 0"],
  flag: ["M5 21V4c6-4 8 5 14 0v10c-6 5-8-4-14 0"],
};

export function aiIcon(name, className = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.7",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" }).forEach(([key, value]) => svg.setAttribute(key, value));
  (paths[name] || paths.info).forEach((data) => {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", data);
    svg.append(path);
  });
  return element("span", { className: `dv-ai-icon ${className}`.trim(), attrs: { "aria-hidden": "true" } }, svg);
}

export function aiMark() {
  return element("span", { className: "dv-ai-mark", attrs: { "aria-hidden": "true" } }, aiIcon("spark"));
}
