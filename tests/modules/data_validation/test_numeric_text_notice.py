from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


def test_numeric_text_predicate_explains_type_without_dropping_the_predicate():
    fields = [('row_id', '记录编号', 'varchar', 'Y'), ('day', '数据日期', 'date', ''),
              ('reading', '读数', 'numeric', '')]
    rule = {'target': {'table': 'test_table'}, 'draft': {
        'rule_name': '读数文字检查', 'rule_type': 'field_compare', 'business_key': 'row_id',
        'expression': {'left': 'reading', 'op': 'contains_any', 'right_type': 'value', 'right': ['%', '‰']},
        'violation_message': '读数含单位符号', 'null_policy': 'skip',
        'semantic_intent': {'metrics': [{'side': 'left', 'term': '读数', 'fields': ['reading']}],
                            'scopes': [], 'open_questions': []}}}
    service, _ = _rules_with_doc([rule], fields=fields)
    result = service.parse_rule_request(user(), _request(request_text='读数不得包含%或‰', analysis_protocol=2))
    assert result['preview'] and not result['questions']
    assert result['expression'] == rule['draft']['expression']
    assert any('数值型' in notice and '原始文本' in notice for notice in result['notices'])
