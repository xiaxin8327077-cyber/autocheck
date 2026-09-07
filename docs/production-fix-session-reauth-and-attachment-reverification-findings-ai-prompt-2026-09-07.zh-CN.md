# 登录恢复与记录附件剩余问题修复提示词

将下面内容完整复制给新接手的开发 AI：

---

请在 `D:\xiaxin\auto_check` 仓库中直接修复“登录超时续操作与报表特殊处理记录附件”第二轮复验遗留的 3 个问题。你是新接手的 AI，之前的开发上下文不在你的会话中；请先理解下面的项目状态，不要重做已经完成的功能，也不要清理当前工作区。

## 一、项目概况

Auto Check（对外名称“监管智核”）是本地 Windows Web 应用：

- 后端主要为 Python，本地 HTTP 服务位于 `src/auto_check/app/`。
- 前端为 `src/auto_check/web/` 下的静态 HTML/CSS/JavaScript。
- 普通业务功能采用独立模块，报表特殊处理模块位于 `src/auto_check/modules/report_special_processing/`。
- 应用自身数据使用 MySQL；报表特殊处理模块拥有独立迁移和 `schema_version`。
- 当前展示大版本保持 `V1.2`，本批功能已经写入应用更新日志 `v1.2.23`。
- 报表特殊处理模块已经升级为 `version=1.2.13`、`schema_version=6`，新增迁移 `006_record_attachments.sql`。

当前 Git HEAD 为 `682049d`，工作区包含前一个 AI 尚未提交的完整功能实现、测试、设计文档和验收报告。所有已有修改及未跟踪文件都属于本需求成果或用户工作区，必须原地增量修复：

- 不得执行 `git reset --hard`、`git checkout --` 或其他回退、覆盖操作。
- 不得删除、重建或整体替换现有实现。
- 开始前记录 `git status --short`，只修改本提示词允许的文件。
- 不升级 `V1.2`、`v1.2.23`、模块 `1.2.13` 或 `schema_version=6`。
- 本次不打包，不刷新 `dist/auto-check.exe`，不提交、不推送、不创建 PR。

## 二、必须完整阅读的文件

修改前依次完整阅读：

1. `AGENTS.md`
2. `docs/ai-modular-development-rules.zh-CN.md`
3. `docs/superpowers/specs/2026-09-04-session-expiry-reauthentication-design.md`
4. `docs/superpowers/plans/2026-09-04-session-expiry-reauthentication.md`
5. `docs/superpowers/specs/2026-09-04-report-special-processing-record-attachments-design.md`
6. `docs/superpowers/plans/2026-09-04-report-special-processing-record-attachments.md`
7. `docs/session-reauth-and-record-attachments-verification-2026-09-07.zh-CN.md`
8. `docs/session-reauth-and-record-attachments-reverification-2026-09-07.zh-CN.md`

两份设计已经由用户确认。本轮只处理第二轮复验报告中的 R1–R3，不扩大需求，不重新设计附件存储、登录遮罩、权限、版本或页面样式。

## 三、当前已经完成且不得破坏的行为

- 登录超时后保留当前页面和表单，遮罩固定原用户名，只输入密码。
- 正确密码后使用新 CSRF Token 自动重试原请求一次；无专用标识的业务错误不重放。
- `account-mismatch` 在业务路由前阻断，错误账号不得接管原页面。
- 大附件 JSON 在发送前执行 `authPreflight`；异常状态 fail closed。
- 版本冲突保留抽屉、字段和待保存附件，只有用户点击“加载最新记录”才刷新。
- 并发恢复、并发注销、迟到登录结果、`destroy()` 等已有回归测试。
- 附件支持图片、Excel、Word、ZIP 的粘贴和上传；限制为每条 10 个、单个 10 MiB、总计 30 MiB。
- 附件保存与记录、审计在同一事务中；历史记录可查看修改前后附件。
- Base64 已改为严格解码；损坏 OOXML 已映射为字段校验错误。
- 详情和审计的附件元数据查询已经排除 `content LONGBLOB`。

修复前的最近验证结果为：

- 定向测试：`264 passed, 5 skipped in 59.60s`。
- 全量测试：`1692 passed, 7 skipped in 141.47s`。
- 其中 5 项因未配置真实 MySQL 测试库而跳过，2 项因当前环境不能创建目录符号链接而跳过。
- 自动化测试没有失败，但独立复验仍确认下面 3 个问题。

## 四、必须修复的 3 个问题

### Task 1：迟到登录会话注销失败必须保持阻塞并可重试

主要文件：

- `src/auto_check/web/auth_recovery.js`
- `src/auto_check/web/app.js`
- `tests/test_auth_recovery_frontend.py`

当前问题：用户已经提交重新认证，在登录响应未返回时点击“退出系统”。如果迟到的登录响应成功建立了新会话，`discardLateSession()` 会调用 `discardSession(payload)`；但当前在 `terminal` 状态下采用 fire-and-forget，并通过空 `catch` 吞掉注销失败。遮罩已经隐藏、页面已经跳转登录页，用户没有“重试退出”入口；登录页可能再次识别到刚建立的有效会话。

先增加能在当前代码上失败的测试，至少覆盖：

1. 重新认证请求在途时点击退出，暂时不得跳转登录页。
2. 在途认证失败且没有建立会话时，才完成退出。
3. 在途认证成功时，不得调用 `applySession`，必须用响应中的 CSRF Token 注销新会话。
4. 注销失败时保持不透明遮罩、密码和重新登录按钮禁用、退出按钮显示“重试退出”，`isRecovering()` 为 true。
5. 点击“重试退出”且注销成功后，才调用 `exitSession()` 并取消所有等待者。
6. 同一迟到结果不得重复应用、重复退出或并行注销。
7. `applySession` 已在途时点击退出，也执行同样的安全收口。
8. 如果 `destroy()` 可能发生在认证请求在途期间，不得静默吞掉已经建立会话的注销失败；应使清理结果可观察或阻止不安全拆卸，并保持既有调用方兼容。

推荐状态流：用户点击退出时先让当前认证尝试失效并进入受控退出等待态，不立即导航；等待认证请求确定结果。未建立会话则退出，已建立会话则进入现有 `discarding` 流程；只有注销成功才跳转，注销失败继续提供“重试退出”。不能把 AbortController 或 `location.href` 当作“服务端一定没有建立会话”的证明。

不要恢复被取消的原业务请求，不得保存密码，不得允许其他账号接管页面。

### Task 2：附件修改事务查询必须排除正文大字段

主要文件：

- `src/auto_check/modules/report_special_processing/storage.py`
- `tests/modules/report_special_processing/test_storage.py`
- `tests/modules/report_special_processing/test_storage_real_mysql.py`

当前问题：详情和审计查询已经使用 `RECORD_ATTACHMENT_METADATA_COLUMNS` 排除 `content`，但 `_apply_record_attachment_change()` 仍执行 `select(RECORD_ATTACHMENTS)`。该方法只需要当前附件 ID，却会把当前附件正文一起读取，附件修改时可能无谓加载最多 30 MiB。

先增加失败测试，再进行最小修复：

1. `_apply_record_attachment_change()` 只选择实际需要的列，优先仅选择 `RECORD_ATTACHMENTS.c.id`；保留当前排序和 ID 校验语义。
2. 单元测试直接检查该方法生成的 SELECT 不包含正文列，不能只检查列表和审计方法。
3. SQL 断言要区分精确的 `content` 列与 `content_type`、`content_sha256`，不要用会产生误报的简单子串判断。
4. 真实 MySQL 测试必须在执行 `storage.update()` 前清空 SQL 捕获列表，然后断言整个附件更新路径没有查询正文列。
5. 保持下载路径仍能按需读取 `content`；不得破坏当前附件、历史附件和审计元数据返回。

### Task 3：重写真实 MySQL 测试库安全门控

主要文件：

- `tests/modules/report_special_processing/test_storage_real_mysql.py`
- 必要时同步模块测试说明；不要把凭据或真实 DSN 写入文档、日志或提交内容。

当前测试 fixture 会直接删除 DSN 中指定的数据库。它只校验库名是小写标识符且不等于精确的 `auto_check`；如果误写成 `mysql`、`sys`、`auto_check_prod` 或其他业务库，测试仍会执行 `DROP DATABASE`。

必须先修好安全门控，之后才能设置 `AUTO_CHECK_IT_MYSQL_DSN`：

1. 永远不要把 DSN 自带的数据库名直接作为 DROP 目标。
2. 在测试代码内部生成本轮唯一库名，例如 `auto_check_it_rsp_<pid>_<random>`；随机部分使用安全、受控字符。
3. 创建和清理前都再次断言名称严格匹配固定测试前缀及完整正则；拒绝 MySQL 系统库、`auto_check` 及所有非测试前缀名称。
4. 默认只允许明确的测试主机范围，至少本机回环地址；若未来需要远程测试实例，必须由独立显式配置开放，不能从普通 DSN 自动推断授权。
5. 只创建、迁移和删除本轮内部生成的 scratch 库；fixture 不删除任何预先存在的 DSN 数据库。
6. 使用 `try/finally` 清理；清理目标必须是本轮保存的精确随机库名，不能从后来变化的环境变量重新计算。
7. 测试输出只允许显示脱敏主机和生成的测试库名，不输出用户名、密码或完整 DSN。
8. 为门控本身增加不连接数据库的单元测试，证明 `mysql`、`sys`、`information_schema`、`performance_schema`、`auto_check`、`auto_check_prod` 和任意非测试名称都不可能成为 DROP 目标。

修复代码时不要自行设置、猜测或读取业务库凭据，不要连接、迁移或删除现有 `auto_check` 应用库。若当前环境没有明确隔离的测试 MySQL，真实 MySQL 测试继续安全 skip，并在交付结果中说明未执行。

## 五、真实 MySQL 测试覆盖需要补齐

现有 5 项门控测试覆盖部分真实事务场景。本轮同时补充或完善以下用例：

- stale `row_version` 冲突不留下附件软删除、新附件或审计。
- 插入新附件失败时，主记录更新、旧附件软删除、新附件和审计全部回滚。
- 删除记录时清理当前及历史记录附件。
- 历史软删除附件仍可按 record_id 和 attachment_id 读取。
- 整个 update 元数据查询路径不读取 `content`。

这些测试必须使用内部生成的独立 scratch 库。没有安全测试实例时允许跳过，但不得把 skip 说成真库事务已通过。

## 六、边界要求

- 登录恢复是已批准的平台能力，可以修改本 Task 1 列出的平台文件，但不得加入报表特殊处理业务规则。
- Task 2 和 Task 3 留在报表特殊处理模块及其测试范围内。
- 不修改现有迁移 `001`–`006`，不新增数据库业务表或迁移版本。
- 不新增依赖，不修改能力码、权限矩阵、菜单、主题或附件限制。
- 不增加新版本号或第二个 `v1.2.23` 更新日志块。
- 不修改两份验收报告来掩盖旧结果；它们是历史验证证据。
- 保留用户已有无关改动，禁止顺手格式化或重构大文件。

## 七、实施与验证方式

严格使用测试驱动方式：每个 Task 先写能够在当前实现上失败的精确测试，运行并确认失败原因，再做最小修改并运行通过。不要只写源码字符串断言；状态机使用真实 Promise 交错，仓储查询检查实际生成 SQL，事务使用安全 scratch MySQL。

建议依次运行：

```powershell
python -m pytest -q tests/test_auth_recovery_frontend.py -k "late or discard or exit or destroy"
python -m pytest -q tests/modules/report_special_processing/test_storage.py tests/modules/report_special_processing/test_validator_and_permissions.py
python -m pytest -q tests/modules/report_special_processing/test_record_attachments_frontend.py
python -m pytest -q tests/test_auth_recovery_frontend.py tests/modules/report_special_processing/ tests/module_system/test_server_integration.py tests/notifications/test_frontend_static.py
python -m pytest -q
git diff --check
git status --short
```

只有 Task 3 的安全门控和门控单元测试先通过、并且当前环境已有明确隔离的 MySQL 测试实例时，才允许设置测试 DSN 并运行：

```powershell
python -m pytest -q tests/modules/report_special_processing/test_storage_real_mysql.py
```

测试和验证可清晰拆分时，按项目约定优先交给 `gpt-5.6-luna` high 子代理运行，主会话必须检查真实输出。不得在没有输出时宣称通过。

## 八、交付要求

完成后报告：

1. R1、R2、R3 分别修改了什么以及为什么。
2. 新增或调整了哪些测试，先失败的证据和修复后的结果。
3. 定向测试与全量测试的通过、失败、跳过数量和耗时。
4. 真实 MySQL 测试是否实际执行；未执行时明确说明原因。
5. `git diff --check` 和最终 `git status --short`。
6. 明确说明未打包、未提交、未推送。

请直接开始，不要再次询问用户是否修复这 3 项。只有发现必须修改现有数据库迁移、扩大到计划外模块、需要真实业务库权限，或无法在保持同账号安全边界的情况下修复，才停止并说明具体阻塞。

---
