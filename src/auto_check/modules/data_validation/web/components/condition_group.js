import { OPERATOR_OPTIONS } from "../constants.js";
import { isFormulaComparison, isGrouped, isKeywordOperator } from "../comparisons.js";
import { createKeywordEditor } from "./keyword_editor.js";
import { candidateCondition } from "./ai_candidate.js";
import { button, element, field, input, select } from "./dom.js";

const operators = [...OPERATOR_OPTIONS, ["is_null", "为空"], ["is_not_null", "不为空"]];

export function createConditionGroup({ listen, columnsForTable, onEdit }) {
  const root = element("fieldset", { className: "dv-condition-group", hidden: true });
  let expression = null;
  let removers = [];

  function bind(node, type, handler) {
    removers.push(listen(node, type, handler));
  }

  function columnSelect(table, current) {
    const options = [["", "请选择真实字段"], ...columnsForTable(table).map((column) => [
      column.column_name, [column.column_name, column.comment].filter(Boolean).join(" · "),
    ])];
    if (current && !options.some(([value]) => value === current)) options.push([current, current + "（待核验）"]);
    return select(options, { value: current || "" });
  }

  function render() {
    removers.forEach((remove) => remove?.());
    removers = [];
    root.replaceChildren();
    root.hidden = !expression;
    if (!expression) return;
    const logic = select([["any", "满足任一条件"], ["all", "满足全部条件"]], { value: expression.logic });
    root.append(element("legend", { text: "组合校验条件" }), field("异常触发方式", logic));
    bind(logic, "change", () => { expression.logic = logic.value; onEdit(); });
    expression.conditions.forEach((item, index) => {
      const controls = element("div", { className: "dv-form-grid" });
      if (isFormulaComparison(item)) {
        root.append(element("div", { className: "dv-condition-row" }, element("strong", { text: `条件 ${index + 1}` }),
          field("公式条件（只读）", element("span", { text: candidateCondition({ expression: item, columns: columnsForTable("base") }) }))));
        return;
      }
      const left = columnSelect("base", item.left);
      const op = select(operators, { value: item.op || "" });
      controls.append(field("左字段", left), field("异常触发关系", op));
      bind(left, "change", () => { item.left = left.value; onEdit(); });
      bind(op, "change", () => {
        item.op = op.value;
        if (["is_null", "is_not_null"].includes(op.value)) {
          delete item.right; delete item.right_type; delete item.right_table;
        } else if (isKeywordOperator(op.value)) {
          if (!Array.isArray(item.right)) item.right = [""];
          item.right_type = "value";
          delete item.right_table;
        } else if (Array.isArray(item.right)) {
          item.right = "";
        }
        render(); onEdit();
      });
      if (isKeywordOperator(item.op)) {
        const editor = createKeywordEditor(listen, () => { item.right = editor.read(); onEdit(); });
        editor.set(item.right);
        controls.append(editor.element);
        removers.push(() => editor.dispose());
      } else if (!["is_null", "is_not_null"].includes(item.op)) {
        const target = item.right_type === "value" ? (typeof item.right === "string" ? "text" : "value") : item.right_table === "related" ? "related" : "base";
        const types = [["value", "数值常量"], ["text", "文本常量"], ["base", "主表字段"]];
        if (columnsForTable("related").length || target === "related") types.push(["related", "关联表字段"]);
        const type = select(types, { value: target });
        controls.append(field("比较目标类型", type));
        bind(type, "change", () => {
          item.right_type = ["value", "text"].includes(type.value) ? "value" : "field";
          item.right = type.value === "value" ? null : "";
          if (type.value === "related") item.right_table = "related";
          else delete item.right_table;
          render(); onEdit();
        });
        if (target === "value" || target === "text") {
          const number = input({ type: target === "text" ? "text" : "number", value: item.right ?? "" });
          number.step = "any";
          controls.append(field(target === "text" ? "文本常量" : "数值常量", number));
          bind(number, "input", () => {
            const value = Number(number.value);
            item.right = target === "text" ? number.value : String(number.value).trim() && Number.isFinite(value) ? value : null;
            onEdit();
          });
        } else {
          const right = columnSelect(target, item.right);
          controls.append(field("右字段", right));
          bind(right, "change", () => { item.right = right.value; onEdit(); });
        }
      }
      const remove = button("移除条件", { className: "dv-button dv-button-danger", disabled: expression.conditions.length <= 2 });
      bind(remove, "click", () => {
        if (expression.conditions.length <= 2) return;
        expression.conditions.splice(index, 1); render(); onEdit();
      });
      root.append(element("div", { className: "dv-condition-row" }, element("strong", { text: `条件 ${index + 1}` }), controls, remove));
    });
    const add = button("添加条件", { disabled: expression.conditions.length >= 8 });
    bind(add, "click", () => {
      if (expression.conditions.length >= 8) return;
      expression.conditions.push({ left: "", op: "eq", right_type: "value", right: null });
      render(); onEdit();
    });
    root.append(add);
  }

  return {
    element: root, render,
    read: () => expression && { logic: expression.logic, conditions: expression.conditions.map((item) => ({ ...item })) },
    set(value) {
      expression = isGrouped(value)
        ? { logic: value.logic, conditions: value.conditions.map((item) => ({ ...item })) } : null;
      render();
    },
    dispose() { expression = null; render(); },
  };
}
