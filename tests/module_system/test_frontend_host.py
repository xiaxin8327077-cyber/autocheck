from __future__ import annotations

import subprocess
import textwrap
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOST_JS = ROOT / "src" / "auto_check" / "web" / "module_host.js"
HOST_CSS = ROOT / "src" / "auto_check" / "web" / "module_host.css"
INDEX_HTML = ROOT / "src" / "auto_check" / "web" / "index.html"
APP_JS = ROOT / "src" / "auto_check" / "web" / "app.js"


def test_module_host_has_stable_lifecycle_contract():
    script = HOST_JS.read_text(encoding="utf-8")

    for fragment in [
        "window.AutoCheckModuleHost",
        "function createModuleHost",
        "async function initialize",
        "async function activate",
        "async function deactivate",
        "async function unmount",
        'api("/api/system/modules")',
        "importModule(module.frontend_entry)",
        "instance.mount(context)",
        "instance.activate(route)",
        "instance.deactivate()",
        "instance.unmount()",
    ]:
        assert fragment in script


def test_module_host_is_loaded_once_before_app_bootstrap():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert html.count('src="/module_host.js') == 1
    assert html.index('src="/module_host.js') < html.index('src="/app.js')
    assert 'id="moduleSideNavigation"' in html
    assert 'id="moduleTopNavigation"' in html
    assert 'id="modulePageHost"' in html


def test_module_host_css_is_scoped():
    css = HOST_CSS.read_text(encoding="utf-8")

    assert ".auto-check-module" in css
    assert ".auto-check-module-host:not([hidden])" in css
    assert ".auto-check-module:not([hidden])" in css
    assert "height: 100%" in css
    assert "flex: 1 1 auto" in css
    assert "\nbutton {" not in css
    assert "\ninput {" not in css
    assert "\ntable {" not in css


def test_module_navigation_buttons_use_scoped_reset_and_accessible_active_state():
    css = HOST_CSS.read_text(encoding="utf-8")

    assert "#moduleTopNavigation .module-top-nav-item" in css
    assert "#moduleTopNavigation .module-top-nav-group-toggle" in css
    assert "appearance: none" in css
    assert "border: 0" in css
    assert "background: transparent" in css
    assert "[aria-current=\"page\"]" in css
    assert "border-radius: var(--ui-radius)" in css


def test_legacy_app_exposes_only_explicit_platform_bridge():
    script = APP_JS.read_text(encoding="utf-8")

    assert "window.AutoCheckModuleHost.initialize({" in script
    assert "api," in script
    assert "user: () => ({ ...authState.user })" in script
    assert "notify: showToast" in script
    assert "confirm: showConfirm" in script
    assert "legacyNavigate: switchPage" in script


def test_module_host_release_notes_are_readonly_and_cleared_on_reload_failure(tmp_path: Path):
    script = textwrap.dedent(
        """
        "use strict";
        const assert = require("node:assert/strict");
        const { createModuleHost } = require(process.argv[2]);
        class FakeElement {
          constructor() { this.children = []; this.dataset = {}; this.hidden = true; this.listeners = new Map(); }
          appendChild(child) { this.children.push(child); return child; }
          replaceChildren(...children) { this.children = children; }
          addEventListener(type, listener) { this.listeners.set(type, listener); }
          removeEventListener(type) { this.listeners.delete(type); }
          setAttribute(name, value) { this[name] = String(value); }
          querySelector() { return null; }
          querySelectorAll() { return []; }
        }
        const elements = {
          moduleSideNavigation: new FakeElement(),
          moduleTopNavigation: new FakeElement(),
          modulePageHost: new FakeElement(),
        };
        const documentRef = {
          documentElement: { dataset: {} },
          createElement: () => new FakeElement(),
          getElementById: (id) => elements[id] || null,
          querySelectorAll: () => [],
        };
        let fail = false;
        const platform = {
          api: async () => {
            if (fail) throw new Error("unavailable");
            return { modules: [], release_notes: [{
              module_id: "alpha", module_name: "Alpha", version: "1.0.0", items: ["note"],
            }] };
          },
          user: () => ({}), notify: () => {}, confirm: async () => true,
          legacyNavigate: async () => {},
        };
        (async () => {
          const host = createModuleHost({ documentRef, locationRef: { hash: "" }, windowRef: null });
          assert.deepEqual(host.releaseNotes(), []);
          await host.initialize(platform);
          const first = host.releaseNotes();
          const second = host.releaseNotes();
          assert.notEqual(first, second);
          assert.ok(Object.isFrozen(first));
          assert.ok(Object.isFrozen(first[0]));
          assert.ok(Object.isFrozen(first[0].items));
          assert.deepEqual(first, [{ module_id: "alpha", module_name: "Alpha", version: "1.0.0", items: ["note"] }]);
          assert.throws(() => first[0].items.push("mutated"), TypeError);
          fail = true;
          assert.equal(await host.reload(), false);
          assert.deepEqual(host.releaseNotes(), []);
          await host.unmount();
          assert.deepEqual(host.releaseNotes(), []);
        })().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
        """
    )
    scenario_path = tmp_path / "module_release_notes_scenario.cjs"
    scenario_path.write_text(script, encoding="utf-8")
    subprocess.run(["node", str(scenario_path), str(HOST_JS)], check=True, cwd=ROOT)


def test_legacy_changelog_safely_renders_generic_module_release_notes(tmp_path: Path):
    source = APP_JS.read_text(encoding="utf-8")
    start = source.find("function renderModuleReleaseNotes")
    assert start >= 0
    end = source.find('document.getElementById("aboutChangelog")', start)
    assert end > start
    escape = re.search(r"function escapeHtml\(v\) \{.*?\n\}", source, re.S)
    assert escape is not None
    helper = source[start:end]
    assert "AutoCheckModuleHost" not in helper
    assert "report_special" not in helper
    script = textwrap.dedent(
        rf"""
        const assert = require("node:assert/strict");
        {escape.group(0)}
        {helper}
        assert.equal(renderModuleReleaseNotes([]), "");
        const html = renderModuleReleaseNotes([
          {{ module_id: "one", module_name: "<img src=x onerror=1>", version: "1.0.0", items: ["<script>alert(1)</script>"] }},
          {{ module_id: "two", module_name: "Two", version: "2.0.0", items: ["Second", "Third"] }},
        ]);
        assert.match(html, /模块更新/);
        assert.match(html, /&lt;img src=x onerror=1&gt;/);
        assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
        assert.doesNotMatch(html, /<script>|<img/);
        assert.match(html, /Second/);
        assert.match(html, /Third/);
        """
    )
    scenario_path = tmp_path / "render_module_release_notes.cjs"
    scenario_path.write_text(script, encoding="utf-8")
    subprocess.run(["node", str(scenario_path)], check=True, cwd=ROOT)

    assert "window.AutoCheckModuleHost.releaseNotes()" in source


def test_module_host_lifecycle_and_failure_isolation(tmp_path: Path):
    script = textwrap.dedent(
        """
        const assert = require("node:assert/strict");
        const { createModuleHost } = require(process.argv[2]);

        class FakeElement {
          constructor(tagName = "div") {
            this.tagName = tagName.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.listeners = new Map();
            this.hidden = false;
            this.className = "";
            this.textContent = "";
          }
          appendChild(child) {
            this.children.push(child);
            child.parentNode = this;
            if (this.tagName === "HEAD" && child.tagName === "LINK") {
              queueMicrotask(() => child.listeners.get("load")?.({ target: child }));
            }
            return child;
          }
          replaceChildren(...children) { this.children = []; children.forEach((child) => this.appendChild(child)); }
          addEventListener(type, listener) { this.listeners.set(type, listener); }
          removeEventListener(type) { this.listeners.delete(type); }
          click(target = this) { return this.listeners.get("click")?.({ target, preventDefault() {} }); }
          closest(selector) {
            if (selector === "[data-module-route]" && this.dataset.moduleRoute) return this;
            return null;
          }
          setAttribute(name, value) { this[name] = String(value); }
        }

        const elements = {
          moduleSideNavigation: new FakeElement(),
          moduleTopNavigation: new FakeElement(),
          modulePageHost: new FakeElement("section"),
        };
        const documentRef = {
          head: new FakeElement("head"),
          createElement: (tagName) => new FakeElement(tagName),
          getElementById: (id) => elements[id] || null,
        };
        const locationRef = { hash: "#alpha" };
        const calls = [];
        const moduleDefinition = {
          mount: async (context) => { calls.push(["mount", context]); },
          activate: async (route) => { calls.push(["activate", route]); },
          deactivate: async () => { calls.push(["deactivate"]); },
          unmount: async () => { calls.push(["unmount"]); },
        };
        const host = createModuleHost({
          documentRef,
          locationRef,
          importModule: async (url) => {
            if (url === "/module-assets/broken/index.js") throw new Error("broken module");
            return { default: moduleDefinition };
          },
        });
        const platform = {
          api: async () => ({ modules: [
            { id: "alpha", frontend_entry: "/module-assets/alpha/index.js", frontend_style: "/module-assets/alpha/styles.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] },
            { id: "broken", frontend_entry: "/module-assets/broken/index.js", frontend_style: "/module-assets/broken/styles.css", navigation: [{ id: "broken", label: "Broken", route: "broken" }] },
          ] }),
          user: () => ({ id: "user-1" }),
          notify: () => {},
          confirm: async () => true,
          legacyNavigate: async () => {},
        };

        (async () => {
          assert.equal(await host.initialize(platform), true);
          assert.equal(elements.moduleSideNavigation.children.length, 0);
          assert.equal(elements.moduleTopNavigation.children.length, 2);
          assert.deepEqual(calls.map(([name]) => name), ["mount", "activate"]);
          await host.deactivate();
          assert.equal(calls.at(-1)[0], "deactivate");
          locationRef.hash = "#broken";
          assert.equal(await host.activate("broken"), true);
          assert.ok(elements.modulePageHost.children.some((child) => /模块加载失败/.test(child.textContent)));
        })().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
        """
    )
    scenario_path = tmp_path / "module_host_scenario.cjs"
    scenario_path.write_text(script, encoding="utf-8")
    subprocess.run(["node", str(scenario_path), str(HOST_JS)], check=True, cwd=ROOT)


def _run_module_host_scenario(tmp_path: Path, scenario: str) -> None:
    script = textwrap.dedent(
        """
        const assert = require("node:assert/strict");
        const { createModuleHost } = require(process.argv[2]);

        class FakeElement {
          constructor(tagName = "div") {
            this.tagName = tagName.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = new Map();
            this.listeners = new Map();
            this.className = "";
            this.hidden = false;
            this.textContent = "";
            this.parentNode = null;
            this.classList = {
              values: new Set(),
              add: (name) => this.classList.values.add(name),
              remove: (...names) => names.forEach((name) => this.classList.values.delete(name)),
              toggle: (name, enabled) => enabled ? this.classList.values.add(name) : this.classList.values.delete(name),
              contains: (name) => this.classList.values.has(name),
            };
          }
          appendChild(child) {
            this.children.push(child);
            child.parentNode = this;
            if (this.tagName === "HEAD" && child.tagName === "LINK") {
              queueMicrotask(() => child.dispatch("load"));
            }
            return child;
          }
          replaceChildren(...children) { this.children.slice().forEach((child) => { child.parentNode = null; }); this.children = []; children.forEach((child) => this.appendChild(child)); }
          remove() { if (!this.parentNode) return; this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.parentNode = null; }
          contains(target) { return this.children.includes(target) || this.children.some((child) => child.contains?.(target)); }
          addEventListener(type, listener) { this.listeners.set(type, listener); }
          removeEventListener(type) { this.listeners.delete(type); }
          dispatch(type, target = this, options = {}) { return this.listeners.get(type)?.({ target, preventDefault() {}, ...options }); }
          focus() { this.focused = true; }
          closest(selector) {
            if (selector === "[data-module-route]" && this.dataset.moduleRoute) return this;
            if (selector === "[data-module-group-toggle]" && this.dataset.moduleGroupToggle) return this;
            if (selector === "[data-module-group-menu]") {
              let current = this;
              while (current) {
                if (current.dataset.moduleGroupMenu) return current;
                current = current.parentNode;
              }
            }
            return null;
          }
          setAttribute(name, value) { this.attributes.set(name, String(value)); }
          getAttribute(name) { return this.attributes.get(name) || null; }
          removeAttribute(name) { this.attributes.delete(name); }
          querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
          querySelectorAll(selector) {
            const matches = (element) => (
              (selector === ".page" && element.classList.contains("page"))
              || (selector === "[data-module-host-error]" && element.dataset.moduleHostError)
              || (selector === "[data-module-host-diagnostic]" && element.dataset.moduleHostDiagnostic)
              || (selector === ".nav-item[data-page], .top-nav-item[data-page]" && element.dataset.page)
              || (selector === "[data-module-route]" && element.dataset.moduleRoute)
              || (selector === '[data-nav-group="smart-reconcile"]' && (
                element.dataset.navGroup === "smart-reconcile"
                || element.getAttribute("data-nav-group") === "smart-reconcile"
              ))
              || (selector === "[data-nav-group-toggle]" && (
                Boolean(element.dataset.navGroupToggle)
                || Boolean(element.getAttribute("data-nav-group-toggle"))
              ))
            );
            const result = [];
            const visit = (element) => { element.children.forEach((child) => { if (matches(child)) result.push(child); visit(child); }); };
            visit(this);
            return result;
          }
        }

        function deferred() {
          let resolve;
          const promise = new Promise((res) => { resolve = res; });
          return { promise, resolve };
        }
        async function flush() { for (let index = 0; index < 8; index += 1) await Promise.resolve(); }
        function makeEnvironment(hash = "") {
          const pageHost = new FakeElement("section");
          const side = new FakeElement("div");
          const top = new FakeElement("div");
          const legacyPage = new FakeElement("section"); legacyPage.classList.add("page"); legacyPage.dataset.page = "report-navigation";
          const legacyNav = new FakeElement("a"); legacyNav.dataset.page = "report-navigation";
          const root = new FakeElement("html"); root.appendChild(legacyPage); root.appendChild(legacyNav);
          const elements = { modulePageHost: pageHost, moduleSideNavigation: side, moduleTopNavigation: top };
          const documentRef = {
            documentElement: root,
            head: new FakeElement("head"),
            createElement: (tagName) => new FakeElement(tagName),
            getElementById: (id) => elements[id] || null,
            querySelectorAll: (selector) => root.querySelectorAll(selector),
          };
          const listeners = new Map();
          const windowRef = { addEventListener: (name, listener) => listeners.set(name, listener), removeEventListener: (name) => listeners.delete(name), dispatch: (name) => listeners.get(name)?.() };
          return { documentRef, locationRef: { hash }, windowRef, elements, legacyPage, legacyNav };
        }

        (async () => {
        __SCENARIO__
        })().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
        """
    ).replace("__SCENARIO__", textwrap.indent(textwrap.dedent(scenario).strip(), "  "))
    scenario_path = tmp_path / "module_host_review_scenario.cjs"
    scenario_path.write_text(script, encoding="utf-8")
    subprocess.run(["node", str(scenario_path), str(HOST_JS)], check=True, cwd=ROOT)


def test_module_host_owns_module_legacy_visibility_and_hash_history(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment("#alpha");
        const calls = [];
        const instances = {
          alpha: { mount: async () => {}, activate: async () => calls.push("alpha:activate"), deactivate: async () => calls.push("alpha:deactivate"), unmount: async () => {} },
          beta: { mount: async () => {}, activate: async () => calls.push("beta:activate"), deactivate: async () => calls.push("beta:deactivate"), unmount: async () => {} },
        };
        const legacyRoutes = [];
        const host = createModuleHost({ ...env, importModule: async (url) => ({ default: instances[url.includes("beta") ? "beta" : "alpha"] }) });
        const platform = {
          api: async () => ({ modules: [
            { id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] },
            { id: "beta", frontend_entry: "/beta.js", frontend_style: "/beta.css", navigation: [{ id: "beta", label: "Beta", route: "beta" }, { id: "duplicate", label: "Duplicate", route: "alpha" }] },
          ] }),
          user: () => ({}), notify: () => { throw new Error("module errors must not toast"); }, confirm: async () => true,
          legacyNavigate: async (route) => { legacyRoutes.push(route); env.documentRef.documentElement.dataset.page = route; env.legacyPage.hidden = false; },
        };
        assert.equal(await host.initialize(platform), true);
        assert.equal(env.documentRef.documentElement.dataset.page, "module-alpha");
        assert.equal(env.elements.modulePageHost.hidden, false);
        assert.equal(env.legacyPage.hidden, true);
        assert.equal(env.elements.moduleSideNavigation.children.length, 0);
        assert.equal(env.elements.moduleTopNavigation.children.length, 2);
        assert.equal(env.elements.moduleTopNavigation.children[0].getAttribute("aria-current"), "page");
        env.locationRef.hash = "#beta";
        env.windowRef.dispatch("hashchange");
        await new Promise((resolve) => setImmediate(resolve));
        await flush();
        assert.equal(env.documentRef.documentElement.dataset.page, "module-beta");
        assert.equal(env.locationRef.hash, "#beta");
        env.locationRef.hash = "#report-navigation";
        env.windowRef.dispatch("hashchange");
        await new Promise((resolve) => setImmediate(resolve));
        await flush();
        assert.deepEqual(legacyRoutes, ["report-navigation"]);
        assert.equal(env.elements.modulePageHost.hidden, true);
        assert.equal(env.legacyPage.hidden, false);
        env.locationRef.hash = "#alpha";
        env.windowRef.dispatch("hashchange");
        await new Promise((resolve) => setImmediate(resolve));
        await flush();
        assert.equal(env.elements.modulePageHost.hidden, false);
        assert.equal(env.legacyPage.hidden, true);
        assert.equal(env.documentRef.documentElement.dataset.page, "module-alpha");
        """,
    )


def test_module_host_serializes_lifecycle_and_cleans_every_resource(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment();
        const alphaActivation = deferred();
        let apiCalls = 0;
        let partialUnmounts = 0;
        const notifyCalls = [];
        const alpha = { mount: async () => {}, activate: async () => alphaActivation.promise, deactivate: async () => {}, unmount: async () => {} };
        const beta = { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} };
        const partial = { mount: async () => { throw new Error("mount failure"); }, activate: async () => {}, deactivate: async () => {}, unmount: async () => { partialUnmounts += 1; } };
        const host = createModuleHost({
          ...env,
          importModule: async (url) => ({ default: url.includes("partial") ? partial : (url.includes("beta") ? beta : alpha) }),
        });
        const platform = {
          api: async () => { apiCalls += 1; return { modules: [
            { id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] },
            { id: "beta", frontend_entry: "/beta.js", frontend_style: "/beta.css", navigation: [{ id: "beta", label: "Beta", route: "beta" }] },
            { id: "partial", frontend_entry: "/partial.js", frontend_style: "/partial.css", navigation: [{ id: "partial", label: "Partial", route: "partial" }] },
          ] }; },
          user: () => ({}), notify: (...args) => notifyCalls.push(args), confirm: async () => true, legacyNavigate: async () => {},
        };
        await Promise.all([host.initialize(platform), host.initialize(platform)]);
        assert.equal(apiCalls, 1);
        assert.equal(partialUnmounts, 1);
        assert.equal(notifyCalls.length, 0);
        const alphaRequest = host.activate("alpha");
        await flush();
        const betaRequest = host.activate("beta");
        alphaActivation.resolve();
        await Promise.all([alphaRequest, betaRequest]);
        const roots = env.elements.modulePageHost.children.filter((child) => child.dataset.module);
        assert.equal(roots.find((root) => root.dataset.module === "beta").hidden, false);
        assert.equal(roots.find((root) => root.dataset.module === "alpha").hidden, true);
        await host.unmount();
        assert.equal(env.elements.modulePageHost.children.length, 0);
        assert.equal(env.elements.moduleSideNavigation.children.length, 0);
        assert.equal(env.elements.moduleTopNavigation.children.length, 0);
        assert.equal(env.documentRef.head.children.length, 0);
        await host.initialize(platform);
        assert.equal(apiCalls, 2);
        """,
    )


def test_module_host_hashchange_avoids_legacy_reload_and_contains_errors(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const legacyEnv = makeEnvironment("#report-navigation");
        legacyEnv.elements.modulePageHost.hidden = true;
        legacyEnv.documentRef.documentElement.dataset.page = "report-navigation";
        const legacyRoutes = [];
        const legacyHost = createModuleHost({ ...legacyEnv, importModule: async () => ({ default: {} }) });
        const stablePlatform = {
          api: async () => ({ modules: [] }), user: () => ({}), notify: () => { throw new Error("hash errors must not toast"); }, confirm: async () => true,
          legacyNavigate: async (route) => { legacyRoutes.push(route); legacyEnv.documentRef.documentElement.dataset.page = route; },
        };
        assert.equal(await legacyHost.initialize(stablePlatform), false);
        legacyEnv.windowRef.dispatch("hashchange");
        await new Promise((resolve) => setImmediate(resolve));
        assert.deepEqual(legacyRoutes, []);
        legacyEnv.locationRef.hash = "#home";
        legacyEnv.windowRef.dispatch("hashchange");
        await new Promise((resolve) => setImmediate(resolve));
        assert.deepEqual(legacyRoutes, ["home"]);

        const moduleEnv = makeEnvironment("#alpha");
        const moduleRoutes = [];
        const moduleHost = createModuleHost({
          ...moduleEnv,
          importModule: async () => ({ default: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} } }),
        });
        const modulePlatform = {
          api: async () => ({ modules: [{ id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] }] }),
          user: () => ({}), notify: () => { throw new Error("module transition must not toast"); }, confirm: async () => true,
          legacyNavigate: async (route) => { moduleRoutes.push(route); moduleEnv.documentRef.documentElement.dataset.page = route; },
        };
        assert.equal(await moduleHost.initialize(modulePlatform), true);
        moduleEnv.locationRef.hash = "#report-navigation";
        moduleEnv.windowRef.dispatch("hashchange");
        await new Promise((resolve) => setImmediate(resolve));
        assert.deepEqual(moduleRoutes, ["report-navigation"]);

        const errorEnv = makeEnvironment("#report-navigation");
        errorEnv.elements.modulePageHost.hidden = true;
        errorEnv.documentRef.documentElement.dataset.page = "report-navigation";
        const notifyCalls = [];
        const errorHost = createModuleHost({ ...errorEnv, importModule: async () => ({ default: {} }) });
        assert.equal(await errorHost.initialize({
          api: async () => ({ modules: [] }), user: () => ({}), notify: (...args) => notifyCalls.push(args), confirm: async () => true,
          legacyNavigate: async () => { throw new Error("legacy navigation failure"); },
        }), false);
        errorEnv.locationRef.hash = "#home";
        errorEnv.windowRef.dispatch("hashchange");
        await new Promise((resolve) => setImmediate(resolve));
        assert.equal(notifyCalls.length, 0);
        assert.ok(errorEnv.elements.modulePageHost.querySelector("[data-module-host-diagnostic]"));
        """,
    )


def test_module_host_waits_for_styles_and_contains_style_failures(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment("#alpha");
        let imports = 0;
        let mounts = 0;
        env.documentRef.head.appendChild = function appendFailingStyle(child) {
          this.children.push(child);
          child.parentNode = this;
          queueMicrotask(() => child.dispatch("error"));
          return child;
        };
        const host = createModuleHost({
          ...env,
          stylesheetTimeoutMs: 25,
          importModule: async () => {
            imports += 1;
            return { default: { mount: async () => { mounts += 1; }, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} } };
          },
        });
        const platform = {
          api: async () => ({ modules: [{ id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] }] }),
          user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };
        assert.equal(await host.initialize(platform), true);
        assert.equal(imports, 0);
        assert.equal(mounts, 0);
        assert.equal(env.documentRef.head.children.length, 0);
        assert.ok(env.elements.modulePageHost.querySelector("[data-module-host-error]"));
        """,
    )


def test_module_host_waits_for_style_success_and_times_out_safely(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const successEnv = makeEnvironment("#alpha");
        let pendingLink;
        let imports = 0;
        successEnv.documentRef.head.appendChild = function appendPendingStyle(child) {
          this.children.push(child);
          child.parentNode = this;
          pendingLink = child;
          return child;
        };
        const successHost = createModuleHost({
          ...successEnv,
          stylesheetTimeoutMs: 100,
          importModule: async () => { imports += 1; return { default: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} } }; },
        });
        const platform = {
          api: async () => ({ modules: [{ id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] }] }),
          user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };
        const initialized = successHost.initialize(platform);
        await flush();
        assert.equal(imports, 0);
        pendingLink.dispatch("load");
        assert.equal(await initialized, true);
        assert.equal(imports, 1);

        const timeoutEnv = makeEnvironment("#alpha");
        timeoutEnv.documentRef.head.appendChild = function appendNeverLoadedStyle(child) {
          this.children.push(child);
          child.parentNode = this;
          return child;
        };
        let timeoutImports = 0;
        const timeoutHost = createModuleHost({
          ...timeoutEnv,
          stylesheetTimeoutMs: 10,
          importModule: async () => { timeoutImports += 1; throw new Error("must not import"); },
        });
        assert.equal(await timeoutHost.initialize(platform), true);
        assert.equal(timeoutImports, 0);
        assert.equal(timeoutEnv.documentRef.head.children.length, 0);
        assert.ok(timeoutEnv.elements.modulePageHost.querySelector("[data-module-host-error]"));
        """,
    )


def test_module_host_contains_an_import_that_never_settles(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment("#alpha");
        const never = new Promise(() => {});
        let imports = 0;
        const host = createModuleHost({
          ...env,
          moduleImportTimeoutMs: 10,
          importModule: async () => { imports += 1; return never; },
        });
        const platform = {
          api: async () => ({ modules: [{ id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] }] }),
          user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };

        const started = Date.now();
        const initialized = await Promise.race([
          host.initialize(platform),
          new Promise((_, reject) => setTimeout(() => reject(new Error("module import deadlocked")), 250)),
        ]);
        assert.equal(initialized, true);

        assert.ok(Date.now() - started < 250);
        assert.equal(imports, 1);
        assert.equal(env.documentRef.head.children.length, 0);
        assert.ok(env.elements.modulePageHost.querySelector("[data-module-host-error]"));
        """,
    )


def test_module_host_defers_lifecycle_navigation_without_queue_deadlock(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const modules = [
          { id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] },
          { id: "beta", frontend_entry: "/beta.js", frontend_style: "/beta.css", navigation: [{ id: "beta", label: "Beta", route: "beta" }] },
        ];
        const platform = {
          api: async () => ({ modules }), user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };

        const mountEnv = makeEnvironment("#alpha");
        const mountInstances = {
          alpha: { mount: async (context) => { assert.equal(await context.navigate("beta"), true); }, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} },
          beta: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} },
        };
        const mountHost = createModuleHost({ ...mountEnv, importModule: async (url) => ({ default: mountInstances[url.includes("beta") ? "beta" : "alpha"] }) });
        await Promise.race([
          mountHost.initialize(platform),
          new Promise((_, reject) => setTimeout(() => reject(new Error("mount navigation deadlocked")), 100)),
        ]);
        const mountRoots = mountEnv.elements.modulePageHost.children.filter((child) => child.dataset.module);
        assert.equal(mountRoots.find((root) => root.dataset.module === "beta").hidden, false);

        const activateEnv = makeEnvironment("#alpha");
        let alphaContext;
        const activateInstances = {
          alpha: { mount: async (context) => { alphaContext = context; }, activate: async () => { assert.equal(await alphaContext.navigate("beta"), true); }, deactivate: async () => {}, unmount: async () => {} },
          beta: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} },
        };
        const activateHost = createModuleHost({ ...activateEnv, importModule: async (url) => ({ default: activateInstances[url.includes("beta") ? "beta" : "alpha"] }) });
        await Promise.race([
          activateHost.initialize(platform),
          new Promise((_, reject) => setTimeout(() => reject(new Error("activate navigation deadlocked")), 100)),
        ]);
        const activateRoots = activateEnv.elements.modulePageHost.children.filter((child) => child.dataset.module);
        assert.equal(activateRoots.find((root) => root.dataset.module === "beta").hidden, false);
        assert.equal(activateEnv.locationRef.hash, "#beta");
        """,
    )


def test_module_host_defers_legacy_navigation_until_lifecycle_queue_is_released(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const modules = [{ id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] }];
        const mountEnv = makeEnvironment("#alpha");
        let mountHost;
        const mountLegacyRoutes = [];
        const mountInstance = {
          mount: async (value) => { assert.equal(await value.navigate("report-navigation"), false); },
          activate: async () => {}, deactivate: async () => {}, unmount: async () => {},
        };
        mountHost = createModuleHost({ ...mountEnv, importModule: async () => ({ default: mountInstance }) });
        const mountPlatform = {
          api: async () => ({ modules }), user: () => ({}), notify: () => {}, confirm: async () => true,
          legacyNavigate: async (route) => { await mountHost.deactivate(); mountLegacyRoutes.push(route); },
        };
        assert.equal(await Promise.race([
          mountHost.initialize(mountPlatform),
          new Promise((_, reject) => setTimeout(() => reject(new Error("mount legacy navigation deadlocked")), 100)),
        ]), true);
        await new Promise((resolve) => setImmediate(resolve));
        await flush();
        assert.deepEqual(mountLegacyRoutes, ["report-navigation"]);

        const env = makeEnvironment("#alpha");
        let context;
        let host;
        const legacyRoutes = [];
        const instance = {
          mount: async (value) => { context = value; },
          activate: async () => { assert.equal(await context.navigate("report-navigation"), false); },
          deactivate: async () => {},
          unmount: async () => {},
        };
        host = createModuleHost({ ...env, importModule: async () => ({ default: instance }) });
        const platform = {
          api: async () => ({ modules }),
          user: () => ({}), notify: () => {}, confirm: async () => true,
          legacyNavigate: async (route) => {
            await host.deactivate();
            legacyRoutes.push(route);
          },
        };
        assert.equal(await Promise.race([
          host.initialize(platform),
          new Promise((_, reject) => setTimeout(() => reject(new Error("legacy navigation deadlocked")), 100)),
        ]), true);
        await new Promise((resolve) => setImmediate(resolve));
        await flush();
        assert.deepEqual(legacyRoutes, ["report-navigation"]);
        assert.equal(env.elements.modulePageHost.hidden, true);
        """,
    )


def test_module_host_does_not_attribute_stale_navigation_to_another_module(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment("#alpha");
        const betaActivation = deferred();
        let alphaContext;
        const instances = {
          alpha: { mount: async (context) => { alphaContext = context; }, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} },
          beta: { mount: async () => {}, activate: async () => betaActivation.promise, deactivate: async () => {}, unmount: async () => {} },
        };
        const host = createModuleHost({ ...env, importModule: async (url) => ({ default: instances[url.includes("beta") ? "beta" : "alpha"] }) });
        const platform = {
          api: async () => ({ modules: [
            { id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] },
            { id: "beta", frontend_entry: "/beta.js", frontend_style: "/beta.css", navigation: [{ id: "beta", label: "Beta", route: "beta" }] },
          ] }),
          user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };
        assert.equal(await host.initialize(platform), true);
        const activatingBeta = host.activate("beta");
        await flush();
        assert.equal(await alphaContext.navigate("alpha"), false);
        betaActivation.resolve();
        assert.equal(await activatingBeta, true);
        const roots = env.elements.modulePageHost.children.filter((child) => child.dataset.module);
        assert.equal(roots.find((root) => root.dataset.module === "beta").hidden, false);
        assert.equal(env.locationRef.hash, "#beta");
        """,
    )


def test_module_host_cancels_stale_legacy_intent_after_newer_navigation(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment("#alpha");
        const intentReady = deferred();
        const releaseAlpha = deferred();
        const legacyRoutes = [];
        let alphaContext;
        const instances = {
          alpha: {
            mount: async (context) => { alphaContext = context; },
            activate: async (route) => {
              if (route !== "alpha-alt") return;
              assert.equal(await alphaContext.navigate("report-navigation"), false);
              intentReady.resolve();
              await releaseAlpha.promise;
            },
            deactivate: async () => {}, unmount: async () => {},
          },
          beta: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} },
        };
        const host = createModuleHost({ ...env, importModule: async (url) => ({ default: instances[url.includes("beta") ? "beta" : "alpha"] }) });
        const platform = {
          api: async () => ({ modules: [
            { id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }, { id: "alpha-alt", label: "Alpha alt", route: "alpha-alt" }] },
            { id: "beta", frontend_entry: "/beta.js", frontend_style: "/beta.css", navigation: [{ id: "beta", label: "Beta", route: "beta" }] },
          ] }),
          user: () => ({}), notify: () => {}, confirm: async () => true,
          legacyNavigate: async (route) => { legacyRoutes.push(route); await host.deactivate(); },
        };
        assert.equal(await host.initialize(platform), true);
        const staleRequest = host.activate("alpha-alt");
        await intentReady.promise;
        const currentRequest = host.activate("beta");
        releaseAlpha.resolve();
        await Promise.all([staleRequest, currentRequest]);
        await new Promise((resolve) => setImmediate(resolve));
        await flush();
        assert.deepEqual(legacyRoutes, []);
        const roots = env.elements.modulePageHost.children.filter((child) => child.dataset.module);
        assert.equal(roots.find((root) => root.dataset.module === "beta").hidden, false);
        assert.equal(env.locationRef.hash, "#beta");
        """,
    )


def test_module_host_does_not_start_a_stale_module_redirect(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment("#alpha");
        const intentReady = deferred();
        const releaseAlpha = deferred();
        let alphaContext;
        let betaActivations = 0;
        const instances = {
          alpha: {
            mount: async (context) => { alphaContext = context; },
            activate: async (route) => {
              if (route !== "alpha-alt") return;
              assert.equal(await alphaContext.navigate("beta"), true);
              intentReady.resolve();
              await releaseAlpha.promise;
            },
            deactivate: async () => {}, unmount: async () => {},
          },
          beta: { mount: async () => {}, activate: async () => { betaActivations += 1; }, deactivate: async () => {}, unmount: async () => {} },
          gamma: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} },
        };
        const host = createModuleHost({
          ...env,
          importModule: async (url) => ({ default: instances[url.includes("beta") ? "beta" : (url.includes("gamma") ? "gamma" : "alpha")] }),
        });
        const platform = {
          api: async () => ({ modules: [
            { id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }, { id: "alpha-alt", label: "Alpha alt", route: "alpha-alt" }] },
            { id: "beta", frontend_entry: "/beta.js", frontend_style: "/beta.css", navigation: [{ id: "beta", label: "Beta", route: "beta" }] },
            { id: "gamma", frontend_entry: "/gamma.js", frontend_style: "/gamma.css", navigation: [{ id: "gamma", label: "Gamma", route: "gamma" }] },
          ] }),
          user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };
        assert.equal(await host.initialize(platform), true);
        const staleRequest = host.activate("alpha-alt");
        await intentReady.promise;
        const currentRequest = host.activate("gamma");
        releaseAlpha.resolve();
        await Promise.all([staleRequest, currentRequest]);
        assert.equal(betaActivations, 0);
        const roots = env.elements.modulePageHost.children.filter((child) => child.dataset.module);
        assert.equal(roots.find((root) => root.dataset.module === "gamma").hidden, false);
        assert.equal(env.locationRef.hash, "#gamma");
        """,
    )


def test_module_host_bounds_stuck_lifecycle_callbacks(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const mountEnv = makeEnvironment("#alpha");
        const never = new Promise(() => {});
        let imports = 0;
        const stuckMountHost = createModuleHost({
          ...mountEnv,
          lifecycleTimeoutMs: 10,
          importModule: async () => {
            imports += 1;
            return { default: { mount: async () => never, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} } };
          },
        });
        const platform = {
          api: async () => ({ modules: [{ id: "alpha", frontend_entry: "/alpha.js", frontend_style: "/alpha.css", navigation: [{ id: "alpha", label: "Alpha", route: "alpha" }] }] }),
          user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };
        assert.equal(await Promise.race([
          stuckMountHost.initialize(platform),
          new Promise((_, reject) => setTimeout(() => reject(new Error("mount timeout did not release host")), 100)),
        ]), true);
        assert.equal(imports, 1);
        assert.ok(mountEnv.elements.modulePageHost.querySelector("[data-module-host-error]"));

        const unmountEnv = makeEnvironment("#alpha");
        const stuckUnmountHost = createModuleHost({
          ...unmountEnv,
          lifecycleTimeoutMs: 10,
          importModule: async () => ({ default: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => never } }),
        });
        assert.equal(await stuckUnmountHost.initialize(platform), true);
        await Promise.race([
          stuckUnmountHost.unmount(),
          new Promise((_, reject) => setTimeout(() => reject(new Error("unmount timeout did not release host")), 100)),
        ]);
        assert.equal(unmountEnv.elements.modulePageHost.children.length, 0);
        """,
    )


def test_module_host_clears_legacy_smart_reconcile_active_when_activating_module(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment("#special");
        const smartGroup = new FakeElement("div");
        smartGroup.classList.add("top-nav-group");
        smartGroup.classList.add("active");
        smartGroup.classList.add("open");
        smartGroup.dataset.navGroup = "smart-reconcile";
        smartGroup.setAttribute("data-nav-group", "smart-reconcile");
        const smartToggle = new FakeElement("button");
        smartToggle.classList.add("top-nav-item");
        smartToggle.classList.add("top-nav-group-toggle");
        smartToggle.classList.add("active");
        smartToggle.dataset.navGroupToggle = "smart-reconcile";
        smartToggle.setAttribute("data-nav-group-toggle", "smart-reconcile");
        smartToggle.setAttribute("aria-expanded", "true");
        smartGroup.appendChild(smartToggle);
        env.documentRef.documentElement.appendChild(smartGroup);

        const host = createModuleHost({
          ...env,
          importModule: async () => ({ default: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} } }),
        });
        const platform = {
          api: async () => ({ modules: [
            { id: "special", frontend_entry: "/special.js", frontend_style: "/special.css", navigation: [
              { id: "special-entry", label: "Special entry", route: "special", order: 1, group_id: "data-entry", group_label: "Data entry", group_order: 1 },
            ] },
          ] }),
          user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };
        assert.equal(await host.initialize(platform), true);
        assert.equal(smartGroup.classList.contains("active"), false);
        assert.equal(smartGroup.classList.contains("open"), false);
        assert.equal(smartToggle.classList.contains("active"), false);
        assert.equal(smartToggle.getAttribute("aria-expanded"), "false");
        const moduleGroup = env.elements.moduleTopNavigation.children[0];
        assert.ok(moduleGroup.children[0].classList.contains("active"));
        """,
    )


def test_module_host_renders_top_grouped_navigation_and_keeps_sidebar_empty(tmp_path: Path):
    _run_module_host_scenario(
        tmp_path,
        """
        const env = makeEnvironment("#review-new");
        const host = createModuleHost({
          ...env,
          importModule: async () => ({ default: { mount: async () => {}, activate: async () => {}, deactivate: async () => {}, unmount: async () => {} } }),
        });
        const grouped = (id, label, route, order, groupId, groupLabel, groupOrder) => ({
          id, label, route, order, group_id: groupId, group_label: groupLabel, group_order: groupOrder,
        });
        const platform = {
          api: async () => ({ modules: [
            { id: "review", frontend_entry: "/review.js", frontend_style: "/review.css", navigation: [
              grouped("review-new", "New review", "review-new", 2, "review", "Reviews", 2),
              grouped("review-history", "Review history", "review-history", 1, "review", "Reviews", 2),
            ] },
            { id: "data", frontend_entry: "/data.js", frontend_style: "/data.css", navigation: [
              grouped("data-import", "Import data", "data-import", 1, "data", "Data", 1),
            ] },
            { id: "legacy", frontend_entry: "/legacy.js", frontend_style: "/legacy.css", navigation: [
              { id: "legacy-b", label: "Legacy B", route: "legacy-b", order: 2 },
              { id: "legacy-a", label: "Legacy A", route: "legacy-a", order: 1 },
            ] },
            { id: "empty", frontend_entry: "/empty.js", frontend_style: "/empty.css", navigation: [] },
          ] }),
          user: () => ({}), notify: () => {}, confirm: async () => true, legacyNavigate: async () => {},
        };
        assert.equal(await host.initialize(platform), true);
        const top = env.elements.moduleTopNavigation;
        const side = env.elements.moduleSideNavigation;
        assert.equal(side.children.length, 0);
        assert.equal(top.children.length, 4);
        const dataGroup = top.children[0];
        const reviewGroup = top.children[1];
        assert.equal(dataGroup.children[0].textContent, "Data");
        assert.equal(reviewGroup.children[0].textContent, "Reviews");
        assert.equal(top.children[2].textContent, "Legacy A");
        const reviewToggle = reviewGroup.children[0];
        const reviewMenu = reviewGroup.children[1];
        assert.ok(dataGroup.className.includes("top-nav-group"));
        assert.ok(reviewToggle.className.includes("top-nav-group-toggle"));
        assert.ok(reviewMenu.className.includes("top-nav-submenu"));
        assert.ok(reviewMenu.children[0].className.includes("top-nav-subitem"));
        assert.equal(reviewMenu.children[0].textContent, "Review history");
        assert.equal(reviewMenu.children[1].textContent, "New review");
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "false");
        assert.equal(reviewToggle.getAttribute("aria-controls"), reviewMenu.id);
        assert.equal(reviewMenu.getAttribute("aria-label"), "Reviews");
        assert.ok(reviewToggle.classList.contains("active"));
        assert.equal(reviewMenu.children[1].getAttribute("aria-current"), "page");

        top.dispatch("keydown", reviewToggle, { key: "Escape" });
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "false");
        assert.equal(reviewMenu.hidden, true);
        assert.equal(reviewToggle.focused, true);
        reviewGroup.dispatch("mouseenter");
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "true");
        assert.equal(reviewMenu.hidden, false);
        reviewGroup.dispatch("mouseleave");
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "true");
        reviewGroup.dispatch("mouseenter");
        await new Promise((resolve) => setTimeout(resolve, 150));
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "true");
        assert.equal(reviewMenu.hidden, false);
        reviewGroup.dispatch("mouseleave");
        await new Promise((resolve) => setTimeout(resolve, 150));
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "false");
        assert.equal(reviewMenu.hidden, true);
        top.dispatch("keydown", reviewToggle, { key: " " });
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "true");
        // 鼠标点击已展开的父菜单不应收起、也不跳转任何页面（与"悬浮展开、父菜单不跳转"契约一致）。
        const hashBeforeClick = env.locationRef.hash;
        top.dispatch("click", reviewToggle);
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "true");
        assert.equal(reviewMenu.hidden, false);
        assert.equal(env.locationRef.hash, hashBeforeClick);
        top.dispatch("keydown", reviewMenu.children[0], { key: "Escape" });
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "false");
        assert.equal(reviewMenu.hidden, true);
        assert.equal(reviewToggle.focused, true);
        top.dispatch("keydown", reviewToggle, { key: " " });
        top.dispatch("click", reviewMenu.children[0]);
        await new Promise((resolve) => setImmediate(resolve));
        await flush();
        assert.equal(env.locationRef.hash, "#review-history");
        assert.ok(reviewToggle.classList.contains("active"));
        assert.equal(reviewMenu.children[0].getAttribute("aria-current"), "page");
        top.dispatch("click", dataGroup.children[0]);
        assert.equal(dataGroup.children[0].getAttribute("aria-expanded"), "true");
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "false");
        assert.equal(await host.activate("legacy-a"), true);
        assert.equal(dataGroup.children[0].getAttribute("aria-expanded"), "false");
        assert.equal(reviewToggle.getAttribute("aria-expanded"), "false");
        assert.equal(top.children[2].getAttribute("aria-current"), "page");
        assert.equal(await host.reload(), true);
        assert.equal(top.children.length, 4);
        assert.equal(top.listeners.size, 2);
        assert.equal(side.children.length, 0);
        await host.unmount();
        assert.equal(top.children.length, 0);
        assert.equal(top.listeners.size, 0);
        assert.equal(side.children.length, 0);
        """,
    )
