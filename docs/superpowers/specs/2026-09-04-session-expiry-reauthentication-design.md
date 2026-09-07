# 登录超时原账号重新认证与原操作恢复设计

状态：已确认，可交付开发

日期：2026-09-04

## 1. 背景

Auto Check 当前采用空闲会话超时。认证请求成功后会顺延会话有效期；超过“会话过期时间”后，下一次受保护的业务 API 请求在业务路由执行前返回 401。现有前端收到 401 后直接跳转登录页，登录成功又固定返回系统入口，因此当前页面、打开的业务弹窗、未提交输入和正在轮询的后台任务界面都会中断。

典型问题是：用户在不知情会话已经过期的情况下填写“报表特殊处理录入”新建表单，点击保存后被跳到登录页，重新登录后无法继续刚才的保存。

本需求将会话恢复建设为平台级前端能力，而不是在报表特殊处理模块中加入专用补丁。

## 2. 已确认需求

- 会话过期后不得跳离当前页面，应显示覆盖整个应用的重新登录遮罩。
- 底层页面、业务弹窗和未提交表单继续保留在当前标签页内，但在重新认证完成前不可操作、不可聚焦。
- 遮罩固定显示原登录账号，用户名不可修改，用户只输入密码。
- 重新登录必须仍是原用户；其他账号不能接管旧页面状态。
- 重新登录成功后更新会话、CSRF Token、用户资料和权限，并自动重试因带平台前置标识的 401 被拒绝的原请求一次。
- 报表特殊处理“新建后点击保存”的请求在重新登录成功后应自动完成保存，成功提示和弹窗关闭行为与未超时时一致。
- 多个请求同时遇到带平台前置标识的 401 时只显示一个重新登录遮罩，共享同一次重新认证结果。
- 文件上传、文件下载、通知请求和后台任务轮询也应接入恢复机制。
- 未提交表单只保存在当前标签页内，不写入 localStorage 或 sessionStorage；主动刷新、关闭标签页或应用重启后不恢复未提交内容。
- 已经提交到后端的后台任务不因会话过期而取消；重新登录后当前页面中的轮询继续。
- 遮罩不能通过背景点击或 Esc 关闭。用户只能重新登录，或者选择“退出系统”并放弃当前状态。
- 不新增数据库表，不改变会话有效期规则，不提升顶栏展示用大版本号 V1.2。
- 本次普通开发不打包、不刷新 dist/auto-check.exe、不提交、不推送，除非用户另行明确要求。

## 3. 非目标

- 不恢复主动刷新、关闭浏览器或应用进程重启前的未提交表单。
- 不允许切换账号后继承原用户页面。
- 不在浏览器中保存密码。
- 不重构现有后端登录系统、用户表或会话存储。
- 不为每个业务模块分别制作登录弹窗。
- 不对网络超时、500、403 或业务校验失败进行认证重试。
- 不无限重试请求；每个原请求最多进行一次认证恢复重试。

## 4. 平台边界

这是经过用户确认的平台协议变更，具有跨核心页面和跨模块复用价值：

- 平台负责会话失效识别、重新认证界面、并发协调、会话应用和请求重试。
- 业务模块继续通过 FrontendModuleContext 提供的 API 能力发请求，不保存密码、不直接操作认证状态。
- 报表特殊处理模块的普通 JSON 请求已经通过 context.api 进入平台请求链；其新建、修改、确认、作废、重开和删除不需要加入专用认证代码。
- 二进制下载需要使用平台 API 新增的可选 raw 响应模式。这是向后兼容的增量能力，现有 JSON 调用不变，platform_api 仍保持 1。
- 人行文件上传当前使用 XMLHttpRequest 展示进度，需要在平台页面内对带平台前置标识的 401 做一次重建上传请求，而不是修改后端导入业务。
- 通知中心属于平台组件，改为复用平台 API，并提供重新认证成功后的会话刷新入口。

本功能不得把报表特殊处理业务规则写入 app.js、auth_recovery.js 或其他平台文件。

## 5. 用户体验

### 5.1 遮罩

遮罩使用现有亮色活力主题、全局圆角变量和 Logo 蓝色规范。建议文案：

> 登录状态已过期
>
> 为保护当前操作，请重新验证身份。验证成功后将继续当前操作。
>
> 账号：张三
>
> 密码：________
>
> [退出系统] [重新登录]

账号区域是只读文本，不使用可编辑输入框。遮罩打开后自动聚焦密码框；回车提交。密码错误后清空密码并重新聚焦。

### 5.2 页面保护

- 遮罩显示期间，应用主区域设置 inert，并设置适当的 aria-hidden 或 aria-busy 状态。
- 登录卡使用 role="dialog"、aria-modal="true" 和明确标题关联。
- 背景点击和 Esc 不关闭遮罩。
- 登录成功后移除 inert，恢复触发请求前的焦点上下文；如果原业务成功后主动关闭弹窗，则遵循业务自身焦点恢复行为。

### 5.3 退出系统

点击“退出系统”后：

1. 拒绝所有等待重新认证的请求。
2. 停止通知连接和当前页面轮询产生的新请求。
3. 清空前端认证状态及密码字段。
4. 跳转普通登录页。
5. 不保存当前表单数据。

## 6. 总体架构

新增独立平台脚本 src/auto_check/web/auth_recovery.js。该脚本只负责重新认证状态机和遮罩交互，不包含任何业务页面逻辑。

接口契约：

```javascript
const recovery = createAuthRecovery({
  documentRef: document,
  getCurrentUser: () => authState.user,
  authenticate: authenticateOriginalUser,
  applySession: applyReauthenticatedSession,
  discardSession: discardAuthenticatedSession,
  exitSession: exitExpiredSession,
});

await recovery.recover();
await recovery.discardUnexpectedSession(payload);
recovery.isRecovering();
recovery.destroy();
```

- `getCurrentUser()` 返回恢复开始时的原用户，至少包含 `id` 和 `username`。
- `authenticate({ username, password })` 成功时返回 `Promise<{ csrf_token: string, user: object }>`；密码错误、账号不可用或网络失败时抛出可显示的错误。
- `applySession(payload)` 必须同步或异步完成新 CSRF Token、用户、权限和通知会话应用；完成前不得释放等待请求。应用失败时共享恢复 Promise 继续保持阻塞，并转入退出重试态。
- `discardSession(payload)` 使用 payload 中的新 CSRF Token 注销已经建立但不能采用的会话；身份不一致或 `applySession` 失败时调用。调用前先停止新会话通知、清空 `authState` 及已应用的权限和用户界面状态，避免留下半新半旧的认证状态；即使网络注销失败，这些本地状态也不得恢复。
- `exitSession()` 负责终止等待请求、清理认证状态并进入普通登录流程。
- `recover()` 成功时 resolve；用户退出或不可恢复错误时 reject `AuthRecoveryCancelledError`。
- `discardUnexpectedSession(payload)` 在尚未发送业务请求时发现浏览器 Cookie 已属于其他账号，直接打开 `discarding` 遮罩、注销该 payload 对应会话并退出；不得短暂释放底层页面。

状态机：

```text
authenticated
    │ 首个业务请求收到带专用标识的 401
    ▼
reauthenticating ──密码错误/网络错误──> reauthenticating
    │
    ├──同一用户登录成功──> authenticated，释放等待请求
    │
    ├──身份不一致/会话应用失败──> discarding ──注销失败──> discarding
    │                                  │
    │                                  └──注销成功──> exiting
    │
    └──退出系统──> exiting，拒绝等待请求并跳登录页
```

recovery.recover() 在 reauthenticating 状态下必须返回同一个 Promise。这样多个并发的前置 401 只会打开一个遮罩。

身份不一致或 `applySession` 失败时先进入阻塞的 `discarding` 状态并注销刚建立的新会话。此状态禁用密码输入和“重新登录”按钮，把“退出系统”按钮改为“重试退出”；点击后再次调用 `discardSession(payload)`。只有注销成功后才能进入 exiting；注销失败时遮罩保持不透明且不可关闭，提示“退出失败，请重试”，不得让错误账号会话进入应用或普通登录页。

## 7. 请求恢复协议

### 7.1 通用 fetch

后端与前端使用专用响应头区分“平台会话失效”和业务处理器自行返回的 401：

```http
X-Auto-Check-Auth-Recovery: required
```

该响应头只能由 `server.py` 的全局会话前置校验在 `session is None` 时添加。登录接口的密码错误、模块业务 401 以及其他非前置 401 均不得携带此标识。前端只有同时满足 `status === 401` 和该响应头值为 `required` 时才允许重新认证并重放请求。

所有已经进入应用的受保护 fetch/XHR 请求还必须携带：

```http
X-Auto-Check-Expected-User-Id: <authState.user.id>
```

后端在全局会话校验成功后、CSRF 和业务路由执行前比较该值与 `session.user_id`。若请求头存在且不一致，业务处理器不得执行，返回 409，并携带 `X-Auto-Check-Auth-Recovery: account-mismatch`；响应 JSON 提供当前意外会话的 `user` 和 `csrf_token`，供前端安全注销。缺少预期用户头时为兼容现有非浏览器调用暂不拒绝，但平台 API 和专用 XHR 必须发送。该头是防止跨标签页误用身份的安全绑定，不替代服务端正常授权。

主应用新增内部 authenticatedFetch(path, options)：

1. 每次发送前复制调用方请求头，并根据最新 authState.csrfToken 和 authState.user.id 覆盖 CSRF 与预期用户头，不能复用过期认证状态。
2. 保持现有 API 默认值：JSON 调用继续设置 `Content-Type: application/json`，所有请求使用 `credentials: "same-origin"`；调用方显式提供的非认证请求头不得丢失。
3. 响应为带 `account-mismatch` 标识的 409 时，解析其会话 payload 并调用 `discardUnexpectedSession(payload)`；不重试业务请求。
4. 首次响应不是带 `required` 标识的 401 时直接返回，包括没有标识的业务 401。
5. 首次响应是带 `required` 标识的 401 时调用 recovery.recover()。
6. 重新认证成功后检查 AbortSignal；已经取消则抛出 AbortError。
7. 使用同一路径、方法、可重放请求体和非认证请求头重新发送一次，并重新生成预期用户头。
8. 第二次仍是带 `required` 标识的 401 时抛出 session recovery failed 错误，不再递归；第二次账号不一致仍立即退出。

通用自动重试只接受无请求体或可重复使用的字符串请求体（当前 JSON API 属于此类）。`ReadableStream` 等一次性请求体不得进入通用自动重试，必须直接报出不可重放错误。人行上传的 `File`/`FormData` 由专用 XHR 流程保留源对象并重新构建请求。

对于附件等大 JSON 请求，调用方设置仅供平台使用的 `options.authPreflight = true`。`authenticatedFetch` 必须在发送大请求体前直接调用 `GET /api/auth/status`，请求使用 `credentials: "same-origin"`、`cache: "no-store"`，并从实际业务 fetch options 中移除 authPreflight：

- 返回未认证：先执行 recovery.recover()，成功后再发送业务请求。
- 返回原 user.id/username：若 CSRF Token 与当前状态不同，先通过 `applySession(statusPayload)` 原子采用最新用户、权限、Token 和通知会话；相同则直接发送业务请求。
- 返回其他用户：不得发送业务请求；调用 `recovery.discardUnexpectedSession(statusPayload)` 清理并注销该意外会话，进入不可恢复退出流程，防止原用户未提交内容以其他账号身份保存。
- 返回非 2xx、JSON 解析失败、字段缺失或网络失败：全部 fail closed，不发送业务请求，按状态检查错误返回，页面内容继续保留。

`/api/auth/status` 响应必须增加 `Cache-Control: private, no-store`。该预检解决大请求在服务端前置鉴权时只会有限排空请求体、连接可能提前关闭的问题。预检之后仍保留专用 401 和预期用户头的原子校验：前者覆盖会话过期竞态，后者覆盖其他标签页切换账号竞态。

后端 Handler 在进入 Router 和模块处理器前校验会话，因此带专用标识的 401 表示原写请求未进入业务处理。只有这一前置 401 才允许自动重试。

### 7.2 JSON API

现有 api(path, options) 改为调用 authenticatedFetch。默认继续解析 JSON，保持错误对象的 status 和 payload 行为不变。

新增可选 options.responseType：

- json 或未指定：返回解析后的 JSON。
- raw：平台先消费带 `required` 的 401 和带 `account-mismatch` 的 409；完成对应认证处理后，才把最终原始 Response 交给下载调用方。没有专用标识的 401、普通 409 以及 403、500 等按原始 Response 返回，不由平台改写错误语义。

responseType 和 authPreflight 仅影响平台请求行为，不发送到 fetch。

### 7.3 报表特殊处理

报表特殊处理的 createRecord 等 JSON 方法无需改变调用方式。其 Promise 在重新认证期间保持 pending，record_drawer.js 中的表单 DOM 不会重建：

```text
createRecord()
  -> context.api()
  -> 首次 POST 返回 401
  -> 遮罩重新登录
  -> context.api() 自动重试 POST
  -> createRecord() 正常返回
  -> onSaved()
  -> 关闭抽屉并刷新列表
```

模块下载改为 context.api(url, { method: "GET", responseType: "raw" })，删除模块内部对 401 的直接判断，让平台统一恢复后再返回 Response。

### 7.4 人行文件上传

uploadPbcFileWithProgress 保留 File 和 FormData，并把单次 XHR 创建拆成独立 attempt。首次 XHR 同时返回 401 且 `getResponseHeader("X-Auto-Check-Auth-Recovery") === "required"` 时：

1. 等待 recovery.recover()。
2. 使用最新 CSRF Token 和 X-Auto-Check-Expected-User-Id 创建新的 XHR。
3. 从 0% 重新上传一次。
4. 第二次仍返回带专用标识的 401 时终止并显示认证恢复失败。

XHR 收到 account-mismatch 409 时注销意外会话并退出，不重传。其他 HTTP 错误、网络错误和用户取消不进行认证重试。

### 7.5 后台任务轮询

自动对数、逐笔校验、流程链和人行导入的轮询均通过 api() 或接入后的上传助手运行。第一个状态请求收到带专用标识的 401 时，原轮询 Promise 等待重新认证；后端任务线程不受影响。恢复后同一个 job_id 继续查询状态。

遮罩期间后续轮询请求可以共同等待同一个恢复 Promise；恢复完成后正常继续。不得为同一个 401 创建多个登录界面。

### 7.6 通知中心

notification_center.js 保存平台传入的 api 回调，不再用独立 fetch 处理 JSON API。新增 updateSession({ user, csrfToken })：

- 校验 user.id 与现有 state.userId 相同。
- 更新 CSRF Token。
- 关闭旧 EventSource。
- 重新建立 EventSource，并重新加载准确未读数。
- 不重复绑定 DOM 事件。

SSE 连接本身不能可靠读取 HTTP 401；由任一普通 API 触发重新认证后，updateSession 负责重建。

## 8. 重新认证实现

重新认证复用现有端点：

- GET /api/auth/key
- POST /api/auth/login

密码必须继续通过 window.autoCheckCrypto.encryptPasswordForTransport 加密。登录请求不经过 authenticatedFetch，避免认证接口自身 401 再次触发恢复。

登录请求体中的 username 来自首次进入恢复状态时捕获的原 authState.user.username，页面上没有可修改该值的控件。

登录成功后必须同时校验：

- payload.user.id 与原 user.id 相同。
- payload.user.username 与原 username 相同。
- payload.csrf_token 非空。

成功后 applyReauthenticatedSession：

- 更新 authState.user 和 authState.csrfToken。
- 重新应用 role、capabilities、用户名显示和用户主题边界。
- 调用通知中心 updateSession。
- 关闭遮罩并释放等待请求。

当前 `AuthManager.login_failure_reason()` 对密码错误、账号停用或账号删除统一返回 `invalid credentials`，遮罩对应统一提示“账号或密码验证失败”，不改变后端错误语义，并允许用户继续尝试或退出系统。若登录响应身份与原用户不一致，或 `applyReauthenticatedSession` 失败，必须通过 `discardAuthenticatedSession(payload)` 使用新响应中的 CSRF Token 直接注销刚建立的新会话。注销前先停止通知并清空局部认证、权限和用户界面状态；注销成功后显示不可恢复提示并退出系统；注销失败时进入 `discarding` 状态，只允许通过“重试退出”再次注销，不得跳转普通登录页，避免有效 Cookie 反复把页面带回应用。

## 9. 并发、取消与错误

- recovery.recover() 使用单例 Promise；成功或退出后清理引用。
- 错误密码和临时网络错误只更新遮罩提示，不 reject 共享 Promise。
- 模块 deactivate() 触发的 AbortController 仍有效。请求等待期间 signal 被取消时，重新认证成功后不得重发该请求。
- authenticatedFetch 在单次调用内部最多执行一次恢复后的第二次请求，不使用递归，也不暴露可被调用方放宽的重试次数。
- 没有专用响应头的 401 不触发重新登录或自动重试，按现有业务错误链处理。
- 403 代表权限或 CSRF 业务结果，不触发重新登录。重新认证后的最新 CSRF Token 应避免使用旧 Token。
- 普通无认证标识的 409、422、500 和网络错误按现有业务错误链处理；带 `account-mismatch` 的 409 由平台接管，进入 `discarding` 并注销意外会话，不交给模块且不重试业务请求。
- 第二次仍收到带专用标识的 401 时显示“登录状态恢复失败，请退出后重新登录”，不自动打开第二轮。
- 重新认证期间禁止重复提交登录表单。
- 密码字段在失败、成功、退出和组件销毁时清空。

## 10. 文件改动范围

平台文件：

- 新增 src/auto_check/web/auth_recovery.js：重新认证状态机和遮罩控制。
- 修改 src/auto_check/web/index.html：加载脚本、增加遮罩语义结构，并把 styles.css、auth_recovery.js 和 app.js 的缓存参数更新为 20260904a。
- 修改 src/auto_check/web/styles.css：全局重新认证遮罩样式，严格限定 .auth-recovery-* 作用域。
- 修改 src/auto_check/web/app.js：authenticatedFetch、api 接入、认证回调、会话应用、退出处理、XHR 上传恢复、v1.2.23 更新日志。
- 修改 src/auto_check/web/notification_center.js：使用平台 API 和 updateSession。
- 修改 src/auto_check/modules/report_special_processing/web/api.js：下载使用 context.api 的 raw 模式；不加入模块专用登录逻辑。
- 修改 src/auto_check/app/server.py：前置 401 增加 required 标识；校验 X-Auto-Check-Expected-User-Id 并在不一致时返回 account-mismatch；认证状态响应禁止缓存。

测试和文档：

- 新增 tests/test_auth_recovery_frontend.py：Node 场景测试重新认证状态机。
- 修改 tests/test_web_static.py：资源加载、API 重试、上传恢复、遮罩结构和版本日志断言。
- 修改 tests/notifications/test_frontend_static.py：通知中心 API 注入和会话刷新断言。
- 修改 tests/modules/report_special_processing/test_frontend_static.py：下载走平台 raw API、模块不自行处理登录。
- 修改 tests/module_system/test_server_integration.py：专用响应头、预期用户绑定、状态禁缓存及所有前置拒绝均不执行写路由。
- 修改 README.md：详细记录行为和限制，新增 v1.2.23。

登录恢复自身的 server.py 改动只限前置认证响应头、预期用户绑定和认证状态禁缓存，不修改 security.py、数据库、权限矩阵和模块 manifest。与记录附件需求合并实施时，允许附件设计按其独立范围修改报表特殊处理模块 manifest 和数据库迁移；若登录恢复还需要扩大后端范围，开发者应先停止并说明原因。

## 11. 测试设计

### 11.1 状态机

- 首个 recover 打开遮罩并固定原用户名。
- 并发调用返回同一 Promise，只发送一次登录。
- 错误密码保持等待状态并清空密码。
- 网络错误可继续重试。
- 同用户登录成功释放所有等待者。
- 身份不一致拒绝恢复。
- 退出系统拒绝等待者并调用退出回调。
- Esc 和背景点击不关闭。
- destroy 清理事件和密码。

### 11.2 请求重试

- GET 首次收到带专用标识的 401 后登录成功，自动重试一次并返回结果。
- POST 首次收到带专用标识的 401 时业务处理次数为 0；恢复后只执行一次。
- 没有专用标识的业务 401 不触发遮罩或重试。
- 预期用户与实际会话不一致时返回 account-mismatch，业务处理次数为 0，前端注销意外会话且不重试原业务请求。
- 第二次仍收到带专用标识的 401 时不再重试。
- 403、普通无认证标识的 409、500 和网络错误不触发遮罩；只有带 `account-mismatch` 标识的 409 进入 `discarding` 遮罩并注销意外会话，不重试业务请求。
- JSON 默认请求头、same-origin credentials 和调用方非认证请求头在两次请求中保持一致。
- 每次业务请求使用当前 authState.user.id 生成预期用户头；后端实际路由前校验，防止预检后的跨标签页账号切换竞态。
- ReadableStream 等不可重放请求体拒绝自动重试。
- authPreflight 在发送业务 body 前发现未认证时先恢复；发现不同账号或网络失败时不发送业务请求。
- authPreflight 使用双端 no-store；非 2xx、异常 JSON 或字段缺失均 fail closed，业务请求次数为 0。
- 并发 JSON 请求只共享认证，不互相覆盖响应。
- 等待期间 AbortSignal 取消的请求不重发。
- raw 响应保留 Content-Disposition 和 Blob。

### 11.3 报表特殊处理验收场景

1. 登录并打开“报表特殊处理录入”。
2. 点击新建，填写全部必填项。
3. 模拟会话过期。
4. 点击保存。
5. 页面不跳转，抽屉内容不变，显示固定原账号的重新登录遮罩。
6. 输入错误密码，遮罩提示错误，表单仍保留。
7. 输入正确密码。
8. 系统自动完成原保存，不要求再次点击保存。
9. 只新增一条记录，成功提示、抽屉关闭和列表刷新正常。

### 11.4 其他回归

- 自动对数、逐笔校验、流程链和人行导入轮询恢复。
- 人行上传 401 后重新从 0% 上传一次。
- 报表特殊处理导出在恢复后完成下载。
- 通知中心更新 Token、重建 SSE 且不重复绑定事件。
- 普通首次访问无会话仍跳普通登录页。
- 主动退出登录行为不变。
- 角色权限被收回后，重试返回 403 并正确提示。
- 页面主题、圆角和焦点样式符合现有规范。

## 12. 文档与版本

- 顶栏和系统信息继续显示 V1.2，不跨大版本。
- 应用内新增 v1.2.23，功能条目简明描述“新增登录超时原账号重新认证及原操作自动恢复”，并保留一条“系统优化及BUG修复”。
- README 的 v1.2.23 详细说明遮罩、同账号限制、自动重试一次、当前标签页保留和刷新后不恢复。
- 登录恢复本身不产生模块 manifest.release_notes；合并实施时由记录附件设计把附件功能写入报表特殊处理模块 release notes。

## 13. 回滚

该功能无数据库迁移。回滚时恢复 server.py、index.html、styles.css、app.js、notification_center.js 和报表特殊处理 web/api.js，删除 auth_recovery.js 及其测试即可。回滚后移除专用响应头并恢复现有 401 跳普通登录页行为，不影响已存在的用户、配置、历史和业务数据。

## 14. 验收标准

1. 会话过期时当前页面不跳转。
2. 重新登录遮罩只允许原用户名和密码。
3. 未提交表单在当前标签页中保持不变。
4. 报表特殊处理保存请求在正确密码登录后自动完成且只落一条记录。
5. 并发 401 只出现一个遮罩。
6. 每个请求最多自动重试一次。
7. 后台任务轮询使用原 job_id 继续。
8. 上传、下载和通知恢复符合设计。
9. 退出系统清理状态并跳普通登录页。
10. 相关测试、模块测试和全量测试通过，git diff --check 无真实 whitespace error。
11. 未打包、未提交、未推送。
