"""规则修改历史的差异、快照与旧版本兼容组装。"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Mapping

_HISTORY_ACTIONS = {"create", "update", "confirm", "disable", "copy"}
_VERSION_ACTIONS = {"create", "update", "copy"}
_SENSITIVE_NAMES = {
    "api_key", "apikey", "password", "secret", "token", "authorization",
    "credential", "credentials", "access_key", "private_key", "connection_string",
}
_MASK = "********"
_SORT_REAL_EVENT = 1
_SORT_SYNTHESIZED_EVENT = 0
_SORT_SAVE_EVENT = 0
_SORT_CONFIRM_EVENT = 1
_LABELS = {
    "name": "规则名称",
    "rule_name": "规则名称",
    "description": "规则说明",
    "source_id": "数据源",
    "table_name": "目标表",
    "rule_type": "规则类型",
    "dialect": "数据库方言",
    "business_key": "业务键",
    "violation_message": "异常提示",
    "null_policy": "空值处理口径",
    "equality_policy": "相等值处理口径",
    "mapping_version": "字段映射版本",
    "generation_mode": "生成方式",
    "expression.left": "比较左字段",
    "expression.op": "比较运算符",
    "expression.right_type": "比较目标类型",
    "expression.right": "比较右字段",
    "expression.right_table": "比较右字段所属表",
    "filters": "适用范围筛选",
    "join": "两表关联口径",
    "join.table_name": "关联表",
    "join.on": "两表关联键",
    "join.report_date_field": "关联表校验日期字段",
    "join.relationship_confirmed": "关联含义已确认",
    "join.unmatched_policy": "无关联记录处理口径",
    "assets": "资产字段",
    "liabilities": "负债字段",
    "equity": "权益字段",
    "tolerance": "金额容差",
    "field": "校验字段",
    "allowed": "允许值",
    "keys": "唯一键字段",
    "other_table": "关联表",
    "key": "本表关联字段",
    "other_key": "关联表字段",
    "params": "SQL 参数",
    "sql": "自定义 SQL",
    "identifiers": "标识符",
    "report_date": "报送日期",
    "report_date_field": "校验日期字段",
    "uncertainties": "待确认事项",
    "uncertainty_resolutions": "口径处理说明",
    "unsupported_requirements": "当前规则不支持的要求",
}


def operator_name(user: Mapping[str, Any]) -> str:
    """Return the name snapshot used by both history writes and responses."""

    return str(user.get("display_name") or user.get("username") or user.get("id") or "")


def definition_changes(before: Any, after: Any) -> list[dict[str, Any]]:
    """Recursively diff mappings while retaining only changed values."""

    changes: list[dict[str, Any]] = []
    _diff_value("", before, after, changes)
    return changes


def history_event(
    action_code: str,
    user: Mapping[str, Any],
    *,
    version_no: int | None,
    content_sha256: str = "",
    changes: list[dict[str, Any]] | None = None,
    before_status: str | None = None,
    after_status: str | None = None,
    summary: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the small, persistable event; never retain the request payload."""

    if action_code not in _HISTORY_ACTIONS:
        raise ValueError("unsupported rule history action")
    event = dict(details or {})
    event.update({
        "history_schema": 1,
        "action_code": action_code,
        "version_no": version_no,
        "operator_user_id": str(user.get("id") or ""),
        "operator_name": operator_name(user),
        "operator_username": str(user.get("username") or ""),
        "content_sha256": str(content_sha256 or ""),
        "summary": summary,
        "changes": changes or [],
        "before_status": before_status,
        "after_status": after_status,
    })
    return event


def merge_rule_history(
    *,
    rule: Mapping[str, Any],
    versions: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    confirmations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge persistent events with legacy rows without modifying either source."""

    sortable: list[tuple[tuple[str, int, int, int, int, str], dict[str, Any]]] = []
    seen_version_actions: set[tuple[int, str]] = set()
    for row in sorted(audits, key=lambda item: int(item["id"])):
        action = str(row["action_code"])
        if action not in _HISTORY_ACTIONS:
            continue
        detail = _json_object(row.get("detail_json"))
        version_no = _optional_int(detail.get("version_no"))
        if version_no is not None and action in _VERSION_ACTIONS | {"confirm"}:
            seen_version_actions.add((version_no, action))
        item = _history_item(
            item_id=f"audit-{int(row['id'])}",
            action_code=action,
            version_no=version_no,
            operator_user_id=str(row.get("operator_user_id") or ""),
            operator_name=str(
                detail.get("operator_name")
                or detail.get("operator_username")
                or row.get("operator_user_id")
                or ""
            ),
            created_at=str(row.get("created_at") or ""),
            summary=str(detail.get("summary") or _default_summary(action, version_no)),
            changes=_safe_changes(detail.get("changes")),
            before_status=_optional_string(detail.get("before_status")),
            after_status=_optional_string(detail.get("after_status")),
        )
        sortable.append((_audit_event_key(item, int(row["id"])), item))

    for row in sorted(confirmations, key=lambda item: int(item["id"])):
        version_no = int(row["version_no"])
        if (version_no, "confirm") in seen_version_actions:
            continue
        passed = int(row.get("passed_count") or 0)
        failed = int(row.get("failed_count") or 0)
        not_run = int(row.get("not_run_count") or 0)
        digest = str(row.get("content_sha256") or "")
        item = _history_item(
            item_id=f"confirmation-{int(row['id'])}",
            action_code="confirm",
            version_no=version_no,
            operator_user_id=str(row.get("confirmer_user_id") or ""),
            operator_name=str(row.get("confirmer_user_id") or ""),
            created_at=str(row.get("created_at") or ""),
            summary=_confirmation_summary(version_no, digest, passed, failed, not_run),
            changes=[],
            before_status=None,
            after_status="enabled",
        )
        sortable.append((_synthesized_event_key(item, version_no, _SORT_CONFIRM_EVENT, int(row["id"])), item))

    ordered_versions = sorted(versions, key=lambda item: (int(item["version_no"]), int(item["id"])))
    previous_definition: Any = None
    for row in ordered_versions:
        version_no = int(row["version_no"])
        definition = _json_value(row.get("definition_json"))
        action = "create" if version_no == 1 else "update"
        copied = version_no == 1 and (1, "copy") in seen_version_actions
        if (version_no, action) not in seen_version_actions and not copied:
            before = None if version_no == 1 else previous_definition
            changes = definition_changes(before, definition)
            digest = str(row.get("content_sha256") or "")
            if action == "create":
                summary = f"创建规则，保存版本 {version_no}，哈希 {digest}"
                before_status = None
            else:
                summary = f"编辑保存版本 {version_no}，变更 {len(changes)} 项，哈希 {digest}"
                before_status = "draft"
            creator = str(rule.get("creator_user_id") or "")
            item = _history_item(
                item_id=f"version-{int(row['id'])}",
                action_code=action,
                version_no=version_no,
                operator_user_id=creator,
                operator_name=creator,
                created_at=str(row.get("created_at") or ""),
                summary=summary,
                changes=changes,
                before_status=before_status,
                after_status=str(row.get("status") or "draft"),
            )
            sortable.append((_synthesized_event_key(item, version_no, _SORT_SAVE_EVENT, int(row["id"])), item))
        previous_definition = definition

    return [item for _sort_key, item in sorted(sortable, key=lambda pair: pair[0], reverse=True)]


def _audit_event_key(item: Mapping[str, Any], audit_id: int) -> tuple[str, int, int, int, int, str]:
    """真实审计事件的排序键：同一秒内按自身 id 保持因果，并排在遗留合成事件之上。"""

    return (str(item["created_at"]), _SORT_REAL_EVENT, 0, 0, int(audit_id), str(item["id"]))


def _synthesized_event_key(
    item: Mapping[str, Any], version_no: int, action_rank: int, row_id: int,
) -> tuple[str, int, int, int, int, str]:
    """遗留合成事件的排序键：同一秒内按 version_no 降序，同一版本的确认排在保存之上。"""

    return (
        str(item["created_at"]), _SORT_SYNTHESIZED_EVENT, int(version_no),
        int(action_rank), int(row_id), str(item["id"]),
    )


def _diff_value(path: str, before: Any, after: Any, changes: list[dict[str, Any]], label: str = "") -> None:
    if isinstance(after, Mapping) and before is None:
        before = {}
    if isinstance(before, Mapping) and after is None:
        after = {}
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        for key in sorted(set(before) | set(after), key=str):
            name = str(key)
            child_path = f"{path}.{name}" if path else name
            child_label = ""
            if path == "expression" and name == "right":
                right_type = after.get("right_type") if isinstance(after, Mapping) else None
                if right_type is None and isinstance(before, Mapping):
                    right_type = before.get("right_type")
                if right_type == "value":
                    child_label = "比较数值常量"
            _diff_value(child_path, before.get(key), after.get(key), changes, child_label)
        return
    if before == after:
        return
    sensitive = _is_sensitive(path)
    changes.append({
        "field": path or "definition",
        "label": label or field_label(path),
        "before": _safe_value(before, sensitive=sensitive),
        "after": _safe_value(after, sensitive=sensitive),
    })


def field_label(path: str) -> str:
    if path in _LABELS:
        return _LABELS[path]
    leaf = path.rsplit(".", 1)[-1]
    if leaf in _LABELS:
        return _LABELS[leaf]
    return f"规则配置（{path or 'definition'}）"


def _safe_value(value: Any, *, sensitive: bool = False) -> Any:
    if sensitive:
        return None if value is None else _MASK
    if isinstance(value, Mapping):
        return {
            str(key): _safe_value(item, sensitive=_is_sensitive(str(key)))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_value(item) for item in value]
    return deepcopy(value)


def _safe_changes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for entry in value:
        if not isinstance(entry, Mapping):
            continue
        field = str(entry.get("field") or "definition")
        sensitive = _is_sensitive(field)
        result.append({
            "field": field,
            "label": str(entry.get("label") or field_label(field)),
            "before": _safe_value(entry.get("before"), sensitive=sensitive),
            "after": _safe_value(entry.get("after"), sensitive=sensitive),
        })
    return result


def _is_sensitive(path: str) -> bool:
    normalized = path.lower().replace("-", "_")
    segments = set(normalized.split("."))
    if segments & _SENSITIVE_NAMES:
        return True
    return any(
        segment.endswith(("_password", "_secret", "_token", "_api_key", "_credential"))
        for segment in segments
    )


def _history_item(**values: Any) -> dict[str, Any]:
    return {
        "id": values["item_id"],
        "action_code": values["action_code"],
        "version_no": values["version_no"],
        "operator_user_id": values["operator_user_id"],
        "operator_name": values["operator_name"],
        "created_at": values["created_at"],
        "summary": values["summary"],
        "changes": values["changes"],
        "before_status": values["before_status"],
        "after_status": values["after_status"],
    }


def _confirmation_summary(version_no: int, digest: str, passed: int, failed: int, not_run: int) -> str:
    return (
        f"确认启用版本 {version_no}；测试通过 {passed}、失败 {failed}、未运行 {not_run}；"
        f"哈希 {digest}"
    )


def _default_summary(action: str, version_no: int | None) -> str:
    labels = {
        "create": "创建规则",
        "update": "编辑保存规则",
        "confirm": "确认启用规则",
        "disable": "停用规则",
        "copy": "复制创建规则",
    }
    suffix = f"，版本 {version_no}" if version_no is not None else ""
    return f"{labels.get(action, action)}{suffix}"


def _json_object(value: Any) -> dict[str, Any]:
    decoded = _json_value(value)
    return dict(decoded) if isinstance(decoded, Mapping) else {}


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)
