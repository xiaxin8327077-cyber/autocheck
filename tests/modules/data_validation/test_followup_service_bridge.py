"""service 项目身份 + 通用 AI 建议整合的消费桥：真实文档、真实明细、恶意输入不削弱门禁。"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import insert

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from tests.modules.data_validation.support import Metadata, SequenceModel, doc_xlsx_bytes, service, user
from tests.modules.data_validation.test_ai_service import (
    SourceOnlyMetadata, _Processes, _generate_payload, _request, _select_payload,
)


def _add_table(rules, *, name: str, cn: str, dimension: str, fields, source_desc: str = "") -> None:
    document = rules.storage.active_document()
    base = rules.storage.doc_tables(int(document["id"]))[0]
    row = {key: value for key, value in base.items() if key != "id"}
    row.update(table_name=name, table_name_cn=cn, dimension=dimension, source_desc=source_desc)
    template = rules.storage.doc_fields(int(base["id"]))[0]
    with rules.storage.database.begin() as connection:
        table_id = connection.execute(insert(DOC_TABLES).values(**row)).inserted_primary_key[0]
        for order, (field_name, field_cn, data_type, is_pk) in enumerate(fields):
            field_row = {key: value for key, value in template.items() if key != "id"}
            field_row.update(
                table_id=int(table_id), field_name=field_name, field_cn=field_cn,
                data_type=data_type, is_pk=is_pk, sort_order=order,
            )
            connection.execute(insert(DOC_FIELDS).values(**field_row))


def _rules(payloads, *, table="test_table", table_cn="测试表", dimension="项目", fields=None, extra_tables=()):
    model = SequenceModel(payloads)
    _database, rules = service(
        metadata=SourceOnlyMetadata(), model=model, report_navigation=_Processes(),
    )
    content = doc_xlsx_bytes(table=table, table_cn=table_cn, dimension=dimension, fields=fields)
    rules.import_document(user(), "doc.xlsx", content)
    for spec in extra_tables:
        _add_table(rules, **spec)
    return rules, model


def _project_definition(*, source_id="src", table_name="contract", context=None, expression=None):
    definition = {
        "name": "合同金额异常", "rule_type": "field_compare", "dialect": "mysql",
        "source_id": source_id, "table_name": table_name, "business_key": "c_pactid",
        "report_date_field": "report_date", "violation_message": "金额异常",
        "null_policy": "skip", "equality_policy": "allow_equal",
        "expression": expression or {"left": "amount", "op": "gt", "right_type": "value", "right": 0},
    }
    if context is not None:
        definition["project_context"] = context
    return definition


def test_mixed_sentence_suggestions_are_isolated_and_do_not_block_main():
    fields = [("row_id", "编号", "varchar", "Y"), ("c_projcode", "项目编号", "varchar", ""),
              ("c_projname", "项目名称", "varchar", ""),
              ("amount", "金额", "decimal", ""),
              ("report_date", "报送日期", "date", "")]
    generate = _generate_payload(
        expression={"left": "金额", "op": "eq", "right_type": "value", "right": 0},
        uncertainties=["“金额”可能对应多个字段；未指定业务日期口径，是否需过滤特定日期数据"],
        ai_suggestions=[
            {"title": "伪造建议", "references": [{"table_name": "test_table", "field_name": "nope"}]},
            {"title": "缺引用建议"},
            {"title": "恶意建议", "references": [{"table_name": "test_table", "field_name": "amount"}],
             "preconditions": [["嵌套"], {"bad": True}, 7, "有效"], "sql": {"raw": "SELECT 1"}},
        ],
    )
    rules, model = _rules([_select_payload(), generate], fields=fields)

    candidate = rules.parse_rule_request(user(), _request(request_text="金额不得为 0"))

    assert len(model.calls) == 2
    assert candidate["preview"] is None
    assert all("建议" not in reason for reason in candidate["uncertainties"])
    assert isinstance(candidate["ai_suggestions"], list)
    # 未知/缺引用不能冒充文档事实；有效模型提案展示，但不采用模型SQL或执行定义。
    assert len(candidate["ai_suggestions"]) == 1
    suggestion = candidate["ai_suggestions"][0]
    assert suggestion["provenance"] == "model" and suggestion["support_level"] == "needs_confirmation"
    assert suggestion["preconditions"] == ["有效"]
    assert "definition" not in suggestion and "sql" not in suggestion
    # 处理主规则自身的歧义后才能编译，独立建议不进入规则定义。
    definition = {**candidate, "uncertainty_resolutions": ["采用金额字段"] * len(candidate["uncertainties"])}
    assert "ai_suggestions" not in rules.preview_candidate(user(), definition)["definition"]


def test_three_independent_tables_with_contract_project_identity():
    contract_fields = [
        ("c_pactid", "合同编号", "varchar", "Y"),
        ("project_code", "项目编号", "varchar", ""),
        ("amount", "金额", "decimal", ""),
        ("report_date", "报送日期", "date", ""),
    ]
    dim_fields = [
        ("project_code", "项目编号", "varchar", "Y"),
        ("project_name", "项目名称", "varchar", ""),
        ("report_date", "报送日期", "date", "Y"),
    ]
    balance_fields = [
        ("project_code", "项目编号", "varchar", "Y"),
        ("balance_amt", "余额", "decimal", ""),
        ("report_date", "余额日期", "date", ""),
    ]
    rules, _model = _rules(
        [_select_payload(target={"table": "contract"}),
         _generate_payload(expression={"left": "金额", "op": "eq", "right_type": "value", "right": 0})],
        table="contract", table_cn="合同明细", dimension="合同", fields=contract_fields,
        extra_tables=[
            {"name": "dim_project", "cn": "项目维表", "dimension": "项目", "fields": dim_fields},
            {"name": "balance_sum", "cn": "余额汇总", "dimension": "余额", "fields": balance_fields},
        ],
    )

    candidate = rules.parse_rule_request(user(), _request(request_text="合同金额不得为 0"))

    context = candidate["project_context"]
    assert context["mode"] == "lookup"
    assert context["table_name"] == "dim_project"
    assert context["key"] == {"left": "project_code", "right": "project_code"}
    assert context["unique_evidence"]["kind"] == "pk"
    # lookup 关系需具体确认问题，不能只出合同键。
    assert any(item["id"] == "project_context.confirmed" for item in candidate["questions"])
    assert candidate["preview"] is None
    # 用户确认后按真实项目维表预览，project_columns 一并透传。
    confirmed = {**candidate, "name": candidate["rule_name"], "questions": []}
    confirmed["project_context"] = {**context, "confirmed": True}
    preview = rules.preview_candidate(user(), confirmed)
    assert "project_name" in preview["sql_preview"]
    assert preview["project_columns"]
    assert "ai_suggestions" not in preview["definition"]


def test_single_unknown_grain_still_returns_optional_suggestions():
    fields = [("row_id", "编号", "varchar", "Y"), ("amount", "金额", "decimal", ""),
              ("report_date", "报送日期", "date", "")]
    generate = _generate_payload(
        expression={"left": "金额", "op": "eq", "right_type": "value", "right": 0},
        ai_suggestions=[{
            "title": "核实金额完整性", "reason": "建议核实",
            "references": [{"table_name": "test_table", "field_name": "amount"}],
        }],
    )
    rules, _model = _rules([_select_payload(), generate], dimension="", fields=fields)

    candidate = rules.parse_rule_request(user(), _request(request_text="金额不得为 0"))

    assert candidate["preview"] is not None
    assert [item["title"] for item in candidate["ai_suggestions"]] == ["核实金额完整性"]
    assert candidate["ai_suggestions"][0]["provenance"] == "model"
    assert "definition" not in candidate["ai_suggestions"][0]


def test_client_context_and_source_tampering_are_revalidated():
    contract_fields = [
        ("c_pactid", "合同编号", "varchar", "Y"),
        ("project_code", "项目编号", "varchar", ""),
        ("amount", "金额", "decimal", ""),
        ("report_date", "报送日期", "date", ""),
    ]
    dim_fields = [
        ("project_code", "项目编号", "varchar", "Y"),
        ("project_name", "项目名称", "varchar", ""),
        ("report_date", "报送日期", "date", "Y"),
    ]
    rules, _model = _rules(
        [_select_payload(target={"table": "contract"}), _generate_payload()],
        table="contract", table_cn="合同明细", dimension="合同", fields=contract_fields,
        extra_tables=[{"name": "dim_project", "cn": "项目维表", "dimension": "项目", "fields": dim_fields}],
    )
    context = {
        "mode": "lookup", "code_field": "project_code", "name_field": "project_name",
        "table_name": "dim_project", "key": {"left": "project_code", "right": "project_code"},
        "date_field": "report_date",
        # 客户端伪造证据/确认：文档重核后应忽略 fake fields，且关系仍需用户确认。
        "unique_evidence": {"kind": "pk", "fields": ["fake_field"], "confirmed": True},
        "confirmed": False,
    }

    preview = rules.preview_candidate(user(), _project_definition(context=context), return_questions=True)
    assert "sql_preview" not in preview and "content_sha256" not in preview
    resolved = preview["definition"]["project_context"]
    assert resolved["unique_evidence"]["kind"] == "pk"
    assert resolved["unique_evidence"]["fields"] == ["project_code", "report_date"]
    assert resolved["confirmed"] is False
    assert any(item["id"] == "project_context.confirmed" for item in preview["questions"])

    with pytest.raises(AppError) as error:
        rules.preview_candidate(user(), _project_definition(
            context={**context, "table_name": "missing_table"},
        ))
    assert error.value.code == "VALIDATION_ERROR"

    with pytest.raises(AppError) as error:
        rules.preview_candidate(user(), _project_definition(
            context={**context, "table_name": "contract"},
        ))
    assert error.value.code == "VALIDATION_ERROR"

    with pytest.raises(AppError) as error:
        rules.preview_candidate(user(), _project_definition(source_id="other"))
    assert error.value.code == "SOURCE_UNAVAILABLE"

    # 维表不能证明唯一时，该表不是可用候选：项目口径拒绝完整预览。
    weak_fields = [
        ("project_code", "项目编号", "varchar", ""),
        ("project_name", "项目名称", "varchar", ""),
        ("report_date", "报送日期", "date", ""),
    ]
    weak_rules, _weak_model = _rules(
        [_select_payload(target={"table": "contract"}), _generate_payload()],
        table="contract", table_cn="合同明细", dimension="合同", fields=contract_fields,
        extra_tables=[{"name": "dim_project", "cn": "项目维表", "dimension": "项目", "fields": weak_fields}],
    )
    with pytest.raises(AppError) as error:
        weak_rules.preview_candidate(user(), _project_definition(context=context))
    assert error.value.code == "PROJECT_CONTEXT_REQUIRED"


class _ProjectMetadata(Metadata):
    def execute_select(self, source_id, sql, params, timeout_seconds, max_rows):
        self.calls.append(sql)
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE contract(c_pactid, project_code, amount, report_date)")
            db.execute("CREATE TABLE dim_project(project_code, project_name, report_date)")
            for pact, code, name in self.rows:
                db.execute("INSERT INTO contract VALUES(?,?,1,?)", (pact, code, "2026-09-30"))
                db.execute("INSERT INTO dim_project VALUES(?,?,?)", (code, name, "2026-09-30"))
            cursor = db.execute(sql, params)
            return SimpleNamespace(columns=[c[0] for c in cursor.description], rows=cursor.fetchall(), truncated=False)


def test_real_rows_are_persisted_per_issue_with_project_columns():
    metadata = _ProjectMetadata(
        columns=[
            {"column_name": "c_pactid", "data_type": "varchar", "comment": "合同编号"},
            {"column_name": "project_code", "data_type": "varchar", "comment": "项目编号"},
            {"column_name": "amount", "data_type": "decimal", "comment": "金额"},
            {"column_name": "report_date", "data_type": "date", "comment": "报送日期"},
            {"column_name": "project_name", "data_type": "varchar", "comment": "项目名称"},
        ],
        sources=[SimpleNamespace(id="src", name="监管报送集市", dialect="mysql")],
    )
    metadata.rows = (
        ("C1", "P1", "项目一"),
        ("0", "0", "零号项目"),
    )
    _database, rules = service(metadata=metadata)
    owner = user()
    definition = _project_definition(
        context={
            "mode": "lookup", "code_field": "project_code", "name_field": "project_name",
            "table_name": "dim_project", "key": {"left": "project_code", "right": "project_code"},
            "date_field": "report_date",
            "unique_evidence": {"kind": "pk", "fields": ["project_code", "report_date"], "confirmed": True},
            "confirmed": True,
        },
    )
    # 文档需提供同名真实字段，预览/测试才按真实结构校验。
    content = doc_xlsx_bytes(table="contract", table_cn="合同明细", dimension="合同", fields=[
        ("c_pactid", "合同编号", "varchar", "Y"),
        ("project_code", "项目编号", "varchar", ""),
        ("amount", "金额", "decimal", ""),
        ("report_date", "报送日期", "date", ""),
    ])
    rules.import_document(owner, "doc.xlsx", content)
    _add_table(rules, name="dim_project", cn="项目维表", dimension="项目", fields=[
        ("project_code", "项目编号", "varchar", "Y"),
        ("project_name", "项目名称", "varchar", ""),
        ("report_date", "报送日期", "date", "Y"),
    ])

    saved = rules.save_draft(owner, definition)
    version = rules.storage.latest_version(saved["id"])
    rules.run_tests(owner, saved["id"], 1)
    rules.confirm_rule(owner, saved["id"], 1, version["content_sha256"])
    response = rules.start_task(owner, {
        "rule_ids": [saved["id"]], "source_id": "src", "report_period": "2026-09-30",
    })

    rows = rules.storage.list_issues(response["id"])["items"]
    assert [row["business_key"] for row in rows] == ["C1", "0"]
    assert [row["project_code"] for row in rows] == ["P1", "0"]
    assert [row["project_name"] for row in rows] == ["项目一", "零号项目"]
    assert [row["project_name_status"] for row in rows] == ["ok", "ok"]


def test_batch_save_keeps_sql_and_hash_per_candidate():
    fields = [("row_id", "编号", "varchar", "Y"), ("c_projcode", "项目编号", "varchar", ""),
              ("c_projname", "项目名称", "varchar", ""),
              ("amount", "金额", "decimal", ""),
              ("report_date", "报送日期", "date", "")]
    generate = _generate_payload(
        expression={"left": "金额", "op": "eq", "right_type": "value", "right": 0},
        ai_suggestions=[{"title": "建议", "references": [{"table_name": "test_table", "field_name": "amount"}]}],
    )
    rules, _model = _rules([_select_payload(), generate], fields=fields)
    candidate = rules.parse_rule_request(user(), _request(request_text="金额不得为 0"))
    first = {**candidate["preview"]["definition"], "name": "一"}
    second = {**candidate["preview"]["definition"], "name": "二", "violation_message": "另一个"}
    saved = rules.batch_save_candidates(user(), {
        "request_key": "11111111-1111-1111-1111-111111111111",
        "definitions": [first, second],
    })
    assert saved["count"] == 2
    assert saved["rules"][0]["content_sha256"] != saved["rules"][1]["content_sha256"]
    versions = [rules.storage.latest_version(int(rule["id"])) for rule in saved["rules"]]
    assert all("ai_suggestions" not in version["definition"] for version in versions)
    assert all(version["sql_text"] for version in versions)
