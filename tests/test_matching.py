from decimal import Decimal

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
