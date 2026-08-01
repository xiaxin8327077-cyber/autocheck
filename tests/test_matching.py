from decimal import Decimal
import time

import pytest

import auto_check.engine.matching as matching_module
from auto_check.engine.matching import find_valuation_matches
from auto_check.engine.models import ValuationRow


def row(code: str, value: str, name: str = "asset") -> ValuationRow:
    return ValuationRow(account_code=code, account_name=name, market_value=Decimal(value))


def test_finds_single_row_match_first():
    matches = find_valuation_matches([row("1001.01.01.01.0001", "5")], Decimal("5"))

    assert matches.match_type == "single"
    assert [matched.account_code for matched in matches.rows] == ["1001.01.01.01.0001"]


def test_finds_grouped_account_match_after_single_match_fails():
    rows = [row("1001.01.01.01.0001", "2"), row("1001.01.01.01.0001", "3")]

    matches = find_valuation_matches(rows, Decimal("5"))

    assert matches.match_type == "grouped"
    assert len(matches.rows) == 2


def test_finds_bounded_combination_match():
    rows = [
        row("1001.01.01.01.0001", "2"),
        row("1002.01.01.01.0002", "3"),
        row("1003.01.01.01.0003", "9"),
    ]

    matches = find_valuation_matches(rows, Decimal("5"), max_combination_rows=10)

    assert matches.match_type == "combination"
    assert [matched.market_value for matched in matches.rows] == [Decimal("2"), Decimal("3")]


def test_combination_prefers_fewer_rows_over_first_match():
    rows = [
        row("1001.01.01.01.0001", "2"),
        row("1002.01.01.01.0002", "3"),
        row("1003.01.01.01.0003", "5"),
        row("1004.01.01.01.0004", "8"),
    ]

    matches = find_valuation_matches(rows, Decimal("10"), max_combination_rows=10)

    assert matches.match_type == "combination"
    assert len(matches.rows) == 2
    assert {matched.market_value for matched in matches.rows} == {Decimal("2"), Decimal("8")}


def test_can_mark_ambiguous_when_multiple_combinations_match():
    rows = [
        row("2001.01.01.01.0001", "20", "Candidate A"),
        row("2002.01.01.01.0002", "30", "Candidate B"),
        row("2003.01.01.01.0003", "10", "Candidate C"),
        row("2004.01.01.01.0004", "40", "Candidate D"),
    ]

    matches = find_valuation_matches(
        rows,
        Decimal("50"),
        max_combination_rows=10,
        detect_ambiguous_combinations=True,
    )

    assert matches.match_type == "ambiguous_combination"
    assert matches.message == "候选不唯一"
    assert len(matches.candidate_groups) == 2
    assert [[row.account_name for row in group] for group in matches.candidate_groups] == [
        ["Candidate A", "Candidate B"],
        ["Candidate C", "Candidate D"],
    ]


def test_ambiguous_combination_details_are_capped_at_five_groups():
    rows = [
        row(f"2001.01.01.01.{index:04d}", "1", f"Candidate {index}")
        for index in range(12)
    ]

    matches = find_valuation_matches(
        rows,
        Decimal("2"),
        max_combination_rows=20,
        detect_ambiguous_combinations=True,
        max_ambiguous_groups=5,
    )

    assert matches.match_type == "ambiguous_combination"
    assert len(matches.candidate_groups) == 5


def test_ambiguous_combination_groups_keep_five_smallest_group_sizes():
    rows = [
        row("2001.01.01.01.0001", "20", "Candidate A"),
        row("2002.01.01.01.0002", "30", "Candidate B"),
        row("2003.01.01.01.0003", "50", "Candidate C"),
        row("2004.01.01.01.0004", "25", "Candidate D"),
        row("2005.01.01.01.0005", "35", "Candidate E"),
        row("2006.01.01.01.0006", "40", "Candidate F"),
        row("2007.01.01.01.0007", "45", "Candidate G"),
        row("2008.01.01.01.0008", "30", "Candidate H"),
        row("2009.01.01.01.0009", "60", "Candidate I"),
    ]

    matches = find_valuation_matches(
        rows,
        Decimal("100"),
        max_combination_rows=10,
        detect_ambiguous_combinations=True,
        max_ambiguous_groups=5,
    )

    assert matches.match_type == "ambiguous_combination"
    assert len(matches.candidate_groups) == 5
    assert [[row.account_name for row in group] for group in matches.candidate_groups][0] == [
        "Candidate F",
        "Candidate I",
    ]
    assert [len(group) for group in matches.candidate_groups] == [2, 3, 3, 3, 3]


def test_marks_combination_overflow_when_candidates_exceed_limit():
    rows = [row(f"1001.01.01.01.{index:04d}", "1") for index in range(12)]

    matches = find_valuation_matches(rows, Decimal("99"), max_combination_rows=10)

    assert matches.match_type == "combination_overflow"


def test_default_combination_limit_is_fifty_rows():
    rows = [row(f"1001.01.01.01.{index:04d}", "1") for index in range(51)]

    matches = find_valuation_matches(rows, Decimal("99"))

    assert matches.match_type == "combination_overflow"
    assert "超过上限 50" in matches.message


def test_marks_combination_overflow_when_subset_state_limit_is_reached():
    rows = [row(f"1001.01.01.01.{index:04d}", str(2 ** index)) for index in range(12)]

    matches = find_valuation_matches(rows, Decimal("999999"), max_combination_rows=50, max_combination_states=20)

    assert matches.match_type == "combination_overflow"
    assert "组合状态数" in matches.message


@pytest.mark.parametrize(
    ("solution_size", "target"),
    [
        (2, "3"),
        (3, "7"),
        (4, "15"),
        (5, "31"),
    ],
)
def test_large_candidate_pool_still_finds_two_to_five_row_matches(solution_size: int, target: str):
    solution_rows = [
        row(f"1001.01.01.01.S{index}", str(2 ** index), f"Solution {index}")
        for index in range(solution_size)
    ]
    filler_rows = [
        row(f"1002.01.01.01.F{index:03d}", str(1000 + index), f"Filler {index}")
        for index in range(74 - solution_size)
    ]

    matches = find_valuation_matches(
        filler_rows + list(reversed(solution_rows)),
        Decimal(target),
        max_combination_rows=50,
    )

    assert matches.match_type == "combination"
    assert [matched.account_code for matched in matches.rows] == [
        f"1001.01.01.01.S{index}" for index in reversed(range(solution_size))
    ]


def test_large_candidate_pool_keeps_ambiguity_protection_for_fast_matches():
    rows = [
        row("1001.01.01.01.A", "20", "Candidate A"),
        row("1001.01.01.01.B", "30", "Candidate B"),
        row("1001.01.01.01.C", "10", "Candidate C"),
        row("1001.01.01.01.D", "40", "Candidate D"),
    ] + [
        row(f"1002.01.01.01.F{index:03d}", str(1000 + index), f"Filler {index}")
        for index in range(70)
    ]

    matches = find_valuation_matches(
        rows,
        Decimal("50"),
        max_combination_rows=50,
        detect_ambiguous_combinations=True,
    )

    assert matches.match_type == "ambiguous_combination"
    assert [[item.account_name for item in group] for group in matches.candidate_groups] == [
        ["Candidate A", "Candidate B"],
        ["Candidate C", "Candidate D"],
    ]


def test_combination_result_preserves_candidate_input_order():
    rows = [
        row("1001.01.01.01.C", "4"),
        row("1001.01.01.01.A", "1"),
        row("1001.01.01.01.B", "2"),
        row("1001.01.01.01.Z", "100"),
    ]

    first = find_valuation_matches(rows, Decimal("7"))
    assert first.match_type == "combination"
    assert [item.account_code for item in first.rows] == [
        "1001.01.01.01.C",
        "1001.01.01.01.A",
        "1001.01.01.01.B",
    ]


def test_bounded_deep_search_can_find_six_to_ten_row_match():
    rows = [
        row(f"1001.01.01.01.S{index}", str(2 ** index), f"Solution {index}")
        for index in range(8)
    ] + [
        row(f"1002.01.01.01.F{index}", str(1000 + index), f"Filler {index}")
        for index in range(4)
    ]

    matches = find_valuation_matches(rows, Decimal("255"), max_combination_size=10)

    assert matches.match_type == "combination"
    assert len(matches.rows) == 8


def test_combination_search_returns_timeout_after_deadline():
    rows = [row(f"1001.01.01.01.{index:04d}", str(1000 + index)) for index in range(20)]

    matches = find_valuation_matches(
        rows,
        Decimal("999999"),
        deadline=time.perf_counter() - 1,
    )

    assert matches.match_type == "combination_timeout"
    assert "时间上限" in matches.message


def test_combination_search_reports_stage_and_periodic_heartbeat(monkeypatch):
    clock = {"now": 100.0}

    def fake_perf_counter():
        clock["now"] += 1.0
        return clock["now"]

    monkeypatch.setattr(matching_module.time, "perf_counter", fake_perf_counter)
    messages = []
    rows = [row(f"1001.01.01.01.{index:04d}", str(1000 + index)) for index in range(12)]

    find_valuation_matches(
        rows,
        Decimal("999999"),
        deadline=1000.0,
        progress_callback=messages.append,
    )

    assert any("2～5条快速组合匹配" in message for message in messages)
    assert any(
        "组合匹配进行中" in message
        and "候选=12行" in message
        and "组合状态=" in message
        and "本次搜索已耗时=" in message
        and "项目剩余=" in message
        for message in messages
    )


def test_large_combination_can_match_an_entire_positive_natural_group():
    rows = [
        row(f"1001.01.01.01.S{index:02d}", str(index + 1), f"Asset {index}")
        for index in range(30)
    ]

    matches = find_valuation_matches(rows, sum((item.market_value for item in rows), Decimal("0")))

    assert matches.match_type == "combination"
    assert len(matches.rows) == 30


@pytest.mark.parametrize("solution_size", [20, 25])
def test_large_combination_uses_small_excluded_complement(solution_size: int):
    solution_rows = [
        row(f"1001.01.01.01.S{index:02d}", "1", f"Solution {index}")
        for index in range(solution_size)
    ]
    excluded_rows = [
        row(f"1001.01.01.01.X{index:02d}", str(1000 + index), f"Excluded {index}")
        for index in range(30 - solution_size)
    ]
    target = sum((item.market_value for item in solution_rows), Decimal("0"))

    matches = find_valuation_matches(solution_rows + excluded_rows, target)

    assert matches.match_type == "combination"
    assert [item.account_code for item in matches.rows] == [item.account_code for item in solution_rows]
