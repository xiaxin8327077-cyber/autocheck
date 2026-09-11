"""结构化特殊处理内容的语义化审计 Diff。

处理表、条件和修改字段优先按持久化 item_id 匹配；历史数据没有 item_id 时，
仅在物理对象身份唯一或只剩一个明确候选时保守匹配，避免把删除后重新添加误判为修改。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any


TABLE_INFO_KEYS = (
    "datasource_id",
    "datasource_name",
    "datasource_type",
    "schema",
    "table_name",
    "chinese_table_name",
)
SCOPE_INFO_KEYS = ("limit_report_period", "report_period_field")
CONDITION_KEYS = ("column_name", "operator", "values")
FIELD_KEYS = ("column_name", "chinese_column_name", "value_before", "value_after")


def _objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _item_id(item: Mapping[str, Any]) -> str:
    return str(item.get("item_id") or "").strip()


def _match_items(
    old_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    identity: Callable[[Mapping[str, Any]], tuple[Any, ...]],
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    old_used: set[int] = set()
    new_used: set[int] = set()

    new_ids = {_item_id(item): index for index, item in enumerate(new_items) if _item_id(item)}
    for old_index, old_item in enumerate(old_items):
        old_id = _item_id(old_item)
        new_index = new_ids.get(old_id) if old_id else None
        if new_index is None or new_index in new_used:
            continue
        pairs.append((old_item, new_items[new_index]))
        old_used.add(old_index)
        new_used.add(new_index)

    for old_index, old_item in enumerate(old_items):
        if old_index in old_used:
            continue
        key = identity(old_item)
        candidates = [
            new_index for new_index, new_item in enumerate(new_items)
            if new_index not in new_used
            and identity(new_item) == key
            and not (_item_id(old_item) and _item_id(new_item))
        ]
        if len(candidates) != 1:
            continue
        new_index = candidates[0]
        pairs.append((old_item, new_items[new_index]))
        old_used.add(old_index)
        new_used.add(new_index)

    remaining_old = [index for index in range(len(old_items)) if index not in old_used]
    remaining_new = [index for index in range(len(new_items)) if index not in new_used]
    if len(remaining_old) == len(remaining_new) == 1:
        old_index, new_index = remaining_old[0], remaining_new[0]
        old_item, new_item = old_items[old_index], new_items[new_index]
        if not (_item_id(old_item) and _item_id(new_item)):
            pairs.append((old_item, new_item))
            old_used.add(old_index)
            new_used.add(new_index)

    added = [item for index, item in enumerate(new_items) if index not in new_used]
    removed = [item for index, item in enumerate(old_items) if index not in old_used]
    return pairs, added, removed


def _value_equal(key: str, old: Any, new: Any, old_parent: Mapping[str, Any], new_parent: Mapping[str, Any]) -> bool:
    if key == "values" and str(old_parent.get("operator") or "").upper() == "IN" \
            and str(new_parent.get("operator") or "").upper() == "IN":
        return set(old or []) == set(new or [])
    return old == new


def _changed_values(
    old: Mapping[str, Any], new: Mapping[str, Any], keys: Sequence[str],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key in keys:
        old_value = old.get(key)
        new_value = new.get(key)
        if _value_equal(key, old_value, new_value, old, new):
            continue
        changes.append({"key": key, "old": deepcopy(old_value), "new": deepcopy(new_value)})
    return changes


def _condition_identity(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (str(item.get("column_name") or ""),)


def _field_identity(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (str(item.get("column_name") or ""),)


def _table_identity(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(item.get("datasource_id") or ""),
        str(item.get("schema") or ""),
        str(item.get("table_name") or ""),
    )


def _semantic_events(
    old_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    *,
    identity: Callable[[Mapping[str, Any]], tuple[Any, ...]],
    keys: Sequence[str],
) -> list[dict[str, Any]]:
    pairs, added, removed = _match_items(old_items, new_items, identity)
    modified: list[dict[str, Any]] = []
    for old_item, new_item in pairs:
        changes = _changed_values(old_item, new_item, keys)
        if changes:
            modified.append({
                "change": "modified",
                "item_id": _item_id(new_item) or _item_id(old_item),
                "before": deepcopy(old_item),
                "after": deepcopy(new_item),
                "changes": changes,
                "change_count": len(changes),
            })
    return [
        *modified,
        *({"change": "added", "item_id": _item_id(item), "after": deepcopy(item), "change_count": 1}
          for item in added),
        *({"change": "removed", "item_id": _item_id(item), "before": deepcopy(item), "change_count": 1}
          for item in removed),
    ]


def _modified_table(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any] | None:
    table_info = _changed_values(old, new, TABLE_INFO_KEYS)
    scope_info = _changed_values(old, new, SCOPE_INFO_KEYS)
    conditions = _semantic_events(
        _objects(old.get("conditions")), _objects(new.get("conditions")),
        identity=_condition_identity, keys=CONDITION_KEYS,
    )
    fields = _semantic_events(
        _objects(old.get("fields")), _objects(new.get("fields")),
        identity=_field_identity, keys=FIELD_KEYS,
    )
    change_count = len(table_info) + len(scope_info)
    change_count += sum(int(item["change_count"]) for item in conditions)
    change_count += sum(int(item["change_count"]) for item in fields)
    if not change_count:
        return None
    return {
        "change": "modified",
        "item_id": _item_id(new) or _item_id(old),
        "before": deepcopy(dict(old)),
        "after": deepcopy(dict(new)),
        "table_info": table_info,
        "scope_info": scope_info,
        "conditions": conditions,
        "fields": fields,
        "change_count": change_count,
    }


def build_structured_audit_diff(
    old_content: Mapping[str, Any] | None,
    new_content: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """返回适合持久化和前端渲染的结构化语义 Diff；无变化时返回 None。"""
    if not isinstance(old_content, Mapping) or not isinstance(new_content, Mapping):
        return None
    old_tables = _objects(old_content.get("tables"))
    new_tables = _objects(new_content.get("tables"))
    pairs, added, removed = _match_items(old_tables, new_tables, _table_identity)

    modified = [item for old, new in pairs if (item := _modified_table(old, new)) is not None]
    table_changes = [
        *modified,
        *({
            "change": "added", "item_id": _item_id(item), "after": deepcopy(item), "change_count": 1,
        } for item in added),
        *({
            "change": "removed", "item_id": _item_id(item), "before": deepcopy(item), "change_count": 1,
        } for item in removed),
    ]
    if not table_changes:
        return None
    return {
        "changed": True,
        "change_count": sum(int(item["change_count"]) for item in table_changes),
        "affected_tables": len(table_changes),
        "modified_tables": len(modified),
        "added_tables": len(added),
        "removed_tables": len(removed),
        "tables": table_changes,
    }
