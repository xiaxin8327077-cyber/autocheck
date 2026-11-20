import assert from "node:assert/strict";
import { createState } from "./state.mjs";
import { createRuntime } from "./runtime.mjs";
import { createRuleTable } from "./components/rule_table.mjs";
import { createRulesPage } from "./pages/rules.mjs";
import { createApi } from "./api.mjs";
import { FakeElement, collectByClass, collectText, findButton } from "./frontend_workbench_dom.mjs";

FakeElement.prototype.closest = function (selector) {
  const match = selector.match(/^\[data-([\w-]+)\]$/);
  if (!match) return null;
  const key = match[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
  for (let node = this; node; node = node.parentNode) if (node.dataset?.[key] !== undefined) return node;
  return null;
};
FakeElement.prototype.contains = function (target) {
  for (let node = target; node; node = node.parentNode) if (node === this) return true;
  return false;
};
function inputs(root, result = []) {
  if (root.tagName === "INPUT" && root.type === "checkbox") result.push(root);
  for (const child of root.children || []) inputs(child, result);
  return result;
}
const owner = { id: "1", capabilities: ["dv.view", "dv.manage", "dv.run", "dv.export"] };
const rows = [1, 2, 3].map(id => ({ id, rule_code: `DV00000${id}`, name: `规则${id}`, description: "完整说明",
  creator_user_id: id === 3 ? "2" : "1", status: "enabled", version_no: 1,
  table_name: "proj_info_dtl_pboc", table_name_cn: id === 1 ? "项目信息" : "", rule_type: "field_compare" }));
const runtime = createRuntime({ notify(message) { throw new Error(message); } });
runtime.activate();
const selection = new Map();
let table;
const update = () => table.update({ items: rows, total: rows.length, page: 1, page_size: 50 }, selection);
table = createRuleTable({ listen: runtime.listen, user: owner, onAction() {}, onSelect(rule, checked) {
  if (checked) selection.set(rule.id, rule); else selection.delete(rule.id);
  update();
} });
update();
let checks = inputs(table.element);
checks[0].checked = true;
await checks[0].dispatch("change");
assert.equal(selection.size, 3, "逐条回调重绘不能破坏全选目标值");
checks = inputs(table.element);
assert.equal(checks[0].checked, true);
assert.equal(checks[0].indeterminate, false);
assert.equal(collectByClass(table.element, "is-selected").length, 3);
checks[0].checked = false;
await checks[0].dispatch("change");
assert.equal(selection.size, 0);
checks = inputs(table.element);
checks[1].focus();
checks[1].checked = true;
await checks[1].dispatch("change");
checks = inputs(table.element);
assert.ok(document.activeElement === checks[1], "勾选重绘后保留同一规则的键盘焦点");
assert.equal(checks[0].indeterminate, true);
assert.ok(checks.every(input => input.classList.contains("dv-rule-checkbox")));
const cells = collectByClass(table.element, "dv-rule-table-name");
assert.equal(collectText(cells[0]), "项目信息（proj_info_dtl_pboc）");
assert.equal(collectText(cells[1]), "proj_info_dtl_pboc", "缺少中文名时只展示实际表名");
assert.equal(collectByClass(table.element, "dv-rule-table-code").length, 0, "表英文名只在括号中显示一次");
for (const [table_name_cn, expected] of [
  ["项目信息（proj_info_dtl_pboc.ktr）", "项目信息（proj_info_dtl_pboc）"],
  ["项目信息表 (old_project_v2.KTR)", "项目信息表（proj_info_dtl_pboc）"],
  ["项目信息（proj_info_dtl_pboc）", "项目信息（proj_info_dtl_pboc）"],
  ["项目信息（季度）（proj_info_dtl_pboc.ktr）", "项目信息（季度）（proj_info_dtl_pboc）"],
  ["proj_info_dtl_pboc", "proj_info_dtl_pboc"],
]) {
  table.update({ items: [{ ...rows[0], table_name_cn }], total: 1, page: 1, page_size: 50 }, selection);
  const cell = collectByClass(table.element, "dv-rule-table-name")[0];
  assert.equal(collectText(cell), expected);
  assert.equal(cell.getAttribute("title"), expected);
}
update();
const tableRows = table.element.children[1].children[1].children;
assert.equal(findButton(tableRows[0], "删除").disabled, false);
assert.equal(findButton(tableRows[0], "删除").dataset.capability, "dv.manage");
assert.equal(findButton(tableRows[2], "删除").disabled, true, "管理员以外的他人规则不可删除");
table.update({ items: rows, total: rows.length, page: 1, page_size: 50 }, selection, { busy: true });
assert.ok(inputs(table.element).every(input => input.disabled));
assert.equal(findButton(table.element, "删除").disabled, true);
runtime.destroy();

async function pageScenario({ failAt = null, accept = true } = {}) {
  const state = createState();
  state.sources = [];
  state.rules = { items: structuredClone(rows.slice(0, 2)), total: 2, page: 1, page_size: 50 };
  state.rulesStatus = state.statsStatus = "success";
  state.selectedRules = new Map(state.rules.items.map(rule => [rule.id, rule]));
  const runtime = createRuntime({ notify() {} }); runtime.activate();
  const deleted = [], confirmations = [], notices = [];
  const api = {
    deleteRule: async id => { if (id === failAt) throw new Error("模拟删除失败"); deleted.push(id); return { id, status: "deleted" }; },
    rules: async query => ({ ...state.rules, page: query.page, items: state.rules.items.filter(rule => !deleted.includes(rule.id)), total: 2 - deleted.length }),
    stats: async () => ({ total: 2 - deleted.length, enabled: 2 - deleted.length, disabled: 0, draft: 0, categories: [] }),
  };
  const host = new FakeElement("div");
  const page = createRulesPage({ state, runtime, api, listen: runtime.listen, user: owner, host,
    notify(message, tone) { notices.push({ message, tone }); },
    confirmAction: async message => { confirmations.push(message); return accept; },
    onOpenWorkbench() {}, onOpenTask() {}, onOpenHistory() {} });
  host.append(page.header, page.panel);
  return { page, host, state, runtime, deleted, confirmations, notices };
}
const menuScenario = await pageScenario();
const toggles = collectByClass(menuScenario.page.panel, "dv-more-toggle");
const moreMenus = collectByClass(menuScenario.page.panel, "dv-more-menu");
await toggles[0].dispatch("click");
assert.equal(moreMenus[0].hidden, false, "打开更多菜单");
await toggles[1].dispatch("click");
assert.equal(moreMenus[0].hidden, true, "同一时间只展开一个菜单");
assert.equal(moreMenus[1].hidden, false);
await menuScenario.host.dispatch("click");
assert.equal(moreMenus[1].hidden, true, "点击模块空白处收起更多");
await toggles[0].dispatch("click");
await menuScenario.page.header.dispatch("click");
assert.equal(moreMenus[0].hidden, true, "点击表格外的标题空白同样收起");
await toggles[0].dispatch("click");
await collectByClass(menuScenario.page.panel, "dv-table-wrap")[0].dispatch("click");
assert.equal(moreMenus[0].hidden, true, "点击表格内部空白收起");
menuScenario.runtime.destroy();
assert.equal((menuScenario.host.listeners.get("click") || []).length, 0, "卸载时清理收起菜单的监听器");

const bulk = await pageScenario();
bulk.state.selectedRules.clear(); bulk.page.render();
const bulkBody = collectByClass(bulk.page.panel, "dv-rule-table")[0].children[1];
let bodyRenders = 0;
const replaceChildren = bulkBody.replaceChildren.bind(bulkBody);
bulkBody.replaceChildren = (...args) => { bodyRenders++; return replaceChildren(...args); };
inputs(bulk.page.panel)[0].checked = true;
await inputs(bulk.page.panel)[0].dispatch("change");
assert.equal(bodyRenders, 1, "全选当前页只重绘一次，避免逐条重绘整表");
await findButton(bulk.page.panel, "批量删除").dispatch("click");
assert.deepEqual(bulk.deleted, [1, 2]);
assert.equal(bulk.confirmations.length, 1);
assert.match(bulk.confirmations[0], /2/);
assert.equal(bulk.state.selectedRules.size, 0);
assert.equal(bulk.state.rules.total, 0);
bulk.runtime.destroy();

const cancelled = await pageScenario({ accept: false });
await findButton(cancelled.page.panel, "批量删除").dispatch("click");
assert.deepEqual(cancelled.deleted, []);
assert.equal(cancelled.state.selectedRules.size, 2);
cancelled.runtime.destroy();

const denied = await pageScenario();
denied.state.selectedRules.set(3, rows[2]); denied.page.render();
assert.equal(findButton(denied.page.panel, "批量删除").disabled, true);
await findButton(denied.page.panel, "批量删除").dispatch("click");
assert.equal(denied.confirmations.length, 0);
assert.equal(denied.deleted.length, 0, "混入他人规则时不擅自只删除本人部分");
denied.runtime.destroy();

const partial = await pageScenario({ failAt: 2 });
await findButton(partial.page.panel, "批量删除").dispatch("click");
assert.deepEqual(partial.deleted, [1]);
assert.deepEqual([...partial.state.selectedRules.keys()], [2]);
assert.equal(partial.state.rules.total, 1);
assert.ok(partial.notices.some(item => /1/.test(item.message) && /未完成/.test(item.message)));
partial.runtime.destroy();

const single = await pageScenario();
await findButton(collectByClass(single.page.panel, "dv-rule-table")[0].children[1].children[0], "删除").dispatch("click");
assert.deepEqual(single.deleted, [1]);
assert.deepEqual([...single.state.selectedRules.keys()], [2]);
assert.match(single.confirmations[0], /规则1/);
single.runtime.destroy();

let apiCall;
const api = createApi({ api: async (path, options) => { apiCall = { path, options }; return { data: { id: 7, status: "deleted" } }; } });
assert.deepEqual(await api.deleteRule(7), { id: 7, status: "deleted" });
assert.equal(apiCall.path, "/api/modules/data-validation/rules/7");
assert.equal(apiCall.options.method, "DELETE");
