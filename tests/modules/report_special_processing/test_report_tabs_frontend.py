from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
COMPONENTS = ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web" / "components"


def test_report_tabs_overflow_keeps_order_searches_and_releases_observers(tmp_path: Path) -> None:
    """Narrow tab rows must move only trailing reports into an operable menu."""
    shutil.copy2(COMPONENTS / "dom.js", tmp_path / "dom.js")
    shutil.copy2(COMPONENTS / "report_tabs.js", tmp_path / "report_tabs.js")
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    (tmp_path / "scenario.js").write_text(
        r'''
import assert from "node:assert/strict";
import { createReportTabs } from "./report_tabs.js";

const widths = { "": 52, pbc: 62, crs: 66, ext_a: 78, ext_b: 80, __more__: 72 };
class FakeNode {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.parentNode = null;
    this.attributes = {}; this.dataset = {}; this.className = ""; this.textContent = "";
    this.hidden = false; this.value = ""; this.disabled = false; this._listeners = {};
    this.classList = {
      add: (...names) => { const current = new Set(this.className.split(/\s+/).filter(Boolean)); names.forEach((name) => current.add(name)); this.className = [...current].join(" "); },
      remove: (...names) => { const drop = new Set(names); this.className = this.className.split(/\s+/).filter((name) => name && !drop.has(name)).join(" "); },
      toggle: (name, force) => { const has = this.className.split(/\s+/).includes(name); const next = force === undefined ? !has : Boolean(force); if (next) this.classList.add(name); else this.classList.remove(name); return next; },
      contains: (name) => this.className.split(/\s+/).includes(name),
    };
  }
  append(...items) { items.filter(Boolean).forEach((item) => { item.parentNode = this; this.children.push(item); }); }
  appendChild(item) { this.append(item); return item; }
  replaceChildren(...items) { this.children = []; this.append(...items); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((item) => item !== this); }
  contains(target) { return target === this || this.children.some((item) => item.contains?.(target)); }
  setAttribute(name, value) { this.attributes[name] = String(value); if (name === "hidden") this.hidden = true; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; if (name === "hidden") this.hidden = false; }
  addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); }
  removeEventListener(type, fn) { this._listeners[type] = (this._listeners[type] || []).filter((item) => item !== fn); }
  dispatchEvent(event) { const evt = { target: this, preventDefault() {}, stopPropagation() {}, ...event }; (this._listeners[evt.type] || []).slice().forEach((fn) => fn(evt)); }
  focus() { this.focused = true; }
  getBoundingClientRect() { return { left: 20, top: 10, bottom: 42, width: this._width ?? widths[this.dataset.code] ?? (this.className.includes("rsp-report-tabs-more-trigger") ? widths.__more__ : 20) }; }
}
function walk(node, predicate, found = []) { if (predicate(node)) found.push(node); node.children.forEach((child) => walk(child, predicate, found)); return found; }
const windowListeners = {};
let observer = null;
const view = {
  addEventListener(type, fn) { (windowListeners[type] ||= []).push(fn); },
  removeEventListener(type, fn) { windowListeners[type] = (windowListeners[type] || []).filter((item) => item !== fn); },
  requestAnimationFrame(fn) { fn(); return 1; }, cancelAnimationFrame() {},
  ResizeObserver: class { constructor(fn) { this.callback = fn; observer = this; } observe() {} disconnect() { this.disconnected = true; } },
};
const documentRef = {
  defaultView: view,
  createElement: (tag) => new FakeNode(tag),
  createTextNode: (text) => { const node = new FakeNode("#text"); node.textContent = String(text); return node; },
  addEventListener() {}, removeEventListener() {},
};
const selected = [];
const tabs = createReportTabs(documentRef, {
  items: [
    { code: "", name: "全部", count: 9 }, { code: "pbc", name: "人行报送", count: 3 },
    { code: "crs", name: "CRS报送", count: 2 }, { code: "ext_a", name: "扩展报送甲", count: 1 },
    { code: "ext_b", name: "12345678901234😀Z", count: 0 },
  ],
  activeCode: "", onSelect: (code) => selected.push(code),
});
tabs.root._width = 210;
tabs.refresh();
let trigger = walk(tabs.root, (node) => node.classList?.contains("rsp-report-tabs-more-trigger"))[0];
assert.ok(trigger, "尾部报送应收纳到更多菜单");
assert.equal(trigger.textContent, "更多报送（3） ▾");
trigger.dispatchEvent({ type: "click" });
const search = walk(tabs.root, (node) => node.getAttribute?.("aria-label") === "搜索更多报送")[0];
assert.ok(search, "更多菜单提供名称和数量搜索");
search.value = "扩展报送甲"; search.dispatchEvent({ type: "input" });
const matched = walk(tabs.root, (node) => node.dataset?.code === "ext_a" && node.classList?.contains("rsp-report-tabs-more-option"))[0];
assert.ok(matched && !matched.hidden, "搜索后保留匹配的尾部项");
matched.dispatchEvent({ type: "click" });
assert.deepEqual(selected, ["ext_a"]);
trigger = walk(tabs.root, (node) => node.classList?.contains("rsp-report-tabs-more-trigger"))[0];
assert.match(trigger.textContent, /扩展报送甲/);
assert.ok(trigger.classList.contains("is-active"), "隐藏的当前报送要在更多入口高亮显示");
tabs.root._width = 500; observer.callback();
assert.equal(walk(tabs.root, (node) => node.classList?.contains("rsp-report-tabs-more-trigger")).length, 0, "扩宽后重新显示能放下的页签");
const longTab = walk(tabs.root, (node) => node.dataset?.code === "ext_b" && node.classList?.contains("rsp-report-tab-measure") === false)[0];
const longTabLabel = longTab?.children?.[0];
assert.equal(longTabLabel?.textContent, "12345678901234😀", "页签名称按 Unicode codepoint 截至前 15 个字符且不追加省略号");
assert.equal(longTabLabel?.getAttribute("title"), "12345678901234😀Z", "页签悬停保留完整报送名称");
tabs.destroy();
assert.ok(observer.disconnected, "销毁时释放 ResizeObserver");
assert.equal((windowListeners.resize || []).length, 0, "销毁时移除窗口缩放监听");
''',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", "scenario.js"], cwd=tmp_path, text=True, encoding="utf-8", capture_output=True
    )
    assert result.returncode == 0, result.stderr


def test_ledger_uses_tab_catalog_only_and_keeps_removed_history_selectable_once() -> None:
    ledger = (ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web" / "pages" / "ledger.js").read_text(encoding="utf-8")
    drawer = (COMPONENTS / "record_drawer.js").read_text(encoding="utf-8")
    multi_select = (COMPONENTS / "process_multi_select.js").read_text(encoding="utf-8")

    assert "catalog?.report_process_tabs ?? catalog?.report_processes" in ledger
    assert "createReportTabs" in ledger
    assert "record.report_processes" in drawer
    assert "historical: true" in drawer
    assert "item.historical" in multi_select
    assert "selected.has(code)" in multi_select
    assert "focusActive" in ledger


def test_visible_tabs_fill_available_row_after_natural_width_measurement() -> None:
    css = (ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web" / "styles.css").read_text(encoding="utf-8")
    source = (COMPONENTS / "report_tabs.js").read_text(encoding="utf-8")

    assert "rsp-report-tab-measure" in source
    assert 'node.classList.remove("rsp-report-tab-measure")' in source
    assert "Array.from(String(name || \"\")).slice(0, REPORT_TAB_LABEL_LIMIT).join(\"\")" in source
    assert "title: item.name" in source
    assert '.rsp-report-tabs > [role="tab"].rsp-report-tab-measure' in css
    assert "flex: 0 0 auto;" in css
    assert "flex: 1 0 auto;" in css
    assert "text-overflow: ellipsis;" not in css[css.index(".rsp-report-tab-label"):css.index(".rsp-report-tabs-more-trigger")]


def test_removed_active_report_tab_returns_to_all_filter_after_catalog_refresh(tmp_path: Path) -> None:
    shutil.copy2(COMPONENTS / "dom.js", tmp_path / "dom.js")
    shutil.copy2(COMPONENTS / "report_tabs.js", tmp_path / "report_tabs.js")
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    (tmp_path / "scenario.js").write_text(
        '''
import assert from "node:assert/strict";
import { normalizeActiveTabCode } from "./report_tabs.js";
const catalog = { report_process_tabs: [
  { code: "group:pbc", active: true },
  { code: "pbc_crs", active: true },
] };
assert.equal(normalizeActiveTabCode("removed_extra", catalog), "");
assert.equal(normalizeActiveTabCode("group:pbc", catalog), "group:pbc");
assert.equal(normalizeActiveTabCode("", catalog), "");
assert.equal(normalizeActiveTabCode("pbc", { report_processes: [{ code: "pbc", active: true }] }), "pbc");
''',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", "scenario.js"], cwd=tmp_path, text=True, encoding="utf-8", capture_output=True
    )
    assert result.returncode == 0, result.stderr
