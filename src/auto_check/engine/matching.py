from __future__ import annotations

import time
from bisect import bisect_right
from collections import defaultdict
from decimal import Decimal
from typing import Callable

from auto_check.engine.models import ValuationMatch, ValuationRow
from auto_check.engine.money import amounts_equal


class _CombinationTimeout(RuntimeError):
    def __init__(self, searched_size: int):
        self.searched_size = searched_size


class _CombinationStateOverflow(RuntimeError):
    def __init__(self, state_count: int):
        self.state_count = state_count


class _SearchBudget:
    def __init__(
        self,
        *,
        deadline: float | None,
        max_states: int,
        cancel_checker: Callable[[], None] | None,
        progress_callback: Callable[[str], None] | None,
        candidate_count: int,
        heartbeat_seconds: float,
    ) -> None:
        self.deadline = deadline
        self.max_states = max_states
        self.cancel_checker = cancel_checker
        self.progress_callback = progress_callback
        self.candidate_count = candidate_count
        self.heartbeat_seconds = max(0.0, heartbeat_seconds)
        self.state_count = 0
        self.stage = "准备组合匹配"
        self.started_at = time.perf_counter()
        self.last_heartbeat_at = self.started_at

    def set_stage(self, stage: str, *, announce: bool = False) -> None:
        self.stage = stage
        if announce and self.progress_callback is not None:
            self.progress_callback(
                f"进入{stage}：候选={self.candidate_count}行，当前组合状态={self.state_count}"
            )

    def check(self, searched_size: int) -> None:
        if self.cancel_checker is not None:
            self.cancel_checker()
        now = time.perf_counter()
        if self.deadline is not None and now >= self.deadline:
            raise _CombinationTimeout(searched_size)
        if (
            self.progress_callback is not None
            and now - self.last_heartbeat_at >= self.heartbeat_seconds
        ):
            message = (
                f"组合匹配进行中：{self.stage}，候选={self.candidate_count}行，"
                f"组合状态={self.state_count}，本次搜索已耗时={now - self.started_at:.1f}s"
            )
            if self.deadline is not None:
                message += f"，项目剩余={max(0.0, self.deadline - now):.1f}s"
            self.progress_callback(message)
            self.last_heartbeat_at = now

    def add_states(self, count: int, searched_size: int) -> None:
        self.state_count += count
        if self.state_count > self.max_states:
            raise _CombinationStateOverflow(self.state_count)
        self.check(searched_size)


def find_valuation_matches(
    rows: list[ValuationRow],
    target: Decimal,
    *,
    combination_rows: list[ValuationRow] | None = None,
    max_combination_rows: int = 50,
    max_combination_states: int = 500000,
    max_combination_size: int = 30,
    detect_ambiguous_combinations: bool = False,
    max_ambiguous_groups: int = 5,
    cancel_checker: Callable[[], None] | None = None,
    deadline: float | None = None,
    progress_callback: Callable[[str], None] | None = None,
    heartbeat_seconds: float = 5.0,
) -> ValuationMatch:
    # 估值表金额匹配优先级保持不变：单行、同科目汇总、少行数组合、深层组合。
    # 候选行阈值限制 6～30 行深层搜索；2～5 行快速层可处理更大的候选池。
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
    stable_candidates = _stable_candidates(combination_candidates)
    group_limit = max(2, max_ambiguous_groups) if detect_ambiguous_combinations else 1
    budget = _SearchBudget(
        deadline=deadline,
        max_states=max_combination_states,
        cancel_checker=cancel_checker,
        progress_callback=progress_callback,
        candidate_count=len(stable_candidates),
        heartbeat_seconds=heartbeat_seconds,
    )

    try:
        budget.check(1)
        budget.set_stage("2～5条快速组合匹配（当前2条）", announce=True)
        matched_indexes, searched_size = _find_fast_combination_indexes(
            stable_candidates,
            target,
            max_size=min(5, max_combination_size),
            group_limit=group_limit,
            budget=budget,
        )

        if matched_indexes and (
            not detect_ambiguous_combinations or len(matched_indexes) >= group_limit
        ):
            return _combination_result(stable_candidates, matched_indexes, max_ambiguous_groups)

        candidate_total = sum((row.market_value for row in stable_candidates), Decimal("0"))
        if (
            6 <= len(stable_candidates) <= max_combination_size
            and amounts_equal(candidate_total, target)
            and (
                all(row.market_value > 0 for row in stable_candidates)
                or all(row.market_value < 0 for row in stable_candidates)
            )
        ):
            return ValuationMatch(match_type="combination", rows=stable_candidates)

        if len(stable_candidates) > max_combination_rows:
            if matched_indexes:
                return _combination_result(stable_candidates, matched_indexes, max_ambiguous_groups)
            return ValuationMatch(
                match_type="combination_overflow",
                message=f"组合候选行数 {len(stable_candidates)} 超过上限 {max_combination_rows}",
            )

        if max_combination_size >= 6 and len(matched_indexes) < group_limit:
            _find_deep_combination_indexes(
                stable_candidates,
                target,
                min_size=6,
                max_size=min(max_combination_size, len(stable_candidates)),
                matched_indexes=matched_indexes,
                group_limit=group_limit,
                budget=budget,
            )
            searched_size = min(max_combination_size, len(stable_candidates))

        if matched_indexes:
            return _combination_result(stable_candidates, matched_indexes, max_ambiguous_groups)
        return ValuationMatch(match_type="none")
    except _CombinationTimeout as exc:
        return ValuationMatch(
            match_type="combination_timeout",
            message=f"组合匹配达到时间上限，已搜索至 {max(searched_size if 'searched_size' in locals() else 1, exc.searched_size)} 行组合",
        )
    except _CombinationStateOverflow as exc:
        return ValuationMatch(
            match_type="combination_overflow",
            message=f"组合状态数 {exc.state_count} 超过上限 {max_combination_states}",
        )


def _stable_candidates(rows: list[ValuationRow]) -> list[ValuationRow]:
    # 保留仓储层返回顺序，避免改变既有具体原因编号和详情表顺序。
    return list(rows)


def _find_fast_combination_indexes(
    rows: list[ValuationRow],
    target: Decimal,
    *,
    max_size: int,
    group_limit: int,
    budget: _SearchBudget,
) -> tuple[list[tuple[int, ...]], int]:
    matched: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    count = len(rows)
    if count < 2 or max_size < 2:
        return matched, 1

    pair_sums: dict[Decimal, list[tuple[int, int]]] = defaultdict(list)
    searched_size = 2
    for first in range(count - 1):
        budget.check(2)
        for second in range(first + 1, count):
            pair = (first, second)
            pair_total = rows[first].market_value + rows[second].market_value
            pair_sums[pair_total].append(pair)
            budget.add_states(1, 2)
            if amounts_equal(pair_total, target):
                _append_match(matched, seen, pair, group_limit)
                if len(matched) >= group_limit:
                    return matched, searched_size

    if max_size >= 3 and count >= 3:
        searched_size = 3
        budget.set_stage("2～5条快速组合匹配（当前3条）")
        for first in range(count - 2):
            budget.check(3)
            pairs = pair_sums.get(target - rows[first].market_value, [])
            start = bisect_right(pairs, (first, count))
            for pair_index, (second, third) in enumerate(pairs[start:], start=1):
                if pair_index % 256 == 0:
                    budget.check(3)
                _append_match(matched, seen, (first, second, third), group_limit)
                if len(matched) >= group_limit:
                    return matched, searched_size

    if max_size >= 4 and count >= 4:
        searched_size = 4
        budget.set_stage("2～5条快速组合匹配（当前4条）")
        for pair_total, left_pairs in pair_sums.items():
            budget.check(4)
            right_pairs = pair_sums.get(target - pair_total, [])
            if not right_pairs:
                continue
            for first, second in left_pairs:
                start = bisect_right(right_pairs, (second, count))
                for pair_index, (third, fourth) in enumerate(right_pairs[start:], start=1):
                    if pair_index % 256 == 0:
                        budget.check(4)
                    _append_match(matched, seen, (first, second, third, fourth), group_limit)
                    if len(matched) >= group_limit:
                        return matched, searched_size

    if max_size >= 5 and count >= 5:
        searched_size = 5
        budget.set_stage("2～5条快速组合匹配（当前5条）")
        for first in range(count - 4):
            budget.check(5)
            for second in range(first + 1, count - 3):
                first_two = rows[first].market_value + rows[second].market_value
                for third in range(second + 1, count - 2):
                    if third % 64 == 0:
                        budget.check(5)
                    remaining = target - first_two - rows[third].market_value
                    pairs = pair_sums.get(remaining, [])
                    start = bisect_right(pairs, (third, count))
                    for pair_index, (fourth, fifth) in enumerate(pairs[start:], start=1):
                        if pair_index % 256 == 0:
                            budget.check(5)
                        _append_match(matched, seen, (first, second, third, fourth, fifth), group_limit)
                        if len(matched) >= group_limit:
                            return matched, searched_size

    return matched, searched_size


def _find_deep_combination_indexes(
    rows: list[ValuationRow],
    target: Decimal,
    *,
    min_size: int,
    max_size: int,
    matched_indexes: list[tuple[int, ...]],
    group_limit: int,
    budget: _SearchBudget,
) -> None:
    if min_size > max_size:
        return

    values = [row.market_value for row in rows]
    min_sums, max_sums = _suffix_sum_bounds(values, max_size)
    seen = set(matched_indexes)
    total = sum(values, Decimal("0"))

    for size in _deep_cardinality_order(len(rows), min_size, max_size):
        budget.check(size)
        inverted = size > len(rows) // 2
        search_size = len(rows) - size if inverted else size
        search_target = total - target if inverted else target
        if 6 <= size <= 10:
            stage = f"6～10条剪枝搜索（当前{size}条）"
        elif 20 <= size <= 30 and inverted:
            stage = f"20～30条反向补集搜索（目标{size}条，排除{search_size}条）"
        elif 20 <= size <= 30:
            stage = f"20～30条有界搜索（当前{size}条）"
        else:
            stage = f"深层有界搜索（当前{size}条）"
        budget.set_stage(stage, announce=True)
        if search_size == 0:
            if amounts_equal(search_target, Decimal("0")):
                _append_match(matched_indexes, seen, tuple(range(len(rows))), group_limit)
            if len(matched_indexes) >= group_limit:
                return
            continue

        failed_states: set[tuple[int, int, Decimal]] = set()
        local_matches: list[tuple[int, ...]] = []
        local_seen: set[tuple[int, ...]] = set()

        def search(start: int, needed: int, remaining: Decimal, path: tuple[int, ...]) -> bool:
            budget.add_states(1, size)
            if needed == 0:
                if amounts_equal(remaining, Decimal("0")):
                    _append_match(local_matches, local_seen, path, group_limit)
                    return True
                return False
            if len(rows) - start < needed:
                return False

            minimum = min_sums[start][needed]
            maximum = max_sums[start][needed]
            if minimum is None or maximum is None or remaining < minimum or remaining > maximum:
                return False

            state = (start, needed, remaining)
            if state in failed_states:
                return False

            found = False
            last_start = len(rows) - needed
            for index in range(start, last_start + 1):
                next_remaining = remaining - values[index]
                next_minimum = min_sums[index + 1][needed - 1]
                next_maximum = max_sums[index + 1][needed - 1]
                if next_minimum is None or next_maximum is None:
                    continue
                if next_remaining < next_minimum or next_remaining > next_maximum:
                    continue
                if search(index + 1, needed - 1, next_remaining, path + (index,)):
                    found = True
                    if len(local_matches) >= group_limit:
                        return True

            if not found:
                failed_states.add(state)
            return found

        search(0, search_size, search_target, ())
        for indexes in local_matches:
            candidate = _complement_indexes(len(rows), indexes) if inverted else indexes
            _append_match(matched_indexes, seen, candidate, group_limit)
        if len(matched_indexes) >= group_limit:
            return


def _deep_cardinality_order(candidate_count: int, min_size: int, max_size: int) -> list[int]:
    sizes = set(range(min_size, max_size + 1))
    common_sizes = [size for size in range(6, 11) if size in sizes]
    large_sizes = sorted(
        (size for size in sizes if 20 <= size <= 30),
        key=lambda size: (candidate_count - size if size > candidate_count // 2 else size, size),
    )
    medium_sizes = [size for size in range(11, 20) if size in sizes]
    remaining_sizes = sorted(sizes - set(common_sizes) - set(large_sizes) - set(medium_sizes))
    return common_sizes + large_sizes + medium_sizes + remaining_sizes


def _complement_indexes(candidate_count: int, excluded: tuple[int, ...]) -> tuple[int, ...]:
    excluded_set = set(excluded)
    return tuple(index for index in range(candidate_count) if index not in excluded_set)


def _suffix_sum_bounds(
    values: list[Decimal],
    max_size: int,
) -> tuple[list[list[Decimal | None]], list[list[Decimal | None]]]:
    count = len(values)
    minimums: list[list[Decimal | None]] = [[None] * (max_size + 1) for _ in range(count + 1)]
    maximums: list[list[Decimal | None]] = [[None] * (max_size + 1) for _ in range(count + 1)]
    minimums[count][0] = Decimal("0")
    maximums[count][0] = Decimal("0")

    for index in range(count - 1, -1, -1):
        minimums[index][0] = Decimal("0")
        maximums[index][0] = Decimal("0")
        for size in range(1, max_size + 1):
            min_options: list[Decimal] = []
            max_options: list[Decimal] = []
            if minimums[index + 1][size] is not None:
                min_options.append(minimums[index + 1][size])
                max_options.append(maximums[index + 1][size])
            if minimums[index + 1][size - 1] is not None:
                min_options.append(values[index] + minimums[index + 1][size - 1])
                max_options.append(values[index] + maximums[index + 1][size - 1])
            if min_options:
                minimums[index][size] = min(min_options)
                maximums[index][size] = max(max_options)

    return minimums, maximums


def _append_match(
    matched: list[tuple[int, ...]],
    seen: set[tuple[int, ...]],
    candidate: tuple[int, ...],
    limit: int,
) -> None:
    if candidate in seen:
        return
    seen.add(candidate)
    matched.append(candidate)
    matched.sort(key=lambda indexes: (len(indexes), indexes))
    del matched[limit:]


def _combination_result(
    rows: list[ValuationRow],
    matched_indexes: list[tuple[int, ...]],
    max_ambiguous_groups: int,
) -> ValuationMatch:
    ranked_indexes = sorted(matched_indexes, key=lambda indexes: (len(indexes), indexes))
    candidate_groups = [[rows[index] for index in indexes] for indexes in ranked_indexes]
    if len(candidate_groups) > 1:
        displayed_groups = candidate_groups[:max(1, max_ambiguous_groups)]
        return ValuationMatch(
            match_type="ambiguous_combination",
            rows=displayed_groups[0],
            message="候选不唯一",
            candidate_groups=displayed_groups,
        )
    return ValuationMatch(match_type="combination", rows=candidate_groups[0])
