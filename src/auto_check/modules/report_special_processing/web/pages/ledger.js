import { dataOf, defaultPeriod } from "../state.js";
import { element, option } from "../components/dom.js";
import { createFilters } from "../components/filters.js";
import { createRecordTable } from "../components/record_table.js";
import { createRecordDrawer } from "../components/record_drawer.js";

function nowLocal() {
  const date = new Date();
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 19);
}

export function createLedgerPage({ root, api, state, user, notify, confirm, navigate }) {
  const documentRef = root.ownerDocument;

  async function loadCatalog() {
    try {
      state.catalog = dataOf(await api.catalog(), {});
      state.catalogAvailable = Array.isArray(state.catalog.report_processes)
        && state.catalog.report_processes.some((item) => item.active !== false)
        && Array.isArray(state.catalog.users)
        && state.catalog.users.length > 0;
      if (!state.activeProcessCode) state.activeProcessCode = state.catalog.report_processes?.find((item) => item.active !== false)?.code || "";
    } catch (error) {
      if (error?.name === "AbortError") return;
      state.catalogAvailable = false;
      state.catalog = { report_processes: [], users: [], statuses: [], workflow: { enabled: false } };
      notify("用户和报送目录暂时不可用，已禁止保存，请稍后刷新", "error");
    }
  }

  async function loadLedger() {
    if (!state.catalogAvailable) {
      render();
      return;
    }
    try {
      const parameters = {
        report_process_code: state.activeProcessCode,
        report_period: state.reportPeriod,
        ...state.filters,
        page: state.page,
        page_size: state.pageSize,
        sort: "special_handling_at_desc",
      };
      const [recordsResponse, summaryResponse] = await Promise.all([
        api.listRecords(parameters),
        api.summary(state.reportPeriod),
      ]);
      const records = dataOf(recordsResponse, {});
      state.records = records.items || [];
      state.page = records.page || 1;
      state.pageSize = records.page_size || state.pageSize;
      state.total = records.total || 0;
      state.totalPages = records.total_pages || 1;
      state.summary = dataOf(summaryResponse, { by_report_process: [] });
      render();
    } catch (error) {
      if (error?.name !== "AbortError") notify("台账加载失败，请重试", "error");
    }
  }

  async function refreshRecord(recordId) {
    const response = await api.getRecord(recordId);
    state.drawer = { mode: "detail", record: dataOf(response, response) };
    render();
  }

  function closeDrawer() {
    const restore = state.restoreFocus;
    state.drawer = null;
    render();
    if (restore?.kind === "create") root.querySelector?.(".rsp-button-primary")?.focus?.();
    if (restore?.kind === "record") root.querySelector?.(`[data-record-id="${restore.id}"]`)?.focus?.();
    state.restoreFocus = null;
  }

  async function openRecord(record, trigger) {
    state.restoreFocus = { kind: "record", id: String(record.id) };
    try {
      const response = await api.getRecord(record.id);
      state.drawer = { mode: "detail", record: dataOf(response, response) };
      render();
      root.querySelector?.(".rsp-record-drawer button")?.focus?.();
    } catch (error) {
      if (error?.name !== "AbortError") notify("记录详情加载失败", "error");
    }
  }

  function openCreate(trigger) {
    state.restoreFocus = { kind: "create" };
    state.drawer = { mode: "create", record: null };
    render();
    root.querySelector?.(".rsp-record-drawer select")?.focus?.();
  }

  function createTabs() {
    const counts = new Map((state.summary.by_report_process || []).map((item) => [item.code, item.effective_count]));
    const tabs = element(documentRef, "div", { className: "rsp-report-tabs", role: "tablist", "aria-label": "关联报送" });
    const report_processes = state.catalog?.report_processes || [];
    report_processes.map((processItem) => {
      const active = processItem.code === state.activeProcessCode;
      const tab = element(documentRef, "button", {
        type: "button",
        role: "tab",
        "aria-selected": String(active),
        tabIndex: active ? "0" : "-1",
        className: active ? "is-active" : "",
        onClick: () => {
          state.activeProcessCode = processItem.code;
          state.page = 1;
          state.drawer = null;
          loadLedger();
        },
      }, [
        element(documentRef, "span", { text: processItem.name }),
        element(documentRef, "small", { text: String(counts.get(processItem.code) || 0) }),
      ]);
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault();
        const available = report_processes.filter((item) => item.active !== false);
        const index = available.findIndex((item) => item.code === processItem.code);
        const offset = event.key === "ArrowRight" ? 1 : -1;
        const next = available[(index + offset + available.length) % available.length];
        state.activeProcessCode = next.code;
        state.page = 1;
        loadLedger();
      });
      tabs.append(tab);
    });
    return tabs;
  }

  function pagination() {
    const size = element(documentRef, "select", { "aria-label": "每页条数" }, [
      option(documentRef, "20", "20条/页"), option(documentRef, "50", "50条/页"), option(documentRef, "100", "100条/页"),
    ]);
    size.value = String(state.pageSize);
    size.addEventListener("change", () => { state.pageSize = Number(size.value); state.page = 1; loadLedger(); });
    return element(documentRef, "footer", { className: "rsp-pagination" }, [
      element(documentRef, "span", { text: `共 ${state.total} 条，第 ${state.page} / ${state.totalPages} 页` }),
      element(documentRef, "div", {}, [
        element(documentRef, "button", { type: "button", text: "上一页", disabled: state.page <= 1, onClick: () => { state.page -= 1; loadLedger(); } }),
        element(documentRef, "button", { type: "button", text: "下一页", disabled: state.page >= state.totalPages, onClick: () => { state.page += 1; loadLedger(); } }),
        size,
      ]),
    ]);
  }

  function render() {
    if (!state.active) return;
    const createButton = element(documentRef, "button", {
      type: "button",
      className: "rsp-button rsp-button-primary",
      text: "新建特殊处理",
      disabled: !state.catalogAvailable,
    });
    createButton.addEventListener("click", () => openCreate(createButton));
    const period = element(documentRef, "input", { type: "date", value: state.reportPeriod, "aria-label": "报送期" });
    period.addEventListener("change", () => { state.reportPeriod = period.value; state.page = 1; loadLedger(); });

    const intro = element(documentRef, "header", { className: "rsp-page-intro" }, [
      element(documentRef, "div", {}, [
        element(documentRef, "p", { className: "rsp-breadcrumb", text: "数据录入 / 报表特殊处理录入" }),
        element(documentRef, "h1", { text: "报表特殊处理录入" }),
        element(documentRef, "p", { text: "按报送流程维护特殊处理记录，集中查询、编辑和追溯操作留痕。" }),
      ]),
      element(documentRef, "div", { className: "rsp-intro-actions" }, [
        element(documentRef, "label", {}, [element(documentRef, "span", { text: "报送期" }), period]),
        createButton,
      ]),
    ]);
    const availability = state.catalogAvailable ? null : element(documentRef, "div", { className: "rsp-catalog-warning", role: "alert", text: "用户或报送目录暂时不可用，保存功能已禁用。" });
    const master = element(documentRef, "section", { className: "rsp-master-pane" }, [
      createFilters(documentRef, {
        catalog: state.catalog,
        filters: state.filters,
        onApply: (filters) => { state.filters = filters; state.page = 1; loadLedger(); },
        onReset: () => { state.filters = { status: "", keyword: "", handler_user_id: "" }; state.page = 1; loadLedger(); },
      }),
      createRecordTable(documentRef, state.records, { selectedId: state.drawer?.record?.id, onOpen: openRecord }),
      pagination(),
    ]);
    const layout = element(documentRef, "div", { className: "rsp-workbench" }, [master]);
    if (state.drawer) {
      layout.append(createRecordDrawer(documentRef, {
        catalog: state.catalog,
        catalogAvailable: state.catalogAvailable,
        record: state.drawer.record,
        mode: state.drawer.mode,
        user,
        reportPeriod: state.reportPeriod,
        activeProcessCode: state.activeProcessCode,
        now: nowLocal(),
        actions: api,
        notify,
        confirm,
        onClose: closeDrawer,
        onSaved: async (saved) => {
          if (saved?.id) await refreshRecord(saved.id);
          await loadLedger();
        },
        onConflict: async () => {
          if (state.drawer?.record?.id) await refreshRecord(state.drawer.record.id);
        },
      }));
    }
    root.replaceChildren(intro, availability, createTabs(), layout);
  }

  return Object.freeze({
    async activate(route) {
      state.active = true;
      state.reportPeriod ||= defaultPeriod();
      render();
      await loadCatalog();
      await loadLedger();
      return route;
    },
    deactivate() {
      state.active = false;
      state.drawer = null;
      state.restoreFocus = null;
      api.cancelAll();
      root.replaceChildren();
    },
    destroy() {
      state.active = false;
      api.cancelAll();
      root.replaceChildren();
    },
    navigate,
  });
}
