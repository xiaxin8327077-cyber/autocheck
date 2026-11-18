import assert from "node:assert/strict";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createRuleForm } from "./components/rule_form.mjs";

class FakeText {
  constructor(text) { this.textContent = String(text); this.parentNode = null; }
}
class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.dataset = {};
    this.listeners = new Map();
    this._className = "";
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = "";
    this.type = "";
    this.classList = {
      add: (...names) => {
        const values = new Set(this._className.split(/\s+/).filter(Boolean));
        names.forEach((name) => values.add(name));
        this._className = [...values].join(" ");
      },
      remove: (...names) => {
        const removed = new Set(names);
        this._className = this._className.split(/\s+/).filter((name) => name && !removed.has(name)).join(" ");
      },
      toggle: (name, force) => {
        const values = new Set(this._className.split(/\s+/).filter(Boolean));
        const enabled = force === undefined ? !values.has(name) : Boolean(force);
        if (enabled) values.add(name); else values.delete(name);
        this._className = [...values].join(" ");
        return enabled;
      },
      contains: (name) => this._className.split(/\s+/).includes(name),
    };
  }
  get className() { return this._className; }
  set className(value) { this._className = String(value || ""); }
  get options() { return this.children.filter((child) => child.tagName === "OPTION"); }
  setAttribute(name, value) { this.attributes.set(String(name), String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  append(...nodes) {
    nodes.flat(Infinity).forEach((child) => {
      if (child === null || child === undefined || child === false) return;
      const value = typeof child === "string" ? new FakeText(child) : child;
      if (value.parentNode) value.parentNode.children = value.parentNode.children.filter((item) => item !== value);
      value.parentNode = this;
      this.children.push(value);
    });
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }
  removeEventListener(type, handler) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter((item) => item !== handler));
  }
  async dispatch(type, event = {}) {
    const payload = { target: this, currentTarget: this, preventDefault() {}, ...event };
    payload.stopPropagation = () => { payload.__stopped = true; };
    for (const handler of [...(this.listeners.get(type) || [])]) await handler(payload);
  }
}
globalThis.document = {
  activeElement: null,
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_namespace, tag) => new FakeElement(tag),
  createTextNode: (text) => new FakeText(text),
};

const state = createState();
state.sourcesStatus = "success";
state.sources = [{ id: "src", name: "监管报表", dialect: "mysql" }];
state.categoriesStatus = "success";
state.categories = [{ code: "pbc_central", name: "人行大集中报送" }];
const runtime = createRuntime({ notify: () => {} });
runtime.activate();
const user = { id: "1", role: "user", capabilities: ["dv.manage", "dv.ai_use"] };
const form = createRuleForm({
  state, mode: "ai", listen: (node, type, handler) => node.addEventListener(type, handler), user,
  onChange: () => {}, onDescribe: () => {}, onParse: () => {},
});
form.setSources();
form.setCategories();
form.setMetadata({
  mapping_version: "doc-v1-ctx",
  columns: [
    { column_name: "c_projcode", comment: "项目编号", data_type: "varchar" },
    { column_name: "f_endp_amt", comment: "实收信托", data_type: "numeric" },
    { column_name: "d_cldate", comment: "数据日期", data_type: "date" },
  ],
  project_table: "proj_info_dtl",
  project_columns: [
    { column_name: "c_projcode", table_name: "proj_info_dtl", data_type: "varchar", comment: "项目编号" },
    { column_name: "c_projname", table_name: "proj_info_dtl", data_type: "varchar", comment: "项目名称" },
    { column_name: "d_projdate", table_name: "proj_info_dtl", data_type: "date", comment: "项目日期" },
    { column_name: "d_etl", table_name: "proj_info_dtl", data_type: "datetime", comment: "采集时间" },
    { column_name: "d_ts", table_name: "proj_info_dtl", data_type: "timestamp", comment: "时间戳" },
  ],
});
form.applyCandidate({
  rule_type: "field_compare", rule_name: "项目校验", table_name: "reg_pub_project_info",
  source_id: "src", dialect: "mysql", report_category: "pbc_central",
  business_key: "c_projcode", report_date_field: "d_cldate",
  expression: { left: "f_endp_amt", op: "eq", right_type: "value", right: 0 },
  violation_message: "异常", null_policy: "skip", equality_policy: "allow_equal",
  columns: [
    { column_name: "c_projcode", comment: "项目编号", data_type: "varchar" },
    { column_name: "f_endp_amt", comment: "实收信托", data_type: "numeric" },
    { column_name: "d_cldate", comment: "数据日期", data_type: "date" },
  ],
  uncertainties: ["选择项目上下文"], uncertainty_resolutions: [""],
});
const readCtx = () => form.read().project_context;

// mode 是独立 enum，不走列校验。
form.applyDecision("project_context.mode", "lookup", { options: [{ value: "base", label: "本表" }, { value: "lookup", label: "关联表" }], uncertainty: "选择项目上下文" });
assert.equal(readCtx().mode, "lookup");
assert.throws(() => form.applyDecision("project_context.mode", "c_projcode", { options: [{ value: "base" }, { value: "lookup" }] }));

// table_name 只按后端真实 options 验证；切换清空旧 mapping 证据。
form.applyDecision("project_context.table_name", "proj_info_dtl", { options: [{ value: "proj_info_dtl", label: "项目信息表" }], uncertainty: "选择项目上下文" });
assert.equal(readCtx().table_name, "proj_info_dtl");
assert.throws(() => form.applyDecision("project_context.table_name", "not_a_table", { options: [{ value: "proj_info_dtl" }] }));
form.applyDecision("project_context.table_name", "proj_info_dtl", { options: [] });
assert.equal(readCtx().table_name, "proj_info_dtl", "无 options 时按 metadata.project_table 校验");

// mapping 虚拟问题只消费 selection，不把 mapping 字段写入 ctx。
form.applyDecision("project_context.mapping", "m1", {
  options: [{ value: "m1", label: "项目映射", selection: { mode: "lookup", table_name: "proj_info_dtl", key: { left: "c_projcode", right: "c_projcode" }, name_field: "c_projname", date_field: "d_projdate", unique_evidence: "主键" } }],
  uncertainty: "选择项目上下文",
});
let ctx = readCtx();
assert.equal(ctx.mode, "lookup");
assert.equal(ctx.table_name, "proj_info_dtl");
assert.deepEqual(ctx.key, { left: "c_projcode", right: "c_projcode" });
assert.equal(ctx.name_field, "c_projname");
assert.equal(ctx.date_field, "d_projdate");
assert.equal(ctx.unique_evidence, "主键");
assert.equal(Object.hasOwn(ctx, "mapping"), false, "mapping 不得写入 project_context");

// code_field 校验 base；name/key/date 校验 project_columns；unique_evidence 不当列名。
form.applyDecision("project_context.code_field", "c_projcode", { options: [{ value: "c_projcode" }] });
assert.equal(readCtx().code_field, "c_projcode");
assert.throws(() => form.applyDecision("project_context.code_field", "c_projname", { options: [{ value: "c_projname" }] }), "base 无此列必须拒绝");
form.applyDecision("project_context.name_field", "c_projname", { options: [{ value: "c_projname" }] });
assert.equal(readCtx().name_field, "c_projname");
assert.throws(() => form.applyDecision("project_context.name_field", "f_endp_amt", { options: [{ value: "f_endp_amt" }] }), "第二表列不在 project_columns 必须拒绝");
form.applyDecision("project_context.date_field", "d_projdate", { options: [{ value: "d_projdate" }] });
assert.equal(readCtx().date_field, "d_projdate");
assert.throws(() => form.applyDecision("project_context.date_field", "c_projname", { options: [{ value: "c_projname" }] }), "关联日期必须真实 DATE");
assert.throws(() => form.applyDecision("project_context.date_field", "d_etl", { options: [{ value: "d_etl" }] }), "datetime 必须拒绝");
assert.throws(() => form.applyDecision("project_context.date_field", "d_ts", { options: [{ value: "d_ts" }] }), "timestamp 必须拒绝");
form.applyDecision("project_context.unique_evidence", "项目编号唯一且非空", { options: [] });
assert.equal(readCtx().unique_evidence, "项目编号唯一且非空");

// confirmed 字符串 'true' 转 bool；JSON 往返保留 ctx。
form.applyDecision("project_context.confirmed", "true", { options: [{ value: "true" }] });
assert.equal(readCtx().confirmed, true);
const serialized = JSON.parse(JSON.stringify(form.read().project_context));
assert.equal(serialized.mode, "lookup");
assert.equal(serialized.confirmed, true);
runtime.destroy();
console.log(JSON.stringify({ ok: true, assertions: "project_context/lookup/mapping/columns/confirmed" }));
