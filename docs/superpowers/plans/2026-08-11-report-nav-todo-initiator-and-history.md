# 报送导航待办发起人与处理记录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 待办展示发起人；全部待办弹窗增加「处理记录」叠层弹窗（本人确认完成记录）；两弹窗均分页每页 10 条；查看打开只读详情且不跳转录入页。

**Architecture:** 扩展平台 TodoItem（`initiator`）并新增 History Provider 协议与 `GET /api/report-navigation/processing-history`；RSP 注册确认历史 Provider；前端全部待办客户端分页 + 处理记录服务端分页；宿主暴露 `openDetailOverlay`。

**Tech Stack:** Python 平台协议 / pytest；静态前端 `app.js`/`index.html`/`styles.css`；RSP 模块 storage/audit；`module_host.js`。

**Spec:** `docs/superpowers/specs/2026-08-11-report-nav-todo-initiator-and-history-design.md`

## Global Constraints

- 工作区：`D:\xiaxin\auto_check`，分支 `feature/auto-check`
- 入口按钮文案固定：**处理记录**
- 处理记录标题（RSP）：**报表特殊处理**
- 操作按钮：**查看** → `open=detail` 只读，禁止 `open=confirm`
- 分页：全部待办与处理记录均为 **每页 10 条**
- 处理记录范围：当前用户审计确认至 `completed` 且记录仍为 `completed`
- 遵守 `docs/ai-modular-development-rules.zh-CN.md`：业务在模块内，平台只做协议
- 应用内更新日志精简；`README.md` 写详细
- **不要主动 git commit / push**，除非用户明确要求
- 每任务结束后跑该任务指定的 pytest；全部完成后 `python -m pytest -q`

## File Map

| File | Responsibility |
|------|----------------|
| `src/auto_check/app/report_navigation_platform.py` | `initiator`；`HistoryItem`/`HistoryProvider`/`collect_history_payloads`/`paginate` |
| `src/auto_check/app/report_navigation.py` | `register_history_provider`；`processing_history(page)` |
| `src/auto_check/app/server.py` | 注册 GET processing-history（仅路由挂载，无业务） |
| `src/auto_check/modules/report_special_processing/todos.py` | 待办填 `initiator` |
| `src/auto_check/modules/report_special_processing/history.py` | 新建：确认历史 Provider |
| `src/auto_check/modules/report_special_processing/storage.py` | `list_confirmed_history_for_operator` |
| `src/auto_check/modules/report_special_processing/module.py` | 注册/注销 history provider |
| `src/auto_check/modules/report_special_processing/web/*` | `openDetailOverlay` / `open=detail` |
| `src/auto_check/web/module_host.js` | `openDetailOverlay(route, query)` |
| `src/auto_check/web/index.html` | 处理记录弹窗 markup；全部待办分页容器与「处理记录」按钮 |
| `src/auto_check/web/app.js` | 发起人渲染；双弹窗分页；history API；查看 action |
| `src/auto_check/web/styles.css` | 弹窗分页与叠层 z-index |
| tests / README | 覆盖与说明 |

---

### Task 1: Platform TodoItem `initiator` + History Provider + API

**Files:**
- Modify: `src/auto_check/app/report_navigation_platform.py`
- Modify: `src/auto_check/app/report_navigation.py`
- Modify: `src/auto_check/app/server.py`（仅增加路由分支）
- Modify: `tests/test_report_navigation_todos.py`（或新建 `tests/test_report_navigation_history.py`）

**Interfaces:**
- Produces:
  - `TodoItem(..., initiator: str = "")`
  - `HistoryItem(id, title, summary, actor_user_id, module_id, processed_at, initiator, action)`
  - `HistoryListRequest(current_user, now)`
  - `HistoryProvider.list_history(request) -> Sequence[HistoryItem]`
  - `collect_history_payloads(registry, current_user=, now=) -> list[dict]`
  - `paginate_items(items, *, page: int, page_size: int) -> dict` with keys `items,total,page,page_size`
  - `ReportNavigationService.register_history_provider(**kwargs)`
  - `ReportNavigationService.processing_history(*, current_user, page=1, page_size=10, now=None) -> dict`
  - HTTP: `GET /api/report-navigation/processing-history?page=1&page_size=10`

- [ ] **Step 1: 写失败测试（initiator payload + history 聚合分页）**

```python
def test_todo_payload_includes_initiator():
    item = TodoItem(
        id="t1", title="标题", summary="摘要",
        assignee_user_id="u1", module_id="m",
        created_at=None, action=TodoAction("navigate", "r", {}),
        initiator="张三",
    )
    payload = todo_item_payload(item)
    assert payload["initiator"] == "张三"


def test_processing_history_filters_actor_sorts_and_paginates():
    service = _service()
    bound = create_report_navigation_service(service).binder("rsp")
    now = datetime(2026, 8, 11, 12, 0, tzinfo=SHANGHAI)

    class Provider:
        def list_history(self, request):
            return [
                HistoryItem(
                    id=f"h-{i}", title="报表特殊处理", summary=f"s{i}",
                    actor_user_id="user-a" if i < 12 else "user-b",
                    module_id="report_special_processing",
                    processed_at=datetime(2026, 8, 11, i, 0, tzinfo=SHANGHAI),
                    initiator="发起人A",
                    action=TodoAction("navigate", "report-special-processing",
                                     {"record_id": str(i), "open": "detail"}),
                )
                for i in range(1, 14)
            ]

    bound.value.register_history_provider(
        provider_id="rsp_confirmed_history", provider=Provider(), semantics_version=1,
    )
    page1 = service.processing_history(
        current_user={"id": "user-a"}, page=1, page_size=10, now=now,
    )
    assert page1["total"] == 12
    assert page1["page"] == 1
    assert page1["page_size"] == 10
    assert len(page1["items"]) == 10
    assert page1["items"][0]["id"] == "h-12"  # newest first among user-a
    assert page1["items"][0]["initiator"] == "发起人A"
    assert page1["items"][0]["processed_at"]
    page2 = service.processing_history(
        current_user={"id": "user-a"}, page=2, page_size=10, now=now,
    )
    assert len(page2["items"]) == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest -q tests/test_report_navigation_todos.py tests/test_report_navigation_history.py -k "initiator or processing_history" 2>&1`  
Expected: FAIL（缺字段/缺方法）

- [ ] **Step 3: 实现平台类型、注册表、collect、paginate、service 方法、server 路由**

要点：
- `validate_todo_item` / `todo_item_payload` 读写 `initiator`（默认 `""`）。
- 复制 TodoProviderRegistry 模式为 `HistoryProviderRegistry`（或泛化，优先复制保持小改）。
- `create_report_navigation_service` binder 增加 `register_history_provider`。
- `page_size` 仅接受 `10`，非法则 400 或夹紧为 10（测试锁一种：非法 `page_size` → ValueError/400）。
- `page < 1` 当作 1；超出总页返回空 `items` 且 `page` 为请求页或最后页（锁：返回请求页、`items=[]` 若越界）。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest -q tests/test_report_navigation_todos.py tests/test_report_navigation_history.py -q`  
Expected: PASS

---

### Task 2: RSP 待办 initiator + 确认历史 Provider

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/todos.py`
- Create: `src/auto_check/modules/report_special_processing/history.py`
- Modify: `src/auto_check/modules/report_special_processing/storage.py`
- Modify: `src/auto_check/modules/report_special_processing/module.py`
- Modify: `tests/modules/report_special_processing/test_todos.py`
- Create/Modify: `tests/modules/report_special_processing/test_history.py`

**Interfaces:**
- Consumes: `HistoryItem`, `HistoryListRequest`, `register_history_provider`
- Produces:
  - `HISTORY_PROVIDER_ID = "rsp_confirmed_history"`
  - `HISTORY_TITLE = "报表特殊处理"`
  - `ConfirmedHistoryProvider.list_history`
  - `SpecialProcessingStorage.list_confirmed_history_for_operator(user_id) -> list[dict]`
    每行至少含：`id, dimension, field_name, creator_* , confirmed_at`（审计确认时刻）

- [ ] **Step 1: 失败测试**

```python
def test_todo_provider_sets_initiator_from_creator_snapshot():
    storage = FakeStorage([_record(
        creator_display_name_snapshot="王五",
        creator_username_snapshot="wangwu",
    )])
    items = PendingConfirmTodoProvider(storage).list_todos(...)
    assert items[0].initiator == "王五"


def test_history_provider_returns_only_my_completed_confirms():
    # FakeStorage.list_confirmed_history_for_operator 返回两条：一条 mine completed，过滤其它
    provider = ConfirmedHistoryProvider(storage)
    items = provider.list_history(HistoryListRequest(current_user={"id": "owner-a"}, now=...))
    assert items[0].title == "报表特殊处理"
    assert items[0].action.query == {"record_id": "1", "open": "detail"}
    assert "confirm" not in items[0].action.query.values()
```

Storage 查询逻辑（实现约束）：
- join `report_special_processing_audit_logs` + `records`
- `operator_user_id = user` AND `to_status = 'completed'` AND `records.status = 'completed'`
- 同一 `record_id` 多条确认审计时取 **最近一次** `occurred_at`
- 按 `confirmed_at` 倒序

- [ ] **Step 2: 跑测失败 → 实现 → 跑测通过**

Run: `python -m pytest -q tests/modules/report_special_processing/test_todos.py tests/modules/report_special_processing/test_history.py -q`

- [ ] **Step 3: module.start 注册 / stop 关闭 history handle**

```python
self._history_provider_handle = report_navigation.register_history_provider(
    provider_id=HISTORY_PROVIDER_ID,
    provider=ConfirmedHistoryProvider(storage),
    semantics_version=HISTORY_SEMANTICS_VERSION,
)
```

---

### Task 3: 模块宿主 + RSP `openDetailOverlay`

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/pages/ledger.js`
- Modify: `src/auto_check/modules/report_special_processing/web/index.js`
- Modify: `src/auto_check/web/module_host.js`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`
- Modify: `tests/module_system/test_frontend_host.py`

**Interfaces:**
- Produces: `openDetailOverlay(recordId) -> Promise<boolean>`（复用 `todoConfirmHost` 浮层，`mode: "detail"`）
- Host: `AutoCheckModuleHost.openDetailOverlay(route, query)`
- `app.js` 后续：`query.open === "detail"` 时调 detail；`confirm` 仍走 confirm

- [ ] **Step 1: 静态测试断言新增符号**
- [ ] **Step 2: 实现 ledger/index/host（可抽 `openRecordOverlay(recordId, mode)` 避免重复）**
- [ ] **Step 3: 跑相关静态测试通过**

Run: `python -m pytest -q tests/modules/report_special_processing/test_frontend_static.py tests/module_system/test_frontend_host.py::test_module_host_has_stable_lifecycle_contract -q`

---

### Task 4: 前端 — 发起人、全部待办分页、处理记录弹窗

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`
- Modify: `README.md`
- Modify: `app.js` 更新日志（精简：如「我的待办发起人与处理记录。」）

**Interfaces:**
- Consumes: todos[].initiator；`/api/report-navigation/processing-history`；`openDetailOverlay`
- UI:
  - 时间行：`发起时间：…` +（有值则）`发起人：…`
  - 全部待办：`REPORT_NAV_TODO_PAGE_SIZE = 10`；分页条；按钮 `处理记录`
  - 处理记录弹窗 id：`reportNavHistoryModal`；列表/分页/关闭不关全部待办
  - 行：`处理时间` + `发起人`；按钮 `查看` → `open=detail`
  - z-index：history 弹窗 > todo-all（3000）；detail overlay 保持 ≥3200

- [ ] **Step 1: 静态测试（关键字符串/选择器）**

断言示例：
- `发起人：`
- `id="reportNavHistoryModal"`
- `处理记录`
- `REPORT_NAV_TODO_PAGE_SIZE = 10`
- `processing-history`
- `openDetailOverlay`
- `处理时间：`

- [ ] **Step 2: HTML 增加处理记录弹窗与全部待办分页容器、处理记录按钮**
- [ ] **Step 3: JS 渲染与事件**
  - `buildReportNavTodoItemHtml` 增加 initiator
  - `reportNavTodoAllPage` 状态；`renderReportNavTodoAllModalList` 切片 10 条
  - `openReportNavHistoryModal` / `loadReportNavHistory(page)` / `buildReportNavHistoryItemHtml`
  - `handleReportNavTodoAction`：`open===detail` → `openDetailOverlay`
  - 刷新事件：确认成功后若 history 打开则重载当前页
- [ ] **Step 4: CSS 分页与 `#reportNavHistoryModal { z-index: 3100; }`（todo-all=3000，detail=3200）**
- [ ] **Step 5: 更新 README + 精简 changelog**
- [ ] **Step 6: 跑测试**

Run: `python -m pytest -q tests/test_web_static.py -k "report_nav_todo or history or processing_history or shared_modal" -q`  
然后：`python -m pytest -q`

---

## Spec Coverage Self-Check

| Spec 要求 | Task |
|-----------|------|
| 发起人在发起时间后 | 1 + 2 + 4 |
| 处理记录入口「处理记录」、叠层弹窗 | 4 |
| RSP 标题「报表特殊处理」、查看只读 | 2 + 3 + 4 |
| 两弹窗每页 10 条 | 1（history API）+ 4（todos 客户端） |
| History Provider 可扩展 | 1 + 2 |
| 不跳转录入页 | 3 + 4 |
| README / 更新日志 | 4 |

## Placeholder Scan

无 TBD；`page_size` 非法行为在 Task 1 锁死为「仅接受 10」。

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-11-report-nav-todo-initiator-and-history.md`.**

**执行方式二选一：**

1. **Subagent-Driven（推荐）** — 每任务新开子代理，任务间复查  
2. **Inline Execution** — 本会话按任务连续实施并设检查点  

选哪种？
