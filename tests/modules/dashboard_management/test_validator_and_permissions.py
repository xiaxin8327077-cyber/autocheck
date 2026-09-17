from __future__ import annotations


def test_dashboard_permissions_map_to_platform_capabilities():
    from auto_check.app.module_system.permissions import default_permission_evaluator

    assert not default_permission_evaluator(None, "dashboard_management.view")
    assert default_permission_evaluator(
        {"role": "user", "capabilities": ["sys.dashboard_management"]},
        "dashboard_management.view",
    )
    assert not default_permission_evaluator(
        {"role": "user", "capabilities": ["sys.dashboard_management"]},
        "dashboard_management.manage",
    )
    assert default_permission_evaluator(
        {"role": "user", "capabilities": ["sys.dashboard_management.manage"]},
        "dashboard_management.manage",
    )
    assert default_permission_evaluator(
        {
            "role": "user",
            "capabilities": ["sys.dashboard_management.external_api_token_manage"],
        },
        "dashboard_management.external_api_token_manage",
    )


def test_validator_exposes_all_six_supported_field_types():
    from auto_check.modules.dashboard_management.validator import FIELD_VALUE_TYPES

    assert FIELD_VALUE_TYPES == frozenset({"string", "integer", "decimal", "boolean", "date", "datetime"})
