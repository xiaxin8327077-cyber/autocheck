from copy import deepcopy

import pytest

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.module import MANIFEST
from auto_check.modules.data_validation.project_driver import DRIVER_VERSION
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_project_driver_binding import make_rules, semantic_draft


@pytest.fixture(params=[1, 2], ids=["saved-v1", "saved-v2"])
def stored_rule(request):
    rules, _ = make_rules([
        {"target": {"table": "asset_rows"}, "report_category": "pbc_central"}, semantic_draft(),
    ])
    owner = {**user(), "capabilities": ["dv.manage", "dv.view"]}
    result = rules.parse_rule_request(owner, _request(
        request_text="收益转让标识为是的项目，资产收益权余额应大于0", analysis_protocol=2,
    ))
    original = deepcopy(result["preview"]["definition"])
    original["project_driver"]["version"] = request.param
    original["semantic_intent"]["expected_project_driver"]["version"] = request.param
    rule_id = rules.save_draft(owner, original)["id"]
    first = rules.storage.latest_version(rule_id)
    rules.storage.set_status(rule_id, "enabled", first["id"])
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    detail = rules.get_rule(owner, rule_id)

    def save(edited):
        return router.dispatch(ModuleRequest(
            method="PUT", path=f"{MANIFEST.api_prefix}/rules/{rule_id}", path_params={}, query={},
            body={**edited, "expected_rule": {key: detail[key] for key in (
                "version_no", "content_sha256", "status", "current_version_id",
            )}}, current_user=owner,
        ))

    return rules, rule_id, first, save


@pytest.mark.parametrize("submitted_version", [1, 2, DRIVER_VERSION], ids=["editor-copy", "v2-copy", "regenerated"])
def test_saving_new_version_upgrades_only_the_draft_compiler(stored_rule, submitted_version):
    rules, rule_id, first, save = stored_rule
    edited = deepcopy(first["definition"])
    edited["name"] += "（复核）"
    edited["project_driver"]["version"] = submitted_version
    history = rules.list_rule_history(user(), rule_id)["items"]

    response = save(edited)
    assert response.status == 200, response.body
    second = rules.storage.latest_version(rule_id)
    assert second["version_no"] == 2 and second["status"] == "draft"
    old_intent = first["definition"]["semantic_intent"]
    marker = {"version": DRIVER_VERSION, "table_role": "related"}
    assert second["definition"]["project_driver"] == marker
    assert second["definition"]["semantic_intent"] == {**old_intent, "expected_project_driver": marker}
    assert ("dv_duplicate_project" in first["sql_text"]) == (first["definition"]["project_driver"]["version"] == 1)
    assert "dv_duplicate_project" not in second["sql_text"]
    assert "LEFT JOIN" in first["sql_text"] and "INNER JOIN" in second["sql_text"]
    assert first["content_sha256"] != second["content_sha256"]
    assert rules.storage.get_version(rule_id, 1) == first
    assert rules.storage.get_rule(rule_id)["current_version_id"] == first["id"]
    assert rules.list_rule_history(user(), rule_id)["items"][1:] == history


@pytest.mark.parametrize("tamper", ["role", "metric", "filter", "locator", "boolean_version"])
def test_legacy_driver_edit_rechecks_server_intent_and_role(stored_rule, tamper):
    rules, rule_id, first, save = stored_rule
    edited = deepcopy(first["definition"])
    edited["project_driver"]["version"] = 2
    intent = edited["semantic_intent"]
    if tamper == "role":
        edited["project_driver"]["table_role"] = "base"
    elif tamper == "metric":
        edited["expression"]["right"] = 10
        intent["expected_expression"] = deepcopy(edited["expression"])
    elif tamper == "filter":
        edited["filters"] = []
        intent.update(scopes=[], explicit_filters=[], dictionary_snapshots={})
    elif tamper == "locator":
        edited["business_key"] = "other_amount"
    else:
        edited["project_driver"]["version"] = True
    intent["expected_project_driver"] = dict(edited["project_driver"])

    assert save(edited).status == 400
    assert rules.storage.latest_version(rule_id) == first
    assert rules.storage.get_rule(rule_id)["current_version_id"] == first["id"]
