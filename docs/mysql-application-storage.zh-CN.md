# MySQL 应用存储说明

本文说明 Auto Check 当前版本的应用自身数据存储方式、上线准备、界面偏好表规范、旧 SQLite 离线导出和验收口径。

## 一、当前架构

当前版本使用 MySQL 应用库 `auto_check` 保存系统自身配置、用户、认证数据、执行历史、报送导航配置/快照和界面偏好。DWS 数据源和报表数据源仍由页面配置维护，继续支持 PostgreSQL 或 MySQL，不属于本应用库。完整应用结构为 39 张表，`app_schema_version` 仍为 `1`。

运行时只读取现有 `config.json` 中的 `app_database` 启动连接信息。动态配置、用户、自动对数历史、人行逐笔校验历史和流程链执行历史不再写回 JSON 或 SQLite。

界面偏好分为两层：

- `user_interface_preferences` 按每个用户保存圆角和折线图风格；两个可空的个人主题色字段仅作为历史结构兼容字段保留，当前版本不开放写入入口。
- `system_interface_preferences` 作为独立兼容表保留系统级主题色及审计信息，默认值为 `#3466D9` 和 `#355F63`；当前前端不读取该表，也不提供自定义主题色入口。
- `user_interface_preferences` 中的两个个人主题色字段不属于当前界面能力，当前前端不解析也不应用这些字段，且不得据此提供自定义主题色入口。
- 系统主题色绝不使用 `app_settings` 保存；不得把主题色字段、默认值或管理接口迁回该旧逻辑。
- 当前界面仅保留亮色活力主题，固定使用 Logo 蓝渐变 `#3466D9` 到 `#6AA4FF`，不提供自定义主题色或渐变开关；沉稳主题和暗色模式入口已移除。空心按钮、可点击文字和身份标签使用纯蓝文字/边框，不使用渐变；悬浮反馈不使用主题光晕，仅保留主题色描边和轻微位移。登录页强制使用浅色布局，只有页面背景使用其自身的浅蓝到少量浅橙渐变，并沿用用户最近一次成功登录保存的圆角。

本地数据查询页面及入口已隐藏，不再提供 SQLite 查询、导出、备份或旧历史迁移入口，也不新增 MySQL 管理查询页面。

## 二、上线与升级顺序

1. 手工创建 MySQL 数据库 `auto_check`。
2. 执行 `sql/app_storage/mysql/001_init_schema.sql` 创建 20 张应用存储表。
3. 如需迁移旧数据，停机备份后运行 `scripts/export_sqlite_to_mysql.py` 只读导出旧 SQLite 数据 SQL 和迁移报告。
4. 由运维人员人工检查并执行数据 SQL，不在应用启动时自动迁移。
5. 执行 `sql/app_storage/mysql/002_report_navigation.sql` 新增 17 张报送导航表。
6. 执行 `sql/app_storage/mysql/003_report_navigation_seed.sql` 写入报送导航种子配置。
7. 执行 `sql/app_storage/mysql/004_user_interface_preferences.sql` 新增第 36 张 `user_interface_preferences` 表。
8. 执行 `sql/app_storage/mysql/005_user_appearance_preferences.sql`，为用户偏好表增加折线图风格、两个可空个人主题色及检查约束。
9. 执行 `sql/app_storage/mysql/006_system_interface_preferences.sql` 新增第 39 张 `system_interface_preferences` 表。
10. 执行 `sql/app_storage/mysql/007_report_navigation_schedule_owner.sql`，为月度报送日程补充负责人字段。
11. 执行 `sql/app_storage/mysql/008_report_navigation_work_calendar.sql`，创建或更新法定节假日与调休工作日日历。
12. 执行 `sql/app_storage/mysql/009_report_navigation_manual_step_permissions.sql`，规范报送步骤人工确认开关。
13. 配置 `config.json` 的 `app_database` 节点。
14. 启动应用并确认连接、结构版本和关键表数据。

建表/升级脚本不包含 `CREATE DATABASE`、`DROP`、`TRUNCATE`、生产凭据或业务数据。`004`、`006` 和 `008` 使用 `CREATE TABLE IF NOT EXISTS`；`005` 与 `007` 通过 `information_schema` 判断字段或约束是否存在后再升级。六个脚本可按顺序重复执行，不会重复建表、重复加列或删除现有数据；`008` 会幂等写入年度法定节假日和调休工作日配置，`009` 会将当前可人工确认范围规范为“资管产品模板、逐笔报送”第七步。如果目标表已经存在，仍需人工核对字段和约束是否符合当前规范。

`user_interface_preferences` 不设置外键；用户删除后，孤儿偏好由应用在用户数据变更事务中清理。`006` 只创建表，不预插入 `id=1` 记录；当前前端不依赖该记录，后端兼容接口在记录不存在时使用代码默认色，并在显式调用保存接口时原子 upsert 唯一记录。

从已完成 `001`、`002`、`003` 的版本升级时，应先停机和备份，在升级应用前依次执行随发布提供的 `004_user_interface_preferences.sql`、`005_user_appearance_preferences.sql`、`006_system_interface_preferences.sql`、`007_report_navigation_schedule_owner.sql`、`008_report_navigation_work_calendar.sql`、`009_report_navigation_manual_step_permissions.sql`，再部署新程序。本文仅说明初始化和升级步骤，不代表已在任何线上环境执行。

## 三、界面偏好完整规范 DDL

以下为执行 `004`、`005` 后 `user_interface_preferences` 的最终完整规范。实际升级必须使用上节列出的守卫脚本，不要直接用本节语句覆盖现有表。

```sql
CREATE TABLE `user_interface_preferences` (
  `user_id` VARCHAR(64) NOT NULL COMMENT '用户 ID',
  `radius_px` TINYINT UNSIGNED NOT NULL DEFAULT 4 COMMENT '界面圆角像素值，范围 1 至 15',
  `line_chart_style` VARCHAR(16) NOT NULL DEFAULT 'straight' COMMENT '折线图风格：straight 直线折线，smooth 平滑曲线',
  `vitality_theme_color` CHAR(7) NULL COMMENT '预留个人活力主题色，格式 #RRGGBB',
  `calm_theme_color` CHAR(7) NULL COMMENT '预留个人沉稳主题色，格式 #RRGGBB',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`user_id`),
  CONSTRAINT `chk_user_interface_radius_px` CHECK (`radius_px` BETWEEN 1 AND 15),
  CONSTRAINT `chk_user_interface_line_chart_style` CHECK (`line_chart_style` IN ('straight', 'smooth')),
  CONSTRAINT `chk_user_interface_vitality_theme_color` CHECK (`vitality_theme_color` IS NULL OR REGEXP_LIKE(`vitality_theme_color`, '^#[0-9A-F]{6}$', 'c')),
  CONSTRAINT `chk_user_interface_calm_theme_color` CHECK (`calm_theme_color` IS NULL OR REGEXP_LIKE(`calm_theme_color`, '^#[0-9A-F]{6}$', 'c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户界面偏好表：保存每个用户的界面圆角设置。';
```

以下为 `system_interface_preferences` 的最终完整规范：

```sql
CREATE TABLE `system_interface_preferences` (
  `id` TINYINT UNSIGNED NOT NULL COMMENT '固定主键，仅允许 1',
  `vitality_theme_color` CHAR(7) NOT NULL DEFAULT '#3466D9' COMMENT '系统活力主题色，格式 #RRGGBB',
  `calm_theme_color` CHAR(7) NOT NULL DEFAULT '#355F63' COMMENT '系统沉稳主题色，格式 #RRGGBB',
  `updated_by` VARCHAR(64) NULL COMMENT '最后修改管理员用户 ID',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_system_interface_preferences_singleton` CHECK (`id` = 1),
  CONSTRAINT `chk_system_interface_vitality_theme_color` CHECK (REGEXP_LIKE(`vitality_theme_color`, '^#[0-9A-F]{6}$', 'c')),
  CONSTRAINT `chk_system_interface_calm_theme_color` CHECK (REGEXP_LIKE(`calm_theme_color`, '^#[0-9A-F]{6}$', 'c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='系统界面偏好表：保留全局主题色兼容配置。';
```

数据约束和运行规则：

- `radius_px` 仅允许 `1`–`15`，默认 `4`。
- `line_chart_style` 仅允许 `straight` 或 `smooth`，默认 `straight`。
- 主题色只接受完整六位 `#RRGGBB`。接口允许输入小写，但持久化前统一转为大写；数据库约束只接受大写。
- 两个个人主题色允许 `NULL`，仅作为历史结构兼容字段保留；本版本的圆角/折线保存不得覆盖已有兼容值，前端也不得读取或应用它们。
- 系统表只允许 `id=1`；兼容默认色为 `#3466D9`、`#355F63`，同时记录 `updated_by` 和 `updated_at`。
- 当前“系统设置→界面设置”只维护用户圆角和折线图风格：圆角范围为 `1`–`15`、默认 `4`，折线默认使用 `straight` 直线样式；不展示主题色输入、主题切换或渐变开关。固定 Logo 蓝渐变由前端样式令牌统一提供。

## 四、配置示例

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

### 离线导出

旧 SQLite 导出命令示例：

```powershell
python scripts\export_sqlite_to_mysql.py `
  --source "D:\path\auto-check.db" `
  --database auto_check `
  --schema-output "D:\output\auto_check_mysql_schema.sql" `
  --data-output "D:\output\auto_check_mysql_data.sql" `
  --report-output "D:\output\auto_check_mysql_migration_report.json"
```

导出器只读打开 SQLite，不连接 MySQL。数据 SQL 会包含加密后的数据源密码和用户密码哈希，应按敏感生产数据处理；控制台只输出汇总，不输出行内容。导出后的升级顺序仍为 `004_user_interface_preferences.sql`、`005_user_appearance_preferences.sql`、`006_system_interface_preferences.sql`、`007_report_navigation_schedule_owner.sql`、`008_report_navigation_work_calendar.sql`、`009_report_navigation_manual_step_permissions.sql`。

## 五、验收口径

上线连接 MySQL 后，需要分别确认旧数据迁移结果和当前完整表结构。至少确认：

- `app_schema_version` 当前版本为 `1`。
- 当前完整 39 张应用存储表结构齐全，且已按顺序应用 `004_user_interface_preferences.sql`、`005_user_appearance_preferences.sql`、`006_system_interface_preferences.sql`、`007_report_navigation_schedule_owner.sql`、`008_report_navigation_work_calendar.sql`、`009_report_navigation_manual_step_permissions.sql`。
- `user_interface_preferences` 包含圆角、折线图风格和两个可空个人主题色；主键、默认值、范围/枚举/HEX 检查约束符合本节完整 DDL，现有行数在结构升级前后保持一致。
- `system_interface_preferences` 包含唯一行约束、两个兼容色默认值/HEX 约束、最后修改人和更新时间；允许零行，不应出现 `id<>1` 或多余记录。
- 界面设置中不存在自定义主题色或渐变开关；兼容主题色也不写入 `app_settings`。
- 迁移报告中 SQLite `integrity_check` 为 `ok`，外键异常数为 `0`。
- 原 20 张迁移目标表的数据行数与迁移报告一致，并确认 `total_exported_rows` 与运维执行后的 MySQL 行数抽查结果相符。
- 数据源、用户、自动对数历史、人行逐笔校验历史和流程链历史都能从 MySQL 正常读取。
- 删除旧 SQLite `auto-check.db` 后应用仍应只依赖 MySQL 应用库运行。

## 六、回滚

回滚程序前先备份 MySQL 应用库。旧版本程序不会识别新增界面偏好字段/表，但本次 `004`–`006` 不改写原 20 张迁移目标表数据，也不自动删除新增结构；需要数据库级回滚时由运维根据备份和变更窗口单独执行，不得由应用启动过程自动回退。

如同时回滚到旧 SQLite 架构，应恢复旧版本程序、旧 `config.json`、旧 `auto-check.db` 和相关旧 JSON 文件。新版本不会在运行时自动回退到 SQLite 或 JSON，也不会自动从旧 SQLite 迁移数据。
