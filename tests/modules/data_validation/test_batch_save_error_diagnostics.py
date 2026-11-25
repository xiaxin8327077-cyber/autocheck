import logging
import re
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.exc import DataError

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.diagnostic_logging import start_diagnostics, stop_diagnostics
from auto_check.modules.data_validation.module import MANIFEST
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _rules_with_doc


def _post_batch(rules, payload):
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    return router.dispatch(ModuleRequest(
        method="POST", path=MANIFEST.api_prefix + "/ai/candidates/batch-save", path_params={}, query={},
        body=payload, current_user={**user(), "capabilities": ["dv.manage"]},
    ))


def test_batch_save_lost_receipt_is_traceable_and_same_key_retry_reuses_commit(monkeypatch, caplog, tmp_path):
    rules, _ = _rules_with_doc([])
    payload = {"request_key": str(uuid4()), "definitions": [{
        "name": "private-request-body", "rule_type": "field_compare", "source_id": "src",
        "dialect": "mysql", "table_name": "test_table", "business_key": "row_id",
        "report_date_field": "issue_date", "violation_message": "期限异常",
        "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
    }]}
    latest_version = rules.storage.latest_version

    def fail_post_commit(*args):
        raise DataError("SELECT private-sql", ("private-parameter",), ValueError(1406, "private-connection-secret"))

    monkeypatch.setattr(rules.storage, "latest_version", fail_post_commit)
    monkeypatch.setenv("AUTO_CHECK_ANALYSIS_LOG_DIR", str(tmp_path))
    handler = start_diagnostics(SimpleNamespace(config_path=tmp_path / "app.json", logger=logging.getLogger(__name__)))
    try:
        response = _post_batch(rules, payload)
        assert response.status == 500
        error = response.body["error"]
        assert isinstance(error, dict), "batch save must return a module error with a reference"
        assert error["code"] == "BATCH_SAVE_RESULT_UNKNOWN"
        assert error["stage"] == "batch_save"
        assert re.fullmatch(r"[0-9a-f]{12}", error["reference"])
        diagnostic = (tmp_path / "analysis.log").read_text(encoding="utf-8")
        for log in (diagnostic, caplog.text):
            assert f"reference={error['reference']}" in log
            assert "stage=batch_save" in log and "type=DataError" in log
            assert "driver_code=1406" in log
            assert re.search(r"test_batch_save_error_diagnostics\.py:\d+", log)
        for public_output in (str(response.body), diagnostic, caplog.text):
            assert "private-" not in public_output
            assert payload["request_key"] not in public_output
            assert str(tmp_path) not in public_output

        monkeypatch.setattr(rules.storage, "latest_version", latest_version)
        recovered = _post_batch(rules, payload)
        assert recovered.status == 200
        assert recovered.body["data"]["reused"] is True
        assert len(rules.storage.visible_rules("1")) == 1
    finally:
        stop_diagnostics(handler)


def test_batch_save_validation_error_retains_status_and_code(caplog):
    rules, _ = _rules_with_doc([])
    response = _post_batch(rules, {"request_key": str(uuid4()), "definitions": []})
    assert response.status == 400
    assert response.body == {"error": {"code": "VALIDATION_ERROR", "message": "VALIDATION_ERROR"}}
    assert "stage=batch_save" not in caplog.text
