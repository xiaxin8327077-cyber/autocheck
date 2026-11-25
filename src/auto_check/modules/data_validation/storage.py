"""数据校验模块的应用库存储。列表查询在 SQL 里分页。"""

from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, Index, Integer, MetaData, Select, String, Table, Text, and_, case, delete, desc, func, insert, select, tuple_, type_coerce, update

from sqlalchemy.exc import IntegrityError

from . import analysis_memory
from .analysis_result_cache import result_key
from .contracts import AppError, PBC_REPORT_CATEGORIES, PBC_SHARED_CATEGORY
from .history import HISTORY_ACTIONS, history_event, merge_rule_history
from .task_results import MAX_TASK_RULES, UNCLASSIFIED, category_code
from .issue_query_results import encode_result

METADATA = MetaData()
EXECUTION_CHUNK = 500
_RULE_DESCRIPTION_LIMIT = 1_000

ANALYSIS_RESULTS = Table(
    "data_validation_analysis_results", METADATA,
    Column("cache_key", String(64), primary_key=True),
    Column("response_json", Text, nullable=False),
    Column("updated_at", String(32), nullable=False),
)

ANALYSIS_MEMORIES = Table(
    "data_validation_analysis_memories", METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("memory_key", String(64), nullable=False, unique=True),
    Column("context_key", String(64), nullable=False),
    Column("request_key", String(64), nullable=False),
    Column("pattern_key", String(64), nullable=False),
    Column("request_text", Text, nullable=False),
    Column("baseline_json", Text, nullable=False),
    Index("dv_memory_exact", "context_key", "request_key", "id"),
    Index("dv_memory_pattern", "context_key", "pattern_key", "id"),
    Index("dv_memory_recent", "context_key", "id"),
)

RULES = Table(
    "data_validation_rules",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("rule_code", String(32), nullable=False),
    Column("name", String(200), nullable=False),
    Column("description", String(_RULE_DESCRIPTION_LIMIT), nullable=False),
    Column("creator_user_id", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("current_version_id", Integer),
    Column("source_id", String(64), nullable=False),
    Column("table_name", String(128), nullable=False),
    Column("report_category", String(64), nullable=False, server_default=""),
    Column("rule_type", String(64), nullable=False),
    Column("updated_at", String(32), nullable=False),
)
VERSIONS = Table(
    "data_validation_rule_versions",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("rule_id", Integer, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("definition_json", String, nullable=False),
    Column("sql_text", String, nullable=False),
    Column("mapping_version", String(64), nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("generation_mode", String(16), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", String(32), nullable=False),
)
AUDITS = Table(
    "data_validation_audit_logs",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("rule_id", Integer),
    Column("task_id", Integer),
    Column("action_code", String(64), nullable=False),
    Column("operator_user_id", String(64), nullable=False),
    Column("detail_json", String, nullable=False),
    Column("created_at", String(32), nullable=False),
)
SETTINGS = Table(
    "data_validation_settings",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_allowlist_json", String, nullable=False),
    Column("max_rules_per_task", Integer, nullable=False),
    Column("source_concurrency", Integer, nullable=False),
    Column("rule_timeout_seconds", Integer, nullable=False),
    Column("task_timeout_seconds", Integer, nullable=False),
    Column("issue_preview_limit", Integer, nullable=False),
)
TRUST_KNOWLEDGE = Table(
    "data_validation_trust_knowledge",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("revision", Integer, nullable=False),
    Column("active_revision", Integer, nullable=False),
    Column("draft_json", Text, nullable=False),
    Column("active_json", Text, nullable=False),
    Column("updated_by", String(64), nullable=False),
    Column("updated_at", String(32), nullable=False),
)
INVOCATIONS = Table(
    "data_validation_ai_invocations",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("operator_user_id", String(64), nullable=False),
    Column("model_id", String(64), nullable=False),
    Column("model_name", String(200), nullable=False),
    Column("prompt_version", String(64), nullable=False),
    Column("tool_names", String(500), nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("error_code", String(64), nullable=False),
    Column("created_at", String(32), nullable=False),
)
CASES = Table(
    "data_validation_test_cases",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("rule_id", Integer, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("case_name", String(64), nullable=False),
    Column("input_json", String, nullable=False),
    Column("expected_count", Integer, nullable=False),
    Column("actual_count", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", String(32), nullable=False),
)
CONFIRMATIONS = Table(
    "data_validation_confirmations",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("rule_id", Integer, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("version_id", Integer, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("confirmer_user_id", String(64), nullable=False),
    Column("passed_count", Integer, nullable=False),
    Column("failed_count", Integer, nullable=False),
    Column("not_run_count", Integer, nullable=False),
    Column("created_at", String(32), nullable=False),
)
TASKS = Table(
    "data_validation_tasks",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("creator_user_id", String(64), nullable=False),
    Column("source_id", String(64), nullable=False),
    Column("report_period", String(10), nullable=False),
    Column("status", String(32), nullable=False),
    Column("params_json", String, nullable=False),
    Column("truncated", Integer, nullable=False),
    Column("created_at", String(32), nullable=False),
)
TASK_RULES = Table(
    "data_validation_task_rules",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_id", Integer, nullable=False),
    Column("rule_id", Integer, nullable=False),
    Column("version_id", Integer, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("sql_summary", String, nullable=False),
    Column("source_id", String(64)),
    Column("source_name", Text),
    Column("table_name_cn", Text),
    Column("report_category_name", Text),
    Column("report_category", String(64)),
    Column("execution_generation", Integer, nullable=False, server_default="0"),
    Column("status", String(32), nullable=False),
    Column("violation_count", Integer, nullable=False),
    Column("truncated", Integer, nullable=False),
    Column("error_code", String(64), nullable=False),
)
ISSUES = Table(
    "data_validation_issues",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_id", Integer, nullable=False),
    Column("rule_id", Integer, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("business_key", String(200), nullable=False),
    Column("project_code", Text),
    Column("project_name", Text),
    Column("project_name_status", String(32), nullable=False, server_default="legacy_unavailable"),
    Column("query_result_json", Text),
    Column("issue_kind", String(32), nullable=False, server_default="legacy"),
    Column("message", String(500), nullable=False),
    Column("created_at", String(32), nullable=False),
)



DOCUMENTS = Table(
    "data_validation_documents",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(200), nullable=False),
    Column("file_name", String(255), nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("table_count", Integer, nullable=False),
    Column("field_count", Integer, nullable=False),
    Column("warnings_json", String, nullable=False),
    Column("imported_by", String(64), nullable=False),
    Column("imported_at", String(32), nullable=False),
    Column("activated_at", String(32)),
)
DOC_TABLES = Table(
    "data_validation_doc_tables",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("document_id", Integer, nullable=False),
    Column("data_source_name", String(128), nullable=False),
    Column("table_name", String(128), nullable=False),
    Column("table_name_cn", String(255), nullable=False),
    Column("sheet_name", String(200), nullable=False),
    Column("source_desc", String, nullable=False),
    Column("dimension", String(128), nullable=False),
    Column("period", String(64), nullable=False),
    Column("scope", String, nullable=False),
    Column("sort_order", Integer, nullable=False),
)
DOC_FIELDS = Table(
    "data_validation_doc_fields",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_id", Integer, nullable=False),
    Column("field_name", String(128), nullable=False),
    Column("field_cn", String(255), nullable=False),
    Column("data_type", String(64), nullable=False),
    Column("is_pk", String(1), nullable=False),
    Column("nullable", String(8), nullable=False),
    Column("default_value", String(255), nullable=False),
    Column("dictionary", String, nullable=False),
    Column("logic", String, nullable=False),
    Column("source_table", String(200), nullable=False),
    Column("source_field", String(128), nullable=False),
    Column("source_field_cn", String(255), nullable=False),
    Column("source_table_cn", String(255), nullable=False),
    Column("sort_order", Integer, nullable=False),
)
PROMPTS = Table(
    "data_validation_prompt_templates",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("stage", String(32), nullable=False),
    Column("content", String, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("is_active", Integer, nullable=False),
    Column("updated_by", String(64), nullable=False),
    Column("updated_at", String(32), nullable=False),
)
SOURCE_RULES = Table(
    "data_validation_doc_source_rules",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("sheet_prefix", String(128), nullable=False),
    Column("data_source_name", String(128), nullable=False),
    Column("sort_order", Integer, nullable=False),
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _rule_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["current_version_id"] = data.get("current_version_id")
    return data


class RuleStorage:
    def __init__(self, database: Any) -> None:
        self.database = database

    def _begin(self) -> Any:
        """兼容应用库（transaction）与测试库（begin）两种事务接口。"""
        transaction = getattr(self.database, "transaction", None)
        if callable(transaction):
            return transaction()
        return self.database.begin()

    @contextmanager
    def _rule_transaction(self):
        with self._begin() as connection:
            # SQLite 忽略 FOR UPDATE，须在读取待修改状态前取得写锁。
            if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            yield connection

    @staticmethod
    def _lock_rule(connection: Any, rule_id: int, *, allow_deleted: bool = False) -> dict[str, Any]:
        row = connection.execute(
            select(RULES).where(RULES.c.id == rule_id).with_for_update()
        ).mappings().one_or_none()
        if row is None:
            raise AppError("RULE_NOT_FOUND")
        if row["status"] == "deleted" and not allow_deleted:
            raise AppError("RULE_DELETED")
        return _rule_row(row)

    def cached_analysis_result(self, context: dict, request_text: str) -> dict | None:
        key = result_key(context, request_text)
        if not key:
            return None
        with self.database.connect() as connection:
            content = connection.execute(select(ANALYSIS_RESULTS.c.response_json).where(
                ANALYSIS_RESULTS.c.cache_key == key)).scalar_one_or_none()
        if content is None:
            return None
        try:
            result = json.loads(content)
        except (ValueError, TypeError):
            return None
        return result if isinstance(result, dict) else None

    def publish_analysis(self, context: dict, request_text: str, baseline: dict | None, responses: list[dict]) -> None:
        if baseline is None and not responses:
            return
        with self._rule_transaction() as connection:
            if baseline is not None:
                self.remember_analysis_memory(context, request_text, baseline, connection)
            for response in responses:
                self.remember_analysis_result(context, request_text, response, connection)

    def remember_analysis_result(self, context: dict, request_text: str, response: dict, connection=None) -> None:
        key = result_key(context, request_text)
        if not key:
            return
        values = {"response_json": json.dumps(response, ensure_ascii=True), "updated_at": _now()}
        with (nullcontext(connection) if connection is not None else self._rule_transaction()) as transaction:
            try:
                with transaction.begin_nested():
                    transaction.execute(insert(ANALYSIS_RESULTS).values(cache_key=key, **values))
            except IntegrityError:
                updated = transaction.execute(update(ANALYSIS_RESULTS).where(ANALYSIS_RESULTS.c.cache_key == key).values(**values))
                if not updated.rowcount:
                    raise

    def remember_analysis_memory(self, context: dict, request_text: str, baseline: dict, connection=None) -> None:
        namespace = analysis_memory.context_key(context)
        example = analysis_memory.safe_example(request_text, baseline)
        if not namespace or not example:
            return
        request_key, pattern = analysis_memory.request_keys(request_text)
        key = analysis_memory.digest([namespace, request_key, analysis_memory.example_signature(example)])
        row = {"memory_key": key, "context_key": namespace, "request_key": request_key, "pattern_key": pattern,
               "request_text": request_text.strip(), "baseline_json": json.dumps(example, ensure_ascii=False)}
        # The unique key covers retries and simultaneous analyses by different users.
        with (nullcontext(connection) if connection is not None else self._rule_transaction()) as transaction:
            try:
                with transaction.begin_nested():
                    transaction.execute(insert(ANALYSIS_MEMORIES).values(**row))
            except IntegrityError:
                existing = select(ANALYSIS_MEMORIES.c.id).where(ANALYSIS_MEMORIES.c.memory_key == key).with_for_update()
                if not transaction.execute(existing).first():
                    raise

    def find_analysis_memories(self, context: dict, request_text: str, limit: int = 8) -> list[dict]:
        namespace = analysis_memory.context_key(context)
        if not namespace or not isinstance(request_text, str) or not request_text.strip() or limit <= 0:
            return []
        limit = min(limit, 32)
        request_key, pattern = analysis_memory.request_keys(request_text[:4000])
        cols = ANALYSIS_MEMORIES.c
        scoped = select(cols.id, cols.request_key, cols.pattern_key, cols.request_text, cols.baseline_json).where(
            cols.context_key == namespace).order_by(cols.id.desc())
        with self.database.connect() as connection:
            # Indexed lookups preserve old exact and same-threshold-pattern hits even after many unrelated analyses.
            candidates = {}
            for query in (scoped.where(cols.request_key == request_key).limit(limit),
                          scoped.where(cols.pattern_key == pattern).limit(limit), scoped.limit(96)):
                for row in connection.execute(query).mappings():
                    candidates[row["id"]] = row
            if not candidates:
                return []
            wanted = analysis_memory.text_fragments(request_text[:4000])

            def rank(row):
                terms = analysis_memory.text_fragments(row["request_text"])
                overlap = len(wanted & terms) / max(1, len(wanted | terms))
                return row["request_key"] == request_key, row["pattern_key"] == pattern, overlap, row["id"]

            ranked = sorted(candidates.values(), key=rank, reverse=True)[:limit]
            conflicts = set(connection.execute(select(cols.request_key).where(
                cols.context_key == namespace, cols.request_key.in_({r["request_key"] for r in ranked})
            ).group_by(cols.request_key).having(func.count() > 1)).scalars())
        result = []
        for row in ranked:
            example = json.loads(row["baseline_json"])
            if row["request_key"] in conflicts:
                example["requires_selection"] = True
                example["has_alternatives"] = True
            result.append({"request_text": row["request_text"], "baseline": example})
        return result


    # ---- 文档快照 / 提示词 / 映射规则 ----
    def create_document(
        self,
        *,
        name: str,
        file_name: str,
        content_sha256: str,
        table_count: int,
        field_count: int,
        warnings: list[str],
        imported_by: str,
        tables: list[dict[str, Any]],
    ) -> dict[str, Any]:
        stamp = _now()
        with self._begin() as connection:
            version_no = int(connection.execute(select(func.max(DOCUMENTS.c.version_no))).scalar() or 0) + 1
            connection.execute(update(DOCUMENTS).where(DOCUMENTS.c.status == "active").values(status="archived"))
            document_id = connection.execute(insert(DOCUMENTS).values(
                name=name, file_name=file_name, content_sha256=content_sha256, version_no=version_no,
                status="active", table_count=table_count, field_count=field_count,
                warnings_json=json.dumps(warnings, ensure_ascii=False), imported_by=imported_by,
                imported_at=stamp, activated_at=stamp,
            )).inserted_primary_key[0]
            for table_index, table in enumerate(tables):
                table_id = connection.execute(insert(DOC_TABLES).values(
                    document_id=int(document_id), data_source_name=str(table.get("data_source_name") or ""),
                    table_name=str(table.get("table_name") or ""), table_name_cn=str(table.get("table_name_cn") or ""),
                    sheet_name=str(table.get("sheet_name") or ""), source_desc=str(table.get("source_desc") or ""),
                    dimension=str(table.get("dimension") or ""), period=str(table.get("period") or ""),
                    scope=str(table.get("scope") or ""), sort_order=table_index,
                )).inserted_primary_key[0]
                for order, field in enumerate(table.get("fields") or []):
                    connection.execute(insert(DOC_FIELDS).values(
                        table_id=int(table_id), field_name=str(field.get("field_name") or ""),
                        field_cn=str(field.get("field_cn") or ""), data_type=str(field.get("data_type") or ""),
                        is_pk=str(field.get("is_pk") or ""), nullable=str(field.get("nullable") or ""),
                        default_value=str(field.get("default_value") or ""), dictionary=str(field.get("dictionary") or ""),
                        logic=str(field.get("logic") or ""), source_table=str(field.get("source_table") or ""),
                        source_field=str(field.get("source_field") or ""),
                        source_field_cn=str(field.get("source_field_cn") or ""),
                        source_table_cn=str(field.get("source_table_cn") or ""), sort_order=order,
                    ))
        document = self.get_document(int(document_id))
        return document

    def _document_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        try:
            data["warnings"] = json.loads(data.pop("warnings_json") or "[]")
        except ValueError:
            data["warnings"] = []
        return data

    def get_document(self, document_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(select(DOCUMENTS).where(DOCUMENTS.c.id == document_id)).mappings().first()
        return self._document_row(row)

    def list_documents(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(select(DOCUMENTS).order_by(desc(DOCUMENTS.c.version_no))).mappings().all()
        return [self._document_row(row) for row in rows]

    def active_document(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                select(DOCUMENTS).where(DOCUMENTS.c.status == "active").order_by(desc(DOCUMENTS.c.version_no)).limit(1)
            ).mappings().first()
        return self._document_row(row) if row else None

    def activate_document(self, document_id: int) -> dict[str, Any]:
        stamp = _now()
        with self._begin() as connection:
            connection.execute(update(DOCUMENTS).where(DOCUMENTS.c.status == "active").values(status="archived"))
            connection.execute(update(DOCUMENTS).where(DOCUMENTS.c.id == document_id).values(
                status="active", activated_at=stamp,
            ))
        return self.get_document(document_id)

    def doc_tables(self, document_id: int, data_source_name: str = "") -> list[dict[str, Any]]:
        statement = select(DOC_TABLES).where(DOC_TABLES.c.document_id == document_id)
        if data_source_name:
            statement = statement.where(DOC_TABLES.c.data_source_name == data_source_name)
        statement = statement.order_by(DOC_TABLES.c.sort_order, DOC_TABLES.c.id)
        with self.database.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def doc_table(self, document_id: int, table_name: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                select(DOC_TABLES).where(and_(
                    DOC_TABLES.c.document_id == document_id, DOC_TABLES.c.table_name == table_name,
                ))
            ).mappings().first()
        return dict(row) if row else None

    def active_table_labels(self, names: set[str]) -> list[dict[str, Any]]:
        active_id = select(DOCUMENTS.c.id).where(DOCUMENTS.c.status == "active").order_by(
            desc(DOCUMENTS.c.version_no)
        ).limit(1).scalar_subquery()
        statement = select(
            DOC_TABLES.c.data_source_name, DOC_TABLES.c.table_name, DOC_TABLES.c.table_name_cn, DOC_TABLES.c.sheet_name,
        ).where(DOC_TABLES.c.document_id == active_id)
        names = sorted(names)
        with self.database.connect() as connection:
            rows = []
            for offset in range(0, len(names), EXECUTION_CHUNK):
                chunk = statement.where(DOC_TABLES.c.table_name.in_(names[offset:offset + EXECUTION_CHUNK]))
                rows.extend(dict(row) for row in connection.execute(chunk).mappings())
            return rows

    def doc_fields(self, table_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                select(DOC_FIELDS).where(DOC_FIELDS.c.table_id == table_id).order_by(DOC_FIELDS.c.sort_order, DOC_FIELDS.c.id)
            ).mappings().all()
        return [dict(row) for row in rows]

    def doc_fields_for_tables(self, table_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        """Read a bounded selector's field hints in one parameterized query."""
        ids = list(dict.fromkeys(table_ids))
        if len(ids) > 80 or any(type(item) is not int or item <= 0 for item in ids):
            raise ValueError("Invalid document table selection")
        grouped: dict[int, list[dict[str, Any]]] = {item: [] for item in ids}
        if not ids:
            return grouped
        with self.database.connect() as connection:
            rows = connection.execute(select(DOC_FIELDS).where(DOC_FIELDS.c.table_id.in_(ids))
                                      .order_by(DOC_FIELDS.c.table_id, DOC_FIELDS.c.sort_order, DOC_FIELDS.c.id)).mappings().all()
        for row in rows:
            grouped[int(row["table_id"])].append(dict(row))
        return grouped

    def knowledge_record(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(select(TRUST_KNOWLEDGE).where(TRUST_KNOWLEDGE.c.id == 1)).mappings().first()
        return dict(row) if row else None

    def active_knowledge_revision(self) -> int:
        with self.database.connect() as connection:
            revision = connection.execute(select(TRUST_KNOWLEDGE.c.active_revision).where(
                TRUST_KNOWLEDGE.c.id == 1,
            )).scalar()
        return int(revision or 0)

    def write_knowledge(self, expected: int, operator: str, *, draft: list[dict[str, Any]] | None = None,
                        enabled: bool | None = None) -> None:
        """Compare-and-swap; saving a draft never changes the active snapshot."""
        try:
            with self._begin() as connection:
                row = connection.execute(select(TRUST_KNOWLEDGE).where(
                    TRUST_KNOWLEDGE.c.id == 1,
                )).mappings().first()
                if int(row["revision"] if row else 0) != expected:
                    raise AppError("CONFLICT_VERSION")
                values = {"revision": expected + 1, "updated_by": operator, "updated_at": _now()}
                if draft is not None:
                    values["draft_json"] = json.dumps(draft, ensure_ascii=False, separators=(",", ":"))
                elif row is None or (enabled and row["draft_json"] == "[]"):
                    raise AppError("VALIDATION_ERROR")
                else:
                    values.update(active_revision=expected + 1 if enabled else 0,
                                  active_json=row["draft_json"] if enabled else "[]")
                if row is None:
                    connection.execute(insert(TRUST_KNOWLEDGE).values(id=1, active_revision=0, active_json="[]", **values))
                else:
                    updated = connection.execute(update(TRUST_KNOWLEDGE).where(
                        TRUST_KNOWLEDGE.c.id == 1, TRUST_KNOWLEDGE.c.revision == expected,
                    ).values(**values))
                    if updated.rowcount != 1:
                        raise AppError("CONFLICT_VERSION")
        except IntegrityError:
            if expected != 0:
                raise
            raise AppError("CONFLICT_VERSION") from None

    def save_prompt(self, stage: str, content: str, updated_by: str) -> dict[str, Any]:
        stamp = _now()
        with self._begin() as connection:
            version_no = int(connection.execute(
                select(func.max(PROMPTS.c.version_no)).where(PROMPTS.c.stage == stage)
            ).scalar() or 0) + 1
            connection.execute(update(PROMPTS).where(PROMPTS.c.stage == stage).values(is_active=0))
            prompt_id = connection.execute(insert(PROMPTS).values(
                stage=stage, content=content, version_no=version_no, is_active=1,
                updated_by=updated_by, updated_at=stamp,
            )).inserted_primary_key[0]
        with self.database.connect() as connection:
            row = connection.execute(select(PROMPTS).where(PROMPTS.c.id == int(prompt_id))).mappings().first()
        return dict(row)

    def active_prompt(self, stage: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                select(PROMPTS).where(and_(PROMPTS.c.stage == stage, PROMPTS.c.is_active == 1))
                .order_by(desc(PROMPTS.c.version_no)).limit(1)
            ).mappings().first()
        return dict(row) if row else None

    def prompt_versions(self, stage: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                select(PROMPTS).where(PROMPTS.c.stage == stage).order_by(desc(PROMPTS.c.version_no))
            ).mappings().all()
        return [dict(row) for row in rows]

    def source_rules(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                select(SOURCE_RULES).order_by(SOURCE_RULES.c.sort_order, SOURCE_RULES.c.id)
            ).mappings().all()
        return [dict(row) for row in rows]

    def save_source_rules(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._begin() as connection:
            connection.execute(delete(SOURCE_RULES))
            for order, rule in enumerate(rules):
                connection.execute(insert(SOURCE_RULES).values(
                    sheet_prefix=str(rule.get("sheet_prefix") or ""),
                    data_source_name=str(rule.get("data_source_name") or ""),
                    sort_order=order,
                ))
        return self.source_rules()

    def _insert_rule_tx(self, connection: Any, *, creator_user_id: str, name: str, description: str,
                        definition: dict[str, Any], sql_text: str, mapping_version: str,
                        content_sha256: str, generation_mode: str, status: str = "draft",
                        history: dict[str, Any] | None = None) -> tuple[int, int]:
        """事务内插入规则与版本；规则编号由自增主键生成，单/批共用避免同码。"""
        stamp = _now()
        rule_id = int(connection.execute(insert(RULES).values(
            rule_code="", name=name, description=description[:_RULE_DESCRIPTION_LIMIT],
            creator_user_id=creator_user_id,
            status=status, current_version_id=None, source_id=str(definition.get("source_id") or ""),
            table_name=str(definition.get("table_name") or ""), rule_type=str(definition.get("rule_type") or ""),
            report_category=str(definition.get("report_category") or ""), updated_at=stamp,
        )).inserted_primary_key[0])
        connection.execute(update(RULES).where(RULES.c.id == rule_id).values(rule_code=f"DV{rule_id:06d}"))
        version_id = int(connection.execute(insert(VERSIONS).values(
            rule_id=rule_id, version_no=1, definition_json=json.dumps(definition, ensure_ascii=False),
            sql_text=sql_text, mapping_version=mapping_version, content_sha256=content_sha256,
            generation_mode=generation_mode, status="draft", created_at=stamp,
        )).inserted_primary_key[0])
        self._write_history(connection, rule_id, history, stamp)
        return rule_id, version_id

    @staticmethod
    def _lock_active_document(connection: Any) -> tuple[Any, Any, Any] | None:
        """对活动文档行加事务锁：跨进程串行批量保存并校验快照未漂移。"""
        rows = connection.execute(
            select(DOCUMENTS.c.id, DOCUMENTS.c.version_no, DOCUMENTS.c.content_sha256)
            .where(DOCUMENTS.c.status == "active").order_by(desc(DOCUMENTS.c.id))
            .with_for_update()
        ).all()
        if not rows:
            return None
        if len(rows) > 1:
            # 历史/人工数据出现多个活动文档时拒绝保存，避免不同事务锁到不同快照。
            raise AppError("VALIDATION_ERROR")
        row = rows[0]
        return row[0], row[1], row[2]

    def save_batch(self, *, creator_user_id: str, prepared: list[dict[str, Any]],
                   request_key: str, payload_hash: str) -> dict[str, Any]:
        """幂等批量草稿：活动文档行锁内查回执并同事务写入全部规则。"""
        action = f"ai_batch:{request_key}"
        with self._begin() as connection:
            document = self._lock_active_document(connection)
            if document is None:
                raise AppError("VALIDATION_ERROR")
            _doc_id, doc_version, doc_sha = document
            existing = connection.execute(
                select(AUDITS.c.detail_json).where(
                    AUDITS.c.action_code == action,
                    AUDITS.c.operator_user_id == str(creator_user_id),
                ).order_by(desc(AUDITS.c.id)).limit(5)
            ).all()
            matched_key = False
            for (raw,) in existing:
                try:
                    receipt = json.loads(raw or "{}")
                except ValueError:
                    continue
                matched_key = True
                same_payload = str(receipt.get("payload_hash") or "") == payload_hash
                same_document = int(receipt.get("doc_version") or -1) == int(doc_version)
                if same_payload and same_document:
                    return {"reused": True, "rule_ids": [int(item) for item in receipt.get("rule_ids") or []]}
            if matched_key:
                raise AppError("CONFLICT_VERSION")
            expected_mapping = f"doc-v{int(doc_version)}-{str(doc_sha)[:12]}"
            for item in prepared:
                if str(item.get("mapping_version") or "") != expected_mapping:
                    raise AppError("CONFLICT_VERSION")
            inserted = [self._insert_rule_tx(connection, **item) for item in prepared]
            rule_ids = [rule_id for rule_id, _version_id in inserted]
            self._insert_audit_tx(
                connection, rule_id=None, task_id=None, action_code=action,
                operator_user_id=str(creator_user_id),
                detail={
                    "request_key": request_key, "payload_hash": payload_hash,
                    "owner": str(creator_user_id), "rule_ids": rule_ids,
                    "doc_version": int(doc_version),
                },
            )
        return {
            "reused": False, "rule_ids": rule_ids,
            "version_ids": [version_id for _rule_id, version_id in inserted],
        }

    def create_rule(self, *, creator_user_id: str, name: str, description: str, definition: dict[str, Any], sql_text: str, mapping_version: str, content_sha256: str, generation_mode: str, status: str = "draft", history: dict[str, Any] | None = None, copy_from: int | None = None) -> dict[str, Any]:
        with self._rule_transaction() as connection:
            if copy_from is not None:
                self._lock_rule(connection, copy_from)
            rule_id, version_id = self._insert_rule_tx(
                connection, creator_user_id=creator_user_id, name=name, description=description,
                definition=definition, sql_text=sql_text, mapping_version=mapping_version,
                content_sha256=content_sha256, generation_mode=generation_mode, status=status, history=history,
            )
        rule = self.get_rule(int(rule_id))
        rule["version_id"] = int(version_id)
        rule["version_no"] = 1
        return rule

    def add_version(self, rule_id: int, definition: dict[str, Any], sql_text: str, mapping_version: str, content_sha256: str, history: dict[str, Any] | None = None, *, expected_rule: dict | None = None) -> dict[str, Any]:
        stamp = _now()
        with self._rule_transaction() as connection:
            locked_rule = self._lock_rule(connection, rule_id)
            self._check_edit_context(connection, locked_rule, expected_rule)
            version_no = int(connection.execute(select(func.max(VERSIONS.c.version_no)).where(
                VERSIONS.c.rule_id == rule_id,
            )).scalar_one()) + 1
            if history and history["version_no"] != version_no:
                raise AppError("CONFLICT_VERSION")
            version_id = connection.execute(insert(VERSIONS).values(
                rule_id=rule_id, version_no=version_no, definition_json=json.dumps(definition, ensure_ascii=False),
                sql_text=sql_text, mapping_version=mapping_version, content_sha256=content_sha256,
                generation_mode=str(definition.get("generation_mode") or "manual"), status="draft", created_at=stamp,
            )).inserted_primary_key[0]
            connection.execute(update(RULES).where(RULES.c.id == rule_id).values(
                name=str(definition.get("name") or ""),
                description=str(definition.get("description") or "")[:_RULE_DESCRIPTION_LIMIT],
                source_id=str(definition.get("source_id") or ""), table_name=str(definition.get("table_name") or ""),
                rule_type=str(definition.get("rule_type") or ""),
                report_category=str(definition.get("report_category") or ""), updated_at=stamp,
            ))
            self._write_history(connection, rule_id, history, stamp)
        version = self.get_version_by_id(int(version_id))
        return version

    def set_status(self, rule_id: int, status: str, current_version_id: int | None = None, history: dict[str, Any] | None = None, confirmation: dict[str, Any] | None = None, *, expected_rule: dict | None = None) -> None:
        values: dict[str, Any] = {"status": status, "updated_at": _now()}
        if current_version_id is not None:
            values["current_version_id"] = current_version_id
        with self._rule_transaction() as connection:
            locked_rule = self._lock_rule(connection, rule_id)
            self._check_edit_context(connection, locked_rule, expected_rule)
            connection.execute(update(RULES).where(RULES.c.id == rule_id).values(**values))
            self._write_history(connection, rule_id, history, values["updated_at"])
            if confirmation:
                connection.execute(insert(CONFIRMATIONS).values(**confirmation, created_at=values["updated_at"]))

    @staticmethod
    def _check_edit_context(connection: Any, rule: dict[str, Any], expected: dict | None) -> None:
        if expected is None:
            return
        from .edit_context import check_edit_context
        version = connection.execute(select(VERSIONS.c.version_no, VERSIONS.c.content_sha256).where(
            VERSIONS.c.rule_id == rule["id"],
        ).order_by(desc(VERSIONS.c.version_no)).limit(1)).mappings().one()
        check_edit_context(rule, dict(version), expected)

    def delete_rule(self, rule_id: int, user: dict[str, Any]) -> dict[str, Any]:
        with self._rule_transaction() as connection:
            rule = self._lock_rule(connection, rule_id, allow_deleted=True)
            if rule["status"] == "deleted":
                return rule
            version = connection.execute(select(VERSIONS.c.version_no, VERSIONS.c.content_sha256).where(
                VERSIONS.c.rule_id == rule_id,
            ).order_by(desc(VERSIONS.c.version_no)).limit(1)).one()
            history = history_event(
                "delete", user, version_no=version.version_no, content_sha256=version.content_sha256,
                before_status=rule["status"], after_status="deleted", summary="删除规则，保留版本与历史执行记录",
            )
            rule.update(status="deleted", updated_at=_now())
            connection.execute(update(RULES).where(RULES.c.id == rule_id).values(
                status="deleted", updated_at=rule["updated_at"],
            ))
            self._write_history(connection, rule_id, history, rule["updated_at"])
            return rule

    def get_rule(self, rule_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(select(RULES).where(RULES.c.id == rule_id)).mappings().first()
        if row is None:
            raise AppError("RULE_NOT_FOUND")
        return _rule_row(row)

    def latest_version(self, rule_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                select(VERSIONS).where(VERSIONS.c.rule_id == rule_id).order_by(desc(VERSIONS.c.version_no)).limit(1)
            ).mappings().first()
        return self._version(row)

    def get_version(self, rule_id: int, version_no: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                select(VERSIONS).where(and_(VERSIONS.c.rule_id == rule_id, VERSIONS.c.version_no == version_no))
            ).mappings().first()
        return self._version(row)

    def get_version_by_id(self, version_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(select(VERSIONS).where(VERSIONS.c.id == version_id)).mappings().first()
        return self._version(row)

    def list_rule_history(self, rule_id: int, *, page: int, page_size: int) -> dict[str, Any]:
        safe_page = max(int(page), 1)
        safe_page_size = int(page_size) if int(page_size) in {20, 50, 100} else 20
        rule = self.get_rule(rule_id)
        with self.database.connect() as connection:
            versions = connection.execute(
                select(VERSIONS).where(VERSIONS.c.rule_id == rule_id).order_by(VERSIONS.c.version_no, VERSIONS.c.id)
            ).mappings().all()
            audits = connection.execute(
                select(AUDITS).where(and_(
                    AUDITS.c.rule_id == rule_id,
                    AUDITS.c.action_code.in_(HISTORY_ACTIONS),
                )).order_by(AUDITS.c.id)
            ).mappings().all()
            confirmations = connection.execute(
                select(CONFIRMATIONS).where(CONFIRMATIONS.c.rule_id == rule_id).order_by(CONFIRMATIONS.c.id)
            ).mappings().all()
        items = merge_rule_history(
            rule=rule,
            versions=[dict(row) for row in versions],
            audits=[dict(row) for row in audits],
            confirmations=[dict(row) for row in confirmations],
        )
        offset = (safe_page - 1) * safe_page_size
        return {
            "items": items[offset:offset + safe_page_size],
            "total": len(items),
            "page": safe_page,
            "page_size": safe_page_size,
        }

    @staticmethod
    def _rule_filter(creator_user_id, keyword, status, report_category, source_id, rule_type=""):
        filters = [RULES.c.status != "deleted"]
        if creator_user_id is not None:
            filters.append(RULES.c.creator_user_id == creator_user_id)
        if status:
            filters.append(RULES.c.status == status)
        if report_category == PBC_SHARED_CATEGORY or report_category in PBC_REPORT_CATEGORIES:
            filters.append(RULES.c.report_category.in_((*sorted(PBC_REPORT_CATEGORIES), PBC_SHARED_CATEGORY)))
        elif report_category:
            filters.append(RULES.c.report_category == ("" if report_category == UNCLASSIFIED else report_category))
        if source_id:
            filters.append(RULES.c.source_id == source_id)
        if rule_type:
            filters.append(RULES.c.rule_type == rule_type)
        if keyword:
            text = f"%{keyword}%"
            filters.append((RULES.c.name.like(text)) | (RULES.c.rule_code.like(text)) | (RULES.c.description.like(text)))
        return and_(*filters)

    def execution_selection(self, creator_user_id: str | None, query: dict) -> dict:
        where = self._rule_filter(creator_user_id, str(query.get("keyword") or ""), "enabled",
                                  str(query.get("report_category") or ""), str(query.get("source_id") or ""))
        statement = select(RULES.c.id).where(where, RULES.c.current_version_id.is_not(None)).order_by(
            RULES.c.id.desc()).limit(MAX_TASK_RULES + 1)
        with self.database.connect() as connection:
            ids = list(connection.execute(statement).scalars())
        if len(ids) > MAX_TASK_RULES:
            raise AppError("TASK_SELECTION_LIMIT")
        return {"rule_ids": ids, "count": len(ids)}

    def list_rules(self, *, creator_user_id: str | None, keyword: str, status: str, report_category: str = "",
                   source_id: str = "", rule_type: str = "", page: int, page_size: int) -> dict[str, Any]:
        where = self._rule_filter(creator_user_id, keyword, status, report_category, source_id, rule_type)
        offset = (page - 1) * page_size
        with self.database.connect() as connection:
            count_stmt = select(func.count()).select_from(RULES)
            list_stmt = select(RULES).order_by(desc(RULES.c.id)).limit(page_size).offset(offset)
            count_stmt = count_stmt.where(where)
            list_stmt = list_stmt.where(where)
            total = int(connection.execute(count_stmt).scalar_one())
            rows = connection.execute(list_stmt).mappings().all()
            items = [_rule_row(row) for row in rows]
            if items:
                ids = [int(item["id"]) for item in items]
                version_rows = connection.execute(
                    select(VERSIONS.c.rule_id, func.max(VERSIONS.c.version_no))
                    .where(VERSIONS.c.rule_id.in_(ids))
                    .group_by(VERSIONS.c.rule_id)
                ).all()
                version_map = {int(rule_id): int(version_no) for rule_id, version_no in version_rows}
                for item in items:
                    item["version_no"] = version_map.get(int(item["id"]), 0)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def stats(self, creator_user_id: str | None) -> dict[str, int]:
        statement = select(RULES.c.status, func.count()).where(RULES.c.status != "deleted").group_by(RULES.c.status)
        if creator_user_id is not None:
            statement = statement.where(RULES.c.creator_user_id == creator_user_id)
        counts = {"total": 0, "enabled": 0, "disabled": 0, "draft": 0}
        with self.database.connect() as connection:
            for status, count in connection.execute(statement):
                amount = int(count)
                counts["total"] += amount
                if status in counts:
                    counts[status] += amount
        return counts

    def category_stats(self, creator_user_id: str | None) -> list[dict[str, Any]]:
        statement = select(RULES.c.report_category, RULES.c.status, func.count()).where(RULES.c.status != "deleted").group_by(
            RULES.c.report_category, RULES.c.status,
        )
        if creator_user_id is not None:
            statement = statement.where(RULES.c.creator_user_id == creator_user_id)
        grouped: dict[str, dict[str, int]] = {}
        with self.database.connect() as connection:
            for category, status, count in connection.execute(statement):
                bucket = grouped.setdefault(str(category or ""), {"total": 0, "enabled": 0, "disabled": 0, "draft": 0})
                amount = int(count)
                bucket["total"] += amount
                if status in bucket:
                    bucket[status] += amount
        return [{"report_category": code, **counts} for code, counts in grouped.items()]

    def audit(self, *, rule_id: int | None, task_id: int | None, action_code: str, operator_user_id: str, detail: dict[str, Any] | None = None) -> None:
        with self._begin() as connection:
            self._insert_audit_tx(
                connection, rule_id=rule_id, task_id=task_id, action_code=action_code,
                operator_user_id=operator_user_id, detail=detail,
            )

    @staticmethod
    def _insert_audit_tx(connection: Any, *, rule_id: int | None, task_id: int | None,
                         action_code: str, operator_user_id: str, detail: dict[str, Any] | None) -> None:
        connection.execute(insert(AUDITS).values(
            rule_id=rule_id, task_id=task_id, action_code=action_code, operator_user_id=operator_user_id,
            detail_json=json.dumps(detail or {}, ensure_ascii=False), created_at=_now(),
        ))

    def latest_audit(self, rule_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                select(AUDITS).where(AUDITS.c.rule_id == rule_id).order_by(desc(AUDITS.c.id)).limit(1)
            ).mappings().first()
        return dict(row) if row else None

    def invalidate_cases(self, rule_id: int, version_no: int) -> None:
        with self._rule_transaction() as connection:
            self._lock_rule(connection, rule_id)
            connection.execute(update(CASES).where(and_(CASES.c.rule_id == rule_id, CASES.c.version_no == version_no)).values(
                status="not_run", actual_count=-1,
            ))

    def replace_cases(self, rule_id: int, version_no: int, cases: list[dict[str, Any]]) -> None:
        with self._rule_transaction() as connection:
            self._lock_rule(connection, rule_id)
            connection.execute(CASES.delete().where(and_(CASES.c.rule_id == rule_id, CASES.c.version_no == version_no)))
            if cases:
                connection.execute(insert(CASES), [
                    {
                        "rule_id": rule_id, "version_no": version_no, "case_name": item["name"],
                        "input_json": json.dumps(item["row"], ensure_ascii=False),
                        "expected_count": int(item["expected_count"]), "actual_count": int(item["actual_count"]) if item["actual_count"] is not None else -1,
                        "status": item["status"], "created_at": _now(),
                    }
                    for item in cases
                ])

    def list_cases(self, rule_id: int, version_no: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                select(CASES).where(and_(CASES.c.rule_id == rule_id, CASES.c.version_no == version_no))
            ).mappings().all()
        return [dict(row) for row in rows]

    def add_confirmation(self, **values: Any) -> None:
        values["created_at"] = _now()
        with self._begin() as connection:
            connection.execute(insert(CONFIRMATIONS).values(**values))

    def execution_candidates(self, rule_ids: list[int]) -> dict[int, dict]:
        definition = type_coerce(VERSIONS.c.definition_json, JSON)
        statement = select(
            RULES.c.id.label("rule_id"), RULES.c.creator_user_id, RULES.c.status, RULES.c.current_version_id,
            VERSIONS.c.id.label("version_id"), VERSIONS.c.version_no, VERSIONS.c.content_sha256,
            func.substr(VERSIONS.c.sql_text, 1, 180).label("sql_summary"),
            *(definition[key].as_string().label(key) for key in ("source_id", "table_name", "report_category", "report_category_name")),
        ).select_from(RULES.outerjoin(VERSIONS, VERSIONS.c.id == RULES.c.current_version_id))
        result = {}
        with self.database.connect() as connection:
            for offset in range(0, len(rule_ids), EXECUTION_CHUNK):
                page = statement.where(RULES.c.id.in_(rule_ids[offset:offset + EXECUTION_CHUNK]))
                result.update((row["rule_id"], dict(row)) for row in connection.execute(page).mappings())
        return result

    def create_task(self, *, creator_user_id: str, source_id: str, report_period: str, params: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
        with self._rule_transaction() as connection:
            if rules:
                expected = {int(item["rule_id"]): item["version_id"] for item in rules}
                ids = sorted(expected)
                for offset in range(0, len(ids), EXECUTION_CHUNK):
                    chunk = ids[offset:offset + EXECUTION_CHUNK]
                    locked = connection.execute(select(RULES.c.id, RULES.c.status, RULES.c.current_version_id).where(
                        RULES.c.id.in_(chunk)).order_by(RULES.c.id).with_for_update()).all()
                    if any(row.status == "deleted" for row in locked):
                        raise AppError("RULE_DELETED")
                    if len(locked) != len(chunk) or any(row.status != "enabled" or expected[row.id] != row.current_version_id for row in locked):
                        raise AppError("CONFLICT_VERSION")
            task_id = connection.execute(insert(TASKS).values(
                creator_user_id=creator_user_id, source_id=source_id, report_period=report_period, status="queued",
                params_json=json.dumps(params, ensure_ascii=False), truncated=0, created_at=_now(),
            )).inserted_primary_key[0]
            for offset in range(0, len(rules), EXECUTION_CHUNK):
                connection.execute(insert(TASK_RULES), [
                    {
                        "task_id": int(task_id), "rule_id": item["rule_id"], "version_id": item["version_id"],
                        "version_no": item["version_no"], "content_sha256": item["content_sha256"],
                        "sql_summary": item["sql_summary"], "status": "queued", "violation_count": 0,
                        "source_id": item.get("source_id"),
                        "source_name": item.get("source_name"), "table_name_cn": item.get("table_name_cn"),
                        "report_category_name": item.get("report_category_name"),
                        "report_category": (category_code(item["report_category"]) or UNCLASSIFIED) if "report_category" in item else None,
                        "truncated": 0, "error_code": "",
                    }
                    for item in rules[offset:offset + EXECUTION_CHUNK]
                ])
        return self.get_task(int(task_id), with_params=False)

    @staticmethod
    def legacy_snapshot_field(key: str):
        return select(type_coerce(VERSIONS.c.definition_json, JSON)[key].as_string()).where(
            VERSIONS.c.id == TASK_RULES.c.version_id).correlate(TASK_RULES).scalar_subquery()

    @classmethod
    def snapshot_category(cls):
        raw = func.coalesce(func.trim(cls.legacy_snapshot_field("report_category")), "")
        legacy = case((raw == "", UNCLASSIFIED), (raw.in_(tuple(PBC_REPORT_CATEGORIES)), PBC_SHARED_CATEGORY), else_=raw)
        return func.coalesce(TASK_RULES.c.report_category, legacy)

    def list_tasks(self, creator_user_id: str | None, report_period: str = "", report_category: str = "") -> list[dict[str, Any]]:
        statement = select(*(c for c in TASKS.c if c.name != "params_json")).order_by(desc(TASKS.c.id)).limit(100)
        previous = TASKS.alias("previous_task")
        ordinal = select(func.count()).select_from(previous).where(previous.c.id <= TASKS.c.id)
        filters = []
        if creator_user_id is not None:
            filters.append(TASKS.c.creator_user_id == creator_user_id)
            ordinal = ordinal.where(previous.c.creator_user_id == creator_user_id)
        if report_period:
            filters.append(TASKS.c.report_period == report_period)
            ordinal = ordinal.where(previous.c.report_period == report_period)
        if report_category:
            code = category_code(report_category)
            filters.append(select(TASK_RULES.c.id).where(
                TASK_RULES.c.task_id == TASKS.c.id, self.snapshot_category() == code).exists())
        if filters:
            statement = statement.where(and_(*filters))
        statement = statement.add_columns(ordinal.correlate(TASKS).scalar_subquery().label("run_no"))
        with self.database.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def snapshot_select():
        definition = type_coerce(VERSIONS.c.definition_json, JSON)
        return select(
            TASK_RULES.c.task_id, TASK_RULES.c.rule_id, TASK_RULES.c.version_no,
            TASK_RULES.c.status, TASK_RULES.c.error_code, TASK_RULES.c.truncated, TASK_RULES.c.violation_count,
            TASK_RULES.c.source_name, TASK_RULES.c.table_name_cn,
            func.coalesce(TASK_RULES.c.report_category_name, definition["report_category_name"].as_string()).label("report_category_name"),
            func.coalesce(TASK_RULES.c.report_category, definition["report_category"].as_string()).label("report_category"),
            func.coalesce(TASK_RULES.c.source_id, definition["source_id"].as_string()).label("source_id"),
            *(definition[key].as_string().label(key) for key in (
                "name", "rule_name", "table_name")),
        ).select_from(TASK_RULES.outerjoin(VERSIONS, VERSIONS.c.id == TASK_RULES.c.version_id))

    def task_rule_snapshots(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids:
            return []
        statement = self.snapshot_select().where(TASK_RULES.c.task_id.in_(ids)).order_by(TASK_RULES.c.id)
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def get_task(self, task_id: int, *, with_params: bool = True) -> dict[str, Any]:
        with self.database.connect() as connection:
            columns = list(TASKS.c) if with_params else [c for c in TASKS.c if c.name != "params_json"]
            row = connection.execute(select(*columns).where(TASKS.c.id == task_id)).mappings().first()
        if row is None:
            raise KeyError(task_id)
        return dict(row)

    def task_rules(self, task_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(select(TASK_RULES).where(TASK_RULES.c.task_id == task_id).order_by(TASK_RULES.c.id)).mappings().all()
        return [dict(row) for row in rows]

    def queued_task_rules(self, task_id: int, after_id: int, generation: int) -> list[dict]:
        stmt = select(TASK_RULES).where(TASK_RULES.c.task_id == task_id, TASK_RULES.c.id > after_id,
                                        TASK_RULES.c.status == "queued", TASK_RULES.c.execution_generation == generation)
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute(stmt.order_by(TASK_RULES.c.id).limit(EXECUTION_CHUNK)).mappings()]

    @staticmethod
    def _later_execution(task_id, generation):
        return select(TASK_RULES.c.id).where(TASK_RULES.c.task_id == task_id,
                                             TASK_RULES.c.execution_generation > generation).exists()

    def transition_task(self, task_id: int, from_states: tuple[str, ...], status: str, *, generation: int | None = None) -> bool:
        with self._rule_transaction() as connection:
            stmt = update(TASKS).where(TASKS.c.id == task_id, TASKS.c.status.in_(from_states))
            if generation is not None:
                stmt = stmt.where(~self._later_execution(task_id, generation))
            changed = connection.execute(stmt.values(status=status))
            return bool(changed.rowcount)

    def resume_generation(self, task_id: int) -> int | None:
        with self._rule_transaction() as connection:
            changed = connection.execute(update(TASKS).where(TASKS.c.id == task_id, TASKS.c.status == "paused").values(status="queued"))
            if changed.rowcount:
                return int(connection.scalar(select(func.max(TASK_RULES.c.execution_generation)).where(TASK_RULES.c.task_id == task_id)) or 0)
        return None

    def claim_failed_task_rules(self, task_id: int, *, queue: bool = False) -> list[dict[str, Any]]:
        """先锁规则再领取失败快照，整批重试与删除按同一事务顺序受理。"""
        with self._rule_transaction() as connection:
            rule_ids = select(TASK_RULES.c.rule_id).where(TASK_RULES.c.task_id == task_id)
            states = dict(connection.execute(
                select(RULES.c.id, RULES.c.status).where(RULES.c.id.in_(rule_ids))
                .order_by(RULES.c.id).with_for_update()
            ).all())
            failed = connection.execute(select(TASK_RULES).where(
                TASK_RULES.c.task_id == task_id, TASK_RULES.c.status.in_(("ERROR", "TIMEOUT", "CANCELLED")),
            ).order_by(TASK_RULES.c.id).with_for_update()).mappings().all()
            if not failed:
                return []
            parent = connection.execute(select(TASKS.c.status).where(TASKS.c.id == task_id).with_for_update()).scalar_one()
            if parent in {"queued", "running", "pausing", "paused"}:
                return []
            for item in failed:
                if item["rule_id"] not in states:
                    raise AppError("RULE_NOT_FOUND")
                if states[item["rule_id"]] == "deleted":
                    raise AppError("RULE_DELETED")
            generation = 1 + int(connection.scalar(select(func.max(TASK_RULES.c.execution_generation)).where(TASK_RULES.c.task_id == task_id)) or 0)
            state = "queued" if queue else "running"
            connection.execute(update(TASK_RULES).where(
                TASK_RULES.c.task_id == task_id, TASK_RULES.c.status.in_(("ERROR", "TIMEOUT", "CANCELLED")),
            ).values(status=state, execution_generation=generation))
            connection.execute(update(TASKS).where(TASKS.c.id == task_id).values(status=state))
            return [dict(item, status=state, execution_generation=generation) for item in failed]

    def update_task_rule(self, task_rule_id: int, **values: Any) -> None:
        with self._begin() as connection:
            connection.execute(update(TASK_RULES).where(TASK_RULES.c.id == task_rule_id).values(**values))

    def update_task(self, task_id: int, **values: Any) -> None:
        with self._begin() as connection:
            connection.execute(update(TASKS).where(TASKS.c.id == task_id).values(**values))

    def cancel_task(self, task_id: int) -> None:
        with self._rule_transaction() as connection:
            stopped = connection.execute(update(TASK_RULES).where(
                TASK_RULES.c.task_id == task_id, TASK_RULES.c.status.in_(("queued", "running"))
            ).values(status="CANCELLED"))
            if stopped.rowcount:
                connection.execute(update(TASKS).where(
                    TASKS.c.id == task_id, TASKS.c.status.in_(("queued", "running", "pausing", "paused"))
                ).values(status="cancelled"))

    def claim_execution_rule(self, task_id: int, task_rule_id: int, generation: int) -> bool | None:
        """只领取本次执行代尚未开始的快照。"""
        with self._rule_transaction() as connection:
            # 与取消和结果写回保持快照 -> 父任务的加锁顺序。
            state = connection.execute(select(TASK_RULES.c.status).where(
                TASK_RULES.c.id == task_rule_id).with_for_update()).scalar_one()
            if state != "queued":
                return False
            parent = connection.execute(select(TASKS.c.status).where(TASKS.c.id == task_id).with_for_update()).scalar_one()
            if parent not in {"queued", "running"}:
                return None
            claimed = connection.execute(update(TASK_RULES).where(
                TASK_RULES.c.id == task_rule_id, TASK_RULES.c.task_id == task_id,
                TASK_RULES.c.status == "queued", TASK_RULES.c.execution_generation == generation,
            ).values(status="running"))
            if claimed.rowcount and parent == "queued":
                connection.execute(update(TASKS).where(
                    TASKS.c.id == task_id, TASKS.c.status == "queued",
                ).values(status="running"))
            return bool(claimed.rowcount)

    def finish_execution(self, task_id: int, generation: int, status: str, error_code: str = "") -> None:
        """收尾指定执行代，保留已完成的结果和后来重试的执行代。"""
        with self._rule_transaction() as connection:
            changed = connection.execute(update(TASK_RULES).where(
                TASK_RULES.c.task_id == task_id, TASK_RULES.c.execution_generation == generation,
                TASK_RULES.c.status.in_(("queued", "running")),
            ).values(status=status, error_code=error_code))
            self._refresh_task_status(connection, task_id, generation=generation, cancelled=status == "CANCELLED" and bool(changed.rowcount))

    def refresh_task_status(self, task_id: int, *, generation: int | None = None) -> None:
        with self._rule_transaction() as connection:
            self._refresh_task_status(connection, task_id, generation=generation)

    @staticmethod
    def _refresh_task_status(connection: Any, task_id: int, *, generation: int | None = None, cancelled: bool = False) -> None:
        statuses = set(connection.execute(select(TASK_RULES.c.status).where(
            TASK_RULES.c.task_id == task_id
        ).order_by(TASK_RULES.c.id).with_for_update()).scalars())
        if statuses & {"queued", "running"}:
            status = "running"
        elif cancelled or statuses == {"CANCELLED"}:
            status = "cancelled"
        elif statuses <= {"PASS", "VIOLATION"}:
            status = "completed"
        elif statuses & {"PASS", "VIOLATION"}:
            status = "partial_failed"
        else:
            status = "failed"
        update_task = update(TASKS).where(TASKS.c.id == task_id, TASKS.c.status != "cancelled")
        if generation is not None:
            update_task = update_task.where(~RuleStorage._later_execution(task_id, generation))
        if status == "running":
            update_task = update_task.where(TASKS.c.status.not_in(("pausing", "paused")))
        connection.execute(update_task.values(status=status))

    def record_rule_result(
        self, task_rule_id: int, *, status: str, error_code: str,
        violation_count: int, truncated: bool, issues: list[dict[str, Any]],
        execution_generation: int = 0,
    ) -> bool:
        """Publish a rule outcome and its real detail rows in one transaction.

        Repeated/late worker completions cannot duplicate issues or overwrite a
        cancellation. No business query is performed by this application-store write.
        """
        if status not in {"PASS", "VIOLATION", "ERROR", "TIMEOUT", "CANCELLED"}:
            raise ValueError("Invalid rule result status")
        if violation_count < 0 or violation_count != len(issues):
            raise ValueError("Violation count must match registered detail rows")
        if (status == "VIOLATION") != bool(issues):
            raise ValueError("Only a violation outcome may contain detail rows")
        with self._rule_transaction() as connection:
            item = connection.execute(
                select(TASK_RULES).where(TASK_RULES.c.id == task_rule_id).with_for_update()
            ).mappings().first()
            if item is None:
                raise KeyError(task_rule_id)
            parent_status = connection.execute(
                select(TASKS.c.status).where(TASKS.c.id == int(item["task_id"])).with_for_update()
            ).scalar_one()
            if (item["execution_generation"] != execution_generation
                    or item["status"] not in {"queued", "running"} or parent_status not in {"queued", "running", "pausing"}):
                return False
            now = _now()
            rows = []
            for issue in issues:
                issue_kind = issue.get("issue_kind") or "comparison"
                if not isinstance(issue_kind, str) or issue_kind not in {"numeric", "missing_value", "missing_record", "calculation_error", "comparison", "legacy"}:
                    raise ValueError("Invalid issue kind")
                project_status = issue.get("project_name_status") or (
                    "unmapped" if issue.get("project_code") is not None or issue.get("project_name") is not None else "not_required"
                )
                if not isinstance(project_status, str) or project_status not in {
                    "ok", "missing_code", "missing_null", "missing_reference", "duplicate", "unmapped",
                    "not_required", "legacy_unavailable",
                }:
                    raise ValueError("Invalid project identity status")
                if project_status == "ok" and any(
                    issue.get(key) is None or not str(issue[key]).strip() for key in ("project_code", "project_name")
                ):
                    raise ValueError("A resolved project identity must contain its real code and name")
                rows.append({
                    "task_id": int(item["task_id"]), "rule_id": int(item["rule_id"]),
                    "version_no": int(item["version_no"]),
                    "business_key": "" if issue.get("business_key") is None else str(issue["business_key"])[:200],
                    "project_code": None if issue.get("project_code") is None else str(issue["project_code"]),
                    "project_name": None if issue.get("project_name") is None else str(issue["project_name"]),
                    "project_name_status": project_status,
                    "issue_kind": issue_kind,
                    "query_result_json": encode_result(issue.get("query_result")),
                    "message": str(issue.get("message") or "")[:500], "created_at": now,
                })
            if rows:
                connection.execute(insert(ISSUES), rows)
            connection.execute(update(TASK_RULES).where(TASK_RULES.c.id == task_rule_id).values(
                status=status, error_code=error_code, violation_count=violation_count,
                truncated=1 if truncated else 0,
            ))
            if truncated:
                connection.execute(update(TASKS).where(TASKS.c.id == int(item["task_id"])).values(truncated=1))
        return True

    def add_issue(self, **values: Any) -> None:
        values.setdefault("project_name_status", "not_required")
        values.setdefault("issue_kind", "comparison")
        values["created_at"] = _now()
        with self._begin() as connection:
            connection.execute(insert(ISSUES).values(**values))

    def scoped_issue_page(self, task_id: int, rule_id: int | None, category: str, page: int, size: int):
        scope = [TASK_RULES.c.task_id == task_id]
        if rule_id is not None:
            scope.append(TASK_RULES.c.rule_id == rule_id)
        if category:
            scope.append(self.snapshot_category() == category)
        selected = select(TASK_RULES.c.rule_id).where(*scope) if rule_id or category else None
        result = self.list_issues(task_id, page=page, page_size=size, rule_ids=selected)
        keys = {(row["rule_id"], row["version_no"]) for row in result["items"]}
        with self.database.connect() as connection:
            truncated = bool(connection.scalar(select(func.max(TASK_RULES.c.truncated)).where(*scope)))
            snapshots = []
            if keys:
                page_rules = self.snapshot_select().where(TASK_RULES.c.task_id == task_id,
                    tuple_(TASK_RULES.c.rule_id, TASK_RULES.c.version_no).in_(keys))
                snapshots = [dict(row) for row in connection.execute(page_rules).mappings()]
        return result, snapshots, truncated

    def list_issues(self, task_id: int, *, page: int = 1, page_size: int = 50,
                    rule_ids: list[int] | Select | None = None) -> dict[str, Any]:
        safe_page = max(int(page), 1)
        safe_page_size = min(max(int(page_size), 1), 100)
        offset = (safe_page - 1) * safe_page_size
        where = ISSUES.c.task_id == task_id
        if rule_ids is not None:
            where = and_(where, ISSUES.c.rule_id.in_(rule_ids))
        with self.database.connect() as connection:
            total = int(connection.execute(select(func.count()).select_from(ISSUES).where(where)).scalar_one())
            rows = connection.execute(
                select(ISSUES).where(where).order_by(ISSUES.c.id).limit(safe_page_size).offset(offset)
            ).mappings().all()
        items = [dict(row) for row in rows]
        for item in items:
            encoded = item.pop("query_result_json")
            item["query_result"] = json.loads(encoded) if encoded else None
        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
        }

    def visible_rules(self, creator_user_id: str | None) -> list[dict[str, Any]]:
        page = self.list_rules(creator_user_id=creator_user_id, keyword="", status="", page=1, page_size=100000)
        return page["items"]

    @staticmethod
    def _write_history(connection: Any, rule_id: int, history: dict[str, Any] | None, created_at: str) -> None:
        if history is None:
            return
        detail = {
            key: value
            for key, value in history.items()
            if key not in {"action_code", "operator_user_id"}
        }
        connection.execute(insert(AUDITS).values(
            rule_id=rule_id,
            task_id=None,
            action_code=str(history["action_code"]),
            operator_user_id=str(history["operator_user_id"]),
            detail_json=json.dumps(detail, ensure_ascii=False),
            created_at=created_at,
        ))

    def _version(self, row: Any) -> dict[str, Any]:
        if row is None:
            raise KeyError("version")
        data = dict(row)
        data["definition"] = json.loads(data.pop("definition_json"))
        return data
