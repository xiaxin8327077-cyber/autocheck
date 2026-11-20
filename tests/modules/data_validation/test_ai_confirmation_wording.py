from auto_check.modules.data_validation.business_display import business_key_option
from auto_check.modules.data_validation.query_grounding import bind_model_join
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload


BASE_FIELDS = [
    {"field_name": "c_projinnercode", "field_cn": "项目内部编号", "data_type": "varchar"},
    {"field_name": "report_date", "field_cn": "报送日期", "data_type": "date"},
]
RELATED_FIELDS = [
    {"field_name": "c_projinnercode", "field_cn": "项目内部编号", "data_type": "varchar"},
    {"field_name": "report_date", "field_cn": "报送日期", "data_type": "date"},
]


def _question(candidate, key):
    return next(item for item in candidate["questions"] if item["id"] == key)


def _join(**overrides):
    join = {"table_name": "related_report", "on": [{"left": "c_projinnercode", "right": "c_projinnercode"}]}
    join.update(overrides)
    return join


def test_join_relationship_question_uses_documented_chinese_fields_and_report_date():
    candidate = {"target": {"table": "base_report"}}
    bind_model_join(candidate, _join(), BASE_FIELDS, RELATED_FIELDS)

    question = _question(candidate, "join.relationship_confirmed")
    option = question["options"][0]
    assert question["text"] == "是否按以下方式找到同一报送日期的对应信息？"
    assert "项目内部编号" in option["label"] and "同一报送日期" in option["label"]
    assert "↔" not in option["label"] and "c_projinnercode" not in option["label"]
    assert "base_report.c_projinnercode ↔ related_report.c_projinnercode" in option["description"]
    assert "同一报送日期" in option["description"]
    # 只改文案：真实关联键和待用户确认的状态均保持不变。
    assert option["selection"]["on"] == [{"left": "c_projinnercode", "right": "c_projinnercode"}]
    assert candidate["join"]["relationship_confirmed"] is False
    assert candidate["join"]["unmatched_policy"] == "unresolved"


def test_join_question_uses_resolved_business_objects_when_available():
    candidate = {'table_name_cn': '余额明细（balances.ktr）', 'related_table_name_cn': '项目信息（projects.ktr）'}
    bind_model_join(candidate, _join(), BASE_FIELDS, RELATED_FIELDS)
    question = _question(candidate, 'join.relationship_confirmed')
    assert '项目信息' in question['text']
    assert '余额明细' in question['options'][0]['label']
    assert '主表' not in question['options'][0]['label']
    assert '.ktr' not in question['options'][0]['label'] and '.ktr' not in question['text']
    assert '项目信息' in _question(candidate, 'join.unmatched_policy')['text']


def test_documented_join_still_auto_confirms_without_business_questions():
    documented = _join(relationship_confirmed=True, unmatched_policy="exclude", report_date_field="report_date")
    candidate = {"filters": [{"confirmed": True}]}
    assert bind_model_join(candidate, documented, BASE_FIELDS, RELATED_FIELDS, documented_join=documented) is True
    assert candidate["join"] == documented
    assert "questions" not in candidate


def test_unmatched_policy_explains_skipped_records_are_not_treated_as_passed():
    candidate = {}
    bind_model_join(candidate, _join(), BASE_FIELDS, RELATED_FIELDS)

    question = _question(candidate, "join.unmatched_policy")
    option = question["options"][0]
    assert question["text"] == "本次检查的信息找不到同一报送日期的对应信息时，本次怎么处理？"
    assert option["value"] == "exclude"
    assert "暂不检查" in option["label"] and "不能视为通过" in option["label"]
    assert "另行核查" in option["description"] and "不代表符合要求" in option["description"]


def test_sum_join_marks_missing_rows_as_pending_review_not_pass():
    candidate = {}
    bind_model_join(candidate, _join(right_aggregate="sum"), BASE_FIELDS, RELATED_FIELDS)

    option = _question(candidate, "join.unmatched_policy")["options"][0]
    assert option["value"] == "review"
    assert "待核查" in option["label"] and "不能视为通过" in option["label"]
    assert "列为待核查" in option["description"]


def test_business_key_option_explains_which_record_is_located_without_changing_value():
    option = business_key_option("c_projinnercode", "项目")
    assert option["value"] == "c_projinnercode"
    assert option["label"] == "项目"
    assert "哪条记录" in option["description"]
    assert "不改变校验条件" in option["description"]
    assert "c_projinnercode" in option["description"]


def test_parse_uses_business_locator_wording_when_document_key_is_missing():
    fields = [("c_projinnercode", "项目", "varchar", ""), ("c_prodcode", "产品", "varchar", ""),
              ("c_pactcode", "合同", "varchar", ""), ("report_date", "报送日期", "date", "")]
    draft = _generate_payload(expression={"left": "c_projinnercode", "op": "is_null"})
    rules, _model = _rules_with_doc([_select_payload(), draft], fields=fields)

    result = rules.parse_rule_request(user(), _request(request_text="项目内部编号不能为空"))

    question = next(item for item in result["questions"] if item["id"] == "business_key")
    assert question["text"] == "核查结果里，用哪个编号方便你查找记录？"
    option = next(item for item in question["options"] if item["value"] == "c_projinnercode")
    assert option["label"] == "项目"
    assert "定位" in option["description"] and "不改变校验条件" in option["description"]
    assert result["business_key"] == ""


def test_composite_identifier_choices_do_not_include_unrelated_status_flags():
    fields = [('ticket', '单号', 'varchar', 'Y'), ('segment', '分段序号', 'int', 'Y'),
              ('green_flag', '绿色领域标识', 'varchar', ''), ('report_date', '报送日期', 'date', '')]
    rules, _ = _rules_with_doc([_select_payload(), _generate_payload(expression={'left': 'ticket', 'op': 'is_null'})],
                               fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text='单号不得为空'))
    question = next(q for q in result['questions'] if q['id'] == 'business_key')
    assert {o['value'] for o in question['options']} == {'ticket', 'segment'}
