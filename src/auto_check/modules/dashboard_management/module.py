from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
from typing import Any

from auto_check.app.module_system.contracts import ModuleHealth, ModuleManifest

from .api import register_routes
from .external_api_access import DashboardExternalApiAccessService
from .external_api_credentials import DashboardExternalApiCredentialService
from .external_api_monitoring import ExternalApiMonitoringService, ExternalApiMonitoringStore
from .service import DashboardManagementService
from .storage import DashboardManagementStorage


def _manifest() -> ModuleManifest:
    payload = json.loads(resources.files(__package__).joinpath("manifest.json").read_text(encoding="utf-8"))
    return ModuleManifest.from_mapping(payload)


MANIFEST = _manifest()


@dataclass
class DashboardManagementModule:
    manifest: ModuleManifest = field(default=MANIFEST)
    _storage: DashboardManagementStorage | None = field(default=None, init=False, repr=False)
    _service: DashboardManagementService | None = field(default=None, init=False, repr=False)
    _monitoring_service: ExternalApiMonitoringService | None = field(default=None, init=False, repr=False)
    _credential_service: DashboardExternalApiCredentialService | None = field(default=None, init=False, repr=False)
    _access_service: DashboardExternalApiAccessService | None = field(default=None, init=False, repr=False)

    def register_routes(self, router: Any) -> None:
        register_routes(
            router,
            self._require_service,
            self._require_monitoring_service,
            self._credential_service_if_available,
            self._access_service_if_available,
        )

    def _credential_service_if_available(self) -> Any:
        return self._credential_service

    def _access_service_if_available(self) -> Any:
        return self._access_service

    def register_schema(self, registry: Any) -> None:
        registry.add("dashboard_management_regions", {
            "id", "board_code", "region_code", "name", "shape", "built_in", "enabled",
            "system_supported", "default_mode", "display_order", "description", "created_at",
            "updated_at", "row_version",
        })
        registry.add("dashboard_management_fields", {
            "id", "region_id", "field_alias", "name", "value_type", "nullable", "built_in",
            "enabled", "display_order", "description", "created_at", "updated_at", "row_version",
        })
        registry.add("dashboard_management_source_configs", {
            "region_id", "source_mode", "datasource_id", "sql_text", "tested_signature", "tested_at",
            "tested_by", "created_at", "updated_at", "row_version",
        })
        registry.add("dashboard_management_year_snapshots", {
            "id", "region_id", "period_year", "period_type", "period_value", "row_json",
            "source_refreshed_at", "created_at", "updated_at",
        })
        registry.add("dashboard_management_external_api_calls", {
            "id", "called_at", "board_code", "http_status", "result_status",
            "failed_region_count", "duration_ms", "request_id", "caller_ip",
            "error_code", "error_message",
        })
        registry.add("dashboard_management_external_api_credentials", {
            "scope_key", "token_digest", "token_fingerprint",
            "created_by", "created_at", "updated_by", "updated_at",
        })
        registry.add("dashboard_management_external_api_access_policies", {
            "scope_key", "whitelist_enabled", "allowed_ips_json",
            "created_by", "created_at", "updated_by", "updated_at",
        })

    def start(self, context: Any) -> None:
        self._storage = DashboardManagementStorage(context.application_database)
        self._storage.seed_builtin_catalog()
        self._service = DashboardManagementService(self._storage, now=context.now)
        status_facade = context.services.resolve("platform.external_api_status", 2)
        self._monitoring_service = ExternalApiMonitoringService(
            ExternalApiMonitoringStore(context.application_database),
            status_facade=status_facade,
            logger=context.logger,
        )
        self._credential_service = DashboardExternalApiCredentialService(
            context.application_database,
            status_facade,
        )
        self._access_service = DashboardExternalApiAccessService(context.application_database)

    def stop(self) -> None:
        self._access_service = None
        self._credential_service = None
        self._monitoring_service = None
        self._service = None
        self._storage = None

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            healthy=self._service is not None
            and self._monitoring_service is not None
            and self._credential_service is not None
            and self._access_service is not None,
        )

    def _require_service(self) -> DashboardManagementService:
        if self._service is None:
            raise RuntimeError("module service is unavailable")
        return self._service

    def _require_monitoring_service(self) -> ExternalApiMonitoringService:
        if self._monitoring_service is None:
            raise RuntimeError("module monitoring service is unavailable")
        return self._monitoring_service

    def _require_credential_service(self) -> DashboardExternalApiCredentialService:
        if self._credential_service is None:
            raise RuntimeError("module credential service is unavailable")
        return self._credential_service


def create_module() -> DashboardManagementModule:
    return DashboardManagementModule()
