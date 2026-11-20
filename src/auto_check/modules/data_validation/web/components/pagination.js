import { PAGE_SIZES, paginationView } from "../state.js";
import { button, element, input } from "./dom.js";

// 与系统其他列表页一致：左侧状态文案 + 已选数量，右侧「条/页」选择、上一页、页码、下一页、跳至。
// 条/页使用模块自有下拉，避免平台全局 select 增强在本页产生的浮层错位。
export function createPagination({ listen, onPage, onPageSize, pageSizes = PAGE_SIZES }) {
  const selection = element("span", { className: "pagination-selection", hidden: true });
  const info = element("div", { className: "pagination-info", text: "暂无数据" });
  const infoGroup = element("div", { className: "pagination-summary" }, selection, info);

  const previous = button("上一页", { listen, className: "page-btn", onClick: () => onPage(current.page - 1) });
  const pages = element("span", { className: "pagination-pages" });
  const next = button("下一页", { listen, className: "page-btn", onClick: () => onPage(current.page + 1) });

  const jump = input({ type: "number", className: "dv-page-jump-input" });
  jump.min = "1";
  jump.step = "1";
  jump.setAttribute("aria-label", "跳转页码");
  const go = () => {
    const page = Math.max(1, Math.trunc(Number(jump.value) || 1));
    jump.value = String(page);
    onPage(page);
  };
  listen(jump, "change", go);
  listen(jump, "keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    go();
  });
  const jumpLabel = element("label", { className: "pagination-jump" }, "跳至", jump, element("span", { text: "页" }));

  let currentSize = Number(pageSizes[0]) || 50;
  const sizeLabel = element("span", { className: "dv-page-size-label", text: `${currentSize} 条/页` });
  const sizeToggle = element("button", {
    className: "dv-page-size-trigger",
    attrs: { type: "button", "aria-label": "每页条数", "aria-haspopup": "listbox", "aria-expanded": "false" },
  }, sizeLabel, element("span", { className: "dv-page-size-chevron", text: "▾", attrs: { "aria-hidden": "true" } }));
  const sizePanel = element("div", { className: "dv-page-size-panel", hidden: true, attrs: { role: "listbox", "aria-label": "每页条数" } });
  const sizeRoot = element("div", { className: "dv-page-size" }, sizeToggle, sizePanel);

  function closeSizePanel() {
    sizePanel.hidden = true;
    sizeToggle.setAttribute("aria-expanded", "false");
  }

  function chooseSize(value) {
    currentSize = Number(value) || currentSize;
    sizeLabel.textContent = `${currentSize} 条/页`;
    closeSizePanel();
    renderSizeOptions();
    onPageSize?.(currentSize);
  }

  function renderSizeOptions() {
    sizePanel.replaceChildren();
    pageSizes.forEach((value) => {
      const option = element("button", {
        className: "dv-page-size-option",
        dataset: { pageSize: value },
        attrs: { type: "button", role: "option", "aria-selected": String(Number(value) === currentSize) },
      }, element("span", { text: `${value} 条/页` }));
      if (Number(value) === currentSize) {
        option.classList.add("is-selected");
        option.append(element("span", { className: "dv-page-size-check", text: "✓", attrs: { "aria-hidden": "true" } }));
      }
      sizePanel.append(option);
    });
  }
  listen(sizeToggle, "click", () => {
    const willOpen = sizePanel.hidden;
    sizePanel.hidden = !willOpen;
    sizeToggle.setAttribute("aria-expanded", String(willOpen));
  });
  listen(sizePanel, "click", event => {
    const option = event.target.closest("[data-page-size]");
    if (option && !sizeToggle.disabled) chooseSize(option.dataset.pageSize);
  });
  listen(pages, "click", event => {
    const target = event.target.closest("[data-page-number]");
    if (target && !target.disabled) return onPage(Number(target.dataset.pageNumber));
  });
  renderSizeOptions();

  function renderPages(loading) {
    pages.replaceChildren();
    if (!current.total) return;
    const total = current.pages;
    const active = current.page;
    const windowStart = Math.max(1, Math.min(active - 2, total - 4));
    const windowEnd = Math.min(total, windowStart + 4);
    const values = [];
    for (let value = windowStart; value <= windowEnd; value += 1) values.push(value);
    if (windowStart > 1) values.unshift(1);
    if (windowEnd < total) values.push(total);
    values.forEach((value, index) => {
      if (index > 0 && value - values[index - 1] > 1) {
        pages.append(element("span", { className: "pagination-ellipsis", text: "…" }));
      }
      const pageButton = element("button", {
        className: `page-num${value === active ? " page-current is-active" : ""}`,
        text: String(value),
        dataset: { pageNumber: value },
        attrs: { type: "button", "aria-label": `第 ${value} 页`, "aria-current": value === active ? "page" : null },
      });
      pageButton.disabled = loading;
      pages.append(pageButton);
    });
  }

  const controls = element("div", { className: "pagination-controls" }, sizeRoot, previous, pages, next, jumpLabel);
  const root = element("div", { className: "pagination" }, infoGroup, controls);
  let current = paginationView({ total: 0, page: 1, page_size: currentSize });

  return {
    element: root,
    update(payload, { loading = false, selectedCount = null } = {}) {
      current = paginationView(payload);
      info.textContent = current.info;
      if (selectedCount === null || selectedCount === undefined) {
        selection.hidden = true;
      } else {
        selection.hidden = false;
        selection.textContent = `已选 ${Number(selectedCount) || 0} 项 ｜ `;
      }
      previous.disabled = loading || current.previousDisabled;
      next.disabled = loading || current.nextDisabled;
      jump.disabled = loading || !current.total;
      jump.value = current.total ? String(current.page) : "";
      jump.max = String(current.pages);
      renderPages(loading);
      const nextSize = pageSizes.includes(Number(payload?.page_size)) ? Number(payload.page_size) : currentSize;
      if (nextSize !== currentSize) {
        currentSize = nextSize;
        sizeLabel.textContent = `${currentSize} 条/页`;
        renderSizeOptions();
      }
      sizeToggle.disabled = loading;
      root.dataset.empty = current.total ? "false" : "true";
    },
  };
}
