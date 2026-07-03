from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from auto_check.app.storage_schema import fingerprint_text, migration_completed, record_migration


def save_reconcile_run(connection: sqlite3.Connection, run: dict[str, Any]) -> None:
    run_id = str(run.get("id", "") or "")
    if not run_id:
        raise ValueError("history run id is required")

    connection.execute(
        """
        INSERT INTO run_headers(
            id, kind, run_date, run_at, finished_at, status,
            executor_id, executor_username, executor_name,
            config_fingerprint, payload_json
        )
        VALUES (?, 'reconcile', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            kind = excluded.kind,
            run_date = excluded.run_date,
            run_at = excluded.run_at,
            finished_at = excluded.finished_at,
            status = excluded.status,
            executor_id = excluded.executor_id,
            executor_username = excluded.executor_username,
            executor_name = excluded.executor_name,
            config_fingerprint = excluded.config_fingerprint,
            payload_json = excluded.payload_json
        """,
        (
            run_id,
            _text(run.get("run_date")),
            _text(run.get("run_at")),
            _text(run.get("finished_at")),
            _text(run.get("status")),
            _text(run.get("executor_id")),
            _text(run.get("executor_username")),
            _text(run.get("executor_name")),
            _text(run.get("config_fingerprint")),
            _json(run),
        ),
    )
    connection.execute(
        """
        INSERT INTO reconcile_runs(
            id, config_name, dws_source_name, rule_version,
            baseline_id, baseline_run_at, baseline_count,
            total_count, added_count, removed_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            config_name = excluded.config_name,
            dws_source_name = excluded.dws_source_name,
            rule_version = excluded.rule_version,
            baseline_id = excluded.baseline_id,
            baseline_run_at = excluded.baseline_run_at,
            baseline_count = excluded.baseline_count,
            total_count = excluded.total_count,
            added_count = excluded.added_count,
            removed_count = excluded.removed_count
        """,
        (
            run_id,
            _text(run.get("config_name")),
            _text(run.get("dws_source_name")),
            _text(run.get("rule_version")),
            _text(run.get("baseline_id")),
            _text(run.get("baseline_run_at")),
            _optional_int(run.get("baseline_count")),
            _optional_int(run.get("total_count")) or 0,
            _optional_int(run.get("added_count")),
            _optional_int(run.get("removed_count")),
        ),
    )
    _replace_reconcile_children(connection, run_id, run)


def list_reconcile_runs(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT payload_json
        FROM run_headers
        WHERE kind = 'reconcile'
        ORDER BY run_date DESC, run_at DESC
        """
    ).fetchall()
    return [_parse_payload(row["payload_json"]) for row in rows]


def get_reconcile_run(connection: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT payload_json FROM run_headers WHERE kind = 'reconcile' AND id = ?",
        (str(run_id),),
    ).fetchone()
    if row is None:
        return None
    return _parse_payload(row["payload_json"])


def delete_reconcile_run(connection: sqlite3.Connection, run_id: str) -> bool:
    cursor = connection.execute(
        "DELETE FROM run_headers WHERE kind = 'reconcile' AND id = ?",
        (str(run_id),),
    )
    return cursor.rowcount > 0


def save_db_validation_run(connection: sqlite3.Connection, run: dict[str, Any]) -> None:
    run_id = _required_run_id(run)
    _upsert_run_header(connection, "db_validation", run)
    connection.execute(
        """
        INSERT INTO db_validation_runs(
            id, report_date, result_count, warning_count, table_count,
            enable_public_info_check, enable_template_check,
            excel_filename, excel_path, download_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            report_date = excluded.report_date,
            result_count = excluded.result_count,
            warning_count = excluded.warning_count,
            table_count = excluded.table_count,
            enable_public_info_check = excluded.enable_public_info_check,
            enable_template_check = excluded.enable_template_check,
            excel_filename = excluded.excel_filename,
            excel_path = excluded.excel_path,
            download_url = excluded.download_url
        """,
        (
            run_id,
            _text(run.get("report_date") or run.get("run_date")),
            _optional_int(run.get("result_count")) or 0,
            _optional_int(run.get("warning_count")) or len(_list(run.get("warnings"))),
            _optional_int(run.get("table_count")) or len(_list(run.get("selected_tables"))),
            1 if bool(run.get("enable_public_info_check")) else 0,
            1 if bool(run.get("enable_template_check")) else 0,
            _text(run.get("excel_filename")),
            _text(run.get("excel_path")),
            _text(run.get("download_url")),
        ),
    )
    _replace_db_validation_children(connection, run_id, run)


def list_db_validation_runs(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT payload_json
        FROM run_headers
        WHERE kind = 'db_validation'
        ORDER BY run_at DESC, id DESC
        """
    ).fetchall()
    return [_parse_payload(row["payload_json"]) for row in rows]


def get_db_validation_run(connection: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    return _get_kind_run(connection, "db_validation", run_id)


def delete_db_validation_run(connection: sqlite3.Connection, run_id: str) -> bool:
    return _delete_kind_run(connection, "db_validation", run_id)


def save_flow_chain_run(connection: sqlite3.Connection, run: dict[str, Any]) -> None:
    run_id = _required_run_id(run)
    _upsert_run_header(connection, "flow_chain", run)
    connection.execute(
        """
        INSERT INTO flow_chain_runs(
            id, chain_id, chain_name, is_multi_chain, trigger_type,
            executor_name, status, error, step_count, duration_seconds
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            chain_id = excluded.chain_id,
            chain_name = excluded.chain_name,
            is_multi_chain = excluded.is_multi_chain,
            trigger_type = excluded.trigger_type,
            executor_name = excluded.executor_name,
            status = excluded.status,
            error = excluded.error,
            step_count = excluded.step_count,
            duration_seconds = excluded.duration_seconds
        """,
        (
            run_id,
            _text(run.get("chain_id")),
            _text(run.get("chain_name")),
            1 if bool(run.get("is_multi_chain")) else 0,
            _text(run.get("trigger_type")),
            _text(run.get("executor_name")),
            _text(run.get("status")),
            _text(run.get("error")),
            _optional_int(run.get("step_count")) or len(_list(run.get("steps"))),
            _optional_int(run.get("duration_seconds")) or 0,
        ),
    )
    _replace_flow_chain_children(connection, run_id, run)


def list_flow_chain_runs(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT payload_json
        FROM run_headers
        WHERE kind = 'flow_chain'
        ORDER BY run_at DESC, id DESC
        """
    ).fetchall()
    return [_parse_payload(row["payload_json"]) for row in rows]


def get_flow_chain_run(connection: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    return _get_kind_run(connection, "flow_chain", run_id)


def delete_flow_chain_run(connection: sqlite3.Connection, run_id: str) -> bool:
    return _delete_kind_run(connection, "flow_chain", run_id)


def has_reconcile_runs(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT COUNT(*) FROM run_headers WHERE kind = 'reconcile'"
    ).fetchone()
    return int(row[0]) > 0


def migrate_legacy_reconcile_runs(connection: sqlite3.Connection, config_path: str | Path) -> int:
    rows = connection.execute(
        """
        SELECT id, payload
        FROM history_runs
        WHERE kind = 'reconcile'
        ORDER BY run_date DESC, run_at DESC
        """
    ).fetchall()
    if not rows:
        return 0
    source_text = "\n".join(str(row["payload"] or "") for row in rows)
    source_fingerprint = fingerprint_text(source_text)
    source_path = str(Path(config_path).with_name("auto-check.db"))
    if migration_completed(connection, "history_runs", source_path, "reconcile", source_fingerprint):
        return 0

    migrated_count = 0
    skipped_count = 0
    for row in rows:
        run = _parse_payload(row["payload"])
        run_id = _text(run.get("id") or row["id"])
        if not run_id:
            skipped_count += 1
            continue
        run["id"] = run_id
        if _reconcile_run_exists(connection, run_id):
            skipped_count += 1
            continue
        save_reconcile_run(connection, run)
        migrated_count += 1

    record_migration(
        connection,
        source_type="history_runs",
        source_path=source_path,
        source_key="reconcile",
        source_fingerprint=source_fingerprint,
        migrated_count=migrated_count,
        skipped_count=skipped_count,
        status="completed",
    )
    return migrated_count


def migrate_legacy_db_validation_runs(connection: sqlite3.Connection, config_path: str | Path) -> int:
    rows = connection.execute(
        """
        SELECT id, payload
        FROM history_runs
        WHERE kind = 'db_validation'
        ORDER BY run_date DESC, run_at DESC
        """
    ).fetchall()
    if not rows:
        return 0
    source_text = "\n".join(str(row["payload"] or "") for row in rows)
    source_fingerprint = fingerprint_text(source_text)
    source_path = str(Path(config_path).with_name("auto-check.db"))
    if migration_completed(connection, "history_runs", source_path, "db_validation", source_fingerprint):
        return 0

    migrated_count = 0
    skipped_count = 0
    for row in rows:
        run = _parse_payload(row["payload"])
        run_id = _text(run.get("id") or row["id"])
        if not run_id:
            skipped_count += 1
            continue
        run["id"] = run_id
        if _kind_run_exists(connection, "db_validation", run_id):
            skipped_count += 1
            continue
        save_db_validation_run(connection, run)
        migrated_count += 1

    record_migration(
        connection,
        source_type="history_runs",
        source_path=source_path,
        source_key="db_validation",
        source_fingerprint=source_fingerprint,
        migrated_count=migrated_count,
        skipped_count=skipped_count,
        status="completed",
    )
    return migrated_count


def migrate_legacy_flow_chain_runs(connection: sqlite3.Connection, config_path: str | Path) -> int:
    rows = connection.execute(
        """
        SELECT id, payload
        FROM history_runs
        WHERE kind = 'flow_chain'
        ORDER BY run_date DESC, run_at DESC
        """
    ).fetchall()
    if not rows:
        return 0
    source_text = "\n".join(str(row["payload"] or "") for row in rows)
    source_fingerprint = fingerprint_text(source_text)
    source_path = str(Path(config_path).with_name("auto-check.db"))
    if migration_completed(connection, "history_runs", source_path, "flow_chain", source_fingerprint):
        return 0

    migrated_count = 0
    skipped_count = 0
    for row in rows:
        run = _parse_payload(row["payload"])
        run_id = _text(run.get("id") or row["id"])
        if not run_id:
            skipped_count += 1
            continue
        run["id"] = run_id
        if _kind_run_exists(connection, "flow_chain", run_id):
            skipped_count += 1
            continue
        save_flow_chain_run(connection, run)
        migrated_count += 1

    record_migration(
        connection,
        source_type="history_runs",
        source_path=source_path,
        source_key="flow_chain",
        source_fingerprint=source_fingerprint,
        migrated_count=migrated_count,
        skipped_count=skipped_count,
        status="completed",
    )
    return migrated_count


def migrate_reconcile_history_json(connection: sqlite3.Connection, config_path: str | Path) -> int:
    path = Path(config_path).with_name("history.json")
    if not path.exists():
        return 0
    try:
        source_text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    source_fingerprint = fingerprint_text(source_text)
    if migration_completed(connection, "history_json", str(path), "", source_fingerprint):
        return 0

    migrated_count = 0
    skipped_count = 0
    for run in _load_runs_from_text(source_text):
        run_id = _text(run.get("id"))
        if not run_id:
            skipped_count += 1
            continue
        if _reconcile_run_exists(connection, run_id):
            skipped_count += 1
        else:
            save_reconcile_run(connection, run)
            migrated_count += 1
        _insert_legacy_history_run(connection, "reconcile", run)

    record_migration(
        connection,
        source_type="history_json",
        source_path=str(path),
        source_key="",
        source_fingerprint=source_fingerprint,
        migrated_count=migrated_count,
        skipped_count=skipped_count,
        status="completed",
    )
    return migrated_count


def migrate_db_validation_history_json_to_legacy_runs(
    connection: sqlite3.Connection,
    config_path: str | Path,
) -> int:
    path = Path(config_path).with_name("db-validation-history.json")
    if not path.exists():
        return 0
    try:
        source_text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    source_fingerprint = fingerprint_text(source_text)
    if migration_completed(connection, "db_validation_history_json", str(path), "", source_fingerprint):
        return 0

    migrated_count = 0
    skipped_count = 0
    for run in _load_runs_from_text(source_text):
        run_id = _text(run.get("id"))
        if not run_id:
            skipped_count += 1
            continue
        if _kind_run_exists(connection, "db_validation", run_id):
            skipped_count += 1
        else:
            save_db_validation_run(connection, run)
            migrated_count += 1
        _insert_legacy_history_run(connection, "db_validation", run)

    record_migration(
        connection,
        source_type="db_validation_history_json",
        source_path=str(path),
        source_key="",
        source_fingerprint=source_fingerprint,
        migrated_count=migrated_count,
        skipped_count=skipped_count,
        status="completed",
    )
    return migrated_count


def _reconcile_run_exists(connection: sqlite3.Connection, run_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM run_headers WHERE kind = 'reconcile' AND id = ?",
        (str(run_id),),
    ).fetchone()
    return row is not None


def _legacy_history_run_exists(connection: sqlite3.Connection, kind: str, run_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM history_runs WHERE kind = ? AND id = ?",
        (str(kind), str(run_id)),
    ).fetchone()
    return row is not None


def _kind_run_exists(connection: sqlite3.Connection, kind: str, run_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM run_headers WHERE kind = ? AND id = ?",
        (str(kind), str(run_id)),
    ).fetchone()
    return row is not None


def _insert_legacy_history_run(connection: sqlite3.Connection, kind: str, run: dict[str, Any]) -> None:
    run_id = _text(run.get("id"))
    if not run_id:
        return
    connection.execute(
        """
        INSERT INTO history_runs(kind, id, payload, run_date, run_at, config_fingerprint)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(kind, id) DO UPDATE SET
            payload = excluded.payload,
            run_date = excluded.run_date,
            run_at = excluded.run_at,
            config_fingerprint = excluded.config_fingerprint
        """,
        (
            str(kind),
            run_id,
            _json(run),
            _text(run.get("run_date") or run.get("report_date")),
            _text(run.get("run_at")),
            _text(run.get("config_fingerprint")),
        ),
    )


def _upsert_run_header(connection: sqlite3.Connection, kind: str, run: dict[str, Any]) -> None:
    run_id = _required_run_id(run)
    connection.execute(
        """
        INSERT INTO run_headers(
            id, kind, run_date, run_at, finished_at, status,
            executor_id, executor_username, executor_name,
            config_fingerprint, payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            kind = excluded.kind,
            run_date = excluded.run_date,
            run_at = excluded.run_at,
            finished_at = excluded.finished_at,
            status = excluded.status,
            executor_id = excluded.executor_id,
            executor_username = excluded.executor_username,
            executor_name = excluded.executor_name,
            config_fingerprint = excluded.config_fingerprint,
            payload_json = excluded.payload_json
        """,
        (
            run_id,
            kind,
            _text(run.get("run_date") or run.get("report_date")),
            _text(run.get("run_at") or run.get("started_at")),
            _text(run.get("finished_at")),
            _text(run.get("status")),
            _text(run.get("executor_id")),
            _text(run.get("executor_username")),
            _text(run.get("executor_name")),
            _text(run.get("config_fingerprint")),
            _json(run),
        ),
    )


def _get_kind_run(connection: sqlite3.Connection, kind: str, run_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT payload_json FROM run_headers WHERE kind = ? AND id = ?",
        (str(kind), str(run_id)),
    ).fetchone()
    if row is None:
        return None
    return _parse_payload(row["payload_json"])


def _delete_kind_run(connection: sqlite3.Connection, kind: str, run_id: str) -> bool:
    cursor = connection.execute(
        "DELETE FROM run_headers WHERE kind = ? AND id = ?",
        (str(kind), str(run_id)),
    )
    return cursor.rowcount > 0


def _replace_db_validation_children(connection: sqlite3.Connection, run_id: str, run: dict[str, Any]) -> None:
    connection.execute("DELETE FROM db_validation_selected_tables WHERE run_id = ?", (run_id,))
    connection.execute("DELETE FROM db_validation_warnings WHERE run_id = ?", (run_id,))
    connection.execute("DELETE FROM db_validation_result_rows WHERE run_id = ?", (run_id,))

    for index, table_code in enumerate(_list(run.get("selected_tables"))):
        connection.execute(
            """
            INSERT INTO db_validation_selected_tables(run_id, table_order, table_code)
            VALUES (?, ?, ?)
            """,
            (run_id, index, _text(table_code)),
        )
    for index, message in enumerate(_list(run.get("warnings"))):
        connection.execute(
            """
            INSERT INTO db_validation_warnings(run_id, warning_order, message)
            VALUES (?, ?, ?)
            """,
            (run_id, index, _text(message)),
        )
    for index, row in enumerate(_dict_list(run.get("rows"))):
        connection.execute(
            """
            INSERT INTO db_validation_result_rows(
                run_id, row_order, table_code, rule_id, severity,
                message, detail, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                index,
                _text(row.get("table_code") or row.get("table")),
                _text(row.get("rule_id") or row.get("rule")),
                _text(row.get("severity") or row.get("level")),
                _text(row.get("message")),
                _text(row.get("detail")),
                _json(row),
            ),
        )


def _replace_flow_chain_children(connection: sqlite3.Connection, run_id: str, run: dict[str, Any]) -> None:
    connection.execute("DELETE FROM flow_chain_run_steps WHERE run_id = ?", (run_id,))
    connection.execute("DELETE FROM flow_chain_run_logs WHERE run_id = ?", (run_id,))
    connection.execute("DELETE FROM flow_chain_run_details WHERE run_id = ?", (run_id,))

    for index, step in enumerate(_dict_list(run.get("steps"))):
        connection.execute(
            """
            INSERT INTO flow_chain_run_steps(
                run_id, step_order, flow_id, name, status, sp_task_id,
                start_time, end_time, duration_seconds, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                index,
                _text(step.get("flow_id")),
                _text(step.get("name") or step.get("flow_name")),
                _text(step.get("status")),
                _text(step.get("sp_task_id")),
                _text(step.get("start_time") or step.get("begin_time")),
                _text(step.get("end_time") or step.get("finished_at")),
                _optional_int(step.get("duration_seconds")),
                _json(step),
            ),
        )

    for index, log in enumerate(_dict_list(run.get("logs"))):
        connection.execute(
            """
            INSERT INTO flow_chain_run_logs(
                run_id, log_order, log_time, message, progress, step, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                index,
                _text(log.get("time") or log.get("log_time") or log.get("created_at")),
                _text(log.get("message")),
                _optional_int(log.get("progress")),
                _text(log.get("step")),
                _json(log),
            ),
        )

    for index, detail in enumerate(_dict_list(run.get("chain_details"))):
        connection.execute(
            """
            INSERT INTO flow_chain_run_details(
                run_id, chain_order, chain_name, status,
                step_count, duration_seconds, error, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                index,
                _text(detail.get("chain_name")),
                _text(detail.get("status")),
                _optional_int(detail.get("step_count")) or 0,
                _optional_int(detail.get("duration_seconds")) or 0,
                _text(detail.get("error")),
                _json(detail),
            ),
        )


def _load_runs_from_text(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("runs"), list):
        return [item for item in payload["runs"] if isinstance(item, dict)]
    return []


def _replace_reconcile_children(connection: sqlite3.Connection, run_id: str, run: dict[str, Any]) -> None:
    connection.execute("DELETE FROM reconcile_run_counts WHERE run_id = ?", (run_id,))
    connection.execute("DELETE FROM reconcile_delta_results WHERE run_id = ?", (run_id,))
    connection.execute(
        """
        DELETE FROM reconcile_result_details
        WHERE result_id IN (SELECT id FROM reconcile_results WHERE run_id = ?)
        """,
        (run_id,),
    )
    connection.execute("DELETE FROM reconcile_results WHERE run_id = ?", (run_id,))

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


def _insert_count(connection: sqlite3.Connection, run_id: str, count_type: str, label: str, count: int) -> None:
    connection.execute(
        """
        INSERT INTO reconcile_run_counts(run_id, count_type, label, count_value)
        VALUES (?, ?, ?, ?)
        """,
        (run_id, count_type, label, count),
    )


def _insert_reconcile_result(
    connection: sqlite3.Connection,
    run_id: str,
    result_order: int,
    result: dict[str, Any],
) -> None:
    cursor = connection.execute(
        """
        INSERT INTO reconcile_results(
            run_id, result_order, project_code, project_name,
            asset_total, liability_equity_total, received_trust_balance,
            difference, direction, difference_reason, match_status,
            valuation_asset_total, payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            result_order,
            _text(result.get("project_code")),
            _text(result.get("project_name")),
            _text(result.get("asset_total")),
            _text(result.get("liability_equity_total")),
            _text(result.get("received_trust_balance")),
            _text(result.get("difference")),
            _text(result.get("direction")),
            _text(result.get("difference_reason")),
            _text(result.get("match_status")),
            _text(result.get("valuation_asset_total")),
            _json(result),
        ),
    )
    result_id = int(cursor.lastrowid)
    for detail_order, detail in enumerate(_dict_list(result.get("details"))):
        data = detail.get("data") if isinstance(detail.get("data"), dict) else {}
        specific_reason = _text(data.get("specific_reason") or detail.get("specific_reason"))
        connection.execute(
            """
            INSERT INTO reconcile_result_details(
                result_id, detail_order, kind, specific_reason, data_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                result_id,
                detail_order,
                _text(detail.get("kind")),
                specific_reason,
                _json(data),
            ),
        )


def _insert_delta_result(
    connection: sqlite3.Connection,
    run_id: str,
    delta_type: str,
    result_order: int,
    result: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO reconcile_delta_results(run_id, delta_type, result_order, payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (run_id, delta_type, result_order, _json(result)),
    )


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


def _required_run_id(run: dict[str, Any]) -> str:
    run_id = _text(run.get("id"))
    if not run_id:
        raise ValueError("history run id is required")
    return run_id


def _text(value: Any) -> str:
    return str(value or "")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
