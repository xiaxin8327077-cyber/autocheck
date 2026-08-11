# RSP 维度/治理负责人/待确认待办 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改造报表特殊处理弹窗与列表字段，接通「待确认 → 我的待办 → 弹窗确认」闭环。

**Architecture:** RSP 模块新增维度/治理负责人/修改字段组；扩展 `platform.user_directory` 返回 `role`；扩展 `platform.report_navigation` 增加 Todo Provider；报送导航「我的待办」动态聚合；确认需 `rsp.confirm` + 治理负责人（admin 例外）。

**Tech Stack:** Python 3.11、SQLAlchemy/MySQL 模块迁移、原生 JS 模块前端、pytest、平台服务 facade

**Spec:** `docs/superpowers/specs/2026-08-10-rsp-dimension-governance-todo-design.md`

## Global Constraints

- 所属维度枚举：`project/fund/asset/finance` ↔ 项目端/资金端/资产端/财务端
- 角色显示名精确匹配：`数据治理_项目资产`（项目端+资产端）、`数据治理_资金财务`（资金端+财务端）
- 处理摘要最多 50 字；处理说明与涉及报表从界面移除
- 列表仅 8 列：修改字段名、修改前、修改后、关联报送、状态、处理人、处理时间、操作
- `pending` 界面文案改为「待确认」；确认弹窗主按钮「源系统已确认」
- 待办摘要：所属维度、修改字段名
- 不得把 RSP 业务 SQL 硬编码进 `server.py`；待办必须经 Todo Provider
- 前端仅亮色活力主题；圆角/主题色用现有 CSS 变量
- 改完跑相关 pytest；涉及可见 UI 时更新 `README.md`、`app.js` 更新日志、`index.html` 资源版本号

## File Map

| File | Responsibility |
|------|----------------|
| `docs/superpowers/specs/2026-08-10-rsp-dimension-governance-todo-design.md` | 已确认设计 |
| `src/auto_check/modules/report_special_processing/migrations/003_dimension_governance_fields.sql` | 新列 DDL |
| `src/auto_check/modules/report_special_processing/storage.py` | 表定义与读写 |
| `src/auto_check/modules/report_special_processing/contracts.py` | RecordInput/枚举/文案 |
| `src/auto_check/modules/report_special_processing/validator.py` | 入参校验 |
| `src/auto_check/modules/report_special_processing/permissions.py` | can_confirm(user, record) |
| `src/auto_check/modules/report_special_processing/service.py` | catalog/create/update/confirm/todos |
| `src/auto_check/modules/report_special_processing/todos.py` | TodoProvider 实现 |
| `src/auto_check/modules/report_special_processing/module.py` | 注册 todo provider |
| `src/auto_check/modules/report_special_processing/manifest.json` | schema_version=3 |
| `src/auto_check/modules/report_special_processing/web/components/*` | 弹窗/列表/筛选 |
| `src/auto_check/modules/report_special_processing/web/pages/ledger.js` | 确认弹窗与 record_id 定位 |
| `src/auto_check/app/platform_services.py` | PublicUser + role |
| `src/auto_check/app/report_navigation_platform.py` | Todo 类型与 facade API |
| `src/auto_check/app/report_navigation.py` | todo 注册与 dashboard 聚合 |
| `src/auto_check/web/index.html` / `app.js` / `styles.css` | 我的待办动态渲染 |
| `tests/modules/report_special_processing/*` | 模块测试 |
| `tests/` 平台相关测试 | user_directory / report_navigation todos |

---

### Task 1: 迁移与存储新列

**Files:**
- Create: `src/auto_check/modules/report_special_processing/migrations/003_dimension_governance_fields.sql`
- Modify: `src/auto_check/modules/report_special_processing/storage.py`
- Modify: `src/auto_check/modules/report_special_processing/manifest.json` (`schema_version`: 3)
- Modify: `src/auto_check/modules/report_special_processing/module.py` (schema 字段集)
- Test: `tests/modules/report_special_processing/test_manifest_and_migrations.py`
- Test: `tests/modules/report_special_processing/test_storage.py`（若无则补）

**Interfaces:**
- Produces: records 表可读可写 `dimension`, `governance_owner_*`, `table_name`, `field_name`, `value_before`, `value_after`

- [ ] **Step 1: 写失败测试（migration 版本与列存在）**

```python
def test_migration_003_adds_dimension_governance_columns():
    migrations = load_module_migrations("auto_check.modules.report_special_processing")
    assert len(migrations) == 3
    assert migrations[2].version == 3
    sql = "\n".join(migrations[2].statements).upper()
    for col in (
        "DIMENSION",
        "GOVERNANCE_OWNER_USER_ID",
        "TABLE_NAME",
        "FIELD_NAME",
        "VALUE_BEFORE",
        "VALUE_AFTER",
    ):
        assert col in sql
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/modules/report_special_processing/test_manifest_and_migrations.py::test_migration_003_adds_dimension_governance_columns -v`  
Expected: FAIL（无 003 或仍为 2 个 migration）

- [ ] **Step 3: 新增迁移 SQL**

```sql
ALTER TABLE report_special_processing_records
    ADD COLUMN dimension VARCHAR(16) NULL COMMENT '所属维度 project/fund/asset/finance' AFTER report_period,
    ADD COLUMN governance_owner_user_id VARCHAR(64) NULL COMMENT '数据治理负责人用户ID' AFTER handler_display_name_snapshot,
    ADD COLUMN governance_owner_username_snapshot VARCHAR(64) NULL COMMENT '数据治理负责人用户名快照' AFTER governance_owner_user_id,
    ADD COLUMN governance_owner_display_name_snapshot VARCHAR(64) NULL COMMENT '数据治理负责人显示名快照' AFTER governance_owner_username_snapshot,
    ADD COLUMN table_name VARCHAR(128) NULL COMMENT '处理表名' AFTER summary,
    ADD COLUMN field_name VARCHAR(128) NULL COMMENT '处理字段名' AFTER table_name,
    ADD COLUMN value_before VARCHAR(500) NULL COMMENT '修改前' AFTER field_name,
    ADD COLUMN value_after VARCHAR(500) NULL COMMENT '修改后' AFTER value_before
```

同步 `storage.py` `RECORDS` Table 列、`module.py` schema 字段、`manifest.json` `schema_version: 3`。

- [ ] **Step 4: 跑测试通过**

Run: `pytest tests/modules/report_special_processing/test_manifest_and_migrations.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/auto_check/modules/report_special_processing/migrations/003_dimension_governance_fields.sql \
  src/auto_check/modules/report_special_processing/storage.py \
  src/auto_check/modules/report_special_processing/manifest.json \
  src/auto_check/modules/report_special_processing/module.py \
  tests/modules/report_special_processing/test_manifest_and_migrations.py
git commit -m "feat(rsp): add dimension and governance owner storage columns"
```

---

### Task 2: 合约、校验器与确认权限

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/contracts.py`
- Modify: `src/auto_check/modules/report_special_processing/validator.py`
- Modify: `src/auto_check/modules/report_special_processing/permissions.py`
- Test: `tests/modules/report_special_processing/test_validator_and_permissions.py`

**Interfaces:**
- Produces:
  - `DIMENSIONS = {"project","fund","asset","finance"}`
  - `STATUS_LABELS[PENDING] = "待确认"`
  - `RecordInput` 新字段：`dimension`, `governance_owner_user_id`, `table_name`, `field_name`, `value_before`, `value_after`
  - `can_confirm(user, record) -> bool`
- Consumes: Task 1 存储列名

- [ ] **Step 1: 写失败测试**

```python
def test_validate_record_input_requires_dimension_fields_for_formal_save():
    with pytest.raises(ValidationError) as exc:
        validate_record_input({
            "save_mode": "record",
            "report_process_codes": ["p1"],
            "report_period": "2026-07-31",
            "summary": "s" * 10,
            "handler_user_id": "u1",
            "special_handling_at": "2026-07-31T10:00:00+08:00",
        })
    assert "dimension" in exc.value.fields

def test_summary_allows_50_chars_rejects_51():
    payload = {..., "summary": "字" * 50, "dimension": "project", ...}
    assert validate_record_input(payload).summary == "字" * 50
    with pytest.raises(ValidationError):
        validate_record_input({**payload, "summary": "字" * 51})

def test_can_confirm_requires_capability_and_governance_owner():
    record = {"governance_owner_user_id": "owner-1", "status": "pending"}
    assert can_confirm({"id": "owner-1", "role": "user", "capabilities": ["rsp.confirm"]}, record)
    assert not can_confirm({"id": "other", "role": "user", "capabilities": ["rsp.confirm"]}, record)
    assert can_confirm({"id": "admin", "role": "admin", "capabilities": ["rsp.confirm"]}, record)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/modules/report_special_processing/test_validator_and_permissions.py -k "dimension or summary_allows or can_confirm_requires" -v`  
Expected: FAIL

- [ ] **Step 3: 最小实现**

`contracts.py`：
- `STATUS_LABELS[PENDING] = "待确认"`
- `DIMENSION_LABELS` 映射
- `RecordInput` 增加新字段；`reports`/`processing_content` 保留但默认空

`validator.py`：
- `_RECORD_FIELDS` 增加新字段；正式保存不再要求 `reports`/`processing_content`
- `summary` max=50
- 正式保存必填：`dimension`（枚举）、`governance_owner_user_id`、`table_name`(≤128)、`field_name`(≤128)、`value_before`(≤500)、`value_after`(≤500)
- 传入的 `reports`/`processing_content`：忽略（不写入校验失败），返回空

`permissions.py`：
```python
def can_confirm(user, record=None) -> bool:
    if not user_has_capability(user, "rsp.confirm"):
        return False
    if is_admin(user):
        return True
    if record is None:
        return False
    return str((user or {}).get("id") or "") == str(record.get("governance_owner_user_id") or "")
```

更新所有 `can_confirm(user)` 调用点传 `record`。

- [ ] **Step 4: 跑测试通过**

Run: `pytest tests/modules/report_special_processing/test_validator_and_permissions.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(rsp): validate dimension fields and tighten confirm permission"
```

---

### Task 3: user_directory 返回 role + catalog 治理候选人

**Files:**
- Modify: `src/auto_check/app/platform_services.py`
- Modify: `src/auto_check/modules/report_special_processing/service.py`
- Test: `tests/test_platform_services.py`（或现有 user_directory 测试）
- Test: `tests/modules/report_special_processing/test_service.py`

**Interfaces:**
- Produces: `PublicUser.role: str`
- Produces: `catalog()["dimensions"]`, `catalog()["governance_owner_candidates_by_dimension"]`
- Consumes: `AuthManager.list_users()` 含 `role`；角色定义显示名

- [ ] **Step 1: 写失败测试**

```python
def test_public_user_includes_role():
    # list_active_users 每项有 role 字段
    ...

def test_catalog_governance_candidates_by_dimension_role_display_name(monkeypatch):
    # 构造用户：role_code 映射显示名「数据治理_项目资产」
    # project/asset 候选人相同；fund/finance 为「数据治理_资金财务」
    # 无匹配角色时对应维度列表为空
    ...
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

`PublicUser` 增加 `role: str`；`_active_users` 从 `list_users()` 取 `role`。

`service.catalog`：
1. 加载自定义+系统角色定义，建立 `display_name -> role_code`
2. 解析 `数据治理_项目资产` / `数据治理_资金财务` 对应 role_code（找不到则候选人空）
3. 过滤 `list_active_users()` 中 `user.role` 匹配者
4. 返回：

```python
{
  "dimensions": [
    {"code": "project", "label": "项目端"},
    {"code": "fund", "label": "资金端"},
    {"code": "asset", "label": "资产端"},
    {"code": "finance", "label": "财务端"},
  ],
  "governance_owner_candidates_by_dimension": {
    "project": [...], "asset": [...], "fund": [...], "finance": [...]
  },
  # 既有 users/statuses/limits/...
}
```

角色定义读取：模块可通过 `application_database` + `load_role_definitions`；若模块不宜直接依赖 storage，则在 service 构造时注入 `role_label_resolver` 回调。推荐：在 `module.start` 注入基于 `application_database` 的轻量查询函数，避免改 user_directory 大版本。

- [ ] **Step 4: 跑测试通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: expose user role and RSP governance owner candidates"
```

---

### Task 4: Service 读写新字段 + 正式保存待确认

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/service.py`
- Modify: `src/auto_check/modules/report_special_processing/export_workbook.py`
- Test: `tests/modules/report_special_processing/test_service.py`
- Test: `tests/modules/report_special_processing/test_export.py`

**Interfaces:**
- Consumes: Task 1–3
- Produces: create/update 持久化新字段；正式保存 status=`pending`；list payload 含新字段；confirm 走新 `can_confirm`

- [ ] **Step 1: 写失败测试（创建正式记录带维度/治理负责人/字段组；列表返回；非负责人确认 403）**

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `_record_values` / create / update / public record 映射；不再写 reports 子表；`processing_content=""`；治理负责人快照类似 handler**

正式保存：`status = pending`。  
`change_status(..., completed)` 调用 `can_confirm(user, record)`。

导出列：所属报送期、关联报送、所属维度、处理摘要、处理表名、处理字段名、修改前、修改后、处理人、数据治理负责人、处理时间、状态（去掉涉及报表/处理说明）。

- [ ] **Step 4: 跑模块 service/api/export 测试**

Run: `pytest tests/modules/report_special_processing/ -q`  
Expected: PASS（本 Task 相关）

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(rsp): persist dimension fields and enforce confirm owner"
```

---

### Task 5: RSP 前端弹窗与列表

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_drawer.js`
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_table.js`
- Modify: `src/auto_check/modules/report_special_processing/web/components/filters.js`
- Modify: `src/auto_check/modules/report_special_processing/web/pages/ledger.js`
- Modify: `src/auto_check/modules/report_special_processing/web/styles.css`（如需）
- Test: `tests/modules/report_special_processing/test_frontend_static.py`

**Interfaces:**
- Consumes: catalog dimensions + governance_owner_candidates_by_dimension
- Produces: 弹窗/列表符合设计；确认弹窗按钮「源系统已确认」；支持 `?record_id=&highlight=1`

- [ ] **Step 1: 写/更新前端静态测试断言**

断言包含：
- 无「涉及报表」「处理说明」
- 有「所属维度」「数据治理负责人」「处理表名」「处理字段名」「修改前」「修改后」
- 摘要 maxlength=50
- 列表表头 8 列文案
- 「源系统已确认」
- `STATUS` 文案「待确认」

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 UI**

弹窗基本信息：关联报送、报送期、处理人、所属维度、数据治理负责人。  
维度 `change`：从 `governance_owner_candidates_by_dimension[code]` 填充下拉；若多人 `Math.floor(Math.random()*n)` 默认选中；空则清空不带入。  
特殊处理内容：摘要 + 表名 + 字段名 + 修改前 + 修改后。  

列表列与操作：确认按钮仅当 `capabilities.can_confirm`（后端已按负责人计算）且 status∈{pending,processing}。  
确认弹窗展示关键信息，主按钮文案「源系统已确认」，提交 `{target_status:"completed"}`。  

`ledger.js` 启动时读 URL/hash query `record_id`：加载后滚动并高亮该行。

- [ ] **Step 4: 跑前端静态测试通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(rsp): update drawer and ledger for dimension and confirm modal"
```

---

### Task 6: 平台 Todo Provider 协议

**Files:**
- Modify: `src/auto_check/app/report_navigation_platform.py`
- Modify: `src/auto_check/app/report_navigation.py`
- Test: `tests/test_report_navigation_platform.py`（或新建 `tests/test_report_navigation_todos.py`）

**Interfaces:**
- Produces:
  - `TodoItem(id, title, summary, assignee_user_id, module_id, created_at, action)`
  - `TodoAction(type="navigate", route, query)`
  - `register_todo_provider(provider_id, provider, semantics_version) -> handle`
  - `dashboard(...)["todos"]` 仅当前用户

- [ ] **Step 1: 写失败测试**

```python
def test_register_todo_provider_and_dashboard_filters_by_assignee():
    # 注册 provider 返回两条不同 assignee
    # dashboard(current_user=A) 只含 A 的待办
    ...
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

仿照 `_CardProviderRegistry`：内存注册表 + facade `register_todo_provider`。  
`dashboard` 调用各 provider.list_todos(request)，过滤 `assignee_user_id == current_user.id`，合并排序（按 created_at desc）。  
Provider 异常：单 provider 失败不影响其他，记日志。

`request` 最小字段：`current_user`, `now`。

- [ ] **Step 4: 跑测试通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add report navigation todo provider protocol"
```

---

### Task 7: RSP 注册 TodoProvider + 我的待办前端

**Files:**
- Create: `src/auto_check/modules/report_special_processing/todos.py`
- Modify: `src/auto_check/modules/report_special_processing/module.py`
- Modify: `src/auto_check/web/index.html`（待办区改为空容器）
- Modify: `src/auto_check/web/app.js`（dashboard 渲染 todos；处理跳转）
- Modify: `src/auto_check/web/styles.css`（空态如需）
- Modify: `src/auto_check/web/module_host.js`（若 activate 需保留 query）
- Test: `tests/modules/report_special_processing/test_todos.py`
- Test: `tests/test_web_static.py` 相关断言 / `tests/module_system/test_frontend_host.py` 如涉及

**Interfaces:**
- Consumes: Task 6 API；RSP pending + governance_owner
- Produces: 待办 title=`报表特殊处理待确认`；summary=`{维度标签} · {field_name}`；action navigate `report-special-processing` + `record_id`/`highlight`

- [ ] **Step 1: 写失败测试（provider 只返回当前负责人的 pending；确认后不再返回）**

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

`todos.py`：查询 storage 中 `status=pending` 且 `governance_owner_user_id=request.current_user.id`。  

`module.start`：`register_todo_provider(provider_id="rsp_pending_confirm", ...)`，`stop` 关闭 handle。  

前端：
- `index.html`：`report-nav-todo-list` 置空；标题数量用 `<small id="reportNavTodoCount">` 
- `app.js`：dashboard 成功后 `renderReportNavTodos(payload.todos || [])`
- 「处理」：`location.hash = "#report-special-processing?record_id=...&highlight=1"` 或经 module host API；确保 RSP ledger 能读到 query
- 空态文案：`暂无待办`

- [ ] **Step 4: 跑相关测试**

Run:
```
pytest tests/modules/report_special_processing/test_todos.py tests/test_report_navigation_todos.py -q
```
并更新 web static 中「我的待办」硬编码 3 条的旧断言。

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: wire RSP pending confirms into report navigation todos"
```

---

### Task 8: 文档、版本号与总验收

**Files:**
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`（系统更新日志精简条）
- Modify: `src/auto_check/web/index.html`（`app.js`/`styles.css` `?v=`）
- Modify: `src/auto_check/modules/report_special_processing/README.md`（若有字段说明）
- Modify: `docs/superpowers/specs/2026-08-10-rsp-dimension-governance-todo-design.md` 状态改为「已实施」

- [ ] **Step 1: 更新 README 详细变更；app.js 更新日志写「报表特殊处理字段与待确认待办」类条目 +「系统优化及BUG修复」按需**

- [ ] **Step 2:  bump 静态资源版本号**

- [ ] **Step 3: 跑聚焦测试套件**

```
pytest -q tests/modules/report_special_processing/ \
  tests/test_platform_services.py \
  tests/test_report_navigation_todos.py \
  tests/module_system/test_frontend_host.py \
  tests/test_web_static.py::test_role_permissions_page_and_capability_access_are_present
```

Expected: PASS

- [ ] **Step 4: 手动验收清单（开发者自测）**

1. 弹窗字段符合设计；维度联动负责人
2. 列表 8 列；状态「待确认」
3. 治理负责人看到待办；摘要含维度与字段名
4. 「处理」跳转并定位
5. 确认弹窗按钮「源系统已确认」；完成后待办消失
6. 非负责人不能确认

- [ ] **Step 5: Commit**

```bash
git commit -m "docs: note RSP dimension governance and confirmation todos"
```

---

## Spec Coverage Self-Review

| Spec 要求 | Task |
|-----------|------|
| 去掉涉及报表/处理说明 | 2, 5 |
| 所属维度 + 治理负责人联动角色 | 3, 5 |
| 表名/字段/修改前/修改后一组 | 1, 2, 4, 5 |
| 摘要 ≤50 | 2, 5 |
| 列表 8 列 | 5 |
| pending=待确认；确认权限 | 2, 4, 5 |
| 确认弹窗「源系统已确认」 | 5 |
| Todo Provider 协议 | 6 |
| RSP 待办注入 + 我的待办动态化 | 7 |
| 跳转定位 | 5, 7 |
| README/版本号 | 8 |

无占位符；类型名在 Task 6/7 一致（`TodoItem`/`register_todo_provider`）。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-10-rsp-dimension-governance-todo.md`.

**Two execution options:**

1. **Subagent-Driven（推荐）** — 每 Task 派生子代理，任务间复审  
2. **Inline Execution** — 本会话按 executing-plans 连续执行并设检查点  

选哪种？
