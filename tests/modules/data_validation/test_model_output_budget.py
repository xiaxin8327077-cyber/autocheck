"""Per-question output bounds and budgets derived from real selected targets."""
import json
from copy import deepcopy

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc
from tests.modules.data_validation.test_followup_service_bridge import _add_table
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


def analysis_with_usage(usages, *, reasoning=True):
    rules, model = _rules_with_doc([{'target': {'table': 'test_table'}}], fields=FIELDS)
    for name in ('ledger_b', 'ledger_c'):
        _add_table(rules, name=name, cn=name, dimension='业务记录', fields=FIELDS)
    request = _request(request_text='核对份额', analysis_protocol=2)
    inputs = rules._analysis_inputs(user(), request)
    inputs['reasoning_enabled'] = reasoning
    analysis = SemanticAnalysis(rules, user(), inputs, request['request_text'], None, None)
    calls = []
    def detailed(_model_id, messages, *, options, **_kwargs):
        index = len(calls)
        calls.append({'options': dict(options), 'prompt': messages[0]['content']})
        usage = usages[index] if index < len(usages) else usages[-1]
        return {'content': json.dumps({'target': {'table': 'test_table'}}), 'finish_reason': 'stop',
                'usage': usage if isinstance(usage, dict) else {} if usage is None else {'completion_tokens': usage}}
    model.complete_with_options = detailed
    return analysis, calls


@pytest.mark.parametrize('selection,want', [
    ({'target': {'table': 'test_table'}}, 3072),
    ({'target': {'table': 'test_table'}, 'related_target': {'table': 'ledger_b'}}, 3072),
    ({'target': {'table': 'test_table'}, 'candidate_targets': [{'table': 'ledger_b'}]}, 6144),
    ({'target': {'table': 'test_table'}, 'candidate_targets': [{'table': 'ledger_b'}, {'table': 'ledger_c'}]}, 9216),
    ({'target': {'table': 'test_table'}, 'candidate_targets': [{'table': 'test_table'}]}, 3072),
])
def test_generation_budget_follows_distinct_rules_not_joined_table_count(selection, want):
    analysis, calls = analysis_with_usage([25])
    analysis.prepare_selection(selection)

    analysis.call('生成规则', 'generate_rule')

    assert calls[0]['options'] == {'reasoning_effort': 'low', 'max_tokens': want, 'temperature': 0}
    assert str(want) in calls[0]['prompt']


def test_all_rounds_share_one_ten_thousand_token_output_budget():
    analysis, calls = analysis_with_usage([9000, 1000])
    analysis.prepare_selection({'target': {'table': 'test_table'},
                                'candidate_targets': [{'table': 'ledger_b'}, {'table': 'ledger_c'}]})
    analysis.call('生成多规则', 'generate_rule')
    analysis.call('修复结构', 'repair_rule')

    with pytest.raises(AppError, match='ANALYSIS_OUTPUT_LIMIT'):
        analysis.call('不能再发请求', 'repair_rule')

    assert [call['options']['max_tokens'] for call in calls] == [9216, 1000]
    assert '1000' in calls[1]['prompt']


def test_unknown_usage_reserves_the_whole_allocation_before_another_round():
    analysis, calls = analysis_with_usage([None])
    for _ in range(4):
        analysis.call('有限请求', 'repair_rule')

    with pytest.raises(AppError, match='ANALYSIS_OUTPUT_LIMIT'):
        analysis.call('超过总预算', 'repair_rule')

    assert [call['options']['max_tokens'] for call in calls] == [3072, 3072, 3072, 784]


def test_disabling_reasoning_preserves_the_round_budget():
    analysis, calls = analysis_with_usage([25], reasoning=False)
    analysis.call('核实', 'generate_rule')
    assert calls[0]['options'] == {'max_tokens': 3072, 'reasoning_effort': 'none', 'temperature': 0}


def test_unbound_candidate_cannot_increase_generation_budget():
    analysis, calls = analysis_with_usage([25])
    with pytest.raises(AppError, match='MODEL_RESPONSE_INVALID'):
        analysis.prepare_selection({'target': {'table': 'test_table'},
                                    'candidate_targets': [{'table': 'not_in_document'}]})
    analysis.call('仍是简单预算', 'generate_rule')
    assert calls[0]['options']['max_tokens'] == 3072


@pytest.mark.parametrize('usage,expected', [
    ({'completion_tokens': 24, 'completion_tokens_details': {'reasoning_tokens': 18}}, 24),
    ({'completion_tokens': 0}, 3072),
    ({'completion_tokens': 1, 'completion_tokens_details': {'reasoning_tokens': 3000}}, 3072),
    ({'completion_tokens': 24, 'prompt_tokens': 100, 'total_tokens': 3100}, 3072),
])
def test_round_usage_includes_reasoning_and_reserves_allocation_on_contradiction(usage, expected):
    analysis, _ = analysis_with_usage([usage])
    analysis.call('核实', 'generate_rule')
    assert analysis.output_tokens_used == expected


def test_unbounded_model_is_rejected_before_sending_a_request():
    analysis, _ = analysis_with_usage([25])
    class LegacyOnly:
        sent = False
        def complete(self, *_args, **_kwargs):
            self.sent = True
            return '{}'
    model = LegacyOnly()
    analysis.service.model = model
    with pytest.raises(AppError, match='MODEL_UNAVAILABLE'):
        analysis.call('核实', 'generate_rule')
    assert not model.sent


@pytest.mark.parametrize('last_metric,want', [('amount', 3072), ('balance', 6144)])
def test_same_table_plan_budget_counts_distinct_checks(last_metric, want):
    analysis, calls = analysis_with_usage([25])
    first = draft('amount')
    repeat = deepcopy(first)
    repeat['rule_name'] = '同一条件的另一种表述'
    repeat['semantic_intent']['metrics'][0]['term'] = '指标的另一种措辞'
    plans = [first, repeat, draft(last_metric)]
    analysis.preserve_plan_group({'plan_mode': 'parallel', 'plans': plans}, {'target': {'table': 'test_table'}})
    analysis.call('核实', 'generate_rule')
    assert calls[0]['options']['max_tokens'] == want


def test_empty_candidate_target_yields_public_error_without_allocating_extra_budget():
    analysis, _ = analysis_with_usage([25])
    with pytest.raises(AppError, match='MODEL_RESPONSE_INVALID'):
        analysis.prepare_selection({'target': {'table': 'test_table'}, 'candidate_targets': [{}]})
    assert analysis.budget_units == 1


def test_invalid_cached_group_cannot_raise_fresh_selection_budget(monkeypatch):
    analysis, _ = analysis_with_usage([25])
    cached = {'selection': {'target': {'table': 'test_table'},
                            'candidate_targets': [{'table': 'ledger_b'}, {'table': 'ledger_c'}]}, 'draft': None}
    monkeypatch.setattr(analysis.service.storage, 'cached_analysis_result', lambda *_: cached)
    allocations = []
    def detailed(_model_id, _messages, *, options, **_kwargs):
        allocations.append(options['max_tokens'])
        return {'content': '', 'finish_reason': 'length', 'usage': {'completion_tokens': options['max_tokens']}}
    monkeypatch.setattr(analysis.service.model, 'complete_with_options', detailed)
    with pytest.raises(AppError, match='MODEL_OUTPUT_LIMIT'):
        analysis.run([], [], [])
    assert allocations == [3072]


def test_document_context_retry_keeps_the_original_question_budget(monkeypatch):
    analysis, _ = analysis_with_usage([25])
    service = analysis.service
    read_inputs = service._analysis_inputs
    caps = []
    def changing_inputs(*args):
        result = read_inputs(*args)
        result['context']['prompt_fingerprint'] = 'initial' if not caps else 'updated'
        return result
    def detailed(_model_id, _messages, *, options, **_kwargs):
        caps.append(options['max_tokens'])
        reason = 'stop' if len(caps) % 2 else 'length'
        return {'content': '{"target":{"table":"test_table"}}', 'finish_reason': reason,
                'usage': {'completion_tokens': options['max_tokens']}}
    monkeypatch.setattr(service, '_analysis_inputs', changing_inputs)
    monkeypatch.setattr(service.model, 'complete_with_options', detailed)
    with pytest.raises(AppError, match='MODEL_OUTPUT_LIMIT'):
        service.parse_rule_request(user(), _request(request_text='份额非负', analysis_protocol=2))
    assert caps == [3072, 3072, 3072, 784]


def test_empty_length_response_reserves_allocation_even_if_usage_reports_zero(monkeypatch):
    analysis, _ = analysis_with_usage([25])
    def truncated(*_args, **_kwargs):
        return {'content': '', 'finish_reason': 'length', 'usage': {'completion_tokens': 0}}
    monkeypatch.setattr(analysis.service.model, 'complete_with_options', truncated)
    with pytest.raises(AppError, match='MODEL_OUTPUT_LIMIT'):
        analysis.call('核实', 'generate_rule')
    assert analysis.output_tokens_used == 3072
