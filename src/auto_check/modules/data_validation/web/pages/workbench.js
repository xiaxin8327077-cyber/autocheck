import { createRuntime, errorMessage } from "../runtime.js";
import { canChooseAllFields, candidateIssues, reviewCandidate, createTestEvidence, confirmationReadiness, previewReadiness, ruleScopeIssues, hasCapability, ownsResource } from "../state.js";
import { bindComparisonField, comparisonFields, fieldTarget, hasComparison, isGrouped } from "../comparisons.js";
import { createAiCandidatePanel, candidateCondition, candidateFiltersText } from "../components/ai_candidate.js";
import { createCandidateOptionsPanel, createRequestKeyRegistry } from "../components/candidate_options.js";
import { createDialog } from "../components/dialog.js";
import { button, element } from "../components/dom.js";
import { createRuleForm } from "../components/rule_form.js";
import { createTestPanel } from "../components/test_panel.js";
import { aiMark, aiIcon } from "../components/ai_visuals.js";
import { readScopeChoice, rememberScopeChoice } from "../components/scope_choice_memory.js";
import { applyBusinessAnswers, collectBusinessQuestions, preparedOptions, reviewDefinition } from "../candidate_review.js";
import { createBusinessQuestionsPanel } from "../components/business_questions.js";
import { openSqlTestDialog } from "../components/sql_test_dialog.js";

const CHANNELS = ["workbench-detail", "workbench-metadata", "workbench-ai", "workbench-save", "workbench-test", "workbench-confirm", "workbench-preview"];
const ANALYSIS_POLL_MS = 900;
const ANALYSIS_WAIT_CHOICE_SECONDS = 60;
const ANALYSIS_CONNECTION_TIMEOUT_MS = 10000;
const TEST_PREPARATION_MS = 3000;
const ANALYSIS_ENDED_NOTE = "本次分析会话已结束。";
const ANALYSIS_STEPS = [
  { id: "semantics", label: "解析业务语义与逻辑" },
  { id: "metadata", label: "检索数据字典与表结构说明" },
  { id: "generation", label: "核对校验规则与待确认口径" },
];

// Authentication may still be waiting before the host starts fetch. Bound both
// the UI wait and the actual request, including a later authenticated retry.
async function analysisConnection(send, signal) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  let timer;
  try {
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => {
        reject(new Error("连接分析服务超时，请检查网络后重试"));
        abort();
      }, ANALYSIS_CONNECTION_TIMEOUT_MS);
    });
    return await Promise.race([send(controller.signal), timeout]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export function createWorkbench({
  state, runtime, api, listen, user, notify, host, confirmAction,
  onClose, onChanged, onRetrySources, onRetryModels,
  onSupplementReady,
}) {
  const work = {
    mode: "manual", ruleId: null, detail: null, evidence: null, candidate: null,
    revision: 0, readOnly: false, busy: false, aiLoading: false, aiError: "", aiElapsed: 0, testing: false,
    confirmBusy: false, descriptionCollapsed: false,
    preview: null, previewCases: null, previewEvidence: null, preparingTests: false,
    analysisInput: "", previewBusy: false, selectedChoice: null,
    analysis: null, analysisNote: "",
    options: [], selectedOptions: [], activeOptionId: "", expandedOptionId: "", optionWork: {}, comparisonSuggestions: [], aiSuggestions: [],
    requestKeyRegistry: null, savedOptionRules: [], optionsSaving: false, pendingOptionSave: null,
  };
  let dialog = null;
  let sqlTestDialog = null;
  let footerButton = null;
  let page = null;
  let lastConfigVisible = false;
  let lastTestingVisible = false;
  let elapsedTimer = null;
  let analysisTimer = null;
  let activeAnalysis = null;
  let supplementWorkbench = null;
  let supplementTitle = "";
  let supplementAdoption = null;
  let returningSupplement = false;
  let deferredSupplements = [];
  let deferredSupplementInput = "";
  let businessReview = null;
  let businessReviewSession = null;
  let clarificationContext = null;
  let analyzeStartedAt = 0;

  // 单页结构：① 需求输入（始终显示，AI 分析成功后折叠为一行）→ ② 校验属性与 AI 结果 → ③ 测试与启用。
  // ②③ 初始隐藏，随用户操作逐步出现，不使用步骤条。
  function buildPage(mode) {
    const isAi = mode === "ai";
    const form = createRuleForm({
      state, mode, listen, user,
      onChange: ({ groupEdited = false } = {}) => {
        work.revision += 1;
        if (clarificationContext && !clarificationAnswers(page?.form.read() || {}).length) clarificationContext = null;
        work.aiError = "";
        if (groupEdited && work.mode === "ai" && work.candidate) {
          work.preview = null; work.previewEvidence = null; work.previewCases = null;
          work.candidate = { ...work.candidate, ...page.form.read(), preview: null, preview_error: "", preview_request_error: "" };
        }
        if (work.mode === "ai" && work.analysisInput && analysisStale()) {
          work.previewEvidence = null;
          work.previewCases = null;
          runtime.invalidate("workbench-test"); runtime.invalidate("workbench-preview");
          work.testing = false; work.preparingTests = false; work.previewBusy = false;
        }
        render();
      },
      onDescribe: describe,
      onParse: parse,
      onCancelEdit: cancelDescriptionEdit,
      onTestModel: (modelId) => api.testModel(modelId),
      onRetrySources,
      onRetryModels,
    });
    const candidate = isAi ? createAiCandidatePanel({ listen, onEdit: expandDescription, onReanalyze: parse,
      onTestSql: ["dv.test", "dv.run", "dv.view_results"].every(code => hasCapability(user, code)) ? (preview) => {
        sqlTestDialog?.close();
        sqlTestDialog = openSqlTestDialog({ host, api, preview, parent: dialog?.element });
      } : null,
      onRetry: () => businessReview ? verifyBusinessReview() : applyDecision(), notify,
      onChoice: (id, value) => {
        if (work.pendingOptionSave) return;
        work.selectedChoice = { id, value }; render(); page?.candidate.focusSelected();
      },
    }) : null;
    const businessQuestions = isAi ? createBusinessQuestionsPanel({ listen, onConfirm: confirmBusinessQuestions }) : null;
    const switchButton = isAi
      ? button("转手工继续", { listen, className: "dv-button dv-button-plain", onClick: () => switchToManual() })
      : null;
    const tests = createTestPanel({ listen, onTest: () => runTests(), onCaseChange: changeCase, showSql: !isAi });
    const saveButton = button("保存草稿", { listen, className: "dv-button", onClick: () => saveDraft() });
    const footerBulk = isAi
      ? button("保存所选 0 条草稿", { listen, className: "dv-button", onClick: () => saveSelectedOptions() })
      : null;
    const reselectBusiness = isAi ? button("重新选择口径", {
      listen, className: "dv-button", capability: "dv.ai_use", hidden: true, onClick: reselectBusinessQuestions,
    }) : null;
    const confirmButton = button(isAi ? "保存并启用" : "确认启用", {
      listen, className: "dv-button dv-button-primary", capability: "dv.confirm",
      onClick: () => confirmFromPage(),
    });
    const saveHint = element("span", { className: "dv-inline-status" });
    const saveNote = isAi ? element("div", { className: "dv-ai-footer-note" }, aiIcon("lock"), saveHint) : null;
    const verifyHint = element("span", { className: "dv-inline-status" });
    const collapsedText = element("span", { className: "dv-description-text" });
    const waitRequestText = element("p", { className: "dv-ai-wait-request-text" });
    const waitSource = element("span");
    const waitModel = element("span", { className: "dv-ai-wait-model" });
    const waitRequest = isAi ? element("div", { className: "dv-ai-wait-request", hidden: true },
      element("div", { className: "dv-ai-wait-request-meta" },
        element("span", { className: "dv-ai-wait-request-label", text: "你的需求" }),
        element("span", { className: "dv-ai-wait-chip" }, aiIcon("database"), waitSource),
        element("span", { className: "dv-ai-wait-chip" }, waitModel),
        element("span", { className: "dv-ai-wait-readonly", text: "READ-ONLY", attrs: { "aria-label": "只读" } })),
      waitRequestText) : null;
    const aiWaitTimer = element("strong", { className: "dv-ai-wait-value" });
    const aiWaitStage = element("span", { className: "dv-ai-wait-stage", attrs: { role: "status" } });
    const aiProgressText = element("p", { className: "dv-ai-progress-text", attrs: { role: "status" } });
    const aiProgressNote = element("p", { className: "dv-ai-progress-note", hidden: true, attrs: { role: "status" } });
    const continueWaiting = isAi ? button("继续等待", {
      listen, className: "dv-button dv-button-primary", hidden: true,
      onClick: () => {
        if (!activeAnalysis || activeAnalysis.ending) return;
        activeAnalysis.continued = true;
        renderElapsed();
        footerButton?.focus();
      },
    }) : null;
    const aiWaitBody = element("div", { className: "dv-ai-wait-body", hidden: true },
      element("span", { className: "dv-ai-wait-symbol", attrs: { "aria-hidden": "true" } },
        element("span", { className: "dv-ai-wait-mark" }, aiIcon("star"))),
      element("div", { className: "dv-ai-wait-copy" },
        element("strong", { className: "dv-ai-wait-title", text: "AI 正在分析你的校验需求" }),
        element("p", { text: "结合文档中的表结构与字段说明，理解你的业务口径。" })),
      element("span", { className: "dv-ai-wait-timer" },
        element("span", {}, "已等待 ", aiWaitTimer, " 秒")),
      element("span", { className: "dv-ai-wait-track", attrs: { role: "progressbar", "aria-label": "正在分析，不显示百分比" } }),
      aiWaitStage, aiProgressNote);
    const aiProgress = isAi
      ? element("section", { className: "dv-ai-progress", hidden: true }, aiWaitBody, aiProgressText)
      : null;
    const editRequest = isAi ? button("修改需求", { listen, className: "dv-ai-text-button dv-ai-edit-request", onClick: expandDescription }) : null;
    if (isAi) form.groups.aiContext.append(editRequest);
    const collapsedBar = isAi ? element("div", { className: "dv-description-collapsed", hidden: true }, collapsedText) : null;
    const choiceContinue = isAi ? button("确认当前口径", { listen, className: "dv-button dv-button-primary", capability: "dv.ai_use",
      onClick: () => { const question = work.candidate?.questions?.[0]; if (question && work.selectedChoice?.id === question.id) return applyDecision(question.id, work.selectedChoice.value); },
    }) : null;

    const inputSection = element("section", { className: "dv-page-section dv-input-section" },
      element("div", { className: "dv-page-section-heading" }, element("h2", { text: isAi ? "需求描述与 AI 分析" : "基本信息" })),
      isAi ? form.groups.aiContext : null,
      isAi ? form.groups.aiInput : form.groups.basics,
      collapsedBar, waitRequest,
      element("div", { className: "dv-switch-manual" }, switchButton));

    const optionsPanel = isAi
      ? createCandidateOptionsPanel({
        listen,
        onToggle: (id, checked) => toggleOption(id, checked),
        onActive: (id) => toggleOptionCard(id),
        onSaveOption: (id) => saveOptionAndEnable(id),
        onSaveSelected: () => saveSelectedOptions(),
      })
      : null;
    const editor = isAi ? element("details", { className: "dv-ai-reasoning", hidden: true },
      element("summary", { text: "编辑组合条件" }), form.groupEditor) : null;
    const detailHome = isAi ? element("div", { className: "dv-ai-single-detail" }, candidate.element, editor) : null;
    const configBody = isAi
      ? element("div", { className: "dv-ai-result" }, businessQuestions.element, optionsPanel.element, detailHome)
      : form.groups.config;
    const configSection = element("section", {
      className: "dv-page-section dv-config-section", hidden: true,
    },
      element("div", { className: "dv-page-section-heading" }, element("h2", { text: isAi ? "分析结论" : "校验属性与配置" })),
      configBody,
      isAi ? null : element("div", { className: "dv-verify-actions" }, saveButton, saveHint));

    const testLaunchLabel = isAi ? element("span", { text: "生成并运行测试用例" }) : null;
    const testLaunch = isAi ? button("", {
      listen, className: "dv-button dv-button-primary", capability: "dv.test", onClick: () => runTests(),
    }) : null;
    testLaunch?.append(aiIcon("spark"), testLaunchLabel);
    const testPreparing = isAi ? element("div", { className: "dv-ai-test-preparing", hidden: true, attrs: { role: "status" } },
      element("span", { className: "dv-ai-test-generating-symbol", attrs: { "aria-hidden": "true" } }, aiIcon("spark")),
      element("div", { className: "dv-ai-test-generating-copy" },
        element("strong", {}, "正在生成并运行测试用例",
          element("span", { className: "dv-ai-loading-dots", attrs: { "aria-hidden": "true" } }, element("span"), element("span"), element("span"))),
        element("p", { text: "根据所选方案准备样本和预期判断" }),
        element("span", { className: "dv-ai-wait-track", attrs: { "aria-hidden": "true" } })),
      element("div", { className: "dv-ai-test-skeleton", attrs: { "aria-hidden": "true" } }, element("span"), element("span"), element("span"))) : null;
    const testTitle = element("h2", { text: isAi ? "测试用例" : "测试与启用", hidden: isAi });
    const testCount = isAi ? element("span", { className: "dv-ai-test-count", hidden: true }) : null;
    const testingSection = element("section", {
      className: "dv-page-section dv-testing-section", hidden: true,
    },
      element("div", { className: `dv-page-section-heading${isAi ? " dv-ai-test-heading" : ""}` },
        testTitle, testCount, testLaunch),
      testPreparing, tests.element,
      isAi ? null : element("div", { className: "dv-confirm-actions" }, confirmButton, verifyHint));

    const suggestionsList = element("div", { className: "dv-ai-supplement-list" });
    const suggestionsSection = isAi
      ? element("section", { className: "dv-ai-supplements", hidden: true },
        element("h3", { className: "dv-ai-supplement-title", text: "AI补充建议" }), suggestionsList)
      : null;
    const root = element("section", { className: "dv-workbench dv-workbench-modal-content dv-single-page" },
      inputSection, aiProgress, configSection, suggestionsSection, testingSection);
    const scene = {
      suggestionsSection, suggestionsList, suggestionRemovers: [],
      form, candidate, businessQuestions, reselectBusiness, optionsPanel, detailHome, editor, switchButton, tests, saveButton, footerBulk, confirmButton, saveHint, saveNote, verifyHint,
      collapsedText, collapsedBar, waitRequest, waitRequestText, waitSource, waitModel,
      aiProgress, aiWaitBody, aiWaitTimer, aiWaitStage, aiProgressText, aiProgressNote, continueWaiting,
      inputSection, configSection, testingSection, root, editRequest, choiceContinue,
      testLaunch, testLaunchLabel, testPreparing, testTitle, testCount,
    };
    return scene;
  }

  function stopElapsed() {
    runtime.clearTimer(elapsedTimer);
    elapsedTimer = null;
  }

  function renderElapsed() {
    if (!page) return;
    page.aiWaitTimer.textContent = work.aiElapsed.toFixed(1);
    const run = activeAnalysis;
    const offerChoice = Boolean(run && !run.ending && !run.continued && work.aiElapsed >= ANALYSIS_WAIT_CHOICE_SECONDS);
    if (page.continueWaiting) page.continueWaiting.hidden = !offerChoice;
    let note = "";
    if (run?.ending) note = run.stopError || "正在结束会话，请等待后台确认。";
    else if (run?.pollError) note = run.pollError;
    else if (run && work.aiElapsed >= ANALYSIS_WAIT_CHOICE_SECONDS) {
      const limit = work.analysis?.timeout_ms;
      note = Number.isFinite(limit) ? `本次分析耗时较长，分析总时限为 ${limit / 1000} 秒。可随时结束会话。`
        : "本次分析耗时较长，可随时结束会话。";
    }
    page.aiProgressNote.hidden = !note;
    if (page.aiProgressNote.textContent !== note) page.aiProgressNote.textContent = note;
  }

  function startElapsed() {
    stopElapsed();
    analyzeStartedAt = performance.now();
    work.aiElapsed = 0;
    const tick = () => {
      if (!work.aiLoading) return;
      work.aiElapsed = Math.max(0, (performance.now() - analyzeStartedAt) / 1000);
      // Update only the clock: a 100ms timer must not rebuild forms or restart the step spinner.
      renderElapsed();
      elapsedTimer = runtime.setTimer(tick, 100);
    };
    elapsedTimer = runtime.setTimer(tick, 100);
  }

  function inputSignature() {
    const context = page?.form.read() || {};
    return JSON.stringify([context.source_id, context.request_text, context.model_id, context.reasoning_enabled, clarificationAnswers(context)]);
  }

  function clarificationAnswers(context) {
    return clarificationContext?.source === context.source_id && clarificationContext?.request === context.request_text
      ? clarificationContext?.answers || [] : [];
  }

  function restoreAnalysisInput(signature) {
    const [source, request, , , answers = []] = JSON.parse(signature);
    clarificationContext = answers.length ? { source, request, answers } : null;
    page.form.restoreInput(signature);
  }

  function analysisStale() {
    return !work.analysisInput || inputSignature() !== work.analysisInput;
  }

  function revisionContext(context) {
    const prior = work.analysis;
    if (prior?.status !== "completed" || !prior.analysis_id || !work.analysisInput || !work.candidate) return {};
    if (work.candidate.supplementAnalysis) return {};
    const [source, request, model, reasoning] = JSON.parse(work.analysisInput);
    if (source !== context.source_id || model !== context.model_id || reasoning !== context.reasoning_enabled || request === context.request_text) return {};
    const revision = { revision_of: prior.analysis_id };
    const candidate = work.candidate;
    if (!businessReview && candidate.rule_type === "field_compare" && !candidate.questions?.length && candidate.table_name) {
      revision.revised_definition = { table_name: candidate.table_name, expression: candidate.expression, filters: candidate.filters || [] };
    }
    return revision;
  }

  function changeCase(index, expected, target = work) {
    if (!target.previewCases || work.busy || work.confirmBusy || work.optionsSaving || work.pendingOptionSave
        || work.testing || work.previewBusy || ![0, 1].includes(expected)) return;
    target.previewCases = target.previewCases.map((item, offset) => ({ ...item,
      expected_count: offset === index ? expected : item.expected_count, status: "not_run", actual_count: null }));
    target.previewEvidence = null;
    if (target !== work) loadActiveTestState();
    render();
  }

  function shareParallelScope(question, definition) {
    if (!work.candidate?.parallel_check || question?.remember_scope !== "active_status") return;
    const chosen = definition.filters?.[Number(question.id.split(".")[1])];
    if (!chosen || chosen.confirmed !== true) return;
    for (const [id, state] of Object.entries(work.optionWork)) {
      if (id === work.activeOptionId || !state.candidate?.parallel_check) continue;
      const sibling = state.candidate;
      const pending = sibling.questions?.find((item) => item.id === question.id && item.remember_scope === "active_status");
      if (!pending?.options?.some(({ selection }) => selection?.table === chosen.table && selection?.field === chosen.field
          && selection.op === chosen.op && selection.value === chosen.value)) continue;
      const filters = [...sibling.filters];
      filters[Number(pending.id.split(".")[1])] = { ...chosen };
      const resolutions = (sibling.uncertainties || []).map((text, index) => text === pending.uncertainty
        ? (definition.uncertainty_resolutions?.[definition.uncertainties?.indexOf(question.uncertainty)] || "已明确选择存续筛选")
        : (sibling.uncertainty_resolutions?.[index] || ""));
      state.candidate = { ...sibling, filters, uncertainty_resolutions: resolutions,
        questions: sibling.questions.filter((item) => item !== pending), preview: null };
      state.definition = null; state.selectedChoice = null; state.preview = null; state.previewCases = null; state.previewEvidence = null;
    }
  }

  function canRequestPreview(candidate) {
    if (!candidate || candidate.questions?.length) return false;
    const check = { ...candidate };
    if (candidate.recheckFieldType && check.null_policy === "unresolved") delete check.null_policy;
    if (candidate.recheckProjectMapping) delete check.project_context;
    // 旧候选可能同时保留结构化答案和等价的模型原话。交给预览接口用文档核对。
    // 原问题与逐项答案完整随 definition 发送；仅在本地判断能否发起这次核对时跳过文本门禁。
    if (candidate.rule_type === "field_compare" && hasComparison(candidate.expression)) {
      delete check.uncertainties;
      delete check.uncertainty_resolutions;
    }
    return candidateIssues(check).length === 0;
  }

  function previewPayload(definition, candidate) {
    const payload = { definition };
    if (candidate?.pending_dictionary_questions?.length) {
      payload.pending_dictionary_questions = candidate.pending_dictionary_questions;
    }
    const snapshot = work.analysis;
    if (candidate?.supplementAnalysis) return { ...payload, ...candidate.supplementAnalysis };
    if (snapshot?.status === "completed" && snapshot.analysis_id && snapshot.result?.analysis_context && work.analysisInput) {
      const [, request, model, reasoning] = JSON.parse(work.analysisInput);
      Object.assign(payload, { analysis_id: snapshot.analysis_id, analysis_context: snapshot.result.analysis_context,
        model_id: model, reasoning_enabled: reasoning === true, analysis_request_text: request,
        clarification_answers: snapshot.result.clarification_answers || [] });
    }
    return payload;
  }

  function receivePreview(candidate, response) {
    const review = response.definition.uncertainties || candidate.uncertainties || [];
    const result = { ...candidate, ...response.definition, rule_name: response.definition.name,
      ...Object.fromEntries(["table_name_cn", "related_table_name_cn", "document_scope", "grain"]
        .filter((key) => key in response).map((key) => [key, response[key]])),
      questions: response.questions || [], uncertainties: [...new Set([...review, ...(response.uncertainties || [])])],
      columns: response.columns || candidate.columns, related_columns: response.related_columns || candidate.related_columns,
      project_columns: response.project_columns || candidate.project_columns, project_table: response.project_table || candidate.project_table,
      mapping_version: response.mapping_version || candidate.mapping_version,
      preview_error: response.preview_error || "", preview_request_error: "", recheckFieldType: false, recheckProjectMapping: false };
    return reviewCandidate(result, response);
  }

  function previewFailure(error) {
    const code = error?.payload?.error?.code || error?.code;
    if (code === "ANALYSIS_CONTEXT_CHANGED") return { analysis_context_changed: true, preview_error: errorMessage(error) };
    const confirmationNeeded = ["VALIDATION_ERROR", "PROJECT_CONTEXT_REQUIRED", "MAPPING_DRIFT", "CONFLICT_VERSION",
      "PREVIEW_DATE_FIELD_REQUIRED", "PREVIEW_DATE_FIELD_INVALID"].includes(code);
    const message = code === "VALIDATION_ERROR" ? (error?.payload?.error?.message || errorMessage(error)) : errorMessage(error);
    return confirmationNeeded ? { preview_error: message } : { preview_request_error: message };
  }

  async function applyDecision(key, value) {
    if (work.busy || work.previewBusy || work.aiLoading || work.pendingOptionSave || analysisStale()) return;
    const choice = work.candidate?.questions?.find((item) => item.id === key);
    if (key && !choice) return;
    if (canChooseAllFields(choice) && Array.isArray(value)) {
      const options = choice.options.filter((item) => value.includes(item.value));
      if (!options.length) return;
      if (options.length > 1) return applyFieldChoices(choice, options);
      value = options[0].value;
    }
    const token = runtime.next("workbench-preview");
    const snapshot = inputSignature();
    const pendingQuestions = work.candidate?.questions || [];
    if (!key && !canRequestPreview(work.candidate)) return;
    work.previewBusy = true; work.preview = null; work.previewEvidence = null; work.previewCases = null;
    try {
      const question = pendingQuestions.find((item) => item.id === key);
      if (key) {
        page.form.applyDecision(key, value, question);
        rememberScopeChoice(user?.id, work.candidate, question, value);
      }
      const definition = page.form.read();
      shareParallelScope(question, definition);
      work.candidate = { ...work.candidate, ...definition, preview: null, preview_request_error: "",
        recheckFieldType: work.candidate.recheckFieldType || Boolean(fieldTarget(key)),
        recheckProjectMapping: work.candidate.recheckProjectMapping || key?.startsWith("project_context."),
        questions: pendingQuestions.filter((item) => item.id !== key) };
      work.selectedChoice = null;
      if (!canRequestPreview(work.candidate)) {
        work.previewBusy = false;
        if (work.options.length) syncActiveOptionState();
        render();
        return;
      }
      render();
      const preview = await runtime.request(token, (signal) => api.preview(previewPayload(page.form.read(), work.candidate), { signal }));
      if (!runtime.current(token) || inputSignature() !== snapshot) return;
      work.candidate = receivePreview(work.candidate, preview);
      page.form.setMetadata({
        columns: preview.columns || work.candidate?.columns || [],
        related_columns: preview.related_columns || work.candidate?.related_columns || [],
        project_columns: preview.project_columns || null,
        project_table: preview.project_table || null,
        mapping_version: preview.mapping_version || work.candidate?.mapping_version || "",
      });
      work.preview = work.candidate.preview;
      work.descriptionCollapsed = true;
      page.form.applyCandidate(work.candidate, { regenerate: false });
      work.previewBusy = false;
      if (work.options.length) syncActiveOptionState();
      render();
    } catch (error) {
      if (runtime.current(token)) {
        work.previewBusy = false;
        work.candidate = { ...work.candidate, preview: null, ...previewFailure(error) };
        if (work.options.length) syncActiveOptionState();
        render();
      }
    }
  }

  async function applyFieldChoices(question, selectedOptions) {
    if (work.pendingOptionSave) return;
    const candidate = work.candidate;
    const pending = candidate.questions.filter((item) => item.id !== question.id);
    const definition = page.form.read();
    const { index, side } = fieldTarget(question.id);
    const condition = index === null ? definition.expression : definition.expression.conditions[index];
    const columns = side === "right" && condition.right_table === "related"
      ? page.form.relatedColumns() : page.form.metadataColumns();
    const activeId = work.activeOptionId;
    const snapshot = inputSignature();
    const token = runtime.next("workbench-preview");
    work.previewBusy = true;
    render();
    try {
      const options = [];
      for (const option of selectedOptions) {
        const field = columns.find((column) => column.column_name === option.value);
        const label = field?.comment || option.label;
        const variant = { ...definition, name: option.rule_name || `${definition.name || candidate.rule_name} · ${label}`,
          expression: bindComparisonField(definition.expression, question, option.value,
            (table) => table === "related" ? page.form.relatedColumns() : page.form.metadataColumns()),
          violation_message: `${label}命中校验条件，请核实。`,
          uncertainty_resolutions: (definition.uncertainties || []).map((note, index) => note === question.uncertainty
            ? `明确选择 ${option.value}` : definition.uncertainty_resolutions?.[index] || ""),
        };
        let result = { ...candidate, ...variant, rule_name: variant.name, questions: pending, recheckFieldType: true, preview: null };
        if (canRequestPreview(result)) {
          try {
            const response = await runtime.request(token, (signal) => api.preview(previewPayload(variant, result), { signal }));
            result = receivePreview(result, response);
          } catch (error) {
            result = { ...result, ...previewFailure(error) };
          }
        }
        if (!runtime.current(token) || inputSignature() !== snapshot) return;
        options.push({ id: `${activeId || "field"}-${side}-${option.value}`, label: variant.name,
          table_label: candidate.table_name_cn || candidate.table_name, field_label: label,
          grain: work.options.find((item) => item.id === activeId)?.grain || "",
          fromSelection: true, candidate: result,
        });
      }
      if (work.options.length) {
        work.options = work.options.flatMap((item) => item.id === activeId ? options : [item]);
        delete work.optionWork[activeId];
        options.forEach(({ id, candidate: result }) => {
          work.optionWork[id] = { candidate: result, preview: result.preview, previewCases: null,
            previewEvidence: null, analysisInput: snapshot, selectedChoice: null, saved: null };
        });
        work.selectedOptions = [...work.selectedOptions.filter((id) => id !== activeId), ...options.map((item) => item.id)];
        work.requestKeyRegistry.refresh();
        work.expandedOptionId = options[0].id;
        loadOptionIntoForm(options[0].id);
      } else {
        if (options.some((option) => option.candidate.questions?.length || candidateIssues(option.candidate).length)) {
          startBusinessReview({ candidate_options: options.map((option) => ({ ...option, recommended: true })) });
          return;
        }
        setupMultiOptions({ candidate_options: options });
        work.selectedOptions = options.map((item) => item.id);
        render();
      }
    } finally {
      if (runtime.current(token)) { work.previewBusy = false; render(); }
    }
  }

  function releaseAnalysis() {
    const run = activeAnalysis;
    activeAnalysis = null;
    stopAnalysisPolling();
    if (run?.id && !run.stopSent) cancelDetachedAnalysis(run.id);
  }

  async function cancelDetachedAnalysis(id) {
    try { await analysisConnection((signal) => api.cancelAnalysis(id, { signal })); }
    catch (error) { if (runtime.isActive()) notify(`未能确认上次分析已结束：${errorMessage(error)}`, "warning"); }
  }

  function invalidate() {
    supplementWorkbench?.close();
    sqlTestDialog?.close(); sqlTestDialog = null;
    businessReview = null;
    businessReviewSession = null;
    page?.businessQuestions?.clear();
    releaseAnalysis();
    CHANNELS.forEach((channel) => runtime.invalidate(channel));
    page?.tests.dispose();
    page?.form.disposeGroup();
    page?.suggestionRemovers.splice(0).forEach((remove) => remove?.());
  }

  function cancelDescriptionEdit() {
    if (!work.candidate || !work.analysisInput || work.aiLoading || work.busy || work.testing || work.confirmBusy || work.previewBusy) return;
    restoreAnalysisInput(work.analysisInput);
    page.form.setMetadata({
      columns: work.candidate.columns || [], related_columns: work.candidate.related_columns || [],
      project_columns: work.candidate.project_columns || null, project_table: work.candidate.project_table || null,
      mapping_version: work.candidate.mapping_version,
    });
    page.form.applyCandidate(work.candidate, { regenerate: false });
    work.descriptionCollapsed = true; work.aiError = "";
    render();
  }

  function expandDescription() {
    work.descriptionCollapsed = false;
    render();
    page?.form.focusRequest?.();
  }

  function collectSeed() {
    const context = page.form.read();
    const columns = page.form.metadataColumns();
    return {
      name: context.name,
      source_id: context.source_id,
      table_name: context.table_name,
      request_text: context.request_text,
      ...Object.fromEntries(["uncertainties", "uncertainty_resolutions", "unsupported_requirements", "filters"]
        .filter((key) => Array.isArray(context[key])).map((key) => [key, context[key]])),
      ...(context.join ? { join: context.join } : {}),
      ...Object.fromEntries(["null_handling", "null_evidence", "include_result_fields", "project_context", "project_driver"]
        .filter((key) => context[key] !== undefined).map((key) => [key, context[key]])),
      expression: context.expression, report_date_field: context.report_date_field,
      null_policy: context.null_policy, equality_policy: context.equality_policy,
      related_columns: page.form.relatedColumns(),
      metadata: columns.length ? { columns, related_columns: page.form.relatedColumns(), mapping_version: context.mapping_version } : null,
    };
  }

  async function switchToManual() {
    const seed = collectSeed();
    close();
    await open({ mode: "manual", seed });
    notify("已转入手工创建，此前填写的需求与数据源已保留", "info");
  }

  async function open({ mode = "manual", ruleId = null, seed = null, supplement = null } = {}) {
    invalidate();
    clarificationContext = null;
    dialog?.close();
    deferredSupplements = [];
    Object.assign(work, {
      mode: mode === "ai" ? "ai" : "manual", ruleId: ruleId || null, detail: null, evidence: null, candidate: null,
      revision: 0, readOnly: false, busy: false, aiLoading: false, aiError: "", aiElapsed: 0, testing: false,
      confirmBusy: false, descriptionCollapsed: false,
      preview: null, previewCases: null, previewEvidence: null, preparingTests: false,
      analysisInput: "", previewBusy: false, selectedChoice: null,
      analysis: null, analysisNote: "",
      options: [], selectedOptions: [], activeOptionId: "", expandedOptionId: "", optionWork: {}, comparisonSuggestions: [], aiSuggestions: [],
      requestKeyRegistry: null, savedOptionRules: [], optionsSaving: false, pendingOptionSave: null,
    });
    stopElapsed();
    lastConfigVisible = false;
    lastTestingVisible = false;
    page = buildPage(work.mode);
    page.form.reset(null, seed);
    page.form.setSources();
    page.form.setCategories();
    if (work.mode === "ai") page.form.setModels();
    supplementTitle = supplement?.title || "";
    supplementAdoption = supplement?.adoptionContext || null;
    if (supplement) page.form.restoreInput(supplement.signature);
    dialog = createDialog({
      host,
      title: ruleId ? "编辑、测试与确认规则" : work.mode === "ai" ? "AI 新建校验规则" : "新建校验规则",
      icon: work.mode === "ai" ? aiMark() : null,
      subtitle: work.mode === "ai" ? "/ 分析结果" : "",
      className: `dv-workbench-dialog${work.mode === "ai" ? " dv-ai-workbench-dialog" : ""}`,
      onClose: () => {
        stopElapsed();
        invalidate();
        dialog = null;
        footerButton = null;
        page = null;
        onClose?.();
      },
      onError: (message) => notify(message, "error"),
    });
    footerButton = button("取消");
    dialog.bind(footerButton, "click", () => {
      if (work.aiLoading) {
        return cancelWaiting();
      }
      close();
    });
    if (work.mode === "ai") dialog.footer.append(page.saveNote, page.businessQuestions.progress,
      element("div", { className: "dv-ai-footer-actions" }, page.continueWaiting, page.reselectBusiness, footerButton, page.footerBulk,
        page.saveButton, page.confirmButton, page.choiceContinue, page.businessQuestions.submit));
    else dialog.footer.append(footerButton);
    dialog.body.append(page.root);
    render();
    if (ruleId) await loadDetail(ruleId);
    if (supplement) await parse();
    return dialog;
  }

  async function loadDetail(ruleId) {
    const token = runtime.next("workbench-detail");
    try {
      const detail = await runtime.request(token, (signal) => api.rule(ruleId, { signal }));
      if (!runtime.current(token) || work.ruleId !== ruleId) return;
      work.detail = detail;
      work.evidence = null;
      work.readOnly = !ownsResource(user, detail);
      page.form.reset(detail);
      page.form.setSources();
      page.form.setCategories();
      work.revision = 0;
      render();
      if (detail.definition?.source_id && detail.definition?.table_name) await describe();
    } catch (error) {
      if (runtime.current(token)) {
        work.aiError = `规则详情加载失败：${errorMessage(error)}`;
        render();
      }
      throw error;
    }
  }

  async function describe() {
    const context = page.form.read();
    if (!context.source_id || !context.table_name) throw new Error("请先选择数据源并填写物理表名");
    const token = runtime.next("workbench-metadata");
    const revision = work.revision;
    page.form.setMetadataFeedback("正在读取真实表结构与候选字段…", "loading");
    page.form.setBusy(true);
    try {
      const metadata = await runtime.request(token, (signal) => api.describe(context.source_id, context.table_name, { signal }));
      if (!runtime.current(token)) return;
      const current = page.form.read();
      if (current.source_id !== context.source_id || current.table_name !== context.table_name || work.revision !== revision) return;
      page.form.setMetadata(metadata);
      page.form.setBusy(work.busy);
      render();
    } catch (error) {
      if (runtime.current(token)) {
        page.form.setMetadataFeedback(`表结构读取失败：${errorMessage(error)}`, "error");
        page.form.setBusy(work.busy);
      }
      throw error;
    }
  }

  function stopAnalysisPolling() {
    if (analysisTimer !== null) {
      runtime.clearTimer(analysisTimer);
      analysisTimer = null;
    }
  }

  function renderAnalysisStage() {
    // 真实阶段仍由轮询快照驱动，方案 A 不再在等待区展开三步列表。
    const steps = Array.isArray(work.analysis?.steps) ? work.analysis.steps : [];
    const current = work.aiLoading && !activeAnalysis?.ending && steps.find((step) => step.status === "running");
    const stage = current && ANALYSIS_STEPS.find((step) => step.id === current.id);
    const activity = work.aiLoading && !activeAnalysis?.ending && work.analysis?.activity;
    const announcement = [stage?.label, activity ? "" : current?.detail, current?.table_name,
      Number.isInteger(current?.field_count) ? `字段 ${current.field_count}` : "",
      activity?.round_number > 0 ? `第 ${activity.round_number} 轮` : "", activity?.detail,
      Number.isFinite(activity?.elapsed_ms) ? `最近状态更新于第 ${(activity.elapsed_ms / 1000).toFixed(1)} 秒` : "",
    ].filter(Boolean).join("，");
    if (page.aiWaitStage.textContent !== announcement) page.aiWaitStage.textContent = announcement;
  }

  function setupMultiOptions(result) {
    work.options = [...result.candidate_options];
    if (work.options.some((item) => item.candidate?.parallel_check)) work.descriptionCollapsed = true;
    work.comparisonSuggestions = Array.isArray(result.comparison_suggestions) ? result.comparison_suggestions : [];
    work.selectedOptions = work.options.filter((item) => item.recommended).map((item) => item.id);
    if (!work.selectedOptions.length) work.selectedOptions = [work.options[0].id];
    work.activeOptionId = work.selectedOptions[0] || work.options[0].id;
    work.expandedOptionId = work.activeOptionId;
    work.requestKeyRegistry = businessReviewSession?.requestKeyRegistry || createRequestKeyRegistry();
    work.savedOptionRules = [];
    work.optionsSaving = false;
    work.optionWork = {};
    const signature = inputSignature();
    work.options.forEach((option) => {
      const candidate = reviewCandidate(option.candidate || {});
      work.optionWork[option.id] = {
        candidate, definition: null, selectedChoice: null,
        preview: candidate.preview || null, previewCases: null,
        previewEvidence: null, analysisInput: signature, saved: null,
      };
    });
    work.candidate = null;
    work.preview = null; work.previewCases = null; work.previewEvidence = null;
    work.analysisInput = signature;
    if (businessReviewSession) {
      work.options.forEach((option) => {
        const state = work.optionWork[option.id];
        const canonical = canonicalOptionKey(canonicalOptionDefinition(state));
        const saved = businessReviewSession.saved.get(canonical);
        if (saved) { state.saved = saved; state.savedCanonical = canonical; }
      });
      work.savedOptionRules = work.options.map((option) => work.optionWork[option.id].saved).filter(Boolean);
    }
    loadOptionIntoForm(work.activeOptionId, { resetRevision: true });
  }

  function syncActiveOptionState() {
    if (!work.options.length || !work.activeOptionId) return;
    const state = work.optionWork[work.activeOptionId];
    if (!state) return;
    try {
      state.definition = page.form.read();
    } catch {
      state.definition = state.definition || state.candidate;
    }
    state.candidate = work.candidate || state.candidate;
    state.selectedChoice = work.selectedChoice;
    state.preview = work.preview; state.previewCases = work.previewCases; state.previewEvidence = work.previewEvidence;
    state.analysisInput = work.analysisInput;
  }

  function canonicalOptionDefinition(state) {
    return state?.preview?.definition || state?.definition || state?.candidate || null;
  }

  function canonicalOptionKey(definition) {
    if (!definition) return "";
    const stable = (value) => {
      if (Array.isArray(value)) return value.map(stable);
      if (value && typeof value === "object") {
        return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
      }
      return value;
    };
    return JSON.stringify(stable(definition));
  }

  function optionsFingerprint() {
    return work.options
      .filter((option) => work.selectedOptions.includes(option.id))
      .map((option) => ({ id: option.id, definition: canonicalOptionDefinition(work.optionWork[option.id]) }));
  }

  function optionDraftProblem(option, state) {
    const definition = canonicalOptionDefinition(state) || {};
    if (!definition.rule_type || !definition.table_name || !definition.business_key || !hasComparison(definition.expression)) {
      return "缺少安全规则结构（规则类型/目标表/业务主键/表达式）";
    }
    if (!state.preview?.sql_preview) return "请先确认该方案的全部口径并生成 SQL 预览";
    if (state?.saved && state.savedCanonical !== canonicalOptionKey(definition)) {
      return "该方案已保存且口径已修改，请在规则列表编辑原规则，避免重复创建";
    }
    return "";
  }

  function optionGate(id) {
    if (!id) return { enabled: false, reasons: ["请先展开要启用的方案"] };
    const state = work.optionWork[id];
    if (!state) return { enabled: false, reasons: ["缺少方案状态"] };
    const reasons = [];
    if (!hasCapability(user, "dv.manage") || !hasCapability(user, "dv.test") || !hasCapability(user, "dv.confirm")) {
      reasons.push("缺少管理/测试/确认权限");
    }
    if (work.busy || work.optionsSaving || work.testing || work.previewBusy || work.confirmBusy || work.aiLoading) reasons.push("当前有操作进行中");
    if (work.readOnly) reasons.push("当前为只读模式");
    if (analysisStale()) reasons.push("请先应用需求修改");
    const definition = canonicalOptionDefinition(state);
    const key = canonicalOptionKey(definition);
    if (!definition || !definition.rule_type || !definition.table_name || !definition.business_key || !hasComparison(definition.expression)) {
      reasons.push("缺少安全规则结构");
    }
    if (!state.preview?.sql_preview) reasons.push("请先确认该方案的全部口径并生成 SQL 预览");
    if (state.saved && state.savedCanonical !== key) {
      reasons.push("该方案已保存且口径已修改，请在规则列表编辑后启用");
    } else if (!state.previewEvidence) {
      const waitingForPreview = work.selectedOptions.some((id) => !work.optionWork[id]?.preview?.sql_preview);
      reasons.push(waitingForPreview ? "请先完善或取消勾选尚未生成 SQL 的方案" : "请先运行当前方案的测试");
    } else {
      const preview = { definition, content_sha256: state.preview?.content_sha256 || state.previewEvidence?.content_sha256 || "" };
      const readiness = previewReadiness(preview, state.previewEvidence, analysisStale());
      if (!readiness.ready) reasons.push(...readiness.reasons);
    }
    return { enabled: reasons.length === 0, reasons };
  }

  function selectedOptionGate() {
    const selected = work.options.filter((option) => work.selectedOptions.includes(option.id));
    if (!selected.length) return { enabled: false, reasons: ["请至少勾选一个方案"], selected };
    const reasons = selected.flatMap((option) => optionGate(option.id).reasons
      .map((reason) => `${option.label || option.id}：${reason}`));
    return { enabled: reasons.length === 0, reasons, selected };
  }

  function loadOptionIntoForm(id, { resetRevision = false } = {}) {
    const state = work.optionWork[id];
    if (!state) return;
    if (work.candidate) syncActiveOptionState();
    const candidate = reviewCandidate(state.definition ? { ...state.candidate, ...state.definition } : state.candidate, state.preview);
    // applyCandidate emits onChange synchronously: do not save the new form into the previous option.
    work.loadingOption = true;
    try {
      page.form.setMetadata({
        columns: candidate?.columns || [], related_columns: candidate?.related_columns || [],
        project_columns: candidate?.project_columns || [], project_table: candidate?.project_table,
        mapping_version: candidate?.mapping_version || "",
      });
      page.form.applyCandidate(candidate || {}, { regenerate: false });
    } finally {
      work.loadingOption = false;
    }
    work.activeOptionId = id;
    work.candidate = candidate || {};
    work.selectedChoice = state.selectedChoice;
    work.preview = candidate.preview;
    if (!work.preview) { state.previewCases = null; state.previewEvidence = null; }
    loadActiveTestState();
    work.analysisInput = state.analysisInput || inputSignature();
    work.aiError = "";
    work.revision += 1;
    runtime.invalidate("workbench-preview");
    runtime.invalidate("workbench-test");
    runtime.invalidate("workbench-confirm");
    runtime.invalidate("workbench-save");
    work.previewBusy = false;
    work.testing = false; work.preparingTests = false;
    render();
  }

  function activateOption(id) {
    if (work.busy || work.optionsSaving || work.testing) return;
    if (!work.optionWork[id] || id === work.activeOptionId) return;
    loadOptionIntoForm(id);
  }

  function unmountOptionDetail() {
    if (!page) return;
    if (page.candidate?.element?.parentNode !== page.detailHome) page.detailHome.append(page.candidate.element, page.editor);
  }

  function mountOptionDetail() {
    if (!page || work.mode !== "ai") return;
    page.detailHome.hidden = work.options.length > 0;
    if (!work.options.length || !work.expandedOptionId) {
      unmountOptionDetail();
      return;
    }
    const slot = page.optionsPanel?.getSlotEl(work.expandedOptionId);
    if (!slot) return;
    slot.hidden = false;
    slot.replaceChildren();
    slot.append(page.candidate.element, page.editor);
  }

  function toggleOptionCard(id) {
    if (work.busy || work.optionsSaving || work.testing) return;
    if (!work.optionWork[id]) return;
    if (work.expandedOptionId === id) {
      work.expandedOptionId = "";
      unmountOptionDetail();
      render();
      return;
    }
    work.expandedOptionId = id;
    loadOptionIntoForm(id);
    if (work.candidate?.parallel_check && canRequestPreview(work.candidate) && !work.preview) {
      return applyDecision();
    }
  }

  function toggleOption(id, checked) {
    if (work.pendingOptionSave) { render(); return; }
    if (work.busy || work.optionsSaving || work.testing) return;
    const current = new Set(work.selectedOptions);
    if (checked) current.add(id); else current.delete(id);
    work.selectedOptions = [...current];
    work.requestKeyRegistry?.refresh();
    render();
  }

  async function saveSelectedOptions() {
    if (work.pendingOptionSave) return;
    if (work.busy || work.optionsSaving || work.testing || work.previewBusy || work.confirmBusy || work.aiLoading) return;
    if (work.readOnly || !hasCapability(user, "dv.manage") || analysisStale()) {
      notify(analysisStale() ? "请先应用需求修改后保存" : "当前无权保存规则", "warning");
      return;
    }
    syncActiveOptionState();
    const selected = work.options.filter((option) => work.selectedOptions.includes(option.id));
    if (!selected.length) return;
    const problems = selected.map((option) => ({ option, problem: optionDraftProblem(option, work.optionWork[option.id]) }))
      .filter((item) => item.problem);
    if (problems.length) {
      const target = problems[0];
      notify(`方案“${target.option.label || target.option.id}”需要完善：${target.problem}`, "warning");
      if (target.option.id !== work.activeOptionId) loadOptionIntoForm(target.option.id);
      return;
    }
    const pending = selected.filter((option) => {
      const state = work.optionWork[option.id];
      return !(state.saved && state.savedCanonical === canonicalOptionKey(canonicalOptionDefinition(state)));
    });
    if (!pending.length) {
      notify("所选方案均已保存，未重复创建", "info");
      return;
    }
    const definitions = pending.map((option) => canonicalOptionDefinition(work.optionWork[option.id]));
    const token = runtime.next("workbench-save");
    work.optionsSaving = true;
    render();
    try {
      const response = await runtime.request(token, (signal) => api.batchSaveCandidates({
        request_key: work.requestKeyRegistry.fingerprint(JSON.stringify(optionsFingerprint())),
        definitions,
      }, { signal }));
      if (!runtime.current(token)) return;
      work.optionsSaving = false;
      const rules = Array.isArray(response?.rules) ? response.rules : [];
      pending.forEach((option, index) => {
        const state = work.optionWork[option.id];
        const rule = rules[index];
        if (state && rule) {
          state.saved = rule;
          state.savedCanonical = canonicalOptionKey(canonicalOptionDefinition(state));
        }
      });
      work.savedOptionRules = rules;
      work.requestKeyRegistry.markSaved();
      notify(`已保存 ${rules.length} 条草稿（未自动启用）`, "success");
      render();
    } catch (error) {
      if (!runtime.current(token)) return;
      work.optionsSaving = false;
      notify(errorMessage(error, "批量保存失败"), "error");
      render();
    }
  }

  async function saveOptionAndEnable(id) {
    if (work.busy || work.optionsSaving || work.pendingOptionSave) return;
    const state = work.optionWork[id];
    if (!state) return;
    const gate = optionGate(id);
    if (!gate.enabled) {
      notify(gate.reasons.join("；") || "该方案暂不能启用", "warning");
      if (id !== work.activeOptionId) loadOptionIntoForm(id);
      return;
    }
    if (id !== work.activeOptionId) loadOptionIntoForm(id);
    syncActiveOptionState();
    const current = work.optionWork[id];
    const definition = canonicalOptionDefinition(current);
    const token = runtime.next("workbench-confirm");
    work.busy = true; render();
    try {
      let detail;
      if (current.saved && current.savedCanonical === canonicalOptionKey(definition)) {
        detail = await runtime.request(token, (signal) => api.rule(current.saved.id, { signal }));
      } else {
        const saved = await runtime.request(token, (signal) => api.save(definition, null, { signal }));
        if (!runtime.current(token)) return;
        current.saved = saved;
        current.savedCanonical = canonicalOptionKey(definition);
        detail = await runtime.request(token, (signal) => api.rule(saved.id, { signal }));
      }
      if (!runtime.current(token)) return;
      if (detail.content_sha256 !== current.preview.content_sha256) {
        throw new Error("已保存规则版本已变化，请到规则列表核实后继续。");
      }
      const cases = current.previewEvidence ? current.previewCases : null;
      const result = await runtime.request(token, (signal) => api.test(detail.id, {
        version_no: detail.version_no, ...(cases ? { cases } : {}),
      }, { signal }));
      if (!runtime.current(token)) return;
      const failed = Number(result.failed_count) || 0;
      const notRun = Number(result.not_run_count) || 0;
      const passed = Number(result.passed_count) || 0;
      if (!Array.isArray(result.cases) || !result.cases.length || failed || notRun || !passed) {
        throw new Error("该方案测试未全部通过，不能启用");
      }
      await runtime.request(token, (signal) => api.confirm(detail.id, {
        version_no: detail.version_no, expected_hash: detail.content_sha256,
      }, { signal }));
      if (!runtime.current(token)) return;
      current.saved = { ...(current.saved || {}), id: detail.id, rule_code: detail.rule_code, name: detail.name };
      current.savedCanonical = canonicalOptionKey(definition);
      notify(`方案已保存并启用：${detail.rule_code || ""}`, "success");
      render();
    } catch (error) {
      if (!runtime.current(token)) return;
      notify(errorMessage(error, "保存并启用失败"), "error");
      render();
    } finally {
      if (runtime.current(token)) { work.busy = false; render(); }
    }
  }

  async function saveSelectedOptionsAndEnable() {
    if (work.busy || work.optionsSaving || work.testing || work.previewBusy || work.confirmBusy || work.aiLoading) return;
    syncActiveOptionState();
    const gate = selectedOptionGate();
    if (!gate.enabled) { notify(gate.reasons.join("；"), "warning"); return; }
    const snapshots = gate.selected.map((option) => {
      const state = work.optionWork[option.id];
      const definition = structuredClone(canonicalOptionDefinition(state));
      return { state, definition, canonical: canonicalOptionKey(definition),
        hash: state.preview.content_sha256, cases: structuredClone(state.previewCases || state.previewEvidence.cases) };
    });
    const token = runtime.next("workbench-confirm");
    const signature = inputSignature();
    const current = () => runtime.current(token) && inputSignature() === signature;
    let started = 0, changed = false, complete = false;
    work.busy = true;
    render();
    try {
      const pending = snapshots.filter((item) => !item.state.saved || item.state.savedCanonical !== item.canonical);
      if (pending.length) {
        const definitions = pending.map((item) => item.definition);
        const recoveringSave = Boolean(work.pendingOptionSave);
        work.pendingOptionSave ??= {
          request_key: work.requestKeyRegistry.fingerprint(`save-and-enable:${canonicalOptionKey(definitions)}`), definitions,
        };
        let response;
        try {
          response = await runtime.request(token, (signal) => api.batchSaveCandidates({
            ...work.pendingOptionSave,
          }, { signal }));
        } catch (error) {
          // These structured rejections precede the batch transaction. Unknown prior attempts still keep their receipt.
          if (!recoveringSave && Number(error?.status) >= 400 && Number(error?.status) < 500
              && ["VALIDATION_ERROR", "FORBIDDEN", "CONFLICT_VERSION", "ANALYSIS_CONTEXT_CHANGED"].includes(error?.payload?.error?.code)) {
            work.pendingOptionSave = null;
          }
          throw error;
        }
        if (!current()) return;
        const rules = response?.rules;
        if (!Array.isArray(rules) || rules.length !== pending.length || rules.some((rule) => !Number.isInteger(Number(rule?.id)) || Number(rule.id) <= 0)
            || new Set(rules.map((rule) => String(rule.id))).size !== rules.length) {
          throw new Error("保存返回的规则不完整，请重试读取本次保存结果。");
        }
        pending.forEach((item, index) => {
          item.state.saved = rules[index];
          item.state.savedCanonical = item.canonical;
          businessReviewSession?.saved.set(item.canonical, rules[index]);
        });
        work.savedOptionRules = snapshots.map((item) => item.state.saved);
        work.requestKeyRegistry.markSaved();
        work.pendingOptionSave = null;
        changed = true;
      }
      const checked = [];
      // Verify every selected saved version before starting the first one.
      for (const item of snapshots) {
        const detail = await runtime.request(token, (signal) => api.rule(item.state.saved.id, { signal }));
        if (!current()) return;
        if (detail.content_sha256 !== item.hash) throw new Error(`「${item.definition.name}」的保存版本已变化，请重新核实。`);
        if (detail.status === "enabled" && detail.version_id && Number(detail.current_version_id) === Number(detail.version_id)) {
          started += 1;
          continue;
        }
        const result = await runtime.request(token, (signal) => api.test(detail.id, {
          version_no: detail.version_no, cases: item.cases,
        }, { signal }));
        if (!current()) return;
        const readiness = confirmationReadiness(detail, createTestEvidence(detail, result), false);
        item.state.previewEvidence = { ...result, content_sha256: item.hash };
        loadActiveTestState();
        if (!readiness.ready) throw new Error(`「${item.definition.name}」未通过保存版本复测：${readiness.reasons.join("；")}`);
        checked.push({ item, detail });
      }
      for (const { item, detail } of checked) {
        await runtime.request(token, (signal) => api.confirm(detail.id, {
          version_no: detail.version_no, expected_hash: detail.content_sha256,
        }, { signal }));
        if (!current()) return;
        item.state.saved = { ...item.state.saved, id: detail.id, rule_code: detail.rule_code, name: detail.name, status: "enabled" };
        item.state.savedCanonical = item.canonical;
        started += 1;
        changed = true;
      }
      complete = true;
      notify(`已保存并启动${snapshots.length}个方案`, "success");
    } catch (error) {
      if (current()) notify(started
        ? `已确认启动 ${started}/${snapshots.length} 个方案，其余尚未完成：${errorMessage(error)}`
        : errorMessage(error, "保存并启动失败，请重试"), "error");
    } finally {
      if (runtime.current(token)) {
        if (changed) {
          try { await onChanged?.(); }
          catch (error) { notify(`规则列表刷新失败：${errorMessage(error)}`, "warning"); }
        }
        if (runtime.current(token)) {
          work.busy = false;
          if (complete) close();
          else render();
        }
      }
    }
  }

  function suggestionScopeReady() {
    return work.mode === "ai" && !work.aiLoading && !work.previewBusy && !work.aiError
      && !analysisStale() && Boolean(work.preview?.sql_preview && work.preview?.definition)
      && !work.candidate?.questions?.length && !work.preview.questions?.length
      && ruleScopeIssues(work.preview.definition).length === 0
      && ruleScopeIssues(work.candidate || {}).length === 0;
  }

  function suggestionAdoptionReady(item) {
    if (item.adoption) {
      return !supplementWorkbench && !work.aiLoading && !work.aiError && !work.previewBusy && !analysisStale()
        && !work.options.some(o => o.suggestionId === item.id) && !deferredSupplements.some(o => o.suggestionId === item.id)
        && !item.references_ambiguous && item.support_level !== "unsupported" && Boolean(item.references?.length);
    }
    if (!suggestionScopeReady()) return false;
    const table = String(work.candidate?.table_name || "").toLowerCase();
    const fields = comparisonFields(work.candidate?.expression).map((name) => name.toLowerCase());
    return item?.support_level === "supported" && !item.references_ambiguous
      && Array.isArray(item.references) && item.references.some((ref) =>
        String(ref?.table_name || "").toLowerCase() === table
        && fields.includes(String(ref?.field_name || "").toLowerCase()));
  }

  function appendSupplementCards(cards) {
    if (!work.options.length) {
      const primary = work.candidate;
      const id = "primary";
      work.options = [{ id, label: primary.rule_name, candidate: primary, recommended: true,
        table_label: primary.table_name_cn || primary.table_name, field_label: comparisonFields(primary.expression).join("、") }];
      work.activeOptionId = id;
      work.selectedOptions = [id];
      work.optionWork[id] = { saved: work.ruleId ? work.detail : null };
      work.requestKeyRegistry = createRequestKeyRegistry();
    }
    syncActiveOptionState();
    for (const card of cards) {
      if (work.optionWork[card.id]) continue;
      work.options.push(card);
      work.optionWork[card.id] = { candidate: card.candidate, definition: null, selectedChoice: null,
        preview: card.candidate.preview, previewCases: null, previewEvidence: null, analysisInput: work.analysisInput, saved: null };
      if (card.recommended) work.selectedOptions.push(card.id);
    }
    work.requestKeyRegistry.refresh();
    work.expandedOptionId = cards[0].id;
    loadOptionIntoForm(cards[0].id);
  }

  function returnSupplementWhenReady() {
    if (!onSupplementReady || returningSupplement || activeAnalysis || businessReview || work.previewBusy
        || !work.preview?.sql_preview || analysisStale()) return;
    const options = work.options.length ? work.options : [{ id: "primary", label: work.candidate.rule_name, candidate: work.candidate }];
    const cards = options.map(option => {
      const state = work.optionWork[option.id];
      const candidate = state?.candidate || option.candidate;
      return { ...option, candidate: { ...candidate, preview: state?.preview || candidate.preview },
        recommended: !work.options.length || work.selectedOptions.includes(option.id) };
    });
    if (cards.some(card => !card.candidate.preview?.sql_preview)) return;
    const anchor = previewPayload({}, work.candidate);
    delete anchor.definition;
    returningSupplement = true;
    // Finish the current refresh before disposing its form and listeners.
    queueMicrotask(() => {
      if (!dialog) return;
      try {
        onSupplementReady(cards, anchor);
        close();
      } catch (error) {
        returningSupplement = false;
        notify(errorMessage(error, "补充方案未能加入当前工作台"), "error");
      }
    });
  }

  function selectedAdoptionOptions() {
    return work.options.length ? work.options.filter(o => work.selectedOptions.includes(o.id))
      .map(o => ({ candidate: work.optionWork[o.id]?.candidate || o.candidate,
        preview: o.id === work.activeOptionId ? work.preview : work.optionWork[o.id]?.preview }))
      : [{ candidate: work.candidate, preview: work.preview }];
  }

  function periodConditions(item) {
    if (businessReview || item.category !== "period" || !item.adoption || item.references?.length !== 1
        || !work.analysis?.analysis_id || !work.analysis.result?.analysis_context) return [];
    const ref = item.references[0];
    const summaries = new Set();
    for (const { preview, candidate } of selectedAdoptionOptions()) {
      const d = preview?.definition;
      if (!d || d.join || !preview.sql_preview || !preview.content_sha256 || candidate?.questions?.length || preview.questions?.length
          || d.table_name !== ref.table_name) return [];
      const terms = d.expression?.conditions || [d.expression];
      const source = terms[0]?.left;
      const columnType = name => String(preview.columns?.find(c => c.column_name === name)?.data_type || "")
        .toLowerCase().split("(")[0].trim();
      const family = type => {
        if (/^(?:tinyint|mediumint|smallint|int(?:eger|2|4|8)?|bigint|bit|decimal|numeric|float[48]?|double(?: precision)?|real|money|(?:big)?serial)$/.test(type)) return "number";
        if (/^(?:char|varchar|text|tinytext|mediumtext|longtext|enum|set|uuid|character varying|character|bpchar)$/.test(type)) return "text";
        if (/^(?:date|datetime|timestamp|time|year)$/.test(type)) return "date";
        return "";
      };
      const targetType = family(columnType(ref.field_name));
      if (!targetType || typeof source !== "string" || targetType !== family(columnType(source))) return [];
      if (!terms.every(t => t.left === source && (!t.left_type || t.left_type === "field")
          && (["is_null", "is_not_null"].includes(t.op) || (targetType === "number" && t.right_type === "value"
            && Number.isFinite(t.right) && ["gt","gte","lt","lte","eq","neq"].includes(t.op))))) return [];
      const renamed = terms.map(t => ({ ...t, left: ref.field_name }));
      const expression = isGrouped(d.expression) ? { ...d.expression, conditions: renamed } : renamed[0];
      const policies = { skip: "空值跳过", review: "空值待核查", zero: "数值空值按0", violate: "空值计异常", empty_string_as_null: "空字符串视为空值" };
      summaries.add([candidateCondition({ ...d, expression, columns: preview.columns }), policies[d.null_policy]].filter(Boolean).join("，"));
    }
    return [...summaries];
  }

  async function adoptSuggestion(suggestion, inheritCheck = false) {
    if (!suggestionAdoptionReady(suggestion) || work.testing || work.busy || work.confirmBusy
        || work.optionsSaving || work.pendingOptionSave || work.readOnly || !hasCapability(user, "dv.ai_use")) return;
    if (suggestion.adoption) {
      const { source_id, model_id, reasoning_enabled } = page.form.read();
      const referenced = new Set(suggestion.references.map(ref => ref.table_name));
      const options = selectedAdoptionOptions();
      const inheritedConditions = inheritCheck ? periodConditions(suggestion) : [];
      if (inheritCheck && !inheritedConditions.length) return;
      const scopes = [];
      const checks = [];
      const parents = [];
      const categories = new Set();
      for (const { candidate, preview } of options) {
        if (!candidate || (!referenced.has(candidate.table_name) && !referenced.has(candidate.join?.table_name))) continue;
        if (candidate.report_category) categories.add(candidate.report_category);
        const filters = [];
        for (const filter of candidate.filters || []) {
          if (filter.confirmed !== true) continue;
          const table = filter.table === "related" ? candidate.join?.table_name : candidate.table_name;
          if (table) filters.push({ table, field: filter.field, op: filter.op, value: filter.value });
        }
        scopes.push({ table: candidate.table_name, filters });
        const def = preview?.definition;
        if (!businessReview && preview?.sql_preview && def?.expression && !candidate.questions?.length && !preview.questions?.length) {
          checks.push({ table: def.table_name, related_table: def.join?.table_name, join: def.join, expression: def.expression,
            null_policy: def.null_policy, null_handling: def.null_handling, equality_policy: def.equality_policy });
          if (referenced.has(def.table_name) && preview.content_sha256) parents.push({ definition: def, hash: preview.content_sha256 });
        }
      }
      const request = [
        suggestion.title, suggestion.reason !== suggestion.title ? suggestion.reason : "",
        suggestion.kind && "建议检查类型：" + suggestion.kind,
        "文档字段：" + suggestion.references.map(ref => `${ref.table_name}.${ref.field_name}`).join("、"),
        categories.size === 1 && "原方案报送分类：" + [...categories][0],
        suggestion.adoption.operations?.length && "建议运算：" + suggestion.adoption.operations.join("、"),
        suggestion.applicability_filters?.length && "已核实的期间适用范围：" + JSON.stringify(suggestion.applicability_filters),
        scopes.some(group => group.filters.length) && "各原方案的适用范围：" + JSON.stringify(scopes),
        checks.length && "已选方案的检查口径：" + JSON.stringify(checks),
        checks.length && "用户已选且核实的适用范围默认保留在新方案的筛选条件中。建议明确改变某项范围时，仅替换对应条件，其余保留。新增期间限制与原范围叠加，须同时满足。主方案的异常表达式仅作背景，按建议的独立目标生成检查，不机械取反或合并。期间指标建议明确继承主方案边界时，沿用相应上下界、等号和空值口径。",
        inheritCheck && "用户选择按原条件采纳。以下为该期间指标的已确认异常条件，原建议中的条件描述由本次选择替代：" + inheritedConditions.join("；"),
        suggestion.adoption.preconditions?.length && "原建议所列前提，请结合当前已确认业务知识核实：" + suggestion.adoption.preconditions.join("；"),
        suggestion.limitations?.length && "建议适用限制：" + suggestion.limitations.join("；"),
      ].filter(Boolean).join("\n");
      let adoptionContext = null;
      if (suggestion.category === "period" && referenced.size === 1 && work.analysis?.analysis_id && work.analysis.result?.analysis_context) {
        const owner = { parent_analysis_id: work.analysis.analysis_id, parent_context: work.analysis.result.analysis_context,
          suggestion_id: suggestion.id };
        if (parents.length && parents.length === options.length && parents.every(p => !p.definition.join)
            && (inheritCheck || suggestion.applicability_filters?.length || parents.some(p => p.definition.filters?.length))) {
          adoptionContext = { ...owner, parents, ...(inheritCheck ? { inherit_check: true } : {}) };
        } else if (suggestion.applicability_filters?.length) {
          adoptionContext = { ...owner, mode: "suggestion_only" };
        }
      }
      const childRuntime = createRuntime({ notify });
      const parentInput = inputSignature();
      childRuntime.activate();
      const parentOverlay = dialog.element;
      parentOverlay.hidden = true;
      supplementWorkbench = createWorkbench({ state, api, user, notify, host, confirmAction, onChanged, onRetrySources, onRetryModels,
        onSupplementReady: (options, anchor) => {
          if (!dialog || parentInput !== inputSignature()) return;
          const cards = options.map((option, index) => ({ ...option,
            id: `supplement-${suggestion.id}${index ? "-" + index : ""}`, supplemental: true, suggestionId: suggestion.id,
            label: option.label || suggestion.title, match_reason: suggestion.reason,
            candidate: { ...option.candidate, supplementAnalysis: anchor } }));
          if (businessReview || !work.candidate?.rule_type) {
            deferredSupplements.push(...cards);
            deferredSupplementInput = JSON.stringify(JSON.parse(parentInput).slice(0, 4));
          } else appendSupplementCards(cards);
        },
        runtime: childRuntime, listen: childRuntime.listen, onClose: () => {
          childRuntime.destroy();
          supplementWorkbench = null;
          parentOverlay.hidden = false;
          render();
        } });
      try {
        await supplementWorkbench.open({ mode: "ai", supplement: { title: suggestion.title, adoptionContext,
          signature: JSON.stringify([source_id, request, model_id, reasoning_enabled]) } });
      } catch (error) {
        // An analysis error stays visible in the independent editor for retry.
        if (!supplementWorkbench?.isOpen()) {
          childRuntime.destroy();
          supplementWorkbench = null;
          parentOverlay.hidden = false;
        }
        throw error;
      }
      return;
    }
    if (!suggestion.definition) return;
    const id = `supplement-${suggestion.id}`;
    if (work.optionWork[id]) return;
    const primary = work.candidate;
    const token = runtime.next("workbench-preview");
    const snapshot = inputSignature();
    work.previewBusy = true;
    render();
    try {
      const proposed = { ...suggestion.definition, rule_name: suggestion.definition.name,
        questions: suggestion.questions || suggestion.definition.questions || [],
        uncertainties: [...new Set([...(suggestion.definition.uncertainties || []), ...(suggestion.preconditions || [])])] };
      const response = canRequestPreview(proposed)
        ? await runtime.request(token, (signal) => api.preview(previewPayload(proposed, proposed), { signal })) : null;
      if (!runtime.current(token) || inputSignature() !== snapshot) return;
      if (!work.options.length) {
        const primaryId = `primary-${work.preview.content_sha256}`;
        work.options = [{ id: primaryId, label: primary.rule_name || work.preview.definition.name,
          candidate: primary, recommended: true, table_label: primary.table_name_cn || primary.table_name,
          field_label: comparisonFields(primary.expression).map((name) =>
            page.form.metadataColumns().find((field) => field.column_name === name)?.comment || name).join("、"),
          grain: primary.grain || "", match_reason: "原校验方案",
        }];
        work.activeOptionId = primaryId;
        work.selectedOptions = [primaryId];
        work.optionWork[primaryId] = {};
        work.requestKeyRegistry = createRequestKeyRegistry();
        syncActiveOptionState();
      }
      const primaryOption = work.options.find((option) => option.candidate?.table_name === proposed.table_name);
      proposed.columns = primaryOption?.candidate?.columns || [];
      const candidate = response ? receivePreview(proposed, response) : reviewCandidate(proposed);
      work.options.push({ id, supplemental: true, label: suggestion.title, grain: primaryOption?.grain || "",
        table_label: primaryOption?.table_label || candidate.table_name, field_label: primaryOption?.field_label || comparisonFields(candidate.expression).join("、"),
        match_reason: suggestion.reason, candidate,
      });
      work.optionWork[id] = { candidate, definition: null, selectedChoice: null, preview: candidate.preview,
        previewCases: null, previewEvidence: null, analysisInput: snapshot, saved: null,
      };
      work.selectedOptions = [...work.selectedOptions, id];
      work.requestKeyRegistry.refresh();
      work.expandedOptionId = id;
      loadOptionIntoForm(id);
    } finally {
      if (runtime.current(token)) { work.previewBusy = false; render(); }
    }
  }

  function renderSuggestions() {
    if (!page || !page.suggestionsSection) return;
    page.suggestionRemovers.splice(0).forEach((remove) => remove?.());
    const list = !onSupplementReady && work.mode === "ai" && !work.aiLoading && !work.aiError && !analysisStale()
      ? work.aiSuggestions.filter((item) => item && typeof item === "object") : [];
    page.suggestionsSection.hidden = !list.length;
    page.suggestionsList.replaceChildren();
    list.forEach((item) => {
      const adopted = Boolean(work.optionWork[`supplement-${item.id}`]) || deferredSupplements.some(o => o.suggestionId === item.id);
      const conditions = periodConditions(item);
      const adopt = (item.adoption || (item.support_level === "supported" && item.definition)) && item.id && hasCapability(user, "dv.ai_use")
        ? button(adopted ? "已采纳" : conditions.length ? "按原条件采纳" : "采纳", { capability: "dv.ai_use", className: "dv-button dv-ai-supplement-adopt",
          disabled: !suggestionAdoptionReady(item) || adopted || work.testing || work.busy || work.confirmBusy || work.optionsSaving || Boolean(work.pendingOptionSave) || work.readOnly,
        }) : null;
      if (adopt) page.suggestionRemovers.push(listen(adopt, "click", () => adoptSuggestion(item, Boolean(conditions.length))));
      const independent = adopt && conditions.length && !adopted
        ? button("独立分析", { capability: "dv.ai_use", className: "dv-button", disabled: adopt.disabled }) : null;
      if (independent) page.suggestionRemovers.push(listen(independent, "click", () => adoptSuggestion(item)));
      const card = element("div", { className: "dv-ai-supplement" },
        element("div", { className: "dv-ai-supplement-head" },
          element("strong", { text: item.title || "补充建议" }),
          element("span", { className: `dv-ai-supplement-support is-${item.support_level || "needs_confirmation"}`,
            text: item.support_level === "supported" ? "可进一步检查"
              : item.support_level === "unsupported" ? "暂不支持直接生成" : item.adoption ? "可单独分析" : "需先确认口径" }), adopt, independent));
      if (conditions.length) card.append(element("div", { className: "dv-ai-supplement-reason",
        text: "按原条件检查：" + conditions.join("；") }));
      card.append(element("div", { className: "dv-ai-supplement-reason", text: item.provenance === "model"
        ? (item.references_ambiguous ? "来源：模型建议，待确认文档归属" : "来源：模型建议，系统已核对文档引用")
        : "来源：待核实的建议依据" }));
      if (item.applicability_filters?.length) {
        const source = selectedAdoptionOptions().find(({ candidate }) => candidate?.table_name === item.references[0]?.table_name);
        if (source) {
          const scope = candidateFiltersText({ columns: source.preview?.columns || source.candidate.columns,
            filters: item.applicability_filters.map(f => ({ ...f, table: "base" })),
            semantic_intent: { dictionary_snapshots: { base: item.applicability_dictionary || {} } } });
          card.append(element("div", { className: "dv-ai-supplement-pre", text: "已核实的期间适用范围：" + scope }));
        }
      }
      if (item.reason) card.append(element("div", { className: "dv-ai-supplement-reason",
        text: (conditions.length ? "独立分析建议：" : "") + item.reason }));
      if (Array.isArray(item.references) && item.references.length) {
        card.append(element("div", { className: "dv-ai-supplement-refs", text: `证据：${item.references
          .map((ref) => `${ref.table_name || "—"}.${ref.field_name || "—"}`).join("；")}` }));
      }
      if (Array.isArray(item.preconditions) && item.preconditions.length) {
        const label = item.adoption ? "建议所列前提" : "待核实";
        card.append(element("div", { className: "dv-ai-supplement-pre", text: `${label}：${item.preconditions.join("；")}` }));
      }
      if (Array.isArray(item.limitations) && item.limitations.length) {
        card.append(element("ul", { className: "dv-ai-supplement-limits" },
          item.limitations.map((text) => element("li", { text: (conditions.length ? "独立分析限制：" : "") + text }))));
      }
      page.suggestionsList.append(card);
    });
  }

  function businessAnswerKey(item) {
    return JSON.stringify([item.key, item.question, item.targets, item.multiple, item.dictionaries]);
  }

  function restoreBusinessAnswers(items) {
    const answers = businessReviewSession?.answers;
    return items.map((item) => answers?.has(businessAnswerKey(item))
      ? { ...item, value: structuredClone(answers.get(businessAnswerKey(item))) } : item);
  }

  function startBusinessReview(result, session = null) {
    businessReviewSession = session || {
      result: structuredClone(result), input: inputSignature(), answers: new Map(), saved: new Map(), requestKeyRegistry: null,
    };
    const options = preparedOptions(result.candidate_options);
    const items = restoreBusinessAnswers(collectBusinessQuestions(options));
    businessReview = { result, options, items, decisions: [], retry: false };
    work.candidate = { ...options[0].candidate, questions: [], preview: null };
    work.analysisInput = inputSignature();
    work.selectedChoice = null;
    work.descriptionCollapsed = true;
    work.preview = null; work.previewCases = null; work.previewEvidence = null;
    page.businessQuestions.clear();
    render();
    if (!items.length) return verifyBusinessReview();
  }

  function canReselectBusinessQuestions() {
    return work.mode === "ai" && Boolean(businessReviewSession?.answers.size) && !businessReview
      && businessReviewSession.input === inputSignature();
  }

  function reselectBusinessQuestions() {
    if (!canReselectBusinessQuestions() || work.pendingOptionSave || work.readOnly || !hasCapability(user, "dv.ai_use")
        || work.busy || work.testing || work.preparingTests || work.confirmBusy || work.previewBusy || work.aiLoading || work.optionsSaving) return;
    const session = businessReviewSession;
    session.reselecting = true;
    work.options.forEach((option) => {
      const state = work.optionWork[option.id];
      if (state?.saved && state.savedCanonical) session.saved.set(state.savedCanonical, state.saved);
    });
    if (work.detail?.definition) {
      session.saved.set(canonicalOptionKey(work.detail.definition), work.detail);
    }
    if (work.requestKeyRegistry) session.requestKeyRegistry = work.requestKeyRegistry;
    ["workbench-preview", "workbench-test", "workbench-save", "workbench-confirm"].forEach((channel) => runtime.invalidate(channel));
    // Rebuild from the original candidates, never from already expanded/confirmed plans.
    // Saved rules remain independent; new selections require fresh preview and test evidence.
    Object.assign(work, {
      ruleId: null, detail: null, evidence: null, candidate: null,
      preview: null, previewCases: null, previewEvidence: null, selectedChoice: null,
      options: [], selectedOptions: [], activeOptionId: "", expandedOptionId: "", optionWork: {},
      requestKeyRegistry: null, savedOptionRules: [], comparisonSuggestions: [],
      aiSuggestions: session.result.ai_suggestions || [], aiError: "", analysisNote: "",
    });
    work.revision += 1;
    page.form.reset(null);
    page.form.setSources(); page.form.setCategories(); page.form.setModels();
    restoreAnalysisInput(session.input);
    const pending = startBusinessReview(structuredClone(session.result), session);
    scrollToSection(page.configSection);
    return pending;
  }

  async function confirmBusinessQuestions(answers) {
    const batch = businessReview;
    if (!batch || work.previewBusy || analysisStale()) return;
    const [source, requestText] = JSON.parse(work.analysisInput);
    const decisions = batch.items.map(({ key, context, question }) => {
      const value = answers.get(key);
      const values = Array.isArray(value) ? value : [value];
      const meaning = values.map((v) => {
        const selected = question.options?.find((o) => (o.selection ?? o.value) === v
          || (o.selection && JSON.stringify(o.selection) === JSON.stringify(v)));
        if (!selected) return String(v);
        const filter = selected.selection;
        const detail = filter?.field ? `${filter.field} ${filter.op} ${[].concat(filter.value).join("、")}` : selected.value;
        return `${selected.label}（${detail}）`;
      }).join("、");
      return { question_id: question.id || "", context: question.evidence_term || context || "", question: question.text, answer: meaning };
    });
    if (batch.items.some(({ question }) => !question.options?.length || question.requires_analysis)) {
      if (businessReviewSession?.reselecting) {
        notify("当前口径仍需补充依据，请修改需求后重新分析。", "warning");
        return;
      }
      const merged = new Map();
      for (const item of [...clarificationAnswers(page.form.read()), ...batch.decisions, ...decisions]) {
        merged.set(JSON.stringify([item.question_id, item.context, item.question]), item);
      }
      clarificationContext = { source, request: requestText, answers: [...merged.values()] };
      work.candidate = { ...work.candidate, questions: batch.items.map((item) => item.question) };
      await parse();
      return;
    }
    try {
      batch.options = applyBusinessAnswers(batch.options, batch.items, answers, state, user, requestText);
      batch.items.forEach((item) => businessReviewSession.answers.set(businessAnswerKey(item), structuredClone(answers.get(item.key))));
      batch.decisions.push(...decisions);
      batch.items = [];
      await verifyBusinessReview();
    } catch (error) {
      notify(errorMessage(error), "error");
    }
  }

  async function verifyBusinessReview() {
    const batch = businessReview;
    if (!batch || work.previewBusy || analysisStale()) return;
    const token = runtime.next("workbench-preview");
    const snapshot = work.analysisInput;
    const current = () => businessReview === batch && runtime.current(token) && inputSignature() === snapshot;
    const requestText = JSON.parse(snapshot)[1];
    work.previewBusy = true;
    batch.retry = false;
    render();
    let active;
    try {
      const strict = batch.options.some(({ candidate }) => candidate.analysis_protocol === 2);
      for (const reviewOnly of strict ? [true, false] : [false]) {
        for (const option of batch.options) {
          active = option;
          const candidate = option.candidate;
          if (candidate.preview?.sql_preview && !reviewOnly) continue;
          const definition = reviewDefinition(candidate, state, user, requestText);
          const payload = previewPayload(definition, candidate);
          if (reviewOnly) payload.review_only = true;
          const response = await runtime.request(token, (signal) => api.preview(payload, { signal }));
          if (!current()) return;
          option.candidate = receivePreview(candidate, response);
          if (reviewOnly && response.ready !== true && !collectBusinessQuestions([option]).length) {
            throw new Error("文档复核尚未确认该口径，请重试。");
          }
          if (!reviewOnly && !option.candidate.preview?.sql_preview) break;
        }
        batch.items = restoreBusinessAnswers(collectBusinessQuestions(batch.options));
        if (batch.items.length) {
          page.businessQuestions.clear();
          return;
        }
      }
      if (batch.options.some(({ candidate }) => !candidate.preview?.sql_preview)) throw new Error("未取得完整预览，请重试。");
      businessReview = null;
      work.previewBusy = false;
      page.businessQuestions.clear();
      if (batch.options.length === 1) applySingleResult(batch.options[0].candidate);
      else {
        const originalIds = new Set(batch.result.candidate_options.map((item) => item.id));
        setupMultiOptions({ ...batch.result, candidate_options: batch.options.map((item) => ({
          ...item, fromSelection: !originalIds.has(item.id),
        })) });
      }
    } catch (error) {
      if (!current()) return;
      batch.retry = true;
      work.candidate = { ...active?.candidate, ...previewFailure(error), preview: null };
      if (!work.candidate.preview_request_error && !work.candidate.analysis_context_changed) {
        batch.items = restoreBusinessAnswers(collectBusinessQuestions([{ ...active, candidate: work.candidate }]));
        batch.retry = !batch.items.length;
      }
    } finally {
      if (runtime.current(token)) {
        work.previewBusy = false;
        render();
      }
    }
  }

  function applyAnalysisResult(result) {
    if (!result) {
      work.aiError = "AI 分析未返回结果";
      render();
      return;
    }
    if (Array.isArray(result.candidate_options) && result.candidate_options.length > 1) {
      work.aiSuggestions = Array.isArray(result.ai_suggestions) ? result.ai_suggestions : [];
      if (preparedOptions(result.candidate_options).some(({ candidate }) =>
        candidate.questions.length || candidateIssues(candidate).length || (candidate.analysis_protocol === 2 && !candidate.preview))) {
        startBusinessReview(result);
        return;
      }
      setupMultiOptions(result);
      page.form.setBusy(work.busy);
      render();
      return;
    }
    if (result.candidate_options?.length === 1 && !result.rule_type) result = { ...result, ...result.candidate_options[0].candidate };
    const single = { id: "primary", label: result.rule_name, candidate: reviewCandidate(result), recommended: true };
    const represented = new Set(single.candidate.questions.flatMap((item) => [item.text, item.uncertainty]));
    const legacyRecheck = !result.analysis_protocol && !result.preview_error && !result.unsupported_requirements?.length
      && result.uncertainties?.some((note, index) => !represented.has(note) && !result.uncertainty_resolutions?.[index]);
    if (!single.candidate.preview && (result.analysis_protocol === 2 || (single.candidate.questions.length
        && !legacyRecheck && collectBusinessQuestions([single]).length > 1))) {
      work.aiSuggestions = result.ai_suggestions || [];
      startBusinessReview({ ...result, candidate_options: [single] });
      return;
    }
    applySingleResult(result);
  }

  function applySingleResult(result) {
    result = reviewCandidate(result);
    work.candidate = result;
    work.aiSuggestions = Array.isArray(result.ai_suggestions) ? result.ai_suggestions : [];
    work.selectedChoice = null;
    work.analysisInput = inputSignature();
    work.preview = result.preview || null;
    work.previewCases = null;
    work.previewEvidence = null;
    const saved = work.preview && businessReviewSession?.saved.get(canonicalOptionKey(work.preview.definition));
    if (saved) {
      work.ruleId = Number(saved.id);
      work.detail = { ...saved, definition: work.preview.definition, generation_mode: "ai" };
    }
    if (result.rule_type === "field_compare" && Array.isArray(result.columns)) {
      page.form.setMetadata({
        columns: result.columns, related_columns: result.related_columns || [],
        project_columns: result.project_columns || null, project_table: result.project_table || null,
        mapping_version: result.mapping_version,
      });
      page.form.applyCandidate(result, { regenerate: false });
      work.descriptionCollapsed = true;
    } else if (result.status === "needs_clarification") {
      page.form.applyCandidate(result, { regenerate: false });
      work.descriptionCollapsed = false;
    } else notify("当前仅支持 field_compare 候选编辑，其他类型不会伪装成可编辑规则", "warning");
    page.form.setBusy(work.busy);
    render();
  }

  function finishAnalysis() {
    activeAnalysis = null;
    work.aiLoading = false;
    stopAnalysisPolling();
    stopElapsed();
    page.form.setBusy(work.busy);
  }

  // POST、GET 和 DELETE 都返回同一种快照；只有服务端终态才能解除等待。
  function applyAnalysisSnapshot(run, snapshot) {
    if (!["running", "cancelling", "completed", "failed", "cancelled"].includes(snapshot?.status)) {
      throw new Error("未收到有效的分析状态");
    }
    work.analysis = snapshot;
    if (snapshot.status === "cancelling") {
      run.ending = true;
      run.stopSent = true;
    }
    if (!["completed", "failed", "cancelled"].includes(snapshot.status)) {
      render();
      return false;
    }
    finishAnalysis();
    if (supplementTitle && run.ending) {
      close();
      return true;
    }
    if (snapshot.status === "cancelled") {
      work.analysisNote = ANALYSIS_ENDED_NOTE;
    } else if (snapshot.status === "completed") {
      applyAnalysisResult(snapshot.result);
      return true;
    } else {
      const error = { ...snapshot.error };
      if (error.code === "ANALYSIS_TIMEOUT") {
        const limit = Number.isFinite(snapshot.timeout_ms) ? `（${snapshot.timeout_ms / 1000} 秒）` : "";
        error.message = `已达到分析总时限${limit}，请重新分析或转手工继续。`;
      } else if (error.code === "ANALYSIS_ROUND_LIMIT") {
        error.message = "本次分析已达到模型调用轮数上限。请补充待校验的对象、字段或条件后重新分析。";
      }
      work.aiError = errorMessage({ payload: { error } }, "AI 分析失败");
    }
    render();
    return true;
  }

  function startAnalysisPolling(run) {
    stopAnalysisPolling();
    const token = run.token;
    const tick = async () => {
      analysisTimer = null;
      if (!runtime.current(token) || activeAnalysis !== run) return;
      try {
        const snapshot = await runtime.request(token, (signal) =>
          analysisConnection((connection) => api.getAnalysis(run.id, { signal: connection }), signal));
        if (!runtime.current(token) || activeAnalysis !== run) return;
        run.pollError = "";
        if (applyAnalysisSnapshot(run, snapshot)) return;
      } catch (error) {
        if (!runtime.current(token) || activeAnalysis !== run) return;
        const code = error?.payload?.error?.code || error?.code;
        if (["FORBIDDEN", "ANALYSIS_UNAVAILABLE"].includes(code)) {
          finishAnalysis();
          work.aiError = `无法再查询本次分析：${errorMessage(error)}`;
          render();
          return;
        }
        run.pollError = "进度连接中断，正在重新连接。页面显示的是上次收到的后台状态。";
        if (Number.isFinite(work.analysis?.timeout_ms) && work.aiElapsed * 1000 >= work.analysis.timeout_ms) {
          finishAnalysis();
          work.aiError = "进度连接中断，已超过本次分析的等待时限，无法确认后台结果。";
          render();
          return;
        }
        if (run.ending) {
          run.stopSent = false;
          run.stopError = "暂时无法确认会话已结束，请重试结束会话。";
          render();
          return;
        }
        renderElapsed();
      }
      analysisTimer = runtime.setTimer(tick, ANALYSIS_POLL_MS);
    };
    analysisTimer = runtime.setTimer(tick, ANALYSIS_POLL_MS);
  }

  async function cancelWaiting() {
    const run = activeAnalysis;
    if (!run || run.stopSent) return;
    run.ending = true;
    run.stopError = "";
    stopAnalysisPolling();
    render();
    // 创建响应带回任务 ID 后由 parse 接续发送同一次取消。
    if (!run.id) return;
    run.stopSent = true;
    run.token = runtime.next("workbench-ai");
    try {
      const snapshot = await analysisConnection((signal) => api.cancelAnalysis(run.id, { signal }));
      if (activeAnalysis !== run || !runtime.current(run.token)) return;
      if (!applyAnalysisSnapshot(run, snapshot)) startAnalysisPolling(run);
    } catch (error) {
      if (activeAnalysis !== run || !runtime.current(run.token)) return;
      run.stopSent = false;
      run.stopError = `未能确认会话已结束，请重试结束会话。${errorMessage(error)}`;
      render();
    }
  }

  async function parse() {
    if (work.pendingOptionSave) { notify("请先重试保存，核实上一次保存结果。", "warning"); return; }
    if (activeAnalysis) return;
    const context = page.form.read();
    if (deferredSupplements.length && JSON.stringify(JSON.parse(inputSignature()).slice(0, 4)) !== deferredSupplementInput) {
      deferredSupplements = [];
    }
    if (!context.request_text) throw new Error("请先填写需求描述");
    if (!context.model_id) throw new Error(state.modelsStatus === "error" ? "模型加载失败，请转手工继续或重试" : "请选择可用模型，或转手工继续");
    if (!context.source_id || !context.dialect) throw new Error("请先选择有效数据源");
    page.form.validateForParse();
    const previous = revisionContext(context);
    businessReview = null;
    businessReviewSession = null;
    page.businessQuestions.clear();
    const token = runtime.next("workbench-ai");
    const revision = work.revision;
    work.aiLoading = true;
    work.aiError = "";
    work.analysisNote = "";
    const run = { token, id: null, ending: false, stopSent: false, continued: false };
    activeAnalysis = run;
    work.analysis = {
      analysis_id: "", status: "running", elapsed_ms: 0,
      activity: { phase: "submitting", detail: "正在提交分析请求" },
      steps: ANALYSIS_STEPS.map((step) => ({ id: step.id, status: "pending" })),
    };
    work.candidate = null;
    work.preview = null;
    work.previewEvidence = null;
    work.previewCases = null;
    work.selectedChoice = null;
    work.options = []; work.selectedOptions = []; work.activeOptionId = ""; work.expandedOptionId = ""; work.optionWork = {};
    work.comparisonSuggestions = []; work.aiSuggestions = []; work.savedOptionRules = []; work.optionsSaving = false;
    startElapsed();
    page.form.setBusy(true);
    render();
    try {
      // 首次 GET 才启动模型。即使创建响应丢失，模型也不会在后台运行。
      const snapshot = await runtime.request(token, (signal) => analysisConnection((connection) => api.createAnalysis({
        request_text: context.request_text,
        model_id: context.model_id,
        reasoning_enabled: context.reasoning_enabled,
        clarification_answers: clarificationAnswers(context),
        source_id: context.source_id,
        await_first_poll: true,
        ...(onSupplementReady ? { include_suggestions: false } : {}),
        ...(supplementAdoption ? { adoption_context: supplementAdoption } : {}),
        ...previous,
      }, { signal: connection }), signal));
      if (!runtime.current(token) || activeAnalysis !== run) {
        if (snapshot?.analysis_id && !["completed", "cancelled", "failed"].includes(snapshot.status)) {
          await cancelDetachedAnalysis(snapshot.analysis_id);
        }
        return;
      }
      run.id = snapshot.analysis_id;
      if (work.revision !== revision) run.ending = true;
      if (applyAnalysisSnapshot(run, snapshot)) return;
      if (run.ending && !run.stopSent) await cancelWaiting();
      else startAnalysisPolling(run);
    } catch (error) {
      if (!runtime.current(token) || activeAnalysis !== run) return;
      finishAnalysis();
      work.aiError = run.ending ? `未能确认本次会话的状态：${errorMessage(error)}` : errorMessage(error, "AI 分析失败");
      if (error?.payload?.error?.code === "VALIDATION_ERROR") {
        work.aiError += "（请确认已在「校验设置 → 文档快照」导入文档，且表/字段存在）";
      }
      work.descriptionCollapsed = false;
      page.form.setBusy(work.busy);
      render();
      throw error;
    }
  }

  function savedAiRule() {
    return work.detail?.generation_mode === "ai" || work.detail?.definition?.generation_mode === "ai";
  }

  function savedAiNeedsReview() {
    return savedAiRule() && (page.form.isDirty() || ruleScopeIssues(work.detail.definition).length > 0);
  }

  function definitionForSave() {
    if (work.mode === "ai") {
      if (!work.preview?.definition || analysisStale()) throw new Error("请先确认全部口径并生成 SQL");
      return work.preview.definition;
    }
    const definition = page.form.validateForSave();
    if (savedAiRule()) {
      const issues = ruleScopeIssues(definition, { detailed: true });
      if (issues.length) throw new Error(issues.join("；"));
    }
    return definition;
  }

  async function saveDraft() {
    if (work.pendingOptionSave) return;
    const payload = definitionForSave();
    const reviewed = work.ruleId && savedAiRule() ? page.form.reviewedUncertainties() : [];
    const request = reviewed.length ? { ...payload, reviewed_uncertainties: reviewed } : payload;
    const token = runtime.next("workbench-save");
    const revision = work.revision;
    work.busy = true;
    page.form.setBusy(true);
    render();
    try {
      const existing = work.mode === "ai" && businessReviewSession?.saved.get(canonicalOptionKey(payload));
      const targetId = businessReviewSession?.reselecting ? null : work.ruleId;
      const saved = existing || await runtime.request(token, (signal) => api.save(request, targetId, { signal }));
      if (!runtime.current(token)) return;
      if (work.mode === "ai") businessReviewSession?.saved.set(canonicalOptionKey(payload), saved);
      const detail = await runtime.request(token, (signal) => api.rule(saved.id, { signal }));
      if (!runtime.current(token)) return;
      if (existing && detail.content_sha256 !== work.preview.content_sha256) {
        throw new Error("已保存规则版本已变化，请到规则列表核实后继续。");
      }
      work.ruleId = Number(detail.id);
      work.detail = detail;
      if (work.mode === "ai") businessReviewSession?.saved.set(canonicalOptionKey(payload), detail);
      work.evidence = null;
      work.readOnly = false;
      if (work.options.length) {
        const state = work.optionWork[work.activeOptionId];
        if (state) {
          state.definition = payload;
          state.saved = detail;
          state.candidate = { ...state.candidate, ...(detail.definition || {}) };
        }
      }
      if (work.revision === revision) {
        const columns = page.form.metadataColumns();
        page.form.reset(detail);
        if (work.mode === "ai" && work.analysisInput) restoreAnalysisInput(work.analysisInput);
        page.form.setSources();
        page.form.setMetadata({ columns, mapping_version: payload.mapping_version });
        work.revision = 0;
        notify("草稿已保存，已读取真实 SQL；可继续测试或关闭后从列表继续", "success");
      } else notify("草稿已保存；之后修改的表单内容仍未保存，请再次保存", "warning");
      work.busy = false;
      page.form.setBusy(false);
      render();
      await onChanged?.();
    } catch (error) {
      if (runtime.current(token)) {
        work.busy = false;
        page.form.setBusy(false);
        render();
      }
      throw error;
    }
  }

  function previewTestTargets() {
    if (!work.options.length) return [work];
    const ids = new Set(work.selectedOptions);
    if (work.optionWork[work.expandedOptionId]?.preview?.sql_preview) ids.add(work.expandedOptionId);
    return [...ids].map((id) => work.optionWork[id]).filter(Boolean);
  }

  function loadActiveTestState() {
    const active = work.optionWork[work.activeOptionId];
    if (!active) return;
    work.previewCases = active.previewCases;
    work.previewEvidence = active.previewEvidence;
  }

  function waitForTestPreparation(token) {
    return runtime.request(token, (signal) => new Promise((resolve, reject) => {
      const timer = runtime.setTimer(resolve, TEST_PREPARATION_MS);
      signal.addEventListener("abort", () => {
        runtime.clearTimer(timer);
        reject(signal.reason);
      }, { once: true });
    }));
  }

  async function runTests() {
    if (work.mode === "ai") {
      if (work.pendingOptionSave) return;
      if (work.testing || work.busy || work.previewBusy || work.aiLoading || work.optionsSaving || work.confirmBusy
          || work.readOnly || !hasCapability(user, "dv.test")) return;
      const targets = previewTestTargets();
      if (!targets.length || targets.some((target) => !target.preview?.sql_preview) || analysisStale()) {
        throw new Error("请先完成所选方案的 SQL 预览");
      }
      const token = runtime.next("workbench-test");
      const snapshot = inputSignature();
      work.testing = true;
      work.preparingTests = true;
      targets.forEach((target) => { target.previewEvidence = null; });
      loadActiveTestState();
      render();
      scrollToSection(page.testingSection);
      try {
        await waitForTestPreparation(token);
        if (!runtime.current(token) || inputSignature() !== snapshot) return;
        targets.forEach((target) => { target.previewCases ??= target.preview.cases || []; });
        loadActiveTestState();
        const results = await Promise.allSettled(targets.map((target) => {
          const preview = target.preview;
          return runtime.request(token, (signal) => api.testCandidate({ definition: preview.definition,
            expected_hash: preview.content_sha256, cases: target.previewCases }, { signal }));
        }));
        if (!runtime.current(token) || inputSignature() !== snapshot) return;
        results.forEach((result, index) => {
          const target = targets[index];
          if (result.status === "fulfilled" && result.value.content_sha256 === target.preview.content_sha256) {
            target.previewEvidence = result.value;
            return;
          }
          const issue = result.status === "rejected" ? errorMessage(result.reason, "测试请求失败") : "测试结果与当前规则不一致";
          notify(`${target.preview.definition.name || "当前方案"}：${issue}，请重新运行测试`, "error");
        });
      } finally {
        if (runtime.current(token)) {
          work.testing = false;
          work.preparingTests = false;
          loadActiveTestState();
          render();
        }
      }
      return;
    }
    if (!work.detail) throw new Error("请先保存草稿并读取详情");
    if (savedAiNeedsReview()) throw new Error("请先确认全部业务口径并保存当前版本，再运行测试");
    if (page.form.isDirty()) throw new Error("请先保存当前修改，再测试服务端版本");
    const detail = work.detail;
    const token = runtime.next("workbench-test");
    work.testing = true;
    render();
    try {
      const result = await runtime.request(token, (signal) => api.test(detail.id, { version_no: detail.version_no }, { signal }));
      if (!runtime.current(token) || work.detail?.content_sha256 !== detail.content_sha256) return;
      work.evidence = createTestEvidence(detail, result);
      work.testing = false;
      render();
      notify(`真实测试返回：通过 ${result.passed_count}，失败 ${result.failed_count}`, result.failed_count ? "error" : "success");
    } catch (error) {
      if (runtime.current(token)) {
        work.testing = false;
        render();
      }
      throw error;
    }
  }

  async function confirmFromPage() {
    if (work.mode === "ai" && work.options.length) return saveSelectedOptionsAndEnable();
    if (work.mode === "ai") {
      const readiness = previewReadiness(work.preview, work.previewEvidence, analysisStale() || work.previewBusy);
      if (!readiness.ready) { notify(readiness.reasons.join("；"), "warning"); return; }
      const digest = work.preview.content_sha256;
      const accepted = await confirmAction?.("保存并启用这条规则？系统会保存真实版本，并在后端重新运行你检查的测试用例；全部通过才启用，不会自动执行校验任务。");
      if (accepted === false) return;
      if (analysisStale() || work.preview?.content_sha256 !== digest || !work.previewEvidence) throw new Error("规则已修改，请重新运行测试");
      const token = runtime.next("workbench-confirm");
      work.confirmBusy = true; render();
      try {
        const existing = businessReviewSession?.saved.get(canonicalOptionKey(work.preview.definition));
        const targetId = businessReviewSession?.reselecting ? null : work.ruleId;
        const saved = existing || await runtime.request(token, (signal) => api.save(work.preview.definition, targetId, { signal }));
        if (!runtime.current(token)) return;
        businessReviewSession?.saved.set(canonicalOptionKey(work.preview.definition), saved);
        const detail = await runtime.request(token, (signal) => api.rule(saved.id, { signal }));
        if (!runtime.current(token)) return;
        if (existing && detail.content_sha256 !== digest) throw new Error("已保存规则版本已变化，请到规则列表核实后继续。");
        work.ruleId = Number(detail.id); work.detail = detail;
        const result = await runtime.request(token, (signal) => api.test(detail.id, { version_no: detail.version_no, cases: work.previewCases }, { signal }));
        if (!runtime.current(token)) return;
        const storedEvidence = createTestEvidence(detail, result);
        const checked = confirmationReadiness(detail, storedEvidence, false);
        if (!checked.ready) throw new Error(`已保留为草稿，暂未启用：${checked.reasons.join("；")}`);
        await runtime.request(token, (signal) => api.confirm(detail.id, { version_no: detail.version_no, expected_hash: detail.content_sha256 }, { signal }));
        if (!runtime.current(token)) return;
        notify("规则已保存并启用，当前保存版本的测试已全部通过；未自动执行校验任务", "success");
        await onChanged?.(); close();
      } catch (error) {
        if (runtime.current(token)) { work.confirmBusy = false; render(); await onChanged?.(); }
        throw error;
      }
      return;
    }
    if (!work.detail) {
      notify("请先保存草稿并运行测试", "error");
      return;
    }
    const readiness = confirmationReadiness(work.detail, work.evidence, page.form.isDirty());
    if (!readiness.ready) {
      notify(readiness.reasons.join("；"), "error");
      return;
    }
    const accepted = await confirmAction?.(
      `确认启用规则「${work.detail.name}」版本 v${work.detail.version_no}？`
      + `测试通过 ${Number(work.evidence?.passed_count) || 0} 条、失败 0 条；启用后不会自动创建校验任务。`,
    );
    if (accepted === false) return;
    await confirmCurrent();
  }

  async function confirmCurrent() {
    const detail = work.detail;
    const token = runtime.next("workbench-confirm");
    work.confirmBusy = true;
    render();
    try {
      await runtime.request(token, (signal) => api.confirm(detail.id, {
        version_no: detail.version_no,
        expected_hash: detail.content_sha256,
      }, { signal }));
      if (!runtime.current(token)) return;
      notify("规则已确认启用；未自动创建校验任务", "success");
      await onChanged?.();
      close();
    } catch (error) {
      if (runtime.current(token)) {
        work.confirmBusy = false;
        render();
      }
      throw error;
    }
  }

  function viewModel() {
    const hideSavedSql = work.mode === "manual" && savedAiNeedsReview();
    return {
      detail: hideSavedSql ? null : work.detail,
      evidence: work.mode === "ai" ? work.previewEvidence : hideSavedSql ? null : work.evidence,
      dirty: page.form.isDirty(),
      preview: work.mode === "ai" ? work.preview : null,
      previewCases: work.previewCases || [], columns: page.form.metadataColumns(), relatedColumns: page.form.relatedColumns(),
      stale: work.mode === "ai" && analysisStale(),
      canTest: hasCapability(user, "dv.test"),
      readOnly: work.readOnly,
      busy: work.busy || work.confirmBusy || work.previewBusy || Boolean(work.pendingOptionSave),
      testing: work.testing,
    };
  }

  function saveReadiness() {
    try {
      definitionForSave();
      return { ready: true, reason: "" };
    } catch (error) {
      return { ready: false, reason: error?.message || String(error) };
    }
  }

  function scrollToSection(section) {
    section?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  function render() {
    if (!page || !dialog) return;
    if (deferredSupplements.length && !businessReview && !work.aiLoading && work.preview?.sql_preview && !analysisStale()) {
      appendSupplementCards(deferredSupplements.splice(0));
      return;
    }
    const editing = page.editor?.contains?.(document.activeElement) ? document.activeElement : null;
    const question = work.candidate?.questions?.[0];
    const stale = work.mode === "ai" && Boolean(work.candidate) && analysisStale();
    page.businessQuestions?.update(businessReview?.items, { busy: work.previewBusy || work.aiLoading });
    if (page.businessQuestions) {
      const showBusinessQuestions = !stale && Boolean(businessReview?.items.length);
      page.businessQuestions.setVisible(showBusinessQuestions);
      page.saveNote.hidden = showBusinessQuestions;
    }
    const last = !stale && readScopeChoice(user?.id, work.candidate, question);
    const lastChoice = last ? { id: question.id, value: last.selection } : null;
    if (!question || work.selectedChoice?.id !== question.id) work.selectedChoice = lastChoice;
    if (work.options.length && work.candidate && !work.loadingOption) syncActiveOptionState();
    page.candidate?.update(work.candidate, page.form.read(), { loading: work.aiLoading || work.previewBusy, error: work.aiError,
      stale, preview: work.preview, selectedChoice: work.selectedChoice, lastChoice, locked: Boolean(work.pendingOptionSave),
      canRecheck: canRequestPreview(work.candidate), option: work.options.find((item) => item.id === work.activeOptionId) });
    if (work.mode === "ai" && page.optionsPanel) {
      page.optionsPanel.update(
        { candidate_options: work.options.map((item) => ({ ...item, candidate: work.optionWork[item.id]?.candidate || item.candidate })),
          parallel_checks: work.options.some((item) => item.candidate?.parallel_check),
          comparison_suggestions: [] },
        {
          selected: work.selectedOptions, activeId: work.expandedOptionId,
          savedRules: work.savedOptionRules, saving: work.optionsSaving,
          locked: Boolean(work.busy || work.optionsSaving || work.testing || work.pendingOptionSave),
          gates: Object.fromEntries(work.options.map((option) => [option.id, optionGate(option.id)])),
          savedDuplicate: work.options.length > 0 && work.selectedOptions.length > 0
            && work.options.filter((option) => work.selectedOptions.includes(option.id)).every((option) => {
              const state = work.optionWork[option.id];
              return state.saved && state.savedCanonical === canonicalOptionKey(canonicalOptionDefinition(state));
            }),
          hideSave: work.options.length > 0,
        },
      );
      renderSuggestions();
    }
    const isAi = work.mode === "ai";
    const multi = isAi && work.options.length > 0;
    const targets = isAi ? previewTestTargets() : [];
    const caseItems = multi ? targets.flatMap((target) => (target.previewEvidence?.cases || target.previewCases || [])
      .map((item, index) => ({ item, index, target, columns: target.candidate.columns || [],
        relatedColumns: target.candidate.related_columns || [] }))) : null;
    const model = viewModel();
    const testReadiness = page.tests.update({ ...model, caseItems });
    const gate = multi ? selectedOptionGate() : null;
    const readiness = gate ? { ready: gate.enabled, reasons: gate.reasons } : testReadiness;
    const busy = work.busy || work.testing || work.confirmBusy || work.previewBusy || work.aiLoading || work.optionsSaving;
    if (page.reselectBusiness) {
      page.reselectBusiness.hidden = !canReselectBusinessQuestions();
      page.reselectBusiness.disabled = busy || work.preparingTests || Boolean(work.pendingOptionSave) || work.readOnly || !hasCapability(user, "dv.ai_use");
    }
    page.form.lockGroup(busy || Boolean(work.pendingOptionSave) || work.readOnly);

    const configVisible = isAi ? Boolean(work.candidate || work.options.length) : page.form.metadataColumns().length > 0;
    const readyToTest = targets.length > 0 && targets.every((target) => target.preview?.sql_preview);
    const testingVisible = isAi
      ? !model.stale && model.canTest && !work.readOnly && readyToTest
      : Boolean(model.detail);
    page.configSection.hidden = !configVisible;
    page.testingSection.hidden = !testingVisible;

    if (isAi) {
      const generatedCaseCount = targets.reduce((total, target) => total + (target.previewEvidence?.cases || target.previewCases || []).length, 0);
      page.testTitle.hidden = work.preparingTests || generatedCaseCount === 0;
      page.testCount.hidden = page.testTitle.hidden;
      page.testCount.textContent = `${generatedCaseCount} 个场景`;
      const hasNewCases = targets.some((target) => target.previewCases === null);
      const testsUncheckedCurrent = multi && targets.length > work.selectedOptions.length;
      const testScope = testsUncheckedCurrent
        ? (work.selectedOptions.length ? "当前及所选方案" : "当前方案") : "所选方案";
      page.testLaunch.hidden = false;
      page.testLaunch.disabled = busy || Boolean(work.pendingOptionSave) || !readyToTest;
      page.testLaunchLabel.textContent = work.preparingTests ? "正在生成并运行…"
        : hasNewCases && !testsUncheckedCurrent ? "生成并运行测试用例" : multi ? `运行${testScope}测试` : "重新运行测试";
      page.testLaunch.setAttribute("aria-label", page.testLaunchLabel.textContent);
      page.testLaunch.title = !readyToTest ? "请先完成所选方案的 SQL 预览"
        : multi ? `测试${testScope}（${targets.length} 个）` : "运行当前方案的合成样本";
      page.testPreparing.hidden = !work.preparingTests;
      page.tests.element.hidden = work.preparingTests || (multi ? !targets.some((target) => target.previewCases !== null) : work.previewCases === null);
      const collapsed = work.descriptionCollapsed || work.aiLoading;
      page.collapsedBar.hidden = !collapsed || work.aiLoading;
      page.form.groups.aiContext.hidden = work.aiLoading;
      page.form.groups.aiInput.hidden = collapsed;
      page.waitRequest.hidden = !work.aiLoading;
      dialog?.dialog.classList.toggle("is-ai-waiting", work.aiLoading);
      page.editRequest.hidden = !collapsed || work.aiLoading;
      page.editRequest.disabled = busy || Boolean(work.pendingOptionSave);
      page.form.setRequestEditing(Boolean(work.candidate));
      const question = work.candidate?.questions?.[0];
      page.choiceContinue.hidden = !question || stale || (multi && !work.expandedOptionId);
      page.choiceContinue.disabled = busy || Boolean(work.pendingOptionSave) || analysisStale() || work.selectedChoice?.id !== question?.id
        || (Array.isArray(work.selectedChoice?.value) && !work.selectedChoice.value.length);
      page.editor.hidden = !isGrouped(work.candidate?.expression) || Boolean(question) || stale;
      const { request_text, source_id, model_id } = page.form.read();
      page.collapsedText.textContent = request_text || "—";
      if (work.aiLoading) {
        page.waitRequestText.textContent = request_text || "—";
        page.waitSource.textContent = state.sources.find((item) => String(item.id) === source_id)?.name || "未选择";
        page.waitModel.textContent = state.models.find((item) => String(item.id) === model_id)?.name || "未选择";
      }
      page.form.setAnalyzing(work.aiLoading);
      page.form.lockInputs(busy || Boolean(work.pendingOptionSave));
      if (page.aiProgress) {
        const waiting = work.aiLoading || Boolean(work.aiError) || Boolean(work.analysisNote);
        page.aiProgress.hidden = !waiting;
        page.aiProgress.classList.toggle("is-loading", Boolean(work.aiLoading));
        page.aiProgress.classList.toggle("is-error", !work.aiLoading && Boolean(work.aiError));
        page.aiWaitBody.hidden = !work.aiLoading;
        page.aiProgressText.hidden = work.aiLoading;
        page.aiProgressText.textContent = work.aiLoading ? "" : (work.aiError || work.analysisNote);
        renderElapsed();
        renderAnalysisStage();
      }
    }

    if (configVisible && !lastConfigVisible) scrollToSection(isAi ? page.inputSection : page.configSection);
    if (!isAi && testingVisible && !lastTestingVisible) scrollToSection(page.testingSection);
    lastConfigVisible = configVisible;
    lastTestingVisible = testingVisible;

    const save = saveReadiness();
    page.saveButton.hidden = isAi;
    page.saveButton.disabled = busy || work.readOnly || !save.ready || !hasCapability(user, "dv.manage");
    if (isAi && page.footerBulk) {
      const multi = work.options.length > 0;
      page.footerBulk.hidden = true;
      page.footerBulk.disabled = busy || work.readOnly || !hasCapability(user, "dv.manage") || analysisStale() || !readyToTest
        || work.options.filter((option) => work.selectedOptions.includes(option.id)).every((option) => {
          const state = work.optionWork[option.id];
          return state.saved && state.savedCanonical === canonicalOptionKey(canonicalOptionDefinition(state));
        });
      page.footerBulk.textContent = `保存所选 ${work.selectedOptions.length} 条草稿`;
    }
    page.saveButton.textContent = work.busy ? "保存中…" : "保存草稿";
    page.saveButton.title = save.ready ? "保存草稿；之后可继续测试" : save.reason;
    page.saveHint.textContent = save.ready
      ? (isAi ? "可先运行测试，再决定保存或启用" : "保存草稿后可运行测试；也可以只保存草稿后关闭")
      : save.reason;
    if (isAi) page.saveHint.textContent = work.aiLoading
      ? "分析与预览测试仅检索文档元数据，不会读取业务数据或直接创建规则"
      : !work.candidate ? "分析和预览测试不会创建规则"
        : stale ? "应用修改后可预览" : work.preview ? "测试通过后可保存并启用" : "全部业务口径确认后生成 SQL";
    page.saveHint.classList.toggle("is-error", !isAi && !save.ready);

    page.confirmButton.hidden = isAi && (stale || (!multi && !work.preview));
    page.confirmButton.textContent = isAi ? (multi ? `保存并启动以上${gate.selected.length}个方案` : "保存并启用") : "确认启用";
    page.confirmButton.disabled = busy || work.readOnly || !readiness.ready || (isAi && !hasCapability(user, "dv.manage"));
    page.confirmButton.title = readiness.ready ? "确认固化并启用当前版本" : readiness.reasons.join("；");
    if (multi && !page.confirmButton.hidden && !busy) {
      page.saveHint.textContent = work.pendingOptionSave ? "保存结果待确认，请再次点击保存按钮核实"
        : readiness.ready ? `所选 ${gate.selected.length} 个方案的测试已全部通过` : readiness.reasons[0];
    }
    page.verifyHint.textContent = readiness.ready
      ? (isAi ? "样本测试已通过，可保存并启用；启动时会重新核验保存版本" : "测试已通过：可确认启用，或只保存草稿后关闭弹窗")
      : readiness.reasons.join("；");
    page.verifyHint.classList.toggle("is-success", readiness.ready);
    page.verifyHint.classList.toggle("is-error", !readiness.ready && Boolean(readiness.reasons.length));

    if (page.switchButton) {
      const modelUnavailable = state.modelsStatus === "error" || !state.models.length;
      page.switchButton.hidden = !work.aiError && !modelUnavailable;
    }
    if (footerButton) {
      const run = activeAnalysis;
      footerButton.textContent = run ? (run.stopError ? "重试结束会话" : run.ending ? "正在结束…" : "结束会话")
        : work.detail ? "关闭" : "取消";
      footerButton.classList.toggle("dv-button-danger", Boolean(run));
      footerButton.setAttribute("aria-label", footerButton.textContent);
      footerButton.disabled = Boolean(run?.ending && !run.stopError)
        || work.busy || work.testing || work.confirmBusy || work.previewBusy;
    }
    if (dialog) dialog.closeButton.disabled = Boolean(activeAnalysis?.ending)
      || work.busy || work.testing || work.confirmBusy || work.previewBusy;
    dialog?.setTitle(work.ruleId
      ? `${work.readOnly ? "查看" : "编辑、测试与确认"} ${work.detail?.rule_code || "规则"}`
      : supplementTitle ? `AI 补充规则 · ${supplementTitle}` : work.mode === "ai" ? "AI 新建校验规则" : "新建校验规则");
    mountOptionDetail();
    returnSupplementWhenReady();
    if (businessReview && !businessReview.retry && !stale && !work.previewBusy) page.detailHome.hidden = true;
    if (editing?.isConnected && document.activeElement !== editing) editing.focus({ preventScroll: true });
    return readiness;
  }

  function close() {
    if (dialog) dialog.close();
    else invalidate();
  }

  return {
    get element() { return dialog?.dialog || (page ? page.root : null); },
    open,
    close,
    cancel: close,
    refreshSources() {
      if (!work.aiLoading) stopElapsed();
      page?.form.setSources();
      page?.form.setCategories();
      if (work.mode === "ai") page?.form.setModels();
      render();
    },
    isOpen: () => Boolean(dialog),
  };
}
