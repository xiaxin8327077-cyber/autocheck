import { button, node } from "./dom.js";

const BOARD_LABELS = new Map([
  ["report_submission", "金融监管报表报送大屏"],
  ["reporting_process", "金融监管报送流程大屏"],
]);

export function renderDashboardTabs({ boards, activeBoardCode, onSelect, onPreview }) {
  const toolbar = node("div", { className: "dm-tabs" });
  const tabs = node("div", { className: "dm-tab-switches", attrs: { role: "tablist", "aria-label": "看板选择" } });
  boards.forEach((board) => {
    const name = BOARD_LABELS.get(board.code) || board.name;
    const tab = button("", "dm-tab", () => onSelect(board.code));
    if (board.code === activeBoardCode) tab.classList.add("is-active");
    tab.setAttribute("role", "tab");
    tab.id = `dm-tab-${board.code}`;
    tab.setAttribute("aria-controls", `dm-panel-${board.code}`);
    tab.setAttribute("aria-selected", String(board.code === activeBoardCode));
    tab.append(node("span", { className: "dm-tab-label", text: name }));
    tabs.append(tab);
  });
  const activeBoard = boards.find((board) => board.code === activeBoardCode) || boards[0];
  toolbar.append(tabs);
  if (activeBoard) {
    const preview = node("div", { className: "dm-tab-preview" });
    const trigger = button("", "dm-tab-preview-trigger", () => {});
    trigger.append(
      node("span", { className: "dm-tab-preview-label", text: "预览当前看板" }),
      node("span", { className: "dm-tab-preview-chevron", attrs: { "aria-hidden": "true" } }),
    );
    trigger.setAttribute("aria-haspopup", "menu"); trigger.setAttribute("aria-label", `${BOARD_LABELS.get(activeBoard.code) || activeBoard.name}预览`);
    const menu = node("div", { className: "dm-tab-preview-menu", attrs: { role: "menu" } });
    menu.append(
      button("接口数据", "dm-tab-preview-item", () => onPreview(activeBoard, "data", trigger)),
      button("看板页面", "dm-tab-preview-item", () => onPreview(activeBoard, "screen", trigger)),
    );
    preview.append(trigger, menu);
    toolbar.append(preview);
  }
  return toolbar;
}
