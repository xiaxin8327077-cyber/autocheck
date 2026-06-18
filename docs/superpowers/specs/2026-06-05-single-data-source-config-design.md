# 单条数据源配置设计

状态：方案 A 已确认，待实施计划
日期：2026-06-05

## 背景

当前系统数据源以“配置组”的形式保存，每个配置组固定包含 `DWS` 和 `业务库` 两条连接。普通对账功能可以使用这个模型，但数据库校验引擎需要分别配置逐笔数据、公开信息、模板数据和字段匹配数据。继续沿用“配置组 + dws/business 子来源”会让用户在同一个用途上做两次选择，容易选到错误连接，例如字段匹配数据源被选成“逐笔校验数据源 / 业务库”。

本设计将基础数据源改为单条连接配置，业务功能再按用途引用这些连接。

## 目标

- 系统数据源管理改为单条数据源配置，不再以 `DWS + 业务库` 强制成组。
- 对账功能仍然支持同时选择一个 DWS 数据源和一个业务库数据源。
- 数据库校验引擎直接配置四类用途数据源：逐笔数据源、公开信息数据源、模板数据源、字段匹配数据源。
- 旧配置自动迁移，不要求用户手工重建现有数据源。
- 保持现有密码加密存储、配置导入导出、连接测试和默认配置能力。
- 为后续模板校验预留模板数据源，不在本次实现模板校验规则。

## 非目标

- 不修改数据库校验规则本身。
- 不改变逐笔表名、公开信息表名、baseinfo 表名、field_info 表名的业务含义。
- 不改变数据库客户端对 MySQL 和 PostgreSQL 的支持方式。
- 不引入远程配置中心或多用户权限模型。

## 新配置模型

### 数据源注册表

新增单条数据源模型：

```text
DataSourceEntry
- id: 稳定唯一标识
- name: 用户可见名称
- db_type: mysql 或 postgresql
- host
- port
- database
- schema
- username
- password
- is_default: 是否默认数据源
```

`id` 用于业务配置引用，重命名数据源时不影响已有功能配置。`name` 仅用于展示。

### 对账功能配置

对账功能不再直接依赖旧的 `NamedConfig(dws, business)`。新增对账用途配置：

```text
ReconcileDataSourceSettings
- dws_source_id
- business_source_id
```

运行对账时由这两个 id 解析出 `AppConfig(dws, business)`，从而保持现有对账仓储、历史记录和连接测试逻辑可逐步兼容。

### 数据库校验引擎配置

数据库校验引擎配置改为直接引用数据源 id：

```text
DbValidationDatasetSettings
- source_id
- sys_manage_id
- classification_id

DbValidationSettings
- detail: DbValidationDatasetSettings
- public_info: DbValidationDatasetSettings
- template: DbValidationDatasetSettings
- field_mapping_source_id
- baseinfo_table
- field_info_table
- public_info_table
```

其中：

- 逐笔数据源使用 `detail.source_id`。
- 公开信息数据源使用 `public_info.source_id`。
- 模板数据源使用 `template.source_id`，本期仅预留。
- 字段匹配数据源使用 `field_mapping_source_id`。
- `sys_manage_id` 和 `classification_id` 继续支持英文分号分隔多个值。
- 固定表名仍保存在配置中，不写死在规则代码中。

## 旧配置迁移

旧配置结构：

```text
NamedConfig
- name
- dws
- business
- is_default
```

迁移为：

```text
DataSourceEntry: <name> - DWS
DataSourceEntry: <name> - 业务库
```

迁移规则：

- 每个旧配置组拆成两条数据源。
- `id` 使用稳定生成规则，例如 `legacy:<config_name>:dws` 和 `legacy:<config_name>:business`。
- 旧默认配置组里的 DWS 数据源设为默认数据源。
- 新增 `ReconcileDataSourceSettings`，指向旧默认配置组拆出的 DWS 和业务库。
- 旧 `db_validation.detail.config_name + source` 转换为 `detail.source_id`。
- 旧 `db_validation.public_info.config_name + source` 转换为 `public_info.source_id`。
- 旧 `db_validation.template.config_name + source` 转换为 `template.source_id`。
- 旧 `db_validation.field_mapping_config_name + field_mapping_source` 转换为 `field_mapping_source_id`。
- 旧密码密文原样迁移，不在迁移过程中明文落盘。

迁移在 `load_store()` 中执行一次，并通过 `save_store()` 写回新结构。

## API 调整

### 系统数据源

保留 `/api/configs` 作为前端入口，但响应语义改为单条数据源列表：

```text
GET /api/configs
POST /api/configs
DELETE /api/configs
POST /api/configs/default
GET /api/configs/export
```

为了降低改造风险，后端可以短期保留旧格式兼容：

- 读取旧格式导入文件时自动迁移。
- 如果请求体包含 `dws` 和 `business`，按旧格式拆成两条数据源保存。
- 新前端只发送单条数据源结构。

### 对账用途配置

新增或扩展设置接口：

```text
GET /api/settings/reconcile-data-sources
POST /api/settings/reconcile-data-sources
```

返回所有可选数据源和当前对账使用的 DWS、业务库数据源 id。

### 数据库校验引擎配置

现有接口继续使用：

```text
GET /api/tools/db-validation/settings
POST /api/tools/db-validation/settings
POST /api/tools/db-validation/field-mapping/refresh
POST /api/tools/db-validation/start
```

响应中的 `data_sources` 改为单条数据源列表。前端选择框不再出现 `/ DWS` 或 `/ 业务库` 后缀。

## 页面调整

### 数据源配置

系统设置中的“数据源配置”改为单条数据源列表：

- 名称
- 数据库类型
- 地址
- 端口
- 数据库
- schema
- 用户名
- 是否默认
- 编辑、删除、连接测试

新增和编辑弹窗只编辑一条连接。

### 对账配置

系统设置中增加“对账数据源设置”：

- DWS 数据源：选择一条系统数据源
- 业务库数据源：选择一条系统数据源

这样保留原有对账语义，但不再强迫所有数据源都成组维护。

### 数据库校验引擎配置

数据库校验引擎配置区域改为：

- 逐笔数据源：选择一条系统数据源
- 逐笔 `sys_manage_id`
- 逐笔 `classification_id`
- 公开信息数据源：选择一条系统数据源
- 公开信息 `sys_manage_id`
- 公开信息 `classification_id`
- 模板数据源：选择一条系统数据源
- 模板 `sys_manage_id`
- 模板 `classification_id`
- 字段匹配数据源：选择一条系统数据源
- baseinfo 表
- field_info 表
- 公开信息表
- 刷新逐笔字段映射

执行校验弹窗继续不展示逐笔数据源选择，只使用系统设置中保存的配置。

## 运行时数据流

### 对账

1. 读取 `ReconcileDataSourceSettings`。
2. 通过 `dws_source_id` 和 `business_source_id` 解析单条数据源。
3. 组装现有 `AppConfig(dws, business)`。
4. 复用现有对账执行链路。

### 数据库校验

1. 读取 `DbValidationSettings`。
2. 通过 `detail.source_id` 解析逐笔数据源。
3. 通过 `field_mapping_source_id` 解析字段匹配数据源。
4. 通过 `public_info.source_id` 解析公开信息数据源。
5. 字段映射缓存初始化或刷新时，只访问字段匹配数据源。
6. 执行校验时，逐笔表、公开信息表和元数据表各自使用已配置的数据源。

## 错误处理

- 引用的数据源不存在：保存设置时阻止，运行时也返回清晰错误。
- 删除被引用的数据源：阻止删除，并提示被哪个功能引用。
- 字段映射刷新失败：显示数据源名称、数据库/schema、baseinfo 表、field_info 表和数据库返回的首行错误。
- 旧配置迁移失败：保留原文件不覆盖，返回迁移错误，提示用户导出备份后处理。
- 导入旧配置：自动迁移为新结构。
- 导入新配置：按 `data_sources` 和用途设置直接保存。

## 测试计划

- 配置迁移测试：旧 `NamedConfig(dws, business)` 自动拆成两条数据源。
- 密码安全测试：迁移后配置文件不出现明文密码。
- 数据源 CRUD 测试：新增、编辑、删除、默认数据源。
- 引用保护测试：被对账或数据库校验引用的数据源不能删除。
- 对账兼容测试：新单条数据源配置仍可组装旧 `AppConfig`。
- 数据库校验设置测试：四类用途均保存 `source_id`，不再保存 `config_name + source`。
- 字段映射刷新测试：错误时返回可读状态，不再只显示通用“操作失败”。
- 前端静态测试：页面不再展示 `配置名 / DWS` 和 `配置名 / 业务库` 作为数据库校验选择项。
- 全量回归：`python -m pytest -q`。
- 打包验证：刷新 `dist/auto-check.exe`。

## 实施顺序建议

1. 新增单条数据源模型和旧配置迁移。
2. 增加数据源解析与对账用途配置，保证原对账功能可用。
3. 改数据库校验配置为直接引用单条数据源。
4. 调整系统设置页面和数据库校验引擎配置页面。
5. 补齐字段映射刷新失败的可读错误。
6. 全量测试并重新打包。

## 验收标准

- 系统设置中的数据源以单条连接维护，不再强制分 DWS 和业务库一组。
- 对账功能仍可配置并使用 DWS 数据源和业务库数据源。
- 数据库校验引擎配置中的逐笔、公开信息、模板、字段匹配均直接选择单条数据源。
- 执行校验界面不出现逐笔数据源选择。
- 旧配置打开后自动迁移，现有本地连接和密码可继续使用。
- 字段映射刷新不会因为误选“同配置组下的业务库”而发生歧义。
- 所有测试通过，并完成 Windows exe 打包。
