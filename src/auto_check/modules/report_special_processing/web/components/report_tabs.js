import { element } from "./dom.js";

const REPORT_TAB_LABEL_LIMIT = 15;

export function normalizeActiveTabCode(activeCode, catalog) {
  const code = String(activeCode || "");
  if (!code) return "";
  const entries = catalog?.report_process_tabs ?? catalog?.report_processes ?? [];
  return entries.some((item) => item?.active !== false && String(item?.code || "") === code)
    ? code
    : "";
}

function textOf(item) {
  return String(item?.name || item?.code || "");
}

function countOf(item) {
  return Number(item?.count) || 0;
}

function tabLabel(name) {
  return Array.from(String(name || "")).slice(0, REPORT_TAB_LABEL_LIMIT).join("");
}

function moreLabel(hiddenItems, activeHidden) {
  return activeHidden
    ? `更多报送：${tabLabel(activeHidden.name)} ▾`
    : `更多报送（${hiddenItems.length}） ▾`;
}

/**
 * A single-line report tab controller. It measures rendered controls, then
 * moves only trailing tabs into an accessible fixed-position menu.
 */
export function createReportTabs(documentRef, {
  items = [],
  activeCode = "",
  onSelect = () => {},
} = {}) {
  const view = documentRef?.defaultView || globalThis;
  const ordered = items.map((item) => ({
    code: String(item?.code || ""),
    name: textOf(item),
    count: countOf(item),
  }));
  const root = element(documentRef, "div", {
    className: "rsp-report-tabs",
    role: "tablist",
    "aria-label": "关联报送",
  });
  let currentCode = String(activeCode || "");
  let destroyed = false;
  let frame = null;
  let cancelFrame = null;
  let refreshScheduled = false;
  let resizeObserver = null;
  let menu = null;
  let menuTrigger = null;
  let restoreSelectionFocus = false;

  function tabButton(item, active) {
    const tab = element(documentRef, "button", {
      type: "button",
      role: "tab",
      "aria-selected": String(active),
      tabIndex: active ? "0" : "-1",
      className: active ? "rsp-report-tab-measure is-active" : "rsp-report-tab-measure",
      dataset: { code: item.code },
    }, [
      element(documentRef, "span", {
        className: "rsp-report-tab-label",
        text: tabLabel(item.name),
        title: item.name,
      }),
      element(documentRef, "small", { text: String(item.count) }),
    ]);
    tab.addEventListener("click", () => select(item.code));
    tab.addEventListener("keydown", (event) => {
      const index = ordered.findIndex((entry) => entry.code === item.code);
      if (index < 0) return;
      let next = null;
      if (event.key === "ArrowLeft") next = ordered[(index - 1 + ordered.length) % ordered.length];
      if (event.key === "ArrowRight") next = ordered[(index + 1) % ordered.length];
      if (event.key === "Home") next = ordered[0];
      if (event.key === "End") next = ordered[ordered.length - 1];
      if (!next) return;
      event.preventDefault();
      select(next.code, { restoreFocus: true });
    });
    return tab;
  }

  function positionMenu() {
    if (!menu || !menuTrigger || menu.hidden) return;
    const rect = menuTrigger.getBoundingClientRect?.();
    if (!rect || !menu.style) return;
    menu.style.top = `${Math.round(rect.bottom + 6)}px`;
    menu.style.right = `${Math.max(8, Math.round((view.innerWidth || 0) - rect.right))}px`;
  }

  function closeMenu() {
    if (!menu) return;
    if (menu.matches?.(":popover-open")) menu.hidePopover?.();
    menu.hidden = true;
    menuTrigger?.setAttribute("aria-expanded", "false");
  }

  function openMenu() {
    if (!menu || !menuTrigger) return;
    menu.hidden = false;
    menu.showPopover?.();
    menuTrigger.setAttribute("aria-expanded", "true");
    positionMenu();
    menu.querySelector?.('input[aria-label="搜索更多报送"]')?.focus?.();
  }

  function select(code, { restoreFocus = false } = {}) {
    currentCode = String(code || "");
    restoreSelectionFocus = restoreFocus;
    onSelect(currentCode);
    closeMenu();
    render();
  }

  function createMoreButton(hiddenItems, activeHidden) {
    const label = moreLabel(hiddenItems, activeHidden);
    const trigger = element(documentRef, "button", {
      type: "button",
      className: activeHidden ? "rsp-report-tabs-more-trigger is-active" : "rsp-report-tabs-more-trigger",
      "aria-label": "更多报送",
      "aria-haspopup": "dialog",
      "aria-expanded": "false",
      text: label,
      title: activeHidden ? `更多报送：${activeHidden.name}` : label,
    });
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      if (menu?.hidden) openMenu();
      else closeMenu();
    });
    trigger.addEventListener("keydown", (event) => {
      if (!["ArrowDown", "Enter", " "].includes(event.key)) return;
      event.preventDefault();
      openMenu();
    });
    return trigger;
  }

  function createMoreMenu(hiddenItems) {
    const search = element(documentRef, "input", {
      type: "search",
      className: "rsp-report-tabs-more-search",
      placeholder: "搜索报送名称",
      "aria-label": "搜索更多报送",
    });
    const count = element(documentRef, "span", { className: "rsp-report-tabs-more-count", text: `共 ${hiddenItems.length} 项` });
    const optionList = element(documentRef, "div", { className: "rsp-report-tabs-more-list", role: "listbox", "aria-label": "更多报送列表" });
    const empty = element(documentRef, "p", { className: "rsp-report-tabs-more-empty", text: "未找到匹配的报送", hidden: "" });
    const panel = element(documentRef, "div", {
      className: "rsp-report-tabs-more-panel",
      role: "dialog",
      "aria-label": "更多报送",
      popover: "manual",
      hidden: "",
    }, [
      element(documentRef, "div", { className: "rsp-report-tabs-more-head" }, [search, count]),
      optionList,
      empty,
    ]);
    const options = hiddenItems.map((item) => {
      const active = item.code === currentCode;
      const option = element(documentRef, "button", {
        type: "button",
        className: active ? "rsp-report-tabs-more-option is-active" : "rsp-report-tabs-more-option",
        role: "option",
        "aria-selected": String(active),
        dataset: { code: item.code },
        text: `${item.name}（${item.count}）`,
      });
      option.addEventListener("click", () => select(item.code));
      option.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          closeMenu();
          menuTrigger?.focus?.();
        }
      });
      optionList.append(option);
      return { item, option };
    });
    const filter = () => {
      const keyword = String(search.value || "").trim().toLowerCase();
      let visible = 0;
      options.forEach(({ item, option }) => {
        const matched = !keyword || item.name.toLowerCase().includes(keyword) || String(item.count).includes(keyword);
        option.hidden = !matched;
        if (matched) visible += 1;
      });
      count.textContent = `共 ${visible} / ${hiddenItems.length} 项`;
      empty.hidden = visible > 0;
    };
    search.addEventListener("input", filter);
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMenu();
        menuTrigger?.focus?.();
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        options.find(({ option }) => !option.hidden)?.option.focus?.();
      }
    });
    return panel;
  }

  function measuredWidth(node) {
    return Math.ceil(Number(node?.getBoundingClientRect?.().width) || 0);
  }

  function layout(itemsWithNodes) {
    const available = measuredWidth(root);
    if (!available) return itemsWithNodes.length;
    const widths = itemsWithNodes.map(({ node }) => measuredWidth(node));
    const total = widths.reduce((sum, width) => sum + width, 0);
    if (total <= available) return itemsWithNodes.length;
    for (let visible = widths.length - 1; visible >= 0; visible -= 1) {
      const hidden = itemsWithNodes.slice(visible).map(({ item }) => item);
      const activeHidden = hidden.find((item) => item.code === currentCode) || null;
      const label = moreLabel(hidden, activeHidden);
      const probe = element(documentRef, "button", {
        type: "button",
        className: activeHidden
          ? "rsp-report-tabs-more-trigger rsp-report-tabs-more-measure is-active"
          : "rsp-report-tabs-more-trigger rsp-report-tabs-more-measure",
        text: label,
      });
      if (probe.style) {
        probe.style.position = "absolute";
        probe.style.visibility = "hidden";
        probe.style.pointerEvents = "none";
      }
      root.append(probe);
      const moreWidth = measuredWidth(probe);
      probe.remove?.();
      const used = widths.slice(0, visible).reduce((sum, width) => sum + width, 0);
      if (used + moreWidth <= available) return visible;
    }
    return 0;
  }

  function render() {
    if (destroyed) return;
    root.replaceChildren();
    menu = null;
    menuTrigger = null;
    const probes = ordered.map((item) => ({ item, node: tabButton(item, item.code === currentCode) }));
    probes.forEach(({ node }) => root.append(node));
    const visibleCount = layout(probes);
    const visible = probes.slice(0, visibleCount);
    const hidden = probes.slice(visibleCount).map(({ item }) => item);
    const visibleByCode = new Map(visible.map(({ item, node }) => [item.code, node]));
    visible.forEach(({ node }) => node.classList.remove("rsp-report-tab-measure"));
    root.replaceChildren(...visible.map(({ node }) => node));
    if (!hidden.length) {
      if (restoreSelectionFocus) {
        visibleByCode.get(currentCode)?.focus?.();
        restoreSelectionFocus = false;
      }
      return;
    }
    const activeHidden = hidden.find((item) => item.code === currentCode) || null;
    menu = createMoreMenu(hidden);
    menuTrigger = createMoreButton(hidden, activeHidden);
    root.append(menuTrigger, menu);
    if (restoreSelectionFocus) {
      (visibleByCode.get(currentCode) || menuTrigger)?.focus?.();
      restoreSelectionFocus = false;
    }
  }

  function scheduleRefresh() {
    if (destroyed || refreshScheduled) return;
    refreshScheduled = true;
    const timeout = view.setTimeout?.bind(view) || globalThis.setTimeout?.bind(globalThis) || ((callback) => {
      callback();
      return null;
    });
    const request = view.requestAnimationFrame?.bind(view) || ((callback) => timeout(callback, 0));
    cancelFrame = view.cancelAnimationFrame?.bind(view) || globalThis.clearTimeout?.bind(globalThis) || null;
    frame = request(() => {
      frame = null;
      cancelFrame = null;
      refreshScheduled = false;
      render();
      positionMenu();
    });
  }

  function onDocumentClick(event) {
    if (menu?.hidden || root.contains?.(event.target)) return;
    closeMenu();
  }

  function onWindowResize() {
    scheduleRefresh();
  }

  documentRef.addEventListener?.("click", onDocumentClick, true);
  view.addEventListener?.("resize", onWindowResize);
  if (typeof view.ResizeObserver === "function") {
    resizeObserver = new view.ResizeObserver(scheduleRefresh);
    resizeObserver.observe(root);
  }
  render();
  scheduleRefresh();

  return Object.freeze({
    root,
    refresh: scheduleRefresh,
    focusActive() {
      restoreSelectionFocus = true;
      scheduleRefresh();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      if (frame != null) {
        cancelFrame?.(frame);
        frame = null;
      }
      cancelFrame = null;
      refreshScheduled = false;
      resizeObserver?.disconnect?.();
      documentRef.removeEventListener?.("click", onDocumentClick, true);
      view.removeEventListener?.("resize", onWindowResize);
      root.replaceChildren();
    },
  });
}
