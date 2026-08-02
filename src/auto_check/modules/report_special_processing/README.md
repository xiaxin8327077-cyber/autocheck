# 报表特殊处理录入模块

该可选内置模块维护报送期特殊处理台账，并向 `special_governance` 卡片提供真实统计。模块只保存脚本文本及 SHA-256 留痕，永不解析、试运行或执行脚本。

## 后端边界

- API：`/api/modules/report-special-processing`，请求体最大 1 MiB。
- 权限：普通登录用户可查看和创建；创建人或处理人可编辑未完成记录；管理员可编辑全部未完成记录、作废和重开。
- 状态：`draft → pending → processing/completed`，`processing → pending/completed`；管理员可将 `pending/processing` 作废，将 `completed/voided` 重开为 `pending`。
- 数据：三张 `report_special_processing_` 表由独立 `001_initial.sql` 管理，无 DELETE 记录接口，停用模块不删除数据。
- 并发：所有修改携带 `row_version`，冲突返回 409；业务写入和审计处于同一数据库事务。
- 目录：处理人和报送流程分别来自 owner-bound `platform.user_directory` v1 与 `platform.report_navigation` v1，不在模块硬编码人员或七类报送。
- 统计：按平台传入的 Asia/Shanghai 左闭右开周期，以 `special_handling_at` 汇总；草稿和作废排除。

## 运维

上线前备份应用库。模块迁移不提供 down migration；出现问题时优先禁用模块，保留三张表、迁移历史和报送导航最后成功快照。后续结构变化只能新增迁移，不得修改已发布的 `001_initial.sql`。
