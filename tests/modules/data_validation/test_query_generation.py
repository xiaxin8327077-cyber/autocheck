from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import insert, update

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.generation_policy import review_ready
from auto_check.modules.data_validation.project_context import infer_project_context
from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from auto_check.modules.data_validation.trust_knowledge import PAID_IN_MAPPING_ENTRIES
from tests.modules.data_validation.support import Metadata, SequenceModel, doc_xlsx_bytes, service, user
from tests.modules.data_validation.test_ai_service import _Processes, _generate_payload, _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_followup_service_bridge import _rules


FIELDS = [("row_id", "项目编号", "varchar", "Y"), ("c_projname", "项目名称", "varchar", ""),
          ("amount", "实收信托", "numeric", ""),
          ("start_date", "项目开始日", "date", ""), ("status", "项目状态", "varchar", ""),
          ("report_status", "项目状态", "varchar", ""), ("business_day", "数据日期", "date", "")]


def make_rules(*, unary=False, related=False):
    selection = _select_payload()
    if related:
        selection["related_target"] = {"table": "state_table"}
    expression = {"left": "项目开始日", "op": "is_null"} if unary else {
        "left": "amount", "op": "eq", "right_type": "value", "right": 0}
    draft = _generate_payload(expression=expression)
    draft["filters"] = [{"table": "related" if related else "base", "field": "status", "op": "eq", "value": "1", "confirmed": True}]
    if related:
        draft["join"] = {"table_name": "state_table", "on": [{"left": "row_id", "right": "row_id"}],
                         "report_date_field": "business_day", "relationship_confirmed": True, "unmatched_policy": "exclude"}
    rules, model = _rules_with_doc([selection, draft], fields=FIELDS)
    table = rules.storage.doc_tables(rules.storage.active_document()["id"])[0]
    with rules.storage.database.begin() as connection:
        for name, dictionary in [("status", "【D1】\n0-已完结\n1-存续"), ("report_status", "【D2】\n0-本月销户\n1-已完结未销户\n2-存续")]:
            connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == table["id"], DOC_FIELDS.c.field_name == name).values(dictionary=dictionary))
        if related:
            second = {key: value for key, value in table.items() if key != "id"}
            second.update(table_name="state_table", table_name_cn="项目状态表")
            related_id = connection.execute(insert(DOC_TABLES).values(**second)).inserted_primary_key[0]
            for field in rules.storage.doc_fields(table["id"]):
                copied = {key: value for key, value in field.items() if key != "id"}
                copied["table_id"] = related_id
                connection.execute(insert(DOC_FIELDS).values(**copied))
    return rules, model


def resolved_definition(candidate):
    definition = {**candidate, "name": candidate["rule_name"], "description": "存续项目校验", "report_date_field": "business_day"}
    definition["questions"] = []
    choice = next(item for item in candidate["questions"] if item["id"] == "filters.0")["options"][1]
    definition["filters"] = [deepcopy(choice["selection"])]
    definition["uncertainty_resolutions"] = [choice["label"] for _ in definition["uncertainties"]]
    if definition.get("join"):
        definition["join"] = {**definition["join"], "relationship_confirmed": True, "unmatched_policy": "exclude", "report_date_field": "business_day"}
    return definition


def test_begin_date_required_with_documented_scope_is_not_rejected_as_unsupported():
    rules, model = make_rules(unary=True)
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目项目开始日不能为空"))
    assert candidate["unsupported_requirements"] == []
    assert candidate["expression"] == {"left": "start_date", "op": "is_null"}
    assert candidate["null_policy"] == "violate"
    assert candidate["equality_policy"] == "allow_equal"
    assert candidate["preview"] is None
    definition = resolved_definition(candidate)
    preview = rules.preview_candidate(user(), definition)
    assert '"start_date" IS NULL' in preview["sql_preview"]
    assert '"start_date" IS NOT NULL' not in preview["sql_preview"]
    assert preview["sql_params"]["filter_1"] == "2"
    result = rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"]})
    assert result["failed_count"] == result["not_run_count"] == 0
    assert result["passed_count"] >= 4
    assert len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []


def test_two_table_choices_compile_exists_and_never_accept_model_confirmation():
    rules, model = make_rules(related=True)
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目实收信托一般不为0"))
    assert candidate["join"]["relationship_confirmed"] is False
    assert candidate["join"]["unmatched_policy"] == "unresolved"
    assert candidate["filters"][0]["confirmed"] is False
    assert candidate["join"]["report_date_field"] == "business_day"
    assert {item["id"] for item in candidate["questions"]} >= {"filters.0", "join.relationship_confirmed", "join.unmatched_policy"}
    definition = resolved_definition(candidate)
    definition["null_policy"] = "skip"
    preview = rules.preview_candidate(user(), definition)
    assert "EXISTS" in preview["sql_preview"] and '"state_table"' in preview["sql_preview"]
    assert preview["related_columns"]
    result = rules.test_candidate(user(), {"definition": definition})
    assert result["failed_count"] == result["not_run_count"] == 0
    assert result["passed_count"] > 4
    assert len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []


@pytest.mark.parametrize("dictionary_code", ["1", "7"])
@pytest.mark.parametrize("missing_project_name", [False, True])
def test_single_documented_active_scope_skips_confirmation(dictionary_code, missing_project_name):
    fields = [
        ("row_id", "项目编号", "varchar", "Y"), ("c_projname", "项目名全称", "varchar", ""),
        ("amount", "实收信托", "numeric", ""), ("c_projstatus", "产品存续状态", "varchar", ""),
        ("business_day", "报送日期", "date", ""),
    ]
    if missing_project_name:
        fields = [field for field in fields if field[0] != "c_projname"]
    rules, _ = _rules_with_doc([
        _select_payload(uncertainties=["需确认存续范围使用哪个状态字段。"]),
        _generate_payload(expression={"left": "amount", "op": "lt", "right_type": "value", "right": 0},
                          filters=[{"field": "c_projstatus", "op": "eq", "value": "1"}]),
    ], fields=fields, sheet="人行_测试表")
    rules.metadata.list_sources = lambda: [SimpleNamespace(id="src", name="监管报表", dialect="postgresql")]
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "c_projstatus")
                           .values(dictionary=f"2-终止\n{dictionary_code}-存续"))

    result = rules.parse_rule_request(user(), _request(request_text="存续项目的实收不得小于0"))

    assert not any(question["id"].startswith("filters.") for question in result["questions"])
    assert result["filters"] == [{"table": "base", "field": "c_projstatus", "op": "eq",
                                 "value": dictionary_code, "confirmed": True}]
    if missing_project_name:
        assert result["preview"] is None
        assert "缺少项目名称字段" in result["preview_error"]
        assert "文档快照" in result["preview_error"]
        assert not result["can_enable"]
    else:
        assert '"c_projstatus" = :filter_1' in result["preview"]["sql_preview"]
        assert result["preview"]["sql_params"]["filter_1"] == dictionary_code
        assert result["uncertainties"] == [] and result["can_enable"]


PROJECT_TABLE = "reg_pub_project_info"
PROJECT_FIELDS = [
    ("c_projcode", "项目编号", "varchar", "Y"), ("c_proj_name", "项目名称", "varchar", ""),
    ("c_projname", "项目名全称", "varchar", ""), ("start_date", "项目开始日期", "date", ""),
    ("c_projstatus", "项目状态", "varchar", ""), ("pro_status", "项目状态", "varchar", ""),
    ("pro_isclose", "信托产品存续标识", "varchar", ""), ("business_day", "数据日期", "date", ""),
]


def _pboc_project_rules(*, model_filters=(), missing_mapping=None, selection_reviews=(), draft_reviews=(),
                        extra_fields=(), dialect="mysql"):
    table_name = "proj_info_dtl_pboc"
    fields = [
        ("c_projinnercode", "TCMP编号", "varchar", "Y"), ("c_projcode", "产品代码", "varchar", ""),
        ("c_projname", "产品名称", "varchar", ""), ("d_cldate", "数据日期", "date", ""),
        ("c_is_over", "是否当期终止", "varchar", ""), ("f_equity_total_4001_bal", "权益合计（4001科目余额）", "numeric", ""),
        ("c_projxttype", "信托产品类型", "varchar", ""), ("c_projstatus", "产品存续状态", "varchar", ""),
    ] + list(extra_fields)
    model = SequenceModel([
        _select_payload(target={"table": table_name}, uncertainties=list(selection_reviews)),
        _generate_payload(expression={"left": "f_equity_total_4001_bal", "op": "gt", "right_type": "value", "right": 0},
                          filters=list(model_filters), uncertainties=list(draft_reviews)),
    ])
    metadata = Metadata(sources=[SimpleNamespace(id="src", name="监管报表", dialect=dialect)])
    database, rules = service(metadata=metadata, model=model, report_navigation=_Processes())
    rules.import_document(user(), "人行明细.xlsx", doc_xlsx_bytes(
        sheet="人行明细表_项目明细表", table=table_name, table_cn="项目信息", dimension="项目", fields=fields,
    ))
    with database.begin() as connection:
        connection.execute(update(DOC_TABLES).values(
            scope="报送取数范围 RH001：p.c_projxttype <> '3' AND (p.c_projstatus = '1' OR p.c_is_over = '1')",
        ))
        for name, source, meaning in [("c_projinnercode", "c_projcode", "项目编号"),
                                       ("c_projcode", "c_spvcode", "项目SPV代码/资管产品代码"),
                                       ("c_projname", "c_projname", "项目名全称")]:
            connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == name).values(
                source_table=PROJECT_TABLE if name == missing_mapping else f"reg_data_market.{PROJECT_TABLE}",
                source_field="" if name == missing_mapping else source,
                logic=f"直接取项目信息表的{meaning}[{source}]。",
            ))
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "c_is_over")
                           .values(dictionary="1-是\n2-否"))
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "c_projxttype")
                           .values(dictionary="3-资产证券化服务信托\n6-资产管理信托"))
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "c_projstatus")
                           .values(dictionary="1-存续\n2-终止"))
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "f_equity_total_4001_bal")
                           .values(logic="会计日期等于报送日期、信托会计科目编号为4001-实收信托，取科目余额[f_balance]。"))
    return rules


@pytest.mark.parametrize("missing_mapping", [None, "c_projinnercode", "c_projname"])
@pytest.mark.parametrize("model_filters", [
    [],
    [{"field": "c_is_over", "op": "eq", "value": "1"}],
    [{"field": "c_projxttype", "op": "neq", "value": "3"},
     {"field": "c_projstatus", "op": "eq", "value": "1"}],
])
def test_pboc_project_detail_uses_documented_identity_and_termination_scope(missing_mapping, model_filters):
    rules = _pboc_project_rules(model_filters=model_filters, missing_mapping=missing_mapping)
    result = rules.parse_rule_request(user(), _request(request_text="当期终止项目的实收不得大于 0"))

    assert result["questions"] == []
    assert result["filters"] == [{"table": "base", "field": "c_is_over", "op": "eq", "value": "1", "confirmed": True}]
    if missing_mapping:
        assert result["preview"] is None and "project_context" not in result
        assert result["preview_error"]
        return

    assert not result.get("preview_error")
    assert result["project_context"] == {"mode": "base", "code_field": "c_projinnercode",
                                         "name_field": "c_projname", "confirmed": True}
    preview = result["preview"]
    sql = preview["sql_preview"]
    assert '`c_projinnercode` AS `TCMP编号（项目编号）`' in sql and '`c_projname` AS `产品名称`' in sql
    assert '`c_is_over` = :filter_1' in sql and preview["sql_params"]["filter_1"] == "1"
    assert 'COALESCE(t.`f_equity_total_4001_bal`, 0) > :right_value' in sql and preview["sql_params"]["right_value"] == 0
    assert "c_projxttype" not in sql and "c_projstatus" not in sql
    tests = rules.test_candidate(user(), {"definition": preview["definition"], "expected_hash": preview["content_sha256"]})
    assert tests["passed_count"] > 0 and tests["failed_count"] == tests["not_run_count"] == 0


_TERMINATION_REVIEW = ("需确认'当期终止'的判定字段：proj_info_dtl_pboc.c_is_over（是否当期终止）"
                       "或 c_projstatus（产品存续状态=2）")
_MEASURE_REVIEW = "'实收'对应的金额字段名称"


@pytest.mark.parametrize(("soft_limit", "independent"), [
    ("一般", ""), ("原则上", ""), ("一般", "金额单位与币种需确认"), ("一般", "关联表跨期取哪个截止日期"),
    ("一般", "是否还要限制信托类型范围"),
])
def test_two_round_field_reviews_are_resolved_by_final_document_bindings(soft_limit, independent):
    mixed = _TERMINATION_REVIEW + "，以及" + _MEASURE_REVIEW
    rules = _pboc_project_rules(
        selection_reviews=[mixed + ("，以及" + independent if independent else "")],
        draft_reviews=["需确认“实收”对应的金额字段名称。"],
        extra_fields=[(f"extra_{idx}", f"备注{idx}", "varchar", "") for idx in range(62)],
    )
    candidate = rules.parse_rule_request(user(), _request(request_text=f"当期终止项目的实收{soft_limit}不得大于 0"))
    assert candidate["uncertainties"] == []
    assert candidate["preview"]["definition"]["uncertainties"] == candidate["uncertainties"]
    assert candidate["can_enable"]
    if independent:
        assert independent in candidate["model_judgments"]["select_table"]["uncertainties"][0]
    assert candidate["preview"]["sql_params"]["filter_1"] == "1"
    assert "COALESCE(t.`f_equity_total_4001_bal`, 0) > :right_value" in candidate["preview"]["sql_preview"]
    assert "OR t.`f_equity_total_4001_bal` IS NULL" not in candidate["preview"]["sql_preview"]
    assert any("70" in notice and "60" in notice for notice in candidate["notices"])
    assert any("合理例外" in notice for notice in candidate["notices"])


@pytest.mark.parametrize("model_code", ["1", "2"])
def test_review_of_a_concrete_field_binding_uses_the_documented_code(model_code):
    status = f"需确认c_is_over字典编码{model_code}表示当期终止"
    model_note = status + "，且f_equity_total_4001_bal为本期实收字段"
    rules = _pboc_project_rules(draft_reviews=[model_note])
    result = rules.parse_rule_request(user(), _request(request_text="当期终止项目的实收原则上不得大于 0"))
    assert result["model_judgments"]["generate_rule"]["uncertainties"] == [model_note]
    assert result["uncertainties"] == []
    assert result["can_enable"] and result["filters"][0]["value"] == "1"


@pytest.mark.parametrize("independent", ["", "，另需核对币种。"])
def test_live_model_binding_notes_do_not_repeat_verified_document_questions(independent):
    notes = [
        "实收字段未明确选择：proj_info_dtl_pboc中实收通过科目余额f_equity_total_4001_bal表达，"
        "但需求未明确使用该字段还是其他实收字段，需核对字段映射。",
        "当期终止判定字段存在多个线索：c_is_over（字典编码1表示当期终止）与c_projstatus（2=终止），"
        "需求明确使用c_is_over，但需确认该字段在proj_info_dtl_pboc中存在且值域正确" + (independent or "。"),
    ]
    rules = _pboc_project_rules(draft_reviews=notes)
    result = rules.parse_rule_request(user(), _request(request_text="当期终止项目的实收原则上不得大于 0" + independent))
    assert result["model_judgments"]["generate_rule"]["uncertainties"] == notes
    if independent:
        assert any("另需核对币种" in item for item in result["uncertainties"])
    else:
        assert result["uncertainties"] == []
    assert result["can_enable"] is (not independent)


@pytest.mark.parametrize("model_table", ["proj_info_dtl_pboc", "raise_info_dtl_pboc", ""])
def test_document_recovers_from_model_field_gap_and_keeps_original_judgments(model_table):
    request_text = "当期终止项目的实收原则上不得大于 0"
    refusal = f"需求要求“{request_text}”，但目标表缺少实收字段和终止状态字段，无法构造字段比较表达式。"
    rules = _pboc_project_rules()
    with rules.storage.database.begin() as connection:
        table = rules.storage.doc_tables(rules.storage.active_document()["id"])[0]
        connection.execute(insert(DOC_TABLES).values(**{
            **{key: value for key, value in table.items() if key != "id"},
            "table_name": "raise_info_dtl_pboc", "dimension": "项目内部编号＋合同ID",
        }))
    rules.model.payloads = [
        _select_payload(target={"table": model_table} if model_table else {},
                        uncertainties=[] if model_table else ["无法确定目标表"]),
        _generate_payload(rule_type=None, expression={}, uncertainties=[refusal]),
    ]
    saved = rules.knowledge.save(user(), {"expected_revision": 0, "entries": list(PAID_IN_MAPPING_ENTRIES)})
    rules.knowledge.save(user(), {"expected_revision": saved["revision"], "enabled": True}, activation=True)

    result = rules.parse_rule_request(user(), _request(request_text=request_text))

    raw = result["model_judgments"]
    assert raw["select_table"].get("table", "") == model_table
    assert raw["generate_rule"]["expression"] == {}
    assert raw["generate_rule"]["uncertainties"] == [refusal]
    prompts = [call["messages"][0]["content"] for call in rules.model.calls]
    assert all("监管报表项目实收字段映射" in text and "f_actual_trust_scale" not in text for text in prompts)
    assert result["table_name"] == "proj_info_dtl_pboc"
    assert result["expression"]["left"] == "f_equity_total_4001_bal"
    assert result["filters"][0]["field"] == "c_is_over"
    assert result["uncertainties"] == [] and result["can_enable"]
    preview = result["preview"]
    assert "COALESCE(t.`f_equity_total_4001_bal`, 0) > :right_value" in preview["sql_preview"]
    assert "IS NULL" not in preview["sql_preview"] and "model_judgments" not in preview["definition"]
    tests = rules.test_candidate(user(), {"definition": preview["definition"], "expected_hash": preview["content_sha256"]})
    assert tests["failed_count"] == tests["not_run_count"] == 0


@pytest.mark.parametrize("local_status,broken_lineage", [(True, ""), (False, ""), (False, "identity"), (False, "day")])
def test_scoped_measure_candidate_keeps_its_grain_and_uses_only_documented_scope(local_status, broken_lineage):
    rules = _pboc_project_rules()
    project = rules.storage.doc_tables(rules.storage.active_document()["id"])[0]
    raw = {f["field_name"]: f for f in rules.storage.doc_fields(project["id"])}
    with rules.storage.database.begin() as connection:
        metric = {key: val for key, val in project.items() if key != "id"}
        metric.update(table_name="payment_rows", table_name_cn="缴款明细", dimension="项目编号＋合同ID；每项目每合同一条")
        table_id = connection.execute(insert(DOC_TABLES).values(**metric)).inserted_primary_key[0]
        def add(template, name, label, **attrs):
            field = {key: val for key, val in raw[template].items() if key != "id"}
            field.update(table_id=table_id, field_name=name, field_cn=label, is_pk="")
            field.update(source_table="report." + project["table_name"], source_field=template, logic="直取")
            connection.execute(insert(DOC_FIELDS).values(**{**field, **attrs}))
        add("c_projinnercode", "project_ref", "项目编号", is_pk="Y",
            source_field="wrong" if broken_lineage == "identity" else "c_projinnercode")
        add("c_projname", "name", "项目名称")
        add("d_cldate", "report_day", "报送日期", source_field="wrong" if broken_lineage == "day" else "d_cldate")
        add("c_projinnercode", "contract_id", "合同编号", is_pk="Y", source_table="", source_field="")
        add("f_equity_total_4001_bal", "end_units", "期末产品份额（实收本金）", logic="份额加待结转收益")
        add("f_equity_total_4001_bal", "prior_units", "上期份额", logic="上期的期末产品份额（实收本金）")
        if local_status:
            add("c_is_over", "end_state", "是否当期终止")
        else:
            add("c_is_over", "contract_state", "合同状态", source_table="", source_field="",
                dictionary="1-当期终止")
    result = rules.parse_rule_request(user(), _request(request_text="当期结束的项目的实收原则上不应该大于 0。"))
    options = {opt["candidate"]["table_name"]: opt for opt in result.get("candidate_options", [])}
    if broken_lineage:
        assert "payment_rows" not in options or options["payment_rows"]["candidate"].get("preview") is None
        return
    option = options["payment_rows"]
    inner = option["candidate"]
    assert "合同" in option["grain"] and inner["business_key"] == "contract_id"
    assert inner["expression"] == {"left": "end_units", "op": "gt", "right_type": "value", "right": 0}
    preview = inner["preview"]
    assert preview and preview["sql_params"]["filter_1"] == "1"
    if local_status:
        assert not inner.get("join") and inner["filters"][0]["field"] == "end_state"
    else:
        assert inner["join"]["on"] == [{"left": "project_ref", "right": "c_projinnercode"}]
        assert inner["join"]["report_date_field"] == "d_cldate"
        assert inner["filters"] == [{"field": "c_is_over", "table": "related", "op": "eq", "value": "1", "confirmed": True}]
        assert "EXISTS" in preview["sql_preview"]
        wrong = deepcopy(preview["definition"])
        wrong["join"]["on"][0]["left"] = "contract_id"
        with pytest.raises(AppError):
            rules.preview_candidate(user(), wrong)
    tested = rules.test_candidate(user(), {"definition": preview["definition"], "expected_hash": preview["content_sha256"]})
    assert tested["failed_count"] == tested["not_run_count"] == 0


@pytest.mark.parametrize("owner_dimension", ["合同", "项目"])
def test_measure_only_on_child_table_uses_requested_entity_relationship(owner_dimension):
    from tests.modules.data_validation.test_candidate_options import _add_table
    fields = [("row_id", "明细编号", "varchar", "Y"), ("parent_id", "合同编号", "varchar", ""),
              ("balance", "期末余额", "numeric", ""), ("report_day", "报送日期", "date", "")]
    rules, _ = _rules_with_doc([_select_payload(), _generate_payload(
        expression={"left": "balance", "op": "gt", "right_type": "value", "right": 0})], fields=fields)
    _add_table(rules, name="status_owner", cn="状态信息", dimension=owner_dimension, fields=[
        ("entity_id", owner_dimension + "编号", "varchar", "Y"), ("ended", "是否当期终止", "varchar", ""),
        ("as_of", "数据日期", "date", "")])
    tables = {t["table_name"]: t["id"] for t in rules.storage.doc_tables(rules.storage.active_document()["id"])}
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_TABLES).where(DOC_TABLES.c.id == tables["test_table"])
                           .values(dimension="明细", scope=""))
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "ended").values(dictionary="e-是\nn-否"))
        for name, source in [("parent_id", "entity_id"), ("report_day", "as_of")]:
            connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == name)
                               .values(source_table="report.status_owner", source_field=source, logic="直取"))
    result = rules.parse_rule_request(user(), _request(request_text="当期结束的合同的余额不得大于0"))
    if owner_dimension == "项目":
        assert not result.get("join") and not result["preview"]
        return
    assert result["table_name"] == "test_table" and result["preview"]
    assert result["expression"]["left"] == "balance" and result["filters"][0]["field"] == "ended"
    assert result["join"]["on"] == [{"left": "parent_id", "right": "entity_id"}]
    assert result["join"]["report_date_field"] == "as_of"


def test_generic_status_on_project_row_cannot_filter_contract_termination():
    rules = _pboc_project_rules()
    result = rules.parse_rule_request(user(), _request(request_text="当期结束的合同的实收不得大于0"))
    assert not result["preview"] and not result.get("can_enable")
    assert any("合同" in issue for issue in result["uncertainties"])


@pytest.mark.parametrize(("dialect", "quote", "other_dialect"), [("mysql", "`", "postgresql"), ("postgresql", '"', "mysql")])
def test_pbc_shared_report_keeps_current_period_end_scope_from_the_users_wording(dialect, quote, other_dialect):
    request_text = "当期结束的项目的实收原则上不应该大于 0。"
    classification = ("报告分类无法唯一确定：proj_info_dtl_pboc同时涉及人行大集中报送和资管产品模板、逐笔，"
                      "需求未明确归属，需确认")
    rules = _pboc_project_rules(
        model_filters=[{"field": "c_is_over", "op": "eq", "value": "1"}], selection_reviews=[classification], dialect=dialect,
    )
    rules.model.payloads[0]["report_category"] = ""
    categories = _Processes().list_report_processes() + [
        SimpleNamespace(code="pbc_template", name="资管产品模板、逐笔", active=True),
    ]
    rules.report_navigation = SimpleNamespace(list_report_processes=lambda: categories)

    result = rules.parse_rule_request(user(), _request(request_text=request_text))

    assert result["report_category"] == "group:pbc" and result["report_category_name"] == "人行报送"
    assert result["questions"] == result["uncertainties"] == []
    assert result["model_judgments"]["select_table"]["uncertainties"] == [classification]
    assert result["filters"] == [{"table": "base", "field": "c_is_over", "op": "eq", "value": "1", "confirmed": True}]
    assert any("原则上" in notice for notice in result["notices"])
    assert not any("“一般”" in notice for notice in result["notices"])
    preview = result["preview"]
    assert f"t.{quote}c_is_over{quote} = :filter_1 AND COALESCE(t.{quote}f_equity_total_4001_bal{quote}, 0) > :right_value" in preview["sql_preview"]
    assert preview["sql_params"]["filter_1"] == "1" and preview["sql_params"]["right_value"] == 0
    override = {**preview["definition"], "dialect": other_dialect}
    assert rules.preview_candidate(user(), {"definition": override})["sql_preview"] == preview["sql_preview"]
    saved = rules.save_draft(user(), override)
    version = rules.storage.latest_version(saved["id"])
    assert version["definition"]["dialect"] == dialect
    for category in ("group:pbc", "pbc_central", "pbc_template"):
        assert [item["id"] for item in rules.list_rules(user(), {"report_category": category})["items"]] == [saved["id"]]
    stats = rules.rule_stats(user())
    assert stats["total"] == 1 and stats["unclassified"]["total"] == 0
    assert {item["code"]: item["total"] for item in stats["categories"]} == {
        "group:pbc": 1, "east5": 0,
    }
    rules.metadata.sources = [SimpleNamespace(id="src", name="监管报表", dialect=other_dialect)]
    drift = execute_version(version, {"report_date": "2026-10-31"}, rules.metadata)
    assert drift.error_code == "MAPPING_DRIFT" and not rules.metadata.calls


@pytest.mark.parametrize("request_text", [
    "已终止项目的实收不得大于0",
    "上期结束的项目的实收不得大于0",
    "截至上期已终止的项目的实收不得大于0",
    "截至上期存续项目的实收不得大于0",
    "当期结束或存续项目的实收不得大于0",
    "当期结束的项目的实收原则上不应该大于0，且信托产品类型不等于3",
    "当期结束的项目的实收原则上不应该大于0，且币种为人民币",
    "当期结束的项目的实收原则上不应该大于0，且信托产品类型不等于3且币种为人民币",
    "当期结束的项目的实收原则上不应该大于0，或信托产品类型不等于3",
    "当期结束的项目的实收原则上不应该大于1万元",
])
def test_does_not_compile_when_model_omits_requested_scope_or_threshold(request_text):
    filters = [{"field": "c_is_over", "op": "eq", "value": "1"}]
    if "3且" in request_text or "或" in request_text:
        filters.append({"field": "c_projxttype", "op": "neq", "value": "3"})
    rules = _pboc_project_rules(model_filters=filters)
    result = rules.parse_rule_request(user(), _request(request_text=request_text))
    assert result["preview"] is None and result["preview_error"]
    assert result["can_enable"] is False
    assert "candidate_options" not in result and result["status"] == "needs_clarification"


@pytest.mark.parametrize(("op", "right"), [("lte", 0), ("gt", 8)])
def test_does_not_compile_a_model_comparison_that_changes_the_request(op, right):
    rules = _pboc_project_rules()
    rules.model.payloads[1]["expression"].update(op=op, right=right)
    result = rules.parse_rule_request(user(), _request(request_text="当期结束项目实收不得大于0"))
    assert result["preview"] is None and "比较方向或阈值" in result["preview_error"]


def test_current_end_filter_survives_without_particle_and_rejects_conflicting_dictionary():
    rules = _pboc_project_rules()
    request = _request(request_text="当期结束项目实收不得大于0")
    candidate = rules.parse_rule_request(user(), request)
    assert candidate["preview"]["sql_params"]["filter_1"] == "1"
    broadened = {**candidate["preview"]["definition"], "filters": []}
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.preview_candidate(user(), broadened)
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.save_draft(user(), {**broadened, "filters": candidate["filters"],
                                  "expression": {**candidate["expression"], "right": 9}})
    rules.model.calls.clear()
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "c_is_over").values(dictionary="1-是\n1-否"))
    blocked = rules.parse_rule_request(user(), request)
    assert blocked["preview"] is None and "歧义" in blocked["preview_error"]


@pytest.mark.parametrize("missing_evidence", ["measure", "dictionary", "alternative"])
def test_field_reviews_keep_the_unproven_part_even_when_model_selects_real_columns(missing_evidence):
    scope_question = _TERMINATION_REVIEW
    if missing_evidence == "alternative":
        scope_question += "或 other_table.c_is_over"
    competing = [("other_amount", "另一种实收金额", "decimal", "")] if missing_evidence == "measure" else []
    rules = _pboc_project_rules(selection_reviews=[scope_question + "，以及" + _MEASURE_REVIEW], extra_fields=competing)
    if missing_evidence == "dictionary":
        with rules.storage.database.begin() as connection:
            connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "c_is_over").values(dictionary=""))
    candidate = rules.parse_rule_request(user(), _request(request_text="当期终止项目的实收不得大于 0"))
    if missing_evidence == "alternative":
        assert candidate["uncertainties"] == [] and candidate["can_enable"]
    else:
        expected = _MEASURE_REVIEW if missing_evidence == "measure" else scope_question
        assert expected in candidate["uncertainties"]
        assert not candidate["can_enable"]
        if missing_evidence == "dictionary":
            assert candidate.get("preview") is None and "当期终止字段" in candidate["preview_error"]


@pytest.mark.parametrize("scope_note", ["存续范围对应的状态字段和状态码尚未确认",
                                        "需确认哪个用于筛选存续项目", "存续项目用哪一列过滤？"])
@pytest.mark.parametrize(("separator", "independent"), [("", ""), ("，", "关联键无法确认"),
                                                        ("以及", "截止日期尚未确认")])
def test_first_active_scope_choice_reaches_backend_sql_without_repeat_prompt(scope_note, separator, independent):
    # 实际截图措辞和模型两轮变体，并核对独立问题不被一并放行。
    mixed = scope_note.rstrip("？")
    if independent:
        mixed += separator + independent
    rules, model = _rules([
        _select_payload(target={"table": "reg_pub_project_account_info"}, uncertainties=["需确认存续范围使用哪个状态字段。"]),
        _generate_payload(expression={"left": "start_date", "op": "is_null"}, uncertainties=[mixed],
                          filters=[{"table": "base", "field": "pro_status", "op": "eq", "value": "2"}]),
    ], table=PROJECT_TABLE, table_cn="项目基本信息", fields=PROJECT_FIELDS, extra_tables=[{
        "name": "reg_pub_project_account_info", "cn": "项目账户表", "dimension": "账户", "fields": PROJECT_FIELDS[:3],
    }])
    with rules.storage.database.begin() as connection:
        for name, entry in [("c_projstatus", "1-存续"), ("pro_status", "2-存续"), ("pro_isclose", "1-存续（未完结）")]:
            connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == name).values(dictionary=entry))

    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目开始日期不能为空"))
    question = next(item for item in candidate["questions"] if item["id"] == "filters.0")
    assert candidate["table_name"] == PROJECT_TABLE and "candidate_options" not in candidate
    assert [item["selection"]["field"] for item in question["options"]] == ["c_projstatus", "pro_status", "pro_isclose"]
    assert question["remember_scope"] == "active_status"
    choice = question["options"][0]
    assert choice["selection"] == {"table": "base", "field": "c_projstatus", "op": "eq", "value": "1", "confirmed": True}
    assert candidate["filters"][0]["confirmed"] is False
    assert candidate["uncertainties"] == [question["uncertainty"]] + ([independent] if independent else [])
    # 同表单逻辑：只对关联到该选项的事项记录处理结果，不给其余问题批量写已确认。
    definition = {**candidate, "questions": [], "name": candidate["rule_name"], "filters": [choice["selection"]],
                  "uncertainty_resolutions": [choice["label"] if issue == question["uncertainty"] else ""
                                              for issue in candidate["uncertainties"]]}
    if independent:
        with pytest.raises(AppError):
            rules.preview_candidate(user(), {"definition": definition})
        assert not review_ready(definition)
        definition["uncertainty_resolutions"][-1] = "已补充该项业务口径"
    preview = rules.preview_candidate(user(), {"definition": definition})
    sql = preview["sql_preview"]
    assert '"c_projstatus" = :filter_1' in sql
    assert preview["sql_params"]["filter_1"] == "1"
    assert 't."c_projname" AS "项目名全称"' in sql
    assert not any(f'"{field}"' in sql for field in ("pro_status", "pro_isclose", "c_acstate_origin", "c_proj_name"))
    normalized = preview["definition"]
    assert all(normalized["uncertainty_resolutions"])
    assert review_ready(normalized)
    result = rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"]})
    assert result["passed_count"] >= 4 and result["failed_count"] == result["not_run_count"] == 0
    assert {case["row"]["base"]["c_projstatus"]: case["actual_count"] for case in result["cases"]
            if case["row"]["base"]["start_date"] is None}["1"] == 1
    outside = next(case for case in result["cases"] if case["name"] == "筛选不命中")
    assert outside["row"]["base"]["start_date"] is None and outside["actual_count"] == 0
    assert preview["persisted"] is result["persisted"] is False
    assert len(model.calls) == 2
    assert rules.storage.visible_rules("1") == []


@pytest.mark.parametrize("table_name", [PROJECT_TABLE, "another_project_table"])
def test_preferred_project_name_is_scoped_to_exact_physical_table(table_name):
    table = {"id": 1, "table_name": table_name, "dimension": "项目"}
    fields = [{"field_name": name, "field_cn": cn, "data_type": kind, "is_pk": key}
              for name, cn, kind, key in PROJECT_FIELDS]
    result = infer_project_context({}, table, fields, [table], {1: fields})
    if table_name == PROJECT_TABLE:
        assert result["context"]["name_field"] == "c_projname"
        assert not result["questions"]
        supplied = {"project_context": {"mode": "base", "name_field": "c_proj_name"}}
        assert infer_project_context(supplied, table, fields, [table], {1: fields})["context"]["name_field"] == "c_projname"
        missing = [field for field in fields if field["field_name"] != "c_projname"]
        result = infer_project_context({}, table, missing, [table], {1: missing})
        assert result["context"] is None and not result["questions"]
        assert "c_projname" in result["uncertainties"][0]
    else:
        assert result["context"] is None
        assert result["questions"][0]["id"] == "project_context.name_field"
        assert {option["value"] for option in result["questions"][0]["options"]} == {"c_projname", "c_proj_name"}


def test_second_table_must_belong_to_the_same_document_source():
    rules, model = make_rules(related=True)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "state_table").values(data_source_name="监管报表"))
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text="存续项目实收不为0"))
    assert error.value.code == "MODEL_RESPONSE_INVALID"
    assert len(model.calls) == 1


def test_saved_scope_retests_current_version_and_document_change_blocks_confirmation():
    from tests.modules.data_validation.support import doc_xlsx_bytes
    rules, _model = make_rules()
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目实收信托不为0"))
    definition = resolved_definition(candidate)
    definition["null_policy"] = "skip"
    preview = rules.preview_candidate(user(), definition)
    rule = rules.save_draft(user(), definition)
    version = rules.storage.latest_version(rule["id"])
    assert version["content_sha256"] == preview["content_sha256"]
    assert version["definition"]["mapping_version"].startswith("doc-v1-")
    columns = [{"column_name": name, "comment": label, "data_type": kind} for name, label, kind, _pk in FIELDS]
    rules.metadata.describe_table = lambda _source, _table: {"columns": columns}
    result = rules.run_tests(user(), rule["id"], 1)
    assert result["persisted"] is True
    assert result["content_sha256"] == version["content_sha256"]
    assert result["failed_count"] == result["not_run_count"] == 0
    assert rules.storage.list_cases(rule["id"], 1)
    rules.metadata.describe_table = lambda _source, _table: {"columns": [item for item in columns if item["column_name"] != "business_day"]}
    with pytest.raises(AppError) as drift:
        rules.run_tests(user(), rule["id"], 1)
    assert drift.value.code == "MAPPING_DRIFT"
    assert all(item["status"] == "not_run" for item in rules.storage.list_cases(rule["id"], 1))
    with pytest.raises(AppError):
        rules.confirm_rule(user(), rule["id"], 1, version["content_sha256"])
    rules.metadata.describe_table = lambda _source, _table: {"columns": columns}
    rules.run_tests(user(), rule["id"], 1)
    rules.import_document(user(), "new-doc.xlsx", doc_xlsx_bytes(fields=FIELDS))
    with pytest.raises(AppError) as error:
        rules.confirm_rule(user(), rule["id"], 1, version["content_sha256"])
    assert error.value.code == "CONFLICT_VERSION"


def test_unconfirmed_ai_scope_cannot_save_compiled_sql_or_test_results():
    rules, _model = make_rules(unary=True)
    candidate = rules.parse_rule_request(user(), _request(request_text="存续项目项目开始日不能为空"))
    definition = resolved_definition(candidate)
    definition["filters"][0]["confirmed"] = False
    with pytest.raises(AppError):
        rules.save_draft(user(), definition)
    with pytest.raises(AppError):
        rules.test_candidate(user(), {"definition": definition})
    assert rules.storage.visible_rules("1") == []
