export function isGrouped(expression) {
  return Array.isArray(expression?.conditions);
}

export function comparisons(expression) {
  return isGrouped(expression) ? expression.conditions : [expression || {}];
}

export function comparisonFields(expression) {
  return [...new Set(comparisons(expression).map((item) => item.left).filter(Boolean))];
}

export function hasComparison(expression) {
  return (!isGrouped(expression) || (["any", "all"].includes(expression.logic)
    && expression.conditions.length >= 2 && expression.conditions.length <= 8))
    && comparisons(expression).every((item) => item?.left && item.op);
}

export function fieldTarget(path) {
  const match = /^expression\.(?:conditions\.([0-7])\.)?(left|right)$/.exec(path || "");
  return match && { index: match[1] === undefined ? null : Number(match[1]), side: match[2] };
}

export function bindComparisonField(expression, question, field, columnsForTable) {
  const paths = [...new Set([question.id, ...(question.targets || [])])];
  const result = isGrouped(expression)
    ? { ...expression, conditions: expression.conditions.map((condition) => ({ ...condition })) } : { ...expression };
  for (const path of paths) {
    const target = fieldTarget(path);
    if (!target || (target.index !== null) !== isGrouped(result)) throw new Error("字段选择与当前规则条件不一致");
    const condition = target.index === null ? result : result.conditions[target.index];
    if (!condition) throw new Error("待确认的比较条件已变化");
    const table = target.side === "right" && condition.right_table === "related" ? "related" : "base";
    if (!columnsForTable(table).some((column) => column.column_name === field)) {
      throw new Error("该选择不在当前可用范围内，请重新分析");
    }
    condition[target.side] = field;
  }
  return result;
}
