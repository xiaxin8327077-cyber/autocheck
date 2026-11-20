from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.prompt_defaults import SEMANTIC_OUTPUT_CONTRACT
from auto_check.modules.data_validation.semantic_generation import _execution_signature
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_semantic_generation import draft
from tests.modules.data_validation.test_frontend_multi_behavior import copy_web_modules
from tests.modules.data_validation.test_model_output_budget import analysis_with_usage


MEASURES = [
    ("temperature", "温度"), ("pressure", "压力"), ("flow_rate", "流量"), ("voltage", "电压"),
    ("humidity", "湿度"), ("speed", "转速"), ("vibration", "振幅"), ("current_reading", "电流"),
    ("density", "密度"),
]


def device_plans(count, *, duplicate=False, variant=None):
    measures = MEASURES[:count]
    fields = [("row_id", "设备编号", "varchar", "Y"), ("business_day", "数据日期", "date", ""),
              *[(name, label, "numeric", "") for name, label in measures]]
    plans = []
    for name, label in measures:
        plan = draft(name, rule_name=f"{label}低于阈值", business_key="row_id", equality_policy="allow_equal")
        plan["semantic_intent"]["metrics"][0]["term"] = label
        plans.append(plan)
    if duplicate or variant:
        plans[-1] = deepcopy(plans[0])
        if duplicate == "alias" or variant:
            plans[-1]["rule_name"] = "设备温度低于阈值"
            plans[-1]["violation_message"] = "请核实设备温度"
            plans[-1]["semantic_intent"]["metrics"][0]["term"] = "设备温度"
        if variant == "scope":
            plans[-1]["filters"] = [{"table": "base", "field": "row_id", "op": "eq", "value": "T1"}]
        elif variant == "threshold":
            plans[-1]["expression"]["right"] = 9
        elif variant == "null_policy":
            plans[-1]["null_policy"] = "review"
        elif variant == "numeric_form":
            plans[-1]["expression"]["right"] = float(plans[0]["expression"]["right"])
        elif variant == "filter_order":
            filters = [{"table": "base", "field": "row_id", "op": "neq", "value": code} for code in ("01", "02")]
            plans[0]["filters"] = filters
            plans[-1]["filters"] = list(reversed(filters))
        elif variant in ("all", "any"):
            for index, sequence in ((0, (0, 1)), (-1, (1, 0))):
                plans[index]["expression"] = {"logic": variant, "conditions": [
                    {"left": measures[i][0], "op": "lt", "right_type": "value", "right": 19} for i in sequence]}
                plans[index]["semantic_intent"]["metrics"] = [
                    {"side": "left", "condition_index": j, "term": measures[i][1], "fields": [measures[i][0]]}
                    for j, i in enumerate(sequence)]
    rules, model = _rules_with_doc([_select_payload(), {"plan_mode": "parallel", "plans": plans}], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text="、".join(label for _, label in measures) + "分别低于19时提醒",
                                                       analysis_protocol=2))
    return rules, model, result


@pytest.mark.parametrize("count", [4, 8])
def test_independent_device_measures_arrive_together_and_can_be_tested_and_saved(count):
    rules, _, result = device_plans(count)
    options = result["candidate_options"]
    assert len(options) == len({option["id"] for option in options}) == count
    definitions = [option["candidate"]["preview"]["definition"] for option in options]
    assert [definition["expression"]["left"] for definition in definitions] == [name for name, _ in MEASURES[:count]]
    for definition in definitions:
        sample = rules.test_candidate(user(), {"definition": definition})
        assert sample["passed_count"] and sample["failed_count"] == sample["not_run_count"] == 0
    result = rules.batch_save_candidates(user(), {"definitions": definitions, "request_key": str(uuid.uuid4())})
    assert result["count"] == count


@pytest.mark.parametrize(("count", "duplicate"), [(9, False), (4, True), (4, "alias")])
def test_excess_or_identical_plans_are_not_published_as_independent_rules(count, duplicate):
    if count > 8:
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            device_plans(count)
        return
    try:
        _, _, result = device_plans(count, duplicate=duplicate)
    except AppError as exc:
        assert exc.code == "MODEL_RESPONSE_INVALID"
    else:
        options = result["candidate_options"]
        assert len(options) == len({option["candidate"]["expression"]["left"] for option in options}) == count - 1


def test_rule_and_suggestion_capacity_are_independent():
    assert "最多8份草稿" in SEMANTIC_OUTPUT_CONTRACT
    assert "最多3条有业务价值的独立补充校验" in SEMANTIC_OUTPUT_CONTRACT


@pytest.mark.parametrize("variant", ["numeric_form", "filter_order", "all", "any"])
def test_equivalent_ready_predicates_do_not_produce_separately_saveable_options(variant):
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        device_plans(4, variant=variant)


def test_signature_preserves_literal_types_exact_values_and_group_logic():
    def signature(value):
        return _execution_signature({"expression": {"left": "reading", "op": "eq", "right": value}})
    assert signature(1) == signature(1.0)
    assert len({signature(v) for v in [1, True, "1", "01", 10**32, 10**32 + 1]}) == 6
    parts = [{"left": field, "op": "is_null"} for field in ("reading", "threshold")]
    assert _execution_signature({"expression": {"logic": "any", "conditions": parts}}) != (
        _execution_signature({"expression": {"logic": "all", "conditions": parts}}))


@pytest.mark.parametrize("op", ["in", "not_in"])
def test_membership_signature_sorts_only_the_comparison_copy(op):
    def definition(codes):
        return {"filters": [{"table": "base", "field": "code", "op": op, "value": codes}]}
    original = definition(["02", "01"])
    assert _execution_signature(original) == _execution_signature(definition(["01", "02"]))
    assert _execution_signature(original) != _execution_signature(definition(["1", "02"]))
    assert original["filters"][0]["value"] == ["02", "01"]


@pytest.mark.parametrize("variant", ["scope", "threshold", "null_policy"])
def test_same_operand_with_different_execution_semantics_keeps_each_rule(variant):
    _, _, result = device_plans(4, variant=variant)
    definitions = [option["candidate"]["preview"]["definition"] for option in result["candidate_options"]]
    assert len(definitions) == 4 and definitions[0]["expression"]["left"] == definitions[-1]["expression"]["left"]
    key = {"scope": "filters", "threshold": "expression", "null_policy": "null_policy"}[variant]
    assert definitions[0][key] != definitions[-1][key]


def test_eight_plans_still_share_the_existing_output_budget():
    analysis, calls = analysis_with_usage([9000, 1000])
    plans = [draft("amount") for _ in range(8)]
    for i, plan in enumerate(plans):
        plan["expression"]["right"] = i + 1
    analysis.preserve_plan_group({"plan_mode": "parallel", "plans": plans}, {"target": {"table": "test_table"}})
    analysis.call("生成计划", "generate_rule")
    analysis.call("修复结构", "repair_rule")
    with pytest.raises(AppError, match="ANALYSIS_OUTPUT_LIMIT"):
        analysis.call("额度已用完", "repair_rule")
    assert [call["options"]["max_tokens"] for call in calls] == [9216, 1000]


@pytest.mark.skipif(not shutil.which("node"), reason="需要 Node.js 验证工作台")
def test_four_cards_reach_batch_save_with_their_own_test_hashes(tmp_path):
    rules, _, result = device_plans(4)
    copy_web_modules(tmp_path)
    scenario = shutil.copy(Path(__file__).with_name("frontend_plan_capacity.mjs"), tmp_path)
    shutil.copy(Path(__file__).with_name("frontend_workbench_dom.mjs"), tmp_path)
    fixture = tmp_path / "four.json"
    fixture.write_text(json.dumps(result), encoding="utf-8")
    run = subprocess.run(["node", scenario, fixture], cwd=tmp_path, encoding="utf-8", capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    for sample in data["samples"]:
        tested = rules.test_candidate(user(), sample)
        assert tested["passed_count"] and not tested["failed_count"] and not tested["not_run_count"]
    saved = rules.batch_save_candidates(user(), data["batch"])
    hashes = {rules.storage.latest_version(row["id"])["content_sha256"] for row in saved["rules"]}
    assert len(hashes) == 4 and hashes == {p["expected_hash"] for p in data["samples"]}
