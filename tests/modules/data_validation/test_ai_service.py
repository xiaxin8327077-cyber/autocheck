import json
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import (
    Metadata, SequenceModel, doc_xlsx_bytes, loan_definition, service, user,
)


class _Processes:
    def list_report_processes(self):
        return [
            SimpleNamespace(code="pbc_central", name="人行大集中报送", order=1, active=True),
            SimpleNamespace(code="east5", name="East5报送", order=2, active=True),
        ]


class SourceOnlyMetadata:
    """只提供数据源清单；任何表清单/表结构读取都应视为违规。"""

    def list_sources(self):
        return [SimpleNamespace(id="src", name="监管报送集市", dialect="postgresql")]

    def list_tables(self, *_args, **_kwargs):
        raise AssertionError("AI 分析不得读取数据库表清单")

    def describe_table(self, *_args, **_kwargs):
        raise AssertionError("AI 分析不得读取数据库表结构")


def _select_payload(**overrides):
    payload = {"target": {"table": "test_table"}, "report_category": "pbc_central"}
    payload.update(overrides)
    return payload


def _generate_payload(**overrides):
    payload = {
        "rule_name": "测试规则",
        "rule_type": "field_compare",
        "expression": {"left": "到期日期", "op": "lt", "right": "发放日期"},
        "violation_message": "到期日期不得早于发放日期",
        "null_policy": "unresolved",
        "equality_policy": "unresolved",
        "uncertainties": [],
    }
    payload.update(overrides)
    return payload


def _rules_with_doc(payloads, *, fields=None, sheet="集市层_测试表", error=None):
    model = SequenceModel(payloads, error=error)
    _database, rules = service(
        metadata=SourceOnlyMetadata(), model=model, report_navigation=_Processes(),
    )
    content = doc_xlsx_bytes(sheet=sheet, fields=fields)
    rules.import_document(user(), "doc.xlsx", content)
    return rules, model


def _request(**overrides):
    payload = {"request_text": "贷款到期日期不能早于贷款发放日期", "source_id": "src", "model_id": "model-1"}
    payload.update(overrides)
    return payload


def test_doc_driven_parse_uses_document_without_database() -> None:
    """AI 分析只依赖已导入文档：不调用 list_tables/describe_table，表不存在也能生成候选。"""
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()])
    result = rules.parse_rule_request(user(), _request())
    assert len(model.calls) == 2, "两段式：先选表，再生成规则"
    assert "test_table" in model.calls[0]["messages"][0]["content"]
    assert "监管报送集市" in model.calls[0]["messages"][0]["content"]
    assert "maturity_date" in model.calls[1]["messages"][0]["content"]
    assert result["rule_name"] == "测试规则"
    assert result["table_name"] == "test_table"
    assert result["report_category"] == "group:pbc"
    assert result["report_category_name"] == "人行报送"
    assert result["expression"] == {"left": "maturity_date", "op": "lt", "right": "issue_date"}
    assert [item["column_name"] for item in result["columns"]] == ["row_id", "maturity_date", "issue_date"]
    assert result["mapping_version"].startswith("doc-v1-")
    assert result["doc_version"] == 1
    assert result["verification_status"] == "not_run"


def test_doc_parse_works_even_when_physical_tables_are_missing() -> None:
    """数据源里没有任何真实表时仍能生成并保存草稿（真实核验留到测试/确认阶段）。"""
    rules, _model = _rules_with_doc([_select_payload(), _generate_payload()])
    result = rules.parse_rule_request(user(), _request())
    saved = rules.save_draft(user(), {
        "name": result["rule_name"], "rule_type": "field_compare", "dialect": result["dialect"],
        "source_id": result["source_id"], "report_category": result["report_category"],
        "table_name": result["table_name"], "business_key": "row_id",
        "expression": result["expression"], "violation_message": "到期日期不得早于发放日期",
        "null_policy": "unresolved", "equality_policy": "unresolved", "generation_mode": "ai",
        "mapping_version": result["mapping_version"],
    })
    assert saved["status"] == "draft"


def test_missing_document_blocks_analysis() -> None:
    model = SequenceModel([_select_payload(), _generate_payload()])
    _database, rules = service(metadata=SourceOnlyMetadata(), model=model, report_navigation=_Processes())
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request())
    assert error.value.code == "VALIDATION_ERROR"


def test_model_selected_table_must_exist_in_document() -> None:
    rules, _model = _rules_with_doc([
        _select_payload(target={"table": "not_exists_table"}),
        _generate_payload(),
    ])
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request())
    assert error.value.code == "MODEL_RESPONSE_INVALID"


def test_model_selected_category_must_exist_in_report_processes() -> None:
    rules, _model = _rules_with_doc([
        _select_payload(report_category="not_exists_category"),
        _generate_payload(),
    ])
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request())
    assert error.value.code == "MODEL_RESPONSE_INVALID"


def test_ambiguous_alias_stays_unresolved() -> None:
    fields = [
        ("row_id", "编号", "varchar", "Y"),
        ("maturity_date", "到期日期", "date", ""),
        ("end_date", "到期日期", "date", ""),
        ("issue_date", "发放日期", "date", ""),
    ]
    rules, _model = _rules_with_doc([_select_payload(), _generate_payload()], fields=fields)
    result = rules.parse_rule_request(user(), _request())
    assert result["uncertainties"]
    assert result["can_enable"] is False


def test_model_can_ask_for_documented_field_choice_without_discarding_its_proposal() -> None:
    fields = [
        ("row_id", "编号", "varchar", "Y"), ("reading_date", "数据日期", "date", ""),
        ("initial_qty", "期初数量", "decimal", ""), ("last_qty", "期末数量", "decimal", ""),
    ]
    rules, model = _rules_with_doc([_select_payload(), _generate_payload(
        expression={"left": "last_qty", "op": "is_null"},
        field_choices=[{"side": "left", "term": "数量", "fields": ["initial_qty", "invented", "last_qty"],
                        "recommended": "last_qty"}],
    )], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text="数量不能为空"))
    question = next(item for item in result["questions"] if item["id"] == "expression.left")
    assert [item["value"] for item in question["options"]] == ["initial_qty", "last_qty"]
    assert question["options"][1]["tag"] == "模型建议"
    assert result["expression"]["left"] == "last_qty" and result["preview"] is None
    assert "field_choices" in model.calls[1]["messages"][0]["content"]


def test_exact_duplicate_points_at_existing_code() -> None:
    rules, _model = _rules_with_doc([_select_payload(), _generate_payload()])
    rules.save_draft(user(), {
        "name": "既有规则", "description": "", "rule_type": "field_compare",
        "source_id": "src", "dialect": "postgresql", "table_name": "test_table",
        "business_key": "row_id", "violation_message": "期限异常",
        "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
    })
    result = rules.parse_rule_request(user(), _request())
    assert result["duplicate"]["kind"] == "exact"
    assert result["duplicate"]["rule_code"] == "DV000001"


def test_same_named_indicator_in_other_table_is_not_exact_duplicate() -> None:
    rules, _model = _rules_with_doc([_select_payload(), _generate_payload()])
    rules.save_draft(user(), {
        "name": "合同口径既有规则", "description": "", "rule_type": "field_compare",
        "source_id": "src", "dialect": "postgresql", "table_name": "contract_table",
        "business_key": "row_id", "violation_message": "期限异常",
        "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": {"left": "maturity_date", "op": "lt", "right": "issue_date"},
    })
    result = rules.parse_rule_request(user(), _request())
    assert result["duplicate"]["kind"] == "partial_overlap"
    assert result["duplicate"]["rule_code"] == "DV000001"
    assert "对象不同" in result["duplicate"]["evidence"]


def test_model_unavailable_keeps_manual_draft_path() -> None:
    rules, _model = _rules_with_doc([_select_payload()], error=RuntimeError("down"))
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request())
    assert error.value.code == "MODEL_UNAVAILABLE"
    assert rules.save_draft(user(), loan_definition())["status"] == "draft"


def test_old_template_model_sql_is_discarded_not_executed() -> None:
    rules, _model = _rules_with_doc([
        _select_payload(),
        _generate_payload(sql="DELETE FROM test_table"),
    ])
    result = rules.parse_rule_request(user(), _request())
    assert result["sql_status"] == "candidate"
    assert result["error_code"] == ""
    assert "sql" not in result


def test_model_returns_select_draft_only() -> None:
    rules, _model = _rules_with_doc([
        _select_payload(),
        _generate_payload(sql="SELECT 1"),
    ])
    result = rules.parse_rule_request(user(), _request())
    assert result["sql_status"] == "candidate"


def test_source_without_document_tables_is_rejected() -> None:
    rules, _model = _rules_with_doc(
        [_select_payload(), _generate_payload()], sheet="人行明细表_测试表",
    )
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request())
    assert error.value.code == "VALIDATION_ERROR"


def test_custom_prompt_is_used_and_validated() -> None:
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()])
    template = (
        "CUSTOM-MARK 需求：{request_text} 数据源：{source_name} "
        "表：{tables} 分类：{categories}"
    )
    rules.save_prompt(user(), "select_table", template)
    rules.save_prompt(user(), "business_scope", "CUSTOM-SCOPE 校验按同一数据日期对齐")
    rules.parse_rule_request(user(), _request())
    assert "CUSTOM-MARK" in model.calls[0]["messages"][0]["content"]
    assert all("CUSTOM-SCOPE" in call["messages"][0]["content"] for call in model.calls)
    assert not any("所有数据校验统一忽略币种" in call["messages"][0]["content"] for call in model.calls)
    with pytest.raises(AppError) as error:
        rules.save_prompt(user(), "select_table", "缺少变量")
    assert error.value.code == "VALIDATION_ERROR"


def test_model_availability_check() -> None:
    """模型可用性测试：发起一次最小请求；失败返回 MODEL_UNAVAILABLE。"""
    model = SequenceModel([{"ok": True}])
    _database, rules = service(metadata=Metadata(), model=model)
    assert rules.test_model(user(), "model-1") == {"available": True, "model_id": "model-1"}
    assert len(model.calls) == 1
    _database2, failing = service(metadata=Metadata(), model=SequenceModel([], error=RuntimeError("down")))
    with pytest.raises(AppError) as error:
        failing.test_model(user(), "model-1")
    assert error.value.code == "MODEL_UNAVAILABLE"

def test_large_table_field_context_is_filtered_and_marked() -> None:
    """超大表只把与需求相关的字段+主键发给模型，并明确告知字段被裁剪。"""
    fields = [("row_id", "编号", "varchar", "Y")]
    fields += [(f"spare_field_{index}", f"备用字段{index}", "varchar", "") for index in range(120)]
    fields += [("maturity_date", "到期日期", "date", ""), ("issue_date", "发放日期", "date", "")]
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()], fields=fields)
    result = rules.parse_rule_request(user(), _request())
    prompt = model.calls[1]["messages"][0]["content"]
    assert "maturity_date" in prompt and "issue_date" in prompt
    assert "spare_field_119" not in prompt, "无关字段不应进入字段上下文"
    assert not any("字段数量" in item for item in result["uncertainties"])
    assert any("字段数量" in item for item in result["notices"])
    assert any(item["id"] == "report_date_field" for item in result["questions"])
    assert result["can_enable"] is False
