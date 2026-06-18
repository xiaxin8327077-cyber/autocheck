from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Callable

from auto_check.engine.models import ValuationMatch, ValuationRow
from auto_check.engine.money import amounts_equal


def find_valuation_matches(
    rows: list[ValuationRow],
    target: Decimal,
    *,
    combination_rows: list[ValuationRow] | None = None,
    max_combination_rows: int = 50,
    max_combination_states: int = 50000,
    detect_ambiguous_combinations: bool = False,
    max_ambiguous_groups: int = 5,
    cancel_checker: Callable[[], None] | None = None,
) -> ValuationMatch:
    # 估值表金额匹配优先级：
    # 1. 单行 f_marketvalue 与目标差异完全相等。
    # 2. 同一个科目代码下多行 f_marketvalue 汇总后完全相等。
    # 3. 多个不同科目组合汇总后完全相等。
    # 4. 候选行过多时停止组合穷举，避免生产数据量大时页面卡死。
    for row in rows:
        if amounts_equal(row.market_value, target):
            return ValuationMatch(match_type="single", rows=[row])

    grouped_rows: dict[str, list[ValuationRow]] = defaultdict(list)
    for row in rows:
        grouped_rows[row.account_code].append(row)

    for account_rows in grouped_rows.values():
        total = sum((row.market_value for row in account_rows), Decimal("0"))
        if len(account_rows) > 1 and amounts_equal(total, target):
            return ValuationMatch(match_type="grouped", rows=account_rows)

    combination_candidates = rows if combination_rows is None else combination_rows

    if len(combination_candidates) > max_combination_rows:
        return ValuationMatch(
            match_type="combination_overflow",
            message=f"组合候选行数 {len(combination_candidates)} 超过上限 {max_combination_rows}",
        )

    if detect_ambiguous_combinations:
        best_match = _find_best_combination_match(
            combination_candidates,
            target,
            max_combination_states=max_combination_states,
            cancel_checker=cancel_checker,
        )
        if best_match.match_type != "combination":
            return best_match
        candidate_groups = _collect_combination_groups(
            combination_candidates,
            target,
            max_combination_states=max_combination_states,
            max_ambiguous_groups=max_ambiguous_groups,
            cancel_checker=cancel_checker,
        )
        if len(candidate_groups) > 1:
            return ValuationMatch(
                match_type="ambiguous_combination",
                rows=candidate_groups[0],
                message="候选不唯一",
                candidate_groups=candidate_groups,
            )
        return best_match

    return _find_best_combination_match(
        combination_candidates,
        target,
        max_combination_states=max_combination_states,
        cancel_checker=cancel_checker,
    )


def _find_best_combination_match(
    combination_candidates: list[ValuationRow],
    target: Decimal,
    *,
    max_combination_states: int,
    cancel_checker: Callable[[], None] | None,
) -> ValuationMatch:
    states: dict[Decimal, list[int]] = {Decimal("0"): []}
    best_match_indexes: list[int] | None = None
    for index, row in enumerate(combination_candidates):
        if cancel_checker is not None:
            cancel_checker()
        current_states = list(states.items())
        for total, indexes in current_states:
            new_total = total + row.market_value
            new_indexes = indexes + [index]
            if len(new_indexes) > 1 and amounts_equal(new_total, target):
                if best_match_indexes is None or _is_better_combination(new_indexes, best_match_indexes):
                    best_match_indexes = new_indexes
            current_indexes = states.get(new_total)
            if current_indexes is not None and not _is_better_combination(new_indexes, current_indexes):
                continue
            states[new_total] = new_indexes
            if len(states) > max_combination_states:
                if best_match_indexes is not None:
                    return ValuationMatch(
                        match_type="combination",
                        rows=[combination_candidates[i] for i in best_match_indexes],
                    )
                return ValuationMatch(
                    match_type="combination_overflow",
                    message=f"组合状态数 {len(states)} 超过上限 {max_combination_states}",
                )

    if best_match_indexes is not None:
        return ValuationMatch(match_type="combination", rows=[combination_candidates[i] for i in best_match_indexes])

    return ValuationMatch(match_type="none")


def _collect_combination_groups(
    combination_candidates: list[ValuationRow],
    target: Decimal,
    *,
    max_combination_states: int,
    max_ambiguous_groups: int,
    cancel_checker: Callable[[], None] | None,
) -> list[list[ValuationRow]]:
    states: dict[Decimal, list[list[int]]] = {Decimal("0"): [[]]}
    matched_indexes: list[list[int]] = []
    seen_matches: set[tuple[int, ...]] = set()
    max_groups = max(2, max_ambiguous_groups)

    for index, row in enumerate(combination_candidates):
        if cancel_checker is not None:
            cancel_checker()
        current_states = [(total, [group[:] for group in groups]) for total, groups in states.items()]
        for total, groups in current_states:
            new_total = total + row.market_value
            bucket = states.setdefault(new_total, [])
            for indexes in groups:
                new_indexes = indexes + [index]
                if len(new_indexes) > 1 and amounts_equal(new_total, target):
                    key = tuple(new_indexes)
                    if key not in seen_matches:
                        seen_matches.add(key)
                        _append_ranked_group(matched_indexes, new_indexes, max_groups)
                _append_ranked_group(bucket, new_indexes, max_groups)
            if len(states) > max_combination_states:
                return [
                    [combination_candidates[i] for i in group]
                    for group in matched_indexes[:max_ambiguous_groups]
                ]

    return [
        [combination_candidates[i] for i in group]
        for group in matched_indexes[:max_ambiguous_groups]
    ]


def _append_ranked_group(groups: list[list[int]], candidate: list[int], limit: int) -> None:
    key = tuple(candidate)
    if any(tuple(group) == key for group in groups):
        return
    groups.append(candidate)
    groups.sort(key=lambda group: (len(group), group))
    del groups[limit:]


def _is_better_combination(candidate: list[int], current: list[int]) -> bool:
    if len(candidate) != len(current):
        return len(candidate) < len(current)
    return candidate < current
