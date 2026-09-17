const DEFAULT_BOARD = "report_submission";
export const SELECTION_STORAGE_KEY = "auto-check.dashboard-management.selection.v1";
function draftKey(boardCode, regionId) { return `${boardCode}:${regionId}`; }
function copyDraft(region, { forceIdle = false, revision = 1 } = {}) {
  const source = region.source_config || {};
  return { region_id: region.id, row_version: source.row_version || 1, source_mode: source.source_mode || region.default_mode || "sql", datasource_id: source.datasource_id || "", sql_text: source.sql_text || "", testStatus: !forceIdle && source.tested_signature ? "passed" : "idle", testError: "", preview: null, revision };
}
function cloneDraft(draft) { return { ...draft, preview: draft.preview ? { ...draft.preview, rows: [...(draft.preview.rows || [])] } : null }; }
function keyForToken(token) { return token?.key || draftKey(token?.boardCode, token?.regionId); }
function samePersistedSource(left, right) {
  return Boolean(left && right)
    && left.source_mode === right.source_mode
    && String(left.datasource_id || "") === String(right.datasource_id || "")
    && String(left.sql_text || "") === String(right.sql_text || "");
}
function syncDirtyRegion(state, region, draft) {
  const key = draftKey(state.activeBoardCode, region.id);
  if (samePersistedSource(draft, state.serverSnapshots.get(key))) state.dirtyRegions.delete(key);
  else state.dirtyRegions.add(key);
  return draft;
}

function defaultSelectionStorage() {
  try { return globalThis.sessionStorage || null; } catch (_error) { return null; }
}
function restoredSelection(storage) {
  try {
    const value = JSON.parse(storage?.getItem(SELECTION_STORAGE_KEY) || "null");
    const activeBoardCode = typeof value?.activeBoardCode === "string" && value.activeBoardCode ? value.activeBoardCode : DEFAULT_BOARD;
    const selections = Object.entries(value?.selectedRegionByBoard || {}).flatMap(([boardCode, regionId]) => {
      const normalized = Number(regionId);
      return boardCode && Number.isInteger(normalized) && normalized > 0 ? [[boardCode, normalized]] : [];
    });
    return { activeBoardCode, selectedRegionByBoard: new Map(selections) };
  } catch (_error) { return { activeBoardCode: DEFAULT_BOARD, selectedRegionByBoard: new Map() }; }
}
function persistSelection(state) {
  try {
    state.selectionStorage?.setItem(SELECTION_STORAGE_KEY, JSON.stringify({
      activeBoardCode: state.activeBoardCode,
      selectedRegionByBoard: Object.fromEntries(state.selectedRegionByBoard),
    }));
  } catch (_error) { /* 浏览器禁用会话存储时仍保持页面内选择。 */ }
}
export function createState(selectionStorage = defaultSelectionStorage()) {
  const selection = restoredSelection(selectionStorage);
  return { activeBoardCode: selection.activeBoardCode, selectedRegionByBoard: selection.selectedRegionByBoard, selectionStorage, catalogs: new Map(), drafts: new Map(), serverSnapshots: new Map(), previews: new Map(), dirtyRegions: new Set(), pending: new Set(), requestController: null, requestControllers: new Set(), lifecycleGeneration: 0, active: true, viewMode: "management", managementScrollTop: 0, monitorSummary: null, monitorCalls: null, monitorFilters: { board_code: "", result_status: "", caller_ip: "", started_at: "", ended_at: "" }, monitorPage: 1, monitorLoading: false, monitorError: "" };
}
export function applyCatalog(state, boardCode, catalog, { resetRegionIds = [] } = {}) {
  const reset = new Set(resetRegionIds.map(Number));
  const normalized = { ...catalog, regions: Array.isArray(catalog?.regions) ? catalog.regions : [] };
  state.catalogs.set(boardCode, normalized);
  const selected = state.selectedRegionByBoard.get(boardCode);
  if (!normalized.regions.some((region) => region.id === selected)) { state.selectedRegionByBoard.set(boardCode, normalized.regions[0]?.id || null); persistSelection(state); }
  normalized.regions.forEach((region) => {
    const key = draftKey(boardCode, region.id);
    if (!state.drafts.has(key) || reset.has(Number(region.id))) {
      const draft = copyDraft(region, { forceIdle: reset.has(Number(region.id)), revision: (state.drafts.get(key)?.revision || 0) + 1 });
      state.drafts.set(key, draft); state.serverSnapshots.set(key, cloneDraft(draft)); state.previews.delete(key); state.dirtyRegions.delete(key);
    } else state.serverSnapshots.set(key, copyDraft(region));
  });
  return normalized;
}
export function selectBoard(state, boardCode) { state.activeBoardCode = boardCode; const catalog = state.catalogs.get(boardCode); if (catalog && !state.selectedRegionByBoard.get(boardCode)) state.selectedRegionByBoard.set(boardCode, catalog.regions[0]?.id || null); persistSelection(state); return currentRegion(state); }
export function currentRegion(state) { const catalog = state.catalogs.get(state.activeBoardCode); const selectedId = state.selectedRegionByBoard.get(state.activeBoardCode); return catalog?.regions.find((region) => region.id === selectedId) || null; }
export function selectRegion(state, regionId) { state.selectedRegionByBoard.set(state.activeBoardCode, Number(regionId)); persistSelection(state); return currentRegion(state); }
export function currentDraft(state) { const region = currentRegion(state); return region ? state.drafts.get(draftKey(state.activeBoardCode, region.id)) || null : null; }
export function captureRequest(state) { const region = currentRegion(state); const draft = currentDraft(state); return region && draft ? { boardCode: state.activeBoardCode, regionId: region.id, key: draftKey(state.activeBoardCode, region.id), generation: state.lifecycleGeneration, revision: draft.revision } : null; }
export function isTokenCurrent(state, token) { return Boolean(token && state.active && token.generation === state.lifecycleGeneration && token.boardCode === state.activeBoardCode && state.selectedRegionByBoard.get(token.boardCode) === token.regionId); }
export function beginPending(state, key) { if (state.pending.has(key)) return false; state.pending.add(key); return true; }
export function endPending(state, key) { state.pending.delete(key); }
export function setSourceMode(state, sourceMode) { const region = currentRegion(state); const draft = currentDraft(state); if (!region || !draft || draft.source_mode === sourceMode || (sourceMode === "system" && !region.system_supported)) return draft; draft.source_mode = sourceMode; draft.testStatus = "idle"; draft.testError = ""; draft.preview = null; draft.revision += 1; state.previews.delete(draftKey(state.activeBoardCode, region.id)); return syncDirtyRegion(state, region, draft); }
export function markSqlChanged(state, sqlText) { const region = currentRegion(state); const draft = currentDraft(state); if (!region || !draft) return null; if (draft.sql_text === sqlText) return draft; draft.sql_text = sqlText; draft.testStatus = "idle"; draft.testError = ""; draft.preview = null; draft.revision += 1; state.previews.delete(draftKey(state.activeBoardCode, region.id)); return syncDirtyRegion(state, region, draft); }
export function markDatasourceChanged(state, datasourceId) { const region = currentRegion(state); const draft = currentDraft(state); if (!region || !draft || String(draft.datasource_id || "") === String(datasourceId || "")) return draft; draft.datasource_id = datasourceId; draft.testStatus = "idle"; draft.testError = ""; draft.preview = null; draft.revision += 1; state.previews.delete(draftKey(state.activeBoardCode, region.id)); return syncDirtyRegion(state, region, draft); }
export function recordPreview(state, token, preview) { const key = keyForToken(token); const draft = state.drafts.get(key); if (!draft || token?.generation !== state.lifecycleGeneration || token?.revision !== draft.revision) return null; const safePreview = { ...preview, rows: previewRows(preview?.rows || []) }; draft.preview = safePreview; draft.testStatus = "passed"; draft.testError = ""; if (Number.isInteger(preview?.row_version) && preview.row_version > 0) draft.row_version = preview.row_version; state.previews.set(key, safePreview); return safePreview; }
export function markPreviewFailed(state, token, reason) { const key = keyForToken(token); const draft = state.drafts.get(key); if (!draft || token?.generation !== state.lifecycleGeneration || token?.revision !== draft.revision) return null; draft.testStatus = "failed"; draft.testError = String(reason || "").trim(); return draft; }
export function markSaved(state, token, sourceConfig) { const key = keyForToken(token); const draft = state.drafts.get(key); if (!draft || token?.generation !== state.lifecycleGeneration || token?.revision !== draft.revision) return null; draft.row_version = sourceConfig?.row_version || draft.row_version; if (sourceConfig?.source_mode) draft.source_mode = sourceConfig.source_mode; const sqlWarning = String(sourceConfig?.sql_warning || "").trim(); if (sqlWarning && draft.testStatus !== "failed") { draft.testStatus = "failed"; draft.testError = sqlWarning; } state.serverSnapshots.set(key, cloneDraft(draft)); state.dirtyRegions.delete(key); return draft; }
export function discardDraft(state, token) { const key = keyForToken(token); const snapshot = state.serverSnapshots.get(key); const current = state.drafts.get(key); if (!snapshot || !current) return null; const restored = cloneDraft(snapshot); restored.revision = current.revision + 1; state.drafts.set(key, restored); state.previews.delete(key); state.dirtyRegions.delete(key); return restored; }
export function previewRows(rows) { return Array.isArray(rows) ? rows.slice(0, 10) : []; }
export function hasPermission(user, permission) { const capabilities = user?.capabilities || []; return user?.role === "admin" || capabilities.includes(permission) || capabilities.includes(`sys.${permission}`); }
export async function requestLeave(state, confirm, token = captureRequest(state)) { if (!token || !state.dirtyRegions.has(keyForToken(token))) return true; const accepted = Boolean(await confirm("当前区域存在未保存修改，确定离开并放弃修改吗？")); if (accepted) discardDraft(state, token); return accepted; }
export function startRequest(state, context, path, options = {}) { const controller = new AbortController(); state.requestController = controller; state.requestControllers.add(controller); return context.api(path, { ...options, signal: controller.signal }).finally(() => { state.requestControllers.delete(controller); if (state.requestController === controller) state.requestController = null; }); }
export function activateLifecycle(state) { state.active = true; }
export function stopRequests(state) { state.lifecycleGeneration += 1; state.active = false; state.requestControllers.forEach((controller) => controller.abort()); state.requestControllers.clear(); state.requestController = null; }
export function enterMonitorView(state, scrollTop = 0) {
  state.managementScrollTop = Math.max(0, Number(scrollTop) || 0);
  state.viewMode = "monitor";
}
export function leaveMonitorView(state) {
  state.viewMode = "management";
}
export function resetMonitorFilters(state) {
  state.monitorFilters = { board_code: "", result_status: "", caller_ip: "", started_at: "", ended_at: "" };
  state.monitorPage = 1;
}
