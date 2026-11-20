from types import SimpleNamespace

import pytest
from sqlalchemy import insert

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.storage import DOC_FIELDS

from tests.modules.data_validation.support import SequenceModel, service, user
from tests.modules.data_validation.test_ai_service import _request


class Categories:
    def list_report_processes(self):
        return [SimpleNamespace(code=code, name=name, order=index, active=True) for index, (code, name) in enumerate(
            [("rating", "评级报送"), ("audit", "审计报送")])]


class Sources:
    def list_sources(self):
        return [SimpleNamespace(id="src", name="监管报表", dialect="mysql")]


def _document(rules, version, candidates, caption):
    tables = []
    for table, category, scope, field_caption in candidates:
        fields = [{"field_name": name, "field_cn": label, "data_type": dtype, "is_pk": pk} for name, label, dtype, pk in [
            ("project_id", "项目编号", "varchar", "Y"), ("project_name", "项目名称", "varchar", ""),
            ("day", "数据日期", "date", ""), ("metric", field_caption or caption, "decimal", "")]]
        tables.append({"table_name": table, "table_name_cn": "项目明细", "sheet_name": category + "_项目明细",
                       "scope": scope, "dimension": "项目", "data_source_name": "监管报表", "fields": fields})
    doc = rules.storage.create_document(name="文档", file_name="fixture.xlsx", content_sha256=str(version) * 64,
        table_count=len(tables), field_count=4 * len(tables), warnings=[], imported_by="A", tables=tables)
    rules.storage.activate_document(doc["id"])


@pytest.mark.parametrize("caption", ["单位净值", "风险敞口"])
def test_new_category_with_a_real_same_named_metric_requires_scope_before_preview(caption):
    first = ("rating_projects", "评级报送", "仍在评级的项目", "")
    other = ("audit_projects", "审计报送", "年度审计项目", "")
    unrelated = ("audit_accounts", "审计报送", "账户信息", "账户编号")
    select = {"target": {"table": first[0]}, "report_category": "rating"}
    draft = {"rule_type": "field_compare", "expression": {"left": "metric", "op": "is_null"}}
    model = SequenceModel([select, draft, select, draft])
    _, rules = service(metadata=Sources(), model=model, report_navigation=Categories())
    _document(rules, 1, [first], caption)
    req = _request(request_text=f"{caption}不能为空")
    assert rules.parse_rule_request(user("A"), req)["preview"]
    _document(rules, 2, [first, other, unrelated], caption)
    result = rules.parse_rule_request(user("B"), req)
    assert not result.get("preview")
    options = result["candidate_options"]
    assert {o["candidate"]["report_category"] for o in options} == {"rating", "audit"}
    assert {o["candidate"]["table_name"] for o in options} == {first[0], other[0]}
    for item in options:
        candidate = item["candidate"]
        assert not candidate.get("preview") and candidate["expression"]["left"] == "metric"
        question = next(q for q in candidate["questions"] if q["id"] == "report_category")
        assert [o["value"] for o in question["options"]] == [candidate["report_category"]]
        assert candidate["report_category_name"] in item["label"]
        confirmed = {**candidate, "questions": [q for q in candidate["questions"] if q is not question],
                     "uncertainty_resolutions": ["明确选择" + candidate["report_category_name"]]}
        assert candidate["table_name"] in rules.preview_candidate(user("B"), confirmed, return_questions=True)["sql_preview"]


@pytest.mark.parametrize("model_keeps_old_table", [True, False])
def test_explicit_reporting_category_only_uses_that_documents_table(model_keeps_old_table):
    first = ("rating_projects", "评级报送", "仍在评级的项目", "")
    other = ("audit_projects", "审计报送", "年度审计项目", "")
    selection = {"target": {"table": first[0] if model_keeps_old_table else other[0]}, "report_category": "rating" if model_keeps_old_table else "audit"}
    draft = {"rule_type": "field_compare", "expression": {"left": "metric", "op": "is_null"}}
    _, rules = service(metadata=Sources(), model=SequenceModel([selection, draft]), report_navigation=Categories())
    _document(rules, 2, [first, other], "风险敞口")
    explicit = rules.parse_rule_request(user("B"), _request(request_text="审计报送的风险敞口不能为空"))
    assert explicit["report_category"] == "audit" and explicit["table_name"] == other[0]
    assert not explicit.get("candidate_options")
    assert other[0] in explicit["preview"]["sql_preview"]


@pytest.mark.parametrize("explicit", [False, True])
def test_same_physical_table_and_fields_use_the_chosen_worksheets_dictionary(explicit):
    name = "project_facts"
    sources = [(name, "评级报送", "评级项目", ""), (name, "审计报送", "审计项目", "")]
    select = {"target": {"table": name}, "report_category": "rating"}
    draft = {"rule_type": "field_compare", "expression": {"left": "metric", "op": "is_null"}}
    _, rules = service(metadata=Sources(), model=SequenceModel([select, draft]), report_navigation=Categories())
    _document(rules, 1, sources, "风险敞口")
    for table in rules.storage.doc_tables(rules.storage.active_document()["id"]):
        template = rules.storage.doc_fields(table["id"])[0]
        row = {key: value for key, value in template.items() if key != "id"}
        code = "A" if table["sheet_name"].startswith("评级") else "B"
        row.update(field_name="class_code", field_cn="项目等级", data_type="varchar", is_pk="", dictionary=f"{code}-特别\nZ-普通")
        with rules.storage.database.begin() as conn:
            conn.execute(insert(DOC_FIELDS).values(**row))
    text = ("审计报送：" if explicit else "") + "当项目等级为特别时，风险敞口不得为空"
    result = rules.parse_rule_request(user(), _request(request_text=text))
    if explicit:
        assert result["report_category"] == "audit" and result["preview"] and not result.get("candidate_options"), result
        assert result["preview"]["definition"]["filters"][0]["value"] == "B"
        return
    options = result["candidate_options"]
    assert len(options) == len({item["id"] for item in options}) == 2
    assert not result.get("preview") and all(not o["candidate"].get("preview") for o in options)
    for option in options:
        candidate = option["candidate"]
        code = "B" if candidate["report_category"] == "audit" else "A"
        q, = candidate["questions"]
        assert q["id"] == "report_category" and candidate["filters"][0]["value"] == code
        chosen = {**candidate, "questions": [], "uncertainty_resolutions": ["明确选择 " + candidate["report_category_name"]]}
        assert rules.preview_candidate(user(), chosen, return_questions=True)["definition"]["filters"][0]["value"] == code
        missing_category = {**chosen, "report_category": "", "uncertainties": [], "uncertainty_resolutions": []}
        waiting = rules.preview_candidate(user(), missing_category, return_questions=True)
        assert not waiting.get("sql_preview") and waiting["status"] == "needs_confirmation"
        assert {o["value"] for o in waiting["questions"][0]["options"]} == {"rating", "audit"}
        wrong = {**chosen, "report_category": "rating" if code == "B" else "audit"}
        try:
            rejected = rules.preview_candidate(user(), wrong, return_questions=True)
        except AppError as exc:
            assert exc.code == "VALIDATION_ERROR"
        else:
            assert not rejected.get("sql_preview")
