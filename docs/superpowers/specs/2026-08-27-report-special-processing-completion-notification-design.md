# 报表特殊处理确认完成通知设计

状态：已审阅，可进入实施计划

日期：2026-08-27

## 1. 目标

当数据治理负责人成功确认一条报表特殊处理记录后，系统向该记录的创建人发送应用内通知，使发起用户无需反复进入台账查询确认结果。

本设计只新增“确认完成”通知场景，复用现有 `platform.notification` v1 服务，不修改通知平台协议、数据库结构、权限能力或通知中心界面。

## 2. 已确认需求

- 触发动作：数据治理人员将记录成功确认到 `completed` 状态。
- 接收人：记录的创建人，即 `creator_user_id`；不使用可由表单选择的 `handler_user_id`。
- 通知标题：`您提交的报表特殊处理已完成确认`。
- 通知正文：沿用现有通知摘要格式，使用 `维度名称 · 字段名称`。
- 点击通知：进入“报表特殊处理录入”模块并打开对应记录详情，不进入确认模式。
- 只对功能上线后实际发生的确认动作发布，不扫描或补发历史已完成记录。

## 3. 方案选择

采用业务服务在确认事务成功提交后直接发布通知。

未采用以下方式：

- 模块事件订阅：当前只有一个明确触发点，引入额外事件协议会增加不必要的生命周期和失败处理复杂度。
- 定时扫描已完成记录：存在通知延迟，并需要额外水位、去重和补偿状态，不适合即时确认结果通知。

该方案与模块现有“待确认事项”通知保持一致：业务存储成功后调用 owner-bound `platform.notification` 门面，通知失败不反向回滚业务结果。

## 4. 模块边界与改动范围

允许修改：

- `src/auto_check/modules/report_special_processing/service.py`
- `src/auto_check/modules/report_special_processing/manifest.json`
- `src/auto_check/modules/report_special_processing/README.md`
- `tests/modules/report_special_processing/test_service.py`
- 必要的模块文档和根 `README.md`

禁止修改：

- 通知平台契约、存储、HTTP API、SSE 和公共前端。
- `src/auto_check/app/server.py`、公共模块宿主和其他业务模块。
- 报表特殊处理数据库迁移、权限能力码和现有状态机规则。

本次不新增可见控件，因此无需新增菜单或能力码；通知点击后的记录访问仍由目标模块现有权限校验负责。

## 5. 触发与数据流

触发点位于 `SpecialProcessingService.change_status()`：

1. 读取当前记录并执行现有 `rsp.confirm`、治理负责人归属、状态转换和完整性校验。
2. 调用仓储将状态更新为 `completed` 并写入审计记录。
3. 仓储成功返回更新后的记录后，调用新的确认完成通知辅助方法。
4. 刷新现有统计卡并返回业务结果。

只在 `target_status == "completed"` 且仓储更新成功时发布。权限失败、校验失败、乐观锁冲突、无效状态转换以及仓储回滚均不得产生通知。

重开记录后再次完成确认属于新的业务确认结果。由于记录的 `row_version` 已变化，应产生一条新的确认完成通知。

## 6. 通知契约

发布请求使用以下固定语义：

```python
NotificationPublishRequest(
    event_type="confirmation_completed",
    dedupe_key=f"rsp-completed:{record_id}:{row_version}:{creator_user_id}",
    recipient_user_ids=(creator_user_id,),
    category="task",
    level="success",
    title="您提交的报表特殊处理已完成确认",
    content=f"{dimension_label} · {field_name}",
    action=NotificationAction(
        type="navigate",
        route="report-special-processing",
        query={
            "record_id": str(record_id),
            "highlight": "1",
            "period": report_period_label,
        },
    ),
)
```

跳转参数不包含 `open=confirm`，避免已完成记录再次进入确认界面。模块沿用现有页面逻辑，通过 `record_id` 打开记录详情并高亮目标记录；`period` 沿用现有通知跳转口径，在报送期存在时传递去掉年份后的 `MM-DD` 标签（例如 `07-31`）。

若 `creator_user_id` 为空，辅助方法直接跳过发布并记录可排查日志。按现有正式数据约束，该情况只可能来自异常或历史脏数据，不能影响确认业务返回。

## 7. 幂等与失败处理

幂等键由记录 ID、确认成功后的 `row_version` 和创建人 ID 组成：

```text
rsp-completed:{record_id}:{row_version}:{creator_user_id}
```

同一确认结果因调用重试而重复发布时，通知平台返回已有通知且不再次推送。记录重开并再次完成后版本变化，因此会创建新通知。

通知发布是业务事务之后的独立短事务。发布异常时：

- 已完成的业务状态和审计记录保持成功。
- 模块记录脱敏警告，包含记录 ID、版本、接收人和请求号，不记录通知正文或敏感信息。
- API 仍返回已确认完成的记录。

## 8. 测试设计

在 `tests/modules/report_special_processing/test_service.py` 中新增或调整测试：

1. 治理负责人确认后恰好向 `creator_user_id` 发布一条通知，即使 `handler_user_id` 是另一个用户。
2. 断言事件类型、标题、`task/success` 语义、摘要正文和详情跳转参数。
3. 断言确认通知的去重键包含确认后的 `row_version` 和创建人 ID。
4. 保存草稿、创建待确认、普通编辑、改派、作废、删除和重开本身不发布“确认完成”通知；原有“待确认”通知行为保持不变。
5. 权限失败、非法状态转换和乐观锁冲突不发布确认完成通知。
6. 通知发布异常时，确认结果仍为 `completed`。
7. 重开后再次确认使用新版本生成新的确认完成通知。

验证顺序：

1. 运行 `tests/modules/report_special_processing/test_service.py`。
2. 运行整个 `tests/modules/report_special_processing/`。
3. 由后台子代理运行 `python -m pytest -q` 全量测试，主会话检查实际输出。
4. 运行 `git diff --check` 并检查改动未越过模块边界。

除非用户另行明确要求，不运行 Windows 或 Linux 打包，不刷新可执行文件，不提交或推送代码。

## 9. 文档与版本

- 模块版本由 `1.2.8` 升为 `1.2.9`。
- 模块发布说明增加：`确认完成后通知记录创建人`。
- 模块 README 说明触发条件、接收人为创建人、点击进入详情以及通知失败不影响确认结果。
- 根 README 按现有详细变更口径记录行为变化。
- 模块发布说明由现有宿主聚合进系统更新日志，不直接修改公共 `app.js`，不提升展示用大版本号。

## 10. 验收标准

1. 数据治理负责人确认完成后，记录创建人收到标题为“您提交的报表特殊处理已完成确认”的应用内通知。
2. 记录处理人与创建人不同时，通知只发送给创建人。
3. 点击通知打开对应已完成记录详情，不出现确认操作界面。
4. 同一确认结果不会因重复调用产生重复通知；重开后再次确认会产生新通知。
5. 通知平台异常不会回滚或阻断已经成功的确认操作。
6. 原有待确认通知、权限、状态机、审计和统计行为保持不变。
