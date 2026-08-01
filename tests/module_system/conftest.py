from __future__ import annotations

import pytest

from auto_check.app.module_system.contracts import ModuleManifest


@pytest.fixture
def valid_manifest() -> ModuleManifest:
    return ModuleManifest.from_mapping(
        {
            "id": "custom_reports",
            "name": "自定义报表",
            "version": "1.0.0",
            "platform_api": 1,
            "required": False,
            "backend_entry": "auto_check.modules.custom_reports.module:create_module",
            "api_prefix": "/api/modules/custom-reports",
            "frontend_entry": "/module-assets/custom_reports/index.js",
            "frontend_style": "/module-assets/custom_reports/styles.css",
            "navigation": [
                {
                    "id": "custom-reports",
                    "label": "自定义报表",
                    "route": "custom-reports",
                    "order": 60,
                    "permission": "custom_reports.view",
                }
            ],
            "permissions": ["custom_reports.view", "custom_reports.publish"],
            "dependencies": [],
            "schema_version": 0,
        }
    )
