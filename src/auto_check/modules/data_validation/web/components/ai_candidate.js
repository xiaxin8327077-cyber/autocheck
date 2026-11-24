import { button, element } from "./dom.js";
import { aiIcon } from "./ai_visuals.js";
import { columnLabel, documentEvidence, filterValues, objectLabel, tableLabel } from "./candidate_evidence.js";
import { documentPreviewGap } from "../runtime.js";
import { formulaText, hasComparison, isGrouped } from "../comparisons.js";
import { ALL_FIELD_CHOICES, canChooseAllFields, candidateIssues, reviewCandidate, visibleSql } from "../state.js";

const OPERATORS = {
  lt: "小于", lte: "小于或等于", gt: "大于", gte: "大于或等于", eq: "为", neq: "不为",
  is_null: "为空", is_not_null: "不为空",
  contains_any: "包含任一关键词", not_contains_any: "不包含任何关键词",
};

const FILTER_OP_LABELS = {
  lt: "早于", lte: "不晚于", gt: "晚于", gte: "不早于", eq: "为", neq: "不为",
  in: "属于", not_in: "不属于", is_null: "为空", is_not_null: "不为空",
  contains_any: "包含任一关键词", not_contains_any: "不包含以下任何关键词",
};

function filterText(candidate, filter) {
  const label = columnLabel(candidate, filter.field, filter.table);
  const op = FILTER_OP_LABELS[filter.op] || "筛选";
  if (filter.op === "is_null" || filter.op === "is_not_null") return `${label}${op}`;
  const value = filterValues(candidate, filter).map((item) => item.label || item.value).join("、") || "待确认";
  return `${label}${op}${value}`;
}

export function candidateFiltersText(candidate) {
  const filters = Array.isArray(candidate.filters) ? candidate.filters : [];
  if (!filters.length) return "";
  return filters.map((filter) => filterText(candidate, filter)).join("，且 ");
}

function candidateJoinText(candidate) {
  const join = candidate.join;
  if (!join || !join.table_name) return "";
  const on = Array.isArray(join.on) ? join.on : [];
  const pairs = on.map((pair) => {
    const left = columnLabel(candidate, pair.left), right = columnLabel(candidate, pair.right, "related");
    return left === right ? left : `${left}对应${right}`;
  });
  return `${tableLabel(candidate, {}, true)}${pairs.length ? "，按" + pairs.join("、") + (join.right_aggregate === "sum" ? "汇总后核对" : "匹配") : ""}`;
}

function candidateDateText(candidate) {
  const main = columnLabel(candidate, candidate.report_date_field);
  const related = columnLabel(candidate, candidate.join?.report_date_field, "related");
  const dates = [main, related && "关联表的" + related].filter(Boolean).join("、");
  return dates ? `${dates}等于本次报送日期` : "";
}

function optionDescriptionLines(description) {
  const text = description || "按这个口径理解并生成校验建议";
  const breaks = [];
  let expected = 1;
  for (const match of text.matchAll(/(^|[\s。；;])([1-9]\d?)[.．、)）](?!\d)/gu)) {
    if (Number(match[2]) !== expected) continue;
    breaks.push(match.index + match[1].length);
    expected += 1;
  }
  if (breaks.length < 2) return [text];
  const bounds = [...new Set([0, ...breaks, text.length])];
  return bounds.slice(1).map((end, index) => text.slice(bounds[index], end).trim()).filter(Boolean);
}

export function candidateCondition(candidate) {
  const expression = candidate.expression || {};
  if (isGrouped(expression)) {
    const conditions = expression.conditions.map((item) => candidateCondition({ ...candidate, expression: item }));
    return (expression.logic === "all" ? "同时满足：" : "满足任一项：") + conditions.join(expression.logic === "all" ? "，且" : "，或");
  }
  const label = (name) => columnLabel(candidate, name);
  const left = expression.left_type === "formula" ? formulaText(expression.left, label) : label(expression.left) || "待确定的指标";
  const opLabel = OPERATORS[expression.op] || "比较";
  if (expression.op === "is_null" || expression.op === "is_not_null") return `${left}${opLabel}`;
  let right = expression.right_type === "formula" ? formulaText(expression.right, label)
    : expression.right_type === "value" ? String(expression.right ?? "待确定值")
      : columnLabel(candidate, expression.right, expression.right_table) || "待确定的指标";
  if (Array.isArray(expression.right)) right = expression.right.map((word) => `「${word}」`).join("、");
  if (expression.right_type !== "value" && expression.right_table === "related") {
    const related = tableLabel(candidate, {}, true);
    if (related) right = `${related}的${right}`;
    if (candidate.join?.right_aggregate === "sum") right += "合计";
  }
  return `${left}${opLabel} ${right}`;
}

export function candidateRuleName(candidate) {
  return candidate.name?.trim() || candidate.rule_name?.trim() || candidateCondition(candidate);
}

function modelJudgmentDetails(candidate) {
  const selection = candidate.model_judgments?.select_table;
  const generation = candidate.model_judgments?.generate_rule;
  if (!selection && !generation) return null;
  const lines = [];
  const knowledge = candidate.knowledge_context;
  if (knowledge?.topics?.length) lines.push(`本次提供的业务知识（v${knowledge.revision}）：${knowledge.topics.join("、")}`);
  if (selection) {
    lines.push(`模型选表：${selection.table || "未指定"}`);
    if (selection.related_table) lines.push(`模型选择的关联表：${selection.related_table}`);
    if (selection.report_category) lines.push(`模型选择的报送分类：${selection.report_category}`);
    for (const reason of [...(selection.uncertainties || []), ...(selection.unsupported_requirements || [])]) {
      lines.push(`选表时的判断：${reason}`);
    }
  }
  if (generation) {
    const expression = generation.expression;
    lines.push(`模型生成的条件：${hasComparison(expression) ? candidateCondition({ expression }) : "未生成"}`);
    const filters = generation.filters?.filter((item) => item.field && item.op) || [];
    if (filters.length) lines.push(`模型建议的筛选：${filters.map((filter) => filterText({}, filter)).join("，且 ")}`);
    const policies = { review: "缺值单列核查", skip: "跳过空值", zero: "空值按 0", unresolved: "未确定" };
    if (policies[generation.null_policy]) lines.push(`模型建议的空值处理：${policies[generation.null_policy]}`);
    for (const reason of [...(generation.uncertainties || []), ...(generation.unsupported_requirements || [])]) {
      lines.push(`生成时的判断：${reason}`);
    }
  }
  if (candidate.table_name) lines.push(`系统核对的目标表：${candidate.table_name}`);
  if (candidate.rule_type === "field_compare" && hasComparison(candidate.expression)) {
    lines.push(`当前校验条件：${candidateCondition(candidate)}`);
    const scope = candidateFiltersText(candidate);
    if (scope) lines.push(`当前${scope}`);
  }
  return element("details", { className: "dv-ai-reasoning" },
    element("summary", {}, aiIcon("chevron"), "模型判断"),
    element("ul", {}, ...lines.map((text) => element("li", { text }))));
}

let choiceSerial = 0;
export function createAiCandidatePanel({ listen = (node, event, fn) => node.addEventListener(event, fn), onEdit, onChoice, onRetry, onReanalyze, onTestSql, notify } = {}) {
  const root = element("section", { className: "dv-ai-result" });
  const radioName = `dv-ai-meaning-${++choiceSerial}`;
  let selectedRadio = null;
  let focusedOption = null;
  let removers = [];
  let actionsLocked = false;
  function action(label, handler, className = "dv-ai-text-button") {
    const control = button(label, { className, disabled: actionsLocked });
    removers.push(listen(control, "click", (event) => { if (!actionsLocked) return handler?.(event); }));
    return control;
  }
  return {
    element: root,
    focusSelected() { selectedRadio?.focus?.(); },
    update(candidate, context = {}, { loading = false, error = "", stale = false, preview = null, selectedChoice = null, lastChoice = null, canRecheck = false, option = null, locked = false } = {}) {
      actionsLocked = locked;
      selectedRadio = null;
      removers.forEach((remove) => remove?.());
      removers = [];
      root.replaceChildren();
      if (loading) {
        root.append(element("div", { className: "dv-ai-candidate-loading", attrs: { role: "status" } },
          element("span", { className: "dv-ai-loading-dots", attrs: { "aria-hidden": "true" } },
            element("span"), element("span"), element("span")),
          element("span", { text: "正在理解需求并生成校验建议…" })));
        return;
      }
      if (error) {
        root.append(element("p", { className: "dv-feedback is-error", text: error }), action("修改需求后重新分析", onEdit));
        return;
      }
      if (!candidate) return;
      if (stale) {
        root.append(element("div", { className: "dv-notice is-warning", text: "需求已修改。点击「应用修改」更新规则和预览。" }));
        return;
      }
      if (candidate.analysis_context_changed) {
        root.append(element("p", { className: "dv-notice is-warning", text: candidate.preview_error }),
          action("按最新口径重新分析", onReanalyze));
        return;
      }
      candidate = reviewCandidate(candidate, preview || candidate.preview);
      const question = candidate.questions?.[0];
      const incomplete = candidate.status === "needs_clarification" || candidate.rule_type !== "field_compare";
      const documentGap = documentPreviewGap(candidate);
      const issues = candidateIssues(candidate);
      const subsequent = (candidate.questions || []).slice(1).map((item) => canChooseAllFields(item)
        ? `${item.text}（可选“全部都要”）` : item.text);
      const questionNotes = new Set((candidate.questions || []).flatMap((item) => [item.text, item.uncertainty]));
      const outstanding = [...new Set([...subsequent, ...issues.filter((text) => !questionNotes.has(text))])];
      const renderOutstanding = () => {
        if (outstanding.length) root.append(element("div", { className: "dv-ai-unresolved" },
          element("strong", { text: question ? "本方案还需确认或补充" : "生成 SQL 前需要补充" }),
          element("ul", {}, outstanding.map((text) => element("li", { text }))),
          question ? null : action("补充需求", onEdit)));
      };
      const judgmentDetails = modelJudgmentDetails(candidate);
      root.append(element("div", { className: `dv-ai-result-status${incomplete || question || issues.length ? " is-warning" : ""}` },
        aiIcon(question ? "question" : incomplete || issues.length ? "info" : "check"),
        element("span", { text: question ? "请确认业务口径" : documentGap ? "暂时无法预览" : incomplete || issues.length ? "待补充需求" : "已生成校验建议" })));
      if (question) {
        const multiple = canChooseAllFields(question);
        root.append(element("h2", { className: "dv-ai-conclusion", text: question.text }),
          element("p", { className: "dv-ai-result-description", text: multiple
            ? "可勾选一个或多个指标，每个指标生成一条规则。" : "选择适用的口径并确认。全部事项确认后，系统才会生成校验 SQL。" }));
        const choices = element("fieldset", { className: "dv-ai-choices", attrs: { "aria-label": question.text } });
        const chosen = multiple && selectedChoice?.id === question.id && Array.isArray(selectedChoice.value)
          ? selectedChoice.value : [];
        const options = multiple ? [...question.options, {
          value: ALL_FIELD_CHOICES, label: "全部都要", description: "每个字段生成一条规则。",
        }] : question.options;
        options.forEach((option, index) => {
          const value = option.selection || option.value;
          const wasLast = lastChoice?.id === question.id && lastChoice.value === value;
          const radio = element("input"); radio.type = "radio"; radio.name = radioName; radio.value = String(option.value ?? index);
          radio.disabled = locked;
          if (multiple) radio.type = "checkbox";
          const selectAll = value === ALL_FIELD_CHOICES;
          radio.checked = multiple
            ? (selectAll ? chosen.length === question.options.length : chosen.includes(value))
            : selectedChoice?.id === question.id && selectedChoice.value === value;
          if (focusedOption?.id === question.id ? focusedOption.index === index : radio.checked) selectedRadio = radio;
          removers.push(listen(radio, "change", () => {
            if (actionsLocked) return;
            focusedOption = { id: question.id, index };
            if (!multiple) {
              if (radio.checked) onChoice?.(question.id, value);
              return;
            }
            const values = question.options.map((item) => item.value).filter((item) =>
              selectAll || item === value ? radio.checked : chosen.includes(item));
            onChoice?.(question.id, values);
          }));
          choices.append(element("label", { className: `dv-ai-choice${radio.checked ? " is-selected" : ""}` }, radio,
            element("span", { className: "dv-ai-choice-body" },
              element("span", { className: "dv-ai-choice-title", text: option.label }),
              element("span", { className: "dv-ai-choice-note" }, ...optionDescriptionLines(option.description).map((line) =>
                element("span", { className: "dv-ai-choice-note-line", text: line })))),
            wasLast || option.tag ? element("span", { className: `dv-ai-choice-tail${wasLast ? " is-last" : ""}`,
              text: wasLast ? "上次" : option.tag }) : null));
        });
        root.append(choices, element("p", { className: "dv-ai-clarify-footnote" }, "都不是？", action("修改需求，补充一句说明", onEdit)));
        if (candidate.preview_request_error) root.append(element("p", { className: "dv-notice is-warning", attrs: { role: "alert" }, text: candidate.preview_request_error }));
        renderOutstanding();
        if (judgmentDetails) root.append(judgmentDetails);
        return;
      }
      if (incomplete) {
        root.append(element("h2", { className: "dv-ai-conclusion", text: "暂时还不能生成完整校验建议" }));
        renderOutstanding();
        if (judgmentDetails) root.append(judgmentDetails);
        return;
      }
      const facts = [];
      function fact(icon, label, value) {
        if (value) facts.push(element("div", {}, aiIcon(icon), element("span", { className: "dv-muted", text: label }), element("span", { text: value })));
      }
      fact("scope", "检查对象", objectLabel(candidate, option || {}));
      fact("database", "适用范围", candidateFiltersText(candidate));
      fact("database", "关联核对", candidateJoinText(candidate));
      fact("scope", "检查日期", candidateDateText(candidate));
      if (candidate.null_policy === "zero") facts.push(element("div", {}, aiIcon("info"), element("span", { className: "dv-muted", text: "空值处理" }), element("span", { text: "数值比较：NULL按0处理" })));
      if (candidate.null_policy === "review") facts.push(element("div", {}, aiIcon("info"), element("span", { className: "dv-muted", text: "空值处理" }), element("span", { text: "系统处理：缺值单列核查" })));
      const nullEvidence = [...new Set((candidate.null_evidence || [])
        .map((evidence) => evidence?.source?.trim()).filter(Boolean))];
      root.append(element("h2", { className: "dv-ai-conclusion", text: candidateRuleName(candidate) }),
        element("div", { className: "dv-ai-business-facts" }, ...facts));
      if (!option) root.append(documentEvidence(candidate));
      const qualifier = (context.request_text || context.description || "").match(/一般|通常|原则上/)?.[0];
      if (qualifier) {
        root.append(element("div", { className: "dv-ai-soft-warning" }, aiIcon("info"),
          element("span", {}, element("strong", { text: `保留“${qualifier}”的含义 ` }), "可能存在合理例外，命中后先核实。")));
      }
      if (issues.length) {
        renderOutstanding();
        if (canRecheck && onRetry) {
          if (candidate.preview_request_error) root.append(element("p", { text: candidate.preview_request_error }));
          root.append(action(candidate.preview_request_error ? "重试核对文档" : "重新核对已选口径", onRetry));
        }
        if (judgmentDetails) root.append(judgmentDetails);
        return;
      }
      const actualPreview = candidate.preview;
      if (actualPreview?.sql_preview) {
        const display = visibleSql(actualPreview, "sql_preview");
        const sql = element("code", { text: display || "SQL 参数暂无法完整还原。" });
        const pre = element("pre", { className: "dv-ai-sql-code dv-scroll" }, sql);
        const copy = action("复制 SQL", async () => {
          try {
            if (!globalThis.navigator?.clipboard?.writeText) throw new Error("CLIPBOARD_UNAVAILABLE");
            await navigator.clipboard.writeText(sql.textContent);
            notify?.("已复制校验 SQL", "success");
          } catch {
            if (document.createRange && globalThis.getSelection) {
              const range = document.createRange(); range.selectNodeContents(sql);
              const selection = globalThis.getSelection(); selection.removeAllRanges(); selection.addRange(range);
              notify?.("已选中 SQL，请按 Ctrl+C 复制", "info");
            } else notify?.("浏览器不允许复制，请手动选择 SQL", "warning");
          }
        });
        copy.disabled = !display;
        const params = Object.fromEntries(Object.entries(actualPreview.sql_display_params ?? actualPreview.sql_params ?? {})
          .filter(([name]) => name === "report_date"));
        const testSql = action("测试运行", () => onTestSql?.(actualPreview));
        testSql.dataset.capability = "dv.test";
        testSql.disabled = locked || !onTestSql;
        root.append(element("section", { className: "dv-ai-sql-preview" },
          element("div", { className: "dv-ai-sql-heading" }, element("div", {}, element("strong", { text: "校验 SQL" }),
            element("span", { className: "dv-muted", text: " 后端编译 · 只读预览" })),
            element("div", { className: "dv-ai-sql-actions" }, testSql, copy)), pre,
          element("div", { className: "dv-ai-sql-params" },
            ...Object.entries(params).map(([key, value]) => element("span", { text: `${key}：${value === null || value === undefined ? "运行时传入" : String(value)}` })))));
      } else root.append(element("div", { className: "dv-notice is-warning", attrs: { role: "alert" } },
        element("p", { text: candidate.preview_request_error || "业务口径已确认，可生成校验 SQL。" }),
        onRetry ? action(candidate.preview_request_error ? "重试生成预览" : "生成 SQL 预览", onRetry) : null));
      const more = (candidate.notices || []).filter((text) => !nullEvidence.includes(String(text).trim()));
      root.append(element("details", { className: "dv-ai-reasoning" }, element("summary", {}, aiIcon("chevron"), "为什么这样判断 / 需要留意什么"),
        element("ul", {}, candidate.violation_message ? element("li", { text: `命中后的提示：${candidate.violation_message}` }) : null,
          element("li", { text: "SQL 由后端根据结构化定义编译，不直接使用模型输出的 SQL。" }),
          element("li", { text: "先检查并运行测试用例，通过后可保存并启用所选方案；预览测试不写规则。" }),
          ...more.map((text) => element("li", { text })))));
      if (judgmentDetails) root.append(judgmentDetails);
    },
  };
}
