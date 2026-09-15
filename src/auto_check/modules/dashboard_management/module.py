from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
from typing import Any

from auto_check.app.module_system.contracts import ModuleHealth, ModuleManifest

from .api import register_routes
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

    def register_routes(self, router: Any) -> None:
        register_routes(router, self._require_service)

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

    def start(self, context: Any) -> None:
        self._storage = DashboardManagementStorage(context.application_database)
        self._storage.seed_builtin_catalog()
        self._service = DashboardManagementService(self._storage, now=context.now)

    def stop(self) -> None:
        self._service = None
        self._storage = None

    def health(self) -> ModuleHealth:
        return ModuleHealth(healthy=self._service is not None)

    def _require_service(self) -> DashboardManagementService:
        if self._service is None:
            raise RuntimeError("module service is unavailable")
        return self._service


def create_module() -> DashboardManagementModule:
    return DashboardManagementModule()
