# 数据治理负责人可改选全部用户 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 编辑/新建弹窗中，数据治理负责人按所属维度自动带出后，下拉可选全部启用用户；改维度仍按新维度重新自动带出并覆盖当前选择。确认权限不变。

**Architecture:** 只改 `record_drawer.js` 的 `syncGovernanceOwnerOptions`：选项来自已有的 `catalog.users`（与处理人同源），自动带出仍用 `governance_owner_candidates_by_dimension`。后端 `_user()` 已接受任意启用用户；`can_confirm` 不改。

**Tech Stack:** 模块前端 ES module、pytest 静态断言、模块 manifest / README / 根 README / `app.js` 更新日志。

## Global Constraints

- 普通模块改动，禁止改平台内核、能力码、迁移、`permissions.py`
- 展示用大版本保持 `V1.2`；应用内小版本 `v1.2.21`；模块版本 `1.2.12`
- 亮色主题、`--ui-radius`、不新增控件
- 不主动提交/推送，除非用户明确要求
- 规格：`docs/superpowers/specs/2026-09-02-rsp-governance-owner-all-users-design.md`

---

### Task 1: 前端静态测试锁定名单与改维度覆盖

**Files:**
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`
- Test: 同上
- Later implement: `src/auto_check/modules/report_special_processing/web/components/record_drawer.js`

**Interfaces:**
- Consumes: `createRecordDrawer` 内已有 `users`、`candidatesByDimension`、`syncGovernanceOwnerOptions`
- Produces: 失败断言，迫使下拉填 `users`、改维度强制 `autoPick`

- [ ] **Step 1: 在 `test_frontend_static.py` 现有治理负责人断言旁追加**

在 `assert "governance_owner_candidates_by_dimension" in drawer` 之后加入：

```python
    assert "fillSelect(governanceOwner, users," in drawer
    assert "fillSelect(governanceOwner, candidates" not in drawer
    assert "previous && candidates.some" not in drawer
    assert "syncGovernanceOwnerOptions({ preferExisting: false, autoPick: true })" in drawer
    assert "Math.floor(Math.random()" in drawer
```

保留原有 `governance_owner_candidates_by_dimension` 与随机断言，确保自动带出仍读维度候选人。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_frontend_static.py -k test_frontend`

Expected: FAIL，当前仍是 `fillSelect(governanceOwner, candidates`。

- [ ] **Step 3: 改 `syncGovernanceOwnerOptions`**

`fillSelect(governanceOwner, users, "请选择数据治理负责人")`。`preferExisting` 用 `users.some` 判断已保存负责人是否在全量名单；不在则仍追加快照 option。删除 `previous` 及「改维度时若原人仍在新候选人中则保留」分支。`dimension` 的 `change` 仍调用 `{ preferExisting: false, autoPick: true }`，此时 `!next && autoPick` 会从新维度 `candidates` 随机带出；无候选人则清空。

- [ ] **Step 4: 再跑前端静态测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_frontend_static.py`

Expected: PASS

---

### Task 2: 后端锁定「非维度候选人也可保存」；确认权限测试保持绿

**Files:**
- Modify: `tests/modules/report_special_processing/test_service.py`
- Do not modify: `permissions.py`、`service.py`（除非测试证明保存被拒）

- [ ] **Step 1: 新增测试**

```python
def test_create_accepts_governance_owner_outside_dimension_candidates():
    directory = Directory()
    directory.users["outsider"] = User("outsider", "other", "其他用户", role="user")
    service = _service(directory=directory)
    record = service.create(
        _payload(governance_owner_user_id="outsider"),
        {"id": "1", "username": "creator", "display_name": "创建人", "role": "user"},
        request_id="req-any-owner",
    )
    assert record["governance_owner_user_id"] == "outsider"
    assert record["governance_owner_display_name_snapshot"] == "其他用户"
```

- [ ] **Step 2: 运行该测试与既有确认权限测试**

Run: `python -m pytest -q tests/modules/report_special_processing/test_service.py::test_create_accepts_governance_owner_outside_dimension_candidates tests/modules/report_special_processing/test_service.py::test_confirm_denied_for_non_governance_owner_even_with_capability tests/modules/report_special_processing/test_validator_and_permissions.py::test_can_confirm_requires_capability_and_governance_owner`

Expected: PASS（后端本就可保存任意启用用户；A 不能确认 B）

---

### Task 3: 版本、README、更新日志

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/manifest.json`
- Modify: `src/auto_check/modules/report_special_processing/README.md`
- Modify: `tests/modules/report_special_processing/test_manifest_and_migrations.py`
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`
- Modify: `docs/superpowers/specs/2026-09-02-rsp-governance-owner-all-users-design.md`（状态改为已认可并实施）

- [ ] **Step 1: 先改清单测试为 1.2.12 与新 release_notes，确认失败**

```python
    assert manifest.version == "1.2.12"
    assert manifest.release_notes.version == "1.2.12"
    assert manifest.release_notes.items == (
        "数据治理负责人可按所属维度自动带出后，改选任意启用用户",
    )
```

`app.js` 最新条目改为 `v1.2.21`（2026-09-02），列表仅「系统优化及BUG修复。」；`tests/test_web_static.py` 将 `v1.2.20` 最新断言改为同时包含 `v1.2.21`。根 README 新增 `v1.2.21` 详细条：报表特殊处理录入模块：数据治理负责人按所属维度自动带出后，可改选任意启用用户；改维度会按新维度重新自动带出。模块 README「字段」段改为：下拉为全部启用用户；自动带出仍按维度对应治理角色；改维度覆盖当前选择；确认仍仅该条负责人或管理员。

- [ ] **Step 2: 改 manifest / 文档 / changelog 使测试通过**

- [ ] **Step 3: 全量测试**

Run: `python -m pytest -q`

Expected: 全部通过。不打包、不提交，除非用户要求。
