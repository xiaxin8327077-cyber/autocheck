from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.mysql import DATE, DATETIME, TIME, insert as mysql_insert
from sqlalchemy.engine import Connection


_METADATA = MetaData()

RUN_HEADERS = Table(
    "run_headers",
    _METADATA,
    Column("id", String(64), primary_key=True),
    Column("kind", String(32), nullable=False),
    Column("run_date", DATE, nullable=True),
    Column("run_at", DATETIME(fsp=6), nullable=True),
    Column("finished_at", DATETIME(fsp=6), nullable=True),
    Column("status", String(64), nullable=False),
    Column("executor_id", String(64), nullable=False),
    Column("executor_username", String(191), nullable=False),
    Column("executor_name", String(191), nullable=False),
    Column("config_fingerprint", String(64), nullable=False),
    Column("payload_json", Text, nullable=False),
)

RECONCILE_RUNS = Table(
    "reconcile_runs",
    _METADATA,
    Column("id", String(64), primary_key=True),
    Column("config_name", String(255), nullable=False),
    Column("dws_source_name", String(255), nullable=False),
    Column("rule_version", String(64), nullable=False),
    Column("baseline_id", String(64), nullable=False),
    Column("baseline_run_at", DATETIME(fsp=6), nullable=True),
    Column("baseline_count", Integer, nullable=True),
    Column("total_count", Integer, nullable=False),
    Column("added_count", Integer, nullable=True),
    Column("removed_count", Integer, nullable=True),
)

RECONCILE_RUN_COUNTS = Table(
    "reconcile_run_counts",
    _METADATA,
    Column("run_id", String(64), nullable=False),
    Column("count_type", String(32), nullable=False),
    Column("label", String(255), nullable=False),
    Column("count_value", Integer, nullable=False),
)

RECONCILE_RESULTS = Table(
    "reconcile_results",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("result_order", Integer, nullable=False),
    Column("project_code", String(191), nullable=False),
    Column("project_name", String(255), nullable=False),
    Column("asset_total", Numeric(38, 12), nullable=True),
    Column("liability_equity_total", Numeric(38, 12), nullable=True),
    Column("received_trust_balance", Numeric(38, 12), nullable=True),
    Column("difference", Numeric(38, 12), nullable=True),
    Column("direction", String(255), nullable=False),
    Column("difference_reason", String(255), nullable=False),
    Column("match_status", String(64), nullable=False),
    Column("valuation_asset_total", Numeric(38, 12), nullable=True),
    Column("payload_json", Text, nullable=False),
)

RECONCILE_RESULT_DETAILS = Table(
    "reconcile_result_details",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("result_id", BigInteger, nullable=False),
    Column("detail_order", Integer, nullable=False),
    Column("kind", String(64), nullable=False),
    Column("specific_reason", String(255), nullable=False),
    Column("data_json", Text, nullable=False),
)

RECONCILE_DELTA_RESULTS = Table(
    "reconcile_delta_results",
    _METADATA,
    Column("run_id", String(64), nullable=False),
    Column("delta_type", String(16), nullable=False),
    Column("result_order", Integer, nullable=False),
    Column("payload_json", Text, nullable=False),
)

DB_VALIDATION_RUNS = Table(
    "db_validation_runs",
    _METADATA,
    Column("id", String(64), primary_key=True),
    Column("report_date", DATE, nullable=True),
    Column("result_count", Integer, nullable=False),
    Column("warning_count", Integer, nullable=False),
    Column("table_count", Integer, nullable=False),
    Column("enable_public_info_check", Boolean, nullable=False),
    Column("enable_template_check", Boolean, nullable=False),
    Column("excel_filename", String(255), nullable=False),
    Column("excel_path", String(1024), nullable=False),
    Column("download_url", String(1024), nullable=False),
)

DB_VALIDATION_SELECTED_TABLES = Table(
    "db_validation_selected_tables",
    _METADATA,
    Column("run_id", String(64), nullable=False),
    Column("table_order", Integer, nullable=False),
    Column("table_code", String(64), nullable=False),
)

DB_VALIDATION_WARNINGS = Table(
    "db_validation_warnings",
    _METADATA,
    Column("run_id", String(64), nullable=False),
    Column("warning_order", Integer, nullable=False),
    Column("message", Text, nullable=False),
)

DB_VALIDATION_RESULT_ROWS = Table(
    "db_validation_result_rows",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("row_order", Integer, nullable=False),
    Column("table_code", String(64), nullable=False),
    Column("rule_id", String(191), nullable=False),
    Column("severity", String(32), nullable=False),
    Column("message", Text, nullable=False),
    Column("detail", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
)

FLOW_CHAIN_RUNS = Table(
    "flow_chain_runs",
    _METADATA,
    Column("id", String(64), primary_key=True),
    Column("chain_id", String(191), nullable=False),
    Column("chain_name", String(255), nullable=False),
    Column("is_multi_chain", Boolean, nullable=False),
    Column("trigger_type", String(32), nullable=False),
    Column("executor_name", String(191), nullable=False),
    Column("status", String(64), nullable=False),
    Column("error", Text, nullable=False),
    Column("step_count", Integer, nullable=False),
    Column("duration_seconds", Integer, nullable=False),
)

FLOW_CHAIN_RUN_STEPS = Table(
    "flow_chain_run_steps",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("step_order", Integer, nullable=False),
    Column("flow_id", String(191), nullable=False),
    Column("name", String(255), nullable=False),
    Column("status", String(64), nullable=False),
    Column("sp_task_id", String(64), nullable=False),
    Column("start_time", DATETIME(fsp=6), nullable=True),
    Column("end_time", DATETIME(fsp=6), nullable=True),
    Column("duration_seconds", Integer, nullable=True),
    Column("payload_json", Text, nullable=False),
)

FLOW_CHAIN_RUN_LOGS = Table(
    "flow_chain_run_logs",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("log_order", Integer, nullable=False),
    Column("log_time", TIME(fsp=6), nullable=True),
    Column("message", Text, nullable=False),
    Column("progress", Integer, nullable=True),
    Column("step", String(255), nullable=False),
    Column("payload_json", Text, nullable=False),
)

FLOW_CHAIN_RUN_DETAILS = Table(
    "flow_chain_run_details",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("run_id", String(64), nullable=False),
    Column("chain_order", Integer, nullable=False),
    Column("chain_name", String(255), nullable=False),
    Column("status", String(64), nullable=False),
    Column("step_count", Integer, nullable=False),
    Column("duration_seconds", Integer, nullable=False),
    Column("error", Text, nullable=False),
    Column("payload_json", Text, nullable=False),
)


def save_reconcile_run(connection: Connection, run: dict[str, Any]) -> None:
    run_id = _required_run_id(run)
    _upsert_run_header(connection, "reconcile", run)
    _execute_upsert(
        connection,
        RECONCILE_RUNS,
        {
            "id": run_id,
            "config_name": _text(run.get("config_name")),
            "dws_source_name": _text(run.get("dws_source_name")),
            "rule_version": _text(run.get("rule_version")),
            "baseline_id": _text(run.get("baseline_id")),
            "baseline_run_at": _optional_datetime(run.get("baseline_run_at")),
            "baseline_count": _optional_int(run.get("baseline_count")),
            "total_count": _optional_int(run.get("total_count")) or 0,
            "added_count": _optional_int(run.get("added_count")),
            "removed_count": _optional_int(run.get("removed_count")),
        },
    )
    _replace_reconcile_children(connection, run_id, run)


def list_reconcile_runs(connection: Connection) -> list[dict[str, Any]]:
    return _list_kind_runs(connection, "reconcile", RUN_HEADERS.c.run_date.desc(), RUN_HEADERS.c.run_at.desc())


def get_reconcile_run(connection: Connection, run_id: str) -> dict[str, Any] | None:
    return _get_kind_run(connection, "reconcile", run_id)


def delete_reconcile_run(connection: Connection, run_id: str) -> bool:
    return _delete_kind_run(connection, "reconcile", run_id)


def save_db_validation_run(connection: Connection, run: dict[str, Any]) -> None:
    run_id = _required_run_id(run)
    _upsert_run_header(connection, "db_validation", run)
    _execute_upsert(
        connection,
        DB_VALIDATION_RUNS,
        {
            "id": run_id,
            "report_date": _optional_date(run.get("report_date") or run.get("run_date")),
            "result_count": _optional_int(run.get("result_count")) or 0,
            "warning_count": _optional_int(run.get("warning_count")) or len(_list(run.get("warnings"))),
            "table_count": _optional_int(run.get("table_count")) or len(_list(run.get("selected_tables"))),
            "enable_public_info_check": bool(run.get("enable_public_info_check")),
            "enable_template_check": bool(run.get("enable_template_check")),
            "excel_filename": _text(run.get("excel_filename")),
            "excel_path": _text(run.get("excel_path")),
            "download_url": _text(run.get("download_url")),
        },
    )
    _replace_db_validation_children(connection, run_id, run)


def list_db_validation_runs(connection: Connection) -> list[dict[str, Any]]:
    return _list_kind_runs(connection, "db_validation", RUN_HEADERS.c.run_at.desc(), RUN_HEADERS.c.id.desc())


def list_db_validation_run_summaries(connection: Connection) -> list[dict[str, Any]]:
    header_rows = connection.execute(
        select(
            RUN_HEADERS.c.id,
            RUN_HEADERS.c.run_date,
            RUN_HEADERS.c.run_at,
            RUN_HEADERS.c.finished_at,
            RUN_HEADERS.c.status,
            RUN_HEADERS.c.executor_id,
            RUN_HEADERS.c.executor_username,
            RUN_HEADERS.c.executor_name,
        )
        .where(RUN_HEADERS.c.kind == "db_validation")
        .order_by(RUN_HEADERS.c.run_at.desc(), RUN_HEADERS.c.id.desc())
    ).mappings().all()
    if not header_rows:
        return []

    run_ids = [str(row["id"]) for row in header_rows]
    detail_rows = connection.execute(
        select(
            DB_VALIDATION_RUNS.c.id,
            DB_VALIDATION_RUNS.c.report_date,
            DB_VALIDATION_RUNS.c.result_count,
            DB_VALIDATION_RUNS.c.warning_count,
            DB_VALIDATION_RUNS.c.table_count,
            DB_VALIDATION_RUNS.c.enable_public_info_check,
            DB_VALIDATION_RUNS.c.enable_template_check,
            DB_VALIDATION_RUNS.c.download_url,
        ).where(DB_VALIDATION_RUNS.c.id.in_(run_ids))
    ).mappings().all()
    details_by_id = {str(row["id"]): row for row in detail_rows}

    summaries: list[dict[str, Any]] = []
    for header in header_rows:
        run_id = str(header["id"])
        detail = details_by_id.get(run_id)
        if detail is None:
            continue
        summaries.append(
            {
                "id": run_id,
                "run_at": _history_text(header["run_at"]),
                "finished_at": _history_text(header["finished_at"]),
                "run_date": _history_text(header["run_date"]),
                "report_date": _history_text(detail["report_date"]),
                "status": _text(header["status"]),
                "executor_id": _text(header["executor_id"]),
                "executor_username": _text(header["executor_username"]),
                "executor_name": _text(header["executor_name"]),
                "result_count": int(detail["result_count"] or 0),
                "warning_count": int(detail["warning_count"] or 0),
                "table_count": int(detail["table_count"] or 0),
                "enable_public_info_check": bool(detail["enable_public_info_check"]),
                "enable_template_check": bool(detail["enable_template_check"]),
                "download_url": _text(detail["download_url"]),
            }
        )
    return summaries


def get_db_validation_run(connection: Connection, run_id: str) -> dict[str, Any] | None:
    return _get_kind_run(connection, "db_validation", run_id)


def get_db_validation_download_metadata(connection: Connection, run_id: str) -> dict[str, str] | None:
    row = connection.execute(
        select(DB_VALIDATION_RUNS.c.excel_path, DB_VALIDATION_RUNS.c.excel_filename).where(
            DB_VALIDATION_RUNS.c.id == str(run_id)
        )
    ).mappings().first()
    if row is None:
        return None
    return {
        "excel_path": _text(row["excel_path"]),
        "excel_filename": _text(row["excel_filename"]),
    }


def delete_db_validation_run(connection: Connection, run_id: str) -> bool:
    return _delete_kind_run(connection, "db_validation", run_id)


def save_flow_chain_run(connection: Connection, run: dict[str, Any]) -> None:
    run_id = _required_run_id(run)
    _upsert_run_header(connection, "flow_chain", run)
    _execute_upsert(
        connection,
        FLOW_CHAIN_RUNS,
        {
            "id": run_id,
            "chain_id": _text(run.get("chain_id")),
            "chain_name": _text(run.get("chain_name")),
            "is_multi_chain": bool(run.get("is_multi_chain")),
            "trigger_type": _text(run.get("trigger_type")),
            "executor_name": _text(run.get("executor_name")),
            "status": _text(run.get("status")),
            "error": _text(run.get("error")),
            "step_count": _optional_int(run.get("step_count")) or len(_list(run.get("steps"))),
            "duration_seconds": _optional_int(run.get("duration_seconds")) or 0,
        },
    )
    _replace_flow_chain_children(connection, run_id, run)


def list_flow_chain_runs(connection: Connection) -> list[dict[str, Any]]:
    return _list_kind_runs(connection, "flow_chain", RUN_HEADERS.c.run_at.desc(), RUN_HEADERS.c.id.desc())


def get_flow_chain_run(connection: Connection, run_id: str) -> dict[str, Any] | None:
    return _get_kind_run(connection, "flow_chain", run_id)


def delete_flow_chain_run(connection: Connection, run_id: str) -> bool:
    return _delete_kind_run(connection, "flow_chain", run_id)


def count_kind_runs(connection: Connection, kind: str) -> int:
    value = connection.execute(
        select(func.count()).select_from(RUN_HEADERS).where(RUN_HEADERS.c.kind == str(kind))
    ).scalar_one()
    return int(value or 0)


def _upsert_run_header(connection: Connection, kind: str, run: dict[str, Any]) -> None:
    _execute_upsert(
        connection,
        RUN_HEADERS,
        {
            "id": _required_run_id(run),
            "kind": kind,
            "run_date": _optional_date(run.get("run_date") or run.get("report_date")),
            "run_at": _optional_datetime(run.get("run_at") or run.get("started_at")),
            "finished_at": _optional_datetime(run.get("finished_at")),
            "status": _text(run.get("status")),
            "executor_id": _text(run.get("executor_id")),
            "executor_username": _text(run.get("executor_username")),
            "executor_name": _text(run.get("executor_name")),
            "config_fingerprint": _text(run.get("config_fingerprint")),
            "payload_json": _json(run),
        },
    )


def _execute_upsert(connection: Connection, table: Table, values: dict[str, Any]) -> None:
    statement = mysql_insert(table).values(**values)
    update_values = {
        column.name: getattr(statement.inserted, column.name)
        for column in table.columns
        if not column.primary_key
    }
    connection.execute(statement.on_duplicate_key_update(**update_values))


def _list_kind_runs(connection: Connection, kind: str, *order_by: Any) -> list[dict[str, Any]]:
    rows = connection.execute(
        select(RUN_HEADERS.c.payload_json).where(RUN_HEADERS.c.kind == str(kind)).order_by(*order_by)
    ).mappings().all()
    return [_parse_payload(row["payload_json"]) for row in rows]


def _get_kind_run(connection: Connection, kind: str, run_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        select(RUN_HEADERS.c.payload_json).where(
            RUN_HEADERS.c.kind == str(kind),
            RUN_HEADERS.c.id == str(run_id),
        )
    ).mappings().first()
    if row is None:
        return None
    return _parse_payload(row["payload_json"])


def _delete_kind_run(connection: Connection, kind: str, run_id: str) -> bool:
    run_id = str(run_id)
    _delete_children(connection, run_id)
    result = connection.execute(
        delete(RUN_HEADERS).where(RUN_HEADERS.c.kind == str(kind), RUN_HEADERS.c.id == run_id)
    )
    return bool(getattr(result, "rowcount", 0))


def _delete_children(connection: Connection, run_id: str) -> None:
    _delete_reconcile_children(connection, run_id)
    for table in (
        DB_VALIDATION_SELECTED_TABLES,
        DB_VALIDATION_WARNINGS,
        DB_VALIDATION_RESULT_ROWS,
        FLOW_CHAIN_RUN_STEPS,
        FLOW_CHAIN_RUN_LOGS,
        FLOW_CHAIN_RUN_DETAILS,
    ):
        connection.execute(delete(table).where(table.c.run_id == str(run_id)))
    for table in (RECONCILE_RUNS, DB_VALIDATION_RUNS, FLOW_CHAIN_RUNS):
        connection.execute(delete(table).where(table.c.id == str(run_id)))


def _delete_reconcile_children(connection: Connection, run_id: str) -> None:
    result_ids = [
        row["id"]
        for row in connection.execute(
            select(RECONCILE_RESULTS.c.id).where(RECONCILE_RESULTS.c.run_id == str(run_id))
        ).mappings().all()
    ]
    if result_ids:
        connection.execute(delete(RECONCILE_RESULT_DETAILS).where(RECONCILE_RESULT_DETAILS.c.result_id.in_(result_ids)))
    for table in (
        RECONCILE_RUN_COUNTS,
        RECONCILE_DELTA_RESULTS,
        RECONCILE_RESULTS,
    ):
        connection.execute(delete(table).where(table.c.run_id == str(run_id)))


def _replace_reconcile_children(connection: Connection, run_id: str, run: dict[str, Any]) -> None:
    _delete_reconcile_children(connection, run_id)
    for label, count in _count_items(run.get("status_counts")).items():
        _insert_count(connection, run_id, "status", label, count)
    for label, count in _count_items(run.get("reason_counts")).items():
        _insert_count(connection, run_id, "reason", label, count)
    for index, result in enumerate(_dict_list(run.get("results"))):
        _insert_reconcile_result(connection, run_id, index, result)
    for index, result in enumerate(_dict_list(run.get("added_results"))):
        _insert_delta_result(connection, run_id, "added", index, result)
    for index, result in enumerate(_dict_list(run.get("removed_results"))):
        _insert_delta_result(connection, run_id, "removed", index, result)


def _insert_count(connection: Connection, run_id: str, count_type: str, label: str, count: int) -> None:
    connection.execute(
        mysql_insert(RECONCILE_RUN_COUNTS).values(
            run_id=run_id,
            count_type=count_type,
            label=label,
            count_value=int(count),
        )
    )


def _insert_reconcile_result(connection: Connection, run_id: str, result_order: int, result: dict[str, Any]) -> None:
    insert_result = connection.execute(
        mysql_insert(RECONCILE_RESULTS).values(
            run_id=run_id,
            result_order=result_order,
            project_code=_text(result.get("project_code")),
            project_name=_text(result.get("project_name")),
            asset_total=_optional_decimal(result.get("asset_total")),
            liability_equity_total=_optional_decimal(result.get("liability_equity_total")),
            received_trust_balance=_optional_decimal(result.get("received_trust_balance")),
            difference=_optional_decimal(result.get("difference")),
            direction=_text(result.get("direction")),
            difference_reason=_text(result.get("difference_reason")),
            match_status=_text(result.get("match_status")),
            valuation_asset_total=_optional_decimal(result.get("valuation_asset_total")),
            payload_json=_json(result),
        )
    )
    result_id = _inserted_id(insert_result)
    for detail_order, detail in enumerate(_dict_list(result.get("details"))):
        data = detail.get("data") if isinstance(detail.get("data"), dict) else {}
        specific_reason = _text(data.get("specific_reason") or detail.get("specific_reason"))
        connection.execute(
            mysql_insert(RECONCILE_RESULT_DETAILS).values(
                result_id=result_id,
                detail_order=detail_order,
                kind=_text(detail.get("kind")),
                specific_reason=specific_reason,
                data_json=_json(data),
            )
        )


def _insert_delta_result(connection: Connection, run_id: str, delta_type: str, result_order: int, result: dict[str, Any]) -> None:
    connection.execute(
        mysql_insert(RECONCILE_DELTA_RESULTS).values(
            run_id=run_id,
            delta_type=delta_type,
            result_order=result_order,
            payload_json=_json(result),
        )
    )


def _replace_db_validation_children(connection: Connection, run_id: str, run: dict[str, Any]) -> None:
    for table in (DB_VALIDATION_SELECTED_TABLES, DB_VALIDATION_WARNINGS, DB_VALIDATION_RESULT_ROWS):
        connection.execute(delete(table).where(table.c.run_id == run_id))
    for index, table_code in enumerate(_list(run.get("selected_tables"))):
        connection.execute(
            mysql_insert(DB_VALIDATION_SELECTED_TABLES).values(
                run_id=run_id,
                table_order=index,
                table_code=_text(table_code),
            )
        )
    for index, message in enumerate(_list(run.get("warnings"))):
        connection.execute(
            mysql_insert(DB_VALIDATION_WARNINGS).values(
                run_id=run_id,
                warning_order=index,
                message=_text(message),
            )
        )
    for index, row in enumerate(_dict_list(run.get("rows"))):
        connection.execute(
            mysql_insert(DB_VALIDATION_RESULT_ROWS).values(
                run_id=run_id,
                row_order=index,
                table_code=_text(row.get("table_code") or row.get("table")),
                rule_id=_text(row.get("rule_id") or row.get("rule")),
                severity=_text(row.get("severity") or row.get("level")),
                message=_text(row.get("message")),
                detail=_text(row.get("detail")),
                payload_json=_json(row),
            )
        )


def _replace_flow_chain_children(connection: Connection, run_id: str, run: dict[str, Any]) -> None:
    for table in (FLOW_CHAIN_RUN_STEPS, FLOW_CHAIN_RUN_LOGS, FLOW_CHAIN_RUN_DETAILS):
        connection.execute(delete(table).where(table.c.run_id == run_id))
    for index, step in enumerate(_dict_list(run.get("steps"))):
        connection.execute(
            mysql_insert(FLOW_CHAIN_RUN_STEPS).values(
                run_id=run_id,
                step_order=index,
                flow_id=_text(step.get("flow_id")),
                name=_text(step.get("name") or step.get("flow_name")),
                status=_text(step.get("status")),
                sp_task_id=_text(step.get("sp_task_id")),
                start_time=_optional_datetime(step.get("start_time") or step.get("begin_time")),
                end_time=_optional_datetime(step.get("end_time") or step.get("finished_at")),
                duration_seconds=_optional_int(step.get("duration_seconds")),
                payload_json=_json(step),
            )
        )
    for index, log in enumerate(_dict_list(run.get("logs"))):
        connection.execute(
            mysql_insert(FLOW_CHAIN_RUN_LOGS).values(
                run_id=run_id,
                log_order=index,
                log_time=_optional_time(log.get("time") or log.get("log_time") or log.get("created_at")),
                message=_text(log.get("message")),
                progress=_optional_int(log.get("progress")),
                step=_text(log.get("step")),
                payload_json=_json(log),
            )
        )
    for index, detail in enumerate(_dict_list(run.get("chain_details"))):
        connection.execute(
            mysql_insert(FLOW_CHAIN_RUN_DETAILS).values(
                run_id=run_id,
                chain_order=index,
                chain_name=_text(detail.get("chain_name")),
                status=_text(detail.get("status")),
                step_count=_optional_int(detail.get("step_count")) or 0,
                duration_seconds=_optional_int(detail.get("duration_seconds")) or 0,
                error=_text(detail.get("error")),
                payload_json=_json(detail),
            )
        )


def _inserted_id(result: Any) -> int:
    primary_key = getattr(result, "inserted_primary_key", None)
    if primary_key:
        return int(primary_key[0])
    return int(getattr(result, "lastrowid"))


def _count_items(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for label, count in value.items():
        parsed = _optional_int(count)
        counts[_text(label)] = parsed if parsed is not None else 0
    return counts


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _parse_payload(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return Decimal(str(value))


def _optional_date(value: Any) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def _optional_datetime(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("T", " ")
    if len(text) == 10:
        text += " 00:00:00"
    return datetime.fromisoformat(text).replace(tzinfo=None)


def _optional_time(value: Any) -> time | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.time().replace(tzinfo=None)
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("T", " ")
    if " " in text:
        text = text.rsplit(" ", 1)[1]
    return time.fromisoformat(text).replace(tzinfo=None)


def _required_run_id(run: dict[str, Any]) -> str:
    run_id = _text(run.get("id"))
    if not run_id:
        raise ValueError("history run id is required")
    return run_id


def _text(value: Any) -> str:
    return str(value or "")


def _history_text(value: Any) -> str:
    if isinstance(value, datetime):
        timespec = "microseconds" if value.microsecond else "seconds"
        return value.isoformat(sep=" ", timespec=timespec)
    if isinstance(value, (date, time)):
        return value.isoformat()
    return _text(value)


def _json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
