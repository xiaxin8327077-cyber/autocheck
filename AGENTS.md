# AGENTS.md

## 适用范围

本文件适用于整个仓库。

## 项目概况

Auto Check（对外名称"监管智核"）是一个本地 Windows Web 应用，用于自动对数、人行全量产品导入、人行逐笔校验和相关数据核对流程。

核心目录布局：

- `src/auto_check/app/`：本地 Web 服务、配置、数据访问、历史记录、流程工具、PBC 导入、安全与仓储查询
- `src/auto_check/engine/`：自动对数规则、金额比较、匹配模型（`reconcile.py`、`matching.py`、`money.py`）
- `src/auto_check/db_validation/`：人行逐笔校验引擎，含规则、规则文档、Excel 读取、表结构 DDL 与元数据
- `src/auto_check/resources/`：内置资源数据
- `src/auto_check/web/`：前端静态资源（页面、样式、导出详情脚本、加密兜底）
- `tests/`：单元测试和前端静态结构测试
- `docs/`：中文规则说明和设计说明（详见下方"相关文档"）
- `scripts/`：本地测试辅助脚本和打包脚本
- `sql/`：本地测试库 DDL 和造数脚本
- `config/`：本地测试配置样例
- `dist\auto-check.exe`：打包产物

支持的数据源类型为 PostgreSQL 和 MySQL，界面上维护 DWS 数据源与报表数据源两类连接配置。

## 常用命令

- 运行测试：`python -m pytest -q`
- 打包 Windows 可执行文件：`powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1`
- 打包产物路径：`dist\auto-check.exe`

如果需要指定 Python 运行时：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1 -PythonPath "<path-to-python.exe>"
```

## 开发约定

- 优先沿用现有代码风格和项目结构，避免无关重构。
- 不要回退用户或工作区中已有的无关改动。
- 搜索文件或文本时优先使用 `rg`。
- 测试、验证或任务可清晰拆分时，可以自动开启子代理并行处理；主会话负责协调、检查结果和必要的后续修正。
- 子代理或后台线程多轮等待仍无回复、影响当前任务推进时，可以切回主会话直接处理或补做必要验证，并在结果说明中注明原因。
- 每次修改后都需要说明修改内容，说明应包含涉及的代码内容、配置/文档内容和行为变化。
- 前端当前仅保留亮色活力主题；新增或修改界面时不得恢复沉稳主题、暗色模式或相关切换入口。
- 各功能模块的图标、按钮形态和背景色应统一遵循固定 Logo 蓝渐变（`#3466D9` 到 `#6AA4FF`）及现有语义色规范，不提供自定义主题色或渐变开关。
- 新增功能或新增可见界面元素时，默认必须遵循系统统一的圆角和主题色规范；卡片、弹窗、按钮、输入框、选择框、日期控件、标签、图标容器等应使用现有全局圆角变量（如 `--ui-radius`）和主题色变量，不得另行硬编码一套圆角或主题色。只有用户明确提出特殊视觉要求时才允许例外。
- 主题渐变仅用于实心主操作按钮等需要突出强调的主操作表面。空心按钮、可点击纯文字、角色标签和“我”等身份标签不得使用渐变，应使用纯主题色文字/边框及必要的浅色主题背景，且必须保证文字和图标清晰可见、不得通过透明文字实现视觉效果。
- 卡片、面板和按钮的悬浮反馈不得使用主题光晕；需要反馈时仅使用纯主题色描边和轻微位移，并保留必要的中性阴影层级。
- 按钮颜色应优先遵循操作语义：主操作使用主题色，删除和停止等危险操作使用红色，警告操作使用警告色，成功操作使用成功色，中性或次要操作使用中性色；不得为了统一主题色而覆盖明确的操作语义颜色。
- 修改公共主题、按钮、链接或表单控件样式时，应限制选择器作用范围，避免通用规则覆盖用户管理操作按钮、筛选项、弹窗按钮等已有语义样式。
- 人行全量产品一键导入需要保持四步流程：上传文件、字段映射、开始导入、完成。
- 修改上传、解析、映射或导入逻辑时，需要同步更新后端测试和前端静态测试。
- 修改可见 UI、版本号或更新日志时，需要同步更新 `README.md`、`src/auto_check/web/app.js` 中的系统更新日志，以及相关测试，除非用户明确要求某一处不更新。
- `src/auto_check/web/app.js` 中系统设置的更新日志应保持精简：新增功能列出具体功能；系统界面布局、美化、体验优化、问题修复等统一写为“系统优化及BUG修复”，不要展开细节。
- `README.md` 中的版本说明仍需要保留详细变更内容，正常列出关键优化、修复和行为变化，不套用应用内更新日志的精简口径。
- 登录和用户管理的新密码规则为：至少 6 位且至少包含 1 个字母；初始化管理员密码、新建用户、管理员修改/重置用户密码都必须执行该限制，已有用户密码和登录验证不受新规则影响。
- 修改自动对数核心逻辑、对数仓储查询、差异类型/具体原因展示或导出逻辑时，必须同步更新 `docs/reconcile-execution-flow.zh-CN.md`。
- 修改人行逐笔校验引擎的规则、表结构 DDL、字段映射、Excel 读取或元数据时，需要同步更新 `src/auto_check/db_validation/rules_document.py` 中的规则文档内容，以及对应的后端测试（`tests/test_db_validation_*.py`），并确认"对账业务设置/业务字段清单"页面展示与实际逻辑一致。
- 修改流程执行工具、流程链定义、后台执行或浮动提示等逻辑时，需要参照 `docs/flow-bg-execution-design.zh-CN.md` 并同步相关测试。
- 修改代码前需要写出方案，得到认可后才能改代码。

## 相关文档

- `docs/reconcile-execution-flow.zh-CN.md`：自动对数执行流程、仓储查询、差异类型与导出逻辑的权威说明，改动对应逻辑时必须同步。
- `docs/reconcile-rules.zh-CN.md` / `docs/对账逻辑说明.md`：自动对数规则与逻辑历史说明。
- `docs/reconcile-logic-history.zh-CN.md`：自动对数逻辑演进历史。
- `docs/flow-bg-execution-design.zh-CN.md`：流程执行工具后台执行与浮动提示设计。
- `docs/check-history-design.zh-CN.md`：核对历史相关设计。
- `docs/business-schema-config-roadmap.zh-CN.md`：对账业务设置/业务字段清单路线图。
- `docs/asset-missing-refinement-*.zh-CN.md`：资产缺失细分相关设计与临时方案。
- `docs/reconcile-candidate-report-check-mapping.zh-CN.md`：候选不唯一与导出备注映射说明。
- `docs/deployment.zh-CN.md`：跨平台部署说明。
- `docs/prototypes/`：原型与设计预览（可包含 HTML 原型），不属于正式产物。
- `README.md`：对外说明与版本变更记录，修改可见 UI、版本号或更新日志时需同步。

## 验证要求

- 代码改动后运行：`python -m pytest -q`
- 影响源码或前端展示且需要交付应用时，运行打包脚本刷新 `dist\auto-check.exe`。
- 打包前先确认没有正在运行的 `dist\auto-check.exe` 占用文件。
- `git diff --check` 中的 CRLF/LF 提示通常只是换行符提示；若出现实际 whitespace error，需要修复。

## Git 约定

- 提交应聚焦当前请求，不混入无关改动。
- 不要提交 `build/` 等生成目录，除非用户明确要求。
- 用户要求提交或推送时，先完成测试和必要打包，再提交并推送当前分支。
- 用户要求推送时，默认将当前分支同时推送到 GitHub（`origin`）和 Gitee（`gitee`）；若 GitHub 连接失败，则至少确保 Gitee 推送成功。
- 当 GitHub 连接失败时，从 Gitee 拉取代码（地址：`https://gitee.com/xiaxin8327077-cyber/autocheck.git`）。
