# 角色轻量可配权限（一期）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地平台级能力矩阵与「系统管理」导航（系统设置 / 角色权限 / 用户管理），并把对数历史删除迁到 `history.delete`；**不改**报表特殊处理业务行为。

**Architecture:** 在平台内核新增能力注册表 + 默认矩阵 + `has_capability`；矩阵以单行 JSON 快照存应用库；登录/会话下发当前用户能力列表；前端按能力控制「系统管理」子菜单与设置页管理员专属区块；`rsp.*` 能力码一期只注册展示，运行时不接通 RSP。

**Tech Stack:** Python 3 + SQLAlchemy MySQL 应用库、现有 `AuthManager`/`server.py`、原生前端 `index.html` + `app.js` + `styles.css`、`pytest`。

**Spec:** `docs/superpowers/specs/2026-08-07-role-capabilities-and-rsp-workflow-design.md`（一期范围）

## Global Constraints

- 一期**禁止**修改 `src/auto_check/modules/report_special_processing/**` 业务鉴权、状态机、按钮。
- 管理员列能力锁定：UI 禁用 + 后端拒绝改写 `admin` 行。
- 系统设置页保留现网管理员/普通用户内容区分；不得整页收成仅管理员。
- 预留角色（含 `governance`）一期实际行为等同现普通用户（RSP 未接通）；仅身份可区分保存。
- 前端仅亮色活力主题；圆角/主题色用现有 CSS 变量；危险操作用红色语义。
- 可见 UI 变更需同步 `README.md`、`app.js` 更新日志（应用内精简口径）、相关静态测试。
- 改完跑 `python -m pytest -q`；提交仅在用户要求时执行。
- 二期（RSP 状态迁移 + 接通 `rsp.*`）另开计划，本计划不包含。

---

## File Structure

| 路径 | 职责 |
|---|---|
| `src/auto_check/app/capabilities.py` | 角色码、能力码、默认矩阵、合并、`has_capability`、锁定校验 |
| `src/auto_check/app/storage_role_capabilities.py` | 读写 `role_capability_settings` JSON 快照 |
| `sql/app_storage/mysql/014_role_capability_settings.sql` | 增量建表 |
| `src/auto_check/app/app_database.py` | `EXPECTED_APP_SCHEMA` 登记新表 |
| `src/auto_check/app/security.py` | 扩展合法角色码；用户 CRUD 校验 |
| `src/auto_check/app/server.py` | 会话下发 capabilities；GET/PUT 角色权限 API；历史删除改 `has_capability`；设置页 admin 专属 API 逐步改用 `sys.settings.admin`（与现网等价） |
| `src/auto_check/web/index.html` | 「系统管理」分组；角色权限页骨架 |
| `src/auto_check/web/app.js` | 能力判断、导航显隐、角色权限页、用户角色选项、`canManageHistory` |
| `src/auto_check/web/styles.css` | 角色权限页样式 |
| `tests/test_capabilities.py` | 矩阵/合并/锁定单测 |
| `tests/test_role_capabilities_api.py` | API + 历史删除能力测试 |
| `tests/test_security.py` | 扩展角色校验 |
| `tests/test_web_static.py` | 导航与页面静态结构 |
| `README.md` | 版本说明 |

---

### Task 1: 能力注册表与 `has_capability`

**Files:**
- Create: `src/auto_check/app/capabilities.py`
- Test: `tests/test_capabilities.py`

**Interfaces:**
- Produces:
  - `ROLE_DEFINITIONS: dict[str, str]`（role_code → 中文名）
  - `CAPABILITY_DEFINITIONS: dict[str, str]`（code → 中文名）
  - `DEFAULT_MATRIX: dict[str, dict[str, bool]]`（role → capability → allowed）
  - `LOCKED_ROLE = "admin"`
  - `KNOWN_ROLES: frozenset[str]`
  - `def merge_matrix(stored: dict | None) -> dict[str, dict[str, bool]]`
  - `def has_capability(role: str, capability: str, matrix: dict | None = None) -> bool`
  - `def assert_admin_column_unchanged(previous, incoming) -> None`（违规抛 `ValueError`）
  - `def capabilities_for_role(role: str, matrix: dict | None = None) -> list[str]`

- [ ] **Step 1: 写失败单测**

```python
# tests/test_capabilities.py
from auto_check.app.capabilities import (
    DEFAULT_MATRIX,
    has_capability,
    merge_matrix,
    assert_admin_column_unchanged,
    capabilities_for_role,
)

def test_default_standard_roles_match_user_tier():
    for role in ("user", "regulatory_report", "data_middle", "fund_custody"):
        assert has_capability(role, "sys.settings") is True
        assert has_capability(role, "sys.settings.admin") is False
        assert has_capability(role, "sys.users") is False
        assert has_capability(role, "history.delete") is False
        assert has_capability(role, "rsp.view") is True  # 仅注册；一期不接通业务

def test_governance_defaults_include_rsp_confirm_but_not_create():
    assert has_capability("governance", "rsp.confirm") is True
    assert has_capability("governance", "rsp.create") is False

def test_admin_has_all_registered_capabilities():
    for code in DEFAULT_MATRIX["admin"]:
        assert has_capability("admin", code) is True

def test_merge_fills_missing_without_overwriting_saved():
    stored = {"user": {"sys.settings": False}}
    merged = merge_matrix(stored)
    assert merged["user"]["sys.settings"] is False
    assert "history.delete" in merged["user"]
    assert merged["admin"]["history.delete"] is True

def test_admin_column_lock_rejects_change():
    previous = merge_matrix(None)
    incoming = merge_matrix(None)
    incoming["admin"]["history.delete"] = False
    try:
        assert_admin_column_unchanged(previous, incoming)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "admin" in str(exc).lower()

def test_capabilities_for_role_lists_allowed_only():
    codes = capabilities_for_role("user")
    assert "sys.settings" in codes
    assert "sys.users" not in codes
```

- [ ] **Step 2: 跑测确认失败**

Run: `python -m pytest tests/test_capabilities.py -q`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `capabilities.py`**

按设计文档 §4～§5 写入角色、能力、默认矩阵（含全部 `rsp.*` 码以便角色权限页展示；注释标明一期 RSP 未接通）。`merge_matrix`：对每个已知角色/能力，已存值保留，缺失用默认。`has_capability`：未知角色按 `user` 档；未知能力返回 `False`。

- [ ] **Step 4: 跑测通过**

Run: `python -m pytest tests/test_capabilities.py -q`  
Expected: PASS

---

### Task 2: 应用库存储快照

**Files:**
- Create: `sql/app_storage/mysql/014_role_capability_settings.sql`
- Create: `src/auto_check/app/storage_role_capabilities.py`
- Modify: `src/auto_check/app/app_database.py`（登记表列）
- Test: `tests/test_capabilities.py`（追加存储测）或 `tests/test_role_capabilities_storage.py`

**Interfaces:**
- Consumes: `merge_matrix`, `assert_admin_column_unchanged`
- Produces:
  - `load_role_capability_matrix(connection) -> dict`
  - `save_role_capability_matrix(connection, matrix, *, updated_by: str) -> dict`（保存前锁定校验 + merge）

- [ ] **Step 1: 写 DDL**

```sql
-- sql/app_storage/mysql/014_role_capability_settings.sql
-- 安全增量：仅 CREATE TABLE IF NOT EXISTS，无 DROP/TRUNCATE
CREATE TABLE IF NOT EXISTS `role_capability_settings` (
  `id` TINYINT UNSIGNED NOT NULL COMMENT '固定为 1 的单行配置',
  `matrix_json` JSON NOT NULL COMMENT '角色×能力矩阵快照',
  `version` INT NOT NULL DEFAULT 1 COMMENT '矩阵版本',
  `updated_by` VARCHAR(64) NULL COMMENT '更新人用户 ID',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='角色能力矩阵配置（单行 JSON 快照）';
```

- [ ] **Step 2: 实现 storage 模块 + EXPECTED_APP_SCHEMA 列清单**

参照 `storage_system_interface_preferences.py`：`id=1` 单行 upsert；无行则 `merge_matrix(None)`；保存时 `json.dumps` 写入。

- [ ] **Step 3: 用 `shared_application_database` fixture 测 load/save/lock**

Run: `python -m pytest tests/test_role_capabilities_storage.py -q`（或并入 capabilities 测）  
Expected: PASS

---

### Task 3: 扩展用户角色码

**Files:**
- Modify: `src/auto_check/app/security.py`（`_normalize_role`）
- Modify: `tests/test_security.py`
- 前端用户角色展示延后 Task 6，本任务先过后端

**Interfaces:**
- Consumes: `KNOWN_ROLES` / `ROLE_DEFINITIONS` from `capabilities.py`
- Produces: `_normalize_role` 接受 `admin|governance|user|regulatory_report|data_middle|fund_custody`

- [ ] **Step 1: 失败测**

```python
def test_normalize_role_accepts_reserved_roles():
    from auto_check.app.security import _normalize_role
    assert _normalize_role("governance") == "governance"
    assert _normalize_role("regulatory_report") == "regulatory_report"

def test_create_user_with_governance_role(tmp_path, shared_application_database):
    # 使用现有 AuthManager 测建用户 role=governance 成功
    ...
```

- [ ] **Step 2: 改 `_normalize_role` 使用 `KNOWN_ROLES`，错误文案列出合法角色**

- [ ] **Step 3: 跑 `tests/test_security.py -q` 相关用例 PASS**

说明：一期委派管理员规则仍按「是否 admin」判断，不因新角色改变。

---

### Task 4: API 与会话下发能力

**Files:**
- Modify: `src/auto_check/app/server.py`
- Test: `tests/test_role_capabilities_api.py`

**Interfaces:**
- Produces HTTP:
  - `GET /api/role-capabilities` → `{ matrix, roles, capabilities, locked_roles: ["admin"] }`（需 `sys.role_permissions`）
  - `PUT /api/role-capabilities` body `{ matrix }` → 保存（需 `sys.role_permissions`；拒绝改 admin 列 → 400）
  - 登录/会话载荷增加 `capabilities: string[]`（当前角色允许的能力码列表）
- `DELETE /api/history`：改为 `has_capability(role, "history.delete", matrix)`，403 文案可用 `capability required: history.delete`（或保持兼容旧文案二选一，测里对齐实现）

- [ ] **Step 1: 写 API 测**

```python
# 管理员 GET 成功；普通用户 GET 403
# 管理员把 user.history.delete 改为 True 后，该用户登录 capabilities 含 history.delete，且 DELETE /api/history 200
# 尝试改 admin.history.delete=False → 400
# governance 用户 capabilities 含 rsp.confirm（仅校验下发，不测 RSP API）
```

- [ ] **Step 2: 实现 server 接线**（启动时 load matrix 缓存或每次读库；保存后刷新）

- [ ] **Step 3: 跑测 PASS**

---

### Task 5: 系统管理导航 + 角色权限页（前端）

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: `authState.user.capabilities`
- Produces: `hasCapability(code)`, `applyCapabilityAccess()`（替代/扩展 `applyRoleAccess`）

- [ ] **Step 1: 改顶栏（复用智能核数 `top-nav-group` 模式）**

```html
<div class="top-nav-group" data-nav-group="system-admin">
  <button class="top-nav-item top-nav-group-toggle" type="button" data-nav-group-toggle="system-admin" aria-expanded="false">
    <span>系统管理</span>
    <span class="top-nav-group-chevron" aria-hidden="true">&#9662;</span>
  </button>
  <div class="top-nav-submenu">
    <a class="top-nav-item top-nav-subitem" data-page="settings" data-capability="sys.settings" href="#">系统设置</a>
    <a class="top-nav-item top-nav-subitem" data-page="role-permissions" data-capability="sys.role_permissions" href="#">角色权限</a>
    <a class="top-nav-item top-nav-subitem" data-page="users" data-capability="sys.users" href="#">用户管理</a>
  </div>
</div>
```

同步侧栏若仍有独立「系统设置」「用户管理」入口，改为同组或按能力显隐，避免双入口不一致。

- [ ] **Step 2: 新增 `page-role-permissions`：角色×能力勾选表；admin 列 `disabled`；保存调 `PUT /api/role-capabilities`**

页内说明：`rsp.*` 一期仅预配置，接通后再生效。

- [ ] **Step 3: `applyCapabilityAccess`**

- 无 `sys.settings` 隐藏设置入口；无 `sys.users` 隐藏用户管理；无 `sys.role_permissions` 隐藏角色权限。
- 无 `sys.settings.admin` 时隐藏 `.admin-only` 设置卡片（与现网普通用户一致）；**不要**再用「非 admin 角色一律 dataset.role=user」覆盖掉已具备 `sys.settings.admin` 的未来配置（一期默认矩阵下行为与现网相同）。
- `canManageHistory()` → `hasCapability("history.delete")`。

- [ ] **Step 4: 静态测更新**

更新 `test_user_management_page_and_role_based_navigation_are_present`：断言「系统管理」分组、`data-page="role-permissions"`、`hasCapability` / `applyCapabilityAccess` 存在；不再要求顶栏裸 `data-page="settings"` 一级项（若已移入分组）。

- [ ] **Step 5: `python -m pytest tests/test_web_static.py -q -k "user_management or role_permission or history or settings"` 及相关 FAIL 修到 PASS**

---

### Task 6: 用户管理角色选项与展示

**Files:**
- Modify: `src/auto_check/web/index.html`（用户弹窗角色卡片/下拉）
- Modify: `src/auto_check/web/app.js`（`userDisplayRole` 映射六角色）
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: `userDisplayRole` 覆盖全部 `ROLE_DEFINITIONS`**
- [ ] **Step 2: 新建/编辑用户可选非 admin 预留角色；委派管理员仍不可设 admin（现规则保留）**
- [ ] **Step 3: 筛选/统计：一期可将非 admin 计入「普通/其他」或按角色细分——优先最小改动：筛选增加新角色值，统计「管理员 vs 非管理员」口径不变**
- [ ] **Step 4: 静态测断言角色选项文案存在**

---

### Task 7: 设置页管理员专属后端对齐（可选但推荐）

**Files:**
- Modify: `src/auto_check/app/server.py` 中设置类写接口的 `role != "admin"` 检查

- [ ] 将「系统设置管理员专属」写接口改为 `has_capability(..., "sys.settings.admin")`（默认仅 admin，行为不变）。
- [ ] 用户管理 API 改为 `sys.users`；角色权限 API 已是 `sys.role_permissions`。
- [ ] **不要**改报送导航维护、模块管理等未列入一期矩阵的 `admin` 检查。

回归：`tests/test_security.py` 中 theme-colors 403 用例（普通用户仍 403）。

---

### Task 8: 文档与全量验证

**Files:**
- Modify: `README.md`（详细变更）
- Modify: `src/auto_check/web/app.js` 系统更新日志（精简：新功能写「角色权限配置」等；体验类写「系统优化及BUG修复」）
- 确认部署文档是否需追加 `014_role_capability_settings.sql` 说明（`docs/deployment.zh-CN.md` / intranet 若已列脚本清单则追加一行）

- [ ] **Step 1: 更新 README / 更新日志 / 部署脚本清单**
- [ ] **Step 2: 全量测试**

Run: `python -m pytest -q`  
Expected: 全绿

- [ ] **Step 3: 手工冒烟清单**

1. 普通用户：可见「系统管理→系统设置」；不可见角色权限/用户管理；设置页无数据源等 admin 卡片；对数历史无删除。
2. 管理员：三项子菜单均可见；角色权限页 admin 列不可勾改；改标准档 `history.delete` 后另开普通用户会话可删历史。
3. 报表特殊处理：按钮/状态与改前一致。

---

## Spec coverage（自检）

| 设计要求 | 任务 |
|---|---|
| 固定角色 + 可扩展能力矩阵 | Task 1–2 |
| admin 列锁定 | Task 1、2、4、5 |
| 系统管理导航三项 | Task 5 |
| 系统设置页内 admin/普通区分 | Task 5、7 |
| `history.delete` | Task 4、5 |
| 一期不接通 RSP | Global + Task 1 注释 + Task 8 冒烟 |
| `rsp.*` 可先展示 | Task 1、5 页内说明 |
| 预留角色等同普通用户行为 | Task 3、6 + 默认矩阵 |

## Out of scope → 二期计划

- RSP 状态迁移与新流程按钮
- RSP 接通 `has_capability(rsp.*)`
- 去掉处理人

---
