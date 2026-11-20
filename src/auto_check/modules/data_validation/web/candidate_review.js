import { canChooseAllFields, candidateIssues, reviewCandidate } from "./state.js";
import { createRuleForm } from "./components/rule_form.js";

// 跟随批量保存接口的单次定义数量上限。
const MAX_BUSINESS_PLANS = 26;

// Compare document sets independent of ordering, retaining the types of dictionary codes.
function normalized(value) {
  if (Array.isArray(value)) return value.map(normalized).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalized(value[key])]));
  }
  return value;
}

function filterSelection(value) {
  return value && JSON.stringify(normalized({ table: value.table, field: value.field, op: value.op, value: value.value }));
}

function filterScope(candidate, question) {
  const match = /^filters\.(\d+)$/.exec(question.id);
  return match && candidate.semantic_intent?.scopes?.[Number(match[1])];
}

function canChooseScopeFields(candidate, question, scope) {
  if (candidate.analysis_protocol !== 2 || !scope?.category || !scope.fields?.length || !(question.options?.length > 1)) return false;
  const fields = new Set();
  for (const { selection } of question.options) {
    if (selection?.confirmed !== true || selection.table !== (scope.table || "base") || !scope.fields.includes(selection.field)
      || !["eq", "in"].includes(selection.op) || fields.has(selection.field)) return false;
    fields.add(selection.field);
  }
  return true;
}

function sharedFilter(candidate, question, scope) {
  if (!/^filters\.\d+$/.test(question.id) || !candidate.source_id || !candidate.table_name || !candidate.report_category || !candidate.mapping_version
      || !question.options?.length || !question.options.every((option) => option.selection?.field && option.selection.confirmed === true)) return null;
  const legacyStatus = !candidate.analysis_protocol && candidate.parallel_check && question.remember_scope === "active_status";
  if (!(candidate.analysis_protocol === 2 && scope?.category && scope.fields?.length) && !legacyStatus) return null;
  const related = question.options.some(({ selection }) => selection.table === "related");
  if (related && !candidate.join?.table_name) return null;
  const criteria = scope ? { ...scope } : { remember_scope: "active_status" };
  delete criteria.recommended;
  const snapshots = candidate.semantic_intent?.dictionary_snapshots?.[scope?.table || "base"];
  const dictionaries = Object.fromEntries((scope?.fields || []).map((field) => [field, snapshots?.[field]]));
  return JSON.stringify(normalized({
    source: candidate.source_id, table: candidate.table_name, category: candidate.report_category,
    mapping: candidate.mapping_version, related: related ? candidate.join : null, criteria, dictionaries,
    choices: question.options.map(({ selection }) => filterSelection(selection)),
  }));
}

export function collectBusinessQuestions(options) {
  const items = [];
  const shared = new Map();
  for (const option of options) {
    const candidate = option.candidate;
    const questions = candidate.questions || [];
    const represented = new Set(questions.flatMap((question) => [question.text, question.uncertainty]));
    const pending = (candidate.uncertainties || []).filter((note, i) => !candidate.uncertainty_resolutions?.[i]?.trim());
    // 旧候选的自由判断可能只是结构化问题的另一种表述，保留原文交给文档复核。
    const outstanding = !candidate.analysis_protocol && questions.length ? [] : pending;
    const notes = [...new Set([...(candidate.unsupported_requirements || []), ...outstanding, candidate.preview_error, candidate.parallel_blocked])]
      .filter((note) => note && !represented.has(note));
    if (!questions.length && !notes.length) notes.push(...candidateIssues(candidate));
    for (const question of [...questions, ...notes.map((text, i) => ({ id: `supplement.${i}`, text, options: [] }))]) {
      const scope = filterScope(candidate, question);
      const identity = sharedFilter(candidate, question, scope);
      let item = identity && shared.get(identity);
      if (!item || item.targets.some((target) => target.id === option.id)) {
        item = { key: JSON.stringify([option.id, question.id]), question, targets: [], labels: [],
          multiple: canChooseAllFields(question) || canChooseScopeFields(candidate, question, scope),
          dictionaries: scope?.category ? candidate.semantic_intent?.dictionary_snapshots : undefined };
        if (identity) shared.set(identity, item);
        items.push(item);
      }
      item.targets.push({ id: option.id, question });
      item.labels.push(option.label || candidate.rule_name || candidate.table_name);
      item.context = options.length > 1 ? [...new Set(item.labels)].join("、") : "";
    }
  }
  return items;
}

export function applyBusinessAnswers(options, items, answers, state, user, requestText) {
  const expandsScope = items.some(({ key, question, multiple }) =>
    multiple && question.id.startsWith("filters.") && answers.get(key)?.length > 1);
  let planCount = 0;
  return options.flatMap((option, index) => {
    const remainingOptions = options.length - index - 1;
    let variants = [option];
    for (const item of items) {
      const target = item.targets.find((entry) => entry.id === option.id);
      if (!target) continue;
      const question = target.question;
      if (!question.options?.length) continue;
      const input = answers.get(item.key);
      const selected = Array.isArray(input) && item.multiple ? input : [input];
      const choices = selected.map((value) => question.options.find((entry) => entry.value === value
        || (value?.field && entry.selection?.field && filterSelection(entry.selection) === filterSelection(value))
        || (entry.selection && JSON.stringify(entry.selection) === JSON.stringify(value))));
      if (!choices.length || choices.some((choice) => !choice)) throw new Error("已选业务口径发生变化，请重新选择");
      if (expandsScope && planCount + variants.length * choices.length + remainingOptions > MAX_BUSINESS_PLANS) {
        throw new Error(`本次选择会生成超过 ${MAX_BUSINESS_PLANS} 个方案，请减少勾选项后重试。`);
      }
      variants = variants.flatMap((variant) => choices.map((choice) => {
        const candidate = variant.candidate;
        const definition = reviewDefinition(candidate, state, user, requestText, question, choice);
        const split = choices.length > 1;
        const filterField = choice.selection?.field;
        if (split) {
          if (!choice.rule_name) definition.name = `${definition.name || variant.label} · ${filterField || choice.label}`;
          if (!filterField) definition.violation_message = `${choice.label}命中校验条件，请核实。`;
        }
        return { ...variant, ...(split ? { id: JSON.stringify([variant.id, question.id, choice.value ?? filterField]),
          label: definition.name, field_label: filterField ? variant.field_label : choice.label,
          match_reason: filterField ? "按所选筛选字段分别校验" : "按所选字段逐项校验" } : {}),
          candidate: { ...candidate, ...definition, rule_name: definition.name, preview: null, preview_request_error: "",
            questions: candidate.questions.filter((q) => q.id !== question.id) } };
      }));
    }
    planCount += variants.length;
    return variants;
  });
}

export function preparedOptions(options) {
  return options.map((option) => ({ ...option, candidate: reviewCandidate(option.candidate || {}) }));
}

export function reviewDefinition(candidate, state, user, requestText, question, choice) {
  const form = createRuleForm({ state, user, mode: "ai", listen: () => () => {} });
  form.reset({ definition: { ...candidate, description: candidate.description || requestText } });
  form.setMetadata({ columns: candidate.columns || [], related_columns: candidate.related_columns || [],
    project_columns: candidate.project_columns || [], project_table: candidate.project_table, mapping_version: candidate.mapping_version });
  form.applyCandidate(candidate, { regenerate: false });
  if (question) form.applyDecision(question.id, choice.selection || choice.value, question);
  const definition = form.read();
  form.disposeGroup();
  return definition;
}
