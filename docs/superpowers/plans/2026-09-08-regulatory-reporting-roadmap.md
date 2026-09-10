# 监管报送管理模块实施总计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在监管智核中交付独立的“报送管理”模块，覆盖七类报送的报表生成、SQL 校验和配置管理，并以“资管产品模板逐笔”交付首个完整报文生成器。

**Architecture:** 先把数据源、Spider 流程和持久文件存储封装为版本化平台服务，再按独立模块规范实现长期配置、混合流程、校验和报文功能。报表生成、校验、报文生成分别建模、分别留痕，只通过报送编码和报送期关联查询，不建立统一批次或轮次。

**Tech Stack:** Python 3.12、现有本地 HTTP/模块运行时、PostgreSQL/MySQL、原生 JavaScript/CSS、pytest、openpyxl 与 BIFF8 `.xls` 写入依赖。

## Global Constraints

- 开发前完整阅读 `AGENTS.md`、`docs/ai-modular-development-rules.zh-CN.md` 和 `docs/superpowers/specs/2026-09-08-regulatory-reporting-module-design.md`。
- 普通业务代码只能放在 `src/auto_check/modules/regulatory_reporting/`，不得写入 `server.py`、`app.js`、`index.html`、全局 `styles.css` 或其他业务模块。
- 平台公共能力改动和业务模块改动分开评审；未获批准不得扩大平台 API。
- 模块 ID 固定为 `regulatory_reporting`，API 前缀固定为 `/api/modules/regulatory-reporting`，`required=false`。
- 页面只保留“报表生成、报表校验、配置管理”三个主页签；不增加“报文下载”或“执行历史”主页签。
- 配置按七类报送分别维护且不跟报送期变化；执行页只使用一个“报送期”。
- 生成、校验、报文是三类独立任务和记录，不建立统一批次，不推断底层数据是否变化，不做校验拦截。
- 生成报表默认不自动校验，只有勾选“生成完成后自动执行校验”且生成成功时，才创建一条独立的全规则校验记录。
- 校验 SQL 只允许单条只读 `SELECT` 或 `WITH ... SELECT`，每条规则独立选择数据源，返回行即错误明细。
- 试运行最多读取 5 行、默认超时 10 秒、不做完整计数、不写历史；正式执行保存完整错误明细。
- 历史、错误明细、报文文件第一阶段永久保留，不提供删除入口和自动清理任务。
- 第一阶段只有“资管产品模板逐笔”可生成完整报文；其他六类显示“该报送的报文格式尚未接入”。
- 前端只使用现有亮色活力主题、全局圆角和 `#3466D9` 到 `#6AA4FF` 的 Logo 蓝渐变；样式必须限制在 `.auto-check-module[data-module="regulatory_reporting"]`。
- 新菜单、按钮和接口必须注册能力码并同时做前后端鉴权。
- 不修改展示用大版本号；可见 UI 最终交付时同步更新 `README.md` 和当前系统更新日志。
- 不自动打包、不刷新 `dist/auto-check.exe`、不提交、不推送；只有用户明确授权相应动作后才执行。

---

## 1. 计划拆分与依赖顺序

本需求包含四个可独立评审的子系统，必须按以下顺序执行：

1. [平台公共服务计划](./2026-09-08-regulatory-reporting-platform-services.md)，包含 Kettle Basic Auth 安全封装
2. [模块基础、映射与混合流程计划](./2026-09-08-regulatory-reporting-foundation-generation.md)
3. [SQL 校验与永久明细计划](./2026-09-08-regulatory-reporting-validation.md)
4. [人行逐笔报文、页面与总验收计划](./2026-09-08-regulatory-reporting-message-ui-acceptance.md)

上一计划的专项测试通过并完成代码审查后，才能进入下一计划。每个计划都形成可运行、可测试的增量；不要把四个计划压成一个大提交。

## 2. 开发前输入门槛

### 2.1 开工即可使用的仓库依据

- 总体设计：`docs/superpowers/specs/2026-09-08-regulatory-reporting-module-design.md`
- 人行逐笔报文契约：`docs/superpowers/specs/2026-09-03-db-validation-message-export-design.md`
- 独立模块规范：`docs/ai-modular-development-rules.zh-CN.md`
- 模块参考实现：`src/auto_check/modules/report_special_processing/`
- 人行元数据映射参考：`src/auto_check/db_validation/metadata.py`
- Spider 流程参考：`src/auto_check/app/flow_tool.py`
- 已确认交互原型：`docs/prototypes/regulatory-reporting-workbench/`

### 2.2 已确认的 Kettle 启动契约与待补输入

- KJB 当前通过 `GET {base_url}/kettle/executeJob/?job={远端kjb绝对路径}&{运行参数}` 启动。
- KTR 当前通过 `GET {base_url}/kettle/executeTrans/?trans={远端ktr绝对路径}&{运行参数}` 启动。
- 当前认证为 HTTP Basic Auth；截图中的实际 Authorization 值不得复制进代码、文档、测试、日志或提交历史，实施前应轮换对应账号密码。
- `job`、`trans` 和类似 `inputdate` 的运行参数必须使用 URL query encoding；保存的步骤参数只保存参数名与模板，不保存已解析敏感值。
- PDIA 10.1 文档确认：`executeJob` 成功响应可返回 Carte ID；`executeTrans` 成功时可能返回空响应；`jobStatus/transStatus` 支持 name、可选 id、增量日志起点 from 和 `xml=Y`；`stopJob/stopTrans` 支持 name、可选 id 和 `xml=Y`。
- 仍需在实际 Pentaho 11 测试环境确认上述行为，并取得 KJB/KTR 实际启动、状态、日志和停止的脱敏响应样例，以及重复提交/幂等行为说明。
- KTR 无法取得唯一 Carte ID 时，同一远端 KTR 最多一个活动执行；不得用按名称查询的最近状态关联多个并发任务。

缺少 Pentaho 11 实测样例时，可以按 10.1 文档完成协议测试、模拟网关、流程编排和页面；不得声称完整生产联调完成，也不得猜测版本差异。

### 2.3 初始校验规则装载前必须由用户提供

- 一份最终 Excel 或 SQL 初始化文件。
- 初始化文件中每条规则对应的数据源 ID 或一份明确的数据源名称到 ID 的映射表。
- 规则编号、名称、分类、分组、级别、启用状态和 SQL 的列含义。

缺少文件时，完成版本化种子转换器及夹具测试，正式种子迁移留在未执行状态；不得生成虚构的 14,000 条生产规则。

## 3. 阶段验收门

### Gate A：平台公共服务

- [ ] `platform.data_sources` v1 只暴露脱敏目录与受限只读查询，不泄露配置对象或凭据。
- [ ] `platform.kettle_execution` v1 使用加密平台配置和 Basic Auth 调用已确认的两个启动端点，模块看不到凭据。
- [ ] `platform.flow_execution` v1 复用既有 Spider 逻辑，既有流程工具回归通过。
- [ ] `platform.artifact_storage` v1 强制模块命名空间和路径穿越防护，支持流式写入、范围读取、哈希校验和容量统计。
- [ ] 四个新增服务均可撤销；模块停止后旧 facade 调用失败。
- [ ] 平台专项测试、模块运行时测试、既有 Spider 测试通过。

### Gate B：基础配置与报表生成

- [ ] 七类报送来自 `platform.report_navigation`，模块不维护第二份名单。
- [ ] 报送数据配置只录入编码、数据源、分类编号、频率；表 ID 由分类编号自动获取。
- [ ] 映射刷新原子切换快照，失败保留上一成功快照。
- [ ] KJB、KTR、Spider 可自由混排，步骤支持超时、失败停止/继续和增量日志。
- [ ] 每类报送同一时间最多一个生成任务；Kettle 全局最多 2 步，Spider 全局最多 1 步。
- [ ] 页面关闭不终止任务，重启不重复提交已存在外部任务号的步骤。

### Gate C：SQL 校验

- [ ] 每条规则独立选择数据源；规则保存立即生效并写完整修订和字段差异审计。
- [ ] 展示字段通过零行元数据查询识别，用户可隐藏字段；涉及源表由静态解析识别。
- [ ] `${xxx}` 参数按报送期与频率解析，值参数绑定，标识符参数只接受受控值。
- [ ] 试运行最多 5 行且不写历史；正式执行统计通过、不通过、异常和完整错误条数。
- [ ] 正式错误明细压缩分块永久保存，分页只读取覆盖当前页的分块。
- [ ] 每类报送最多一个校验任务，全局最多 2 个任务、单数据源并发 4、全局 SQL 并发 16、单规则超时 120 秒。

### Gate D：报文、前端与全量验收

- [ ] “资管产品模板逐笔”一次生成 14 个 `.xlsx` 和 2 个 `.xls`，结构符合已确认契约。
- [ ] 报文生成锁定映射快照，全部文件校验通过后才登记成功版本；旧版本不覆盖。
- [ ] 其他六类隐藏报文生成操作并显示明确未接入提示。
- [ ] 生成、校验、配置三个页面按原型实现，生成和校验历史分别内嵌。
- [ ] 历史报送期仅查看和下载，没有重跑入口；当前报送期不做校验拦截。
- [ ] 能力码矩阵、后端鉴权、前端显隐、错误脱敏和任务归属测试通过。
- [ ] `python -m pytest -q` 与 `git diff --check` 通过。

## 4. 最终人工验收剧本

1. 管理员进入“报送管理”，确认左侧七类报送名称与报送导航一致。
2. 选择“资管产品模板逐笔”，配置数据源、分类编号和频率，刷新映射并核对表与字段状态。
3. 编排一条 KJB → KTR → Spider 流程，验证失败停止和失败继续两种策略。
4. 选择当前报送期执行报表生成，分别验证未勾选和勾选自动校验时的行为。
5. 同一报送期手工执行至少两次校验，确认生成记录与校验记录互不合并。
6. 打开规则配置，修改 SQL 后核对修改前/修改后差异；试运行只展示 5 条示例且不新增历史。
7. 正式执行一条大结果集规则，核对错误条数、动态列、隐藏字段、分页和完整下载。
8. 在校验失败状态下生成报文，确认系统不拦截；重新生成后保留两个文件版本。
9. 切换历史报送期，确认只能查看和下载，不能执行生成、校验或重新生成报文。
10. 切换普通用户，验证默认能查看、生成报表、停止生成、运行校验和看明细，但默认不能生成/下载报文和维护配置。
11. 切换其他六类报送，确认可以配置、生成报表和校验，但显示“该报送的报文格式尚未接入”。

## 5. 每阶段统一收尾

- [ ] 运行阶段专项测试，预期全部通过。
- [ ] 运行受影响既有回归测试，预期全部通过。
- [ ] 运行 `python -m pytest -q`，预期退出码为 0。
- [ ] 运行 `git diff --check`，预期无实际 whitespace error。
- [ ] 检查 `git status --short`，确认没有改动用户已有的原型和无关文件。
- [ ] 向用户汇报代码、配置/文档和行为变化，以及尚未完成的外部联调门槛。
- [ ] 只有用户明确要求时，才运行 Windows 打包、创建中文提交或推送远端。
