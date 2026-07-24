# Auto Check 生产基线与候选版本差异审计

## 审计范围

- 生产基线：`D:\xiaxin\auto_check-v2.1-0703对账表改成配置.zip`
- 基线 SHA-256：`40A6431A472D153C3B9DE4F09876C4569DE2B37A6E978BFE746F972EF6D407DB`
- 基线大小：403,311,548 字节
- ZIP 条目：3,636
- ZIP 安全检查：未发现路径穿越或符号链接
- ZIP 内 Git HEAD：`e0b89cbc764931fad650d45477421822e5fe1d7d`
- 候选功能代码提交：`9d85cda7a32d68b5fa555963551d7aa099fb1293`

ZIP 内工作树存在未提交改动，因此基线比较以解压后的实际文件内容为准，不能只比较两个 Git 提交。

## 差异规模

- 基线相关文件：171
- 候选相关文件：251
- 新增：82
- 删除：2
- 修改：37
- 候选相对基线 HEAD 前进约 150 个提交
- 测试文件由 32 个增加到 43 个

界面版本仍显示 `v2.1`，Python 包版本仍为 `0.1.0`，不能依赖版本号识别实际投产内容；必须冻结提交 SHA、文件清单和制品 SHA-256。

## 关键架构变化

### 应用存储

生产基线主要使用 SQLite `auto-check.db` 和 `config.json`；候选改为强制使用 MySQL `auto_check` 应用库：

- 配置、用户、认证、三类执行历史、界面偏好、报送导航配置和快照均保存到 MySQL。
- `config.json` 必须包含 `app_database`，应用库后端仅接受 MySQL。
- 启动时只连接并校验 39 张表、字段和 `app_schema_version=1`。
- 应用不会自动建库、建表、升级或迁移。
- 旧 SQLite 运行时迁移已禁用；需停机后对 SQLite 备份副本运行 `scripts/export_sqlite_to_mysql.py`，再由运维人工执行 SQL。
- 迁移导出覆盖 20 张旧应用存储目标表；报送导航为候选新增数据，由 DDL 和种子脚本创建。

### SQL 脚本重号

仓库存在两组重号脚本：

- `007_report_navigation_comparison_delta.sql`
- `007_report_navigation_schedule_owner.sql`
- `008_report_navigation_manual_history.sql`
- `008_report_navigation_work_calendar.sql`

投产步骤不得写成模糊的“执行 007、008”，也不得仅按数字自动排序。必须冻结完整文件名、哈希、来源和执行顺序。SQLite 导出器生成的 schema 包含前一组内容，后续仍需按部署要求执行后一组及 `009` 至 `011`。

### 报送导航和后台任务

候选新增完整报送导航并作为默认页面：

- 七条主要流程、报送日程、负责人、工作日日历、人工确认和统计快照。
- 启动约 30 秒后开始后台采集，之后默认每 10 分钟运行。
- 使用 30 分钟 MySQL 租约锁控制并发。
- 每轮会访问多个业务数据源，投产前必须确认账号只读、网络、超时、连接池和查询负载。
- 业务报告期固定为当前月份上一个自然月的最后一天。
- `010`、`011` 会删除或覆盖部分导航快照、字段映射和配置，执行后需重新采集并核对状态。

### 前端与业务

- 新增报送导航、日程、待办、弹层、统计和界面偏好。
- 登录、用户管理、核对历史和本地数据入口均有变化。
- 本地 SQLite 管理入口已隐藏。
- `engine/reconcile.py` 存在实际修改，必须重新执行自动对数金标样本回归，不能假定核心规则未变。

### 打包和制品

- 打包脚本新增 SQLAlchemy MySQL 方言隐藏导入。
- 当前 `dist\auto-check.exe` 的生成时间早于最终候选源码。
- 现有 EXE 和基线二进制均不能证明由候选提交构建，不得直接作为投产物。

## 投产阻断项

以下任一项未关闭时禁止投产：

1. MySQL 39 张表、字段、约束或 `app_schema_version=1` 未完全满足。
2. SQLite 迁移前后 20 张目标表行数、抽样内容不一致。
3. 用户、配置、三类历史、数据源密码或下载文件迁移后不可用。
4. `AUTO_CHECK_SECRET_KEY` 不确定，或更换服务账户导致密钥派生变化。
5. 两组 `007/008` 的完整执行顺序和执行记录未冻结。
6. 最终候选提交、工作树、SQL 清单和交付制品 SHA-256 未冻结。
7. 使用早于候选提交的现有 `dist\auto-check.exe` 或旧二进制。
8. 没有在隔离生产等价环境完成完整升级和回滚演练。
9. 报送导航后台采集会使用未经批准的生产账号或产生不可接受负载。
10. 直接依赖存在新旧方案混杂的旧 SQLite 迁移文档，而没有按当前代码和 MySQL 部署文档复核。

## 建议升级顺序

1. 冻结最终提交、源码清单、SQL 清单和制品哈希。
2. 停止旧服务并确认没有运行中的导入、校验、流程链或自动对数任务。
3. 备份程序、完整数据目录、SQLite、JSON 历史、上传/结果文件、配置、服务参数、环境变量和密钥。
4. 对 SQLite 备份副本执行只读导出，保存 schema SQL、data SQL、迁移报告和哈希。
5. 在隔离 MySQL 空库执行导出 SQL。
6. 按完整文件名执行 `007_report_navigation_schedule_owner.sql`、`008_report_navigation_work_calendar.sql`、`009_report_navigation_manual_step_permissions.sql`、`010_pbc_template_step_seven_display_only.sql`、`011_report_navigation_completion_time_sources.sql`。
7. 核对 39 张表结构和迁移报告中 20 张表的数据。
8. 使用独立候选配置和原 `AUTO_CHECK_SECRET_KEY`，在非生产端口启动。
9. 完成登录、配置、三类历史、下载、自动对数、报送导航和后台调度验收。
10. 演练停止候选、恢复旧程序及完整旧数据目录和环境变量，验证旧版可用。

详细独立验收步骤见 [production-release-ai-test-prompt-2026-07-25.zh-CN.md](production-release-ai-test-prompt-2026-07-25.zh-CN.md)。
