import { button, element } from "./dom.js";

// 状态胶囊：与后端真实规则状态一一对应（全部/已启用/草稿/已停用），数量来自 stats 接口。
const STATUS_PILLS = [
  { status: "", label: "全部", key: "total", tone: "accent" },
  { status: "enabled", label: "已启用", key: "enabled", tone: "success" },
  { status: "draft", label: "草稿", key: "draft", tone: "warning" },
  { status: "disabled", label: "已停用", key: "disabled", tone: "neutral" },
];

export function createStatsCards({ listen, onFilter }) {
  const root = element("div", { className: "dv-status-pills", attrs: { "aria-label": "规则状态统计" } });
  const pills = STATUS_PILLS.map((item) => {
    const count = element("span", { className: "dv-pill-count", text: "—" });
    const pill = button("", {
      listen, className: `dv-status-pill is-${item.tone}`, onClick: () => onFilter(item.status),
    });
    pill.append(
      element("span", { className: "dv-pill-dot", attrs: { "aria-hidden": "true" } }),
      element("span", { text: item.label }),
      count,
    );
    root.append(pill);
    return { pill, count, item };
  });

  return {
    element: root,
    update(stats, currentStatus, status) {
      const unavailable = status !== "success";
      pills.forEach(({ pill, count, item }) => {
        count.textContent = unavailable ? "—" : String(Number(stats?.[item.key]) || 0);
        pill.classList.toggle("is-active", currentStatus === item.status);
      });
    },
  };
}