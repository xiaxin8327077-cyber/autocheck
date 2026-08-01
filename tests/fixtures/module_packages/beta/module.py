from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from auto_check.app.module_system.contracts import ModuleHealth, ModuleManifest


CALLS: list[str] = []


@dataclass
class BetaModule:
    calls: list[str] = field(default_factory=lambda: CALLS)
    manifest: ModuleManifest = field(
        default_factory=lambda: ModuleManifest.from_mapping(
            {
                "id": "beta",
                "name": "Beta",
                "version": "1.0.0",
                "platform_api": 1,
                "required": False,
                "backend_entry": "module_packages.beta.module:create_module",
                "api_prefix": "/api/modules/beta",
                "frontend_entry": "/module-assets/beta/index.js",
                "frontend_style": "/module-assets/beta/styles.css",
                "navigation": [
                    {
                        "id": "beta",
                        "label": "Beta",
                        "route": "beta",
                        "order": 20,
                        "permission": "beta.view",
                    }
                ],
                "permissions": ["beta.view"],
                "dependencies": ["alpha"],
                "schema_version": 0,
            }
        )
    )

    def register_routes(self, router: Any) -> None:
        return None

    def register_schema(self, registry: Any) -> None:
        return None

    def start(self, context: Any) -> None:
        self.calls.append("beta:start")

    def stop(self) -> None:
        self.calls.append("beta:stop")

    def health(self) -> ModuleHealth:
        return ModuleHealth(healthy=True)


def create_module() -> BetaModule:
    return BetaModule()
