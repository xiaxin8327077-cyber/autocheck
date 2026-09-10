from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math
import uuid
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT

from .contracts import PageQuery, RecordNotFoundError, VersionConflictError


SHANGHAI = ZoneInfo("Asia/Shanghai")
METADATA = MetaData()
RECORDS = Table(
    "report_special_processing_records",
    METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("record_no", String(32), nullable=False),
    Column("report_process_code", String(64), nullable=False),
    Column("report_process_name_snapshot", String(100), nullable=False),
    Column("report_period", Date),
    Column("dimension", String(16)),
    Column("business_system_code", String(64)),
    Column("business_system_name_snapshot", String(100)),
    Column("datasource_id", String(64)),
    Column("datasource_name_snapshot", String(200)),
    Column("datasource_type", String(32)),
    Column("structured_content_json", Text),
    Column("summary", String(200)),
    Column("table_name", Text),
    Column("field_name", Text),
    Column("value_before", Text),
    Column("value_after", Text),
    Column("processing_content", Text),
    Column("processing_script", Text),
    Column("script_sha256", String(64)),
    Column("status", String(20), nullable=False),
    Column("special_handling_at", DateTime),
    Column("handler_user_id", String(64)),
    Column("handler_username_snapshot", String(100)),
    Column("handler_display_name_snapshot", String(100)),
    Column("governance_owner_user_id", String(64)),
    Column("governance_owner_username_snapshot", String(64)),
    Column("governance_owner_display_name_snapshot", String(64)),
    Column("creator_user_id", String(64), nullable=False),
    Column("creator_username_snapshot", String(100), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_by_user_id", String(64), nullable=False),
    Column("updated_by_username_snapshot", String(100), nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Column("completed_at", DateTime),
    Column("voided_at", DateTime),
    Column("voided_by_user_id", String(64)),
    Column("void_reason", String(500)),
    Column("workflow_status", String(32), nullable=False),
    Column("workflow_instance_id", String(64)),
    Column("workflow_version", Integer, nullable=False),
    Column("row_version", BigInteger, nullable=False),
)
REPORTS = Table(
    "report_special_processing_reports",
    METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("record_id", BigInteger, nullable=False),
    Column("sequence_no", Integer, nullable=False),
    Column("report_name", String(200), nullable=False),
    Column("report_name_normalized", String(200), nullable=False),
    Column("created_at", DateTime, nullable=False),
)
PROCESSES = Table(
    "report_special_processing_processes",
    METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("record_id", BigInteger, nullable=False),
    Column("sequence_no", Integer, nullable=False),
    Column("report_process_code", String(64), nullable=False),
    Column("report_process_name_snapshot", String(100), nullable=False),
    Column("created_at", DateTime, nullable=False),
)
AUDITS = Table(
    "report_special_processing_audit_logs",
    METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("record_id", BigInteger, nullable=False),
    Column("record_no_snapshot", String(32), nullable=False),
    Column("action_code", String(32), nullable=False),
    Column("operator_user_id", String(64), nullable=False),
    Column("operator_username_snapshot", String(100), nullable=False),
    Column("operator_display_name_snapshot", String(100), nullable=False),
    Column("occurred_at", DateTime, nullable=False),
    Column("from_status", String(20)),
    Column("to_status", String(20)),
    Column("changed_fields_json", LONGTEXT, nullable=False),
    Column("action_summary", String(1000), nullable=False),
    Column("request_id", String(64)),
)
FIELD_MAPPINGS = Table(
    "report_special_processing_field_mappings",
    METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("datasource_id", String(64), nullable=False),
    Column("schema_name", String(128), nullable=False),
    Column("table_name", String(128), nullable=False),
    Column("project_field", String(128), nullable=False),
    Column("contract_field", String(128), nullable=False),
    Column("updated_by_user_id", String(64)),
    Column("updated_by_username_snapshot", String(100)),
    Column("updated_at", DateTime),
)
ATTACHMENTS = Table(
    "report_special_processing_confirm_attachments",
    METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("record_id", BigInteger, nullable=False),
    Column("audit_id", BigInteger, nullable=False),
    Column("sequence_no", Integer, nullable=False),
    Column("content_type", String(64), nullable=False),
    Column("byte_size", Integer, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("content", LONGBLOB, nullable=False),
    Column("created_at", DateTime, nullable=False),
)
RECORD_ATTACHMENTS = Table(
    "report_special_processing_record_attachments",
    METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("record_id", BigInteger, nullable=False),
    Column("original_file_name", String(255), nullable=False),
    Column("file_extension", String(16), nullable=False),
    Column("content_type", String(128), nullable=False),
    Column("byte_size", Integer, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("content", LONGBLOB, nullable=False),
    Column("created_by_user_id", String(64), nullable=False),
    Column("created_by_username_snapshot", String(100), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("removed_by_user_id", String(64)),
    Column("removed_by_username_snapshot", String(100)),
    Column("removed_at", DateTime),
)

# 附件元数据查询显式选列：排除 content LONGBLOB，避免详情/审计读取拉回正文。
# 只有 get_record_attachment（下载路径）才读取 content。
RECORD_ATTACHMENT_METADATA_COLUMNS = (
    RECORD_ATTACHMENTS.c.id,
    RECORD_ATTACHMENTS.c.record_id,
    RECORD_ATTACHMENTS.c.original_file_name,
    RECORD_ATTACHMENTS.c.file_extension,
    RECORD_ATTACHMENTS.c.content_type,
    RECORD_ATTACHMENTS.c.byte_size,
    RECORD_ATTACHMENTS.c.content_sha256,
    RECORD_ATTACHMENTS.c.created_by_user_id,
    RECORD_ATTACHMENTS.c.created_by_username_snapshot,
    RECORD_ATTACHMENTS.c.created_at,
    RECORD_ATTACHMENTS.c.removed_at,
)

SORTS = {
    "special_handling_at_desc": (RECORDS.c.special_handling_at.desc(), RECORDS.c.id.desc()),
    "updated_at_desc": (RECORDS.c.updated_at.desc(), RECORDS.c.id.desc()),
    "created_at_desc": (RECORDS.c.created_at.desc(), RECORDS.c.id.desc()),
}


def generate_record_no(now: datetime) -> str:
    localized = _aware(now)
    return f"RSP-{localized:%Y%m%d}-{uuid.uuid4().hex[:18]}"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=SHANGHAI)
    return value.astimezone(SHANGHAI)


def _db_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _aware(value).replace(tzinfo=None)
    return value


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


def _row(result: Any) -> dict[str, Any] | None:
    value = result.mappings().first()
    return dict(value) if value is not None else None


def _field_mapping_row(row: Mapping[str, Any]) -> dict[str, Any]:
    updated_at = row.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = _aware(updated_at)
    return {
        "datasource_id": str(row["datasource_id"]),
        "schema": str(row["schema_name"]),
        "table_name": str(row["table_name"]),
        "project_field": str(row["project_field"]),
        "contract_field": str(row["contract_field"]),
        "updated_by_username_snapshot": str(row.get("updated_by_username_snapshot") or ""),
        "updated_at": updated_at,
    }


def _normalize_record(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("created_at", "updated_at", "completed_at", "voided_at", "special_handling_at"):
        if isinstance(result.get(key), datetime):
            result[key] = _aware(result[key])
    # 结构化内容以解析后的 dict 对外暴露；解析失败（历史/损坏）按无结构化处理。
    raw_structured = result.pop("structured_content_json", None)
    structured = None
    if raw_structured:
        try:
            parsed = json.loads(str(raw_structured))
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            structured = parsed
    result["structured_content"] = structured
    return result


class SpecialProcessingStorage:
    SORTS = SORTS

    def __init__(self, database: Any) -> None:
        self.database = database

    def backfill_processes_from_records(self) -> int:
        """Copy legacy single process columns into the multi-process table once."""
        missing = (
            select(
                RECORDS.c.id,
                RECORDS.c.report_process_code,
                RECORDS.c.report_process_name_snapshot,
                RECORDS.c.created_at,
            )
            .select_from(
                RECORDS.outerjoin(PROCESSES, RECORDS.c.id == PROCESSES.c.record_id)
            )
            .where(PROCESSES.c.id.is_(None))
        )
        with self.database.transaction() as connection:
            rows = [
                row
                for row in _rows(connection.execute(missing))
                if row.get("report_process_code")
            ]
            if not rows:
                return 0
            connection.execute(
                insert(PROCESSES),
                [
                    {
                        "record_id": int(row["id"]),
                        "sequence_no": 1,
                        "report_process_code": str(row["report_process_code"]),
                        "report_process_name_snapshot": str(row["report_process_name_snapshot"] or "")[:100],
                        "created_at": _db_value(row["created_at"]),
                    }
                    for row in rows
                ],
            )
        return len(rows)

    def create(
        self,
        record: Mapping[str, Any],
        reports: Sequence[str],
        processes: Sequence[Mapping[str, str]],
        audit: Mapping[str, Any],
        *,
        record_attachment_change: Any = None,
        attachment_actor: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        values = {key: _db_value(value) for key, value in record.items()}
        values["record_no"] = generate_record_no(record["created_at"])
        new_files = (
            tuple(record_attachment_change.new_files)
            if record_attachment_change is not None
            else ()
        )
        if new_files and attachment_actor is None:
            raise ValueError("attachment_actor is required when creating attachments")
        with self.database.transaction() as connection:
            result = connection.execute(insert(RECORDS).values(**values))
            record_id = int(result.inserted_primary_key[0])
            self._replace_reports(connection, record_id, reports, record["created_at"])
            self._replace_processes(connection, record_id, processes, record["created_at"])
            audit_to_write = audit
            if record_attachment_change is not None:
                attachment_ids = (
                    self._insert_record_attachments(
                        connection, record_id, new_files, attachment_actor, record["created_at"]
                    )
                    if new_files
                    else []
                )
                audit_to_write = self._with_attachment_audit_fields(
                    audit, {"record_attachments": {"count": len(attachment_ids), "ids": attachment_ids}}
                )
            self._write_audit(connection, record_id, values["record_no"], audit_to_write)
            created = self._get_with_connection(connection, record_id)
        return created

    def get(self, record_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return self._get_with_connection(connection, record_id)

    def update(
        self,
        record_id: int,
        row_version: int,
        changes: Mapping[str, Any],
        reports: Sequence[str],
        processes: Sequence[Mapping[str, str]],
        audit: Mapping[str, Any],
        *,
        record_attachment_change: Any = None,
        attachment_actor: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        values = {key: _db_value(value) for key, value in changes.items()}
        if record_attachment_change is not None and attachment_actor is None:
            raise ValueError("attachment_actor is required when modifying attachments")
        with self.database.transaction() as connection:
            result = connection.execute(
                update(RECORDS)
                .where(and_(RECORDS.c.id == record_id, RECORDS.c.row_version == row_version))
                .values(**values, row_version=RECORDS.c.row_version + 1)
            )
            if result.rowcount != 1:
                raise VersionConflictError()
            self._replace_reports(connection, record_id, reports, changes["updated_at"])
            self._replace_processes(connection, record_id, processes, changes["updated_at"])
            audit_to_write = audit
            if record_attachment_change is not None:
                audit_to_write = self._apply_record_attachment_change(
                    connection,
                    record_id,
                    record_attachment_change,
                    attachment_actor,
                    changes["updated_at"],
                    audit,
                )
            current = self._get_with_connection(connection, record_id)
            self._write_audit(connection, record_id, current["record_no"], audit_to_write)
        return current

    def update_status(
        self,
        record_id: int,
        row_version: int,
        changes: Mapping[str, Any],
        audit: Mapping[str, Any],
        attachments: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        values = {key: _db_value(value) for key, value in changes.items()}
        with self.database.transaction() as connection:
            result = connection.execute(
                update(RECORDS)
                .where(and_(RECORDS.c.id == record_id, RECORDS.c.row_version == row_version))
                .values(**values, row_version=RECORDS.c.row_version + 1)
            )
            if result.rowcount != 1:
                raise VersionConflictError()
            current = self._get_with_connection(connection, record_id)
            audit_id = self._write_audit(connection, record_id, current["record_no"], audit)
            if attachments:
                self._write_confirm_attachments(
                    connection,
                    record_id,
                    audit_id,
                    attachments,
                    current["updated_at"],
                )
        return current

    def delete_record(self, record_id: int, row_version: int) -> None:
        with self.database.transaction() as connection:
            current = self._get_with_connection(connection, record_id)
            if current is None:
                raise RecordNotFoundError()
            if int(current.get("row_version") or 0) != int(row_version):
                raise VersionConflictError()
            connection.execute(delete(REPORTS).where(REPORTS.c.record_id == record_id))
            connection.execute(delete(PROCESSES).where(PROCESSES.c.record_id == record_id))
            connection.execute(delete(ATTACHMENTS).where(ATTACHMENTS.c.record_id == record_id))
            connection.execute(
                delete(RECORD_ATTACHMENTS).where(RECORD_ATTACHMENTS.c.record_id == record_id)
            )
            connection.execute(delete(AUDITS).where(AUDITS.c.record_id == record_id))
            result = connection.execute(
                delete(RECORDS).where(
                    and_(RECORDS.c.id == record_id, RECORDS.c.row_version == row_version)
                )
            )
            if result.rowcount != 1:
                raise VersionConflictError()

    def list_pending_for_governance_owner(self, user_id: str) -> list[dict[str, Any]]:
        owner = str(user_id or "").strip()
        if not owner:
            return []
        statement = (
            select(RECORDS)
            .where(
                and_(
                    RECORDS.c.status == "pending",
                    RECORDS.c.governance_owner_user_id == owner,
                )
            )
            .order_by(RECORDS.c.special_handling_at.desc(), RECORDS.c.id.desc())
        )
        with self.database.connect() as connection:
            items = [_normalize_record(row) for row in _rows(connection.execute(statement))]
            self._attach_reports(connection, items)
            self._attach_processes(connection, items)
        return items

    def list_confirmed_history_for_operator(self, user_id: str) -> list[dict[str, Any]]:
        operator = str(user_id or "").strip()
        if not operator:
            return []
        latest_confirm = (
            select(
                AUDITS.c.record_id.label("record_id"),
                func.max(AUDITS.c.occurred_at).label("confirmed_at"),
            )
            .where(
                and_(
                    AUDITS.c.operator_user_id == operator,
                    AUDITS.c.to_status == "completed",
                )
            )
            .group_by(AUDITS.c.record_id)
            .subquery()
        )
        statement = (
            select(
                RECORDS.c.id,
                RECORDS.c.dimension,
                RECORDS.c.field_name,
                RECORDS.c.creator_user_id,
                RECORDS.c.creator_username_snapshot,
                RECORDS.c.handler_username_snapshot,
                RECORDS.c.handler_display_name_snapshot,
                latest_confirm.c.confirmed_at,
            )
            .select_from(
                RECORDS.join(
                    latest_confirm,
                    RECORDS.c.id == latest_confirm.c.record_id,
                )
            )
            .where(RECORDS.c.status == "completed")
            .order_by(latest_confirm.c.confirmed_at.desc(), RECORDS.c.id.desc())
        )
        with self.database.connect() as connection:
            items = []
            for row in _rows(connection.execute(statement)):
                item = dict(row)
                confirmed_at = item.get("confirmed_at")
                if isinstance(confirmed_at, datetime):
                    item["confirmed_at"] = _aware(confirmed_at)
                items.append(item)
        return items

    def list(self, query: PageQuery) -> dict[str, Any]:
        conditions = self._conditions(query.filters)
        statement = select(RECORDS)
        count_statement = select(func.count(func.distinct(RECORDS.c.id))).select_from(RECORDS)
        keyword = query.filters.get("keyword")
        if keyword:
            report_match = select(REPORTS.c.record_id).where(
                REPORTS.c.report_name_normalized.contains(str(keyword), autoescape=True)
            )
            conditions.append(
                or_(
                    RECORDS.c.record_no.contains(str(keyword), autoescape=True),
                    RECORDS.c.summary.contains(str(keyword), autoescape=True),
                    RECORDS.c.id.in_(report_match),
                )
            )
        if conditions:
            statement = statement.where(and_(*conditions))
            count_statement = count_statement.where(and_(*conditions))
        statement = statement.order_by(*SORTS[query.sort]).offset(
            (query.page - 1) * query.page_size
        ).limit(query.page_size)
        with self.database.connect() as connection:
            total = int(connection.execute(count_statement).scalar_one() or 0)
            items = [_normalize_record(row) for row in _rows(connection.execute(statement))]
            self._attach_reports(connection, items)
            self._attach_processes(connection, items)
            self._attach_record_attachment_counts(connection, items)
        return {
            "items": items,
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": math.ceil(total / query.page_size) if total else 0,
        }

    def list_for_export(self, query: PageQuery, *, limit: int) -> list[dict[str, Any]]:
        conditions = self._conditions(query.filters)
        statement = select(RECORDS)
        keyword = query.filters.get("keyword")
        if keyword:
            report_match = select(REPORTS.c.record_id).where(
                REPORTS.c.report_name_normalized.contains(str(keyword), autoescape=True)
            )
            conditions.append(
                or_(
                    RECORDS.c.record_no.contains(str(keyword), autoescape=True),
                    RECORDS.c.summary.contains(str(keyword), autoescape=True),
                    RECORDS.c.id.in_(report_match),
                )
            )
        if conditions:
            statement = statement.where(and_(*conditions))
        statement = statement.order_by(*SORTS[query.sort]).limit(limit)
        with self.database.connect() as connection:
            items = [_normalize_record(row) for row in _rows(connection.execute(statement))]
            self._attach_reports(connection, items)
            self._attach_processes(connection, items)
        return items

    def get_confirm_attachment(self, record_id: int, attachment_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return _row(
                connection.execute(
                    select(ATTACHMENTS).where(
                        and_(
                            ATTACHMENTS.c.id == attachment_id,
                            ATTACHMENTS.c.record_id == record_id,
                        )
                    )
                )
            )

    def list_record_attachments(
        self,
        record_id: int,
        *,
        include_removed: bool = False,
        attachment_ids: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            return self._list_record_attachments_with_connection(
                connection,
                record_id,
                include_removed=include_removed,
                attachment_ids=attachment_ids,
            )

    def get_record_attachment(self, record_id: int, attachment_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = _row(
                connection.execute(
                    select(RECORD_ATTACHMENTS).where(
                        and_(
                            RECORD_ATTACHMENTS.c.id == attachment_id,
                            RECORD_ATTACHMENTS.c.record_id == record_id,
                        )
                    )
                )
            )
        if row is None:
            return None
        metadata = self._record_attachment_metadata(row)
        content = row.get("content")
        metadata["content"] = bytes(content) if isinstance(content, (bytes, bytearray)) else b""
        return metadata

    def _list_record_attachments_with_connection(
        self,
        connection: Any,
        record_id: int,
        *,
        include_removed: bool = False,
        attachment_ids: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        statement = select(*RECORD_ATTACHMENT_METADATA_COLUMNS).where(
            RECORD_ATTACHMENTS.c.record_id == record_id
        )
        if attachment_ids is not None:
            if not attachment_ids:
                return []
            statement = statement.where(
                RECORD_ATTACHMENTS.c.id.in_(tuple(int(item) for item in attachment_ids))
            )
        elif not include_removed:
            statement = statement.where(RECORD_ATTACHMENTS.c.removed_at.is_(None))
        statement = statement.order_by(
            RECORD_ATTACHMENTS.c.created_at.asc(), RECORD_ATTACHMENTS.c.id.asc()
        )
        rows = _rows(connection.execute(statement))
        return [self._record_attachment_metadata(row) for row in rows]

    # ===== 处理表 项目/合同 定位字段映射 =====

    def list_field_mappings(self, datasource_id: str) -> list[dict[str, Any]]:
        wanted = str(datasource_id or "").strip()
        if not wanted:
            return []
        statement = (
            select(
                FIELD_MAPPINGS.c.datasource_id,
                FIELD_MAPPINGS.c.schema_name,
                FIELD_MAPPINGS.c.table_name,
                FIELD_MAPPINGS.c.project_field,
                FIELD_MAPPINGS.c.contract_field,
                FIELD_MAPPINGS.c.updated_by_username_snapshot,
                FIELD_MAPPINGS.c.updated_at,
            )
            .where(FIELD_MAPPINGS.c.datasource_id == wanted)
            .order_by(FIELD_MAPPINGS.c.table_name.asc(), FIELD_MAPPINGS.c.schema_name.asc())
        )
        with self.database.connect() as connection:
            return [_field_mapping_row(row) for row in _rows(connection.execute(statement))]

    def get_field_mapping(self, datasource_id: str, schema_name: str, table_name: str) -> dict[str, Any] | None:
        statement = (
            select(
                FIELD_MAPPINGS.c.datasource_id,
                FIELD_MAPPINGS.c.schema_name,
                FIELD_MAPPINGS.c.table_name,
                FIELD_MAPPINGS.c.project_field,
                FIELD_MAPPINGS.c.contract_field,
            )
            .where(
                and_(
                    FIELD_MAPPINGS.c.datasource_id == str(datasource_id or "").strip(),
                    FIELD_MAPPINGS.c.schema_name == str(schema_name or "").strip(),
                    FIELD_MAPPINGS.c.table_name == str(table_name or "").strip(),
                )
            )
        )
        with self.database.connect() as connection:
            row = _row(connection.execute(statement))
        return _field_mapping_row(row) if row else None

    def upsert_field_mapping(
        self,
        datasource_id: str,
        schema_name: str,
        table_name: str,
        project_field: str,
        contract_field: str,
        *,
        user_id: str,
        username: str,
    ) -> dict[str, Any]:
        datasource_id = str(datasource_id or "").strip()
        schema_name = str(schema_name or "").strip()
        table_name = str(table_name or "").strip()
        project_field = str(project_field or "").strip()[:128]
        contract_field = str(contract_field or "").strip()[:128]
        now = datetime.now(SHANGHAI)
        with self.database.transaction() as connection:
            existing = _row(
                connection.execute(
                    select(FIELD_MAPPINGS.c.id).where(
                        and_(
                            FIELD_MAPPINGS.c.datasource_id == datasource_id,
                            FIELD_MAPPINGS.c.schema_name == schema_name,
                            FIELD_MAPPINGS.c.table_name == table_name,
                        )
                    )
                )
            )
            if existing is None:
                connection.execute(
                    insert(FIELD_MAPPINGS).values(
                        datasource_id=datasource_id,
                        schema_name=schema_name,
                        table_name=table_name,
                        project_field=project_field,
                        contract_field=contract_field,
                        updated_by_user_id=str(user_id or "").strip()[:64],
                        updated_by_username_snapshot=str(username or "").strip()[:100],
                        updated_at=_db_value(now),
                    )
                )
            else:
                connection.execute(
                    update(FIELD_MAPPINGS)
                    .where(FIELD_MAPPINGS.c.id == existing["id"])
                    .values(
                        project_field=project_field,
                        contract_field=contract_field,
                        updated_by_user_id=str(user_id or "").strip()[:64],
                        updated_by_username_snapshot=str(username or "").strip()[:100],
                        updated_at=_db_value(now),
                    )
                )
        return self.get_field_mapping(datasource_id, schema_name, table_name) or {
            "datasource_id": datasource_id,
            "schema_name": schema_name,
            "table_name": table_name,
            "project_field": project_field,
            "contract_field": contract_field,
        }

    @staticmethod
    def _record_attachment_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
        created_at = row.get("created_at")
        if isinstance(created_at, datetime):
            created_at = _aware(created_at)
        return {
            "id": int(row["id"]),
            "file_name": str(row["original_file_name"]),
            "file_extension": str(row["file_extension"]),
            "content_type": str(row["content_type"]),
            "byte_size": int(row["byte_size"]),
            "content_sha256": str(row["content_sha256"]),
            "created_by": {
                "user_id": str(row["created_by_user_id"]),
                "username": str(row["created_by_username_snapshot"]),
            },
            "created_at": created_at,
            "removed": row.get("removed_at") is not None,
        }

    def audit(self, record_id: int, query: PageQuery) -> dict[str, Any]:
        count_statement = select(func.count()).select_from(AUDITS).where(
            AUDITS.c.record_id == record_id
        )
        with self.database.connect() as connection:
            total = int(connection.execute(count_statement).scalar_one() or 0)
            total_pages = math.ceil(total / query.page_size) if total else 0
            page = query.page
            if total_pages <= 0:
                page = 1
            elif page > total_pages:
                page = total_pages
            statement = (
                select(AUDITS)
                .where(AUDITS.c.record_id == record_id)
                .order_by(AUDITS.c.occurred_at.desc(), AUDITS.c.id.desc())
                .offset((page - 1) * query.page_size)
                .limit(query.page_size)
            )
            items = _rows(connection.execute(statement)) if total else []
            for item in items:
                if isinstance(item.get("occurred_at"), datetime):
                    item["occurred_at"] = _aware(item["occurred_at"])
                try:
                    item["changed_fields"] = json.loads(item.pop("changed_fields_json"))
                except (TypeError, ValueError):
                    item["changed_fields"] = {}
            self._hydrate_record_attachment_audits(connection, record_id, items)
        return {
            "items": items,
            "page": page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def _hydrate_record_attachment_audits(
        self, connection: Any, record_id: int, items: list[dict[str, Any]]
    ) -> None:
        """批量补全审计中的附件修改前后元数据，避免逐附件 N+1 查询。

        新增/移除/保留标签只按该条审计自身的 old_ids/new_ids 集合差计算，
        不读取附件行当前的 removed_at 推断历史状态。
        """
        attachment_fields: list[dict[str, Any]] = []
        wanted: set[int] = set()
        for item in items:
            changed = item.get("changed_fields") or {}
            field = changed.get("record_attachments")
            if not isinstance(field, dict) or "ids" in field:
                continue
            old_ids = field.get("old_ids") or []
            new_ids = field.get("new_ids") or []
            wanted.update(int(value) for value in old_ids)
            wanted.update(int(value) for value in new_ids)
            attachment_fields.append(field)
        if not wanted:
            return
        rows = _rows(
            connection.execute(
                select(*RECORD_ATTACHMENT_METADATA_COLUMNS).where(
                    and_(
                        RECORD_ATTACHMENTS.c.record_id == record_id,
                        RECORD_ATTACHMENTS.c.id.in_(tuple(wanted)),
                    )
                )
            )
        )
        metadata = {int(row["id"]): self._record_attachment_metadata(row) for row in rows}
        for field in attachment_fields:
            old_ids = [int(value) for value in field.get("old_ids") or []]
            new_ids = [int(value) for value in field.get("new_ids") or []]
            old_set = set(old_ids)
            new_set = set(new_ids)
            field["old"] = [
                {**(metadata.get(attachment_id) or {"id": attachment_id}),
                 "change": "retained" if attachment_id in new_set else "removed"}
                for attachment_id in old_ids
            ]
            field["new"] = [
                {**(metadata.get(attachment_id) or {"id": attachment_id}),
                 "change": "retained" if attachment_id in old_set else "added"}
                for attachment_id in new_ids
            ]

    def count_by_handling_period(
        self, start: datetime, end_exclusive: datetime
    ) -> dict[str, int]:
        statement = (
            select(RECORDS.c.status, func.count().label("count"))
            .where(
                and_(
                    RECORDS.c.special_handling_at >= start,
                    RECORDS.c.special_handling_at < end_exclusive,
                )
            )
            .group_by(RECORDS.c.status)
        )
        with self.database.connect() as connection:
            rows = _rows(connection.execute(statement))
        return {str(row["status"]): int(row["count"]) for row in rows}

    def summary_for_report_period(self, period: date) -> tuple[dict[str, int], list[dict[str, Any]], int]:
        counts_statement = (
            select(RECORDS.c.status, func.count().label("count"))
            .where(RECORDS.c.report_period == period)
            .group_by(RECORDS.c.status)
        )
        total_statement = (
            select(func.count().label("record_total"))
            .where(RECORDS.c.report_period == period)
        )
        process_statement = (
            select(
                PROCESSES.c.report_process_code,
                PROCESSES.c.report_process_name_snapshot,
                func.count(func.distinct(RECORDS.c.id)).label("effective_count"),
            )
            .select_from(
                PROCESSES.join(RECORDS, PROCESSES.c.record_id == RECORDS.c.id)
            )
            .where(
                and_(
                    RECORDS.c.report_period == period,
                    RECORDS.c.status.in_(("pending", "processing", "completed")),
                )
            )
            .group_by(PROCESSES.c.report_process_code, PROCESSES.c.report_process_name_snapshot)
        )
        with self.database.connect() as connection:
            counts_rows = _rows(connection.execute(counts_statement))
            total_row = _row(connection.execute(total_statement)) or {}
            process_rows = _rows(connection.execute(process_statement))
        return (
            {str(row["status"]): int(row["count"]) for row in counts_rows},
            [
                {
                    "code": str(row["report_process_code"]),
                    "name": str(row["report_process_name_snapshot"]),
                    "effective_count": int(row["effective_count"] or 0),
                }
                for row in process_rows
            ],
            int(total_row.get("record_total") or 0),
        )

    def _get_with_connection(self, connection: Any, record_id: int) -> dict[str, Any] | None:
        record = _row(connection.execute(select(RECORDS).where(RECORDS.c.id == record_id)))
        if record is None:
            return None
        result = _normalize_record(record)
        self._attach_reports(connection, [result])
        self._attach_processes(connection, [result])
        result["record_attachments"] = self._list_record_attachments_with_connection(
            connection, record_id
        )
        return result

    @staticmethod
    def _replace_reports(
        connection: Any, record_id: int, reports: Sequence[str], created_at: datetime
    ) -> None:
        connection.execute(delete(REPORTS).where(REPORTS.c.record_id == record_id))
        if reports:
            connection.execute(
                insert(REPORTS),
                [
                    {
                        "record_id": record_id,
                        "sequence_no": index,
                        "report_name": name,
                        "report_name_normalized": name,
                        "created_at": _db_value(created_at),
                    }
                    for index, name in enumerate(reports, 1)
                ],
            )

    @staticmethod
    def _replace_processes(
        connection: Any,
        record_id: int,
        processes: Sequence[Mapping[str, str]],
        created_at: datetime,
    ) -> None:
        connection.execute(delete(PROCESSES).where(PROCESSES.c.record_id == record_id))
        if processes:
            connection.execute(
                insert(PROCESSES),
                [
                    {
                        "record_id": record_id,
                        "sequence_no": index,
                        "report_process_code": item["code"],
                        "report_process_name_snapshot": item["name"],
                        "created_at": _db_value(created_at),
                    }
                    for index, item in enumerate(processes, 1)
                ],
            )

    @staticmethod
    def _write_audit(
        connection: Any,
        record_id: int,
        record_no: str,
        audit: Mapping[str, Any],
    ) -> int:
        result = connection.execute(
            insert(AUDITS).values(
                record_id=record_id,
                record_no_snapshot=record_no,
                **{key: _db_value(value) for key, value in audit.items()},
            )
        )
        primary_key = result.inserted_primary_key
        if primary_key:
            return int(primary_key[0])
        return int(result.lastrowid)

    @staticmethod
    def _write_confirm_attachments(
        connection: Any,
        record_id: int,
        audit_id: int,
        attachments: Sequence[Mapping[str, Any]],
        created_at: datetime,
    ) -> None:
        ids: list[int] = []
        for sequence_no, item in enumerate(attachments, 1):
            content = bytes(item["content"])
            result = connection.execute(
                insert(ATTACHMENTS).values(
                    record_id=record_id,
                    audit_id=audit_id,
                    sequence_no=sequence_no,
                    content_type=str(item["content_type"]),
                    byte_size=len(content),
                    content_sha256=hashlib.sha256(content).hexdigest(),
                    content=content,
                    created_at=_db_value(created_at),
                )
            )
            primary_key = result.inserted_primary_key
            attachment_id = int(primary_key[0]) if primary_key else int(result.lastrowid)
            ids.append(attachment_id)
        raw_changed = connection.execute(
            select(AUDITS.c.changed_fields_json).where(AUDITS.c.id == audit_id)
        ).scalar_one()
        try:
            changed = json.loads(raw_changed)
        except (TypeError, ValueError):
            changed = {}
        if not isinstance(changed, dict):
            changed = {}
        changed["confirm_attachments"] = {"count": len(ids), "ids": ids}
        connection.execute(
            update(AUDITS)
            .where(AUDITS.c.id == audit_id)
            .values(changed_fields_json=json.dumps(changed, ensure_ascii=False, separators=(",", ":")))
        )

    def _insert_record_attachments(
        self,
        connection: Any,
        record_id: int,
        files: Sequence[Any],
        actor: Mapping[str, str],
        created_at: datetime,
    ) -> list[int]:
        ids: list[int] = []
        for item in files:
            content = bytes(item.content)
            result = connection.execute(
                insert(RECORD_ATTACHMENTS).values(
                    record_id=record_id,
                    original_file_name=item.file_name,
                    file_extension=item.file_extension,
                    content_type=item.content_type,
                    byte_size=len(content),
                    content_sha256=item.content_sha256,
                    content=content,
                    created_by_user_id=str(actor["user_id"]),
                    created_by_username_snapshot=str(actor["username"]),
                    created_at=_db_value(created_at),
                )
            )
            primary_key = result.inserted_primary_key
            attachment_id = int(primary_key[0]) if primary_key else int(result.lastrowid)
            ids.append(attachment_id)
        return ids

    @staticmethod
    def _with_attachment_audit_fields(
        audit: Mapping[str, Any], extra: Mapping[str, Any]
    ) -> dict[str, Any]:
        merged = dict(audit)
        try:
            changed = json.loads(merged.get("changed_fields_json") or "{}")
        except (TypeError, ValueError):
            changed = {}
        if not isinstance(changed, dict):
            changed = {}
        changed.update(extra)
        merged["changed_fields_json"] = json.dumps(
            changed, ensure_ascii=False, separators=(",", ":")
        )
        return merged

    def _apply_record_attachment_change(
        self,
        connection: Any,
        record_id: int,
        change: Any,
        actor: Mapping[str, str] | None,
        updated_at: datetime,
        audit: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        # 只需当前附件 ID：显式选择 id 列，禁止把 content LONGBLOB 读回事务内存。
        current_rows = _rows(
            connection.execute(
                select(RECORD_ATTACHMENTS.c.id)
                .where(
                    and_(
                        RECORD_ATTACHMENTS.c.record_id == record_id,
                        RECORD_ATTACHMENTS.c.removed_at.is_(None),
                    )
                )
                .order_by(
                    RECORD_ATTACHMENTS.c.created_at.asc(), RECORD_ATTACHMENTS.c.id.asc()
                )
            )
        )
        current_ids = [int(row["id"]) for row in current_rows]
        retained_set = {int(item) for item in change.retained_ids}
        if not retained_set.issubset(set(current_ids)):
            raise RecordNotFoundError()
        removed_ids = [cid for cid in current_ids if cid not in retained_set]
        added_ids: list[int] = []
        if removed_ids or change.new_files:
            if actor is None:
                raise ValueError("attachment_actor is required when modifying attachments")
        if removed_ids:
            connection.execute(
                update(RECORD_ATTACHMENTS)
                .where(
                    and_(
                        RECORD_ATTACHMENTS.c.record_id == record_id,
                        RECORD_ATTACHMENTS.c.id.in_(tuple(removed_ids)),
                        RECORD_ATTACHMENTS.c.removed_at.is_(None),
                    )
                )
                .values(
                    removed_by_user_id=str(actor["user_id"]),
                    removed_by_username_snapshot=str(actor["username"]),
                    removed_at=_db_value(updated_at),
                )
            )
        if change.new_files:
            added_ids = self._insert_record_attachments(
                connection, record_id, change.new_files, actor, updated_at
            )
        if not removed_ids and not added_ids:
            # 集合未变化：不计为附件修改，避免产生空审计字段。
            return audit
        retained_in_order = [cid for cid in current_ids if cid in retained_set]
        new_ids = retained_in_order + added_ids
        return self._with_attachment_audit_fields(
            audit,
            {
                "record_attachments": {
                    "changed": True,
                    "old_ids": current_ids,
                    "new_ids": new_ids,
                    "added_ids": added_ids,
                    "removed_ids": removed_ids,
                }
            },
        )

    @staticmethod
    def _attach_reports(connection: Any, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        ids = [record["id"] for record in records]
        rows = _rows(
            connection.execute(
                select(REPORTS)
                .where(REPORTS.c.record_id.in_(ids))
                .order_by(REPORTS.c.record_id, REPORTS.c.sequence_no)
            )
        )
        grouped: dict[int, list[str]] = {}
        for row in rows:
            grouped.setdefault(int(row["record_id"]), []).append(str(row["report_name"]))
        for record in records:
            record["reports"] = grouped.get(int(record["id"]), [])

    @staticmethod
    def _attach_processes(connection: Any, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        ids = [record["id"] for record in records]
        rows = _rows(
            connection.execute(
                select(PROCESSES)
                .where(PROCESSES.c.record_id.in_(ids))
                .order_by(PROCESSES.c.record_id, PROCESSES.c.sequence_no)
            )
        )
        grouped: dict[int, list[dict[str, str]]] = {}
        for row in rows:
            grouped.setdefault(int(row["record_id"]), []).append(
                {
                    "code": str(row["report_process_code"]),
                    "name": str(row["report_process_name_snapshot"]),
                }
            )
        for record in records:
            processes = grouped.get(int(record["id"]), [])
            if not processes and record.get("report_process_code"):
                processes = [
                    {
                        "code": str(record["report_process_code"]),
                        "name": str(record.get("report_process_name_snapshot") or ""),
                    }
                ]
            record["report_processes"] = processes
            record["report_process_codes"] = [item["code"] for item in processes]
            if processes:
                record["report_process_name_snapshot"] = "；".join(
                    item["name"] for item in processes if item["name"]
                ) or record.get("report_process_name_snapshot")

    @staticmethod
    def _attach_record_attachment_counts(connection: Any, records: list[dict[str, Any]]) -> None:
        for record in records:
            record["record_attachment_count"] = 0
        if not records:
            return
        ids = [record["id"] for record in records]
        rows = _rows(
            connection.execute(
                select(RECORD_ATTACHMENTS.c.record_id, func.count().label("attachment_count"))
                .where(
                    and_(
                        RECORD_ATTACHMENTS.c.record_id.in_(tuple(ids)),
                        RECORD_ATTACHMENTS.c.removed_at.is_(None),
                    )
                )
                .group_by(RECORD_ATTACHMENTS.c.record_id)
            )
        )
        counts = {int(row["record_id"]): int(row["attachment_count"]) for row in rows}
        for record in records:
            record["record_attachment_count"] = counts.get(int(record["id"]), 0)

    @staticmethod
    def _conditions(filters: Mapping[str, Any]) -> list[Any]:
        conditions = []
        process_code = filters.get("report_process_code")
        if process_code not in {None, ""}:
            process_match = select(PROCESSES.c.record_id).where(
                PROCESSES.c.report_process_code == process_code
            )
            conditions.append(
                or_(
                    RECORDS.c.report_process_code == process_code,
                    RECORDS.c.id.in_(process_match),
                )
            )
        for key in ("status", "handler_user_id", "report_period"):
            if key in filters:
                conditions.append(RECORDS.c[key] == filters[key])
        if "special_handling_from" in filters:
            conditions.append(RECORDS.c.special_handling_at >= filters["special_handling_from"])
        if "special_handling_to" in filters:
            conditions.append(RECORDS.c.special_handling_at < filters["special_handling_to"])
        return conditions
