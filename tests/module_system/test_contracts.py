from __future__ import annotations

import pytest

from auto_check.app.module_system.contracts import (
    ModuleHttpResponse,
    ModuleManifest,
    ModuleManifestError,
)


VALID_MANIFEST = {
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
    "permissions": ["custom_reports.view", "custom_reports.design"],
    "dependencies": [],
    "schema_version": 0,
}


def test_manifest_parses_valid_payload():
    manifest = ModuleManifest.from_mapping(VALID_MANIFEST)

    assert manifest.id == "custom_reports"
    assert manifest.api_prefix == "/api/modules/custom-reports"
    assert manifest.navigation[0].permission == "custom_reports.view"
    assert manifest.schema_version == 0
    assert manifest.table_prefix == "custom_reports_"


def test_manifest_accepts_documented_singular_table_prefix():
    manifest = ModuleManifest.from_mapping(
        {**VALID_MANIFEST, "table_prefix": "custom_report_"}
    )

    assert manifest.table_prefix == "custom_report_"


def test_module_response_keeps_a_verified_wire_snapshot_after_mapping_mutates():
    body = {"top": "before", "nested": {"value": "before"}}

    response = ModuleHttpResponse.json(200, body)
    body["top"] = "after"
    body["nested"]["value"] = "after"

    assert response.wire_body == b'{"top":"before","nested":{"value":"before"}}'


def test_manifest_defaults_services_and_validates_declared_service_namespace_and_version():
    assert ModuleManifest.from_mapping(VALID_MANIFEST).services == ()

    manifest = ModuleManifest.from_mapping(
        {
            **VALID_MANIFEST,
            "services": [{"name": "custom_reports.lookup", "version": 2}],
        }
    )

    assert [(service.name, service.version) for service in manifest.services] == [
        ("custom_reports.lookup", 2)
    ]


@pytest.mark.parametrize(
    "services",
    [
        [{"name": "other.lookup", "version": 1}],
        [{"name": "custom_reports.lookup", "version": 0}],
        [
            {"name": "custom_reports.lookup", "version": 1},
            {"name": "custom_reports.lookup", "version": 2},
        ],
    ],
)
def test_manifest_rejects_invalid_service_declarations(services):
    with pytest.raises(ModuleManifestError):
        ModuleManifest.from_mapping({**VALID_MANIFEST, "services": services})


@pytest.mark.parametrize("table_prefix", ["app_", "app_modules_", "custom_other_", "Other_"])
def test_manifest_rejects_reserved_or_unrelated_table_prefix(table_prefix):
    with pytest.raises(ModuleManifestError, match="table_prefix"):
        ModuleManifest.from_mapping({**VALID_MANIFEST, "table_prefix": table_prefix})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "Custom-Reports", "id"),
        ("platform_api", 2, "platform_api"),
        ("api_prefix", "/api/config", "api_prefix"),
        ("backend_entry", "missing_separator", "backend_entry"),
        ("permissions", ["other.view"], "permission"),
        ("schema_version", -1, "schema_version"),
    ],
)
def test_manifest_rejects_invalid_fields(field, value, message):
    payload = {**VALID_MANIFEST, field: value}

    with pytest.raises(ModuleManifestError, match=message):
        ModuleManifest.from_mapping(payload)


@pytest.mark.parametrize(
    "backend_entry",
    [
        ":factory",
        "package:",
        "package:factory",
        "package..module:factory",
        "package.module:invalid-name",
    ],
)
def test_manifest_rejects_invalid_backend_entry_format(backend_entry):
    payload = {**VALID_MANIFEST, "backend_entry": backend_entry}

    with pytest.raises(ModuleManifestError, match="backend_entry"):
        ModuleManifest.from_mapping(payload)
