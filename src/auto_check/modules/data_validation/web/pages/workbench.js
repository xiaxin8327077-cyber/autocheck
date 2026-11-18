import { errorMessage } from "../runtime.js";
import { createTestEvidence, confirmationReadiness, previewReadiness, ruleScopeIssues, hasCapability, ownsResource } from "../state.js";
import { createAiCandidatePanel } from "../components/ai_candidate.js";
import { createCandidateOptionsPanel, createRequestKeyRegistry } from "../components/candidate_options.js";
import { createDialog } from "../components/dialog.js";
import { button, element } from "../components/dom.js";
import { createRuleForm } from "../components/rule_form.js";
import { createTestPanel } from "../components/test_panel.js";
import { aiMark, aiIcon } from "../components/ai_visuals.js";
import { readScopeChoice, rememberScopeChoice } from "../components/scope_choice_memory.js";

const CHANNELS = ["workbench-detail", "workbench-metadata", "workbench-ai", "workbench-save", "workbench-test", "workbench-confirm", "workbench-preview"];
const ANALYSIS_POLL_MS = 900;
const ANALYSIS_STEPS = [
  { id: "semantics", label: "解析业务语义与逻辑" },
  { id: "metadata", label: "检索数据字典与表结构说明" },
  { id: "generation", label: "生成校验规则与 SQL 预览" },
];

export function createWorkbench({
  state, runtime, api, listen, user, notify, host, confirmAction,
  onClose, onChanged, onRetrySources, onRetryModels,
}) {
  const work = {
    mode: "manual", ruleId: null, detail: null, evidence: null, candidate: null,
    revision: 0, readOnly: false, busy: false, aiLoading: false, aiError: "", aiElapsed: 0, testing: false,
    confirmBusy: false, descriptionCollapsed: false,
    preview: null, previewCases: [], previewEvidence: null, analysisInput: "", previewBusy: false, selectedChoice: null,
    analysis: null, analysisId: null, analysisToken: null, analysisNote: "", analysisSourceId: "", analysisModelId: "",
    cancelRequested: false,
    options: [], selectedOptions: [], activeOptionId: "", expandedOptionId: "", optionWork: {}, comparisonSuggestions: [], aiSuggestions: [],
    requestKeyRegistry: null, savedOptionRules: [], optionsSaving: false,
  };
  let dialog = null;
  let footerButton = null;
  let page = null;
  let lastConfigVisible = false;
  let lastTestingVisible = false;
  let elapsedTimer = null;
  let analysisTimer = null;
  let analyzeStartedAt = 0;

  // 单页结构：① 需求输入（始终显示，AI 分析成功后折叠为一行）→ ② 校验属性与 AI 结果 → ③ 测试与启用。
  // ②③ 初始隐藏，随用户操作逐步出现，不使用步骤条。
  function buildPage(mode) {
    const isAi = mode === "ai";
    const form = createRuleForm({
      state, mode, listen, user,
      onChange: () => {
        work.revision += 1;
        work.aiError = "";
        if (work.mode === "ai" && work.analysisInput && analysisStale()) {
          work.previewEvidence = null;
          work.previewCases = work.previewCases.map((item) => ({ ...item, status: "not_run", actual_count: null }));
          runtime.invalidate("workbench-test"); runtime.invalidate("workbench-preview");
          work.testing = false; work.previewBusy = false;
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
    const candidate = isAi ? createAiCandidatePanel({ listen, onEdit: expandDescription, onRetry: () => applyDecision(), notify,
      onChoice: (id, value) => { work.selectedChoice = { id, value }; render(); page?.candidate.focusSelected(); },
    }) : null;
    const switchButton = isAi
      ? button("转手工继续", { listen, className: "dv-button dv-button-plain", onClick: () => switchToManual() })
      : null;
    const tests = createTestPanel({ listen, onTest: runTests, onCaseChange: changeCase, onDecision: applyDecision, showSql: !isAi });
    const saveButton = button("保存草稿", { listen, className: "dv-button", onClick: () => saveDraft() });
    const footerBulk = isAi
      ? button("保存所选 0 条草稿", { listen, className: "dv-button", onClick: () => saveSelectedOptions() })
      : null;
    const confirmButton = button(isAi ? "保存并启用" : "确认启用", {
      listen, className: "dv-button dv-button-primary", capability: "dv.confirm",
      onClick: () => confirmFromPage(),
    });
    const saveHint = element("span", { className: "dv-inline-status" });
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
    const choiceContinue = isAi ? button("按此口径继续分析", { listen, className: "dv-button dv-button-primary", capability: "dv.ai_use",
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
    const configBody = isAi
      ? element("div", { className: "dv-ai-result" }, optionsPanel.element, candidate.element)
      : form.groups.config;
    const detailHome = isAi ? configBody : null;
    const configSection = element("section", {
      className: "dv-page-section dv-config-section", hidden: true,
    },
      element("div", { className: "dv-page-section-heading" }, element("h2", { text: isAi ? "分析结论" : "校验属性与配置" })),
      configBody,
      isAi ? null : element("div", { className: "dv-verify-actions" }, saveButton, saveHint));

    const testingSection = element("section", {
      className: "dv-page-section dv-testing-section", hidden: true,
    },
      element("div", { className: "dv-page-section-heading" }, element("h2", { text: isAi ? "测试用例" : "测试与启用" })),
      tests.element,
      isAi ? element("p", { className: "dv-ai-verify-hint" }, verifyHint) : element("div", { className: "dv-confirm-actions" }, confirmButton, verifyHint));

    const suggestionsList = element("div", { className: "dv-ai-supplement-list" });
    const suggestionsSection = isAi
      ? element("section", { className: "dv-ai-supplements", hidden: true },
        element("h3", { className: "dv-ai-supplement-title", text: "AI补充建议" }), suggestionsList)
      : null;
    const root = element("section", { className: "dv-workbench dv-workbench-modal-content dv-single-page" },
      inputSection, aiProgress, configSection, suggestionsSection, testingSection);
    const scene = {
      suggestionsSection, suggestionsList,
      form, candidate, optionsPanel, detailHome, switchButton, tests, saveButton, footerBulk, confirmButton, saveHint, verifyHint,
      collapsedText, collapsedBar, waitRequest, waitRequestText, waitSource, waitModel,
      aiProgress, aiWaitBody, aiWaitTimer, aiWaitStage, aiProgressText, aiProgressNote,
      inputSection, configSection, testingSection, root, editRequest, choiceContinue,
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
    const slow = work.aiLoading && work.aiElapsed >= 30;
    if (page.aiProgressNote.hidden === slow) {
      page.aiProgressNote.hidden = !slow;
      page.aiProgressNote.textContent = slow ? "模型响应较慢，仍在等待返回，请勿重复提交。" : "";
    }
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
    return JSON.stringify([context.source_id, context.request_text, context.model_id]);
  }

  function analysisStale() {
    return !work.analysisInput || inputSignature() !== work.analysisInput;
  }

  function changeCase(index, expected) {
    if (!work.preview || work.testing || work.previewBusy || ![0, 1].includes(expected)) return;
    work.previewCases = work.previewCases.map((item, offset) => ({ ...item,
      expected_count: offset === index ? expected : item.expected_count, status: "not_run", actual_count: null }));
    work.previewEvidence = null;
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
      state.definition = null; state.selectedChoice = null; state.preview = null; state.previewCases = []; state.previewEvidence = null;
    }
  }

  async function applyDecision(key, value) {
    if (work.busy || work.previewBusy || work.aiLoading || analysisStale()) return;
    const token = runtime.next("workbench-preview");
    const snapshot = inputSignature();
    const pendingQuestions = work.candidate?.questions || [];
    work.previewBusy = true; work.preview = null; work.previewEvidence = null; work.previewCases = [];
    try {
      const question = pendingQuestions.find((item) => item.id === key);
      if (key) {
        page.form.applyDecision(key, value, question);
        rememberScopeChoice(user?.id, work.candidate, question, value);
      }
      const definition = page.form.read();
      shareParallelScope(question, definition);
      work.candidate = { ...work.candidate, ...definition, preview: null,
        preview_error: work.candidate?.parallel_blocked || "", questions: pendingQuestions.filter((item) => item.id !== key) };
      if (work.candidate.questions.length || work.candidate.parallel_blocked) { work.previewBusy = false; if (work.options.length) syncActiveOptionState(); render(); return; }
      render();
      const preview = await runtime.request(token, (signal) => api.preview({ definition: page.form.read() }, { signal }));
      if (!runtime.current(token) || inputSignature() !== snapshot) return;
      const previousQuestions = (work.candidate?.questions || []).filter((item) => item.id !== key);
      const backendQuestions = Array.isArray(preview.questions) ? preview.questions : [];
      const mergedQuestions = mergeQuestions(backendQuestions, previousQuestions);
      page.form.setMetadata({
        columns: preview.columns || work.candidate?.columns || [],
        related_columns: preview.related_columns || work.candidate?.related_columns || [],
        project_columns: preview.project_columns || null,
        project_table: preview.project_table || null,
        mapping_version: preview.mapping_version || work.candidate?.mapping_version || "",
      });
      work.preview = preview; work.previewCases = preview.cases || [];
      work.descriptionCollapsed = true;
      work.candidate = {
        ...work.candidate, ...preview.definition,
        columns: preview.columns || work.candidate?.columns,
        related_columns: preview.related_columns || work.candidate?.related_columns,
        project_columns: preview.project_columns || work.candidate?.project_columns,
        project_table: preview.project_table || work.candidate?.project_table,
        rule_name: preview.definition.name, preview,
        questions: mergedQuestions,
      };
      work.previewBusy = false;
      if (work.options.length) syncActiveOptionState();
      render();
    } catch (error) {
      if (runtime.current(token)) {
        work.previewBusy = false;
        work.candidate = { ...work.candidate, preview: null, questions: pendingQuestions,
          preview_error: `${errorMessage(error)}。已选口径和分析结果已保留，可重试生成预览，无需重新调用 AI。` };
        if (work.options.length) syncActiveOptionState();
        render();
      }
    }
  }

  function invalidateAnalysisToken() {
    if (work.analysisToken) runtime.invalidate(work.analysisToken.channel);
    work.analysisToken = null;
  }

  function bestEffortCancelAnalysis() {
    const analysisId = work.analysisId;
    work.analysisId = null;
    work.cancelRequested = true;
    invalidateAnalysisToken();
    stopAnalysisPolling();
    if (analysisId) {
      try {
        void Promise.resolve(api.cancelAnalysis(analysisId)).catch(() => {});
      } catch {
        // 尽力标记，不暗示上游已立即停止。
      }
    }
  }

  function invalidate() {
    bestEffortCancelAnalysis();
    CHANNELS.forEach((channel) => runtime.invalidate(channel));
  }

  function cancelDescriptionEdit() {
    if (!work.candidate || !work.analysisInput || work.aiLoading || work.busy || work.testing || work.confirmBusy || work.previewBusy) return;
    page.form.restoreInput(work.analysisInput);
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

  async function open({ mode = "manual", ruleId = null, seed = null } = {}) {
    invalidate();
    dialog?.close();
    Object.assign(work, {
      mode: mode === "ai" ? "ai" : "manual", ruleId: ruleId || null, detail: null, evidence: null, candidate: null,
      revision: 0, readOnly: false, busy: false, aiLoading: false, aiError: "", aiElapsed: 0, testing: false,
      confirmBusy: false, descriptionCollapsed: false,
      preview: null, previewCases: [], previewEvidence: null, analysisInput: "", previewBusy: false, selectedChoice: null,
      options: [], selectedOptions: [], activeOptionId: "", expandedOptionId: "", optionWork: {}, comparisonSuggestions: [], aiSuggestions: [],
      requestKeyRegistry: null, savedOptionRules: [], optionsSaving: false,
    });
    stopElapsed();
    lastConfigVisible = false;
    lastTestingVisible = false;
    page = buildPage(work.mode);
    page.form.reset(null, seed);
    page.form.setSources();
    page.form.setCategories();
    if (work.mode === "ai") page.form.setModels();
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
        cancelWaiting();
        return;
      }
      close();
    });
    if (work.mode === "ai") dialog.footer.append(element("div", { className: "dv-ai-footer-note" }, aiIcon("lock"), page.saveHint), element("div", { className: "dv-ai-footer-actions" }, footerButton, page.footerBulk, page.saveButton, page.confirmButton, page.choiceContinue));
    else dialog.footer.append(footerButton);
    dialog.body.append(page.root);
    render();
    if (ruleId) await loadDetail(ruleId);
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
    const current = work.aiLoading && steps.find((step) => step.status === "running");
    const stage = current && ANALYSIS_STEPS.find((step) => step.id === current.id);
    const announcement = stage ? [stage.label, current.detail, current.table_name,
      Number.isInteger(current.field_count) ? `字段 ${current.field_count}` : ""].filter(Boolean).join("，") : "";
    if (page.aiWaitStage.textContent !== announcement) page.aiWaitStage.textContent = announcement;
  }

  function setupMultiOptions(result) {
    work.options = result.candidate_options;
    if (work.options.some((item) => item.candidate?.parallel_check)) work.descriptionCollapsed = true;
    work.comparisonSuggestions = Array.isArray(result.comparison_suggestions) ? result.comparison_suggestions : [];
    work.selectedOptions = work.options.filter((item) => item.recommended).map((item) => item.id);
    if (!work.selectedOptions.length) work.selectedOptions = [work.options[0].id];
    work.activeOptionId = work.selectedOptions[0] || work.options[0].id;
    work.expandedOptionId = work.activeOptionId;
    work.requestKeyRegistry = createRequestKeyRegistry();
    work.savedOptionRules = [];
    work.optionsSaving = false;
    work.optionWork = {};
    const signature = inputSignature();
    work.options.forEach((option) => {
      const candidate = option.candidate || {};
      work.optionWork[option.id] = {
        candidate, definition: null, selectedChoice: null,
        preview: candidate.preview || null, previewCases: candidate.preview?.cases || [],
        previewEvidence: null, analysisInput: signature, saved: null,
      };
    });
    work.candidate = null;
    work.preview = null; work.previewCases = []; work.previewEvidence = null;
    work.analysisInput = signature;
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
    if (!definition.rule_type || !definition.table_name || !definition.business_key || !definition.expression?.left) {
      return "缺少安全规则结构（规则类型/目标表/业务主键/表达式）";
    }
    if (state?.candidate?.parallel_check && !state.preview) return "请先完成该检查项的预览";
    if (Array.isArray(state?.candidate?.questions) && state.candidate.questions.length) {
      return "仍有待确认口径问题，需先在该方案内处理";
    }
    if (state?.saved && state.savedCanonical !== canonicalOptionKey(definition)) {
      return "该方案已保存且口径已修改，请在规则列表编辑原规则，避免重复创建";
    }
    return "";
  }

  function optionGate(id) {
    const state = work.optionWork[id];
    if (!state) return { enabled: false, reasons: ["缺少方案状态"] };
    const reasons = [];
    if (!hasCapability(user, "dv.manage") || !hasCapability(user, "dv.test") || !hasCapability(user, "dv.confirm")) {
      reasons.push("缺少管理/测试/确认权限");
    }
    if (work.busy || work.optionsSaving || work.testing || work.previewBusy || work.confirmBusy || work.aiLoading) reasons.push("当前有操作进行中");
    if (work.readOnly) reasons.push("当前为只读模式");
    if (analysisStale()) reasons.push("需求已修改，请重新分析");
    const definition = canonicalOptionDefinition(state);
    const key = canonicalOptionKey(definition);
    if (!definition || !definition.rule_type || !definition.table_name || !definition.business_key || !definition.expression?.left) {
      reasons.push("缺少安全规则结构");
    }
    if (Array.isArray(state.candidate?.questions) && state.candidate.questions.length) reasons.push("仍有待确认口径");
    if (state.saved && state.savedCanonical !== key) {
      reasons.push("该方案已保存且口径已修改，请在规则列表编辑后启用");
    } else {
      const preview = { definition, content_sha256: state.preview?.content_sha256 || state.previewEvidence?.content_sha256 || "" };
      const readiness = previewReadiness(preview, state.previewEvidence, analysisStale());
      if (!readiness.ready) reasons.push(...readiness.reasons);
    }
    return { enabled: reasons.length === 0, reasons };
  }

  function loadOptionIntoForm(id, { resetRevision = false } = {}) {
    const state = work.optionWork[id];
    if (!state) return;
    if (work.candidate) syncActiveOptionState();
    const candidate = state.definition ? { ...state.candidate, ...state.definition } : state.candidate;
    // applyCandidate emits onChange synchronously: do not save the new form into the previous option.
    work.loadingOption = true;
    try {
      page.form.setMetadata({
        columns: candidate?.columns || [], related_columns: candidate?.related_columns || [],
        mapping_version: candidate?.mapping_version || "",
      });
      page.form.applyCandidate(candidate || {}, { regenerate: !candidate.parallel_check });
    } finally {
      work.loadingOption = false;
    }
    work.activeOptionId = id;
    work.candidate = candidate || {};
    work.selectedChoice = state.selectedChoice;
    work.preview = state.preview; work.previewCases = state.previewCases; work.previewEvidence = state.previewEvidence;
    work.analysisInput = state.analysisInput || inputSignature();
    work.aiError = "";
    work.revision += 1;
    runtime.invalidate("workbench-preview");
    runtime.invalidate("workbench-test");
    runtime.invalidate("workbench-confirm");
    runtime.invalidate("workbench-save");
    work.previewBusy = false;
    work.testing = false;
    render();
  }

  function activateOption(id) {
    if (work.busy || work.optionsSaving) return;
    if (!work.optionWork[id] || id === work.activeOptionId) return;
    loadOptionIntoForm(id);
  }

  function unmountOptionDetail() {
    if (!page) return;
    if (page.candidate?.element?.parentNode !== page.detailHome) page.detailHome.append(page.candidate.element);
    if (page.tests?.element?.parentNode !== page.testingSection) page.testingSection.append(page.tests.element);
  }

  function mountOptionDetail() {
    if (!page || work.mode !== "ai" || !work.options.length) return;
    if (!work.expandedOptionId) {
      unmountOptionDetail();
      return;
    }
    const slot = page.optionsPanel?.getSlotEl(work.expandedOptionId);
    if (!slot) return;
    slot.hidden = false;
    slot.replaceChildren();
    slot.append(page.candidate.element, page.tests.element);
  }

  function toggleOptionCard(id) {
    if (work.busy || work.optionsSaving) return;
    if (!work.optionWork[id]) return;
    if (work.expandedOptionId === id) {
      work.expandedOptionId = "";
      unmountOptionDetail();
      render();
      return;
    }
    work.expandedOptionId = id;
    loadOptionIntoForm(id);
    if (work.candidate?.parallel_check && !work.candidate.parallel_blocked && !work.candidate.questions?.length && !work.preview) {
      return applyDecision();
    }
  }

  function toggleOption(id, checked) {
    if (work.busy || work.optionsSaving) return;
    const current = new Set(work.selectedOptions);
    if (checked) current.add(id); else current.delete(id);
    work.selectedOptions = [...current];
    work.requestKeyRegistry?.refresh();
    render();
  }

  async function saveSelectedOptions() {
    if (work.busy || work.optionsSaving || work.testing || work.previewBusy || work.confirmBusy || work.aiLoading) return;
    if (work.readOnly || !hasCapability(user, "dv.manage") || analysisStale()) {
      notify(analysisStale() ? "需求已修改，请重新分析后保存" : "当前无权保存规则", "warning");
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
    if (work.busy || work.optionsSaving) return;
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
        detail = await runtime.request(token, (signal) => api.rule(saved.id, { signal }));
      }
      if (!runtime.current(token)) return;
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

  function suggestionScopeReady() {
    return work.mode === "ai" && !work.aiLoading && !work.previewBusy && !work.aiError
      && !analysisStale() && Boolean(work.preview?.sql_preview && work.preview?.definition)
      && !work.candidate?.questions?.length && !work.preview.questions?.length
      && ruleScopeIssues(work.preview.definition).length === 0
      && ruleScopeIssues(work.candidate || {}).length === 0;
  }

  function renderSuggestions() {
    if (!page || !page.suggestionsSection) return;
    const table = String(work.candidate?.table_name || "").toLowerCase();
    const field = String(work.candidate?.expression?.left || "").toLowerCase();
    const list = table && field && suggestionScopeReady()
      ? work.aiSuggestions.filter((item) => item?.support_level === "supported" && Array.isArray(item.references)
          && item.references.some((ref) => String(ref?.table_name || "").toLowerCase() === table
            && String(ref?.field_name || "").toLowerCase() === field))
      : [];
    page.suggestionsSection.hidden = !list.length;
    page.suggestionsList.replaceChildren();
    list.forEach((item) => {
      const card = element("div", { className: "dv-ai-supplement" },
        element("div", { className: "dv-ai-supplement-head" },
          element("strong", { text: item.title || "补充建议" }),
          element("span", { className: "dv-ai-supplement-support is-supported", text: "可进一步检查" })));
      if (item.reason) card.append(element("div", { className: "dv-ai-supplement-reason", text: item.reason }));
      if (Array.isArray(item.references) && item.references.length) {
        card.append(element("div", { className: "dv-ai-supplement-refs", text: `证据：${item.references
          .map((ref) => `${ref.table_name || "—"}.${ref.field_name || "—"}`).join("；")}` }));
      }
      if (Array.isArray(item.preconditions) && item.preconditions.length) {
        card.append(element("div", { className: "dv-ai-supplement-pre", text: `待核实：${item.preconditions.join("；")}` }));
      }
      if (Array.isArray(item.limitations) && item.limitations.length) {
        card.append(element("ul", { className: "dv-ai-supplement-limits" },
          item.limitations.map((text) => element("li", { text }))));
      }
      page.suggestionsList.append(card);
    });
  }

  function mergeQuestions(primary, secondary) {
    const merged = [];
    const seen = new Set();
    [...(Array.isArray(primary) ? primary : []), ...(Array.isArray(secondary) ? secondary : [])].forEach((item) => {
      const id = String(item?.id || "");
      if (!id || seen.has(id)) return;
      seen.add(id);
      merged.push(item);
    });
    return merged;
  }

  function applyAnalysisResult(result) {
    if (!result) {
      work.aiError = "AI 分析未返回结果";
      render();
      return;
    }
    if (Array.isArray(result.candidate_options) && result.candidate_options.length > 1) {
      work.aiSuggestions = Array.isArray(result.ai_suggestions) ? result.ai_suggestions : [];
      setupMultiOptions(result);
      page.form.setBusy(work.busy);
      render();
      return;
    }
    work.candidate = result;
    work.aiSuggestions = Array.isArray(result.ai_suggestions) ? result.ai_suggestions : [];
    work.selectedChoice = null;
    work.analysisInput = inputSignature();
    work.preview = result.preview || null;
    work.previewCases = result.preview?.cases || [];
    work.previewEvidence = null;
    if (result.status === "needs_clarification") {
      page.form.applyCandidate(result);
      work.descriptionCollapsed = false;
      notify("请先澄清待确认口径或调整当前规则无法表达的要求，再重新生成", "warning");
    } else if (result.rule_type === "field_compare" && Array.isArray(result.columns)) {
      page.form.setMetadata({
        columns: result.columns, related_columns: result.related_columns || [],
        project_columns: result.project_columns || null, project_table: result.project_table || null,
        mapping_version: result.mapping_version,
      });
      page.form.applyCandidate(result);
      work.candidate = {
        ...work.candidate,
        project_columns: result.project_columns || work.candidate.project_columns,
        project_table: result.project_table || work.candidate.project_table,
        questions: mergeQuestions(result.preview?.questions, result.questions),
      };
      work.descriptionCollapsed = true;
    } else notify("当前仅支持 field_compare 候选编辑，其他类型不会伪装成可编辑规则", "warning");
    page.form.setBusy(work.busy);
    render();
  }

  function analysisFailure(snapshot) {
    work.aiLoading = false;
    stopElapsed();
    work.aiError = errorMessage({ payload: { error: snapshot?.error || {} } }, "AI 分析失败");
    render();
  }

  async function startAnalysisPolling(analysisId, token, revision) {
    stopAnalysisPolling();
    const tick = async () => {
      analysisTimer = null;
      if (!runtime.current(token) || work.analysisId !== analysisId || work.revision !== revision) return;
      let snapshot;
      try {
        snapshot = await runtime.request(token, (signal) => api.getAnalysis(analysisId, { signal }));
      } catch (error) {
        if (!runtime.current(token) || work.analysisId !== analysisId || work.revision !== revision) return;
        work.aiLoading = false;
        stopElapsed();
        work.aiError = errorMessage(error, "AI 分析失败");
        render();
        return;
      }
      if (!runtime.current(token) || work.analysisId !== analysisId || work.revision !== revision) return;
      work.analysis = snapshot;
      if (snapshot.status === "completed") {
        work.aiLoading = false;
        stopElapsed();
        render();
        applyAnalysisResult(snapshot.result);
        return;
      }
      if (snapshot.status === "cancelled") {
        work.aiLoading = false;
        stopElapsed();
        work.analysis = null;
        work.analysisNote = "已取消等待；正在进行的上游请求可能仍会结束，后续阶段将尽力停止。如需继续，请稍后重新分析。";
        render();
        return;
      }
      if (snapshot.status === "failed") {
        analysisFailure(snapshot);
        return;
      }
      render();
      analysisTimer = runtime.setTimer(tick, ANALYSIS_POLL_MS);
    };
    analysisTimer = runtime.setTimer(tick, ANALYSIS_POLL_MS);
  }

  async function cancelWaiting() {
    const analysisId = work.analysisId;
    work.cancelRequested = true;
    work.analysisId = null;
    invalidateAnalysisToken();
    stopAnalysisPolling();
    work.aiLoading = false;
    stopElapsed();
    work.analysis = null;
    work.analysisNote = "已取消等待；正在进行的上游请求可能仍会结束，后续阶段将尽力停止。如需继续，请稍后重新分析。";
    render();
    if (analysisId) {
      try {
        await api.cancelAnalysis(analysisId);
      } catch {
        // 尽力标记，不暗示上游已立即停止。
      }
    }
  }

  async function parse() {
    const context = page.form.read();
    if (!context.request_text) throw new Error("请先填写需求描述");
    if (!context.model_id) throw new Error(state.modelsStatus === "error" ? "模型加载失败，请转手工继续或重试" : "请选择可用模型，或转手工继续");
    if (!context.source_id || !context.dialect) throw new Error("请先选择有效数据源");
    page.form.validateForParse();
    const token = runtime.next("workbench-ai");
    const revision = work.revision;
    work.aiLoading = true;
    work.aiError = "";
    work.analysisNote = "";
    work.cancelRequested = false;
    stopAnalysisPolling();
    work.analysisId = null;
    work.analysisToken = null;
    work.analysis = {
      analysis_id: "", status: "running", elapsed_ms: 0,
      steps: ANALYSIS_STEPS.map((step, index) => ({ id: step.id, status: index === 0 ? "running" : "pending" })),
    };
    work.candidate = null;
    work.preview = null;
    work.previewEvidence = null;
    work.previewCases = [];
    work.selectedChoice = null;
    work.options = []; work.selectedOptions = []; work.activeOptionId = ""; work.expandedOptionId = ""; work.optionWork = {};
    work.comparisonSuggestions = []; work.aiSuggestions = []; work.savedOptionRules = []; work.optionsSaving = false;
    work.analysisSourceId = context.source_id;
    work.analysisModelId = context.model_id;
    startElapsed();
    page.form.setBusy(true);
    render();
    try {
      // 新 UI 走分析任务：只提交需求、模型与数据源；表清单、真实表结构与监管报送分类由后端读取或选定。
      const snapshot = await runtime.request(token, (signal) => api.createAnalysis({
        request_text: context.request_text,
        model_id: context.model_id,
        source_id: context.source_id,
      }, { signal }));
      if (snapshot?.analysis_id && work.cancelRequested) {
        const lateId = snapshot.analysis_id;
        work.cancelRequested = false;
        try {
          await api.cancelAnalysis(lateId);
        } catch {
          // 尽力标记。
        }
        return;
      }
      if (!runtime.current(token) || work.revision !== revision) {
        if (snapshot?.analysis_id) {
          const lateId = snapshot.analysis_id;
          try {
            await api.cancelAnalysis(lateId);
          } catch {
            // 迟到响应：尽力删除，不覆盖已关闭/修改后的状态。
          }
        }
        return;
      }
      work.analysis = snapshot;
      work.analysisId = snapshot.analysis_id;
      work.analysisToken = token;
      if (snapshot.status === "completed") {
        work.aiLoading = false;
        stopElapsed();
        render();
        applyAnalysisResult(snapshot.result);
        return;
      }
      if (snapshot.status === "failed") {
        analysisFailure(snapshot);
        return;
      }
      if (snapshot.status === "cancelled") {
        work.aiLoading = false;
        stopElapsed();
        work.analysis = null;
        work.analysisNote = "已取消等待；正在进行的上游请求可能仍会结束，后续阶段将尽力停止。如需继续，请稍后重新分析。";
        render();
        return;
      }
      render();
      startAnalysisPolling(snapshot.analysis_id, token, revision);
    } catch (error) {
      if (!runtime.current(token)) return;
      work.aiLoading = false;
      stopElapsed();
      work.aiError = errorMessage(error, "AI 分析失败");
      if (error?.payload?.error?.code === "VALIDATION_ERROR") {
        work.aiError += "（请确认已在「校验设置 → 文档快照」导入文档，且表/字段存在）";
      }
      work.descriptionCollapsed = false;
      page.form.setBusy(work.busy);
      render();
      throw error;
    }
  }

  async function saveDraft() {
    if (work.mode === "ai" && (analysisStale() || !work.preview)) throw new Error("请先完成当前需求的分析和 SQL 预览");
    const payload = page.form.validateForSave();
    const token = runtime.next("workbench-save");
    const revision = work.revision;
    work.busy = true;
    page.form.setBusy(true);
    render();
    try {
      const saved = await runtime.request(token, (signal) => api.save(payload, work.ruleId, { signal }));
      if (!runtime.current(token)) return;
      const detail = await runtime.request(token, (signal) => api.rule(saved.id, { signal }));
      if (!runtime.current(token)) return;
      work.ruleId = Number(detail.id);
      work.detail = detail;
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

  async function runTests() {
    if (work.mode === "ai") {
      if (!work.preview || analysisStale()) throw new Error("请先完成当前需求的分析，无需先保存草稿");
      const token = runtime.next("workbench-test");
      const digest = work.preview.content_sha256;
      const snapshot = inputSignature();
      work.testing = true; work.previewEvidence = null; render();
      try {
        const result = await runtime.request(token, (signal) => api.testCandidate({ definition: work.preview.definition,
          expected_hash: digest, cases: work.previewCases }, { signal }));
        if (!runtime.current(token) || work.preview?.content_sha256 !== digest || inputSignature() !== snapshot) return;
        if (result.content_sha256 !== digest) throw new Error("测试结果与当前规则不一致，请重新运行");
        work.previewEvidence = result; work.testing = false;
        if (work.options.length) syncActiveOptionState();
        render();
      } catch (error) {
        if (runtime.current(token)) { work.testing = false; render(); }
        throw error;
      }
      return;
    }
    if (!work.detail) throw new Error("请先保存草稿并读取详情");
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
    if (work.mode === "ai" && work.options.length) return saveOptionAndEnable(work.activeOptionId);
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
        const saved = await runtime.request(token, (signal) => api.save(work.preview.definition, work.ruleId, { signal }));
        if (!runtime.current(token)) return;
        const detail = await runtime.request(token, (signal) => api.rule(saved.id, { signal }));
        if (!runtime.current(token)) return;
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
    return {
      detail: work.detail,
      evidence: work.mode === "ai" ? work.previewEvidence : work.evidence,
      dirty: page.form.isDirty(),
      preview: work.mode === "ai" ? work.preview : null,
      previewCases: work.previewCases, columns: page.form.metadataColumns(),
      stale: work.mode === "ai" && analysisStale(),
      canTest: hasCapability(user, "dv.test"),
      readOnly: work.readOnly,
      busy: work.busy || work.confirmBusy || work.previewBusy,
      testing: work.testing,
    };
  }

  function saveReadiness() {
    try {
      page.form.validateForSave();
      if (work.mode === "ai" && (!work.preview || analysisStale())) return { ready: false, reason: "请先完成当前需求的分析" };
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
    const question = work.candidate?.questions?.[0];
    const stale = work.mode === "ai" && Boolean(work.candidate) && analysisStale();
    const last = !stale && readScopeChoice(user?.id, work.candidate, question);
    const lastChoice = last ? { id: question.id, value: last.selection } : null;
    if (!question || work.selectedChoice?.id !== question.id) work.selectedChoice = lastChoice;
    if (work.options.length && work.candidate && !work.loadingOption) syncActiveOptionState();
    page.candidate?.update(work.candidate, page.form.read(), { loading: work.aiLoading || work.previewBusy, error: work.aiError,
      stale, preview: work.preview, selectedChoice: work.selectedChoice, lastChoice });
    if (work.mode === "ai" && page.optionsPanel) {
      page.optionsPanel.update(
        { candidate_options: work.options, parallel_checks: work.options.some((item) => item.candidate?.parallel_check),
          comparison_suggestions: suggestionScopeReady()
            ? work.comparisonSuggestions.filter((item) => item?.supported === true) : [] },
        {
          selected: work.selectedOptions, activeId: work.expandedOptionId,
          savedRules: work.savedOptionRules, saving: work.optionsSaving,
          locked: Boolean(work.busy || work.optionsSaving),
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
    const readiness = page.tests.update(viewModel());
    const busy = work.busy || work.testing || work.confirmBusy || work.previewBusy || work.aiLoading || work.optionsSaving;
    const isAi = work.mode === "ai";

    const configVisible = isAi ? Boolean(work.candidate || work.options.length) : page.form.metadataColumns().length > 0;
    const testingVisible = isAi ? Boolean(work.preview) && !analysisStale() && work.options.length === 0 : Boolean(work.detail);
    page.configSection.hidden = !configVisible;
    page.testingSection.hidden = !testingVisible;

    if (isAi) {
      const collapsed = work.descriptionCollapsed || work.aiLoading;
      page.collapsedBar.hidden = !collapsed || work.aiLoading;
      page.form.groups.aiContext.hidden = work.aiLoading;
      page.form.groups.aiInput.hidden = collapsed;
      page.waitRequest.hidden = !work.aiLoading;
      dialog?.dialog.classList.toggle("is-ai-waiting", work.aiLoading);
      page.editRequest.hidden = !collapsed || work.aiLoading;
      page.editRequest.disabled = busy;
      page.form.setRequestEditing(Boolean(work.candidate));
      const question = work.candidate?.questions?.[0];
      page.choiceContinue.hidden = !question;
      page.choiceContinue.disabled = busy || analysisStale() || work.selectedChoice?.id !== question?.id;
      const { request_text, source_id, model_id } = page.form.read();
      page.collapsedText.textContent = request_text || "—";
      if (work.aiLoading) {
        page.waitRequestText.textContent = request_text || "—";
        page.waitSource.textContent = state.sources.find((item) => String(item.id) === source_id)?.name || "未选择";
        page.waitModel.textContent = state.models.find((item) => String(item.id) === model_id)?.name || "未选择";
      }
      page.form.setAnalyzing(work.aiLoading);
      page.form.lockInputs(busy);
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
    page.saveButton.hidden = isAi && (work.options.length > 0 || !work.candidate || Boolean(work.candidate.questions?.length));
    page.saveButton.disabled = busy || work.readOnly || !save.ready || !hasCapability(user, "dv.manage");
    if (isAi && page.footerBulk) {
      const multi = work.options.length > 0;
      page.footerBulk.hidden = !multi;
      page.footerBulk.disabled = busy || work.readOnly || !hasCapability(user, "dv.manage") || analysisStale() || !work.selectedOptions.length
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
        : work.preview ? "可先运行测试，无需先保存草稿" : "补充这一项后，再生成完整建议";
    page.saveHint.classList.toggle("is-error", !isAi && !save.ready);

    page.confirmButton.hidden = isAi && !work.preview;
    page.confirmButton.textContent = isAi ? (work.options.length ? "保存此方案并启用" : "保存并启用") : "确认启用";
    page.confirmButton.disabled = busy || work.readOnly || !readiness.ready || (isAi && !hasCapability(user, "dv.manage"))
      || (isAi && work.options.length > 0 && !optionGate(work.activeOptionId).enabled);
    page.confirmButton.title = readiness.ready ? "确认固化并启用当前版本" : readiness.reasons.join("；");
    page.verifyHint.textContent = readiness.ready
      ? (isAi ? "样本测试已通过，可保存草稿或保存并启用；启用时会重新核验保存版本" : "测试已通过：可确认启用，或只保存草稿后关闭弹窗")
      : readiness.reasons.join("；");
    page.verifyHint.classList.toggle("is-success", readiness.ready);
    page.verifyHint.classList.toggle("is-error", !readiness.ready && Boolean(readiness.reasons.length));

    if (page.switchButton) {
      const modelUnavailable = state.modelsStatus === "error" || !state.models.length;
      page.switchButton.hidden = !work.aiError && !modelUnavailable;
    }
    if (footerButton) {
      footerButton.textContent = work.detail ? "关闭" : "取消";
      footerButton.setAttribute("aria-label", work.aiLoading ? "取消等待" : footerButton.textContent);
      footerButton.disabled = work.busy || work.testing || work.confirmBusy || work.previewBusy;
    }
    if (dialog) dialog.closeButton.disabled = work.busy || work.testing || work.confirmBusy || work.previewBusy;
    dialog?.setTitle(work.ruleId
      ? `${work.readOnly ? "查看" : "编辑、测试与确认"} ${work.detail?.rule_code || "规则"}`
      : work.mode === "ai" ? "AI 新建校验规则" : "新建校验规则");
    mountOptionDetail();
    return readiness;
  }

  function close() {
    bestEffortCancelAnalysis();
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