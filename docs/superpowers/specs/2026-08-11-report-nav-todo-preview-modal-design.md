# 报送导航「我的待办」预览上限与全部弹窗

状态：已实施

日期：2026-08-11

分支：`feature/auto-check`（工作区 `D:\xiaxin\auto_check`）

## 1. 背景与目标

报送导航右侧「我的待办」卡片高度与左侧报送日程同步，按当前 3 行/条布局大约只能完整放下 5 条。现实现会把全部待办直接渲染进卡片，条数多时会溢出或挤压布局；标题旁「全部 >」仅为静态文案，不可点击。

目标：

1. 卡片预览最多展示 **5** 条待办。
2. 点击「全部」打开模态框查看**全部**待办。
3. **任意条数**（含 0、1～5、>5）均可点击「全部」。
4. 卡片与「全部」内「处理」均直接打开确认弹窗；从「全部」进入时「全部」保持不关。

## 2. 已确认需求

- 采用前端截断方案（不改后端 todos API 的分页模型；可扩展 action query）。
- 标题计数 `（N）` 显示**全量**条数，不是预览条数。
- 「全部」在任何条数下都可打开弹窗。
- 弹窗列表交互与卡片一致：标题、摘要、发起时间、「处理」按钮。
- 弹窗使用现有 `app-modal-overlay` / `app-modal-shell` 规范（圆角、主题色、关闭按钮）。
- **卡片与「全部」弹窗内的「处理」**：都直接打开报表特殊处理的**确认弹窗**（不再只高亮台账行）。
- 从「全部」弹窗点「处理」时：**不关闭「全部」弹窗**；确认弹窗叠在其上方。

## 3. 方案

采用方案 A：前端预览截断 + 全量弹窗 + 待办直达确认。

不采用：

- 后端 `limit` 双接口（过重）
- 卡片内滚动展开（已排除）
- 「全部」与确认互斥（关闭全部再开确认）——已按产品要求排除

## 4. 行为细节

### 4.1 预览区

- 常量：`REPORT_NAV_TODO_PREVIEW_LIMIT = 5`
- `renderReportNavTodos`：
  - 计数仍用 `items.length`
  - 列表渲染 `items.slice(0, REPORT_NAV_TODO_PREVIEW_LIMIT)`
  - 空态仍显示「暂无待办」
- 预览区不出现「还有 N 条」类额外文案（查看超出项靠「全部」）

### 4.2 「全部」入口

- 将 `.report-nav-todo-all` 从纯 `span` 改为可激活控件（`button` 或等价），保持现有视觉。
- 任意条数可点击；`0` 条时弹窗内显示「暂无待办」。

### 4.3 全部待办弹窗

- 新增 overlay，例如 `reportNavTodoAllModal`，结构对齐现有系统弹窗。
- 标题：我的待办；可显示全量计数。
- 内容区可滚动，渲染完整 `items`（与卡片同结构的行 +「处理」）。
- 关闭：右上角关闭、遮罩点击（若项目同类弹窗惯例支持）、Esc（若已有统一处理则跟齐）。
- 点「处理」：**保持「全部」打开**，再打开确认弹窗。
- 确认完成/关闭后：「全部」仍在；刷新待办后预览与「全部」列表同步重绘。

### 4.4 「处理」直达确认弹窗

现状：待办 action 为 `navigate` → `#report-special-processing?record_id=&highlight=1`，会跳转到特殊处理录入台账。

目标：

1. RSP Todo Provider 的 action query 增加直达确认标记（例如 `open=confirm`，并保留 `record_id`；`highlight` 可保留作辅助）。
2. 报送导航点「处理」时**不切换 hash / 不进入台账页**；经 `AutoCheckModuleHost.openConfirmOverlay` 在当前页直接打开确认弹窗（`todoConfirmHost` 浮层模式）。
3. 仅当 overlay API 不可用时，才回退到原 navigate / activate 路径（仍可识别 `open=confirm` 后直开确认）。
4. 卡片「处理」与「全部」内「处理」共用同一 action 处理路径。
5. 从「全部」触发时**不**调用关闭「全部」；从卡片触发时本来无「全部」层。

### 4.5 叠层（z-index）

- 「全部」使用系统弹窗层级（约 `app-modal` 量级）。
- 现有 RSP 确认遮罩在模块内约为 `z-index: 100`，低于系统弹窗，若「全部」不关会挡住确认。
- 实施要求：确认弹窗必须能点到、盖在「全部」之上。优先做法：
  - 打开确认时将 RSP 确认遮罩提升到高于「全部」的固定层级；或
  - 将确认遮罩挂到 `document.body` 并赋予更高 z-index。
- 关闭确认后恢复/移除提升，避免影响模块内普通打开确认的叠层习惯（若提升是全局样式也可统一调高 RSP 确认层级到高于系统待办弹窗，需在样式中明确数值关系）。

### 4.6 高度同步

- 继续调用 `syncReportNavigationTodoCardHeight()`；预览最多 5 条后，卡片内容不再因待办过多撑破同步高度。

## 5. 改动范围

| 文件 | 变更 |
|------|------|
| `src/auto_check/web/index.html` | 「全部」可点击；新增待办全量弹窗 markup |
| `src/auto_check/web/app.js` | 预览截断、打开/关闭全部弹窗；处理优先 openConfirmOverlay；更新日志 |
| `src/auto_check/web/module_host.js` | 暴露 `openConfirmOverlay(route, query)` |
| `src/auto_check/web/styles.css` | 全部弹窗样式；顶栏描边与内容卡一致 |
| `src/auto_check/modules/report_special_processing/todos.py` | action query 增加 `open=confirm` |
| `src/auto_check/modules/report_special_processing/web/pages/ledger.js` | `openConfirmOverlay` 浮层确认；locate/activate 回退仍可直开 |
| `src/auto_check/modules/report_special_processing/web/styles.css` | 确认遮罩层级高于「全部」弹窗；浮层不占布局 |
| `tests/...` | 预览 limit、全部可点、弹窗结构、action query、直开 confirm |
| `README.md` | 详细变更说明 |

不改：todos 聚合权限模型、确认业务规则（仍要 `rsp.confirm` + 治理负责人等现有校验）。

## 6. 验收

1. 0 条：卡片空态；点「全部」弹窗也是空态。
2. 1～5 条：卡片全部可见；点「全部」弹窗内容与卡片一致。
3. >5 条：卡片仅前 5 条；计数为全量；弹窗可见全部；第 6 条及以后只能在弹窗看到。
4. 卡片点「处理」：停留在报送导航，直接打开确认弹窗（确认态，不跳转录入页）。
5. 「全部」内点「处理」：确认弹窗打开且**「全部」仍打开**；确认在上层可操作。
6. 确认完成后：待办刷新；「全部」若仍打开则列表更新；已处理项消失。
7. `python -m pytest -q` 相关测试通过。

## 7. 非目标

- 弹窗内筛选/分页/搜索
- 待办已读状态
- 修改确认权限规则
- 强制「全部」与确认互斥关闭
