from __future__ import annotations

import subprocess
import textwrap
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
    assert "\nbutton {" not in css
    assert "\ninput {" not in css
    assert "\ntable {" not in css


def test_module_navigation_buttons_use_scoped_reset_and_accessible_active_state():
    css = HOST_CSS.read_text(encoding="utf-8")

    assert "#moduleSideNavigation .module-nav-item" in css
    assert "#moduleTopNavigation .module-top-nav-item" in css
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
          appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
          replaceChildren(...children) { this.children = []; children.forEach((child) => this.appendChild(child)); }
          addEventListener(type, listener) { this.listeners.set(type, listener); }
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
          assert.equal(elements.moduleSideNavigation.children.length, 2);
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
              remove: (name) => this.classList.values.delete(name),
              toggle: (name, enabled) => enabled ? this.classList.values.add(name) : this.classList.values.delete(name),
              contains: (name) => this.classList.values.has(name),
            };
          }
          appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
          replaceChildren(...children) { this.children.slice().forEach((child) => { child.parentNode = null; }); this.children = []; children.forEach((child) => this.appendChild(child)); }
          remove() { if (!this.parentNode) return; this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.parentNode = null; }
          contains(target) { return this.children.includes(target) || this.children.some((child) => child.contains?.(target)); }
          addEventListener(type, listener) { this.listeners.set(type, listener); }
          dispatch(type, target = this) { return this.listeners.get(type)?.({ target, preventDefault() {} }); }
          closest(selector) { return selector === "[data-module-route]" && this.dataset.moduleRoute ? this : null; }
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
        assert.equal(env.elements.moduleSideNavigation.children.length, 2);
        assert.equal(env.elements.moduleTopNavigation.children.length, 2);
        assert.equal(env.elements.moduleSideNavigation.children[0].getAttribute("aria-current"), "page");
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
