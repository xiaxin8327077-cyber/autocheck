# 登录超时续操作与报表特殊处理记录附件开发提示词

将下面内容完整复制给负责开发的 AI：

---

请在 `D:\xiaxin\auto_check` 仓库中直接实施以下两个已确认需求：

1. 登录超时后，原账号只输入密码重新认证，并自动继续一次被前置鉴权拒绝的原操作。
2. 报表特殊处理记录支持粘贴或上传图片、Excel、Word、ZIP 附件，附件修改进入操作记录并可查看修改前后的附件。

开始修改前必须完整阅读并遵守：

1. `AGENTS.md`
2. `docs/ai-modular-development-rules.zh-CN.md`
3. `docs/superpowers/specs/2026-09-04-session-expiry-reauthentication-design.md`
4. `docs/superpowers/plans/2026-09-04-session-expiry-reauthentication.md`
5. `docs/superpowers/specs/2026-09-04-report-special-processing-record-attachments-design.md`
6. `docs/superpowers/plans/2026-09-04-report-special-processing-record-attachments.md`

两套设计已经由用户确认，不要再次询问是否采用全屏重新认证遮罩、数据库附件存储或既定附件限制。必须采用测试驱动开发，严格执行计划中的失败测试、最小实现、通过测试和最终验证。不得把需求缩减为临时补丁。

## 推荐实施顺序

1. 记录修改前的 `git status --short` 基线。
2. 完成登录恢复计划 Tasks 1–7，先建立专用 401 协议、raw API 和统一恢复能力。
3. 完成记录附件计划 Tasks 1–9，复用已经建立的 raw API 和登录恢复能力。
4. 合并执行登录恢复 Task 8 与附件 Task 10，只生成一个一致的 `v1.2.23` 更新日志和 README 版本块。
5. 运行所有直接测试、全量 pytest、diff 检查和人工验收。

## 登录超时恢复必须达到

- 用户在“报表特殊处理录入”新建或编辑抽屉填写内容后，会话无感过期。
- 点击保存时页面不跳转，抽屉、文本和未保存附件保持原样。
- 显示不可通过背景或 Esc 关闭的全屏遮罩；固定显示原用户名，用户名不可编辑，只输入密码。
- 错误密码后继续停留并保留原操作；正确密码后自动重试一次原请求。
- 保存最终只创建或修改一次，不产生重复记录、重复附件或重复审计。
- 多个并发前置认证 401 共享一个恢复 Promise 和一个遮罩。
- 上传、下载、后台轮询和通知会话按登录恢复设计接入；后台任务继续使用原 job_id。
- 未提交状态只存在当前标签页，刷新、关闭或重启后不恢复。

认证协议必须严格遵守：

- 后端仅在全局会话前置校验 `session is None` 时返回 `X-Auto-Check-Auth-Recovery: required`。
- 登录失败、模块业务 401 和其他非前置 401 不带该响应头。
- 前端只有同时收到 401 和该响应头时才重新认证并自动重试；无标识业务 401 不得重放。
- 每个请求最多重试一次；400、403、普通无认证标识的 409、422、500 和网络错误不触发认证处理或重试。只有带 `account-mismatch` 标识的 409 由平台进入 `discarding`、注销意外会话且不重试业务请求。
- JSON 重试保留 `Content-Type: application/json`、`credentials: "same-origin"`、调用方非认证请求头和完全相同的字符串 body，每次重新读取最新 CSRF Token。
- 通用恢复不重放 ReadableStream 等一次性 body；人行 XHR 按设计保留 File/FormData 并单独重建。
- `responseType: "raw"` 先由平台消费带 `required` 的 401 和带 `account-mismatch` 的 409，再返回最终原始 Response；无认证标识的错误仍由调用模块按原语义处理。
- 平台 API 支持并剥离 `authPreflight: true`：发送大 JSON body 前以 `cache: "no-store"` 和 same-origin credentials 检查 `/api/auth/status`，服务端状态响应也设置 `Cache-Control: private, no-store`。未认证则先恢复；同一用户但 Token 不同时先 applySession，同 Token 直接继续；其他用户调用 `discardUnexpectedSession(statusPayload)` 且不发送业务请求。
- 状态预检非 2xx、异常 JSON、字段缺失或网络失败必须 fail closed，业务 body 发送次数为 0。
- authPreflight 后仍保留专用 401 处理，覆盖状态检查与业务请求之间的过期竞态。
- 所有平台 fetch 和专用 XHR 业务请求都添加 `X-Auto-Check-Expected-User-Id`。后端在 session 成功后、CSRF 与业务路由前原子比较；不一致时处理器不执行，返回 409、`X-Auto-Check-Auth-Recovery: account-mismatch` 及当前会话 user/csrf payload，前端注销退出且不重试业务。缺少该头仅为兼容现有调用保留。
- `authenticate({username,password})` 成功返回 `{csrf_token,user}`，`applySession` 完成前不能释放等待请求。
- 身份不一致或 applySession 失败时，停止通知并清空局部认证、角色、权限和用户界面状态，再用新 CSRF Token 注销。
- 注销失败进入 `discarding`：禁用密码和重新登录按钮，将退出按钮改为“重试退出”；注销成功后才能去普通登录页。

后端安全测试必须证明：

- 失效会话的前置 401 有专用响应头，并且模块写处理器调用次数为 0。
- 登录密码错误 401 无专用响应头。
- 有效会话下普通非模块 router 返回的业务 401 无专用响应头。
- 预期用户与实际 session 不一致时返回 account-mismatch，写处理器调用次数为 0；相同或缺少预期头时保持正常兼容行为。
- `/api/auth/status` 响应具有 private,no-store 缓存控制。

## 记录附件必须达到

- 新建、保存草稿和编辑抽屉具有“附件（选填）”区域。
- 支持点击上传多选和剪贴板粘贴；只有剪贴板含文件时拦截 paste，纯文字粘贴不受影响。
- 支持 PNG/JPEG/WebP、XLS/XLSX、DOC/DOCX、ZIP。
- 当前每条最多 10 个、单个最多 10 MiB、原始字节总计最多 30 MiB。
- 图片提供缩略图和大图预览；Excel、Word、ZIP 只下载，不在线执行或渲染。
- 同一当前集合中相同 SHA-256 拒绝；同名不同内容允许。
- 新文件以 Base64 随记录 JSON 原子提交，保留附件只提交 ID；不使用临时目录、分片上传或新平台文件协议。
- create/update payload 只要包含 `record_attachments`，调用 `context.api` 时必须设置 `authPreflight: true`，避免最多约 40 MiB 的 Base64 body 在已过期会话上先发送；模块不得自行请求登录接口。
- POST/PUT 模块路由上限为 45 MiB；平台 50 MiB 硬上限和其他路由原上限不变。
- 附件内容和元数据不可覆盖；从当前集合移除时设置 removed 信息但保留字节，记录整体删除时才物理清理。
- 只修改附件也递增 row_version 并写 update 审计。
- 审计保存 old/new/added/removed IDs，查询时批量补全元数据，不能产生 N+1。
- 操作记录用“修改前 / 修改后”双栏完整展示附件，标签按该条审计的 old/new ID 集合计算，不能按当前 removed_at 推断历史状态。
- 当前与历史附件下载都必须校验详情权限和 record_id 归属；跨记录使用统一 not found，不泄露存在性。
- 现有确认说明图片附件继续使用原表和原流程，最多 3 张的行为不变。

附件 API 省略语义必须精确：

- 新建省略 `record_attachments` 等同无附件。
- 修改省略该字段表示附件不变。
- 一旦提供，必须同时显式提供 `retained_ids` 和 `new_files` 两个数组。
- `{retained_ids: [], new_files: []}` 表示清空当前附件。
- 空对象、缺少数组、重复 retained ID、跨记录或历史已移除 ID 返回 400，并回滚整次保存。

旧 `.xls/.doc` 只校验 OLE 容器，服务端 MIME 保存为 `application/x-ole-storage`，扩展名仅用于允许列表、名称和图标。明确保持设计中的已知限制：不提供恶意软件扫描，不在服务端执行附件；显式宏格式 XLSM/DOCM 拒绝。

## 模块化与界面边界

- 登录恢复是平台能力，允许修改其计划列出的平台文件和 `server.py` 的单点认证响应头。
- 附件是 `report_special_processing` 模块能力，数据库、验证、服务、API 和界面都留在该模块。
- 不把附件业务规则写入 `app.js`、`auth_recovery.js`、`server.py` 或其他模块。
- 不新增菜单、能力码、权限矩阵、依赖、数据库外文件存储或主题开关。
- 仅使用现有亮色活力主题、全局圆角和语义色；空心上传按钮不用渐变，删除附件用危险红色，不使用主题光晕。
- 登录恢复自身不修改模块 manifest；附件功能必须把模块版本从 `1.2.12` 升至 `1.2.13`，schema version 从 5 升至 6。这个附件版本变更优先于登录计划中的模块 manifest 限制。

## 文档与版本

- 顶栏和系统信息继续显示 `V1.2`，不得提升大版本。
- 应用内只新增一个 `v1.2.23` 条目；明确列出登录恢复功能，并保留最多一条“系统优化及BUG修复”。
- 附件功能通过模块 `release_notes` 并入该版本，模块条目只写具体功能，不写通用 BUG 修复。
- 根 `README.md` 的 v1.2.23 详细记录两个需求。
- 同步模块 README、`docs/report-special-processing-module.zh-CN.md`、相关静态测试和打包迁移清单。
- `index.html` 中 styles.css、auth_recovery.js、app.js 的缓存参数统一为 `20260904a`。

## 验证要求

- 按两份计划逐项运行直接测试，不得在没有实际输出时宣称通过。
- 测试和验证优先交给 `gpt-5.6-luna` high 子代理，主会话检查真实结果并处理失败。
- 最后运行：

```powershell
python -m pytest -q
git diff --check
git status --short
```

- 将最终 git 状态与开发前基线比较，只审计本次需求引入的差异，不清理用户已有无关修改。
- 人工完成两份设计中的关键场景，尤其验证“带附件保存时会话过期，原账号重登后只保存一次”和“附件修改前后历史均可读取”。

## 交付限制

- 本次不要运行 Windows 打包脚本，不要刷新 `dist/auto-check.exe`。
- 未经用户明确要求，不要提交、推送、创建 PR 或修改远端。
- 完成后按“代码、数据库迁移、界面行为、文档版本、测试结果、未执行事项”汇报。

请直接开始实施。只有当专用 401 的前置安全不变量不成立、45 MiB JSON 无法在现有 50 MiB 平台上限内工作、数据库事务无法保证附件和审计一致，或必须扩大到计划外的平台/数据库范围时，才停止并向用户说明。

---
