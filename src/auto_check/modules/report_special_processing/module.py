from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
from typing import Any

from auto_check.app.module_system.contracts import ModuleHealth, ModuleManifest

from .api import register_routes
from .service import SpecialProcessingService
from .statistics import SEMANTICS_VERSION, SpecialHandlingStatistics
from .storage import SpecialProcessingStorage


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

    def register_routes(self, router: Any) -> None:
        register_routes(router, self._require_service)

    def register_schema(self, registry: Any) -> None:
        registry.add(
            "report_special_processing_records",
            {
                "id", "record_no", "report_process_code", "report_process_name_snapshot",
                "report_period", "summary", "processing_content", "processing_script",
                "script_sha256", "status", "special_handling_at", "handler_user_id",
                "handler_username_snapshot", "handler_display_name_snapshot", "creator_user_id",
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
        storage = SpecialProcessingStorage(context.application_database)
        self._service = SpecialProcessingService(
            storage, user_directory, report_navigation, now=context.now
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

    def stop(self) -> None:
        handle = self._provider_handle
        self._provider_handle = None
        self._service = None
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
