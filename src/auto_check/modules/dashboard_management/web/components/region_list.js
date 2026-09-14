import { button, node } from "./dom.js";

export function renderRegionList({ regions, selectedId, canManage, onSelect, onCreate, onManage }) {
  const panel = node("aside", { className: "dm-region-panel" });
  const header = node("div", { className: "dm-panel-heading" });
  header.append(node("h2", { text: "数据区域列表" }), button("新增数据区域", "dm-button dm-button-secondary", onCreate, { disabled: !canManage }));
  panel.append(header);
  const list = node("div", { className: "dm-region-list" });
  regions.forEach((region, index) => {
    const item = node("div", { className: "dm-region-item" });
    if (region.id === selectedId) item.classList.add("is-active");
    const selectButton = button("", "dm-region-select", () => onSelect(region.id));
    selectButton.append(
      node("span", { className: "dm-region-number", text: String(index + 1).padStart(2, "0") }),
      node("strong", { text: region.name }),
      node("span", { className: "dm-source-badge", text: region.source_config?.source_mode === "system" ? "系统数据" : "自定义 SQL" }),
    );
    item.append(selectButton);
    if (canManage) item.append(button("编辑", "dm-region-edit", () => onManage(region)));
    list.append(item);
  });
  panel.append(list);
  return panel;
}
