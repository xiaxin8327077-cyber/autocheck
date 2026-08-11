# 报送导航待办发起人与处理记录设计

状态：待用户确认  
日期：2026-08-11  
工作区：`D:\xiaxin\auto_check`，分支 `feature/auto-check`

## 1. 背景与目标

在「我的待办」卡片与「全部」弹窗中：

1. **全部待办弹窗**中，发起时间后展示 **发起人**（卡片预览不展示发起人）。
2. 在「全部待办」弹窗上增加 **「处理记录」** 入口，再叠一层「我的处理记录」弹窗，查询当前用户已处理完的记录。
3. **全部待办**与**处理记录**两个弹窗列表均需 **分页，每页 10 条**。

当前仅有报表特殊处理（RSP）一种处理类型；协议需可扩展，后续其它模块可注册同类处理记录，无需再改公共业务硬编码。

## 2. 已确认需求

| 项 | 约定 |
|----|------|
| 发起人 | 与处理人/创建人为同一人；取处理人快照（优先显示名，否则用户名，再否则创建人用户名）；文案「发起人」与现有「发起时间」对齐 |
| 处理记录范围（RSP 本期） | 当前用户点过「源系统已确认」、记录状态为已完成（`completed`） |
| 打开方式 | 不关「全部待办」，再开「处理记录」弹窗 |
| 入口文案 | **处理记录**（不是「我的处理记录」） |
| 列表标题（RSP） | **报表特殊处理** |
| 摘要 | `维度 · 字段`（与待办一致） |
| 时间行 | **处理时间** + **发起人** |
| 操作 | 右侧 **查看** → 只读详情（`detail`，不走确认） |
| 分页 | 全部待办、处理记录均为每页 **10** 条 |

## 3. 方案选择

采用 **平台 History Provider + 前端叠层弹窗**（相对 RSP 专用接口或同窗页签）：

- 公共层只做聚合、鉴权会话与 UI 壳。
- RSP 通过 Provider / 模块能力提供数据与只读详情打开。
- 符合 `docs/ai-modular-development-rules.zh-CN.md`：平台协议扩展单独设计；业务实现落在模块内。

## 4. 平台协议

### 4.1 TodoItem 扩展

在现有 `TodoItem` / `todo_item_payload` 增加可选字段：

- `initiator: str`（可空字符串）：发起人展示名。

校验：类型为 `str`；缺省视为 `""`。前端无值时不渲染「发起人」段。

全部待办弹窗时间行展示：

```text
发起时间：YYYY-MM-DD HH:mm:ss　发起人：张三
```

卡片预览仅展示发起时间，不展示发起人；与全部弹窗共用渲染函数，通过 `includeInitiator` 开关区分。

### 4.2 History Provider（新建）

对称于 Todo Provider：

```text
HistoryItem
  id, title, summary, actor_user_id, module_id,
  processed_at (确认/处理完成时间),
  initiator (发起人展示名),
  action: TodoAction（type=navigate；RSP 用 open=detail + record_id）

HistoryListRequest
  current_user, now

HistoryProvider.list_history(request) -> Sequence[HistoryItem]
```

- 注册：`register_history_provider(owner, provider_id, provider, semantics_version)`，冲突语义对齐 Todo。
- 聚合：仅保留 `actor_user_id == 当前用户 id` 的项；按 `processed_at` 倒序。
- Payload 字段：`id/title/summary/module_id/processed_at/initiator/action`。
- 失败隔离：单个 provider 异常记日志，不影响其它 provider 与待办。

本轮为 **平台协议缺口**，允许改动：

- `src/auto_check/app/report_navigation_platform.py`
- `src/auto_check/app/report_navigation.py`（dashboard 或独立接口挂载）
- 对应 `tests/test_report_navigation_*.py`

### 4.3 API

二选一（实施时取更小改动；推荐 B 以免撑大 dashboard）：

- **A**：dashboard 增加 `processing_history: [...]`（全量，前端分页）。
- **B（推荐）**：`GET /api/report-navigation/processing-history?page=1&page_size=10`  
  返回 `{ items, total, page, page_size }`；服务端对聚合结果切片。  
  `page_size` 固定允许值 **10**（或仅接受 10）。

全部待办：仍用 dashboard 的 `todos` 全量缓存；**仅在全部弹窗内前端按 10 条分页**（预览卡仍最多 5 条，不受分页影响）。

## 5. RSP 模块行为

### 5.1 待办发起人

`PendingConfirmTodoProvider` 写入：

- `initiator` = `creator_display_name_snapshot` 或 `creator_username_snapshot`

### 5.2 处理记录 Provider

- `provider_id` 如 `rsp_confirmed_history`
- 数据来源：审计日志中 `operator_user_id=当前用户` 且 `to_status=completed`（或等价「确认完成」动作）的记录，关联当前 `status=completed` 的台账行；按确认时间倒序。
- `title`：`报表特殊处理`
- `summary`：`{维度标签} · {字段名}`
- `processed_at`：确认发生时间（审计 `occurred_at` 或记录 `completed_at`，优先审计确认时刻）
- `initiator`：创建人快照
- `action.query`：`{ record_id, open: "detail" }`（不要 `open=confirm`）

### 5.3 「查看」打开只读详情

复用模块宿主 overlay 能力（与待办确认同类、不跳转录入页）：

- 扩展或并列：`openDetailOverlay(route, query)` / 模块 `openConfirmOverlay` 旁增加 `openDetailOverlay(recordId)`，内部 `mode: "detail"`。
- 浮层不切换 hash、不激活台账页；关闭后仍停在报送导航 + 下层弹窗。
- z-index：处理记录弹窗 > 全部待办；详情/确认浮层 ≥ 处理记录弹窗。

## 6. 前端交互

### 6.1 全部待办弹窗

- 标题区右侧增加空心主题色按钮：**处理记录**（`aria-haspopup="dialog"`）。
- 列表：每页 10 条；分页控件放列表下方（上一页 / 页码或「第 x/y 页」/ 下一页），风格对齐系统列表紧凑分页，作用域限定在该弹窗。
- 切页不关闭弹窗；刷新待办后尽量保持当前页，若超出总页则回到最后一页。

### 6.2 处理记录弹窗

- Markup：新建 overlay（如 `reportNavHistoryModal`），壳样式对齐全部待办弹窗。
- 标题：`我的处理记录` + 总数（`（N）`）。
- 列表行结构对齐待办：标题、摘要、`处理时间` + `发起人`、右侧 **查看**。
- 分页：每页 10 条（走 history API 的 page 参数，或前端切片；与 4.3 选定方案一致）。
- 关闭：右上角关闭、点遮罩；**不**关闭全部待办。
- 空态：`暂无处理记录`。
- 打开时请求/刷新数据；确认完成后若两弹窗仍开，刷新待办与处理记录。

### 6.3 卡片预览

- 卡片预览：同步展示发起时间；**不**展示发起人；**不**放「处理记录」入口（仅全部弹窗）。
- 全部待办弹窗：时间行展示发起时间 + 发起人。

## 7. 改动范围（预估）

| 区域 | 文件（示意） |
|------|----------------|
| 平台 | `report_navigation_platform.py`、`report_navigation.py` |
| RSP | `todos.py`、新建 history provider、`storage` 查询、`module.py` 注册、`web` overlay detail |
| 前端壳 | `index.html`、`app.js`、`styles.css`（分页与叠层） |
| 宿主 | `module_host.js`（如暴露 `openDetailOverlay`） |
| 测试 | 平台 todos/history、RSP、`test_web_static`、模块前端静态 |
| 文档 | 本设计、实施计划、`README.md`、应用内更新日志精简项 |

禁止：把 RSP 确认/审计查询逻辑堆进 `server.py` 业务分支以外的无协议入口；禁止其它业务模块互相 import。

## 8. 验收

1. 待办卡片预览：只显示发起时间，不显示发起人；全部弹窗：有发起人时显示在发起时间后。
2. 全部待办 >10 条时分页，每页 10；总数与标题计数一致。
3. 点「处理记录」打开上层弹窗，全部待办仍在。
4. 处理记录仅含本人确认完成的 RSP；标题为「报表特殊处理」；查看打开只读详情且不跳转录入页。
5. 处理记录分页每页 10；空态文案正确。
6. 确认一条待办后：待办减少，处理记录在刷新后可见该条。
7. `python -m pytest -q` 相关用例通过。

## 9. 非目标

- 处理记录筛选、搜索、导出
- 卡片上的处理记录入口
- 非「源系统已确认」的其它 RSP 动作（作废、编辑等）计入处理记录
- 暗色/多主题；自定义每页条数

## 10. 自检

- 无 TBD/占位未决项；分页与按钮文案已按用户补充写死。
- 与既有「待办预览/全部/确认浮层」设计兼容；确认叠层 z-index 需在实施时核对数值。
- 范围含平台协议，已标明允许改动的平台文件。
