from __future__ import annotations

import sqlite3
from copy import deepcopy
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.analysis_result_cache import model_snapshot
from auto_check.modules.data_validation.compiler import compile_rule
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.executor import execute_version
from auto_check.modules.data_validation.project_driver import DRIVER_VERSION, bind_project_driver, normalize_project_driver, resolve_project_driver
from auto_check.modules.data_validation.query_spec import needs_issue_kind, validate_query_spec, validate_spec_against_columns
from tests.modules.data_validation.support import SequenceModel, service, user
from tests.modules.data_validation.test_ai_service import SourceOnlyMetadata, _Processes, _request


DAY = "2026-11-30"
SOURCE = "监管报送集市"


def field(name, caption, kind="varchar", *, pk="", source=(), logic="直取", dictionary=""):
    return {
        "field_name": name,
        "field_cn": caption,
        "data_type": kind,
        "is_pk": pk,
        "dictionary": dictionary,
        "logic": logic,
        "source_table": source[0] if source else "",
        "source_field": source[1] if source else "",
    }


def table(table_id, name, caption, dimension, fields):
    return {
        "id": table_id,
        "data_source_name": SOURCE,
        "table_name": name,
        "table_name_cn": caption,
        "sheet_name": "人行_测试",
        "dimension": dimension,
        "period": "月",
        "scope": "",
        "source_desc": "虚构测试文档",
        "fields": fields,
    }


def document_tables():
    project_fields = [
        field("day", "数据日期", "date"),
        field(
            "project_key", "TCMP编号", pk="Y", source=("upstream.entity", "entity_id"),
            logic="直接取项目主数据的项目编号[entity_id]。",
        ),
        field("project_name", "项目名全称"),
        field("transfer_flag", "收益转让标识", dictionary="1-是\n2-否"),
        field("project_total", "项目总额", "numeric"),
        field("project_received", "项目实收", "numeric"),
    ]
    asset_fields = [
        field("row_id", "明细编号", pk="Y"),
        field("day", "数据日期", "date"),
        field("owner_ref", "项目编号", source=("mart.project_snapshot", "project_key")),
        field("local_name", "项目名称", source=("mart.project_snapshot", "project_name")),
        field(
            "local_flag", "收益转让标识", source=("mart.project_snapshot", "transfer_flag"),
            dictionary="1-是\n2-否",
        ),
        field("detail_scope", "本明细检查范围", "int"),
        field("amount", "资产收益权余额", "numeric"),
        field("other_amount", "其他余额", "numeric"),
    ]
    funding_fields = [
        field("funding_id", "募集明细编号", pk="Y"),
        field("day", "数据日期", "date"),
        field("funding_owner", "项目编号", source=("mart.project_snapshot", "project_key")),
        field("funding_received", "募集实收", "numeric"),
    ]
    other_fields = [
        field("other_id", "其他编号", pk="Y"),
        field("day", "数据日期", "date"),
        field("other_amount", "其他表余额", "numeric"),
    ]
    return [
        table(1, "project_snapshot", "项目快照", "项目", project_fields),
        table(2, "asset_rows", "资产明细", "项目＋合同", asset_fields),
        table(3, "funding_rows", "募集明细", "项目＋募集", funding_fields),
        table(4, "other_rows", "其他明细", "合同", other_fields),
    ]


def document_parts(tables=None):
    tables = deepcopy(tables or document_tables())
    fields = {item["id"]: item["fields"] for item in tables}
    bare = [{key: value for key, value in item.items() if key != "fields"} for item in tables]
    return bare, fields


def definition(name="asset_rows", **changes):
    result = {
        "name": "项目余额检查",
        "description": "收益转让标识为是的项目，资产收益权余额应大于0",
        "rule_type": "field_compare",
        "source_id": "src",
        "dialect": "postgresql",
        "table_name": name,
        "business_key": "row_id",
        "report_date_field": "day",
        "expression": {"left": "amount", "op": "lte", "right_type": "value", "right": 0},
        "violation_message": "资产收益权余额应大于0",
        "null_policy": "zero",
        "equality_policy": "allow_equal",
        "filters": [{"table": "base", "field": "detail_scope", "op": "eq", "value": 1, "confirmed": True}],
    }
    result.update(changes)
    return result


def bind(definition_value, tables=None, *, required=True):
    tables = deepcopy(tables or document_tables())
    bare, fields = document_parts(tables)
    base = next(item for item in bare if item["table_name"] == definition_value["table_name"])
    return bind_project_driver(
        definition_value,
        base,
        fields[base["id"]],
        bare,
        fields,
        required=required,
    )


def columns(fields):
    return [
        {
            "column_name": item["field_name"],
            "comment": item["field_cn"],
            "field_cn": item["field_cn"],
            "data_type": item["data_type"],
            "is_pk": item["is_pk"],
            "logic": item["logic"],
            "dictionary": item["dictionary"],
            "source_table": item["source_table"],
            "source_field": item["source_field"],
        }
        for item in fields
    ]


def make_rules(payloads, tables=None):
    model = SequenceModel(payloads)
    _database, rules = service(metadata=SourceOnlyMetadata(), model=model, report_navigation=_Processes())
    tables = deepcopy(tables or document_tables())
    rules.storage.create_document(
        name="虚构项目文档",
        file_name="unused-in-memory",
        content_sha256="a" * 64,
        table_count=len(tables),
        field_count=sum(len(item["fields"]) for item in tables),
        warnings=[],
        imported_by="1",
        tables=tables,
    )
    return rules, model


def semantic_draft(*, target="asset_rows", metric="amount", business_key="row_id", marker=True):
    result = {
        "rule_name": "收益转让项目余额检查",
        "rule_type": "field_compare",
        "expression": {"left": metric, "op": "lte", "right_type": "value", "right": 0},
        "violation_message": "资产收益权余额应大于0",
        "null_policy": "zero",
        "equality_policy": "allow_equal",
        "business_key": business_key,
        "semantic_intent": {
            "metrics": [{"side": "left", "term": "资产收益权余额", "fields": [metric]}],
            "scopes": [{
                "category": "收益转让为是",
                "table": "base",
                "fields": ["local_flag"],
                "memberships": {"local_flag": {"include": ["1"], "exclude": ["2"]}},
            }],
            "open_questions": [],
        },
        "filters": [{"table": "base", "field": "detail_scope", "op": "eq", "value": 1}],
        "uncertainties": [],
        "unsupported_requirements": [],
    }
    if marker:
        result["project_driver"] = {"version": 1, "table_role": "related"}
    return result


def test_project_itself_and_two_received_dimensions_get_independent_roles():
    tables = document_tables()
    project = definition(
        "project_snapshot",
        business_key="project_key",
        expression={"left": "project_received", "op": "lt", "right_type": "value", "right": 0},
        filters=[],
    )
    bound_project = bind(project, tables)
    assert bound_project["definition"]["project_driver"] == {"version": DRIVER_VERSION, "table_role": "base"}
    assert bound_project["definition"]["project_context"]["mode"] == "base"
    assert "join" not in bound_project["definition"]

    funding = definition(
        "funding_rows",
        business_key="funding_id",
        expression={"left": "funding_received", "op": "lt", "right_type": "value", "right": 0},
        filters=[],
    )
    bound_funding = bind(funding, tables)
    assert bound_funding["definition"]["project_driver"] == {"version": DRIVER_VERSION, "table_role": "related"}
    assert bound_funding["definition"]["project_context"]["key"] == {
        "left": "funding_owner", "right": "project_key",
    }
    assert bound_funding["definition"]["expression"]["left"] == "funding_received"


def test_detail_with_local_name_uses_project_authority_and_keeps_detail_scope():
    original = definition()
    original["filters"].insert(0, {
        "table": "base", "field": "local_flag", "op": "eq", "value": "1", "confirmed": True,
    })

    result = bind(original)

    bound = result["definition"]
    assert bound["project_driver"] == {"version": DRIVER_VERSION, "table_role": "related"}
    assert bound["project_context"]["mode"] == "lookup"
    assert bound["project_context"]["name_field"] == "project_name"
    assert bound["project_context"]["date_field"] == "day"
    assert bound["join"]["table_name"] == "project_snapshot"
    assert bound["join"]["on"] == [{"left": "owner_ref", "right": "project_key"}]
    assert [(item["table"], item["field"]) for item in bound["filters"]] == [
        ("related", "transfer_flag"), ("base", "detail_scope"),
    ]
    assert bound["expression"]["left"] == "amount"
    assert bound["business_key"] == "row_id"
    assert result["field_mapping"]["local_name"] == "project_name"
    assert original["filters"][0]["table"] == "base"


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
@pytest.mark.parametrize("project_role", ["base", "related"])
@pytest.mark.parametrize("explicit_date_pairs", [1, 2])
def test_new_project_binding_emits_one_period_join(dialect, project_role, explicit_date_pairs):
    tables = document_tables()
    tables[1]["fields"][1]["field_name"] = "stamp"
    if project_role == "base":
        original = definition("project_snapshot", dialect=dialect, business_key="project_key", filters=[],
                              expression={"left": "project_received", "op": "lt", "right_type": "value", "right": 0})
        key = {"left": "project_key", "right": "owner_ref"}
        original["join"] = {"table_name": "asset_rows", "on": [key], "report_date_field": "stamp"}
    else:
        original = definition(dialect=dialect, report_date_field="stamp")
        key = {"left": "owner_ref", "right": "project_key"}
        original["join"] = {"table_name": "project_snapshot", "on": [key], "report_date_field": "day"}
    expected = bind(original, tables)["definition"]
    expected_sql = compile_rule({"definition": expected})
    date_pair = {"left": original["report_date_field"], "right": original["join"]["report_date_field"]}
    original["join"]["on"].extend(dict(date_pair) for _ in range(explicit_date_pairs))
    bound = bind(original, tables)
    assert not bound["uncertainties"] and not bound["unsupported_requirements"]
    assert bound["definition"]["join"]["on"] == [key]
    assert compile_rule({"definition": bound["definition"]}) == expected_sql
    date_match = 'd.`stamp` = p.`day`' if dialect == "mysql" else 'd."stamp" = p."day"'
    assert expected_sql[0].count(date_match) == 1
    assert len(original["join"]["on"]) == 1 + explicit_date_pairs


@pytest.mark.parametrize("version", [1, 2])
def test_revalidating_stored_project_rules_preserves_explicit_date_keys_and_sql(version):
    stored = bind(definition())["definition"]
    stored["project_driver"]["version"] = version
    stored["join"]["on"].append({"left": "day", "right": "day"})
    expected_sql = compile_rule({"definition": stored})
    bare, fields = document_parts()
    bound = bind_project_driver(stored, bare[1], fields[2], bare, fields, required=True, preserve_version=True)
    assert not bound["uncertainties"] and not bound["unsupported_requirements"]
    assert bound["definition"] == stored
    assert compile_rule({"definition": bound["definition"]}) == expected_sql
    resolve_project_driver(stored, bare[1], fields[2], bare, fields)


def test_indirect_lineage_is_accepted_only_when_all_sources_converge():
    tables = document_tables()
    summary_fields = [
        field("summary_id", "汇总编号", pk="Y"),
        field("day", "数据日期", "date"),
        field("summary_owner", "项目编号", source=("mart.asset_rows", "owner_ref")),
        field("summary_amount", "汇总余额", "numeric"),
    ]
    tables.append(table(5, "summary_rows", "剩余期限汇总", "项目＋期限", summary_fields))
    original = definition(
        "summary_rows",
        business_key="summary_id",
        expression={"left": "summary_amount", "op": "eq", "right_type": "value", "right": 0},
        filters=[],
    )

    bound = bind(original, tables)["definition"]

    assert bound["project_driver"]["table_role"] == "related"
    assert bound["project_context"]["key"]["left"] == "summary_owner"
    assert bound["join"]["table_name"] == "project_snapshot"


def test_ambiguous_nonunique_and_third_table_never_fall_back_to_detail_driver():
    tables = document_tables()
    second = deepcopy(tables[0])
    second["id"] = 9
    second["table_name"] = "another_project_snapshot"
    ambiguous = bind(definition(), [*tables, second])
    assert "project_driver" not in ambiguous["definition"]
    assert ambiguous["involved"] and ambiguous["uncertainties"]

    nonunique_tables = document_tables()
    nonunique_tables[0]["fields"][1]["is_pk"] = ""
    nonunique = bind(definition(), nonunique_tables)
    assert "project_driver" not in nonunique["definition"]
    assert nonunique["uncertainties"]

    original = definition(
        join={
            "table_name": "other_rows",
            "on": [{"left": "amount", "right": "other_amount"}],
            "report_date_field": "day",
            "relationship_confirmed": True,
            "unmatched_policy": "exclude",
        },
        expression={"left": "amount", "op": "neq", "right_table": "related", "right": "other_amount"},
    )
    third = bind(original)
    assert "project_driver" not in third["definition"]
    assert third["definition"]["join"] == original["join"]
    assert third["definition"]["expression"] == original["expression"]
    assert third["unsupported_requirements"]


def test_pure_non_project_definition_and_legacy_sql_are_not_rewritten():
    tables = document_tables()
    bare, fields = document_parts(tables)
    other = bare[3]
    legacy = definition(
        "other_rows",
        business_key="other_id",
        expression={"left": "other_amount", "op": "eq", "right_type": "value", "right": 0},
        null_policy="skip",
        filters=[],
    )
    sql, params = compile_rule({"definition": legacy})

    result = bind_project_driver(legacy, other, fields[other["id"]], bare, fields, required=False)

    assert result["involved"] is False
    assert result["definition"] == legacy
    assert compile_rule({"definition": result["definition"]}) == (sql, params)
    assert needs_issue_kind(legacy) is False


@pytest.mark.parametrize("raw", [
    None,
    {},
    {"version": True, "table_role": "base"},
    {"version": 1, "table_role": "unknown"},
    {"version": 1},
    {"version": 1, "table_role": "base", "extra": True},
])
def test_driver_shape_is_strict(raw):
    with pytest.raises(AppError) as error:
        normalize_project_driver(raw)
    assert error.value.code == "VALIDATION_ERROR"


def test_driver_real_columns_key_types_uniqueness_and_on_are_rechecked():
    bound = bind(definition())["definition"]
    bare, fields = document_parts()
    base_columns = columns(fields[2])
    project_columns = columns(fields[1])
    spec = validate_spec_against_columns(bound, base_columns, project_columns)
    assert spec["project_driver"]["table_role"] == "related"
    assert needs_issue_kind(bound) is True

    wrong_key = deepcopy(base_columns)
    wrong_key[2]["data_type"] = "int"
    with pytest.raises(AppError):
        validate_spec_against_columns(bound, wrong_key, project_columns)

    not_unique = deepcopy(project_columns)
    not_unique[1]["is_pk"] = ""
    with pytest.raises(AppError):
        validate_spec_against_columns(bound, base_columns, not_unique)

    extra_on = deepcopy(bound)
    extra_on["join"]["on"].append({"left": "day", "right": "day"})
    extra_on["join"]["on"].append({"left": "detail_scope", "right": "transfer_flag"})
    with pytest.raises(AppError):
        validate_query_spec(extra_on)


@pytest.mark.parametrize("missing_policy", [None, "exclude", "review"])
def test_semantic_generation_binds_scopes_cache_save_and_preview_hash(missing_policy):
    draft = semantic_draft()
    selection = {"target": {"table": "asset_rows"}, "report_category": "pbc_central"}
    if missing_policy:
        selection["related_target"] = {"table": "project_snapshot"}
        draft["join"] = {"table_name": "project_snapshot", "on": [{"left": "owner_ref", "right": "project_key"},
                                                               {"left": "day", "right": "day"}],
                         "report_date_field": "day", "relationship_confirmed": True, "unmatched_policy": missing_policy}
    rules, model = make_rules([
        selection,
        draft,
    ])
    request = _request(
        request_text="收益转让标识为是的项目，资产收益权余额应大于0",
        analysis_protocol=2,
    )

    result = rules.parse_rule_request(user(), request)

    assert len(model.calls) == 2
    assert result["project_driver"] == {"version": DRIVER_VERSION, "table_role": "related"}
    assert result["preview"] and result["preview"]["sql_preview"]
    preview_definition = result["preview"]["definition"]
    assert preview_definition["join"]["on"] == [{"left": "owner_ref", "right": "project_key"}]
    assert [(item["table"], item["field"]) for item in preview_definition["filters"]] == [
        ("related", "transfer_flag"), ("base", "detail_scope"),
    ]
    intent = preview_definition["semantic_intent"]
    assert intent["scopes"][0]["table"] == "related"
    assert intent["scopes"][0]["fields"] == ["transfer_flag"]
    assert set(intent["dictionary_snapshots"]) == {"related"}
    assert intent["expected_join"]["table_name"] == "project_snapshot"
    assert intent["expected_project_driver"] == preview_definition["project_driver"]
    assert "INNER JOIN" in result["preview"]["sql_preview"]
    saved = rules.save_draft(user(), preview_definition)
    version = rules.storage.latest_version(saved["id"])
    detail = rules.get_rule(user(), saved["id"])
    assert detail["sql_text"] == version["sql_text"]
    assert ":report_date" in detail["sql_display"]
    assert ":violation_message" not in detail["sql_display"] and ":dv_missing_record" not in detail["sql_display"]
    assert version["definition"]["project_driver"] == preview_definition["project_driver"]
    assert version["sql_text"] == result["preview"]["sql_preview"]
    assert version["content_sha256"] == result["preview"]["content_sha256"]
    replayed = rules.preview_candidate(user(), {"definition": version["definition"]}, preserve_result_fields=True)
    assert replayed["content_sha256"] == version["content_sha256"]

    cached_context = rules._analysis_inputs(user(), request)["context"]
    cached = rules.storage.cached_analysis_result(cached_context, request["request_text"])
    assert cached["draft"]["project_driver"] == {"version": 1, "table_role": "related"}
    repeated = rules.parse_rule_request(user("other"), request)
    assert len(model.calls) == 2
    assert repeated["project_driver"] == result["project_driver"]
    assert repeated["preview"]["content_sha256"] == result["preview"]["content_sha256"]


def test_proven_driver_resolves_technical_join_choices_without_resolving_a_metric_choice():
    draft = semantic_draft()
    draft["join"] = {"table_name": "project_snapshot", "on": [{"left": "owner_ref", "right": "project_key"}],
                     "report_date_field": "day", "relationship_confirmed": False, "unmatched_policy": "unresolved"}
    draft["semantic_intent"]["metrics"][0]["fields"] = ["amount", "other_amount"]
    rules, _ = make_rules([
        {"target": {"table": "asset_rows"}, "related_target": {"table": "project_snapshot"}, "report_category": "pbc_central"}, draft,
    ])
    result = rules.parse_rule_request(user(), _request(request_text="收益转让项目余额应大于0", analysis_protocol=2))
    assert {q["id"] for q in result["questions"]} == {"expression.left"}
    assert result["join"]["relationship_confirmed"] is True
    assert result["preview"] is None


def test_field_choices_and_raw_model_snapshot_keep_driver():
    draft = semantic_draft()
    draft["semantic_intent"]["metrics"][0]["fields"] = ["amount", "other_amount"]
    rules, model = make_rules([
        {"target": {"table": "asset_rows"}, "report_category": "pbc_central"},
        draft,
    ])
    request = _request(request_text="收益转让项目余额应大于0", analysis_protocol=2)

    first = rules.parse_rule_request(user(), request)
    assert first["preview"] is None
    assert first["project_driver"]["table_role"] == "related"
    assert any(item["id"] == "expression.left" for item in first["questions"])
    repeated = rules.parse_rule_request(user(), request)
    assert len(model.calls) == 2
    assert repeated["project_driver"] == first["project_driver"]
    assert repeated["questions"] == first["questions"]

    snapshot = model_snapshot({}, draft)
    assert snapshot["draft"]["project_driver"] == draft["project_driver"]


def test_repair_can_complete_a_missing_driver_without_changing_the_metric():
    incomplete = semantic_draft(marker=False, business_key="unknown_locator")
    repaired = semantic_draft()
    rules, model = make_rules([
        {"target": {"table": "asset_rows"}, "report_category": "pbc_central"},
        incomplete, repaired,
    ])
    result = rules.parse_rule_request(user(), _request(
        request_text="收益转让标识为是的项目，资产收益权余额应大于0", analysis_protocol=2,
    ))
    assert len(model.calls) == 3
    assert result["preview"] and result["project_driver"] == {"version": DRIVER_VERSION, "table_role": "related"}
    assert result["expression"] == incomplete["expression"]


@pytest.mark.parametrize("role", ["base", "related"])
def test_document_binding_checks_project_driver_hint_for_scalar_model_draft(role):
    draft = semantic_draft(marker=False)
    selection = {"target": {"table": "asset_rows"}, "report_category": "pbc_central"}
    request = _request(request_text="收益转让标识为是的项目，资产收益权余额应大于0", analysis_protocol=2)
    unmarked, unmarked_model = make_rules([{**selection, "draft": draft}])
    marked, model = make_rules([{**selection, "draft": {
        **draft, "project_driver": {"version": 1, "table_role": role},
    }}])
    expected = unmarked.parse_rule_request(user(), request)["preview"]
    actual = marked.parse_rule_request(user(), request)["preview"]

    assert len(model.calls) == len(unmarked_model.calls)
    assert actual["definition"] == expected["definition"]
    assert actual["sql_preview"] == expected["sql_preview"]
    assert actual["content_sha256"] == expected["content_sha256"]
    assert actual["definition"]["project_driver"] == {"version": DRIVER_VERSION, "table_role": "related"}
    forged = {**actual["definition"], "project_driver": {"version": DRIVER_VERSION, "table_role": "base"}}
    with pytest.raises(AppError):
        marked.preview_candidate(user(), {"definition": forged})


def test_wrong_scalar_model_driver_hint_still_requires_document_lineage():
    tables = document_tables()
    asset = next(item for item in tables if item["table_name"] == "asset_rows")
    key = next(item for item in asset["fields"] if item["field_name"] == "owner_ref")
    key.update(source_table="", source_field="")
    draft = semantic_draft()
    draft["project_driver"]["table_role"] = "base"
    selection = {"target": {"table": "asset_rows"}, "report_category": "pbc_central"}
    rules, _ = make_rules([{**selection, "draft": draft}], tables)
    result = rules.parse_rule_request(user(), _request(
        request_text="收益转让标识为是的项目，资产收益权余额应大于0", analysis_protocol=2,
    ))
    assert not result["preview"]
    assert any("来源" in note for note in result["uncertainties"])


@pytest.mark.parametrize(("marker", "raises"), [
    (None, False),
    ({"version": 99, "table_role": "base"}, True),
    ({"version": 1, "table_role": "sideways"}, True),
])
def test_scalar_model_driver_hint_does_not_bypass_marker_validation(marker, raises):
    draft = {**semantic_draft(marker=False), "project_driver": marker}
    selection = {"target": {"table": "asset_rows"}, "report_category": "pbc_central"}
    rules, _ = make_rules([{**selection, "draft": draft}])
    request = _request(request_text="收益转让标识为是的项目，资产收益权余额应大于0", analysis_protocol=2)
    if raises:
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            rules.parse_rule_request(user(), request)
    else:
        result = rules.parse_rule_request(user(), request)
        assert not result["preview"]


def test_failed_new_project_binding_cannot_be_cleared_into_a_detail_preview():
    tables = document_tables()
    tables[0]["fields"][1]["is_pk"] = ""
    rules, _ = make_rules([
        {"target": {"table": "asset_rows"}, "report_category": "pbc_central"},
        semantic_draft(marker=False),
    ], tables)
    result = rules.parse_rule_request(user(), _request(
        request_text="收益转让标识为是的项目，资产收益权余额应大于0", analysis_protocol=2,
    ))
    assert not result["preview"] and result["uncertainties"]
    edited = {**result, "name": result["rule_name"], "questions": [], "uncertainties": [],
              "uncertainty_resolutions": [], "unsupported_requirements": []}
    with pytest.raises(AppError):
        rules.preview_candidate(user(), edited)


def test_project_only_model_rule_has_no_detail_join():
    draft = semantic_draft(target="project_snapshot", metric="project_total", business_key="project_key")
    draft["project_driver"] = {"version": 1, "table_role": "base"}
    draft["semantic_intent"]["metrics"][0]["term"] = "项目总额"
    draft["semantic_intent"]["scopes"][0]["fields"] = ["transfer_flag"]
    draft["semantic_intent"]["scopes"][0]["memberships"] = {
        "transfer_flag": {"include": ["1"], "exclude": ["2"]},
    }
    draft["filters"] = []
    rules, _model = make_rules([
        {"target": {"table": "project_snapshot"}, "report_category": "pbc_central"},
        draft,
    ])

    result = rules.parse_rule_request(user(), _request(request_text="项目总额应大于0", analysis_protocol=2))

    assert result["project_driver"] == {"version": DRIVER_VERSION, "table_role": "base"}
    assert result["project_context"]["mode"] == "base"
    assert "LEFT JOIN" not in result["preview"]["sql_preview"]
    assert result["filters"] == [{
        "table": "base", "field": "transfer_flag", "op": "eq", "value": "1", "confirmed": True,
    }]


def test_legacy_project_definition_preview_and_save_do_not_gain_driver():
    rules, _model = make_rules([])
    legacy = definition(
        generation_mode="manual",
        project_context={"mode": "base", "code_field": "owner_ref", "name_field": "local_name", "confirmed": True},
    )

    preview = rules.preview_candidate(user(), {"definition": legacy})
    assert "project_driver" not in preview["definition"]
    assert "LEFT JOIN" not in preview["sql_preview"]
    saved = rules.save_draft(user(), legacy)
    version = rules.storage.latest_version(saved["id"])
    assert "project_driver" not in version["definition"]
    replayed = rules.preview_candidate(user(), {"definition": version["definition"]}, preserve_result_fields=True)
    assert replayed["sql_preview"] == version["sql_text"]
    assert replayed["content_sha256"] == version["content_sha256"]


def test_compiled_driver_preserves_multirow_and_chinese_identity_without_missing_period_rows():
    rules, _model = make_rules([
        {"target": {"table": "asset_rows"}, "report_category": "pbc_central"},
        semantic_draft(),
    ])
    result = rules.parse_rule_request(
        user(), _request(request_text="收益转让标识为是的项目，资产收益权余额应大于0", analysis_protocol=2),
    )
    definition_value = result["preview"]["definition"]
    sql = result["preview"]["sql_preview"]
    _bare, fields = document_parts()

    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE project_snapshot "
            "(day date, project_key text, project_name text, transfer_flag text, project_total numeric, project_received numeric)",
        )
        connection.execute(
            "CREATE TABLE asset_rows "
            "(row_id text, day date, owner_ref text, local_name text, local_flag text, "
            "detail_scope integer, amount numeric, other_amount numeric)",
        )
        connection.executemany("INSERT INTO project_snapshot VALUES (?, ?, ?, ?, ?, ?)", [
            (DAY, "P1", "项目甲", "1", 0, 0),
            (DAY, "P2", "项目乙", "1", 0, 0),
            (DAY, "P3", "项目丙", "1", 0, 0),
            (DAY, "P4", "范围外项目", "2", 0, 0),
        ])
        connection.executemany("INSERT INTO asset_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            ("a1", DAY, "P1", "副本名称", "2", 1, 0, 0),
            ("a2", DAY, "P1", "副本名称", "2", 1, None, 0),
            ("excluded", DAY, "P1", "副本名称", "2", 0, 0, 0),
            ("old", "2026-10-31", "P2", "副本名称", "2", 1, 0, 0),
            ("c1", DAY, "P3", "副本名称", "2", 1, None, 0),
            ("outside", DAY, "P4", "副本名称", "2", 1, 0, 0),
        ])

        def describe(_source, name):
            return {"columns": columns(fields[1] if name == "project_snapshot" else fields[2])}

        def select(_source, statement, params, **_limits):
            cursor = connection.execute(statement, params)
            return SimpleNamespace(
                columns=[item[0] for item in cursor.description], rows=cursor.fetchall(), truncated=False,
            )

        metadata = SimpleNamespace(describe_table=describe, execute_select=select)
        run = execute_version(
            {"definition": definition_value, "sql_text": sql}, {"report_date": DAY}, metadata,
        )

    assert run.status == "VIOLATION", run.error_code
    assert sorted((row["project_code"], row["business_key"], row["issue_kind"]) for row in run.rows) == [
        ("P1", "a1", "numeric"), ("P1", "a2", "numeric"),
        ("P3", "c1", "numeric"),
    ]
    assert {row["project_code"]: row["project_name"] for row in run.rows} == {
        "P1": "项目甲", "P3": "项目丙",
    }
    date_alias = definition_value["result_aliases"]["data_date"]
    assert all(row["values"][date_alias] == DAY for row in run.query_results)
    assert definition_value["result_aliases"]["project_code"] == "TCMP编号"
    assert definition_value["result_aliases"]["data_date"] == "数据日期"
