# 监管报送管理模块开发提示词

下面正文可以直接复制给负责开发的 AI。

---

你是 Auto Check（对外名称“监管智核”）项目的主开发代理。请在 `D:\xiaxin\auto_check` 中按照已确认设计和分阶段实施计划，开发独立的“报送管理”模块。

## 一、开始前必须做的事

1. 完整阅读仓库根目录 `AGENTS.md`。
2. 完整阅读 `docs/ai-modular-development-rules.zh-CN.md`。
3. 完整阅读已确认设计：
   - `docs/superpowers/specs/2026-09-08-regulatory-reporting-module-design.md`
4. 按顺序完整阅读并执行以下计划：
   - `docs/superpowers/plans/2026-09-08-regulatory-reporting-roadmap.md`
   - `docs/superpowers/plans/2026-09-08-regulatory-reporting-platform-services.md`
   - `docs/superpowers/plans/2026-09-08-regulatory-reporting-foundation-generation.md`
   - `docs/superpowers/plans/2026-09-08-regulatory-reporting-validation.md`
   - `docs/superpowers/plans/2026-09-08-regulatory-reporting-message-ui-acceptance.md`
5. 阅读“资管产品模板逐笔”报文结构契约：
   - `docs/superpowers/specs/2026-09-03-db-validation-message-export-design.md`
6. 阅读 Pentaho REST API 文档中认证、执行、状态、日志和停止章节：
   - `D:\xiaxin\wx\xwechat_files\ccqlove_5f6d\msg\file\2026-09\PDIA_REST_API_10_1_MK-95PDIA010-01 (1).pdf`
   - 重点为 PDF 页 10-11、29-30、39-40、43-44、56-57、59-60、63-64。
7. 阅读参考实现，但只借鉴结构，不跨业务模块导入私有代码：
   - `src/auto_check/modules/report_special_processing/`
   - `src/auto_check/db_validation/metadata.py`
   - `src/auto_check/app/flow_tool.py`
8. 执行 `git status --short`，保留用户已有修改和未跟踪文件；不得覆盖 `docs/prototypes/regulatory-reporting-workbench/` 或其他无关改动。
9. 如果当前目录不是独立功能 worktree，先按仓库规范创建 `codex/` 前缀的独立分支或 worktree。不要移动、重置或清理用户现有工作区。

## 二、执行方式

使用 `superpowers:executing-plans` 或 `superpowers:subagent-driven-development` 逐任务执行。严格采用 TDD：先写失败测试并确认失败，再写最小实现，再运行专项测试。

四个阶段必须依次完成：

1. 平台公共服务。
2. 模块基础、报送配置、映射和报表生成。
3. SQL 校验、动态错误明细和永久历史。
4. 资管产品模板逐笔报文、三个页面和总验收。

每个阶段完成后先停止扩展，执行该阶段专项测试、受影响回归、`python -m pytest -q` 和 `git diff --check`，然后给出审查摘要。上一阶段没有通过，不进入下一阶段。

不要一次提交全部功能，不要在平台兼容层中混入报送业务，不要在业务模块提交中修改平台协议。

## 三、不可改变的业务范围

- 新增一个顶层“报送管理”入口。
- 覆盖七类报送，名称和稳定编码必须从 `platform.report_navigation` 获取，不在模块维护第二份名单。
- 模块只保留三个主页签：报表生成、报表校验、配置管理。
- 配置管理只保留三个子页签：报送数据配置、流程编排、校验配置。
- 不新增独立“报文下载”或“执行历史”主页签。
- 生成历史放在生成页，校验历史放在校验页，报文下载放在生成记录内。
- 报表生成、SQL 校验、报文生成是三类独立任务和独立记录，不建立统一批次或轮次。
- 系统不判断底层数据是否改变，不把某次校验或报文强行绑定为某次生成的数据版本。
- 生成报表不自动生成报文。
- “生成完成后自动执行校验”默认不勾选；勾选且生成成功后，创建一条独立全规则校验记录。
- 校验不拦截报文生成或下载。
- 配置不跟报送期变化；执行页只保留一个报送期。
- 历史报送期只能查看和下载，不允许重新执行。
- 第一阶段七类报送都有配置、混合流程和 SQL 校验；只有“资管产品模板逐笔”提供完整报文格式器。
- 其他六类明确显示“该报送的报文格式尚未接入”，前后端都拒绝生成报文。
- 在线 WebSpoon/Kettle 设计器和 SVN 编辑不属于本次开发范围；该方向正在单独评估。本次只维护 KJB/KTR 远端路径、参数映射和执行。

## 四、Kettle 接口硬约束

当前生产调用模式已经确认：

```text
KJB: GET {base_url}/kettle/executeJob/?job={url_encoded_remote_kjb_path}&{url_encoded_variables}
KTR: GET {base_url}/kettle/executeTrans/?trans={url_encoded_remote_ktr_path}&{url_encoded_variables}
认证: HTTP Basic Auth
```

实现要求：

- Kettle HTTP 调用和凭据保管必须位于 `platform.kettle_execution` v1，业务模块不能读取密码或 Authorization。
- Basic Auth 密码使用平台现有 AES-GCM 机制加密保存；GET 配置和日志永不返回密码或完整 Authorization。
- 不使用 `user/pass` query 参数传输认证信息。
- `job`、`trans` 和所有 Kettle 变量都必须 URL 编码。
- `executeJob` 成功时解析 `<webresult>` 的 `result/message/id`。
- `executeTrans` 必须同时处理带 `<webresult><id>` 和成功空响应。
- 状态和增量日志使用：
  - `/kettle/jobStatus/?name=...&id=...&from=...&xml=Y`
  - `/kettle/transStatus/?name=...&id=...&from=...&xml=Y`
- 停止使用：
  - `/kettle/stopJob/?name=...&id=...&xml=Y`
  - `/kettle/stopTrans/?name=...&id=...&xml=Y`
- 保存 `first_log_line_nr/last_log_line_nr`，下一次查询的 `from` 为上次 `last_log_line_nr + 1`。
- 安全解码 `logging_string`；限制解码后大小，禁止把 Java 堆栈、生产 URL或凭据原样返回前端。
- 不能只根据 HTTP 200 判断成功；XML `result=ERROR` 或状态错误必须判失败。
- PDIA 文档版本为 10.1，必须在 Pentaho 11 测试环境做契约测试，不得直接声称兼容。
- 如果 `executeTrans` 实测不返回唯一 Carte ID，对同一规范化 KTR 路径加独占锁，禁止并发；不得用“按名称查询到的最近一次执行”关联多个任务。
- 未经用户确认不得擅自把生产启动接口改为 `/runTrans` 或其他路径。

截图中出现过真实 Basic Authorization 值。严禁复制、解码、提交或记录该值；开发联调只使用用户轮换后的测试凭据。

## 五、SQL 校验硬约束

- 每条规则独立选择数据源；修改连接只改 `data_source_id`，不改 SQL 中的库名、schema 或表名。
- 规则使用 `${xxx}` 参数，内置报送期、上期、年初、上年末等日期参数。
- 只允许单条只读 `SELECT` 或 `WITH ... SELECT`。
- 展示字段以所选数据源执行零行包装查询取得的元数据为准：

```sql
SELECT * FROM (<用户SQL>) ac_meta WHERE 1 = 0
```

- 静态解析只负责危险语句阻断、参数位置和涉及源表识别。
- 展示字段自动带出，用户可以隐藏某列；完整明细仍保存 SQL 返回的全部列。
- 试运行外层限制 5 行、超时 10 秒、不做 count、不写历史、不保存明细。
- 正式执行：0 行通过，返回 N 行则失败且错误数为 N；SQL 异常必须单列为异常，不能算通过。
- 一条规则异常不停止其他规则。
- 完整错误明细使用 gzip JSONL 分块永久保存，页面服务端分页，下载流式合并。
- 规则长期有效，只有禁用才停止；不增加定位字段、权重、有效期、自定义 SQL 开关。
- 不开发生产批量导入页面。用户提供的 Excel/SQL 只在开发期转换为一次性版本化种子迁移。
- 未收到最终初始化文件前，只完成转换器和测试，不虚构生产规则。

## 六、模块和前端边界

- 业务代码只能放入 `src/auto_check/modules/regulatory_reporting/`。
- 不在 `server.py`、`app.js`、`index.html`、全局 `styles.css` 写模块业务代码。
- 平台公共服务必须单独修改、单独测试、单独评审。
- 模块 API 前缀固定为 `/api/modules/regulatory-reporting`。
- 模块 `required=false`；模块故障不能阻止核心系统启动。
- 所有样式限制在 `.auto-check-module[data-module="regulatory_reporting"]`。
- 只使用现有亮色活力主题、全局圆角和语义色。
- 只有实心主操作按钮使用 Logo 蓝渐变 `#3466D9` 到 `#6AA4FF`。
- 不恢复暗色模式或主题切换，不使用主题光晕，不用图片代替页面组件。
- 更新日志通过模块 `manifest.release_notes` 提供，不直接修改全局 `app.js`。
- 新增的十个能力码必须注册到 `src/auto_check/app/capabilities.py` 并补全默认矩阵；前端显隐和后端 API 都要鉴权。

## 七、数据与历史硬约束

- 报送数据配置只维护报送编码、数据源 ID、分类编号、报送频率。
- 表 ID 通过分类编号查询报表信息表取得，不允许手填。
- 字段中英文名和顺序通过字段信息表取得，并校验实际物理字段。
- 映射刷新必须原子切换；失败时保留上一成功快照。
- 映射只用于报文生成，不参与 SQL 校验。
- 生成、校验、报文分别使用自己的运行表和历史表，不建统一批次表。
- 报文和错误明细第一阶段永久保留，不开发删除和自动清理。
- 每次重新生成报文都形成新版本，不覆盖旧文件。

## 八、人行逐笔报文硬约束

- “资管产品模板逐笔”必须一次生成 16 个文件：14 个 `.xlsx` 和 2 个 BIFF8 `.xls`。
- 严格遵守 `2026-09-03-db-validation-message-export-design.md` 的目录、文件名、工作表、完整列顺序、中文名、类型、格式和样式。
- 旧设计只提供输出结构契约；旧核心接口、旧弹窗和旧映射表接线不再适用。
- 新格式器必须使用报送管理模块自己的活动 mapping snapshot。
- ZG01 新增和变更来自不同物理表，不能按“信息类型”拆分同一表。
- 所有文件生成并校验成功后才发布 ZIP；任一个失败则整次失败，不提供残包。
- 参考包只提取脱敏结构，不提交生产业务数据。
- `.xls` 不能替换为 `.xlsx`。先做 BIFF8 写入库能力证明；不满足就停止并报告，不降低格式标准。

## 九、并发和恢复

- 同一报送类型同时最多一个生成任务。
- Kettle 全局最多两个活动步骤。
- Spider 全局最多一个活动步骤。
- 同一报送类型同时最多一个校验任务。
- 全局最多两个校验任务。
- 单数据源 SQL 并发最多四条。
- 全局 SQL 并发最多十六条。
- 正式单规则超时 120 秒，试运行 10 秒，字段识别 5 秒。
- 页面关闭不停止任务。
- 应用重启后先标记本地未完成任务为 interrupted；已保存外部任务 ID 的步骤只能查询状态，不能重复提交。
- 外部状态无法确认时标记 unknown，不猜成功。

## 十、测试和交付规则

每个任务：

1. 先写明确失败测试。
2. 运行该测试并记录真实失败。
3. 实现最小代码。
4. 运行专项测试并记录结果。
5. 检查接口、权限、脱敏、并发和回滚边界。

每个阶段结束运行：

```powershell
python -m pytest tests/modules/regulatory_reporting -q
python -m pytest -q
git diff --check
git status --short
```

还必须运行受影响的平台、数据库、流程、权限和静态前端测试。

不要自动执行：

- Windows 打包
- 刷新 `dist/auto-check.exe`
- Git commit
- Git push
- 部署测试或生产服务器

只有用户明确要求对应操作时才执行。获得提交授权后使用中文提交说明；获得推送授权后按仓库规则处理 GitHub 和 Gitee。

## 十一、阶段汇报格式

每完成一个阶段，向用户汇报：

1. 已完成的代码文件。
2. 数据库迁移和配置变化。
3. 页面和行为变化。
4. 运行的测试命令、通过数和失败数。
5. `git diff --check` 结果。
6. 未完成的外部依赖或 Pentaho 11 联调项目。
7. 与设计文档是否存在偏差；如有偏差，先停止并请求确认，不得自行改变需求。

现在从平台公共服务计划的 Task 1 开始。不要跳阶段，不要先写页面，不要把整个需求一次性实现。
