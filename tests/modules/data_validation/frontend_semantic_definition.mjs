import assert from "node:assert/strict";
import { createRuleForm } from "./components/rule_form.mjs";
import { createState } from "./state.mjs";

// This form test uses only input values, select options and the editor's tree.
class FormNode {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.value = "";
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute() {}
  get options() { return this.children.filter((node) => node.tagName === "OPTION"); }
}
globalThis.document = {
  createElement: (tag) => new FormNode(tag),
  createElementNS: (_, tag) => new FormNode(tag),
  createTextNode: (text) => ({ textContent: text }),
};
const state = createState();
state.sources = [{ id: "src", name: "报表", dialect: "mysql" }];
const form = createRuleForm({ state, mode: "ai", user: { role: "admin" }, listen: () => () => {} });
const metadata = { columns: ["id", "period", "units", "total"].map((column_name) => ({ column_name })),
  mapping_version: "doc-v1" };
const intent = { metrics: [{ term: "价值", fields: ["units", "total"], side: "left" }],
  scopes: [], open_questions: [] };
const candidate = { name: "价值检查", rule_name: "价值检查", generation_mode: "ai", source_id: "src",
  table_name: "items", rule_type: "field_compare", business_key: "id", report_date_field: "period",
  report_category: "group:pbc", expression: { left: "units", op: "is_null" }, violation_message: "价值缺失",
  analysis_protocol: 2, semantic_intent: intent };
const verifyIntent = (definition) => {
  assert.equal(definition.analysis_protocol, 2);
  assert.deepEqual(definition.semantic_intent, intent);
};
const verifyLegacy = (definition) => {
  assert.ok(!Object.hasOwn(definition, "analysis_protocol"));
  assert.ok(!Object.hasOwn(definition, "semantic_intent"));
};
form.reset({ definition: candidate });
form.setMetadata(metadata);
form.applyCandidate(candidate);
verifyIntent(form.read());
const otherIntent = { metrics: [], scopes: [], open_questions: ["是否限定月末？"] };
form.applyCandidate({ ...candidate, semantic_intent: otherIntent });
assert.deepEqual(form.read().semantic_intent, otherIntent);
const second = { ...candidate, expression: { left: "total", op: "is_null" } };
form.applyCandidate(second);
const saved = form.validateForSave();
assert.equal(saved.expression.left, "total");
verifyIntent(saved);
const namedChoice = { id: "expression.left", text: "选择价值字段", options: [
  { value: "units", label: "单位价值", rule_name: "当期项目单位价值非空校验" },
  { value: "total", label: "累计价值", rule_name: "当期项目累计价值非空校验" },
] };
form.applyDecision(namedChoice.id, "total", namedChoice);
assert.equal(form.validateForSave().name, "当期项目累计价值非空校验", "选择字段时采用模型为该字段组织的完整规则名称");
const editor = createRuleForm({ state, mode: "manual", user: { role: "admin" }, listen: () => () => {} });
editor.reset({ definition: saved });
editor.setMetadata(metadata);
verifyIntent(editor.validateForSave());
const { analysis_protocol, semantic_intent, ...legacy } = candidate;
form.applyCandidate(legacy);
verifyLegacy(form.read());
editor.reset({ definition: legacy });
verifyLegacy(editor.read());
form.applyCandidate(candidate);
form.setMetadata(null);
verifyLegacy(form.read());
editor.reset({ definition: saved });
editor.reset(null);
verifyLegacy(editor.read());
