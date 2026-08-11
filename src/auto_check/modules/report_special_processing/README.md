# 报表特殊处理录入模块

该可选内置模块维护报送期特殊处理台账，并向 `special_governance` 卡片提供真实统计。模块只保存脚本文本及 SHA-256 留痕，永不解析、试运行或执行脚本。

## 后端边界

- API：`/api/modules/report-special-processing`，请求体最大 1 MiB。
- 权限：按角色能力矩阵 `rsp.view/create/edit/confirm/void/reopen/delete` 判定；标准用户遵循“谁创建谁处理”（仅创建人可编辑/作废/重开，处理人不可单独操作）；`rsp.confirm` 控制完成确认，且确认人须为该条「数据治理负责人」（管理员例外可确认任意条）；`rsp.delete` 控制任意状态物理删除。管理员默认拥有全部能力。
- 状态：`draft → pending(待确认) → completed`；界面不再主动进入 `processing`（历史数据仍可显示）；具备作废能力可将 `draft/pending/processing` 作废；具备重开能力可将 `completed/voided` 重开为 `pending`；具备删除能力可对任意状态记录物理删除（二次确认，不可恢复）。
- 字段：基本信息含关联报送、所处报送期、处理人、所属维度、数据治理负责人；特殊处理内容含处理摘要（≤50 字）、处理表名、处理字段名、修改前、修改后；界面已去掉涉及报表与处理说明。所属维度枚举为项目端/资金端/资产端/财务端；治理负责人按维度从角色「数据治理_项目资产」（项目端、资产端）或「数据治理_资金财务」（资金端、财务端）启用用户中联动候选。
- 列表：仅 8 列——修改字段名、修改前、修改后、关联报送、状态、处理人、处理时间、操作；确认经弹窗完成，主按钮「源系统已确认」。
- 待办：`pending` 且治理负责人为当前用户时，经平台 Todo Provider 注入报送导航「我的待办」；摘要含所属维度与修改字段名；「处理」跳转台账并定位该条。
- 数据：主表与关联报送、审计日志表由独立迁移管理；删除接口会同步清除该记录的明细与审计；停用模块不删除数据。
- 关联报送：支持多选；主表保留首项编码，名称快照为分号拼接；页签筛选与按报送统计走关联表；台账按报送逐行展示。
- 并发：所有修改携带 `row_version`，冲突返回 409；业务写入和审计处于同一数据库事务。
- 目录：处理人和报送流程分别来自 owner-bound `platform.user_directory` v1 与 `platform.report_navigation` v1，不在模块硬编码人员或七类报送。
- 统计：按平台传入的 Asia/Shanghai 左闭右开周期，以 `special_handling_at` 汇总；草稿和作废排除。
- 统计刷新：注册为 `include_in_collect=False` + `refresh_on_dashboard=True`。定时/手工 `collect_once` 均不采集本卡；进入报送导航读取 dashboard 时按台账实时刷新；台账写入成功后仍 best-effort 调用 owner 作用域 `refresh_card_provider`；刷新失败不影响业务写入与页面读取。

## 运维

上线前备份应用库。模块迁移不提供 down migration；出现问题时优先禁用模块，保留业务表、迁移历史和报送导航最后成功快照。后续结构变化只能新增迁移，不得修改已发布的 `001_initial.sql`。当前 schema_version=3（`003_dimension_governance_fields.sql`）。
