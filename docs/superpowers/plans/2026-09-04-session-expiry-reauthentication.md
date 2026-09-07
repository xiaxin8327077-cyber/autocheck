# Session Expiry Reauthentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不离开当前页面的前提下完成原账号重新认证，并安全地自动重试一次因会话过期而被业务前置鉴权拒绝的请求。

**Architecture:** 新增独立 auth_recovery.js 管理单例重新认证状态机和全屏遮罩；后端只在全局会话前置校验失败时返回 `X-Auto-Check-Auth-Recovery: required`，主应用仅据此标识通过 authenticatedFetch 更新会话并重试一次。模块 JSON 请求沿用 context.api，raw 下载使用 context.api 的增量响应模式，XHR 上传和通知中心接入同一平台恢复生命周期。

**Tech Stack:** 原生 JavaScript、HTML/CSS、Python pytest、Node.js 场景测试、现有 Python HTTP 服务与认证 API。

## Global Constraints

- 开发前完整阅读 AGENTS.md、docs/ai-modular-development-rules.zh-CN.md 和设计文档 docs/superpowers/specs/2026-09-04-session-expiry-reauthentication-design.md。
- 与记录附件需求合并实施时，同时阅读并执行 `docs/superpowers/specs/2026-09-04-report-special-processing-record-attachments-design.md` 和 `docs/superpowers/plans/2026-09-04-report-special-processing-record-attachments.md`。
- 这是已批准的平台能力变更；不得把业务规则写入平台文件，也不得在报表特殊处理模块中复制登录逻辑。
- 重新认证只允许原用户，用户名不可编辑，每个请求最多认证恢复重试一次。
- 只有带 `X-Auto-Check-Auth-Recovery: required` 的平台前置 401 能触发遮罩和自动重试；业务 401 不得重放。
- 未提交数据只保留在当前标签页内，不写 localStorage 或 sessionStorage。
- 不新增依赖、数据库表、权限码或配置项。
- 顶栏大版本保持 V1.2；应用内更新日志新增 v1.2.23。
- 登录恢复自身不修改模块 manifest；合并实施时允许附件计划把报表特殊处理模块升至 1.2.13、schema 升至 6，并把模块功能并入同一个 v1.2.23。
- 修改任何文件前记录 `git status --short` 基线；最终只比较本需求引入的差异，不要求用户原有脏工作区变干净。
- 测试和验证优先交由 gpt-5.6-luna high 子代理执行，主会话检查结果。
- 除非用户另行要求，不打包、不刷新 dist/auto-check.exe、不提交、不推送。

---

### Task 1: 建立可独立测试的重新认证状态机

**Files:**
- Create: `src/auto_check/web/auth_recovery.js`
- Create: `tests/test_auth_recovery_frontend.py`

**Interfaces:**
- Consumes: `getCurrentUser()`；`authenticate({ username, password }) -> Promise<{ csrf_token, user }>`；可异步的 `applySession(payload)`；`discardSession(payload)`；`exitSession()`。
- Produces: `createAuthRecovery(options)`，返回 `recover()`、`discardUnexpectedSession(payload)`、`isRecovering()`、`destroy()`。

- [ ] **Step 1: 写 Node 场景测试加载新脚本**

在 tests/test_auth_recovery_frontend.py 中用 subprocess.run(["node", script]) 建立最小 DOM stub，覆盖：

```javascript
const recovery = createAuthRecovery({
  documentRef,
  getCurrentUser: () => ({ id: "user-1", username: "zhangsan", display_name: "张三" }),
  authenticate,
  applySession,
  discardSession,
  exitSession,
});
const first = recovery.recover();
const second = recovery.recover();
assert.equal(first, second);
assert.equal(overlay.hidden, false);
assert.equal(username.textContent, "zhangsan");
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_auth_recovery_frontend.py`

Expected: FAIL，因为 auth_recovery.js 或 createAuthRecovery 尚不存在。

- [ ] **Step 3: 实现单例恢复 Promise 和遮罩事件**

auth_recovery.js 使用 IIFE，同时暴露浏览器全局和 CommonJS 测试入口：

```javascript
(function (globalScope) {
  "use strict";

  class AuthRecoveryCancelledError extends Error {
    constructor(message = "authentication recovery cancelled") {
      super(message);
      this.name = "AuthRecoveryCancelledError";
    }
  }

  function createAuthRecovery(options) {
    let recoveryPromise = null;
    let resolveRecovery = null;
    let rejectRecovery = null;
    let originalUser = null;

    function recover() {
      if (recoveryPromise) return recoveryPromise;
      originalUser = Object.freeze({ ...options.getCurrentUser() });
      recoveryPromise = new Promise((resolve, reject) => {
        resolveRecovery = resolve;
        rejectRecovery = reject;
      });
      openOverlay(originalUser);
      return recoveryPromise;
    }

    return Object.freeze({
      recover,
      discardUnexpectedSession,
      isRecovering: () => recoveryPromise !== null,
      destroy,
    });
  }

  globalScope.AutoCheckAuthRecovery = { createAuthRecovery, AuthRecoveryCancelledError };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { createAuthRecovery, AuthRecoveryCancelledError };
  }
})(typeof window !== "undefined" ? window : globalThis);
```

补齐 openOverlay、登录提交、错误显示、同 user.id/username 校验、退出和 destroy。错误密码或网络错误不得 reject recoveryPromise；`applySession` 完成前不得 resolve；成功和退出后必须清理密码及 Promise 引用。身份不一致或 `applySession` 失败时进入 `discarding`，调用 `discardSession(payload)`。该状态禁用密码和重新登录按钮，将退出按钮文案改成“重试退出”；注销失败后点击此按钮再次调用 `discardSession`，注销成功后才调用 `exitSession`。不得把有效 Cookie 带到应用或普通登录页。

- [ ] **Step 4: 增加完整状态机测试**

覆盖并发共享、错误密码重试、网络错误、applySession 失败、身份不一致时注销新会话、局部状态清理、`discarding` 按钮状态与注销失败重试、`discardUnexpectedSession(payload)` 不释放页面且不进入密码验证、退出、Esc/背景不可关闭、重复提交保护和 destroy。

- [ ] **Step 5: 运行状态机测试**

Run: `python -m pytest -q tests/test_auth_recovery_frontend.py`

Expected: PASS。

### Task 2: 加入遮罩结构、样式和主应用认证回调

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: Task 1 的 `window.AutoCheckAuthRecovery.createAuthRecovery`。
- Produces: `authRecovery`、`authenticateOriginalUser`、`applyReauthenticatedSession`、`discardAuthenticatedSession`、`exitExpiredSession`。

- [ ] **Step 1: 写遮罩静态契约测试**

断言 index.html 在 app.js 前加载 /auth_recovery.js?v=20260904a，把 /styles.css 和 /app.js 的缓存参数同步更新为 20260904a，并包含：

```html
<div id="authRecoveryOverlay" class="auth-recovery-overlay" hidden>
  <section role="dialog" aria-modal="true" aria-labelledby="authRecoveryTitle">
    <span id="authRecoveryUsername"></span>
    <input id="authRecoveryPassword" type="password" autocomplete="current-password">
    <button id="authRecoveryExit" type="button">退出系统</button>
    <button id="authRecoverySubmit" type="submit">重新登录</button>
  </section>
</div>
```

断言样式全部限定在 .auth-recovery-*，使用 var(--ui-radius)、现有主题色变量，不包含暗色主题或自定义主题。

- [ ] **Step 2: 运行静态测试并确认失败**

Run: `python -m pytest -q tests/test_web_static.py -k "auth_recovery"`

Expected: FAIL，因为遮罩和脚本尚未接入。

- [ ] **Step 3: 加入 HTML、CSS 和脚本加载**

在 notification_center.js 与 app.js 之前加载 auth_recovery.js。遮罩层使用固定定位和最高业务层级；显示期间给应用容器设置 inert，关闭后移除。

- [ ] **Step 4: 实现认证回调**

authenticateOriginalUser 使用直接 fetch 调用 /api/auth/key 和 /api/auth/login，不能调用会触发恢复的 authenticatedFetch。密码继续通过 autoCheckCrypto 加密。

discardAuthenticatedSession(payload) 先把 `payload.csrf_token` 保存为局部变量，再停止通知中心、清空 authState 和已经应用的角色/权限/用户名界面状态，最后用保存的 Token 直接 POST /api/auth/logout，不经过 authenticatedFetch。失败时抛错；本地认证状态仍保持清空，由遮罩进入 `discarding` 并通过“重试退出”重试同一个 payload。

applyReauthenticatedSession 必须：

```javascript
async function applyReauthenticatedSession(payload) {
  authState.csrfToken = payload.csrf_token || "";
  authState.user = payload.user || null;
  document.documentElement.dataset.role =
    authState.user?.role === "admin" ? "admin" : "user";
  updateCurrentUsername();
  applyRoleAccess();
  await window.AutoCheckNotificationCenter?.updateSession?.({
    user: { ...authState.user },
    csrfToken: authState.csrfToken,
  });
}
```

exitExpiredSession 清空认证状态和密码，停止通知中心并跳转 /login.html。

- [ ] **Step 5: 运行遮罩和现有登录静态测试**

Run: `python -m pytest -q tests/test_web_static.py -k "auth_recovery or authenticated or logout or csrf" tests/test_login_page.py`

Expected: PASS。

### Task 3: 用 authenticatedFetch 统一恢复 JSON 和 raw 请求

**Files:**
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_auth_recovery_frontend.py`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: Task 2 的 `authRecovery.recover()` 和实时 `authState.csrfToken`。
- Produces: `authenticatedFetch(path, options)`；扩展 `api(path, options)` 支持 `responseType: "raw"` 和平台内部 `authPreflight: true`。

- [ ] **Step 1: 写请求重试失败测试**

用 Node stub 依次返回带 `X-Auto-Check-Auth-Recovery: required` 的 401 和 200，断言：

```javascript
const result = await api("/api/modules/report-special-processing/records", {
  method: "POST",
  body: JSON.stringify({ table_name: "t_demo" }),
});
assert.equal(fetchCalls.length, 2);
assert.equal(loginCalls, 1);
assert.equal(fetchCalls[1].headers.get("X-CSRF-Token"), "new-token");
assert.equal(result.ok, true);
```

另测第二次带标识的 401、无标识业务 401、account-mismatch 409、403 不恢复、AbortSignal、并发前置 401 单遮罩、raw Response、请求头与 credentials 保持，以及不可重放请求体拒绝恢复。无标识业务 401 必须保持现有错误处理且 fetch 只调用一次；账号不一致时业务处理为 0 且不得重试。

为 `authPreflight: true` 增加场景：状态为原用户且 Token 相同则业务请求一次；原用户但 Token 不同时先 applySession 再发送；未认证则先恢复再发送；状态为其他用户则注销并退出且业务请求零次；状态检查非 2xx、异常 JSON、字段缺失或网络失败时业务请求零次。断言预检 fetch 同时使用 `cache: "no-store"` 和 same-origin credentials，且 `authPreflight` 不进入业务 fetch options。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_auth_recovery_frontend.py -k "request or retry or concurrent or raw"`

Expected: FAIL，因为 api 仍直接跳登录页。

- [ ] **Step 3: 实现请求工厂和一次重试**

每次调用 requestOnce 时重新构造 headers。`isRecoverableAuthResponse` 必须同时检查状态码和专用响应头：

```javascript
async function authenticatedFetch(path, options = {}) {
  const { authPreflight = false, responseType: _responseType, ...fetchOptions } = options;
  if (authPreflight) await verifyOriginalSessionBeforeSend();
  const requestOnce = () => {
    const method = String(fetchOptions.method || "GET").toUpperCase();
    const headers = new Headers(fetchOptions.headers || {});
    if (authState.user?.id) {
      headers.set("X-Auto-Check-Expected-User-Id", String(authState.user.id));
    }
    if (method !== "GET" && authState.csrfToken) {
      headers.set("X-CSRF-Token", authState.csrfToken);
    }
    return fetch(path, { ...fetchOptions, credentials: "same-origin", headers });
  };

  let response = await requestOnce();
  if (isAccountMismatchResponse(response)) {
    await authRecovery.discardUnexpectedSession(await response.clone().json());
    throw new window.AutoCheckAuthRecovery.AuthRecoveryCancelledError();
  }
  if (!isRecoverableAuthResponse(response)) return response;
  assertReplayableBody(fetchOptions.body);
  await authRecovery.recover();
  if (fetchOptions.signal?.aborted) throw createAbortError();
  response = await requestOnce();
  if (isAccountMismatchResponse(response)) {
    await authRecovery.discardUnexpectedSession(await response.clone().json());
    throw new window.AutoCheckAuthRecovery.AuthRecoveryCancelledError();
  }
  if (isRecoverableAuthResponse(response)) throw createAuthRecoveryFailedError();
  return response;
}
```

`verifyOriginalSessionBeforeSend()` 直接 fetch `/api/auth/status`，固定使用 `{credentials: "same-origin", cache: "no-store"}`，不递归进入 authenticatedFetch。响应必须为 2xx 合法 JSON并含布尔 authenticated；authenticated=false 时要求 user 为空并调用共享 recovery，authenticated=true 时要求合法 user 和非空 csrf_token。同一用户且 Token 不同时 await applySession(statusPayload)，Token 相同时直接继续；不同用户时调用 `authRecovery.discardUnexpectedSession(statusPayload)`。不符合结构的响应全部 fail closed。预检后仍执行正常业务 401 标识和 account-mismatch 判断，分别覆盖过期与跨标签页切换账号竞态。

现有 `api` 的 JSON 默认分支继续补 `Content-Type: application/json`，不能因包装丢失调用方 headers 或 same-origin credentials。平台请求每次从 authState.user.id 生成 X-Auto-Check-Expected-User-Id。通用重试只支持无 body 或字符串 body；`ReadableStream` 等一次性 body 在重登前直接抛出不可重放错误。`api` 从 options 中移除 responseType 和 authPreflight；平台先消费带 required 的 401 和带 account-mismatch 的 409，raw 模式随后返回最终 `Response`。无标识 401、普通 409、403、500 等不改写状态或错误语义；默认 JSON 分支继续保留现有错误格式。

- [ ] **Step 4: 保持首次加载边界**

ensureAuthenticated 在应用初始化时仍直接检查 /api/auth/status。初始无会话继续跳 /login.html；只有已经进入应用后的业务请求 401 才显示遮罩。

- [ ] **Step 5: 运行请求测试**

Run: `python -m pytest -q tests/test_auth_recovery_frontend.py tests/test_web_static.py -k "auth_recovery or api_helper or authenticated"`

Expected: PASS。

### Task 4: 接入报表特殊处理保存与下载

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/api.js`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`
- Modify: `tests/test_auth_recovery_frontend.py`

**Interfaces:**
- Consumes: Task 3 的 context.api JSON 默认模式和 responseType raw 模式。
- Produces: 所有模块请求统一走平台认证恢复；模块不自行显示登录或跳转。

- [ ] **Step 1: 写模块契约测试**

断言 createRecord 继续调用 context.api；download 改为：

```javascript
const response = await context.api(
  API_PREFIX + path + queryString(parameters),
  { method: "GET", responseType: "raw", signal: controller.signal },
);
```

断言模块 api.js 不再通过 `window.location` 跳登录页，也不再对 401 实现模块私有的登录恢复；模块仍可把 raw Response 的非 2xx 状态交给现有 normalizeError 链处理。

- [ ] **Step 2: 运行模块测试并确认失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_frontend_static.py -k "api or download or auth"`

Expected: FAIL，因为下载仍使用原生 fetch。

- [ ] **Step 3: 修改下载实现**

保留 AbortController、Content-Disposition、空 Blob 和 normalizeError 行为，只把底层 fetch 改为 context.api raw 模式。

- [ ] **Step 4: 增加新建保存验收场景**

在 Node 场景中保持一组表单 DOM 值，模拟 createRecord 首次收到带专用标识的 401、同用户登录、第二次 200。断言表单值在登录期间不变、业务调用最终成功、保存回调一次、创建成功一次。

- [ ] **Step 5: 运行报表特殊处理前端测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_frontend_static.py tests/test_auth_recovery_frontend.py`

Expected: PASS。

### Task 5: 接入人行上传和后台轮询

**Files:**
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`
- Modify: `tests/test_auth_recovery_frontend.py`

**Interfaces:**
- Consumes: `authRecovery.recover()` 和最新 `authState.csrfToken`。
- Produces: `uploadPbcFileAttempt(file, form)` 和最多一次重试的 `uploadPbcFileWithProgress(file, form)`。

- [ ] **Step 1: 写 XHR 恢复测试**

模拟第一个 XHR 返回 401 且 `getResponseHeader("X-Auto-Check-Auth-Recovery")` 为 `required`、第二个返回 200，断言创建两个 XHR、两次都携带对应 authState 的 X-Auto-Check-Expected-User-Id、第二次携带新 CSRF Token、进度从 0 重新开始、最终只加入一个 uploaded file。另测没有专用响应头的 401 不触发恢复或重传，account-mismatch 409 注销退出且不重传。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/test_auth_recovery_frontend.py -k "upload or polling"`

Expected: FAIL，因为 XHR 401 仍被当作普通上传失败。

- [ ] **Step 3: 拆分 XHR attempt 并接入一次恢复**

XHR 每次发送都设置 X-Auto-Check-Expected-User-Id。非 2xx 错误对象必须包含 status、payload 和认证恢复响应头。uploadPbcFileWithProgress 仅在 status === 401 且标识值为 required 时调用恢复并重新创建 XHR；account-mismatch 409 调用 discardUnexpectedSession，其他错误直接抛出。第二次仍收到带标识的 401 时不再重传。

- [ ] **Step 4: 验证轮询保持 job_id**

为 pollRunJob、pollDbValidationJob、pollFlowChainJob 和 pollPbcImportJob 添加场景断言：状态请求首次收到带专用标识的 401 并恢复后仍请求同一 URL，不重新调用 start API。

- [ ] **Step 5: 运行相关前端测试**

Run: `python -m pytest -q tests/test_web_static.py tests/test_auth_recovery_frontend.py -k "pbc or poll or run_job or flow or db_validation or auth_recovery"`

Expected: PASS。

### Task 6: 更新通知中心认证生命周期

**Files:**
- Modify: `src/auto_check/web/notification_center.js`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/notifications/test_frontend_static.py`

**Interfaces:**
- Consumes: start 参数中的 `api` 和 Task 2 的重新认证成功回调。
- Produces: `window.AutoCheckNotificationCenter.updateSession({ user, csrfToken })`。

- [ ] **Step 1: 写通知中心测试**

断言 apiRequest 调用 state.api；updateSession 只接受同 user.id，更新 Token，关闭旧 EventSource，重建连接并加载第一页，而且不再次调用 bindEvents。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/notifications/test_frontend_static.py`

Expected: FAIL，因为通知中心仍直接 fetch 且没有 updateSession。

- [ ] **Step 3: 保存平台 API 并实现 updateSession**

start 时保存 api；现有所有通知 JSON 请求通过该回调执行。updateSession 只刷新会话和连接，不改变 started，不重复绑定事件。

- [ ] **Step 4: 主应用传入 api**

ensureAuthenticated 后启动通知中心时把 api 传入，而不是 null。applyReauthenticatedSession 调用 updateSession。

- [ ] **Step 5: 运行通知测试**

Run: `python -m pytest -q tests/notifications tests/test_web_static.py -k "notification or auth_recovery"`

Expected: PASS。

### Task 7: 增加认证恢复标识、预期用户绑定和禁缓存状态

**Files:**
- Modify: `src/auto_check/app/server.py`
- Modify: `tests/module_system/test_server_integration.py`

**Interfaces:**
- Consumes: 现有 Handler 鉴权、`_send_early_json(..., headers=...)`、模块路由和测试服务器 fixture。
- Produces: required/account-mismatch 两类协议标识、X-Auto-Check-Expected-User-Id 原子绑定、auth status no-store 和写请求安全证据。

- [ ] **Step 1: 写专用响应头和不调用模块处理器的失败测试**

注册一个会记录调用次数的 POST 模块路由，使用失效 Cookie 发送带 JSON body 的请求：

```python
status, data, response_headers = _request(
    server,
    "POST",
    "/api/modules/alpha/tiny",
    body={"value": "keep"},
    headers={"Cookie": "auto_check_session=expired"},
)
assert status == 401
assert json.loads(data) == {"error": "login required"}
assert response_headers["X-Auto-Check-Auth-Recovery"] == "required"
assert server.module_route_calls == []
```

再覆盖两类反例，防止业务 401 被前端误判后重放：

1. 登录接口密码错误返回 401，不包含该响应头。
2. 携带有效会话请求普通非模块 API，并让 router stub 返回业务 401，不包含该响应头。

再写预期用户绑定测试：有效会话 user-2 收到 `X-Auto-Check-Expected-User-Id: user-1` 时，在 CSRF 和业务路由之前返回 409，响应头为 `X-Auto-Check-Auth-Recovery: account-mismatch`，响应 JSON 含 user-2 和其 csrf_token，模块写调用为 0。预期 ID 相同时继续正常处理；缺少该头保持兼容。

auth status 测试断言响应包含 `Cache-Control: private, no-store`。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest -q tests/module_system/test_server_integration.py -k "requires_login or expired_session or expected_user or auth_status"`

Expected: FAIL，因为当前尚无专用响应头、预期用户绑定和 status no-store；但失效会话的 `module_route_calls` 必须仍为 0。若调用计数不为 0，立即停止实施，因为自动重试写请求的安全前提不成立。

- [ ] **Step 3: 实现三项最小后端协议**

在 `server.py` 中完成：

1. `session is None` 的 `_send_early_json` 增加 required 标识：

```python
self._send_early_json(
    method,
    401,
    {"error": "login required"},
    headers=[("X-Auto-Check-Auth-Recovery", "required")],
)
```

2. session 成功后、CSRF 校验前读取 `X-Auto-Check-Expected-User-Id`。存在且不等于 `session.user_id` 时，用 `_send_early_json` 返回 409、account-mismatch 响应头，以及 `{error, csrf_token, user}`；user 使用 `router.session_user_payload(session)`。
3. `/api/auth/status` 的 200 响应增加 `Cache-Control: private, no-store`。

不要给登录失败、业务路由 401 或普通 409 统一添加认证恢复头，不修改 security.py。预期用户头缺失时保持向后兼容。

- [ ] **Step 4: 运行后端契约测试**

Run: `python -m pytest -q tests/module_system/test_server_integration.py -k "requires_login or expired_session or expected_user or auth_status" tests/test_security.py`

Expected: PASS；前置 401 有 required，普通 401 无标识，账号不一致 409 有 account-mismatch，status 禁缓存，所有前置拒绝的模块写处理器调用次数为 0。

### Task 8: 同步版本文档并完成验证

**Files:**
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: Tasks 1-7 的最终行为。
- Produces: v1.2.23 更新说明和完整验证证据。

- [ ] **Step 1: 写版本断言**

断言应用内存在 v1.2.23，包含“新增登录超时原账号重新认证及原操作自动恢复”和一条“系统优化及BUG修复”；DEFAULT_VERSION 仍为 V1.2；index.html 中 styles.css、auth_recovery.js 和 app.js 的缓存参数均为 20260904a。

- [ ] **Step 2: 更新 README 和应用内日志**

README 详细说明同账号、遮罩保留、自动重试一次、主动刷新不恢复、上传重新开始和后台轮询继续。应用内日志保持精简。

- [ ] **Step 3: 运行直接相关测试**

Run:

```powershell
python -m pytest -q tests/test_auth_recovery_frontend.py
python -m pytest -q tests/test_security.py
python -m pytest -q tests/test_web_static.py
python -m pytest -q tests/notifications
python -m pytest -q tests/modules/report_special_processing
python -m pytest -q tests/module_system/test_server_integration.py
```

Expected: 全部 PASS。

- [ ] **Step 4: 运行全量验证**

核对开发开始前保存的 `git status --short` 工作区基线，区分用户已有修改与本需求新增修改。完成后由子代理运行：

```powershell
python -m pytest -q
git diff --check
git status --short
```

Expected: pytest 全部 PASS；git diff --check 无真实 whitespace error；相对开发前基线，本需求只新增或修改计划批准的文件，用户原有无关修改保持不变。

- [ ] **Step 5: 人工验收关键场景**

按设计文档 11.3 的九步场景验证报表特殊处理新建保存。再验证错误密码、退出系统、权限收回、上传、下载和一个后台任务轮询。

- [ ] **Step 6: 交付说明**

按“代码内容、配置/文档内容、行为变化、测试证据、未执行事项”五部分报告。明确说明未新增配置和数据库变更，未打包、未提交、未推送。
