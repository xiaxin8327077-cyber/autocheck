# 报送导航状态统计与日期维护设计

## 目标

将当前静态的“报送导航”改为基于数据库配置和定时统计快照的动态页面，实现：

- 根据鱼骨节点实际完成状态统计“报送报表”总数、已完成数和未完成数。
- 根据补录任务表统计“补录任务”总数、已完成数和未完成数。
- “数据治理流程”和“报表特殊治理”暂时统一显示 0。
- 后台每 10 分钟串行执行一次状态统计，页面只读取应用 MySQL 快照，不在打开页面时实时查询业务库。
- 管理员可以手动完成或取消手动完成鱼骨步骤。
- 报送日期按月落库，管理员可以双击修改。
- 1、4、7、10 月显示“五篇大文章报送”，其他月份隐藏该节点及对应报送日期。
- 所有数据源、表、字段和固定业务值使用普通关系字段配置，不使用 JSON 字段。

## 范围

本次包含：

- 新增报送导航专用关系表和初始化数据。
- 新增固定判断逻辑、后台串行定时任务、快照读取接口、管理员手工完成接口和日期修改接口。
- 改造报送导航四张统计卡、鱼骨图状态、报送日期和错误提示。
- 使用提供的工作日 Excel 数据初始化月度报送日期。

本次不包含：

- 不修改任何现有表的字段、索引、主键、外键或其他结构。
- 不增加规则配置页面；管理员后续直接修改新增配置表。
- 不增加工作日 Excel 页面上传入口。
- 不增加定时任务启停、周期调整、手动执行或历史查看页面；只为这些后续能力预留关系表和服务边界。
- 不统计数据治理流程和报表特殊治理的真实业务数据。

## 核心口径

### 报告月份与业务报告期

- 鱼骨图和报送日期始终展示系统当前月份，不受顶部“本周／本月／本季度／本年”选择影响。
- 需要“同对账报告期”的判断规则，统一取自动对数历史中最新的报告期。
- 例如最新自动对数报告期为 `2026-06-30`：
  - 普通日期字段使用 `2026-06-30`。
  - `ck_result.period` 使用 `2026_06_30`。
  - 版本号使用 `V.20260630`。
- 如果没有任何自动对数历史，依赖业务报告期的步骤显示“等待报告期”并按未完成处理。

### 自动判断与人工完成

- 每个步骤先执行固定的自动判断逻辑。
- 管理员可以将步骤手动置为完成；手动完成按报告月份保存。
- 管理员取消手动完成时删除人工覆盖，步骤恢复使用自动判断结果。
- 页面显示“人工”标记，区分人工完成和自动完成。
- 不提供“强制未完成”状态。

### 空数据和异常

- 对“无异常”“无待确认”“无空值”等否定式规则，必须先存在当前范围内的数据，然后不存在异常记录，才算完成。
- 当前范围一条数据都没有时按未完成处理，避免空表被误判为通过。
- 数据源配置、表或字段不存在，或者查询失败时，步骤状态为“判断异常”，节点按未完成处理。
- 全局定时任务无法启动或无法写入应用库时，页面保留上一份快照并显示“数据可能已过期”。

### 节点完成时间

- “完成于 2026-06-01 10:24”表示鱼骨节点整体完成时间，不是单个步骤时间。
- 定时任务首次检测到节点全部有效步骤完成时，记录当前检测完成时间。
- 管理员操作使最后一个未完成步骤变为完成时，立即记录当前操作时间。
- 节点重新变为未完成或判断异常时清除当前完成时间；再次全部完成时重新记录。

## 数据库设计

### 只新增表

新增 `sql/app_storage/mysql/002_report_navigation.sql`，只包含新表的 `CREATE TABLE`，不执行任何现有表的 `ALTER TABLE`。

应用现有 `app_schema_version` 表和结构版本保持不变。新环境需依次执行：

1. `001_init_schema.sql`
2. `002_report_navigation.sql`
3. 报送导航初始化数据脚本

初始化数据脚本只向新增表写入节点、步骤、映射、固定业务值和月度日期，不修改现有表。

### 新增配置表

#### `report_nav_processes`

保存鱼骨节点：

- `process_code`
- `process_name`
- `display_order`
- `enabled`
- `allow_manual_step_completion`

#### `report_nav_process_months`

保存节点适用月份：

- `process_code`
- `month_no`

五篇大文章配置 1、4、7、10，其余节点配置 1 至 12。

#### `report_nav_steps`

保存节点步骤和固定判断器入口：

- `step_code`
- `process_code`
- `step_name`
- `display_order`
- `evaluator_key`
- `enabled`
- `default_completed`
- `manual_completion_allowed`

判断器逻辑写在 Python 代码中；`evaluator_key` 只选择对应的固定判断器。

#### `report_nav_step_dependencies`

保存步骤依赖：

- `step_code`
- `depends_on_step_code`

1104 步骤 2、步骤 3 依赖步骤 4；人行模板步骤 5 依赖步骤 6。

#### `report_nav_step_sources`

保存步骤使用的数据源和表：

- `id`
- `step_code`
- `source_role`
- `data_source_name`
- `table_name`
- `display_order`
- `enabled`

一个步骤可以配置多个数据源或多张表。

#### `report_nav_step_fields`

保存逻辑字段与实际字段名的映射：

- `id`
- `step_source_id`
- `field_role`
- `column_name`

示例：`period_field → reporting_period`、`status_field → status`、`version_field → version_num`。

#### `report_nav_step_values`

保存固定业务值：

- `id`
- `step_code`
- `value_role`
- `value_text`
- `value_type`
- `display_order`

示例：`target_ck_id → 7118`、`completed_status → 5`、`manage_code → east5`。

以上配置表均不使用 JSON 字段，也不保存可直接执行的任意 SQL。

### 新增状态和任务表

#### `report_nav_step_overrides`

按月份保存管理员手动完成：

- `report_month`
- `step_code`
- `completed`
- `operator_id`
- `operator_username`
- `operator_name`
- `created_at`
- `updated_at`

取消人工完成时删除对应覆盖记录。

#### `report_nav_step_snapshots`

保存最近一次步骤统计结果：

- `report_month`
- `step_code`
- `auto_status`
- `effective_status`
- `completion_source`
- `status_message`
- `error_message`
- `auto_completed_at`
- `evaluated_at`
- `run_id`

#### `report_nav_process_snapshots`

保存节点整体状态：

- `report_month`
- `process_code`
- `total_steps`
- `completed_steps`
- `status`
- `completed_at`
- `evaluated_at`
- `run_id`

#### `report_nav_card_snapshots`

保存四张统计卡在各统计周期下的最近一次结果：

- `stat_period`
- `card_code`
- `total_count`
- `completed_count`
- `incomplete_count`
- `completion_rate`
- `evaluated_at`
- `run_id`

`stat_period` 使用 `week`、`month`、`quarter`、`year`。补录任务分别保存四种周期快照；报送报表、数据治理流程和报表特殊治理保存当前月份口径，并在接口层复用于四种顶部选项。

#### `report_nav_monthly_schedules`

保存月度报送日期：

- `report_month`
- `process_code`
- `report_date`
- `source_type`
- `source_year`
- `updated_by`
- `updated_at`

`source_type` 使用普通字符串值区分 `imported`、`default`、`inherited` 和 `manual`。

#### `report_nav_stat_runs`

保存每次统计任务摘要：

- `id`
- `trigger_type`
- `report_month`
- `business_report_date`
- `started_at`
- `finished_at`
- `status`
- `completed_processes`
- `failed_steps`
- `error_message`

#### `report_nav_scheduler_state`

保存定时任务状态和互斥锁：

- `id`
- `enabled`
- `interval_minutes`
- `next_run_at`
- `lock_owner`
- `lock_until`
- `last_started_at`
- `last_finished_at`
- `last_status`
- `last_error`
- `updated_at`

默认启用，周期为 10 分钟。后续定时任务管理页面直接复用该表。

## 定时任务设计

- 应用启动约 30 秒后尝试执行首次统计。
- 之后默认每 10 分钟执行一次。
- 调度器先原子获取 `report_nav_scheduler_state` 的数据库锁；锁未过期时跳过本轮。
- 锁包含过期时间，应用异常退出后可以自动恢复。
- 一个任务内部严格按照节点顺序、步骤顺序逐个查询，不并行访问任何数据源。
- 单个步骤失败不阻止后续步骤执行，失败信息写入该步骤快照。
- 定时任务运行期间收到下一次触发时直接跳过，不排队重复执行。
- 页面打开和普通刷新不触发业务数据源查询，只读取应用 MySQL 快照。
- 管理员手动完成、取消完成或修改日期时，只更新对应应用库状态，不启动全量统计任务。

后续可在页面增加启用、停止、修改周期、手动执行和查看运行记录，本次不实现这些控件。

## 步骤判断逻辑

### 人行大集中

#### 步骤 1：导入并生成存续回购业务明细

- 数据源：`ass_man_reg`
- 表：`ex_pledge_back`
- 报告期字段角色：`reporting_period`
- 完成条件：表中存在数据，且所有记录的 `reporting_period` 都等于最新自动对数报告期。

#### 步骤 2：资产合计与负债及权益合计一致

- 数据源：`reg-report-analysis`
- 表：`zf_detail_2024`
- 报告期字段角色：`caldate`
- 金额字段角色：`a0001`、`d0000`
- 完成条件：当前报告期存在数据，且不存在 `a0001 != d0000` 的记录。

#### 步骤 3：地区、客户类型和份额跨期校验

规则 A：

- 数据源：`currency_report_24`
- 表：`currency_report_duration`
- 报告期字段：`caldate`
- 完成条件：当前报告期存在数据，且不存在 `c_regioncode` 或 `c_custtype` 为 NULL 或空字符串的记录。

规则 B：

- 数据源：`reg-report-analysis`
- 表：`ck_result`
- 报告期字段：`period`，格式为 `yyyy_mm_dd`
- 固定业务值：`ck_id = 5677`
- 完成条件：`ck_result` 在当前报告期存在数据，且不存在 `ck_id = 5677` 的记录。

规则 A、B 同时满足才完成。

#### 步骤 4：TA 客户与资产端交易对手校验

规则 A：

- 数据源：`reg-report-analysis`
- 表：`ck_result`
- 报告期字段：`period`，格式为 `yyyy_mm_dd`
- 固定业务值：`ck_id = 7118`
- 完成条件：`ck_result` 在当前报告期存在数据，且不存在 `ck_id = 7118` 的记录。

规则 B：

- 数据源：`ass_man_reg_24`
- 表：`zgxgzh_spvdetail_zg08`
- 时间字段：`tbtime`
- 完成条件：表中存在数据，且最小 `tbtime` 位于系统当前月份。

规则 A、B 同时满足才完成。

### 人行模板、逐笔报送

#### 步骤 1：债券发行人和交易对手信息确认

- 数据源：`currency_report_24`
- 表：`straight_flush`、`straight_flush_yxzgq`
- 报告期字段：`caldate`
- 状态字段：`status`
- 固定业务值：`待确认`、`待补充`
- 完成条件：两张表在业务报告期所在月份均存在数据，且均不存在状态为“待确认”或“待补充”的记录。

#### 步骤 2：维度变化报备

- 数据源：`ass_man_reg`
- 表：`product_change`
- 日期字段：`chdate`
- 完成条件：存在业务报告期所在月份的数据；如果不存在，则在人行模板步骤 6 完成后自动完成。

#### 步骤 3：补录底表更新和任务触发

- 默认完成，不执行数据源查询。

#### 步骤 4：导入人行全量 SPV 码

- 数据源：`ass_man_reg_24`
- 表：`zg08_wb`
- 时间字段：`tbtime`
- 完成条件：表中存在数据，且最小 `tbtime` 位于系统当前月份。

#### 步骤 5：监管平台人行报表校验

- 依赖步骤 6；步骤 6 完成后自动完成。

#### 步骤 6：归档并上传人行报送网站

- 数据源：`reg-report-analysis`
- 表：`xt_reg_version`
- 字段：`manage_code`、`version_num`
- 固定业务值：`manage_code` 包含 `20002` 和 `zbbs24`
- 完成条件：两个 `manage_code` 都存在 `version_num = V.当前报告期` 的记录。

#### 步骤 7：填写数据调整情况说明

- 自动条件：系统当前日期达到或超过人行模板、逐笔报送日期时自动完成。
- 报送日期之前，管理员可以手动完成。
- 取消手动完成后恢复自动日期判断。

### 1104 报送

#### 步骤 1：导入报送外部数据

- 仅 1、4、7、10 月执行自动查询，其他月份默认完成。
- 数据源：`1104`
- 表：`relation_ship_1104_dm`
- 日期字段：`createdate`
- 完成条件：表中存在数据，且 `createdate` 位于系统当前月份。

#### 步骤 2、步骤 3

- 均依赖步骤 4；步骤 4 完成后自动完成。

#### 步骤 4：归档并上传金监报送网站

- 数据源：`reg-report-analysis`
- 表：`xt_reg_version`
- 字段：`manage_code`、`version_num`
- 固定业务值：`manage_code = system1104`
- 完成条件：存在 `version_num = V.当前报告期` 的记录。

### 21、23 版全要素报送

该节点使用一个内部判断步骤：

- 数据源：`reg-report-analysis`
- 表：`xt_reg_version`
- 字段：`manage_code`、`version_num`
- 固定业务值：`manage_code = qysnew`
- 完成条件：存在 `version_num = V.当前报告期` 的记录。

### 中信登定期报送

#### 步骤 1：补录底表更新和任务触发

- 默认完成。

#### 步骤 2：导入报送外部数据

- 数据源：`zxd`
- 表：`zxd_asset_credit_info`、`result14_xtbzjj_external_data`、`jsxt_basic_info`
- 日期字段：`createdate`
- 完成条件：三张表均存在数据，且各表都存在 `createdate` 位于系统当前月份的记录。

#### 步骤 3、步骤 4

- 均依赖步骤 5；步骤 5 完成后自动完成。

#### 步骤 5：归档并上传中信登平台

- 数据源：`reg-report-analysis`
- 表：`xt_reg_version`
- 字段：`manage_code`、`version_num`
- 固定业务值：`manage_code = zxdreport`
- 完成条件：存在 `version_num = V.当前报告期` 的记录。

### East5 报送

该节点使用一个内部判断步骤：

- 数据源：`reg-report-analysis`
- 表：`xt_reg_version`
- 字段：`manage_code`、`version_num`
- 固定业务值：`manage_code = east5`
- 完成条件：存在 `version_num = V.当前报告期` 的记录。

### 五篇大文章报送

- 仅 1、4、7、10 月启用和展示。
- 该节点使用一个内部判断步骤。
- 数据源：`reg-report-analysis`
- 表：`xt_reg_version`
- 字段：`manage_code`、`version_num`
- 固定业务值：`manage_code = dwz5`
- 完成条件：存在 `version_num = V.当前报告期` 的记录。

## 补录任务统计

- 数据源：`bl`
- 类型：MySQL
- 数据库：`jsxt_console`
- 表：`rep_data_task_detail`
- 唯一标识：`id`
- 状态字段：`status`
- 日期字段：`create_date`
- 删除标记：`del_flag`
- 完成状态固定值：`5`
- 有效记录：`del_flag = 0`

顶部统计周期控制 `create_date` 范围：

- 本周：本周一 00:00（含）至下周一 00:00（不含）。
- 本月：本月 1 日 00:00（含）至下月 1 日 00:00（不含）。
- 本季度：本季度首日 00:00（含）至下季度首日 00:00（不含）。
- 本年：本年 1 月 1 日 00:00（含）至下一年 1 月 1 日 00:00（不含）。

统计公式：

- 总数：有效记录且 `create_date` 位于所选周期。
- 已完成：总数范围内 `status = 5`。
- 未完成：总数范围内 `status != 5`，包含 NULL 状态。

补录任务统计由后台定时任务按四种周期分别计算并保存，页面切换周期时直接读取对应快照，不实时访问 `bl` 数据源。

## 报送日期

### 初始数据

使用 `工作日数据(1).xlsx` 初始化 2026 年日期：

- 人行大集中：文件中不存在，默认每月 1 日。
- 人行模板、逐笔报送：读取“人行模板\逐笔”。
- 1104：同月多条时只保存最大日期。
- 全要素：读取“全要素”。
- 中信登：读取“中信登定期”。
- East5：读取“EAST5.0”。
- 五篇大文章：读取“五篇大文章”。

### 缺失月份回退

- 目标年月没有配置时，自动沿用上一年同月同日并以 `inherited` 保存。
- 2 月 29 日复制到非闰年时使用 2 月最后一天。
- 如果没有上一年配置，人行大集中仍使用每月 1 日；其他节点显示“日期待维护”。
- 后续可以重新导入新的工作日文件，但本次不提供页面导入入口。

### 页面修改

- 只有管理员可以双击日期编辑。
- 只能修改当前月和未来月份，历史月份不展示也不可修改。
- 修改日期必须属于对应报送月份。
- 保存无需二次确认，成功后立即更新页面和修改人、修改时间。
- Esc、取消按钮或点击弹框取消区域可以放弃修改。

## 页面设计

### 四张统计卡

- 删除四张卡右上角的趋势百分比标签。
- 保留完成率进度条和进度条右侧百分比。
- 卡片底部统一显示“已完成 X”“未完成 X”。
- 报送报表：
  - 1、4、7、10 月总数为 7，其他月份总数为 6。
  - 已完成为全部步骤完成的可见节点数量。
  - 未完成为总数减已完成。
- 补录任务：按顶部统计周期读取对应快照。
- 数据治理流程：总数 0、已完成 0、未完成 0。
- 报表特殊治理：总数 0、已完成 0、未完成 0。

### 鱼骨图

- 非 1、4、7、10 月隐藏五篇大文章节点，并将其余 6 个节点重新均匀排列。
- 步骤显示自动完成、人工完成、未完成或判断异常。
- 管理员点击步骤状态图标后弹出确认框：
  - 未人工完成时确认“手动置为完成”。
  - 已人工完成时确认“取消手动完成”。
- 节点全部完成时显示 `DONE · 完成数/总数` 和节点整体完成时间。
- 节点未完成时显示当前完成数和未完成步骤。
- 无快照时显示“等待首次统计”。

### 报送日期和统计时间

- 浅色模式下报送日期使用黑色字体。
- 暗色模式下使用高对比浅色字体，不强制使用黑色。
- 页面显示最近一次统计完成时间。
- 全局任务失败时显示简短警告并保留上一次快照。

## 接口设计

### 只读接口

`GET /api/report-navigation/dashboard?period=month`

返回：

- 当前月份和最新自动对数报告期。
- 四张统计卡快照。
- 当前月可见节点、步骤状态、人工标记、错误信息和节点完成时间。
- 报送日期及是否允许编辑。
- 最近一次任务状态和完成时间。

`period` 仅控制补录任务卡，可选 `week`、`month`、`quarter`、`year`。

### 管理员接口

- `POST /api/report-navigation/steps/{step_code}/manual-complete`
- `POST /api/report-navigation/steps/{step_code}/manual-cancel`
- `POST /api/report-navigation/schedules/{process_code}`

所有写接口必须验证登录、管理员角色和 CSRF。普通用户调用返回 403。

## 安全与兼容

- 数据源仍从系统现有数据源配置读取，兼容 MySQL 和 PostgreSQL。
- 数据源名、表名和字段名从配置表加载后必须通过标识符校验，并使用对应数据库方言安全引用。
- 所有业务值均使用参数绑定，不拼接到 SQL 文本。
- 不允许配置任意 SQL。
- 活力主题、沉稳主题和暗色模式均保持可读。
- 定时任务不得阻塞 Web 请求线程。

## 测试策略

### 后端

- 新增表结构与应用预期结构测试，确认未修改现有表定义。
- 各固定判断器分别覆盖完成、未完成、空数据和查询异常。
- 覆盖日期格式：`yyyy-MM-dd`、`yyyy_mm_dd` 和 `V.yyyymmdd`。
- 覆盖多数据源、多表同时满足规则。
- 覆盖依赖步骤、默认完成、日期自动完成和人工覆盖。
- 覆盖人工完成、取消完成、普通用户拒绝和 CSRF 校验。
- 覆盖节点整体完成时间的首次写入、保持、清除和再次写入。
- 覆盖定时任务 10 分钟周期、启动延迟、数据库锁、超时恢复和严格串行执行。
- 覆盖补录任务周、月、季度、年度边界和 NULL 状态。
- 覆盖工作日数据初始化、1104 最大日期、上一年沿用和闰年回退。

### 前端

- 四张卡无右上角百分比，底部只有已完成和未完成标签。
- 五篇大文章按月份显示或隐藏，6/7 节点布局正确。
- 日期颜色兼容浅色、暗色、活力和沉稳主题。
- 管理员与普通用户的步骤操作和日期编辑权限正确。
- 确认框、成功提示、失败提示、等待首次统计和快照过期状态正确。

### 交付验证

- 运行 `python -m pytest -q`。
- 运行 `git diff --check`。
- 停止占用 `dist/auto-check.exe` 的进程并重新打包。
- 核验新 EXE 的时间、大小和 SHA256。
