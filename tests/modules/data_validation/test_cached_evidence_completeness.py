from copy import deepcopy

from auto_check.modules.data_validation.analysis_result_cache import model_snapshot
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_project_driver_binding import document_tables, make_rules


def test_cached_single_plan_is_rechecked_against_independent_documented_grain():
    project, _, funding, _ = document_tables()
    for table, name in [(project, 'project_received'), (funding, 'funding_received')]:
        field = next(f for f in table['fields'] if f['field_name'] == name)
        field['logic'] = '业务别名：独立读数。'
    next(f for f in funding['fields'] if f['field_name'] == 'day').update(
        source_table='mart.project_snapshot', source_field='day')
    draft = {'rule_name': '读数核查', 'rule_type': 'field_compare', 'business_key': 'project_key',
             'expression': {'left': 'project_received', 'op': 'lt', 'right_type': 'value', 'right': 0},
             'violation_message': '读数为负', 'null_policy': 'zero',
             'semantic_intent': {'metrics': [{'side': 'left', 'term': '独立读数', 'fields': ['project_received']}],
                                 'scopes': [], 'open_questions': []}}
    selection = {'target': {'table': 'project_snapshot'}}
    other = deepcopy(draft)
    other.update(target={'table': 'funding_rows'}, related_target={'table': 'project_snapshot'}, business_key='funding_id',
                 join={'table_name': 'project_snapshot', 'on': [{'left': 'funding_owner', 'right': 'project_key'}],
                       'report_date_field': 'day', 'relationship_confirmed': True, 'unmatched_policy': 'exclude'})
    other['expression']['left'] = 'funding_received'
    other['semantic_intent']['metrics'][0]['fields'] = ['funding_received']
    complete = {'plans': [{**draft, 'target': selection['target']}, other]}
    discovery = {**selection, 'candidate_targets': [
        {'target': {'table': 'funding_rows'}, 'related_target': selection['target']}]}
    rules, model = make_rules([discovery, complete, {'ai_suggestions': []}], tables=[project, funding])
    request = _request(request_text='独立读数不得小于0', analysis_protocol=2)
    context = rules._analysis_inputs(user(), request)['context']
    rules.storage.remember_analysis_result(context, request['request_text'], model_snapshot(selection, draft))
    result = rules.parse_rule_request(user(), request)
    assert {o['candidate']['table_name'] for o in result.get('candidate_options', [])} == {
        'project_snapshot', 'funding_rows'}
    # The cache must not make an incomplete old interpretation permanently authoritative.
    assert result.get('memory_decision') != 'exact' or len(result['candidate_options']) == 2
