const API_PREFIX = "/api/modules/data-validation";

function queryString(values) {
  const params = new URLSearchParams();
  Object.entries(values || {}).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) params.set(key, String(value));
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

function body(method, payload, options = {}) {
  return { ...options, method, body: JSON.stringify(payload ?? {}) };
}

export function createApi(context) {
  const request = (path, options = {}) => {
    const aiWrite = path.startsWith("/ai/") && ["POST", "DELETE"].includes(options.method);
    return context.api(`${API_PREFIX}${path}`, aiWrite ? { ...options, authPreflight: true } : options)
      .then((payload) => payload?.data ?? payload);
  };
  const executionRequest = (path, options) => request(path, options).catch(error => {
    const message = error?.payload?.error;
    if ((error?.status === 400 && message === "invalid request")
        || (error?.status === 404 && message === "module route not found")) {
      error.code = "TASK_API_VERSION_MISMATCH";
    }
    throw error;
  });

  return {
    rules: (query = {}, options = {}) => request(`/rules${queryString({
      page: query.page || 1,
      page_size: query.page_size || 50,
      keyword: query.keyword || "",
      status: query.status || "",
      report_category: query.report_category || "",
      source_id: query.source_id || "",
      rule_type: query.rule_type || "",
    })}`, options),
    stats: (options = {}) => request("/rules/stats", options),
    reportCategories: (options = {}) => request("/report-categories", options),
    rule: (ruleId, options = {}) => request(`/rules/${encodeURIComponent(ruleId)}`, options),
    ruleHistory: (ruleId, query = {}, options = {}) => request(
      `/rules/${encodeURIComponent(ruleId)}/history${queryString({
        page: query.page || 1,
        page_size: query.page_size || 20,
      })}`, options,
    ),
    sources: (options = {}) => request("/sources", options),
    describe: (sourceId, tableName, options = {}) => request(
      `/sources/${encodeURIComponent(sourceId)}/tables/${encodeURIComponent(tableName)}`, options,
    ),
    save: (payload, ruleId, options = {}) => request(
      ruleId ? `/rules/${encodeURIComponent(ruleId)}` : "/rules",
      body(ruleId ? "PUT" : "POST", payload, options),
    ),
    copy: (ruleId, options = {}) => request(`/rules/${encodeURIComponent(ruleId)}/copy`, body("POST", {}, options)),
    disable: (ruleId, { expected_rule, ...options } = {}) => request(`/rules/${encodeURIComponent(ruleId)}/disable`, body("POST", expected_rule ? { expected_rule } : {}, options)),
    deleteRule: (ruleId, options = {}) => request(`/rules/${encodeURIComponent(ruleId)}`, body("DELETE", {}, options)),
    models: (options = {}) => request("/models", options),
    testModel: (modelId, options = {}) => request("/models/test", body("POST", { model_id: modelId }, options)),
    documents: (options = {}) => request("/settings/documents", options),
    importDocument: (payload, options = {}) => request("/settings/documents", body("POST", payload, options)),
    activateDocument: (documentId, options = {}) => request(
      `/settings/documents/${encodeURIComponent(documentId)}/activate`, body("POST", {}, options),
    ),
    knowledge: (options = {}) => request("/settings/knowledge", options),
    previewKnowledge: (payload, options = {}) => request("/settings/knowledge/preview", body("POST", payload, options)),
    saveKnowledge: (payload, options = {}) => request("/settings/knowledge", body("PUT", payload, options)),
    activateKnowledge: (payload, options = {}) => request("/settings/knowledge/activation", body("POST", payload, options)),
    prompts: (options = {}) => request("/settings/prompts", options),
    savePrompt: (payload, options = {}) => request("/settings/prompts", body("POST", payload, options)),
    resetPrompt: (stage, options = {}) => request(
      `/settings/prompts/${encodeURIComponent(stage)}/reset`, body("POST", {}, options),
    ),
    sourceRules: (options = {}) => request("/settings/source-rules", options),
    saveSourceRules: (rules, options = {}) => request("/settings/source-rules", body("POST", { rules }, options)),
    parse: (payload, options = {}) => request("/ai/parse-rule", body("POST", payload, options)),
    createAnalysis: (payload, options = {}) => request("/ai/analyses", body("POST", payload, options)),
    batchSaveCandidates: (payload, options = {}) => request(
      "/ai/candidates/batch-save", body("POST", payload, options),
    ),
    getAnalysis: (analysisId, options = {}) => request(`/ai/analyses/${encodeURIComponent(analysisId)}`, options),
    cancelAnalysis: (analysisId, options = {}) => request(
      `/ai/analyses/${encodeURIComponent(analysisId)}`, body("DELETE", {}, options),
    ),
    preview: (payload, options = {}) => request("/ai/preview", body("POST", payload, options)),
    testCandidate: (payload, options = {}) => request("/ai/tests", body("POST", payload, options)),
    runCandidateSql: (payload, options = {}) => request("/ai/sql-test", body("POST", payload, options)),
    test: (ruleId, payload, options = {}) => request(
      `/rules/${encodeURIComponent(ruleId)}/tests`, body("POST", payload, options),
    ),
    confirm: (ruleId, payload, options = {}) => request(
      `/rules/${encodeURIComponent(ruleId)}/confirm`, body("POST", payload, options),
    ),
    startTask: (payload, options = {}) => request("/tasks", body("POST", payload, options)),
    executionRuleIds: (query = {}, options = {}) => executionRequest(`/rules/execution-selection${queryString({
      keyword: query.keyword || "", source_id: query.source_id || "", report_category: query.report_category || "",
    })}`, options),
    taskProgress: (ids = [], { report_category = "", ...options } = {}) => executionRequest(`/tasks/progress${queryString({
      task_ids: ids.join(","), report_category,
    })}`, options),
    tasks: (query = {}, options = {}) => request(`/tasks${queryString({ report_period: query.report_period || "", report_category: query.report_category || "" })}`, options),
    taskDetails: (taskId, query = {}, options = {}) => request(
      `/tasks/${encodeURIComponent(taskId)}${queryString({ report_category: query.report_category || "", keyword: query.keyword || "",
        page: query.page || "", page_size: query.page_size || "", only_issues: query.only_issues ? "1" : "" })}`, options,
    ),
    issues: (taskId, query = {}, options = {}) => request(
      `/tasks/${encodeURIComponent(taskId)}/issues${queryString({
        page: query.page || 1,
        page_size: query.page_size || 50,
        report_category: query.report_category || "",
        rule_id: query.rule_id || "",
      })}`, options,
    ),
    cancelTask: (taskId, options = {}) => request(`/tasks/${encodeURIComponent(taskId)}/cancel`, body("POST", {}, options)),
    pauseTask: (taskId, options = {}) => request(`/tasks/${encodeURIComponent(taskId)}/pause`, body("POST", {}, options)),
    resumeTask: (taskId, options = {}) => request(`/tasks/${encodeURIComponent(taskId)}/resume`, body("POST", {}, options)),
    retryTask: (taskId, options = {}) => request(`/tasks/${encodeURIComponent(taskId)}/retry`, body("POST", {}, options)),
    exportIssues: (taskId, { report_category = "", rule_id = null, ...options } = {}) => request(
      "/exports", body("POST", { task_id: taskId, file_type: "csv", report_category, ...(rule_id ? { rule_id } : {}) }, options),
    ),
    exportRulePack: (ruleIds, options = {}) => request("/rule-packs/export", body("POST", { rule_ids: ruleIds }, options)),
    importRulePack: (content, options = {}) => request("/rule-packs/import", body("POST", { content }, options)),
  };
}
