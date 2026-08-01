# Auto Check 投产文件清单

生产环境已有运行版本，MySQL `auto_check` 已存在 20 张初始表。本次只准备升级必需文件。

## 1. 最终程序

- [ ] 从最终提交构建的 Linux x86_64 单文件可执行程序 `auto-check`
- [ ] 产物最高依赖的 GLIBC 符号不高于 `GLIBC_2.17`，可覆盖生产环境 glibc 2.28
- [ ] 已在 manylinux2014/glibc 2.17 容器内执行 `auto-check --help`
- [ ] 最终提交 SHA 和应用程序 SHA-256

使用东京打包环境的 `dist-glibc217/auto-check` 产物，不单独构建 glibc 2.28 版本。当前仓库中的 Windows `dist\auto-check.exe` 与旧 Linux 产物均不能直接用于本次投产。

## 2. 数据库升级 SQL

按以下顺序执行：

1. `002_report_navigation.sql`
2. `003_report_navigation_seed.sql`
3. `004_user_interface_preferences.sql`
4. `005_user_appearance_preferences.sql`
5. `006_system_interface_preferences.sql`
6. `007_report_navigation_schedule_owner.sql`
7. `008_report_navigation_work_calendar.sql`
8. `009_report_navigation_manual_step_permissions.sql`
9. `010_pbc_template_step_seven_display_only.sql`
10. `011_report_navigation_completion_time_sources.sql`
11. `012_module_system.sql`

注意：

- 不执行 `001_init_schema.sql`，现有 20 张表已经对应其结构。
- 不执行 `007_report_navigation_comparison_delta.sql`，`002` 已包含该字段。
- 不执行 `008_report_navigation_manual_history.sql`，`002` 已包含该表。
- 执行 `012_module_system.sql` 前必须完成生产 MySQL 备份，并由运维人工执行；应用不得自动执行该生产升级。
- 执行结束后平台应用表数量应为 42 张，`app_schema_version` 仍为 `1`；模块业务表不加入全局 `EXPECTED_APP_SCHEMA`。

## 3. 生产配置

- [ ] 当前生产 `config.json`，确认 `app_database` 指向已建立的 MySQL 库
- [ ] 保持当前生产 `AUTO_CHECK_SECRET_KEY` 不变
- [ ] 保持现有 Linux 服务、端口、启动账户和启动方式不变

真实数据库密码和密钥不得放入普通投产压缩包。

## 4. 上线前备份

- [ ] 当前正在运行的旧程序
- [ ] 当前生产 `config.json`
- [ ] MySQL `auto_check` 当前 39 张表的完整备份（执行 `012_module_system.sql` 前）
- [ ] 当前生产数据目录
- [ ] 当前生产密钥和启动参数的安全备份

## 5. 执行后检查

- [ ] MySQL 平台应用表数量为 42
- [ ] 原 20 张表及数据未丢失
- [ ] 新增 19 张表均已建立
- [ ] 应用能够正常启动和登录
- [ ] 数据源连接正常
- [ ] 自动对数、历史记录和下载正常
- [ ] 报送导航能够刷新，且没有统计错误
- [ ] 人行模板第七步仅展示，第六步为最终完成节点
- [ ] 完成时间和跨月报告期显示正确

## 6. 回滚文件

- [ ] 旧程序
- [ ] 旧配置
- [ ] 升级前 MySQL 备份
- [ ] 原启动命令或服务配置

出现无法启动、无法登录、原数据丢失或核心业务异常时，停止新版本并使用以上文件回滚。
