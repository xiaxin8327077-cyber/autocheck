# 监管智核

监管智核（Auto Check）用于监管报表自动对数、人行产品导入与逐笔校验、报送流程跟踪和报表特殊处理。生产环境以 Linux 单文件程序提供 Web 服务，用户通过浏览器访问；Windows 源码环境用于本地开发。

[快速开始](#本地开发) · [部署与升级](#部署与升级) · [文档导航](#文档导航) · [最新变更](#最新变更说明)

## 版本信息

| 项目 | 当前说明 |
| --- | --- |
| 界面版本 | **V1.3**；Python 包版本 `0.1.0` |
| 规则版本 | `logic-2026-06-12-v1` |
| 源码运行环境 | Python **3.12 及以上**，常规开发使用 3.12 |
| 生产交付 | Linux x86_64 单文件 `dist-glibc217/auto-check`，兼容 glibc 2.17 及以上 |
| 默认端口 | `8765` |
| 应用存储 | MySQL 应用库；`config.json` 保存启动连接信息，动态配置与历史记录存入应用库 |
| 业务数据源 | DWS、报表数据源均支持 PostgreSQL / MySQL |
| 使用范围 | 桌面端浏览器，建议窗口宽度不低于 `900px` |

业务报表库使用只读连接；导入、执行工具等功能按各自明确授权的流程执行。应用自身的用户、配置、台账和历史记录写入 MySQL 应用库。

## 当前功能

| 功能 | 用途与说明入口 |
| --- | --- |
| 报送导航 | 查看报送日程、流程进度、待办和完成情况 |
| 自动对数 | 识别资产、负债权益、实收本金等差异，查看原因、历史和 Excel 导出；见 [执行流程](docs/reconcile-execution-flow.zh-CN.md) |
| 人行产品导入 | 上传文件、字段映射、开始导入、完成四步流程 |
| 人行逐笔校验 | 表结构与字段规则校验、结果和历史查询；规则文档可在应用内查看 |
| 报表特殊处理 | 记录字段修改、关联报送、确认与审计，按筛选导出台账；见 [模块说明](src/auto_check/modules/report_special_processing/README.md) |
| 流程执行工具 | 维护执行流程链、后台执行及进度提示；见 [后台执行设计](docs/flow-bg-execution-design.zh-CN.md) |
| 看板管理 | 看板配置、年度趋势快照、页面预览及外部只读接口；见 [模块说明](src/auto_check/modules/dashboard_management/README.md) |
| 系统管理 | 用户与角色权限、字典、定时任务、数据源和系统设置 |

界面仅保留统一亮色主题；个人偏好支持全局圆角及折线图风格。功能权限由角色能力配置控制。

## 本地开发

以下命令在仓库根目录使用 PowerShell 7 执行。先确认 `python --version` 为 3.12 或以上；其他系统使用对应的虚拟环境 Python 路径。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

启动前完成 [MySQL 应用库初始化](docs/mysql-application-storage.zh-CN.md)，并准备包含有效 `app_database` 连接信息的配置文件。已有环境应继续使用原配置和 `AUTO_CHECK_SECRET_KEY`，避免旧数据源密码无法解密。

```powershell
# 使用已经配置好的应用库；不要求重新创建配置
.\.venv\Scripts\python.exe -m auto_check --host 0.0.0.0 --port 8765 --no-browser

# 如需指定配置文件，将路径替换为自己的实际配置
.\.venv\Scripts\python.exe -m auto_check --config "C:/path/to/config.json" --host 0.0.0.0 --port 8765 --no-browser
```

访问 `http://127.0.0.1:8765/`；局域网访问使用本机实际 IP。配置也可通过 `AUTO_CHECK_CONFIG` 指定。源码服务没有自动热重载，后端代码修改后需要重启。

需要执行测试时：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

本地测试 SQL 和辅助脚本分别位于 [sql/](sql/) 与 [scripts/](scripts/)，执行造数前确认目标为测试环境。

## 部署与升级

- **应用库准备**：先备份，再按 [MySQL 应用存储说明](docs/mysql-application-storage.zh-CN.md) 执行适用迁移。模块业务表由各模块的独立迁移与 `schema_version` 管理。
- **Linux 生产部署**：标准交付文件为 `dist-glibc217/auto-check`，通过 systemd 管理服务；安装、配置、升级和回滚步骤见 [内网生产部署](docs/intranet-production-deployment.zh-CN.md)。
- **打包与交付**：按明确的提交版本打包，保留提交号、SHA256 和验证结果。构建不等于部署，不自动重启运行中的服务。
- **Windows 可选交付**：仅在需要可执行程序时运行 `pwsh -NoLogo -NoProfile -File scripts/package-windows.ps1`，产物为 `dist/auto-check.exe`；日常源码修改不自动打包。

业务数据源与应用库是两类连接：前者服务于对数、校验等业务，后者保存系统自身数据。不要用测试配置覆盖已有应用库配置。

## 文档导航

| 要查什么 | 文档 |
| --- | --- |
| 数据库初始化、迁移和旧数据处理 | [MySQL 应用存储](docs/mysql-application-storage.zh-CN.md) |
| 服务安装、升级、备份和回滚 | [内网生产部署](docs/intranet-production-deployment.zh-CN.md) · [跨平台部署参考](docs/deployment.zh-CN.md) |
| 当前对数流程与规则 | [执行流程](docs/reconcile-execution-flow.zh-CN.md) · [规则说明](docs/reconcile-rules.zh-CN.md) · [规则历史](docs/reconcile-logic-history.zh-CN.md) |
| 核对历史与差异对比 | [历史记录设计](docs/check-history-design.zh-CN.md) |
| 特殊处理的录入、关联报送和导出 | [模块使用说明](src/auto_check/modules/report_special_processing/README.md) · [设计说明](docs/report-special-processing-module.zh-CN.md) |
| 看板与外部接口 | [模块说明](src/auto_check/modules/dashboard_management/README.md) · [外部 API](docs/dashboard-management-external-api.zh-CN.md) |
| 新模块开发与边界约束 | [模块开发指南](docs/module-development-guide.zh-CN.md) · [模块化规则](docs/ai-modular-development-rules.zh-CN.md) |
| 原型页面及局域网预览 | [报送工作台原型](docs/prototypes/regulatory-reporting-workbench/README.md) |

## 目录说明

```text
src/auto_check/app/            Web 服务、平台配置、数据访问与历史记录
src/auto_check/engine/         对数规则、金额比较与匹配模型
src/auto_check/db_validation/  人行逐笔校验引擎与规则资源
src/auto_check/modules/        独立业务模块及各自前后端、迁移
src/auto_check/web/            主应用前端资源
src/auto_check/resources/      内置资源数据
tests/                        后端、前端结构与模块测试
scripts/                      开发、测试辅助和打包脚本
sql/                          应用库迁移及本地测试 SQL
config/                       配置样例
docs/                         业务、开发与运维文档
docs/prototypes/              独立原型，不属于正式应用入口
```

## 最新变更说明

后续按“版本 / 日期 + 主要更新”维护简约记录。已有详细说明与历次更新完整保存在 [历史记录](docs/project-history.zh-CN.md)。

### `v1.3.0` (2026-09-21)

- 报表特殊处理支持字典扩展关联报送，优化统计标签和 Excel 导出。
