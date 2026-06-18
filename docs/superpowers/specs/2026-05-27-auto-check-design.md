# 自动对数工具设计

## 目标

构建一个 Windows 单机可执行工具，用于按日期自动核对项目资产负债差异，并识别已确认的差异原因。工具通过本地 Web 界面操作，后端只执行查询操作，不对任何业务数据库写入数据。

最终交付物应包含：

- 一个可双击运行的 Windows `.exe`
- 本地 Web 界面
- 可持久化保存的数据库连接配置
- 用于本地测试建表的 `sql/` 脚本目录

## 运行形态

程序打包为 Windows 单机 `.exe`。用户双击后，程序启动本地服务并打开浏览器访问本机页面，例如 `http://127.0.0.1:<port>`。

工具本身不依赖外部部署服务。数据库驱动、后端服务和前端资源随程序一起打包。

## 数据源配置

系统保存两个数据源配置，下次启动自动加载，不需要每次执行前重新填写。

### DWS 数据源

用于表名带 `_dws` 的表：

- `fa_valuationreport_dws`
- `am_pactasset_dws`
- `fa_accountbalance_dws`

默认数据库类型为 PostgreSQL，但界面允许配置为 MySQL，以便适配本地测试或后续环境变化。

### 业务数据源

用于非 `_dws` 表：

- `zf_detail_2024`
- `currency_report_duration`

默认数据库类型为 MySQL，但界面允许配置为 PostgreSQL。这样即使本地测试时把 `zf_detail_2024` 建在 PostgreSQL 的 `dws` schema 下，也可以通过配置适配。

### 配置内容

每个数据源保存：

- 数据库类型：PostgreSQL 或 MySQL
- 主机
- 端口
- 数据库名
- schema 或库名前缀
- 用户名
- 密码

表名和字段名固定在程序中，不开放给普通用户配置，降低误配概率。

配置文件保存到本机，例如程序目录的 `config/app-config.json` 或用户目录 `%APPDATA%/auto-check/config.json`。第一版密码可随配置保存，配置文件不纳入代码仓库；后续如有安全要求，可改为 Windows 凭据管理器保存密码。

## 核心字段

### `zf_detail_2024`

- 查询日期：`caldate`
- 项目编号：`projinnercode`
- 项目名称：`projname`
- 资产合计：`a0001`
- 负债及权益合计：`d0000`
- 主差异：`a0001 - d0000`

只处理主差异不等于 0 的项目。主差异保留正负号：

- 大于 0：资产大于负债及权益
- 小于 0：资产小于负债及权益

### `fa_accountbalance_dws`

- 项目编号：`c_projcode`
- 日期：`d_balancedate`
- 科目代码：`c_accountcode`
- 金额：`f_balance`

### `currency_report_duration`

- 查询日期：`caldate`
- 项目编号：`c_projectcode`
- 份额：`f_assetshare`

### `fa_valuationreport_dws`

- 项目编号：`c_projcode`
- 日期：`d_valuationdate`
- 科目代码：`c_accountcode`
- 科目名称：`c_accountname`
- 市值：`f_marketvalue`

### `am_pactasset_dws`

- 项目编号：`c_projcode`
- 日期：`d_cldate`
- 资产名称：`c_udlyasset`
- 标的代码：`c_stockcode`

## 对数流程

### 1. 读取主差异

按输入日期查询 `zf_detail_2024`：

- `caldate = 输入日期`
- 计算 `主差异 = a0001 - d0000`
- 过滤 `主差异 != 0`

每个有差异的项目进入后续判断。

### 2. FA/TA 实收优先判断

在查询估值表明细前，先判断是否属于 FA 与 TA 实收不一致。

对同一项目、同一日期：

1. 从 `fa_accountbalance_dws` 查询：
   - `d_balancedate = 输入日期`
   - `c_projcode = projinnercode`
   - `c_accountcode = '4001'`
   - 金额取 `f_balance`
2. 从 `currency_report_duration` 查询：
   - `caldate = 输入日期`
   - `c_projectcode = projinnercode`
   - 金额取 `sum(f_assetshare)`
3. 计算 `FA4001金额 - TA份额合计`

如果该差异与主差异完全相等，则：

- 差异情况：`FA与TA实收不一致`
- 匹配状态：已解释
- 不再执行估值表明细匹配和 AM 标的复核
- 明细展示 FA4001 金额、TA 份额合计、FA-TA 差异

金额比较不允许误差，必须完全相等。

### 3. 估值表匹配范围

如果 FA/TA 实收优先判断未命中，则查询 `fa_valuationreport_dws`：

- `d_valuationdate = 输入日期`
- `c_projcode = projinnercode`

默认只取末级科目，即 `c_accountcode` 中正好包含 4 个英文句点 `.` 的科目。

负差异存在特殊范围规则：

1. 当 `a0001 - d0000 < 0` 时，先查询估值表 `c_accountcode = '0004'` 的 `f_marketvalue`。
2. 如果 `a0001 != 0004资产合计`，则估值表明细匹配只保留 `c_accountcode` 以 `1` 开头且正好包含 4 个 `.` 的末级科目。
3. 如果 `a0001 = 0004资产合计`，则使用默认末级科目范围。

### 4. 估值表金额匹配

在确定匹配范围后，按以下顺序尝试解释主差异：

1. 单行匹配：某一行 `f_marketvalue = 主差异`
2. 科目汇总匹配：按末级科目代码汇总后 `sum(f_marketvalue) = 主差异`
3. 多行组合匹配：多行 `f_marketvalue` 相加等于主差异

金额比较不允许误差，必须完全相等。

多行组合匹配可能存在组合爆炸风险。第一版应设置保护策略，例如限制参与组合的行数、优先按金额绝对值筛选候选行，或在界面显示“组合候选过多，未穷举”。具体限制在实施计划中确定。

### 5. AM 标的复核

对估值表匹配出的科目继续核对 `am_pactasset_dws`。

匹配条件：

- `am_pactasset_dws.c_projcode = zf_detail_2024.projinnercode`
- `am_pactasset_dws.d_cldate = 输入日期`
- `am_pactasset_dws.c_udlyasset = fa_valuationreport_dws.c_accountname`

复核规则：

- 取估值表 `c_accountcode` 最后一个 `.` 后的代码
- 与 `am_pactasset_dws.c_stockcode` 比较

如果不一致：

- 差异情况：`FA与AM标的不一致`
- 匹配状态：已解释
- 明细展示估值科目代码、估值科目名称、科目尾段代码、AM 资产名称、AM 标的代码

如果一致，保留估值表匹配明细，但差异情况为空，后续可以继续追加其他差异原因规则。

## 结果展示

结果总览表包含：

- 项目编号
- 项目名称
- 资产合计
- 负债及权益合计
- 差异
- 差异方向
- 差异情况
- 匹配状态

差异方向显示：

- `资产大于负债及权益`
- `资产小于负债及权益`

差异情况第一版支持：

- `FA与TA实收不一致`
- `FA与AM标的不一致`
- 空

匹配状态支持：

- 已解释
- 未解释
- 部分匹配
- 组合候选过多

每行可展开查看明细：

- FA/TA 实收明细
- 估值表匹配明细
- FA/AM 标的不一致明细
- 未解释时的匹配范围和尝试结果

## 界面结构

### 配置页

- DWS 数据源配置
- 业务数据源配置
- 保存配置
- 测试连接
- 修改配置

### 执行页

- 输入对数日期
- 点击开始对数
- 显示执行进度：
  - 读取主差异
  - FA/TA 实收优先判断
  - 估值表匹配
  - AM 标的复核
  - 汇总结果

### 结果页

- 结果总览表
- 差异情况筛选
- 匹配状态筛选
- 项目编号或项目名称搜索
- 行内展开明细

第一版可以预留导出 Excel 按钮，是否实现导出在实施计划中确定。

## 建表脚本

程序运行时不自动建表，保持只查询原则。

交付物可包含 `sql/` 目录，整理以下本地测试建表脚本：

- `fa_accountbalance_dws`
- `currency_report_duration`

这些脚本用于测试环境手工建表，不由对数程序自动执行。

## 错误处理

需要处理并展示以下错误：

- 数据库连接失败
- 某个数据源配置缺失
- 表不存在
- 字段不存在
- 日期格式不合法
- 某项目缺少 FA4001 数据
- 某项目缺少 TA 份额数据
- 某项目缺少估值表数据
- 多行组合候选过多

错误应尽量落到项目级，不因单个项目失败而中断整批对数。全局连接或 SQL 语法错误除外。

## 测试策略

测试重点：

- PostgreSQL 和 MySQL 两类数据源连接
- 配置保存和自动加载
- 主差异正负号保留
- FA/TA 实收优先命中后短路
- 负差异下 `0004` 资产合计判断
- 末级科目过滤：科目代码必须正好包含 4 个 `.`
- 单行匹配
- 科目汇总匹配
- 多行组合匹配
- AM 标的代码不一致
- 未解释结果展示

## 待实施计划细化

实施计划需要进一步确定：

- 具体技术栈
- `.exe` 打包方式
- 配置文件存放路径
- 多行组合匹配的性能保护阈值
- 是否在第一版实现 Excel 导出
- 本地 Web 服务端口冲突处理
