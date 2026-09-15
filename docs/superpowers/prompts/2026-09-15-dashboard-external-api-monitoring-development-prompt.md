# AutoCheck 看板外部接口监控开发提示词

你现在接手 AutoCheck 的“看板外部接口监控”开发。请直接在当前主会话完成，不要使用 DSH、子代理或后台代理。

## 工作区与边界

- 工作目录：`D:\xiaxin\auto_check`
- 当前分支：`feature/auto-check`
- 只修改 AutoCheck，不得修改 `D:\xiaxin\kanban` 的任何文件或数据。
- 当前工作区已有大量尚未提交的看板管理和外部接口改动，必须保留；不要执行 reset、checkout、stash 或任何会覆盖现有改动的操作。
- 不要修改以下无关用户改动：
  - `docs/prototypes/regulatory-reporting-workbench/package.json`
  - `docs/prototypes/regulatory-reporting-workbench/src/SchedulingManagement.jsx`
  - `docs/prototypes/regulatory-reporting-workbench/vite.config.mjs`
  - `.dumate/`
  - `.zcode/`
  - `docs/prototypes/regulatory-reporting-workbench/` 下未跟踪脚本和测试
- 本次不要打包 `dist\auto-check.exe`，不要提交、不要推送。

## 开始前必须完成

1. 执行 `git status --short` 和 `git diff --stat`，确认当前真实状态。
2. 完整阅读仓库 `AGENTS.md`。
3. 完整阅读以下文件；长文档必须分段读到 EOF：
   - `docs/ai-modular-development-rules.zh-CN.md`
   - `docs/superpowers/specs/2026-07-31-modular-extension-architecture-design.md`
   - `docs/superpowers/plans/2026-07-31-modular-extension-host-implementation.md`
   - `docs/superpowers/specs/2026-09-15-external-readonly-dashboard-api-design.md`
   - `docs/superpowers/specs/2026-09-15-dashboard-external-api-monitoring-design.md`
   - `docs/superpowers/plans/2026-09-15-dashboard-external-api-monitoring-implementation.md`
4. 先检查当前外部接口实现和测试，不要重新实现或回退已经完成的部分。

## 要实现的结果

在“系统管理 → 看板管理”中增加“接口监控”入口和独立子页面：

- 展示外部接口是否启用、Token 是否已配置、两个固定接口地址、最近调用和最近成功时间。
- 展示近 24 小时调用、成功、部分成功、失败、平均耗时。
- 展示认证通过且命中看板预览路由后的逐次调用记录，字段包括调用时间、完整调用方 IP、看板、HTTP 状态、业务状态、失败区域数、耗时、request_id、错误摘要。
- 调用方 IP 必须取 TCP 对端地址，规范化 IPv4/IPv6；忽略可伪造的 `X-Forwarded-For` 和 `Forwarded`。
- 只记录认证通过并命中看板预览路由的 200、认证后 404 和处理器 500；401、503、错误方法、未命中路由和内部预览不记录。
- 记录滚动保留 30 天，写入和查看时清理过期记录。
- 不保存或展示 Token、Token 摘要、Authorization、SQL、数据源配置或响应数据。
- 监控页必须有清晰的“返回看板管理”按钮；返回后恢复进入前的当前看板、区域、未保存草稿、测试状态、预览结果和可恢复的滚动位置，不触发放弃修改确认。
- 增加 `dashboard_management.external_api_monitor` / `sys.dashboard_management.external_api_monitor`，默认仅管理员开启，前端入口和后端 API 双重鉴权。

## 页面显示规范

不要只实现功能，必须逐项满足实施计划中的 `Page Display and Interaction Acceptance Specification`。重点包括：

- 入口位于看板管理顶部标题/Tabs 栏右侧，使用空心次要按钮，不新增全局菜单或弹窗。
- 监控页纵向 flex 满高，整页只有一个与现有看板管理/角色权限管理同源的 `.dm-management-card` 外框；内部严格按“标题栏 → 状态区 → 五项统计条 → 筛选栏 → 表格 → 底部分页”排列，表格区占满剩余高度并独立滚动。
- 内部区域只用现有分隔线组织，不得拆成漂浮卡片、卡片瀑布或多套边框；复用 `--ui-radius`、`--outline-variant`、`--surface-container-lowest` 等系统变量。
- 状态区、五个指标、五项筛选和九列调用记录必须完整。
- 表格列顺序：调用时间、调用方 IP、看板、HTTP 状态、业务状态、失败区域数、耗时、request_id、错误摘要。
- success/partial/error 使用成功/警告/危险语义色，同时显示文字，不能只靠颜色。
- IP 和 request_id 使用等宽字体并支持复制；错误摘要安全截断并可通过 title 查看。
- 分页必须复用 `.pagination`、`.pagination-info`、`.pagination-controls`、`.page-btn`、`.page-current`、`.pagination-jump`，空数据和单页也始终显示。
- 有数据文案“共 N 条，第 P / T 页”，空数据“暂无数据”，空数据当前页为“-”。筛选变化、查询、清除回第一页，前后翻页、跳页和越界收敛正确。
- 有明确的加载、空数据、失败重试状态；失败时保留筛选，不能伪装为空数据。
- 桌面宽度下五项统计等宽等高、文字基线一致；标题栏、筛选控件、表头/行高、状态标签、按钮尺寸和间距直接对齐“系统管理 / 角色权限”现有实现，不另建页面密度。
- 文本列左对齐，HTTP 状态、业务状态、失败区域数和耗时居中；同一行的文字、标签和复制按钮垂直居中，不能高低错位。
- 窄窗口下统计项和筛选自适应换行，表格自身横向滚动，整页不横向溢出；响应式只改变排列，不改变内容顺序和视觉语言。
- 只保留当前亮色活力主题；Logo 蓝渐变仅用于实心主操作，返回/筛选/复制等次要按钮使用纯色；禁止主题光晕和自建圆角体系。
- 禁止巨型圆角、彩色投影、玻璃拟态、悬浮卡片、胶囊式导航、超大指标数字和新的独立图标语言；页面必须看起来就是现有系统管理页的一部分，不能特立独行。
- 所有按钮 `type="button"`，分页按钮有 `aria-label`。

## 架构约束

- 平台层增加通用 `ModuleRequest.client_ip`，不能让看板模块读取 `BaseHTTPRequestHandler` 或平台内部对象。
- Token 读取提取为单一函数；认证入口和 `platform.external_api_status` v1 共用。状态服务只返回 `token_configured: bool`。
- 看板模块拥有 `dashboard_management_external_api_calls` 表、schema v3、仓储、统计、分页和监控页面；server.py 不得出现 board_code 或看板业务判断。
- 内部 API：
  - `GET /api/modules/dashboard-management/external-api/monitor/summary`
  - `GET /api/modules/dashboard-management/external-api/monitor/calls`
- calls 支持 `page`、`page_size`、`board_code`、`result_status`、`caller_ip`、`started_at`、`ended_at`；默认 10、最大 100、按 `called_at DESC, id DESC`。
- 写调用记录失败不能改变外部看板响应，只记服务端异常；监控查询失败返回安全错误。

## 实施方式

- 严格按 `docs/superpowers/plans/2026-09-15-dashboard-external-api-monitoring-implementation.md` 的 Task 1 到 Task 10 顺序执行。
- 每个任务先写失败测试，运行并确认预期失败，再用 `apply_patch` 写最小实现，再运行目标测试。
- 搜索使用 `rg`；PowerShell 使用 `pwsh -NoLogo -NoProfile`。
- 不进行无关重构，不改动现有外部接口响应格式、固定区域和字段契约。
- 可在计划复选框中记录进度，但不要创建 git commit。

## 最终验证

必须运行：

```powershell
python -m pytest -q
git diff --check
git status --short
```

全部测试通过后，安全识别并只重启明确属于 `D:\xiaxin\auto_check` 的 8765 源码开发进程。验证：

- 8765 正常监听；
- 无 Token 401；
- 错误 Token 401；
- 隔离短时进程下未配置 Token 503；
- 正确 Token 调用两个固定看板均为 200；
- 正确调用产生两条带真实 TCP 对端 IP 的记录，401/503 不产生记录；
- summary 统计更新；
- 页面权限、状态卡、指标、筛选、表格、复制、分页、响应式、错误/空状态符合规范；
- 从监控页返回后看板、区域和未保存草稿完整恢复。

最终回复要明确列出：代码改动、配置/文档改动、行为变化、实际测试结果、开发环境实测结果，以及确认未打包、未提交、未推送。不得只说“已经完成”。
