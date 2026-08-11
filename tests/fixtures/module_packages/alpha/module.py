from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from auto_check.app.module_system.contracts import ModuleHealth, ModuleManifest


CALLS: list[str] = []


@dataclass
class AlphaModule:
    calls: list[str] = field(default_factory=lambda: CALLS)
    manifest: ModuleManifest = field(
        default_factory=lambda: ModuleManifest.from_mapping(
            {
                "id": "alpha",
                "name": "Alpha",
                "version": "1.0.0",
                "platform_api": 1,
                "required": False,
                "backend_entry": "module_packages.alpha.module:create_module",
                "api_prefix": "/api/modules/alpha",
                "frontend_entry": "/module-assets/alpha/index.js",
                "frontend_style": "/module-assets/alpha/styles.css",
                "navigation": [
                    {
                        "id": "alpha",
                        "label": "Alpha",
                        "route": "alpha",
                        "order": 10,
                        "permission": "alpha.view",
                    }
                ],
                "permissions": ["alpha.view"],
                "dependencies": [],
                "schema_version": 2,
            }
        )
    )

    def register_routes(self, router: Any) -> None:
        return None

    def register_schema(self, registry: Any) -> None:
        registry.add("alpha_items", {"id", "note"})

    def start(self, context: Any) -> None:
        self.calls.append("alpha:start")

    def stop(self) -> None:
        self.calls.append("alpha:stop")

    def health(self) -> ModuleHealth:
        return ModuleHealth(healthy=True)


def create_module() -> AlphaModule:
    return AlphaModule()
