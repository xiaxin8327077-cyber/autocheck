"""按冻结版本在应用库汇总批次、分页读取规则，不载入业务明细。"""

import json

from sqlalchemy import JSON, String, case, cast, func, literal, or_, select, type_coerce

from .compiler import compile_rule
from .contracts import AppError, PBC_SHARED_CATEGORY, PBC_SHARED_CATEGORY_NAME
from .sql_display import inline_sql_parameters
from .storage import EXECUTION_CHUNK, TASK_RULES, TASKS, VERSIONS, RuleStorage
from .task_results import UNCLASSIFIED, category_code, rule_view, selected_rule_ids


def summaries(connection, tasks, category=""):
    items = {}
    for task in tasks:
        items[task["id"]] = {**task, "categories": [], "sources": [], "summary": {
            "rule_count": 0, "completed_count": 0, "failed_count": 0, "issue_count": 0,
            "pending_count": 0, "truncated": False}}
    ids = list(items)
    code = RuleStorage.snapshot_category().label("snapshot_category")
    label = case((TASK_RULES.c.report_category.is_not(None), TASK_RULES.c.report_category_name),
                 else_=func.coalesce(TASK_RULES.c.report_category_name, RuleStorage.legacy_snapshot_field("report_category_name")))
    done = func.sum(case((TASK_RULES.c.status.in_(("PASS", "VIOLATION")), 1), else_=0))
    failed = func.sum(case((TASK_RULES.c.status.in_(("ERROR", "TIMEOUT", "CANCELLED")), 1), else_=0))
    query = select(TASK_RULES.c.task_id, code, func.min(label), func.count(), done, failed,
                   func.sum(TASK_RULES.c.violation_count), func.max(TASK_RULES.c.truncated)).select_from(
        TASK_RULES
    ).group_by(TASK_RULES.c.task_id, "snapshot_category").order_by(func.min(TASK_RULES.c.id))
    source_id = func.coalesce(TASK_RULES.c.source_id, RuleStorage.legacy_snapshot_field("source_id"), "").label("snapshot_source")
    sources = select(TASK_RULES.c.task_id, source_id, func.min(TASK_RULES.c.source_name), func.count()).group_by(
        TASK_RULES.c.task_id, "snapshot_source").order_by(func.min(TASK_RULES.c.id))
    for offset in range(0, len(ids), EXECUTION_CHUNK):
        batch_ids = ids[offset:offset + EXECUTION_CHUNK]
        for tid, source, name, count in connection.execute(sources.where(TASK_RULES.c.task_id.in_(batch_ids))):
            items[tid]["sources"].append({"id": source, "name": name or "", "rule_count": count})
        for tid, key, name, count, complete, fail, issues, truncated in connection.execute(
            query.where(TASK_RULES.c.task_id.in_(batch_ids))
        ):
            name = {UNCLASSIFIED: "未分类", PBC_SHARED_CATEGORY: PBC_SHARED_CATEGORY_NAME}.get(key, name or key)
            items[tid]["categories"].append({"code": key, "name": name, "rule_count": count})
            if category and key != category:
                continue
            summary = items[tid]["summary"]
            summary["rule_count"] += count
            summary["completed_count"] += int(complete)
            summary["failed_count"] += int(fail)
            summary["pending_count"] += count - int(complete) - int(fail)
            summary["issue_count"] += int(issues)
            summary["truncated"] |= bool(truncated)
    return list(items.values())


def progress(storage, owner: str, query: dict) -> list[dict]:
    raw = query.get("task_ids") or ""
    parts = str(raw).split(",") if raw else []
    if len(parts) > 20:
        raise AppError("VALIDATION_ERROR")
    ids = selected_rule_ids(parts) if parts else []
    included = TASKS.c.status.in_(("queued", "running", "pausing", "paused")) | TASKS.c.id.in_(ids)
    stmt = select(*(c for c in TASKS.c if c.name != "params_json")).where(
        TASKS.c.creator_user_id == owner, included).order_by(TASKS.c.id.desc())
    with storage.database.connect() as connection:
        return summaries(connection, connection.execute(stmt).mappings(), category_code(query.get("report_category")))


def detail(storage, task, query):
    try:
        page, size = max(1, int(query.get("page") or 1)), int(query.get("page_size") or 50)
    except (ValueError, TypeError) as exc:
        raise AppError("VALIDATION_ERROR") from exc
    size = size if size in (20, 50, 100) else 50
    category = category_code(query.get("report_category"))
    conditions = [TASK_RULES.c.task_id == task["id"]]
    if category:
        conditions.append(storage.snapshot_category() == category)
    keyword = str(query.get("keyword") or "").strip()[:200].lower()
    if keyword:
        fields = [storage.legacy_snapshot_field(key) for key in ("name", "rule_name", "table_name")]
        fields += [TASK_RULES.c.source_name, TASK_RULES.c.table_name_cn]
        identifier = cast(TASK_RULES.c.rule_id, String)
        padded = case((func.length(identifier) < 6, func.substr(literal("000000") + identifier, -6)), else_=identifier)
        fields.append(literal("DV") + padded)
        matches = [func.lower(func.coalesce(field, "")).contains(keyword, autoescape=True) for field in fields]
        conditions.append(or_(*matches))
    with storage.database.connect() as connection:
        result, = summaries(connection, [task], category)
        count = result["summary"]["rule_count"]
        if str(query.get("only_issues") or "").lower() in {"1", "true"}:
            conditions.append(TASK_RULES.c.violation_count > 0)
        if keyword or str(query.get("only_issues") or "").lower() in {"1", "true"}:
            count = connection.scalar(select(func.count()).select_from(TASK_RULES).where(*conditions))
        page = min(page, max(1, (count + size - 1) // size))
        definition = type_coerce(VERSIONS.c.definition_json, JSON)
        review = storage.snapshot_select().add_columns(VERSIONS.c.sql_text,
            VERSIONS.c.definition_json.label("_review_definition"),
            *(definition[key].as_string().label(key) for key in ("description", "violation_message")))
        rows = connection.execute(review.where(*conditions).order_by(TASK_RULES.c.id)
                                  .limit(size).offset((page - 1) * size)).mappings()
        result["rules"] = [_review_rule(dict(row), task["report_period"]) for row in rows]
    result["rule_page"] = {"total": count, "page": page, "page_size": size}
    if keyword:
        result["rule_page"]["keyword"] = str(query.get("keyword") or "").strip()[:200]
    result["total_rule_count"] = sum(c["rule_count"] for c in result["categories"])
    return result


def _review_rule(row, report_period):
    definition_json = row.pop("_review_definition", None)
    result = rule_view(row)
    try:
        definition = json.loads(definition_json) if isinstance(definition_json, str) else definition_json
        if definition.get("rule_type") == "custom_sql":
            sql = result["sql_text"] or definition.get("sql") or ""
            params = dict(definition.get("params") or {})
        else:
            compiled_sql, params = compile_rule({"definition": definition})
            sql = result["sql_text"] or compiled_sql
        # 与执行器一致：静态参数来自冻结定义，报送期由批次覆盖。
        params = {**params, "report_date": str(report_period)}
        result["sql_display"] = inline_sql_parameters(sql, params, definition["dialect"],
                                                     preserve_report_date=False, require_all_parameters=True)
    except (AppError, TypeError, ValueError, KeyError, AttributeError):
        result["sql_display_error"] = "EXECUTION_SQL_DISPLAY_UNAVAILABLE"
    return result
