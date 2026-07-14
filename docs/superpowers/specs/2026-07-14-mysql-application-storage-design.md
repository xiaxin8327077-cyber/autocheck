# MySQL 应用自身存储设计

## 目标

Auto Check 运行时彻底停止使用 SQLite 保存自身数据，改为单实例连接 MySQL 数据库 `auto_check`。数据库结构和生产数据由运维人员在发布前手工执行 SQL 完成，应用只连接、校验和读写，不执行建库、建表、升级或 SQLite 数据迁移。

现有 DWS 与报表数据源继续支持 PostgreSQL 和 MySQL。本设计只限制“应用自身数据库”为 MySQL。

## 已确认边界

- 单个 Auto Check 服务实例供全部用户访问。
- MySQL 连接配置放入现有 `config.json` 的 `app_database` 节点。
- 继续沿用现有 `--config` 与 `AUTO_CHECK_CONFIG`，不新增启动参数。
- MySQL 数据库 `auto_check` 已由生产运维创建。
- 应用启动时不执行任何 DDL，也不自动迁移 SQLite。
- 提供由运维手工执行的建表 SQL 和 SQLite 转 MySQL 离线导出脚本。
- “本地数据查询/应用数据库查询”页面整体隐藏，不再显示入口，也不在前端自动请求相关接口。
- 不采用运行时双写；MySQL 是新版本唯一真源。

## 启动配置

`config.json` 增加只读启动配置：

```json
{
  "app_database": {
    "backend": "mysql",
    "host": "10.0.0.21",
    "port": 3306,
    "database": "auto_check",
    "username": "auto_check_app",
    "password": "******",
    "charset": "utf8mb4",
    "connect_timeout": 10,
    "pool_size": 5,
    "pool_max_overflow": 5,
    "ssl": false
  }
}
```

动态系统设置、用户、业务数据源和运行历史不再写回 `config.json`。旧动态节点只作为人工迁移来源保留，MySQL 切换完成后运行时忽略它们。

## 启动顺序与失败行为

1. 读取 `config.json` 中的 `app_database`。
2. 校验 `backend=mysql`、主机、端口、库名和账号。
3. 使用 SQLAlchemy Core 与 PyMySQL 创建连接池。
4. 执行 `SELECT 1`。
5. 只读检查 `app_schema_version` 最新版本等于程序要求版本。
6. 只读检查 19 张业务表及关键字段存在。
7. 初始化配置、认证和历史仓储后启动 HTTP 服务。

配置缺失、连接失败、版本不符或表结构不完整时直接拒绝启动，错误信息必须指出具体原因。应用不得创建 `auto-check.db`，也不得回退 JSON 或 SQLite。

## 代码结构

- `src/auto_check/app/app_database.py`：启动配置、SQLAlchemy Engine、连接池、事务和只读结构校验。
- `src/auto_check/app/storage_config.py`：MySQL 配置、设置和用户仓储。
- `src/auto_check/app/storage_history.py`：MySQL 三类结构化历史仓储。
- `src/auto_check/app/config.py`：以 MySQL 为唯一动态配置真源。
- `src/auto_check/app/security.py`：以 MySQL `users` 表为用户真源，保留现有密码规则与 AES-GCM 数据源密码能力。
- `src/auto_check/app/history.py`：使用数据库历史仓储替换 `SqliteHistoryStore`。
- `src/auto_check/app/server.py`：应用启动时创建并注入共享 `ApplicationDatabase`。
- `src/auto_check/app/local_store.py`：退出运行主链路；仅旧数据离线导出脚本允许读取 SQLite。
- `sql/app_storage/mysql/001_init_schema.sql`：人工执行的通用 MySQL V1 结构脚本，含中文表说明和字段注释。
- `scripts/export_sqlite_to_mysql.py`：离线生成 INSERT SQL 和校验报告，应用不调用。

## 数据模型

目标库包含 19 张业务/审计表及 `app_schema_version`：

- 配置和用户：`data_sources`、`app_settings`、`users`、`config_snapshots`
- 历史公共：`run_headers`
- 自动对数：`reconcile_runs`、`reconcile_run_counts`、`reconcile_results`、`reconcile_result_details`、`reconcile_delta_results`
- 人行逐笔：`db_validation_runs`、`db_validation_selected_tables`、`db_validation_warnings`、`db_validation_result_rows`
- 流程执行：`flow_chain_runs`、`flow_chain_run_steps`、`flow_chain_run_logs`、`flow_chain_run_details`
- 迁移审计：`storage_migration_runs`

不创建 `app_kv`、`history_runs`、SQLite `schema_migrations` 或 `sqlite_sequence`。

字段规范：

- 日期：`DATE`
- 日期时间：`DATETIME(6)`
- 仅时间：`TIME(6)`
- 金额：`DECIMAL(38,12)`
- JSON：MySQL `JSON`
- 布尔：`TINYINT(1)`
- 自增明细主键：`BIGINT AUTO_INCREMENT`
- 字符集/排序规则：`utf8mb4` / `utf8mb4_unicode_ci`

生产 SQLite 已验证可无损转换：金额最高 12 位小数；空的完成时间、基准时间和最后登录时间转换为 `NULL`。

## 事务与并发

连接池启用 `pool_pre_ping`，默认 `pool_size=5`、`pool_max_overflow=5`、`pool_recycle=1800`。每次配置保存、用户变更或完整历史保存使用独立事务。

保存运行历史时，运行头、类型运行表及全部子明细在同一事务内完成；任何一步失败整体回滚。首期只支持单应用实例，不承诺会话共享、任务租约或横向扩容。

## 页面与接口

前端隐藏“本地数据查询”导航、页面和相关自动加载逻辑。SQLite 健康、文件备份和旧历史迁移按钮不再可见。

为减少无关改动，后端原存储管理接口可以保留兼容路由但不再由前端调用；接口不得访问 SQLite，可返回功能已停用的明确响应。后续若重新开放 MySQL 管理页，需要单独设计权限和查询范围。

## 人工迁移与回滚

发布顺序：

1. 停止旧版应用写入。
2. 备份旧程序、`auto-check.db`、`config.json` 和 `AUTO_CHECK_SECRET_KEY`。
3. 人工执行通用建表 SQL。
4. 人工执行生产 INSERT SQL。
5. 核对表记录数、外键和 `app_schema_version`。
6. 在 `config.json` 写入 `app_database`。
7. 启动新版并完成登录、配置、三类历史和业务流程冒烟测试。

回滚时停止新版，恢复旧程序、旧 `auto-check.db` 和旧配置。新旧版本之间不做数据回灌或双写。

## 测试与交付

- 为应用数据库配置、连接失败、结构版本和缺表缺字段增加单元测试。
- 配置、用户和三类历史仓储使用 MySQL 方言测试；具备 MySQL 环境时执行真实集成测试。
- SQLite 仅保留为离线导出脚本的输入夹具。
- 更新服务端和前端静态测试，确认页面入口隐藏且不再发起存储管理请求。
- 更新 README、应用内更新日志、部署文档、核对历史和流程执行设计文档。
- 运行全量测试、`git diff --check`，随后重新打包 `dist/auto-check.exe`。

## 验收标准

- `src/auto_check/app` 运行链路不再导入或连接 SQLite。
- 缺少 MySQL 配置、连接失败或结构版本不匹配时应用拒绝启动。
- 登录、用户管理、系统设置和数据源配置重启后保持一致。
- 自动对数、人行逐笔和流程执行历史的列表、详情、删除与导出行为保持兼容。
- 前端不显示“本地数据查询/应用数据库查询”入口。
- 应用启动和普通请求不会执行 DDL。
- 全量测试通过，Windows 可执行文件成功刷新。
