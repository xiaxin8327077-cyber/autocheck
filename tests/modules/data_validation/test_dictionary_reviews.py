from copy import deepcopy

import pytest

from auto_check.modules.data_validation import dictionary_reviews


TABLE = "account_ledger"
QUESTION = {"table": TABLE, "field": "account_kind", "category": "普通类"}
FIELDS = [
    {"field_name": "account_kind", "field_cn": "账户类型", "data_type": "varchar",
     "dictionary": "【账户类型】\n01-开放普通类\n02-非普通类\n03-封闭普通类"},
    {"field_name": "derived_kind", "field_cn": "账户类型", "data_type": "int", "dictionary": "1-普通类\n2-专用类"},
]
FILTER = {"table": "base", "field": "account_kind", "op": "in", "value": ["03", "01"], "confirmed": True}


def test_dictionary_fact_comes_from_every_line_of_the_exact_physical_field():
    fields = deepcopy(FIELDS)
    fields[0]["dictionary"] = "\n".join(f"X{i}-其他类别" for i in range(110)) + "\n" + fields[0]["dictionary"]
    assert dictionary_reviews.documented_dictionary_entries(QUESTION, TABLE, fields) == [
        {"value": "01", "label": "开放普通类"}, {"value": "03", "label": "封闭普通类"},
    ]
    assert dictionary_reviews.documented_dictionary_entries({**QUESTION, "field": "derived_kind"}, TABLE, fields) == [
        {"value": 1, "label": "普通类"},
    ]


@pytest.mark.parametrize(("question", "fields"), [
    ({**QUESTION, "table": "different_table"}, FIELDS),
    ({**QUESTION, "field": "账户类型"}, FIELDS),
    ({**QUESTION, "field": "missing_field"}, FIELDS),
    ({**QUESTION, "category": ""}, FIELDS),
    ({**QUESTION, "business_date": "需确认日期"}, FIELDS),
    (QUESTION, [*FIELDS, FIELDS[0]]),
    (QUESTION, [{**FIELDS[0], "dictionary": "1-普通类\n1-特别类"}]),
    (QUESTION, [{**FIELDS[0], "dictionary": "1-普通类\n未解析条目"}]),
])
def test_incomplete_or_ambiguous_dictionary_references_remain_open(question, fields):
    assert not dictionary_reviews.documented_dictionary_entries(question, TABLE, fields)


@pytest.mark.parametrize("filters", [
    [], [{**FILTER, "confirmed": False}], [{**FILTER, "value": ["01"]}],
    [{**FILTER, "value": ["01", "01"]}], [{**FILTER, "value": ["01", "02", "03"]}],
    [{**FILTER, "value": [1, 3]}], [{**FILTER, "value": [[], {}]}],
    [{**FILTER, "table": "related"}], [{**FILTER, "field": "derived_kind"}],
    [{**FILTER, "op": "not_in"}], [FILTER, {**FILTER, "op": "eq", "value": "01"}],
])
def test_an_incomplete_wrong_or_unconfirmed_filter_cannot_answer_the_question(filters):
    assert not dictionary_reviews.dictionary_filter_answers(QUESTION, TABLE, FIELDS, filters)


def test_complete_bound_filter_answers_only_its_own_fact_and_leaves_other_decisions_intact():
    filters = [FILTER.copy(), {"table": "base", "field": "report_date", "op": "gte", "confirmed": False}]
    original = deepcopy(filters)
    assert dictionary_reviews.dictionary_filter_answers(QUESTION, TABLE, FIELDS, filters)
    assert filters == original
    question = {**QUESTION, "field": "derived_kind"}
    condition = {**FILTER, "field": "derived_kind", "op": "eq", "value": 1}
    assert dictionary_reviews.dictionary_filter_answers(question, TABLE, FIELDS, [condition])
    assert not dictionary_reviews.dictionary_filter_answers(question, TABLE, FIELDS, [{**condition, "value": True}])


def test_applying_confirmed_dictionary_fact_keeps_independent_questions_and_answers_paired():
    question = dictionary_reviews.dictionary_question_text(QUESTION)
    other = {**QUESTION, "field": "derived_kind"}
    pending_text = dictionary_reviews.dictionary_question_text(other)
    original = {"filters": [FILTER], "uncertainties": ["同日日期是否为入账日？", question, pending_text, question + "另须确认日期。"],
                "uncertainty_resolutions": ["按报送日期", "", "", "核对日期后处理"]}
    review = deepcopy(original)
    pending = dictionary_reviews.apply_dictionary_filter_answers(review, [QUESTION, other, other], TABLE, FIELDS)
    assert pending == [other]
    assert review["uncertainties"] == [original["uncertainties"][index] for index in (0, 2, 3)]
    assert review["uncertainty_resolutions"] == ["按报送日期", "", "核对日期后处理"]
    assert review["filters"] == original["filters"]


def test_a_human_explanation_remains_even_if_the_filter_independently_confirms_the_fact():
    text = dictionary_reviews.dictionary_question_text(QUESTION)
    definition = {"filters": [FILTER], "uncertainties": [text], "uncertainty_resolutions": ["已按业务要求核对"]}
    before = deepcopy(definition)
    assert dictionary_reviews.apply_dictionary_filter_answers(definition, [QUESTION], TABLE, FIELDS) == []
    assert definition == before


def test_missing_malformed_or_excess_external_references_cannot_remove_a_pending_review():
    text = dictionary_reviews.dictionary_question_text(QUESTION)
    definition = {"filters": [FILTER], "uncertainties": [text], "uncertainty_resolutions": [""]}
    before = deepcopy(definition)
    unknown = {**QUESTION, "category": "尚无定义"}
    inputs = [[None, 3, [], {**QUESTION, "other": "额外业务范围"}, {"table": TABLE}, {**QUESTION, "field": []}, unknown],
              [unknown] * 100 + [QUESTION], QUESTION]
    for supplied in inputs:
        assert dictionary_reviews.apply_dictionary_filter_answers(definition, supplied, TABLE, FIELDS) == []
        assert definition == before


@pytest.mark.parametrize("invalid", [
    {"filters": [FILTER, "未解析"]}, {"uncertainty_resolutions": [None]},
    {"uncertainty_resolutions": "自由说明"}, {"uncertainties": [{"text": "待核实"}]},
])
def test_malformed_preview_input_never_discards_review_evidence(invalid):
    text = dictionary_reviews.dictionary_question_text(QUESTION)
    definition = {"filters": [FILTER], "uncertainties": [text], "uncertainty_resolutions": [""], **invalid}
    before = deepcopy(definition)
    dictionary_reviews.apply_dictionary_filter_answers(definition, [QUESTION], TABLE, FIELDS)
    assert definition == before
