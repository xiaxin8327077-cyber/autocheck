from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
from typing import Any

from auto_check.app.module_system.contracts import ModuleHealth, ModuleManifest

from .api import register_routes
from .history import (
    HISTORY_PROVIDER_ID,
    HISTORY_SEMANTICS_VERSION,
    ConfirmedHistoryProvider,
)
from .service import SpecialProcessingService
from .statistics import SEMANTICS_VERSION, SpecialHandlingStatistics
from .storage import SpecialProcessingStorage
from .todos import PROVIDER_ID, SEMANTICS_VERSION as TODO_SEMANTICS_VERSION, PendingConfirmTodoProvider


def _manifest() -> ModuleManifest:
    payload = json.loads(
        resources.files(__package__).joinpath("manifest.json").read_text(encoding="utf-8")
    )
    return ModuleManifest.from_mapping(payload)


MANIFEST = _manifest()


@dataclass
class ReportSpecialProcessingModule:
    manifest: ModuleManifest = field(default=MANIFEST)
    _service: SpecialProcessingService | None = field(default=None, init=False, repr=False)
    _provider_handle: Any = field(default=None, init=False, repr=False)
    _todo_provider_handle: Any = field(default=None, init=False, repr=False)
    _history_provider_handle: Any = field(default=None, init=False, repr=False)

    def register_routes(self, router: Any) -> None:
        register_routes(router, self._require_service)

    def register_schema(self, registry: Any) -> None:
        registry.add(
            "report_special_processing_records",
            {
                "id", "record_no", "report_process_code", "report_process_name_snapshot",
                "report_period", "dimension", "summary", "table_name", "field_name",
                "value_before", "value_after", "processing_content", "processing_script",
                "script_sha256", "status", "special_handling_at", "handler_user_id",
                "handler_username_snapshot", "handler_display_name_snapshot",
                "governance_owner_user_id", "governance_owner_username_snapshot",
                "governance_owner_display_name_snapshot", "creator_user_id",
                "creator_username_snapshot", "created_at", "updated_by_user_id",
                "updated_by_username_snapshot", "updated_at", "completed_at", "voided_at",
                "voided_by_user_id", "void_reason", "workflow_status", "workflow_instance_id",
                "workflow_version", "row_version",
            },
        )
        registry.add(
            "report_special_processing_reports",
            {"id", "record_id", "sequence_no", "report_name", "report_name_normalized", "created_at"},
        )
        registry.add(
            "report_special_processing_processes",
            {
                "id", "record_id", "sequence_no", "report_process_code",
                "report_process_name_snapshot", "created_at",
            },
        )
        registry.add(
            "report_special_processing_audit_logs",
            {
                "id", "record_id", "record_no_snapshot", "action_code", "operator_user_id",
                "operator_username_snapshot", "operator_display_name_snapshot", "occurred_at",
                "from_status", "to_status", "changed_fields_json", "action_summary", "request_id",
            },
        )

    def start(self, context: Any) -> None:
        user_directory = context.services.resolve("platform.user_directory", 1)
        report_navigation = context.services.resolve("platform.report_navigation", 1)
        notification_publisher = context.services.resolve("platform.notification", 1)
        storage = SpecialProcessingStorage(context.application_database)

        def role_label_resolver() -> dict[str, str]:
            from auto_check.app.storage_role_definitions import load_role_definitions

            mapping: dict[str, str] = {}
            with context.application_database.connect() as connection:
                for item in load_role_definitions(connection):
                    display_name = str(item.get("display_name") or "").strip()
                    role_code = str(item.get("role_code") or "").strip()
                    if display_name and role_code:
                        mapping[display_name] = role_code
            return mapping

        self._service = SpecialProcessingService(
            storage,
            user_directory,
            report_navigation,
            now=context.now,
            role_label_resolver=role_label_resolver,
            notification_publisher=notification_publisher,
        )
        try:
            storage.backfill_processes_from_records()
        except Exception:
            pass
        provider = SpecialHandlingStatistics(storage, now=context.now)
        self._provider_handle = report_navigation.register_card_provider(
            card_code="special_governance",
            provider=provider,
            semantics_version=SEMANTICS_VERSION,
            include_in_collect=False,
            refresh_on_dashboard=True,
        )
        self._todo_provider_handle = report_navigation.register_todo_provider(
            provider_id=PROVIDER_ID,
            provider=PendingConfirmTodoProvider(storage),
            semantics_version=TODO_SEMANTICS_VERSION,
        )
        self._history_provider_handle = report_navigation.register_history_provider(
            provider_id=HISTORY_PROVIDER_ID,
            provider=ConfirmedHistoryProvider(storage),
            semantics_version=HISTORY_SEMANTICS_VERSION,
        )

    def stop(self) -> None:
        history_handle = self._history_provider_handle
        todo_handle = self._todo_provider_handle
        handle = self._provider_handle
        self._history_provider_handle = None
        self._todo_provider_handle = None
        self._provider_handle = None
        self._service = None
        if history_handle is not None:
            history_handle.close()
        if todo_handle is not None:
            todo_handle.close()
        if handle is not None:
            handle.close()

    def health(self) -> ModuleHealth:
        return ModuleHealth(healthy=self._service is not None)

    def _require_service(self) -> SpecialProcessingService:
        if self._service is None:
            raise RuntimeError("module service is unavailable")
        return self._service


def create_module() -> ReportSpecialProcessingModule:
    return ReportSpecialProcessingModule()
