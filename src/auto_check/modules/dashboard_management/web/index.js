import { createApi } from "./api.js";
import { activateLifecycle, applyCatalog, beginPending, captureRequest, createState, currentDraft, currentRegion, endPending, hasPermission, isTokenCurrent, markDatasourceChanged, markSaved, markSqlChanged, recordPreview, requestLeave, selectBoard, selectRegion, setSourceMode, stopRequests } from "./state.js";
import { button, clear, node } from "./components/dom.js";
import { renderDashboardTabs } from "./components/dashboard_tabs.js";
import { renderRegionList } from "./components/region_list.js";
import { openFieldDialog, openManageRegionDialog, openRegionDialog, renderFieldPanel } from "./components/catalog_dialog.js";
import { renderSourceEditor } from "./components/source_editor.js";
import { renderPreviewTable } from "./components/preview_table.js";
import { openBoardPreviewDialog, openBoardScreenPreviewDialog } from "./components/board_preview_dialog.js";

let instance = null;
function message(error, fallback) { return error?.payload?.error?.message || error?.message || fallback; }
function aborted(error) { return error?.name === "AbortError"; }

function createPage(context) {
  const state = createState(); const api = createApi(context, state); const user = context.user(); const canManage = hasPermission(user, "dashboard_management.manage"); const canTest = hasPermission(user, "dashboard_management.test_sql");
  const notify = (text, kind = "info") => context.notify(text, kind);
  const shouldRender = (token) => isTokenCurrent(state, token);
  const loadBoard = async (boardCode, { force = false, resetRegionIds = [], generation = state.lifecycleGeneration } = {}) => {
    if (!force && state.catalogs.has(boardCode)) return state.catalogs.get(boardCode);
    const catalog = await api.catalog(boardCode);
    if (!state.active || generation !== state.lifecycleGeneration) return null;
    return applyCatalog(state, boardCode, catalog, { resetRegionIds });
  };
  const refreshBoard = async (token, resetRegionIds = []) => {
    await loadBoard(token.boardCode, { force: true, resetRegionIds, generation: token.generation });
    if (shouldRender(token)) render();
  };
  const changeBoard = async (boardCode) => {
    if (boardCode === state.activeBoardCode) return;
    const leaving = captureRequest(state); if (!await requestLeave(state, context.confirm, leaving)) return;
    selectBoard(state, boardCode); const generation = state.lifecycleGeneration;
    try { await loadBoard(boardCode, { generation }); if (state.active && generation === state.lifecycleGeneration && state.activeBoardCode === boardCode) render(); }
    catch (error) { if (!aborted(error) && state.active && generation === state.lifecycleGeneration) notify(message(error, "切换看板失败"), "error"); }
  };
  const changeRegion = async (regionId) => {
    if (currentRegion(state)?.id === Number(regionId)) return;
    const leaving = captureRequest(state); if (!await requestLeave(state, context.confirm, leaving)) return;
    selectRegion(state, regionId); if (state.active) render();
  };
  const createRegion = async (payload) => {
    const token = captureRequest(state); const pendingKey = `create-region:${token?.boardCode || state.activeBoardCode}`; if (!beginPending(state, pendingKey)) return;
    try {
      const created = await api.createRegion(token.boardCode, { ...payload, enabled: true, display_order: 9999 });
      await refreshBoard(token, [created.id]);
      if (shouldRender(token)) { selectRegion(state, created.id); render(); notify("数据区域已新增", "success"); }
    } catch (error) { if (!aborted(error) && shouldRender(token)) notify(message(error, "新增数据区域失败"), "error"); throw error; }
    finally { endPending(state, pendingKey); if (shouldRender(token)) render(); }
  };
  const saveField = async (field, payload) => {
    const token = captureRequest(state); if (!token) return; const pendingKey = `field:${token.key}`; if (!beginPending(state, pendingKey)) return;
    const region = currentRegion(state); const wasSystem = !field && region.system_supported && currentDraft(state)?.source_mode === "system"; const request = { field_alias: payload.alias, name: payload.name, value_type: payload.value_type, nullable: payload.nullable, enabled: payload.enabled, display_order: payload.display_order, description: payload.description, ...(field ? { row_version: payload.row_version } : {}) };
    try {
      if (field) await api.updateField(field.id, request); else await api.createField(region.id, request);
      await refreshBoard(token, [token.regionId]);
      if (shouldRender(token) && wasSystem) notify("已切换为自定义 SQL，需由一条 SQL 返回全部启用字段", "info");
      if (shouldRender(token)) notify("字段已保存，SQL 测试状态已失效。", "success");
    } catch (error) { if (!aborted(error) && shouldRender(token)) notify(message(error, "字段保存失败"), "error"); throw error; }
    finally { endPending(state, pendingKey); if (shouldRender(token)) render(); }
  };
  const saveRegion = async (payload) => {
    const token = captureRequest(state); if (!token) return; const pendingKey = `region:${token.key}`; if (!beginPending(state, pendingKey)) return;
    try { await api.updateRegion(token.regionId, payload); await refreshBoard(token, [token.regionId]); if (shouldRender(token)) notify("区域配置已保存", "success"); }
    catch (error) { if (!aborted(error) && shouldRender(token)) notify(message(error, "区域保存失败"), "error"); throw error; }
    finally { endPending(state, pendingKey); if (shouldRender(token)) render(); }
  };
  const deleteRegion = async (region) => {
    if (region.built_in) return false;
    if (!await context.confirm(`确定删除自定义区域“${region.name}”吗？该区域的字段和数据来源配置将一并删除。`)) return false;
    const boardCode = state.activeBoardCode; const generation = state.lifecycleGeneration; const pendingKey = `delete-region:${region.id}`;
    if (!beginPending(state, pendingKey)) return false;
    try {
      await api.deleteRegion(region.id, { row_version: region.row_version });
      await loadBoard(boardCode, { force: true, generation });
      if (state.active && generation === state.lifecycleGeneration && state.activeBoardCode === boardCode) { render(); notify("数据区域已删除", "success"); }
      return true;
    } catch (error) { if (!aborted(error) && state.active && generation === state.lifecycleGeneration) notify(message(error, "删除数据区域失败"), "error"); return false; }
    finally { endPending(state, pendingKey); }
  };
  const manageRegion = async (targetRegion) => {
    const boardCode = state.activeBoardCode; const generation = state.lifecycleGeneration;
    try {
      const latest = await loadBoard(boardCode, { force: true, generation });
      if (!state.active || generation !== state.lifecycleGeneration || state.activeBoardCode !== boardCode) return;
      const region = latest?.regions?.find((item) => item.id === targetRegion.id);
      if (!region) { render(); notify("数据区域已不存在", "info"); return; }
      openManageRegionDialog(context.root, { region, onSave: saveRegion, onDelete: deleteRegion, notify });
    } catch (error) { if (!aborted(error) && state.active && generation === state.lifecycleGeneration) notify(message(error, "区域信息刷新失败"), "error"); }
  };
  const onTest = async () => {
    const token = captureRequest(state); const draft = token && state.drafts.get(token.key); if (!token || !draft) return; if (draft.source_mode === "sql" && (!draft.datasource_id || !draft.sql_text.trim())) { notify("请选择数据源并填写 SQL 后再测试。", "error"); return; }
    const pendingKey = `test:${token.key}`; if (!beginPending(state, pendingKey)) return; draft.testStatus = "running"; if (shouldRender(token)) render();
    try { const preview = draft.source_mode === "system" ? await api.previewSystem(token.regionId) : await api.testSql(token.regionId, { datasource_id: draft.datasource_id, sql_text: draft.sql_text }); if (!state.active || token.generation !== state.lifecycleGeneration) return; if (recordPreview(state, token, preview)) { if (shouldRender(token)) notify(draft.source_mode === "system" ? "系统数据预览已更新。" : "测试通过，结果预览已更新。", "success"); } else if (shouldRender(token)) notify("测试结果已过期", "info"); }
    catch (error) { if (!aborted(error) && state.active && token.generation === state.lifecycleGeneration) { const original = state.drafts.get(token.key); if (original) original.testStatus = "failed"; if (shouldRender(token)) notify(message(error, draft.source_mode === "system" ? "系统数据读取失败" : "SQL 测试失败"), "error"); } }
    finally { endPending(state, pendingKey); if (shouldRender(token)) render(); }
  };
  const onSave = async () => {
    const token = captureRequest(state); const draft = token && state.drafts.get(token.key); if (!token || !draft) return; const pendingKey = `save:${token.key}`; if (!beginPending(state, pendingKey)) return; if (shouldRender(token)) render();
    try { const saved = await api.saveSource(token.regionId, { source_mode: draft.source_mode, datasource_id: draft.datasource_id || null, sql_text: draft.sql_text || null, row_version: draft.row_version }); if (!state.active || token.generation !== state.lifecycleGeneration) return; if (markSaved(state, token, saved)) { if (shouldRender(token)) notify("配置已保存", "success"); } else if (shouldRender(token)) notify("保存结果已过期", "info"); }
    catch (error) { if (!aborted(error) && shouldRender(token)) notify(message(error, "保存配置失败"), "error"); }
    finally { endPending(state, pendingKey); if (shouldRender(token)) render(); }
  };
  const previewBoard = (board, mode, trigger) => {
    if (mode === "screen") {
      openBoardScreenPreviewDialog(context.root, { board, screenUrl: `/api/modules/dashboard-management/boards/${encodeURIComponent(board.code)}/screen`, trigger });
      return;
    }
    openBoardPreviewDialog(context.root, { board, endpoint: `/api/modules/dashboard-management/boards/${encodeURIComponent(board.code)}/preview`, loadPreview: () => api.previewBoard(board.code), trigger });
  };
  const render = () => {
    if (!state.active) return; const catalog = state.catalogs.get(state.activeBoardCode); clear(context.root);
    if (!catalog) { context.root.append(node("p", { className: "dm-loading", text: "正在加载看板目录…" })); return; }
    const shell = node("section", { className: "dm-management-card" });
    shell.append(renderDashboardTabs({ boards: catalog.boards || [], activeBoardCode: state.activeBoardCode, onSelect: changeBoard, onPreview: previewBoard }));
    const layout = node("div", { className: "dm-layout" }); const region = currentRegion(state); const draft = currentDraft(state);
    layout.append(renderRegionList({ regions: catalog.regions, selectedId: region?.id, canManage, onSelect: changeRegion, onCreate: () => openRegionDialog(context.root, { onCreate: createRegion, notify }), onManage: (targetRegion) => targetRegion && manageRegion(targetRegion) }));
    const detail = node("div", { className: "dm-detail-content" });
    if (!region || !draft) detail.append(node("p", { className: "dm-empty", text: "请选择一个数据区域。" }));
    else {
      const contextBar = node("header", { className: "dm-region-context" });
      contextBar.append(node("h2", { text: region.name }));
      const contextTags = node("div", { className: "dm-region-context-tags" });
      contextTags.append(
        node("span", { className: "dm-context-tag", text: region.shape === "scalar" ? "单值" : "列表" }),
        node("span", { className: "dm-context-tag is-source", text: draft.source_mode === "system" ? "系统数据" : "自定义 SQL" }),
      );
      if (region.enabled === false) contextTags.append(node("span", { className: "dm-context-tag is-disabled", text: "已停用" }));
      contextBar.append(contextTags);
      detail.append(contextBar, renderFieldPanel({ fields: region.fields || [], canManage, onCreate: () => openFieldDialog(context.root, { onSave: (payload) => saveField(null, payload), notify }), onManage: (field) => openFieldDialog(context.root, { field, onSave: (payload) => saveField(field, payload), notify }) }));
      const pending = state.pending.has(`save:${captureRequest(state)?.key}`) || state.pending.has(`test:${captureRequest(state)?.key}`);
      let previewSection;
      let saveButton;
      const invalidateDraftView = (nextDraft) => {
        if (previewSection) { const nextPreview = renderPreviewTable(nextDraft?.preview, nextDraft?.source_mode, region.fields || []); previewSection.replaceWith(nextPreview); previewSection = nextPreview; }
        if (saveButton) saveButton.disabled = !canManage || pending || (nextDraft?.source_mode === "sql" && nextDraft?.testStatus !== "passed");
        return nextDraft;
      };
      const sourcePreviewGrid = node("div", { className: "dm-source-preview-grid" });
      sourcePreviewGrid.append(renderSourceEditor({ region, draft, datasources: state.datasources || [], canManage, canTest, pending, onMode: (mode) => { setSourceMode(state, mode); render(); }, onDatasource: (value) => invalidateDraftView(markDatasourceChanged(state, value)), onSql: (value) => invalidateDraftView(markSqlChanged(state, value)), onTest }));
      previewSection = renderPreviewTable(draft.preview, draft.source_mode, region.fields || []); sourcePreviewGrid.append(previewSection); detail.append(sourcePreviewGrid);
      const saveBar = node("div", { className: "dm-save-bar" }); saveBar.append(node("p", { text: draft.source_mode === "sql" ? "测试通过后保存当前配置" : "保存当前系统数据配置" })); saveButton = button("保存配置", "dm-button dm-button-primary", onSave, { disabled: !canManage || pending || (draft.source_mode === "sql" && draft.testStatus !== "passed") }); saveBar.append(saveButton); detail.append(saveBar);
    }
    const panels = node("div", { className: "dm-detail-panels" });
    (catalog.boards || []).forEach((board) => {
      const panel = node("main", { className: "dm-detail", attrs: { id: `dm-panel-${board.code}`, role: "tabpanel", "aria-labelledby": `dm-tab-${board.code}` } });
      panel.hidden = board.code !== state.activeBoardCode;
      if (!panel.hidden) panel.append(detail);
      panels.append(panel);
    });
    layout.append(panels); shell.append(layout); context.root.append(shell);
  };
  return {
    async activate() { activateLifecycle(state); const generation = state.lifecycleGeneration; try { const selectedCatalog = await loadBoard(state.activeBoardCode, { generation }); const boards = selectedCatalog?.boards || []; await Promise.all(boards.map((board) => loadBoard(board.code, { generation }))); if (!state.datasources) state.datasources = await api.datasources(); } catch (error) { if (!aborted(error) && state.active && generation === state.lifecycleGeneration) notify(message(error, "看板管理加载失败"), "error"); } if (state.active && generation === state.lifecycleGeneration) render(); },
    deactivate() { stopRequests(state); },
    unmount() { stopRequests(state); clear(context.root); },
  };
}
export function mount(context) { if (!context?.root || typeof context.api !== "function" || typeof context.user !== "function" || typeof context.notify !== "function" || typeof context.confirm !== "function") throw new Error("看板管理模块缺少宿主能力"); instance = createPage(context); }
export function activate(route) { if (!instance) throw new Error("看板管理模块尚未挂载"); return instance.activate(route); }
export function deactivate() { instance?.deactivate(); }
export function unmount() { instance?.unmount(); instance = null; }
