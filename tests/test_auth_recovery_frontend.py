"""Node 场景测试：登录超时原账号重新认证状态机与请求恢复。

这些测试通过 ``node`` 子进程运行最小 DOM stub，验证
``src/auto_check/web/auth_recovery.js`` 的重新认证状态机，以及主应用
``authenticatedFetch``/``api`` 的自动重试行为。设计依据：
``docs/superpowers/specs/2026-09-04-session-expiry-reauthentication-design.md``。
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTH_RECOVERY_JS = ROOT / "src" / "auto_check" / "web" / "auth_recovery.js"


# 一个足够支撑重新认证遮罩交互的最小 DOM 实现。auth_recovery.js 在找不到
# 既有遮罩节点时会自行创建，因此这里只需提供节点创建、事件与基础属性能力。
DOM_STUB = r"""
function makeClassList() {
  const set = new Set();
  return {
    add: (...names) => names.forEach((n) => set.add(n)),
    remove: (...names) => names.forEach((n) => set.delete(n)),
    contains: (name) => set.has(name),
    toggle: (name) => (set.has(name) ? set.delete(name) : set.add(name)),
  };
}

let EVENT_LOG = [];

function makeElement(tagName) {
  const element = {
    tagName: String(tagName || "div").toUpperCase(),
    children: [],
    parentNode: null,
    attributes: {},
    dataset: {},
    style: { setProperty() {}, removeProperty() {} },
    classList: makeClassList(),
    _listeners: {},
    textContent: "",
    innerHTML: "",
    value: "",
    hidden: false,
    disabled: false,
    readOnly: false,
    type: "",
    id: "",
    _focused: false,
    addEventListener(type, handler) {
      (this._listeners[type] = this._listeners[type] || []).push(handler);
    },
    removeEventListener(type, handler) {
      this._listeners[type] = (this._listeners[type] || []).filter((h) => h !== handler);
    },
    dispatchEvent(event) {
      event.target = event.target || this;
      const handlers = (this._listeners[event.type] || []).slice();
      for (const handler of handlers) handler.call(this, event);
      return true;
    },
    appendChild(child) {
      if (child.parentNode) child.parentNode.removeChild(child);
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      this.children = this.children.filter((item) => item !== child);
      child.parentNode = null;
      return child;
    },
    remove() {
      if (this.parentNode) this.parentNode.removeChild(this);
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name === "hidden") this.hidden = true;
      if (name === "disabled") this.disabled = true;
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name)
        ? this.attributes[name]
        : null;
    },
    hasAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name);
    },
    removeAttribute(name) {
      delete this.attributes[name];
      if (name === "hidden") this.hidden = false;
      if (name === "disabled") this.disabled = false;
    },
    focus() {
      this._focused = true;
    },
    select() {},
    click() {
      this.dispatchEvent({ type: "click", target: this, preventDefault() {}, stopPropagation() {} });
    },
    contains(other) {
      let node = other;
      while (node) {
        if (node === this) return true;
        node = node.parentNode;
      }
      return false;
    },
    querySelector(selector) {
      return findById(this, selector.replace(/^#/, ""));
    },
    querySelectorAll(selector) {
      const found = findById(this, selector.replace(/^#/, ""));
      return found ? [found] : [];
    },
  };
  return element;
}

function findById(root, id) {
  if (!root) return null;
  if (root.id === id) return root;
  for (const child of root.children || []) {
    const match = findById(child, id);
    if (match) return match;
  }
  return null;
}

function makeDocument() {
  const body = makeElement("body");
  const documentElement = makeElement("html");
  const doc = {
    body,
    documentElement,
    _listeners: {},
    createElement: (tag) => makeElement(tag),
    createTextNode: (text) => ({ textContent: String(text) }),
    getElementById(id) {
      return findById(body, id);
    },
    addEventListener(type, handler) {
      (this._listeners[type] = this._listeners[type] || []).push(handler);
    },
    removeEventListener(type, handler) {
      this._listeners[type] = (this._listeners[type] || []).filter((h) => h !== handler);
    },
    dispatchEvent(event) {
      const handlers = (this._listeners[event.type] || []).slice();
      for (const handler of handlers) handler.call(this, event);
      return true;
    },
    querySelector(selector) {
      return findById(body, selector.replace(/^#/, ""));
    },
    querySelectorAll() {
      return [];
    },
  };
  return doc;
}

function makeEvent(type, extra = {}) {
  return Object.assign(
    { type, preventDefault() {}, stopPropagation() {} },
    extra,
  );
}
"""


def _scenario(tmp_path: Path, body: str, name: str = "scenario") -> subprocess.CompletedProcess:
    script = textwrap.dedent(
        f"""\
        const assert = require("node:assert/strict");
        globalThis.window = globalThis.window || {{}};
        {DOM_STUB}
        const {{ createAuthRecovery, AuthRecoveryCancelledError }} = require({json.dumps(str(AUTH_RECOVERY_JS))});
        const documentRef = makeDocument();
        async function runScenario() {{
        {textwrap.indent(body, '  ')}
        }}
        runScenario().then(
          () => {{ console.log("OK"); }},
          (error) => {{ console.error(error && error.stack || error); process.exitCode = 1; }}
        );
        """
    )
    path = tmp_path / f"{name}.cjs"
    path.write_text(script, encoding="utf-8")
    return subprocess.run(["node", str(path)], cwd=ROOT, text=True, capture_output=True)


def _assert_ok(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, (
        f"node scenario failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "OK" in result.stdout


def _overlay_handles(doc_expr: str = "documentRef") -> str:
    """Return JS that fetches overlay elements by id for assertions."""
    return f"""
    const overlay = {doc_expr}.getElementById("authRecoveryOverlay");
    const username = {doc_expr}.getElementById("authRecoveryUsername");
    const password = {doc_expr}.getElementById("authRecoveryPassword");
    const exitButton = {doc_expr}.getElementById("authRecoveryExit");
    const submitButton = {doc_expr}.getElementById("authRecoverySubmit");
    """


def test_auth_recovery_script_exists_and_exports_factory(tmp_path: Path) -> None:
    assert AUTH_RECOVERY_JS.exists(), "auth_recovery.js must exist"
    result = _scenario(
        tmp_path,
        "assert.equal(typeof createAuthRecovery, 'function');",
        name="exports",
    )
    # 若脚本不存在，require 会抛错，返回码非 0。
    assert result.returncode == 0, result.stderr


def test_concurrent_recover_shares_single_promise_and_overlay(tmp_path: Path) -> None:
    body = f"""
    const authenticateCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan", display_name: "张三" }}),
      authenticate: async ({{ username, password }}) => {{
        authenticateCalls.push({{ username, password }});
        return {{ csrf_token: "new-token", user: {{ id: "user-1", username: "zhangsan" }} }};
      }},
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{}},
    }});
    const first = recovery.recover();
    const second = recovery.recover();
    assert.equal(first, second, "recover() must return the same promise while recovering");
    assert.equal(recovery.isRecovering(), true);
    {_overlay_handles()}
    assert.ok(overlay, "overlay element must exist");
    assert.equal(overlay.hidden, false, "overlay must be visible during recovery");
    assert.equal(username.textContent, "zhangsan");
    assert.equal(recovery.isRecovering(), true);
    """
    _assert_ok(_scenario(tmp_path, body, name="concurrent_recover"))


def test_wrong_password_keeps_waiting_and_clears_password(tmp_path: Path) -> None:
    body = f"""
    let attempts = 0;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => {{
        attempts += 1;
        if (attempts === 1) throw new Error("账号或密码验证失败");
        return {{ csrf_token: "t2", user: {{ id: "user-1", username: "zhangsan" }} }};
      }},
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{}},
    }});
    const promise = recovery.recover();
    {_overlay_handles()}
    password.value = "bad-password";
    submitButton.click();
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(recovery.isRecovering(), true, "must stay in recovery after wrong password");
    assert.equal(password.value, "", "password must be cleared after a failed attempt");
    // 第二次正确密码后恢复完成
    password.value = "good";
    submitButton.click();
    await promise;
    assert.equal(attempts, 2);
    assert.equal(recovery.isRecovering(), false);
    """
    _assert_ok(_scenario(tmp_path, body, name="wrong_password"))


def test_identity_mismatch_discards_new_session(tmp_path: Path) -> None:
    body = f"""
    const discarded = [];
    let exited = false;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{
        csrf_token: "other-token",
        user: {{ id: "user-9", username: "lisi" }},
      }}),
      applySession: async () => {{ throw new Error("must not apply mismatched session"); }},
      discardSession: async (payload) => {{ discarded.push(payload); }},
      exitSession: () => {{ exited = true; }},
    }});
    const promise = recovery.recover();
    {_overlay_handles()}
    password.value = "whatever";
    submitButton.click();
    const settled = await Promise.race([
      promise.then(() => "resolved", (error) => error),
      new Promise((resolve) => setTimeout(() => resolve("pending"), 50)),
    ]);
    assert.equal(discarded.length, 1, "mismatched session must be discarded");
    assert.equal(settled.name, "AuthRecoveryCancelledError");
    assert.equal(exited, true, "must exit after discarding mismatched session");
    """
    _assert_ok(_scenario(tmp_path, body, name="identity_mismatch"))


def test_apply_session_failure_enters_discarding_and_retries(tmp_path: Path) -> None:
    body = f"""
    let discardAttempts = 0;
    let exited = false;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "tok", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{ throw new Error("apply failed"); }},
      discardSession: async () => {{
        discardAttempts += 1;
        if (discardAttempts === 1) throw new Error("logout failed");
      }},
      exitSession: () => {{ exited = true; }},
    }});
    const promise = recovery.recover();
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(discardAttempts, 1);
    assert.equal(recovery.isRecovering(), true, "must remain blocked while discarding");
    assert.equal(exited, false, "must not exit before discard succeeds");
    assert.equal(password.disabled, true, "password disabled during discarding");
    assert.equal(submitButton.disabled, true, "submit disabled during discarding");
    // 重试退出按钮再次触发注销，成功后才退出
    exitButton.click();
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(discardAttempts, 2);
    assert.equal(exited, true, "exit only after discard succeeds");
    """
    _assert_ok(_scenario(tmp_path, body, name="apply_failure_discarding"))


def test_exit_system_rejects_waiters_and_calls_exit(tmp_path: Path) -> None:
    body = f"""
    let exited = false;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{ exited = true; }},
    }});
    const promise = recovery.recover();
    {_overlay_handles()}
    exitButton.click();
    const error = await promise.then(() => null, (err) => err);
    assert.ok(error instanceof AuthRecoveryCancelledError, "exit must reject waiters");
    assert.equal(exited, true);
    assert.equal(recovery.isRecovering(), false);
    assert.equal(password.value, "", "password cleared on exit");
    """
    _assert_ok(_scenario(tmp_path, body, name="exit_system"))


def test_discard_unexpected_session_blocks_and_exits(tmp_path: Path) -> None:
    body = f"""
    const discarded = [];
    let exited = false;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => {{ throw new Error("must not prompt password"); }},
      applySession: async () => {{}},
      discardSession: async (payload) => {{ discarded.push(payload); }},
      exitSession: () => {{ exited = true; }},
    }});
    const resultPromise = recovery.discardUnexpectedSession({{
      csrf_token: "unexpected",
      user: {{ id: "user-2", username: "wangwu" }},
    }});
    {_overlay_handles()}
    assert.ok(overlay, "overlay must open in discarding mode");
    assert.equal(overlay.hidden, false);
    const error = await resultPromise.then(() => null, (err) => err);
    assert.ok(error instanceof AuthRecoveryCancelledError);
    assert.equal(discarded.length, 1);
    assert.equal(discarded[0].user.username, "wangwu");
    assert.equal(exited, true);
    assert.equal(recovery.isRecovering(), false);
    """
    _assert_ok(_scenario(tmp_path, body, name="discard_unexpected"))


def test_esc_and_background_do_not_close_overlay(tmp_path: Path) -> None:
    body = f"""
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{}},
    }});
    recovery.recover();
    {_overlay_handles()}
    documentRef.dispatchEvent(makeEvent("keydown", {{ key: "Escape" }}));
    overlay.dispatchEvent(makeEvent("click", {{ target: overlay }}));
    assert.equal(overlay.hidden, false, "overlay must not close on Esc or background click");
    assert.equal(recovery.isRecovering(), true);
    """
    _assert_ok(_scenario(tmp_path, body, name="esc_background"))


def test_repeated_submit_is_guarded(tmp_path: Path) -> None:
    body = f"""
    let attempts = 0;
    let resolveAuth;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => {{
        attempts += 1;
        await new Promise((resolve) => {{ resolveAuth = resolve; }});
        return {{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }};
      }},
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{}},
    }});
    const promise = recovery.recover();
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    submitButton.click();
    submitButton.click();
    await new Promise((resolve) => setTimeout(resolve, 5));
    assert.equal(attempts, 1, "concurrent submits must not trigger multiple authentications");
    resolveAuth();
    await promise;
    """
    _assert_ok(_scenario(tmp_path, body, name="repeat_submit"))


def test_destroy_cleans_password_and_listeners(tmp_path: Path) -> None:
    body = f"""
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{}},
    }});
    recovery.recover();
    {_overlay_handles()}
    password.value = "secret";
    recovery.destroy();
    assert.equal(password.value, "", "destroy must clear the password field");
    assert.equal(recovery.isRecovering(), false);
    """
    _assert_ok(_scenario(tmp_path, body, name="destroy"))


# ---------------------------------------------------------------------------
# authenticatedFetch / api 请求恢复（从 app.js 提取请求层在 Node 中运行）
# ---------------------------------------------------------------------------

def _request_layer_source() -> str:
    app_js = (ROOT / "src" / "auto_check" / "web" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("// Auth recovery request layer start")
    end = app_js.index("// Auth recovery request layer end")
    return app_js[start:end]


# Node 场景运行在打包 builder 镜像（Node 16）时没有浏览器/Node18+ 的 WHATWG 全局。
# app.js 请求层用到 `new Headers(init)`，构造入参可能是普通对象、二元组数组，或
# 已有 Headers 实例（透传测试）。这里只在宿主缺失时补一个最小且大小写不敏感的实现，
# 使被测代码逻辑不依赖"宿主碰巧带了哪些内置对象"。
BROWSER_GLOBAL_POLYFILL = r"""
if (typeof globalThis.Headers === "undefined") {
  class HeadersPolyfill {
    constructor(init) {
      this._map = new Map();
      const append = (name, value) => {
        this._map.set(String(name).toLowerCase(), String(value));
      };
      if (init instanceof HeadersPolyfill) {
        init.forEach((value, name) => append(name, value));
      } else if (Array.isArray(init)) {
        for (const pair of init) append(pair[0], pair[1]);
      } else if (init && typeof init === "object") {
        for (const name of Object.keys(init)) append(name, init[name]);
      }
    }
    get(name) {
      const key = String(name).toLowerCase();
      return this._map.has(key) ? this._map.get(key) : null;
    }
    set(name, value) {
      this._map.set(String(name).toLowerCase(), String(value));
    }
    has(name) {
      return this._map.has(String(name).toLowerCase());
    }
    delete(name) {
      this._map.delete(String(name).toLowerCase());
    }
    forEach(callback, thisArg) {
      for (const [key, value] of this._map) callback.call(thisArg, value, key, this);
    }
  }
  globalThis.Headers = HeadersPolyfill;
}
"""

REQUEST_LAYER_STUBS = r"""
const authState = { csrfToken: "old-token", user: { id: "user-1", username: "zhangsan" } };
const applyCalls = [];
const discardCalls = [];
const recoverCalls = [];
async function applyReauthenticatedSession(payload) {
  applyCalls.push(payload);
  authState.csrfToken = payload.csrf_token;
  authState.user = payload.user;
}
function formatApiErrorMessage(message) { return String(message || ""); }
globalThis.window = globalThis.window || {};
window.AutoCheckAuthRecovery = window.AutoCheckAuthRecovery || {
  AuthRecoveryCancelledError: class extends Error {
    constructor(message = "authentication recovery cancelled") {
      super(message);
      this.name = "AuthRecoveryCancelledError";
    }
  },
};
const fetchCalls = [];
const responders = [];
globalThis.fetch = async (path, options) => {
  const call = { path, options: options || {} };
  fetchCalls.push(call);
  if (!responders.length) throw new Error("no responder for " + path);
  const next = responders.shift();
  return typeof next === "function" ? next(call) : next;
};
function makeResponse({ status = 200, headers = {}, body = null } = {}) {
  const headerMap = new Map(Object.entries(headers));
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: (name) => (headerMap.has(name) ? headerMap.get(name) : null) },
    clone() { return this; },
    async json() {
      if (body === null || body === undefined) throw new Error("empty body");
      return typeof body === "string" ? JSON.parse(body) : body;
    },
  };
}
const REQUIRED = { "X-Auto-Check-Auth-Recovery": "required" };
const MISMATCH = { "X-Auto-Check-Auth-Recovery": "account-mismatch" };
const authRecovery = {
  recover: async () => {
    recoverCalls.push(1);
    authState.csrfToken = "new-token";
  },
  discardUnexpectedSession: async (payload) => {
    discardCalls.push(payload);
    throw new window.AutoCheckAuthRecovery.AuthRecoveryCancelledError();
  },
};
"""


def _run_request_layer_scenario(tmp_path: Path, scenario: str, name: str) -> subprocess.CompletedProcess:
    script = textwrap.dedent(
        f"""\
        const assert = require("node:assert/strict");
        {BROWSER_GLOBAL_POLYFILL}
        {REQUEST_LAYER_STUBS}
        {_request_layer_source()}
        async function runScenario() {{
        {textwrap.indent(scenario, '  ')}
        }}
        runScenario().then(
          () => {{ console.log("OK"); }},
          (error) => {{ console.error(error && error.stack || error); process.exitCode = 1; }}
        );
        """
    )
    path = tmp_path / f"request_layer_{name}.cjs"
    path.write_text(script, encoding="utf-8")
    return subprocess.run(["node", str(path)], cwd=ROOT, text=True, capture_output=True)


def test_post_replays_once_after_recoverable_401_with_new_csrf(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 401, headers: REQUIRED }));
    responders.push(makeResponse({ status: 200, body: { saved: true } }));
    const result = await api("/api/modules/report-special-processing/records", {
      method: "POST",
      body: JSON.stringify({ table_name: "t_demo" }),
    });
    assert.equal(fetchCalls.length, 2, "must retry exactly once");
    assert.equal(recoverCalls.length, 1, "single recovery for the 401");
    assert.equal(result.saved, true);
    const secondHeaders = fetchCalls[1].options.headers;
    assert.equal(secondHeaders.get("X-CSRF-Token"), "new-token");
    assert.equal(secondHeaders.get("X-Auto-Check-Expected-User-Id"), "user-1");
    assert.equal(secondHeaders.get("Content-Type"), "application/json");
    assert.equal(fetchCalls[1].options.credentials, "same-origin");
    assert.equal(fetchCalls[1].options.body, JSON.stringify({ table_name: "t_demo" }));
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "post_replay"))


def test_business_401_without_header_is_not_replayed(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 401, body: { error: "business 401" } }));
    let threw = null;
    try {
      await api("/api/x", { method: "GET" });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw, "business 401 must surface as an error");
    assert.equal(threw.status, 401);
    assert.equal(fetchCalls.length, 1, "no retry for unmarked 401");
    assert.equal(recoverCalls.length, 0, "no recovery triggered");
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "business_401"))


def test_second_recoverable_401_raises_recovery_failed(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 401, headers: REQUIRED }));
    responders.push(makeResponse({ status: 401, headers: REQUIRED }));
    let threw = null;
    try {
      await api("/api/x", { method: "GET" });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.code, "auth_recovery_failed");
    assert.equal(fetchCalls.length, 2, "must not retry beyond once");
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "second_401"))


def test_account_mismatch_409_discards_and_does_not_retry(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 409, headers: MISMATCH, body: { csrf_token: "t", user: { id: "user-2" } } }));
    let threw = null;
    try {
      await api("/api/x", { method: "POST", body: "{}" });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw instanceof window.AutoCheckAuthRecovery.AuthRecoveryCancelledError);
    assert.equal(discardCalls.length, 1);
    assert.equal(fetchCalls.length, 1, "business request must not be retried");
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "account_mismatch"))


def test_403_and_500_do_not_trigger_recovery(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 403, body: { error: "forbidden" } }));
    let threw = null;
    try { await api("/api/x", { method: "GET" }); } catch (e) { threw = e; }
    assert.equal(threw.status, 403);
    assert.equal(recoverCalls.length, 0);
    assert.equal(fetchCalls.length, 1);
    responders.push(makeResponse({ status: 500, body: { error: "server" } }));
    threw = null;
    try { await api("/api/y", { method: "GET" }); } catch (e) { threw = e; }
    assert.equal(threw.status, 500);
    assert.equal(recoverCalls.length, 0);
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "status_no_recovery"))


def test_non_replayable_body_refuses_recovery(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 401, headers: REQUIRED }));
    const stream = { pipeThrough: () => {} };
    let threw = null;
    try {
      await authenticatedFetch("/api/x", { method: "POST", body: stream });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.code, "auth_body_not_replayable");
    assert.equal(recoverCalls.length, 0, "must not recover for non-replayable body");
    assert.equal(fetchCalls.length, 1);
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "non_replayable"))


def test_raw_response_type_returns_final_response(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 401, headers: REQUIRED }));
    responders.push(makeResponse({ status: 200, headers: { "Content-Disposition": "attachment; filename=x.xlsx" }, body: { blob: true } }));
    const response = await api("/api/x/export", { method: "GET", responseType: "raw" });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Content-Disposition"), "attachment; filename=x.xlsx");
    assert.equal(fetchCalls.length, 2);
    assert.equal("responseType" in fetchCalls[1].options, false);
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "raw_response"))


def test_abort_signal_prevents_replay_after_recovery(tmp_path: Path) -> None:
    scenario = """
    const controller = new AbortController();
    responders.push(makeResponse({ status: 401, headers: REQUIRED }));
    responders.push(makeResponse({ status: 200, body: { saved: true } }));
    const realRecover = authRecovery.recover;
    authRecovery.recover = async () => { await realRecover(); controller.abort(); };
    let threw = null;
    try {
      await api("/api/x", { method: "POST", body: "{}", signal: controller.signal });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.name, "AbortError");
    assert.equal(fetchCalls.length, 1, "aborted request must not be replayed");
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "abort_signal"))


def test_authpreflight_recovers_before_sending_large_body(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 200, body: { authenticated: false, user: null, csrf_token: "" } }));
    responders.push(makeResponse({ status: 200, body: { saved: true } }));
    const result = await api("/api/x", {
      method: "POST",
      body: JSON.stringify({ record_attachments: { retained_ids: [], new_files: [] } }),
      authPreflight: true,
    });
    assert.equal(result.saved, true);
    assert.equal(recoverCalls.length, 1);
    assert.equal(fetchCalls.length, 2, "status check + one business request");
    assert.equal(fetchCalls[0].path, "/api/auth/status");
    assert.equal(fetchCalls[0].options.cache, "no-store");
    assert.equal(fetchCalls[0].options.credentials, "same-origin");
    assert.equal("authPreflight" in fetchCalls[1].options, false);
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "preflight_unauthenticated"))


def test_authpreflight_other_user_discards_and_sends_zero_business(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 200, body: { authenticated: true, user: { id: "user-9", username: "lisi" }, csrf_token: "x" } }));
    let threw = null;
    try {
      await api("/api/x", { method: "POST", body: "{}", authPreflight: true });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw instanceof window.AutoCheckAuthRecovery.AuthRecoveryCancelledError);
    assert.equal(discardCalls.length, 1);
    assert.equal(fetchCalls.length, 1, "business body must never be sent");
    assert.equal(fetchCalls[0].path, "/api/auth/status");
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "preflight_other_user"))


def test_authpreflight_network_failure_fails_closed(tmp_path: Path) -> None:
    scenario = """
    responders.push(() => { throw new Error("network down"); });
    let threw = null;
    try {
      await api("/api/x", { method: "POST", body: "{}", authPreflight: true });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.code, "auth_preflight_failed");
    assert.equal(fetchCalls.length, 1, "only the status check was attempted");
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "preflight_network_fail"))


def test_authpreflight_same_user_different_token_applies_session(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 200, body: { authenticated: true, user: { id: "user-1", username: "zhangsan" }, csrf_token: "rotated-token" } }));
    responders.push(makeResponse({ status: 200, body: { saved: true } }));
    const result = await api("/api/x", { method: "POST", body: "{}", authPreflight: true });
    assert.equal(result.saved, true);
    assert.equal(applyCalls.length, 1, "token rotation must apply session");
    assert.equal(authState.csrfToken, "rotated-token");
    assert.equal(recoverCalls.length, 0);
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "preflight_token_rotation"))


# ---------------------------------------------------------------------------
# 人行文件上传 XHR 的认证恢复（从 app.js 提取上传层在 Node 中运行）
# ---------------------------------------------------------------------------

def _upload_layer_source() -> str:
    app_js = (ROOT / "src" / "auto_check" / "web" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("// Auth recovery upload start")
    end = app_js.index("// Auth recovery upload end")
    return app_js[start:end]


UPLOAD_LAYER_STUBS = r"""
const AUTH_RECOVERY_HEADER = "X-Auto-Check-Auth-Recovery";
const AUTH_RECOVERY_REQUIRED = "required";
const AUTH_RECOVERY_ACCOUNT_MISMATCH = "account-mismatch";
const authState = { csrfToken: "old-token", user: { id: "user-1", username: "zhangsan" } };
const recoverCalls = [];
const discardCalls = [];
const authRecovery = {
  recover: async () => {
    recoverCalls.push(1);
    authState.csrfToken = "new-token";
  },
  discardUnexpectedSession: async (payload) => {
    discardCalls.push(payload);
    const error = new Error("authentication recovery cancelled");
    error.name = "AuthRecoveryCancelledError";
    throw error;
  },
};
function setPbcUploadState() {}
function createAuthRecoveryFailedError() {
  const error = new Error("recovery failed");
  error.code = "auth_recovery_failed";
  return error;
}
function authRecoveryCancelledError() {
  const error = new Error("cancelled");
  error.name = "AuthRecoveryCancelledError";
  return error;
}
class FakeXHR {
  constructor() {
    this.headers = {};
    this.upload = {};
    this.status = 0;
    this.responseText = "{}";
    this.responseHeaders = {};
    this.progressEvents = [];
    FakeXHR.instances.push(this);
  }
  open(method, url) { this.method = method; this.url = url; }
  setRequestHeader(name, value) { this.headers[name] = value; }
  getResponseHeader(name) {
    return Object.prototype.hasOwnProperty.call(this.responseHeaders, name)
      ? this.responseHeaders[name]
      : null;
  }
  send(body) {
    this.sentBody = body;
    const next = FakeXHR.responders.shift();
    queueMicrotask(() => {
      if (!next) { this.onerror && this.onerror(); return; }
      if (next.networkError) { this.onerror && this.onerror(); return; }
      this.status = next.status;
      this.responseText = next.body ? JSON.stringify(next.body) : "{}";
      this.responseHeaders = next.headers || {};
      if (this.upload.onprogress) {
        this.upload.onprogress({ lengthComputable: true, loaded: 10, total: 100 });
      }
      this.onload && this.onload();
    });
  }
}
FakeXHR.instances = [];
FakeXHR.responders = [];
const XMLHttpRequest = FakeXHR;
"""


def _run_upload_layer_scenario(tmp_path: Path, scenario: str, name: str) -> subprocess.CompletedProcess:
    script = textwrap.dedent(
        f"""\
        const assert = require("node:assert/strict");
        {UPLOAD_LAYER_STUBS}
        {_upload_layer_source()}
        async function runScenario() {{
        {textwrap.indent(scenario, '  ')}
        }}
        runScenario().then(
          () => {{ console.log("OK"); }},
          (error) => {{ console.error(error && error.stack || error); process.exitCode = 1; }}
        );
        """
    )
    path = tmp_path / f"upload_layer_{name}.cjs"
    path.write_text(script, encoding="utf-8")
    return subprocess.run(["node", str(path)], cwd=ROOT, text=True, capture_output=True)


def test_pbc_upload_retries_once_after_recoverable_401(tmp_path: Path) -> None:
    scenario = """
    FakeXHR.responders.push({ status: 401, headers: { "X-Auto-Check-Auth-Recovery": "required" }, body: { error: "login required" } });
    FakeXHR.responders.push({ status: 200, body: { upload_id: "u-1" } });
    const form = { marker: "formdata" };
    const result = await uploadPbcFileWithProgress({ name: "a.zip" }, form);
    assert.equal(result.upload_id, "u-1");
    assert.equal(FakeXHR.instances.length, 2, "must create a second XHR after recovery");
    assert.equal(recoverCalls.length, 1);
    assert.equal(FakeXHR.instances[0].headers["X-Auto-Check-Expected-User-Id"], "user-1");
    assert.equal(FakeXHR.instances[1].headers["X-CSRF-Token"], "new-token");
    assert.equal(FakeXHR.instances[1].headers["X-Auto-Check-Expected-User-Id"], "user-1");
    assert.equal(FakeXHR.instances[1].sentBody, form, "resends the same FormData");
    """
    _assert_ok(_run_upload_layer_scenario(tmp_path, scenario, "upload_retry"))


def test_pbc_upload_unmarked_401_does_not_retry(tmp_path: Path) -> None:
    scenario = """
    FakeXHR.responders.push({ status: 401, body: { error: "business" } });
    let threw = null;
    try {
      await uploadPbcFileWithProgress({ name: "a.zip" }, {});
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.status, 401);
    assert.equal(FakeXHR.instances.length, 1, "no retry for unmarked 401");
    assert.equal(recoverCalls.length, 0);
    """
    _assert_ok(_run_upload_layer_scenario(tmp_path, scenario, "upload_no_retry"))


def test_pbc_upload_account_mismatch_discards_and_exits(tmp_path: Path) -> None:
    scenario = """
    FakeXHR.responders.push({ status: 409, headers: { "X-Auto-Check-Auth-Recovery": "account-mismatch" }, body: { csrf_token: "t", user: { id: "user-2" } } });
    let threw = null;
    try {
      await uploadPbcFileWithProgress({ name: "a.zip" }, {});
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.name, "AuthRecoveryCancelledError");
    assert.equal(discardCalls.length, 1);
    assert.equal(FakeXHR.instances.length, 1, "no re-upload after mismatch");
    """
    _assert_ok(_run_upload_layer_scenario(tmp_path, scenario, "upload_mismatch"))


def test_pbc_upload_second_recoverable_401_reports_recovery_failed(tmp_path: Path) -> None:
    scenario = """
    FakeXHR.responders.push({ status: 401, headers: { "X-Auto-Check-Auth-Recovery": "required" }, body: {} });
    FakeXHR.responders.push({ status: 401, headers: { "X-Auto-Check-Auth-Recovery": "required" }, body: {} });
    let threw = null;
    try {
      await uploadPbcFileWithProgress({ name: "a.zip" }, {});
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.code, "auth_recovery_failed");
    assert.equal(FakeXHR.instances.length, 2, "must not upload a third time");
    """
    _assert_ok(_run_upload_layer_scenario(tmp_path, scenario, "upload_second_401"))


# ---------------------------------------------------------------------------
# 端到端组合：模块 api.js + 平台请求层 + 真实重新认证状态机
# ---------------------------------------------------------------------------

import shutil as _shutil

MODULE_WEB = ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web"

E2E_STUBS = r"""
const authState = { csrfToken: "old-token", user: { id: "user-1", username: "zhangsan" } };
const applyCalls = [];
const discardCalls = [];
const exitCalls = [];
const authenticateCalls = [];
async function applyReauthenticatedSession(payload) {
  applyCalls.push(payload);
  authState.csrfToken = payload.csrf_token;
  authState.user = payload.user;
}
function formatApiErrorMessage(message) { return String(message || ""); }
const fetchCalls = [];
const responders = [];
globalThis.fetch = async (path, options) => {
  const call = { path, options: options || {} };
  fetchCalls.push(call);
  if (!responders.length) throw new Error("no responder for " + path);
  const next = responders.shift();
  return typeof next === "function" ? next(call) : next;
};
function makeResponse({ status = 200, headers = {}, body = null } = {}) {
  const headerMap = new Map(Object.entries(headers));
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: (name) => (headerMap.has(name) ? headerMap.get(name) : null) },
    clone() { return this; },
    async json() {
      if (body === null || body === undefined) throw new Error("empty body");
      return typeof body === "string" ? JSON.parse(body) : body;
    },
  };
}
const REQUIRED = { "X-Auto-Check-Auth-Recovery": "required" };
const MISMATCH = { "X-Auto-Check-Auth-Recovery": "account-mismatch" };
const documentRef = makeDocument();
const authRecovery = createAuthRecovery({
  documentRef,
  getCurrentUser: () => authState.user,
  authenticate: async ({ username, password }) => {
    authenticateCalls.push({ username, password });
    return { csrf_token: "new-token", user: { id: "user-1", username: "zhangsan" } };
  },
  applySession: applyReauthenticatedSession,
  discardSession: async (payload) => { discardCalls.push(payload); },
  exitSession: () => { exitCalls.push(1); },
});
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function attachmentPayload(marker) {
  return {
    save_mode: "record",
    table_name: "t_demo",
    field_name: "amount",
    record_attachments: {
      retained_ids: [],
      new_files: [{
        client_id: "local-1",
        file_name: "big.png",
        content_type: "image/png",
        data_base64: marker.repeat(70000),
      }],
    },
  };
}
"""


def _run_e2e_scenario(tmp_path: Path, scenario: str, name: str) -> subprocess.CompletedProcess:
    workdir = tmp_path / name
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    _shutil.copy(MODULE_WEB / "api.js", workdir / "module_api.js")
    _shutil.copy(AUTH_RECOVERY_JS, workdir / "auth_recovery.js")
    script = textwrap.dedent(
        f"""\
        import assert from "node:assert/strict";
        import {{ createApi }} from "./module_api.js";
        globalThis.window = globalThis.window || {{}};
        {BROWSER_GLOBAL_POLYFILL}
        await import("./auth_recovery.js");
        const {{ createAuthRecovery }} = window.AutoCheckAuthRecovery;
        {DOM_STUB}
        {E2E_STUBS}
        {_request_layer_source()}
        async function runScenario() {{
        {textwrap.indent(scenario, '  ')}
        }}
        runScenario().then(
          () => {{ console.log("OK"); }},
          (error) => {{ console.error(error && error.stack || error); process.exitCode = 1; }}
        );
        """
    )
    (workdir / "scenario.js").write_text(script, encoding="utf-8")
    return subprocess.run(["node", "scenario.js"], cwd=workdir, text=True, capture_output=True)


def test_attachment_save_with_expired_session_recovers_and_saves_once(tmp_path: Path) -> None:
    scenario = """
    const moduleApi = createApi({ api });
    responders.push(makeResponse({ status: 200, body: { authenticated: false, user: null, csrf_token: "" } }));
    responders.push(makeResponse({ status: 201, body: { data: { id: 77 }, meta: {} } }));
    const savePromise = moduleApi.createRecord(attachmentPayload("A"));
    await sleep(20);
    // authPreflight 先发现会话过期：遮罩打开且业务 body 发送次数为 0。
    const postsBefore = fetchCalls.filter((call) => call.path.endsWith("/records"));
    assert.equal(postsBefore.length, 0, "恢复成功前业务 body 不得发送");
    const overlay = documentRef.getElementById("authRecoveryOverlay");
    assert.equal(overlay.hidden, false);
    assert.equal(documentRef.getElementById("authRecoveryUsername").textContent, "zhangsan");
    documentRef.getElementById("authRecoveryPassword").value = "right-password";
    documentRef.getElementById("authRecoverySubmit").click();
    const result = await savePromise;
    assert.equal(result.data.id, 77, "createRecord 只 resolve 一次");
    assert.equal(fetchCalls.length, 2, "状态预检 + 一次业务请求");
    const business = fetchCalls[1];
    assert.equal(business.path, "/api/modules/report-special-processing/records");
    assert.ok(business.options.body.length > 65536, "附件大 body 完整发送");
    assert.equal(business.options.headers.get("X-CSRF-Token"), "new-token");
    assert.equal(business.options.headers.get("X-Auto-Check-Expected-User-Id"), "user-1");
    assert.equal("authPreflight" in business.options, false);
    assert.equal(authenticateCalls.length, 1);
    assert.equal(overlay.hidden, true, "恢复成功后遮罩关闭");
    """
    _assert_ok(_run_e2e_scenario(tmp_path, scenario, "e2e_preflight_recovery"))


def test_attachment_save_expiry_race_replays_identical_body_once(tmp_path: Path) -> None:
    scenario = """
    const moduleApi = createApi({ api });
    // 预检通过（同用户同 Token），但业务请求发出时会话恰好过期。
    responders.push(makeResponse({ status: 200, body: { authenticated: true, user: { id: "user-1", username: "zhangsan" }, csrf_token: "old-token" } }));
    responders.push(makeResponse({ status: 401, headers: REQUIRED, body: { error: "login required" } }));
    responders.push(makeResponse({ status: 201, body: { data: { id: 88 }, meta: {} } }));
    const savePromise = moduleApi.createRecord(attachmentPayload("B"));
    await sleep(20);
    const overlay = documentRef.getElementById("authRecoveryOverlay");
    assert.equal(overlay.hidden, false, "前置 401 打开遮罩");
    const postsBefore = fetchCalls.filter((call) => call.path.endsWith("/records"));
    assert.equal(postsBefore.length, 1);
    documentRef.getElementById("authRecoveryPassword").value = "pw";
    documentRef.getElementById("authRecoverySubmit").click();
    const result = await savePromise;
    assert.equal(result.data.id, 88);
    const posts = fetchCalls.filter((call) => call.path.endsWith("/records"));
    assert.equal(posts.length, 2, "业务只重发一次");
    assert.equal(posts[0].options.body, posts[1].options.body, "两次 body 字符串逐字节相同");
    assert.equal(posts[0].options.headers.get("X-CSRF-Token"), "old-token");
    assert.equal(posts[1].options.headers.get("X-CSRF-Token"), "new-token");
    assert.equal(posts[1].options.headers.get("X-Auto-Check-Expected-User-Id"), "user-1");
    assert.equal(authenticateCalls.length, 1);
    """
    _assert_ok(_run_e2e_scenario(tmp_path, scenario, "e2e_race_replay"))


def test_attachment_save_account_switch_race_discards_without_replay(tmp_path: Path) -> None:
    scenario = """
    const moduleApi = createApi({ api });
    responders.push(makeResponse({ status: 200, body: { authenticated: true, user: { id: "user-1", username: "zhangsan" }, csrf_token: "old-token" } }));
    responders.push(makeResponse({
      status: 409,
      headers: MISMATCH,
      body: { error: "account mismatch", csrf_token: "other-token", user: { id: "user-2", username: "lisi" } },
    }));
    let threw = null;
    try {
      await moduleApi.createRecord(attachmentPayload("C"));
    } catch (error) {
      threw = error;
    }
    assert.ok(threw, "平台取消错误必须传播");
    const posts = fetchCalls.filter((call) => call.path.endsWith("/records"));
    assert.equal(posts.length, 1, "account-mismatch 不重试业务请求");
    assert.equal(fetchCalls.length, 2);
    assert.equal(discardCalls.length, 1, "注销意外会话");
    assert.equal(discardCalls[0].user.username, "lisi");
    assert.equal(exitCalls.length, 1, "注销成功后退出");
    """
    _assert_ok(_run_e2e_scenario(tmp_path, scenario, "e2e_account_switch"))


def test_attachment_save_business_errors_keep_form_and_do_not_replay(tmp_path: Path) -> None:
    scenario = """
    const moduleApi = createApi({ api });
    // 无专用标识的业务 401、400、普通 409、500 均只发送一次且不触发遮罩。
    for (const status of [401, 400, 409, 500]) {
      responders.push(makeResponse({ status: 200, body: { authenticated: true, user: { id: "user-1", username: "zhangsan" }, csrf_token: authState.csrfToken } }));
      responders.push(makeResponse({ status, body: { error: { code: "x", message: "失败", fields: {} } } }));
      let threw = null;
      try {
        await moduleApi.createRecord(attachmentPayload("D"));
      } catch (error) {
        threw = error;
      }
      assert.ok(threw, `status ${status} 必须报错`);
      assert.equal(threw.status, status);
    }
    const posts = fetchCalls.filter((call) => call.path.endsWith("/records"));
    assert.equal(posts.length, 4, "每种错误各只发送一次业务请求");
    assert.equal(authenticateCalls.length, 0, "不触发重新认证");
    const overlay = documentRef.getElementById("authRecoveryOverlay");
    assert.ok(!overlay || overlay.hidden !== false, "不显示遮罩");
    """
    _assert_ok(_run_e2e_scenario(tmp_path, scenario, "e2e_business_errors"))


def test_preflight_rejects_contradictory_unauthenticated_with_user(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 200, body: { authenticated: false, user: { id: "user-9", username: "lisi" }, csrf_token: "" } }));
    responders.push(makeResponse({ status: 200, body: { ok: true } }));
    let threw = null;
    try {
      await api("/test-write", { method: "POST", body: "{}", authPreflight: true });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw, "未认证但 user 非空必须 fail closed");
    assert.equal(threw.code, "auth_preflight_failed");
    assert.equal(fetchCalls.filter((call) => call.path === "/test-write").length, 0);
    assert.equal(recoverCalls.length, 0, "矛盾结构不得进入恢复");
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "preflight_contradiction"))


def test_preflight_rejects_authenticated_user_without_username(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 200, body: { authenticated: true, user: { id: "user-1" }, csrf_token: "old-token" } }));
    responders.push(makeResponse({ status: 200, body: { ok: true } }));
    let threw = null;
    try {
      await api("/test-write", { method: "POST", body: "{}", authPreflight: true });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw, "已认证但 user 缺 username 必须 fail closed");
    assert.equal(threw.code, "auth_preflight_failed");
    assert.equal(fetchCalls.filter((call) => call.path === "/test-write").length, 0);
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "preflight_missing_username"))


def test_preflight_username_mismatch_treated_as_account_mismatch(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 200, body: { authenticated: true, user: { id: "user-1", username: "lisi" }, csrf_token: "other-token" } }));
    responders.push(makeResponse({ status: 200, body: { ok: true } }));
    let threw = null;
    try {
      await api("/test-write", { method: "POST", body: "{}", authPreflight: true });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.name, "AuthRecoveryCancelledError");
    assert.equal(discardCalls.length, 1, "用户名不一致按账号不一致处理");
    assert.equal(fetchCalls.filter((call) => call.path === "/test-write").length, 0);
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "preflight_username_mismatch"))


def test_preflight_fails_closed_when_local_user_missing(tmp_path: Path) -> None:
    scenario = """
    authState.user = null;
    responders.push(makeResponse({ status: 200, body: { authenticated: true, user: { id: "user-1", username: "zhangsan" }, csrf_token: "old-token" } }));
    responders.push(makeResponse({ status: 200, body: { ok: true } }));
    let threw = null;
    try {
      await api("/test-write", { method: "POST", body: "{}", authPreflight: true });
    } catch (error) {
      threw = error;
    }
    assert.ok(threw, "本地无用户时必须 fail closed");
    assert.equal(threw.code, "auth_preflight_failed");
    assert.equal(fetchCalls.filter((call) => call.path === "/test-write").length, 0);
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "preflight_local_user_missing"))


def test_api_preserves_caller_headers_instances_and_tuple_arrays(tmp_path: Path) -> None:
    scenario = """
    responders.push(makeResponse({ status: 200, body: { ok: 1 } }));
    responders.push(makeResponse({ status: 200, body: { ok: 2 } }));
    await api("/test-write", { method: "POST", body: "{}", headers: new Headers({ "X-Custom": "keep" }) });
    assert.equal(fetchCalls[0].options.headers.get("X-Custom"), "keep");
    assert.equal(fetchCalls[0].options.headers.get("Content-Type"), "application/json");
    await api("/test-write", { method: "POST", body: "{}", headers: [["X-Custom", "keep2"]] });
    assert.equal(fetchCalls[1].options.headers.get("X-Custom"), "keep2");
    assert.equal(fetchCalls[1].options.headers.get("Content-Type"), "application/json");
    """
    _assert_ok(_run_request_layer_scenario(tmp_path, scenario, "headers_passthrough"))


def test_pbc_upload_retry_account_mismatch_enters_discard(tmp_path: Path) -> None:
    scenario = """
    FakeXHR.responders.push({ status: 401, headers: { "X-Auto-Check-Auth-Recovery": "required" }, body: { error: "login required" } });
    FakeXHR.responders.push({
      status: 409,
      headers: { "X-Auto-Check-Auth-Recovery": "account-mismatch" },
      body: { error: "account mismatch", csrf_token: "other", user: { id: "user-2", username: "lisi" } },
    });
    let threw = null;
    try {
      await uploadPbcFileWithProgress({ name: "a.zip" }, {});
    } catch (error) {
      threw = error;
    }
    assert.ok(threw);
    assert.equal(threw.name, "AuthRecoveryCancelledError");
    assert.equal(FakeXHR.instances.length, 2, "不进行第三次上传");
    assert.equal(discardCalls.length, 1, "重试的账号不一致必须进入注销流程");
    assert.equal(discardCalls[0].user.username, "lisi");
    """
    _assert_ok(_run_upload_layer_scenario(tmp_path, scenario, "upload_retry_mismatch"))


def _make_recovery_options(extra: str = "") -> str:
    return extra


def test_recover_blocked_while_discarding_failure(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    const authenticateCalls = [];
    const discardCalls = [];
    const exitCalls = [];
    let discardFail = true;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async (arg) => {{
        authenticateCalls.push(arg);
        return {{ csrf_token: "new-token", user: {{ id: "user-1", username: "zhangsan" }} }};
      }},
      applySession: async () => {{}},
      discardSession: async (payload) => {{
        discardCalls.push(payload);
        if (discardFail) throw new Error("logout failed");
      }},
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const p1 = recovery.discardUnexpectedSession({{ csrf_token: "ta", user: {{ id: "user-2", username: "lisi" }} }});
    p1.catch(() => {{}});
    await sleep(10);
    const p2 = recovery.recover();
    p2.catch(() => {{}});
    await sleep(10);
    {_overlay_handles()}
    assert.equal(overlay.hidden, false, "注销失败态遮罩保持");
    assert.equal(password.disabled, true, "密码框不得重新启用");
    assert.equal(submitButton.disabled, true);
    assert.equal(exitButton.textContent, "重试退出");
    assert.equal(authenticateCalls.length, 0, "discarding 中 recover 不得重开登录");
    assert.equal(recovery.isRecovering(), true);
    assert.equal(username.textContent, "zhangsan", "原用户身份不得被覆盖");
    const raced = await Promise.race([
      p2.then(() => "resolved", (e) => e.name),
      sleep(30).then(() => "pending"),
    ]);
    assert.equal(raced, "pending", "recover 等待者在 discarding 期间被阻塞");
    discardFail = false;
    exitButton.click();
    await sleep(10);
    const err2 = await p2.then(() => null, (e) => e);
    assert.ok(err2 instanceof AuthRecoveryCancelledError, "注销完成后统一取消等待者");
    const err1 = await p1.then(() => null, (e) => e);
    assert.ok(err1 instanceof AuthRecoveryCancelledError);
    assert.equal(exitCalls.length, 1);
    assert.equal(recovery.isRecovering(), false);
    assert.equal(overlay.hidden, true);
    await sleep(20);
    assert.equal(unhandled, null, "不得产生未捕获 rejection");
    """
    _assert_ok(_scenario(tmp_path, body, name="f2_recover_blocked"))


def test_recover_after_terminal_rejects_immediately(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let userCalls = 0;
    const exitCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => {{
        userCalls += 1;
        return {{ id: "user-1", username: "zhangsan" }};
      }},
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const waiter = recovery.recover();
    waiter.catch(() => {{}});
    {_overlay_handles()}
    exitButton.click();
    await sleep(10);
    const before = userCalls;
    const pa = recovery.recover();
    const pb = recovery.recover();
    const ea = await pa.then(() => null, (e) => e);
    const eb = await pb.then(() => null, (e) => e);
    assert.ok(ea instanceof AuthRecoveryCancelledError);
    assert.ok(eb instanceof AuthRecoveryCancelledError);
    assert.equal(userCalls, before, "terminal 后不得重新捕获用户");
    assert.equal(overlay.hidden, true);
    assert.equal(recovery.isRecovering(), false);
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="f2_terminal_recover"))


def test_exit_during_login_inflight_discards_late_session(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let resolveAuth = null;
    const applyCalls = [];
    const discardCalls = [];
    const exitCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: () => new Promise((resolve) => {{ resolveAuth = resolve; }}),
      applySession: async (payload) => {{ applyCalls.push(payload); }},
      discardSession: async (payload) => {{ discardCalls.push(payload); }},
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const waiter = recovery.recover();
    waiter.catch(() => {{}});
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    await sleep(5);
    exitButton.click();
    await sleep(5);
    // R1：认证在途期间退出不得立即导航/释放等待者，进入受控退出等待态。
    const werrEarly = await Promise.race([
      waiter.then(() => null, (e) => e),
      sleep(20).then(() => "pending"),
    ]);
    assert.equal(werrEarly, "pending", "在途认证期间等待者不得提前释放");
    assert.equal(exitCalls.length, 0, "认证结果未知时不得导航登录页");
    assert.equal(overlay.hidden, false, "受控退出等待期间遮罩保持阻塞");
    resolveAuth({{ csrf_token: "late", user: {{ id: "user-1", username: "zhangsan" }} }});
    await sleep(10);
    assert.equal(applyCalls.length, 0, "迟到的登录成功不得应用会话");
    assert.equal(discardCalls.length, 1, "迟到但已建立的会话必须被注销");
    assert.equal(discardCalls[0].csrf_token, "late");
    const werr = await waiter.then(() => "resolved", (e) => e);
    assert.ok(werr instanceof AuthRecoveryCancelledError, "注销成功后统一取消等待者");
    assert.equal(exitCalls.length, 1);
    assert.equal(recovery.isRecovering(), false);
    const p3 = recovery.recover();
    const e3 = await p3.then(() => null, (e) => e);
    assert.ok(e3 instanceof AuthRecoveryCancelledError);
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="f3_exit_during_login"))


def test_exit_during_apply_session_discards_late_established_session(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let resolveApply = null;
    const discardCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "tok", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: () => new Promise((resolve) => {{ resolveApply = resolve; }}),
      discardSession: async (payload) => {{ discardCalls.push(payload); }},
      exitSession: () => {{}},
    }});
    const waiter = recovery.recover();
    waiter.catch(() => {{}});
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    await sleep(5);
    exitButton.click();
    await sleep(5);
    resolveApply();
    await sleep(10);
    const werr = await waiter.then(() => "resolved", (e) => e);
    assert.ok(werr instanceof AuthRecoveryCancelledError, "applySession 迟到完成不得释放等待者");
    assert.equal(overlay.hidden, true);
    assert.equal(recovery.isRecovering(), false);
    assert.equal(discardCalls.length, 1, "applySession 已产生的副作用会话需注销");
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="f3_exit_during_apply"))


def test_late_auth_failure_after_exit_is_noop(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let rejectAuth = null;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: () => new Promise((_resolve, reject) => {{ rejectAuth = reject; }}),
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{}},
    }});
    const waiter = recovery.recover();
    waiter.catch(() => {{}});
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    await sleep(5);
    exitButton.click();
    await sleep(5);
    rejectAuth(new Error("账号或密码验证失败"));
    await sleep(10);
    const errorNode = documentRef.getElementById("authRecoveryError");
    assert.equal(errorNode.hidden, true, "迟到的失败不得写遮罩文案");
    assert.equal(overlay.hidden, true);
    assert.equal(recovery.isRecovering(), false);
    """
    _assert_ok(_scenario(tmp_path, body, name="f3_late_failure_noop"))


def test_concurrent_discard_unexpected_shares_single_promise(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    const discardCalls = [];
    const exitCalls = [];
    let discardFail = true;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: async (payload) => {{
        discardCalls.push(payload);
        if (discardFail) throw new Error("logout failed");
      }},
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const pA = {{ csrf_token: "ta", user: {{ id: "user-2", username: "lisi" }} }};
    const pB = {{ csrf_token: "tb", user: {{ id: "user-3", username: "wangwu" }} }};
    const p1 = recovery.discardUnexpectedSession(pA);
    p1.catch(() => {{}});
    await sleep(10);
    const p2 = recovery.discardUnexpectedSession(pB);
    p2.catch(() => {{}});
    assert.equal(p1, p2, "并发账号不一致共享同一次注销 Promise");
    assert.equal(discardCalls.length, 1, "不得并行注销");
    {_overlay_handles()}
    discardFail = false;
    exitButton.click();
    await sleep(10);
    assert.equal(discardCalls.length, 2, "重试退出使用刷新后的凭据");
    assert.equal(discardCalls[1], pB);
    const e1 = await p1.then(() => null, (e) => e);
    const e2 = await p2.then(() => null, (e) => e);
    assert.ok(e1 instanceof AuthRecoveryCancelledError);
    assert.ok(e2 instanceof AuthRecoveryCancelledError);
    assert.equal(exitCalls.length, 1);
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="f4_concurrent_discard"))


def test_double_retry_click_is_latched(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let resolveDiscard = null;
    const discardCalls = [];
    const exitCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: () => new Promise((resolve) => {{
        discardCalls.push(1);
        resolveDiscard = resolve;
      }}),
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const p1 = recovery.discardUnexpectedSession({{ csrf_token: "ta", user: {{ id: "user-2", username: "lisi" }} }});
    p1.catch(() => {{}});
    await sleep(10);
    {_overlay_handles()}
    exitButton.click();
    exitButton.click();
    exitButton.click();
    await sleep(10);
    assert.equal(discardCalls.length, 1, "在途注销期间重复点击为 no-op");
    resolveDiscard();
    await sleep(10);
    assert.equal(exitCalls.length, 1);
    assert.equal(recovery.isRecovering(), false);
    """
    _assert_ok(_scenario(tmp_path, body, name="f4_retry_latched"))


def test_discard_unexpected_during_reauthenticating_cancels_waiter(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const authenticateCalls = [];
    const exitCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async (arg) => {{
        authenticateCalls.push(arg);
        return {{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }};
      }},
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const waiter = recovery.recover();
    waiter.catch(() => {{}});
    await sleep(5);
    const p = recovery.discardUnexpectedSession({{ csrf_token: "ta", user: {{ id: "user-2", username: "lisi" }} }});
    p.catch(() => {{}});
    const werr = await waiter.then(() => null, (e) => e);
    assert.ok(werr instanceof AuthRecoveryCancelledError, "既有等待者立即取消");
    {_overlay_handles()}
    assert.equal(password.disabled, true);
    assert.equal(submitButton.disabled, true);
    submitButton.click();
    await sleep(5);
    assert.equal(authenticateCalls.length, 0, "discarding 状态门禁提交");
    const perr = await p.then(() => null, (e) => e);
    assert.ok(perr instanceof AuthRecoveryCancelledError, "注销完成统一取消");
    assert.equal(exitCalls.length, 1);
    assert.equal(recovery.isRecovering(), false);
    """
    _assert_ok(_scenario(tmp_path, body, name="f4_discard_during_reauth"))


def test_destroy_rejects_waiters_and_unbinds_listeners(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    const exitCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: () => new Promise(() => {{}}),
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const p1 = recovery.discardUnexpectedSession({{ csrf_token: "ta", user: {{ id: "user-2", username: "lisi" }} }});
    p1.catch(() => {{}});
    await sleep(10);
    const p2 = recovery.recover();
    p2.catch(() => {{}});
    await sleep(5);
    {_overlay_handles()}
    password.value = "secret";
    recovery.destroy();
    const e1 = await p1.then(() => null, (e) => e);
    const e2 = await p2.then(() => null, (e) => e);
    assert.ok(e1 instanceof AuthRecoveryCancelledError);
    assert.ok(e2 instanceof AuthRecoveryCancelledError);
    assert.equal(password.value, "");
    assert.equal(exitButton.textContent, "退出系统");
    assert.equal(overlay.hidden, true);
    assert.equal(submitButton._listeners.click.length, 0, "submit 监听已解绑");
    assert.equal(exitButton._listeners.click.length, 0, "exit 监听已解绑");
    assert.equal(password._listeners.keydown.length, 0, "password 监听已解绑");
    assert.equal(overlay._listeners.click.length, 0, "overlay 监听已解绑");
    assert.equal(recovery.isRecovering(), false);
    assert.equal(exitCalls.length, 0, "destroy 不导航");
    recovery.destroy();
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="g1_destroy_unbind"))


def test_exit_during_inflight_auth_waits_then_blocks_on_discard_failure(tmp_path: Path) -> None:
    """R1：在途认证期间点击退出不得立即放行导航；迟到会话注销失败必须保持阻塞并可重试。"""
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let resolveAuth = null;
    const applyCalls = [];
    const discardCalls = [];
    const exitCalls = [];
    let discardFail = true;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: () => new Promise((resolve) => {{ resolveAuth = resolve; }}),
      applySession: async (payload) => {{ applyCalls.push(payload); }},
      discardSession: async (payload) => {{
        discardCalls.push(payload);
        if (discardFail) throw new Error("logout failed");
      }},
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const waiter = recovery.recover();
    waiter.catch(() => {{}});
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    await sleep(5);
    exitButton.click();
    await sleep(5);
    // 认证结果未知：不得放行导航，等待者保持阻塞，遮罩保持阻塞态。
    const racedEarly = await Promise.race([
      waiter.then(() => "resolved", (e) => e.name),
      sleep(30).then(() => "pending"),
    ]);
    assert.equal(racedEarly, "pending", "在途认证期间退出不得立即释放等待者");
    assert.equal(exitCalls.length, 0, "认证结果未知时不得导航登录页");
    assert.equal(overlay.hidden, false, "受控退出等待期间遮罩保持阻塞");
    assert.equal(password.disabled, true, "等待期间密码禁用");
    assert.equal(submitButton.disabled, true, "等待期间提交禁用");
    assert.equal(recovery.isRecovering(), true);
    // 迟到认证成功：不得应用会话，必须用响应 Token 进入受控注销。
    resolveAuth({{ csrf_token: "late", user: {{ id: "user-1", username: "zhangsan" }} }});
    await sleep(10);
    assert.equal(applyCalls.length, 0, "迟到登录成功不得调用 applySession");
    assert.equal(discardCalls.length, 1, "已建立会话必须注销");
    assert.equal(discardCalls[0].csrf_token, "late");
    // 注销失败：保持不透明遮罩、禁用密码/提交、退出按钮显示“重试退出”。
    assert.equal(overlay.hidden, false, "注销失败后遮罩保持阻塞");
    assert.equal(password.disabled, true);
    assert.equal(submitButton.disabled, true);
    assert.equal(exitButton.textContent, "重试退出");
    assert.equal(exitButton.disabled, false);
    assert.equal(recovery.isRecovering(), true);
    assert.equal(exitCalls.length, 0, "注销失败不得完成退出");
    const racedRetry = await Promise.race([
      waiter.then(() => "resolved", (e) => e.name),
      sleep(30).then(() => "pending"),
    ]);
    assert.equal(racedRetry, "pending", "注销失败期间等待者仍阻塞");
    // 点击“重试退出”，注销成功后才退出并统一取消等待者。
    discardFail = false;
    exitButton.click();
    await sleep(10);
    const werr = await waiter.then(() => null, (e) => e);
    assert.ok(werr instanceof AuthRecoveryCancelledError, "注销完成后统一取消等待者");
    assert.equal(exitCalls.length, 1);
    assert.equal(overlay.hidden, true);
    assert.equal(recovery.isRecovering(), false);
    // 重复点击“重试退出”与后续 recover 均不得再次注销/退出（terminal 收口）。
    exitButton.click();
    await sleep(10);
    assert.equal(discardCalls.length, 2);
    assert.equal(exitCalls.length, 1);
    const p3 = recovery.recover();
    const e3 = await p3.then(() => null, (e) => e);
    assert.ok(e3 instanceof AuthRecoveryCancelledError);
    // 同一迟到结果不得重复应用/退出。
    resolveAuth({{ csrf_token: "late", user: {{ id: "user-1", username: "zhangsan" }} }});
    await sleep(10);
    assert.equal(applyCalls.length, 0);
    assert.equal(discardCalls.length, 2);
    assert.equal(exitCalls.length, 1);
    await sleep(20);
    assert.equal(unhandled, null, "不得产生未捕获 rejection");
    """
    _assert_ok(_scenario(tmp_path, body, name="r1_exit_wait_discard_failure"))


def test_destroy_during_inflight_discard_surfaces_failure(tmp_path: Path) -> None:
    """问题1：进入注销状态后 destroy()，随后注销失败，清理结果必须反映失败。"""
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let resolveDiscard = null;
    let rejectDiscard = null;
    const discardCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => {{ throw new Error("must not prompt"); }},
      applySession: async () => {{}},
      discardSession: () => new Promise((resolve, reject) => {{
        discardCalls.push(1);
        resolveDiscard = resolve;
        rejectDiscard = reject;
      }}),
      exitSession: () => {{}},
    }});
    const waiter = recovery.discardUnexpectedSession({{
      csrf_token: "ta",
      user: {{ id: "user-2", username: "lisi" }},
    }});
    waiter.catch(() => {{}});
    await sleep(10);
    assert.equal(discardCalls.length, 1, "已进入注销流程，在途注销未返回");
    // 在途注销期间执行 destroy：清理 Promise 不得在注销结果确定前完成。
    const cleanup = recovery.destroy();
    const settled = await Promise.race([
      cleanup.then(() => "resolved", (e) => e),
      sleep(20).then(() => "pending"),
    ]);
    assert.equal(settled, "pending", "destroy 必须等待在途注销完成");
    // 注销失败：清理结果必须 reject，而不是静默忽略。
    rejectDiscard(new Error("logout failed"));
    const err = await cleanup.then(() => null, (e) => e);
    assert.ok(err instanceof AuthRecoveryCancelledError, "注销失败必须反映在清理结果上");
    assert.ok(
      err.cause && /logout failed/.test(String(err.cause.message || "")),
      "清理失败须挂接原始注销异常",
    );
    assert.equal(discardCalls.length, 1, "destroy 不重复触发注销");
    assert.equal(recovery.isRecovering(), false);
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="p1_destroy_during_discard_fail"))


def test_destroy_during_inflight_discard_resolves_on_success(tmp_path: Path) -> None:
    """问题1：进入注销状态后 destroy()，注销成功时清理结果正常完成。"""
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let resolveDiscard = null;
    const discardCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => {{ throw new Error("must not prompt"); }},
      applySession: async () => {{}},
      discardSession: () => new Promise((resolve) => {{
        discardCalls.push(1);
        resolveDiscard = resolve;
      }}),
      exitSession: () => {{}},
    }});
    const waiter = recovery.discardUnexpectedSession({{
      csrf_token: "ta",
      user: {{ id: "user-2", username: "lisi" }},
    }});
    waiter.catch(() => {{}});
    await sleep(10);
    const cleanup = recovery.destroy();
    const settledEarly = await Promise.race([
      cleanup.then(() => "resolved", (e) => e),
      sleep(15).then(() => "pending"),
    ]);
    assert.equal(settledEarly, "pending", "在途注销未结束前清理不完成");
    resolveDiscard();
    await cleanup;
    assert.equal(discardCalls.length, 1);
    assert.equal(recovery.isRecovering(), false);
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="p1_destroy_during_discard_ok"))


def test_exit_during_inflight_auth_with_auth_failure_completes_exit(tmp_path: Path) -> None:
    """R1：在途认证期间点击退出，认证最终失败且未建立会话时才完成退出。"""
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let rejectAuth = null;
    const discardCalls = [];
    const exitCalls = [];
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: () => new Promise((_resolve, reject) => {{ rejectAuth = reject; }}),
      applySession: async () => {{}},
      discardSession: async (payload) => {{ discardCalls.push(payload); }},
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const waiter = recovery.recover();
    waiter.catch(() => {{}});
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    await sleep(5);
    exitButton.click();
    await sleep(5);
    const racedEarly = await Promise.race([
      waiter.then(() => "resolved", (e) => e.name),
      sleep(20).then(() => "pending"),
    ]);
    assert.equal(racedEarly, "pending", "认证结果未知时不得提前退出");
    assert.equal(exitCalls.length, 0);
    rejectAuth(new Error("账号或密码验证失败"));
    await sleep(10);
    const werr = await waiter.then(() => null, (e) => e);
    assert.ok(werr instanceof AuthRecoveryCancelledError);
    assert.equal(discardCalls.length, 0, "未建立会话无需注销");
    assert.equal(exitCalls.length, 1, "认证失败后才完成退出");
    assert.equal(recovery.isRecovering(), false);
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="r1_exit_wait_auth_failure"))


def test_exit_during_inflight_apply_session_discards_and_blocks_until_logout(tmp_path: Path) -> None:
    """R1：applySession 已调用（会话已建立/接管）期间点击退出，必须等注销成功才收口。"""
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let resolveApply = null;
    const discardCalls = [];
    const exitCalls = [];
    let discardFail = true;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "tok", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: () => new Promise((resolve) => {{ resolveApply = resolve; }}),
      discardSession: async (payload) => {{
        discardCalls.push(payload);
        if (discardFail) throw new Error("logout failed");
      }},
      exitSession: () => {{ exitCalls.push(1); }},
    }});
    const waiter = recovery.recover();
    waiter.catch(() => {{}});
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    await sleep(5);
    exitButton.click();
    await sleep(5);
    const racedPending = await Promise.race([
      waiter.then(() => "resolved", (e) => e.name),
      sleep(20).then(() => "pending"),
    ]);
    assert.equal(racedPending, "pending", "applySession 在途期间等待者不得释放");
    assert.equal(overlay.hidden, false);
    assert.equal(exitCalls.length, 0, "会话接管尚未注销，不得导航");
    resolveApply();
    await sleep(10);
    assert.equal(discardCalls.length, 1, "applySession 已产生的副作用会话必须注销");
    assert.equal(discardCalls[0].csrf_token, "tok");
    // 注销失败：保持阻塞 + 重试退出。
    assert.equal(overlay.hidden, false);
    assert.equal(exitButton.textContent, "重试退出");
    assert.equal(exitButton.disabled, false);
    assert.equal(password.disabled, true);
    assert.equal(submitButton.disabled, true);
    assert.equal(recovery.isRecovering(), true);
    assert.equal(exitCalls.length, 0);
    discardFail = false;
    exitButton.click();
    await sleep(10);
    const werr = await waiter.then(() => null, (e) => e);
    assert.ok(werr instanceof AuthRecoveryCancelledError);
    assert.equal(exitCalls.length, 1);
    assert.equal(overlay.hidden, true);
    assert.equal(recovery.isRecovering(), false);
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="r1_exit_during_apply_blocks"))


def test_destroy_with_inflight_auth_reports_session_risk_on_discard_failure(
    tmp_path: Path,
) -> None:
    """R1(第 8 点)：destroy 遇认证在途时不得静默吞掉已建立会话的注销失败。"""
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    let unhandled = null;
    process.on("unhandledRejection", (e) => {{ unhandled = e; }});
    let resolveAuth = null;
    const applyCalls = [];
    const discardCalls = [];
    let discardFail = true;
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: () => new Promise((resolve) => {{ resolveAuth = resolve; }}),
      applySession: async (payload) => {{ applyCalls.push(payload); }},
      discardSession: async (payload) => {{
        discardCalls.push(payload);
        if (discardFail) throw new Error("logout failed");
      }},
      exitSession: () => {{}},
    }});
    let waiterError = null;
    const waiter = recovery.recover();
    waiter.then(() => {{}}, (e) => {{ waiterError = e; }});
    {_overlay_handles()}
    password.value = "pw";
    submitButton.click();
    await sleep(5);
    const cleanup = recovery.destroy();
    const settled = await Promise.race([
      cleanup.then(() => "resolved", (e) => e),
      sleep(20).then(() => "pending"),
    ]);
    assert.equal(settled, "pending", "认证在途时清理结果等待迟到结果");
    assert.ok(waiterError instanceof AuthRecoveryCancelledError, "destroy 立即取消等待者");
    assert.equal(waiterError._isRecoveryCancelled, true);
    assert.equal(overlay.hidden, true, "destroy 仍拆卸遮罩");
    assert.equal(recovery.isRecovering(), false);
    resolveAuth({{ csrf_token: "late", user: {{ id: "user-1", username: "zhangsan" }} }});
    await sleep(10);
    assert.equal(applyCalls.length, 0, "destroy 后迟到会话不得应用");
    assert.equal(discardCalls.length, 1, "已建立会话仍须注销");
    const err = await cleanup.then(() => null, (e) => e);
    assert.ok(err instanceof AuthRecoveryCancelledError, "注销失败必须反映在清理结果上");
    assert.ok(err.cause && /logout failed/.test(String(err.cause.message || "")), "清理失败挂接原始注销异常");
    assert.equal(discardCalls.length, 1, "迟到会话仅注销一次");
    // 无法确认会话已注销时保持 fail closed：后续清理结果继续暴露风险。
    const cleanup2 = recovery.destroy();
    const err2 = await cleanup2.then(() => null, (e) => e);
    assert.ok(err2 instanceof AuthRecoveryCancelledError);
    await sleep(20);
    assert.equal(unhandled, null);
    """
    _assert_ok(_scenario(tmp_path, body, name="r1_destroy_inflight_session_risk"))


def test_destroy_without_inflight_auth_resolves(tmp_path: Path) -> None:
    """R1(第 8 点)：无在途会话时 destroy 的清理 Promise 正常完成，保持调用方兼容。"""
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{}},
    }});
    await recovery.destroy();
    const waiter = recovery.recover();
    const err = await waiter.then(() => null, (e) => e);
    assert.ok(err instanceof AuthRecoveryCancelledError);
    await recovery.destroy();
    const stillUndefined = recovery.destroy();
    assert.ok(stillUndefined && typeof stillUndefined.then === "function");
    await stillUndefined;
    """
    _assert_ok(_scenario(tmp_path, body, name="r1_destroy_clean_resolve"))


def test_destroy_before_any_overlay_is_null_safe(tmp_path: Path) -> None:
    body = f"""
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const recovery = createAuthRecovery({{
      documentRef,
      getCurrentUser: () => ({{ id: "user-1", username: "zhangsan" }}),
      authenticate: async () => ({{ csrf_token: "t", user: {{ id: "user-1", username: "zhangsan" }} }}),
      applySession: async () => {{}},
      discardSession: async () => {{}},
      exitSession: () => {{}},
    }});
    recovery.destroy();
    assert.equal(recovery.isRecovering(), false);
    const p = recovery.recover();
    const e = await p.then(() => null, (err) => err);
    assert.ok(e instanceof AuthRecoveryCancelledError);
    """
    _assert_ok(_scenario(tmp_path, body, name="g1_destroy_null_safe"))
