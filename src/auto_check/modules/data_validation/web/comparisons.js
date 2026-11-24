export function isGrouped(expression) {
  return Array.isArray(expression?.conditions);
}

export function isKeywordOperator(op) {
  return op === "contains_any" || op === "not_contains_any";
}

export function comparisons(expression) {
  return isGrouped(expression) ? expression.conditions : [expression || {}];
}

export function isFormulaComparison(item) {
  return item?.left_type === "formula" || item?.right_type === "formula";
}

export function operandFields(item, side) {
  if (item[side + "_type"] === "value" || !item[side]) return [];
  if (item[side + "_type"] !== "formula") return [item[side]];
  function fields(node) {
    if (typeof node?.field === "string") return [node.field];
    return node?.op ? [...fields(node.left), ...fields(node.right)] : [];
  }
  return fields(item[side]);
}

export function formulaText(node, fieldLabel) {
  if (typeof node?.field === "string") return fieldLabel(node.field);
  if (Number.isFinite(node?.value)) return String(node.value);
  if (!["+", "-", "*", "/"].includes(node?.op)) return "待确定的公式";
  return "(" + formulaText(node.left, fieldLabel) + " " + node.op + " " + formulaText(node.right, fieldLabel) + ")";
}

export function comparisonFields(expression) {
  return [...new Set(comparisons(expression).flatMap((item) => isFormulaComparison(item)
    ? [...operandFields(item, "left"), ...operandFields(item, "right")] : operandFields(item, "left")))];
}

export function hasComparison(expression) {
  return (!isGrouped(expression) || (["any", "all"].includes(expression.logic)
    && expression.conditions.length >= 2 && expression.conditions.length <= 8))
    && comparisons(expression).every((item) => item?.left && item.op);
}

export function fieldTarget(path) {
  const match = /^expression\.(?:conditions\.([0-7])\.)?(left|right)((?:\.(?:left|right))*\.field)?$/.exec(path || "");
  return match && { index: match[1] === undefined ? null : Number(match[1]), side: match[2],
    ...(match[3] ? { formulaPath: match[3].slice(1).split(".").slice(0, -1) } : {}) };
}

export function bindComparisonField(expression, question, field, columnsForTable) {
  const paths = [...new Set([question.id, ...(question.targets || [])])];
  if (paths.length > 1 && paths.some((path) => fieldTarget(path)?.formulaPath)) {
    throw new Error("公式中的字段须按各自的运算位置确认");
  }
  const result = JSON.parse(JSON.stringify(expression));
  for (const path of paths) {
    const target = fieldTarget(path);
    if (!target || (target.index !== null) !== isGrouped(result)) throw new Error("字段选择与当前规则条件不一致");
    const condition = target.index === null ? result : result.conditions[target.index];
    if (!condition) throw new Error("待确认的比较条件已变化");
    const table = target.side === "right" && condition.right_table === "related" ? "related" : "base";
    if (!columnsForTable(table).some((column) => column.column_name === field)) {
      throw new Error("该选择不在当前可用范围内，请重新分析");
    }
    if (target.formulaPath) {
      let node = condition[target.side];
      for (const part of target.formulaPath) node = node?.[part];
      if (condition[target.side + "_type"] !== "formula" || typeof node?.field !== "string") {
        throw new Error("待确认的公式字段已变化");
      }
      node.field = field;
    } else {
      if (condition[target.side + "_type"] === "formula") throw new Error("请选择公式内的具体字段");
      condition[target.side] = field;
    }
  }
  return result;
}
