# 2026-07-02 新需求实现方案、落地说明与问题原因定位

本文记录 2026-07-02 新需求的原因定位、确认后的实现口径和落地说明。后续排查同类问题时，以本文和 `docs/reconcile-execution-flow.zh-CN.md`、`docs/flow-bg-execution-design.zh-CN.md` 的最终说明为准。

## 范围

本次需求包含四项：

1. AM 复核在 FA 名称匹配不到 AM 标的时增加两类兜底匹配逻辑。
2. 仅调整首页“最新趋势”横轴日期显示为执行对数的日期和时间。
3. 修复流程链配置中排序超过 500 条后的流程无法通过“加入”按钮添加的问题。
4. 首页“标的不一致”统计从按项目结果条数统计，调整为同一项目多条标的不一致按多条统计。

## 落地口径

- AM 复核统一通过 AM 标的选择 helper 处理，顺序为：原名称匹配、FA 尾码匹配 AM 标的代码、江苏信托单边中文括号名称兜底；多候选标的只有在候选规则成立后，才按 AM 合同开始日最新做合同级消歧。
- AM 合同来源 `c_datasource` 只进入原始详情和导出脚本判断，不在页面展开详情中展示。
- 首页最新趋势只调整横轴标签，改为每次自动对数的执行日期和时间，不改变趋势数据来源。
- 首页“标的代码不一致”统计按结构化详情逐条累计，项目明细仍按项目结果展示，不复制虚拟行。
- 流程链配置保留初始 500 条展示上限，通过后端搜索和手工 `flow_id` 添加解决 500 条之后流程无法加入的问题。
- 流程链停止按后台任务 `job_id` 取消，停止本地流程链继续等待或提交后续流程，不强杀申报平台已提交的 `sp_task`。
- 导出处理脚本对 FA/AM 标的不一致增加合同来源前置判断：来源为 `am` 才生成 SQL，非 `am` 或为空时输出“衡泰标的不一致请联系衡泰系统处理。”；同一项目多条标的不一致按 `①②③` 编号。

## 1. AM 复核兜底匹配

### 原因定位

当前 AM 复核入口主要在 `src/auto_check/engine/reconcile.py`：

- `_asset_missing_am_check_for_row()`：资产缺失候选不唯一时，用 AM 复核确认候选组。
- `_special_purpose_vehicle_missing_reason()`：资产缺失细分时生成 AM 标的缺失、FA/AM 标的不一致、合同投融资余额等原因。
- `_matching_pact_assets()`：只按 FA 科目名称与 `am_pactasset_dws.c_udlyasset` 做名称相似匹配。

当前逻辑在名称匹配失败后直接返回 `AM标的缺失`。因此：

- FA 科目尾码其实能匹配 `am_pactasset_dws.c_stockcode` 时，不会继续找 AM 标的。
- “江苏信托”名称中括号内容不同或缺失时，会被现有括号严格匹配规则拦截。
- 现有规则文档明确“括号内容必须一致”，新需求第 ② 条应作为严格限定的例外处理，不能放宽所有名称匹配。

### 确认实现

新增一个内部 AM 标的选择 helper，供 `_asset_missing_am_check_for_row()` 和 `_special_purpose_vehicle_missing_reason()` 共用，保证候选不唯一确认链路和资产缺失细分链路口径一致。

选择顺序建议如下：

1. 先沿用现有 `_matching_pact_assets()` 名称匹配。
2. 若名称匹配成功：
   - 多候选仍按合同开始日 `d_bdate` 倒序取最新合同。
   - 后续按当前逻辑继续比对 FA 尾码、合同投融资余额、SPV DM 和报表明细。
3. 若名称匹配失败，先执行新规则 ①：
   - 用 FA 科目尾码 `valuation_row.account_tail_code` 匹配同项目、同日期 `am_pactasset_dws.c_stockcode`。
   - 若匹配到一个或多个 AM 标的，按关联 `am_projinvest_dws.d_bdate` 倒序取合同开始日最大的一条。
   - 取到后视为已找到 AM 标的，直接进入原合同投融资余额复核和后续正常链路。
4. 若规则 ① 未命中，再执行新规则 ②：
   - 仅当 FA 科目名称包含“江苏信托”时启用。
   - 该规则只处理“仅一方带中文括号、另一方不带中文括号”的场景；如果 FA 科目名称和 AM 标的名称两边都带中文括号，且括号内内容不一致，仍必须按现有严格括号规则视为不匹配。
   - 名称比较方式固定为“去中文括号后基础规范化完全相等”，不使用 0.90 相似度模糊匹配。基础规范化沿用现有口径：NFKC、去首尾空白、转小写、删除所有空白字符、删除末尾 `_...` 或 `＿...` 后缀。
   - 候选成立规则分场景处理：
     - FA 带中文括号、AM 不带中文括号：删除 FA 中文括号及括号内内容后，与 AM 名称基础规范化完全相等；命中一个或多个 AM 标的时，候选成立。
     - FA 不带中文括号、AM 带中文括号：该分支只应处理 AM 带中文括号的候选。因为规则 ② 发生在现有名称匹配失败之后，如果存在与 FA 完全对等的不带中文括号 AM 标的，前置名称匹配应已命中，不应再进入本兜底分支。实现时先筛出所有“AM 带中文括号，且 AM 去中文括号后与 FA 基础规范化完全相等”的候选；只有候选数量为 1 时候选成立，候选数量大于 1 时不放行，仍按 AM 标的缺失处理。
     - FA 和 AM 两边都不带中文括号：应由现有名称匹配命中，不进入本兜底分支。
     - FA 和 AM 两边都带中文括号：应由现有括号严格匹配处理；括号内容不一致时，不进入本兜底分支。
   - 候选成立后，还需到报表库 `zf_detail_2024` 按核对日期查询 `projname`，使用去中文括号后的名称做唯一性校验；命中条数有且仅有 1 条时，才最终视为标的名称匹配成功。
   - 最终候选集合若对应多个 AM 合同，再按现有规则关联合同表 `am_projinvest_dws`，取合同开始日 `d_bdate` 最大的一条；但不能用“最新合同”去消解前一步已经判定为候选不成立的多 AM 标的歧义。
   - 成功后进入原正常后续流程。
5. 若以上均不满足，仍按现有逻辑返回 `AM标的缺失`。

### 需要新增/调整的代码点

- `src/auto_check/engine/reconcile.py`
  - 新增去中文括号规范化 helper，例如 `_normalize_name_without_chinese_parentheses()`。
  - 新增 AM 标的选择 helper，封装“现有名称匹配 + 尾码兜底 + 江苏信托去括号兜底”。
  - 替换 `_asset_missing_am_check_for_row()` 和 `_special_purpose_vehicle_missing_reason()` 中直接调用 `_matching_pact_assets()` 的位置。
- `src/auto_check/app/repositories.py`
  - 新增按 FA 尾码匹配项目 AM 标的的仓储能力，或在引擎侧基于 `list_project_pact_assets()` 过滤 `stock_code`。
  - 新增 `zf_detail_2024` 按日期、去括号名称模糊匹配条数查询方法。
- `tests/test_reconcile.py`
  - 增加尾码匹配单条、多条取最新合同、未命中仍 AM 标的缺失的测试。
  - 增加江苏信托去中文括号名称匹配成功、报表 `projname` 多条不放行、报表无匹配不放行的测试。
  - 保留并确认现有“括号内容不同不匹配”测试只在非新规则限定条件下仍有效。
- `tests/test_repositories.py`
  - 覆盖新 `zf_detail_2024.projname` 查询方法。
- `docs/reconcile-execution-flow.zh-CN.md`
  - 同步更新 AM 标的匹配顺序和两个兜底分支。
- `README.md` 和 `src/auto_check/web/app.js` 更新日志
  - 本次涉及核心对数逻辑和可见说明，实施后需同步版本说明；应用内更新日志按项目约定精简为具体功能 + “系统优化及BUG修复”。

### 风险与边界

- 规则 ① 按标的代码兜底会绕过名称一致性，因此必须只在名称匹配失败后执行。
- 规则 ② 必须限定“中文括号”而非英文括号，且只允许“仅一方带中文括号”的补偿匹配；两边都有括号但括号内容不同的场景仍不能匹配，避免破坏现有括号严格匹配。多 AM 标的歧义必须先按候选成立规则判断，只有候选成立后才能再用合同开始日最新做合同级消歧。
- `zf_detail_2024.projname` 模糊匹配只作为唯一性闸门，不建议用它返回的项目替换当前项目。

## 2. 首页“最新趋势”横轴显示执行日期时间

### 原因定位

首页趋势在 `src/auto_check/web/app.js`：

- `renderChart()` 对应“最新趋势/执行趋势”中按某一核对日期展示当日多次执行。
- 当前横轴标签为：
  - `formatChartMonthDay(targetDate)` 加 `run_at` 的时分。
- 需求要求仅首页最新趋势改 X 轴日期显示为执行对数的日期和时间，其他不变。

当前如果 `run_date` 与真实执行日期不同，横轴前半段使用的是核对日期，不是执行时间所属日期。

### 确认实现

仅修改 `renderChart()` 的 `labels` 生成逻辑：

- 使用每条历史记录的 `run_at` 作为横轴来源。
- 标签格式保持紧凑，建议为 `MM/DD HH:mm`。
- tooltip 仍使用完整执行时间和差异数，现有逻辑基本可保留。
- 不调整底部多指标统计 `renderTrendChart()`，也不调整日期下拉框筛选逻辑。

### 需要新增/调整的代码点

- `src/auto_check/web/app.js`
  - 修改 `renderChart()` 中 `labels = dateRuns.map(...)` 的取值。
  - 若 `run_at` 缺失，则兜底使用 `targetDate + run_at.slice(11,16)` 或原有核对日期。
- `tests/test_web_static.py`
  - 更新静态断言：不再要求横轴标签使用 `targetDate`，改为断言使用 `r.run_at`/`formatDisplayTime` 生成标签。
- `README.md` 和应用内更新日志
  - 可见 UI 变化，实施后同步。

## 3. 流程链超过 500 条后无法加入

### 原因定位

流程表读取链路如下：

- `src/auto_check/app/flow_tool.py`
  - `DatabaseFlowGateway.list_flows(keyword="", limit=500)` 默认限制 500 条。
  - SQL 按 `ORDER BY name, id LIMIT %s` 返回。
- `src/auto_check/app/server.py`
  - `_load_flow_definitions()` 调用 `gateway.list_flows(keyword)`，没有传更大 limit 或分页参数。
- `src/auto_check/web/app.js`
  - `loadFlowDefinitionsForEditor()` 首次只加载 `/api/tools/flow/definitions` 的前 500 条。
  - “加入”按钮只能对当前渲染出的流程添加。
  - 搜索虽然会再次请求后端，但仍受默认 500 条限制；无搜索时排序 500 条后的流程不可见，也就无法加入。

### 确认实现

采用“搜索优先 + 可见提示”的轻量方案：

1. 保留初始加载 500 条，避免一次性渲染过多流程导致弹框卡顿。
2. 后端接口返回 `limit` 和 `truncated` 信息：
   - 当无关键字且结果达到 500 条时，前端显示“仅展示前 500 条，请搜索流程名称或 flow_id 添加更多流程”。
3. 搜索接口支持按关键字查询 `id` 或 `name`，仍限制 500 条，但只要用户输入 flow_id 或名称关键字，就能查到排序 500 条以后的流程。
4. 前端搜索框 placeholder 改为“搜索流程名称或 flow_id”。
5. 如仍担心流程名重复或关键字无法命中，补一个“按 flow_id 添加”的兜底输入或按钮，直接把输入的 flow_id 加入已选列表。

### 已比较方案

- 方案 A：直接把后端 limit 从 500 提高到 5000。
  - 优点：改动小。
  - 缺点：流程表很大时弹框加载和渲染变慢。
- 方案 B：后端分页，前端滚动加载。
  - 优点：体验完整。
  - 缺点：改动较大，需要页码、加载状态和边界测试。
- 方案 C：最终采用方案，保留 500 初始列表，强化搜索和 flow_id 兜底添加。
  - 优点：改动小、性能稳、能解决 500 条后无法添加。

### 需要新增/调整的代码点

- `src/auto_check/app/flow_tool.py`
  - 可增加返回总量或是否截断的能力；或查询 `limit + 1` 判断是否截断。
- `src/auto_check/app/server.py`
  - `/api/tools/flow/definitions` 返回 `flows` 外增加 `limit`、`truncated`。
- `src/auto_check/web/index.html`
  - 搜索框文案调整。
  - 如采用兜底输入，新增 flow_id 输入和添加按钮。
- `src/auto_check/web/app.js`
  - 渲染截断提示。
  - 搜索结果并入 `flowDefinitions` 的现有逻辑保留。
  - 如采用兜底输入，新增事件处理并复用 `addFlowDefinitionToSelected()`。
- `tests/test_server.py`
  - 增加接口返回截断信息测试。
- `tests/test_web_static.py`
  - 增加搜索 flow_id、截断提示、兜底添加入口的静态断言。
- `docs/flow-bg-execution-design.zh-CN.md`
  - 流程链配置逻辑变化需同步说明。
- `README.md` 和应用内更新日志
  - 可见 UI/行为变化，实施后同步。

## 4. 首页“标的不一致”统计按多条标的不一致计数

### 原因定位

首页统计在 `src/auto_check/web/app.js`：

- `homeSpecificReasonMatchesTargetCode(item)` 只判断某条结果是否包含 FA/AM 标的不一致。
- `homeReasonCategoryFromItem()` 将这条结果归入 `targetCode`。
- `buildHomeReasonSummary()` 对每条结果 `summary[category.key] += 1`。
- `buildHomeResultGroups()` 也只把整条结果放入 `groups.targetCode`。

所以同一个项目结果中即使 `details` 或 `asset_missing_refinement.rows` 有多条 FA/AM 标的不一致，首页卡片仍只统计 1 条。

### 确认实现

新增一个专门的计数 helper，例如 `homeTargetCodeMismatchCount(item)`：

- 优先扫描结构化明细：
  - `item.details[*].kind === "fa_am"` 计 1。
  - `asset_missing_refinement` 的 `rows/refinement_rows` 中，`reason` 或 `check_result` 为 `FA和AM标的不一致` 的行逐条计数。
  - `display_details` 表格中如只有展示明细，也按表格行中的同类文字计数。
- 如果结构化明细没有行级信息，但文本包含 FA/AM 标的不一致，则兜底计 1。

统计口径调整：

- 首页顶部“标的代码不一致”数字使用多条计数。
- 报送期统计弹框里的“标的代码不一致”使用同一计数。
- 差异分类仍可把项目结果归到 `targetCode` 分组，用于点击后展示项目明细；展示条数可以显示多条计数，但明细列表仍展示项目结果，不复制多行。
- 从首页跳转到自动对数结果列表时仍按项目过滤，避免结果列表出现虚拟重复行。

### 需要新增/调整的代码点

- `src/auto_check/web/app.js`
  - 新增 `homeTargetCodeMismatchCount(item)`。
  - `buildHomeReasonSummary()` 中 `targetCode` 改用该 count 累加。
  - `summarizeHomeRunForReport()` 间接受益于 `buildHomeReasonSummary()`。
  - `combinedCounts.targetCode` 用多条计数，但 `groups.targetCode` 仍为项目列表。
- `tests/test_web_static.py`
  - 增加静态断言，确保新增 helper 存在并用于 `buildHomeReasonSummary()`。
- 可补充浏览器级或 JS 单元测试能力时，应覆盖“一个项目两条 FA/AM 标的不一致，首页显示 2，项目明细仍显示 1 个项目”的行为。
- `README.md` 和应用内更新日志
  - 可见统计口径变化，实施后同步。

## 验证说明

实现后需要执行以下验证：

1. 后端单元测试：
   - `python -m pytest tests/test_reconcile.py tests/test_repositories.py tests/test_server.py -q`
2. 前端静态测试：
   - `python -m pytest tests/test_web_static.py -q`
3. 全量回归：
   - `python -m pytest -q`
4. 如需要交付应用：
   - 确认无 `dist\auto-check.exe` 占用。
   - 运行 `powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1`。

## 已确认事项

1. 第 3 项流程链修复采用“初始 500 + 搜索 flow_id/name + flow_id 兜底添加”的轻量方案。
2. 第 4 项只改变首页统计数字，不在项目明细和自动对数结果列表中复制虚拟多行。
