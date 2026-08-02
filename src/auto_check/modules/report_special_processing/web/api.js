const API_PREFIX = "/api/modules/report-special-processing";
const SUMMARY_PATH = "/summary";
const STATUS_PATH = "/status";
const VOID_PATH = "/void";
const REOPEN_PATH = "/reopen";
const AUDIT_PATH = "/audit";
const CONFLICT_MESSAGE = "记录已被其他人更新，请刷新后重试";

function queryString(parameters = {}) {
  const query = new URLSearchParams();
  Object.entries(parameters).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) query.set(key, String(value));
  });
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

function bodyOptions(method, payload) {
  return { method, body: JSON.stringify(payload) };
}

function normalizeError(error) {
  if (error?.name === "AbortError") return error;
  const code = error?.payload?.error?.code || "internal_error";
  const status = Number(error?.status || 0);
  const normalized = new Error(
    status === 409 || code === "record_version_conflict"
      ? CONFLICT_MESSAGE
      : status >= 500 || code === "internal_error"
        ? "服务暂时不可用，请稍后重试"
        : error?.payload?.error?.message || error?.message || "请求失败，请重试",
  );
  normalized.status = status;
  normalized.code = code;
  normalized.fields = error?.payload?.error?.fields || {};
  normalized.refreshRequired = status === 409 || code === "record_version_conflict";
  return normalized;
}

export function createApi(context) {
  const controllers = new Set();

  async function request(path, options = {}) {
    const controller = new AbortController();
    controllers.add(controller);
    try {
      return await context.api(`${API_PREFIX}${path}`, { ...options, signal: controller.signal });
    } catch (error) {
      throw normalizeError(error);
    } finally {
      controllers.delete(controller);
    }
  }

  return Object.freeze({
    catalog: () => request("/catalog"),
    listRecords: (parameters) => request(`/records${queryString(parameters)}`),
    summary: (reportPeriod) => request(`${SUMMARY_PATH}${queryString({ report_period: reportPeriod })}`),
    getRecord: (id) => request(`/records/${encodeURIComponent(id)}`),
    createRecord: (payload) => request("/records", bodyOptions("POST", payload)),
    updateRecord: (id, payload) => request(`/records/${encodeURIComponent(id)}`, bodyOptions("PUT", payload)),
    changeStatus: (id, payload) => request(`/records/${encodeURIComponent(id)}${STATUS_PATH}`, bodyOptions("POST", payload)),
    voidRecord: (id, payload) => request(`/records/${encodeURIComponent(id)}${VOID_PATH}`, bodyOptions("POST", payload)),
    reopenRecord: (id, payload) => request(`/records/${encodeURIComponent(id)}${REOPEN_PATH}`, bodyOptions("POST", payload)),
    audit: (id, parameters) => request(`/records/${encodeURIComponent(id)}${AUDIT_PATH}${queryString(parameters)}`),
    cancelAll() {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    },
  });
}
