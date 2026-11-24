from copy import deepcopy
import sqlite3

from sqlalchemy import update

from auto_check.modules.data_validation.query_samples import evaluate_case_with_kind
from auto_check.modules.data_validation.request_scopes import bind_conditional_text_scopes
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc


FIELDS = [('row_id','记录号','varchar','Y'), ('day','数据日期','date',''),
          ('subject','物品摘要','varchar',''), ('kind','分拣类型','varchar','')]
INCLUDE, EXCLUDE = ['晴时','甲且乙','Alpha'], ['损坏','注意']
REQUEST = '物品摘要包含“晴时|甲且乙|Alpha”且不包含“损坏|注意”时分拣类型未归为“快件”，请核实。'


def wrong_group():
    return {'target': {'table':'test_table'}, 'draft': {
        'business_key':'row_id', 'rule_name':'快件核查','rule_type':'field_compare','null_policy':'skip',
        'violation_message':'分拣类型需复核','expression':{'logic':'any','conditions':[
            {'left':'subject','op':'contains_any','right_type':'value','right':INCLUDE},
            {'left':'subject','op':'not_contains_any','right_type':'value','right':EXCLUDE},
            {'left':'kind','op':'neq','right_type':'value','right':'02'}]},
        'semantic_intent':{'metrics':[{'side':'left','term':'物品摘要','fields':['subject']},
            {'side':'left','term':'分拣类型','fields':['kind']}],'scopes':[], 'open_questions':[]}}}


def test_model_or_group_cannot_turn_eligibility_filters_into_violations():
    reply = wrong_group()
    rules, model = _rules_with_doc([deepcopy(reply) for _ in range(3)],fields=FIELDS)
    with rules.storage.database.begin() as c:
        c.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name=='kind').values(dictionary='01-普件\n02-快件'))
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2))
    preview = result['preview']
    assert len(model.calls) == 1 and not result['questions']
    assert preview['definition']['expression'] == reply['draft']['expression']['conditions'][2]
    assert [(f['field'],f['op'],f['value']) for f in preview['definition']['filters']] == [
        ('subject','contains_any',INCLUDE), ('subject','not_contains_any',EXCLUDE)]
    data = [('target','甲且乙','2'), ('other-word','平常','01'), ('excluded','晴时注意','01'),
            ('excluded-only','损坏','01'), ('correct','晴时','02'), ('null-code','晴时',None),
            ('empty-code','晴时',''), ('null-name',None,'01'), ('upper','Alpha','01'), ('lower','alpha','01')]
    day = '2026-10-31'
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE test_table(row_id text, day date, subject text, kind text)')
        db.create_collation('C', lambda x,y:(x>y)-(x<y))
        db.create_function('STRPOS', 2, lambda value, word: value.find(word) + 1 if value is not None else None)
        db.executemany('INSERT INTO test_table VALUES (?,?,?,?)',[(key,day,title,kind) for key,title,kind in data])
        rows = db.execute(preview['sql_preview'],{**preview['sql_params'],'report_date':day}).fetchall()
    assert {r[0] for r in rows} == {'target','upper'}
    for key, title, kind in data:
        sample = {'report_date':day,'base':{'row_id':key,'day':day,'subject':title,'kind':kind}, 'related':[]}
        assert evaluate_case_with_kind(preview['definition'],sample)[0] == int(key in ('target','upper'))


def test_restore_missing_prerequisite_and_leave_a_correct_rule_unchanged():
    fields = [{'field_name':n,'field_cn':label,'data_type':t} for n,label,t,_ in FIELDS]
    draft = wrong_group()['draft']
    draft['expression'] = draft['expression']['conditions'][-1]
    draft['filters'] = [{'table':'base','field':'subject','op':'contains_any','value':INCLUDE}]
    assert not bind_conditional_text_scopes(draft, fields, REQUEST)
    assert [f['op'] for f in draft['filters']] == ['contains_any', 'not_contains_any']
    normalized = deepcopy(draft)
    assert not bind_conditional_text_scopes(draft, fields, REQUEST) and draft == normalized


def test_conflicting_words_and_unproven_or_scope_require_correction():
    fields = [{'field_name':n,'field_cn':label,'data_type':t} for n,label,t,_ in FIELDS]
    for text in [REQUEST, REQUEST.replace('且不包含','或者不包含')]:
        draft = wrong_group()['draft']
        draft['expression']['conditions'][0]['right'] = ['不同词']
        original = deepcopy(draft)
        assert bind_conditional_text_scopes(draft, fields, text)
        assert draft == original


def test_ordinary_violation_or_without_eligibility_clause_is_untouched():
    draft = wrong_group()['draft']
    original = deepcopy(draft)
    fields = [{'field_name':n,'field_cn':label,'data_type':t} for n,label,t,_ in FIELDS]
    assert not bind_conditional_text_scopes(draft, fields, '物品摘要不得有损坏字样且分拣类型应为快件。')
    assert draft == original

def test_completed_filters_do_not_prove_extra_result_clauses_or_scope_restrictions():
    fields = [{'field_name': n, 'field_cn': label, 'data_type': t,
               **({'dictionary': '01-普件\n02-快件'} if n == 'kind' else {})} for n,label,t,_ in FIELDS]
    f = [{'field': 'subject', 'op': op, 'value': words}
         for op, words in [('contains_any', INCLUDE), ('not_contains_any', EXCLUDE)]]
    outcome = wrong_group()['draft']['expression']['conditions'][-1]
    for expressions, extra in [([outcome, {'left':'subject','op':'contains_any','right_type':'value','right':['晴时']}], []),
                               ([outcome], [{'field':'kind','op':'eq','value':'02'}])]:
        draft = wrong_group()['draft']
        draft['expression'] = expressions[0] if len(expressions) == 1 else {'logic':'any','conditions':expressions}
        draft['filters'] = f + extra
        original = deepcopy(draft)
        assert bind_conditional_text_scopes(draft, fields, REQUEST)
        assert draft == original
