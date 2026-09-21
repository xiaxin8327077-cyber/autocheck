# AGENTS.md

适用于整个仓库；用户明确指示优先于默认工作流。

## 项目与目录

监管智核（Auto Check）提供自动对数、人行全量产品导入、逐笔校验及报送相关功能。生产环境为 Linux Web 服务，Windows 用于源码开发及可选程序交付。应用库使用 MySQL；DWS、报表业务数据源均支持 PostgreSQL / MySQL。

- `src/auto_check/app/`：Web、配置、数据访问、历史、流程工具、PBC 导入、安全与仓储查询。
- `src/auto_check/engine/`：规则、金额与匹配（`reconcile.py`、`matching.py`、`money.py`）。
- `src/auto_check/db_validation/`：逐笔规则、规则文档、Excel、DDL 与元数据。
- `src/auto_check/modules/`：独立模块；`src/auto_check/web/`：页面、样式、导出与加密兜底；`src/auto_check/resources/`：内置资源。
- `tests/`：后端和前端结构测试；`scripts/`：测试辅助及打包；`sql/`：迁移、测试 DDL 与造数；`config/`：配置样例；`docs/`：文档。
- `docs/prototypes/`：独立原型和设计预览，不属于正式产物。

## 开发与协作

- 沿用既有风格和结构，不做无关重构、不回退已有改动；搜索优先 `rg`。
- 默认在当前目录、当前分支开发；未经用户明确指示，不得创建隔离分支、Git worktree 或其他隔离检出。技能/流程的默认建议不构成授权。
- 非小范围明确改动先写方案并获认可；小而明确的改动直接执行，不重复确认已授权事项，但仍检查上下文与结果。
- 业务模块改动前完整阅读 `docs/ai-modular-development-rules.zh-CN.md`；业务代码不得进入公共入口、平台内核或其他模块，平台协议缺口单独提案评审。
- 测试、验证或可拆分任务可委派子代理，主会话协调、复核和修正；多轮无回复影响推进时可接手并说明原因。委派提示和模型选择遵循全局规则。
- 完成后说明代码、配置/文档及行为变化，如实交代验证范围。
- PowerShell 优先 `pwsh`（7），确需 5.1 兼容时才用 `powershell.exe` 并说明原因。

## 界面统一规范

- 仅亮色活力主题，不恢复沉稳主题、暗色或切换入口。图标、按钮形态、背景统一遵循 Logo 蓝（`#3466D9` → `#6AA4FF`）及语义色，不提供自定义主题色/渐变开关。
- 卡片、弹窗、按钮、输入、选择、日期、标签、图标容器等复用全局圆角（`--ui-radius`）和主题变量，不硬编码另一套；用户明确要求特殊视觉时例外。
- 系统所有页面及独立模块的结构性背景必须共用统一表面层级：页面 `--ui-page-surface`；主卡片/面板/弹窗主体 `--ui-panel-surface`；内嵌/筛选/只读分组/次级内容 `--ui-subsection-surface`；禁用输入 `--ui-disabled-surface`；中性边框 `--ui-content-border`。模块限自身作用域引用，不另建近似白/灰/浅蓝结构背景；状态色、选中态、图表色和代码预览等语义或专用画布可例外，须限定组件或状态。
- 所有弹窗禁止点击遮罩层或背景空白处关闭，使用关闭/取消/确认/完成按钮，可按交互保留 `Esc`；改动弹窗须补遮罩点击不关闭的回归测试。
- 页面/列表/弹窗滚动条与“报送导航”一致：细条、透明轨道、全圆角滑块，复用 `--ui-thin-scrollbar-size` / `--ui-thin-scrollbar-thumb`，不用默认粗条；同时覆盖 Firefox `scrollbar-width` / `scrollbar-color` 与 WebKit `::-webkit-scrollbar`。
- 渐变仅用于实心主操作等强调表面；空心按钮、可点击纯文字、角色及“我”等身份标签用纯主题色文字/边框和必要浅色背景，禁止渐变或透明文字效果，确保图文清晰。
- 卡片/面板/按钮悬浮不加主题光晕，只用纯主题色描边、轻微位移及必要中性阴影；管理列表内部布局不得悬浮位移。
- 操作颜色守语义：主操作主题色，删除/停止红色，警告、成功、中性/次要各用其色。公共主题、按钮、链接、表单选择器须限定范围，避免覆盖用户管理操作、筛选项及弹窗的原有语义。

## 后台管理列表页统一规范

- 以“系统管理 / 角色权限”为基准，字典、定时任务、用户及后续列表不得另设计样式。标题、筛选、清除/主按钮沿用既有结构尺寸；表头、行高、状态、操作间距及语义色一致。
- 纵向 flex 占满内容区，列表卡片 `flex: 1`、`min-height: 0`，表格滚动区填满剩余空间；数据不足由背景自然撑满，禁止伪造空白行。
- 边框、背景、表头、分隔线、圆角、文字复用全局变量（`--outline-variant`、`--surface-container-lowest`、`--surface`、`--ui-radius` 等），不硬编码近似值。
- 标题与内容共用一个外框，`border-radius: var(--ui-radius)`、`overflow: hidden` 裁切四角；悬浮描边用主题色与 `--outline-variant` 混合纯色，不加光晕、不移动内部布局。
- 分页复用 `.pagination`、`.pagination-info`、`.pagination-controls`、`.page-btn`、`.page-current`、`.pagination-jump` 和公共样式；不得为新页面另建分页样式。
- 分页固定卡片底部，空数据/单页也可见。左侧“共 N 条，第 P / T 页”，空数据“暂无数据”；右侧依次上一页、当前页、下一页、“跳至”输入框；当前页仅 P，空数据“-”。
- 筛选、清除或页容量变化回第一页；越界收敛；页容量复用系统/既有配置，不另设无依据固定值。
- 须补前端结构/行为测试，覆盖满高、公共分页类、空数据/单页可见、文案、前后翻页、跳页及筛选回第一页。

## 业务与权限

- 人行全量导入保持“上传文件、字段映射、开始导入、完成”四步；上传、解析、映射、导入改动同步后端与前端静态测试。
- 自动对数核心、仓储查询、差异类型/具体原因展示或导出改动，同步 `docs/reconcile-execution-flow.zh-CN.md`。
- 逐笔规则、DDL、字段映射、Excel 或元数据改动，同步 `src/auto_check/db_validation/rules_document.py`、`tests/test_db_validation_*.py`，确认“对账业务设置/业务字段清单”与逻辑一致。
- 流程工具、流程链、后台执行、浮动提示改动，参照 `docs/flow-bg-execution-design.zh-CN.md` 并同步测试。
- 新密码至少 6 位且含 1 个字母，适用初始化管理员、新建用户、管理员修改/重置密码；不改变已有密码及登录校验。
- 新增/修改菜单或入口、默认新增按钮/操作接口，在 `src/auto_check/app/capabilities.py` 注册能力码并补全角色默认矩阵；前端用 `data-capability` / `hasCapability()`，后端用 `has_capability()` 或会话 `capabilities` 鉴权。用户明确要求不接权限分配时，在方案中确认并保留单一入口控制。

## 版本与更新记录

- 正式应用可见 UI、版本号或日志改动，同步 `README.md`、`src/auto_check/web/app.js` 系统日志及相关测试；用户明确指定某处不更新时例外。独立原型、纯文档整理记在各自文档，不作为正式功能发布。
- **两处都保持简约**：按版本/日期列主要更新，不展开字段、样式、操作步骤或实现细节。
- **README**：简述关键功能、优化和修复；原有精细内容完整保存在 `docs/project-history.zh-CN.md`。后续更新维护在 README，不要求向历史文件追加精细记录。
- **系统日志**（`app.js` 及模块 `release_notes`）：只含正式项目功能相关更新，可与 README 的功能摘要一致；不得包含项目文档、原型图/原型演示、开发流程或打包操作。简述主要新功能；布局、美化、体验优化、问题修复合并概述，通用“系统优化及BUG修复”每版本最多一条。用户指定某版本的确切文案时严格按指定内容。
- 展示大版本（如 `V1.3`）与日志小版本（如 `v1.3.0`）分开；跨大版本必须经用户明确授权，不得自行推进。
- 模块更新按 `release_notes.version` 并入同号系统版本，旧版本内容不得灌入最新版本；无对应版本则不展示。不单设“模块更新”块或模块版本号。展示格式“XX模块：具体内容”，清单项只写内容，不重复写模块前缀；名称取 `manifest.name`，末尾无“模块”则补上；同版本不重复，模块 `release_notes` 只列自身功能，不再写通用修复条。

## 验证、打包与 Git

- 代码改动默认运行 `python -m pytest -q`；用户明确要求本次不运行时遵从并说明，保留必要静态检查，不声称测试通过。
- 提交前 `git diff --check`；CRLF/LF 提示通常只是换行提示，实际 whitespace error 须修复。
- 日常源码/前端修改不自动打包；仅用户明确要求打包或可执行程序交付时执行，先完成适用验证。Windows 打包前确认无运行中 `dist/auto-check.exe` 占用；使用 `pwsh -NoLogo -NoProfile -File scripts/package-windows.ps1`，可加 `-PythonPath "<path-to-python.exe>"`，产物 `dist/auto-check.exe`。Linux 标准产物 `dist-glibc217/auto-check`，按部署文档及专用打包流程操作。
- 中文提交说明，只含当前请求，不混入无关改动或 `build/` 等生成目录（用户明确要求除外）。仅要求提交时只提交当前分支；**只有明确推送或同等授权才推送**。
- 授权推送默认同时推当前分支到 GitHub `origin`、Gitee `gitee`；GitHub 优先 SSH，不擅改保存的远端 URL。GitHub 失败至少确保 Gitee 成功并如实报告；需拉取时从 Gitee `https://gitee.com/xiaxin8327077-cyber/autocheck.git` 获取。
- Gitee `fetch/pull/push/ls-remote` 用命令级 `git -c http.proxy= -c https.proxy= ...` 绕过代理，不改系统、Git 全局或其他远端代理；直连失败如实报告或尝试不持久修改的安全方式。

## 专项参考

除上文必须同步的文档外，按任务查阅：

- 规则与演进：`docs/reconcile-rules.zh-CN.md`、`docs/对账逻辑说明.md`、`docs/reconcile-logic-history.zh-CN.md`。
- 历史与导出：`docs/check-history-design.zh-CN.md`、`docs/reconcile-candidate-report-check-mapping.zh-CN.md`。
- 字段及待实施方案：`docs/business-schema-config-roadmap.zh-CN.md`、`docs/asset-missing-refinement-*.zh-CN.md`。
- 部署与存储：`docs/intranet-production-deployment.zh-CN.md`、`docs/deployment.zh-CN.md`、`docs/mysql-application-storage.zh-CN.md`。
- 项目入口及简约版本记录：`README.md`；已有详细历史：`docs/project-history.zh-CN.md`。
