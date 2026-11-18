import { button, element } from "./dom.js";

// 分类胶囊：分类清单与数量均来自后端 stats.categories（报送导航实时分类），前端不写死分类名。
export function createCategoryTabs({ listen, onFilter }) {
  const root = element("div", { className: "dv-category-pills", attrs: { "aria-label": "监管报送分类统计" } });
  let pills = [];
  let signature = "";

  function rebuild(stats) {
    const categories = Array.isArray(stats?.categories) ? stats.categories : [];
    const items = categories.map((item) => ({
      code: String(item.code || ""),
      label: String(item.name || item.code || ""),
      count: Number(item.total) || 0,
      interactive: true,
    }));
    const unclassified = Number(stats?.unclassified?.total) || 0;
    if (unclassified > 0) items.push({ code: null, label: "未分类", count: unclassified, interactive: false });
    const next = items.map((item) => `${item.code}:${item.label}:${item.count}`).join("|");
    if (next === signature) return;
    signature = next;
    root.replaceChildren();
    pills = items.map((item) => {
      const count = element("span", { className: "dv-pill-count", text: `(${item.count})` });
      const pill = item.interactive
        ? button("", {
          listen, className: "dv-category-pill", dataset: { category: item.code }, onClick: () => onFilter(item.code),
        })
        : element("span", { className: "dv-category-pill is-static" });
      pill.append(element("span", { text: item.label }), count);
      root.append(pill);
      return { pill, count, item };
    });
  }

  return {
    element: root,
    update(stats, currentCategory, status) {
      rebuild(stats || {});
      const unavailable = status !== "success";
      pills.forEach(({ pill, count, item }) => {
        count.textContent = unavailable ? "(—)" : `(${item.count})`;
        if (item.interactive) pill.classList.toggle("is-active", currentCategory === item.code);
      });
    },
  };
}