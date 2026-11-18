"""确定性期间字段：真实文档证据唯一时自动采用，事件/多候选仍保留人工问题。"""

from __future__ import annotations

from auto_check.modules.data_validation.query_grounding import resolve_report_date
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import (
    _generate_payload, _request, _rules_with_doc, _select_payload,
)
from tests.modules.data_validation.test_query_generation import make_rules


def _columns(*dates: tuple[str, str, str, str]) -> list[tuple[str, str, str, str]]:
    return [("row_id", "编号", "varchar", "Y"), ("amount", "实收金额", "numeric", ""), *dates]


def _parse(fields):
    rules, model = _rules_with_doc([
        _select_payload(),
        _generate_payload(expression={"left": "实收金额", "op": "eq", "right_type": "value", "right": 0}),
    ], fields=fields)
    candidate = rules.parse_rule_request(user(), _request())
    return candidate


def test_single_documented_period_is_adopted_without_field_name_hardcoding() -> None:
    fields = [
        {"field_name": "d_begdate", "field_cn": "项目开始日", "data_type": "date"},
        {"field_name": "d_cldate", "field_cn": "数据日期", "data_type": "date"},
    ]
    chosen, ordered = resolve_report_date(fields)
    assert chosen == "d_cldate"
    assert [item["field_name"] for item in ordered] == ["d_cldate", "d_begdate"]

    renamed = [
        {"field_name": "report_date", "field_cn": "成立日期", "data_type": "date"},
        {"field_name": "other_day", "field_cn": "报送日期", "data_type": "date"},
    ]
    chosen, _ = resolve_report_date(renamed)
    assert chosen == "other_day"


def test_explicit_valid_choice_is_preserved_even_with_multiple_candidates() -> None:
    fields = [
        {"field_name": "day_a", "field_cn": "业务日期", "data_type": "date"},
        {"field_name": "day_b", "field_cn": "数据日期", "data_type": "date"},
    ]
    chosen, _ = resolve_report_date(fields)
    assert chosen == ""
    chosen, _ = resolve_report_date(fields, explicit="day_b")
    assert chosen == "day_b"


def test_event_only_or_non_date_columns_keep_the_human_question() -> None:
    event_only = [{"field_name": "d_begdate", "field_cn": "项目开始日", "data_type": "date"}]
    chosen, ordered = resolve_report_date(event_only)
    assert chosen == "" and [item["field_name"] for item in ordered] == ["d_begdate"]

    timestamp_only = [{"field_name": "etl_time", "field_cn": "数据采集时间", "data_type": "timestamp"}]
    chosen, ordered = resolve_report_date(timestamp_only)
    assert chosen == "" and ordered == []


def test_service_auto_adopts_unique_main_and_related_periods() -> None:
    candidate = _parse(_columns(("d_begdate", "项目开始日", "date", ""), ("d_cldate", "数据日期", "date", "")))
    assert candidate["report_date_field"] == "d_cldate"
    assert "report_date_field" not in {item["id"] for item in candidate["questions"]}

    related, _model = make_rules(related=True)
    candidate = related.parse_rule_request(user(), _request(request_text="存续项目实收信托一般不为0"))
    assert candidate["join"]["report_date_field"] == "business_day"
    assert "join.report_date_field" not in {item["id"] for item in candidate["questions"]}


def test_service_keeps_questions_for_event_only_and_ambiguous_dates() -> None:
    event_only = _parse(_columns(("d_begdate", "项目开始日", "date", "")))
    assert event_only["report_date_field"] == ""
    question = next(item for item in event_only["questions"] if item["id"] == "report_date_field")
    assert [option["value"] for option in question["options"]] == ["d_begdate"]

    ambiguous = _parse(_columns(("d_begdate", "业务日期", "date", ""), ("d_enddate", "数据日期", "date", "")))
    assert ambiguous["report_date_field"] == ""
    question = next(item for item in ambiguous["questions"] if item["id"] == "report_date_field")
    assert {option["value"] for option in question["options"]} == {"d_begdate", "d_enddate"}
