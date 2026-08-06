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
  const isVersionConflict = code === "record_version_conflict";
  const normalized = new Error(
    isVersionConflict
      ? CONFLICT_MESSAGE
      : status >= 500 || code === "internal_error"
        ? "服务暂时不可用，请稍后重试"
        : error?.payload?.error?.message || error?.message || "请求失败，请重试",
  );
  normalized.status = status;
  normalized.code = code;
  normalized.fields = error?.payload?.error?.fields || {};
  normalized.refreshRequired = isVersionConflict;
  return normalized;
}

function filenameFromDisposition(header) {
  const raw = String(header || "");
  const utfMatch = raw.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (utfMatch) {
    try {
      return decodeURIComponent(utfMatch[1].trim().replace(/"/g, ""));
    } catch (_error) {
      return utfMatch[1].trim().replace(/"/g, "");
    }
  }
  const plain = raw.match(/filename\s*=\s*"?([^";]+)"?/i);
  return plain ? plain[1].trim() : "";
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

  async function download(path, parameters = {}) {
    const controller = new AbortController();
    controllers.add(controller);
    try {
      const response = await fetch(`${API_PREFIX}${path}${queryString(parameters)}`, {
        method: "GET",
        credentials: "same-origin",
        signal: controller.signal,
      });
      if (response.status === 401) {
        const error = new Error("login required");
        error.status = 401;
        throw normalizeError(error);
      }
      if (!response.ok) {
        let payload = null;
        try {
          payload = await response.json();
        } catch (_error) {
          payload = null;
        }
        const error = new Error(payload?.error?.message || `请求失败: ${response.status}`);
        error.status = response.status;
        error.payload = payload;
        throw normalizeError(error);
      }
      const blob = await response.blob();
      if (!blob.size) throw normalizeError(new Error("生成的导出文件为空"));
      return {
        blob,
        filename: filenameFromDisposition(response.headers.get("Content-Disposition")) || "报表特殊处理导出.xlsx",
      };
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw normalizeError(error);
    } finally {
      controllers.delete(controller);
    }
  }

  return Object.freeze({
    catalog: () => request("/catalog"),
    listRecords: (parameters) => request(`/records${queryString(parameters)}`),
    exportRecords: (parameters) => download("/records/export", parameters),
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
