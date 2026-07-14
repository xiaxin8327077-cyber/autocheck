from __future__ import annotations

import errno
import json
import mimetypes
import re
import shutil
import socket
import sys
import threading
import uuid
import webbrowser
from calendar import monthrange
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import parse_qsl, quote, urlparse

from auto_check.app.config import (
    AppConfig,
    DataSourceEntry,
    DataSourceConfig,
    FlowChainConfig,
    db_validation_settings_from_dict,
    db_validation_settings_to_dict,
    flow_tool_settings_from_dict,
    flow_tool_settings_to_dict,
    PbcImportToolSettings,
    ReconcileDataSourceSettings,
    default_config,
    default_settings_from_dict,
    default_settings_to_dict,
    NamedConfig,
    config_from_dict,
    config_to_dict,
    default_config_path,
    legacy_source_id,
    load_config,
    load_store,
    reconcile_schema_path_for_config,
    resolve_data_source,
    resolve_data_source_entry,
    save_config,
    save_store,
)
from auto_check.app.app_database import ApplicationDatabase
from auto_check.app.db import DatabaseClient
from auto_check.app.history import (
    HistoryStore,
    JsonHistoryStore,
    SqliteHistoryStore,
    build_history_entry,
    summarize_run,
)
from auto_check.app.history_migration import build_legacy_history_migration_status, migrate_legacy_histories
from auto_check.app.flow_tool import (
    DatabaseFlowGateway,
    FlowChainRunContext,
    FlowChainRunResult,
    flow_chain_result_to_dict,
    run_flow_chain,
)
from auto_check.app.security import AuthManager, AuthSession, sanitize_error_message
from auto_check.app.storage_admin import (
    build_storage_health,
    build_storage_schema_workbook,
    build_storage_table_data_workbook,
    generate_storage_backup,
    get_storage_table_rows,
    get_storage_table_schema,
    list_storage_tables,
)
from auto_check.app.time_utils import beijing_now, beijing_time_text, beijing_timestamp, beijing_today
from auto_check.app.pbc_import import (
    ColumnMapping,
    SUPPORTED_UPLOAD_EXTENSIONS,
    TableColumn,
    TableRef,
    build_column_mappings,
    inspect_import_upload,
    inspect_import_upload_with_target_columns,
    iter_mapped_rows,
    iter_projected_rows,
    mapped_target_columns,
    parse_table_ref,
    projected_columns,
)
from auto_check.app.repositories import AutoCheckRepository, DEFAULT_RECONCILE_TABLES
from auto_check.app.reconcile_schema import (
    ReconcileSchemaSettings,
    ReconcileTableSchema,
    load_reconcile_schema_settings_from_yaml,
    reconcile_schema_settings_from_dict,
    reconcile_schema_settings_to_dict,
    safe_column_name,
)
from auto_check.db_validation.engine import DbValidationEngine
from auto_check.db_validation.field_mapping_cache import FieldMappingCache
from auto_check.db_validation.metadata import FieldMetadataLoader, TableFieldCatalog
from auto_check.db_validation.models import DbValidationRunResult
from auto_check.db_validation.rules_document import build_rules_document
from auto_check.db_validation.tables import ZG_TABLES
from auto_check.engine.models import ReconcileResult
from auto_check.engine.reconcile import NoSourceReportData, ReconcileEngine, RunCancelled


RunnerFactory = Callable[[AppConfig], Any]
ConnectionTester = Callable[[AppConfig], dict[str, dict[str, Any]]]
PbcImportExecutor = Callable[..., int]
PbcTableColumnLoader = Callable[[DataSourceConfig, TableRef], list[TableColumn]]
DbValidationExecutor = Callable[..., DbValidationRunResult]
DbValidationFieldMappingLoader = Callable[..., TableFieldCatalog]
FlowChainExecutor = Callable[..., FlowChainRunResult]
PasswordDecryptor = Callable[[str], str]
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 512 * 1024 * 1024
DEFAULT_SERVER_PORT = 8765


_RECONCILE_FIELD_LABELS: dict[str, dict[str, str]] = {
    "zf_detail": {
        "check_date": "核对日期",
        "project_code": "项目内码",
        "project_name": "项目名称",
        "asset_total": "资产总计",
        "liability_equity_total": "负债和权益总计",
        "received_trust_balance": "实收信托余额",
    },
    "fa_account_balance": {
        "project_code": "项目代码",
        "balance_date": "余额日期",
        "account_code": "科目代码",
        "account_name": "科目名称",
        "balance": "余额",
    },
    "fa_valuation": {
        "project_code": "项目代码",
        "valuation_date": "估值日期",
        "account_code": "科目代码",
        "account_name": "科目名称",
        "market_value": "市值/余额",
    },
    "am_pact_asset": {
        "project_code": "项目代码",
        "close_date": "截止日期",
        "asset_name": "标的名称",
        "stock_code": "标的代码",
        "pact_id": "合同编号",
        "spv_type": "SPV 类型",
        "asset_type": "标的类型",
        "data_source": "合同来源",
    },
    "am_project_invest": {
        "project_code": "项目代码",
        "close_date": "截止日期",
        "pact_id": "合同编号",
        "invest_balance": "投资余额",
        "contract_start_date": "合同开始日",
    },
    "ta_pact_detail": {
        "project_code": "项目代码",
        "close_date": "截止日期",
        "share_amount": "份额",
        "all_income": "累计收益",
    },
    "ta_survamt_dm": {
        "check_date": "核对日期",
        "project_code": "项目代码",
        "pact_id": "合同编号",
        "client_name": "客户名称",
        "client_kind": "客户类型",
        "client_kind_index": "客户类型序号",
        "spv_type": "SPV 类型",
        "ht_income": "衡泰收益",
        "share_amount": "份额",
    },
    "fa_security_balance_dm": {
        "project_code": "项目代码",
        "check_date": "核对日期",
        "stock_code": "证券代码",
        "security_name": "证券名称",
        "bond_category": "债券分类",
        "stock_equity_category": "股票/股权分类",
        "fund_type": "基金类型",
        "balance_cost": "成本余额",
        "balance_fair": "公允价值余额",
        "balance_interest": "利息余额",
    },
    "dm_project_invest": {
        "project_code": "项目代码",
        "close_date": "截止日期",
        "pact_id": "合同编号",
        "invest_balance": "投资余额",
        "equity_invest_type": "股权投资类型",
    },
    "dm_spv_project_invest": {
        "project_code": "项目代码",
        "close_date": "截止日期",
        "pact_id": "合同编号",
        "asset_type": "资产类型",
        "balance_cost": "成本余额",
        "balance_interest": "利息余额",
        "balance_fair": "公允价值余额",
    },
    "property_right_contract": {
        "project_code": "项目代码",
        "pact_id": "合同编号",
        "invest_balance": "投资余额",
    },
    "pledge_back": {
        "project_code": "项目代码",
        "subject_code": "科目/标的代码",
        "buyback_money": "回购金额",
        "expenses": "费用",
    },
    "ta_asset_share_duration": {
        "check_date": "核对日期",
        "project_code": "项目代码",
        "asset_share": "资产份额",
    },
}


def _reconcile_table_display_name(logical_key: str, table_schema: ReconcileTableSchema | None = None) -> str:
    if table_schema is not None and table_schema.display_name:
        return table_schema.display_name
    default = DEFAULT_RECONCILE_TABLES.get(logical_key)
    if default and default.display_name:
        return default.display_name
    return logical_key


def _reconcile_field_label(logical_key: str, field_key: str) -> str:
    return _RECONCILE_FIELD_LABELS.get(logical_key, {}).get(field_key, field_key)


class ConflictError(Exception):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload or {}


class ApiRouter:
    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        application_database: ApplicationDatabase,
        history_path: str | Path | None = None,
        history_store: HistoryStore | None = None,
        runner_factory: RunnerFactory | None = None,
        connection_tester: ConnectionTester | None = None,
        pbc_import_executor: PbcImportExecutor | None = None,
        pbc_table_column_loader: PbcTableColumnLoader | None = None,
        db_validation_executor: DbValidationExecutor | None = None,
        db_validation_field_mapping_loader: DbValidationFieldMappingLoader | None = None,
        flow_chain_executor: FlowChainExecutor | None = None,
        start_field_mapping_auto_refresh: bool = False,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
        max_archive_member_bytes: int = MAX_ARCHIVE_MEMBER_BYTES,
    ):
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        self.application_database = application_database
        if history_store is not None:
            self.history_store = history_store
        elif history_path is not None:
            self.history_store = JsonHistoryStore(Path(history_path))
        else:
            self.history_store = SqliteHistoryStore(self.config_path)
        self.db_validation_history_store = SqliteHistoryStore(self.config_path, kind="db_validation")
        self.flow_chain_history_store = SqliteHistoryStore(self.config_path, kind="flow_chain")
        self.runner_factory = runner_factory
        self.connection_tester = connection_tester or test_connections
        self.pbc_import_executor = pbc_import_executor or execute_pbc_import
        self.pbc_table_column_loader = pbc_table_column_loader or load_pbc_table_columns
        self.db_validation_executor = db_validation_executor or execute_db_validation
        self.db_validation_field_mapping_loader = db_validation_field_mapping_loader or load_db_validation_field_mapping
        self.flow_chain_executor = flow_chain_executor or execute_flow_chain
        self._db_validation_field_mapping_cache = FieldMappingCache()
        self._field_mapping_auto_refresh_stop = threading.Event()
        self._field_mapping_auto_refresh_thread: threading.Thread | None = None
        self.transport_password_decryptor: PasswordDecryptor | None = None
        self._run_jobs: dict[str, RunJob] = {}
        self._run_jobs_lock = threading.Lock()
        self._inline_run_active = False
        self._pbc_import_jobs: dict[str, PbcImportJob] = {}
        self._pbc_import_jobs_lock = threading.Lock()
        self._db_validation_jobs: dict[str, DbValidationJob] = {}
        self._db_validation_jobs_lock = threading.Lock()
        self._flow_chain_jobs: dict[str, FlowChainJob] = {}
        self._flow_chain_jobs_lock = threading.Lock()
        self.upload_dir = self.config_path.parent / "pbc-import-uploads"
        self.db_validation_output_dir = self.config_path.parent / "db-validation-results"
        self.max_upload_bytes = max_upload_bytes
        self.max_archive_member_bytes = max_archive_member_bytes
        if start_field_mapping_auto_refresh:
            self._start_db_validation_field_mapping_auto_refresh()

    def handle(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        *,
        current_user: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            if path.startswith("/api/admin/storage"):
                return self._handle_admin_storage(method, path, body, current_user=current_user)

            # ---- Check History ----
            if method == "GET" and path == "/api/history":
                return 200, {"history": [summarize_run(run) for run in self.history_store.list_runs()]}

            if method == "GET" and path.startswith("/api/history/"):
                history_id = path.rsplit("/", 1)[-1]
                run = self.history_store.get_run(history_id)
                if run is None:
                    return 404, {"error": "history not found"}
                return 200, {"history": run}

            if method == "DELETE" and path == "/api/history":
                if str((current_user or {}).get("role", "")) != "admin":
                    return 403, {"error": "admin role required"}
                history_id = str((body or {}).get("id", "")).strip()
                if not history_id:
                    return 400, {"error": "id is required"}
                return 200, {"ok": self.history_store.delete_run(history_id)}

            if method == "GET" and path == "/api/tools/db-validation/history":
                history = sorted(
                    self.db_validation_history_store.list_runs(),
                    key=_db_validation_history_execution_sort_key,
                    reverse=True,
                )
                return 200, {"history": [summarize_run(run) for run in history]}

            if method == "GET" and path == "/api/tools/flow/history":
                history = sorted(
                    self.flow_chain_history_store.list_runs(),
                    key=lambda run: str(run.get("run_at", "")),
                    reverse=True,
                )
                return 200, {"history": [summarize_run(run) for run in history]}

            if method == "GET" and path.startswith("/api/tools/flow/history/"):
                history_id = path.rsplit("/", 1)[-1]
                run = self.flow_chain_history_store.get_run(history_id)
                if run is None:
                    return 404, {"error": "history not found"}
                return 200, {"history": run}

            if method == "GET" and path == "/api/system-info":
                store = load_store(self.config_path, database=self.application_database)
                return 200, {
                    "history_run_count": _history_run_count(self.history_store),
                    "config_count": len(store.data_sources),
                    "settings": default_settings_to_dict(store.default_settings),
                }

            # ---- Default Settings ----
            if method == "GET" and path == "/api/settings/defaults":
                store = load_store(self.config_path, database=self.application_database)
                return 200, {
                    "settings": default_settings_to_dict(store.default_settings),
                    "api_default_run_date": previous_month_end(),
                }

            if method == "POST" and path == "/api/settings/defaults":
                store = load_store(self.config_path, database=self.application_database)
                store.default_settings = default_settings_from_dict(body or {})
                save_store(store, self.config_path, database=self.application_database)
                return 200, {"settings": default_settings_to_dict(store.default_settings)}

            # ---- Config Store ----
            if method == "GET" and path == "/api/configs":
                store = load_store(self.config_path, database=self.application_database)
                data_sources = sorted(store.data_sources, key=lambda c: (0 if c.is_default else 1, c.name))
                default_source = next((entry for entry in data_sources if entry.is_default), data_sources[0] if data_sources else None)
                return 200, {
                    "data_sources": [_public_data_source_entry(entry) for entry in data_sources],
                    "default_source_id": default_source.id if default_source else "",
                }

            if method == "GET" and path == "/api/configs/export":
                store = load_store(self.config_path, database=self.application_database)
                return 200, {
                    "data_sources": [_public_data_source_entry(entry) for entry in store.data_sources],
                    "reconcile_data_sources": asdict(store.reconcile_data_sources),
                    "default_settings": default_settings_to_dict(store.default_settings),
                    "pbc_import_tool": asdict(store.pbc_import_tool),
                    "db_validation": db_validation_settings_to_dict(store.db_validation),
                    "reconcile_schema": reconcile_schema_settings_to_dict(store.reconcile_schema),
                }

            if method == "POST" and path == "/api/configs":
                name = str((body or {}).get("name", "")).strip()
                if not name:
                    return 400, {"error": "name is required"}
                store = load_store(self.config_path, database=self.application_database)
                if "dws" in (body or {}) and "business" in (body or {}):
                    _save_legacy_grouped_config(store, body or {}, decrypt_password=self.transport_password_decryptor)
                    save_store(store, self.config_path, database=self.application_database)
                    return 200, {"ok": True}

                editing_id = str((body or {}).get("editing_id", "") or "").strip()
                source_id = editing_id or str((body or {}).get("id", "") or "").strip() or f"source:{uuid.uuid4().hex}"
                existing_entry = next((entry for entry in store.data_sources if entry.id == source_id), None)
                default_val = _coerce_request_bool((body or {}).get("is_default"), default=not store.data_sources)
                data_source = _build_ds(
                    body or {},
                    "postgresql",
                    5432,
                    fallback_password=existing_entry.config.password if existing_entry else "",
                    decrypt_password=self.transport_password_decryptor,
                )
                new_entry = DataSourceEntry(id=source_id, name=name, config=data_source, is_default=default_val)
                replaced = False
                for index, entry in enumerate(store.data_sources):
                    if entry.id == source_id:
                        store.data_sources[index] = new_entry
                        replaced = True
                    elif default_val:
                        entry.is_default = False
                if not replaced:
                    store.data_sources.append(new_entry)
                if not any(entry.is_default for entry in store.data_sources) and store.data_sources:
                    store.data_sources[0].is_default = True
                save_store(store, self.config_path, database=self.application_database)
                return 200, {"ok": True}

            if method == "DELETE" and path == "/api/configs":
                source_id = str((body or {}).get("id", "") or "").strip()
                name = str((body or {}).get("name", "") or "").strip()
                if not source_id and not name:
                    return 400, {"error": "id is required"}
                store = load_store(self.config_path, database=self.application_database)
                delete_ids = {source_id} if source_id else {entry.id for entry in store.data_sources if entry.name == name}
                referenced = _referenced_data_source_labels(store, delete_ids)
                if referenced:
                    return 400, {"error": f"数据源正在被使用：{', '.join(referenced)}"}
                store.data_sources = [entry for entry in store.data_sources if entry.id not in delete_ids]
                if store.data_sources and not any(entry.is_default for entry in store.data_sources):
                    store.data_sources[0].is_default = True
                save_store(store, self.config_path, database=self.application_database)
                return 200, {"ok": True}

            if method == "POST" and path == "/api/configs/default":
                source_id = str((body or {}).get("id", "") or "").strip()
                if not source_id:
                    return 400, {"error": "id is required"}
                store = load_store(self.config_path, database=self.application_database)
                found = False
                for entry in store.data_sources:
                    if entry.id == source_id:
                        found = True
                    entry.is_default = entry.id == source_id
                if not found:
                    return 404, {"error": "data source not found"}
                save_store(store, self.config_path, database=self.application_database)
                return 200, {"ok": True}

            if method == "GET" and path == "/api/settings/reconcile-data-sources":
                store = load_store(self.config_path, database=self.application_database)
                return 200, {
                    "settings": asdict(store.reconcile_data_sources),
                    "data_sources": [_public_data_source_entry(entry) for entry in store.data_sources],
                }

            if method == "POST" and path == "/api/settings/reconcile-data-sources":
                store = load_store(self.config_path, database=self.application_database)
                settings = ReconcileDataSourceSettings(
                    dws_source_id=str((body or {}).get("dws_source_id", "") or "").strip(),
                    business_source_id=str((body or {}).get("business_source_id", "") or "").strip(),
                )
                resolve_data_source(store, settings.dws_source_id)
                resolve_data_source(store, settings.business_source_id)
                store.reconcile_data_sources = settings
                save_store(store, self.config_path, database=self.application_database)
                return 200, {"settings": asdict(settings)}

            if method == "GET" and path == "/api/settings/reconcile-schema":
                store = load_store(self.config_path, database=self.application_database)
                return 200, {
                    "schema": reconcile_schema_settings_to_dict(store.reconcile_schema),
                    "schema_file_path": str(reconcile_schema_path_for_config(self.config_path)),
                    "data_sources": [_public_data_source_entry(entry) for entry in store.data_sources],
                }

            if method == "POST" and path == "/api/settings/reconcile-schema":
                store = load_store(self.config_path, database=self.application_database)
                schema_payload = (body or {}).get("schema") if isinstance((body or {}).get("schema"), dict) else (body or {})
                schema = reconcile_schema_settings_from_dict(schema_payload)
                self._validate_reconcile_schema_settings(store, schema)
                store.reconcile_schema = ReconcileSchemaSettings(
                    version=schema.version,
                    tables=schema.tables,
                    strict=True,
                )
                save_store(store, self.config_path, database=self.application_database)
                return 200, {"schema": reconcile_schema_settings_to_dict(store.reconcile_schema)}

            if method == "POST" and path == "/api/settings/reconcile-schema/init-from-file":
                schema_path = reconcile_schema_path_for_config(self.config_path)
                if not schema_path.exists():
                    return 404, {"error": f"reconcile schema file not found: {schema_path}"}
                store = load_store(self.config_path, database=self.application_database)
                schema = load_reconcile_schema_settings_from_yaml(schema_path)
                self._validate_reconcile_schema_settings(store, schema)
                store.reconcile_schema = schema
                save_store(store, self.config_path, database=self.application_database)
                return 200, {
                    "schema": reconcile_schema_settings_to_dict(store.reconcile_schema),
                    "schema_file_path": str(schema_path),
                }

            if method == "POST" and path == "/api/settings/reconcile-schema/columns":
                return 200, self._load_reconcile_schema_columns(body or {})

            # ---- Tools: PBC full product import ----
            if method == "GET" and path == "/api/tools/pbc-import/settings":
                store = load_store(self.config_path, database=self.application_database)
                return 200, {
                    "settings": asdict(store.pbc_import_tool),
                    "data_sources": _pbc_import_data_sources(store),
                }
            if method == "POST" and path == "/api/tools/pbc-import/start":
                job = self._start_pbc_import_job(body or {})
                return 200, {"job_id": job.id}
            if method == "POST" and path == "/api/tools/pbc-import/columns":
                return 200, self._load_pbc_import_columns(body or {})
            if method == "GET" and path.startswith("/api/tools/pbc-import/status/"):
                job_id = path.rsplit("/", 1)[-1]
                job = self._get_pbc_import_job(job_id)
                if job is None:
                    return 404, {"error": "job not found"}
                return 200, {"job": job.to_payload()}

            # ---- Tools: database validation ----
            if method == "GET" and path == "/api/tools/db-validation/settings":
                store = load_store(self.config_path, database=self.application_database)
                return 200, {
                    "settings": db_validation_settings_to_dict(store.db_validation),
                    "data_sources": [_public_data_source_entry(entry) for entry in store.data_sources],
                    "default_report_date": previous_month_end(),
                    "tables": [{"code": code, "table_name": table} for code, table in ZG_TABLES.items()],
                    "field_mapping": self._db_validation_field_mapping_cache.status_payload(),
                }
            if method == "POST" and path == "/api/tools/db-validation/settings":
                store = load_store(self.config_path, database=self.application_database)
                settings_payload = (body or {}).get("settings") if isinstance((body or {}).get("settings"), dict) else (body or {})
                store.db_validation = db_validation_settings_from_dict(settings_payload)
                save_store(store, self.config_path, database=self.application_database)
                store = load_store(self.config_path, database=self.application_database)
                self._db_validation_field_mapping_cache.invalidate()
                return 200, {
                    "settings": db_validation_settings_to_dict(store.db_validation),
                    "field_mapping": self._db_validation_field_mapping_cache.status_payload(),
                }
            if method == "POST" and path == "/api/tools/db-validation/field-mapping/refresh":
                return 200, {"field_mapping": self._refresh_db_validation_field_mapping(source="manual")}
            if method == "POST" and path == "/api/tools/db-validation/start":
                job = self._start_db_validation_job(body or {}, current_user=current_user)
                return 200, {"job_id": job.id}
            if method == "GET" and path.startswith("/api/tools/db-validation/status/"):
                job_id = path.rsplit("/", 1)[-1]
                job = self._get_db_validation_job(job_id)
                if job is None:
                    return 404, {"error": "job not found"}
                return 200, {"job": job.to_payload()}

            # ---- Tools: flow chain execution ----
            if method == "GET" and path == "/api/tools/flow/settings":
                store = load_store(self.config_path, database=self.application_database)
                return 200, {
                    "settings": flow_tool_settings_to_dict(store.flow_tool),
                    "data_sources": [_public_data_source_entry(entry) for entry in store.data_sources],
                }
            if method == "POST" and path == "/api/tools/flow/settings":
                store = load_store(self.config_path, database=self.application_database)
                flow_settings = flow_tool_settings_from_dict(body or {})
                _validate_flow_tool_settings(store, flow_settings)
                store.flow_tool = flow_settings
                save_store(store, self.config_path, database=self.application_database)
                store = load_store(self.config_path, database=self.application_database)
                return 200, {"settings": flow_tool_settings_to_dict(store.flow_tool)}
            if method == "GET" and path == "/api/tools/flow/definitions":
                query = dict(parse_qsl(getattr(self, "_query_string", "") or ""))
                keyword = (query.get("keyword", "") or "").strip()
                flows = self._load_flow_definitions(keyword)
                flow_limit = 500
                return 200, {"flows": flows, "limit": flow_limit, "truncated": len(flows) >= flow_limit}
            if method == "GET" and path == "/api/flow-chain/status":
                active_job = self.get_active_flow_chain_job_payload()
                return 200, {"job": active_job}
            if method == "POST" and path == "/api/tools/flow/start":
                chain_id = str((body or {}).get("chain_id", "") or "").strip()
                is_multi_chain = bool((body or {}).get("is_multi_chain", False))
                job = self._start_flow_chain_job(chain_id, trigger_type="manual", current_user=current_user, save_history=not is_multi_chain)
                return 200, {"job_id": job.id}
            if method == "GET" and path.startswith("/api/tools/flow/status/"):
                job_id = path.rsplit("/", 1)[-1]
                job = self._get_flow_chain_job(job_id)
                if job is None:
                    return 404, {"error": "job not found"}
                payload = job.to_payload()
                if (
                    payload.get("status") in {"completed", "failed", "cancelled"}
                    and job.save_history
                    and job.thread is not None
                    and job.thread.is_alive()
                ):
                    job.thread.join(timeout=2.0)
                    payload = job.to_payload()
                return 200, {"job": payload}
            if method == "POST" and path == "/api/tools/flow/cancel":
                job_id = str((body or {}).get("job_id") or (body or {}).get("chain_id") or "").strip()
                job = self._get_flow_chain_job(job_id)
                if job is None:
                    return 404, {"error": "job not found"}
                job.cancel()
                return 200, {"ok": True, "job": job.to_payload()}
            if method == "POST" and path == "/api/tools/flow/save-merged-history":
                merged_entry = self._save_merged_flow_chain_history(body or {}, current_user)
                return 200, {"ok": True, "entry": merged_entry}

            # ---- Read-only connection status ----
            if method == "GET" and path == "/api/connection-status":
                config = load_config(self.config_path, database=self.application_database)
                return 200, self.connection_tester(config)

            # ---- Test connection (supports body with dws/business) ----
            if method == "POST" and path == "/api/test-connection":
                if body and "dws" in body:
                    store = load_store(self.config_path, database=self.application_database)
                    editing_name = str(body.get("editing_name", "")).strip()
                    existing_cfg = next((c for c in store.configs if c.name == editing_name), None)
                    dws = _build_ds(
                        body.get("dws", {}),
                        "postgresql",
                        5432,
                        fallback_password=existing_cfg.dws.password if existing_cfg else "",
                        decrypt_password=self.transport_password_decryptor,
                    )
                    biz = _build_ds(
                        body.get("business", {}),
                        "mysql",
                        3306,
                        fallback_password=existing_cfg.business.password if existing_cfg else "",
                        decrypt_password=self.transport_password_decryptor,
                    )
                    config = AppConfig(dws=dws, business=biz)
                elif body and "db_type" in body:
                    store = load_store(self.config_path, database=self.application_database)
                    editing_id = str(body.get("editing_id", "") or body.get("id", "") or "").strip()
                    existing_entry = next((entry for entry in store.data_sources if entry.id == editing_id), None)
                    data_source = _build_ds(
                        body,
                        "postgresql",
                        5432,
                        fallback_password=existing_entry.config.password if existing_entry else "",
                        decrypt_password=self.transport_password_decryptor,
                    )
                    return 200, {"source": _test_one_source(DatabaseClient(data_source))}
                else:
                    config = load_config(self.config_path, database=self.application_database)
                return 200, self.connection_tester(config)

            # ---- Legacy ----
            if method == "GET" and path == "/api/config":
                payload = _public_config(load_config(self.config_path, database=self.application_database))
                payload["default_run_date"] = previous_month_end()
                return 200, payload
            if method == "POST" and path == "/api/config":
                if _contains_plaintext_password(body or {}):
                    return 400, {"error": "encrypted database password is required"}
                config = config_from_dict(body or {})
                save_config(config, self.config_path, database=self.application_database)
                return 200, {"ok": True}
            if method == "POST" and path == "/api/run":
                date = str((body or {}).get("date", "")).strip()
                if not date:
                    return 400, {"error": "date is required"}
                max_combination_rows = _coerce_max_combination_rows((body or {}).get("max_combination_rows"))
                self._begin_inline_run()
                try:
                    results, history = self._run_once(date, max_combination_rows=max_combination_rows, current_user=current_user)
                finally:
                    self._end_inline_run()
                return 200, {"results": results, "history": history}
            if method == "POST" and path == "/api/run/start":
                date = str((body or {}).get("date", "")).strip()
                if not date:
                    return 400, {"error": "date is required"}
                max_combination_rows = _coerce_max_combination_rows((body or {}).get("max_combination_rows"))
                job = self._start_run_job(date, max_combination_rows, current_user=current_user)
                return 200, {"job_id": job.id}
            if method == "GET" and path.startswith("/api/run/status/"):
                job_id = path.rsplit("/", 1)[-1]
                job = self._get_run_job(job_id)
                if job is None:
                    return 404, {"error": "job not found"}
                return 200, {"job": job.to_payload()}
            if method == "POST" and path == "/api/run/cancel":
                job_id = str((body or {}).get("job_id", "")).strip()
                job = self._get_run_job(job_id)
                if job is None:
                    return 404, {"error": "job not found"}
                job.cancel()
                return 200, {"ok": True, "job": job.to_payload()}
            return 404, {"error": "not found"}
        except ConflictError as exc:
            return 409, {"error": str(exc), **exc.payload}
        except ValueError as exc:
            return 400, {"error": str(exc)}
        except Exception as exc:
            return 500, {"error": _runtime_error_message(str(exc))}

    def handle_pbc_import_upload(self, filename: str, data: Any) -> tuple[int, dict[str, Any]]:
        try:
            safe_name = Path(str(filename or "upload")).name
            suffix = Path(safe_name).suffix.lower()
            if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
                return 400, {"error": "supported files: .zip, .rar, .7z, .xlsx, .xls, .csv"}
            data_size = _data_size(data)
            if data_size is not None and data_size > self.max_upload_bytes:
                return 413, {"error": "uploaded file is too large"}
            upload_id = uuid.uuid4().hex
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            target = self.upload_dir / f"{upload_id}{suffix}"
            with target.open("wb") as output:
                if hasattr(data, "read"):
                    shutil.copyfileobj(data, output, length=1024 * 1024)
                else:
                    output.write(data)
            inspection = inspect_import_upload(target, display_name=safe_name, max_member_bytes=self.max_archive_member_bytes)
            return 200, {
                "upload_id": upload_id,
                "filename": safe_name,
                "upload_ext": suffix,
                "columns": inspection.columns,
                "files": [asdict(file) for file in inspection.files],
            }
        except Exception as exc:
            return 400, {"error": _runtime_error_message(str(exc))}

    def _start_pbc_import_job(self, body: dict[str, Any]) -> "PbcImportJob":
        upload_ids = _coerce_string_list(body.get("upload_ids"))
        if not upload_ids:
            upload_id = str(body.get("upload_id", "")).strip()
            if upload_id:
                upload_ids = [upload_id]
        upload_paths = [path for upload_id in upload_ids if (path := self._pbc_import_upload_path(upload_id)) is not None]
        if not upload_paths or len(upload_paths) != len(upload_ids):
            raise ValueError("uploaded file not found")
        store = load_store(self.config_path, database=self.application_database)
        config_name = str(body.get("config_name", "")).strip()
        source = str(body.get("source", "dws") or "dws").strip()
        data_source = _select_pbc_import_source(store, config_name, source)
        target_table = str(body.get("target_table", "")).strip()
        table = parse_table_ref(target_table)
        table_columns = self.pbc_table_column_loader(data_source, table)
        inspection = inspect_import_upload_with_target_columns(
            upload_paths,
            table_columns,
            max_member_bytes=self.max_archive_member_bytes,
        )
        columns = inspection.columns or _coerce_string_list(body.get("columns"))
        if not columns:
            raise ValueError("columns are required")
        drop_columns = _coerce_string_list(body.get("drop_columns"))
        column_order = _coerce_string_list(body.get("column_order"))
        column_mappings = _coerce_column_mappings(body.get("column_mappings"))
        mode = str(body.get("mode", "append") or "append").strip()
        if mode not in {"append", "replace"}:
            raise ValueError("mode must be append or replace")

        _save_pbc_import_preferences(
            self.config_path,
            target_table,
            config_name,
            source,
            database=self.application_database,
        )
        job = PbcImportJob(
            upload_path=upload_paths[0],
            upload_paths=upload_paths,
            data_source=data_source,
            table=table,
            columns=columns,
            drop_columns=drop_columns,
            column_order=column_order,
            column_mappings=column_mappings,
            file_layouts=inspection.files,
            mode=mode,
        )
        with self._pbc_import_jobs_lock:
            if self._has_active_pbc_import_for_table_locked(table):
                raise ConflictError("待插入表正在导入，请等待上一个任务完成后再导入。")
            self._pbc_import_jobs[job.id] = job
        thread = threading.Thread(target=self._execute_pbc_import_job, args=(job,), daemon=True)
        job.thread = thread
        thread.start()
        return job

    def _has_active_pbc_import_for_table_locked(self, table: TableRef) -> bool:
        target_key = _table_ref_key(table)
        for job in self._pbc_import_jobs.values():
            if job.is_active() and _table_ref_key(job.table) == target_key:
                return True
        return False

    def _pbc_import_upload_path(self, upload_id: str) -> Path | None:
        if not re.match(r"^[0-9a-f]{32}$", upload_id):
            return None
        matches = [path for path in self.upload_dir.glob(f"{upload_id}.*") if path.suffix.lower() in SUPPORTED_UPLOAD_EXTENSIONS]
        return matches[0] if matches else None

    def _get_pbc_import_job(self, job_id: str) -> "PbcImportJob | None":
        with self._pbc_import_jobs_lock:
            return self._pbc_import_jobs.get(job_id)

    def _execute_pbc_import_job(self, job: "PbcImportJob") -> None:
        job.start()
        try:
            rows_imported = self.pbc_import_executor(
                zip_path=job.upload_paths,
                data_source=job.data_source,
                table=job.table,
                columns=job.columns,
                drop_columns=job.drop_columns,
                column_order=job.column_order,
                column_mappings=job.column_mappings,
                file_layouts=job.file_layouts,
                mode=job.mode,
                log=job.log,
                cancel_event=job.cancel_event,
            )
            job.complete(rows_imported)
        except Exception as exc:
            job.fail(_runtime_error_message(str(exc)))

    def _load_reconcile_schema_columns(self, body: dict[str, Any]) -> dict[str, Any]:
        store = load_store(self.config_path, database=self.application_database)
        source_id = str(body.get("source_id", "") or "").strip()
        if not source_id:
            raise ValueError("source_id is required")
        table_name = str(body.get("table", "") or "").strip()
        if not table_name:
            raise ValueError("table is required")
        try:
            data_source = resolve_data_source(store, source_id)
        except ValueError as exc:
            raise ValueError("数据源不存在") from exc
        table = parse_table_ref(table_name)
        columns = self.pbc_table_column_loader(data_source, table)
        return {"columns": [asdict(column) for column in columns]}

    def _resolve_reconcile_schema_source(self, store: ConfigStore, source_ref: Any) -> DataSourceEntry:
        source_id = str(getattr(source_ref, "id", "") or "").strip()
        source_name = str(getattr(source_ref, "name", "") or "").strip()
        match_by = str(getattr(source_ref, "match_by", "id_then_name") or "id_then_name").strip()
        candidates = [source_id]
        if match_by != "id_only":
            candidates.append(source_name)
        for candidate in [item for item in candidates if item]:
            for entry in store.data_sources:
                if entry.id == candidate or (match_by != "id_only" and entry.name == candidate):
                    return entry
        raise ValueError(f"数据源不存在：{source_id or source_name}")

    def _validate_reconcile_schema_settings(self, store: ConfigStore, schema: ReconcileSchemaSettings) -> None:
        errors: list[str] = []
        submitted_tables = schema.tables or {}
        for logical_key, default_table in sorted(DEFAULT_RECONCILE_TABLES.items()):
            if logical_key not in submitted_tables:
                display_name = _reconcile_table_display_name(logical_key, default_table)
                errors.append(f"缺少逻辑表配置：{display_name}（{logical_key}）")
        for logical_key, table_schema in sorted((schema.tables or {}).items()):
            display_name = _reconcile_table_display_name(logical_key, table_schema)
            table_name = str(table_schema.table or "").strip()
            if not table_name:
                errors.append(f"{display_name}（逻辑表 {logical_key}）缺少物理表名")
                continue
            table_context = f"{display_name}（逻辑表 {logical_key}，物理表 {table_name}）"
            try:
                source_entry = self._resolve_reconcile_schema_source(store, table_schema.source_ref)
                table_ref = parse_table_ref(table_name)
                columns = self.pbc_table_column_loader(source_entry.config, table_ref)
            except ValueError as exc:
                errors.append(f"{table_context}表或数据源错误：{str(exc)}")
                continue
            except Exception as exc:
                errors.append(f"{table_context}表或数据源错误：{_runtime_error_message(exc)}")
                continue

            existing_columns = {str(column.name or "").strip().lower() for column in columns}
            configured_fields = {
                **(table_schema.fields or {}),
                **(table_schema.optional_fields or {}),
            }
            required_field_keys = set(DEFAULT_RECONCILE_TABLES.get(logical_key, ReconcileTableSchema()).fields or {})
            for field_key in sorted(required_field_keys):
                if not str(configured_fields.get(field_key) or "").strip():
                    field_label = _reconcile_field_label(logical_key, field_key)
                    errors.append(f"{table_context}缺少字段配置：{field_label}（{field_key}）")
            for field_key, physical_name in sorted(configured_fields.items()):
                field_name = str(physical_name or "").strip()
                field_label = _reconcile_field_label(logical_key, field_key)
                if not field_name:
                    errors.append(f"{table_context}缺少字段配置：{field_label}（{field_key}）")
                    continue
                try:
                    safe_column_name(field_name)
                except ValueError as exc:
                    errors.append(f"{table_context}字段 {field_label}（{field_key}）={field_name}：{str(exc)}")
                    continue
                if existing_columns and field_name.lower() not in existing_columns:
                    errors.append(f"{table_context}缺少字段 {field_name}（{field_label}，{field_key}）")
        if errors:
            raise ValueError(f"表字段配置校验失败：{'；'.join(errors)}")

    def _load_pbc_import_columns(self, body: dict[str, Any]) -> dict[str, Any]:
        store = load_store(self.config_path, database=self.application_database)
        config_name = str(body.get("config_name", "")).strip()
        source = str(body.get("source", "dws") or "dws").strip()
        data_source = _select_pbc_import_source(store, config_name, source)
        table = parse_table_ref(str(body.get("target_table", "")).strip())
        table_columns = self.pbc_table_column_loader(data_source, table)
        upload_ids = _coerce_string_list(body.get("upload_ids"))
        upload_inspections = []
        source_columns: list[str]
        if upload_ids:
            upload_paths = [path for upload_id in upload_ids if (path := self._pbc_import_upload_path(upload_id)) is not None]
            if len(upload_paths) != len(upload_ids):
                raise ValueError("uploaded file not found")
            source_columns = []
            seen_columns: set[str] = set()
            for upload_id, upload_path in zip(upload_ids, upload_paths):
                inspection = inspect_import_upload_with_target_columns(
                    upload_path,
                    table_columns,
                    max_member_bytes=self.max_archive_member_bytes,
                )
                upload_inspections.append({
                    "upload_id": upload_id,
                    "columns": inspection.columns,
                    "files": [asdict(file) for file in inspection.files],
                })
                for column in inspection.columns:
                    if column not in seen_columns:
                        seen_columns.add(column)
                        source_columns.append(column)
        else:
            source_columns = _coerce_string_list(body.get("source_columns"))
        mappings = build_column_mappings(source_columns, table_columns)
        return {
            "source_columns": source_columns,
            "table_columns": [asdict(column) for column in table_columns],
            "upload_inspections": upload_inspections,
            "mappings": [asdict(mapping) for mapping in mappings],
        }

    def _refresh_db_validation_field_mapping(self, *, source: str) -> dict[str, Any]:
        store = load_store(self.config_path, database=self.application_database)
        settings = store.db_validation
        metadata_source = resolve_data_source(store, settings.field_mapping_source_id or settings.detail.source_id)
        try:
            self._refresh_db_validation_field_mapping_catalog(
                metadata_source=metadata_source,
                baseinfo_table=settings.baseinfo_table,
                field_info_table=settings.field_info_table,
                sys_manage_id=settings.detail.sys_manage_id,
                classification_id=settings.detail.classification_id,
                source=source,
            )
        except Exception:
            if source != "manual":
                raise
        return self._db_validation_field_mapping_cache.status_payload()

    def _get_or_refresh_db_validation_field_mapping_for_job(self, job: "DbValidationJob") -> TableFieldCatalog:
        signature = _db_validation_field_mapping_signature(
            metadata_source=job.metadata_source,
            baseinfo_table=job.baseinfo_table,
            field_info_table=job.field_info_table,
            sys_manage_id=job.detail_sys_manage_id,
            classification_id=job.detail_classification_id,
        )
        return self._db_validation_field_mapping_cache.get_or_refresh(
            signature,
            lambda: self.db_validation_field_mapping_loader(
                metadata_source=job.metadata_source,
                baseinfo_table=job.baseinfo_table,
                field_info_table=job.field_info_table,
                sys_manage_id=job.detail_sys_manage_id,
                classification_id=job.detail_classification_id,
            ),
            source="startup",
        )

    def _refresh_db_validation_field_mapping_catalog(
        self,
        *,
        metadata_source: DataSourceConfig,
        baseinfo_table: str,
        field_info_table: str,
        sys_manage_id: str,
        classification_id: str,
        source: str,
    ) -> TableFieldCatalog:
        signature = _db_validation_field_mapping_signature(
            metadata_source=metadata_source,
            baseinfo_table=baseinfo_table,
            field_info_table=field_info_table,
            sys_manage_id=sys_manage_id,
            classification_id=classification_id,
        )
        return self._db_validation_field_mapping_cache.refresh(
            signature,
            lambda: self.db_validation_field_mapping_loader(
                metadata_source=metadata_source,
                baseinfo_table=baseinfo_table,
                field_info_table=field_info_table,
                sys_manage_id=sys_manage_id,
                classification_id=classification_id,
            ),
            source=source,
        )

    def _start_db_validation_field_mapping_auto_refresh(self) -> None:
        if self._field_mapping_auto_refresh_thread is not None and self._field_mapping_auto_refresh_thread.is_alive():
            return
        thread = threading.Thread(
            target=self._run_db_validation_field_mapping_auto_refresh,
            name="db-validation-field-mapping-refresh",
            daemon=True,
        )
        self._field_mapping_auto_refresh_thread = thread
        thread.start()

    def _run_db_validation_field_mapping_auto_refresh(self) -> None:
        while not self._field_mapping_auto_refresh_stop.is_set():
            now = beijing_now()
            next_midnight = datetime.combine(now.date() + timedelta(days=1), datetime_time.min)
            wait_seconds = max((next_midnight - now).total_seconds(), 1.0)
            if self._field_mapping_auto_refresh_stop.wait(wait_seconds):
                return
            try:
                self._refresh_db_validation_field_mapping(source="auto")
            except Exception as exc:
                print(f"[auto-check][db-validation] 字段映射自动刷新失败：{_runtime_error_message(str(exc))}", flush=True)

    def _start_db_validation_job(
        self,
        body: dict[str, Any],
        *,
        current_user: dict[str, Any] | None = None,
    ) -> "DbValidationJob":
        store = load_store(self.config_path, database=self.application_database)
        settings = store.db_validation
        detail_source_id = settings.detail.source_id
        data_source = resolve_data_source(store, detail_source_id)
        field_mapping_source_id = settings.field_mapping_source_id or detail_source_id
        metadata_source = resolve_data_source(store, field_mapping_source_id)
        public_info_source_id = settings.public_info.source_id or detail_source_id
        public_info_source = resolve_data_source(store, public_info_source_id)
        template_source_id = settings.template.source_id or detail_source_id
        template_source = resolve_data_source(store, template_source_id)
        report_date_value = str(body.get("report_date", "") or "").strip() or previous_month_end()
        report_date = _coerce_date(report_date_value)
        selected_tables = _coerce_db_validation_tables(body.get("selected_tables"))
        enable_public_info_check = _coerce_request_bool(body.get("enable_public_info_check"), default=False)
        enable_template_check = _coerce_request_bool(body.get("enable_template_check"), default=False)

        job = DbValidationJob(
            config_name="",
            source=detail_source_id,
            data_source=data_source,
            metadata_config_name="",
            metadata_source_name=field_mapping_source_id,
            metadata_source=metadata_source,
            public_info_config_name="",
            public_info_source_name=public_info_source_id,
            public_info_source=public_info_source,
            template_config_name="",
            template_source_name=template_source_id,
            template_source=template_source,
            baseinfo_table=settings.baseinfo_table,
            field_info_table=settings.field_info_table,
            public_info_table=settings.public_info_table,
            detail_sys_manage_id=settings.detail.sys_manage_id,
            detail_classification_id=settings.detail.classification_id,
            public_info_sys_manage_id=settings.public_info.sys_manage_id,
            public_info_classification_id=settings.public_info.classification_id,
            template_sys_manage_id=settings.template.sys_manage_id,
            template_classification_id=settings.template.classification_id,
            report_date=report_date,
            selected_tables=selected_tables,
            enable_public_info_check=enable_public_info_check,
            enable_template_check=enable_template_check,
            current_user=current_user,
        )
        with self._db_validation_jobs_lock:
            if any(existing.is_active() for existing in self._db_validation_jobs.values()):
                raise ConflictError("数据库校验任务正在执行，请等待当前任务完成后再开始。")
            self._db_validation_jobs[job.id] = job
        thread = threading.Thread(target=self._execute_db_validation_job, args=(job,), daemon=True)
        job.thread = thread
        thread.start()
        return job

    def _get_db_validation_job(self, job_id: str) -> "DbValidationJob | None":
        with self._db_validation_jobs_lock:
            return self._db_validation_jobs.get(job_id)

    def _execute_db_validation_job(self, job: "DbValidationJob") -> None:
        job.start()
        try:
            self.db_validation_output_dir.mkdir(parents=True, exist_ok=True)
            job.log("初始化逐笔字段映射", 8, "字段映射")
            field_catalog = self._get_or_refresh_db_validation_field_mapping_for_job(job)
            result = self.db_validation_executor(
                data_source=job.data_source,
                metadata_source=job.metadata_source,
                public_info_source=job.public_info_source,
                template_source=job.template_source,
                field_catalog=field_catalog,
                baseinfo_table=job.baseinfo_table,
                field_info_table=job.field_info_table,
                public_info_table=job.public_info_table,
                detail_sys_manage_id=job.detail_sys_manage_id,
                detail_classification_id=job.detail_classification_id,
                public_info_sys_manage_id=job.public_info_sys_manage_id,
                public_info_classification_id=job.public_info_classification_id,
                template_sys_manage_id=job.template_sys_manage_id,
                template_classification_id=job.template_classification_id,
                report_date=job.report_date,
                selected_tables=job.selected_tables,
                enable_public_info_check=job.enable_public_info_check,
                enable_template_check=job.enable_template_check,
                output_dir=self.db_validation_output_dir,
                log=job.log,
            )
            job.complete(result)
            self.db_validation_history_store.save_run(_db_validation_history_entry(job, result))
        except Exception as exc:
            job.fail(_runtime_error_message(str(exc)))

    def get_db_validation_download(self, job_id: str) -> tuple[Path, str]:
        job = self._get_db_validation_job(job_id)
        if job is None:
            raise FileNotFoundError("job not found")
        result = job.result
        if job.status != "completed" or result is None:
            raise ValueError("result is not ready")
        if not result.excel_path.exists():
            raise FileNotFoundError("result file not found")
        return result.excel_path, result.excel_path.name

    def get_db_validation_history_download(self, history_id: str) -> tuple[Path, str]:
        run = self.db_validation_history_store.get_run(history_id)
        if run is None:
            raise FileNotFoundError("history not found")
        excel_path = Path(str(run.get("excel_path", "")))
        if not excel_path.exists() or not excel_path.is_file():
            raise FileNotFoundError("result file not found")
        return excel_path, str(run.get("excel_filename") or excel_path.name)

    def get_db_validation_rules_document(self) -> tuple[str, bytes]:
        return build_rules_document()

    def get_storage_schema_export(self, *, current_user: dict[str, Any] | None = None) -> tuple[str, bytes]:
        self._require_admin_storage_user(current_user)
        return build_storage_schema_workbook(self.config_path)

    def get_storage_table_data_export(self, table_name: str, *, current_user: dict[str, Any] | None = None) -> tuple[str, bytes]:
        self._require_admin_storage_user(current_user)
        return build_storage_table_data_workbook(self.config_path, table_name)

    def _handle_admin_storage(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        *,
        current_user: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        auth_error = self._admin_storage_auth_error(current_user)
        if auth_error is not None:
            return auth_error

        parts = [part for part in path.split("/") if part]
        query = dict(parse_qsl(getattr(self, "_query_string", ""), keep_blank_values=True))
        try:
            if method == "GET" and parts == ["api", "admin", "storage", "health"]:
                return 200, {"health": build_storage_health(self.config_path)}
            if method == "GET" and parts == ["api", "admin", "storage", "tables"]:
                return 200, {"tables": list_storage_tables(self.config_path)}
            if method == "GET" and parts == ["api", "admin", "storage", "history-migration"]:
                return 200, {"migration": build_legacy_history_migration_status(self.config_path)}
            if method == "POST" and parts == ["api", "admin", "storage", "history-migration"]:
                status = build_legacy_history_migration_status(self.config_path)
                if not status["can_migrate"]:
                    return 400, {"error": status["status_text"], "migration": status}
                result = migrate_legacy_histories(self.config_path)
                return 200, {
                    "result": result,
                    "migration": build_legacy_history_migration_status(self.config_path),
                }
            if method == "POST" and parts == ["api", "admin", "storage", "backup"]:
                return 200, {"backup": generate_storage_backup(self.config_path)}
            if method == "GET" and len(parts) == 6 and parts[:4] == ["api", "admin", "storage", "tables"] and parts[5] == "schema":
                return 200, get_storage_table_schema(self.config_path, parts[4])
            if method == "GET" and len(parts) == 6 and parts[:4] == ["api", "admin", "storage", "tables"] and parts[5] == "rows":
                page = _positive_int(query.get("page"), default=1)
                page_size = _positive_int(query.get("page_size"), default=20)
                return 200, get_storage_table_rows(self.config_path, parts[4], page=page, page_size=page_size)
        except LookupError as exc:
            return 404, {"error": str(exc)}
        except PermissionError as exc:
            return 403, {"error": str(exc)}
        except ValueError as exc:
            return 400, {"error": str(exc)}
        return 404, {"error": "not found"}

    def _require_admin_storage_user(self, current_user: dict[str, Any] | None) -> None:
        auth_error = self._admin_storage_auth_error(current_user)
        if auth_error is not None:
            status, payload = auth_error
            message = str(payload.get("error") or "admin role required")
            if status == 401:
                raise PermissionError("login required")
            raise PermissionError(message)

    def _admin_storage_auth_error(self, current_user: dict[str, Any] | None) -> tuple[int, dict[str, Any]] | None:
        if current_user is None:
            return 401, {"error": "login required"}
        if str(current_user.get("role", "")) != "admin":
            return 403, {"error": "admin role required"}
        return None

    def _load_flow_definitions(self, keyword: str) -> list[dict[str, Any]]:
        store = load_store(self.config_path, database=self.application_database)
        settings = store.flow_tool
        if not settings.source_id:
            return []
        data_source_entry = resolve_data_source_entry(store, settings.source_id)
        data_source = data_source_entry.config
        gateway = DatabaseFlowGateway(data_source, flow_table=settings.flow_table, task_table=settings.task_table)
        try:
            return [asdict(flow) for flow in gateway.list_flows(keyword)]
        except Exception as exc:
            reason = _runtime_error_message(str(exc))
            raise RuntimeError(
                f"流程表读取失败：数据源 {data_source_entry.name}，流程表 {settings.flow_table or 'sp_flow'}，原因：{reason}"
            ) from exc

    def _start_flow_chain_job(self, chain_id: str, *, trigger_type: str, current_user: dict[str, Any] | None = None, save_history: bool = True) -> "FlowChainJob":
        store = load_store(self.config_path, database=self.application_database)
        settings = store.flow_tool
        chain = _find_flow_chain(settings.chains, chain_id)
        if chain is None:
            raise ValueError("流程链不存在")
        if not chain.enabled:
            raise ValueError("流程链未启用")
        if not settings.source_id:
            raise ValueError("请先配置流程数据源")
        if not settings.execute_url:
            raise ValueError("请先配置流程执行接口地址")
        data_source = resolve_data_source(store, settings.source_id)
        context = FlowChainRunContext(
            trigger_type=trigger_type,
            execute_url=settings.execute_url,
            poll_interval_seconds=settings.poll_interval_seconds,
            step_timeout_seconds=settings.step_timeout_minutes * 60,
            executor_name=str((current_user or {}).get("display_name") or (current_user or {}).get("username") or ""),
        )
        gateway = DatabaseFlowGateway(data_source, flow_table=settings.flow_table, task_table=settings.task_table)
        job = FlowChainJob(chain=chain, context=context, save_history=save_history)
        with self._flow_chain_jobs_lock:
            active_job = self._active_flow_chain_job_payload_locked()
            if active_job is not None:
                raise ConflictError("流程任务正在执行，请等待当前任务完成后再开始。", payload={"active_job": active_job})
            self._flow_chain_jobs[job.id] = job
        thread = threading.Thread(target=self._execute_flow_chain_job, args=(job, gateway), daemon=True)
        job.thread = thread
        thread.start()
        return job

    def _get_flow_chain_job(self, job_id: str) -> "FlowChainJob | None":
        with self._flow_chain_jobs_lock:
            return self._flow_chain_jobs.get(job_id)

    def _active_flow_chain_job_payload_locked(self) -> dict[str, Any] | None:
        for job in self._flow_chain_jobs.values():
            if job.is_active():
                payload = job.to_payload()
                return {
                    "id": payload["id"],
                    "status": payload["status"],
                    "chain_name": payload.get("chain_name", ""),
                    "trigger_type": payload.get("trigger_type", ""),
                    "started_at": payload.get("started_at", ""),
                }
        return None

    def get_active_flow_chain_job_payload(self) -> dict[str, Any] | None:
        with self._flow_chain_jobs_lock:
            active = next((job for job in self._flow_chain_jobs.values() if job.is_active()), None)
            return active.to_payload() if active is not None else None

    def _execute_flow_chain_job(self, job: "FlowChainJob", gateway: Any) -> None:
        job.start()
        try:
            result = self.flow_chain_executor(
                chain=job.chain,
                context=job.context,
                gateway=gateway,
                cancel_event=job.cancel_event,
                log=job.log,
            )
            job.complete(result)
            if job.save_history:
                try:
                    self.flow_chain_history_store.save_run(_flow_chain_history_entry(job, result))
                    print(f"[auto-check][flow] history saved: id={job.id}, status=completed", flush=True)
                except Exception:
                    import traceback
                    print(f"[auto-check][flow] FAILED to save completed history:", flush=True)
                    traceback.print_exc()
        except Exception as exc:
            job.fail(_runtime_error_message(str(exc)))
            if job.save_history:
                try:
                    self.flow_chain_history_store.save_run(_flow_chain_history_entry_from_job(job))
                    print(f"[auto-check][flow] history saved: id={job.id}, status=failed, error={job.error}", flush=True)
                except Exception:
                    import traceback
                    print(f"[auto-check][flow] FAILED to save failed history:", flush=True)
                    traceback.print_exc()

    def _save_merged_flow_chain_history(self, data: dict[str, Any], current_user: dict[str, Any] | None = None) -> dict[str, Any]:
        """保存多流程链合并记录"""
        chain_details = data.get("chain_details", [])
        if not chain_details:
            raise ValueError("chain_details is required")
        
        # 计算总时长
        total_duration = sum(d.get("duration_seconds", 0) for d in chain_details)
        
        # 获取所有链名称
        chain_names = [d.get("chain_name", "") for d in chain_details]
        chain_name_display = ",".join(chain_names)
        
        # 获取最终状态（最后一条链的状态）
        final_status = chain_details[-1].get("status", "completed") if chain_details else "completed"
        
        # 获取开始和结束时间
        started_at = data.get("started_at", "")
        finished_at = data.get("finished_at", "")
        
        # 创建合并记录
        merged_entry = {
            "id": data.get("id", uuid.uuid4().hex),
            "run_at": _display_datetime(started_at),
            "finished_at": _display_datetime(finished_at),
            "run_date": _display_datetime(started_at)[:10],
            "chain_id": "",
            "chain_name": chain_name_display,
            "chain_names": chain_names,
            "is_multi_chain": True,
            "trigger_type": "manual",
            "executor_name": str((current_user or {}).get("display_name") or (current_user or {}).get("username") or ""),
            "status": final_status,
            "step_count": sum(d.get("step_count", 0) for d in chain_details),
            "duration_seconds": total_duration,
            "steps": [],
            "chain_details": chain_details,
        }
        
        try:
            self.flow_chain_history_store.save_run(merged_entry)
            print(f"[auto-check][flow] merged history saved: id={merged_entry['id']}, chains={len(chain_details)}, duration={total_duration}s", flush=True)
        except Exception:
            import traceback
            print(f"[auto-check][flow] FAILED to save merged history:", flush=True)
            traceback.print_exc()
            raise
        
        return merged_entry

    def _create_runner(
        self,
        config: AppConfig,
        *,
        max_combination_rows: int,
        progress_logger: Callable[[str, int | None, str | None], None] | None = None,
        cancel_event: threading.Event | None = None,
        reconcile_schema: Any | None = None,
        source_configs: dict[str, DataSourceConfig] | None = None,
    ) -> Any:
        if self.runner_factory is not None:
            return self.runner_factory(config)
        return ReconcileEngine(
            AutoCheckRepository(config, schema=reconcile_schema, source_configs=source_configs),
            max_combination_rows=max_combination_rows,
            progress_logger=progress_logger,
            cancel_event=cancel_event,
        )

    def _run_once(
        self,
        date: str,
        *,
        max_combination_rows: int,
        progress_logger: Callable[[str, int | None, str | None], None] | None = None,
        cancel_event: threading.Event | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        store = load_store(self.config_path, database=self.application_database)
        config, config_name, dws_source_name = _active_config_and_name_from_store(store, config_path=self.config_path)
        runner = self._create_runner(
            config,
            max_combination_rows=max_combination_rows,
            progress_logger=progress_logger,
            cancel_event=cancel_event,
            reconcile_schema=store.reconcile_schema,
            source_configs=_data_source_config_lookup(store),
        )
        try:
            results = to_jsonable(runner.run(date))
        except NoSourceReportData as exc:
            return [], _no_source_report_payload(exc.date)
        if cancel_event is not None and cancel_event.is_set():
            raise RunCancelled("执行已终止")
        if progress_logger is not None and not results:
            progress_logger("执行完成：报表有数据且未发现差异", 96, "保存历史")
        history = build_history_entry(
            previous_runs=self.history_store.list_runs(),
            run_date=date,
            config_name=config_name,
            dws_source_name=dws_source_name,
            config=config,
            results=results,
            executor_id=str((current_user or {}).get("id", "")),
            executor_username=str((current_user or {}).get("username", "")),
            executor_name=str((current_user or {}).get("display_name") or (current_user or {}).get("username") or ""),
        )
        self.history_store.save_run(history)
        return results, summarize_run(history)

    def _start_run_job(
        self,
        date: str,
        max_combination_rows: int,
        *,
        current_user: dict[str, Any] | None = None,
    ) -> "RunJob":
        job = RunJob(date=date, max_combination_rows=max_combination_rows, current_user=current_user)
        with self._run_jobs_lock:
            active_job = self._active_run_job_payload_locked()
            if self._inline_run_active or active_job is not None:
                raise ConflictError("对数任务正在执行，请等待当前任务完成后再开始。", payload={"active_job": active_job})
            self._run_jobs[job.id] = job
        thread = threading.Thread(target=self._execute_run_job, args=(job,), daemon=True)
        job.thread = thread
        thread.start()
        return job

    def _get_run_job(self, job_id: str) -> "RunJob | None":
        with self._run_jobs_lock:
            return self._run_jobs.get(job_id)

    def _has_active_run_job(self) -> bool:
        with self._run_jobs_lock:
            return self._inline_run_active or any(job.is_active() for job in self._run_jobs.values())

    def _begin_inline_run(self) -> None:
        with self._run_jobs_lock:
            active_job = self._active_run_job_payload_locked()
            if self._inline_run_active or active_job is not None:
                raise ConflictError("对数任务正在执行，请等待当前任务完成后再开始。", payload={"active_job": active_job})
            self._inline_run_active = True

    def _end_inline_run(self) -> None:
        with self._run_jobs_lock:
            self._inline_run_active = False

    def _active_run_job_payload_locked(self) -> dict[str, Any] | None:
        for job in self._run_jobs.values():
            if job.is_active():
                payload = job.to_payload()
                return {
                    "id": payload["id"],
                    "status": payload["status"],
                    "executor": payload.get("executor", {}),
                    "started_at": payload.get("started_at", ""),
                }
        return None

    def _execute_run_job(self, job: "RunJob") -> None:
        job.start()
        try:
            job.log("后台任务已启动", 2, "读取数据")
            results, history = self._run_once(
                job.date,
                max_combination_rows=job.max_combination_rows,
                progress_logger=job.log,
                cancel_event=job.cancel_event,
                current_user=job.current_user,
            )
            job.complete(results, history)
        except RunCancelled as exc:
            job.mark_cancelled(str(exc))
        except Exception as exc:
            import traceback
            traceback.print_exc()
            job.fail(_runtime_error_message(exc))


class RunJob:
    def __init__(self, *, date: str, max_combination_rows: int, current_user: dict[str, Any] | None = None):
        self.id = uuid.uuid4().hex
        self.date = date
        self.max_combination_rows = max_combination_rows
        self.current_user = _public_current_user(current_user)
        self.status = "pending"
        self.progress = 0
        self.step = "等待执行"
        self.logs: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []
        self.history: dict[str, Any] | None = None
        self.error = ""
        self.started_at = ""
        self.finished_at = ""
        self.cancel_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self.status = "running"
            self.started_at = beijing_timestamp()

    def is_active(self) -> bool:
        with self._lock:
            return self.status in {"pending", "running", "cancelling"}

    def log(self, message: str, progress: int | None = None, step: str | None = None) -> None:
        record = {
            "time": beijing_time_text(),
            "message": message,
        }
        with self._lock:
            if progress is not None:
                self.progress = max(0, min(100, int(progress)))
                record["progress"] = self.progress
            if step:
                self.step = step
                record["step"] = step
            self.logs.append(record)
            self.logs = self.logs[-200:]
        print(f"[auto-check][{self.id}] {record['time']} {message}", flush=True)

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._lock:
            if self.status in {"pending", "running", "cancelling"}:
                self.status = "cancelled"
                self.step = "已终止"
                self.error = "执行已终止"
                self.finished_at = beijing_timestamp()
        self.log("收到停止执行请求，已终止本次对数；当前数据库查询返回后不会保存结果", None, "已终止")

    def complete(self, results: list[dict[str, Any]], history: dict[str, Any]) -> None:
        no_source_data = bool(history.get("no_source_data")) if history else False
        with self._lock:
            if self.cancel_event.is_set() or self.status == "cancelled":
                return
            self.status = "completed"
            self.progress = 100
            self.step = "完成"
            self.results = results
            self.history = history
            self.finished_at = beijing_timestamp()
        if no_source_data:
            message = history.get("message") or "报表对应日期无数据"
            if not any(message in str(log.get("message", "")) for log in self.logs):
                self.log(message, 100, "完成")
        else:
            self.log(f"执行完成：生成 {len(results)} 条结果", 100, "完成")

    def mark_cancelled(self, message: str) -> None:
        with self._lock:
            self.status = "cancelled"
            self.error = message
            self.finished_at = beijing_timestamp()
        self.log(message or "执行已终止", None, "已终止")

    def fail(self, message: str) -> None:
        with self._lock:
            if self.cancel_event.is_set() or self.status == "cancelled":
                return
            self.status = "failed"
            self.error = message
            self.finished_at = beijing_timestamp()
        self.log(f"执行失败：{message}", 100, "执行失败")

    def to_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "date": self.date,
                "max_combination_rows": self.max_combination_rows,
                "executor": dict(self.current_user),
                "status": self.status,
                "progress": self.progress,
                "step": self.step,
                "logs": list(self.logs),
                "results": self.results,
                "history": self.history,
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


class FlowChainJob:
    def __init__(self, *, chain: FlowChainConfig, context: FlowChainRunContext, save_history: bool = True):
        self.id = uuid.uuid4().hex
        self.chain = chain
        self.context = context
        self.save_history = save_history
        self.status = "pending"
        self.progress = 0
        self.step = "等待执行"
        self.logs: list[dict[str, Any]] = []
        self.steps: list[dict[str, Any]] = [
            {
                "flow_id": step.flow_id,
                "flow_name": step.name or step.flow_id,
                "status": "pending",
                "sp_task_id": None,
                "begin_time": "",
                "end_time": "",
                "message": "",
            }
            for step in chain.steps
        ]
        self.error = ""
        self.started_at = ""
        self.finished_at = ""
        self.cancel_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self.status = "running"
            self.started_at = beijing_timestamp()

    def is_active(self) -> bool:
        with self._lock:
            return self.status in {"pending", "running", "cancelling"}

    def log(self, message: str, progress: int | None = None, step: str | None = None) -> None:
        record = {
            "time": beijing_time_text(),
            "message": message,
        }
        with self._lock:
            if progress is not None:
                self.progress = max(0, min(100, int(progress)))
                record["progress"] = self.progress
            if step:
                self.step = step
                record["step"] = step
            self.logs.append(record)
            self.logs = self.logs[-200:]
        print(f"[auto-check][flow][{self.id}] {record['time']} {message}", flush=True)

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._lock:
            if self.status in {"pending", "running", "cancelling"}:
                self.status = "cancelled"
                self.step = "已取消"
                self.error = "流程执行已取消"
                self.finished_at = beijing_timestamp()
        self.log("收到取消请求，本地流程链将停止提交后续流程。", None, "已取消")

    def complete(self, result: FlowChainRunResult) -> None:
        payload = flow_chain_result_to_dict(result)
        with self._lock:
            if self.cancel_event.is_set() or self.status == "cancelled":
                return
            self.status = "completed"
            self.progress = 100
            self.step = "完成"
            self.steps = payload["steps"]
            self.finished_at = beijing_timestamp()
        self.log("流程链执行完成", 100, "完成")

    def fail(self, message: str) -> None:
        with self._lock:
            if self.cancel_event.is_set() or self.status == "cancelled":
                return
            self.status = "failed"
            self.error = message
            self.finished_at = beijing_timestamp()
        self.log(f"流程链执行失败：{message}", 100, "执行失败")

    def to_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "chain_id": self.chain.id,
                "chain_name": self.chain.name,
                "trigger_type": self.context.trigger_type,
                "executor_name": self.context.executor_name,
                "status": self.status,
                "progress": self.progress,
                "step": self.step,
                "steps": list(self.steps),
                "logs": list(self.logs),
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


class DbValidationJob:
    def __init__(
        self,
        *,
        config_name: str,
        source: str,
        data_source: DataSourceConfig,
        metadata_config_name: str,
        metadata_source_name: str,
        metadata_source: DataSourceConfig,
        public_info_config_name: str,
        public_info_source_name: str,
        public_info_source: DataSourceConfig,
        template_config_name: str,
        template_source_name: str,
        template_source: DataSourceConfig,
        baseinfo_table: str,
        field_info_table: str,
        public_info_table: str,
        detail_sys_manage_id: str,
        detail_classification_id: str,
        public_info_sys_manage_id: str,
        public_info_classification_id: str,
        template_sys_manage_id: str,
        template_classification_id: str,
        report_date: date,
        selected_tables: list[str],
        enable_public_info_check: bool,
        enable_template_check: bool,
        current_user: dict[str, Any] | None = None,
    ):
        self.id = uuid.uuid4().hex
        self.config_name = config_name
        self.source = source
        self.data_source = data_source
        self.metadata_config_name = metadata_config_name
        self.metadata_source_name = metadata_source_name
        self.metadata_source = metadata_source
        self.public_info_config_name = public_info_config_name
        self.public_info_source_name = public_info_source_name
        self.public_info_source = public_info_source
        self.template_config_name = template_config_name
        self.template_source_name = template_source_name
        self.template_source = template_source
        self.baseinfo_table = baseinfo_table
        self.field_info_table = field_info_table
        self.public_info_table = public_info_table
        self.detail_sys_manage_id = detail_sys_manage_id
        self.detail_classification_id = detail_classification_id
        self.public_info_sys_manage_id = public_info_sys_manage_id
        self.public_info_classification_id = public_info_classification_id
        self.template_sys_manage_id = template_sys_manage_id
        self.template_classification_id = template_classification_id
        self.report_date = report_date
        self.selected_tables = selected_tables
        self.enable_public_info_check = enable_public_info_check
        self.enable_template_check = enable_template_check
        self.executor_id = str((current_user or {}).get("id", ""))
        self.executor_username = str((current_user or {}).get("username", ""))
        self.executor_name = str((current_user or {}).get("display_name") or (current_user or {}).get("username") or "")
        self.status = "pending"
        self.progress = 0
        self.step = "等待执行"
        self.logs: list[dict[str, Any]] = []
        self.result: DbValidationRunResult | None = None
        self.error = ""
        self.started_at = ""
        self.finished_at = ""
        self.thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self.status = "running"
            self.started_at = beijing_timestamp()
        self.log("数据库校验任务已启动", 5, "加载元数据")

    def is_active(self) -> bool:
        with self._lock:
            return self.status in {"pending", "running"}

    def log(self, message: str, progress: int | None = None, step: str | None = None) -> None:
        record: dict[str, Any] = {"time": beijing_time_text(), "message": message}
        with self._lock:
            if progress is not None:
                self.progress = max(0, min(100, int(progress)))
                record["progress"] = self.progress
            if step:
                self.step = step
                record["step"] = step
            self.logs.append(record)
            self.logs = self.logs[-200:]
        print(f"[auto-check][db-validation][{self.id}] {record['time']} {message}", flush=True)

    def complete(self, result: DbValidationRunResult) -> None:
        with self._lock:
            self.status = "completed"
            self.progress = 100
            self.step = "完成"
            self.result = result
            self.finished_at = beijing_timestamp()
        self.log(f"数据库校验完成：输出 {result.error_count} 条结果", 100, "完成")

    def fail(self, message: str) -> None:
        with self._lock:
            self.status = "failed"
            self.error = message
            self.progress = 100
            self.step = "执行失败"
            self.finished_at = beijing_timestamp()
        self.log(f"数据库校验失败：{message}", 100, "执行失败")

    def to_payload(self) -> dict[str, Any]:
        with self._lock:
            result = self.result
            return {
                "id": self.id,
                "config_name": self.config_name,
                "source": self.source,
                "metadata_config_name": self.metadata_config_name,
                "metadata_source": self.metadata_source_name,
                "public_info_config_name": self.public_info_config_name,
                "public_info_source": self.public_info_source_name,
                "template_config_name": self.template_config_name,
                "template_source": self.template_source_name,
                "baseinfo_table": self.baseinfo_table,
                "field_info_table": self.field_info_table,
                "public_info_table": self.public_info_table,
                "detail_sys_manage_id": self.detail_sys_manage_id,
                "detail_classification_id": self.detail_classification_id,
                "public_info_sys_manage_id": self.public_info_sys_manage_id,
                "public_info_classification_id": self.public_info_classification_id,
                "template_sys_manage_id": self.template_sys_manage_id,
                "template_classification_id": self.template_classification_id,
                "report_date": self.report_date.isoformat(),
                "executor_id": self.executor_id,
                "executor_username": self.executor_username,
                "executor_name": self.executor_name,
                "selected_tables": list(self.selected_tables),
                "enable_public_info_check": self.enable_public_info_check,
                "enable_template_check": self.enable_template_check,
                "status": self.status,
                "progress": self.progress,
                "step": self.step,
                "logs": list(self.logs),
                "result": _db_validation_result_payload(result) if result is not None else None,
                "download_url": f"/api/tools/db-validation/download/{self.id}" if self.status == "completed" and result is not None else "",
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


class PbcImportJob:
    def __init__(
        self,
        *,
        upload_path: Path,
        upload_paths: list[Path] | None = None,
        data_source: DataSourceConfig,
        table: TableRef,
        columns: list[str],
        drop_columns: list[str],
        column_order: list[str],
        column_mappings: list[ColumnMapping],
        file_layouts: list[Any] | None = None,
        mode: str,
    ):
        self.id = uuid.uuid4().hex
        self.upload_path = upload_path
        self.upload_paths = upload_paths or [upload_path]
        self.data_source = data_source
        self.table = table
        self.columns = columns
        self.drop_columns = drop_columns
        self.column_order = column_order
        self.column_mappings = column_mappings
        self.file_layouts = file_layouts or []
        self.mode = mode
        self.status = "pending"
        self.progress = 0
        self.step = "waiting"
        self.rows_imported = 0
        self.logs: list[dict[str, Any]] = []
        self.error = ""
        self.started_at = ""
        self.finished_at = ""
        self.cancel_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self.status = "running"
            self.started_at = beijing_timestamp()
        self.log("PBC import job started", 5, "read files")

    def is_active(self) -> bool:
        with self._lock:
            return self.status in {"pending", "running"}

    def log(self, message: str, progress: int | None = None, step: str | None = None, rows: int | None = None) -> None:
        record: dict[str, Any] = {"time": beijing_time_text(), "message": message}
        with self._lock:
            if progress is not None:
                self.progress = max(0, min(100, int(progress)))
                record["progress"] = self.progress
            if rows is not None:
                self.rows_imported = rows
                record["rows"] = rows
            if step:
                self.step = step
                record["step"] = step
            self.logs.append(record)
            self.logs = self.logs[-200:]
        print(f"[auto-check][pbc-import][{self.id}] {record['time']} {message}", flush=True)

    def complete(self, rows_imported: int) -> None:
        with self._lock:
            self.status = "completed"
            self.progress = 100
            self.step = "completed"
            self.rows_imported = rows_imported
            self.finished_at = beijing_timestamp()
        self.log(f"PBC import completed, wrote {rows_imported} rows", 100, "completed", rows=rows_imported)

    def fail(self, message: str) -> None:
        with self._lock:
            self.status = "failed"
            self.error = message
            self.progress = 100
            self.step = "failed"
            self.finished_at = beijing_timestamp()
        self.log(f"PBC import failed: {message}", 100, "failed")

    def to_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "status": self.status,
                "progress": self.progress,
                "step": self.step,
                "rows_imported": self.rows_imported,
                "logs": list(self.logs),
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


def _build_ds(
    payload: dict[str, Any],
    default_type: str,
    default_port: int,
    *,
    fallback_password: str = "",
    decrypt_password: PasswordDecryptor | None = None,
) -> DataSourceConfig:
    raw_password = str(payload.get("password", "") or "")
    if raw_password:
        raise ValueError("encrypted database password is required")
    encrypted_password = str(payload.get("password_encrypted", "") or "")
    password = ""
    if encrypted_password:
        if decrypt_password is None:
            raise ValueError("encrypted database password is unsupported")
        password = decrypt_password(encrypted_password)
    elif fallback_password:
        password = fallback_password
    return DataSourceConfig(
        db_type=str(payload.get("db_type", default_type)),
        host=str(payload.get("host", "")),
        port=int(payload.get("port", default_port)),
        database=str(payload.get("database", "")),
        schema=str(payload.get("schema", "")),
        username=str(payload.get("username", "")),
        password=password,
    )


def _contains_plaintext_password(payload: Any) -> bool:
    if isinstance(payload, dict):
        return any(
            (str(key) == "password" and bool(str(value or "")))
            or _contains_plaintext_password(value)
            for key, value in payload.items()
        )
    if isinstance(payload, list):
        return any(_contains_plaintext_password(item) for item in payload)
    return False


def _public_ds(config: DataSourceConfig) -> dict[str, Any]:
    return {
        "db_type": config.db_type,
        "host": config.host,
        "port": config.port,
        "database": config.database,
        "schema": config.schema,
        "username": config.username,
        "password_set": bool(config.password),
    }


def _describe_data_source(config: DataSourceConfig) -> str:
    schema = config.schema or "-"
    return f"{config.db_type}/{config.host}:{config.port}/{config.database}/{schema}"


def _public_data_source_entry(entry: DataSourceEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "name": entry.name,
        **_public_ds(entry.config),
        "is_default": entry.is_default,
    }


def _public_config(config: AppConfig) -> dict[str, Any]:
    return {"dws": _public_ds(config.dws), "business": _public_ds(config.business)}


def _save_legacy_grouped_config(
    store: ConfigStore,
    body: dict[str, Any],
    *,
    decrypt_password: PasswordDecryptor | None,
) -> None:
    name = str(body.get("name", "") or "").strip()
    old_name = str(body.get("editing_name", "") or "").strip() or name
    default_val = _coerce_request_bool(body.get("is_default"), default=not store.data_sources)
    old_dws_id = legacy_source_id(old_name, "dws")
    old_business_id = legacy_source_id(old_name, "business")
    new_dws_id = legacy_source_id(name, "dws")
    new_business_id = legacy_source_id(name, "business")
    existing_dws = next((entry for entry in store.data_sources if entry.id == old_dws_id), None)
    existing_business = next((entry for entry in store.data_sources if entry.id == old_business_id), None)
    dws = _build_ds(
        body.get("dws", {}),
        "postgresql",
        5432,
        fallback_password=existing_dws.config.password if existing_dws else "",
        decrypt_password=decrypt_password,
    )
    business = _build_ds(
        body.get("business", {}),
        "mysql",
        3306,
        fallback_password=existing_business.config.password if existing_business else "",
        decrypt_password=decrypt_password,
    )
    store.data_sources = [
        entry
        for entry in store.data_sources
        if entry.id not in {old_dws_id, old_business_id, new_dws_id, new_business_id}
    ]
    if default_val:
        for entry in store.data_sources:
            entry.is_default = False
    store.data_sources.append(DataSourceEntry(id=new_dws_id, name=f"{name} - DWS", config=dws, is_default=default_val))
    store.data_sources.append(DataSourceEntry(id=new_business_id, name=f"{name} - 报表库", config=business))
    if not store.reconcile_data_sources.dws_source_id or store.reconcile_data_sources.dws_source_id == old_dws_id:
        store.reconcile_data_sources = ReconcileDataSourceSettings(
            dws_source_id=new_dws_id,
            business_source_id=new_business_id,
        )
    if default_val:
        store.default_name = name


def _referenced_data_source_labels(store: ConfigStore, source_ids: set[str]) -> list[str]:
    references = [
        ("对账 DWS 数据源", store.reconcile_data_sources.dws_source_id),
        ("对账报表库数据源", store.reconcile_data_sources.business_source_id),
        ("逐笔数据源", store.db_validation.detail.source_id),
        ("公开信息数据源", store.db_validation.public_info.source_id),
        ("模板数据源", store.db_validation.template.source_id),
        ("字段匹配数据源", store.db_validation.field_mapping_source_id),
        ("流程数据源", store.flow_tool.source_id),
    ]
    labels: list[str] = []
    for label, source_id in references:
        if source_id in source_ids and label not in labels:
            labels.append(label)
    return labels


def _find_flow_chain(chains: list[FlowChainConfig], chain_id: str) -> FlowChainConfig | None:
    chain_id = str(chain_id or "").strip()
    for chain in chains:
        if chain.id == chain_id:
            return chain
    return None


def _validate_flow_tool_settings(store: ConfigStore, settings: Any) -> None:
    if settings.source_id:
        resolve_data_source(store, settings.source_id)
    _validate_flow_execute_url(settings.execute_url)


def _validate_flow_execute_url(value: str) -> None:
    url = str(value or "").strip()
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("流程执行接口必须是以 http:// 或 https:// 开头的完整地址")
    if any(key.lower() == "id" for key, _value in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError("流程执行接口不要包含 id 参数，系统会在执行时自动追加当前流程 flow_id")


def _data_size(data: Any) -> int | None:
    if isinstance(data, (bytes, bytearray)):
        return len(data)
    if hasattr(data, "getbuffer"):
        return len(data.getbuffer())
    if hasattr(data, "seek") and hasattr(data, "tell"):
        current = data.tell()
        data.seek(0, 2)
        size = data.tell()
        data.seek(current)
        return int(size)
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_column_mappings(value: Any) -> list[ColumnMapping]:
    if not isinstance(value, list):
        return []
    mappings: list[ColumnMapping] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_column", "")).strip()
        target = str(item.get("target_column", "")).strip()
        comment = str(item.get("target_comment", "")).strip()
        if source and target:
            mappings.append(ColumnMapping(source_column=source, target_column=target, target_comment=comment))
    return mappings


def _select_pbc_import_source(store: Any, config_name: str, source: str) -> DataSourceConfig:
    if source not in {"dws", "business"}:
        raise ValueError("source must be dws or business")
    selected = None
    if config_name:
        selected = next((entry for entry in store.data_sources if entry.name == config_name), None)
    if selected is None:
        selected = next((entry for entry in store.data_sources if entry.is_default), None)
    if selected is None and store.data_sources:
        selected = store.data_sources[0]
    if selected is None:
        raise ValueError("no data source config found")
    return selected.config


def _save_pbc_import_preferences(
    config_path: str | Path,
    table: str,
    config_name: str,
    source: str,
    *,
    database: ApplicationDatabase,
) -> None:
    store = load_store(config_path, database=database)
    recent_tables = [table]
    recent_tables.extend(item for item in store.pbc_import_tool.recent_tables if item != table)
    store.pbc_import_tool = PbcImportToolSettings(
        recent_tables=recent_tables[:20],
        last_config_name=config_name,
        last_source=source if source in {"dws", "business"} else "dws",
    )
    save_store(store, config_path, database=database)


def execute_pbc_import(
    *,
    zip_path: Path | list[Path],
    data_source: DataSourceConfig,
    table: TableRef,
    columns: list[str],
    drop_columns: list[str],
    column_order: list[str],
    column_mappings: list[ColumnMapping],
    file_layouts: list[Any] | None = None,
    mode: str,
    log: Callable[..., None],
    cancel_event: threading.Event,
) -> int:
    final_columns = (
        mapped_target_columns(column_mappings)
        if column_mappings
        else projected_columns(columns, drop_columns=drop_columns, column_order=column_order)
    )
    client = DatabaseClient(data_source)
    if mode == "replace":
        log("clearing target table", 10, "clear target")
        client.clear_table(table)
    log("reading archive and writing database", 20, "write database")
    row_iter = (
        iter_mapped_rows(zip_path, column_mappings, file_layouts=file_layouts or [])
        if column_mappings
        else iter_projected_rows(zip_path, columns=columns, drop_columns=drop_columns, column_order=column_order, file_layouts=file_layouts or [])
    )

    def cancellable_rows() -> Iterator[tuple[Any, ...]]:
        for row in row_iter:
            if cancel_event.is_set():
                raise RunCancelled("PBC import stopped")
            yield row

    def log_batch(rows_imported: int) -> None:
        log(f"wrote {rows_imported} rows", 60, "write database", rows=rows_imported)

    if cancel_event.is_set():
        raise RunCancelled("PBC import stopped")
    rows_imported = client.insert_row_batches(
        table,
        final_columns,
        cancellable_rows(),
        batch_size=10000,
        on_batch=log_batch,
    )
    log(f"database write completed, total {rows_imported} rows", 95, "write completed", rows=rows_imported)
    return rows_imported


def load_pbc_table_columns(data_source: DataSourceConfig, table: TableRef) -> list[TableColumn]:
    return DatabaseClient(data_source).table_columns(table)


def load_db_validation_field_mapping(
    *,
    metadata_source: DataSourceConfig,
    baseinfo_table: str,
    field_info_table: str,
    sys_manage_id: str,
    classification_id: str,
) -> TableFieldCatalog:
    try:
        return FieldMetadataLoader(
            DatabaseClient(metadata_source),
            baseinfo_table=baseinfo_table,
            field_info_table=field_info_table,
            sys_manage_id=sys_manage_id,
            classification_id=classification_id,
        ).load()
    except Exception as exc:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        raise RuntimeError(
            f"字段映射表读取失败：{_describe_data_source(metadata_source)}，"
            f"baseinfo={baseinfo_table}，field_info={field_info_table}，原因：{message}"
        ) from exc


def execute_flow_chain(
    *,
    chain: FlowChainConfig,
    context: FlowChainRunContext,
    gateway: Any,
    cancel_event: threading.Event,
    log: Callable[[str, int | None, str | None], None],
) -> FlowChainRunResult:
    return run_flow_chain(
        chain,
        context,
        gateway,
        cancel_event=cancel_event,
        log=log,
    )


def execute_db_validation(
    *,
    data_source: DataSourceConfig,
    metadata_source: DataSourceConfig,
    public_info_source: DataSourceConfig,
    template_source: DataSourceConfig,
    field_catalog: TableFieldCatalog,
    baseinfo_table: str,
    field_info_table: str,
    public_info_table: str,
    detail_sys_manage_id: str,
    detail_classification_id: str,
    public_info_sys_manage_id: str,
    public_info_classification_id: str,
    template_sys_manage_id: str,
    template_classification_id: str,
    report_date: date,
    selected_tables: list[str],
    enable_public_info_check: bool,
    enable_template_check: bool,
    output_dir: Path,
    log: Callable[[str, int | None, str | None], None],
) -> DbValidationRunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = DbValidationEngine(
        data_client=DatabaseClient(data_source),
        metadata_client=DatabaseClient(metadata_source),
        public_info_client=DatabaseClient(public_info_source),
        template_client=DatabaseClient(template_source),
        field_catalog=field_catalog,
        baseinfo_table=baseinfo_table,
        field_info_table=field_info_table,
        public_info_table=public_info_table,
        detail_sys_manage_id=detail_sys_manage_id,
        detail_classification_id=detail_classification_id,
        template_sys_manage_id=template_sys_manage_id,
        template_classification_id=template_classification_id,
        output_dir=output_dir,
    )
    return engine.run(
        report_date=report_date,
        selected_tables=selected_tables,
        enable_public_info_check=enable_public_info_check,
        enable_template_check=enable_template_check,
        log=log,
    )


def _db_validation_result_payload(result: DbValidationRunResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "report_date": result.report_date,
        "error_count": result.error_count,
        "warnings": list(result.warnings),
        "excel_filename": result.excel_path.name,
        "row_count": len(result.rows),
        "rows": [row.to_payload() for row in result.rows[:200]],
    }


def _history_run_count(history_store: HistoryStore) -> int:
    count_runs = getattr(history_store, "count_runs", None)
    if callable(count_runs):
        return int(count_runs())
    return len(history_store.list_runs())


def _db_validation_history_entry(job: DbValidationJob, result: DbValidationRunResult) -> dict[str, Any]:
    return {
        "id": job.id,
        "run_at": _display_datetime(job.started_at),
        "finished_at": _display_datetime(job.finished_at),
        "run_date": result.report_date,
        "report_date": result.report_date,
        "status": job.status,
        "executor_id": job.executor_id,
        "executor_username": job.executor_username,
        "executor_name": job.executor_name,
        "result_count": result.error_count,
        "warning_count": len(result.warnings),
        "table_count": len(job.selected_tables),
        "selected_tables": list(job.selected_tables),
        "warnings": list(result.warnings),
        "rows": [row.to_payload() for row in result.rows],
        "enable_public_info_check": job.enable_public_info_check,
        "enable_template_check": job.enable_template_check,
        "excel_filename": result.excel_path.name,
        "excel_path": str(result.excel_path),
        "download_url": f"/api/tools/db-validation/history/download/{job.id}",
    }


def _flow_chain_history_entry(job: FlowChainJob, result: FlowChainRunResult) -> dict[str, Any]:
    payload = flow_chain_result_to_dict(result)
    duration = _calculate_duration_seconds(job.started_at, job.finished_at)
    return {
        "id": job.id,
        "run_at": _display_datetime(job.started_at),
        "finished_at": _display_datetime(job.finished_at),
        "run_date": _display_datetime(job.started_at)[:10],
        "chain_id": job.chain.id,
        "chain_name": job.chain.name,
        "chain_names": [job.chain.name],
        "is_multi_chain": False,
        "trigger_type": result.trigger_type,
        "executor_name": job.context.executor_name,
        "status": job.status,
        "step_count": len(result.steps),
        "duration_seconds": duration,
        "steps": payload["steps"],
        "logs": list(job.logs),
        "chain_details": [{
            "chain_name": job.chain.name,
            "status": job.status,
            "step_count": len(result.steps),
            "duration_seconds": duration,
            "error": "",
        }],
    }


def _flow_chain_history_entry_from_job(job: FlowChainJob) -> dict[str, Any]:
    duration = _calculate_duration_seconds(job.started_at, job.finished_at)
    return {
        "id": job.id,
        "run_at": _display_datetime(job.started_at),
        "finished_at": _display_datetime(job.finished_at),
        "run_date": _display_datetime(job.started_at)[:10],
        "chain_id": job.chain.id,
        "chain_name": job.chain.name,
        "chain_names": [job.chain.name],
        "is_multi_chain": False,
        "trigger_type": job.context.trigger_type,
        "executor_name": job.context.executor_name,
        "status": job.status,
        "error": job.error,
        "step_count": len(job.steps),
        "duration_seconds": duration,
        "steps": list(job.steps),
        "logs": list(job.logs),
        "chain_details": [{
            "chain_name": job.chain.name,
            "status": job.status,
            "step_count": len(job.steps),
            "duration_seconds": duration,
            "error": job.error,
        }],
    }


def _db_validation_history_execution_sort_key(run: dict[str, Any]) -> tuple[str, str]:
    return (
        _db_validation_history_execution_sort_text(run),
        str(run.get("id") or ""),
    )


def _db_validation_history_execution_sort_text(run: dict[str, Any]) -> str:
    raw = str(run.get("run_at") or run.get("started_at") or run.get("finished_at") or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("T", " ")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(normalized, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return normalized


def _display_datetime(value: str) -> str:
    return str(value or "").replace("T", " ")


def _calculate_duration_seconds(start_str: str, end_str: str) -> int:
    """计算两个时间字符串之间的秒数差"""
    if not start_str or not end_str:
        return 0
    try:
        from datetime import datetime
        start = datetime.fromisoformat(start_str.replace(" ", "T"))
        end = datetime.fromisoformat(end_str.replace(" ", "T"))
        delta = end - start
        return max(0, int(delta.total_seconds()))
    except (ValueError, TypeError):
        return 0


def _active_config_and_name(
    config_path: str | Path,
    *,
    database: ApplicationDatabase,
) -> tuple[AppConfig, str, str]:
    return _active_config_and_name_from_store(
        load_store(config_path, database=database),
        config_path=config_path,
    )


def _active_config_and_name_from_store(store: Any, *, config_path: str | Path | None = None) -> tuple[AppConfig, str, str]:
    if store.data_sources:
        try:
            business_entry = resolve_data_source_entry(store, store.reconcile_data_sources.business_source_id)
            dws_entry = resolve_data_source_entry(store, store.reconcile_data_sources.dws_source_id)
            return (
                AppConfig(
                    dws=resolve_data_source(store, store.reconcile_data_sources.dws_source_id),
                    business=business_entry.config,
                ),
                business_entry.name,
                dws_entry.name,
            )
        except ValueError:
            pass
    for named_config in store.configs:
        if named_config.is_default or named_config.name == store.default_name:
            return AppConfig(dws=named_config.dws, business=named_config.business), named_config.name, f"{named_config.name} - DWS"
    if store.configs:
        named_config = store.configs[0]
        return AppConfig(dws=named_config.dws, business=named_config.business), named_config.name, f"{named_config.name} - DWS"
    fallback_config = default_config()
    return fallback_config, "默认配置", "默认配置 - DWS"


def _data_source_config_lookup(store: Any) -> dict[str, DataSourceConfig]:
    lookup: dict[str, DataSourceConfig] = {}
    for entry in getattr(store, "data_sources", []) or []:
        source_id = str(getattr(entry, "id", "") or "").strip()
        source_name = str(getattr(entry, "name", "") or "").strip()
        if source_id:
            lookup[source_id] = entry.config
        if source_name:
            lookup.setdefault(source_name, entry.config)
    return lookup


def _pbc_import_data_sources(store: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for entry in store.data_sources:
        sources.append({
            "config_name": entry.name,
            "source": "dws" if entry.config.db_type == "postgresql" else "business",
            "label": entry.name,
            "db_type": entry.config.db_type,
            "is_default": bool(entry.is_default),
        })
    return sources


def _db_validation_field_mapping_signature(
    *,
    metadata_source: DataSourceConfig,
    baseinfo_table: str,
    field_info_table: str,
    sys_manage_id: str,
    classification_id: str,
) -> tuple[Any, ...]:
    return (
        metadata_source.db_type,
        metadata_source.host,
        metadata_source.port,
        metadata_source.database,
        metadata_source.schema,
        metadata_source.username,
        metadata_source.password,
        baseinfo_table,
        field_info_table,
        sys_manage_id,
        classification_id,
    )


def _coerce_max_combination_rows(value: Any) -> int:
    if value in (None, ""):
        return 50
    try:
        rows = int(value)
    except (TypeError, ValueError):
        return 50
    return max(1, min(rows, 500))


def _coerce_db_validation_tables(value: Any) -> list[str]:
    if value in (None, "", []):
        return list(ZG_TABLES)
    if not isinstance(value, list):
        raise ValueError("selected_tables must be a list")
    selected: list[str] = []
    seen: set[str] = set()
    for item in value:
        code = str(item or "").strip().upper()
        if not code:
            continue
        if code not in ZG_TABLES:
            raise ValueError(f"unknown db validation table: {code}")
        if code not in seen:
            seen.add(code)
            selected.append(code)
    return selected or list(ZG_TABLES)


def _coerce_request_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def test_connections(config: AppConfig) -> dict[str, dict[str, Any]]:
    return {
        "dws": _test_one_source(DatabaseClient(config.dws)),
        "business": _test_one_source(DatabaseClient(config.business)),
    }


def _test_one_source(client: DatabaseClient) -> dict[str, Any]:
    try:
        client.test_connection()
        return {"ok": True, "message": "连接成功"}
    except Exception as exc:
        return {"ok": False, "message": _connection_error_message(str(exc))}


def _connection_error_message(message: str) -> str:
    text = str(message or "").strip()
    if "\ufffd" in text or _looks_like_mojibake(text):
        return "连接失败：数据库返回错误信息编码异常，请检查用户名、密码、地址和端口"
    detailed = _database_error_message(text)
    if detailed:
        return detailed
    sanitized = sanitize_error_message(text)
    if sanitized != text:
        return sanitized
    return text[:300] or "连接失败：请检查数据库地址、端口、用户名和密码"


def _no_source_report_message(run_date: str) -> str:
    return f"报表对应日期无数据：{run_date}"


def _no_source_report_payload(run_date: str) -> dict[str, Any]:
    return {
        "id": "",
        "run_at": "",
        "run_date": run_date,
        "total_count": 0,
        "added_count": 0,
        "removed_count": 0,
        "baseline_run_at": "",
        "no_source_data": True,
        "message": _no_source_report_message(run_date),
    }


def _runtime_error_message(message: Any) -> str:
    text = str(message or "").strip()
    detailed = _database_error_message(text)
    if detailed:
        return detailed
    if "\ufffd" in text or _looks_like_mojibake(text):
        return "执行失败：数据库返回错误信息编码异常，请检查数据源连接和数据库字符集"
    return sanitize_error_message(text)


def _database_error_message(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        return ""

    unknown_db = re.search(r"Unknown database '([^']+)'", text, re.I)
    if unknown_db:
        database = unknown_db.group(1)
        hint = f"数据库不存在：{database}。"
        if database == "ass_man_reg":
            hint += "当前自动对数规则需要访问 ass_man_reg.ex_pledge_back；请确认报表数据源连接到的 MySQL 实例包含 ass_man_reg 库，或检查地址/端口是否连到了正确实例。"
        else:
            hint += "请确认数据源配置中的库名是否正确，且当前数据库实例已创建该库。"
        return _with_raw_database_error(hint, text)

    pg_missing_db = re.search(r'database "([^"]+)" does not exist', text, re.I)
    if pg_missing_db:
        return _with_raw_database_error(
            f"数据库不存在：{pg_missing_db.group(1)}。请确认数据源配置中的库名是否正确，且当前 PostgreSQL 实例已创建该库。",
            text,
        )

    missing_table = re.search(r"Table '([^']+)' doesn't exist", text, re.I)
    if missing_table:
        return _with_raw_database_error(
            f"数据表不存在：{missing_table.group(1)}。请确认所选数据源连接到了正确实例，并检查该库/模式下是否存在这张表。",
            text,
        )

    pg_missing_relation = re.search(r'relation "([^"]+)" does not exist', text, re.I)
    if pg_missing_relation:
        return _with_raw_database_error(
            f"数据表不存在：{pg_missing_relation.group(1)}。请确认 PostgreSQL schema 配置正确，并检查该 schema 下是否存在这张表。",
            text,
        )

    pg_missing_from = _postgres_table_from_sql_context(text)
    if pg_missing_from and re.search(r"does not exist|不存在|����|UndefinedTable", text, re.I):
        return _with_raw_database_error(
            f"数据表不存在：{pg_missing_from}。请检查表字段配置中的数据源、schema 或物理表名。",
            text,
        )

    missing_column = re.search(r"Unknown column '([^']+)'", text, re.I)
    if missing_column:
        return _with_raw_database_error(
            f"字段不存在：{missing_column.group(1)}。请确认目标表结构与当前规则版本一致，或检查是否连接到了错误版本的数据库。",
            text,
        )

    pg_missing_column = re.search(r'column "([^"]+)" does not exist', text, re.I)
    if pg_missing_column:
        return _with_raw_database_error(
            f"字段不存在：{pg_missing_column.group(1)}。请确认目标表结构与当前规则版本一致，或检查是否连接到了错误版本的数据库。",
            text,
        )

    denied_match = re.search(r"Access denied for user '([^']+)'(?:@'[^']+')?(?: to database '([^']+)')?", text, re.I)
    if denied_match:
        database_text = f"数据库 {denied_match.group(2)}" if denied_match.group(2) else "当前数据源"
        return _with_raw_database_error(
            f"数据库权限不足：用户 {denied_match.group(1)} 无法访问{database_text}。请检查用户名、密码以及该用户的库/表查询权限。",
            text,
        )

    pg_auth = re.search(r'password authentication failed for user "([^"]+)"', text, re.I)
    if pg_auth:
        return _with_raw_database_error(
            f"数据库认证失败：用户 {pg_auth.group(1)} 的密码或认证方式不正确。请检查数据源用户名和密码。",
            text,
        )

    permission = re.search(r"permission denied for (?:table|relation|schema) ([^\s]+)", text, re.I)
    if permission:
        return _with_raw_database_error(
            f"数据库权限不足：当前用户没有访问 {permission.group(1)} 的权限。请联系 DBA 授予查询权限。",
            text,
        )

    if re.search(r"Can't connect to MySQL server|Connection refused|could not connect to server|No route to host", text, re.I):
        return _with_raw_database_error(
            "数据库连接失败：无法连接到配置的地址或端口。请检查数据库服务是否启动、地址端口是否正确、防火墙或网络是否可达。",
            text,
        )

    if re.search(r"Unknown MySQL server host|could not translate host name|Name or service not known", text, re.I):
        return _with_raw_database_error(
            "数据库主机无法解析：请检查数据源中的主机名/IP 是否正确，或当前网络/DNS 是否可用。",
            text,
        )

    if re.search(r"timeout|timed out", text, re.I):
        return _with_raw_database_error(
            "数据库连接或查询超时：请检查网络连通性、数据库负载，或确认查询表数据量是否过大。",
            text,
        )

    if re.search(r"Lost connection|server has gone away|connection already closed", text, re.I):
        return _with_raw_database_error(
            "数据库连接中断：执行过程中连接被数据库或网络断开。请检查数据库稳定性、连接超时设置和网络状态。",
            text,
        )

    if re.search(r"Too many connections", text, re.I):
        return _with_raw_database_error(
            "数据库连接数已满：当前数据库连接过多。请稍后重试或联系 DBA 调整连接数。",
            text,
        )

    return ""


def _with_raw_database_error(prefix: str, raw: str) -> str:
    sanitized = _database_error_excerpt(raw)
    return f"{prefix}原始错误：{sanitized[:180]}"


def _postgres_table_from_sql_context(message: str) -> str:
    text = str(message or "")
    relation = re.search(r'relation "([^"]+)"', text, re.I)
    if relation:
        return relation.group(1)
    from_match = re.search(r'\bFROM\s+((?:"[^"]+"\.){0,2}"[^"]+")', text, re.I)
    if not from_match:
        return ""
    parts = re.findall(r'"([^"]+)"', from_match.group(1))
    return ".".join(parts)


def _database_error_excerpt(raw: str) -> str:
    lines: list[str] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^(LINE\s+\d+:|SELECT\b|FROM\b|WHERE\b|INSERT\b|UPDATE\b|DELETE\b|DROP\b|ALTER\b|CREATE\b|\^)", stripped, re.I):
            continue
        lines.append(stripped)
    text = " ".join(lines) or str(raw or "").strip()
    text = re.sub(r"(?i)(password|passwd|pwd)\s*=\s*[^;\s]+", r"\1=***", text)
    return text[:300] or "数据库错误"


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _looks_like_mojibake(text: str) -> bool:
    if not text:
        return False
    suspicious = sum(text.count(char) for char in ("�", "锛", "绋", "鍛", "鐮", "璇", "鎴", "妫", "€"))
    return suspicious >= 2


def _is_client_disconnect_error(exc: BaseException) -> bool:
    if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        return True
    if not isinstance(exc, OSError):
        return False
    disconnect_codes = {errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, 10053, 10054}
    return getattr(exc, "errno", None) in disconnect_codes or getattr(exc, "winerror", None) in disconnect_codes


class AutoCheckRequestHandler(BaseHTTPRequestHandler):
    router: ApiRouter
    web_dir: Path
    auth_manager: AuthManager

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api("GET")
            return
        self._serve_static()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api("POST")
            return
        self._send_json(404, {"error": "not found"})

    def do_DELETE(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api("DELETE")
            return
        self._send_json(404, {"error": "not found"})

    def do_PUT(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api("PUT")
            return
        self._send_json(404, {"error": "not found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_api(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/auth/"):
            self._handle_auth(method, path)
            return
        session = self._authenticated_session()
        if session is None:
            self._send_json(401, {"error": "login required"})
            return
        if method in {"POST", "PUT", "DELETE"} and self.headers.get("X-CSRF-Token", "") != session.csrf_token:
            self._send_json(403, {"error": "invalid csrf token"})
            return
        if path.startswith("/api/users"):
            self._handle_users(method, path, session)
            return
        if method == "GET" and path.startswith("/api/admin/storage/tables/") and path.endswith("/export"):
            self._handle_storage_table_data_export(path, session)
            return
        if method == "GET" and path == "/api/admin/storage/schema-export":
            self._handle_storage_schema_export(session)
            return
        if method == "POST" and path == "/api/tools/pbc-import/upload":
            self._handle_pbc_import_upload()
            return
        if method == "GET" and path == "/api/tools/db-validation/rules-document":
            self._handle_db_validation_rules_document_download()
            return
        if method == "GET" and path.startswith("/api/tools/db-validation/download/"):
            self._handle_db_validation_download(path)
            return
        if method == "GET" and path.startswith("/api/tools/db-validation/history/download/"):
            self._handle_db_validation_history_download(path)
            return
        body = None
        if method in ("POST", "PUT", "DELETE"):
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw_body or "{}")
        self.router.transport_password_decryptor = self.auth_manager.decrypt_transport_password
        self.router._query_string = self.path.split("?", 1)[1] if "?" in self.path else ""
        status, payload = self.router.handle(method, path, body, current_user=_session_user(session))
        self._send_json(status, payload)

    def _handle_auth(self, method: str, path: str) -> None:
        if method == "GET" and path == "/api/auth/key":
            self._send_json(
                200,
                {
                    "public_key_pem": self.auth_manager.public_key_pem(),
                    "public_key_jwk": self.auth_manager.public_key_jwk(),
                },
            )
            return
        if method == "GET" and path == "/api/auth/status":
            session = self._authenticated_session()
            self._send_json(200, {
                "authenticated": session is not None,
                "setup_required": self.auth_manager.setup_required(),
                "csrf_token": session.csrf_token if session else "",
                "user": _session_user(session),
            })
            return
        if method == "POST" and path in {"/api/auth/setup", "/api/auth/login", "/api/auth/logout"}:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw_body or "{}")
            try:
                if path == "/api/auth/setup":
                    if not self.auth_manager.setup_required():
                        self._send_json(409, {"error": "admin password already configured"})
                        return
                    password = self._encrypted_password_from_body(body)
                    self.auth_manager.set_admin_password(password)
                    session = self.auth_manager.login("admin", password)
                    self._send_auth_session(session)
                    return
                if path == "/api/auth/login":
                    password = self._encrypted_password_from_body(body)
                    username = str(body.get("username", "admin") or "admin")
                    session = self.auth_manager.login(username, password)
                    if session is None:
                        self._send_json(401, {"error": self.auth_manager.login_failure_reason(username, password)})
                        return
                    self._send_auth_session(session)
                    return
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            session = self._authenticated_session()
            if session and self.headers.get("X-CSRF-Token", "") != session.csrf_token:
                self._send_json(403, {"error": "invalid csrf token"})
                return
            if session:
                self.auth_manager.logout(session.session_id)
            self._send_json(200, {"ok": True}, headers=[("Set-Cookie", "auto_check_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")])
            return
        self._send_json(404, {"error": "not found"})

    def _encrypted_password_from_body(self, body: dict[str, Any]) -> str:
        if body.get("password"):
            raise ValueError("encrypted password is required")
        return self.auth_manager.decrypt_transport_password(str(body.get("password_encrypted", "") or ""))

    def _send_auth_session(self, session: AuthSession | None) -> None:
        if session is None:
            self._send_json(500, {"error": "login failed"})
            return
        self._send_json(
            200,
            {"ok": True, "csrf_token": session.csrf_token, "user": _session_user(session)},
            headers=[("Set-Cookie", f"auto_check_session={session.session_id}; Path=/; HttpOnly; SameSite=Lax")],
        )

    def _authenticated_session(self) -> AuthSession | None:
        return self.auth_manager.validate_session(_cookie_value(self.headers.get("Cookie", ""), "auto_check_session"))

    def _handle_users(self, method: str, path: str, session: AuthSession) -> None:
        if session.role != "admin":
            self._send_json(403, {"error": "admin role required"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
        body = json.loads(raw_body or "{}")
        parts = [part for part in path.split("/") if part]
        try:
            if method == "GET" and parts == ["api", "users"]:
                self._send_json(200, {"users": self.auth_manager.list_users()})
                return
            if method == "POST" and parts == ["api", "users"]:
                password = self._encrypted_password_from_body(body)
                user = self.auth_manager.create_user(
                    username=str(body.get("username", "")),
                    display_name=str(body.get("display_name", "")),
                    password=password,
                    role=str(body.get("role", "user")),
                    enabled=bool(body.get("enabled", True)),
                    current_user_id=session.user_id,
                )
                self._send_json(200, {"user": user})
                return
            if len(parts) >= 3 and parts[:2] == ["api", "users"]:
                user_id = parts[2]
                if method == "PUT" and len(parts) == 3:
                    user = self.auth_manager.update_user(
                        user_id,
                        display_name=str(body.get("display_name")) if "display_name" in body else None,
                        role=str(body.get("role")) if "role" in body else None,
                        enabled=bool(body.get("enabled")) if "enabled" in body else None,
                        current_user_id=session.user_id,
                    )
                    self._send_json(200, {"user": user})
                    return
                if method == "POST" and len(parts) == 4 and parts[3] == "reset-password":
                    password = self._encrypted_password_from_body(body)
                    user = self.auth_manager.reset_password(
                        user_id,
                        password,
                        current_user_id=session.user_id,
                        preserve_session_id=session.session_id,
                    )
                    self._send_json(200, {"user": user})
                    return
                if method == "DELETE" and len(parts) == 3:
                    self.auth_manager.delete_user(user_id, current_user_id=session.user_id)
                    self._send_json(200, {"ok": True})
                    return
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(404, {"error": "not found"})

    def _handle_pbc_import_upload(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        boundary = _parse_multipart_boundary(content_type)
        if not boundary:
            self._send_json(400, {"error": "expected multipart/form-data"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)
        file_item = _parse_multipart_file(raw_body, boundary)
        if file_item is None:
            self._send_json(400, {"error": "file is required"})
            return
        status, payload = self.router.handle_pbc_import_upload(file_item["filename"], file_item["data"])
        self._send_json(status, payload)

    def _handle_db_validation_download(self, path: str) -> None:
        job_id = path.rsplit("/", 1)[-1]
        try:
            excel_path, filename = self.router.get_db_validation_download(job_id)
            data = excel_path.read_bytes()
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except FileNotFoundError as exc:
            self._send_json(404, {"error": str(exc)})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self._write_response_body(data)

    def _handle_db_validation_history_download(self, path: str) -> None:
        history_id = path.rsplit("/", 1)[-1]
        try:
            excel_path, filename = self.router.get_db_validation_history_download(history_id)
            data = excel_path.read_bytes()
        except FileNotFoundError as exc:
            self._send_json(404, {"error": str(exc)})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self._write_response_body(data)

    def _handle_db_validation_rules_document_download(self) -> None:
        filename, data = self.router.get_db_validation_rules_document()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self._write_response_body(data)

    def _handle_storage_schema_export(self, session: AuthSession) -> None:
        try:
            filename, data = self.router.get_storage_schema_export(current_user=_session_user(session))
        except PermissionError as exc:
            self._send_json(403, {"error": str(exc)})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self._write_response_body(data)

    def _handle_storage_table_data_export(self, path: str, session: AuthSession) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 6 or parts[:4] != ["api", "admin", "storage", "tables"] or parts[5] != "export":
            self._send_json(404, {"error": "not found"})
            return
        try:
            filename, data = self.router.get_storage_table_data_export(parts[4], current_user=_session_user(session))
        except LookupError as exc:
            self._send_json(404, {"error": str(exc)})
            return
        except PermissionError as exc:
            self._send_json(403, {"error": str(exc)})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self._write_response_body(data)

    def _serve_static(self) -> None:
        relative = self.path.split("?", 1)[0].lstrip("/") or "index.html"
        web_root_path = self.web_dir.resolve()
        target = (web_root_path / relative).resolve()
        try:
            target.relative_to(web_root_path)
        except ValueError:
            self._send_json(404, {"error": "not found"})
            return
        if not target.exists() or not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self._write_response_body(data)

    def _send_json(self, status: int, payload: dict[str, Any], headers: list[tuple[str, str]] | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for name, value in headers or []:
            self.send_header(name, value)
        self.end_headers()
        self._write_response_body(data)

    def _write_response_body(self, data: bytes) -> bool:
        try:
            self.wfile.write(data)
        except OSError as exc:
            if _is_client_disconnect_error(exc):
                return False
            raise
        return True


def _cookie_value(cookie_header: str, name: str) -> str:
    for part in str(cookie_header or "").split(";"):
        key, sep, value = part.strip().partition("=")
        if sep and key == name:
            return value
    return ""


def _session_user(session: AuthSession | None) -> dict[str, Any] | None:
    if session is None:
        return None
    return {
        "id": session.user_id,
        "username": session.username,
        "display_name": session.display_name,
        "role": session.role,
    }


def _public_current_user(user: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(user or {})
    username = str(payload.get("username", ""))
    display_name = str(payload.get("display_name") or username)
    return {
        "id": str(payload.get("id", "")),
        "username": username,
        "display_name": display_name,
    }


def _table_ref_key(table: TableRef) -> tuple[str, ...]:
    return tuple(part.lower() for part in table.parts)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, ReconcileResult):
        payload = to_jsonable(asdict(value))
        payload["display_details"] = build_display_details(value)
        return payload
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    return value


def previous_month_end(today: str | date | None = None) -> str:
    current = _coerce_date(today) if today is not None else beijing_today()
    year = current.year
    month = current.month - 1
    if month == 0:
        year -= 1
        month = 12
    day = monthrange(year, month)[1]
    return date(year, month, day).isoformat()


def build_display_details(result: ReconcileResult) -> list[dict[str, Any]]:
    detail_by_kind = {detail.kind: detail.data for detail in result.details}
    sections: list[dict[str, Any]] = [_final_judgement_section(result, detail_by_kind)]
    for detail in result.details:
        if detail.kind == "fa_am":
            sections.append(_fa_am_section(detail.data))
        elif detail.kind == "am_missing":
            sections.append(_am_missing_section(detail.data))
        elif detail.kind == "project_invest_balance":
            sections.append(_project_invest_balance_section(detail.data))
        elif detail.kind == "property_right_invest":
            sections.append(_property_right_invest_section(detail.data))
        elif detail.kind == "asset_difference_refinement":
            sections.append(_asset_difference_refinement_section(detail.data))
        elif detail.kind == "asset_missing_refinement":
            sections.append(_asset_missing_refinement_section(detail.data))
        elif detail.kind == "asset_duplicate_refinement":
            sections.append(_asset_duplicate_refinement_section(detail.data))
        elif detail.kind == "received_trust" and detail.data.get("refinement_rows"):
            sections.append(_received_trust_refinement_section(detail.data))
        elif detail.kind == "liability_equity" and detail.data.get("rows"):
            sections.append(_liability_equity_refinement_section(detail.data))
        elif detail.data.get("candidate_groups"):
            sections.append(_candidate_groups_section(detail.data))
        elif detail.kind == "ta_total_mismatch":
            sections.append(_ta_total_mismatch_section(detail.data))
        elif detail.kind == "ta_blank_client_type":
            sections.append(_ta_blank_client_type_section(detail.data))
    if result.valuation_match and result.valuation_match.rows and result.valuation_match.match_type != "ambiguous_combination":
        sections.insert(1, _valuation_rows_section(result))
    return sections


def _final_judgement_section(result: ReconcileResult, detail_by_kind: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = [
        {"label": "差异类型", "value": result.difference_reason or "暂无法确定"},
        {"label": "差异金额", "value": str(result.difference)},
        {"label": "差异方向", "value": result.direction},
        {"label": "匹配状态", "value": result.match_status},
    ]
    specific_reason = _specific_reason(result)
    if specific_reason:
        rows.insert(1, {"label": "具体原因", "value": specific_reason})
    if data := detail_by_kind.get("asset_gap"):
        rows.extend([
            {"label": "资负报表资产合计", "value": data.get("zf_asset_total", "")},
            {"label": "估值表资产合计", "value": data.get("valuation_asset_total", "")},
            {"label": "资产差异金额", "value": data.get("asset_gap", "")},
            {"label": "命中方式", "value": _match_type_label(str(data.get("match_type", "")))},
        ])
        if data.get("match_message"):
            rows.append({"label": "匹配说明", "value": data.get("match_message", "")})
    elif data := detail_by_kind.get("received_trust"):
        rows.extend([
            {"label": "c1000 实收本金余额", "value": data.get("c1000_balance", "")},
            {"label": "FA 4001 科目余额", "value": data.get("fa_4001_balance", "")},
            {"label": "4001-c1000 差异", "value": data.get("received_trust_difference", "")},
        ])
        if liability_data := detail_by_kind.get("liability_equity"):
            if liability_data.get("main_difference"):
                rows.append({"label": "主差异", "value": liability_data.get("main_difference", "")})
            if liability_data.get("received_trust_difference"):
                rows.append({"label": "实收差额", "value": liability_data.get("received_trust_difference", "")})
            if liability_data.get("residual_difference"):
                rows.append({"label": "剩余差额", "value": liability_data.get("residual_difference", "")})
            rows.extend([
                {"label": "核对范围", "value": liability_data.get("account_scope", "")},
                {"label": "命中方式", "value": _match_type_label(str(liability_data.get("match_type", "")))},
                {"label": "命中金额", "value": liability_data.get("match_total", "")},
            ])
            if liability_data.get("match_message"):
                rows.append({"label": "匹配说明", "value": liability_data.get("match_message", "")})
    elif data := detail_by_kind.get("liability_equity"):
        rows.extend([
            {"label": "核对范围", "value": data.get("account_scope", "")},
            {"label": "命中方式", "value": _match_type_label(str(data.get("match_type", "")))},
            {"label": "命中金额", "value": data.get("match_total", "")},
        ])
        if data.get("match_message"):
            rows.append({"label": "匹配说明", "value": data.get("match_message", "")})
    elif data := detail_by_kind.get("property_right_invest"):
        rows.extend([
            {"label": "估值1541科目金额合计", "value": data.get("market_total", "")},
            {"label": "AM合同投融资余额合计", "value": data.get("project_invest_total", "")},
            {"label": "投融资-估值差异合计", "value": data.get("difference_total", "")},
            {"label": "判断依据", "value": data.get("basis", "")},
        ])
    if data := detail_by_kind.get("asset_difference_refinement"):
        rows.extend([
            {"label": "资产合计差额(a0001-0004)", "value": data.get("asset_total_gap", "")},
            {"label": "资产差异FA科目余额合计", "value": data.get("market_total", "")},
            {"label": "资产差异DM证券余额/AM投融资余额/存续回购业务表金额合计", "value": data.get("project_invest_total", "")},
            {"label": "资产差异金额合计", "value": data.get("difference_total", "")},
            {"label": "判断依据", "value": data.get("basis", "")},
        ])
        if data.get("remaining_difference") is not None:
            rows.append({"label": "资产端解释后剩余差额", "value": data.get("remaining_difference", "")})
    elif data := detail_by_kind.get("unknown"):
        rows.append({"label": "判断依据", "value": data.get("basis", "已配置规则未命中")})
    if detail_by_kind.get("asset_gap"):
        if data := detail_by_kind.get("received_trust"):
            rows.extend([
                {"label": "c1000 实收本金余额", "value": data.get("c1000_balance", "")},
                {"label": "FA 4001 科目余额", "value": data.get("fa_4001_balance", "")},
                {"label": "4001-c1000 差异", "value": data.get("received_trust_difference", "")},
            ])
        if data := detail_by_kind.get("liability_equity"):
            if data.get("main_difference"):
                rows.append({"label": "主差异", "value": data.get("main_difference", "")})
            if data.get("received_trust_difference"):
                rows.append({"label": "实收差额", "value": data.get("received_trust_difference", "")})
            if data.get("residual_difference"):
                rows.append({"label": "剩余差额", "value": data.get("residual_difference", "")})
            rows.extend([
                {"label": "核对范围", "value": data.get("account_scope", "")},
                {"label": "命中方式", "value": _match_type_label(str(data.get("match_type", "")))},
                {"label": "命中金额", "value": data.get("match_total", "")},
            ])
            if data.get("match_message"):
                rows.append({"label": "匹配说明", "value": data.get("match_message", "")})
    return {"title": "最终判断结果", "description": "", "rows": rows}


def _specific_reason(result: ReconcileResult) -> str:
    for detail in reversed(result.details):
        reason = detail.data.get("specific_reason")
        if reason:
            return str(reason)
    return ""


def _valuation_rows_section(result: ReconcileResult) -> dict[str, Any]:
    assert result.valuation_match is not None
    return {
        "title": "具体差异明细",
        "description": "",
        "table": {
            "headers": ["科目代码", "科目名称", "科目尾段代码", "金额"],
            "rows": [
                [row.account_code, row.account_name, row.account_tail_code, str(row.market_value)]
                for row in result.valuation_match.rows
            ],
        },
    }


def _fa_am_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "标的代码核对",
        "description": "",
        "rows": [
            {"label": "FA 估值科目代码", "value": data.get("fa_account_code", "")},
            {"label": "FA 估值科目名称", "value": data.get("fa_account_name", "")},
            {"label": "FA 科目尾段代码", "value": data.get("fa_tail_code", "")},
            {"label": "FA 科目余额", "value": data.get("fa_market_value", "")},
            {"label": "AM 资产名称", "value": data.get("am_asset_name", "")},
            {"label": "AM 标的代码", "value": data.get("am_stock_code", "")},
            {"label": "AM 合同代码", "value": data.get("pact_id", "")},
            {"label": "判定结果", "value": "FA 科目尾段代码与 AM 标的代码不一致。"},
        ],
    }


def _am_missing_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "AM标的缺失",
        "description": "",
        "rows": [
            {"label": "FA 估值科目代码", "value": data.get("fa_account_code", "")},
            {"label": "FA 估值科目名称", "value": data.get("fa_account_name", "")},
            {"label": "FA 科目尾段代码", "value": data.get("fa_tail_code", "")},
            {"label": "FA 科目余额", "value": data.get("fa_market_value", "")},
            {"label": "需复核四级科目", "value": data.get("expected_account_level", "")},
            {"label": "判定结果", "value": "按科目名称与 AM 资产名称相等/高匹配度规则，未找到对应 AM 标的数据。"},
        ],
    }


def _project_invest_balance_section(data: dict[str, Any]) -> dict[str, Any]:
    balance = str(data.get("project_invest_balance", ""))
    result = (
        "合同投融资余额为0但FA科目余额不为0。"
        if balance == "0"
        else "合同投融资余额非0，继续核查SPV DM表和报表明细。"
    )
    return {
        "title": "合同投融资余额核对",
        "description": "",
        "rows": [
            {"label": "FA 估值科目代码", "value": data.get("fa_account_code", "")},
            {"label": "FA 估值科目名称", "value": data.get("fa_account_name", "")},
            {"label": "FA 科目尾段代码", "value": data.get("fa_tail_code", "")},
            {"label": "FA 科目余额", "value": data.get("fa_market_value", "")},
            {"label": "AM 资产名称", "value": data.get("am_asset_name", "")},
            {"label": "AM 标的代码", "value": data.get("am_stock_code", "")},
            {"label": "AM 合同代码", "value": data.get("pact_id", "")},
            {"label": "合同投融资余额", "value": balance},
            {"label": "判定结果", "value": result},
        ],
    }


def _property_right_invest_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "财产权合同投融资核对",
        "description": "",
        "table": {
            "headers": ["科目代码", "科目名称", "合同代码", "估值金额", "AM合同投融资余额", "差异"],
            "rows": [
                [
                    row.get("account_code", ""),
                    row.get("account_name", ""),
                    row.get("pact_id", ""),
                    row.get("market_value", ""),
                    row.get("project_invest_balance", ""),
                    row.get("difference", ""),
                ]
                for row in data.get("rows", [])
            ],
        },
    }


def _asset_difference_refinement_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "资产差异细分",
        "description": "",
        "table": {
            "headers": ["序号", "资产类型", "资产名称", "FA科目编码", "合同代码/证券代码", "FA科目余额", "DM证券余额/AM投融资余额/存续回购业务表金额", "差异值", "核查表", "原因"],
            "rows": [
                [
                    row.get("index", ""),
                    row.get("asset_type", ""),
                    row.get("asset_name", ""),
                    row.get("account_code", ""),
                    row.get("pact_id", "") or row.get("security_code", ""),
                    row.get("market_value", ""),
                    row.get("project_invest_balance", ""),
                    row.get("difference", ""),
                    row.get("check_table", ""),
                    row.get("reason", ""),
                ]
                for row in data.get("rows", [])
            ],
        },
    }


def _asset_missing_refinement_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "资产缺失细分",
        "description": "",
        "table": {
            "headers": ["序号", "资产类型", "资产名称", "FA科目编码", "科目尾段", "FA估值金额", "核查表", "核查结果", "关键字段", "AM标的代码", "AM合同代码", "原因"],
            "rows": [
                [
                    row.get("index", ""),
                    row.get("asset_type", ""),
                    row.get("asset_name", ""),
                    row.get("fa_account_code", ""),
                    row.get("account_tail", ""),
                    row.get("fa_market_value", ""),
                    row.get("check_table", ""),
                    row.get("check_result", ""),
                    row.get("key_field", ""),
                    row.get("am_stock_code", ""),
                    row.get("pact_id", ""),
                    row.get("reason", ""),
                ]
                for row in data.get("rows", [])
            ],
        },
    }


def _asset_duplicate_refinement_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "资产重复细分",
        "description": "",
        "table": {
            "headers": ["序号", "资产类型", "资产名称", "FA科目编码", "科目尾段", "FA估值金额", "核查表", "核查结果", "关键字段", "AM SPV类型", "AM资产类型", "原因"],
            "rows": [
                [
                    row.get("index", ""),
                    row.get("asset_type", ""),
                    row.get("asset_name", ""),
                    row.get("fa_account_code", ""),
                    row.get("account_tail", ""),
                    row.get("fa_market_value", ""),
                    row.get("check_table", ""),
                    row.get("check_result", ""),
                    row.get("key_field", ""),
                    row.get("am_spv_type", ""),
                    row.get("am_asset_type", ""),
                    row.get("reason", ""),
                ]
                for row in data.get("rows", [])
            ],
        },
    }


def _received_trust_refinement_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "实收本金细分",
        "description": "",
        "table": {
            "headers": ["序号", "类型", "FA 4001科目余额", "c1000实收本金余额", "差异值", "核查表", "核查结果", "原因"],
            "rows": [
                [
                    row.get("index", ""),
                    row.get("type", ""),
                    row.get("fa_4001_balance", ""),
                    row.get("c1000_balance", ""),
                    row.get("difference", ""),
                    row.get("check_table", ""),
                    row.get("check_result", ""),
                    row.get("reason", ""),
                ]
                for row in data.get("refinement_rows", [])
            ],
        },
    }


def _liability_equity_refinement_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "负债及权益科目细分",
        "description": "",
        "table": {
            "headers": ["序号", "科目类型", "科目名称", "FA科目编码", "科目尾段", "FA科目金额", "存续回购业务表金额", "差异方向", "核查结果", "原因"],
            "rows": [
                [
                    row.get("index", ""),
                    row.get("account_type", ""),
                    row.get("account_name", ""),
                    row.get("account_code", ""),
                    row.get("account_tail", ""),
                    row.get("market_value", ""),
                    row.get("business_amount", ""),
                    row.get("direction", ""),
                    row.get("check_result", ""),
                    row.get("reason", ""),
                ]
                for row in data.get("rows", [])
            ],
        },
    }


def _candidate_groups_section(data: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for group in data.get("candidate_groups", []):
        group_index = group.get("index", "")
        group_total = group.get("total", "")
        for row in group.get("rows", []):
            rows.append(
                [
                    group_index,
                    group_total,
                    row.get("account_code", ""),
                    row.get("account_name", ""),
                    row.get("account_tail", ""),
                    row.get("market_value", ""),
                ]
            )
    return {
        "title": "候选组合明细",
        "description": "",
        "table": {
            "headers": ["候选组合", "组内合计", "科目代码", "科目名称", "科目尾段", "金额"],
            "rows": rows,
        },
    }


def _ta_total_mismatch_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "TA汇总核对",
        "description": "",
        "rows": [
            {"label": "DM TA 份额余额+待结转收益", "value": data.get("dm_total", "")},
            {"label": "DWS TA 份额余额+待结转收益", "value": data.get("dws_total", "")},
            {"label": "DM-DWS 差异", "value": data.get("difference", "")},
        ],
    }


def _ta_blank_client_type_section(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "DM TA客户类型为空",
        "description": "",
        "rows": [
            {"label": "客户类型为空金额合计", "value": data.get("blank_client_type_total", "")},
        ],
        "table": {
            "headers": ["合同编号", "客户名称", "客户类型", "客户类型明细", "SPV类型", "待结转收益", "份额余额", "合计"],
            "rows": [
                [
                    row.get("pact_id", ""),
                    row.get("client_name", ""),
                    row.get("client_kind", ""),
                    row.get("client_kind_index", ""),
                    row.get("spv_type", ""),
                    row.get("ht_income", ""),
                    row.get("share_amount", ""),
                    row.get("amount", ""),
                ]
                for row in data.get("rows", [])
            ],
        },
    }


def _match_type_label(match_type: str) -> str:
    labels = {
        "single": "单行金额命中",
        "grouped": "同一科目多行汇总命中",
        "combination": "多个科目组合命中",
        "ambiguous_combination": "候选不唯一",
        "property_right_invest": "1541财产权合同投融资差异命中",
        "combination_overflow": "组合候选过多，未继续穷举",
        "none": "未找到可解释金额的估值科目",
    }
    return labels.get(match_type, match_type or "无")


def _coerce_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_multipart_boundary(content_type: str) -> str:
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            return part[len("boundary="):].strip().strip('"')
    return ""


def _parse_multipart_file(raw_body: bytes, boundary: str) -> dict[str, Any] | None:
    delimiter = f"--{boundary}".encode()
    for part in raw_body.split(delimiter):
        part = part.lstrip(b"\r\n")
        if not part or part.startswith(b"--"):
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        header_section = part[:header_end].decode("utf-8", errors="replace")
        body_bytes = part[header_end + 4:]
        if body_bytes.endswith(b"\r\n"):
            body_bytes = body_bytes[:-2]
        filename = "upload.zip"
        for line in header_section.split("\r\n"):
            if not line.lower().startswith("content-disposition:"):
                continue
            for token in line.split(";"):
                token = token.strip()
                if token.lower().startswith("filename="):
                    filename = token.split("=", 1)[1].strip().strip('"')
                    break
        from io import BytesIO

        return {"filename": filename, "data": BytesIO(body_bytes)}
    return None


def web_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "auto_check" / "web"
    return Path(__file__).resolve().parent.parent / "web"


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_SERVER_PORT,
    open_browser: bool = True,
    config_path: str | Path | None = None,
) -> ThreadingHTTPServer | None:
    class Handler(AutoCheckRequestHandler):
        pass

    Handler.web_dir = web_root()
    browser_host = _browser_host(host)
    url = f"http://{browser_host}:{port}"
    if _is_tcp_port_active(host, port):
        print(f"Auto Check appears to be already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return None

    resolved_config_path = Path(config_path) if config_path is not None else default_config_path()
    application_database = ApplicationDatabase.from_config_path(resolved_config_path)
    try:
        application_database.test_connection()
        application_database.validate_schema()
        try:
            server = ThreadingHTTPServer((host, port), Handler)
        except OSError as exc:
            if _is_port_in_use_error(exc):
                print(f"Auto Check appears to be already running at {url}")
                if open_browser:
                    webbrowser.open(url)
                return None
            raise

        router = ApiRouter(
            config_path=resolved_config_path,
            application_database=application_database,
            start_field_mapping_auto_refresh=True,
        )
        auth_manager = AuthManager(router.config_path, database=application_database)

        Handler.router = router
        Handler.auth_manager = auth_manager
        actual_port = server.server_address[1]
        url = f"http://{browser_host}:{actual_port}"
        print(f"Auto Check running at {url}")
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return server
    finally:
        application_database.close()


def _browser_host(host: str) -> str:
    normalized = str(host or "127.0.0.1")
    if normalized in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return normalized


def _is_tcp_port_active(host: str, port: int) -> bool:
    try:
        normalized_port = int(port)
    except (TypeError, ValueError):
        return False
    if normalized_port <= 0:
        return False
    probe_host = _browser_host(host)
    try:
        with socket.create_connection((probe_host, normalized_port), timeout=0.25):
            return True
    except OSError:
        return False


def _is_port_in_use_error(exc: OSError) -> bool:
    if exc.errno in {errno.EADDRINUSE, 10048}:
        return True
    message = str(exc).lower()
    return "address already in use" in message or "only one usage of each socket address" in message
