const API_PREFIX = "/api/modules/dashboard-management";

function unwrap(response) {
  return response?.data ?? response;
}

function monitorDateBoundaryIso(key, value) {
  const boundary = key === "ended_at" ? "T23:59:59.999" : "T00:00:00.000";
  return new Date(`${value}${boundary}`).toISOString();
}

export function createApi(context, state) {
  if (typeof context?.api !== "function") throw new Error("看板管理模块缺少 API 能力");
  const request = (path, options = {}, unwrapPayload = true) => {
    const controller = new AbortController();
    state.requestController = controller;
    state.requestControllers.add(controller);
    return context.api(`${API_PREFIX}${path}`, { ...options, signal: controller.signal })
      .then((response) => unwrapPayload ? unwrap(response) : response)
      .finally(() => {
        state.requestControllers.delete(controller);
        if (state.requestController === controller) state.requestController = null;
      });
  };
  const body = (method, payload) => ({ method, body: JSON.stringify(payload) });
  return Object.freeze({
    boards: () => request("/boards"),
    catalog: (boardCode) => request(`/boards/${encodeURIComponent(boardCode)}/catalog`),
    previewBoard: (boardCode) => request(`/boards/${encodeURIComponent(boardCode)}/preview`, {}, false),
    datasources: () => request("/datasources"),
    createRegion: (boardCode, payload) => request(`/boards/${encodeURIComponent(boardCode)}/regions`, body("POST", payload)),
    updateRegion: (regionId, payload) => request(`/regions/${encodeURIComponent(regionId)}`, body("PUT", payload)),
    deleteRegion: (regionId, payload) => request(`/regions/${encodeURIComponent(regionId)}`, body("DELETE", payload)),
    createField: (regionId, payload) => request(`/regions/${encodeURIComponent(regionId)}/fields`, body("POST", payload)),
    updateField: (fieldId, payload) => request(`/fields/${encodeURIComponent(fieldId)}`, body("PUT", payload)),
    testSql: (regionId, payload) => request(`/regions/${encodeURIComponent(regionId)}/source/test`, body("POST", payload)),
    previewSystem: (regionId) => request(`/regions/${encodeURIComponent(regionId)}/source/system-preview`, { method: "POST" }),
    saveSource: (regionId, payload) => request(`/regions/${encodeURIComponent(regionId)}/source`, body("PUT", payload)),
    generateExternalApiToken: () => request("/external-api/token/generate", body("POST", {}), false),
    monitorSummary: () => request("/external-api/monitor/summary"),
    monitorCalls: (filters = {}) => {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(filters)) {
        if (!value) continue;
        const normalized = (key === "started_at" || key === "ended_at")
          ? monitorDateBoundaryIso(key, value)
          : value;
        params.set(key, normalized);
      }
      params.set("page", String(filters.page || 1));
      params.set("page_size", String(filters.page_size || 10));
      return request(`/external-api/monitor/calls?${params.toString()}`);
    },
  });
}
