# 报表特殊处理确认完成通知实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 数据治理负责人确认报表特殊处理完成后，向记录创建人发送可定位到已完成记录详情的应用内成功通知。

**Architecture:** 在 `SpecialProcessingService.change_status()` 的仓储提交成功边界之后调用模块私有发布辅助方法，复用已注入的 owner-bound `platform.notification` v1 门面。通知使用确认后版本号构造幂等键；发布失败只记录脱敏警告，不回滚已提交的业务状态和审计。

**Tech Stack:** Python 3.12、pytest、现有模块系统、`platform.notification` v1、JSON 模块清单、Markdown 文档。

## Global Constraints

- 接收人固定为记录的 `creator_user_id`，不得改用 `handler_user_id`。
- 通知标题固定为 `您提交的报表特殊处理已完成确认`。
- 只在记录成功转换为 `completed` 后发布，不补发历史已完成记录。
- 通知使用 `category="task"`、`level="success"` 和 `event_type="confirmation_completed"`。
- 幂等键固定为 `rsp-completed:{record_id}:{row_version}:{creator_user_id}`，其中 `row_version` 是确认成功后的版本。
- 点击通知进入 `report-special-processing` 并打开记录详情；查询参数不得包含 `open=confirm`。
- 通知失败不回滚确认结果，不修改通知平台协议、数据库结构、权限能力码或公共前端。
- 修改范围限于 `report_special_processing` 模块、对应测试和必要文档；不得修改 `server.py`、通知平台或其他业务模块。
- 模块版本从 `1.2.8` 升到 `1.2.9`；不提升系统展示大版本。
- 全量验证交给 `gpt-5.6-luna` 高推理子代理执行；主会话检查实际输出并处理失败。
- 不打包、不刷新可执行文件、不推送。实施代码提交必须另获用户明确授权；当前授权仅包含设计和计划文档提交。

---

## File Map

- `src/auto_check/modules/report_special_processing/service.py`：识别确认完成提交边界，构造并发布创建人通知，隔离通知失败。
- `tests/modules/report_special_processing/test_service.py`：锁定接收人、通知契约、触发矩阵、失败隔离和重开后再次确认行为。
- `src/auto_check/modules/report_special_processing/manifest.json`：模块补丁版本和本次模块发布说明。
- `tests/modules/report_special_processing/test_manifest_and_migrations.py`：锁定模块版本与发布说明，不改变迁移断言。
- `src/auto_check/modules/report_special_processing/README.md`：模块通知行为和故障隔离说明。
- `README.md`：对外功能概览及当前版本详细变更。

### Task 1: 以测试驱动实现确认完成通知

**Files:**
- Modify: `tests/modules/report_special_processing/test_service.py:514-612`
- Modify: `src/auto_check/modules/report_special_processing/service.py:368-413`
- Modify: `src/auto_check/modules/report_special_processing/service.py:577-615`

**Interfaces:**
- Consumes: `SpecialProcessingService._notifications.publish(NotificationPublishRequest)`、`DIMENSION_LABELS`、确认成功后仓储返回的记录映射。
- Produces: `SpecialProcessingService._publish_completion_notification(record: Mapping[str, Any], *, request_id: str) -> None`。
- Preserves: `_publish_pending_notification()` 的四类既有待确认通知触发行为。

- [ ] **Step 1: 添加确认完成通知测试辅助函数和成功场景测试**

在 `FakeNotificationPublisher` 后增加按事件类型筛选的辅助函数，并在 `TestNotificationTriggerMatrix` 中增加成功场景：

```python
def _requests_for(publisher, event_type):
    return [
        request
        for request in publisher.requests
        if request.event_type == event_type
    ]


def test_completion_notifies_creator_instead_of_selected_handler(
    service_with_publisher,
):
    service, publisher = service_with_publisher
    record = service.create(
        _payload(
            handler_user_id="2",
            governance_owner_user_id="owner",
        ),
        {
            "id": "1",
            "username": "creator",
            "display_name": "创建人",
            "role": "user",
        },
        request_id="req-create",
    )
    assert record["creator_user_id"] == "1"
    assert record["handler_user_id"] == "2"

    completed = service.change_status(
        record["id"],
        {
            "target_status": "completed",
            "row_version": record["row_version"],
        },
        {
            "id": "owner",
            "username": "gov_owner",
            "display_name": "治理负责人甲",
            "role": "custom_pa",
            "capabilities": ["rsp.confirm"],
        },
        request_id="req-complete",
    )

    requests = _requests_for(publisher, "confirmation_completed")
    assert len(requests) == 1
    request = requests[0]
    assert request.recipient_user_ids == ("1",)
    assert request.category == "task"
    assert request.level == "success"
    assert request.title == "您提交的报表特殊处理已完成确认"
    assert request.content == "项目端 · amt"
    assert request.dedupe_key == (
        f"rsp-completed:{completed['id']}:"
        f"{completed['row_version']}:1"
    )
    assert request.action.type == "navigate"
    assert request.action.route == "report-special-processing"
    assert request.action.query == {
        "record_id": str(completed["id"]),
        "highlight": "1",
        "period": "07-31",
    }
    assert "open" not in request.action.query
```

- [ ] **Step 2: 添加无效确认不发通知和发布失败不回滚测试**

继续在 `TestNotificationTriggerMatrix` 中增加：

```python
def test_denied_or_conflicting_completion_does_not_publish(
    service_with_publisher,
):
    from auto_check.modules.report_special_processing.contracts import (
        PermissionDeniedError,
        VersionConflictError,
    )

    service, publisher = service_with_publisher
    record = service.create(
        _payload(governance_owner_user_id="owner"),
        {
            "id": "1",
            "username": "creator",
            "display_name": "创建人",
            "role": "user",
        },
        request_id="req-create",
    )
    publisher.requests.clear()

    with pytest.raises(PermissionDeniedError):
        service.change_status(
            record["id"],
            {
                "target_status": "completed",
                "row_version": record["row_version"],
            },
            {
                "id": "2",
                "role": "user",
                "capabilities": ["rsp.confirm"],
            },
            request_id="req-denied",
        )
    assert _requests_for(publisher, "confirmation_completed") == []

    with pytest.raises(VersionConflictError):
        service.change_status(
            record["id"],
            {"target_status": "completed", "row_version": 999},
            {
                "id": "owner",
                "role": "custom_pa",
                "capabilities": ["rsp.confirm"],
            },
            request_id="req-conflict",
        )
    assert _requests_for(publisher, "confirmation_completed") == []


def test_completion_publish_failure_preserves_completed_business_result(
    service_with_publisher,
):
    class FailingPublisher:
        def publish(self, request):
            raise RuntimeError("notification service unavailable")

    service, publisher = service_with_publisher
    record = service.create(
        _payload(governance_owner_user_id="owner"),
        {
            "id": "1",
            "username": "creator",
            "display_name": "创建人",
            "role": "user",
        },
        request_id="req-create",
    )
    publisher.requests.clear()
    service._notifications = FailingPublisher()

    completed = service.change_status(
        record["id"],
        {
            "target_status": "completed",
            "row_version": record["row_version"],
        },
        {
            "id": "owner",
            "role": "custom_pa",
            "capabilities": ["rsp.confirm"],
        },
        request_id="req-complete",
    )

    assert completed["status"] == "completed"
    assert service.storage.get(record["id"])["status"] == "completed"
```

- [ ] **Step 3: 运行新增测试并确认红灯原因正确**

Run:

```powershell
python -m pytest tests/modules/report_special_processing/test_service.py -q -k "completion_notifies_creator or denied_or_conflicting_completion or completion_publish_failure"
```

Expected: `test_completion_notifies_creator_instead_of_selected_handler` 失败，因为尚未发布 `confirmation_completed`；权限和版本冲突用例不应产生意外通知。

- [ ] **Step 4: 在确认提交成功后调用新的发布辅助方法**

在 `change_status()` 的 `storage.update_status(...)` 返回之后、统计刷新之前增加：

```python
changed = self.storage.update_status(record_id, version, changes, audit)
if target == "completed":
    self._publish_completion_notification(changed, request_id=request_id)
self._refresh_special_governance_stats()
return changed
```

该调用必须位于仓储返回之后，不能放到权限、状态机或仓储写入之前。

- [ ] **Step 5: 实现最小确认完成通知辅助方法**

在 `_publish_pending_notification()` 后、`_refresh_special_governance_stats()` 前增加：

```python
def _publish_completion_notification(
    self,
    record: Mapping[str, Any],
    *,
    request_id: str,
) -> None:
    if self._notifications is None:
        return
    creator_id = str(record.get("creator_user_id") or "").strip()
    if not creator_id:
        return

    dimension = str(record.get("dimension") or "").strip()
    dimension_label = DIMENSION_LABELS.get(
        dimension,
        dimension or "未分维度",
    )
    field_name = str(record.get("field_name") or "").strip() or "未填字段"
    record_id = int(record["id"])
    row_version = int(record["row_version"])
    report_period = str(record.get("report_period") or "").strip()
    query = {
        "record_id": str(record_id),
        "highlight": "1",
    }
    if len(report_period) >= 10:
        query["period"] = report_period[5:10]

    from auto_check.app.notifications.contracts import (
        NotificationAction,
        NotificationPublishRequest,
    )

    request = NotificationPublishRequest(
        event_type="confirmation_completed",
        dedupe_key=(
            f"rsp-completed:{record_id}:{row_version}:{creator_id}"
        ),
        recipient_user_ids=(creator_id,),
        category="task",
        level="success",
        title="您提交的报表特殊处理已完成确认",
        content=f"{dimension_label} · {field_name}",
        action=NotificationAction(
            type="navigate",
            route="report-special-processing",
            query=query,
        ),
    )
    try:
        self._notifications.publish(request)
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "completion notification publish failed for record "
            "%s:%s recipient=%s request=%s",
            record_id,
            row_version,
            creator_id,
            request_id,
            exc_info=True,
        )
```

- [ ] **Step 6: 调整现有通知触发矩阵以反映新增场景**

在 `test_new_pending_relationship_publishes_one_notification()` 中，不再按全部请求数断言重开流程，而是只统计 `pending_confirmation_created`：

```python
pending_requests = _requests_for(
    publisher,
    "pending_confirmation_created",
)
expected_pending_count = 2 if operation == "reopen_completed" else 1
assert len(pending_requests) == expected_pending_count
request = pending_requests[0]
```

从 `test_non_creation_operations_do_not_publish` 的参数列表中删除 `"complete"` 分支，并将测试重命名为 `test_operations_without_notification_semantics_do_not_publish`。保留 `save_draft`、`void` 和 `delete` 三个场景，继续断言 `publisher.requests == []`。

- [ ] **Step 7: 添加重开后再次确认使用新幂等键的测试**

```python
def test_reopen_then_reconfirm_uses_new_completion_dedupe_key(
    service_with_publisher,
):
    service, publisher = service_with_publisher
    creator = {
        "id": "1",
        "username": "creator",
        "display_name": "创建人",
        "role": "user",
        "capabilities": ["rsp.create", "rsp.reopen"],
    }
    owner = {
        "id": "owner",
        "username": "gov_owner",
        "display_name": "治理负责人甲",
        "role": "custom_pa",
        "capabilities": ["rsp.confirm"],
    }
    record = service.create(
        _payload(governance_owner_user_id="owner"),
        creator,
        request_id="req-create",
    )
    first = service.change_status(
        record["id"],
        {
            "target_status": "completed",
            "row_version": record["row_version"],
        },
        owner,
        request_id="req-complete-1",
    )
    reopened = service.reopen(
        record["id"],
        {"row_version": first["row_version"], "reason": "补充口径"},
        creator,
        request_id="req-reopen",
    )
    second = service.change_status(
        record["id"],
        {
            "target_status": "completed",
            "row_version": reopened["row_version"],
        },
        owner,
        request_id="req-complete-2",
    )

    requests = _requests_for(publisher, "confirmation_completed")
    assert [request.dedupe_key for request in requests] == [
        f"rsp-completed:{first['id']}:{first['row_version']}:1",
        f"rsp-completed:{second['id']}:{second['row_version']}:1",
    ]
    assert requests[0].dedupe_key != requests[1].dedupe_key
```

- [ ] **Step 8: 运行服务测试确认全部通过**

Run:

```powershell
python -m pytest tests/modules/report_special_processing/test_service.py -q
```

Expected: PASS，退出码 `0`；既有待确认通知测试与新增确认完成通知测试同时通过。

- [ ] **Step 9: 实施阶段提交检查点（仅在用户另行授权代码提交时执行）**

```powershell
git add -- src/auto_check/modules/report_special_processing/service.py tests/modules/report_special_processing/test_service.py
git commit -m "feat: 新增特殊处理确认完成通知"
```

### Task 2: 更新模块版本、发布说明和用户文档

**Files:**
- Modify: `tests/modules/report_special_processing/test_manifest_and_migrations.py:37-39`
- Modify: `src/auto_check/modules/report_special_processing/manifest.json:4,41-42`
- Modify: `src/auto_check/modules/report_special_processing/README.md`
- Modify: `README.md:18-20`
- Modify: `README.md:328-332`

**Interfaces:**
- Consumes: 模块宿主对 `manifest.release_notes` 的现有聚合协议。
- Produces: 模块版本 `1.2.9` 和发布说明 `确认完成后通知记录创建人`。
- Preserves: `schema_version=3`、三项平台服务依赖和现有权限列表。

- [ ] **Step 1: 先更新模块清单契约测试**

将清单测试中的版本与发布说明断言替换为：

```python
assert manifest.version == "1.2.9"
assert manifest.release_notes.version == "1.2.9"
assert manifest.release_notes.items == ("确认完成后通知记录创建人",)
```

- [ ] **Step 2: 运行清单测试并确认红灯原因正确**

Run:

```powershell
python -m pytest tests/modules/report_special_processing/test_manifest_and_migrations.py::test_manifest_declares_an_optional_grouped_module_and_platform_services -q
```

Expected: FAIL，实际模块版本仍为 `1.2.8`。

- [ ] **Step 3: 更新模块清单**

将 `manifest.json` 的模块版本和发布说明改为：

```json
"version": "1.2.9"
```

```json
"release_notes": {
  "version": "1.2.9",
  "items": ["确认完成后通知记录创建人"]
}
```

不得修改 `schema_version`、`service_dependencies` 或权限列表。

- [ ] **Step 4: 更新模块 README**

在“后端边界”中新增明确的通知条目：

```markdown
- 通知：正式记录进入待确认或重新产生待确认关系时，通知当前数据治理负责人；数据治理负责人成功确认完成后，通知记录创建人（`creator_user_id`），即使表单处理人不同也不改发处理人。点击完成通知打开已完成记录详情，不再次进入确认模式；通知发布失败不回滚已成功的业务状态和审计。
```

- [ ] **Step 5: 更新根 README 功能概览和当前版本详细变更**

在顶部“报表特殊处理录入”功能概览末尾补充：

```markdown
数据治理负责人确认完成后，系统向记录创建人发送成功通知，点击可定位到已完成记录详情。
```

将 `v1.2.16` 下现有报表特殊处理通知条目扩展为：

```markdown
- 报表特殊处理录入模块：待确认事项接入系统通知，新建正式记录、草稿提交、重开和改派数据治理负责人时通知对应治理负责人；数据治理负责人确认完成后通知记录创建人，点击通知打开已完成记录详情。
```

不新增系统大版本，不直接修改 `src/auto_check/web/app.js`；模块发布说明由宿主聚合。

- [ ] **Step 6: 运行清单和模块文档相关测试**

Run:

```powershell
python -m pytest tests/modules/report_special_processing/test_manifest_and_migrations.py tests/modules/report_special_processing/test_service.py -q
```

Expected: PASS，退出码 `0`。

- [ ] **Step 7: 实施阶段提交检查点（仅在用户另行授权代码提交时执行）**

```powershell
git add -- src/auto_check/modules/report_special_processing/manifest.json src/auto_check/modules/report_special_processing/README.md tests/modules/report_special_processing/test_manifest_and_migrations.py README.md
git commit -m "docs: 更新特殊处理确认通知说明"
```

### Task 3: 模块回归、全量验证和边界检查

**Files:**
- Verify only: `src/auto_check/modules/report_special_processing/`
- Verify only: `tests/modules/report_special_processing/`
- Verify only: `README.md`

**Interfaces:**
- Verifies: 设计文档第 10 节全部验收标准。
- Preserves: 通知平台、公共前端、数据库迁移、权限和状态机无越界改动。

- [ ] **Step 1: 运行整个报表特殊处理模块测试**

Run:

```powershell
python -m pytest tests/modules/report_special_processing -q
```

Expected: PASS，退出码 `0`。

- [ ] **Step 2: 运行通知平台与模块系统回归**

Run:

```powershell
python -m pytest tests/notifications tests/module_system -q
```

Expected: PASS，退出码 `0`，确认新增业务事件未改变 `platform.notification` v1 契约。

- [ ] **Step 3: 由 Luna 高推理子代理运行全量测试**

子代理只运行并报告，不修改文件：

```powershell
python -m pytest -q
```

Expected: PASS，退出码 `0`。主会话检查完整摘要、失败列表和退出码；如失败，只处理与本次改动有关的问题。

- [ ] **Step 4: 检查差异格式和模块边界**

Run:

```powershell
git diff --check
git status --short
git diff --name-only
rg -n "confirmation_completed|您提交的报表特殊处理已完成确认" src/auto_check/app/notifications src/auto_check/web
```

Expected:

- `git diff --check` 没有真实 whitespace error。
- 代码改动只出现在计划列出的模块、测试和文档文件中。
- 最后一条 `rg` 在通知平台和公共前端中无匹配，证明业务文案未进入平台内核。
- 用户原有未跟踪文件 `tag_preview.html` 保持未跟踪且内容不变。

- [ ] **Step 5: 核对最终通知数据流**

检查最终差异并确认：

```text
治理负责人确认 -> 业务状态及审计提交 -> 读取确认后 row_version
-> platform.notification v1 -> creator_user_id
-> success/task 通知 -> 点击打开已完成记录详情
```

同时确认通知发布异常仅产生脱敏警告，API 仍返回 `completed`。

- [ ] **Step 6: 报告交付状态**

最终报告分别说明：

- 代码：确认成功触发点、创建人收件口径、通知契约和失败隔离。
- 配置与数据：无新增配置、权限、迁移或数据库字段。
- 文档：模块版本、发布说明、模块 README 和根 README。
- 行为变化：创建人与处理人不同时只通知创建人，点击进入详情而非确认页。
- 验证证据：模块测试、通知与模块系统回归、全量测试和差异检查的实际结果。
- 未执行事项：未打包、未刷新可执行文件、未推送；若用户未授权实施提交，也明确说明未提交代码改动。

## Rollback

1. 移除 `change_status()` 中 `_publish_completion_notification(...)` 调用及该辅助方法。
2. 恢复 `test_service.py` 的原触发矩阵，并删除确认完成通知专用测试。
3. 将模块版本和发布说明恢复到实施前内容，撤回 README 中本场景说明。
4. 运行模块测试和 `git diff --check`；通知平台和业务数据库均无需回滚。
