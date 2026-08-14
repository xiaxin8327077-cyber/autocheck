# 人行逐笔校验动态映射 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除人行逐笔校验运行代码中的生产业务物理表名和普通业务英文字段名，持久化可查看、可人工覆盖的映射关系，并保持其他功能模块完全隔离。

**Architecture:** 在 `db_validation` 功能内部建立独立映射存储、刷新服务和运行时目录。表级初始化数据由独立 MySQL SQL 文件交付；字段明细仅由刷新动作从源端元数据和实际物理列生成。执行引擎取得单个持久化快照后，通过逻辑表标识和中文字段名读取数据，人工覆盖层优先于自动映射。

**Tech Stack:** Python 3.12、SQLAlchemy、PyMySQL、原生 JavaScript/CSS、pytest、MySQL。

## Global Constraints

- 只修改人行逐笔校验范围、对应测试、SQL 和文档；不得改变其他工具或模块行为。
- 不修改 ZG09/ZG10 模板指标编码转换和匹配逻辑。
- 不修改校验规则业务条件、阈值和结果口径。
- 生产物理表名只允许存在于初始化 SQL 和测试夹具。
- 普通业务英文字段名不得作为规则正常取值入口。
- 字段映射不初始化，点击“刷新字段映射”成功后才事务保存。
- 新功能失败不得阻止应用和其他可选模块启动。
- 不自动提交、推送或打包。

---

### Task 1: 映射数据库结构与表级初始化

**Files:**
- Create: `sql/app_storage/mysql/017_db_validation_mapping.sql`
- Create: `src/auto_check/db_validation/mapping_models.py`
- Create: `src/auto_check/db_validation/mapping_storage.py`
- Test: `tests/test_db_validation_mapping_storage.py`

**Interfaces:**
- Produces: 映射快照、表关系、字段明细、人工覆盖、审计历史的存储接口。
- Produces: 13 条逐笔、4 条模板、1 条公开信息初始关系。

- [ ] 编写存储测试，验证初始关系数量、快照事务保存、覆盖优先、恢复自动映射和审计历史。
- [ ] 运行存储测试并确认失败。
- [ ] 编写独立 SQL，所有表使用 `db_validation_mapping_` 前缀，字段映射表不含初始化记录。
- [ ] 实现模型和存储接口，只访问本功能命名空间表。
- [ ] 运行存储测试并确认通过。

### Task 2: 动态表与字段刷新服务

**Files:**
- Modify: `src/auto_check/db_validation/metadata.py`
- Create: `src/auto_check/db_validation/mapping_service.py`
- Modify: `src/auto_check/db_validation/field_mapping_cache.py`
- Test: `tests/test_db_validation_mapping_service.py`
- Modify: `tests/test_db_validation_metadata.py`

**Interfaces:**
- Consumes: Task 1 的存储接口。
- Produces: `DbValidationMappingSnapshot`，含有效表目录、字段目录、统计和明细。

- [ ] 编写失败测试，覆盖按 ZGXX 解析最新逐笔表、读取实际物理列、排除技术字段、准确统计、保留人工覆盖和冲突检测。
- [ ] 扩展元数据加载结果，保留表关系和字段原始记录，不再固定返回未映射 0。
- [ ] 实现刷新服务，并在单一事务中保存完整成功快照。
- [ ] 刷新失败时保留上一成功快照并记录错误。
- [ ] 运行映射专项测试。

### Task 3: 执行引擎动态表解析

**Files:**
- Modify: `src/auto_check/db_validation/engine.py`
- Modify: `src/auto_check/db_validation/tables.py`
- Modify: `src/auto_check/app/server.py`
- Modify: `tests/test_db_validation_engine.py`
- Modify: `tests/test_db_validation_engine_public_info.py`
- Modify: `tests/test_db_validation_tables.py`

**Interfaces:**
- Consumes: 持久化快照中的 `ZGXX → 表`、`ZGXX+口径 → 模板表`、`公开信息 → 表`。
- Produces: 单任务固定快照下的动态读取行为。

- [ ] 编写失败测试，证明更换源端 ZG01 后刷新即可读取新表。
- [ ] 移除运行代码中的 `ZG_TABLES` 和模板/公开信息物理表常量。
- [ ] 引擎按快照读取逐笔、模板和公开信息表；上期命名集中在表解析层。
- [ ] 设置接口的表清单改为当前有效映射，不再返回常量。
- [ ] 运行引擎专项测试。

### Task 4: 普通业务字段改为中文逻辑字段

**Files:**
- Modify: `src/auto_check/db_validation/rules/basic.py`
- Modify: `src/auto_check/db_validation/engine.py`
- Modify: `tests/test_db_validation_rules.py`
- Modify: `tests/test_db_validation_rule_coverage.py`

**Interfaces:**
- Consumes: `逻辑表 + 中文字段名 → 当前英文字段名`。
- Preserves: ZG09 G/FB 指标和 ZG10 H 指标现有匹配。

- [ ] 增加测试，旧英文列改名、新英文列取得原中文名后规则使用新列。
- [ ] 规则普通字段仅声明中文名；动态模板指标编码保持原样。
- [ ] 读取器只向规则提供中文业务键和明确保留的动态指标键。
- [ ] 增加静态测试，禁止生产物理表名和已知普通业务英文字段重新进入规则。
- [ ] 运行规则与覆盖率测试。

### Task 5: 映射 API 与人工维护

**Files:**
- Modify: `src/auto_check/app/server.py`
- Create: `tests/test_db_validation_mapping_api.py`

**Interfaces:**
- Produces: 状态、最新映射详情、刷新、保存覆盖、恢复自动映射 API。

- [ ] 编写 API 失败测试，覆盖登录/管理员权限、详情查询、修改原因必填、保存覆盖、恢复自动映射。
- [ ] 实现最小 API 接线，业务逻辑委托映射服务。
- [ ] 执行前只阻断本次启用规则所需但未映射的中文字段。
- [ ] 运行 API 测试。

### Task 6: 系统设置映射弹框

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Test: 现有 Web 契约测试及映射页面测试。

**Interfaces:**
- Consumes: Task 5 API。
- Produces: “查看最新映射关系”按钮、按表筛选详情、管理员编辑和恢复自动映射交互。

- [ ] 增加前端契约失败测试。
- [ ] 在刷新按钮旁增加查看按钮和隔离弹框。
- [ ] 展示真实汇总与逐笔/模板/公开信息字段明细。
- [ ] 实现修改原因、保存覆盖、恢复自动映射和冲突提示。
- [ ] 运行前端契约测试。

### Task 7: 本地迁移与隔离回归验证

**Files:**
- Modify: `README.md`（仅同步实际功能变化）
- Modify: `docs/db-validation-dynamic-table-and-field-mapping-plan.zh-CN.md`（同步完成状态）

**Interfaces:**
- Validates: 本功能与其他模块隔离。

- [ ] 备份/检查本地映射表状态，执行 `017_db_validation_mapping.sql`。
- [ ] 点击等价刷新接口生成字段明细，验证数据库持久化和重启加载。
- [ ] 运行人行逐笔校验专项测试。
- [ ] 运行模块系统与 `report_special_processing` 测试，确认状态仍为 enabled。
- [ ] 运行 `python -m pytest -q` 全量测试。
- [ ] 运行 `git diff --check` 和静态硬编码扫描。
- [ ] 重启应用，验证 HTTP 200、映射接口及所有模块健康状态。
- [ ] 检查 Git 差异，确认未修改其他业务模块。
