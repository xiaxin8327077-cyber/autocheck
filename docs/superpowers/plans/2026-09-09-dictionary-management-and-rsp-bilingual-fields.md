# 字典管理与报表特殊处理双语表字段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在“系统管理”中新增可复用的字典管理能力，并让“报表特殊处理录入”从“业务系统”字典选择所属业务系统，同时强制新录入的表名、字段名包含中英文且支持多项分行展示。

**Architecture:** 平台新增字典分类、字典项存储、管理 API 和只读 `platform.dictionary` v1 服务；业务模块只能通过该服务读取启用项，不直接访问平台表。报表特殊处理记录保存业务系统代码与名称快照；表名、字段名保存为受控的规范字符串，由前后端共同解析校验，旧记录按“可读、未改可继续保存、改动后必须升级格式”的规则兼容。

**Tech Stack:** Python 3.12、SQLAlchemy、MySQL 8、原生 JavaScript/CSS、pytest、Node 前端场景测试。

## Global Constraints

- 开始实施前完整阅读 `AGENTS.md` 与 `docs/ai-modular-development-rules.zh-CN.md`。
- 用户要求本次只提供实施方案；执行阶段不得另写设计/spec 文档。
- 平台字典表、管理 API、能力码和公开服务属于平台改动；报表特殊处理业务字段和规则只允许写在 `report_special_processing` 模块内。
- 不得让模块直接导入 `storage_dictionaries.py`、直接查询平台字典表或调用平台私有方法。
- 字典管理菜单能力码固定为 `sys.dictionaries`，仅管理员默认拥有；所有已登录用户均可通过模块间只读服务消费启用字典项。
- 预置字典分类固定为 `business_system` / `业务系统`；分类不可删除、不可修改编码，字典项由管理员维护，不预置具体业务系统。
- 字典分类仅通过 `enabled` 启停；字典项支持在配置弹窗中新增、修改和删除，业务历史由记录中的编码、名称快照保证。
- 报表特殊处理正式保存时“所属业务系统”必填；草稿允许为空。新选或改选的代码必须是当前启用的 `business_system` 字典项。
- 记录保存 `business_system_code` 与 `business_system_name_snapshot`。字典项后续改名或停用不改变历史记录显示。
- 编辑旧记录时，原业务系统即使已停用，只要未改变仍允许保存其他字段；改选时只能选择启用项。
- 表名、字段名的单项规范为 `中文名｜英文名`，双语分隔符固定为全角竖线 `｜`；多项分隔符固定为全角分号 `；`。
- 新建记录的表名、字段名每一项都必须同时填写中文和英文；每类最多 5 项，单个中文名/英文名最多 100 字符，规范化后的整段最多 4096 字符，不允许名称自身包含 `｜` 或 `；`。
- 表清单与字段清单相互独立，不要求数量相等：一个表可对应多个字段，也允许多个表与多个字段；本期不引入表字段关联建模。
- 旧记录中不符合双语格式的原值继续原样展示；编辑时若该字段未发生变化可保存，发生变化则必须整体转换为新格式。
- 台账继续保持 8 列，第一列保持“修改字段名”；双语字段每个条目独占一行，历史字段名保持原样。
- 应用内大版本保持 `V1.2`，系统更新日志新增 `v1.2.25`（2026-09-09）；模块版本从 `1.2.13` 升至 `1.2.14`，模块 schema 从 6 升至 7。
- 应用内 `v1.2.25` 仅写“字典管理：新增通用字典维护并支持报表特殊处理所属业务系统配置。”及“报表特殊处理录入模块：支持业务系统选择及中英文表字段多项录入。”，如同版本已有“系统优化及BUG修复”不得重复。
- `README.md` 保留详细变更；不自动打包、不提交、不推送，除非用户另行明确要求。
- 测试和验证优先交给子代理/后台线程；主会话检查结果并修复失败。

---

## 固定接口与数据格式

### 平台表

```sql
CREATE TABLE `system_dictionaries` (
  `dictionary_code` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `dictionary_name` VARCHAR(100) NOT NULL,
  `description` VARCHAR(255) NOT NULL DEFAULT '',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `system_locked` TINYINT(1) NOT NULL DEFAULT 0,
  `sort_order` INT NOT NULL DEFAULT 0,
  `created_by` VARCHAR(64) NULL,
  `created_at` DATETIME(6) NOT NULL,
  `updated_by` VARCHAR(64) NULL,
  `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`dictionary_code`)
);

CREATE TABLE `system_dictionary_items` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `dictionary_code` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `item_code` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `item_name` VARCHAR(100) NOT NULL,
  `description` VARCHAR(255) NOT NULL DEFAULT '',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `sort_order` INT NOT NULL DEFAULT 0,
  `created_by` VARCHAR(64) NULL,
  `created_at` DATETIME(6) NOT NULL,
  `updated_by` VARCHAR(64) NULL,
  `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_system_dictionary_items_code` (`dictionary_code`, `item_code`),
  KEY `ix_system_dictionary_items_list` (`dictionary_code`, `enabled`, `sort_order`, `id`),
  CONSTRAINT `fk_system_dictionary_items_dictionary`
    FOREIGN KEY (`dictionary_code`) REFERENCES `system_dictionaries` (`dictionary_code`)
);
```

增量 SQL 必须幂等创建两表，并用 `INSERT ... ON DUPLICATE KEY UPDATE dictionary_code=dictionary_code` 写入：

```text
dictionary_code=business_system
dictionary_name=业务系统
description=报表特殊处理等功能使用的所属业务系统
enabled=1
system_locked=1
sort_order=10
```

### 管理 API

全部接口要求登录和 `sys.dictionaries`；写请求继续使用现有 CSRF 防护。

```text
GET  /api/system/dictionaries
POST /api/system/dictionaries
PUT  /api/system/dictionaries/{dictionary_code}
POST /api/system/dictionaries/{dictionary_code}/items
PUT  /api/system/dictionaries/{dictionary_code}/items/{item_id}
```

列表返回：

```json
{
  "dictionaries": [{
    "code": "business_system",
    "name": "业务系统",
    "description": "报表特殊处理等功能使用的所属业务系统",
    "enabled": true,
    "system_locked": true,
    "sort_order": 10,
    "items": [{
      "id": 1,
      "code": "valuation_system",
      "name": "估值系统",
      "description": "",
      "enabled": true,
      "sort_order": 10
    }]
  }]
}
```

分类编码与字典项编码统一校验 `^[a-z0-9][a-z0-9_]{0,63}$`，均支持纯数字；分类编码全局唯一，字典项编码在所属字典内唯一。分类名、字典项名称必填且最多 100 字符；重复编码返回 409；不存在返回 404；受锁分类拒绝修改编码，但允许维护名称和启用状态及其字典项。

### 平台只读服务

```python
DICTIONARY_SERVICE = "platform.dictionary"
DICTIONARY_SERVICE_VERSION = 1

@dataclass(frozen=True)
class PublicDictionaryItem:
    code: str
    label: str
    sort_order: int

class DictionaryFacade:
    def list_active_items(self, dictionary_code: str) -> tuple[PublicDictionaryItem, ...]: ...
    def get_active_item(self, dictionary_code: str, item_code: str) -> PublicDictionaryItem | None: ...
```

排序固定为 `sort_order, id`。facade 必须 owner-bound、可关闭，关闭后调用抛出与其他平台 facade 一致的 `RuntimeError`。

### 报表特殊处理规范串

```python
BILINGUAL_PART_SEPARATOR = "｜"
BILINGUAL_ITEM_SEPARATOR = "；"

def parse_bilingual_items(value: str) -> tuple[tuple[str, str], ...]:
    # "资产表｜fa_balance；估值表｜valuation" ->
    # (("资产表", "fa_balance"), ("估值表", "valuation"))
    ...

def serialize_bilingual_items(items: Sequence[tuple[str, str]]) -> str:
    return "；".join(f"{zh}｜{en}" for zh, en in items)
```

前端不要求用户手输分隔符，而是用可增删的双输入行录入；提交时生成上述规范串。详情、审计和导出保留规范串，台账按 `；` 拆行并将 `｜` 显示为“中文｜英文”。

---

### Task 1: 平台字典表与存储层

**Files:**
- Create: `sql/app_storage/mysql/019_dictionary_management.sql`
- Modify: `sql/app_storage/mysql/001_init_schema.sql`
- Modify: `src/auto_check/app/app_database.py`
- Create: `src/auto_check/app/storage_dictionaries.py`
- Create: `tests/test_dictionaries_storage.py`
- Modify: `tests/test_app_database.py`
- Modify: `tests/mysql_config_test_support.py`

**Interfaces:**
- Produces: `list_dictionaries(connection)`, `create_dictionary(...)`, `update_dictionary(...)`, `create_dictionary_item(...)`, `update_dictionary_item(...)`, `list_active_dictionary_items(connection, dictionary_code)`。
- All write functions receive `updated_by: str | None`; timestamps use UTC naive values, matching current application storage convention.

- [ ] **Step 1: 写存储和 schema 失败测试**

覆盖：预置 `business_system`、分类/项目排序、编码和长度校验、重复编码、启停、锁定编码不可改、无物理删除函数、启用项只读查询、`EXPECTED_APP_SCHEMA` 两张表字段完整。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_dictionaries_storage.py tests/test_app_database.py -k "dictionary"`

Expected: 因 `storage_dictionaries`、新表声明或迁移不存在而失败。

- [ ] **Step 3: 实现最小存储层**

使用 SQLAlchemy `Table` 与参数化语句；写操作放进调用者提供的事务。统一将数据库异常转换为稳定的 `ValueError` 文案，不向 API 暴露 SQL/驱动消息。`list_dictionaries()` 一次查询分类、一次查询全部项目后在内存组装，禁止逐分类 N+1。

- [ ] **Step 4: 运行 GREEN**

Run: `python -m pytest -q tests/test_dictionaries_storage.py tests/test_app_database.py`

Expected: PASS。

- [ ] **Step 5: 提交平台存储变更（仅在用户要求提交时）**

```bash
git add sql/app_storage/mysql/001_init_schema.sql sql/app_storage/mysql/019_dictionary_management.sql src/auto_check/app/app_database.py src/auto_check/app/storage_dictionaries.py tests/test_dictionaries_storage.py tests/test_app_database.py tests/mysql_config_test_support.py
git commit -m "新增系统字典存储能力"
```

### Task 2: 字典管理能力码与后端 API

**Files:**
- Modify: `src/auto_check/app/capabilities.py`
- Modify: `src/auto_check/app/server.py`
- Create: `tests/test_dictionaries_api.py`
- Modify: `tests/test_capabilities.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 存储函数。
- Produces: 固定管理 API；`sys.dictionaries` 菜单能力。

- [ ] **Step 1: 写能力和 API 失败测试**

断言：admin 默认允许、普通用户和自定义角色默认拒绝；无登录 401；无能力 403；GET 返回嵌套分类/项目；POST/PUT 正常；非法编码/名称 400；重复编码 409；不存在 404；所有写接口要求正确 CSRF。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_capabilities.py tests/test_dictionaries_api.py`

Expected: 因能力码和 API 不存在而失败。

- [ ] **Step 3: 注册能力码**

在 `CAPABILITY_DEFINITIONS` 增加：

```python
"sys.dictionaries": {"label": "字典管理", "type": TYPE_MENU},
```

将其加入 `ADMIN_ONLY_CAPABILITIES`；不要加入 `_STANDARD_TIER_TRUE`。默认 admin 列由现有生成逻辑自动为 True。

- [ ] **Step 4: 实现 API 分流和错误映射**

在 `_handle_api()` 中于模块路由前分流 `/api/system/dictionaries`；新增职责单一的 `_handle_dictionaries()`。严格解析路径段与 JSON body；响应错误只返回中文稳定文案，不返回数据库异常细节。

- [ ] **Step 5: 运行 GREEN**

Run: `python -m pytest -q tests/test_capabilities.py tests/test_dictionaries_api.py tests/test_server.py -k "dictionary or capability"`

Expected: PASS。

- [ ] **Step 6: 提交 API 变更（仅在用户要求提交时）**

```bash
git add src/auto_check/app/capabilities.py src/auto_check/app/server.py tests/test_capabilities.py tests/test_dictionaries_api.py tests/test_server.py
git commit -m "新增字典管理接口与权限"
```

### Task 3: 平台只读字典服务

**Files:**
- Modify: `src/auto_check/app/platform_services.py`
- Modify: `src/auto_check/app/server.py`
- Modify: `tests/module_system/test_collaboration.py`
- Modify: `tests/module_system/test_server_integration.py`

**Interfaces:**
- Consumes: `list_active_dictionary_items(connection, dictionary_code)`。
- Produces: `create_dictionary_service(application_database) -> PlatformServiceSpec`，服务名 `platform.dictionary`、版本 1。

- [ ] **Step 1: 写 facade 生命周期和排序失败测试**

验证：只返回启用分类下的启用项；按 `sort_order,id`；未知分类返回空 tuple；关闭后拒绝调用；两个模块获得不同 facade；服务在模块运行时可解析。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/module_system/test_collaboration.py tests/module_system/test_server_integration.py -k dictionary`

Expected: 因 `platform.dictionary` 不存在而失败。

- [ ] **Step 3: 实现和注册服务**

遵循现有 `_UserDirectoryFacade` / `create_user_directory_service()` 模式。`run_server()` 的 `platform_services` tuple 中加入 `create_dictionary_service(application_database)`，不要把数据库连接暴露给模块。

- [ ] **Step 4: 运行 GREEN**

Run: `python -m pytest -q tests/module_system/test_collaboration.py tests/module_system/test_server_integration.py -k "dictionary or user_directory"`

Expected: PASS。

- [ ] **Step 5: 提交公开服务变更（仅在用户要求提交时）**

```bash
git add src/auto_check/app/platform_services.py src/auto_check/app/server.py tests/module_system/test_collaboration.py tests/module_system/test_server_integration.py
git commit -m "开放只读字典平台服务"
```

### Task 4: 系统管理字典页面

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`
- Create: `tests/test_dictionary_management_frontend.py`

**Interfaces:**
- Consumes: Task 2 管理 API、`sys.dictionaries`。
- Produces: `loadDictionaries()`、分类列表、项目列表、新增/编辑分类弹窗、新增/编辑项目弹窗。

- [ ] **Step 1: 写前端失败测试**

断言：系统管理子菜单新增“字典管理”；页面受 `data-capability="sys.dictionaries"` 控制；`systemMgmtPages` 包含 `dictionaries`；切页会加载数据；分类和项目表格均有空态、启停状态、排序；保存使用统一 `api()`；失败保留弹窗输入并显示错误；无任何 `innerHTML` 拼接用户输入。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_web_static.py tests/test_dictionary_management_frontend.py`

Expected: 因页面和行为不存在而失败。

- [ ] **Step 3: 添加页面结构与交互**

页面主列表一个字典一行；点击配置后在同一弹窗内展示字典信息与键值表格，可连续新增多行并统一保存。顶部主操作按钮使用 Logo 蓝渐变；修改为主题色文字，删除为危险色文字，不使用光晕。所有卡片、输入框、选择框、弹窗按钮使用既有 `--ui-radius` 和语义色变量。

分类表列：字典名称、字典编码、键值数量、状态、说明、操作，不提供独立编辑入口。配置弹窗左侧直接维护字典名称和字典说明；右侧键值表列为序号、键值编码、键值名称、操作，键值输入框默认可编辑，操作仅保留删除。`business_system` 首次无键值时提示“暂无业务系统，请新增字典项”。

- [ ] **Step 4: 更新系统管理路由和能力树**

`switchPage("dictionaries")` 无权限时提示“无权访问字典管理”并回到报送导航；角色权限能力树系统管理组增加 `{ code: "sys.dictionaries", label: "字典管理", type: "menu" }`。

- [ ] **Step 5: 运行 GREEN**

Run: `python -m pytest -q tests/test_web_static.py tests/test_dictionary_management_frontend.py`

Expected: PASS。

- [ ] **Step 6: 提交前端平台变更（仅在用户要求提交时）**

```bash
git add src/auto_check/web/index.html src/auto_check/web/app.js src/auto_check/web/styles.css tests/test_web_static.py tests/test_dictionary_management_frontend.py
git commit -m "新增系统字典管理页面"
```

### Task 5: 报表特殊处理接入业务系统

**Files:**
- Create: `src/auto_check/modules/report_special_processing/migrations/007_business_system_and_bilingual_names.sql`
- Modify: `src/auto_check/modules/report_special_processing/manifest.json`
- Modify: `src/auto_check/modules/report_special_processing/module.py`
- Modify: `src/auto_check/modules/report_special_processing/contracts.py`
- Modify: `src/auto_check/modules/report_special_processing/validator.py`
- Modify: `src/auto_check/modules/report_special_processing/service.py`
- Modify: `src/auto_check/modules/report_special_processing/storage.py`
- Modify: `tests/modules/report_special_processing/test_manifest_and_migrations.py`
- Modify: `tests/modules/report_special_processing/test_validator_and_permissions.py`
- Modify: `tests/modules/report_special_processing/test_service.py`
- Modify: `tests/modules/report_special_processing/test_storage.py`

**Interfaces:**
- Consumes: `platform.dictionary` v1。
- Produces: catalog 字段 `business_systems: [{code, name}]`；记录字段 `business_system_code`、`business_system_name_snapshot`。

- [ ] **Step 1: 写迁移、catalog、保存和兼容失败测试**

覆盖：manifest 依赖 `platform.dictionary` v1、schema 7；迁移新增两个业务系统字段并把 `table_name/field_name` 改为 `TEXT`；catalog 只含启用业务系统；正式保存缺失/未知/停用代码失败；创建和改选保存名称快照；字典改名不改历史；原代码停用但未修改时允许编辑其他字段；停用后不可新选。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/modules/report_special_processing/test_manifest_and_migrations.py tests/modules/report_special_processing/test_validator_and_permissions.py tests/modules/report_special_processing/test_service.py tests/modules/report_special_processing/test_storage.py -k "business_system or migration_007 or catalog"`

Expected: 因字段、迁移和服务依赖不存在而失败。

- [ ] **Step 3: 新增模块迁移与数据契约**

迁移内容固定为：

```sql
ALTER TABLE report_special_processing_records
    ADD COLUMN business_system_code VARCHAR(64) NULL COMMENT '所属业务系统字典项编码' AFTER dimension,
    ADD COLUMN business_system_name_snapshot VARCHAR(100) NULL COMMENT '所属业务系统名称快照' AFTER business_system_code,
    MODIFY COLUMN table_name TEXT NULL COMMENT '处理表名，中文名｜英文名，多项用；分隔',
    MODIFY COLUMN field_name TEXT NULL COMMENT '处理字段名，中文名｜英文名，多项用；分隔';
```

`RecordInput` 增加 `business_system_code: str | None`。`register_schema()` 和 SQLAlchemy `RECORDS` 同步新列。

- [ ] **Step 4: 接入只读字典服务**

`module.py:start()` resolve `platform.dictionary` v1 并注入 `SpecialProcessingService`。`catalog()` 返回启用项。服务层负责代码有效性和名称快照，不把此规则放入 API 或 storage。

- [ ] **Step 5: 实现停用项兼容规则**

创建：非空代码必须 `get_active_item()` 命中。更新：若提交代码与当前记录相同，沿用当前名称快照；若不同则必须命中启用项并换快照。草稿为空允许；非空仍执行相同规则。

- [ ] **Step 6: 运行 GREEN**

Run: `python -m pytest -q tests/modules/report_special_processing/test_manifest_and_migrations.py tests/modules/report_special_processing/test_validator_and_permissions.py tests/modules/report_special_processing/test_service.py tests/modules/report_special_processing/test_storage.py`

Expected: PASS。

- [ ] **Step 7: 提交模块后端变更（仅在用户要求提交时）**

```bash
git add src/auto_check/modules/report_special_processing tests/modules/report_special_processing
git commit -m "报表特殊处理接入业务系统字典"
```

### Task 6: 中英文表字段多项录入与台账分行

**Files:**
- Create: `src/auto_check/modules/report_special_processing/bilingual_names.py`
- Modify: `src/auto_check/modules/report_special_processing/validator.py`
- Modify: `src/auto_check/modules/report_special_processing/service.py`
- Create: `src/auto_check/modules/report_special_processing/web/components/bilingual_name_list.js`
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_drawer.js`
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_table.js`
- Modify: `src/auto_check/modules/report_special_processing/web/styles.css`
- Modify: `src/auto_check/modules/report_special_processing/export_workbook.py`
- Modify: `src/auto_check/modules/report_special_processing/todos.py`
- Modify: `src/auto_check/modules/report_special_processing/history.py`
- Modify: `tests/modules/report_special_processing/test_validator_and_permissions.py`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`
- Modify: `tests/modules/report_special_processing/test_export.py`
- Modify: `tests/modules/report_special_processing/test_todos.py`
- Modify: `tests/modules/report_special_processing/test_history.py`
- Create: `tests/modules/report_special_processing/test_bilingual_names.py`

**Interfaces:**
- Produces: Python `parse_bilingual_items()` / `serialize_bilingual_items()`；前端 `parseBilingualItems()` / `serializeBilingualItems()` / `createBilingualNameList()`。

- [ ] **Step 1: 写解析与校验失败测试**

有效：单项、多项、首尾空白归一化。无效：缺中文、缺英文、重复分隔符、空项、超过 5 项、任一名称超过 100 字、总长超过 4096 字、名称包含 `｜` 或 `；`。新建和字段被修改时必须通过；旧值未改时可保留。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/modules/report_special_processing/test_bilingual_names.py tests/modules/report_special_processing/test_validator_and_permissions.py`

Expected: 因解析器与新校验不存在而失败。

- [ ] **Step 3: 实现 Python 解析器和服务兼容判断**

解析器只接受规范格式，不做模糊猜测。`validator.py` 负责请求级长度上限；`service.py` 在 create 时强制解析，在 update 时比较规范化前后的原字段：未变化且为遗留值则放行，发生变化必须解析成功。

- [ ] **Step 4: 写前端组件失败测试**

Node 场景覆盖：初始一行；增加/删除；每行中英文必填；最多 5 行；加载规范串；加载旧串时以普通输入行展示并在未编辑时保留原值；用户编辑旧值后转换成双语行；序列化固定使用 `｜` 和 `；`；错误聚焦首个无效输入。

- [ ] **Step 5: 运行前端 RED**

Run: `python -m pytest -q tests/modules/report_special_processing/test_frontend_static.py -k "bilingual or table_field"`

Expected: 因组件和展示不存在而失败。

- [ ] **Step 6: 接入录入弹窗**

“基本信息”字段顺序固定为：关联报送、所处报送期、处理人、所属维度、所属业务系统、数据治理负责人、处理编号。所属业务系统单选下拉取 `catalog.business_systems`，无可用项时显示“请先在系统管理—字典管理中维护业务系统”。

“处理表名”和“处理字段名”各使用独立可增删双语行：中文输入 placeholder 分别为“中文表名/中文字段名”，英文输入为“英文表名/英文字段名”，次要按钮“+ 添加表”“+ 添加字段”。不增加自定义主题色。

- [ ] **Step 7: 改造台账、待办、历史和导出**

第一列表头保持“修改字段名”。规范双语字段按条目分行，超过当前单元格高度仍用既有 tooltip 展示完整换行文本；无法解析的旧值沿用原字符串，不添加表名或标签。待办/通知摘要取首个字段的中文名，多项时追加“等 N 项”；Excel 中表名、字段名仍分两列，每项用换行符 `\n`，并开启单元格自动换行。

- [ ] **Step 8: 运行 GREEN**

Run: `python -m pytest -q tests/modules/report_special_processing/test_bilingual_names.py tests/modules/report_special_processing/test_frontend_static.py tests/modules/report_special_processing/test_export.py tests/modules/report_special_processing/test_todos.py tests/modules/report_special_processing/test_history.py`

Expected: PASS。

- [ ] **Step 9: 提交多项录入变更（仅在用户要求提交时）**

```bash
git add src/auto_check/modules/report_special_processing tests/modules/report_special_processing
git commit -m "支持中英文表字段多项录入"
```

### Task 7: 版本、说明、部署与总体验证

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/manifest.json`
- Modify: `src/auto_check/modules/report_special_processing/README.md`
- Modify: `docs/report-special-processing-module.zh-CN.md`
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `docs/mysql-app-storage.zh-CN.md`（若仓库实际文件名不同，使用部署文档引用的 MySQL 应用库存储文档）
- Modify: `tests/test_web_static.py`
- Modify: `tests/test_deployment_docs.py`

**Interfaces:**
- Produces: 可执行的升级顺序 `... -> 018_system_notifications.sql -> 019_dictionary_management.sql -> 模块 schema 7`。

- [ ] **Step 1: 写版本与文档失败测试**

断言：系统最新日志为 `v1.2.25` / `2026-09-09`；模块为 `1.2.14`、schema 7；README 说明字典入口、权限、业务系统快照、双语分隔符、旧数据兼容；部署序列包含 019；应用大版本仍为 `V1.2`。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest -q tests/test_web_static.py tests/test_deployment_docs.py tests/modules/report_special_processing/test_manifest_and_migrations.py -k "1_2_25 or dictionary or schema_version"`

Expected: 因版本和文档尚未同步而失败。

- [ ] **Step 3: 同步版本和说明**

模块 `release_notes.items` 仅保留模块自身两点：业务系统选择；中英文表字段多项录入与分行展示。根 README 详细写明管理入口、权限、格式、旧数据兼容、迁移和回滚。MySQL DDL 无自动 down migration；回滚前备份，代码回退后保留两张平台字典表与模块新增列，不主动删数据。

- [ ] **Step 4: 运行平台相关测试**

Run: `python -m pytest -q tests/test_dictionaries_storage.py tests/test_dictionaries_api.py tests/test_capabilities.py tests/test_app_database.py tests/test_web_static.py tests/test_dictionary_management_frontend.py tests/module_system/test_collaboration.py tests/module_system/test_server_integration.py`

Expected: PASS。

- [ ] **Step 5: 运行模块测试**

Run: `python -m pytest -q tests/modules/report_special_processing`

Expected: PASS。

- [ ] **Step 6: 运行全量测试**

Run: `python -m pytest -q`

Expected: 全部 PASS；如失败，必须区分本次回归与工作区原有失败并提供原始输出，不能仅写“环境问题”。

- [ ] **Step 7: 检查差异**

Run: `git diff --check`

Expected: 无实际 whitespace error；仅 CRLF/LF 提示可记录但不得误判为业务失败。

- [ ] **Step 8: 人工验收**

1. 管理员进入“系统管理—字典管理”，在“业务系统”中新增两个启用项目。
2. 普通用户无法看到字典管理菜单，也无法调用管理 API。
3. 新建特殊处理，所属业务系统下拉出现两个项目且位于所属维度之后。
4. 不选业务系统正式保存失败；保存草稿允许为空。
5. 添加两张表、三个字段，每项缺中文或英文均无法保存。
6. 保存后台账第一列仅显示字段名；规范双语字段逐项换行，历史字段名原样展示；详情、审计、Excel 导出一致。
7. 管理员将已使用字典项改名，旧记录仍显示原名称快照，新记录显示新名称。
8. 管理员停用已使用字典项，旧记录可在不改业务系统时修改其他内容，新建或改选不能再选择该项。
9. 打开历史旧格式记录可正常查看；不改旧表字段可保存其他内容，一旦修改则必须转换为中英文规范格式。

- [ ] **Step 9: 最终提交（仅在用户要求提交时）**

```bash
git add README.md docs src tests sql
git commit -m "新增字典管理并优化特殊处理录入"
```

不得自动执行 Windows 打包脚本，不得自动推送 GitHub/Gitee。
