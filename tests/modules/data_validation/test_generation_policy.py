import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.generation_policy import shortlist_tables
from tests.modules.data_validation.support import Metadata, loan_definition, service, user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload


def test_render_replaces_template_placeholders_once_not_user_data():
    from auto_check.modules.data_validation.service import DataValidationService
    result = DataValidationService._render("需求:{request_text} 字段:{fields}", {"request_text": "含{fields}字样", "fields": "amount|金额"})
    assert result == "需求:含{fields}字样 字段:amount|金额"


def test_table_after_first_eighty_is_retrieved_by_name_scope_and_description():
    tables = [{"table_name": f"misc_{i}", "table_name_cn": "其他业务"} for i in range(100)]
    target = {"table_name": "trust_project", "table_name_cn": "项目信息", "scope": "存续项目", "source_desc": "实收信托余额"}
    tables.append(target)
    selected = shortlist_tables(tables, "存续项目实收信托一般不为0", 80)
    assert selected[0] == target
    assert len(selected) == 80
    assert selected == shortlist_tables(tables, "存续项目实收信托一般不为0", 80)
    assert shortlist_tables(tables[:2], "任意需求", 80) == tables[:2]


def test_service_can_select_a_document_table_beyond_initial_window():
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()])
    original = rules.storage.doc_tables
    def many_tables(*args, **kwargs):
        real = original(*args, **kwargs)
        return [{**real[0], "table_name": f"misc_{index}", "table_name_cn": "其他业务", "source_desc": "无关"} for index in range(100)] + real
    rules.storage.doc_tables = many_tables
    result = rules.parse_rule_request(user(), _request(request_text="test_table到期日期不得早于发放日期"))
    assert result["table_name"] == "test_table"
    assert "test_table" in model.calls[0]["messages"][0]["content"]
    assert any("按需求相关性" in item for item in result["uncertainties"])


def test_two_stages_merge_legacy_and_current_questions_and_unsupported_requirements():
    rules, model = _rules_with_doc([
        _select_payload(uncertainty="同名对象需核对范围", uncertainties=["核对单位"], unsupported_requirements=["需额外状态筛选"]),
        _generate_payload(uncertainties=["核对单位", "空值含义未知"], unsupported_requirements=[]),
    ])
    result = rules.parse_rule_request(user(), _request())
    assert result["uncertainties"] == ["核对单位", "同名对象需核对范围", "空值含义未知"]
    assert result["unsupported_requirements"] == ["需额外状态筛选"]
    assert result["can_enable"] is False
    assert "同名对象需核对范围" in model.calls[1]["messages"][0]["content"]


def test_scope_and_exception_qualifiers_cannot_silently_disappear():
    rules, _ = _rules_with_doc([_select_payload(), _generate_payload()])
    result = rules.parse_rule_request(user(), _request(request_text="存续项目实收信托一般不为0"))
    assert any("存续" in item for item in result["uncertainties"])
    assert any("例外" in item for item in result["notices"])
    assert not any("一般" in item for item in result["uncertainties"]), "一般作为待核实提醒，不强迫填写处理说明"
    assert not result["can_enable"]


@pytest.mark.parametrize("selection", [
    {"target": {}, "uncertainties": ["未找到唯一目标表"]},
    {"target": {}, "unsupported_requirements": ["需要跨库匹配"]},
])
def test_ambiguous_selection_returns_clarification_without_second_call(selection):
    rules, model = _rules_with_doc([selection])
    result = rules.parse_rule_request(user(), _request())
    assert result["status"] == "needs_clarification"
    assert result["rule_type"] is None and not result["can_enable"]
    assert len(model.calls) == 1
    assert rules.storage.visible_rules("1") == []


def test_unclassified_rule_continues_generation_without_blocking_business_analysis():
    rules, model = _rules_with_doc([
        {"target": {"table": "test_table"}, "uncertainties": ["无法确定分类"]}, _generate_payload(),
    ])
    result = rules.parse_rule_request(user(), _request())
    assert result["rule_type"] == "field_compare" and result["report_category"] == ""
    assert result["notices"] == ["无法确定分类"]
    assert len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []


def test_empty_classification_catalog_does_not_block_analysis(monkeypatch):
    monkeypatch.setattr("tests.modules.data_validation.test_ai_service._Processes.list_report_processes", lambda self: [])
    rules, model = _rules_with_doc([_select_payload(report_category=""), _generate_payload()])
    result = rules.parse_rule_request(user(), _request())
    assert result["rule_type"] == "field_compare" and result["report_category"] == ""
    assert len(model.calls) == 2


def test_explicit_exception_still_requires_review_instead_of_becoming_a_general_notice():
    rules, _ = _rules_with_doc([_select_payload(), _generate_payload()])
    result = rules.parse_rule_request(user(), _request(request_text="除新成立项目外，实收信托不为0"))
    assert any("例外" in item for item in result["uncertainties"])


def test_unsupported_generation_does_not_invent_expression_or_write_rule():
    rules, _ = _rules_with_doc([_select_payload(), {"unsupported_requirements": ["需复合条件过滤存续状态"]}])
    result = rules.parse_rule_request(user(), _request())
    assert result["status"] == "needs_clarification"
    assert result["expression"] == {}
    assert rules.storage.visible_rules("1") == []


@pytest.mark.parametrize("bad", [None, "说明", [False], ["x"] * 101])
def test_malformed_review_arrays_are_model_response_errors(bad):
    rules, _ = _rules_with_doc([_select_payload(uncertainties=bad)])
    with pytest.raises(AppError) as exc:
        rules.parse_rule_request(user(), _request())
    assert exc.value.code == "MODEL_RESPONSE_INVALID"


def test_custom_templates_are_not_overwritten_and_still_get_contracts():
    rules, model = _rules_with_doc([_select_payload(), _generate_payload(sql="DELETE FROM test_table")])
    templates = {
        "select_table": "OLD-SELECT {request_text} {source_name} {tables} {categories} 输出uncertainty。",
        "generate_rule": "OLD-GENERATE {request_text} {table} {fields} 同时生成SQL。",
    }
    for stage, template in templates.items():
        rules.save_prompt(user(), stage, template)
    result = rules.parse_rule_request(user(), _request())
    assert "OLD-SELECT" in model.calls[0]["messages"][0]["content"]
    assert "unsupported_requirements" in model.calls[0]["messages"][0]["content"]
    assert "OLD-GENERATE" in model.calls[1]["messages"][0]["content"]
    assert "unsupported_requirements" in model.calls[1]["messages"][0]["content"]
    assert "sql" not in result
    assert all(rules.storage.active_prompt(stage)["content"] == template for stage, template in templates.items())
    public = {item["stage"]: item for item in rules.list_prompts()}
    assert public["select_table"]["content"] == templates["select_table"]
    assert "unsupported_requirements" in public["select_table"]["output_contract"]
    assert "field_compare" in public["generate_rule"]["output_contract"]
    assert public["generate_sql"]["output_contract"] == ""


def test_review_notes_survive_save_reload_and_block_confirmation_until_processed():
    _, rules = service(metadata=Metadata())
    saved = rules.save_draft(user(), loan_definition(uncertainties=["确认适用范围"], uncertainty_resolutions=[]))
    version = rules.storage.latest_version(saved["id"])
    rules.run_tests(user(), saved["id"], 1)
    with pytest.raises(AppError):
        rules.confirm_rule(user(), saved["id"], 1, version["content_sha256"])
    detail = rules.get_rule(user(), saved["id"])
    definition = detail["definition"]
    assert definition["uncertainties"] == ["确认适用范围"]
    definition["uncertainty_resolutions"] = ["文档确认全表为存续项目，无额外状态筛选"]
    rules.save_draft(user(), definition, saved["id"])
    current = rules.storage.latest_version(saved["id"])
    rules.run_tests(user(), saved["id"], current["version_no"])
    assert rules.confirm_rule(user(), saved["id"], current["version_no"], current["content_sha256"])["status"] == "enabled"


def test_unsupported_cannot_be_released_with_explanation_and_missing_fields_preserve_review():
    _, rules = service(metadata=Metadata())
    saved = rules.save_draft(user(), loan_definition(
        unsupported_requirements=["需要额外状态过滤"], uncertainties=["核对范围"], uncertainty_resolutions=["已说明"],
    ))
    rules.save_draft(user(), loan_definition(), saved["id"])
    version = rules.storage.latest_version(saved["id"])
    assert version["definition"]["unsupported_requirements"] == ["需要额外状态过滤"]
    assert version["definition"]["uncertainties"] == ["核对范围"]
    rules.run_tests(user(), saved["id"], version["version_no"])
    with pytest.raises(AppError):
        rules.confirm_rule(user(), saved["id"], version["version_no"], version["content_sha256"])


def test_execution_rejects_unresolved_or_unsupported_requirements_before_querying():
    from auto_check.modules.data_validation.executor import execute_version
    class NoQueries:
        def describe_table(self, *args):
            raise AssertionError("Unreviewed rule must not query metadata or business data")
    for review in ({"uncertainties": ["范围待确认"]}, {"unsupported_requirements": ["额外状态筛选"]}):
        result = execute_version({"definition": loan_definition(**review)}, {}, NoQueries())
        assert result.status == "ERROR" and result.error_code == "VALIDATION_ERROR"


def test_changed_questions_invalidate_previous_resolutions():
    _, rules = service(metadata=Metadata())
    saved = rules.save_draft(user(), loan_definition(uncertainties=["旧问题"], uncertainty_resolutions=["旧说明"]))
    rules.save_draft(user(), loan_definition(uncertainties=["新问题"], uncertainty_resolutions=["旧说明"]), saved["id"])
    assert rules.storage.latest_version(saved["id"])["definition"]["uncertainty_resolutions"] == []


def test_changed_comparison_context_invalidates_prior_review_notes():
    _, rules = service(metadata=Metadata())
    saved = rules.save_draft(user(), loan_definition(uncertainties=["核对比较含义"], uncertainty_resolutions=["旧定义依据已核对"]))
    rules.save_draft(user(), loan_definition(
        expression={"left": "issue_date", "op": "lt", "right": "maturity_date"},
        uncertainties=["核对比较含义"], uncertainty_resolutions=["旧定义依据已核对"],
    ), saved["id"])
    assert rules.storage.latest_version(saved["id"])["definition"]["uncertainty_resolutions"] == []
