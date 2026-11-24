from copy import deepcopy

from auto_check.modules.data_validation.model_calls import failure
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


def test_internal_model_error_category_survives_to_the_repair_caller():
    error = failure('MODEL_RESPONSE_INVALID', 'generate_rule', category='invalid_json_object')
    assert error.category == 'invalid_json_object'
    assert str(error) == 'MODEL_RESPONSE_INVALID'


def test_repair_gets_a_specific_operator_hint_without_extra_retry():
    fields = [('id','记录编号','varchar','Y'), ('day','数据日期','date',''), ('amount','读数','numeric','')]
    correct = {'rule_name':'读数校验','rule_type':'field_compare','business_key':'id',
               'expression':{'left':'amount','op':'gt','right_type':'value','right':0},
               'null_policy':'zero','violation_message':'读数异常',
               'semantic_intent':{'metrics':[{'side':'left','term':'读数','fields':['amount']}],
                                  'scopes':[],'open_questions':[]}}
    wrong = deepcopy(correct)
    wrong['expression']['op'] = 'greater'
    rules, model = _rules_with_doc([{'target':{'table':'test_table'},'draft':wrong},correct], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text='核查读数', analysis_protocol=2))
    assert result['preview'] and len(model.calls) == 2
    prompt = model.calls[-1]['messages'][0]['content']
    assert '修复定位：expression.op' in prompt and 'gt' in prompt
