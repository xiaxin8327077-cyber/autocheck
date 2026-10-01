# 人行逐笔校验规则同步实施计划

> For agentic workers: use superpowers:subagent-driven-development and superpowers:test-driven-development. Follow the current directory and branch; do not create a worktree or commit automatically.

**Goal:** 将最终20260930程序的有效业务变化同步到AutoCheck，正确实现新增Rule19，并保持字段映射和结果导出一致。

**Architecture:** 沿用现有db_validation模块、中文业务字段目录、按表必需/可选字段与12字段结果协议。用户只在自己机构内校验，新查重使用产品代码和原始编码，不新增金融机构编码、数据管理机构的必需声明。保持既有空ZG12和双向余额核对。

**Tech Stack:** Python 3.12、现有pytest与openpyxl；不新增pandas依赖、数据库迁移或平台接口。

## Global Constraints

- 目标是最终更新版_20260930_457c9175，不能迁入首次包ZG12 Rule20错字段。
- 用户确认“金融机构编码”和“数据管理机构”不是必须，只做自己机构内校验；不同产品不会共用内部编码。
- 禁用Luna；初次同步由Sol负责测试、Astra负责审查；本轮遵照用户额度要求，后续实施、验证和独立审查全部使用Sol。
- 当前feature/auto-check分支继续，保留已有未跟踪内容；不建分支/worktree，不打包、提交、推送。
- 只读中文业务字段映射，不硬编码物理表名或英文字段；不改变机构字段预检。
- 编码NULL、实际NaN、原始空串判空，纯空格不空；原始编码查重不strip。NULL编码不入重复组，空串重复可同时触发两条规则。
- 五标识的数值0、纯空格都算已填；空串/NULL不算。不得直接用数值非零has_value或带strip的text判定。
- ZG04 Rule15按EXE的float绝对差严格>10，上期0也参与。未匹配上期按0，不增加输出说明；保留整个上期源不可读的已有warning。
- ZG04 Rule19仍按>20%相对变化且非零分母保护，不能被Rule15调整连带改变。
- ZG04 Rule17按EXE原始空值筛选和产品总计左连接；当期0、上期不等于0时提示，包含未匹配上期的NaN。
- ZG06 Rule14仅原始类型4/5且五标识任一已填时提示；Rule9错误描述、原始日期筛选及逐行输出与EXE一致。
- 新增ZG06 Rule17/18、ZG07 Rule19/20、ZG12 Rule19/20。正确Rule19：ZG07只由借据编码空值决定；ZG12使用其他债权内部编码正常生成明细/数据值，不输出通用规则异常。
- 退出ZG13 Rule15/16执行和现行目录；保留其他规则和仍有使用的字段。
- 同步规则登记、实现覆盖快照、规则说明Excel与对应测试，纠正ZG12说明表名。
- 完成针对性测试、全量pytest、diff检查及Sol独立审查后才能报完成；不连接真实业务DB或运行EXE。

## Task 1 完整梳理执行与映射链

- [x] 阅读db_validation全部职责和server调用边界，核对缓存、覆盖、预检、catalog、读取解密、alias、上期/依赖、执行过滤和Excel协议。
- [x] Astra独立核实架构与业务边界；主要发现记录在rhexe同步实施目录。

## Task 2 行为测试与规则实现

**Files:** rules/basic.py；tests/test_db_validation_rules_20260930.py；对应旧规则测试、ZG12测试和engine集成测试。

- [x] Sol先写测试并运行旧代码，保存预期失败证据。
- [x] 改三条条件、R9描述，局部拆开Rule15与Rule19，新增六条原值编码检查，退出ZG13两条；不全局改其他规则标准化。
- [x] 检查无需机构字段仍能通过正式字段目录执行；Rule19条件/输出/编号正确且无前序条件串扰。
- [x] 检查空ZG12正式入口和金额±方向、0.1边界保持正确。

## Task 3 目录和规则说明

**Files:** legacy_rules.py；rules_document.py；tests/test_db_validation_rule_coverage.py；tests/test_db_validation_rules_document.py。

- [x] 更新活动目录与IMPLEMENTED快照，不把快照当作运行时门。
- [x] 用实际公式、机构内分组范围和缺上期策略生成说明，纠正ZG12表单名称；先验证旧说明测试失败。
- [x] 配套更新项目业务说明和简约功能更新记录，保留当前版本；只在必要处修改日志文字，不加入公共业务逻辑。

## Task 4 整体验证和独立审查

- [x] Sol运行相关测试，再运行项目完整pytest（先确认离线安全），记录命令、退出码、输出。
- [x] 检查源码字段快照与读取字段、required/optional集合兼容及物理名防回退。
- [x] 生成未提交diff审查包，Astra核查所有实现、配套文档与测试。
- [x] 修正具体发现并运行覆盖其改动的测试；最后diff --check，记录完成状态。

**Acceptance:** 新规则、修改规则和停用规则行为与文档一致；正确Rule19正常导出；机构头字段缺失不会阻断或使新规则跳过；既有规则回归无意外变化。

## 首次同步执行记录（后续兼容口径以当前约束为准）

- 旧规则执行RED：72 failed / 78 passed；目录说明RED：16 failed / 5 passed。
- 第一版相关验证299 passed；第一版全量2593 passed / 11 skipped / 1 failed，失败为新增日志后旧静态测试条目数未更新。
- Astra终审发现Rule15小数恰好10因float相减误报，补str/Decimal/float两个方向RED：6 failed / 6 passed；局部十进制差修复，Rule19保留原float相对差。
- 修复后针对验证19 passed，最终相关316 passed（含新167场景、全部逐笔、源码字段快照和日志测试）。最终全量2610 passed / 11 skipped / 1 warning，138.71秒、退出码0；不把第一版全量当通过证据。
- 11项跳过为9项真实MySQL环境门控及2项Windows符号链接权限；1项warning为既有SQLite弃用提示。未执行真实数据库或EXE，未打包、提交或推送。
- Astra完成第二轮及最终日志独立审查，无未解决发现；P2小数边界已关闭。最终规则源SHA256：`BFD239F336BAE781D7E722D0559BDE56CC3157E73702AEB359ADCFAC4CBA1A99`，与测试前后完全一致。最终diff --check退出码0。
- 验证及审查原始记录位于 `D:/xiaxin/rhexe/同步实施_AutoCheck_20261001`。

## 真实结果差异复核及EXE一致性修订

- 用户明确要求AutoCheck保持与EXE一致，覆盖首次同步的Rule17缺失上期保护和Rule15十进制边界纠正；正确的ZG07/ZG12 Rule19及机构内范围仍按此前明确要求执行。
- 真实ZG04两期输入与EXE结果确认：Rule17共68条，16条有非零上期、52条上期完全无该产品。修改前AutoCheck为16条，差异全部来自未匹配上期NaN。
- 收益率局部raw键左连接保留全部候选；Rule15/19连接后实际缺失填0并用float，Rule17先排除实际缺失收益率再左连接、未匹配NaN仍提示。输出标识、数值列标题及情况说明跟随源程序。
- 新增编码规则同步原始明细字段、错误描述、空数据值2和原行顺序；Rule14/9原始空格筛选及完整重复行保留局部对齐，不改全局转换器。
- 回归先RED：收益率58 failed / 30 passed；首轮GREEN88 passed；扩大输出和原始值边界后RED61 failed / 201 passed。最终验证结果以本轮新日志为准，旧2610项通过记录不代替本轮验证。
- Sol终审核实Rule19零金额集合的普通浮点累加与EXE分组求和存在抵消差异，两项RED确认后，局部改用每产品补偿累加；不引入pandas或金额容差。
- 本轮审查和真实重放证据存于 `D:/xiaxin/rhexe/差异排查_Rule17_20261001`，未运行完整EXE或连接生产数据库。

### 本轮最终验证与交接

- Rule19补偿求和回归GREEN：7 passed；最终相关回归686 passed，退出码均为0。
- 真实两期ZG04按EXE读取口径调用实际生产的零金额集合及收益率规则：Rule15为140条、Rule17为68条、Rule19为3条，业务列E:K及情况说明逐条计数一致，无额外、缺失或显示差异。Excel缺失值经现有导入转NULL后的结果及零金额集合也一致。
- 真实ZG06、ZG07、ZG12选定规则重放：ZG06 Rule9为3条，Rule14及六项新增编码规则均为0条，与用户提供的EXE结果相同；有命中的新增编码边界由合成数据回归覆盖。
- 项目全量：2727 passed / 11 skipped / 1 failed / 1 warning，146.23秒、退出码1，不能记为全量通过。唯一失败为未修改的流程链测试 `test_flow_chain_status_returns_active_job_payload`：模拟执行器立即完成，读取活动状态时job已为None，测试直接读取id发生竞态。该项单独复测三次均为1 passed、退出码0；本次不修改流程链模块或测试。
- 11项跳过为9项真实MySQL环境门控及2项Windows符号链接权限；1项warning为既有SQLite弃用提示。全量执行期间源码、测试及关键文档哈希稳定；最终规则源SHA256为 `0548DB9D3DF8D8803C7C44D58F3E0C296B40750DD3B1F5E11A6EC0EC02E5CB4B`。
- 本次范围保留机构内校验及正确的ZG07/ZG12 Rule19；既有ZG12 Rule16双向金额差与EXE单向判断的差异继续单独记录，不宣称全引擎或整个Excel字节一致。不打包、提交、推送或部署。

### 后续整合验证

- 用户后续授权将人行逐笔校验引擎相关改动与对账金额显示、结果滚动条修复一并提交并推送当前分支。
- 整合后相关六文件回归为652 passed；最终全量为2813 passed、11 skipped、0 failed，153.28秒、退出码0，本次没有流程链竞态失败或警告。跳过原因仍为2项Windows符号链接权限及9项未配置真实MySQL集成环境。
- 全量测试前后五个生产文件哈希一致，JavaScript语法及空白检查通过；未连接生产业务数据库或运行完整源EXE。
