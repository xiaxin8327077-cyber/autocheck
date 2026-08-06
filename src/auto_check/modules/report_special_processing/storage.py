from __future__ import annotations

from datetime import date, datetime
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
    Column("summary", String(200)),
    Column("processing_content", Text),
    Column("processing_script", Text),
    Column("script_sha256", String(64)),
    Column("status", String(20), nullable=False),
    Column("special_handling_at", DateTime),
    Column("handler_user_id", String(64)),
    Column("handler_username_snapshot", String(100)),
    Column("handler_display_name_snapshot", String(100)),
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
    Column("changed_fields_json", Text, nullable=False),
    Column("action_summary", String(1000), nullable=False),
    Column("request_id", String(64)),
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


def _normalize_record(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("created_at", "updated_at", "completed_at", "voided_at", "special_handling_at"):
        if isinstance(result.get(key), datetime):
            result[key] = _aware(result[key])
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
    ) -> dict[str, Any]:
        values = {key: _db_value(value) for key, value in record.items()}
        values["record_no"] = generate_record_no(record["created_at"])
        with self.database.transaction() as connection:
            result = connection.execute(insert(RECORDS).values(**values))
            record_id = int(result.inserted_primary_key[0])
            self._replace_reports(connection, record_id, reports, record["created_at"])
            self._replace_processes(connection, record_id, processes, record["created_at"])
            self._write_audit(connection, record_id, values["record_no"], audit)
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
            self._replace_reports(connection, record_id, reports, changes["updated_at"])
            self._replace_processes(connection, record_id, processes, changes["updated_at"])
            current = self._get_with_connection(connection, record_id)
            self._write_audit(connection, record_id, current["record_no"], audit)
        return current

    def update_status(
        self,
        record_id: int,
        row_version: int,
        changes: Mapping[str, Any],
        audit: Mapping[str, Any],
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
            self._write_audit(connection, record_id, current["record_no"], audit)
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
            connection.execute(delete(AUDITS).where(AUDITS.c.record_id == record_id))
            result = connection.execute(
                delete(RECORDS).where(
                    and_(RECORDS.c.id == record_id, RECORDS.c.row_version == row_version)
                )
            )
            if result.rowcount != 1:
                raise VersionConflictError()

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
        return {
            "items": items,
            "page": page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": total_pages,
        }

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
    ) -> None:
        connection.execute(
            insert(AUDITS).values(
                record_id=record_id,
                record_no_snapshot=record_no,
                **{key: _db_value(value) for key, value in audit.items()},
            )
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
