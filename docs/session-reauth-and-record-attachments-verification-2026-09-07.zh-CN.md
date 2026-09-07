# 登录超时续操作与报表特殊处理附件验收报告

验收日期：2026-09-07

验收对象：`D:\xiaxin\auto_check` 当前工作区未提交实现，基线 HEAD `682049d`。

结论：暂不通过验收。既有自动化测试全部通过，但补充审查和隔离场景运行发现下列功能与认证状态处理缺陷。测试通过不能替代这些缺失场景的验收。

## 1. 实际验证结果

| 检查 | 结果 |
| --- | --- |
| 登录恢复、报表特殊处理模块、服务端集成、通知静态定向测试 | 235 passed，54.01s，退出码 0 |
| `python -m pytest -q` | 1663 passed，2 skipped，118.95s，退出码 0 |
| `git diff --check` | 退出码 0，无实际空白错误；仅 LF/CRLF 警告 |
| 状态机、预检与 XHR 补充 Node 场景 | 复现下述 F2–F6；直接加载当前实现或测试中同样提取的源码 |
| 附件抽屉与台账父组件调用链审查 | 确认 F1 的版本冲突重建路径 |
| 附件后端补充检查 | SQLAlchemy 查询列确认 F7；内存 ZIP 校验复现 F8 |

两项 skipped 为 `tests/module_system/test_runtime.py` 的目录符号链接测试，原因是当前环境不支持创建符号链接，不属于业务失败。

本次未连接真实业务数据库执行迁移，未进行登录真实应用后的浏览器全流程人工验收。下述 Node 复现使用隔离 DOM/网络响应，不代表已通过真实浏览器端到端验收。已有明确阻塞项，不能据此批准上线。

## 2. 需修复的问题

### F1 — P1：版本冲突会重建抽屉，丢失未保存字段和附件

位置：

- `src/auto_check/modules/report_special_processing/web/components/record_drawer.js:616`
- `src/auto_check/modules/report_special_processing/web/pages/ledger.js:167`
- `src/auto_check/modules/report_special_processing/web/pages/ledger.js:561`
- `src/auto_check/modules/report_special_processing/web/pages/ledger.js:566`

触发：标签页 A 打开记录、修改字段并添加图片；标签页 B 先保存同一记录，使 `row_version` 递增；A 点击保存。

实际路径：`record_version_conflict` 被标记为 `refreshRequired` → `showError()` 自动调用 `onConflict()` → `refreshRecord()` 获取服务器记录并 `render()` → `root.replaceChildren()` 用新抽屉替换原抽屉。原字段值和待保存附件状态不再保留。虽然新增 catch 注释声称失败不销毁附件，但父组件重建仍丢弃了编辑状态。

要求：普通 409 仅显示冲突提示，保留原表单、File 和附件组件。刷新/放弃/合并必须是明确用户动作，不能在错误回调中自动覆盖。两个抽屉入口都需要检查。

补测：用真实台账父组件和抽屉组合测试上述双标签页冲突，断言字段值、File 对象及附件数量不变，且用户确认前不重建抽屉。

### F2 — P1：注销失败态可被后续超时请求重新打开为登录态

位置：`src/auto_check/web/auth_recovery.js:248`、`:388`。

触发：调用 `discardUnexpectedSession()` 进入 `discarding`，注销请求失败；随后另一并发业务请求收到前置 401 并调用 `recover()`。

实际：`recover()` 只检查 `recoveryPromise`，不阻止 `discarding`。前一步已经清空该 Promise，后一步会重新捕获用户并调用 `openOverlayReauthenticating()`。

隔离运行输出：

```text
DISCARD_BEFORE_RECOVER true 重试退出
DISCARD_AFTER_RECOVER false 退出系统
```

两个布尔值是密码框的 disabled 状态，说明注销失败后密码框被重新启用，破坏“只能重试退出”的状态约束。

要求：`discarding` 和终止态禁止任何新的登录恢复，统一取消/阻塞等待者；注销过程使用单例控制，迟到的 401 不得覆盖退出状态或原用户身份。

### F3 — P2：点击退出后，迟到的登录成功结果仍应用会话

位置：`src/auto_check/web/auth_recovery.js:299`、`:377`。

触发：输入密码点击重新登录，登录响应尚未返回时点击“退出系统”，随后登录成功响应返回。

实际：退出回调执行、原等待请求被取消之后，`handleAuthSuccess()` 仍调用 `applySession()`；没有验证该登录尝试是否已退出/失效，也没有清理迟到建立的会话。

隔离运行输出：

```text
EXIT_DURING_LOGIN ["exit","waiterCancelled","applySession"]
```

影响：前端退出后可被迟到结果恢复认证状态。实际登录响应设置 Cookie，登录页又会自动进入已有会话，因此退出流程不能保证最终处于已注销状态。

要求：为认证尝试设置生命周期标识；退出、销毁、转入注销时使旧回调失效。对已成功建立但不能采用的迟到会话安全注销，不能仅忽略 `applySession`。

补测：延迟登录成功/失败响应，分别在退出、销毁、进入 discarding 后返回，断言不会再次采用或释放会话。

### F4 — P2：并发账号不一致请求会覆盖等待者

位置：`src/auto_check/web/auth_recovery.js:388`，尤其 `:400`。

触发：两个并发请求均返回 `account-mismatch`，先后调用 `discardUnexpectedSession()`。

实际：每次调用创建新 Promise，但只保留一个 `discardCompletion`，第二次覆盖第一次；注销完成后仅第二个 Promise 被取消，第一个永久 pending。

隔离运行输出：

```text
CONCURRENT_DISCARD_PROMISES pending cancelled
```

要求：共享同一次注销 Promise 或完整维护等待者集合；所有等待者最终取消，不能丢失；重复退出点击也应避免并行注销。

### F5 — P2：大请求预检未完整校验响应结构和原用户名

位置：`src/auto_check/web/app.js:1633`。

实际遗漏：

- `authenticated=false` 时没有要求 `user` 为空。
- `authenticated=true` 时只校验用户 ID 存在，没有要求合法用户名，也没有比较原 username。

隔离运行分别返回“已认证但 user 缺 username”和“未认证但 user 非空”，两者随后都发送了业务写请求：

```text
MISSING_USERNAME_ACCEPTED [ '/api/auth/status', '/test-write' ]
CONTRADICTORY_STATUS_ACCEPTED [ '/api/auth/status', '/test-write' ] recoveries 1
```

这违反设计规定的预检结构异常 fail-closed，以及原 `id/username` 绑定。正常服务端响应并不会主动构造上述异常，但兼容性或响应异常场景是已明确要求的验收项。

要求：先完整校验分支结构、用户 ID/用户名和 Token，再执行恢复或发送。异常结构必须业务发送次数为 0；用户名不一致按账号不一致处理。

### F6 — P2：人行上传第二次请求的账号不一致未进入注销流程

位置：`src/auto_check/web/app.js:13071`。

触发：首次 XHR 返回带 required 的 401 → 原账号恢复成功 → 重试 XHR 返回带 account-mismatch 的 409。

实际：内层 catch 只处理第二次 required 401，将专用 409 当普通上传错误抛出，未调用 `discardUnexpectedSession()`。服务端仍会阻止错误账号下的业务执行，但前端未完成要求的意外会话清理。

隔离运行输出：

```text
UPLOAD_RETRY_ACCOUNT_MISMATCH {"requests":2,"discardCalls":0,"error":"upload failed: 409","authRecovery":"account-mismatch"}
```

要求：首次和重试响应共享同样的账号不一致处理；不进行第三次上传。

### F7 — P1：附件元数据查询将当前与历史文件正文一起加载

位置：`src/auto_check/modules/report_special_processing/storage.py:546`、`:643`。

实际：`_list_record_attachments_with_connection()` 和 `_hydrate_record_attachment_audits()` 使用 `select(RECORD_ATTACHMENTS)` 读取全部列，包括 `content LONGBLOB`，之后在 `_record_attachment_metadata()` 中才丢弃正文。SQLAlchemy 查询列检查结果为 `METADATA_SELECT_INCLUDES_CONTENT True`。

影响：普通详情读取当前附件元数据时就可能从数据库加载最多 30 MiB 正文；更新前置读取重复加载。修改记录的一页可包含多次更新的旧、新附件，历史集合不受“当前最多 30 MiB”限制，单次审计查询可能加载远超当前附件上限的正文，放大网络流量与进程内存占用。批量查询避免了 N+1，但没有避免读取大字段。

要求：元数据查询显式选择所需列，排除 `content`；只有用户请求文件内容的下载接口才读取正文。补充断言所生成 SELECT 不含 content 的查询测试，并用较多历史附件验证审计返回数据量。

### F8 — P2：损坏的 OOXML 内容未转换为文件校验错误

位置：`src/auto_check/modules/report_special_processing/validator.py:490`、`src/auto_check/modules/report_special_processing/api.py:128`。

触发：上传中央目录可打开，但 `[Content_Types].xml` 内容 CRC 损坏的 XLSX/DOCX。

实际：仅 ZipFile 打开阶段捕获 `BadZipFile`，`archive.read()` 阶段的同类异常逃逸至 API 通用 500。纯内存损坏 ZIP 运行结果：`OOXML_CRC_EXCEPTION BadZipFile`。

影响：坏附件被显示为服务故障，无法按字段提示用户更换文件。这发生在事务前，未发现由此导致部分保存。

要求：对容器成员读取阶段的损坏、加密或不支持压缩等预期输入错误统一转换为字段校验 400，保留整次保存失败且不写入的行为；不能把真实数据库/程序异常全部伪装为 400。

## 3. 补充契约与测试缺口

- `auth_recovery.js:409` 的 `destroy()` 只清空状态，没有 reject 等待者或解绑已注册事件。隔离运行得到 `DESTROY_WAITING_PROMISE pending listeners 1`；现有名为 `test_destroy_cleans_password_and_listeners` 的测试仅断言密码清空和 isRecovering=false，并未验证监听器/等待者。
- `app.js:1692` 将调用方 headers 当普通对象展开，传入原生 `Headers` 时会丢失自定义头；隔离运行传入 `X-Custom: keep`，最终请求头读取结果为 null。应使用 `new Headers()` 构建并补默认值，补充 Headers 和 tuple-array 两种输入测试。
- `validator.py:431` 在严格 Base64 解码前剥离空白并自动补 padding，非规范输入因此被接受；隔离运行 `_decode_attachment_base64('Y Q', ...)` 得到 `b'a'`。这是低优先级契约偏差，应遵守设计的严格编码校验，并补非法编码用例。
- 附件仓储现有新增测试主要检查表声明、函数签名和源码字符串；服务层测试使用模拟 storage。需要补充真实仓储执行及失败回滚证据，不能以这些测试代替数据库事务原子性验收。

其他审查结论：新增 006 迁移、模块版本 1.2.13/schema 6 与设计一致，旧迁移未被本次修改。下载路径执行详情权限校验并绑定 record_id/attachment_id，历史已移除附件可读取。事务代码静态审查未发现可证实的半提交缺陷，但缺少实际数据库回滚测试证据。OOXML 当前按已确认设计实施 ZIP/目录标识浅校验；它不构成完整 Office 文档有效性或恶意软件检测，未将增加完整主部件解析列为此次必须修复的新要求。

## 4. 修复后复验要求

1. 先为 F1–F8 添加能够在当前实现上失败的回归测试，再修复实现；状态机测试必须覆盖迟到回调和多请求交错。
2. 增加父页面与抽屉组合测试，不能只测附件组件或检查源码注释。
3. 对新增附件迁移、记录/附件/审计事务和失败回滚补充真实数据库或等价受控测试证据；使用独立测试数据库，不操作业务数据。
4. 重新运行定向和全量测试，检查 diff，并完成真实浏览器的超时带附件保存、版本冲突保留、历史新旧附件查看/下载验收。
5. 本报告不代表已授权打包、部署、提交或推送。

本次验收仅新增本报告，未修改业务源码、配置、数据库或设计文档。
