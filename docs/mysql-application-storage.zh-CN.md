# MySQL 应用存储说明

本文说明 Auto Check 当前版本的应用自身数据存储方式、上线准备、旧 SQLite 离线导出和验收口径。

## 一、当前架构

当前版本使用 MySQL 应用库 `auto_check` 保存系统自身配置、用户、认证数据、执行历史、报送导航配置/快照和用户界面偏好。DWS 数据源和报表数据源仍由页面配置维护，继续支持 PostgreSQL 或 MySQL，不属于本应用库。完整应用结构为 36 张表，`app_schema_version` 仍为 `1`。

运行时只读取现有 `config.json` 中的 `app_database` 启动连接信息。动态配置、用户、自动对数历史、人行逐笔校验历史和流程链执行历史不再写回 JSON 或 SQLite。

本地数据查询页面及入口已隐藏，不再提供 SQLite 查询、导出、备份或旧历史迁移入口，也不新增 MySQL 管理查询页面。

## 二、上线顺序

1. 手工创建 MySQL 数据库 `auto_check`。
2. 执行 `sql/app_storage/mysql/001_init_schema.sql` 创建 20 张应用存储表。
3. 如需迁移旧数据，停机备份后运行 `scripts/export_sqlite_to_mysql.py` 只读导出旧 SQLite 数据 SQL 和迁移报告。
4. 由运维人员人工检查并执行数据 SQL，不在应用启动时自动迁移。
5. 执行 `sql/app_storage/mysql/002_report_navigation.sql` 新增 15 张报送导航表。
6. 执行 `sql/app_storage/mysql/003_report_navigation_seed.sql` 写入报送导航种子配置。
7. 执行 `sql/app_storage/mysql/004_user_interface_preferences.sql` 新增第 36 张 `user_interface_preferences` 表。
8. 配置 `config.json` 的 `app_database` 节点。
9. 启动应用并确认连接、结构版本和关键表数据。

建表脚本不包含 `CREATE DATABASE`、`DROP`、`TRUNCATE`、生产数据或凭据。

`user_interface_preferences` 按每个用户独立保存界面圆角偏好，不设置外键；用户删除后，孤儿偏好由应用在用户数据变更事务中清理。`004_user_interface_preferences.sql` 使用 `CREATE TABLE IF NOT EXISTS`，可重复执行且不会重复建表或删除现有数据；如果目标表已经存在，仍需人工核对字段和约束是否符合当前脚本。

从已完成 `001`、`002`、`003` 的版本升级时，应先停机备份，在升级应用前执行随发布提供的 `004_user_interface_preferences.sql`，再部署新程序。本文仅说明初始化和升级步骤，不代表已在任何线上环境执行。

## 三、配置示例

```json
{
  "app_database": {
    "backend": "mysql",
    "host": "127.0.0.1",
    "port": 3306,
    "database": "auto_check",
    "username": "auto_check_app",
    "password": "<set-by-operations>",
    "charset": "utf8mb4",
    "connect_timeout": 10,
    "pool_size": 5,
    "pool_max_overflow": 5
  }
}
```

`AUTO_CHECK_SECRET_KEY` 必须与旧环境保持一致，否则旧数据源加密密码可能无法解密。不要把真实 MySQL 密码、生产数据 SQL 或生产 SQLite 文件提交到 Git。

## 四、离线导出

旧 SQLite 导出命令示例：

```powershell
python scripts\export_sqlite_to_mysql.py `
  --source "D:\path\auto-check.db" `
  --database auto_check `
  --schema-output "D:\output\auto_check_mysql_schema.sql" `
  --data-output "D:\output\auto_check_mysql_data.sql" `
  --report-output "D:\output\auto_check_mysql_migration_report.json"
```

导出器只读打开 SQLite，不连接 MySQL。数据 SQL 会包含加密后的数据源密码和用户密码哈希，应按敏感生产数据处理；控制台只输出汇总，不输出行内容。

## 五、验收口径

上线连接 MySQL 后，需要分别确认旧数据迁移结果和当前完整表结构。至少确认：

- `app_schema_version` 当前版本为 `1`。
- 当前完整 36 张应用存储表结构（含 `004_user_interface_preferences.sql`）齐全，关键字段完整，且 `user_interface_preferences` 的主键、默认值和范围约束符合脚本定义。
- 迁移报告中 SQLite `integrity_check` 为 `ok`，外键异常数为 `0`。
- 原 20 张迁移目标表的数据行数与迁移报告一致，并确认 `total_exported_rows` 与运维执行后的 MySQL 行数抽查结果相符。
- 数据源、用户、自动对数历史、人行逐笔校验历史和流程链历史都能从 MySQL 正常读取。
- 删除旧 SQLite `auto-check.db` 后应用仍应只依赖 MySQL 应用库运行。

## 六、回滚

回滚时恢复旧版本程序、旧 `config.json`、旧 `auto-check.db` 和相关旧 JSON 文件。新版本不会在运行时自动回退到 SQLite 或 JSON，也不会自动从旧 SQLite 迁移数据。
