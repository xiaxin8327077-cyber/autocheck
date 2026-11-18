import assert from "node:assert/strict";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createResultsPage } from "./pages/results.mjs";

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
    this.value = "";
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
  focus() { globalThis.document.activeElement = this; }
}
globalThis.document = {
  activeElement: null,
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_namespace, tag) => new FakeElement(tag),
  createTextNode: (text) => new FakeText(text),
};
function collectByClass(root, className, found = []) {
  if (root.classList?.contains(className)) found.push(root);
  for (const child of root.children || []) collectByClass(child, className, found);
  return found;
}
function collectText(node) {
  if (!node) return "";
  if (node.children && node.children.length) return node.children.map(collectText).join("");
  return node.textContent || "";
}

const runtime = createRuntime({ notify: () => {} });
runtime.activate();
const state = createState();
state.activeTab = "results";
state.tasks = [{ id: 1, run_no: 1, creator_user_id: "1", report_period: state.reportPeriod, status: "completed", created_at: "2026-11-01T01:00:00", truncated: 0 }];
const xssName = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>项目';
const issues = {
  task_id: 1, total: 3, page: 1, page_size: 50,
  items: [
    { id: 101, rule_id: 7, version_no: 2, project_code: "0", project_name: "项目信息表", business_key: "row-0", project_name_status: "ok", issue_kind: "numeric", message: "金额为0", created_at: "2026-11-01T02:00:00" },
    { id: 102, rule_id: 7, version_no: 2, project_code: "C-9", project_name: null, business_key: "row-9", project_name_status: "missing_null", issue_kind: "missing_value", message: xssName, created_at: "2026-11-01T03:00:00" },
    { id: 103, rule_id: 8, version_no: 1, project_code: null, project_name: "合同明细", business_key: "row-8", project_name_status: "legacy_unavailable", issue_kind: "legacy", message: "历史未采集", created_at: "2026-11-01T04:00:00" },
  ],
};
const api = {
  tasks: async () => state.tasks,
  issues: async () => issues,
};
const page = createResultsPage({
  state, runtime, api, listen: runtime.listen,
  user: { id: "1", role: "user", capabilities: ["dv.view", "dv.view_results"] },
  notify: () => {}, confirmAction: async () => true, host: new FakeElement("div"),
  onNewTask: () => {}, onPeriodChange: () => {}, onRender: () => {},
});
await page.loadTasks();
const headers = collectByClass(page.panel, "dv-issue-table")[0].children[0].children[0].children.map((th) => th.textContent);
assert.deepEqual(headers, ["异常编号", "规则 ID / 版本", "项目编号", "项目名称", "明细业务键", "项目定位", "核查类型", "异常说明", "登记时间"]);
const rows = collectByClass(page.panel, "dv-issue-table")[0].children[1].children;
assert.equal(rows.length, 3);
const cells = (row) => row.children.map((td) => collectText(td));
assert.deepEqual(cells(rows[0]), ["101", "7 / v2", "0", "项目信息表", "row-0", "已定位", "数值不符", "金额为0", "2026-11-01 02:00:00"]);
assert.equal(cells(rows[1])[2], "C-9");
assert.equal(cells(rows[1])[3], "—", "项目名称 null 显示 —");
assert.match(cells(rows[1])[5], /项目名称缺失/);
assert.equal(cells(rows[1])[6], "缺值待核实", "缺值与真实数值原因必须区分");
assert.equal(cells(rows[2])[2], "—");
assert.match(cells(rows[2])[5], /不可用|未采集|待核实/);
assert.equal(cells(rows[2])[6], "历史未采集", "legacy 必须明确标记");
// XSS：文本必须原样作为 textContent，不生成 img/script 节点。
assert.ok(cells(rows[1])[7].includes("<img src=x onerror"));
assert.equal(collectByClass(page.panel, "img").length, 0);
assert.equal(collectByClass(page.panel, "script").length, 0);
assert.equal(globalThis.__xss, undefined);
assert.doesNotMatch(collectText(page.panel), /异常明细（现有API字段）/);
const projectCell = rows[0].children[3];
assert.ok(projectCell.classList.contains("dv-project-name"));
runtime.destroy();
console.log(JSON.stringify({ ok: true, assertions: "results/columns/samples/null/xss" }));
