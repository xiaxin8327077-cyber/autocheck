from auto_check.modules.data_validation.semantic_generation import suggestion_backed_interpretations


def test_model_references_can_require_review_of_an_existing_document_candidate():
    missing = [{'id': 'I1', 'kind': 'metrics', 'side': 'left', 'table': 'detail_rows', 'field': 'units'}]
    draft = {'expression': {'left': 'booked', 'op': 'lt', 'right_type': 'value', 'right': 17}}
    suggestions = [{'category': 'consistency', 'kind': 'aggregate_consistency', 'references': [
        {'table_name': 'master_rows', 'field_name': 'booked'},
        {'table_name': 'detail_rows', 'field_name': 'units'}]}]
    assert suggestion_backed_interpretations(missing, draft, 'master_rows', suggestions) == missing


def test_an_unrelated_advice_or_a_scope_hit_does_not_become_a_required_plan():
    missing = [{'id': 'I1', 'kind': 'metrics', 'side': 'left', 'table': 'detail_rows', 'field': 'units'},
               {'id': 'I2', 'kind': 'scopes', 'table': 'detail_rows', 'field': 'flag'}]
    draft = {'expression': {'left': 'booked', 'op': 'neq', 'right_type': 'value', 'right': 9}}
    for suggestions in [[], [{'category': 'dictionary', 'kind': 'review', 'references': [
        {'table_name': 'master_rows', 'field_name': 'booked'},
        {'table_name': 'detail_rows', 'field_name': 'units'}]}],
        [{'category': 'consistency', 'kind': 'aggregate_consistency', 'references': [
        {'table_name': 'master_rows', 'field_name': 'different'},
        {'table_name': 'detail_rows', 'field_name': 'units'}]}]]:
        assert suggestion_backed_interpretations(missing, draft, 'master_rows', suggestions) == []


def test_compound_advice_only_reviews_its_own_operand_and_another_table():
    draft = {'expression': {'logic': 'all', 'conditions': [
        {'left': 'turnover', 'op': 'lt', 'right_type': 'value', 'right': 7},
        {'left': 'quantity', 'op': 'eq', 'right_type': 'value', 'right': 3}]}}
    suggestions = [{'category': 'consistency', 'kind': 'aggregate_consistency', 'references': [
        {'table_name': 'master_rows', 'field_name': 'turnover'},
        {'table_name': 'detail_rows', 'field_name': 'amount'},
        {'table_name': 'master_rows', 'field_name': 'alternate'}]}]
    checks = [{'id':'I1','kind':'metrics','side':'left','condition_index':1,'table':'detail_rows','field':'amount'},
              {'id':'I2','kind':'metrics','side':'left','condition_index':0,'table':'master_rows','field':'alternate'}]
    assert suggestion_backed_interpretations(checks, draft, 'master_rows', suggestions) == []
