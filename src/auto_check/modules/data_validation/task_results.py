"""只用批次实际记录的规则版本构建执行范围和结果摘要。"""

from __future__ import annotations

from typing import Any

from .contracts import AppError, PBC_REPORT_CATEGORIES, PBC_SHARED_CATEGORY, PBC_SHARED_CATEGORY_NAME


UNCLASSIFIED = "__uncategorized__"
MAX_TASK_RULES = 100_000


def selected_rule_ids(raw: Any) -> list[int]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_TASK_RULES:
        raise AppError("VALIDATION_ERROR")
    ids = []
    for value in raw:
        if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 19:
            value = int(value)
        if type(value) is not int or not 1 <= value <= 2**63 - 1:
            raise AppError("VALIDATION_ERROR")
        ids.append(value)
    if len(set(ids)) != len(ids):
        raise AppError("VALIDATION_ERROR")
    return ids


def category_code(value: Any) -> str:
    code = str(value or "").strip()
    return PBC_SHARED_CATEGORY if code in PBC_REPORT_CATEGORIES else code


def rule_view(item: dict) -> dict:
    code = category_code(item["report_category"]) or UNCLASSIFIED
    if code == UNCLASSIFIED:
        name = "未分类"
    elif code == PBC_SHARED_CATEGORY:
        name = PBC_SHARED_CATEGORY_NAME
    else:
        name = item["report_category_name"] or code
    alias = item.pop("rule_name", "")
    return {
        **item, "rule_code": f"DV{item['rule_id']:06d}",
        "name": item["name"] or alias or "未命名规则",
        "report_category": code, "report_category_name": name, "truncated": bool(item["truncated"]),
        "source_id": item["source_id"] or "", "table_name": item["table_name"] or "",
        "source_name": item["source_name"] or "", "table_name_cn": item["table_name_cn"] or "",
    }


def scoped_rules(rules: list[dict], query: dict) -> list[dict]:
    category = category_code(query.get("report_category"))
    selected = query.get("rule_id")
    if selected not in (None, ""):
        try:
            selected = int(selected)
        except (TypeError, ValueError) as exc:
            raise AppError("VALIDATION_ERROR") from exc
        if selected < 1:
            raise AppError("VALIDATION_ERROR")
    return [r for r in rules if (not category or r["report_category"] == category)
            and (not selected or r["rule_id"] == selected)]


def batch_view(task: dict, rules: list[dict], selected: list[dict]) -> dict:
    categories: dict[str, dict] = {}
    for row in rules:
        code = row["report_category"]
        group = categories.setdefault(code, {"code": code, "name": row["report_category_name"], "rule_count": 0})
        group["rule_count"] += 1
    completed = sum(r["status"] in {"PASS", "VIOLATION"} for r in selected)
    failed = sum(r["status"] in {"ERROR", "TIMEOUT", "CANCELLED"} for r in selected)
    return {
        **task, "categories": list(categories.values()),
        "summary": {
            "rule_count": len(selected), "completed_count": completed, "failed_count": failed,
            "pending_count": len(selected) - completed - failed, "issue_count": sum(r["violation_count"] for r in selected),
            "truncated": any(r["truncated"] for r in selected),
        },
    }


def issue_page(storage, task: dict, scope: dict, page: int, size: int) -> dict:
    raw = scope.get("rule_id")
    rule_id = selected_rule_ids([raw])[0] if raw not in (None, "") else None
    result, snapshots, truncated = storage.scoped_issue_page(
        task["id"], rule_id, category_code(scope.get("report_category")), page, size)
    rules = (rule_view(row) for row in snapshots)
    by_version = {(r["rule_id"], r["version_no"]): r for r in rules}
    for issue in result["items"]:
        snapshot = by_version.get((issue["rule_id"], issue["version_no"]), {})
        issue.update(rule_name=snapshot.get("name", ""), rule_code=snapshot.get("rule_code", ""),
                     report_category=snapshot.get("report_category", UNCLASSIFIED),
                     report_category_name=snapshot.get("report_category_name", "未分类"))
    return {**result, "truncated": truncated,
            "report_period": task["report_period"], "task_id": task["id"]}
