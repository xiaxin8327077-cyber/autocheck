// 图形路径直接沿用用户提供的 HTML 参考稿。
export function resultIcon(name) {
  const paths = {
    search: "M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z",
    chevron: "M19.5 8.25l-7.5 7.5-7.5-7.5",
    play: "M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z",
    close: "M6 18L18 6M6 6l12 12",
    copy: "M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184",
  };
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  Object.entries({ class: "dv-reference-icon", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.8", "aria-hidden": "true" }).forEach(([key, value]) => icon.setAttribute(key, value));
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", paths[name] || paths.chevron); path.setAttribute("stroke-linecap", "round"); path.setAttribute("stroke-linejoin", "round");
  icon.append(path); return icon;
}
