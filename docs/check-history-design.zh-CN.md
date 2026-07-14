# 核对历史记录设计说明

本文档说明“核对历史”功能的当前实现、MySQL 应用存储结构和旧历史数据离线迁移方式。

## 一、设计目标

- 每次自动对数成功后，自动保存一条历史记录。
- 历史记录必须能展示本次结果相对上一次的变化。
- 当前保存到 MySQL 应用库 `auto_check`，由 `DatabaseHistoryStore` 通过 SQLAlchemy Core 读写结构化历史表。
- 历史记录属于工具自身数据，不写入业务数据库。

## 二、当前存储方式

当前默认实现使用 `DatabaseHistoryStore`，数据保存在 `config.json` 中 `app_database` 指向的 MySQL 应用库 `auto_check`。`config.json` 仅提供启动连接信息，历史记录不再写入同目录 JSON 或 SQLite。

运行时不再自动迁移旧 SQLite 或旧 JSON 历史；如需迁移旧数据，应在停机备份后使用 `scripts/export_sqlite_to_mysql.py` 只读导出 SQL，再由运维人员人工执行。

自动对数历史使用结构化表保存常用查询字段：

- `run_headers`：运行头、执行人、核对日期、执行时间和完整 payload 快照。
- `reconcile_runs`：自动对数运行摘要、基准记录和增量数量。
- `reconcile_run_counts`：按匹配状态和差异类型统计。
- `reconcile_results`：项目编号、差异类型、匹配状态、差异金额等结果热字段。
- `reconcile_result_details`：结构化详情类型和具体原因。
- `reconcile_delta_results`：新增差异和减少差异快照。

人行逐笔校验历史使用结构化表保存运行摘要、选择表、告警和结果行：

- `db_validation_runs`：报告期、结果数、告警数、表数量、校验开关和下载路径。
- `db_validation_selected_tables`：本次勾选的人行表清单。
- `db_validation_warnings`：本次运行产生的告警信息。
- `db_validation_result_rows`：校验结果行的表号、规则、级别、消息和完整行快照。

流程链执行历史使用结构化表保存运行摘要、步骤、日志和多链路详情：

- `flow_chain_runs`：链路名称、触发方式、执行人、状态、错误、步骤数和总耗时。
- `flow_chain_run_steps`：每个流程步骤的流程编号、名称、状态、申报平台任务号和起止时间。
- `flow_chain_run_logs`：执行日志、进度和当前步骤。
- `flow_chain_run_details`：单链路或多链路合并历史中的链路明细。

旧 `history_runs(kind='reconcile')`、`history_runs(kind='db_validation')`、`history_runs(kind='flow_chain')`，以及同目录 `history.json`、`db-validation-history.json` 仅作为离线迁移来源保留，当前运行版本不会在首次读取历史时自动迁移。

## 三、存储抽象

代码中定义了 `HistoryStore` 接口：

- `list_runs()`：列出历史记录。
- `get_run(run_id)`：读取单条历史详情。
- `save_run(run)`：保存一次核对记录。
- `delete_run(run_id)`：删除一条历史记录。

业务代码只依赖 `HistoryStore`，不直接依赖具体表结构。`DatabaseHistoryStore` 维护 MySQL 结构化表和 `run_headers.payload_json` 完整快照，`JsonHistoryStore` 仅保留给测试和旧文件场景使用。

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
- 取同一个核对日期 `run_date` 下最近的一条历史记录作为基准。
- 当前不再按数据源指纹限制基准记录，避免数据源名称或配置调整后丢失同报告期对比能力。

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

## 八、迁移与回退

结构化历史迁移遵循“旧数据保留、离线只读导出、人工执行 SQL”的原则。运行时不再自动迁移旧 SQLite 或旧 JSON 历史。

- `history_runs(kind='reconcile')` 和同目录 `history.json` 可通过离线导出脚本迁移到结构化自动对数历史表；两类旧来源同时存在时由导出报告记录来源和行数。
- `history.json` 支持顶层数组和 `{"runs": [...]}` 两种格式。
- `history_runs(kind='db_validation')` 和人行逐笔校验旧文件 `db-validation-history.json` 会迁移到 `db_validation_runs`、`db_validation_selected_tables`、`db_validation_warnings` 和 `db_validation_result_rows`。
- `history_runs(kind='flow_chain')` 会迁移到 `flow_chain_runs`、`flow_chain_run_steps`、`flow_chain_run_logs` 和 `flow_chain_run_details`。
- 迁移记录写入 `storage_migration_runs`，记录来源类型、路径、指纹、导入条数、跳过条数、状态和错误摘要；旧 JSON 损坏时应先在离线导出阶段处理，不由运行时静默迁移。

详情页和导出仍可从 `run_headers.payload_json` 还原完整结果；列表、统计和后续筛选优先使用结构化热字段。回退时可以恢复旧版本程序、迁移前备份的 `auto-check.db` 和旧 JSON 文件。
