import { dataOf, defaultPeriod } from "../state.js";
import { element } from "../components/dom.js";
import { createFilters } from "../components/filters.js";
import { createRecordTable } from "../components/record_table.js";
import { createRecordDrawer } from "../components/record_drawer.js";

const ALL_PROCESS_CODE = "";
const ALL_PROCESS_TAB = Object.freeze({ code: ALL_PROCESS_CODE, name: "全部" });

export function createLedgerPage({ root, api, state, user, notify, confirm, navigate }) {
  const documentRef = root.ownerDocument;

  async function loadCatalog() {
    try {
      state.catalog = dataOf(await api.catalog(), {});
      state.catalogAvailable = Array.isArray(state.catalog.report_processes)
        && state.catalog.report_processes.some((item) => item.active !== false)
        && Array.isArray(state.catalog.users)
        && state.catalog.users.length > 0;
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

  async function exportLedger(filters = state.filters) {
    if (!state.catalogAvailable) {
      notify("目录不可用，暂时无法导出", "warning");
      return;
    }
    try {
      const parameters = {
        report_process_code: state.activeProcessCode,
        report_period: state.reportPeriod,
        ...filters,
        sort: "special_handling_at_desc",
      };
      const { blob, filename } = await api.exportRecords(parameters);
      const url = URL.createObjectURL(blob);
      try {
        const anchor = documentRef.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        anchor.style.display = "none";
        documentRef.body.append(anchor);
        anchor.click();
        anchor.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
      notify("导出完成", "success");
    } catch (error) {
      if (error?.name !== "AbortError") notify(error?.message || "导出失败，请重试", "error");
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
      root.querySelector?.(".rsp-record-modal button")?.focus?.();
    } catch (error) {
      if (error?.name !== "AbortError") notify("记录详情加载失败", "error");
    }
  }

  function askReason(message) {
    const value = documentRef.defaultView?.prompt?.(message, "");
    if (value == null) return null;
    const reason = String(value).trim();
    if (!reason) {
      notify("请输入操作原因", "warning");
      return null;
    }
    return reason;
  }

    async function handleRowAction(record, action) {
    const run = async (operation, successMessage) => {
      try {
        await operation();
        notify(successMessage, "success");
        if (state.drawer?.record?.id && String(state.drawer.record.id) === String(record.id)) {
          await refreshRecord(record.id);
        }
        await loadLedger();
      } catch (error) {
        if (error?.name !== "AbortError") notify(error?.message || "操作失败，请重试", "error");
      }
    };
    const withLatestVersion = async (operation) => {
      const latest = dataOf(await api.getRecord(record.id), record);
      return operation(latest);
    };

    if (action === "complete") {
      if (!await confirm("确认将该记录标记为已完成吗？")) return;
      await run(
        () => withLatestVersion((latest) => api.changeStatus(latest.id, {
          target_status: "completed",
          row_version: latest.row_version,
          reason: "处理完成",
        })),
        "记录已完成",
      );
      return;
    }
    if (action === "void") {
      const reason = askReason("请输入作废原因");
      if (!reason) return;
      if (!await confirm("确认作废该记录吗？作废后仍保留完整留痕。")) return;
      await run(
        () => withLatestVersion((latest) => api.voidRecord(latest.id, {
          row_version: latest.row_version,
          reason,
        })),
        "记录已作废",
      );
    }
  }

  function openCreate(trigger) {
    state.restoreFocus = { kind: "create" };
    state.drawer = { mode: "create", record: null };
    render();
    root.querySelector?.(".rsp-record-modal select")?.focus?.();
  }

  function createTabs({ title, actions }) {
    const counts = new Map((state.summary.by_report_process || []).map((item) => [item.code, item.effective_count]));
    const allCount = [...counts.values()].reduce((sum, value) => sum + Number(value || 0), 0);
    const tabs = element(documentRef, "div", { className: "rsp-report-tabs", role: "tablist", "aria-label": "关联报送" });
    const report_processes = (state.catalog?.report_processes || []).filter((item) => item.active !== false);
    const tabItems = [ALL_PROCESS_TAB, ...report_processes];

    tabItems.forEach((processItem) => {
      const active = processItem.code === state.activeProcessCode;
      const count = processItem.code === ALL_PROCESS_CODE ? allCount : (counts.get(processItem.code) || 0);
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
        element(documentRef, "small", { text: String(count) }),
      ]);
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault();
        const index = tabItems.findIndex((item) => item.code === processItem.code);
        const offset = event.key === "ArrowRight" ? 1 : -1;
        const next = tabItems[(index + offset + tabItems.length) % tabItems.length];
        state.activeProcessCode = next.code;
        state.page = 1;
        loadLedger();
      });
      tabs.append(tab);
    });
    const header = element(documentRef, "div", { className: "rsp-tabs-header" }, [
      element(documentRef, "h2", { className: "rsp-tabs-title", text: title }),
      element(documentRef, "div", { className: "rsp-tabs-actions" }, actions),
    ]);
    const card = element(documentRef, "div", { className: "rsp-tabs-card" }, [header, tabs]);
    return card;
  }

  function pagination() {
    const jump = element(documentRef, "input", {
      type: "number",
      min: "1",
      "aria-label": "跳转页码",
    });
    const goToPage = (nextPage) => {
      const page = Number(nextPage);
      if (!Number.isFinite(page) || page < 1 || page > state.totalPages || page === state.page) return;
      state.page = page;
      loadLedger();
    };
    jump.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      goToPage(jump.value);
      jump.value = "";
    });
    const infoText = state.total
      ? `共 ${state.total} 条，第 ${state.page} / ${state.totalPages} 页`
      : "暂无数据";
    return element(documentRef, "footer", { className: "rsp-pagination" }, [
      element(documentRef, "span", { className: "rsp-pagination-info", text: infoText }),
      element(documentRef, "div", { className: "rsp-pagination-controls" }, [
        element(documentRef, "button", {
          type: "button",
          className: "rsp-page-btn",
          text: "◀",
          "aria-label": "上一页",
          disabled: state.page <= 1,
          onClick: () => goToPage(state.page - 1),
        }),
        element(documentRef, "span", { className: "rsp-page-current", text: String(state.page) }),
        element(documentRef, "button", {
          type: "button",
          className: "rsp-page-btn",
          text: "▶",
          "aria-label": "下一页",
          disabled: state.page >= state.totalPages,
          onClick: () => goToPage(state.page + 1),
        }),
        element(documentRef, "span", { className: "rsp-pagination-jump" }, [
          documentRef.createTextNode("跳至 "),
          jump,
          documentRef.createTextNode(" 页"),
        ]),
      ]),
    ]);
  }

  function render() {
    if (!state.active) return;
    const createButton = element(documentRef, "button", {
      type: "button",
      className: "rsp-button rsp-button-primary",
      text: "新建",
      disabled: !state.catalogAvailable,
    });
    createButton.addEventListener("click", () => openCreate(createButton));
    const period = element(documentRef, "input", { type: "date", value: state.reportPeriod, "aria-label": "报送期" });
    period.addEventListener("change", () => { state.reportPeriod = period.value; state.page = 1; loadLedger(); });

    const availability = state.catalogAvailable ? null : element(documentRef, "div", { className: "rsp-catalog-warning", role: "alert", text: "用户或报送目录暂时不可用，保存功能已禁用。" });
    const tabsActions = element(documentRef, "div", { className: "rsp-intro-actions" }, [
      period,
      createButton,
    ]);
    const master = element(documentRef, "section", { className: "rsp-master-pane" }, [
      createTabs({ title: "报表特殊处理", actions: tabsActions }),
      createFilters(documentRef, {
        catalog: state.catalog,
        filters: state.filters,
        onApply: (filters) => { state.filters = filters; state.page = 1; loadLedger(); },
        onReset: () => { state.filters = { status: "", keyword: "", handler_user_id: "" }; state.page = 1; loadLedger(); },
        onExport: (filters) => { state.filters = filters; exportLedger(filters); },
      }),
      createRecordTable(documentRef, state.records, {
        selectedId: state.drawer?.record?.id,
        onOpen: openRecord,
        onAction: handleRowAction,
      }),
      pagination(),
    ]);
    const layout = element(documentRef, "div", { className: "rsp-workbench" }, [master]);
    const modal = state.drawer
      ? createRecordDrawer(documentRef, {
        catalog: state.catalog,
        catalogAvailable: state.catalogAvailable,
        record: state.drawer.record,
        mode: state.drawer.mode,
        user,
        reportPeriod: state.reportPeriod,
        activeProcessCode: state.activeProcessCode,
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
      })
      : null;
    root.replaceChildren(...[availability, layout, modal].filter(Boolean));
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
