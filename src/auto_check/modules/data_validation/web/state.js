import { comparisons, fieldTarget } from "./comparisons.js";

export const PAGE_SIZES = [20, 50, 100];
export const MAX_TASK_RULES = 100000;
export const ALL_FIELD_CHOICES = "__all_field_choices__";

export function visibleSql(record, rawKey = "sql_text") {
  if (!record || record.sql_display_error) return "";
  if (typeof record.sql_display === "string") return record.sql_display;
  const raw = record[rawKey] || "";
  // Older snapshots without display SQL are usable only if static bindings are absent.
  return /(?<!:):(?!report_date\b)[A-Za-z_]\w*/.test(raw) ? "" : raw;
}

export function canChooseAllFields(question) {
  return Boolean(fieldTarget(question?.id))
    && question.options?.length > 1 && question.options.every((option) => typeof option.value === "string" && !option.selection);
}

export function reportCategoryCode(value) {
  const code = String(value || "");
  return code === "pbc_central" || code === "pbc_template" ? "group:pbc" : code;
}

export function targetTableLabel(rule) {
  const table = String(rule.table_name || "—").trim();
  const chinese = String(rule.table_name_cn || "").trim()
    .replace(/\s*[（(]([^（）()\r\n]*)[）)]\s*$/, (group, reference) =>
      /\.ktr$/i.test(reference.trim()) || reference.trim() === table ? "" : group).trim();
  return chinese && chinese !== table ? `${chinese}（${table}）` : table;
}

// 规则状态字典与后端实际产生的状态一一对应；未命中时回退显示后端原始 code。
export const RULE_STATUS_LABELS = {
  draft: "草稿",
  enabled: "已启用",
  disabled: "已停用",
  deleted: "已删除",
};

// 规则类型字典收敛为当前实际支持创建的类型；其余类型回退显示后端原始 code，不编造文案。
export const RULE_TYPE_LABELS = {
  field_compare: "字段比较",
};

export const TASK_STATUS_LABELS = {
  queued: "排队中（queued）",
  running: "运行中（running）",
  completed: "已完成（completed）",
  partial_failed: "部分失败（partial_failed）",
  failed: "失败（failed）",
  cancelled: "已取消（cancelled）",
};

export function emptyPage(pageSize = 50) {
  return { items: [], total: 0, page: 1, page_size: pageSize };
}

export function createState() {
  return {
    activeTab: "rules",
    ruleQuery: { keyword: "", status: "", report_category: "", source_id: "", rule_type: "", page: 1, page_size: 50 },
    rules: emptyPage(50),
    rulesStatus: "idle",
    rulesError: "",
    stats: {
      total: 0, enabled: 0, disabled: 0, draft: 0, categories: [],
      unclassified: { total: 0, enabled: 0, disabled: 0, draft: 0 },
    },
    statsStatus: "idle",
    categories: [],
    categoriesStatus: "idle",
    categoriesError: "",
    selectedRules: new Map(),
    sources: [],
    sourcesStatus: "idle",
    sourcesError: "",
    models: [],
    modelsStatus: "idle",
    modelsError: "",
    reportPeriod: previousMonthEnd(),
    tasks: [],
    tasksStatus: "idle",
    tasksError: "",
    activeTaskId: null,
    issues: emptyPage(50),
    issuesStatus: "idle",
    issuesError: "",
    issueQuery: { page: 1, page_size: 50 },
  };
}

export function hasCapability(user, capability) {
  if (user?.role === "admin") return true;
  return Array.isArray(user?.capabilities) && user.capabilities.includes(capability);
}

export function ownsResource(user, resource) {
  return user?.id !== undefined && user?.id !== null
    && String(resource?.creator_user_id) === String(user.id);
}

export function displayUser(user) {
  return user?.display_name || user?.username || String(user?.id ?? "当前用户");
}

export function updateRuleFilter(state, patch) {
  Object.assign(state.ruleQuery, patch, { page: 1 });
  state.selectedRules.clear();
  return state.ruleQuery;
}

export function clearRuleFilters(state) {
  return updateRuleFilter(state, { keyword: "", status: "", report_category: "", source_id: "", rule_type: "" });
}

export function setRulePageSize(state, pageSize) {
  const safeSize = PAGE_SIZES.includes(Number(pageSize)) ? Number(pageSize) : 50;
  return updateRuleFilter(state, { page_size: safeSize });
}

export function newEnabledRuleQuery() {
  return { keyword: "", status: "enabled", page: 1, page_size: 20 };
}

export function totalPages(payload) {
  const total = Math.max(0, Number(payload?.total) || 0);
  const size = Math.max(1, Number(payload?.page_size) || 50);
  return total ? Math.max(1, Math.ceil(total / size)) : 1;
}

export function pageConvergence(payload, requestedPage) {
  const requested = Math.max(1, Number(requestedPage) || 1);
  const total = Math.max(0, Number(payload?.total) || 0);
  const target = total ? Math.min(requested, totalPages(payload)) : 1;
  return target === requested ? null : target;
}

export async function loadConvergedPage({ query, request, onConverge, isCurrent = () => true }) {
  const first = await request(query);
  if (!isCurrent()) return first;
  const target = pageConvergence(first, query.page);
  if (target === null) return first;
  onConverge(target);
  if (!isCurrent()) return first;
  return request({ ...query, page: target });
}

export function paginationView(payload) {
  const total = Math.max(0, Number(payload?.total) || 0);
  const pages = totalPages(payload);
  const page = total ? Math.min(Math.max(1, Number(payload?.page) || 1), pages) : 1;
  return {
    total,
    pages,
    page,
    info: total ? `共 ${total} 条，第 ${page} / ${pages} 页` : "暂无数据",
    current: total ? String(page) : "-",
    previousDisabled: !total || page <= 1,
    nextDisabled: !total || page >= pages,
  };
}

export function updateBoundedSelection(selection, rule, checked, limit = MAX_TASK_RULES) {
  const id = Number(rule?.id);
  if (!Number.isInteger(id) || id <= 0) return { ok: false, reason: "规则编号无效" };
  if (!checked) {
    selection.delete(id);
    return { ok: true, reason: "" };
  }
  if (!selection.has(id) && selection.size >= limit) {
    return { ok: false, reason: `单个任务最多选择 ${limit} 条规则，请先取消部分选择` };
  }
  selection.set(id, rule);
  return { ok: true, reason: "" };
}

export function createTestEvidence(detail, result) {
  return {
    ...result,
    version_no: Number(detail.version_no),
    content_sha256: String(detail.content_sha256 || ""),
    cases: Array.isArray(result?.cases) ? result.cases : [],
  };
}

export function ruleScopeIssues(definition = {}, { detailed = false } = {}) {
  const reasons = [];
  if (definition.unsupported_requirements?.length) {
    reasons.push(...(detailed ? definition.unsupported_requirements : ["存在当前规则无法表达的要求，请调整需求并重新生成"]));
  }
  const questions = definition.uncertainties || [];
  const resolutions = definition.uncertainty_resolutions || [];
  if (!Array.isArray(questions) || !Array.isArray(resolutions)
      || questions.length !== resolutions.length || resolutions.some((item) => typeof item !== "string" || !item.trim())) {
    const pending = Array.isArray(questions) && Array.isArray(resolutions)
      ? questions.filter((_, index) => !String(resolutions[index] || "").trim()) : [];
    reasons.push(...(detailed && pending.length ? pending : ["待确认口径尚未逐项填写处理说明"]));
  }
  if (definition.null_policy === "unresolved" || definition.equality_policy === "unresolved") {
    reasons.push("空值或相等口径仍未确认");
  }
  if (definition.null_policy === "zero") {
    const binary = comparisons(definition.expression).filter((item) => !["is_null", "is_not_null"].includes(item.op));
    const zeroAllowed = binary.length > 0 && binary.every((item) => ["field", "formula"].includes(item.right_type || "field") && Boolean(item.right)
      || (item.right_type === "value" && Number.isFinite(item.right)));
    if (!zeroAllowed) reasons.push("NULL按0仅支持数值字段比较或有限数值常量");
  }
  const filters = Array.isArray(definition.filters) ? definition.filters : [];
  const unconfirmedFilters = filters.filter((item) => !item || item.confirmed !== true);
  if (unconfirmedFilters.length) reasons.push(`还有 ${unconfirmedFilters.length} 个筛选条件未确认`);
  const join = definition.join;
  if (join && join.table_name) {
    const relationshipConfirmed = join.relationship_confirmed === true || definition.relationship_confirmed === true;
    const unmatchedPolicy = join.unmatched_policy || definition.unmatched_policy;
    if (!relationshipConfirmed) reasons.push("关联关系尚未确认");
    const handlesMissingRows = unmatchedPolicy === "exclude" || (join.right_aggregate === "sum" && unmatchedPolicy === "review");
    if (!handlesMissingRows) reasons.push("关联未匹配记录的处理口径尚未确认");
    if (!Array.isArray(join.on) || !join.on.length) reasons.push("关联字段尚未确认");
    if (!join.report_date_field) reasons.push("关联表校验日期尚未确认");
  }
  const projectContext = definition.project_context;
  if (projectContext && projectContext.mode && projectContext.confirmed !== true) {
    reasons.push("项目上下文口径尚未确认");
  }
  return reasons;
}

export function candidateIssues(candidate = {}) {
  const issues = [candidate.parallel_blocked, candidate.preview_error, ...ruleScopeIssues(candidate, { detailed: true })];
  if (candidate.rule_type !== "field_compare" || candidate.status === "needs_clarification") {
    if (!issues.some(Boolean) && !candidate.questions?.length) issues.push("请补充要检查的业务对象和判断条件。");
  }
  return [...new Set(issues.filter(Boolean))];
}

// Older responses can contain both SQL and pending questions. Keep the decisions,
// and accept the preview only when both the candidate and its definition are ready.
export function reviewCandidate(candidate, preview = candidate.preview) {
  const questions = new Map();
  for (const question of [...(candidate.questions || []), ...(preview?.questions || []), ...(preview?.definition?.questions || [])]) {
    if (question?.id) questions.set(question.id, question);
  }
  // Selecting multiple comparison fields branches the candidate. Resolve shared decisions once first.
  const ordered = [...questions.values()].sort((a, b) => Number(canChooseAllFields(a)) - Number(canChooseAllFields(b)));
  const result = { ...candidate, questions: ordered, preview: null };
  if (preview?.uncertainties?.length) {
    result.uncertainties = [...new Set([...(result.uncertainties || []), ...preview.uncertainties])];
  }
  if (preview?.definition) {
    const canonicalIssues = ruleScopeIssues(preview.definition, { detailed: true });
    const knownIssues = new Set(candidateIssues(result));
    const extra = canonicalIssues.filter((text) => !knownIssues.has(text));
    if (extra.length) result.uncertainties = [...(result.uncertainties || []), ...extra];
  }
  if (preview?.sql_preview && !result.questions.length && !candidateIssues(result).length) result.preview = preview;
  return result;
}

export function confirmationReadiness(detail, evidence, dirty = false, allowUnsaved = false) {
  const reasons = [];
  if (!allowUnsaved && !detail?.id) reasons.push("请先保存草稿并读取服务端规则详情");
  if (dirty) reasons.push("表单有未保存修改，请先保存新版本");
  reasons.push(...ruleScopeIssues(detail?.definition || {}));
  if (!evidence || !Array.isArray(evidence.cases) || evidence.cases.length === 0) {
    reasons.push("尚无当前版本的真实测试案例");
  } else {
    if (Number(evidence.version_no) !== Number(detail?.version_no)
        || String(evidence.content_sha256 || "") !== String(detail?.content_sha256 || "")) {
      reasons.push("测试证据与当前版本或哈希不一致");
    }
    if (Number(evidence.failed_count) !== 0) reasons.push("仍有测试案例失败");
    if (Number(evidence.passed_count) <= 0) reasons.push("没有已通过的测试案例");
    if (Number(evidence.not_run_count) > 0) reasons.push("仍有未运行测试案例");
    if (evidence.cases.some((item) => item.status !== "passed")) reasons.push("测试案例尚未全部通过");
  }
  return { ready: reasons.length === 0, reasons };
}

// Unsaved evidence is only UI readiness, never a server-side activation receipt.
export function previewReadiness(preview, evidence, dirty = false) {
  if (!preview) return { ready: false, reasons: ["请先完成分析并生成校验 SQL"] };
  return confirmationReadiness({ definition: preview.definition, version_no: 0, content_sha256: preview.content_sha256 },
    evidence ? { ...evidence, version_no: 0 } : null, dirty, true);
}

export function isTaskActive(task) {
  return ["queued", "running", "pausing"].includes(task?.status);
}

export function canCancelTask(task) {
  return isTaskActive(task) || task?.status === "paused";
}

export function canRetryTask(task) {
  return ["failed", "partial_failed", "cancelled"].includes(task?.status);
}

export function taskIssueNotice(task, total) {
  const count = Math.max(0, Number(total) || 0);
  switch (task?.status) {
    case "paused":
      return "任务已暂停，当前异常数量不是最终结论；继续执行后可查看完整结果。";
    case "pausing":
      return "正在等待当前查询结束后暂停，当前异常数量不是最终结论。";
    case "queued":
    case "running":
      return "任务尚未完成，当前异常明细不是最终结论，不能据此判定通过。";
    case "failed":
      return "任务执行失败；已登记异常数量不代表校验通过，请排查失败原因或重试。";
    case "partial_failed":
      return "部分规则执行失败；当前异常明细不代表全部规则通过。";
    case "cancelled":
      return "任务已取消；当前异常明细不代表校验通过。";
    case "completed":
      return `任务已完成，接口已登记异常 ${count} 条。`;
    default:
      return "任务状态未知，不能据此判定校验通过。";
  }
}

export function formatDateTime(value) {
  const text = String(value || "").trim();
  return text ? text.replace("T", " ").replace(/([.]\d+)?(?:Z|[+-]\d{2}:?\d{2})$/, "") : "-";
}

export function previousMonthEnd(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  let year = Number(values.year);
  let month = Number(values.month) - 1;
  if (month === 0) {
    year -= 1;
    month = 12;
  }
  const day = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}
