"""Regression coverage for slow models, fenced JSON and numeric constants."""
import json
from urllib.error import HTTPError, URLError

import pytest

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import MANIFEST
from auto_check.modules.data_validation.service import DataValidationService
from tests.modules.data_validation.test_ai_service import (
    _generate_payload, _request, _rules_with_doc, _select_payload,
)
from tests.modules.data_validation.support import user


@pytest.mark.parametrize("wrapper", [lambda s: s, lambda s: f"```json\n{s}\n```", lambda s: f"```\n{s}\n```", lambda s: f"```JSON\r\n{s}\r\n```", lambda s: f"结果如下：{s}"])
def test_json_object_and_fences(wrapper):
    raw = json.dumps({"expression": {"right_type": "value", "right": 0}})
    assert DataValidationService._load_json(wrapper(raw))["expression"]["right"] == 0


def test_fence_is_removed_before_json_decode(monkeypatch):
    original = json.loads
    seen = []
    def loads(raw):
        seen.append(raw)
        return original(raw)
    monkeypatch.setattr(json, "loads", loads)
    assert DataValidationService._load_json('```json\n{"right": 0}\n```') == {"right": 0}
    assert len(seen) == 1
    assert seen[0].startswith("{")


@pytest.mark.parametrize("stage_index, expected_stage", [(0, "select_table"), (1, "generate_rule")])
def test_slow_model_can_use_120_seconds_without_retry(stage_index, expected_stage):
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()])
    original = model.complete
    calls = []
    def slow(model_id, messages, *, timeout_seconds):
        calls.append(timeout_seconds)
        if len(calls) - 1 == stage_index and timeout_seconds <= 60:
            raise TimeoutError("sensitive URL must not escape")
        return original(model_id, messages, timeout_seconds=timeout_seconds)
    model.complete = slow
    assert rules.parse_rule_request(user(), _request())["rule_type"] == "field_compare"
    assert calls == [120, 120]


@pytest.mark.parametrize("exc, code", [
    (TimeoutError("secret"), "MODEL_TIMEOUT"),
    (URLError(TimeoutError("secret")), "MODEL_TIMEOUT"),
    (HTTPError("https://secret.invalid", 429, "secret", {}, None), "MODEL_REQUEST_FAILED"),
    (KeyError("choices"), "MODEL_RESPONSE_INVALID"),
    (RuntimeError("down"), "MODEL_UNAVAILABLE"),
])
def test_wrapped_transport_failures_are_classified_and_redacted(exc, code, caplog):
    rules, model = _rules_with_doc([_select_payload()])
    def fail(*args, **kwargs):
        try:
            raise exc
        except Exception as cause:
            raise RuntimeError("MODEL_UNAVAILABLE") from cause
    model.complete = fail
    with pytest.raises(AppError) as caught:
        rules.parse_rule_request(user(), _request())
    assert caught.value.code == code
    assert caught.value.stage == "select_table"
    assert len(caught.value.reference) == 12
    assert "secret" not in caplog.text
    assert caught.value.reference in caplog.text


@pytest.mark.parametrize("raw", ["", "None", "null", "[]", "not json", "{bad}", None])
def test_invalid_model_response_is_not_reported_as_bad_document(raw):
    rules, model = _rules_with_doc([_select_payload()])
    model.complete = lambda *args, **kwargs: raw
    with pytest.raises(AppError) as caught:
        rules.parse_rule_request(user(), _request())
    assert caught.value.code == "MODEL_RESPONSE_INVALID"
    assert caught.value.stage == "select_table"


def test_second_stage_error_has_safe_stage_and_reference_in_api():
    rules, model = _rules_with_doc([_select_payload()])
    original = model.complete
    def fail_second(*args, **kwargs):
        if model.calls:
            raise TimeoutError("password and endpoint must not escape")
        return original(*args, **kwargs)
    model.complete = fail_second
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    response = router.dispatch(ModuleRequest(
        method="POST", path=f"{MANIFEST.api_prefix}/ai/parse-rule", path_params={}, query={},
        body=_request(), current_user={**user(), "capabilities": ["dv.ai_use"]},
    ))
    assert response.status == 400
    error = response.body["error"]
    assert error["code"] == "MODEL_TIMEOUT"
    assert error["stage"] == "generate_rule"
    assert len(error["reference"]) == 12
    assert "password" not in str(response.body)
    assert rules.storage.visible_rules(str(user()["id"])) == []


def test_numeric_zero_candidate_uses_real_field_and_survives_save():
    fields = [("row_id", "编号", "varchar", "Y"), ("amount", "实收信托", "numeric", "")]
    rules, model = _rules_with_doc([
        _select_payload(), _generate_payload(expression={"left": "实收信托", "op": "eq", "right_type": "value", "right": 0}),
    ], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text="实收信托不得为0"))
    assert result["expression"] == {"left": "amount", "op": "eq", "right_type": "value", "right": 0}
    assert "right_type=value" in model.calls[1]["messages"][0]["content"]
    saved = rules.save_draft(user(), {
        **result, "name": result["rule_name"], "business_key": "row_id", "rule_type": "field_compare",
        "null_policy": "skip", "equality_policy": "reject_equal",
    })
    detail = rules.get_rule(user(), saved["id"])
    assert detail["definition"]["expression"]["right"] == 0
    assert ":right_value" in detail["sql_text"]
    from tests.modules.data_validation.support import Metadata
    rules.metadata = Metadata(columns=[
        {"column_name": "row_id", "data_type": "varchar"},
        {"column_name": "amount", "data_type": "numeric"},
        {"column_name": "report_date", "data_type": "date"},
    ])
    tested = rules.run_tests(user(), saved["id"], detail["version_no"])
    assert tested["failed_count"] == 0
    assert tested["passed_count"] >= 4
    from auto_check.modules.data_validation.executor import execute_version
    observed = []
    original_execute = rules.metadata.execute_select
    def execute(source_id, sql, params, **kwargs):
        observed.append(dict(params))
        return original_execute(source_id, sql, params, **kwargs)
    rules.metadata.execute_select = execute
    assert execute_version(detail, {"report_date": "2026-11-17"}, rules.metadata).status == "PASS"
    assert observed[0]["right_value"] == 0


@pytest.mark.parametrize("constant", [0.1, 1e30, -1e30, 1.7976931348623157e308])
@pytest.mark.parametrize("op", ["eq", "neq", "lt", "lte", "gt", "gte"])
def test_finite_float_samples_remain_distinct_and_serializable(constant, op):
    from auto_check.modules.data_validation.test_runner import default_field_compare_cases, evaluate_case
    definition = {"rule_type": "field_compare", "null_policy": "skip", "equality_policy": "allow_equal",
                  "expression": {"left": "amount", "op": op, "right_type": "value", "right": constant}}
    cases = default_field_compare_cases(definition)
    json.dumps(cases, allow_nan=False)
    assert all(evaluate_case(definition, case["row"]) == case["expected_count"] for case in cases)


def test_stored_custom_sql_keeps_bindings_without_requiring_configured_table():
    from types import SimpleNamespace
    from auto_check.modules.data_validation.executor import execute_version
    observed = []
    class Metadata:
        def describe_table(self, *args):
            return {"columns": [{"column_name": "id"}]}
        def execute_select(self, source_id, sql, params, **kwargs):
            observed.append((sql, params))
            return SimpleNamespace(rows=[], truncated=False)
    version = {"definition": {
        "rule_type": "custom_sql", "dialect": "mysql", "params": {"limit_value": 10},
    }, "sql_text": "SELECT :limit_value AS id"}
    assert execute_version(version, {}, Metadata()).status == "PASS"
    assert observed[0][1]["limit_value"] == 10


def test_explicit_field_type_still_detects_legacy_duplicate():
    rules, _ = _rules_with_doc([
        _select_payload(), _generate_payload(expression={"left": "maturity_date", "op": "lt", "right_type": "field", "right": "issue_date"}),
    ])
    rules.save_draft(user(), {
        "name": "既有规则", "description": "", "rule_type": "field_compare",
        "source_id": "src", "dialect": "postgresql", "table_name": "test_table",
        "business_key": "row_id", "violation_message": "期限异常",
        "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
    })
    assert rules.parse_rule_request(user(), _request())["duplicate"]["kind"] == "exact"


@pytest.mark.parametrize("overrides", [
    {"expression": []}, {"expression": {"left": "maturity_date", "op": [], "right": "issue_date"}},
    {"expression": {"left": "maturity_date", "op": "lt", "right_type": {}, "right": "issue_date"}},
    {"null_policy": "invented"}, {"violation_message": {"text": "bad"}},
])
def test_malformed_candidate_is_reported_as_model_response(overrides):
    rules, _ = _rules_with_doc([_select_payload(), _generate_payload(**overrides)])
    with pytest.raises(AppError) as caught:
        rules.parse_rule_request(user(), _request())
    assert caught.value.code == "MODEL_RESPONSE_INVALID"


@pytest.mark.parametrize("value", [True, None, "0", float("nan"), float("inf")])
def test_invalid_numeric_candidate_is_rejected(value):
    rules, _ = _rules_with_doc([
        _select_payload(), _generate_payload(expression={"left": "maturity_date", "op": "eq", "right_type": "value", "right": value}),
    ])
    with pytest.raises(AppError) as caught:
        rules.parse_rule_request(user(), _request())
    assert caught.value.code == "MODEL_RESPONSE_INVALID"
