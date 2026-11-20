from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _rules_with_doc, _request, _select_payload


def test_competing_terms_do_not_hide_other_fields_of_the_selected_table():
    rules, _ = _rules_with_doc([], fields=[
        ("row_id", "记录编号", "varchar", "Y"), ("data_day", "数据日期", "date", ""),
        ("start_day", "设备启动日期", "date", ""), ("end_day", "预计停用日期", "date", ""),
    ])
    request = _request(request_text="起始日不得晚于预计结束日", analysis_protocol=2)
    analysis = SemanticAnalysis(rules, user(), rules._analysis_inputs(user(), request), request["request_text"], None, None)
    analysis.index = DocumentEvidence(analysis.tables, analysis.fields, analysis.request)
    table = analysis.tables[0]
    analysis.index.details[table["id"]] = {"row_id", "data_day", "end_day"}
    analysis.competing_evidence = [{"kind": "metrics", "term": "结束日", "candidates": [
        {"table_id": table["id"], "fields": ["end_day"]}]}]
    prompt = analysis.expanded_prompt(_select_payload(), [table], [])
    assert '"start_day"' in prompt
    assert '"end_day"' in prompt
