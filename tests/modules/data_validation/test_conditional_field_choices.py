import pytest

from auto_check.modules.data_validation.query_grounding import check_request_coverage, ground_candidate_query


FIELDS = [
    {"field_name": "method", "field_cn": "运行方式", "data_type": "varchar",
     "dictionary": "【D8】\n1-开放式净值型\n2-开放式非净值型\n3-封闭式净值型\n4-封闭式非净值型",
     "logic": "直接取项目表的类型[method]。"},
    {"field_name": "method_orig", "field_cn": "运行方式_原始", "data_type": "varchar",
     "dictionary": "【D8】\n1-开放式净值型\n2-开放式非净值型\n3-封闭式净值型\n4-封闭式非净值型",
     "logic": "直接取项目表的类型[method]。"},
    {"field_name": "unit_metric", "field_cn": "单位净值", "data_type": "numeric"},
    {"field_name": "total_metric", "field_cn": "累计净值", "data_type": "numeric"},
    {"field_name": "date_value", "field_cn": "净值日期", "data_type": "date"},
]
REQUEST = "项目运行方式为净值型时，项目的净值不得为空"
SELECT = [
    "需求未明确“净值”具体指单位净值（unit_metric）还是累计净值（total_metric），待确认。",
    "净值型运行方式对应的method具体码值未在文档中给出，需核对字典D8或相关码值。",
    "project_report与other_report均含运行方式字段，但仅project_report有净值字段，故选该表；若选other_report有关联净值字段需另行确认。",
]
GENERATE = [
    "需求未明确“净值”具体指单位净值（unit_metric）还是累计净值（total_metric），当前按单位净值生成规则，待用户确认。",
    "method字段的字典码值已由D8确认，但需确认是否以该字段为准（存在method_orig同值，不影响）。",
]
FILTER = {"table": "base", "field": "method", "op": "in", "value": ["1", "3"], "confirmed": True}


@pytest.mark.parametrize("caption", ["运行方式_原始", "项目运行方式（原始）"])
def test_model_scope_is_verified_against_qualified_document_label(caption):
    from auto_check.modules.data_validation.query_grounding import field_profiles

    fields = [FIELDS[0], {**FIELDS[1], "field_cn": caption}, *FIELDS[2:]]
    request = "项目原始运行方式为净值型时，累计净值不得为空"
    candidate = {"expression": {"left": "total_metric", "op": "is_null"}, "questions": [],
                 "uncertainties": ["原始运行方式中净值型的具体码值需确认"]}
    draft = {"filters": [{"table": "base", "field": "method_orig", "op": "in", "value": [1, 3]}]}
    ground_candidate_query(candidate, draft, fields, [], request)
    assert candidate["filters"] == [{**FILTER, "field": "method_orig"}]
    assert not candidate["uncertainties"] and not candidate["questions"]
    assert not check_request_coverage({**candidate, "description": request}, fields, [])
    assert check_request_coverage({**candidate, "description": request, "filters": [FILTER]}, fields, [])
    hints = field_profiles([{"id": 1, "table_name": "sample"}], {1: fields}, request)
    assert "1=开放式净值型" in hints and "3=封闭式净值型" in hints


def test_unrelated_dictionary_qualifier_and_prior_period_do_not_satisfy_current_request():
    fields = [{**FIELDS[1], "field_cn": "合同运行方式（原始）"},
              {**FIELDS[3], "field_cn": "上期累计净值"}]
    request = "项目原始运行方式为净值型时，累计净值不得为空"
    definition = {"expression": {"left": "total_metric", "op": "is_null"}, "description": request,
                  "filters": [{**FILTER, "field": "method_orig"}]}
    assert check_request_coverage(definition, fields, [])
    fields[0] = {**fields[0], "field_cn": "项目运行方式（原始）"}
    assert check_request_coverage(definition, fields, [])


def generate(fields=FIELDS, reviews=(), request=REQUEST, selection=SELECT):
    candidate = {"uncertainties": [*selection, *GENERATE, *reviews], "questions": [],
                 "expression": {"left": "unit_metric", "op": "is_null"}}
    draft = {"target": {"table": "project_report"}, "filters": [
        {"field": "method", "op": "in", "value": [1, 3]}]}
    ground_candidate_query(candidate, draft, fields, [], request)
    return candidate


def test_confirm_real_measure_choices_without_reopening_proven_document_questions():
    candidate = generate()
    assert candidate["filters"] == [FILTER]
    assert not candidate.get("preview_error")
    assert len(candidate["questions"]) == 1
    question = candidate["questions"][0]
    assert question["id"] == "expression.left"
    assert [item["value"] for item in question["options"]] == ["unit_metric", "total_metric"]
    assert candidate["uncertainties"] == [SELECT[2], question["uncertainty"]]
    for field in ["unit_metric", "total_metric"]:
        definition = {"description": REQUEST, "filters": [FILTER], "expression": {"op": "is_null", "left": field}}
        assert not check_request_coverage(definition, FIELDS, [])
        assert check_request_coverage({**definition, "filters": []}, FIELDS, [])
        assert check_request_coverage({**definition, "filters": [{**FILTER, "value": ["1","2"]}]}, FIELDS, [])
        assert check_request_coverage({**definition, "expression": {"left": field, "op": "is_not_null"}}, FIELDS, [])
        assert check_request_coverage({**definition, "expression": {"left": "date_value", "op": "is_null"}}, FIELDS, [])


def test_scoped_nonempty_check_keeps_date_and_currency_reviews():
    candidate = generate(reviews=["需确认是否按月末截止。", "若有其他维度还需换算币种。"])
    assert "需确认是否按月末截止。" in candidate["uncertainties"]
    assert "若有其他维度还需换算币种。" in candidate["uncertainties"]
    assert generate(request=REQUEST + "，仅核对月末数据").get("preview_error")


def test_resolving_a_dictionary_clause_keeps_the_month_end_clause_before_sql(monkeypatch):
    from tests.modules.data_validation.test_ai_service import _request
    from tests.modules.data_validation.test_conditional_candidate_options import REQUEST as phrase, _conditional_rules
    from tests.modules.data_validation.support import user

    rules, model = _conditional_rules()
    model.payloads[0]["uncertainties"] = ["原始运行方式中净值型的具体码值需确认；另需确认是否仅在月末核对。"]
    monkeypatch.setattr(rules, "preview_candidate", lambda *_a, **_k: pytest.fail("月末口径未确认"))
    result = rules.parse_rule_request(user(), _request(request_text=phrase))
    for candidate in [result, *(o["candidate"] for o in result["candidate_options"])]:
        assert any("另需确认是否仅在月末核对" in note for note in candidate["uncertainties"])
        assert not any("具体码值" in note for note in candidate["uncertainties"])
        assert not candidate.get("preview")


@pytest.mark.parametrize("dictionary", ["【D8】", "1-开放式净值型\n1-普通型", "1-开放式非净值型", "1-开放式净值型\n3 未提供说明"])
def test_incomplete_or_conflicting_dictionary_blocks_preview(dictionary):
    fields = [{**FIELDS[0], "dictionary": dictionary}, *FIELDS[1:]]
    candidate = generate(fields)
    assert candidate.get("preview_error")
    assert check_request_coverage({"description": REQUEST, "filters": [FILTER],
                                   "expression": candidate["expression"]}, fields, [])


def test_unrelated_dictionary_and_measure_use_the_same_request_grounding():
    fields = [{"field_name": "partner_class", "field_cn": "客户类别", "data_type": "int",
               "dictionary": "10-境内机构\n11-境外机构\n12-境内非机构"},
              {"field_name": "id_code", "field_cn": "登记编号", "data_type": "varchar"}]
    request = "客户类别为机构时，登记编号不能为空"
    candidate = {"expression": {"left": "id_code", "op": "is_null"}, "questions": [], "uncertainties": []}
    ground_candidate_query(candidate, {}, fields, [], request)
    assert candidate["filters"] == [{"table": "base", "field": "partner_class", "op": "in",
                                     "value": [10,11], "confirmed": True}]
    assert not check_request_coverage({**candidate, "description": request}, fields, [])
    assert check_request_coverage({**candidate, "description": request + "，但还要排除特殊对象"}, fields, [])


def test_existing_structured_question_absorbs_the_same_review_without_hiding_independent_issue():
    fields = [
        {"field_name": "book_amount", "field_cn": "账面余额", "data_type": "decimal"},
        {"field_name": "available_amount", "field_cn": "可用余额", "data_type": "decimal"},
    ]
    question = {"id": "expression.left", "text": "这里的余额指什么？",
                "options": [{"value": f["field_name"], "label": f["field_cn"]} for f in fields]}
    candidate = {"questions": [question], "uncertainties": [
        "需求未明确余额指账面余额（book_amount）还是可用余额（available_amount）。另需确认币种。"],
        "expression": {"left": "book_amount", "op": "lt", "right_type": "value", "right": 0}}
    ground_candidate_query(candidate, {}, fields, [], "余额不得小于0")
    assert candidate["questions"] == [question]
    assert candidate["uncertainties"] == ["另需确认币种", question["text"]]
    assert question["uncertainty"] == question["text"]


def test_multiple_documented_scope_fields_give_confirmable_filters():
    fields = [FIELDS[0], {**FIELDS[0], "field_name": "variant", "dictionary": "7-净值型"}, *FIELDS[2:]]
    candidate = generate(fields)
    question = next(q for q in candidate["questions"] if q["id"] == "filters.0")
    selections = [option["selection"] for option in question["options"]]
    assert selections == [FILTER, {"field": "variant", "table": "base", "op": "eq", "value": "7", "confirmed": True}]
    assert not candidate.get("preview_error")
    assert not candidate["filters"][0]["confirmed"]
    for selection in selections:
        assert not check_request_coverage({**candidate, "description": REQUEST, "filters": [selection]}, fields, [])


@pytest.mark.parametrize("phrase", ["净值型项目的累计净值不得为空", "净值型项目，累计净值不能为空"])
def test_business_category_shorthand_checks_model_proposal_against_all_documented_fields(phrase):
    proposed = {"field": "method_orig", "op": "in", "value": [3, 1]}
    candidate = {"expression": {"left": "total_metric", "op": "is_null"}, "questions": [], "uncertainties": []}
    ground_candidate_query(candidate, {"filters": [proposed]}, FIELDS, [], phrase, dimension="项目")
    question, = candidate["questions"]
    assert question["id"] == "filters.0" and not candidate["filters"][0]["confirmed"]
    assert {item["selection"]["field"] for item in question["options"]} == {"method", "method_orig"}
    assert [item["selection"]["field"] for item in question["options"] if item.get("tag") == "模型建议"] == ["method_orig"]
    for option in question["options"]:
        assert option["selection"]["value"] == ["1", "3"]
        assert not check_request_coverage({**candidate, "description": phrase, "filters": [option["selection"]]},
                                          FIELDS, [], dimension="项目")
    assert check_request_coverage({**candidate, "description": phrase, "filters": []}, FIELDS, [], dimension="项目")


def test_live_model_restatements_are_resolved_but_an_independent_date_check_stays_open():
    from auto_check.modules.data_validation.generation_policy import review_ready

    fields = [*FIELDS, {"field_name": "unit_day", "field_cn": "单位净值日期", "data_type": "date"},
              {"field_name": "total_day", "field_cn": "累计净值日期", "data_type": "date"}]
    raw_notes = [
        "净值字段需明确是单位净值unit_metric还是累计净值total_metric，或两者均需非空",
        "运行方式字段需确认使用method还是method_orig，且'净值型'对应的码值未在文档中提供",
        "是否需要关联净值日期（unit_day/total_day）进行非空判断，文档未明确",
        "净值字段可能指单位净值unit_metric或累计净值total_metric，当前规则使用单位净值，请确认是否也需检查累计净值",
        "运行方式字段method与method_orig取数逻辑相同，当前使用method",
    ]
    question = {"id": "expression.left", "text": "这里的净值指哪个字段？", "options": [
        {"value": "unit_metric", "label": "单位净值"}, {"value": "total_metric", "label": "累计净值"}]}
    candidate = {"questions": [question], "uncertainties": [*raw_notes],
                 "expression": {"left": "unit_metric", "op": "is_null"}}
    draft = {"target": {"table": "project_report"}, "filters": [{"field": "method", "op": "in", "value": [1,3]}]}
    ground_candidate_query(candidate, draft, fields, [], REQUEST)
    assert len(candidate["questions"]) == 1 and candidate["questions"][0]["options"] == question["options"]
    assert candidate["uncertainties"] == [raw_notes[2], question["text"]]
    assert candidate["filters"] == [FILTER]
    for answer in question["options"]:
        definition = {**candidate, "questions": [], "uncertainty_resolutions": ["", answer["label"]],
                      "description": REQUEST, "expression": {"left": answer["value"], "op": "is_null"}}
        assert not check_request_coverage(definition, fields, [])
        assert not review_ready(definition)
        definition["uncertainty_resolutions"][0] = "本次只核对净值，日期另设规则"
        assert review_ready(definition)

    fallback = generate(reviews=["缺少净值型码值，无法筛选。", "净值可能包含单位和累计两种指标。"])
    assert [item["value"] for item in fallback["questions"][0]["options"]] == ["unit_metric", "total_metric"]
