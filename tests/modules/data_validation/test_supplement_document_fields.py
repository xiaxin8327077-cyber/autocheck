import json
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis


# Shapes of the two 2026-11-23 gateway proposals: a same-field two-bound comparison
# and a three-field null comparison. The first comparison is only a default choice.
@pytest.mark.parametrize("bounded", [True, False], ids=["two-bounds", "three-null-fields"])
def test_supplement_sees_every_main_option_and_the_separately_documented_period_field(bounded):
    main = ["f_netvalue", "f_totalnetvalue", "f_start_totalnetvalue"]
    initial = "f_initial_nav"
    labels = ["单位净值", "累计净值", "期初累计净值", "当期新发项目初始净值"]
    rows = ([{"left": main[0], "op": op, "right_type": "value", "right": value} for op, value in [("gt", 1), ("lt", 0)]]
            if bounded else [{"left": name, "op": "is_null"} for name in main])
    metrics = [{"condition_index": i, "side": "left", "term": "净值", "fields": main if bounded else [row["left"]]}
               for i, row in enumerate(rows)]
    candidate = {
        "table_name": "projects", "report_category": "market", "report_category_name": "市场报表",
        "expression": {"logic": "any", "conditions": rows},
        "semantic_intent": {"metrics": metrics, "scopes": [], "open_questions": []},
        "columns": [{"column_name": name, "field_cn": label, "data_type": "numeric", "logic": f"文档取值：{label}。"}
                    for name, label in zip([*main, initial, "misc"], [*labels, "其他指标"])],
    }
    prompts = []
    def capture(prompt, stage):
        prompts.append(prompt)
        assert stage == "supplement_suggestions"
        return {"ai_suggestions": [], "no_suggestion_reason": "原文限定的对象不在此期间范围。"}

    prefix = "已确认主规则候选为 " + "、".join(main) + "；独立期间建议使用 " + initial + "，仅适用于当期新发项目。"
    model = SimpleNamespace(prefix=prefix, prompts={"business_scope": prefix}, inputs={"source":{"name":"监管样例来源"}}, request="净值不得大于1或小于0" if bounded else "净值不得为空",
                            round_number=2, output_tokens_used=1000, call=capture)
    assert SemanticAnalysis.supplement_suggestions(model, [candidate]) == []
    prompt, = prompts
    summary, = json.loads(prompt.split("主规则及文档依据：", 1)[1])
    assert summary["expression"] == candidate["expression"]
    assert "监管样例来源" in prompt and summary["report_category"] == "market" and summary["report_category_name"] == "市场报表"
    assert summary["main_metric_bindings"] == metrics
    assert summary["policy_field_evidence"] == [{
        "table_name": "projects", "field_name": initial, "label": labels[-1],
        "data_type": "numeric", "logic": "文档取值：当期新发项目初始净值。",
    }]
    assert "category=period" in prompt and "单一" in prompt


def test_supplement_can_verify_reverse_scope_and_independent_cross_grain_check():
    scopes = [{"category": "参与清算", "table": "related", "fields": ["flag"],
               "memberships": {"flag": {"include": ["A"], "exclude": ["B"]}}}]
    scope_col = {"column_name": "flag", "field_cn": "清算类别", "dictionary": "A=参与；B=未参与"}
    def candidate(table, field, label):
        return {"table_name": table, "expression": {"left": field, "op": "lt", "right_type": "value", "right": 0},
                "semantic_intent": {"metrics": [{"term": label, "side": "left", "fields": [field]}]},
                "columns": [{"column_name": field, "field_cn": label, "logic": f"业务别名：{label}。定义：实际清算量。",
                             "source_field": "raw_" + field, "data_type": "numeric"}]}
    detail = candidate("entries", "qty", "流水清算数量")
    detail["semantic_intent"]["scopes"] = scopes
    detail.update(join={"table_name": "ledgers"}, related_columns=[scope_col])
    ledger = candidate("ledgers", "total", "台账清算总量")
    prompts = []
    policy = "同时核对流水清算数量之和与台账清算总量；未参与清算而数量大于0应单独核查。"
    model = SimpleNamespace(prefix=policy, prompts={"business_scope":policy},
                            inputs={"source":{"name":"清算"}},
                            request="已参与清算的数量不得为负", round_number=2, output_tokens_used=200,
                            call=lambda prompt, stage: prompts.append(prompt) or {"ai_suggestions": []})
    SemanticAnalysis.supplement_suggestions(model, [detail, ledger])
    prompt, = prompts
    details, ledger = json.loads(prompt.split("主规则及文档依据：", 1)[1])
    assert details["main_scope_bindings"] == scopes
    fields = {f["field_name"]: f for f in details["references"] + ledger["references"]}
    assert fields["flag"]["dictionary"] == scope_col["dictionary"]
    assert fields["qty"]["source_field"] == "raw_qty" and fields["total"]["source_field"] == "raw_total"
    assert "反向" in prompt and "汇总" in prompt


@pytest.mark.parametrize("custom_scope", [False, True])
def test_related_scope_only_adds_one_supplement_call_for_enabled_business_policy(custom_scope):
    from tests.modules.data_validation.test_ai_latency_pipeline import run
    from tests.modules.data_validation.test_documented_ambiguity_fast_review import valid_alternative, warehouse, warehouse_draft

    plan = valid_alternative(warehouse_draft())
    plan["business_key"] = "piece_id"
    plan["join"].update(relationship_confirmed=True, unmatched_policy="exclude")
    plan["semantic_intent"]["metrics"][0]["term"] = "测量容积"
    reply = {"target": plan.pop("target"), "related_target": plan.pop("related_target"), "draft": plan}
    rules, model = warehouse([reply, plan, plan, plan])
    if custom_scope:
        from auto_check.modules.data_validation.prompt_defaults import DEFAULT_PROMPTS
        rules.storage.save_prompt("business_scope", DEFAULT_PROMPTS["business_scope"] +
                                  "\n本次测量容积检查可另核查非在途包裹的容积。", "test")
    complete = model.complete_with_options
    def respond(model_id, messages, **kwargs):
        if "本轮只提出独立补充校验建议" in messages[0]["content"]:
            model.payloads[len(model.calls):] = [{"ai_suggestions": []}]
        return complete(model_id, messages, **kwargs)
    model.complete_with_options = respond
    result = run(rules, "在途且优先级高于3的包裹清单的测量容积应大于0")
    assert result["table_name"] == "pieces" and result["join"]["table_name"] == "test_table"
    assert not result.get("candidate_options")
    assert sum("本轮只提出独立补充校验建议" in c["messages"][0]["content"] for c in model.calls) == int(custom_scope)
