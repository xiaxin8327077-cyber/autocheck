import { button, element } from "./dom.js";
import { aiIcon } from "./ai_visuals.js";

const OPERATORS = {
  lt: "小于", lte: "小于或等于", gt: "大于", gte: "大于或等于", eq: "为", neq: "不为",
  is_null: "为空", is_not_null: "不为空",
};

function columnLabel(candidate, name) {
  const pools = [candidate.columns || []];
  if (candidate.expression?.right_table === "related" || candidate.related_columns) pools.push(candidate.related_columns || []);
  for (const pool of pools) {
    const column = pool.find((item) => item.column_name === name);
    if (column) return column.comment || name || "待确定的指标";
  }
  return name || "待确定的指标";
}

const FILTER_OP_LABELS = {
  lt: "早于", lte: "不晚于", gt: "晚于", gte: "不早于", eq: "为", neq: "不为",
  in: "属于", not_in: "不属于", is_null: "为空", is_not_null: "不为空",
};

function filterText(candidate, filter) {
  const label = columnLabel(candidate, filter.field);
  const op = FILTER_OP_LABELS[filter.op] || "筛选";
  if (filter.op === "is_null" || filter.op === "is_not_null") return `${label}${op}`;
  let value = filter.value;
  if (value === null || value === undefined || value === "") value = "待确认";
  else if (Array.isArray(value)) value = value.length ? value.join("、") : "待确认";
  return `${label}${op}${value}`;
}

function candidateFiltersText(candidate) {
  const filters = Array.isArray(candidate.filters) ? candidate.filters : [];
  if (!filters.length) return "";
  return `筛选条件：${filters.map((filter) => filterText(candidate, filter)).join("，且 ")}`;
}

function candidateJoinText(candidate) {
  const join = candidate.join;
  if (!join || !join.table_name) return "";
  const on = Array.isArray(join.on) ? join.on : [];
  const pairs = on.map((pair) => `${pair.left} = ${pair.right}`).join("，");
  const date = join.report_date_field || "关联日期待确认";
  return `关联 ${join.table_name}（${pairs || "关联字段待确认"}），关联日期 ${date}`;
}

function candidateDateText(candidate) {
  const main = candidate.report_date_field || "主表日期待确认";
  const join = candidate.join?.report_date_field ? `，关联日期 ${candidate.join.report_date_field}` : "";
  return `校验日期：${main}${join}`;
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

function optionKey(option, index) {
  if (option?.selection) {
    const selection = option.selection;
    return `selection:${selection.table || ""}:${selection.field || ""}:${selection.op || ""}:${String(selection.value ?? "")}`;
  }
  return String(option?.value ?? index);
}

function selectionKey(selection) {
  return `selection:${selection?.table || ""}:${selection?.field || ""}:${selection?.op || ""}:${String(selection?.value ?? "")}`;
}

export function candidateCondition(candidate) {
  const expression = candidate.expression || {};
  const left = columnLabel(candidate, expression.left);
  const opLabel = OPERATORS[expression.op] || "比较";
  if (expression.op === "is_null" || expression.op === "is_not_null") return `${left}${opLabel}`;
  const right = expression.right_type === "value" ? String(expression.right ?? "待确定值") : columnLabel(candidate, expression.right);
  return `${left}${opLabel} ${right}`;
}

let choiceSerial = 0;
export function createAiCandidatePanel({ listen = (node, event, fn) => node.addEventListener(event, fn), onEdit, onChoice, onRetry, notify } = {}) {
  const root = element("section", { className: "dv-ai-result" });
  const radioName = `dv-ai-meaning-${++choiceSerial}`;
  let selectedRadio = null;
  let removers = [];
  function action(label, handler, className = "dv-ai-text-button") {
    const control = button(label, { className });
    removers.push(listen(control, "click", handler));
    return control;
  }
  return {
    element: root,
    focusSelected() { selectedRadio?.focus?.(); },
    update(candidate, context = {}, { loading = false, error = "", stale = false, preview = null, selectedChoice = null, lastChoice = null } = {}) {
      selectedRadio = null;
      removers.forEach((remove) => remove?.());
      removers = [];
      root.replaceChildren();
      if (loading) {
        root.append(element("p", { className: "dv-loading", text: "正在理解需求并生成校验建议…" }));
        return;
      }
      if (error) {
        root.append(element("p", { className: "dv-feedback is-error", text: error }), action("修改需求后重新分析", onEdit));
        return;
      }
      if (!candidate) return;
      if (stale) {
        root.append(element("div", { className: "dv-notice is-warning", text: "需求或数据源已修改，请重新分析。旧 SQL 和测试结果不会用于当前需求。" }), action("修改需求并重新分析", onEdit));
        return;
      }
      const question = candidate.questions?.[0];
      const incomplete = candidate.status === "needs_clarification" || candidate.rule_type !== "field_compare";
      const condition = candidateCondition(candidate);
      root.append(element("div", { className: `dv-ai-result-status${incomplete || question ? " is-warning" : ""}` },
        aiIcon(question ? "question" : incomplete ? "info" : "check"),
        element("span", { text: question ? "有一个业务口径需要确认" : incomplete ? "还需要补充一个信息" : "已生成草稿建议" })));
      if (question) {
        root.append(element("h2", { className: "dv-ai-conclusion", text: question.text }),
          element("p", { className: "dv-ai-result-description", text: question.id === "report_date_field" ? "请确认记录所属的业务日期。仅生成 SQL 预览，不会重新调用 AI，已选金额口径会保留。" : `找到了${question.options.length === 2 ? "两个" : question.options.length + "个"}可能的口径。选一个就能继续分析，\n不需要填写表名、字段或处理说明。` }));
        const choices = element("fieldset", { className: "dv-ai-choices", attrs: { "aria-label": question.text } });
        question.options.forEach((option, index) => {
          const key = optionKey(option, index);
          const wasLast = lastChoice?.id === question.id && option.selection
            && selectionKey(lastChoice.value) === key;
          const selectedKey = selectedChoice?.id === question.id
            ? (selectedChoice.key || (selectedChoice.value && typeof selectedChoice.value === "object"
              ? selectionKey(selectedChoice.value)
              : String(selectedChoice.value)))
            : "";
          const radio = element("input"); radio.type = "radio"; radio.name = radioName; radio.value = key;
          radio.checked = selectedKey === key;
          if (radio.checked) selectedRadio = radio;
          removers.push(listen(radio, "change", () => { if (radio.checked) onChoice?.(question.id, option.selection || option.value); }));
          choices.append(element("label", { className: `dv-ai-choice${radio.checked ? " is-selected" : ""}` }, radio,
            element("span", { className: "dv-ai-choice-body" },
              element("span", { className: "dv-ai-choice-title", text: option.label }),
              element("span", { className: "dv-ai-choice-note" }, ...optionDescriptionLines(option.description).map((line) =>
                element("span", { className: "dv-ai-choice-note-line", text: line })))),
            wasLast || option.tag ? element("span", { className: `dv-ai-choice-tail${wasLast ? " is-last" : ""}`,
              text: wasLast ? "上次" : option.tag }) : null));
        });
        root.append(choices, element("p", { className: "dv-ai-clarify-footnote" }, "都不是？", action("修改需求，补充一句说明", onEdit)));
        if (candidate.preview_error) root.append(element("p", { className: "dv-notice is-warning", attrs: { role: "alert" }, text: candidate.preview_error }));
        return;
      }
      if (incomplete) {
        const reasons = [...(candidate.unsupported_requirements || []), ...(candidate.uncertainties || [])];
        root.append(element("h2", { className: "dv-ai-conclusion", text: "暂时还不能生成完整校验建议" }),
          element("p", { className: "dv-ai-result-description", text: reasons[0] || "请补充要检查的业务对象和判断条件。" }),
          action("补充一句要求，继续分析", onEdit));
        if (reasons.length > 1) {
          root.append(element("details", { className: "dv-ai-reasoning" }, element("summary", { text: "查看其他需要补充的信息" }),
            element("ul", {}, reasons.slice(1).map((text) => element("li", { text })))));
        }
        return;
      }
      const facts = [
        element("div", {}, aiIcon("scope"), element("span", { className: "dv-muted", text: "检查范围" }), element("span", { text: candidate.scope_description || "所选项目数据（范围待核实）" })),
        element("div", {}, aiIcon("flag"), element("span", { className: "dv-muted", text: "提醒条件" }), element("span", { text: condition })),
      ];
      const relationText = [candidateFiltersText(candidate), candidateJoinText(candidate)].filter(Boolean).join("；");
      if (relationText) facts.push(element("div", {}, aiIcon("database"), element("span", { className: "dv-muted", text: "筛选与关联" }), element("span", { text: relationText })));
      const dateText = candidateDateText(candidate);
      if (dateText) facts.push(element("div", {}, aiIcon("scope"), element("span", { className: "dv-muted", text: "校验日期" }), element("span", { text: dateText })));
      if (candidate.null_policy === "zero") facts.push(element("div", {}, aiIcon("info"), element("span", { className: "dv-muted", text: "空值处理" }), element("span", { text: "数值比较：NULL按0处理" })));
      if (candidate.null_policy === "review") facts.push(element("div", {}, aiIcon("info"), element("span", { className: "dv-muted", text: "空值处理" }), element("span", { text: "系统处理：缺值单列核查" })));
      if (candidate.null_handling || candidate.null_evidence) {
        const evidence = candidate.null_evidence || candidate.null_handling;
        facts.push(element("div", {}, aiIcon("info"), element("span", { className: "dv-muted", text: "空值依据" }), element("span", { text: String(evidence) })));
      }
      root.append(element("h2", { className: "dv-ai-conclusion", text: `${condition}时，提示人工核实` }),
        element("p", { className: "dv-ai-result-description", text: candidate.violation_message || "找出符合以上条件的记录，交由人工核实；生成建议不代表测试通过。" }),
        element("div", { className: "dv-ai-business-facts" }, ...facts));
      if (/一般|通常|原则上/.test(context.request_text || context.description || "")) {
        root.append(element("div", { className: "dv-ai-soft-warning" }, aiIcon("info"),
          element("span", {}, element("strong", { text: "保留“一般”的含义 " }), "可能存在合理例外，命中后先核实，不一刀切判错。")));
      }
      const actualPreview = preview || candidate.preview;
      if (actualPreview?.sql_preview) {
        const sql = element("code", { text: actualPreview.sql_preview });
        const pre = element("pre", { className: "dv-ai-sql-code dv-scroll" }, sql);
        const copy = action("复制 SQL", async () => {
          try {
            if (!globalThis.navigator?.clipboard?.writeText) throw new Error("CLIPBOARD_UNAVAILABLE");
            await navigator.clipboard.writeText(sql.textContent);
            notify?.("已复制校验 SQL（未执行）", "success");
          } catch {
            if (document.createRange && globalThis.getSelection) {
              const range = document.createRange(); range.selectNodeContents(sql);
              const selection = globalThis.getSelection(); selection.removeAllRanges(); selection.addRange(range);
              notify?.("已选中 SQL，请按 Ctrl+C 复制", "info");
            } else notify?.("浏览器不允许复制，请手动选择 SQL", "warning");
          }
        });
        const params = actualPreview.sql_params || {};
        root.append(element("section", { className: "dv-ai-sql-preview" },
          element("div", { className: "dv-ai-sql-heading" }, element("div", {}, element("strong", { text: "校验 SQL" }),
            element("span", { className: "dv-muted", text: " 后端编译 · 只读预览，未执行" })), copy), pre,
          element("div", { className: "dv-ai-sql-params" },
            ...Object.entries(params).map(([key, value]) => element("span", { text: `${key}：${value === null || value === undefined ? "运行时传入" : String(value)}` })))));
      } else root.append(element("div", { className: "dv-notice is-warning", attrs: { role: "alert" } },
        element("p", { text: candidate.preview_error || "当前定义还不能编译 SQL，请检查文档与待确认口径。" }),
        candidate.parallel_blocked ? action("修改需求", onEdit) : onRetry ? action("重试生成预览", onRetry) : null));
      const pending = (candidate.uncertainties || []).filter((_item, index) => !candidate.uncertainty_resolutions?.[index]?.trim());
      const requirements = [...(candidate.unsupported_requirements || []), ...pending];
      if (requirements.length) {
        root.append(element("div", { className: "dv-ai-unresolved" }, element("strong", { text: "启用前还需要补充" }),
          element("p", { text: requirements[0] }), action("补充需求", onEdit)));
      }
      const more = [...(candidate.notices || []), ...requirements.slice(1)];
      root.append(element("details", { className: "dv-ai-reasoning" }, element("summary", {}, aiIcon("chevron"), "为什么这样判断 / 需要留意什么"),
        element("ul", {}, element("li", { text: "SQL 由后端根据结构化定义编译，不直接使用模型输出的 SQL。" }),
          element("li", { text: "可先检查并运行文档合成样本，再决定保存草稿或启用；预览测试不写规则。" }),
          ...more.map((text) => element("li", { text })))));
    },
  };
}
