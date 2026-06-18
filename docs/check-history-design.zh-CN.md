# 核对历史记录设计说明

本文档说明“核对历史”功能的当前实现和后续迁移数据库时的扩展方式。

## 一、设计目标

- 每次自动对数成功后，自动保存一条历史记录。
- 历史记录必须能展示本次结果相对上一次的变化。
- 当前先保存到本地 JSON 文件，后续可以平滑迁移到数据库。
- 历史记录属于工具自身数据，不写入业务数据库。

## 二、当前存储方式

当前实现使用 `JsonHistoryStore`，默认文件位置与配置文件同目录：

```text
history.json
```

如果程序使用默认配置路径，则历史文件位于：

```text
%APPDATA%\auto-check\history.json
```

如果启动时传入 `--config D:\xxx\config.json`，则历史文件位于：

```text
D:\xxx\history.json
```

## 三、存储抽象

代码中定义了 `HistoryStore` 接口：

- `list_runs()`：列出历史记录。
- `get_run(run_id)`：读取单条历史详情。
- `save_run(run)`：保存一次核对记录。
- `delete_run(run_id)`：删除一条历史记录。

业务代码只依赖 `HistoryStore`，不直接依赖 JSON 文件。后续切换数据库时，只需要新增 `DatabaseHistoryStore`，保持接口不变。

## 四、历史记录字段

每次核对生成一条历史记录，主要字段如下：

- `id`：历史记录唯一编号。
- `run_at`：执行时间。
- `run_date`：核对日期。
- `config_name`：执行时使用的数据源名称。
- `config_fingerprint`：数据源指纹。
- `rule_version`：规则版本。
- `baseline_id`：用于对比的上一条历史记录编号。
- `baseline_count`：上一条基准记录的差异数。
- `total_count`：本次差异总数。
- `status_counts`：按匹配状态统计。
- `reason_counts`：按差异类型统计。
- `added_count`：本次新增差异数量。
- `removed_count`：本次减少差异数量。
- `results`：本次完整核对结果。
- `added_results`：本次新增差异明细。
- `removed_results`：本次减少差异明细。

## 五、数据源指纹

历史对比不能只依赖配置名称，因为配置名称可能被修改。

程序会用以下连接信息生成 `config_fingerprint`：

- DWS 数据源类型、主机、端口、数据库、Schema、用户名。
- 业务数据源类型、主机、端口、数据库、Schema、用户名。

密码不会参与指纹，避免在历史数据中间接暴露密码变化。

## 六、新增差异和减少差异的判断规则

对比基准：

- 同一个核对日期 `run_date`。
- 同一个数据源指纹 `config_fingerprint`。
- 取最近的一条历史记录作为基准。

本次新增差异：

- 上一条基准记录没有、本次出现的差异项目。

本次减少差异：

- 上一条基准记录有、本次不再出现的差异项目。

当前对比键：

```text
项目编号 + 差异金额
```

差异金额就是主差异 `a0001-d0000`。同一个项目只要主差异金额变化，就会体现为旧差异减少、新差异新增；如果只是差异类型变化但主差异金额不变，不单独计入新增或减少。

如果后续要更细，可以扩展为：

```text
项目编号 + 差异方向 + 差异类型 + 差异金额 + 命中科目
```

## 七、页面展示

新增菜单：

```text
核对历史
```

列表字段：

- 执行时间。
- 核对日期。
- 数据源。
- 总差异。
- 新增差异。
- 减少差异。
- 已解释。
- 未解释。
- 操作。

操作：

- 查看：展示本次新增差异、本次减少差异、本次完整核对结果。
- 恢复：把这条历史的完整结果恢复到自动对数结果页。
- 删除：删除这条本地历史记录。

## 八、后续数据库落地方案

未来如果需要把历史保存到数据库，建议拆成三张表。

### check_history_run

保存一次核对的汇总信息：

- `id`
- `run_at`
- `run_date`
- `config_name`
- `config_fingerprint`
- `rule_version`
- `baseline_id`
- `baseline_count`
- `total_count`
- `status_counts`
- `reason_counts`
- `added_count`
- `removed_count`

### check_history_result

保存本次完整结果明细：

- `run_id`
- `project_code`
- `project_name`
- `asset_total`
- `liability_equity_total`
- `difference`
- `direction`
- `difference_reason`
- `match_status`
- `display_details`

### check_history_delta

保存本次相对上次的变化明细：

- `run_id`
- `delta_type`，取值为 `added` 或 `removed`。
- `project_code`
- `project_name`
- `difference`
- `difference_reason`
- `match_status`
- `payload`

迁移时，页面和 `ApiRouter` 不需要关心底层变化，只需要把 `JsonHistoryStore` 替换成 `DatabaseHistoryStore`。
