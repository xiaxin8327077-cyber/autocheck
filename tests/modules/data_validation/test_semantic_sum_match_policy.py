from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_project_driver_binding import document_tables, make_rules


def test_model_sum_exclude_is_a_valid_matched_group_comparison():
    project, _, funding, _ = document_tables()
    next(f for f in funding['fields'] if f['field_name'] == 'day').update(source_table='mart.project_snapshot', source_field='day')
    next(f for f in funding['fields'] if f['field_name'] == 'funding_owner')['is_pk'] = 'Y'
    next(f for f in project['fields'] if f['field_name'] == 'project_received')['field_cn'] = '项目端读数'
    next(f for f in funding['fields'] if f['field_name'] == 'funding_received')['field_cn'] = '明细端读数'
    draft = {'business_key': 'project_key', 'project_driver': {'version': 1, 'table_role': 'base'},
             'rule_name': '两侧读数核对', 'rule_type': 'field_compare',
             'expression': {'left': 'project_received', 'op': 'neq', 'right_type': 'field',
                            'right_table': 'related', 'right': 'funding_received'},
             'null_policy': 'zero', 'violation_message': '读数不一致',
             'join': {'table_name': 'funding_rows', 'on': [{'left': 'project_key', 'right': 'funding_owner'}],
                      'report_date_field': 'day', 'right_aggregate': 'sum',
                      'relationship_confirmed': True, 'unmatched_policy': 'exclude'},
             'semantic_intent': {'metrics': [
                 {'side': 'left', 'term': '项目端读数', 'fields': ['project_received']},
                 {'side': 'right', 'term': '明细端读数', 'fields': ['funding_received']}],
                 'scopes': [], 'open_questions': []}}
    reply = {'target': {'table': 'project_snapshot'}, 'related_target': {'table': 'funding_rows'}, 'draft': draft}
    rules, model = make_rules([reply, draft], tables=[project, funding])
    result = rules.parse_rule_request(user(), _request(request_text='对比项目端读数和明细端读数之和是否一致', analysis_protocol=2))
    assert result['preview'] and not result['questions']
    assert result['join']['unmatched_policy'] == 'exclude'
    assert result['join']['right_aggregate'] == 'sum'
    assert len(model.calls) == 1
