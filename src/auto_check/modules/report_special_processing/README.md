# 报表特殊处理录入模块

该可选内置模块维护报送期特殊处理台账，并向 `special_governance` 卡片提供真实统计。模块只保存脚本文本及 SHA-256 留痕，永不解析、试运行或执行脚本。

## 后端边界

- API：`/api/modules/report-special-processing`，请求体最大 1 MiB。
- 权限：普通登录用户可查看和创建；创建人或处理人可编辑未完成记录；管理员可编辑全部未完成记录、作废、重开和物理删除。
- 状态：`draft → pending → processing/completed`，`processing → pending/completed`；管理员可将 `pending/processing` 作废，将 `completed/voided` 重开为 `pending`；管理员可对任意状态记录物理删除（二次确认，不可恢复）。
- 数据：主表与涉及报表、关联报送、审计日志表由独立迁移管理；删除接口会同步清除该记录的明细与审计；停用模块不删除数据。
- 关联报送：支持多选；主表保留首项编码，名称快照为分号拼接；页签筛选与按报送统计走关联表；台账按报送逐行展示。
- 并发：所有修改携带 `row_version`，冲突返回 409；业务写入和审计处于同一数据库事务。
- 目录：处理人和报送流程分别来自 owner-bound `platform.user_directory` v1 与 `platform.report_navigation` v1，不在模块硬编码人员或七类报送。
- 统计：按平台传入的 Asia/Shanghai 左闭右开周期，以 `special_handling_at` 汇总；草稿和作废排除。
- 统计刷新：注册为 `include_in_collect=False` + `refresh_on_dashboard=True`。定时/手工 `collect_once` 均不采集本卡；进入报送导航读取 dashboard 时按台账实时刷新；台账写入成功后仍 best-effort 调用 owner 作用域 `refresh_card_provider`；刷新失败不影响业务写入与页面读取。

## 运维

上线前备份应用库。模块迁移不提供 down migration；出现问题时优先禁用模块，保留三张表、迁移历史和报送导航最后成功快照。后续结构变化只能新增迁移，不得修改已发布的 `001_initial.sql`。当前 schema_version=2（`002_multi_report_processes.sql`）。
