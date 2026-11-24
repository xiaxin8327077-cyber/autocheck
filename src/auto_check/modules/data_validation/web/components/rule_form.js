import {
  BLANK_COLUMN_FIELD, EQUALITY_POLICY_OPTIONS, NULL_POLICY_OPTIONS, OPERATOR_OPTIONS,
} from "../constants.js";
import { errorMessage } from "../runtime.js";
import { bindComparisonField, comparisons, fieldTarget, hasComparison, isFormulaComparison, isGrouped, isKeywordOperator, operandFields } from "../comparisons.js";
import { createKeywordEditor } from "./keyword_editor.js";
import { candidateCondition } from "./ai_candidate.js";
import { createConditionGroup } from "./condition_group.js";
import { aiIcon } from "./ai_visuals.js";
import { hasCapability, reportCategoryCode } from "../state.js";
import { button, element, field, input, select, textarea } from "./dom.js";

function selectedSource(sources, id) {
  return sources.find((source) => String(source.id) === String(id));
}

function finiteNumber(value) {
  if (typeof value === "boolean" || value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const text = String(value).trim();
  if (!text || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text)) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

export function createRuleForm({
  state, mode = "manual", listen, user, onChange, onDescribe, onParse, onCancelEdit, onTestModel, onRetrySources, onRetryModels,
}) {
  const isAiMode = mode === "ai" && hasCapability(user, "dv.ai_use");
  let metadata = null;
  let persistedMappingVersion = "";
  let reportDateField = "report_date";
  let savedSignature = "";
  let aiRuleDescription = "";
  let generationMode = isAiMode ? "ai" : "manual";
  let savedFieldEqualityPolicy = "unresolved";
  let reviewData = {};
  let reviewInputs = [];
  let reviewRemovers = [];
  let savedReviewContext = null;
  const reviewedQuestions = new Set();
  let candidateIncomplete = false;
  // 复合筛选 / 两表关联：由 AI 候选或已保存定义带入，表单必须完整保留，不能读丢。
  let filters = [];
  let join = null;
  let unmatchedPolicy = "unresolved";
  let relationshipConfirmed = false;
  let relatedColumns = [];
  let rightTable = "base";
  let projectContext = null;
  let projectDriver = null;
  let comparisonEvidence = {};
  let simpleFormula = null;
  let semanticReview = {};
  const reviewSection = element("section", { className: "dv-notice is-warning", hidden: true });

  const FILTER_TABLES = ["base", "related"];
  // 与后端 query_grounding 的 operator 名精确一致，不得改写语义。
  const FILTER_OPS = ["lt", "lte", "gt", "gte", "eq", "neq", "in", "not_in", "contains_any", "not_contains_any", "is_null", "is_not_null"];
  const UNMATCHED_POLICIES = ["unresolved", "exclude"];
  const UNARY_EXPRESSION_OPS = ["is_null", "is_not_null"];

  function isUnaryExpressionOp(op) {
    return UNARY_EXPRESSION_OPS.includes(op);
  }

  function clearRelationEvidence() {
    if (simpleFormula) setGroup(null);
    comparisonEvidence = {};
    semanticReview = {};
    filters = [];
    join = null;
    unmatchedPolicy = "unresolved";
    relationshipConfirmed = false;
    relatedColumns = [];
    rightTable = "base";
    projectContext = null;
    projectDriver = null;
  }

  function baseColumns() {
    return [...(metadata?.columns || [])];
  }

  function columnsForTable(table) {
    return table === "related" ? relatedColumns : baseColumns();
  }

  function columnNamesForTable(table) {
    return new Set(columnsForTable(table).map((column) => column.column_name));
  }

  function normalizeFilter(filter) {
    const item = filter && typeof filter === "object" ? filter : null;
    if (!item) {
      return { table: "base", field: "", op: "eq", value: null, confirmed: false, invalid: "筛选条件结构无效" };
    }
    const op = String(item.op || "");
    let value = item.value === undefined ? null : item.value;
    let invalid = "";
    if (!FILTER_OPS.includes(op)) {
      invalid = `筛选运算符 ${op || "空"} 不受支持`;
    } else if (op === "contains_any" || op === "not_contains_any") {
      if (!Array.isArray(value) || !value.length || value.length > 50
          || value.some((word) => typeof word !== "string" || !word || word.length > 200)) invalid = "每组可填写 1 至 50 个关键词，每词最多 200 字";
    } else if (op === "in" || op === "not_in") {
      if (!Array.isArray(value)) invalid = "IN/NOT IN 筛选值必须是数组";
      else if (value.length > 50) invalid = "IN/NOT IN 筛选值不能超过 50 项";
    } else if (op === "is_null" || op === "is_not_null") {
      value = null;
    } else if (typeof value === "string") {
      if (value.length > 200) invalid = "筛选字符串值不能超过 200 字";
    } else if (typeof value !== "number" || !Number.isFinite(value)) {
      invalid = "筛选值必须是有限数值或字符串";
    }
    const result = {
      table: FILTER_TABLES.includes(item.table) ? item.table : "base",
      field: String(item.field || ""),
      op,
      value,
      confirmed: item.confirmed === true,
    };
    if (invalid) result.invalid = invalid;
    return result;
  }

  function readFilters() {
    return filters.map((item) => normalizeFilter(item));
  }

  function readJoin() {
    if (!join || !join.table_name) return null;
    return {
      table_name: String(join.table_name || ""),
      on: (Array.isArray(join.on) ? join.on : []).map((item) => ({
        left: String(item?.left || ""),
        right: String(item?.right || ""),
      })),
      report_date_field: String(join.report_date_field || ""),
      relationship_confirmed: relationshipConfirmed,
      unmatched_policy: unmatchedPolicy,
      ...(join.right_aggregate === "sum" ? { right_aggregate: "sum" } : {}),
    };
  }

  function restoreRelationEvidence(source) {
    const value = source && typeof source === "object" ? source : {};
    semanticReview = value.analysis_protocol === 2
      ? { analysis_protocol: 2, semantic_intent: value.semantic_intent } : {};
    filters = Array.isArray(value.filters) ? value.filters.map(normalizeFilter) : [];
    const joinValue = value.join && value.join.table_name ? value.join : null;
    const nestedConfirmed = joinValue
      ? (joinValue.relationship_confirmed === true || value.relationship_confirmed === true)
      : value.relationship_confirmed === true;
    const nestedUnmatched = joinValue?.right_aggregate === "sum" && joinValue.unmatched_policy === "review" ? "review"
      : (joinValue?.unmatched_policy === "exclude" || value.unmatched_policy === "exclude" ? "exclude" : "unresolved");
    join = joinValue ? {
      table_name: String(joinValue.table_name || ""),
      on: (Array.isArray(joinValue.on) ? joinValue.on : []).map((item) => ({
        left: String(item?.left || ""), right: String(item?.right || ""),
      })),
      report_date_field: String(joinValue.report_date_field || ""),
      relationship_confirmed: nestedConfirmed,
      unmatched_policy: nestedUnmatched,
      ...(joinValue.right_aggregate === "sum" ? { right_aggregate: "sum" } : {}),
    } : null;
    relationshipConfirmed = nestedConfirmed;
    unmatchedPolicy = nestedUnmatched;
    relatedColumns = Array.isArray(value.related_columns) ? [...value.related_columns] : [];
    const expression = value.expression || {};
    comparisonEvidence = Object.fromEntries(["null_handling", "null_evidence", "include_result_fields"]
      .filter((key) => (isGrouped(expression) || isFormulaComparison(expression)) && value[key] !== undefined)
      .map((key) => [key, value[key]]));
    setGroup(expression);
    rightTable = expression.right_table === "related" ? "related" : "base";
    projectContext = value.project_context && typeof value.project_context === "object"
      ? JSON.parse(JSON.stringify(value.project_context))
      : null;
    projectDriver = value.project_driver && typeof value.project_driver === "object"
      ? JSON.parse(JSON.stringify(value.project_driver)) : null;
  }

  function optionSelection(question, value) {
    const options = Array.isArray(question?.options) ? question.options : [];
    const matched = options.find((option) => option?.value === value);
    if (matched?.selection) return matched.selection;
    return value && typeof value === "object" ? value : null;
  }

  function ensureOperatorOption(opName) {
    if (!opName || [...op.options].some((option) => option.value === opName)) return;
    const option = element("option", { text: UNARY_EXPRESSION_OPS.includes(opName) ? `${opName}（一元判断）` : opName });
    option.value = opName;
    op.append(option);
  }

  function recordSelectionResolution(question, text) {
    const review = readReview();
    const index = (review.uncertainties || []).indexOf(question?.uncertainty);
    if (index < 0) return;
    const resolutions = [...(review.uncertainty_resolutions || [])];
    while (resolutions.length <= index) resolutions.push("");
    resolutions[index] = text;
    setReview({ ...review, uncertainty_resolutions: resolutions });
  }

  function selectionLabel(question, selection, fallback) {
    const options = Array.isArray(question?.options) ? question.options : [];
    const matched = options.find((option) => option?.selection === selection || option?.value === selection);
    return matched?.label || fallback || "已选口径";
  }

  const name = input({ placeholder: "输入规则名称" });
  const source = select(BLANK_COLUMN_FIELD, {
    className: isAiMode ? "dv-select dv-ai-meta-select dv-ai-source-select rsp-compact-select" : "dv-select",
  });
  const category = select(BLANK_COLUMN_FIELD);
  const table = input({ placeholder: "输入已通过授权的物理表名" });
  const describe = button("读取表结构", { listen, onClick: () => onDescribe() });
  const tableRow = element("div", { className: "dv-inline-control" }, table, describe);
  const requestLabel = isAiMode ? "需求描述 *" : "规则说明";
  const request = textarea({
    placeholder: isAiMode
      ? "用一句话描述要校验什么，AI 会据此自动选表、生成校验属性与规则"
      : "描述这条规则的用途（选填）",
    rows: 4,
  });
  const requestField = field(requestLabel, request);
  requestField.classList.add("dv-field-wide");

  const model = select(BLANK_COLUMN_FIELD, {
    className: "dv-select dv-ai-meta-select dv-ai-model-select rsp-compact-select",
  });
  const modelTestButton = button("测试可用性", {
    listen, className: "dv-button dv-button-plain", onClick: () => runModelTest(),
  });
  const modelTestStatus = element("span", { className: "dv-inline-status dv-model-test-status" });
  const parse = button("✦ AI 分析", {
    listen, className: "dv-button dv-button-primary", capability: "dv.ai_use", onClick: () => onParse(),
  });
  const modelStatus = element("p", { className: "dv-inline-status" });
  const retryModels = button("重试模型", { listen, className: "dv-button dv-button-plain", onClick: onRetryModels });
  retryModels.hidden = true;

  const businessKey = select(BLANK_COLUMN_FIELD);
  const left = select(BLANK_COLUMN_FIELD);
  const right = select(BLANK_COLUMN_FIELD);
  const rightType = select([["field", "字段"], ["value", "数值常量"], ["text", "文本常量"]]);
  const rightNumber = input({ type: "number", placeholder: "输入有限数值常量，如 0" });
  rightNumber.step = "any";
  const op = select(OPERATOR_OPTIONS);
  const message = input({ placeholder: "命中违规时展示的异常说明" });
  const nullPolicy = select(NULL_POLICY_OPTIONS);
  if (![...nullPolicy.options].some((option) => option.value === "zero")) {
    const zeroOption = element("option", { text: "NULL按0处理（仅数值比较）" });
    zeroOption.value = "zero";
    nullPolicy.append(zeroOption);
  }
  if (![...nullPolicy.options].some((option) => option.value === "review")) {
    const reviewOption = element("option", { text: "系统处理：缺值单列核查" });
    reviewOption.value = "review";
    nullPolicy.append(reviewOption);
  }
  const equalityPolicy = select(EQUALITY_POLICY_OPTIONS);
  const sourceStatus = element("p", { className: "dv-inline-status" });
  const metadataStatus = element("p", { className: "dv-inline-status" });
  const retrySources = button("重试数据源", { listen, className: "dv-button dv-button-plain", onClick: onRetrySources });
  retrySources.hidden = true;

  const sourceField = field("数据源 *", source);
  const sourceFeedback = element("div", { className: "dv-inline-status-row" }, sourceStatus, retrySources);
  const modelField = field("启用模型", model);
  const modelFeedback = element("div", { className: "dv-inline-status-row" }, modelStatus, retryModels);
  const cancelEdit = button("取消修改", { listen, className: "dv-button dv-button-plain", onClick: () => onCancelEdit?.() });
  cancelEdit.hidden = true;
  let reanalysis = false;
  const aiActions = element("div", { className: "dv-ai-actions" }, cancelEdit, parse);
  const tableReadonly = element("span", { className: "dv-readonly-value", text: "待 AI 生成" });
  const tableDisplayField = field("目标表（AI 分析选定）", tableReadonly);

  const rightConstantField = field("数值常量 *", rightNumber);
  rightConstantField.hidden = true;
  const rightField = field("右字段 *", right);
  const rightTypeField = field("比较目标类型 *", rightType);
  const keywords = createKeywordEditor(listen, changed);
  keywords.set([]);
  keywords.element.hidden = true;

  const equalityPolicyField = field("相等处理口径", equalityPolicy);
  const constantEqualityHint = element("p", {
    className: "dv-inline-status",
    text: "数值常量按异常触发关系判断相等",
    hidden: true,
  });
  const nullZeroHint = element("p", {
    className: "dv-inline-status dv-null-zero-hint",
    text: "数值比较：NULL按0处理",
    hidden: true,
  });

  const simpleFields = [
    field("异常触发关系", op),
    field("左字段 *", left), rightTypeField,
    rightField, rightConstantField, keywords.element];
  const formulaSummary = element("span", { className: "dv-readonly-value" });
  const formulaField = field("公式条件（只读）", formulaSummary);
  formulaField.hidden = true;
  const mappingGrid = element("div", { className: "dv-form-grid" }, field("业务主键 *", businessKey), simpleFields, formulaField);
  const addGroup = isAiMode ? null : button("添加比较条件", {
    listen, onClick: () => {
      setGroup({ logic: "any", conditions: [readComparison(), { left: "", op: "eq", right_type: "value", right: null }] });
      changed();
    },
  });
  const group = createConditionGroup({ listen, columnsForTable, onEdit() {
    syncNullPolicyForExpression();
    invalidateReviewAnswers();
    onChange?.({ groupEdited: true });
  } });
  function setGroup(expression) {
    group.set(expression);
    const grouped = isGrouped(expression);
    simpleFormula = isFormulaComparison(expression) ? JSON.parse(JSON.stringify(expression)) : null;
    renderFormula();
    if (addGroup) addGroup.hidden = grouped;
    for (const node of simpleFields) node.hidden = grouped || Boolean(simpleFormula);
    if (grouped || simpleFormula) {
      equalityPolicyField.hidden = true;
      constantEqualityHint.hidden = true;
    }
  }
  function renderFormula() {
    formulaField.hidden = !simpleFormula;
    if (simpleFormula) formulaSummary.textContent = candidateCondition({ expression: simpleFormula, columns: baseColumns() });
  }
  const messageField = field("异常说明 *", message);
  const policyGrid = element("div", { className: "dv-form-grid" },
    field("空值处理口径", nullPolicy), equalityPolicyField, constantEqualityHint, nullZeroHint);

  // 单页分区：AI 模式两块（输入区 / 结果配置区），手动模式两块（基本信息 / 字段配置）。
  const groups = isAiMode
    ? {
      aiContext: element("div", { className: "dv-ai-request-meta" }, element("span", { text: "你的需求" }),
        element("div", { className: "dv-ai-inline-source" }, aiIcon("database"), sourceField),
        element("div", { className: "dv-ai-inline-model" }, modelField)),
      aiInput: element("div", { className: "dv-form-section dv-form-ai-input" },
        requestField,
        sourceFeedback,
        modelFeedback,
        aiActions),
      aiConfig: element("div", { className: "dv-form-section dv-form-ai-config" },
        field("规则名称 *", name, "由 AI 分析自动生成，可修改"),
        field("监管报送分类 *", category, "由 AI 分析自动选定，可修改"),
        tableDisplayField,
        metadataStatus,
        mappingGrid,
        messageField,
        policyGrid),
    }
    : {
      basics: element("div", { className: "dv-form-section dv-form-basics" },
        field("规则名称 *", name),
        sourceField,
        sourceFeedback,
        field("监管报送分类 *", category),
        field("目标表 / 业务对象 *", tableRow, "当前接口不提供表清单；输入物理表名后读取真实字段，不由 AI 猜测"),
        metadataStatus,
        requestField),
      config: element("div", { className: "dv-form-section dv-form-config" },
        mappingGrid, addGroup, group.element,
        messageField,
        policyGrid),
    };
  // Workbench moves these groups into its own sections; keep reviews inside a group.
  (isAiMode ? groups.aiConfig : groups.config).append(reviewSection);
  const form = element("div", { className: "dv-rule-form" }, ...Object.values(groups));

  function setReview(value = {}, regenerate = false) {
    reviewRemovers.forEach((remove) => remove?.());
    reviewRemovers = [];
    reviewInputs = [];
    reviewData = {};
    candidateIncomplete = value.status === "needs_clarification";
    ["uncertainties", "uncertainty_resolutions", "unsupported_requirements"].forEach((key) => {
      if (Array.isArray(value[key])) reviewData[key] = [...value[key]];
    });
    if (regenerate && reviewData.uncertainties) reviewData.uncertainty_resolutions = [];
    reviewSection.replaceChildren();
    const questions = reviewData.uncertainties || [];
    const unsupported = reviewData.unsupported_requirements || [];
    reviewSection.hidden = !questions.length && !unsupported.length;
    if (questions.length) {
      reviewSection.append(element("strong", { text: generationMode === "ai"
        ? "生成 SQL 前请逐项填写业务口径" : "待确认口径（保存草稿后仍会保留，逐项处理并重新测试后才能确认）" }));
      questions.forEach((question, index) => {
        const resolution = textarea({ placeholder: "填写明确口径、适用范围或处理依据，不能只写已阅", rows: 2 });
        resolution.value = reviewData.uncertainty_resolutions?.[index] || "";
        reviewInputs.push(resolution);
        reviewRemovers.push(listen(resolution, "input", () => {
          if (savedReviewContext !== null && resolution.value.trim()) reviewedQuestions.add(question);
          else reviewedQuestions.delete(question);
          changed();
        }));
        reviewSection.append(field(`处理说明 ${index + 1}：${question}`, resolution));
      });
    }
    if (unsupported.length) {
      reviewSection.append(element("strong", { text: "当前字段比较无法表达以下要求，不能以处理说明放行。请缩小需求重新生成或使用适合的规则。" }));
      const list = element("ul");
      unsupported.forEach((item) => list.append(element("li", { text: item })));
      reviewSection.append(list);
    }
  }

  function readReview() {
    const result = { ...reviewData };
    if (Array.isArray(result.uncertainties)) result.uncertainty_resolutions = reviewInputs.map((control) => control.value.trim());
    return result;
  }

  [name, request, message, nullPolicy, businessKey, left, right].forEach((control) => {
    listen(control, control.tagName === "SELECT" ? "change" : "input", changed);
  });
  listen(op, "change", () => {
    applyRightTarget(rightType.value);
    changed();
  });
  listen(equalityPolicy, "change", () => {
    if (rightType.value === "field") savedFieldEqualityPolicy = equalityPolicy.value;
    changed();
  });
  listen(table, "input", () => {
    setMetadata(null);
    changed();
  });
  listen(source, "change", () => {
    setMetadata(null);
    changed();
  });
  listen(model, "change", () => {
    modelTestStatus.textContent = "";
    modelTestStatus.classList.remove("is-success", "is-error");
    changed();
  });
  listen(rightType, "change", () => {
    applyRightTarget(rightType.value);
    changed();
  });
  listen(rightNumber, "input", changed);

  function applyRightTarget(type) {
    const grouped = group.read();
    nullPolicy.disabled = grouped ? grouped.conditions.some((item) => isKeywordOperator(item.op))
      : !simpleFormula && isKeywordOperator(op.value);
    if (nullPolicy.disabled) nullPolicy.value = "skip";
    if (simpleFormula) {
      simpleFields.forEach((node) => { node.hidden = true; });
      equalityPolicyField.hidden = true;
      constantEqualityHint.hidden = true;
      return;
    }
    const valueMode = type === "value" || type === "text";
    const wordMode = isKeywordOperator(op.value);
    keywords.element.hidden = !wordMode;
    rightTypeField.hidden = wordMode;
    if (wordMode) {
      rightField.hidden = rightConstantField.hidden = true;
      equalityPolicyField.hidden = constantEqualityHint.hidden = true;
      equalityPolicy.value = "allow_equal";
      nullPolicy.value = "skip";
      return;
    }
    rightType.value = valueMode ? type : "field";
    rightNumber.type = type === "text" ? "text" : "number";
    rightConstantField.children[0].textContent = type === "text" ? "文本常量 *" : "数值常量 *";
    rightNumber.placeholder = type === "text" ? "输入文本或字典码值" : "输入有限数值常量，如 0";
    constantEqualityHint.textContent = type === "text" ? "文本常量按相等或不相等比较" : "数值常量按异常触发关系判断相等";
    rightConstantField.hidden = !valueMode;
    rightField.hidden = valueMode;
    equalityPolicyField.hidden = valueMode;
    constantEqualityHint.hidden = !valueMode;
    if (valueMode) {
      equalityPolicy.value = "allow_equal";
    } else {
      equalityPolicy.value = savedFieldEqualityPolicy || "unresolved";
    }
    equalityPolicy.disabled = valueMode;
    if (!group.element.hidden || simpleFormula) {
      simpleFields.forEach((node) => { node.hidden = true; });
      equalityPolicyField.hidden = true;
      constantEqualityHint.hidden = true;
    }
  }

  let modelTesting = false;

  async function runModelTest() {
    if (!model.value) {
      modelTestStatus.textContent = "请先选择模型";
      modelTestStatus.classList.add("is-error");
      return;
    }
    modelTesting = true;
    modelTestButton.disabled = true;
    modelTestButton.textContent = "测试中…";
    modelTestStatus.textContent = "正在测试模型可用性…";
    modelTestStatus.classList.remove("is-success", "is-error");
    try {
      await onTestModel?.(model.value);
      modelTestStatus.textContent = "短对话可用（规则生成仍需独立校验）";
      modelTestStatus.classList.add("is-success");
    } catch (error) {
      modelTestStatus.textContent = `模型不可用：${errorMessage(error)}`;
      modelTestStatus.classList.add("is-error");
    } finally {
      modelTesting = false;
      modelTestButton.disabled = false;
      modelTestButton.textContent = "测试可用性";
    }
  }

  function changed() {
    syncNullPolicyForExpression();
    invalidateReviewAnswers();
    onChange?.();
  }

  function reviewContext() {
    const value = read();
    return JSON.stringify([value.rule_type, value.source_id, value.table_name, value.business_key, value.report_date_field,
      value.expression, value.filters, value.join, value.project_context, value.project_driver, value.null_policy, value.equality_policy,
      value.description, value.report_category, value.mapping_version]);
  }

  function invalidateReviewAnswers() {
    if (savedReviewContext === null) return;
    const current = reviewContext();
    if (savedReviewContext === current) return;
    savedReviewContext = current;
    reviewInputs.forEach((input) => { input.value = ""; });
    reviewedQuestions.clear();
  }

  function syncTableReadonly() {
    tableReadonly.textContent = table.value.trim() || "待 AI 生成";
  }

  function columnOptions(columns) {
    return columns.length ? columns.map((column) => [
      column.column_name,
      `${column.column_name}${column.comment ? ` · ${column.comment}` : ""}`,
    ]) : BLANK_COLUMN_FIELD;
  }

  function setColumnOptions(columns, preserved = {}, rightColumns = null) {
    const baseOptions = columnOptions(columns);
    const rightOptions = columnOptions(rightColumns || columns);
    const targets = [
      [businessKey, preserved.businessKey, baseOptions],
      [left, preserved.left, baseOptions],
      [right, preserved.right, rightOptions],
    ];
    targets.forEach(([control, value, options]) => {
      control.replaceChildren();
      options.forEach(([optionValue, label]) => {
        const option = element("option", { text: label });
        option.value = optionValue;
        control.append(option);
      });
      control.value = value || "";
      if (control.value !== (value || "")) control.value = "";
    });
  }

  function refreshRightColumns(preserve = true) {
    setColumnOptions(baseColumns(), {
      businessKey: businessKey.value,
      left: left.value,
      right: preserve ? right.value : "",
    }, rightTable === "related" ? relatedColumns : null);
  }

  const NUMERIC_TYPES = new Set([
    "int", "integer", "bigint", "smallint", "tinyint", "mediumint",
    "decimal", "numeric", "float", "double", "real", "money",
  ]);

  function columnIsNumeric(name) {
    const column = (metadata?.columns || []).find((item) => item.column_name === name);
    const type = String(column?.data_type || "").toLowerCase().split("(")[0].trim();
    return NUMERIC_TYPES.has(type);
  }

  function binaryNumericComparison() {
    const binary = comparisons(readComparison()).filter((item) => !isUnaryExpressionOp(item.op));
    return binary.length > 0 && binary.every((item) => {
      if (!item.left || !operandFields(item, "left").every(columnIsNumeric)) return false;
      if (item.right_type === "formula") return operandFields(item, "right").every(columnIsNumeric);
      if (item.right_type === "value") return Number.isFinite(item.right);
      const column = columnsForTable(item.right_table).find((entry) => entry.column_name === item.right);
      return NUMERIC_TYPES.has(String(column?.data_type || "").toLowerCase().split("(")[0].trim());
    });
  }

  function syncNullPolicyForExpression() {
    nullPolicy.disabled = comparisons(readComparison()).some((item) => isKeywordOperator(item.op));
    if (nullPolicy.disabled) nullPolicy.value = "skip";
    const numeric = binaryNumericComparison();
    const explicitZero = nullPolicy.value === "zero";
    nullZeroHint.hidden = !explicitZero;
    nullZeroHint.textContent = explicitZero
      ? (numeric ? "数值比较：NULL按0处理" : "NULL按0仅支持数值字段或有限数值常量比较")
      : "数值比较：NULL按0处理";
    return explicitZero && numeric;
  }

  function readComparison() {
    const grouped = group.read();
    if (grouped) return grouped;
    if (simpleFormula) return JSON.parse(JSON.stringify(simpleFormula));
    const comparison = { left: left.value, op: op.value };
    if (isUnaryExpressionOp(comparison.op)) return comparison;
    if (isKeywordOperator(comparison.op)) return { ...comparison, right_type: "value", right: keywords.read() };
    if (rightType.value !== "field") {
      comparison.right_type = "value";
      comparison.right = rightType.value === "text" ? rightNumber.value : finiteNumber(rightNumber.value);
    } else {
      comparison.right = right.value;
      if (rightTable === "related") comparison.right_table = "related";
    }
    return comparison;
  }

  function read() {
    const sourceItem = selectedSource(state.sources, source.value);
    const comparison = readComparison();
    const unaryExpression = isUnaryExpressionOp(comparison.op);
    return {
      name: name.value.trim(),
      description: (isAiMode && aiRuleDescription) || request.value.trim(),
      rule_type: "field_compare",
      dialect: sourceItem?.dialect || "",
      source_id: source.value,
      report_category: category.value,
      table_name: table.value.trim(),
      business_key: businessKey.value,
      report_date_field: reportDateField,
      expression: comparison,
      ...(filters.length ? { filters: readFilters() } : {}),
      ...(join ? { join: readJoin() } : {}),
      ...(relatedColumns.length ? { related_columns: relatedColumns.map((column) => ({ ...column })) } : {}),
      ...(projectContext ? { project_context: JSON.parse(JSON.stringify(projectContext)) } : {}),
      ...(projectDriver ? { project_driver: JSON.parse(JSON.stringify(projectDriver)) } : {}),
      ...readReview(), ...comparisonEvidence, ...semanticReview,
      violation_message: message.value.trim(),
      null_policy: unaryExpression ? "violate" : comparisons(comparison).some((item) => isKeywordOperator(item.op)) ? "skip" : nullPolicy.value,
      equality_policy: unaryExpression || isGrouped(comparison)
        ? "allow_equal"
        : (!simpleFormula && rightType.value !== "field" ? "allow_equal" : equalityPolicy.value),
      generation_mode: generationMode,
      mapping_version: metadata?.mapping_version || persistedMappingVersion,
      model_id: model.value,
      ...(isAiMode ? { reasoning_enabled: false } : {}),
      request_text: request.value.trim(),
    };
  }

  function signature() {
    const payload = read();
    delete payload.model_id;
    delete payload.reasoning_enabled;
    delete payload.request_text;
    return JSON.stringify(payload);
  }

  function applySeed(seed) {
    if (!seed) return;
    if (["uncertainties", "uncertainty_resolutions", "unsupported_requirements"].some((key) => Array.isArray(seed[key]))) setReview(seed);
    if (seed.name) name.value = seed.name;
    if (seed.source_id) source.value = seed.source_id;
    if (seed.table_name) table.value = seed.table_name;
    if (seed.request_text) request.value = seed.request_text;
    // 兼容旧草稿字段：推理不再提供入口，seed.reasoning_enabled 一律忽略。
    if (seed.report_category !== undefined) {
      const code = reportCategoryCode(seed.report_category);
      if (code && ![...category.options].some((option) => option.value === code)) {
        const option = element("option", { text: code === "group:pbc" ? "人行报送" : `${code}（历史分类）` });
        option.value = code;
        category.append(option);
      }
      category.value = code;
    }
    if (seed.business_key) businessKey.value = seed.business_key;
    if (seed.violation_message !== undefined) message.value = seed.violation_message || "";
    restoreRelationEvidence(seed);
    const expression = seed.expression || {};
    const seedValueComparison = expression.right_type === "value";
    ensureOperatorOption(expression.op || "lt");
    op.value = expression.op || "lt";
    left.value = typeof expression.left === "string" ? expression.left : "";
    applyRightTarget(seedValueComparison ? (typeof expression.right === "string" ? "text" : "value") : "field");
    if (isKeywordOperator(expression.op)) keywords.set(expression.right);
    if (seedValueComparison) {
      rightNumber.value = String(expression.right ?? "");
    } else {
      refreshRightColumns(false);
      right.value = typeof expression.right === "string" ? expression.right : "";
    }
    const unaryExpression = isUnaryExpressionOp(expression.op);
    if (seed.report_date_field !== undefined) reportDateField = seed.report_date_field || "";
    nullPolicy.value = unaryExpression ? "violate" : (seed.null_policy || "unresolved");
    equalityPolicy.value = unaryExpression ? "allow_equal" : (seed.equality_policy || "unresolved");
    savedFieldEqualityPolicy = equalityPolicy.value;
    syncNullPolicyForExpression();
    if (seed.metadata) setMetadata(seed.metadata);
    refreshRightColumns(true);
    syncTableReadonly();
  }

  return {
    element: form,
    groups,
    groupEditor: group.element,
    lockGroup(locked) {
      group.element.disabled = locked;
      if (addGroup) addGroup.disabled = locked;
    },
    disposeGroup: group.dispose,
    read,
    reviewedUncertainties() { return [...reviewedQuestions]; },
    signature,
    markSaved() { savedSignature = signature(); },
    isDirty() { return Boolean(savedSignature) && savedSignature !== signature(); },
    setCategories() {
      const current = category.value;
      category.replaceChildren();
      let options = [];
      if (state.categoriesStatus === "loading" || state.categoriesStatus === "idle") options = [["", "正在加载报送分类…"]];
      else if (state.categoriesStatus === "error") options = [["", "分类加载失败，请重试"]];
      else if (!state.categories.length) options = [["", "暂无报送分类"]];
      else options = [["", "请选择监管报送分类"], ...state.categories.map((item) => [item.code, item.name])];
      options.forEach(([value, label]) => {
        const option = element("option", { text: label });
        option.value = value;
        category.append(option);
      });
      if (current && !options.some(([value]) => String(value) === String(current))) {
        const option = element("option", { text: `${current}（历史分类）` });
        option.value = current;
        category.append(option);
      }
      category.value = current;
    },
    setSources() {
      const current = source.value;
      // 暂时只在 AI 新建隐藏集市；手工表单和后端来源清单不受影响。
      const available = state.sourcesStatus === "success"
        ? state.sources.filter((item) => !isAiMode || String(item.name || "").trim() !== "监管报送集市") : [];
      source.replaceChildren();
      let options = [];
      if (state.sourcesStatus === "loading" || state.sourcesStatus === "idle") options = [["", "正在加载数据源…"]];
      else if (state.sourcesStatus === "error") options = [["", "数据源加载失败，请重试"]];
      else if (!available.length) options = [["", "暂无可用数据源"]];
      else options = [["", "请选择数据源"], ...available.map((item) => [item.id, isAiMode ? item.name : `${item.name}（${item.dialect}）`])];
      options.forEach(([value, label]) => {
        const option = element("option", { text: label });
        option.value = value;
        source.append(option);
      });
      const currentIsAvailable = available.some((item) => String(item.id) === current);
      const preferred = available.find((item) => isAiMode
        ? String(item.name || "").trim() === "监管报表" : String(item.name || "").includes("监管报送集市")) || available[0];
      source.value = currentIsAvailable ? current : preferred ? String(preferred.id) : "";
      sourceStatus.textContent = state.sourcesStatus === "error" ? state.sourcesError : "";
      sourceStatus.classList.toggle("is-error", state.sourcesStatus === "error");
      retrySources.hidden = state.sourcesStatus !== "error";
    },
    setModels() {
      if (!isAiMode) return;
      const current = model.value;
      model.replaceChildren();
      let options = [];
      if (state.modelsStatus === "loading" || state.modelsStatus === "idle") options = [["", "正在加载模型…"]];
      else if (state.modelsStatus === "error") options = [["", "模型加载失败，可转手工继续"]];
      else if (!state.models.length) options = [["", "暂无可用模型，可转手工继续"]];
      else options = state.models.map((item) => [item.id, item.name || "未命名模型"]);
      options.forEach(([value, label]) => {
        const option = element("option", { text: label });
        option.value = value;
        model.append(option);
      });
      const defaultModel = state.models.find((item) => item.is_default);
      model.value = current || defaultModel?.id || state.models[0]?.id || "";
      modelStatus.textContent = state.modelsStatus === "error" ? state.modelsError : "";
      modelStatus.classList.toggle("is-error", state.modelsStatus === "error");
      retryModels.hidden = state.modelsStatus !== "error";
    },
    setMetadata,
    metadataColumns() { return [...(metadata?.columns || [])]; },
    relatedColumns() { return [...relatedColumns]; },
    setMetadataFeedback(message, tone = "") {
      metadataStatus.textContent = message;
      metadataStatus.classList.remove("is-error", "is-success", "is-warning");
      if (tone) metadataStatus.classList.add(`is-${tone}`);
    },
    reset(detail, seed = null) {
      aiRuleDescription = "";
      savedReviewContext = null;
      reviewedQuestions.clear();
      const definition = detail?.definition || {};
      const expression = definition.expression || {};
      restoreRelationEvidence(definition);
      if (Array.isArray(detail?.related_columns)) relatedColumns = [...detail.related_columns];
      generationMode = definition.generation_mode || detail?.generation_mode || (isAiMode ? "ai" : "manual");
      setReview(definition);
      name.value = detail?.name || definition.name || "";
      if (definition.source_id && ![...source.options].some((option) => option.value === String(definition.source_id))) {
        const option = element("option", { text: `${definition.source_id}（服务端规则数据源）` });
        option.value = definition.source_id;
        source.append(option);
      }
      source.value = definition.source_id || "";
      const savedCategory = reportCategoryCode(detail?.report_category || definition.report_category);
      if (savedCategory && ![...category.options].some((option) => option.value === String(savedCategory))) {
        const option = element("option", { text: `${savedCategory}（历史分类）` });
        option.value = savedCategory;
        category.append(option);
      }
      category.value = savedCategory;
      table.value = definition.table_name || "";
      request.value = definition.description || "";
      message.value = definition.violation_message || "";
      const unaryExpression = isUnaryExpressionOp(expression.op);
      nullPolicy.value = unaryExpression ? "violate" : (definition.null_policy || "unresolved");
      equalityPolicy.value = unaryExpression ? "allow_equal" : (definition.equality_policy || "unresolved");
      savedFieldEqualityPolicy = equalityPolicy.value;
      syncNullPolicyForExpression();
      ensureOperatorOption(expression.op || "lt");
      op.value = expression.op || "lt";
      metadata = null;
      persistedMappingVersion = definition.mapping_version || detail?.mapping_version || "";
      reportDateField = definition.report_date_field ?? "report_date";
      const valueComparison = expression.right_type === "value";
      const rightFieldName = !valueComparison && typeof expression.right === "string" ? expression.right : "";
      applyRightTarget(valueComparison ? (typeof expression.right === "string" ? "text" : "value") : "field");
      if (isKeywordOperator(expression.op)) keywords.set(expression.right);
      const leftFieldName = typeof expression.left === "string" ? expression.left : "";
      const existing = [definition.business_key, leftFieldName, rightFieldName].filter(Boolean);
      const columns = existing.map((column_name) => ({ column_name, comment: "服务端规则字段，待元数据核验" }));
      const rightPool = rightTable === "related"
        ? [...relatedColumns, ...(rightFieldName && !relatedColumns.some((column) => column.column_name === rightFieldName)
          ? [{ column_name: rightFieldName, comment: "服务端规则字段，待元数据核验" }] : [])]
        : columns;
      setColumnOptions(columns, {
        businessKey: definition.business_key, left: leftFieldName, right: rightFieldName,
      }, rightPool);
      if (valueComparison) {
        rightNumber.value = String(expression.right ?? "");
      } else {
        right.value = rightFieldName || "";
      }
      metadataStatus.textContent = detail
        ? "正在按服务端详情核验字段；保存或测试前请读取最新表结构"
        : (isAiMode ? "AI 分析成功后将显示所选目标表的真实字段" : "读取表结构后才能选择候选字段");
      metadataStatus.classList.remove("is-error", "is-success");
      syncTableReadonly();
      savedSignature = "";
      this.markSaved();
      applySeed(seed);
      if (detail && !isAiMode && generationMode === "ai" && reviewInputs.length) savedReviewContext = reviewContext();
    },
    restoreInput(signature) {
      const [sourceId, text, modelId] = JSON.parse(signature);
      source.value = sourceId; request.value = text; model.value = modelId;
    },
    // 兼容已加载页面的旧调用；推理入口已移除，任何调用都只能保持关闭。
    setReasoningEnabled() { return false; },
    setReasoning() { return false; },
    setRequestEditing(hasCandidate) {
      reanalysis = Boolean(hasCandidate);
      cancelEdit.hidden = !reanalysis;
    },
    applyCandidate(candidate, { regenerate = true } = {}) {
      aiRuleDescription = candidate?.description || "";
      restoreRelationEvidence(candidate);
      setReview(candidate || {}, regenerate);
        if (candidate?.rule_type !== "field_compare") return false;
      generationMode = "ai";
      if (candidate.rule_name) name.value = candidate.rule_name;
      if (candidate.table_name) table.value = candidate.table_name;
      category.value = reportCategoryCode(candidate.report_category);
      businessKey.value = candidate.business_key || "";
      reportDateField = candidate.report_date_field ?? "report_date";
      message.value = candidate.violation_message || "";
      const unaryExpression = isUnaryExpressionOp(candidate.expression?.op);
      nullPolicy.value = unaryExpression ? "violate" : (candidate.null_policy || "unresolved");
      equalityPolicy.value = unaryExpression ? "allow_equal" : (candidate.equality_policy || "unresolved");
      savedFieldEqualityPolicy = equalityPolicy.value;
      syncNullPolicyForExpression();
      ensureOperatorOption(candidate.expression?.op || "lt");
      op.value = candidate.expression?.op || "lt";
      left.value = typeof candidate.expression?.left === "string" ? candidate.expression.left : "";
      const valueComparison = candidate.expression?.right_type === "value";
      applyRightTarget(valueComparison ? (typeof candidate.expression.right === "string" ? "text" : "value") : "field");
      if (isKeywordOperator(candidate.expression?.op)) keywords.set(candidate.expression.right);
      if (valueComparison) {
        rightNumber.value = String(candidate.expression.right ?? "");
      } else {
        const field = candidate.expression?.right;
        refreshRightColumns(false);
        right.value = typeof field === "string" ? field : "";
      }
      syncTableReadonly();
      changed();
      return true;
    },
    applyDecision(key, value, question = null) {
      if (key === "check_requirement" && value === "not_empty" && question?.options?.some((option) => option.value === value)) {
        aiRuleDescription = `${request.value.trim()}不得为空`;
        ensureOperatorOption("is_null");
        op.value = "is_null";
        nullPolicy.value = "violate";
        equalityPolicy.value = "allow_equal";
        recordSelectionResolution(question, "明确选择不得为空");
      } else if (String(key).startsWith("project_context.")) {
        const field = String(key).split(".")[1];
        const baseColumns = metadata?.columns || [];
        const projectColumns = Array.isArray(metadata?.project_columns) ? metadata.project_columns : [];
        const questionOptions = Array.isArray(question?.options) ? question.options : [];
        const optionValues = questionOptions.map((option) => option?.value);
        const selection = optionSelection(question, value);
        const projectColumnExists = (name) => projectColumns.some((column) => column?.column_name === name);
        if (field === "mode") {
          if (value !== "base" && value !== "lookup") throw new Error("该选择不在当前可用范围内，请重新分析");
          projectContext = { ...(projectContext || {}), mode: value };
          if (value === "lookup") {
            ["key", "name_field", "date_field", "unique_evidence"].forEach((key) => delete projectContext[key]);
          }
        } else if (field === "table_name") {
          const allowed = optionValues.length
            ? optionValues
            : (metadata?.project_table ? [metadata.project_table] : projectColumns.map((column) => column?.table_name));
          const selectedTable = selection?.table_name || value;
          if (allowed.length && !allowed.includes(selectedTable)) throw new Error("该选择不在当前可用范围内，请重新分析");
          projectContext = { ...(projectContext || {}), mode: "lookup", table_name: selectedTable };
          ["key", "name_field", "date_field", "unique_evidence"].forEach((key) => delete projectContext[key]);
        } else if (field === "mapping") {
          if (!selection || typeof selection !== "object") throw new Error("该选择不在当前可用范围内，请重新分析");
          const next = {
            ...(projectContext || {}),
            mode: selection.mode === "base" ? "base" : "lookup",
            table_name: selection.table_name || projectContext?.table_name || "",
          };
          ["key", "name_field", "date_field"].forEach((name) => {
            if (selection[name] !== undefined) next[name] = selection[name];
          });
          if (selection.unique_evidence !== undefined) next.unique_evidence = selection.unique_evidence;
          projectContext = next;
        } else if (field === "confirmed") {
          projectContext = { ...(projectContext || {}), confirmed: value === true || value === "true" };
        } else if (field === "code_field") {
          if (baseColumns.length && !baseColumns.some((column) => column.column_name === value)) throw new Error("该选择不在当前可用范围内，请重新分析");
          projectContext = { ...(projectContext || {}), code_field: value };
        } else if (field === "name_field" || field === "key" || field === "date_field") {
          const optionAllowed = optionValues.length ? optionValues.includes(value) : true;
          const poolAllowed = projectColumns.length ? projectColumnExists(value) : true;
          if (!optionAllowed || !poolAllowed) throw new Error("该选择不在当前可用范围内，请重新分析");
          if (field === "date_field" && projectColumns.length) {
            const typed = projectColumns.find((column) => column?.column_name === value);
            if (String(typed?.data_type || "").toLowerCase().split("(")[0].trim() !== "date") {
              throw new Error("关联日期必须是真实 DATE 字段");
            }
          }
          projectContext = { ...(projectContext || {}), [field]: value };
        } else if (field === "unique_evidence") {
          projectContext = { ...(projectContext || {}), unique_evidence: String(value) };
        } else {
          throw new Error("该选择不在当前可用范围内，请重新分析");
        }
        recordSelectionResolution(question, `明确选择 ${value}`);
      }
      else if (String(key).startsWith("filters.")) {
        const index = Number(String(key).split(".")[1]);
        const selection = optionSelection(question, value);
        if (!filters[index] || !selection || typeof selection !== "object") throw new Error("该选择不在当前可用范围内，请重新分析");
        if (!columnNamesForTable(selection.table).has(selection.field)) throw new Error("该选择不在当前可用范围内，请重新分析");
        filters[index] = normalizeFilter({ ...selection, confirmed: true });
        recordSelectionResolution(question, `明确选择 ${selectionLabel(question, selection, selection.field)}`);
      }
      else if (key === "join.relationship_confirmed") {
        const selection = optionSelection(question, value);
        if (!join) join = { table_name: "", on: [], report_date_field: "", relationship_confirmed: false, unmatched_policy: "unresolved" };
        if (selection && Array.isArray(selection.on)) {
          const pairs = selection.on.map((pair) => ({ left: String(pair?.left || ""), right: String(pair?.right || "") }));
          join.on = pairs;
          const baseFields = columnNamesForTable("base");
          const relatedFields = columnNamesForTable("related");
          pairs.forEach((pair) => {
            if (baseFields.size && !baseFields.has(pair.left)) throw new Error("该选择不在当前可用范围内，请重新分析");
            if (relatedFields.size && !relatedFields.has(pair.right)) throw new Error("该选择不在当前可用范围内，请重新分析");
          });
        }
        relationshipConfirmed = selection
          ? (selection.relationship_confirmed === true || selection.confirmed === true || selection.value === true)
          : value === true || value === "true";
        join.relationship_confirmed = relationshipConfirmed;
        recordSelectionResolution(question, relationshipConfirmed ? "已确认关联关系" : "未确认关联关系");
      }
      else if (key === "join.unmatched_policy") {
        const selection = optionSelection(question, value);
        const policy = selection?.policy || selection?.value || value;
        if (!UNMATCHED_POLICIES.includes(policy)) throw new Error("该选择不在当前可用范围内，请重新分析");
        if (!join) join = { table_name: "", on: [], report_date_field: "", relationship_confirmed: false, unmatched_policy: "unresolved" };
        unmatchedPolicy = policy;
        join.unmatched_policy = policy;
        recordSelectionResolution(question, `明确选择 ${selectionLabel(question, selection, policy)}`);
      }
      else if (key === "join.report_date_field") {
        const selection = optionSelection(question, value);
        const fieldName = selection?.field || selection?.value || value;
        const column = relatedColumns.find((item) => item.column_name === fieldName);
        if (!column || String(column.data_type || "").trim().toLowerCase() !== "date") throw new Error("该选择不在当前可用范围内，请重新分析");
        if (!join) join = { table_name: "", on: [], report_date_field: "", relationship_confirmed: false, unmatched_policy: "unresolved" };
        join.report_date_field = fieldName;
        recordSelectionResolution(question, `明确选择 ${selectionLabel(question, selection, fieldName)}`);
      }
      else if (fieldTarget(key)?.index != null || (simpleFormula && fieldTarget(key))) {
        setGroup(bindComparisonField(readComparison(), question, value, columnsForTable));
        recordSelectionResolution(question, `明确选择 ${question.options.find((option) => option.value === value)?.label || value}`);
      }
      else if (key === "expression.left" && (metadata?.columns || []).some((column) => column.column_name === value)) {
        left.value = value;
        recordSelectionResolution(question, `明确选择 ${question.options.find((option) => option.value === value)?.label || value}`);
      }
      else if (key === "expression.right") {
        const pool = rightTable === "related" ? relatedColumns : (metadata?.columns || []);
        if (!pool.some((column) => column.column_name === value)) throw new Error("该选择不在当前可用范围内，请重新分析");
        right.value = value;
        recordSelectionResolution(question, `明确选择 ${question.options.find((option) => option.value === value)?.label || value}`);
      }
      else if (key === "report_date_field" && (metadata?.columns || []).some((column) => column.column_name === value && String(column.data_type || "").trim().toLowerCase() === "date")) reportDateField = value;
      else if (key === "business_key" && (metadata?.columns || []).some((column) => column.column_name === value)) businessKey.value = value;
      else if (key === "report_category" && question?.options?.some((option) => option.value === value)
          && Array.from(category.options).some((option) => option.value === value)) category.value = value;
      else if (key === "null_policy" && value === "skip") nullPolicy.value = value;
      else throw new Error("该选择不在当前可用范围内，请重新分析");
      if (["report_date_field", "business_key", "report_category", "null_policy"].includes(key)) {
        recordSelectionResolution(question, `明确选择 ${selectionLabel(question, value, value)}`);
      }
      const selectedName = question?.options?.find((option) => option.value === value)?.rule_name;
      if (fieldTarget(key) && typeof selectedName === "string" && selectedName.trim()) name.value = selectedName.trim();
      changed();
    },
    focusRequest() { request.focus?.(); },
    setAnalyzing(loading) {
      parse.textContent = loading ? "AI 分析中…" : reanalysis ? "应用修改 →" : "✦ AI 分析";
      parse.classList.toggle("is-loading", Boolean(loading));
      parse.disabled = Boolean(loading) || state.modelsStatus !== "success" || !state.models.length;
      cancelEdit.disabled = Boolean(loading);
      request.disabled = Boolean(loading);
      source.disabled = Boolean(loading);
      model.disabled = Boolean(loading);
      modelTestButton.disabled = Boolean(loading) || modelTesting;
    },
    lockInputs(locked) {
      if (locked) [request, source, model, parse, modelTestButton, cancelEdit].forEach((control) => { control.disabled = true; });
    },
    setBusy(busy) {
      describe.disabled = busy || !source.value || !table.value.trim();
      parse.disabled = busy || state.modelsStatus !== "success" || !state.models.length;
      modelTestButton.disabled = busy || modelTesting;
    },
    validateBasics() {
      const payload = read();
      const missing = [];
      if (isAiMode) {
        // AI 模式：名称、目标表与分类由分析自动生成，只校验数据源与需求描述。
        if (!payload.source_id || !payload.dialect) missing.push("有效数据源");
        if (!payload.request_text) missing.push("需求描述");
      } else {
        if (!payload.name) missing.push("规则名称");
        if (!payload.source_id || !payload.dialect) missing.push("有效数据源");
        if (!payload.report_category) missing.push("监管报送分类");
        if (!payload.table_name) missing.push("目标表");
        if (!metadata) missing.push("真实表结构（请点击读取表结构）");
      }
      if (missing.length) throw new Error(`请先完善：${missing.join("、")}`);
      return payload;
    },
    validateForParse() {
      const payload = read();
      if (!payload.request_text) throw new Error("请先填写需求描述");
      if (!payload.source_id || !payload.dialect) throw new Error("请先选择有效数据源");
      return payload;
    },
    validateForSave() {
      if (candidateIncomplete) throw new Error("需求仍需澄清，尚无可保存的规则，请补充需求后重新生成");
      const payload = read();
      const missing = [];
      if (!payload.name) missing.push("规则名称");
      if (!payload.source_id || !payload.dialect) missing.push("有效数据源");
      if (!isAiMode && !payload.report_category) missing.push("监管报送分类");
      if (!payload.table_name) missing.push("目标表");
      if (!payload.business_key) missing.push("业务主键");
      if (isAiMode && !reportDateField) missing.push("校验日期字段");
      const conditions = comparisons(payload.expression);
      if (isGrouped(payload.expression) && !hasComparison(payload.expression)) missing.push("完整的组合条件（2–8 项）");
      for (const condition of conditions) {
        if (!condition.left) missing.push("左比较字段");
        if (isUnaryExpressionOp(condition.op)) continue;
        if (condition.right_type === "value") {
          if (isKeywordOperator(condition.op)) {
            if (!Array.isArray(condition.right) || !condition.right.length || condition.right.length > 50
              || condition.right.some((word) => typeof word !== "string" || !word || [...word].length > 200)) missing.push("1 至 50 个非空关键词，每词最多 200 字");
          } else if (typeof condition.right === "string") {
            if (!["eq", "neq"].includes(condition.op) || !condition.right || condition.right.length > 200) missing.push("文本常量仅支持非空的相等或不相等比较");
          } else if (!Number.isFinite(condition.right)) missing.push("非空有限数值常量");
        } else if (!condition.right) missing.push("右比较字段");
      }
      if (!payload.violation_message) missing.push("异常说明");
      if (!metadata) missing.push("真实表结构（请点击读取表结构）");
      if (missing.length) throw new Error(`请先完善：${missing.join("、")}`);
      const fields = new Set((metadata.columns || []).map((column) => column.column_name));
      const relatedFields = new Set(relatedColumns.map((column) => column.column_name));
      const requiredFields = [payload.business_key, ...conditions.flatMap((item) => operandFields(item, "left"))];
      requiredFields.forEach((fieldName) => {
        if (!fields.has(fieldName)) throw new Error(`字段 ${fieldName} 不在当前真实表结构中，请重新选择`);
      });
      for (const condition of conditions) {
        if (isUnaryExpressionOp(condition.op) || condition.right_type === "value") continue;
        const targetTable = condition.right_table === "related" ? "related" : "base";
        const pool = targetTable === "related" ? relatedFields : fields;
        for (const fieldName of operandFields(condition, "right")) {
          if (!pool.has(fieldName)) throw new Error(`右字段 ${fieldName} 不在${targetTable === "related" ? "关联表" : "当前真实表"}结构中，请重新选择`);
        }
      }
      (payload.filters || []).forEach((filter, index) => {
        if (filter.invalid) throw new Error(`筛选条件 ${index + 1}：${filter.invalid}`);
        const pool = filter.table === "related" ? relatedFields : fields;
        if (!filter.field || !pool.has(filter.field)) throw new Error(`筛选条件 ${index + 1} 字段不在真实表结构中，请重新选择`);
        if (filter.confirmed !== true) throw new Error(`筛选条件 ${index + 1} 尚未确认口径，请先选择真实候选`);
      });
      if (payload.join && payload.join.table_name) {
        if (!Array.isArray(payload.join.on) || !payload.join.on.length) throw new Error("关联字段尚未确认");
        payload.join.on.forEach((pair, index) => {
          if (!pair.left || !fields.has(pair.left)) throw new Error(`关联字段 ${index + 1} 左侧不在主表真实字段中`);
          if (!pair.right || !relatedFields.has(pair.right)) throw new Error(`关联字段 ${index + 1} 右侧不在关联表真实字段中`);
        });
        if (!payload.join.report_date_field || !relatedFields.has(payload.join.report_date_field)) {
          throw new Error("关联表校验日期尚未确认");
        }
      }
      return payload;
    },
  };

  function setMetadata(value) {
    metadata = value;
    if (!metadata) {
      clearRelationEvidence();
      group.render();
      persistedMappingVersion = "";
      setColumnOptions([], {});
      metadataStatus.textContent = isAiMode
        ? "数据源已变化，请重新发起 AI 分析"
        : "数据源或表已变化，请重新读取真实表结构";
      metadataStatus.classList.remove("is-success");
      return;
    }
    persistedMappingVersion = metadata.mapping_version || "";
    if (Array.isArray(metadata.related_columns)) relatedColumns = [...metadata.related_columns];
    group.render();
    renderFormula();
    const current = read();
    setColumnOptions(metadata.columns || [], {
      businessKey: current.business_key,
      left: typeof current.expression.left === "string" ? current.expression.left : "",
      right: current.expression.right_type !== "value" && typeof current.expression.right === "string" ? current.expression.right : "",
    }, rightTable === "related" ? relatedColumns : null);
    const hasReportDate = (metadata.columns || []).some((column) => column.column_name === reportDateField);
    if (!hasReportDate && isAiMode) reportDateField = "";
    metadataStatus.textContent = `已读取 ${(metadata.columns || []).length} 个真实字段，映射版本 ${metadata.mapping_version || "未返回"}。${hasReportDate ? "" : "还需从文档日期字段中明确校验日期，不能编造 report_date。"}`;
    metadataStatus.classList.toggle("is-warning", !hasReportDate);
    metadataStatus.classList.add("is-success");
    metadataStatus.classList.remove("is-error");
    invalidateReviewAnswers();
  }
}
