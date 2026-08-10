# 报表特殊处理：所属维度、治理负责人与待确认待办设计

状态：已实施

日期：2026-08-10

分支：`codex/report-special-processing`

## 1. 背景与目标

报表特殊处理（RSP）当前弹窗/列表仍以「涉及报表 + 处理说明」为主，且报送导航「我的待办」为静态占位，无法承接数据治理确认流程。

本轮目标：

1. 改造 RSP 弹窗基本信息与特殊处理内容字段。
2. 调整列表展示列。
3. 新增「数据治理负责人」独立字段，并按所属维度从指定角色自动带入候选人。
4. 处理人正式保存后进入「待确认」；数据治理负责人在报送导航「我的待办」收到确认待办。
5. 列表确认必须经弹窗完成，主按钮文案为「源系统已确认」。

## 2. 已确认需求

### 2.1 弹窗字段

**基本信息**

- 保留：关联报送、所处报送期、处理人
- 去掉：涉及报表
- 新增：
  - 所属维度：单选固定枚举  
    `项目端` / `资金端` / `资产端` / `财务端`
  - 数据治理负责人：与处理人独立的用户下拉
    - 维度映射角色（角色显示名精确匹配）：
      - 项目端、资产端 → `数据治理_项目资产`
      - 资金端、财务端 → `数据治理_资金财务`
    - 对应角色下有启用用户：默认随机选一人，用户可改选
    - 无对应角色或角色下无启用用户：不自动带入
    - 正式保存时必填

**特殊处理内容**

- 去掉：处理说明（`processing_content`）
- 处理摘要：最多 50 字
- 新增一组（单组，非多行）：
  - 处理表名
  - 处理字段名
  - 修改前
  - 修改后
- 正式保存时上述四项 + 摘要均必填

### 2.2 列表

仅 8 列：

`修改字段名 | 修改前 | 修改后 | 关联报送 | 状态 | 处理人 | 处理时间 | 操作`

- 不再展示：处理摘要、涉及报表、所属维度、数据治理负责人
- 筛选项：去掉涉及报表；保留状态、处理人；本轮不加维度筛选
- 确认：列表点「确认」→ 弹窗 → 主按钮「源系统已确认」；不可列表内直接确认

### 2.3 状态与权限

- 正式保存 → `pending`，界面文案改为 **待确认**（原「待处理」）
- 确认通过 → `completed`（已完成）
- `draft` / `voided` / 重开回 `pending` 保持
- `processing`：本轮 UI 不再主动进入；历史数据仍可显示
- 确认权限：必须同时具备 `rsp.confirm`，且当前用户为该条「数据治理负责人」；管理员例外可确认任意条

### 2.4 我的待办联动

- 记录为 `pending` 且 `governance_owner_user_id == 当前用户` → 产生待办
- 待办摘要示例字段：所属维度、修改字段名
- 点「处理」：跳到 RSP 列表并定位该条；用户再在列表点确认弹窗
- 确认完成或作废后待办自动消失

## 3. 方案选择

采用 **方案 1：扩展 `platform.report_navigation` 增加 Todo Provider**。

理由：

- 与现有 `register_card_provider` 模式一致
- 符合 `docs/ai-modular-development-rules.zh-CN.md` 的平台协议扩展要求
- 后续其他模块可复用待办注入

不采用独立 `platform.todo`（本轮过重），不采用核心硬编码查 RSP 表（违反模块边界）。

## 4. 数据模型

### 4.1 新增迁移 `003_dimension_governance_fields.sql`

在 `report_special_processing_records` 增加：

| 列名 | 类型建议 | 说明 |
|------|----------|------|
| `dimension` | `VARCHAR(16) NULL` | 所属维度：project/fund/asset/finance |
| `governance_owner_user_id` | `VARCHAR(64) NULL` | 数据治理负责人用户 ID |
| `governance_owner_username_snapshot` | `VARCHAR(64) NULL` | 用户名快照 |
| `governance_owner_display_name_snapshot` | `VARCHAR(64) NULL` | 显示名快照 |
| `table_name` | `VARCHAR(128) NULL` | 处理表名 |
| `field_name` | `VARCHAR(128) NULL` | 处理字段名 |
| `value_before` | `VARCHAR(500) NULL` | 修改前 |
| `value_after` | `VARCHAR(500) NULL` | 修改后 |

同步更新：

- `storage.py` Table 定义
- `manifest.json` `schema_version` → 3
- 模块 schema 注册字段集

### 4.2 维度枚举

内部码：

- `project` → 项目端
- `fund` → 资金端
- `asset` → 资产端
- `finance` → 财务端

### 4.3 兼容策略

- `reports` 子表：保留；新数据不再写入；列表/弹窗不再展示
- `processing_content`：列保留；新数据写空字符串；界面不再展示
- `summary`：应用校验上限改为 50；DB `VARCHAR(200)` 不变

## 5. 后端行为

### 5.1 Catalog

`GET /catalog` 增加：

- `dimensions`：固定枚举列表
- `governance_owner_candidates_by_dimension`：各维度对应的启用用户列表  
  （按角色显示名匹配 `数据治理_项目资产` / `数据治理_资金财务`）
- 仍返回全部启用用户供「处理人」选择

角色匹配来源：平台用户目录需能提供角色码；显示名通过角色定义映射。若平台 `user_directory` 当前只返回 id/username/display_name/active，则需在 catalog 组装时结合角色定义与用户角色查询，或最小扩展 user_directory 返回 `role` / `role_label`。

本轮约束：优先在 RSP 模块内通过已有平台用户目录 + 角色定义查询组装，避免无必要的平台服务版本跃迁；若必须扩展 `platform.user_directory`，单独注明为平台协议小改动并同步测试。

### 5.2 校验（`validator.py`）

正式保存（`save_mode=record`）必填：

- `report_process_codes`、`report_period`、`handler_user_id`
- `dimension`、`governance_owner_user_id`
- `summary`（≤50）、`table_name`、`field_name`、`value_before`、`value_after`

草稿可放宽，但字段长度仍校验。

不再要求 / 接收：`reports`、`processing_content`（若传入则忽略或校验拒绝，推荐忽略并写空，避免旧前端兼容问题；模块前端已同步升级，可直接拒绝未知关键字段——本轮采用：忽略 `reports`/`processing_content`，写空/不写子表）。

### 5.3 状态与确认

- 正式保存目标状态：`pending`（待确认）
- `can_confirm(user, record)` 调整为：
  - admin：有 `rsp.confirm` 即可
  - 非 admin：有 `rsp.confirm` 且 `user.id == record.governance_owner_user_id`
- `POST /records/{id}/status`，`target_status=completed` 时走上述校验
- 确认弹窗仅前端交互；后端仍用现有 status API

### 5.4 列表/导出

- 列表返回字段覆盖新列；前端只渲染约定 8 列
- 导出列同步调整（去掉涉及报表/处理说明，增加维度、治理负责人、表名、字段名、修改前、修改后），保持可审计

## 6. 平台 Todo Provider 协议

### 6.1 接口草案

在 `platform.report_navigation` facade 增加：

```text
register_todo_provider(
  provider_id: str,
  provider: TodoProvider,
  *,
  semantics_version: str,
) -> closeable handle
```

`TodoProvider.list_todos(request) -> list[TodoItem]`

`TodoItem` 最小字段：

- `id: str`
- `title: str`
- `summary: str`（RSP：所属维度、修改字段名）
- `assignee_user_id: str`
- `module_id: str`
- `created_at: str | None`
- `action: { type: "navigate", route: str, query: dict }`

### 6.2 Dashboard 聚合

`GET /api/report-navigation/dashboard` 增加：

```json
"todos": [
  {
    "id": "...",
    "title": "报表特殊处理待确认",
    "summary": "项目端 · 余额字段",
    "module_id": "report_special_processing",
    "action": {
      "type": "navigate",
      "route": "report-special-processing",
      "query": { "record_id": "123", "highlight": "1" }
    }
  }
]
```

仅返回 `assignee_user_id == 当前用户` 的待办。

### 6.3 前端「我的待办」

- 去掉静态 3 条 mock
- 按 `todos` 动态渲染；标题数量用真实长度
- 「处理」：按 `action` 切换到模块路由并带 query
- 空态：显示「暂无待办」

### 6.4 RSP Provider

模块 `start()` 注册 todo provider：

- 查询当前用户作为治理负责人、状态为 `pending` 的记录
- action 跳转 `report-special-processing?record_id={id}&highlight=1`
- 模块列表页读取 query：滚动/高亮该行

## 7. 前端改动范围

### 7.1 RSP 模块

- `web/components/record_drawer.js`：字段替换与维度联动负责人
- `web/components/record_table.js`：8 列；确认走弹窗
- `web/components/filters.js`：去掉涉及报表
- `web/pages/ledger.js`：确认弹窗文案「源系统已确认」；支持 `record_id` 定位
- `styles.css`：必要布局

确认弹窗要点：

- 展示关键信息（至少：关联报送、修改字段名、修改前、修改后、所属维度、处理人）
- 主按钮：**源系统已确认**
- 成功后刷新列表

### 7.2 平台前端

- `index.html` / `app.js` / `styles.css`：我的待办动态化
- `module_host.js`：如需支持带 query 的模块激活，补齐 hash/query 传递

## 8. 权限与模块声明

- 能力码不变：`rsp.view` / `rsp.detail` / `rsp.create` / `rsp.edit` / `rsp.confirm` / `rsp.reopen` / `rsp.void` / `rsp.delete`
- `manifest.json`：`schema_version: 3`；权限声明保持模块命名空间映射到 `rsp.*`
- 菜单进入仍由 `report_special_processing.view` → `rsp.view` 控制

## 9. 测试计划

1. 校验器：新字段必填、摘要 ≤50、维度枚举、负责人必填
2. 存储迁移：新列读写
3. 确认权限：负责人可确认；非负责人有能力码也拒绝；admin 可确认
4. Todo provider：pending + 负责人匹配才返回；完成后消失
5. Dashboard todos 聚合与前端静态结构测试
6. 列表列与弹窗标签静态测试
7. 相关 pytest：`tests/modules/report_special_processing/`、`tests/module_system/`、报送导航相关测试

## 10. 非目标（本轮不做）

- 多组「表名/字段/前后值」明细行
- 维度筛选器
- 独立 `platform.todo` 总线
- 修改既有角色定义种子数据（假定环境中已存在 `数据治理_项目资产` / `数据治理_资金财务` 自定义角色）
- 恢复「涉及报表」「处理说明」展示

## 11. 风险与回滚

- 风险：环境缺少指定角色名时负责人无法自动带入；已约定不自动带入，正式保存仍必填，需用户手选或先建角色
- 风险：历史记录无新字段，列表新列可能为空；可显示 `—`
- 回滚：回退迁移脚本与模块版本；平台 todo provider 注册可空实现兜底

## 12. 验收标准

1. 弹窗无「涉及报表」「处理说明」；有维度、治理负责人、表名、字段名、修改前、修改后；摘要上限 50
2. 选维度后按角色规则自动带入负责人，可改；无角色不带入
3. 列表仅 8 列
4. 处理人正式保存后状态显示「待确认」
5. 对应治理负责人在「我的待办」看到该项；摘要含所属维度与修改字段名
6. 「处理」跳转 RSP 列表并定位
7. 列表确认弹窗主按钮为「源系统已确认」；确认后状态已完成且待办消失
8. 非负责人不可确认（管理员除外）
